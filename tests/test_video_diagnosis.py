"""
VideoDiagnosisEngine — Unit Tests.

Validates video-level diagnosis: retention/CTR/distribution severity,
risk vector, primary constraint selection, validation, output structure.
"""

import pytest
from analytics.video_diagnosis import VideoDiagnosisEngine


@pytest.fixture
def engine():
    return VideoDiagnosisEngine()


# ── OUTPUT STRUCTURE ──

class TestOutputStructure:
    def test_returns_dict(self, engine):
        r = engine.diagnose(26.0, 1.5, 10.0, 2.5, 500, "long")
        assert isinstance(r, dict)

    def test_required_keys(self, engine):
        r = engine.diagnose(26.0, 1.5, 10.0, 2.5, 500, "long")
        assert set(r.keys()) == {
            "scope", "primary_constraint", "severity_score",
            "risk_vector", "format_type", "confidence"
        }

    def test_scope_always_video(self, engine):
        r = engine.diagnose(50.0, 5.0, 10.0, 6.0, 5000, "long")
        assert r["scope"] == "video"

    def test_confidence_fixed(self, engine):
        r = engine.diagnose(50.0, 5.0, 10.0, 6.0, 5000, "long")
        assert r["confidence"] == 0.85

    def test_format_type_passthrough_long(self, engine):
        r = engine.diagnose(50.0, 5.0, 10.0, 6.0, 5000, "long")
        assert r["format_type"] == "long"

    def test_format_type_passthrough_short(self, engine):
        r = engine.diagnose(50.0, 0.5, 1.0, 6.0, 5000, "short")
        assert r["format_type"] == "short"


# ── RETENTION SEVERITY ──

class TestRetentionSeverity:
    def test_healthy_retention(self, engine):
        r = engine.diagnose(60.0, 6.0, 10.0, 8.0, 15000, "long")
        assert r["severity_score"] <= 0.10

    def test_moderate_retention(self, engine):
        r = engine.diagnose(38.0, 4.0, 10.0, 8.0, 15000, "long")
        # retention=0.50, ctr=0.10, dist=0.10 → retention wins
        assert r["primary_constraint"] == "retention"
        assert r["severity_score"] == 0.50

    def test_severe_retention(self, engine):
        r = engine.diagnose(28.0, 2.0, 10.0, 8.0, 15000, "long")
        assert r["primary_constraint"] == "retention"
        assert r["severity_score"] == 0.80

    def test_critical_retention(self, engine):
        r = engine.diagnose(20.0, 1.0, 10.0, 8.0, 15000, "long")
        assert r["primary_constraint"] == "retention"
        assert r["severity_score"] == 0.95


# ── CTR SEVERITY ──

class TestCTRSeverity:
    def test_healthy_ctr(self, engine):
        r = engine.diagnose(60.0, 6.0, 10.0, 10.0, 15000, "long")
        assert r["primary_constraint"] == "healthy"

    def test_moderate_ctr(self, engine):
        r = engine.diagnose(60.0, 6.0, 10.0, 4.0, 15000, "long")
        # retention=0.05, ctr=0.65, dist=0.10 → ctr wins
        assert r["primary_constraint"] == "ctr"
        assert r["severity_score"] == 0.65

    def test_severe_ctr(self, engine):
        r = engine.diagnose(60.0, 6.0, 10.0, 1.5, 15000, "long")
        # retention=0.05, ctr=0.90, dist=0.10 → ctr wins
        assert r["primary_constraint"] == "ctr"
        assert r["severity_score"] == 0.90


# ── DISTRIBUTION SEVERITY ──

class TestDistributionSeverity:
    def test_healthy_distribution(self, engine):
        r = engine.diagnose(60.0, 6.0, 10.0, 8.0, 20000, "long")
        assert "distribution" not in r["risk_vector"]

    def test_low_distribution(self, engine):
        r = engine.diagnose(60.0, 6.0, 10.0, 8.0, 500, "long")
        # retention=0.05, ctr=0.10, dist=0.85 → distribution wins
        assert r["primary_constraint"] == "distribution"
        assert r["severity_score"] == 0.85

    def test_moderate_distribution(self, engine):
        r = engine.diagnose(60.0, 6.0, 10.0, 8.0, 2000, "long")
        # retention=0.05, ctr=0.10, dist=0.65 → distribution wins
        assert r["primary_constraint"] == "distribution"


# ── PRIMARY CONSTRAINT SELECTION ──

