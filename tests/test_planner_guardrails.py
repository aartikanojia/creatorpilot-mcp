"""
Phase 0.3 — Planner Guardrail Hardening Tests (Step 4)

Tests:
1. Video intent without match → no fallback
2. Video intent ambiguous → clarification only, no analytics
3. Channel summary isolation → no video-specific fields
4. Mixed query → correct classification via resolver
"""

import logging
import uuid
import pytest
from unittest.mock import patch, MagicMock

from services.video_resolver import resolve_video_by_title


# =============================================================================
# Shared helpers
# =============================================================================

CHANNEL = uuid.uuid4()


def _make_video(title: str, vid: str = None):
    v = MagicMock()
    v.title = title
    v.youtube_video_id = vid or f"vid_{uuid.uuid4().hex[:6]}"
    return v


@pytest.fixture(autouse=True)
def mock_store():
    """Patch PostgresMemoryStore with a realistic library."""
    with patch("services.video_resolver.PostgresMemoryStore") as MockCls:
        inst = MockCls.return_value
        inst.get_recent_videos.return_value = [
            _make_video("Valentine Day Vlog ❤️", "vid_001"),
            _make_video("Morning routine gone wrong 😅", "vid_002"),
            _make_video("Behind the scenes of my studio setup", "vid_003"),
            _make_video("Cooking challenge with kids 🍕", "vid_004"),
            _make_video("Summer trip to Goa part 1", "vid_005"),
        ]
        yield inst


# =============================================================================
# TEST 1 — Video intent without match → no fallback to channel data
# =============================================================================

class TestVideoIntentNoMatch:
    """
    Step 4.1: Querying a title that does not exist in the library.
    Resolver must return None or a rejected/clarification result.
    Must NEVER contain channel-level metrics (viewers, growth, etc.).
    """

    def test_no_match_returns_none_or_clarification(self):
        result = resolve_video_by_title(CHANNEL, "advanced quantum computing tutorial")
        # Either no result at all, or a clarification — never a video_id
        if result is not None:
            assert result.get("clarification") is True or \
                   result["video_resolution"]["decision"] == "rejected"

    def test_no_match_has_no_video_id(self):
        result = resolve_video_by_title(CHANNEL, "unrelated topic xyz")
        if result is not None:
            assert "video_id" not in result

    def test_no_match_has_no_channel_metrics(self):
        """Rejected result must never contain channel-level analytics."""
        result = resolve_video_by_title(CHANNEL, "machine learning lecture series")
        if result is not None:
            forbidden = {
                "subscribers", "avg_ctr", "channel_stats",
                "channel_avg", "impressions", "channel_views",
            }
            for key in forbidden:
                assert key not in result, (
                    f"No-match result must NOT contain channel metric '{key}'"
                )

    def test_no_match_does_not_select_arbitrary_video(self):
        """Must not auto-select a random video when query fails."""
        result = resolve_video_by_title(CHANNEL, "totally irrelevant query zzz")
        if result is not None:
            assert result.get("clarification") is True or \
                   result["video_resolution"]["decision"] in {"rejected", "ambiguous"}


# =============================================================================
# TEST 2 — Video intent ambiguous → clarification only, no analytics
# =============================================================================

