"""
WeeklySummaryGenerator — Unit Tests.

Validates deterministic output, no LLM, structured state,
scope isolation, and no-narrative.
"""

import pytest
from analytics.weekly_summary_generator import WeeklySummaryGenerator


@pytest.fixture
def generator():
    return WeeklySummaryGenerator()


def _analytics_data(**overrides):
    base = {
        "avg_view_percentage": 20.0,
        "avg_watch_minutes": 1.5,
        "avg_video_length_minutes": 8.0,
        "shorts_ratio": 0.3,
        "ctr_percent": 3.0,
        "channel_avg_ctr": 5.0,
        "impressions": 2000,
        "views": 5000,
        "subscribers_gained": 10,
        "channel_avg_conversion_rate": 1.0,
        "total_views": 5000,
        "shorts_views": 1500,
        "long_views": 3500,
        "shorts_avg_retention": 30.0,
        "long_avg_retention": 40.0,
        "current_period_views": 5000,
        "previous_period_views": 4000,
        "current_period_subs": 60,
        "previous_period_subs": 50,
    }
    base.update(overrides)
    return base


# ── OUTPUT STRUCTURE ──

class TestOutputStructure:
    def test_returns_dict(self, generator):
        r = generator.generate(_analytics_data())
        assert isinstance(r, dict)

    def test_has_primary_constraint(self, generator):
        r = generator.generate(_analytics_data())
        assert "primary_constraint" in r

    def test_has_severity(self, generator):
        r = generator.generate(_analytics_data())
        assert "primary_severity" in r

    def test_has_risk_level(self, generator):
        r = generator.generate(_analytics_data())
        assert "risk_level" in r

    def test_has_ranked_constraints(self, generator):
        r = generator.generate(_analytics_data())
        assert "ranked_constraints" in r

    def test_has_engine_severities(self, generator):
        r = generator.generate(_analytics_data())
        assert "engine_severities" in r

    def test_has_confidence(self, generator):
        r = generator.generate(_analytics_data())
        assert "confidence" in r

    def test_has_scope(self, generator):
        r = generator.generate(_analytics_data())
        assert r["scope"] == "channel"

    def test_has_report_type(self, generator):
        r = generator.generate(_analytics_data())
        assert r["report_type"] == "weekly_summary"


# ── DETERMINISM ──

class TestDeterminism:
    def test_ten_runs_identical(self, generator):
        data = _analytics_data()
        results = [generator.generate(data) for _ in range(10)]
        for r in results:
            assert r["primary_constraint"] == results[0]["primary_constraint"]
            assert r["primary_severity"] == results[0]["primary_severity"]
            assert r["risk_level"] == results[0]["risk_level"]
            assert r["confidence"] == results[0]["confidence"]

    def test_reproducible(self, generator):
        data = _analytics_data()
        r1 = generator.generate(data)
        r2 = generator.generate(data)
        assert r1["primary_constraint"] == r2["primary_constraint"]
        assert r1["primary_severity"] == r2["primary_severity"]


# ── CONSTRAINT DETECTION ──

class TestConstraintDetection:
    def test_retention_dominant(self, generator):
        """Low retention (20%) should make retention primary."""
        r = generator.generate(_analytics_data(avg_view_percentage=20.0))
        assert r["primary_constraint"] == "retention"

    def test_severity_populated(self, generator):
        r = generator.generate(_analytics_data())
        assert r["primary_severity"] > 0


# ── NO NARRATIVE ──

class TestNoNarrative:
    def test_no_text_fields(self, generator):
        """Output must not contain narrative text."""
        r = generator.generate(_analytics_data())
        output = str(r)
        for phrase in ["you should", "consider", "recommend",
                       "great job", "keep going", "well done"]:
            assert phrase not in output.lower()

    def test_no_llm_text(self, generator):
        """No LLM-generated text in output."""
        r = generator.generate(_analytics_data())
        # All values should be numbers, strings, lists, dicts — not paragraphs
        assert isinstance(r["primary_constraint"], str)
        assert len(r["primary_constraint"]) < 30  # Not a paragraph

    def test_no_summary_narrative(self, generator):
        """No 'summary' key with narrative text."""
        r = generator.generate(_analytics_data())
        assert "summary" not in r  # Old format had narrative summary


# ── NO LLM DEPENDENCY ──

class TestNoLLM:
    def test_no_gpt_import(self):
        """Module should not import OpenAI or call GPT."""
        import inspect
        import analytics.weekly_summary_generator as mod
        source = inspect.getsource(mod)
        assert "import openai" not in source.lower()
        assert "chat.completions" not in source

    def test_no_premium_formatter_import(self):
        """Module should not import PremiumOutputFormatter."""
        import inspect
        import analytics.weekly_summary_generator as mod
        source = inspect.getsource(mod)
        assert "PremiumOutputFormatter" not in source
