"""
ThumbnailQualityEngine — Unit Tests.
"""

import pytest
from analytics.thumbnail_quality_engine import ThumbnailQualityEngine


@pytest.fixture
def engine():
    return ThumbnailQualityEngine()


# ── OUTPUT STRUCTURE ──

class TestOutputStructure:
    def test_returns_dict(self, engine):
        r = engine.diagnose(impressions=1000, views=50)
        assert isinstance(r, dict)

    def test_has_all_keys(self, engine):
        r = engine.diagnose(impressions=1000, views=50)
        for key in ["ctr", "packaging_score", "packaging_quality",
                     "severity", "risk_level", "confidence"]:
            assert key in r


# ── CTR COMPUTATION ──

class TestCTRComputation:
    def test_basic_ctr(self, engine):
        r = engine.diagnose(impressions=1000, views=50)
        assert r["ctr"] == 5.0

    def test_zero_impressions(self, engine):
        r = engine.diagnose(impressions=0, views=0)
        assert r["ctr"] == 0.0

    def test_high_ctr(self, engine):
        r = engine.diagnose(impressions=100, views=10)
        assert r["ctr"] == 10.0

    def test_low_ctr(self, engine):
        r = engine.diagnose(impressions=1000, views=15)
        assert r["ctr"] == 1.5


# ── PACKAGING QUALITY ──

class TestPackagingQuality:
    def test_strong(self, engine):
        r = engine.diagnose(impressions=1000, views=80)  # 8%
        assert r["packaging_quality"] == "strong"

    def test_average(self, engine):
        r = engine.diagnose(impressions=1000, views=50)  # 5%
        assert r["packaging_quality"] == "average"

    def test_average_at_3(self, engine):
        r = engine.diagnose(impressions=1000, views=30)  # 3%
        assert r["packaging_quality"] == "average"

    def test_weak(self, engine):
        r = engine.diagnose(impressions=1000, views=20)  # 2%
        assert r["packaging_quality"] == "weak"

    def test_weak_at_zero(self, engine):
        r = engine.diagnose(impressions=1000, views=0)   # 0%
        assert r["packaging_quality"] == "weak"


# ── RISK LEVEL ──

class TestRiskLevel:
    def test_critical(self, engine):
        r = engine.diagnose(impressions=1000, views=20)  # 2%
        assert r["risk_level"] == "critical"

    def test_moderate(self, engine):
        r = engine.diagnose(impressions=1000, views=50)  # 5%
        assert r["risk_level"] == "moderate"

    def test_low(self, engine):
        r = engine.diagnose(impressions=1000, views=80)  # 8%
        assert r["risk_level"] == "low"


# ── SEVERITY ──

class TestSeverity:
    def test_inverse_of_score(self, engine):
        r = engine.diagnose(impressions=1000, views=80)
        assert r["severity"] == round(1.0 - r["packaging_score"], 2)

    def test_high_for_low_ctr(self, engine):
        r = engine.diagnose(impressions=1000, views=10)  # 1%
        assert r["severity"] >= 0.8

    def test_low_for_high_ctr(self, engine):
        r = engine.diagnose(impressions=1000, views=100)  # 10%
        assert r["severity"] == 0.0


# ── CONFIDENCE ──

class TestConfidence:
    def test_low_impressions(self, engine):
        r = engine.diagnose(impressions=50, views=3)
        assert r["confidence"] == 0.5

    def test_high_impressions(self, engine):
        r = engine.diagnose(impressions=5000, views=250)
        assert r["confidence"] == 0.85


# ── DETERMINISM ──

class TestDeterminism:
    def test_ten_runs_identical(self, engine):
        results = [engine.diagnose(impressions=1000, views=50) for _ in range(10)]
        for r in results:
            assert r == results[0]


# ── ORCHESTRATOR INTEGRATION ──

class TestOrchestratorIntegration:
    def test_packaging_wins_when_highest(self):
        from analytics.unified_engine_orchestrator import UnifiedEngineOrchestrator
        o = UnifiedEngineOrchestrator()
        engine = ThumbnailQualityEngine()
        thumb = engine.diagnose(impressions=1000, views=10)  # 1% CTR → high severity

        r = o.orchestrate(
            {"severity": 0.1, "confidence": 0.85},
            {"ctr_severity": 0.1, "confidence": 0.7},
            {"conversion_severity": 0.1, "confidence": 0.85},
            {"severity": 0.1, "confidence": 0.75},
            {"severity": 0.1, "confidence": 0.85},
            thumbnail_result=thumb,
        )
        assert r["primary_constraint"] == "packaging"

    def test_packaging_ranked_correctly(self):
        from analytics.unified_engine_orchestrator import UnifiedEngineOrchestrator
        o = UnifiedEngineOrchestrator()
        engine = ThumbnailQualityEngine()
        thumb = engine.diagnose(impressions=1000, views=50)  # 5% CTR

        r = o.orchestrate(
            {"severity": 0.9, "confidence": 0.85},
            {"ctr_severity": 0.6, "confidence": 0.7},
            {"conversion_severity": 0.3, "confidence": 0.85},
            {"severity": 0.4, "confidence": 0.75},
            {"severity": 0.1, "confidence": 0.85},
            thumbnail_result=thumb,
        )
        # Retention (0.9) should still win
        assert r["primary_constraint"] == "retention"
        # Packaging should appear in ranked list
        constraints = [c[0] for c in r["ranked_constraints"]]
        assert "packaging" in constraints


# ── INPUT VALIDATION ──

class TestInputValidation:
    def test_negative_impressions(self, engine):
        with pytest.raises(ValueError):
            engine.diagnose(impressions=-1, views=0)

    def test_negative_views(self, engine):
        with pytest.raises(ValueError):
            engine.diagnose(impressions=100, views=-1)

    def test_string_input(self, engine):
        with pytest.raises(ValueError):
            engine.diagnose(impressions="abc", views=0)
