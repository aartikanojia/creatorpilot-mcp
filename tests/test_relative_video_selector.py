"""
Phase 0.2F — Relative Video Selector Tests.

Validates that positional queries like "last video", "latest video"
bypass the fuzzy resolver and fetch directly from DB by published_at.
"""

import logging
import re
import uuid
import pytest
from unittest.mock import patch, MagicMock

from services.video_resolver import get_latest_video_from_db


# =============================================================================
# Helpers
# =============================================================================

def _make_video(title: str, video_id: str, published_at=None):
    """Build a mock Video with the given title and optional published_at."""
    v = MagicMock()
    v.title = title
    v.youtube_video_id = video_id
    v.published_at = published_at
    return v


CHANNEL = uuid.uuid4()


# =============================================================================
# FIXTURE — ordered video library
# =============================================================================

ORDERED_LIBRARY = [
    # Most recent first (DB returns ORDER BY published_at DESC)
    _make_video("My newest vlog 2024", "vid_newest"),
    _make_video("Previous video about cooking", "vid_previous"),
    _make_video("Old tutorial from last month", "vid_old"),
]


@pytest.fixture(autouse=True)
def mock_store():
    """Patch PostgresMemoryStore globally with ordered library."""
    with patch("services.video_resolver.PostgresMemoryStore") as MockCls:
        inst = MockCls.return_value
        inst.get_recent_videos.return_value = ORDERED_LIBRARY
        yield inst


# =============================================================================
# TEST: get_latest_video_from_db
# =============================================================================

class TestGetLatestVideoFromDB:
    """Test the new DB-direct lookup function."""

    def test_returns_most_recent_video(self):
        result = get_latest_video_from_db(CHANNEL, offset=0)
        assert result is not None
        assert result["video_id"] == "vid_newest"
        assert result["title"] == "My newest vlog 2024"
        assert result["score"] == 100.0
        assert result["video_resolution"]["decision"] == "accepted"

    def test_returns_second_most_recent(self):
        result = get_latest_video_from_db(CHANNEL, offset=1)
        assert result is not None
        assert result["video_id"] == "vid_previous"
        assert result["title"] == "Previous video about cooking"

    def test_returns_none_when_offset_exceeds_count(self):
        result = get_latest_video_from_db(CHANNEL, offset=10)
        assert result is None

    def test_returns_none_when_db_empty(self, mock_store):
        mock_store.get_recent_videos.return_value = []
        result = get_latest_video_from_db(CHANNEL, offset=0)
        assert result is None

    def test_no_clarification_flag(self):
        result = get_latest_video_from_db(CHANNEL, offset=0)
        assert result is not None
        assert "clarification" not in result

    def test_no_fuzzy_scoring(self):
        """Relative lookup must NOT involve normalize or similarity."""
        result = get_latest_video_from_db(CHANNEL, offset=0)
        assert result["score"] == 100.0
        assert result["video_resolution"]["top_score"] == 100.0
        assert result["video_resolution"]["second_score"] == 0.0

    def test_log_relative_lookup(self, caplog):
        with caplog.at_level(logging.INFO, logger="services.video_resolver"):
            get_latest_video_from_db(CHANNEL, offset=0)
        assert any(
            "[VideoResolver] Relative lookup:" in r.message
            for r in caplog.records
        ), "Missing relative lookup log line"


# =============================================================================
# TEST: Relative keyword detection patterns
# =============================================================================

# Same patterns used in executor Step 2a
_RELATIVE_PATTERNS = [
    r"\b(last|latest|recent|newest)\s+(video|upload|content)\b",
    r"\b(my|the)\s+(last|latest|recent)\s+(video|upload)\b",
    r"\b(my|the)\s+last\s+upload\b",
    r"\b(previous)\s+(video|upload)\b",
]


class TestRelativePatterns:
    """Verify the regex patterns match expected queries."""

    @pytest.mark.parametrize("query", [
        "Analyze my last video",
        "How did my latest upload perform?",
        "tell me about the last video",
        "What about my recent video?",
        "analyze newest video",
        "previous video performance",
        "my last upload stats",
        "latest content analysis",
    ])
    def test_relative_patterns_match(self, query):
        matched = any(
            re.search(p, query, re.IGNORECASE)
            for p in _RELATIVE_PATTERNS
        )
        assert matched, f"'{query}' should match a relative pattern"

    @pytest.mark.parametrize("query", [
        "Tell me about Be caution video",
        "Analyze Valentine Day Vlog",
        "How is my channel doing?",
        "What should I upload next?",
    ])
    def test_explicit_titles_not_matched(self, query):
        matched = any(
            re.search(p, query, re.IGNORECASE)
            for p in _RELATIVE_PATTERNS
        )
        assert not matched, f"'{query}' should NOT match a relative pattern"
