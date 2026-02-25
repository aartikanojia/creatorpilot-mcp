"""
Phase 1.6 — Strategy Ranking Engine Tests (ChannelMetrics API).

Validates deterministic ranking with user's exact StrategyRankingEngine.
"""

import pytest
from analytics.strategy_ranker import StrategyRankingEngine, ChannelMetrics, StrategyResult


@pytest.fixture
def engine():
    return StrategyRankingEngine()


# ── TEST 1: Standard Growth — Retention-Constrained ──

class TestStandardGrowth:
    def test_ranking_present(self, engine):
        m = ChannelMetrics(retention=33.7, conversion=0.04, shorts_ratio=78, theme_concentration=80)
        r = engine.rank(m)
        assert len(r.ranked_strategies) > 0

    def test_max_four(self, engine):
        m = ChannelMetrics(retention=33.7, conversion=0.04, shorts_ratio=78, theme_concentration=80)
        r = engine.rank(m)
        assert len(r.ranked_strategies) <= 4

    def test_primary_constraint_retention(self, engine):
        # Use conversion=0.4 so retention severity (3.5) > conversion severity (1.5)
        m = ChannelMetrics(retention=26.0, conversion=0.4, shorts_ratio=50, theme_concentration=40)
        r = engine.rank(m)
        assert r.primary_constraint == "Retention"

    def test_severity_range(self, engine):
        m = ChannelMetrics(retention=26.0, conversion=0.4, shorts_ratio=50, theme_concentration=40)
        r = engine.rank(m)
        assert 0 <= r.severity_score <= 10

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


# ── TEST 2: Order Stability ──

class TestOrderStability:
    def test_five_runs_identical(self, engine):
        m = ChannelMetrics(retention=33.7, conversion=0.04, shorts_ratio=78, theme_concentration=80)
        results = [engine.rank(m) for _ in range(5)]
        ref = [s[0] for s in results[0].ranked_strategies]
        for i, r in enumerate(results[1:], 2):
            assert [s[0] for s in r.ranked_strategies] == ref, f"Run {i} differs"

    def test_severity_stable(self, engine):
        m = ChannelMetrics(retention=33.7, conversion=0.04, shorts_ratio=78, theme_concentration=80)
        results = [engine.rank(m) for _ in range(5)]
        for r in results:
            assert r.severity_score == results[0].severity_score


# ── TEST 3: Retention-Specific ──

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
        # retention=35 → severity=(40-35)/4=1.25, conversion=0.45 → severity=(0.5-0.45)*15=0.75
        m = ChannelMetrics(retention=35.0, conversion=0.45, shorts_ratio=50, theme_concentration=40)
        r = engine.rank(m)
        assert r.primary_constraint == "Retention"
        assert r.ranked_strategies[0][1] == "5–12%"

    def test_no_cta_in_retention(self, engine):
        m = ChannelMetrics(retention=26.0, conversion=0.4, shorts_ratio=50, theme_concentration=40)
        r = engine.rank(m)
        names = [s[0] for s in r.ranked_strategies]
        assert "CTA Optimization" not in names


# ── TEST 4: Conversion-Specific ──

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


# ── TEST 5: Risk Query ──

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


# ── TEST 6: Format Dependency ──

class TestFormatDependency:
    def test_format_risk_primary(self, engine):
        m = ChannelMetrics(retention=45.0, conversion=0.4, shorts_ratio=95, theme_concentration=40)
        r = engine.rank(m)
        assert r.primary_constraint == "Format Risk"
        names = [s[0] for s in r.ranked_strategies]
        assert names[0] == "Format Diversification"

    def test_format_risk_lift(self, engine):
        m = ChannelMetrics(retention=45.0, conversion=0.4, shorts_ratio=95, theme_concentration=40)
        r = engine.rank(m)
        assert r.ranked_strategies[0][1] == "4–10%"


# ── TEST 7: Structural Variation ──

class TestStructuralVariation:
    def test_same_metrics_same_render(self, engine):
        m = ChannelMetrics(retention=26.0, conversion=0.04, shorts_ratio=78, theme_concentration=70)
        r1 = engine.rank(m)
        r2 = engine.rank(m)
        assert engine.render(r1) == engine.render(r2)


# ── TEST 8: Minimal Input ──

class TestMinimalInput:
    def test_single_metric(self, engine):
        m = ChannelMetrics(retention=26.0)
        r = engine.rank(m)
        assert len(r.ranked_strategies) == 4
        assert r.primary_constraint == "Retention"


# ── TEST 9: Hallucination Guardrail ──

class TestHallucinationGuardrail:
    def test_no_data_raises(self, engine):
        m = ChannelMetrics()
        with pytest.raises(ValueError, match="Insufficient"):
            engine.rank(m)

    def test_confidence_drops_with_missing(self, engine):
        m = ChannelMetrics(retention=26.0)  # 4 metrics missing
        r = engine.rank(m)
        assert r.confidence <= 0.7


# ── TEST 10: Stress Test ──

class TestStressTest:
    def test_ten_runs_identical(self, engine):
        m = ChannelMetrics(retention=33.7, conversion=0.04, shorts_ratio=78, theme_concentration=80)
        results = [engine.rank(m) for _ in range(10)]
        ref = engine.render(results[0])
        for i, r in enumerate(results[1:], 2):
            assert engine.render(r) == ref, f"Run {i} differs"

    def test_constraint_never_drifts(self, engine):
        m = ChannelMetrics(retention=26.0, conversion=0.4, shorts_ratio=50, theme_concentration=40)
        for _ in range(10):
            r = engine.rank(m)
            assert r.primary_constraint == "Retention"


# ── BONUS: Severity Math ──

class TestSeverityMath:
    def test_retention_severity_formula(self, engine):
        # (40 - 26) / 4 = 3.5 — use high conversion so retention wins
        m = ChannelMetrics(retention=26.0, ctr=8.0, conversion=0.4, shorts_ratio=50, theme_concentration=40)
        r = engine.rank(m)
        assert r.primary_constraint == "Retention"
        assert r.severity_score == 3.5

    def test_ctr_severity(self, engine):
        # (5 - 2) * 2 = 6.0 → CTR wins
        m = ChannelMetrics(retention=39.0, ctr=2.0, conversion=0.4, shorts_ratio=50, theme_concentration=40)
        r = engine.rank(m)
        assert r.primary_constraint == "CTR"
        assert r.severity_score == 6.0

    def test_theme_risk(self, engine):
        # (100 - 60) / 4 = 10.0 → capped at 10
        m = ChannelMetrics(retention=42.0, conversion=0.4, shorts_ratio=50, theme_concentration=100)
        r = engine.rank(m)
        assert r.primary_constraint == "Theme Risk"
        assert r.severity_score == 10.0
