"""
Phase 1.2 — Strategy Engine

Deterministic strategy framework computed from diagnostic labels.
No raw metrics, no LLM dependency, fully testable.
"""

from typing import Optional


# ── Action Templates ──────────────────────────────────────────────────

_FIX_ACTIONS = [
    "Rework opening hook structure.",
    "Improve title clarity and positioning.",
    "Align thumbnail promise with first 10 seconds.",
]

_OPTIMIZE_ACTIONS = [
    "Enhance pacing in mid-section.",
    "Test thumbnail contrast and framing.",
    "Introduce stronger mid-video retention trigger.",
]

_SCALE_ACTIONS = [
    "Create follow-up within same topic cluster.",
    "Replicate hook structure pattern.",
    "Expand concept into series format.",
]

# ── Execution Pattern Templates ───────────────────────────────────────

_EXECUTION_PATTERNS = {
    "Fix": (
        "Focus the next 2–3 uploads on isolating the weakest variable — "
        "hook, packaging, or format alignment — and iterate with a single "
        "change per upload to identify what moves retention."
    ),
    "Optimize": (
        "Use the next upload cycle to A/B test one element at a time — "
        "thumbnail framing, pacing structure, or mid-roll retention hooks — "
        "while keeping topic and format constant."
    ),
    "Scale": (
        "Maintain the current content pattern across the next 3–5 uploads, "
        "extending the topic cluster with adjacent angles while preserving "
        "the hook and packaging structure that drove performance."
    ),
}


def compute_strategy_framework(
    performance_tier: str,
    retention_category: str,
    momentum_status: str,
    format_type: str,
) -> dict:
    """
    Compute a deterministic strategy framework from diagnostic labels.

    Uses ONLY pre-computed diagnostic labels — never raw metrics.
    Returns a structured dict that the LLM renders verbatim.

    Args:
        performance_tier: Output of compute_performance_tier().
        retention_category: Output of classify_retention().
        momentum_status: Output of detect_momentum().
        format_type: Output of classify_format().

    Returns:
        Strategy framework dict with keys:
            strategy_mode, primary_focus, secondary_focus,
            risk_level, recommended_actions, execution_pattern
    """

    # ── Tier-based strategy mode ──────────────────────────────────────

    if performance_tier == "Underperformer":
        strategy_mode = "Fix"
        risk_level = "High"

        if retention_category in ("Weak Retention", "Moderate Drop-off"):
            primary_focus = "Hook Optimization"
        else:
            primary_focus = "Packaging Adjustment"

        secondary_focus = "Packaging Alignment"
        actions = list(_FIX_ACTIONS)

    elif performance_tier == "Average":
        strategy_mode = "Optimize"
        risk_level = "Medium"
        primary_focus = "Retention Lift"
        secondary_focus = "Thumbnail Refinement"
        actions = list(_OPTIMIZE_ACTIONS)

    elif performance_tier in ("Above Average", "Top Performer"):
        strategy_mode = "Scale"
        risk_level = "Low"
        primary_focus = "Replication Strategy"
        secondary_focus = "Topic Expansion"
        actions = list(_SCALE_ACTIONS)

    else:
        # Unknown / fallback
        strategy_mode = "Optimize"
        risk_level = "Medium"
        primary_focus = "General Review"
        secondary_focus = "Content Audit"
        actions = list(_OPTIMIZE_ACTIONS)

    # ── Format adjustments ────────────────────────────────────────────

    if format_type == "Shorts" and strategy_mode == "Fix":
        actions.append("Tighten first 3 seconds to improve early retention.")

    if momentum_status == "Declining":
        actions.append(
            "Refresh packaging to reintroduce algorithmic testing."
        )

    if momentum_status == "Rising" and strategy_mode == "Scale":
        actions.append(
            "Maintain topic consistency for next 3 uploads."
        )

    # ── Build result ──────────────────────────────────────────────────

    return {
        "strategy_mode": strategy_mode,
        "primary_focus": primary_focus,
        "secondary_focus": secondary_focus,
        "risk_level": risk_level,
        "recommended_actions": actions,
        "execution_pattern": _EXECUTION_PATTERNS[strategy_mode],
    }
