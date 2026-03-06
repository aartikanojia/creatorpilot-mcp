"""
ScopeGuardLayer — Unit Tests.

Validates scope detection, input validation, output sanitization,
enforcement pipeline, determinism, and no-narrative guards.
"""

import pytest
from analytics.scope_guard import ScopeGuardLayer


@pytest.fixture
def guard():
    return ScopeGuardLayer()


# ── SCOPE DETECTION ──


class TestScopeDetection:
    def test_video_analysis(self, guard):
        assert guard.determine_scope("video_analysis") == "video"

    def test_analyze_last_video(self, guard):
        assert guard.determine_scope("analyze_last_video") == "video"

    def test_analyze_this_video(self, guard):
        assert guard.determine_scope("analyze_this_video") == "video"

    def test_insight(self, guard):
        assert guard.determine_scope("insight") == "channel"

    def test_analytics(self, guard):
        assert guard.determine_scope("analytics") == "channel"

    def test_general(self, guard):
        assert guard.determine_scope("general") == "general"

    def test_structural_analysis(self, guard):
        assert guard.determine_scope("structural_analysis") == "channel"

    def test_strategy_ranking(self, guard):
        assert guard.determine_scope("strategy_ranking") == "strategy"

    def test_unknown_intent(self, guard):
        assert guard.determine_scope("random_thing") == "unknown"

    def test_empty_intent(self, guard):
        assert guard.determine_scope("") == "unknown"


# ── INPUT VALIDATION ──


class TestValidation:
    def test_video_valid(self, guard):
        data = {
            "video_avg_view_percentage": 35.0,
            "video_watch_time_minutes": 2.0,
            "video_length_minutes": 10.0,
            "video_ctr": 4.5,
            "impressions": 3000,
            "format_type": "long",
        }
        result = guard.validate_scope_inputs("video", data)
        assert result["status"] == "ok"

    def test_video_missing_field(self, guard):
        data = {
            "video_avg_view_percentage": 35.0,
            "video_watch_time_minutes": 2.0,
            # missing video_length_minutes, video_ctr, impressions, format_type
        }
        result = guard.validate_scope_inputs("video", data)
        assert "error" in result
        assert "Missing required fields" in result["error"]
        assert result["confidence"] == 0.2

    def test_channel_valid(self, guard):
        data = {
            "avg_view_percentage": 26.0,
            "avg_watch_time_minutes": 1.5,
            "avg_video_length_minutes": 10.0,
            "shorts_ratio": 0.78,
            "long_form_ratio": 0.22,
        }
        result = guard.validate_scope_inputs("channel", data)
        assert result["status"] == "ok"

    def test_channel_missing_field(self, guard):
        data = {"avg_view_percentage": 26.0}
        result = guard.validate_scope_inputs("channel", data)
        assert "error" in result
        assert "Missing required fields" in result["error"]

    def test_strategy_valid(self, guard):
        data = {"primary_constraint": "Retention"}
        result = guard.validate_scope_inputs("strategy", data)
        assert result["status"] == "ok"

    def test_strategy_missing_constraint(self, guard):
        data = {"severity_score": 0.8}
        result = guard.validate_scope_inputs("strategy", data)
        assert "error" in result
        assert "constraint" in result["error"].lower()

    def test_unknown_scope_returns_error(self, guard):
        result = guard.validate_scope_inputs("unknown", {})
        assert "error" in result
        assert "Ambiguous scope" in result["error"]


# ── SANITIZATION ──


class TestSanitization:
    def test_video_keeps_only_allowed_keys(self, guard):
        raw = {
            "scope": "video",
            "primary_constraint": "retention",
            "severity_score": 0.85,
            "risk_vector": ["retention"],
            "format_type": "long",
            "confidence": 0.85,
            "channel_avg": 20.0,  # should be stripped
            "strategy_hint": "hook",  # should be stripped
        }
        sanitized = guard.sanitize_for_llm("video", raw)
        assert "channel_avg" not in sanitized
        assert "strategy_hint" not in sanitized
        assert "scope" in sanitized
        assert "primary_constraint" in sanitized

    def test_channel_keeps_only_allowed_keys(self, guard):
        raw = {
            "constraint": "retention",
            "severity_score": 0.93,
            "risk_level": "critical",
            "amplifiers": {"shorts_ratio": 0.78},
            "confidence": 0.85,
            "video_id": "abc123",  # should be stripped
            "risk_vector": ["retention"],  # should be stripped
        }
        sanitized = guard.sanitize_for_llm("channel", raw)
        assert "video_id" not in sanitized
        assert "risk_vector" not in sanitized
        assert "constraint" in sanitized
        assert "risk_level" in sanitized

    def test_unknown_scope_passes_through(self, guard):
        raw = {"anything": "goes", "foo": "bar"}
        sanitized = guard.sanitize_for_llm("unknown", raw)
        assert sanitized == raw

    def test_video_output_count(self, guard):
        raw = {
            "scope": "video",
            "primary_constraint": "retention",
            "severity_score": 0.85,
            "risk_vector": ["retention"],
            "format_type": "long",
            "confidence": 0.85,
            "extra_1": 1,
            "extra_2": 2,
        }
        sanitized = guard.sanitize_for_llm("video", raw)
        assert len(sanitized) == 6  # exactly the 6 allowed keys


