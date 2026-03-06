"""
ShortsImpactAnalyzer — Unit Tests.

Validates shorts ratio, format bias, retention gap, dependence risk,
severity, risk level, confidence, validation, determinism, and no-narrative.
"""

import pytest
from analytics.shorts_impact_analyzer import ShortsImpactAnalyzer


@pytest.fixture
def engine():
    return ShortsImpactAnalyzer()


# ── OUTPUT STRUCTURE ──

class TestOutputStructure:
    def test_returns_dict(self, engine):
        r = engine.diagnose(5000, 2000, 3000, 35.0, 42.0)
        assert isinstance(r, dict)

    def test_required_keys(self, engine):
        r = engine.diagnose(5000, 2000, 3000, 35.0, 42.0)
        assert set(r.keys()) == {
            "shorts_ratio", "format_bias",
            "shorts_avg_retention", "long_avg_retention",
            "retention_gap", "shorts_dependence_risk",
            "severity", "risk_level", "confidence"
        }

    def test_passthrough_retention_values(self, engine):
        r = engine.diagnose(5000, 2000, 3000, 35.0, 42.0)
        assert r["shorts_avg_retention"] == 35.0
        assert r["long_avg_retention"] == 42.0


# ── SHORTS RATIO ──

class TestShortsRatio:
    def test_basic(self, engine):
        r = engine.diagnose(10000, 8500, 1500, 28.0, 22.0)
        assert r["shorts_ratio"] == 0.85

    def test_zero_views(self, engine):
        r = engine.diagnose(0, 0, 0, 0.0, 0.0)
        assert r["shorts_ratio"] == 0.0

    def test_balanced(self, engine):
        r = engine.diagnose(5000, 2000, 3000, 35.0, 42.0)
        assert r["shorts_ratio"] == 0.4


# ── FORMAT BIAS ──

class TestFormatBias:
    def test_shorts_dominant(self, engine):
        r = engine.diagnose(10000, 8000, 2000, 30.0, 25.0)
        assert r["format_bias"] == "shorts_dominant"

    def test_shorts_heavy(self, engine):
        r = engine.diagnose(10000, 5000, 5000, 30.0, 40.0)
        assert r["format_bias"] == "shorts_heavy"

    def test_balanced(self, engine):
        r = engine.diagnose(10000, 3000, 7000, 30.0, 40.0)
        assert r["format_bias"] == "balanced"

    def test_long_form_dominant(self, engine):
        r = engine.diagnose(10000, 1000, 9000, 30.0, 40.0)
        assert r["format_bias"] == "long_form_dominant"


# ── RETENTION GAP ──

class TestRetentionGap:
    def test_positive_gap(self, engine):
        """Long retention > shorts retention → positive gap."""
        r = engine.diagnose(5000, 2000, 3000, 30.0, 45.0)
        assert r["retention_gap"] == 15.0

    def test_negative_gap(self, engine):
        """Shorts retention > long retention → negative gap."""
        r = engine.diagnose(5000, 2000, 3000, 50.0, 30.0)
        assert r["retention_gap"] == -20.0

    def test_zero_gap(self, engine):
        r = engine.diagnose(5000, 2000, 3000, 40.0, 40.0)
        assert r["retention_gap"] == 0.0


# ── SHORTS DEPENDENCE RISK ──

class TestShortsDependenceRisk:
    def test_risk_true(self, engine):
        """ratio >= 0.75 AND long_retention < 30 → risk."""
        r = engine.diagnose(10000, 8000, 2000, 28.0, 22.0)
        assert r["shorts_dependence_risk"] is True

    def test_risk_false_low_ratio(self, engine):
        """ratio < 0.75 → no risk regardless of retention."""
        r = engine.diagnose(10000, 5000, 5000, 28.0, 20.0)
        assert r["shorts_dependence_risk"] is False

    def test_risk_false_good_retention(self, engine):
        """long_retention >= 30 → no risk regardless of ratio."""
        r = engine.diagnose(10000, 8000, 2000, 28.0, 35.0)
        assert r["shorts_dependence_risk"] is False


# ── SEVERITY ──

class TestSeverity:
    def test_extreme(self, engine):
        """ratio 0.85 (0.9) + long_ret 22 (+0.1) + dependence (+0.1) → capped 1.0."""
        r = engine.diagnose(10000, 8500, 1500, 28.0, 22.0)
        assert r["severity"] == 1.0

    def test_high(self, engine):
        """ratio 0.80 (0.8) + dependence (+0.1) → 0.9."""
        r = engine.diagnose(10000, 8000, 2000, 28.0, 28.0)
        assert r["severity"] == 0.9

    def test_moderate(self, engine):
        """ratio 0.60 (0.6) → 0.6."""
        r = engine.diagnose(10000, 6000, 4000, 30.0, 40.0)
        assert r["severity"] == 0.6

    def test_low(self, engine):
        """ratio 0.40 (0.4) → 0.4."""
        r = engine.diagnose(5000, 2000, 3000, 35.0, 42.0)
        assert r["severity"] == 0.4

    def test_minimal(self, engine):
        """ratio < 0.40 → 0.2."""
        r = engine.diagnose(10000, 1000, 9000, 30.0, 40.0)
        assert r["severity"] == 0.2


