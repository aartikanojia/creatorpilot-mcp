"""
NextVideoBlueprintEngine — Unit Tests.
"""

import pytest
from analytics.next_video_blueprint_engine import NextVideoBlueprintEngine


@pytest.fixture
def engine():
    return NextVideoBlueprintEngine()


REQUIRED_KEYS = ["next_video_direction", "opening_approach", "content_structure", "creator_action"]


# ── OUTPUT STRUCTURE ──

class TestOutputStructure:
    def test_returns_dict(self, engine):
        r = engine.generate("retention")
        assert isinstance(r, dict)

    @pytest.mark.parametrize("key", REQUIRED_KEYS)
    def test_has_required_key(self, engine, key):
        r = engine.generate("retention")
        assert key in r

    @pytest.mark.parametrize("key", REQUIRED_KEYS)
    def test_values_are_strings(self, engine, key):
        r = engine.generate("retention")
        assert isinstance(r[key], str)

    @pytest.mark.parametrize("key", REQUIRED_KEYS)
    def test_values_are_non_empty(self, engine, key):
        r = engine.generate("retention")
        assert len(r[key]) > 0


# ── CONSTRAINT MAPPING ──

class TestConstraintMapping:
    def test_retention(self, engine):
        r = engine.generate("retention")
        assert "exciting moment" in r["next_video_direction"].lower() or "opening" in r["next_video_direction"].lower()
        assert "3 seconds" in r["creator_action"]

    def test_ctr(self, engine):
        r = engine.generate("ctr")
        assert "packaging" in r["next_video_direction"].lower()

    def test_conversion(self, engine):
        r = engine.generate("conversion")
        assert "subscribe" in r["next_video_direction"].lower() or "value" in r["next_video_direction"].lower()

    def test_shorts(self, engine):
        r = engine.generate("shorts")
        assert "storytelling" in r["next_video_direction"].lower() or "longer" in r["next_video_direction"].lower()

    def test_growth(self, engine):
        r = engine.generate("growth")
        assert "adjacent" in r["next_video_direction"].lower() or "topic" in r["next_video_direction"].lower()

    def test_unknown_fallback(self, engine):
        r = engine.generate("unknown_constraint")
        assert "next_video_direction" in r
        assert len(r["next_video_direction"]) > 0


# ── CASE INSENSITIVITY ──

class TestCaseInsensitivity:
    def test_uppercase(self, engine):
        r = engine.generate("RETENTION")
        assert "exciting moment" in r["next_video_direction"].lower() or "opening" in r["next_video_direction"].lower()

    def test_mixed_case(self, engine):
        r = engine.generate("Ctr")
        assert "packaging" in r["next_video_direction"].lower()

    def test_whitespace(self, engine):
        r = engine.generate("  conversion  ")
        assert "value" in r["next_video_direction"].lower() or "subscribe" in r["next_video_direction"].lower()


# ── DETERMINISM ──

class TestDeterminism:
    def test_ten_runs_identical(self, engine):
        results = [engine.generate("retention") for _ in range(10)]
        for r in results:
            assert r == results[0]

    @pytest.mark.parametrize("constraint", ["retention", "ctr", "conversion", "shorts", "growth"])
    def test_all_constraints_deterministic(self, engine, constraint):
        r1 = engine.generate(constraint)
        r2 = engine.generate(constraint)
        assert r1 == r2


# ── INPUT VALIDATION ──

class TestInputValidation:
    def test_non_string_raises(self, engine):
        with pytest.raises(ValueError):
            engine.generate(123)

    def test_none_raises(self, engine):
        with pytest.raises(ValueError):
            engine.generate(None)


# ── NO LLM ──

class TestNoLLM:
    def test_no_llm_imports(self):
        import inspect
        import analytics.next_video_blueprint_engine as mod
        source = inspect.getsource(mod)
        assert "import openai" not in source.lower()
        assert "chat.completions" not in source
        assert "langchain" not in source.lower()


# ── NO CREATIVE CONTENT ──

class TestNoCreativeContent:
    @pytest.mark.parametrize("constraint", ["retention", "ctr", "conversion", "shorts", "growth"])
    def test_no_specific_video_titles(self, engine, constraint):
        r = engine.generate(constraint)
        output = str(r).lower()
        for phrase in ["top 5", "top 10", "secrets", "you won't believe", "tutorial:"]:
            assert phrase not in output

    @pytest.mark.parametrize("constraint", ["retention", "ctr", "conversion", "shorts", "growth"])
    def test_no_emoji(self, engine, constraint):
        r = engine.generate(constraint)
        output = str(r)
        import re
        emoji_pattern = re.compile(
            "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF]"
        )
        assert not emoji_pattern.search(output)