# ── ENFORCE PIPELINE ──


class TestEnforce:
    def test_video_full_pipeline(self, guard):
        data = {
            "video_avg_view_percentage": 35.0,
            "video_watch_time_minutes": 2.0,
            "video_length_minutes": 10.0,
            "video_ctr": 4.5,
            "impressions": 3000,
            "format_type": "long",
        }
        result = guard.enforce("video_analysis", data)
        assert result["status"] == "ok"
        assert result["scope"] == "video"

    def test_channel_full_pipeline(self, guard):
        data = {
            "avg_view_percentage": 26.0,
            "avg_watch_time_minutes": 1.5,
            "avg_video_length_minutes": 10.0,
            "shorts_ratio": 0.78,
            "long_form_ratio": 0.22,
        }
        result = guard.enforce("insight", data)
        assert result["status"] == "ok"
        assert result["scope"] == "channel"

    def test_general_full_pipeline(self, guard):
        """General intent routes to pure LLM — no engine, no validation."""
        result = guard.enforce("general", {})
        assert result["status"] == "ok"
        assert result["scope"] == "general"

    def test_unknown_intent_blocked(self, guard):
        result = guard.enforce("random", {})
        assert "error" in result
        assert "Ambiguous scope" in result["error"]
        assert result["confidence"] == 0.3

    def test_video_incomplete_data_blocked(self, guard):
        data = {"video_avg_view_percentage": 35.0}
        result = guard.enforce("video_analysis", data)
        assert "error" in result
        assert "Missing required fields" in result["error"]

    def test_no_auto_fallback(self, guard):
        """Video scope with missing data must NOT fall back to channel."""
        data = {"avg_view_percentage": 26.0}  # channel data, not video
        result = guard.enforce("video_analysis", data)
        assert "error" in result
        assert result.get("scope") is None  # no scope leak


# ── DETERMINISM ──


class TestDeterminism:
    def test_scope_deterministic(self, guard):
        for _ in range(10):
            assert guard.determine_scope("video_analysis") == "video"

    def test_enforce_deterministic(self, guard):
        data = {
            "video_avg_view_percentage": 35.0,
            "video_watch_time_minutes": 2.0,
            "video_length_minutes": 10.0,
            "video_ctr": 4.5,
            "impressions": 3000,
            "format_type": "long",
        }
        results = [guard.enforce("video_analysis", data) for _ in range(10)]
        for r in results:
            assert r == results[0]

    def test_sanitize_deterministic(self, guard):
        raw = {
            "scope": "video",
            "primary_constraint": "ctr",
            "severity_score": 0.9,
            "risk_vector": ["ctr"],
            "format_type": "long",
            "confidence": 0.85,
            "junk": True,
        }
        results = [guard.sanitize_for_llm("video", raw) for _ in range(10)]
        for r in results:
            assert r == results[0]


# ── NO NARRATIVE ──


class TestNoNarrative:
    def test_error_has_no_advice(self, guard):
        result = guard.enforce("random", {})
        output = str(result)
        for phrase in ["you should", "consider", "recommend", "try", "improve"]:
            assert phrase not in output.lower()

    def test_ok_has_no_advice(self, guard):
        data = {
            "video_avg_view_percentage": 35.0,
            "video_watch_time_minutes": 2.0,
            "video_length_minutes": 10.0,
            "video_ctr": 4.5,
            "impressions": 3000,
            "format_type": "long",
        }
        result = guard.enforce("video_analysis", data)
        output = str(result)
        for phrase in ["you should", "consider", "recommend", "try", "improve"]:
            assert phrase not in output.lower()


# ── SCOPE ISOLATION ──


class TestScopeIsolation:
    def test_video_scope_rejects_channel_intent(self, guard):
        """Channel intent data should never produce video scope."""
        assert guard.determine_scope("insight") == "channel"
        assert guard.determine_scope("insight") != "video"

    def test_channel_scope_rejects_video_intent(self, guard):
        """Video intent should never produce channel scope."""
        assert guard.determine_scope("video_analysis") == "video"
        assert guard.determine_scope("video_analysis") != "channel"

    def test_general_scope_is_not_channel(self, guard):
        """General intent must NOT map to channel scope."""
        assert guard.determine_scope("general") != "channel"
        assert guard.determine_scope("general") == "general"

    def test_no_scope_leakage_in_error(self, guard):
        """Error responses must not contain scope information."""
        result = guard.enforce("video_analysis", {})
        assert "error" in result
        assert "scope" not in result