# ── RISK LEVEL ──

class TestRiskLevel:
    def test_critical(self, engine):
        r = engine.diagnose(10000, 8500, 1500, 28.0, 22.0)
        assert r["risk_level"] == "critical"

    def test_high(self, engine):
        """ratio 0.75 (0.8) + no low retention, no dependence risk → 0.8 = high."""
        r = engine.diagnose(10000, 7500, 2500, 28.0, 35.0)
        assert r["risk_level"] == "high"

    def test_moderate(self, engine):
        r = engine.diagnose(10000, 6000, 4000, 30.0, 40.0)
        assert r["risk_level"] == "moderate"

    def test_low(self, engine):
        r = engine.diagnose(5000, 2000, 3000, 35.0, 42.0)
        assert r["risk_level"] == "low"


# ── CONFIDENCE ──

class TestConfidence:
    def test_low_views(self, engine):
        r = engine.diagnose(100, 50, 50, 30.0, 40.0)
        assert r["confidence"] == 0.6

    def test_medium_views(self, engine):
        r = engine.diagnose(500, 200, 300, 30.0, 40.0)
        assert r["confidence"] == 0.75

    def test_high_views(self, engine):
        r = engine.diagnose(5000, 2000, 3000, 30.0, 40.0)
        assert r["confidence"] == 0.85


# ── MANDATORY TEST CASES ──

class TestMandatoryCases:
    def test_case1_shorts_trap(self, engine):
        """total=10000, shorts=8500, long=1500, s_ret=28, l_ret=22."""
        r = engine.diagnose(10000, 8500, 1500, 28.0, 22.0)
        assert r["format_bias"] == "shorts_dominant"
        assert r["shorts_dependence_risk"] is True
        assert r["severity"] == 1.0
        assert r["risk_level"] == "critical"

    def test_case2_balanced_channel(self, engine):
        """total=5000, shorts=1500, long=3500, s_ret=35, l_ret=42.
        ratio=0.30 → balanced, severity=0.2."""
        r = engine.diagnose(5000, 1500, 3500, 35.0, 42.0)
        assert r["format_bias"] == "balanced"
        assert r["shorts_dependence_risk"] is False
        assert r["severity"] == 0.2
        assert r["risk_level"] == "low"


# ── DETERMINISM ──

class TestDeterminism:
    def test_ten_runs_identical(self, engine):
        results = [
            engine.diagnose(10000, 8500, 1500, 28.0, 22.0)
            for _ in range(10)
        ]
        for r in results:
            assert r == results[0]

    def test_reproducible(self, engine):
        r1 = engine.diagnose(5000, 2000, 3000, 35.0, 42.0)
        r2 = engine.diagnose(5000, 2000, 3000, 35.0, 42.0)
        assert r1 == r2


# ── INPUT VALIDATION ──

class TestValidation:
    def test_negative_total_views(self, engine):
        with pytest.raises(ValueError, match="total_views"):
            engine.diagnose(-1, 0, 0, 30.0, 40.0)

    def test_negative_shorts_views(self, engine):
        with pytest.raises(ValueError, match="shorts_views"):
            engine.diagnose(1000, -1, 500, 30.0, 40.0)

    def test_negative_long_views(self, engine):
        with pytest.raises(ValueError, match="long_views"):
            engine.diagnose(1000, 500, -1, 30.0, 40.0)

    def test_negative_shorts_retention(self, engine):
        with pytest.raises(ValueError, match="shorts_avg_retention"):
            engine.diagnose(1000, 500, 500, -1.0, 40.0)

    def test_negative_long_retention(self, engine):
        with pytest.raises(ValueError, match="long_avg_retention"):
            engine.diagnose(1000, 500, 500, 30.0, -1.0)


# ── NO NARRATIVE ──

class TestNoNarrative:
    def test_no_advice(self, engine):
        r = engine.diagnose(10000, 8500, 1500, 28.0, 22.0)
        output = str(r)
        for phrase in ["you should", "consider", "recommend", "try",
                       "improve", "optimize", "hook", "thumbnail", "CTA"]:
            assert phrase not in output.lower()

    def test_no_strategy_reference(self, engine):
        r = engine.diagnose(10000, 8500, 1500, 28.0, 22.0)
        output = str(r)
        assert "strategy" not in output.lower()

    def test_no_archetype_reference(self, engine):
        r = engine.diagnose(10000, 8500, 1500, 28.0, 22.0)
        output = str(r)
        assert "archetype" not in output.lower()
