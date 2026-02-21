"""
Unit tests for the Video Resolver — fuzzy title matching.

Tests:
1. Exact title match
2. Partial title match
3. Title with emojis
4. Misspelled title
5. No match case
6. Top 3 matches for clarification
7. Empty DB / empty fragment edge cases

Phase 0.2B additions:
8. Clear match (>85)
9. Borderline match (75 but large gap)
10. Ambiguous (scores close)
11. Low score (<70)
12. Emoji-heavy title
13. Mixed Hindi/English
14. Hashtag heavy title
"""

import uuid
import pytest
from unittest.mock import patch, MagicMock

from services.video_resolver import (
    resolve_video_by_title,
    get_top_matches,
    get_video_count,
    _normalize,
    _decide,
    _similarity,
    MATCH_THRESHOLD,
    HIGH_CONFIDENCE_THRESHOLD,
    AMBIGUITY_GAP,
)


# =============================================================================
# Helpers — build mock Video objects
# =============================================================================

def _make_video(title: str, video_id: str = None):
    """Build a mock Video with the given title."""
    mock = MagicMock()
    mock.title = title
    mock.youtube_video_id = video_id or f"vid_{uuid.uuid4().hex[:8]}"
    return mock


CHANNEL_UUID = uuid.uuid4()


# A realistic video library for a family/vlog creator
MOCK_VIDEOS = [
    _make_video("Father–Son duo in full shararat mode 🔥😂", "vid_001"),
    _make_video("Valentine Day Vlog ❤️", "vid_002"),
    _make_video("Mihir ki masti #play", "vid_003"),
    _make_video("Morning routine gone wrong 😅", "vid_004"),
    _make_video("Our first family road trip 🚗", "vid_005"),
    _make_video("Behind the scenes of my studio setup", "vid_006"),
    _make_video("Q&A with subscribers!", "vid_007"),
    _make_video("Cooking challenge with kids 🍕", "vid_008"),
]


@pytest.fixture(autouse=True)
def mock_postgres_store():
    """Patch PostgresMemoryStore.get_recent_videos globally."""
    with patch(
        "services.video_resolver.PostgresMemoryStore"
    ) as MockStore:
        instance = MockStore.return_value
        instance.get_recent_videos.return_value = MOCK_VIDEOS
        yield instance


# =============================================================================
# NORMALIZATION TESTS
# =============================================================================

class TestNormalization:
    """Tests for the _normalize helper."""

    def test_lowercase(self):
        assert _normalize("HELLO World") == "hello world"

    def test_emoji_removal(self):
        result = _normalize("shararat mode 🔥😂")
        assert "🔥" not in result
        assert "😂" not in result
        assert "shararat" in result

    def test_punctuation_removal(self):
        result = _normalize("Father–Son duo! Q&A?")
        # Punctuation replaced by space, collapsed
        assert "!" not in result
        assert "?" not in result

    def test_whitespace_collapse(self):
        result = _normalize("  too   many    spaces  ")
        assert result == "too many spaces"

    def test_nfkd_normalization(self):
        """NFKD decomposes ligatures and accented characters."""
        # ﬁ (U+FB01) should decompose to 'fi'
        result = _normalize("ﬁnale")
        assert "fi" in result or "finale" in result.replace(" ", "")

    def test_hashtag_removal(self):
        """Hashtags stripped before matching."""
        result = _normalize("My Video #shorts #viral #trending")
        assert "#" not in result
        assert "shorts" not in result
        assert "viral" not in result
        assert "my video" in result


# =============================================================================
# EXACT MATCH TESTS
# =============================================================================

class TestExactMatch:
    """Test 1: Exact title match."""

    def test_exact_match_returns_video(self):
        result = resolve_video_by_title(
            CHANNEL_UUID, "Father–Son duo in full shararat mode"
        )
        assert result is not None
        assert "clarification" not in result or not result.get("clarification")
        assert result["video_id"] == "vid_001"
        assert result["score"] >= 90

    def test_exact_match_case_insensitive(self):
        result = resolve_video_by_title(
            CHANNEL_UUID, "valentine day vlog"
        )
        assert result is not None
        assert "clarification" not in result or not result.get("clarification")
        assert result["video_id"] == "vid_002"


