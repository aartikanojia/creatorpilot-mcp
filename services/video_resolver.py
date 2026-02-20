"""
Video Resolver — fuzzy title matching for user video queries.

Resolves a user-provided title fragment to a specific video in the DB
using string normalization and fuzzy matching. No network calls,
no LLM involvement — purely local string similarity.
"""

import logging
import re
import unicodedata
from typing import Optional
from uuid import UUID

from memory.postgres_store import PostgresMemoryStore

logger = logging.getLogger(__name__)

# ── Matching threshold ──────────────────────────────────────────────────────
# A score >= MATCH_THRESHOLD is considered an accepted match.
# This is the ONLY place this value is defined.
MATCH_THRESHOLD = 70

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

# ── Fuzzy matching backend ──────────────────────────────────────────────────
try:
    from rapidfuzz import fuzz as _fuzz

    def _similarity(a: str, b: str) -> float:
        """Return 0-100 similarity score using rapidfuzz."""
        return _fuzz.token_sort_ratio(a, b)

    logger.debug("Video resolver using rapidfuzz backend")

except ImportError:
    from difflib import SequenceMatcher

    def _similarity(a: str, b: str) -> float:
        """Return 0-100 similarity score using difflib (fallback)."""
        return SequenceMatcher(None, a, b).ratio() * 100

    logger.debug("Video resolver using difflib fallback (rapidfuzz not installed)")


# ── String normalizer ───────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """
    Normalize a string for comparison.

    Steps:
      1. Lowercase
      2. Remove emojis
      3. Remove punctuation (keep alphanumeric + spaces)
      4. Collapse whitespace
    """
    text = text.lower()
    text = _EMOJI_PATTERN.sub("", text)
    # Remove punctuation: keep letters, digits, whitespace
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ── Public API ──────────────────────────────────────────────────────────────

def resolve_video_by_title(
    channel_id: UUID,
    title_fragment: str,
) -> Optional[dict]:
    """
    Resolve a title fragment to a specific video for the given channel.

    Queries the persistent `videos` table (populated by analytics ingestion).

    1. Fetch last 100 videos for channel from DB.
    2. Normalize strings (lowercase, strip emojis/punctuation, collapse ws).
    3. Compute fuzzy similarity score for each video title.
    4. If best match score >= MATCH_THRESHOLD → return video dict.
    5. Otherwise → return None.

    Args:
        channel_id: UUID of the channel.
        title_fragment: User-provided title text (may be partial / misspelled).

    Returns:
        Dict with video_id, title, score — or None if no match.
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

    best_match = None
    best_score = 0.0

    for video in videos:
        title = video.title or ""
        normalized_title = _normalize(title)
        if not normalized_title:
            continue

        score = _similarity(normalized_fragment, normalized_title)

        if score > best_score:
            best_score = score
            best_match = video

    if best_match and best_score >= MATCH_THRESHOLD:
        logger.info(
            f"[VideoResolver] Match accepted: \"{best_match.title}\" "
            f"(score: {best_score:.1f}, threshold: {MATCH_THRESHOLD})"
        )
        return {
            "video_id": best_match.youtube_video_id,
            "title": best_match.title,
            "score": round(best_score, 1),
        }

    logger.info(
        f"[VideoResolver] Match rejected — best score {best_score:.1f} "
        f"< threshold {MATCH_THRESHOLD}"
    )
    return None


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
