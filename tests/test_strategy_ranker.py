"""
Phase 1.6 — Strategy Ranking Engine Tests (ChannelMetrics API).

Validates deterministic ranking with metric-first priority ordering.
Metrics ALWAYS override structural risks.
"""

import pytest
from analytics.strategy_ranker import StrategyRankingEngine, ChannelMetrics, StrategyResult


@pytest.fixture
def engine():
    return StrategyRankingEngine()


# ── TEST 1: Metric Priority Override ──

class TestMetricPriority:
    def test_retention_critical_overrides_theme(self, engine):
        """Retention 0.95 must override Theme Risk even at 100% concentration."""
        m = ChannelMetrics(retention=20.0, theme_concentration=100)
        r = engine.rank(m)
        assert r.primary_constraint == "Retention"

    def test_retention_moderate_overrides_theme(self, engine):
        """Retention 0.65 must override Theme Risk."""
        m = ChannelMetrics(retention=30.0, theme_concentration=100)
        r = engine.rank(m)
        assert r.primary_constraint == "Retention"

    def test_ctr_critical_overrides_format(self, engine):
        """CTR 0.90 must override Format Risk."""
        m = ChannelMetrics(ctr=1.5, shorts_ratio=95)
        r = engine.rank(m)
        assert r.primary_constraint == "CTR"

    def test_conversion_critical_overrides_all_structural(self, engine):
        """Conversion 0.90 must override Format + Theme Risk."""
        m = ChannelMetrics(conversion=0.01, shorts_ratio=95, theme_concentration=100)
        r = engine.rank(m)
        assert r.primary_constraint == "Conversion"

    def test_theme_only_when_metrics_stable(self, engine):
        """Theme Risk only wins when all metrics are healthy."""
        m = ChannelMetrics(retention=60.0, ctr=10.0, conversion=0.6, theme_concentration=95)
        r = engine.rank(m)
        assert r.primary_constraint == "Theme Risk"

    def test_format_only_when_metrics_stable(self, engine):
        """Format Risk only wins when all metrics are healthy."""
        m = ChannelMetrics(retention=60.0, ctr=10.0, conversion=0.6, shorts_ratio=95)
        r = engine.rank(m)
        assert r.primary_constraint == "Format Risk"


# ── TEST 2: Standard Growth — Retention-Constrained ──

class TestStandardGrowth:
    def test_ranking_present(self, engine):
        m = ChannelMetrics(retention=20.0, conversion=0.04, shorts_ratio=78, theme_concentration=80)
        r = engine.rank(m)
        assert len(r.ranked_strategies) > 0

    def test_max_four(self, engine):
        m = ChannelMetrics(retention=20.0, conversion=0.04, shorts_ratio=78, theme_concentration=80)
        r = engine.rank(m)
        assert len(r.ranked_strategies) <= 4

    def test_primary_constraint_retention(self, engine):
        """Retention at 20% (severity 0.90) must be primary — not theme or format."""
        m = ChannelMetrics(retention=20.0, conversion=0.04, shorts_ratio=78, theme_concentration=80)
        r = engine.rank(m)
        assert r.primary_constraint == "Retention"

    def test_severity_range(self, engine):
        m = ChannelMetrics(retention=26.0, conversion=0.4, shorts_ratio=50, theme_concentration=40)
        r = engine.rank(m)
        assert 0 <= r.severity_score <= 1.0

    def test_confidence_range(self, engine):
        m = ChannelMetrics(retention=26.0, conversion=0.4, shorts_ratio=50, theme_concentration=40)
        r = engine.rank(m)
        assert 0.5 <= r.confidence <= 1.0

    def test_render_format(self, engine):
        m = ChannelMetrics(retention=26.0, conversion=0.4, shorts_ratio=50, theme_concentration=40)
        r = engine.rank(m)
        rendered = engine.render(r)
        assert "Primary Constraint:" in rendered
        assert "Severity Score:" in rendered
        assert "Confidence:" in rendered
        assert "Estimated Lift:" in rendered

    def test_no_narrative(self, engine):
        m = ChannelMetrics(retention=26.0, conversion=0.4, shorts_ratio=50, theme_concentration=40)
        r = engine.rank(m)
        rendered = engine.render(r)
        for phrase in ["you should", "consider", "I recommend", "great job", "keep going"]:
            assert phrase not in rendered.lower()


# ── TEST 3: Order Stability ──

