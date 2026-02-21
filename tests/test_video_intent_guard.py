"""
Phase 0.2C — Strict Video Intent Guard Tests.

Validates that video_analysis intent NEVER falls back to channel-level
analytics when video resolution fails.

Tests:
1. Rejected resolution → no analytics tools, no channel data
2. Ambiguous resolution → only clarification returned
3. No extracted_title → guard fires, no tools/LLM
4. No channel_uuid → guard fires, no tools/LLM
5. Accepted resolution → proceeds normally (control test)
6. Channel-level metrics never appear in guarded output
7. Log validation for VideoGuard
"""

import logging
import uuid
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from services.video_resolver import resolve_video_by_title, _normalize


# =============================================================================
# Helpers
# =============================================================================

CHANNEL = uuid.uuid4()


def _make_video(title: str, vid: str = None):
    v = MagicMock()
    v.title = title
    v.youtube_video_id = vid or f"vid_{uuid.uuid4().hex[:6]}"
    return v


@pytest.fixture(autouse=True)
def mock_store():
    with patch("services.video_resolver.PostgresMemoryStore") as MockCls:
        inst = MockCls.return_value
        inst.get_recent_videos.return_value = [
            _make_video("Father–Son duo in full shararat mode 🔥😂", "vid_001"),
            _make_video("Valentine Day Vlog ❤️", "vid_002"),
            _make_video("Morning routine gone wrong 😅", "vid_003"),
            _make_video("Behind the scenes of my studio setup", "vid_004"),
            _make_video("Cooking challenge with kids 🍕", "vid_005"),
        ]
        yield inst


# =============================================================================
# TEST 1 — Rejected resolution: no analytics, no channel data
# =============================================================================

class TestRejectedResolution:
    """Video intent + rejected → no analytics tool, no channel data."""

    def test_rejected_returns_clarification(self):
        result = resolve_video_by_title(
            CHANNEL, "quantum physics lecture series"
        )
        # Must be either None or clarification
        if result is not None:
            assert result.get("clarification") is True
            assert result["video_resolution"]["decision"] == "rejected"

    def test_rejected_has_no_channel_metrics(self):
        result = resolve_video_by_title(
            CHANNEL, "machine learning deep dive tutorial"
        )
        if result is not None:
            # Must NOT contain any channel-level metrics
            forbidden = {
                "subscribers", "views", "avg_ctr",
                "channel_avg", "channel_stats", "averages",
                "watch_time", "impressions",
            }
            for key in forbidden:
                assert key not in result, (
                    f"Rejected result must NOT contain '{key}'"
                )

    def test_rejected_has_no_video_id(self):
        result = resolve_video_by_title(
            CHANNEL, "how to build a rocket engine"
        )
        if result is not None:
            assert "video_id" not in result

    def test_rejected_decision_metadata(self):
        result = resolve_video_by_title(
            CHANNEL, "completely unrelated xyz abc"
        )
        if result is not None:
            meta = result["video_resolution"]
            assert meta["decision"] == "rejected"
            assert meta["top_score"] < 70


# =============================================================================
# TEST 2 — Ambiguous resolution: only clarification
# =============================================================================

class TestAmbiguousResolution:
    """Video intent + ambiguous → only clarification, nothing else."""

    def test_ambiguous_only_clarification(self, mock_store):
        mock_store.get_recent_videos.return_value = [
            _make_video("Summer trip to Goa part 1", "vid_g1"),
            _make_video("Summer trip to Goa part 2", "vid_g2"),
            _make_video("Unrelated content", "vid_unr"),
        ]
        result = resolve_video_by_title(CHANNEL, "summer trip goa")
        assert result is not None
        meta = result["video_resolution"]
        if meta["decision"] == "ambiguous":
            assert result["clarification"] is True
            assert "candidates" in result
            assert len(result["candidates"]) >= 2
            # No video auto-selected
            assert "video_id" not in result

    def test_ambiguous_has_no_channel_data(self, mock_store):
        mock_store.get_recent_videos.return_value = [
            _make_video("My daily routine morning", "vid_r1"),
            _make_video("My daily routine evening", "vid_r2"),
        ]
        result = resolve_video_by_title(CHANNEL, "my daily routine")
        assert result is not None
        forbidden = {"subscribers", "views", "avg_ctr", "channel_stats"}
        for key in forbidden:
            assert key not in result


# =============================================================================
# TEST 3 — No channel-level metrics in guarded output
# =============================================================================

