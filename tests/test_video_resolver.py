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
"""

import uuid
import pytest
from unittest.mock import patch, MagicMock

from services.video_resolver import (
    resolve_video_by_title,
    get_top_matches,
    get_video_count,
    _normalize,
    _similarity,
    MATCH_THRESHOLD,
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
        assert result["video_id"] == "vid_001"
        assert result["score"] >= 90

    def test_exact_match_case_insensitive(self):
        result = resolve_video_by_title(
            CHANNEL_UUID, "valentine day vlog"
        )
        assert result is not None
        assert result["video_id"] == "vid_002"


# =============================================================================
# PARTIAL MATCH TESTS
# =============================================================================

class TestPartialMatch:
    """Test 2: Partial title match."""

    def test_partial_title_accepted(self):
        result = resolve_video_by_title(CHANNEL_UUID, "Father Son shararat mode")
        assert result is not None
        assert result["video_id"] == "vid_001"
        assert result["score"] >= MATCH_THRESHOLD

    def test_partial_title_cooking(self):
        result = resolve_video_by_title(CHANNEL_UUID, "cooking challenge")
        assert result is not None
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
        assert result["video_id"] == "vid_001"

    def test_user_includes_emoji(self):
        # User types WITH emojis
        result = resolve_video_by_title(
            CHANNEL_UUID, "Morning routine gone wrong 😅"
        )
        assert result is not None
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
        assert result["video_id"] == "vid_001"
        assert result["score"] >= MATCH_THRESHOLD

    def test_misspelled_valentines(self):
        result = resolve_video_by_title(CHANNEL_UUID, "Valentines Day Vlog")
        assert result is not None
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
        assert result is None

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

    def test_below_threshold_rejected(self):
        # Very short fragment that partially matches multiple titles
        result = resolve_video_by_title(CHANNEL_UUID, "the")
        # "the" is too generic to match any specific video above 70
        assert result is None


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

        # Resolver finds no match
        result = resolve_video_by_title(
            CHANNEL_UUID, "How to cook Italian pasta at home"
        )
        assert result is None

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
        assert result is None

        count = get_video_count(CHANNEL_UUID)
        assert count == 1  # Not zero → no sync
