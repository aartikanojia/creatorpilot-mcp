"""
Growth Trend Explanation Engine v1 — Trend Classification.

Classifies channel growth trend using structured historical metrics:
- Growth direction (strong_growth → sharp_decline)
- Velocity classification (volatile / accelerating / steady)
- Acceleration flag
- Severity score (0-1)
- Risk level
- Confidence

Rules:
- Uses only structured numeric inputs
- Produces strict JSON-compatible dict
- Never calls LLM
- Never injects strategy
- Never produces narrative text
"""

import logging

logger = logging.getLogger(__name__)


class GrowthTrendExplanationEngine:
    """
    Deterministic Growth Trend Engine v1.

    Classifies:
    - Growth direction from view delta
    - Velocity from absolute rate
    - Acceleration from dual-metric uptrend

    No strategy. No LLM. No narrative.
    """

    def diagnose(
        self,
        current_period_views: int,
        previous_period_views: int,
        current_period_subs: int,
        previous_period_subs: int,
    ) -> dict:

        self._validate_inputs(
            current_period_views, previous_period_views,
            current_period_subs, previous_period_subs,
        )

        # ── 1. View Growth Rate ──

        if previous_period_views > 0:
            view_growth_rate = (
                (current_period_views - previous_period_views)
                / previous_period_views
            ) * 100
        else:
            view_growth_rate = 0.0

        # ── 2. Subscriber Growth Rate ──

        if previous_period_subs > 0:
            sub_growth_rate = (
                (current_period_subs - previous_period_subs)
                / previous_period_subs
            ) * 100
        else:
            sub_growth_rate = 0.0

        # ── 3. Direction ──

        if view_growth_rate >= 25:
            direction = "strong_growth"
        elif view_growth_rate >= 10:
            direction = "moderate_growth"
        elif view_growth_rate >= -10:
            direction = "stable"
        elif view_growth_rate >= -25:
            direction = "moderate_decline"
        else:
            direction = "sharp_decline"

        # ── 4. Velocity ──

        abs_growth = abs(view_growth_rate)

        if abs_growth >= 40:
            velocity = "volatile"
        elif abs_growth >= 20:
            velocity = "accelerating"
        else:
            velocity = "steady"

        # ── 5. Acceleration Flag ──

        accelerating_growth = (
            current_period_views > previous_period_views
            and current_period_subs > previous_period_subs
        )

        # ── 6. Severity ──

        if direction == "sharp_decline":
            severity = 0.9
        elif direction == "moderate_decline":
            severity = 0.7
        elif direction == "stable":
            severity = 0.3
        elif direction == "moderate_growth":
            severity = 0.2
        else:  # strong_growth
            severity = 0.1

        if sub_growth_rate < -20:
            severity += 0.1

        severity = min(severity, 1.0)

        # ── 7. Risk Level ──

        if severity >= 0.85:
            risk_level = "critical"
        elif severity >= 0.7:
            risk_level = "high"
        elif severity >= 0.5:
            risk_level = "moderate"
        else:
            risk_level = "low"

        # ── 8. Confidence ──

        total_views = current_period_views + previous_period_views

        if total_views < 500:
            confidence = 0.6
        elif total_views < 5000:
            confidence = 0.75
        else:
            confidence = 0.85

        result = {
            "view_growth_rate_percent": round(view_growth_rate, 2),
            "subscriber_growth_rate_percent": round(sub_growth_rate, 2),
            "direction": direction,
            "velocity": velocity,
            "accelerating_growth": accelerating_growth,
            "severity": round(severity, 2),
            "risk_level": risk_level,
            "confidence": confidence,
        }

        logger.info(
            f"[GrowthTrend] direction={result['direction']}, "
            f"velocity={result['velocity']}, severity={result['severity']}, "
            f"risk={result['risk_level']}, accel={result['accelerating_growth']}"
        )

        return result

    # ── Validation ──

    def _validate_inputs(
        self,
        current_period_views: int,
        previous_period_views: int,
        current_period_subs: int,
        previous_period_subs: int,
    ):
        if current_period_views < 0:
            raise ValueError("current_period_views cannot be negative")
        if previous_period_views < 0:
            raise ValueError("previous_period_views cannot be negative")
        if current_period_subs < 0:
            raise ValueError("current_period_subs cannot be negative")
        if previous_period_subs < 0:
            raise ValueError("previous_period_subs cannot be negative")
