"""
ConversionRateAnalyzer — Unit Tests.

Validates conversion severity, funnel weakness, relative underperformance,
risk mapping, confidence, validation, output structure, and determinism.
"""

import pytest
from analytics.conversion_rate_analyzer import ConversionRateAnalyzer


@pytest.fixture
def engine():
    return ConversionRateAnalyzer()


# ── OUTPUT STRUCTURE ──

class TestOutputStructure:
    def test_returns_dict(self, engine):
        r = engine.diagnose(1000, 10, 1.0)
        assert isinstance(r, dict)

    def test_required_keys(self, engine):
        r = engine.diagnose(1000, 10, 1.0)
        assert set(r.keys()) == {
            "conversion_rate_percent", "channel_avg_conversion_rate",
            "conversion_severity", "risk_level",
            "relative_underperformance", "funnel_weakness", "confidence"
        }

    def test_passthrough_channel_avg(self, engine):
        r = engine.diagnose(1000, 10, 1.5)
        assert r["channel_avg_conversion_rate"] == 1.5


# ── CONVERSION RATE COMPUTATION ──

class TestConversionRate:
    def test_basic_computation(self, engine):
        """20 subs / 1000 views = 2%."""
        r = engine.diagnose(1000, 20, 1.0)
        assert r["conversion_rate_percent"] == 2.0

    def test_zero_views(self, engine):
        """Zero views → conversion rate = 0."""
        r = engine.diagnose(0, 0, 1.0)
        assert r["conversion_rate_percent"] == 0.0

    def test_small_conversion(self, engine):
        """2 subs / 5000 views = 0.04%."""
        r = engine.diagnose(5000, 2, 1.0)
        assert r["conversion_rate_percent"] == 0.04


# ── ABSOLUTE SEVERITY ──

class TestAbsoluteSeverity:
    def test_healthy(self, engine):
        """2% conversion → severity 0.1."""
        r = engine.diagnose(1000, 20, 1.0)
        assert r["conversion_severity"] == 0.1

    def test_good(self, engine):
        """1.2% conversion → severity 0.3."""
        r = engine.diagnose(1000, 12, 1.0)
        assert r["conversion_severity"] == 0.3

    def test_moderate(self, engine):
        """0.7% conversion → severity 0.6."""
        r = engine.diagnose(1000, 7, 1.0)
        assert r["conversion_severity"] == 0.6

    def test_weak(self, engine):
        """0.2% conversion → severity 0.8."""
        r = engine.diagnose(1000, 2, 0.2)
        assert r["conversion_severity"] == 0.8

    def test_critical(self, engine):
        """0.04% conversion → severity 0.95."""
        r = engine.diagnose(5000, 2, 0.04)
        assert r["conversion_severity"] == 0.95

    def test_zero_conversion(self, engine):
        """0 subs → severity 0.95."""
        r = engine.diagnose(1000, 0, 0.0)
        assert r["conversion_severity"] == 0.95


# ── RELATIVE UNDERPERFORMANCE ──

class TestRelativeUnderperformance:
    def test_underperforming(self, engine):
        """0.5% < 1.0% * 0.7 = 0.7% → underperforming."""
        r = engine.diagnose(1000, 5, 1.0)
        assert r["relative_underperformance"] is True

    def test_not_underperforming(self, engine):
        """2.0% >= 1.0% * 0.7 → not underperforming."""
        r = engine.diagnose(1000, 20, 1.0)
        assert r["relative_underperformance"] is False

    def test_severity_boost(self, engine):
        """0.5% (0.6) + underperform (+0.1) = 0.7."""
        r = engine.diagnose(1000, 5, 1.0)
        assert r["conversion_severity"] == 0.7

    def test_severity_capped(self, engine):
        """0.04% (0.95) + underperform (+0.1) → capped 1.0."""
        r = engine.diagnose(5000, 2, 1.2)
        assert r["conversion_severity"] == 1.0

    def test_zero_channel_avg(self, engine):
        """Zero channel avg → no underperformance penalty."""
        r = engine.diagnose(1000, 5, 0.0)
        assert r["relative_underperformance"] is False


# ── FUNNEL WEAKNESS ──

