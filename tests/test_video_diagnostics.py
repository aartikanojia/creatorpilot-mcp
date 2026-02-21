"""
Phase 1.1 — Advanced Video Diagnostics Tests

Tests all 5 functions in analytics/diagnostics.py:
- classify_retention
- compute_channel_median
- compute_percentile_rank
- detect_momentum
- classify_format
- compute_performance_tier (bonus — composite)
"""

import pytest
from analytics.diagnostics import (
    classify_retention,
    compute_channel_median,
    compute_percentile_rank,
    detect_momentum,
    classify_format,
    compute_performance_tier,
)


# =============================================================================
# Helpers
# =============================================================================

def _video(view_count=None, avg_view_percentage=None, duration_seconds=None):
    """Return a dict simulating a Video ORM object."""
    return {
        "view_count": view_count,
        "avg_view_percentage": avg_view_percentage,
        "duration_seconds": duration_seconds,
    }


# =============================================================================
# TEST 1 — Retention Classification
# =============================================================================

class TestRetentionClassification:
    """Boundary-exact threshold tests for classify_retention."""

    def test_none_returns_unknown(self):
        assert classify_retention(None) == "Unknown"

    def test_exactly_60_is_strong_hook(self):
        assert classify_retention(60.0) == "Strong Hook"

    def test_above_60_is_strong_hook(self):
        assert classify_retention(75.0) == "Strong Hook"
        assert classify_retention(100.0) == "Strong Hook"

    def test_59_9_is_healthy_retention(self):
        assert classify_retention(59.9) == "Healthy Retention"

    def test_exactly_45_is_healthy_retention(self):
        assert classify_retention(45.0) == "Healthy Retention"

    def test_44_9_is_moderate_dropoff(self):
        assert classify_retention(44.9) == "Moderate Drop-off"

    def test_exactly_30_is_moderate_dropoff(self):
        assert classify_retention(30.0) == "Moderate Drop-off"

    def test_29_9_is_weak_retention(self):
        assert classify_retention(29.9) == "Weak Retention"

    def test_zero_is_weak_retention(self):
        assert classify_retention(0.0) == "Weak Retention"

    def test_negative_clamps_to_weak(self):
        # Negative is invalid data but should not crash
        assert classify_retention(-5.0) == "Weak Retention"

    def test_integer_input_works(self):
        assert classify_retention(50) == "Healthy Retention"


# =============================================================================
# TEST 2 — Channel Median
# =============================================================================

class TestChannelMedian:
    """Tests for compute_channel_median."""

    def test_empty_list_returns_none(self):
        result = compute_channel_median([])
        assert result == {"median_views": None, "median_avg_view_pct": None}

    def test_single_video(self):
        result = compute_channel_median([_video(view_count=1000)])
        assert result["median_views"] == 1000

    def test_two_videos_median(self):
        videos = [_video(view_count=100), _video(view_count=300)]
        result = compute_channel_median(videos)
        assert result["median_views"] == 200  # (100+300)/2

    def test_three_videos_median(self):
        videos = [
            _video(view_count=100),
            _video(view_count=500),
            _video(view_count=900),
        ]
        result = compute_channel_median(videos)
        assert result["median_views"] == 500

    def test_none_view_counts_excluded(self):
        videos = [
            _video(view_count=None),
            _video(view_count=200),
            _video(view_count=400),
        ]
        result = compute_channel_median(videos)
        assert result["median_views"] == 300

    def test_avg_view_pct_median(self):
        videos = [
            _video(avg_view_percentage=30.0),
            _video(avg_view_percentage=50.0),
            _video(avg_view_percentage=70.0),
        ]
        result = compute_channel_median(videos)
        assert result["median_avg_view_pct"] == 50.0

    def test_all_none_view_counts(self):
        videos = [_video(view_count=None), _video(view_count=None)]
        result = compute_channel_median(videos)
        assert result["median_views"] is None


# =============================================================================
# TEST 3 — Percentile Rank
# =============================================================================

