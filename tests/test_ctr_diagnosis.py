"""
CTRDiagnosisEngine — Unit Tests.

Validates CTR severity, distribution gate, relative underperformance,
risk mapping, confidence, validation, output structure, and determinism.
"""

import pytest
from analytics.ctr_diagnosis import CTRDiagnosisEngine


@pytest.fixture
def engine():
    return CTRDiagnosisEngine()


# ── OUTPUT STRUCTURE ──

class TestOutputStructure:
    def test_returns_dict(self, engine):
        r = engine.diagnose(5.0, 6.0, 1000)
        assert isinstance(r, dict)

    def test_required_keys(self, engine):
        r = engine.diagnose(5.0, 6.0, 1000)
        assert set(r.keys()) == {
            "ctr_percent", "channel_avg_ctr", "ctr_severity",
            "risk_level", "distribution_blocked",
            "relative_underperformance", "confidence"
        }

    def test_passthrough_values(self, engine):
        r = engine.diagnose(5.5, 7.0, 2000)
        assert r["ctr_percent"] == 5.5
        assert r["channel_avg_ctr"] == 7.0


# ── ABSOLUTE SEVERITY ──

class TestAbsoluteSeverity:
    def test_healthy_ctr(self, engine):
        r = engine.diagnose(9.0, 6.0, 1000)
        assert r["ctr_severity"] == 0.1

    def test_good_ctr(self, engine):
        r = engine.diagnose(7.0, 6.0, 1000)
        assert r["ctr_severity"] == 0.3

    def test_moderate_ctr(self, engine):
        r = engine.diagnose(5.0, 5.0, 1000)
        assert r["ctr_severity"] == 0.6

    def test_weak_ctr(self, engine):
        r = engine.diagnose(3.0, 3.0, 1000)
        assert r["ctr_severity"] == 0.8

    def test_critical_ctr(self, engine):
        r = engine.diagnose(1.0, 1.0, 1000)
        assert r["ctr_severity"] == 0.95

    def test_zero_ctr(self, engine):
        r = engine.diagnose(0.0, 0.0, 1000)
        assert r["ctr_severity"] == 0.95


# ── RELATIVE UNDERPERFORMANCE ──

class TestRelativeUnderperformance:
    def test_underperforming(self, engine):
        """CTR 3.0 < 6.0 * 0.7 = 4.2 → underperforming."""
        r = engine.diagnose(3.0, 6.0, 1000)
        assert r["relative_underperformance"] is True

    def test_not_underperforming(self, engine):
        """CTR 5.0 >= 6.0 * 0.7 = 4.2 → not underperforming."""
        r = engine.diagnose(5.0, 6.0, 1000)
        assert r["relative_underperformance"] is False

    def test_severity_boost_on_underperformance(self, engine):
        """CTR 3.0 (severity 0.8) + underperformance (+0.1) = 0.9."""
        r = engine.diagnose(3.0, 6.0, 1000)
        assert r["ctr_severity"] == 0.9

    def test_severity_capped_at_1(self, engine):
        """CTR 1.5 (severity 0.95) + underperformance (+0.1) → capped at 1.0."""
        r = engine.diagnose(1.5, 6.0, 1000)
        assert r["ctr_severity"] == 1.0

    def test_zero_channel_avg(self, engine):
        """Zero channel avg → no underperformance penalty."""
        r = engine.diagnose(3.0, 0.0, 1000)
        assert r["relative_underperformance"] is False
        assert r["ctr_severity"] == 0.8


# ── DISTRIBUTION GATE ──

class TestDistributionGate:
    def test_blocked(self, engine):
        """Impressions > 1000 and CTR < 4 → blocked."""
        r = engine.diagnose(3.5, 5.0, 1500)
        assert r["distribution_blocked"] is True

    def test_not_blocked_high_ctr(self, engine):
        """CTR >= 4 → not blocked regardless of impressions."""
        r = engine.diagnose(5.0, 5.0, 5000)
        assert r["distribution_blocked"] is False

    def test_not_blocked_low_impressions(self, engine):
        """Impressions <= 1000 → not blocked even with low CTR."""
        r = engine.diagnose(2.0, 5.0, 500)
        assert r["distribution_blocked"] is False

    def test_boundary_impressions(self, engine):
        """Exactly 1000 impressions → not blocked (> 1000 required)."""
        r = engine.diagnose(3.0, 5.0, 1000)
        assert r["distribution_blocked"] is False

    def test_boundary_impressions_1001(self, engine):
        """1001 impressions + low CTR → blocked."""
        r = engine.diagnose(3.0, 5.0, 1001)
        assert r["distribution_blocked"] is True