class TestFunnelWeakness:
    def test_funnel_weak(self, engine):
        """views > 1000, conversion < 0.3% → weak."""
        r = engine.diagnose(5000, 2, 1.0)
        assert r["funnel_weakness"] is True

    def test_funnel_ok_high_conversion(self, engine):
        """conversion >= 0.3% → not weak."""
        r = engine.diagnose(5000, 20, 1.0)
        assert r["funnel_weakness"] is False

    def test_funnel_ok_low_views(self, engine):
        """views <= 1000 → not weak even with low conversion."""
        r = engine.diagnose(500, 0, 1.0)
        assert r["funnel_weakness"] is False

    def test_boundary_views(self, engine):
        """Exactly 1000 views → not weak (> 1000 required)."""
        r = engine.diagnose(1000, 1, 1.0)
        assert r["funnel_weakness"] is False

    def test_boundary_views_1001(self, engine):
        """1001 views + low conversion → weak."""
        r = engine.diagnose(1001, 1, 1.0)
        assert r["funnel_weakness"] is True


# ── RISK LEVEL ──

class TestRiskLevel:
    def test_critical(self, engine):
        r = engine.diagnose(5000, 2, 1.2)
        assert r["risk_level"] == "critical"

    def test_high(self, engine):
        r = engine.diagnose(1000, 5, 1.0)
        assert r["risk_level"] == "high"

    def test_moderate(self, engine):
        r = engine.diagnose(1000, 7, 1.0)
        assert r["risk_level"] == "moderate"

    def test_low(self, engine):
        r = engine.diagnose(1000, 20, 1.0)
        assert r["risk_level"] == "low"


# ── CONFIDENCE ──

class TestConfidence:
    def test_low_views(self, engine):
        r = engine.diagnose(50, 1, 1.0)
        assert r["confidence"] == 0.5

    def test_medium_views(self, engine):
        r = engine.diagnose(300, 5, 1.0)
        assert r["confidence"] == 0.7

    def test_high_views(self, engine):
        r = engine.diagnose(1000, 10, 1.0)
        assert r["confidence"] == 0.85


# ── MANDATORY TEST CASES ──

class TestMandatoryCases:
    def test_case1_severe_funnel_failure(self, engine):
        """views=5000, subs=2, channel_avg=1.2."""
        r = engine.diagnose(5000, 2, 1.2)
        assert r["conversion_rate_percent"] == 0.04
        assert r["conversion_severity"] == 1.0  # 0.95 + 0.1 relative → capped
        assert r["funnel_weakness"] is True
        assert r["risk_level"] == "critical"

    def test_case2_healthy_funnel(self, engine):
        """views=1000, subs=20, channel_avg=1.0."""
        r = engine.diagnose(1000, 20, 1.0)
        assert r["conversion_rate_percent"] == 2.0
        assert r["conversion_severity"] == 0.1
        assert r["funnel_weakness"] is False
        assert r["risk_level"] == "low"

    def test_case3_moderate_underperformance(self, engine):
        """views=800, subs=4, channel_avg=1.0.
        conversion = 0.5% → severity 0.6, underperform → 0.7."""
        r = engine.diagnose(800, 4, 1.0)
        assert r["conversion_rate_percent"] == 0.5
        assert r["conversion_severity"] == 0.7
        assert r["relative_underperformance"] is True
        assert r["risk_level"] == "high"


# ── DETERMINISM ──

class TestDeterminism:
    def test_ten_runs_identical(self, engine):
        results = [
            engine.diagnose(5000, 2, 1.2)
            for _ in range(10)
        ]
        for r in results:
            assert r == results[0]

    def test_reproducible(self, engine):
        r1 = engine.diagnose(800, 4, 1.0)
        r2 = engine.diagnose(800, 4, 1.0)
        assert r1 == r2


# ── INPUT VALIDATION ──

class TestValidation:
    def test_negative_views(self, engine):
        with pytest.raises(ValueError, match="views"):
            engine.diagnose(-1, 5, 1.0)

    def test_negative_subs(self, engine):
        with pytest.raises(ValueError, match="subscribers_gained"):
            engine.diagnose(1000, -1, 1.0)

    def test_negative_channel_avg(self, engine):
        with pytest.raises(ValueError, match="channel_avg_conversion_rate"):
            engine.diagnose(1000, 5, -1.0)


# ── NO NARRATIVE ──

class TestNoNarrative:
    def test_no_advice_in_output(self, engine):
        r = engine.diagnose(1000, 2, 1.0)
        output = str(r)
        for phrase in ["you should", "consider", "recommend", "try",
                       "improve", "optimize", "CTA", "hook", "thumbnail"]:
            assert phrase not in output.lower()

    def test_no_retention_reference(self, engine):
        r = engine.diagnose(1000, 2, 1.0)
        output = str(r)
        assert "retention" not in output.lower()

    def test_no_ctr_reference(self, engine):
        r = engine.diagnose(1000, 2, 1.0)
        output = str(r)
        assert "ctr" not in output.lower()

    def test_no_strategy_reference(self, engine):
        r = engine.diagnose(1000, 2, 1.0)
        output = str(r)
        assert "strategy" not in output.lower()