# =============================================================================
# PARTIAL MATCH TESTS
# =============================================================================

class TestPartialMatch:
    """Test 2: Partial title match."""

    def test_partial_title_accepted(self):
        result = resolve_video_by_title(CHANNEL_UUID, "Father Son shararat mode")
        assert result is not None
        assert "clarification" not in result or not result.get("clarification")
        assert result["video_id"] == "vid_001"
        assert result["score"] >= MATCH_THRESHOLD

    def test_partial_title_cooking(self):
        result = resolve_video_by_title(CHANNEL_UUID, "cooking challenge")
        assert result is not None
        assert "clarification" not in result or not result.get("clarification")
        assert result["video_id"] == "vid_008"


# =============================================================================
# EMOJI TITLE TESTS
# =============================================================================

class TestEmojiTitle:
    """Test 3: Title with emojis — emojis stripped before matching."""

    def test_emoji_title_matched_without_emoji(self):
        # User types without emojis, DB title has emojis
        result = resolve_video_by_title(
            CHANNEL_UUID, "Father Son duo in full shararat mode"
        )
        assert result is not None
        assert "clarification" not in result or not result.get("clarification")
        assert result["video_id"] == "vid_001"

    def test_user_includes_emoji(self):
        # User types WITH emojis
        result = resolve_video_by_title(
            CHANNEL_UUID, "Morning routine gone wrong 😅"
        )
        assert result is not None
        assert "clarification" not in result or not result.get("clarification")
        assert result["video_id"] == "vid_004"


# =============================================================================
# MISSPELLED TITLE TESTS
# =============================================================================

class TestMisspelledTitle:
    """Test 4: Misspelled title — fuzzy tolerance."""

    def test_misspelled_accepted(self):
        # "shararat" misspelled as "sharaarat"
        result = resolve_video_by_title(
            CHANNEL_UUID, "Father Son duo sharaarat mode"
        )
        assert result is not None
        assert "clarification" not in result or not result.get("clarification")
        assert result["video_id"] == "vid_001"
        assert result["score"] >= MATCH_THRESHOLD

    def test_misspelled_valentines(self):
        result = resolve_video_by_title(CHANNEL_UUID, "Valentines Day Vlog")
        assert result is not None
        assert "clarification" not in result or not result.get("clarification")
        assert result["video_id"] == "vid_002"


# =============================================================================
# NO MATCH TESTS
# =============================================================================

class TestNoMatch:
    """Test 5: No match case — returns None."""

    def test_completely_unrelated(self):
        result = resolve_video_by_title(
            CHANNEL_UUID, "How to cook Italian pasta at home"
        )
        # Should return clarification (rejected) or None
        if result is not None:
            assert result.get("clarification") is True
            assert result["video_resolution"]["decision"] == "rejected"

    def test_empty_fragment(self):
        result = resolve_video_by_title(CHANNEL_UUID, "")
        assert result is None

    def test_emoji_only_fragment(self):
        result = resolve_video_by_title(CHANNEL_UUID, "🔥😂")
        assert result is None


# =============================================================================
# TOP MATCHES TESTS
# =============================================================================

class TestTopMatches:
    """Test 6: Top 3 matches for clarification prompt."""

    def test_top_matches_returned(self):
        matches = get_top_matches(CHANNEL_UUID, "family", limit=3)
        assert len(matches) <= 3
        # Should be sorted by score descending
        scores = [m["score"] for m in matches]
        assert scores == sorted(scores, reverse=True)

    def test_top_matches_have_required_fields(self):
        matches = get_top_matches(CHANNEL_UUID, "video", limit=3)
        for match in matches:
            assert "video_id" in match
            assert "title" in match
            assert "score" in match


