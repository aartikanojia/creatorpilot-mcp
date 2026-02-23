"""
Phase 1.2 — Strategy Engine Tests

Deterministic tests for analytics/strategy.py.
No LLM dependency — all rule-based.
"""

import pytest
from analytics.strategy import compute_strategy_framework


# =============================================================================
# TEST 1 — Strategy Mode Selection
# =============================================================================

class TestStrategyModeSelection:
    """Verify strategy_mode maps correctly from performance_tier."""

    def test_underperformer_returns_fix(self):
        result = compute_strategy_framework(
            "Underperformer", "Weak Retention", "Declining", "Standard"
        )
        assert result["strategy_mode"] == "Fix"

    def test_average_returns_optimize(self):
        result = compute_strategy_framework(
            "Average", "Moderate Drop-off", "Stable", "Standard"
        )
        assert result["strategy_mode"] == "Optimize"

    def test_above_average_returns_scale(self):
        result = compute_strategy_framework(
            "Above Average", "Healthy Retention", "Stable", "Standard"
        )
        assert result["strategy_mode"] == "Scale"

    def test_top_performer_returns_scale(self):
        result = compute_strategy_framework(
            "Top Performer", "Strong Hook", "Rising", "Standard"
        )
        assert result["strategy_mode"] == "Scale"

    def test_unknown_tier_returns_optimize_fallback(self):
        result = compute_strategy_framework(
            "Unknown", "Unknown", "Unknown", "Unknown"
        )
        assert result["strategy_mode"] == "Optimize"


# =============================================================================
# TEST 2 — Risk Level
# =============================================================================

class TestRiskLevel:
    """Verify risk_level maps correctly from performance_tier."""

    def test_underperformer_high_risk(self):
        result = compute_strategy_framework(
            "Underperformer", "Weak Retention", "Declining", "Standard"
        )
        assert result["risk_level"] == "High"

    def test_average_medium_risk(self):
        result = compute_strategy_framework(
            "Average", "Moderate Drop-off", "Stable", "Standard"
        )
        assert result["risk_level"] == "Medium"

    def test_above_average_low_risk(self):
        result = compute_strategy_framework(
            "Above Average", "Healthy Retention", "Stable", "Standard"
        )
        assert result["risk_level"] == "Low"

    def test_top_performer_low_risk(self):
        result = compute_strategy_framework(
            "Top Performer", "Strong Hook", "Rising", "Standard"
        )
        assert result["risk_level"] == "Low"


# =============================================================================
# TEST 3 — Primary / Secondary Focus
# =============================================================================

class TestFocusAreas:
    """Verify primary and secondary focus assignments."""

    def test_underperformer_weak_retention_hook_optimization(self):
        result = compute_strategy_framework(
            "Underperformer", "Weak Retention", "Declining", "Standard"
        )
        assert result["primary_focus"] == "Hook Optimization"
        assert result["secondary_focus"] == "Packaging Alignment"

    def test_underperformer_moderate_dropoff_hook_optimization(self):
        result = compute_strategy_framework(
            "Underperformer", "Moderate Drop-off", "Stable", "Standard"
        )
        assert result["primary_focus"] == "Hook Optimization"
        assert result["secondary_focus"] == "Packaging Alignment"

    def test_underperformer_healthy_retention_packaging(self):
        result = compute_strategy_framework(
            "Underperformer", "Healthy Retention", "Stable", "Standard"
        )
        assert result["primary_focus"] == "Packaging Adjustment"
        assert result["secondary_focus"] == "Packaging Alignment"

    def test_underperformer_strong_hook_packaging(self):
        result = compute_strategy_framework(
            "Underperformer", "Strong Hook", "Stable", "Standard"
        )
        assert result["primary_focus"] == "Packaging Adjustment"
        assert result["secondary_focus"] == "Packaging Alignment"

    def test_average_retention_lift(self):
        result = compute_strategy_framework(
            "Average", "Moderate Drop-off", "Stable", "Standard"
        )
        assert result["primary_focus"] == "Retention Lift"
        assert result["secondary_focus"] == "Thumbnail Refinement"

    def test_top_performer_replication_strategy(self):
        result = compute_strategy_framework(
            "Top Performer", "Strong Hook", "Rising", "Standard"
        )
        assert result["primary_focus"] == "Replication Strategy"
        assert result["secondary_focus"] == "Topic Expansion"

    def test_above_average_replication_strategy(self):
        result = compute_strategy_framework(
            "Above Average", "Healthy Retention", "Stable", "Standard"
        )
        assert result["primary_focus"] == "Replication Strategy"
        assert result["secondary_focus"] == "Topic Expansion"