class TestPercentileRank:
    """Tests for compute_percentile_rank."""

    def test_empty_list_returns_none(self):
        result = compute_percentile_rank(500, [])
        assert result is None

    def test_beats_all(self):
        result = compute_percentile_rank(1000, [100, 200, 300])
        assert result == 100.0

    def test_beats_none(self):
        result = compute_percentile_rank(10, [100, 200, 300])
        assert result == 0.0

    def test_beats_60_percent(self):
        result = compute_percentile_rank(500, [100, 200, 400, 600, 800])
        assert result == 60.0  # beats 3 out of 5

    def test_single_video_in_list_above(self):
        result = compute_percentile_rank(100, [200])
        assert result == 0.0

    def test_single_video_in_list_below(self):
        result = compute_percentile_rank(300, [200])
        assert result == 100.0

    def test_equal_to_channel_video_not_counted(self):
        # Strictly less than — equal counts as NOT beating
        result = compute_percentile_rank(200, [200, 200, 200])
        assert result == 0.0

    def test_result_rounded_to_one_decimal(self):
        # 1 out of 3: 33.333... → 33.3
        result = compute_percentile_rank(500, [100, 200, 1000])
        assert result == 66.7  # beats 100 and 200 (2 out of 3)


# =============================================================================
# TEST 4 — Momentum Detection
# =============================================================================

class TestMomentumDetection:
    """Tests for detect_momentum."""

    def test_none_last7_returns_unknown(self):
        assert detect_momentum(None, 400) == "Unknown"

    def test_none_prev28_returns_unknown(self):
        assert detect_momentum(200, None) == "Unknown"

    def test_both_none_returns_unknown(self):
        assert detect_momentum(None, None) == "Unknown"

    def test_zero_baseline_returns_unknown(self):
        assert detect_momentum(100, 0) == "Unknown"

    def test_rising(self):
        # weekly baseline = 400/4 = 100; last7=130 → ratio=1.3 > 1.2
        assert detect_momentum(130, 400) == "Rising"

    def test_exactly_1_2_is_stable(self):
        # ratio = 1.2 exactly → "Stable" (boundary: >1.2 is Rising)
        assert detect_momentum(120, 400) == "Stable"

    def test_stable_at_1_0(self):
        # ratio = 1.0
        assert detect_momentum(100, 400) == "Stable"

    def test_stable_at_lower_bound(self):
        # ratio = 0.8 exactly → "Stable" (boundary: ≥0.8)
        assert detect_momentum(80, 400) == "Stable"

    def test_declining(self):
        # weekly baseline = 400/4 = 100; last7=70 → ratio=0.7 < 0.8
        assert detect_momentum(70, 400) == "Declining"


# =============================================================================
# TEST 5 — Format Classification
# =============================================================================

class TestFormatClassification:
    """Tests for classify_format."""

    def test_none_duration_no_traffic_returns_unknown(self):
        assert classify_format(None, None) == "Unknown"

    def test_short_under_65_seconds(self):
        assert classify_format(64, None) == "Short"
        assert classify_format(30, None) == "Short"
        assert classify_format(0, None) == "Short"

    def test_exactly_65_is_standard(self):
        assert classify_format(65, None) == "Standard"

    def test_480_is_standard(self):
        assert classify_format(480, None) == "Standard"

    def test_481_is_long_form(self):
        assert classify_format(481, None) == "Long-form"

    def test_large_duration_is_long_form(self):
        assert classify_format(3600, None) == "Long-form"

    def test_shorts_dominant_traffic_overrides_duration(self):
        traffic = {"SHORTS": 800, "YT_SEARCH": 100, "SUGGESTED": 100}
        assert classify_format(120, traffic) == "Shorts"

    def test_shorts_below_threshold_uses_duration(self):
        # SHORTS is 30% — not dominant
        traffic = {"SHORTS": 300, "YT_SEARCH": 700}
        assert classify_format(120, traffic) == "Standard"

    def test_empty_traffic_dict_uses_duration(self):
        assert classify_format(30, {}) == "Short"


# =============================================================================
# TEST 6 — Performance Tier (percentile-primary)
# =============================================================================

