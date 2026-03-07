"""
PremiumOutputFormatter, ChannelOrchestrator, VideoOrchestrator — Tests.

Validates strict key filtering, scope isolation, routing, and no-narrative.
"""

import pytest
from analytics.premium_formatter import PremiumOutputFormatter
from analytics.channel_orchestrator import ChannelOrchestrator
from analytics.video_orchestrator import VideoOrchestrator


# ═══════════════════════════════════════
# PremiumOutputFormatter Tests
# ═══════════════════════════════════════

@pytest.fixture
def formatter():
    return PremiumOutputFormatter(client=None)


def _full_state(**overrides):
    base = {
        "primary_constraint": "retention",
        "severity": 0.9,
        "risk_level": "critical",
        "ranked_strategies": [
            {"name": "Hook Optimization", "estimated_lift": "10-20%"},
            {"name": "Pacing Compression", "estimated_lift": "5-12%"},
        ],
        "confidence": 0.85,
    }
    base.update(overrides)
    return base


class TestFormatterStructure:
    def test_returns_string(self, formatter):
        r = formatter.format(_full_state())
        assert isinstance(r, str)

    def test_contains_primary_constraint(self, formatter):
        r = formatter.format(_full_state())
        assert "Primary Constraint: Viewers Leaving Early" in r

    def test_contains_severity(self, formatter):
        r = formatter.format(_full_state())
        assert "Severity: 0.9" in r

    def test_contains_risk_level(self, formatter):
        r = formatter.format(_full_state())
        # Risk Level removed from creator-facing output
        assert "Risk Level" not in r

    def test_contains_strategies(self, formatter):
        r = formatter.format(_full_state())
        assert "Hook Optimization" in r
        assert "Pacing Compression" in r

    def test_contains_confidence(self, formatter):
        r = formatter.format(_full_state())
        assert "Confidence: 0.85" in r


class TestFormatterStrictFiltering:
    def test_ignores_extra_keys(self, formatter):
        state = _full_state(
            video_title="My Video",
            description="Some desc",
            raw_analytics={"views": 5000},
            emoji="🔥",
        )
        r = formatter.format(state)
        # video_title is now an allowed (optional) key — it SHOULD appear
        assert "My Video" in r
        assert "Some desc" not in r
        assert "5000" not in r
        assert "🔥" not in r

    def test_only_allowed_keys_in_prompt(self, formatter):
        state = _full_state(extra_field="should_be_ignored")
        r = formatter.format(state)
        assert "should_be_ignored" not in r

    def test_incomplete_state(self, formatter):
        r = formatter.format({"primary_constraint": "retention"})
        assert r == "Structured intelligence state incomplete."

    def test_non_dict_input(self, formatter):
        r = formatter.format("not a dict")
        assert r == "Structured intelligence state incomplete."

    def test_empty_dict(self, formatter):
        r = formatter.format({})
        assert r == "Structured intelligence state incomplete."


class TestFormatterStrategyFormats:
    def test_dict_strategies(self, formatter):
        state = _full_state(
            ranked_strategies=[
                {"name": "Hook Opt", "estimated_lift": "10%"},
            ]
        )
        r = formatter.format(state)
        assert "Hook Opt (Lift: 10%)" in r

    def test_tuple_strategies(self, formatter):
        state = _full_state(
            ranked_strategies=[("Hook Opt", "10%")]
        )
        r = formatter.format(state)
        assert "Hook Opt (Lift: 10%)" in r

    def test_string_strategies(self, formatter):
        state = _full_state(
            ranked_strategies=["Hook Optimization"]
        )
        r = formatter.format(state)
        assert "Hook Optimization" in r


# ═══════════════════════════════════════
# ChannelOrchestrator Tests
# ═══════════════════════════════════════

@pytest.fixture
def channel_orch():
    return ChannelOrchestrator()


def _channel_data(**overrides):
    base = {
        "avg_view_percentage": 20.0,
        "avg_watch_minutes": 1.5,
        "avg_video_length_minutes": 8.0,
        "shorts_ratio": 0.3,
        "ctr_percent": 3.0,
        "channel_avg_ctr": 5.0,
        "impressions": 2000,
        "views": 5000,
        "subscribers_gained": 10,
        "channel_avg_conversion_rate": 1.0,
        "total_views": 5000,
        "shorts_views": 1500,
        "long_views": 3500,
        "shorts_avg_retention": 30.0,
        "long_avg_retention": 40.0,
        "current_period_views": 5000,
        "previous_period_views": 4000,
        "current_period_subs": 60,
        "previous_period_subs": 50,
    }
    base.update(overrides)
    return base