# =============================================================================
# TEST 4 — Format Adjustments
# =============================================================================

class TestFormatAdjustments:
    """Verify conditional action appends."""

    def test_shorts_underperformer_adds_hook_tightening(self):
        result = compute_strategy_framework(
            "Underperformer", "Weak Retention", "Declining", "Shorts"
        )
        assert any(
            "first 3 seconds" in a for a in result["recommended_actions"]
        )

    def test_shorts_scale_no_hook_tightening(self):
        """Shorts + Scale should NOT add the Fix-specific hook action."""
        result = compute_strategy_framework(
            "Top Performer", "Strong Hook", "Rising", "Shorts"
        )
        assert not any(
            "first 3 seconds" in a for a in result["recommended_actions"]
        )

    def test_declining_adds_refresh_packaging(self):
        result = compute_strategy_framework(
            "Average", "Moderate Drop-off", "Declining", "Standard"
        )
        assert any(
            "Refresh packaging" in a for a in result["recommended_actions"]
        )

    def test_rising_scale_adds_topic_consistency(self):
        result = compute_strategy_framework(
            "Top Performer", "Strong Hook", "Rising", "Standard"
        )
        assert any(
            "topic consistency" in a for a in result["recommended_actions"]
        )

    def test_rising_fix_no_topic_consistency(self):
        """Rising + Fix should NOT add the Scale-specific action."""
        result = compute_strategy_framework(
            "Underperformer", "Weak Retention", "Rising", "Standard"
        )
        assert not any(
            "topic consistency" in a for a in result["recommended_actions"]
        )

    def test_stable_no_extra_actions(self):
        """Stable momentum should not add declining or rising actions."""
        result = compute_strategy_framework(
            "Average", "Moderate Drop-off", "Stable", "Standard"
        )
        assert not any(
            "Refresh packaging" in a for a in result["recommended_actions"]
        )
        assert not any(
            "topic consistency" in a for a in result["recommended_actions"]
        )


# =============================================================================
# TEST 5 — Recommended Actions Structure
# =============================================================================

class TestRecommendedActions:
    """Verify base actions are always present."""

    def test_fix_has_base_actions(self):
        result = compute_strategy_framework(
            "Underperformer", "Weak Retention", "Stable", "Standard"
        )
        actions = result["recommended_actions"]
        assert "Rework opening hook structure." in actions
        assert "Improve title clarity and positioning." in actions
        assert "Align thumbnail promise with first 10 seconds." in actions

    def test_optimize_has_base_actions(self):
        result = compute_strategy_framework(
            "Average", "Moderate Drop-off", "Stable", "Standard"
        )
        actions = result["recommended_actions"]
        assert "Enhance pacing in mid-section." in actions
        assert "Test thumbnail contrast and framing." in actions

    def test_scale_has_base_actions(self):
        result = compute_strategy_framework(
            "Top Performer", "Strong Hook", "Stable", "Standard"
        )
        actions = result["recommended_actions"]
        assert "Create follow-up within same topic cluster." in actions
        assert "Replicate hook structure pattern." in actions
        assert "Expand concept into series format." in actions


# =============================================================================
# TEST 6 — Execution Pattern
# =============================================================================

class TestExecutionPattern:
    """Verify execution_pattern is a non-empty string."""

    def test_fix_pattern_exists(self):
        result = compute_strategy_framework(
            "Underperformer", "Weak Retention", "Declining", "Standard"
        )
        assert isinstance(result["execution_pattern"], str)
        assert len(result["execution_pattern"]) > 20

    def test_optimize_pattern_exists(self):
        result = compute_strategy_framework(
            "Average", "Moderate Drop-off", "Stable", "Standard"
        )
        assert isinstance(result["execution_pattern"], str)
        assert len(result["execution_pattern"]) > 20

    def test_scale_pattern_exists(self):
        result = compute_strategy_framework(
            "Top Performer", "Strong Hook", "Rising", "Standard"
        )
        assert isinstance(result["execution_pattern"], str)
        assert len(result["execution_pattern"]) > 20