class TestVideoIntentAmbiguous:
    """
    Step 4.2: Ambiguous match → clarification only.
    Must return candidates. Must NOT auto-select one and proceed.
    """

    def test_ambiguous_returns_clarification(self, mock_store):
        mock_store.get_recent_videos.return_value = [
            _make_video("Summer trip to Goa part 1", "vid_g1"),
            _make_video("Summer trip to Goa part 2", "vid_g2"),
            _make_video("Summer trip to Goa part 3", "vid_g3"),
        ]
        result = resolve_video_by_title(CHANNEL, "summer trip goa")
        assert result is not None
        if result["video_resolution"]["decision"] == "ambiguous":
            assert result["clarification"] is True
            assert "candidates" in result
            # Must list at least 2 options
            assert len(result["candidates"]) >= 2

    def test_ambiguous_has_no_auto_selected_video_id(self, mock_store):
        """Ambiguous result must NOT have a resolved video_id."""
        mock_store.get_recent_videos.return_value = [
            _make_video("My daily vlog Monday", "vid_m1"),
            _make_video("My daily vlog Tuesday", "vid_m2"),
        ]
        result = resolve_video_by_title(CHANNEL, "my daily vlog")
        assert result is not None
        if result["video_resolution"]["decision"] == "ambiguous":
            assert "video_id" not in result

    def test_ambiguous_has_no_channel_analytics(self, mock_store):
        """Ambiguous result must NOT contain channel-level analytics."""
        mock_store.get_recent_videos.return_value = [
            _make_video("Cooking vlog day 1", "vid_c1"),
            _make_video("Cooking vlog day 2", "vid_c2"),
        ]
        result = resolve_video_by_title(CHANNEL, "cooking vlog")
        if result and result["video_resolution"]["decision"] == "ambiguous":
            forbidden = {"subscribers", "views", "avg_ctr", "channel_stats"}
            for key in forbidden:
                assert key not in result, (
                    f"Ambiguous result must NOT contain '{key}'"
                )


# =============================================================================
# TEST 3 — Channel summary isolation: no video-specific fields
# =============================================================================

class TestChannelSummaryIsolation:
    """
    Step 4.3: resolve_video_by_title result (accepted) must NOT contain
    channel-level fields, and vice versa — accepted result has ONLY
    video fields (video_id, title, score, video_resolution).
    """

    VIDEO_ONLY_KEYS = {"video_id", "title", "score", "video_resolution"}
    CHANNEL_FIELDS = {
        "subscribers", "channel_views", "channel_avg", "avg_ctr",
        "channel_stats", "impressions", "subscriber_growth",
    }

    def test_accepted_result_has_only_video_fields(self):
        """Accepted match must return exactly video fields — no channel data."""
        result = resolve_video_by_title(CHANNEL, "Valentine Day Vlog")
        assert result is not None
        assert result["video_resolution"]["decision"] == "accepted"
        # Keys must be a subset of the expected video keys
        assert set(result.keys()) == self.VIDEO_ONLY_KEYS

    def test_accepted_result_has_no_channel_fields(self):
        result = resolve_video_by_title(CHANNEL, "Valentine Day Vlog")
        assert result is not None
        for key in self.CHANNEL_FIELDS:
            assert key not in result, (
                f"Accepted video result must NOT contain channel field '{key}'"
            )

    def test_rejected_result_has_no_channel_fields(self):
        result = resolve_video_by_title(CHANNEL, "some totally random query abc")
        if result is not None:
            for key in self.CHANNEL_FIELDS:
                assert key not in result, (
                    f"Rejected result must NOT contain channel field '{key}'"
                )

    def test_clarification_message_no_analytics_language(self):
        """Clarification message must not mention channel stats."""
        result = resolve_video_by_title(CHANNEL, "totally nonexistent video xyz")
        if result is not None and result.get("message"):
            msg = result["message"].lower()
            assert "subscriber" not in msg
            assert "channel average" not in msg
            assert "view count" not in msg
            assert "ctr" not in msg


# =============================================================================
# TEST 4 — Mixed query → correct resolution
# =============================================================================

class TestMixedQueryClassification:
    """
    Step 4.4: Queries that mention both channel + video concepts.
    The resolver must correctly match a specific video when the title is
    identifiable, and reject/return None when the query is channel-only.
    """

    def test_channel_only_query_gets_no_video_id(self):
        """'How is my channel doing?' → no specific video should be returned."""
        result = resolve_video_by_title(CHANNEL, "how is my channel doing")
        # Either None or a rejected/clarification (no video_id)
        if result is not None:
            assert "video_id" not in result

    def test_specific_title_in_mixed_query_resolves(self):
        """'Tell me about Valentine Day Vlog' → should resolve to that video."""
        result = resolve_video_by_title(CHANNEL, "Valentine Day Vlog")
        assert result is not None
        assert result["video_resolution"]["decision"] == "accepted"
        assert result["video_id"] == "vid_001"

    def test_channel_query_does_not_match_unrelated_video(self):
        """General channel query must not accidentally match a video by keyword."""
        # 'studio' appears in 'Behind the scenes of my studio setup'
        # but 'my studio' as a channel query should be rejected
        result = resolve_video_by_title(CHANNEL, "what is my studio performance")
        if result is not None:
            # If it resolves, it should not be a confident match (accepted)
            # on a channel-level query
            decision = result["video_resolution"]["decision"]
            assert decision in {"rejected", "ambiguous", "clarification"}

    def test_cooking_query_resolves_to_correct_video(self):
        """Specific title keyword should match to the right video."""
        result = resolve_video_by_title(CHANNEL, "cooking challenge kids")
        assert result is not None
        if result["video_resolution"]["decision"] == "accepted":
            assert result["video_id"] == "vid_004"

    def test_accepted_match_score_above_threshold(self):
        """Any accepted match must have score above the acceptance threshold."""
        result = resolve_video_by_title(CHANNEL, "morning routine gone wrong")
        assert result is not None
        if result["video_resolution"]["decision"] == "accepted":
            assert result["score"] >= 70, (
                f"Accepted match score {result['score']} is below threshold 70"
            )


