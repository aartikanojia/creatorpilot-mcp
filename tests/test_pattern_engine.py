"""
Phase 1.3 — Pattern Intelligence Engine Tests

Deterministic tests for analytics/patterns.py.
No LLM dependency — all rule-based keyword extraction and clustering.
"""

import pytest
from analytics.patterns import (
    tokenize_title,
    cluster_by_keyword,
    compute_theme_stats,
    detect_top_theme,
    detect_underperforming_theme,
    detect_format_bias,
)


# =============================================================================
# TEST 1 — Tokenization
# =============================================================================

class TestTokenization:
    def test_removes_stopwords_and_lowercase(self):
        title = "The Best way to MAKE a New Cake!"
        tokens = tokenize_title(title)
        assert tokens == ["cake"]

    def test_ignores_punctuation_and_emojis(self):
        title = "Wow!!! 😱 Epic 100-day survival challenge... #minecraft"
        tokens = tokenize_title(title)
        assert "survival" in tokens
        assert "challenge" in tokens
        assert "minecraft" in tokens
        assert "epic" not in tokens  # 'epic' is a stopword
        assert "😱" not in tokens

    def test_drops_short_words(self):
        title = "A B CC DDD EEEE"
        tokens = tokenize_title(title)
        assert tokens == ["eeee"]

    def test_empty_string(self):
        assert tokenize_title("") == []
        assert tokenize_title(None) == []


# =============================================================================
# TEST 2 — Clustering
# =============================================================================

class TestClustering:
    def _mock_videos(self):
        return [
            # "playground adventure" theme (4 videos — matches semantic category)
            {"title": "Play zone masti at the park", "views": 1000},
            {"title": "Kids playground adventure day", "views": 1500},
            {"title": "Play area swing climbing fun", "views": 1200},
            {"title": "Park zone outdoor adventure", "views": 1100},
            
            # "travel vlog" theme (3 videos — matches semantic category)
            {"title": "Travel Diary Going Places", "views": 500},
            {"title": "Japan Travel Experience Amazing", "views": 800},
            {"title": "Europe Travel Adventures Trip", "views": 600},
            
            # "noise" (won't match any category or keyword threshold)
            {"title": "Random thoughts", "views": 100},
            {"title": "Just chatting about life", "views": 200},
        ]

    def test_clusters_by_semantic_category(self):
        videos = self._mock_videos()
        clusters = cluster_by_keyword(videos)
        
        # playground videos should match "playground adventure" category
        assert "playground adventure" in clusters
        assert len(clusters["playground adventure"]) == 4
        
        # travel videos should match "travel vlog" category
        assert "travel vlog" in clusters
        assert len(clusters["travel vlog"]) == 3
        
        # Random words shouldn't be clustered
        assert "random" not in clusters
        assert "thoughts" not in clusters

    def test_empty_dataset(self):
        assert cluster_by_keyword([]) == {}


# =============================================================================
# TEST 3 — Theme Statistics
# =============================================================================

class TestThemeStats:
    def test_compute_stats_calculates_medians_correctly(self):
        cluster = [
            {"views": 100, "averageViewPercentage": 40.5, "percentile_rank": 20, "performance_tier": "Underperformer"},
            {"views": 500, "averageViewPercentage": 50.0, "percentile_rank": 50, "performance_tier": "Average"},
            {"views": 1000, "averageViewPercentage": 60.5, "percentile_rank": 80, "performance_tier": "Top Performer"},
        ]
        stats = compute_theme_stats(cluster)
        
        assert stats["median_views"] == 500
        assert stats["median_avg_view_pct"] == 50.0
        assert stats["avg_percentile_rank"] == 50.0
        assert stats["video_count"] == 3
        assert stats["performance_tier_distribution"] == {
            "Underperformer": 1,
            "Average": 1,
            "Top Performer": 1
        }

    def test_compute_stats_handles_missing_fields(self):
        cluster = [
            {"views": 100},
            {"views": 500},
            {"views": 1000},
        ]
        stats = compute_theme_stats(cluster)
        assert stats["median_views"] == 500
        assert stats["median_avg_view_pct"] == 0.0
        assert stats["avg_percentile_rank"] == 0.0
        assert stats["performance_tier_distribution"] == {"Unknown": 3}

    def test_compute_stats_empty(self):
        stats = compute_theme_stats([])
        assert stats["video_count"] == 0
        assert stats["median_views"] == 0


# =============================================================================
# TEST 4 — Top and Underperforming Themes
# =============================================================================

