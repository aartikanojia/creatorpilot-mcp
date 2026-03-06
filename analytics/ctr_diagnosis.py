"""
CTR Diagnosis Engine v1 — Deterministic Distribution Gate.

Evaluates click-through rate performance:
- CTR severity (0-1)
- Risk level
- Distribution blockage status
- Relative underperformance vs channel baseline
- Confidence score

Rules:
- Uses only structured numeric inputs
- Produces strict JSON-compatible dict
- Never calls LLM
- Never injects strategy
- Never references archetype or retention
- Never produces narrative text
"""

import logging

logger = logging.getLogger(__name__)


class CTRDiagnosisEngine:
    """
    Deterministic CTR Diagnosis Engine v1.

    Diagnoses:
    - Absolute CTR severity
    - Relative underperformance vs channel baseline
    - Distribution blockage (impressions + low CTR)

    No strategy. No LLM. No narrative.
    """

    def diagnose(
        self,
        ctr_percent: float,
        channel_avg_ctr: float,
        impressions: int,
    ) -> dict:

        self._validate_inputs(ctr_percent, channel_avg_ctr, impressions)

        # ── 1. Absolute Severity ──

        if ctr_percent >= 8:
            severity = 0.1
        elif ctr_percent >= 6:
            severity = 0.3
        elif ctr_percent >= 4:
            severity = 0.6
        elif ctr_percent >= 2:
            severity = 0.8
        else:
            severity = 0.95

        # ── 2. Relative Underperformance ──

        relative_underperformance = False

        if channel_avg_ctr > 0:
            if ctr_percent < channel_avg_ctr * 0.7:
                severity += 0.1
                relative_underperformance = True

        severity = min(severity, 1.0)

        # ── 3. Distribution Block ──

        distribution_blocked = False

        if impressions > 1000 and ctr_percent < 4:
            distribution_blocked = True

        # ── 4. Risk Mapping ──

        if severity >= 0.9:
            risk_level = "critical"
        elif severity >= 0.7:
            risk_level = "high"
        elif severity >= 0.5:
            risk_level = "moderate"
        else:
            risk_level = "low"

        # ── 5. Confidence ──

        if impressions < 100:
            confidence = 0.5
        elif impressions < 500:
            confidence = 0.7
        else:
            confidence = 0.85

        result = {
            "ctr_percent": ctr_percent,
            "channel_avg_ctr": channel_avg_ctr,
            "ctr_severity": round(severity, 2),
            "risk_level": risk_level,
            "distribution_blocked": distribution_blocked,
            "relative_underperformance": relative_underperformance,
            "confidence": confidence,
        }

        logger.info(
            f"[CTRDiagnosis] severity={result['ctr_severity']}, "
            f"risk={result['risk_level']}, blocked={result['distribution_blocked']}, "
            f"underperform={result['relative_underperformance']}"
        )

        return result

    # ── Validation ──

    def _validate_inputs(
        self,
        ctr_percent: float,
        channel_avg_ctr: float,
        impressions: int,
    ):
        if ctr_percent < 0:
            raise ValueError("ctr_percent cannot be negative")

        if channel_avg_ctr < 0:
            raise ValueError("channel_avg_ctr cannot be negative")

        if impressions < 0:
            raise ValueError("impressions cannot be negative")
