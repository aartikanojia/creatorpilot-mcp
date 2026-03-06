"""
GrowthTrendExplanationEngine — Unit Tests.

Validates growth rates, direction, velocity, acceleration,
severity, risk level, confidence, validation, determinism, no-narrative.
"""

import pytest
from analytics.growth_trend_engine import GrowthTrendExplanationEngine


@pytest.fixture
def engine():
    return GrowthTrendExplanationEngine()


# ── OUTPUT STRUCTURE ──

class TestOutputStructure:
    def test_returns_dict(self, engine):
        r = engine.diagnose(1000, 800, 50, 40)
        assert isinstance(r, dict)

    def test_required_keys(self, engine):
        r = engine.diagnose(1000, 800, 50, 40)
        assert set(r.keys()) == {
            "view_growth_rate_percent", "subscriber_growth_rate_percent",
            "direction", "velocity", "accelerating_growth",
            "severity", "risk_level", "confidence"
        }


# ── GROWTH RATE COMPUTATION ──

class TestGrowthRate:
    def test_view_growth(self, engine):
        """(1000-800)/800 * 100 = 25%."""
        r = engine.diagnose(1000, 800, 50, 40)
        assert r["view_growth_rate_percent"] == 25.0

    def test_view_decline(self, engine):
        """(500-1000)/1000 * 100 = -50%."""
        r = engine.diagnose(500, 1000, 30, 50)
        assert r["view_growth_rate_percent"] == -50.0

    def test_zero_previous_views(self, engine):
        """Zero previous → growth rate 0."""
        r = engine.diagnose(1000, 0, 50, 0)
        assert r["view_growth_rate_percent"] == 0.0

    def test_sub_growth(self, engine):
        """(60-40)/40 * 100 = 50%."""
        r = engine.diagnose(1000, 800, 60, 40)
        assert r["subscriber_growth_rate_percent"] == 50.0

    def test_zero_previous_subs(self, engine):
        r = engine.diagnose(1000, 800, 50, 0)
        assert r["subscriber_growth_rate_percent"] == 0.0


# ── DIRECTION ──

class TestDirection:
    def test_strong_growth(self, engine):
        """50% growth → strong_growth."""
        r = engine.diagnose(1500, 1000, 50, 40)
        assert r["direction"] == "strong_growth"

    def test_moderate_growth(self, engine):
        """15% growth → moderate_growth."""
        r = engine.diagnose(1150, 1000, 50, 40)
        assert r["direction"] == "moderate_growth"

    def test_stable(self, engine):
        """5% growth → stable."""
        r = engine.diagnose(1050, 1000, 50, 50)
        assert r["direction"] == "stable"

    def test_stable_slight_decline(self, engine):
        """-5% → stable."""
        r = engine.diagnose(950, 1000, 50, 50)
        assert r["direction"] == "stable"

    def test_moderate_decline(self, engine):
        """-15% → moderate_decline."""
        r = engine.diagnose(850, 1000, 50, 50)
        assert r["direction"] == "moderate_decline"

    def test_sharp_decline(self, engine):
        """-50% → sharp_decline."""
        r = engine.diagnose(500, 1000, 30, 50)
        assert r["direction"] == "sharp_decline"


# ── VELOCITY ──

class TestVelocity:
    def test_volatile(self, engine):
        """50% abs growth → volatile."""
        r = engine.diagnose(1500, 1000, 50, 40)
        assert r["velocity"] == "volatile"

    def test_accelerating(self, engine):
        """25% abs growth → accelerating."""
        r = engine.diagnose(1250, 1000, 50, 40)
        assert r["velocity"] == "accelerating"

    def test_steady(self, engine):
        """5% abs growth → steady."""
        r = engine.diagnose(1050, 1000, 50, 50)
        assert r["velocity"] == "steady"

    def test_volatile_decline(self, engine):
        """-50% → abs 50% → volatile."""
        r = engine.diagnose(500, 1000, 30, 50)
        assert r["velocity"] == "volatile"


# ── ACCELERATION FLAG ──

class TestAcceleration:
    def test_accelerating(self, engine):
        """Both views and subs increasing → True."""
        r = engine.diagnose(1200, 1000, 60, 40)
        assert r["accelerating_growth"] is True

    def test_not_accelerating_views_down(self, engine):
        """Views declining → False."""
        r = engine.diagnose(800, 1000, 60, 40)
        assert r["accelerating_growth"] is False

    def test_not_accelerating_subs_down(self, engine):
        """Subs declining → False."""
        r = engine.diagnose(1200, 1000, 30, 40)
        assert r["accelerating_growth"] is False

    def test_not_accelerating_both_flat(self, engine):
        """Equal → not strictly greater → False."""
        r = engine.diagnose(1000, 1000, 50, 50)
        assert r["accelerating_growth"] is False