class TestPrimaryConstraint:
    def test_highest_wins(self, engine):
        # retention=0.95, ctr=0.90, dist=0.85 → retention wins
        r = engine.diagnose(20.0, 1.0, 10.0, 1.5, 500, "long")
        assert r["primary_constraint"] == "retention"

    def test_healthy_when_all_low(self, engine):
        # retention=0.05, ctr=0.10, dist=0.10 → all < 0.4 → healthy
        r = engine.diagnose(60.0, 6.0, 10.0, 8.0, 15000, "long")
        assert r["primary_constraint"] == "healthy"

    def test_ctr_wins_over_distribution(self, engine):
        # retention=0.05, ctr=0.90, dist=0.65
        r = engine.diagnose(60.0, 6.0, 10.0, 1.5, 2000, "long")
        assert r["primary_constraint"] == "ctr"


# ── RISK VECTOR ──

class TestRiskVector:
    def test_all_risky(self, engine):
        r = engine.diagnose(20.0, 1.0, 10.0, 1.5, 500, "long")
        assert "retention" in r["risk_vector"]
        assert "ctr" in r["risk_vector"]
        assert "distribution" in r["risk_vector"]

    def test_no_risks(self, engine):
        r = engine.diagnose(60.0, 6.0, 10.0, 8.0, 15000, "long")
        assert r["risk_vector"] == []

    def test_partial_risks(self, engine):
        # retention=0.50, ctr=0.10, dist=0.10
        r = engine.diagnose(38.0, 4.0, 10.0, 8.0, 15000, "long")
        assert "retention" not in r["risk_vector"]  # 0.50 < 0.60
        assert "ctr" not in r["risk_vector"]

    def test_threshold_at_0_6(self, engine):
        # retention=0.65 (in risk), ctr=0.65 (in risk), dist=0.10
        r = engine.diagnose(32.0, 3.0, 10.0, 4.0, 15000, "long")
        assert "retention" in r["risk_vector"]
        assert "ctr" in r["risk_vector"]


# ── DETERMINISM ──

class TestDeterminism:
    def test_ten_runs_identical(self, engine):
        results = [
            engine.diagnose(26.0, 1.5, 10.0, 2.5, 500, "long")
            for _ in range(10)
        ]
        for r in results:
            assert r == results[0]

    def test_severity_reproducible(self, engine):
        r1 = engine.diagnose(33.0, 2.0, 8.0, 4.5, 3500, "long")
        r2 = engine.diagnose(33.0, 2.0, 8.0, 4.5, 3500, "long")
        assert r1 == r2


# ── INPUT VALIDATION ──

class TestValidation:
    def test_negative_retention(self, engine):
        with pytest.raises(ValueError, match="video_avg_view_percentage"):
            engine.diagnose(-5.0, 1.0, 10.0, 3.0, 1000, "long")

    def test_over_100_retention(self, engine):
        with pytest.raises(ValueError, match="video_avg_view_percentage"):
            engine.diagnose(105.0, 1.0, 10.0, 3.0, 1000, "long")

    def test_negative_watch_time(self, engine):
        with pytest.raises(ValueError, match="video_watch_time_minutes"):
            engine.diagnose(40.0, -1.0, 10.0, 3.0, 1000, "long")

    def test_zero_video_length(self, engine):
        with pytest.raises(ValueError, match="video_length_minutes"):
            engine.diagnose(40.0, 1.0, 0.0, 3.0, 1000, "long")

    def test_negative_ctr(self, engine):
        with pytest.raises(ValueError, match="video_ctr"):
            engine.diagnose(40.0, 1.0, 10.0, -1.0, 1000, "long")

    def test_negative_impressions(self, engine):
        with pytest.raises(ValueError, match="impressions"):
            engine.diagnose(40.0, 1.0, 10.0, 3.0, -100, "long")

    def test_invalid_format(self, engine):
        with pytest.raises(ValueError, match="format_type"):
            engine.diagnose(40.0, 1.0, 10.0, 3.0, 1000, "medium")


# ── NO NARRATIVE ──

class TestNoNarrative:
    def test_no_advice_in_output(self, engine):
        r = engine.diagnose(26.0, 1.5, 10.0, 2.5, 500, "long")
        output_str = str(r)
        for phrase in ["you should", "consider", "recommend", "try", "improve", "optimize", "great"]:
            assert phrase not in output_str.lower()

    def test_no_channel_reference(self, engine):
        r = engine.diagnose(26.0, 1.5, 10.0, 2.5, 500, "long")
        output_str = str(r)
        assert "channel" not in output_str.lower()
