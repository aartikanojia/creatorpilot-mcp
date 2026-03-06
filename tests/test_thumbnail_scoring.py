"""
ThumbnailScoringModule — Unit Tests.

Validates packaging score, quality, risk level, severity,
confidence, determinism, input validation, and no-narrative.
"""

import pytest
from analytics.thumbnail_scoring import ThumbnailScoringModule


@pytest.fixture
def scorer():
    return ThumbnailScoringModule()


# ── OUTPUT STRUCTURE ──

class TestOutputStructure:
    def test_returns_dict(self, scorer):
        r = scorer.score(impressions=1000, views=50, ctr=5.0)
        assert isinstance(r, dict)

    def test_has_packaging_score(self, scorer):
        r = scorer.score(impressions=1000, views=50, ctr=5.0)
        assert "packaging_score" in r

    def test_has_packaging_quality(self, scorer):
        r = scorer.score(impressions=1000, views=50, ctr=5.0)
        assert "packaging_quality" in r

    def test_has_severity(self, scorer):
        r = scorer.score(impressions=1000, views=50, ctr=5.0)
        assert "severity" in r

    def test_has_risk_level(self, scorer):
        r = scorer.score(impressions=1000, views=50, ctr=5.0)
        assert "risk_level" in r

    def test_has_confidence(self, scorer):
        r = scorer.score(impressions=1000, views=50, ctr=5.0)
        assert "confidence" in r

    def test_score_is_float(self, scorer):
        r = scorer.score(impressions=1000, views=50, ctr=5.0)
        assert isinstance(r["packaging_score"], float)

    def test_severity_is_float(self, scorer):
        r = scorer.score(impressions=1000, views=50, ctr=5.0)
        assert isinstance(r["severity"], float)


# ── PACKAGING QUALITY ──

class TestPackagingQuality:
    def test_strong_above_6(self, scorer):
        r = scorer.score(impressions=1000, views=80, ctr=8.0)
        assert r["packaging_quality"] == "strong"

    def test_strong_at_7(self, scorer):
        r = scorer.score(impressions=1000, views=70, ctr=7.0)
        assert r["packaging_quality"] == "strong"

    def test_average_at_5(self, scorer):
        r = scorer.score(impressions=1000, views=50, ctr=5.0)
        assert r["packaging_quality"] == "average"

    def test_average_at_3(self, scorer):
        r = scorer.score(impressions=1000, views=30, ctr=3.0)
        assert r["packaging_quality"] == "average"

    def test_average_at_6(self, scorer):
        r = scorer.score(impressions=1000, views=60, ctr=6.0)
        assert r["packaging_quality"] == "average"

    def test_weak_at_2(self, scorer):
        r = scorer.score(impressions=1000, views=20, ctr=2.0)
        assert r["packaging_quality"] == "weak"

    def test_weak_at_1(self, scorer):
        r = scorer.score(impressions=1000, views=10, ctr=1.0)
        assert r["packaging_quality"] == "weak"

    def test_weak_at_0(self, scorer):
        r = scorer.score(impressions=1000, views=0, ctr=0.0)
        assert r["packaging_quality"] == "weak"


# ── RISK LEVEL ──

class TestRiskLevel:
    def test_critical_below_3(self, scorer):
        r = scorer.score(impressions=1000, views=20, ctr=2.5)
        assert r["risk_level"] == "critical"

    def test_critical_at_1(self, scorer):
        r = scorer.score(impressions=1000, views=10, ctr=1.0)
        assert r["risk_level"] == "critical"

    def test_moderate_at_4(self, scorer):
        r = scorer.score(impressions=1000, views=40, ctr=4.0)
        assert r["risk_level"] == "moderate"

    def test_moderate_at_6(self, scorer):
        r = scorer.score(impressions=1000, views=60, ctr=6.0)
        assert r["risk_level"] == "moderate"

    def test_low_above_6(self, scorer):
        r = scorer.score(impressions=1000, views=80, ctr=8.0)
        assert r["risk_level"] == "low"


# ── SEVERITY ──

class TestSeverity:
    def test_severity_inverse_of_score(self, scorer):
        r = scorer.score(impressions=1000, views=80, ctr=8.0)
        assert r["severity"] == round(1.0 - r["packaging_score"], 2)

    def test_severity_high_for_low_ctr(self, scorer):
        r = scorer.score(impressions=1000, views=10, ctr=1.0)
        assert r["severity"] >= 0.8

    def test_severity_low_for_high_ctr(self, scorer):
        r = scorer.score(impressions=1000, views=100, ctr=10.0)
        assert r["severity"] == 0.0

    def test_severity_range(self, scorer):
        r = scorer.score(impressions=1000, views=50, ctr=5.0)
        assert 0 <= r["severity"] <= 1


# ── CONFIDENCE ──

class TestConfidence:
    def test_low_impressions_low_confidence(self, scorer):
        r = scorer.score(impressions=50, views=5, ctr=5.0)
        assert r["confidence"] == 0.5

    def test_medium_impressions_medium_confidence(self, scorer):
        r = scorer.score(impressions=300, views=15, ctr=5.0)
        assert r["confidence"] == 0.65

    def test_high_impressions_high_confidence(self, scorer):
        r = scorer.score(impressions=5000, views=250, ctr=5.0)
        assert r["confidence"] == 0.85


# ── DETERMINISM ──

class TestDeterminism:
    def test_ten_runs_identical(self, scorer):
        results = [
            scorer.score(impressions=1000, views=50, ctr=5.0)
            for _ in range(10)
        ]
        for r in results:
            assert r["packaging_score"] == results[0]["packaging_score"]
            assert r["severity"] == results[0]["severity"]
            assert r["risk_level"] == results[0]["risk_level"]


# ── INPUT VALIDATION ──

class TestInputValidation:
    def test_negative_impressions(self, scorer):
        with pytest.raises(ValueError):
            scorer.score(impressions=-1, views=0, ctr=0)

    def test_negative_views(self, scorer):
        with pytest.raises(ValueError):
            scorer.score(impressions=100, views=-1, ctr=0)

    def test_negative_ctr(self, scorer):
        with pytest.raises(ValueError):
            scorer.score(impressions=100, views=0, ctr=-1)

    def test_string_impressions(self, scorer):
        with pytest.raises(ValueError):
            scorer.score(impressions="abc", views=0, ctr=0)


# ── NO NARRATIVE ──

class TestNoNarrative:
    def test_no_text_in_output(self, scorer):
        r = scorer.score(impressions=1000, views=50, ctr=5.0)
        output = str(r)
        for phrase in ["you should", "consider", "recommend",
                       "improve", "great job", "thumbnail"]:
            assert phrase not in output.lower()

    def test_no_llm(self):
        import inspect
        import analytics.thumbnail_scoring as mod
        source = inspect.getsource(mod)
        assert "import openai" not in source.lower()
        assert "chat.completions" not in source