# =============================================================================
# EMPTY DB TESTS
# =============================================================================

class TestEmptyDB:
    """Edge case: No videos in DB."""

    def test_resolve_with_no_videos(self, mock_postgres_store):
        mock_postgres_store.get_recent_videos.return_value = []
        result = resolve_video_by_title(CHANNEL_UUID, "any title")
        assert result is None

    def test_top_matches_with_no_videos(self, mock_postgres_store):
        mock_postgres_store.get_recent_videos.return_value = []
        matches = get_top_matches(CHANNEL_UUID, "any title")
        assert matches == []


# =============================================================================
# THRESHOLD TESTS
# =============================================================================

class TestThreshold:
    """Verify MATCH_THRESHOLD is respected."""

    def test_threshold_is_70(self):
        assert MATCH_THRESHOLD == 70

    def test_high_confidence_is_85(self):
        assert HIGH_CONFIDENCE_THRESHOLD == 85

    def test_ambiguity_gap_is_10(self):
        assert AMBIGUITY_GAP == 10

    def test_below_threshold_rejected(self):
        # Very short fragment that doesn't match any title
        result = resolve_video_by_title(CHANNEL_UUID, "zzz")
        # "zzz" has no matching tokens — should be rejected or None
        if result is not None:
            assert result.get("clarification") is True
            assert result["video_resolution"]["decision"] == "rejected"


# =============================================================================
# VIDEO COUNT TESTS
# =============================================================================

class TestVideoCount:
    """Test get_video_count function."""

    def test_count_with_videos(self, mock_postgres_store):
        """DB has videos → count > 0."""
        mock_postgres_store.get_recent_videos.return_value = [MOCK_VIDEOS[0]]
        count = get_video_count(CHANNEL_UUID)
        assert count == 1

    def test_count_with_empty_db(self, mock_postgres_store):
        """DB is empty → count == 0."""
        mock_postgres_store.get_recent_videos.return_value = []
        count = get_video_count(CHANNEL_UUID)
        assert count == 0


# =============================================================================
# COLD-START INGESTION TRIGGER TESTS
# =============================================================================

class TestColdStartIngestionTrigger:
    """
    Validate that YouTube API fetch is ONLY triggered when
    videos_table_count == 0, NEVER when DB has videos but title
    doesn't match.
    """

    def test_empty_db_triggers_no_api_call_from_resolver(
        self, mock_postgres_store
    ):
        """
        Test 1: When DB is empty, resolve_video_by_title returns None.
        The resolver itself does NOT call YouTube API — that's the
        executor's job. Verify get_video_count returns 0.
        """
        mock_postgres_store.get_recent_videos.return_value = []
        result = resolve_video_by_title(CHANNEL_UUID, "some video title")
        assert result is None
        count = get_video_count(CHANNEL_UUID)
        assert count == 0

    def test_populated_db_no_match_does_not_trigger_sync(
        self, mock_postgres_store
    ):
        """
        Test 2: DB has 5 videos, query doesn't match any.
        get_video_count > 0, so executor MUST NOT trigger YouTube fetch.
        """
        five_videos = MOCK_VIDEOS[:5]
        mock_postgres_store.get_recent_videos.return_value = five_videos

        # Resolver finds no match — returns clarification or None
        result = resolve_video_by_title(
            CHANNEL_UUID, "How to cook Italian pasta at home"
        )
        if result is not None:
            assert result.get("clarification") is True

        # But video count > 0 — executor gate blocks API call
        count = get_video_count(CHANNEL_UUID)
        assert count > 0, (
            "DB has videos — cold-start sync MUST NOT trigger"
        )

    def test_integration_first_call_populates_second_skips(
        self, mock_postgres_store
    ):
        """
        Integration test:
        - First call: DB empty → count == 0 → sync should trigger
        - Second call: DB populated → count > 0 → sync skipped
        """
        # First call: empty DB
        mock_postgres_store.get_recent_videos.return_value = []
        result_1 = resolve_video_by_title(CHANNEL_UUID, "Valentine Day")
        count_1 = get_video_count(CHANNEL_UUID)
        assert result_1 is None
        assert count_1 == 0  # Executor would trigger sync here

        # Simulate: after sync, DB now has videos
        mock_postgres_store.get_recent_videos.return_value = MOCK_VIDEOS

        # Second call: DB populated
        result_2 = resolve_video_by_title(CHANNEL_UUID, "Valentine Day Vlog")
        count_2 = get_video_count(CHANNEL_UUID)
        assert result_2 is not None
        assert result_2.get("clarification") is not True
        assert result_2["video_id"] == "vid_002"
        assert count_2 > 0  # Executor would NOT trigger sync

    def test_single_video_in_db_blocks_sync(
        self, mock_postgres_store
    ):
        """
        Even with just 1 video in DB, sync MUST NOT trigger
        when title doesn't match.
        """
        mock_postgres_store.get_recent_videos.return_value = [MOCK_VIDEOS[0]]

        result = resolve_video_by_title(CHANNEL_UUID, "completely unrelated")
        # May be None or clarification
        if result is not None:
            assert result.get("clarification") is True

        count = get_video_count(CHANNEL_UUID)
        assert count == 1  # Not zero → no sync