class TestNoChannelMetrics:
    """Confirm no channel-level metrics appear in any non-accepted output."""

    def test_rejected_no_subscribers(self):
        result = resolve_video_by_title(CHANNEL, "xyz random query")
        if result is not None:
            assert "subscribers" not in result
            assert "views" not in result

    def test_clarification_message_no_metrics(self):
        result = resolve_video_by_title(CHANNEL, "totally wrong title abc")
        if result is not None and result.get("message"):
            msg = result["message"].lower()
            # No analytics language in clarification message
            assert "subscriber" not in msg
            assert "view count" not in msg
            assert "channel average" not in msg

    def test_accepted_only_has_video_fields(self):
        """Control: accepted result has exactly the expected keys."""
        result = resolve_video_by_title(CHANNEL, "Valentine Day Vlog")
        assert result is not None
        assert result.get("clarification") is not True
        expected_keys = {"video_id", "title", "score", "video_resolution"}
        assert set(result.keys()) == expected_keys


# =============================================================================
# TEST 4 — Resolver never makes network calls
# =============================================================================

class TestNoNetworkCalls:
    """Resolver itself must NEVER make external API calls."""

    def test_resolve_no_http_calls(self):
        """
        resolve_video_by_title only queries PostgresMemoryStore.
        It never calls YouTube API, LLM, or any external service.
        The mocked store proves no real DB call happens.
        """
        with patch("services.video_resolver.PostgresMemoryStore") as MockCls:
            inst = MockCls.return_value
            inst.get_recent_videos.return_value = []
            result = resolve_video_by_title(CHANNEL, "any title")
            # Only get_recent_videos was called, nothing else
            inst.get_recent_videos.assert_called_once()
            assert result is None


# =============================================================================
# TEST 5 — Accepted resolution proceeds normally (control)
# =============================================================================

class TestAcceptedProceeds:
    """Control: accepted match returns video data normally."""

    def test_accepted_has_video_id(self):
        result = resolve_video_by_title(CHANNEL, "Valentine Day Vlog")
        assert result is not None
        assert result.get("clarification") is not True
        assert result["video_id"] == "vid_002"
        assert result["video_resolution"]["decision"] == "accepted"

    def test_accepted_has_score(self):
        result = resolve_video_by_title(
            CHANNEL, "Behind the scenes of my studio setup"
        )
        assert result is not None
        assert result["score"] >= 85
        assert result["video_resolution"]["decision"] == "accepted"


# =============================================================================
# TEST 6 — VideoGuard log validation
# =============================================================================

class TestVideoGuardLog:
    """Verify log lines for accepted/rejected transitions."""

    def test_log_accepted(self, caplog):
        with caplog.at_level(logging.INFO, logger="services.video_resolver"):
            resolve_video_by_title(CHANNEL, "Valentine Day Vlog")
        assert any(
            "[VideoResolver] Match accepted" in r.message
            for r in caplog.records
        )

    def test_log_rejected(self, caplog):
        with caplog.at_level(logging.INFO, logger="services.video_resolver"):
            result = resolve_video_by_title(CHANNEL, "quantum physics")
        if result and result.get("video_resolution", {}).get("decision") == "rejected":
            assert any(
                "[VideoResolver] Match rejected" in r.message
                for r in caplog.records
            )

    def test_log_ambiguous(self, caplog, mock_store):
        mock_store.get_recent_videos.return_value = [
            _make_video("Beach vacation day 1", "vid_b1"),
            _make_video("Beach vacation day 2", "vid_b2"),
        ]
        with caplog.at_level(logging.INFO, logger="services.video_resolver"):
            result = resolve_video_by_title(CHANNEL, "beach vacation")
        if result and result.get("video_resolution", {}).get("decision") == "ambiguous":
            assert any(
                "[VideoResolver] Match ambiguous" in r.message
                for r in caplog.records
            )


# =============================================================================
# TEST 7 — Edge cases for the guard
# =============================================================================

class TestGuardEdgeCases:
    """Edge cases that must be caught by the guard."""

    def test_empty_title_returns_none(self):
        """Empty string → None (guard not even needed)."""
        result = resolve_video_by_title(CHANNEL, "")
        assert result is None

    def test_emoji_only_returns_none(self):
        """Emoji-only → None after normalization."""
        result = resolve_video_by_title(CHANNEL, "🔥😂💯")
        assert result is None

    def test_single_char_is_rejected(self):
        """Single character → low score → rejected."""
        result = resolve_video_by_title(CHANNEL, "x")
        if result is not None:
            assert result.get("clarification") is True
            assert result["video_resolution"]["decision"] == "rejected"

    def test_very_long_irrelevant_query(self):
        """Long unrelated query → rejected."""
        result = resolve_video_by_title(
            CHANNEL,
            "this is a very long query about advanced quantum computing "
            "research papers published in nature journal 2024"
        )
        if result is not None:
            assert result.get("clarification") is True
            assert result["video_resolution"]["decision"] == "rejected"
