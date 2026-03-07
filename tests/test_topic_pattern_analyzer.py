"""
TopicPatternAnalyzer — Unit Tests.
"""

import pytest
from analytics.topic_pattern_analyzer import TopicPatternAnalyzer


@pytest.fixture
def analyzer():
    return TopicPatternAnalyzer()


def _lib(*items):
    """Helper: build video library from (title, views) tuples."""
    return [{"title": t, "views": v} for t, v in items]


REQUIRED_KEYS = [
    "top_theme", "top_theme_median_views",
    "weakest_theme", "weakest_theme_median_views",
    "theme_concentration",
]


# ── OUTPUT STRUCTURE ──

class TestOutputStructure:
    def test_returns_dict(self, analyzer):
        lib = _lib(("Cooking pasta recipe", 1000), ("Cooking cake recipe", 2000))
        r = analyzer.analyze(lib)
        assert isinstance(r, dict)

    @pytest.mark.parametrize("key", REQUIRED_KEYS)
    def test_has_required_key(self, analyzer, key):
        lib = _lib(("Cooking pasta", 1000), ("Cooking cake", 2000))
        r = analyzer.analyze(lib)
        assert key in r

    def test_views_are_ints(self, analyzer):
        lib = _lib(("Cooking pasta", 1000), ("Cooking cake", 2000))
        r = analyzer.analyze(lib)
        assert isinstance(r["top_theme_median_views"], int)
        assert isinstance(r["weakest_theme_median_views"], int)

    def test_concentration_valid(self, analyzer):
        lib = _lib(("Cooking pasta", 1000), ("Cooking cake", 2000))
        r = analyzer.analyze(lib)
        assert r["theme_concentration"] in ("low", "moderate", "high")


# ── THEME EXTRACTION ──

class TestThemeExtraction:
    def test_extract_two_words(self, analyzer):
        theme = analyzer.extract_theme("Cooking pasta recipe at home")
        assert theme == "cooking pasta"

    def test_extract_skips_stop_words(self, analyzer):
        theme = analyzer.extract_theme("My new cooking adventure")
        assert "my" not in theme
        assert "new" not in theme
        assert "cooking" in theme

    def test_single_word_title(self, analyzer):
        theme = analyzer.extract_theme("Vlog")
        assert theme == "vlog"

    def test_empty_title(self, analyzer):
        theme = analyzer.extract_theme("")
        assert isinstance(theme, str)
        assert len(theme) > 0


# ── TOP / WEAKEST THEME ──

class TestThemeIdentification:
    def test_top_theme(self, analyzer):
        lib = _lib(
            ("Cooking pasta homemade", 5000),
            ("Cooking pasta special", 3000),
            ("Travel vlog Europe trip", 1000),
            ("Travel vlog Asia trip", 500),
        )
        r = analyzer.analyze(lib)
        assert r["top_theme"] == "cooking pasta"

    def test_weakest_theme(self, analyzer):
        lib = _lib(
            ("Cooking pasta homemade", 5000),
            ("Cooking pasta special", 3000),
            ("Travel vlog Europe trip", 1000),
            ("Travel vlog Asia trip", 500),
        )
        r = analyzer.analyze(lib)
        assert r["weakest_theme"] == "travel vlog"

    def test_median_values(self, analyzer):
        lib = _lib(
            ("Cooking pasta homemade", 5000),
            ("Cooking pasta special", 3000),
            ("Travel vlog Europe trip", 1000),
            ("Travel vlog Asia trip", 500),
        )
        r = analyzer.analyze(lib)
        # Cooking pasta: median of [5000, 3000] = 4000
        assert r["top_theme_median_views"] == 4000
        # Travel vlog: median of [1000, 500] = 750
        assert r["weakest_theme_median_views"] == 750


# ── THEME CONCENTRATION ──

class TestThemeConcentration:
    def test_high_concentration(self, analyzer):
        lib = _lib(
            ("Gaming minecraft", 100),
            ("Gaming roblox", 200),
        )
        r = analyzer.analyze(lib)
        assert r["theme_concentration"] == "high"

    def test_moderate_concentration(self, analyzer):
        lib = _lib(
            ("Gaming mc", 100),
            ("Cooking pasta", 200),
            ("Travel vlog", 300),
        )
        r = analyzer.analyze(lib)
        assert r["theme_concentration"] == "moderate"

    def test_low_concentration(self, analyzer):
        lib = _lib(
            ("Gaming mc", 100),
            ("Cooking pasta", 200),
            ("Travel vlog", 300),
            ("Fitness workout", 400),
            ("Music production", 500),
        )
        r = analyzer.analyze(lib)
        assert r["theme_concentration"] == "low"


# ── EDGE CASES ──

class TestEdgeCases:
    def test_empty_library(self, analyzer):
        r = analyzer.analyze([])
        assert r["top_theme"] == "unknown"
        assert r["top_theme_median_views"] == 0

    def test_single_video(self, analyzer):
        lib = _lib(("Cooking pasta recipe", 5000))
        r = analyzer.analyze(lib)
        assert r["top_theme_median_views"] == 5000
        assert r["top_theme"] == r["weakest_theme"]

    def test_non_dict_videos_skipped(self, analyzer):
        lib = [{"title": "Cooking pasta", "views": 1000}, "bad_entry", None]
        r = analyzer.analyze(lib)
        assert r["top_theme_median_views"] == 1000


# ── DETERMINISM ──

class TestDeterminism:
    def test_ten_runs_identical(self, analyzer):
        lib = _lib(
            ("Cooking pasta", 5000),
            ("Travel vlog", 1000),
            ("Cooking cake", 3000),
        )
        results = [analyzer.analyze(lib) for _ in range(10)]
        for r in results:
            assert r == results[0]


# ── INPUT VALIDATION ──

class TestInputValidation:
    def test_non_list_raises(self, analyzer):
        with pytest.raises(ValueError):
            analyzer.analyze("not a list")

    def test_none_raises(self, analyzer):
        with pytest.raises(ValueError):
            analyzer.analyze(None)


# ── NO LLM ──

class TestNoLLM:
    def test_no_llm_imports(self):
        import inspect
        import analytics.topic_pattern_analyzer as mod
        source = inspect.getsource(mod)
        assert "import openai" not in source.lower()
        assert "chat.completions" not in source
        assert "langchain" not in source.lower()
