"""
Video Diagnosis Engine — Deterministic Python Module.

Diagnoses ONE specific video only.
Does NOT use channel-level averages.
Does NOT use LLM.
Does NOT invent missing data.
Does NOT suggest strategies.
Returns strict JSON-compatible dict output.
"""

from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class VideoDiagnosisResult:
    scope: str
    primary_constraint: str
    severity_score: float
    risk_vector: list
    format_type: str
    confidence: float


class VideoDiagnosisEngine:
    """
    Deterministic Video-Level Diagnosis Engine v1

    Diagnoses:
    - Retention weakness
    - CTR weakness
    - Distribution weakness

    No strategy logic.
    No LLM.
    """

    def diagnose(
        self,
        video_avg_view_percentage: float,
        video_watch_time_minutes: float,
        video_length_minutes: float,
        video_ctr: float,
        impressions: int,
        format_type: str,
    ) -> dict:

        self._validate_inputs(
            video_avg_view_percentage,
            video_watch_time_minutes,
            video_length_minutes,
            video_ctr,
            impressions,
            format_type,
        )

        retention_severity = self._retention_severity(video_avg_view_percentage)
        ctr_severity = self._ctr_severity(video_ctr)
        distribution_severity = self._distribution_severity(impressions)

        severities = {
            "retention": retention_severity,
            "ctr": ctr_severity,
            "distribution": distribution_severity,
        }

        primary_constraint = max(severities, key=severities.get)
        highest_severity = severities[primary_constraint]

        risk_vector = [
            k for k, v in severities.items() if v >= 0.6
        ]

        result = VideoDiagnosisResult(
            scope="video",
            primary_constraint=primary_constraint
            if highest_severity >= 0.4
            else "healthy",
            severity_score=round(highest_severity, 2),
            risk_vector=risk_vector,
            format_type=format_type,
            confidence=0.85,
        )

        logger.info(
            f"[VideoDiagnosis] constraint={result.primary_constraint}, "
            f"severity={result.severity_score}, risk_vector={result.risk_vector}, "
            f"format={result.format_type}"
        )

        return result.__dict__

    # -------------------------
    # INTERNAL METHODS
    # -------------------------

    def _retention_severity(self, avg_view_percentage: float) -> float:
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

    def _ctr_severity(self, ctr: float) -> float:
        if ctr >= 8:
            return 0.10
        elif ctr >= 5:
            return 0.35
        elif ctr >= 3:
            return 0.65
        else:
            return 0.90

    def _distribution_severity(self, impressions: int) -> float:
        if impressions >= 10000:
            return 0.10
        elif impressions >= 3000:
            return 0.40
        elif impressions >= 1000:
            return 0.65
        else:
            return 0.85

    def _validate_inputs(
        self,
        video_avg_view_percentage: float,
        video_watch_time_minutes: float,
        video_length_minutes: float,
        video_ctr: float,
        impressions: int,
        format_type: str,
    ):
        if not 0 <= video_avg_view_percentage <= 100:
            raise ValueError("video_avg_view_percentage must be between 0 and 100")

        if video_watch_time_minutes < 0:
            raise ValueError("video_watch_time_minutes cannot be negative")

        if video_length_minutes <= 0:
            raise ValueError("video_length_minutes must be greater than 0")

        if video_ctr < 0:
            raise ValueError("video_ctr cannot be negative")

        if impressions < 0:
            raise ValueError("impressions cannot be negative")

        if format_type not in ["short", "long"]:
            raise ValueError("format_type must be 'short' or 'long'")
