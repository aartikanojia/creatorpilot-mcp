"""
ThumbnailScoringModule v1 — Deterministic Packaging Diagnosis.

Scores thumbnail/title packaging effectiveness from CTR data.

Input: impressions, views, ctr
Output: packaging_score, packaging_quality, risk_level, severity, confidence

No LLM. No strategy. No narrative.
"""

import logging

logger = logging.getLogger(__name__)


class ThumbnailScoringModule:
    """
    Deterministic thumbnail/title packaging scorer.

    Uses CTR to determine packaging effectiveness.
    No LLM. No narrative. No recommendations.
    """

    def score(
        self,
        impressions: int,
        views: int,
        ctr: float,
    ) -> dict:
        """
        Score packaging effectiveness from CTR data.

        Args:
            impressions: Total impressions.
            views: Total views.
            ctr: Click-through rate (percent, 0-100).

        Returns:
            Deterministic packaging diagnosis dict.
        """
        self._validate_inputs(impressions, views, ctr)

        # ── 1. Packaging Score (0-1, higher = better) ──
        if ctr >= 10:
            packaging_score = 1.0
        elif ctr >= 8:
            packaging_score = 0.9
        elif ctr >= 6:
            packaging_score = 0.8
        elif ctr >= 5:
            packaging_score = 0.7
        elif ctr >= 4:
            packaging_score = 0.55
        elif ctr >= 3:
            packaging_score = 0.4
        elif ctr >= 2:
            packaging_score = 0.25
        elif ctr >= 1:
            packaging_score = 0.15
        else:
            packaging_score = 0.05

        # ── 2. Packaging Quality ──
        if ctr > 6:
            packaging_quality = "strong"
        elif ctr >= 3:
            packaging_quality = "average"
        else:
            packaging_quality = "weak"

        # ── 3. Severity (0-1, higher = worse — inverse of score) ──
        severity = round(1.0 - packaging_score, 2)

        # ── 4. Risk Level ──
        if ctr < 3:
            risk_level = "critical"
        elif ctr <= 6:
            risk_level = "moderate"
        else:
            risk_level = "low"

        # ── 5. Confidence ──
        if impressions < 100:
            confidence = 0.5
        elif impressions < 500:
            confidence = 0.65
        elif impressions < 1000:
            confidence = 0.75
        else:
            confidence = 0.85

        result = {
            "packaging_score": round(packaging_score, 2),
            "packaging_quality": packaging_quality,
            "severity": severity,
            "risk_level": risk_level,
            "confidence": confidence,
        }

        logger.info(
            f"[ThumbnailScoring] score={result['packaging_score']}, "
            f"quality={result['packaging_quality']}, "
            f"risk={result['risk_level']}, sev={result['severity']}"
        )

        return result

    def _validate_inputs(self, impressions: int, views: int, ctr: float):
        if not isinstance(impressions, (int, float)):
            raise ValueError(f"impressions must be numeric, got {type(impressions).__name__}")
        if not isinstance(views, (int, float)):
            raise ValueError(f"views must be numeric, got {type(views).__name__}")
        if not isinstance(ctr, (int, float)):
            raise ValueError(f"ctr must be numeric, got {type(ctr).__name__}")
        if impressions < 0:
            raise ValueError("impressions cannot be negative")
        if views < 0:
            raise ValueError("views cannot be negative")
        if ctr < 0:
            raise ValueError("ctr cannot be negative")