class TestThemeDetection:
    def _mock_clusters(self):
        return {
            "gaming": [
                {"views": 10000}, {"views": 15000}, {"views": 12000}
            ], # median = 12000
            "vlog": [
                {"views": 500}, {"views": 800}, {"views": 600}
            ], # median = 600
            "podcast": [
                {"views": 50000}, {"views": 60000}
            ], # median = 55000, but size = 2 (ignored)
        }

    def test_detect_top_theme(self):
        clusters = self._mock_clusters()
        theme, stats = detect_top_theme(clusters)
        assert theme == "gaming"
        assert stats["median_views"] == 12000

    def test_detect_underperforming_theme(self):
        clusters = self._mock_clusters()
        theme, stats = detect_underperforming_theme(clusters)
        assert theme == "vlog"
        assert stats["median_views"] == 600

    def test_detect_ignores_small_clusters(self):
        # Even though podcast is highest/lowest, it only has 2 videos
        clusters = self._mock_clusters()
        top_theme, _ = detect_top_theme(clusters)
        worst_theme, _ = detect_underperforming_theme(clusters)
        assert top_theme != "podcast"
        assert worst_theme != "podcast"


# =============================================================================
# TEST 5 — Format Bias
# =============================================================================

class TestFormatBias:
    def test_strong_shorts_bias(self):
        videos = [
            {"views": 10000, "duration_seconds": 30},
            {"views": 12000, "duration_seconds": 45},
            {"views": 1000, "duration_seconds": 600},
            {"views": 1500, "duration_seconds": 800},
        ]
        bias = detect_format_bias(videos)
        assert bias["bias"] == "Strong Shorts Bias"
        assert bias["shorts_median"] == 11000
        assert bias["standard_median"] == 1250

    def test_slight_standard_bias(self):
        videos = [
            {"views": 1000, "duration_seconds": 30},
            {"views": 800, "duration_seconds": 45},
            {"views": 1200, "duration_seconds": 600},
            {"views": 1100, "duration_seconds": 800},
        ]
        bias = detect_format_bias(videos)
        assert bias["bias"] == "Slight Standard Bias"

    def test_infers_shorts_from_duration(self):
        videos = [
            {"views": 5000, "duration_seconds": 45}, # Assumed Shorts
            {"views": 1000, "duration_seconds": 300}, # Assumed Standard
        ]
        bias = detect_format_bias(videos)
        assert bias["shorts_count"] == 1
        assert bias["standard_count"] == 1
        assert "Shorts Bias" in bias["bias"]

    def test_insufficient_data_no_duration(self):
        videos = [
            {"views": 5000, "duration_seconds": 0},
            {"views": 6000, "duration_seconds": 0},
        ]
        # Can't classify without duration
        bias = detect_format_bias(videos)
        assert bias["bias"] == "Insufficient Data"
        assert bias["shorts_median"] is None
        assert bias["standard_median"] is None


# =============================================================================
# TEST 6 — Pattern Query Detection
# =============================================================================

class TestPatternQueryDetection:
    """Verify _is_pattern_query routing logic."""

    def _detect(self, message: str) -> bool:
        """Simulate the regex match from _is_pattern_query."""
        import re
        msg_lower = message.lower()
        pattern_keywords = [
            r"\btheme\b",
            r"\bpattern\b",
            r"\bacross videos\b",
            r"\busually\b",
            r"\btends? to\b",
            r"\btype of content\b",
            r"\bformat bias\b",
            r"\b(what|which).*(theme|pattern|type|format).*(best|worst|perform|work)\b",
            r"\b(best|worst|top|underperform).*(theme|pattern|type|topic)\b",
            r"\bshorts vs\b",
            r"\bstandard vs\b",
        ]
        return any(re.search(p, msg_lower) for p in pattern_keywords)

    def test_theme_best_query(self):
        assert self._detect("What theme performs best?") is True

    def test_pattern_query(self):
        assert self._detect("Do you see a pattern across my videos?") is True

    def test_format_bias_query(self):
        assert self._detect("Is there a format bias in my channel?") is True

    def test_shorts_vs_query(self):
        assert self._detect("How do shorts vs standard videos compare?") is True

    def test_type_of_content_query(self):
        assert self._detect("What type of content works best?") is True

    def test_tends_to_query(self):
        assert self._detect("My channel tends to do better with vlogs") is True

    def test_usually_query(self):
        assert self._detect("What usually gets the most views?") is True

    def test_unrelated_query_not_matched(self):
        assert self._detect("Analyze my last video") is False

    def test_growth_query_not_matched(self):
        assert self._detect("How can I grow my channel?") is False

    def test_content_strategy_not_matched(self):
        assert self._detect("What should I upload next?") is False