class TestPerformanceTier:
    """Tests for compute_performance_tier — percentile is primary determinant."""

    def test_none_percentile_returns_unknown(self):
        assert compute_performance_tier(None, "Strong Hook") == "Unknown"
        assert compute_performance_tier(None, "Weak Retention") == "Unknown"

    # --- Top Performer boundary ---
    def test_exactly_75_is_top_performer(self):
        assert compute_performance_tier(75.0, "Weak Retention") == "Top Performer"

    def test_above_75_is_top_performer(self):
        assert compute_performance_tier(90.0, "Moderate Drop-off") == "Top Performer"

    def test_74_9_is_above_average(self):
        assert compute_performance_tier(74.9, "Strong Hook") == "Above Average"

    # --- Above Average boundary ---
    def test_exactly_50_is_above_average(self):
        assert compute_performance_tier(50.0, "Weak Retention") == "Above Average"

    def test_49_9_is_average(self):
        assert compute_performance_tier(49.9, "Strong Hook") == "Average"

    # --- Average boundary ---
    def test_exactly_25_is_average(self):
        assert compute_performance_tier(25.0, "Moderate Drop-off") == "Average"

    def test_24_9_is_underperformer(self):
        assert compute_performance_tier(24.9, "Healthy Retention") == "Underperformer"

    # --- Underperformer ---
    def test_zero_is_underperformer(self):
        assert compute_performance_tier(0.0, "Moderate Drop-off") == "Underperformer"

    def test_low_percentile_weak_retention_is_underperformer(self):
        assert compute_performance_tier(10.0, "Weak Retention") == "Underperformer"

    # --- Retention must NOT contradict percentile ---
    def test_high_percentile_weak_retention_still_top(self):
        """Weak retention MUST NOT downgrade a high-percentile video."""
        assert compute_performance_tier(80.0, "Weak Retention") == "Top Performer"

    def test_low_percentile_strong_retention_still_underperformer(self):
        """Strong retention MUST NOT upgrade a low-percentile video."""
        assert compute_performance_tier(10.0, "Strong Hook") == "Underperformer"

    def test_mid_percentile_strong_retention_does_not_skip_tier(self):
        """Strong retention at percentile=30 → Average, NOT Above Average."""
        assert compute_performance_tier(30.0, "Strong Hook") == "Average"

    def test_mid_percentile_weak_retention_at_60(self):
        """percentile=60 → Above Average regardless of retention."""
        assert compute_performance_tier(60.0, "Weak Retention") == "Above Average"


# =============================================================================
# TEST 7 — Performance Tier Consistency (spec-required)
# =============================================================================

class TestPerformanceTierConsistency:
    """
    Spec requirement: Percentile and Performance Tier must NEVER contradict.

    If percentile == 100 → tier MUST be Top Performer (all retentions).
    If percentile == 0   → tier MUST be Underperformer (all retentions).
    """

    ALL_RETENTIONS = [
        "Strong Hook",
        "Healthy Retention",
        "Moderate Drop-off",
        "Weak Retention",
        "Unknown",
    ]

    def test_percentile_100_always_top_performer(self):
        """100th percentile MUST be Top Performer regardless of retention."""
        for retention in self.ALL_RETENTIONS:
            result = compute_performance_tier(100.0, retention)
            assert result == "Top Performer", (
                f"percentile=100 with retention='{retention}' returned '{result}' "
                f"— must always be 'Top Performer'"
            )

    def test_percentile_0_always_underperformer(self):
        """0th percentile MUST be Underperformer regardless of retention."""
        for retention in self.ALL_RETENTIONS:
            result = compute_performance_tier(0.0, retention)
            assert result == "Underperformer", (
                f"percentile=0 with retention='{retention}' returned '{result}' "
                f"— must always be 'Underperformer'"
            )

    def test_high_percentile_no_downgrade_from_retention(self):
        """No retention value can downgrade tier when percentile ≥75."""
        for retention in self.ALL_RETENTIONS:
            result = compute_performance_tier(85.0, retention)
            assert result == "Top Performer", (
                f"percentile=85 should always be Top Performer, got '{result}' "
                f"with retention='{retention}'"
            )

    def test_low_percentile_no_upgrade_from_retention(self):
        """No retention value can upgrade tier when percentile <25."""
        for retention in self.ALL_RETENTIONS:
            result = compute_performance_tier(15.0, retention)
            assert result == "Underperformer", (
                f"percentile=15 should always be Underperformer, got '{result}' "
                f"with retention='{retention}'"
            )

    def test_above_average_band_consistent(self):
        """percentile in [50, 74.9] → always Above Average regardless of retention."""
        for percentile in [50.0, 60.0, 74.9]:
            for retention in self.ALL_RETENTIONS:
                result = compute_performance_tier(percentile, retention)
                assert result == "Above Average", (
                    f"percentile={percentile} with retention='{retention}' "
                    f"returned '{result}' — must be 'Above Average'"
                )

    def test_average_band_consistent(self):
        """percentile in [25, 49.9] → always Average regardless of retention."""
        for percentile in [25.0, 35.0, 49.9]:
            for retention in self.ALL_RETENTIONS:
                result = compute_performance_tier(percentile, retention)
                assert result == "Average", (
                    f"percentile={percentile} with retention='{retention}' "
                    f"returned '{result}' — must be 'Average'"
                )

