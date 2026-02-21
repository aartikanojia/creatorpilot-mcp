"""
Video Resolver — fuzzy title matching for user video queries.

Resolves a user-provided title fragment to a specific video in the DB
using string normalization and fuzzy matching. No network calls,
no LLM involvement — purely local string similarity.

Phase 0.2B hardening:
  - NFKD unicode normalization
  - Hashtag removal
  - Tiered ambiguity detection (accepted / ambiguous / rejected)
  - Resolution metadata on every return
"""

import logging
import re
import unicodedata
from typing import Optional
from uuid import UUID

from memory.postgres_store import PostgresMemoryStore

logger = logging.getLogger(__name__)

# ── Matching thresholds ─────────────────────────────────────────────────────
# These are the ONLY places these values are defined.
MATCH_THRESHOLD = 70          # Minimum score to consider any match
HIGH_CONFIDENCE_THRESHOLD = 85  # Accept without gap check
AMBIGUITY_GAP = 10            # Minimum gap between top two scores

# ── Emoji removal regex ─────────────────────────────────────────────────────
_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U00002702-\U000027B0"  # dingbats
    "\U0000FE00-\U0000FE0F"  # variation selectors
    "\U0001F900-\U0001F9FF"  # supplemental symbols
    "\U0001FA00-\U0001FA6F"  # chess symbols
    "\U0001FA70-\U0001FAFF"  # symbols extended-A
    "\U00002600-\U000026FF"  # misc symbols
    "\U0000200D"             # zero-width joiner
    "]+",
    flags=re.UNICODE,
)

# ── Hashtag removal regex ───────────────────────────────────────────────────
_HASHTAG_PATTERN = re.compile(r"#\w+", flags=re.UNICODE)

# ── Fuzzy matching backend ──────────────────────────────────────────────────
try:
    from rapidfuzz import fuzz as _fuzz

    def _similarity(a: str, b: str) -> float:
        """
        Return 0-100 similarity score using the best of three strategies.

        Strategies:
          - token_sort_ratio:  order-independent word matching
          - token_set_ratio:   handles extra/missing words gracefully
          - partial_ratio:     substring matching for fragments

        The max is chosen to prevent penalty from extra hashtags,
        emojis, reordered words, or trailing suffixes.
        """
        ratio = _fuzz.ratio(a, b)
        token_set = _fuzz.token_set_ratio(a, b)
        token_sort = _fuzz.token_sort_ratio(a, b)
        # Only use partial_ratio when shortest string is long enough
        # to avoid inflated scores for very short queries like "the"
        shorter = min(len(a), len(b))
        partial = _fuzz.partial_ratio(a, b) if shorter > 4 else 0.0
        chosen = max(token_set, partial, token_sort)
        logger.debug(
            f"[VideoResolver] ratio: {ratio:.1f}, "
            f"token_set: {token_set:.1f}, partial: {partial:.1f}, "
            f"token_sort: {token_sort:.1f}, chosen_score: {chosen:.1f}"
        )
        return chosen

    logger.debug("Video resolver using rapidfuzz backend (multi-strategy)")

except ImportError:
    from difflib import SequenceMatcher

    def _similarity(a: str, b: str) -> float:
        """Return 0-100 similarity score using difflib (fallback)."""
        seq_score = SequenceMatcher(None, a, b).ratio() * 100
        # Simple token-set approach for difflib fallback
        tokens_a = set(a.split())
        tokens_b = set(b.split())
        if tokens_a and tokens_b:
            intersection = tokens_a & tokens_b
            union = tokens_a | tokens_b
            jaccard = (len(intersection) / len(union)) * 100
            return max(seq_score, jaccard)
        return seq_score

    logger.debug("Video resolver using difflib fallback (rapidfuzz not installed)")