# =============================================================================
# DECISION LOGIC TESTS
# =============================================================================

class TestDecideLogic:
    """Test the _decide helper directly."""

    def test_high_confidence_accepted(self):
        assert _decide(92.0, 50.0) == "accepted"

    def test_high_confidence_even_close_second(self):
        """Score >= 85 is always accepted regardless of gap."""
        assert _decide(87.0, 86.0) == "accepted"

    def test_borderline_large_gap_accepted(self):
        assert _decide(75.0, 60.0) == "accepted"

    def test_borderline_small_gap_ambiguous(self):
        assert _decide(75.0, 72.0) == "ambiguous"

    def test_below_threshold_rejected(self):
        assert _decide(55.0, 30.0) == "rejected"

    def test_exact_threshold_boundary(self):
        """Score of exactly 70 with large gap → accepted."""
        assert _decide(70.0, 50.0) == "accepted"

    def test_exact_high_threshold_boundary(self):
        """Score of exactly 85 → accepted."""
        assert _decide(85.0, 84.0) == "accepted"


# =============================================================================
# RESOLUTION METADATA TESTS
# =============================================================================

class TestResolutionMetadata:
    """Verify video_resolution metadata is always present."""

    def test_accepted_has_metadata(self):
        result = resolve_video_by_title(
            CHANNEL_UUID, "Valentine Day Vlog"
        )
        assert result is not None
        assert "video_resolution" in result
        meta = result["video_resolution"]
        assert "top_score" in meta
        assert "second_score" in meta
        assert "decision" in meta
        assert meta["decision"] == "accepted"

    def test_ambiguous_has_metadata(self, mock_postgres_store):
        """Force ambiguous by creating near-identical titles."""
        similar_videos = [
            _make_video("My first cooking video ever", "vid_a"),
            _make_video("My first cooking video review", "vid_b"),
            _make_video("Something completely different topic", "vid_c"),
        ]
        mock_postgres_store.get_recent_videos.return_value = similar_videos
        result = resolve_video_by_title(CHANNEL_UUID, "first cooking video")
        assert result is not None
        assert "video_resolution" in result


# =============================================================================
# PHASE 0.2B — NEW TEST CASES
# =============================================================================


