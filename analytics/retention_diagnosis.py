"""
Retention Diagnosis Engine — Deterministic Python Module.

This engine:
- Computes retention severity from structured inputs
- Applies structural amplifiers (shorts dependency, watch time penalty)
- Returns strict JSON-compatible dict output

It does NOT:
- Generate advice or strategy suggestions
- Use LLM
- Invent or infer missing data
- Output narrative text
"""

from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class RetentionDiagnosisResult:
    constraint: str
    severity_score: float
    risk_level: str
    amplifiers: dict
    confidence: float


class RetentionDiagnosisEngine:
    """
    Deterministic Retention Diagnosis Engine v1

    This engine:
    - Computes retention severity
    - Applies structural amplifiers
    - Returns structured JSON-safe output

    It does NOT:
    - Generate advice
    - Use LLM
    - Invent data
    """

    def diagnose(
        self,
        avg_view_percentage: float,
        avg_watch_time_minutes: float,
        avg_video_length_minutes: float,
        shorts_ratio: float,
        long_form_ratio: float,
    ) -> dict:

        self._validate_inputs(
            avg_view_percentage,
            avg_watch_time_minutes,
            avg_video_length_minutes,
            shorts_ratio,
            long_form_ratio,
        )

        base_severity = self._base_retention_severity(avg_view_percentage)
        shorts_multiplier = self._shorts_dependency_multiplier(shorts_ratio)

        watch_time_ratio = 0.0
        watch_time_penalty = 0.0

        if avg_video_length_minutes > 0:
            watch_time_ratio = avg_watch_time_minutes / avg_video_length_minutes

            if watch_time_ratio < 0.15:
                watch_time_penalty = 0.10
            elif watch_time_ratio < 0.20:
                watch_time_penalty = 0.05

        severity = base_severity * shorts_multiplier + watch_time_penalty
        severity = min(severity, 1.0)

        result = RetentionDiagnosisResult(
            constraint="retention",
            severity_score=round(severity, 2),
            risk_level=self._classify_retention_risk(severity),
            amplifiers={
                "shorts_ratio": round(shorts_ratio, 2),
                "watch_time_ratio": round(watch_time_ratio, 2),
            },
            confidence=0.85,
        )

        logger.info(
            f"[RetentionDiagnosis] severity={result.severity_score}, "
            f"risk={result.risk_level}, confidence={result.confidence}"
        )

        return result.__dict__

    # -----------------------------
    # INTERNAL METHODS
    # -----------------------------

    def _base_retention_severity(self, avg_view_percentage: float) -> float:
        if avg_view_percentage >= 55:
            return 0.05
        elif avg_view_percentage >= 45:
            return 0.25
        elif avg_view_percentage >= 35:
            return 0.50
        elif avg_view_percentage >= 30:
            return 0.65
        elif avg_view_percentage >= 25:
            return 0.80
        else:
            return 0.95

    def _shorts_dependency_multiplier(self, shorts_ratio: float) -> float:
        if shorts_ratio >= 0.85:
            return 1.15
        elif shorts_ratio >= 0.75:
            return 1.10
        elif shorts_ratio >= 0.60:
            return 1.05
        return 1.0

    def _classify_retention_risk(self, severity: float) -> str:
        if severity >= 0.85:
            return "critical"
        elif severity >= 0.70:
            return "severe"
        elif severity >= 0.50:
            return "moderate"
        elif severity >= 0.30:
            return "mild"
        return "healthy"

    def _validate_inputs(
        self,
        avg_view_percentage: float,
        avg_watch_time_minutes: float,
        avg_video_length_minutes: float,
        shorts_ratio: float,
        long_form_ratio: float,
    ):
        if not 0 <= avg_view_percentage <= 100:
            raise ValueError("avg_view_percentage must be between 0 and 100")

        if avg_watch_time_minutes < 0:
            raise ValueError("avg_watch_time_minutes cannot be negative")

        if avg_video_length_minutes < 0:
            raise ValueError("avg_video_length_minutes cannot be negative")

        if not 0 <= shorts_ratio <= 1:
            raise ValueError("shorts_ratio must be between 0 and 1")

        if not 0 <= long_form_ratio <= 1:
            raise ValueError("long_form_ratio must be between 0 and 1")