class TestOrderStability:
    def test_five_runs_identical(self, engine):
        m = ChannelMetrics(retention=20.0, conversion=0.04, shorts_ratio=78, theme_concentration=80)
        results = [engine.rank(m) for _ in range(5)]
        ref = [s[0] for s in results[0].ranked_strategies]
        for i, r in enumerate(results[1:], 2):
            assert [s[0] for s in r.ranked_strategies] == ref, f"Run {i} differs"

    def test_severity_stable(self, engine):
        m = ChannelMetrics(retention=20.0, conversion=0.04, shorts_ratio=78, theme_concentration=80)
        results = [engine.rank(m) for _ in range(5)]
        for r in results:
            assert r.severity_score == results[0].severity_score


# ── TEST 4: Retention-Specific ──

class TestRetentionSpecific:
    def test_retention_strategies(self, engine):
        m = ChannelMetrics(retention=26.0, conversion=0.4, shorts_ratio=50, theme_concentration=40)
        r = engine.rank(m)
        names = [s[0] for s in r.ranked_strategies]
        assert names[0] == "Hook Optimization"
        assert "Pacing Compression" in names

    def test_severe_retention_lift(self, engine):
        m = ChannelMetrics(retention=26.0, conversion=0.4, shorts_ratio=50, theme_concentration=40)
        r = engine.rank(m)
        assert r.ranked_strategies[0][1] == "10–20%"

    def test_moderate_retention_lift(self, engine):
        m = ChannelMetrics(retention=35.0, conversion=0.45, shorts_ratio=50, theme_concentration=40)
        r = engine.rank(m)
        assert r.primary_constraint == "Retention"
        assert r.ranked_strategies[0][1] == "5–12%"

    def test_no_cta_in_retention(self, engine):
        m = ChannelMetrics(retention=26.0, conversion=0.4, shorts_ratio=50, theme_concentration=40)
        r = engine.rank(m)
        names = [s[0] for s in r.ranked_strategies]
        assert "CTA Optimization" not in names


# ── TEST 5: Conversion-Specific ──

class TestConversionSpecific:
    def test_conversion_strategies(self, engine):
        m = ChannelMetrics(retention=55.0, conversion=0.01, shorts_ratio=50, theme_concentration=40)
        r = engine.rank(m)
        assert r.primary_constraint == "Conversion"
        names = [s[0] for s in r.ranked_strategies]
        assert names[0] == "CTA Optimization"

    def test_no_hook_in_conversion(self, engine):
        m = ChannelMetrics(retention=55.0, conversion=0.01, shorts_ratio=50, theme_concentration=40)
        r = engine.rank(m)
        names = [s[0] for s in r.ranked_strategies]
        assert "Hook Optimization" not in names

    def test_conversion_lift(self, engine):
        m = ChannelMetrics(retention=55.0, conversion=0.01, shorts_ratio=50, theme_concentration=40)
        r = engine.rank(m)
        assert r.ranked_strategies[0][1] == "3–8%"


# ── TEST 6: Risk Query ──

class TestRiskQuery:
    def test_constraint_in_render(self, engine):
        m = ChannelMetrics(retention=26.0, conversion=0.4, shorts_ratio=50, theme_concentration=40)
        r = engine.rank(m)
        rendered = engine.render(r)
        assert r.primary_constraint in rendered

    def test_no_motivational(self, engine):
        m = ChannelMetrics(retention=26.0, conversion=0.4, shorts_ratio=50, theme_concentration=40)
        r = engine.rank(m)
        rendered = engine.render(r)
        for phrase in ["believe", "don't give up", "you can do it"]:
            assert phrase not in rendered.lower()


# ── TEST 7: Format Dependency ──

class TestFormatDependency:
    def test_format_risk_primary(self, engine):
        """Format Risk only wins when metrics are healthy."""
        m = ChannelMetrics(retention=60.0, ctr=10.0, conversion=0.6, shorts_ratio=95, theme_concentration=40)
        r = engine.rank(m)
        assert r.primary_constraint == "Format Risk"
        names = [s[0] for s in r.ranked_strategies]
        assert names[0] == "Format Diversification"

    def test_format_risk_lift(self, engine):
        m = ChannelMetrics(retention=60.0, ctr=10.0, conversion=0.6, shorts_ratio=95, theme_concentration=40)
        r = engine.rank(m)
        assert r.ranked_strategies[0][1] == "4–10%"