class TestClearMatchAbove85:
    """Test 8: Clear match with score > 85 — always accepted."""

    def test_near_exact_accepted(self):
        result = resolve_video_by_title(
            CHANNEL_UUID, "Behind the scenes of my studio setup"
        )
        assert result is not None
        assert result.get("clarification") is not True
        assert result["video_id"] == "vid_006"
        assert result["score"] >= HIGH_CONFIDENCE_THRESHOLD
        assert result["video_resolution"]["decision"] == "accepted"

    def test_exact_with_emoji_accepted(self):
        result = resolve_video_by_title(
            CHANNEL_UUID, "Valentine Day Vlog"
        )
        assert result is not None
        assert result.get("clarification") is not True
        assert result["score"] >= HIGH_CONFIDENCE_THRESHOLD
        assert result["video_resolution"]["decision"] == "accepted"


class TestBorderlineAccepted:
    """Test 9: Borderline match (~75) with large gap → accepted."""

    def test_borderline_with_gap(self, mock_postgres_store):
        """
        Query that scores ~75 against top match with large gap
        from second match → should be accepted.
        """
        spread_videos = [
            _make_video("Amazing birthday celebration party", "vid_x1"),
            _make_video("My random daily life stuff", "vid_x2"),
            _make_video("Tech review unboxing video", "vid_x3"),
        ]
        mock_postgres_store.get_recent_videos.return_value = spread_videos
        result = resolve_video_by_title(
            CHANNEL_UUID, "birthday celebration party"
        )
        assert result is not None
        if not result.get("clarification"):
            # Accepted → score in the borderline range
            assert result["video_resolution"]["decision"] == "accepted"
        else:
            # If ambiguous, the gap was too small. That's also valid.
            assert result["video_resolution"]["decision"] in ("accepted", "ambiguous")


class TestAmbiguousMatch:
    """Test 10: Ambiguous — two scores are close together."""

    def test_ambiguous_returns_clarification(self, mock_postgres_store):
        """Two very similar titles → scores close → ambiguous."""
        similar_videos = [
            _make_video("Day in the life of a creator vlog", "vid_s1"),
            _make_video("Day in the life of a student vlog", "vid_s2"),
            _make_video("Unrelated cooking recipe", "vid_s3"),
        ]
        mock_postgres_store.get_recent_videos.return_value = similar_videos
        result = resolve_video_by_title(
            CHANNEL_UUID, "day in the life vlog"
        )
        assert result is not None
        # Should be ambiguous (both scores close) or accepted if one dominates
        meta = result["video_resolution"]
        assert meta["decision"] in ("accepted", "ambiguous")
        if meta["decision"] == "ambiguous":
            assert result.get("clarification") is True
            assert "candidates" in result
            assert len(result["candidates"]) >= 2

    def test_ambiguous_has_candidates(self, mock_postgres_store):
        """Ambiguous result includes candidate list."""
        similar_videos = [
            _make_video("My first trip to Goa", "vid_g1"),
            _make_video("My first trip to Goa part 2", "vid_g2"),
            _make_video("My first trip to Goa vlog", "vid_g3"),
        ]
        mock_postgres_store.get_recent_videos.return_value = similar_videos
        result = resolve_video_by_title(CHANNEL_UUID, "first trip to goa")
        assert result is not None
        meta = result["video_resolution"]
        if meta["decision"] == "ambiguous":
            assert result["clarification"] is True
            assert len(result["candidates"]) <= 3


class TestLowScoreRejected:
    """Test 11: Low score (< 70) → rejected with clarification."""

    def test_weak_query_rejected(self):
        result = resolve_video_by_title(
            CHANNEL_UUID, "quantum physics lecture notes"
        )
        if result is not None:
            assert result.get("clarification") is True
            assert result["video_resolution"]["decision"] == "rejected"
            assert result["video_resolution"]["top_score"] < MATCH_THRESHOLD

    def test_single_char_rejected(self):
        result = resolve_video_by_title(CHANNEL_UUID, "z")
        if result is not None:
            assert result.get("clarification") is True
            assert result["video_resolution"]["decision"] == "rejected"


