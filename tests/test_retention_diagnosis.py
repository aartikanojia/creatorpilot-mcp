"""
RetentionDiagnosisEngine — Unit Tests.

Validates deterministic severity scoring, amplifiers,
risk classification, validation, and output structure.
"""

import pytest
from analytics.retention_diagnosis import RetentionDiagnosisEngine


@pytest.fixture
def engine():
    return RetentionDiagnosisEngine()


# ── OUTPUT STRUCTURE ──

class TestOutputStructure:
    def test_returns_dict(self, engine):
        r = engine.diagnose(26.0, 1.5, 10.0, 0.78, 0.22)
        assert isinstance(r, dict)

    def test_required_keys(self, engine):
        r = engine.diagnose(26.0, 1.5, 10.0, 0.78, 0.22)
        assert set(r.keys()) == {"constraint", "severity_score", "risk_level", "amplifiers", "confidence"}

    def test_constraint_always_retention(self, engine):
        r = engine.diagnose(50.0, 5.0, 10.0, 0.3, 0.7)
        assert r["constraint"] == "retention"

    def test_amplifiers_structure(self, engine):
        r = engine.diagnose(26.0, 1.5, 10.0, 0.78, 0.22)
        assert "shorts_ratio" in r["amplifiers"]
        assert "watch_time_ratio" in r["amplifiers"]

    def test_confidence_fixed(self, engine):
        r = engine.diagnose(26.0, 1.5, 10.0, 0.78, 0.22)
        assert r["confidence"] == 0.85


# ── BASE SEVERITY TIERS ──

class TestBaseSeverity:
    def test_healthy_retention(self, engine):
        r = engine.diagnose(60.0, 6.0, 10.0, 0.3, 0.7)
        assert r["severity_score"] <= 0.10
        assert r["risk_level"] == "healthy"

    def test_mild_retention(self, engine):
        r = engine.diagnose(48.0, 5.0, 10.0, 0.3, 0.7)
        assert r["risk_level"] == "healthy"  # 0.25 base, no amplifiers

    def test_moderate_retention(self, engine):
        r = engine.diagnose(38.0, 4.0, 10.0, 0.3, 0.7)
        assert r["risk_level"] == "moderate"

    def test_severe_retention(self, engine):
        r = engine.diagnose(28.0, 2.0, 10.0, 0.3, 0.7)
        assert r["risk_level"] == "severe"

    def test_critical_retention(self, engine):
        r = engine.diagnose(20.0, 1.0, 10.0, 0.3, 0.7)
        assert r["risk_level"] == "critical"


# ── SHORTS AMPLIFIER ──

class TestShortsAmplifier:
    def test_no_amplification_low_shorts(self, engine):
        r = engine.diagnose(35.0, 4.0, 10.0, 0.50, 0.50)
        assert r["severity_score"] == 0.50  # base * 1.0

    def test_mild_amplification(self, engine):
        r = engine.diagnose(35.0, 4.0, 10.0, 0.65, 0.35)
        assert r["severity_score"] == 0.53  # base 0.50 * 1.05 = 0.525 → 0.53

    def test_moderate_amplification(self, engine):
        r = engine.diagnose(35.0, 4.0, 10.0, 0.78, 0.22)
        assert r["severity_score"] == 0.55  # base 0.50 * 1.10 = 0.55

    def test_high_amplification(self, engine):
        r = engine.diagnose(35.0, 4.0, 10.0, 0.90, 0.10)
        assert r["severity_score"] == 0.57  # base 0.50 * 1.15 = 0.575 → 0.58

    def test_amplifier_stored(self, engine):
        r = engine.diagnose(35.0, 4.0, 10.0, 0.78, 0.22)
        assert r["amplifiers"]["shorts_ratio"] == 0.78


# ── WATCH TIME PENALTY ──