# =============================================================================
# TEST 7 — Return Shape
# =============================================================================

class TestReturnShape:
    """Verify all required keys are present."""

    REQUIRED_KEYS = [
        "strategy_mode",
        "primary_focus",
        "secondary_focus",
        "risk_level",
        "recommended_actions",
        "execution_pattern",
    ]

    def test_all_keys_present(self):
        result = compute_strategy_framework(
            "Average", "Moderate Drop-off", "Stable", "Standard"
        )
        for key in self.REQUIRED_KEYS:
            assert key in result, f"Missing key: {key}"

    def test_recommended_actions_is_list(self):
        result = compute_strategy_framework(
            "Average", "Moderate Drop-off", "Stable", "Standard"
        )
        assert isinstance(result["recommended_actions"], list)
        assert len(result["recommended_actions"]) >= 3


# =============================================================================
# TEST 8 — Risk Level Mapping (all 4 tiers)
# =============================================================================

class TestRiskLevelMapping:
    """Validate deterministic Performance Tier → Risk Level mapping."""

    TIER_RISK_MAP = {
        "Underperformer": "High",
        "Average": "Medium",
        "Above Average": "Low",
        "Top Performer": "Low",
    }

    def test_all_tiers_map_correctly(self):
        for tier, expected_risk in self.TIER_RISK_MAP.items():
            result = compute_strategy_framework(
                tier, "Moderate Drop-off", "Stable", "Standard"
            )
            assert result["risk_level"] == expected_risk, (
                f"Tier '{tier}' should have risk_level='{expected_risk}', "
                f"got '{result['risk_level']}'"
            )

    def test_unknown_tier_defaults_to_medium(self):
        result = compute_strategy_framework(
            "Unknown", "Unknown", "Unknown", "Unknown"
        )
        assert result["risk_level"] == "Medium"


# =============================================================================
# TEST 9 — Secondary Focus Mapping
# =============================================================================

class TestSecondaryFocusMapping:
    """Validate deterministic Primary Focus → Secondary Focus mapping."""

    def test_hook_optimization_maps_to_packaging_alignment(self):
        result = compute_strategy_framework(
            "Underperformer", "Weak Retention", "Stable", "Standard"
        )
        assert result["primary_focus"] == "Hook Optimization"
        assert result["secondary_focus"] == "Packaging Alignment"

    def test_packaging_adjustment_maps_to_packaging_alignment(self):
        result = compute_strategy_framework(
            "Underperformer", "Strong Hook", "Stable", "Standard"
        )
        assert result["primary_focus"] == "Packaging Adjustment"
        assert result["secondary_focus"] == "Packaging Alignment"

    def test_retention_lift_maps_to_thumbnail_refinement(self):
        result = compute_strategy_framework(
            "Average", "Moderate Drop-off", "Stable", "Standard"
        )
        assert result["primary_focus"] == "Retention Lift"
        assert result["secondary_focus"] == "Thumbnail Refinement"

    def test_replication_strategy_maps_to_topic_expansion(self):
        result = compute_strategy_framework(
            "Top Performer", "Strong Hook", "Rising", "Standard"
        )
        assert result["primary_focus"] == "Replication Strategy"
        assert result["secondary_focus"] == "Topic Expansion"

    def test_secondary_focus_consistent_across_retention_values(self):
        """Secondary focus should not change based on retention within same tier."""
        for retention in ["Weak Retention", "Moderate Drop-off"]:
            result = compute_strategy_framework(
                "Underperformer", retention, "Stable", "Standard"
            )
            assert result["secondary_focus"] == "Packaging Alignment"


# =============================================================================
# TEST 10 — Structure Order Consistency
# =============================================================================

class TestStructureOrder:
    """Verify key ordering remains constant across all tiers."""

    ALL_TIERS = ["Underperformer", "Average", "Above Average", "Top Performer"]

    def test_keys_always_in_same_order(self):
        expected_keys = [
            "strategy_mode", "primary_focus", "secondary_focus",
            "risk_level", "recommended_actions", "execution_pattern",
        ]
        for tier in self.ALL_TIERS:
            result = compute_strategy_framework(
                tier, "Moderate Drop-off", "Stable", "Standard"
            )
            assert list(result.keys()) == expected_keys, (
                f"Key order mismatch for tier '{tier}'"
            )