# ── SEVERITY ──

class TestSeverity:
    def test_sharp_decline(self, engine):
        """Sharp decline (0.9), subs flat → no boost → 0.9."""
        r = engine.diagnose(500, 1000, 50, 50)
        assert r["severity"] == 0.9

    def test_moderate_decline(self, engine):
        r = engine.diagnose(850, 1000, 50, 50)
        assert r["severity"] == 0.7

    def test_stable(self, engine):
        r = engine.diagnose(1050, 1000, 50, 50)
        assert r["severity"] == 0.3

    def test_moderate_growth(self, engine):
        r = engine.diagnose(1150, 1000, 50, 40)
        assert r["severity"] == 0.2

    def test_strong_growth(self, engine):
        r = engine.diagnose(1500, 1000, 50, 40)
        assert r["severity"] == 0.1

    def test_sub_decline_boost(self, engine):
        """Sharp decline (0.9) + sub_growth < -20 (+0.1) → capped 1.0."""
        r = engine.diagnose(500, 1000, 10, 50)
        assert r["severity"] == 1.0

    def test_moderate_decline_with_sub_loss(self, engine):
        """Moderate decline (0.7) + sub decline > 20% (+0.1) → 0.8."""
        r = engine.diagnose(850, 1000, 30, 50)
        # sub growth = (30-50)/50 * 100 = -40%
        assert r["severity"] == 0.8


# ── RISK LEVEL ──

class TestRiskLevel:
    def test_critical(self, engine):
        r = engine.diagnose(500, 1000, 10, 50)
        assert r["risk_level"] == "critical"

    def test_high(self, engine):
        r = engine.diagnose(850, 1000, 50, 50)
        assert r["risk_level"] == "high"

    def test_low_growth(self, engine):
        r = engine.diagnose(1500, 1000, 50, 40)
        assert r["risk_level"] == "low"

    def test_low_stable(self, engine):
        r = engine.diagnose(1050, 1000, 50, 50)
        assert r["risk_level"] == "low"


# ── CONFIDENCE ──

class TestConfidence:
    def test_low_views(self, engine):
        r = engine.diagnose(100, 100, 5, 5)
        assert r["confidence"] == 0.6

    def test_medium_views(self, engine):
        r = engine.diagnose(1000, 1000, 50, 50)
        assert r["confidence"] == 0.75

    def test_high_views(self, engine):
        r = engine.diagnose(5000, 5000, 100, 100)
        assert r["confidence"] == 0.85


# ── DETERMINISM ──

class TestDeterminism:
    def test_ten_runs_identical(self, engine):
        results = [
            engine.diagnose(500, 1000, 10, 50)
            for _ in range(10)
        ]
        for r in results:
            assert r == results[0]

    def test_reproducible(self, engine):
        r1 = engine.diagnose(1200, 1000, 60, 40)
        r2 = engine.diagnose(1200, 1000, 60, 40)
        assert r1 == r2


# ── INPUT VALIDATION ──

class TestValidation:
    def test_negative_current_views(self, engine):
        with pytest.raises(ValueError, match="current_period_views"):
            engine.diagnose(-1, 1000, 50, 50)

    def test_negative_previous_views(self, engine):
        with pytest.raises(ValueError, match="previous_period_views"):
            engine.diagnose(1000, -1, 50, 50)

    def test_negative_current_subs(self, engine):
        with pytest.raises(ValueError, match="current_period_subs"):
            engine.diagnose(1000, 1000, -1, 50)

    def test_negative_previous_subs(self, engine):
        with pytest.raises(ValueError, match="previous_period_subs"):
            engine.diagnose(1000, 1000, 50, -1)


# ── NO NARRATIVE ──

class TestNoNarrative:
    def test_no_advice(self, engine):
        r = engine.diagnose(500, 1000, 10, 50)
        output = str(r)
        for phrase in ["you should", "consider", "recommend", "try",
                       "improve", "optimize", "hook", "thumbnail", "CTA"]:
            assert phrase not in output.lower()

    def test_no_strategy_reference(self, engine):
        r = engine.diagnose(500, 1000, 10, 50)
        output = str(r)
        assert "strategy" not in output.lower()