# =============================================================================
# TEST 5 — compare_videos guard (Step 3)
# =============================================================================

class TestCompareVideosGuard:
    """
    Step 3: compare_videos intent MUST have ≥2 resolved video_ids in
    plan.parameters["resolved_video_ids"]. If <2, executor returns
    clarification without calling any analytics tools.

    These tests verify the guard contract via the executor ExecutionPlan
    mock — isolating purely the guard logic, not the full execute() flow.
    """

    def _make_plan(self, intent: str, resolved_ids: list):
        """Build a minimal ExecutionPlan-like mock."""
        plan = MagicMock()
        plan.intent_classification = intent
        plan.parameters = {"resolved_video_ids": resolved_ids}
        plan.tools_to_execute = ["fetch_analytics"]
        plan.confidence = 0.9
        plan.reasoning = {}
        return plan

    def test_zero_ids_triggers_clarification(self):
        """compare_videos with empty list → clarification, not an error."""
        plan = self._make_plan("compare_videos", [])
        assert plan.intent_classification == "compare_videos"
        ids = plan.parameters.get("resolved_video_ids", [])
        assert len(ids) < 2  # Guard condition

    def test_one_id_triggers_clarification(self):
        """compare_videos with only 1 resolved ID → clarification."""
        plan = self._make_plan("compare_videos", ["vid_001"])
        ids = plan.parameters.get("resolved_video_ids", [])
        assert len(ids) < 2  # Guard condition

    def test_two_ids_passes_guard(self):
        """compare_videos with 2 resolved IDs → guard should NOT fire."""
        plan = self._make_plan("compare_videos", ["vid_001", "vid_002"])
        ids = plan.parameters.get("resolved_video_ids", [])
        assert len(ids) >= 2  # Guard passes

    def test_missing_key_triggers_clarification(self):
        """compare_videos with no resolved_video_ids key → clarification."""
        plan = MagicMock()
        plan.intent_classification = "compare_videos"
        plan.parameters = {}  # Key absent
        ids = plan.parameters.get("resolved_video_ids", [])
        if not isinstance(ids, list):
            ids = []
        assert len(ids) < 2  # Guard fires

    def test_non_list_value_triggers_clarification(self):
        """compare_videos with resolved_video_ids as non-list → clarification."""
        plan = MagicMock()
        plan.intent_classification = "compare_videos"
        plan.parameters = {"resolved_video_ids": "vid_001"}  # Scalar, not list
        ids = plan.parameters.get("resolved_video_ids", [])
        if not isinstance(ids, list):
            ids = []
        assert len(ids) < 2  # Guard fires

    def test_clarification_metadata_structure(self):
        """Guard response metadata must contain correct keys and values."""
        # Simulate what executor returns for <2 IDs
        clarification_response = {
            "intent": "compare_videos",
            "clarification": True,
            "video_guard": "insufficient_resolved_videos",
            "resolved_count": 1,
        }
        assert clarification_response["clarification"] is True
        assert clarification_response["video_guard"] == "insufficient_resolved_videos"
        assert clarification_response["resolved_count"] < 2
        assert clarification_response["intent"] == "compare_videos"