# ── TEST 8: Structural Variation ──

class TestStructuralVariation:
    def test_same_metrics_same_render(self, engine):
        m = ChannelMetrics(retention=26.0, conversion=0.04, shorts_ratio=78, theme_concentration=70)
        r1 = engine.rank(m)
        r2 = engine.rank(m)
        assert engine.render(r1) == engine.render(r2)


# ── TEST 9: Minimal Input ──

class TestMinimalInput:
    def test_single_metric(self, engine):
        m = ChannelMetrics(retention=26.0)
        r = engine.rank(m)
        assert len(r.ranked_strategies) == 4
        assert r.primary_constraint == "Retention"


# ── TEST 10: Hallucination Guardrail ──

class TestHallucinationGuardrail:
    def test_no_data_raises(self, engine):
        m = ChannelMetrics()
        with pytest.raises(ValueError, match="Insufficient"):
            engine.rank(m)

    def test_confidence_drops_with_missing(self, engine):
        m = ChannelMetrics(retention=26.0)  # 4 metrics missing
        r = engine.rank(m)
        assert r.confidence <= 0.7


# ── TEST 11: Stress Test ──

class TestStressTest:
    def test_ten_runs_identical(self, engine):
        m = ChannelMetrics(retention=20.0, conversion=0.04, shorts_ratio=78, theme_concentration=80)
        results = [engine.rank(m) for _ in range(10)]
        ref = engine.render(results[0])
        for i, r in enumerate(results[1:], 2):
            assert engine.render(r) == ref, f"Run {i} differs"

    def test_constraint_never_drifts(self, engine):
        m = ChannelMetrics(retention=26.0, conversion=0.4, shorts_ratio=50, theme_concentration=40)
        for _ in range(10):
            r = engine.rank(m)
            assert r.primary_constraint == "Retention"


# ── TEST 12: Severity Scale (0-1) ──

class TestSeverityScale:
    def test_retention_critical(self, engine):
        """Retention 20% → severity 0.90."""
        m = ChannelMetrics(retention=20.0)
        r = engine.rank(m)
        assert r.primary_constraint == "Retention"
        assert r.severity_score == 0.90

    def test_retention_severe(self, engine):
        """Retention 28% → severity 0.80."""
        m = ChannelMetrics(retention=28.0)
        r = engine.rank(m)
        assert r.severity_score == 0.80

    def test_retention_moderate(self, engine):
        """Retention 32% → severity 0.65."""
        m = ChannelMetrics(retention=32.0)
        r = engine.rank(m)
        assert r.severity_score == 0.65

    def test_retention_healthy(self, engine):
        """Retention 60% → severity 0.05."""
        m = ChannelMetrics(retention=60.0)
        r = engine.rank(m)
        assert r.severity_score == 0.05

    def test_ctr_critical(self, engine):
        """CTR 1.5% → severity 0.90."""
        m = ChannelMetrics(ctr=1.5)
        r = engine.rank(m)
        assert r.primary_constraint == "CTR"
        assert r.severity_score == 0.90


# ── TEST 13: The Bug Fix Verification ──

class TestBugFix:
    def test_retention_0_95_beats_theme_100(self, engine):
        """THE BUG: retention=0.95 was losing to theme_concentration=100.
        This must NEVER happen again."""
        m = ChannelMetrics(retention=15.0, theme_concentration=100)
        r = engine.rank(m)
        assert r.primary_constraint == "Retention"
        assert r.primary_constraint != "Theme Risk"

    def test_retention_0_90_beats_format_95(self, engine):
        """Retention severity must override format risk."""
        m = ChannelMetrics(retention=20.0, shorts_ratio=95)
        r = engine.rank(m)
        assert r.primary_constraint == "Retention"

    def test_theme_wins_only_when_metrics_healthy(self, engine):
        """Theme Risk should only be primary when all metrics are low severity."""
        m = ChannelMetrics(retention=40.0, theme_concentration=95)
        r = engine.rank(m)
        # retention=40% → severity 0.50 → still a metric → wins over structural
        assert r.primary_constraint == "Retention"

    def test_theme_wins_when_truly_stable(self, engine):
        """Theme Risk wins when metrics are genuinely healthy."""
        m = ChannelMetrics(retention=60.0, theme_concentration=95)
        r = engine.rank(m)
        assert r.primary_constraint == "Theme Risk"