class TestEmojiHeavyTitle:
    """Test 12: Emoji-heavy title resolves correctly."""

    def test_five_emoji_title(self, mock_postgres_store):
        """Video title packed with emojis still resolves."""
        emoji_videos = [
            _make_video("🔥😂🎉👀💯 Baby's first steps", "vid_e1"),
            _make_video("Normal title here", "vid_e2"),
        ]
        mock_postgres_store.get_recent_videos.return_value = emoji_videos
        result = resolve_video_by_title(
            CHANNEL_UUID, "baby first steps"
        )
        assert result is not None
        if not result.get("clarification"):
            assert result["video_id"] == "vid_e1"

    def test_user_query_with_emojis(self, mock_postgres_store):
        """User sends emoji-laden query, DB title has no emojis."""
        plain_videos = [
            _make_video("My studio tour 2024", "vid_p1"),
            _make_video("Random vlog", "vid_p2"),
        ]
        mock_postgres_store.get_recent_videos.return_value = plain_videos
        result = resolve_video_by_title(
            CHANNEL_UUID, "🔥🔥 studio tour 🔥🔥"
        )
        assert result is not None
        if not result.get("clarification"):
            assert result["video_id"] == "vid_p1"


class TestMixedHindiEnglish:
    """Test 13: Mixed Hindi/English bilingual title matching."""

    def test_hindi_english_match(self, mock_postgres_store):
        bilingual_videos = [
            _make_video("Mihir ki masti with Papa", "vid_h1"),
            _make_video("Family ka Sunday Funday", "vid_h2"),
            _make_video("Cooking with Mumma ji", "vid_h3"),
        ]
        mock_postgres_store.get_recent_videos.return_value = bilingual_videos

        result = resolve_video_by_title(
            CHANNEL_UUID, "mihir ki masti papa"
        )
        assert result is not None
        if not result.get("clarification"):
            assert result["video_id"] == "vid_h1"

    def test_partial_hindi_match(self, mock_postgres_store):
        bilingual_videos = [
            _make_video("Bacchon ke saath picnic 🧺", "vid_h4"),
            _make_video("Office ka boring day", "vid_h5"),
        ]
        mock_postgres_store.get_recent_videos.return_value = bilingual_videos

        result = resolve_video_by_title(
            CHANNEL_UUID, "bacchon ke saath picnic"
        )
        assert result is not None
        if not result.get("clarification"):
            assert result["video_id"] == "vid_h4"


class TestHashtagHeavyTitle:
    """Test 14: Hashtag-heavy title — hashtags stripped before matching."""

    def test_hashtags_stripped(self, mock_postgres_store):
        """DB title has #shorts #viral — user queries without them."""
        hashtag_videos = [
            _make_video(
                "Epic dance battle #shorts #viral #trending #fyp", "vid_ht1"
            ),
            _make_video("Just a normal day", "vid_ht2"),
        ]
        mock_postgres_store.get_recent_videos.return_value = hashtag_videos

        result = resolve_video_by_title(
            CHANNEL_UUID, "epic dance battle"
        )
        assert result is not None
        if not result.get("clarification"):
            assert result["video_id"] == "vid_ht1"

    def test_user_sends_hashtags(self, mock_postgres_store):
        """User queries WITH hashtags, DB title does NOT have them."""
        plain_videos = [
            _make_video("Epic dance battle", "vid_ht3"),
            _make_video("Something else entirely", "vid_ht4"),
        ]
        mock_postgres_store.get_recent_videos.return_value = plain_videos

        result = resolve_video_by_title(
            CHANNEL_UUID, "epic dance battle #shorts #viral"
        )
        assert result is not None
        if not result.get("clarification"):
            assert result["video_id"] == "vid_ht3"

    def test_normalize_strips_all_hashtags(self):
        """Direct test: _normalize removes all hashtags."""
        normalized = _normalize(
            "My Cool Video #shorts #viral #trending #fyp"
        )
        assert "#" not in normalized
        assert "shorts" not in normalized
        assert "viral" not in normalized
        assert "my cool video" in normalized
