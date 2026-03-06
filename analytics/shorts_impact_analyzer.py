"""
Shorts Impact Analyzer v1 — Format Dependency Diagnosis.

Diagnoses Shorts traffic dependency and format risk:
- Shorts traffic ratio
- Format bias classification
- Retention gap (long vs shorts)
- Shorts dependence risk flag
- Severity score (0-1)
- Confidence

Rules:
- Uses only structured numeric inputs
- Produces strict JSON-compatible dict
- Never calls LLM
- Never injects strategy
- Never references archetype, CTR, or conversion
- Never produces narrative text
"""

import logging

logger = logging.getLogger(__name__)


class ShortsImpactAnalyzer:
    """
    Deterministic Shorts Impact Analyzer v1.

    Diagnoses:
    - Format bias (shorts_dominant / shorts_heavy / balanced / long_form_dominant)
    - Shorts dependence risk
    - Retention gap between formats

    No strategy. No LLM. No narrative.
    """

    def diagnose(
        self,
        total_views: int,
        shorts_views: int,
        long_views: int,
        shorts_avg_retention: float,
        long_avg_retention: float,
    ) -> dict:

        self._validate_inputs(
            total_views, shorts_views, long_views,
            shorts_avg_retention, long_avg_retention,
        )

        # ── 1. Shorts Ratio ──

        if total_views > 0:
            shorts_ratio = shorts_views / total_views
        else:
            shorts_ratio = 0.0

        # ── 2. Format Bias ──

        if shorts_ratio >= 0.75:
            format_bias = "shorts_dominant"
        elif shorts_ratio >= 0.40:
            format_bias = "shorts_heavy"
        elif shorts_ratio >= 0.20:
            format_bias = "balanced"
        else:
            format_bias = "long_form_dominant"

        # ── 3. Retention Gap ──

        retention_gap = long_avg_retention - shorts_avg_retention

        # ── 4. Shorts Dependence Risk ──

        shorts_dependence_risk = False

        if shorts_ratio >= 0.75 and long_avg_retention < 30:
            shorts_dependence_risk = True

        # ── 5. Severity ──

        if shorts_ratio >= 0.85:
            severity = 0.9
        elif shorts_ratio >= 0.75:
            severity = 0.8
        elif shorts_ratio >= 0.60:
            severity = 0.6
        elif shorts_ratio >= 0.40:
            severity = 0.4
        else:
            severity = 0.2

        if long_avg_retention < 25:
            severity += 0.1

        if shorts_dependence_risk:
            severity += 0.1

        severity = min(severity, 1.0)

        # ── 6. Risk Level ──

        if severity >= 0.9:
            risk_level = "critical"
        elif severity >= 0.7:
            risk_level = "high"
        elif severity >= 0.5:
            risk_level = "moderate"
        else:
            risk_level = "low"

        # ── 7. Confidence ──

        if total_views < 200:
            confidence = 0.6
        elif total_views < 1000:
            confidence = 0.75
        else:
            confidence = 0.85

        result = {
            "shorts_ratio": round(shorts_ratio, 2),
            "format_bias": format_bias,
            "shorts_avg_retention": shorts_avg_retention,
            "long_avg_retention": long_avg_retention,
            "retention_gap": round(retention_gap, 2),
            "shorts_dependence_risk": shorts_dependence_risk,
            "severity": round(severity, 2),
            "risk_level": risk_level,
            "confidence": confidence,
        }

        logger.info(
            f"[ShortsImpact] ratio={result['shorts_ratio']}, "
            f"bias={result['format_bias']}, severity={result['severity']}, "
            f"risk={result['risk_level']}, dependence={result['shorts_dependence_risk']}"
        )

        return result

    # ── Validation ──

    def _validate_inputs(
        self,
        total_views: int,
        shorts_views: int,
        long_views: int,
        shorts_avg_retention: float,
        long_avg_retention: float,
    ):
        if total_views < 0:
            raise ValueError("total_views cannot be negative")
        if shorts_views < 0:
            raise ValueError("shorts_views cannot be negative")
        if long_views < 0:
            raise ValueError("long_views cannot be negative")
        if shorts_avg_retention < 0:
            raise ValueError("shorts_avg_retention cannot be negative")
        if long_avg_retention < 0:
            raise ValueError("long_avg_retention cannot be negative")