# ── String normalizer ───────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """
    Normalize a string for comparison.

    Steps:
      1. Lowercase
      2. NFKD unicode normalization (decompose ligatures/accents)
      3. Remove emojis
      4. Remove hashtags (#shorts, #viral, etc.)
      5. Remove punctuation (keep alphanumeric + spaces)
      6. Collapse whitespace
      7. Trim leading/trailing spaces
    """
    text = text.lower()
    text = unicodedata.normalize("NFKD", text)
    text = _EMOJI_PATTERN.sub("", text)
    text = _HASHTAG_PATTERN.sub("", text)
    # Remove punctuation: keep letters, digits, whitespace
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ── Decision logic ──────────────────────────────────────────────────────────

def _decide(top_score: float, second_score: float) -> str:
    """
    Determine match decision based on tiered thresholds.

    Rules:
      - top_score >= 85          → accepted
      - 70 <= top_score < 85
          gap >= 10              → accepted
          gap < 10               → ambiguous
      - top_score < 70           → rejected

    Args:
        top_score:    Highest similarity score.
        second_score: Second-highest similarity score.

    Returns:
        "accepted", "ambiguous", or "rejected"
    """
    if top_score >= HIGH_CONFIDENCE_THRESHOLD:
        return "accepted"

    if top_score >= MATCH_THRESHOLD:
        gap = top_score - second_score
        if gap >= AMBIGUITY_GAP:
            return "accepted"
        return "ambiguous"

    return "rejected"


# ── Public API ──────────────────────────────────────────────────────────────

def resolve_video_by_title(
    channel_id: UUID,
    title_fragment: str,
) -> Optional[dict]:
    """
    Resolve a title fragment to a specific video for the given channel.

    Queries the persistent `videos` table (populated by analytics ingestion).

    1. Fetch last 100 videos for channel from DB.
    2. Normalize strings (lowercase, NFKD, strip emojis/hashtags/punct).
    3. Compute fuzzy similarity score for each video title.
    4. Apply tiered decision logic (accepted / ambiguous / rejected).
    5. Return match dict with resolution metadata.

    Args:
        channel_id: UUID of the channel.
        title_fragment: User-provided title text (may be partial / misspelled).

    Returns:
        On accepted: dict with video_id, title, score, video_resolution.
        On ambiguous/rejected: dict with clarification=True,
            message, candidates, video_resolution.
        On empty DB / empty fragment: None.
    """
    store = PostgresMemoryStore()
    videos = store.get_recent_videos(channel_id, limit=100)

    video_count = len(videos)
    logger.info(f"[VideoResolver] Videos in DB: {video_count}")

    if not videos:
        logger.info(f"[VideoResolver] No videos found in DB for channel {channel_id}")
        return None

    normalized_fragment = _normalize(title_fragment)
    if not normalized_fragment:
        logger.warning("[Resolver] Title fragment is empty after normalization")
        return None

    # Score all videos
    scored: list[dict] = []
    for video in videos:
        title = video.title or ""
        normalized_title = _normalize(title)
        if not normalized_title:
            continue

        score = _similarity(normalized_fragment, normalized_title)
        scored.append({
            "video_id": video.youtube_video_id,
            "title": video.title,
            "score": round(score, 1),
        })

    if not scored:
        return None

    # Sort descending by score
    scored.sort(key=lambda x: x["score"], reverse=True)

    top = scored[0]
    top_score = top["score"]
    second_score = scored[1]["score"] if len(scored) > 1 else 0.0

    decision = _decide(top_score, second_score)

    resolution_metadata = {
        "top_score": top_score,
        "second_score": second_score,
        "decision": decision,
    }

    if decision == "accepted":
        logger.info(
            f"[VideoResolver] Match accepted: \"{top['title']}\" "
            f"(score: {top_score}, gap: {top_score - second_score:.1f})"
        )
        return {
            "video_id": top["video_id"],
            "title": top["title"],
            "score": top_score,
            "video_resolution": resolution_metadata,
        }

    # Ambiguous or rejected → return clarification
    candidates = scored[:3]
    label = "ambiguous" if decision == "ambiguous" else "rejected"
    logger.info(
        f"[VideoResolver] Match {label} — "
        f"top: {top_score}, second: {second_score}, "
        f"gap: {top_score - second_score:.1f}"
    )

    msg = "I found a few similar videos. Did you mean:\n"
    for i, c in enumerate(candidates, 1):
        msg += f"  {i}. {c['title']} ({c['score']}%)\n"

    return {
        "clarification": True,
        "message": msg,
        "candidates": candidates,
        "video_resolution": resolution_metadata,
    }


def get_top_matches(
    channel_id: UUID,
    title_fragment: str,
    limit: int = 3,
) -> list[dict]:
    """
    Return the top N video matches with similarity scores.

    Used to generate the clarification prompt when no confident match
    is found.

    Args:
        channel_id: UUID of the channel.
        title_fragment: User-provided title text.
        limit: Number of top matches to return (default: 3).

    Returns:
        List of dicts [{video_id, title, score}, ...] sorted by score desc.
    """
    store = PostgresMemoryStore()
    videos = store.get_recent_videos(channel_id, limit=100)

    if not videos:
        return []

    normalized_fragment = _normalize(title_fragment)
    if not normalized_fragment:
        return []

    scored = []
    for video in videos:
        title = video.title or ""
        normalized_title = _normalize(title)
        if not normalized_title:
            continue

        score = _similarity(normalized_fragment, normalized_title)
        scored.append({
            "video_id": video.youtube_video_id,
            "title": video.title,
            "score": round(score, 1),
        })

    # Sort by score descending
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]


def get_video_count(channel_id: UUID) -> int:
    """
    Return the number of videos in the DB for a channel.

    Used by the executor to decide whether to trigger a cold-start
    YouTube fetch (only when count == 0).

    Args:
        channel_id: UUID of the channel.

    Returns:
        Number of videos in the videos table for this channel.
    """
    store = PostgresMemoryStore()
    videos = store.get_recent_videos(channel_id, limit=1)
    return len(videos)


def get_latest_video_from_db(
    channel_id: UUID,
    offset: int = 0,
) -> Optional[dict]:
    """
    Return the Nth most recent video from the DB (by published_at).

    Used for relative queries like "last video", "latest video".
    Skips the fuzzy resolver entirely — no normalization or scoring.

    Args:
        channel_id: UUID of the channel.
        offset: 0 = most recent, 1 = second most recent, etc.

    Returns:
        dict with video_id, title, score=100 (exact), video_resolution
        or None if no videos exist.
    """
    store = PostgresMemoryStore()
    videos = store.get_recent_videos(channel_id, limit=offset + 1)

    if len(videos) <= offset:
        logger.info(
            f"[VideoResolver] No video at offset={offset} "
            f"(only {len(videos)} videos in DB)"
        )
        return None

    video = videos[offset]
    logger.info(
        f"[VideoResolver] Relative lookup: offset={offset} → "
        f"\"{video.title}\" ({video.youtube_video_id})"
    )
    return {
        "video_id": video.youtube_video_id,
        "title": video.title,
        "score": 100.0,
        "video_resolution": {
            "top_score": 100.0,
            "second_score": 0.0,
            "decision": "accepted",
        },
    }
