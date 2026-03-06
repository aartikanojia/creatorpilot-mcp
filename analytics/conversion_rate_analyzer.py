"""
Conversion Rate Analyzer v1 — Subscriber Funnel Diagnosis.

Diagnoses view → subscriber conversion performance:
- Conversion severity (0-1)
- Risk level
- Relative underperformance vs channel baseline
- Funnel weakness flag
- Confidence score

Rules:
- Uses only structured numeric inputs
- Produces strict JSON-compatible dict
- Never calls LLM
- Never injects strategy
- Never references archetype, retention, or CTR
- Never produces narrative text
"""

import logging

logger = logging.getLogger(__name__)


class ConversionRateAnalyzer:
    """
    Deterministic Conversion Rate Analyzer v1.

    Diagnoses:
    - Absolute conversion severity
    - Relative underperformance vs channel baseline
    - Funnel weakness (high views + no subs)

    No strategy. No LLM. No narrative.
    """

    def diagnose(
        self,
        views: int,
        subscribers_gained: int,
        channel_avg_conversion_rate: float,
    ) -> dict:

        self._validate_inputs(views, subscribers_gained, channel_avg_conversion_rate)

        # ── 1. Compute Conversion Rate ──

        if views > 0:
            conversion_rate = (subscribers_gained / views) * 100
        else:
            conversion_rate = 0.0

        # ── 2. Absolute Severity ──

        if conversion_rate >= 1.5:
            severity = 0.1
        elif conversion_rate >= 1.0:
            severity = 0.3
        elif conversion_rate >= 0.5:
            severity = 0.6
        elif conversion_rate >= 0.1:
            severity = 0.8
        else:
            severity = 0.95

        # ── 3. Relative Underperformance ──

        relative_underperformance = False

        if channel_avg_conversion_rate > 0:
            if conversion_rate < channel_avg_conversion_rate * 0.7:
                severity += 0.1
                relative_underperformance = True

        severity = min(severity, 1.0)

        # ── 4. Funnel Weakness Detection ──

        funnel_weakness = False

        if views > 1000 and conversion_rate < 0.3:
            funnel_weakness = True

        # ── 5. Risk Mapping ──

        if severity >= 0.9:
            risk_level = "critical"
        elif severity >= 0.7:
            risk_level = "high"
        elif severity >= 0.5:
            risk_level = "moderate"
        else:
            risk_level = "low"

        # ── 6. Confidence ──

        if views < 100:
            confidence = 0.5
        elif views < 500:
            confidence = 0.7
        else:
            confidence = 0.85

        result = {
            "conversion_rate_percent": round(conversion_rate, 2),
            "channel_avg_conversion_rate": channel_avg_conversion_rate,
            "conversion_severity": round(severity, 2),
            "risk_level": risk_level,
            "relative_underperformance": relative_underperformance,
            "funnel_weakness": funnel_weakness,
            "confidence": confidence,
        }

        logger.info(
            f"[ConversionDiagnosis] severity={result['conversion_severity']}, "
            f"risk={result['risk_level']}, funnel_weak={result['funnel_weakness']}, "
            f"underperform={result['relative_underperformance']}"
        )

        return result

    # ── Validation ──

    def _validate_inputs(
        self,
        views: int,
        subscribers_gained: int,
        channel_avg_conversion_rate: float,
    ):
        if views < 0:
            raise ValueError("views cannot be negative")

        if subscribers_gained < 0:
            raise ValueError("subscribers_gained cannot be negative")

        if channel_avg_conversion_rate < 0:
            raise ValueError("channel_avg_conversion_rate cannot be negative")