class TestWatchTimePenalty:
    def test_no_penalty_good_ratio(self, engine):
        r = engine.diagnose(55.0, 3.0, 10.0, 0.3, 0.7)
        # watch_time_ratio = 0.30 (good), base = 0.05
        assert r["severity_score"] == 0.05

    def test_mild_penalty(self, engine):
        r = engine.diagnose(55.0, 1.8, 10.0, 0.3, 0.7)
        # watch_time_ratio = 0.18 (< 0.20), penalty = 0.05
        assert r["severity_score"] == 0.10  # 0.05 + 0.05

    def test_severe_penalty(self, engine):
        r = engine.diagnose(55.0, 1.0, 10.0, 0.3, 0.7)
        # watch_time_ratio = 0.10 (< 0.15), penalty = 0.10
        assert r["severity_score"] == 0.15  # 0.05 + 0.10

    def test_zero_video_length_no_crash(self, engine):
        r = engine.diagnose(55.0, 0.0, 0.0, 0.3, 0.7)
        assert r["amplifiers"]["watch_time_ratio"] == 0.0

    def test_watch_time_ratio_stored(self, engine):
        r = engine.diagnose(35.0, 2.0, 10.0, 0.3, 0.7)
        assert r["amplifiers"]["watch_time_ratio"] == 0.2


# ── SEVERITY CAP ──

class TestSeverityCap:
    def test_capped_at_one(self, engine):
        # Worst case: retention=10%, shorts=0.95
        r = engine.diagnose(10.0, 0.5, 10.0, 0.95, 0.05)
        assert r["severity_score"] <= 1.0

    def test_combined_amplifiers_cap(self, engine):
        r = engine.diagnose(15.0, 0.5, 10.0, 0.90, 0.10)
        assert r["severity_score"] <= 1.0


# ── DETERMINISM ──

class TestDeterminism:
    def test_ten_runs_identical(self, engine):
        results = [
            engine.diagnose(26.0, 1.5, 10.0, 0.78, 0.22)
            for _ in range(10)
        ]
        for r in results:
            assert r == results[0]

    def test_severity_reproducible(self, engine):
        r1 = engine.diagnose(33.0, 2.0, 8.0, 0.65, 0.35)
        r2 = engine.diagnose(33.0, 2.0, 8.0, 0.65, 0.35)
        assert r1["severity_score"] == r2["severity_score"]
        assert r1["risk_level"] == r2["risk_level"]


# ── INPUT VALIDATION ──

class TestValidation:
    def test_negative_retention(self, engine):
        with pytest.raises(ValueError, match="avg_view_percentage"):
            engine.diagnose(-5.0, 1.0, 10.0, 0.3, 0.7)

    def test_over_100_retention(self, engine):
        with pytest.raises(ValueError, match="avg_view_percentage"):
            engine.diagnose(105.0, 1.0, 10.0, 0.3, 0.7)

    def test_negative_watch_time(self, engine):
        with pytest.raises(ValueError, match="avg_watch_time_minutes"):
            engine.diagnose(40.0, -1.0, 10.0, 0.3, 0.7)

    def test_negative_video_length(self, engine):
        with pytest.raises(ValueError, match="avg_video_length_minutes"):
            engine.diagnose(40.0, 1.0, -5.0, 0.3, 0.7)

    def test_shorts_ratio_over_1(self, engine):
        with pytest.raises(ValueError, match="shorts_ratio"):
            engine.diagnose(40.0, 1.0, 10.0, 1.5, 0.7)

    def test_negative_shorts_ratio(self, engine):
        with pytest.raises(ValueError, match="shorts_ratio"):
            engine.diagnose(40.0, 1.0, 10.0, -0.1, 0.7)

    def test_long_form_ratio_over_1(self, engine):
        with pytest.raises(ValueError, match="long_form_ratio"):
            engine.diagnose(40.0, 1.0, 10.0, 0.3, 1.5)


# ── NO NARRATIVE ──

class TestNoNarrative:
    def test_no_text_fields(self, engine):
        r = engine.diagnose(26.0, 1.5, 10.0, 0.78, 0.22)
        for key in ["constraint", "risk_level"]:
            val = r[key]
            assert val in ("retention", "healthy", "mild", "moderate", "severe", "critical")

    def test_no_advice_in_output(self, engine):
        r = engine.diagnose(26.0, 1.5, 10.0, 0.78, 0.22)
        output_str = str(r)
        for phrase in ["you should", "consider", "recommend", "try", "improve", "optimize"]:
            assert phrase not in output_str.lower()