# ── RISK LEVEL ──

class TestRiskLevel:
    def test_critical(self, engine):
        r = engine.diagnose(1.0, 1.0, 1000)
        assert r["risk_level"] == "critical"

    def test_high(self, engine):
        r = engine.diagnose(3.0, 3.0, 1000)
        assert r["risk_level"] == "high"

    def test_moderate(self, engine):
        r = engine.diagnose(5.0, 5.0, 1000)
        assert r["risk_level"] == "moderate"

    def test_low(self, engine):
        r = engine.diagnose(9.0, 6.0, 1000)
        assert r["risk_level"] == "low"


# ── CONFIDENCE ──

class TestConfidence:
    def test_low_impressions(self, engine):
        r = engine.diagnose(5.0, 5.0, 50)
        assert r["confidence"] == 0.5

    def test_medium_impressions(self, engine):
        r = engine.diagnose(5.0, 5.0, 300)
        assert r["confidence"] == 0.7

    def test_high_impressions(self, engine):
        r = engine.diagnose(5.0, 5.0, 1000)
        assert r["confidence"] == 0.85


# ── MANDATORY TEST CASES ──

class TestMandatoryCases:
    def test_case1_severe_block(self, engine):
        """CTR=1.8, impressions=5000, channel_avg=6."""
        r = engine.diagnose(1.8, 6.0, 5000)
        assert r["ctr_severity"] == 1.0  # 0.95 + 0.1 relative → capped 1.0
        assert r["risk_level"] == "critical"
        assert r["distribution_blocked"] is True
        assert r["relative_underperformance"] is True

    def test_case2_healthy(self, engine):
        """CTR=7.5, impressions=200, channel_avg=6."""
        r = engine.diagnose(7.5, 6.0, 200)
        assert r["ctr_severity"] == 0.3
        assert r["risk_level"] == "low"
        assert r["distribution_blocked"] is False
        assert r["relative_underperformance"] is False

    def test_case3_moderate_suppression(self, engine):
        """CTR=3.5, impressions=1500, channel_avg=5.5.
        3.5 < 5.5 * 0.7 = 3.85 → underperforming → severity 0.8 + 0.1 = 0.9."""
        r = engine.diagnose(3.5, 5.5, 1500)
        assert r["ctr_severity"] == 0.9  # 0.8 + 0.1 relative
        assert r["distribution_blocked"] is True
        assert r["relative_underperformance"] is True


# ── DETERMINISM ──

class TestDeterminism:
    def test_ten_runs_identical(self, engine):
        results = [
            engine.diagnose(3.5, 5.0, 1500)
            for _ in range(10)
        ]
        for r in results:
            assert r == results[0]

    def test_severity_reproducible(self, engine):
        r1 = engine.diagnose(2.5, 4.0, 800)
        r2 = engine.diagnose(2.5, 4.0, 800)
        assert r1 == r2


# ── INPUT VALIDATION ──

class TestValidation:
    def test_negative_ctr(self, engine):
        with pytest.raises(ValueError, match="ctr_percent"):
            engine.diagnose(-1.0, 5.0, 1000)

    def test_negative_channel_avg(self, engine):
        with pytest.raises(ValueError, match="channel_avg_ctr"):
            engine.diagnose(5.0, -1.0, 1000)

    def test_negative_impressions(self, engine):
        with pytest.raises(ValueError, match="impressions"):
            engine.diagnose(5.0, 5.0, -100)


# ── NO NARRATIVE ──

class TestNoNarrative:
    def test_no_advice_in_output(self, engine):
        r = engine.diagnose(2.0, 5.0, 1000)
        output = str(r)
        for phrase in ["you should", "consider", "recommend", "try",
                       "improve", "optimize", "thumbnail", "title", "hook"]:
            assert phrase not in output.lower()

    def test_no_retention_reference(self, engine):
        r = engine.diagnose(2.0, 5.0, 1000)
        output = str(r)
        assert "retention" not in output.lower()

    def test_no_strategy_reference(self, engine):
        r = engine.diagnose(2.0, 5.0, 1000)
        output = str(r)
        assert "strategy" not in output.lower()