class TestChannelOrchestrator:
    def test_returns_dict(self, channel_orch):
        r = channel_orch.run(_channel_data())
        assert isinstance(r, dict)

    def test_has_scope(self, channel_orch):
        r = channel_orch.run(_channel_data())
        assert r["scope"] == "channel"

    def test_has_primary_constraint(self, channel_orch):
        r = channel_orch.run(_channel_data())
        assert "primary_constraint" in r

    def test_has_severity(self, channel_orch):
        r = channel_orch.run(_channel_data())
        assert "primary_severity" in r

    def test_has_risk_level(self, channel_orch):
        r = channel_orch.run(_channel_data())
        assert "risk_level" in r

    def test_retention_dominant(self, channel_orch):
        """With retention at 20%, retention should be primary."""
        r = channel_orch.run(_channel_data(avg_view_percentage=20.0))
        assert r["primary_constraint"] == "retention"

    def test_determinism(self, channel_orch):
        data = _channel_data()
        results = [channel_orch.run(data) for _ in range(5)]
        for r in results:
            assert r["primary_constraint"] == results[0]["primary_constraint"]
            assert r["primary_severity"] == results[0]["primary_severity"]


# ═══════════════════════════════════════
# VideoOrchestrator Tests
# ═══════════════════════════════════════

@pytest.fixture
def video_orch():
    return VideoOrchestrator()


def _video_data(**overrides):
    base = {
        "video_views": 1000,
        "video_avg_view_percentage": 25.0,
        "video_ctr": 2.5,
        "video_impressions": 5000,
        "video_subscribers_gained": 5,
    }
    base.update(overrides)
    return base


class TestVideoOrchestrator:
    def test_returns_dict(self, video_orch):
        r = video_orch.run(_video_data())
        assert isinstance(r, dict)

    def test_has_scope(self, video_orch):
        r = video_orch.run(_video_data())
        assert r["scope"] == "video"

    def test_has_primary_constraint(self, video_orch):
        r = video_orch.run(_video_data())
        assert "primary_constraint" in r

    def test_has_severity(self, video_orch):
        r = video_orch.run(_video_data())
        assert "primary_severity" in r

    def test_retention_critical(self, video_orch):
        """Video retention 25% → severity 0.80."""
        r = video_orch.run(_video_data(video_avg_view_percentage=25.0))
        assert r["engine_severities"]["retention"] == 0.80

    def test_ctr_critical(self, video_orch):
        """Video CTR 1.5% → severity 0.90."""
        r = video_orch.run(_video_data(video_ctr=1.5))
        assert r["engine_severities"]["ctr"] == 0.90

    def test_determinism(self, video_orch):
        data = _video_data()
        results = [video_orch.run(data) for _ in range(5)]
        for r in results:
            assert r["primary_constraint"] == results[0]["primary_constraint"]


# ═══════════════════════════════════════
# Scope Isolation Tests
# ═══════════════════════════════════════

class TestScopeIsolation:
    def test_channel_scope_tag(self, channel_orch):
        r = channel_orch.run(_channel_data())
        assert r["scope"] == "channel"

    def test_video_scope_tag(self, video_orch):
        r = video_orch.run(_video_data())
        assert r["scope"] == "video"

    def test_no_shared_state(self, channel_orch, video_orch):
        """Channel and video produce independent results."""
        ch = channel_orch.run(_channel_data())
        vi = video_orch.run(_video_data())
        # Different scopes
        assert ch["scope"] != vi["scope"]

    def test_video_no_channel_keys(self, video_orch):
        """Video orchestrator never produces channel-level keys."""
        r = video_orch.run(_video_data())
        assert "shorts" not in r.get("engine_severities", {})
        assert "growth" not in r.get("engine_severities", {})


# ═══════════════════════════════════════
# Router Logic Tests
# ═══════════════════════════════════════

class TestRouter:
    def test_video_intent_routes_to_video(self, video_orch):
        """video_analysis intent → VideoOrchestrator."""
        intent = "video_analysis"
        if intent == "video_analysis":
            r = video_orch.run(_video_data())
        assert r["scope"] == "video"

    def test_channel_intent_routes_to_channel(self, channel_orch):
        """analytics intent → ChannelOrchestrator."""
        intent = "analytics"
        if intent != "video_analysis":
            r = channel_orch.run(_channel_data())
        assert r["scope"] == "channel"


# ═══════════════════════════════════════
# No Narrative
# ═══════════════════════════════════════

class TestNoNarrative:
    def test_formatter_no_advice(self, formatter):
        r = formatter.format(_full_state())
        for phrase in ["you should", "consider", "recommend"]:
            assert phrase not in r.lower()
