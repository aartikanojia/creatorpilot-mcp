"""
Video Orchestrator — Video-scope intelligence aggregation.

Runs video-level diagnostic engines and produces unified state.
Strictly video-scope. Never merges with channel-scope aggregates.

No strategy. No LLM. No narrative.
"""

import logging

logger = logging.getLogger(__name__)


class VideoOrchestrator:
    """
    Video-scope orchestrator.

    Evaluates a single video's metrics in isolation.
    Never accesses channel aggregates.
    """

    def run(self, analytics_data: dict) -> dict:
        """
        Run video-level diagnosis and return unified state.

        Args:
            analytics_data: Video analytics dict with keys:
                - video_views (int)
                - video_avg_view_percentage (float)
                - video_ctr (float)
                - video_impressions (int)
                - video_subscribers_gained (int)
                - channel_avg_view_percentage (float, for relative comparison only)
                - channel_avg_ctr (float, for relative comparison only)

        Returns:
            Video intelligence state dict.
        """
        video_views = analytics_data.get("video_views", 0)
        video_retention = analytics_data.get("video_avg_view_percentage", 0)
        video_ctr = analytics_data.get("video_ctr", 0)
        video_impressions = analytics_data.get("video_impressions", 0)
        video_subs = analytics_data.get("video_subscribers_gained", 0)

        # ── Video Retention Severity ──
        if video_retention >= 55:
            retention_severity = 0.05
        elif video_retention >= 45:
            retention_severity = 0.25
        elif video_retention >= 35:
            retention_severity = 0.50
        elif video_retention >= 30:
            retention_severity = 0.65
        elif video_retention >= 25:
            retention_severity = 0.80
        elif video_retention >= 20:
            retention_severity = 0.90
        else:
            retention_severity = 0.95

        # ── Video CTR Severity ──
        if video_ctr >= 8:
            ctr_severity = 0.1
        elif video_ctr >= 5:
            ctr_severity = 0.35
        elif video_ctr >= 3:
            ctr_severity = 0.65
        elif video_ctr >= 2:
            ctr_severity = 0.80
        else:
            ctr_severity = 0.90

        # ── Video Conversion Severity ──
        if video_views > 0:
            conv_rate = (video_subs / video_views) * 100
        else:
            conv_rate = 0

        if conv_rate >= 1.5:
            conv_severity = 0.1
        elif conv_rate >= 1.0:
            conv_severity = 0.3
        elif conv_rate >= 0.5:
            conv_severity = 0.6
        elif conv_rate >= 0.1:
            conv_severity = 0.8
        else:
            conv_severity = 0.95

        # ── Primary Constraint ──
        severity_map = {
            "retention": retention_severity,
            "ctr": ctr_severity,
            "conversion": conv_severity,
        }

        primary_constraint = max(severity_map, key=severity_map.get)
        primary_severity = severity_map[primary_constraint]

        # ── Risk Level ──
        if primary_severity >= 0.85:
            risk_level = "critical"
        elif primary_severity >= 0.7:
            risk_level = "high"
        elif primary_severity >= 0.5:
            risk_level = "moderate"
        else:
            risk_level = "low"

        # ── Confidence ──
        if video_impressions < 100:
            confidence = 0.5
        elif video_impressions < 500:
            confidence = 0.7
        else:
            confidence = 0.85

        # ── Ranked ──
        ranked_constraints = sorted(
            severity_map.items(),
            key=lambda x: x[1],
            reverse=True,
        )

        result = {
            "primary_constraint": primary_constraint,
            "primary_severity": round(primary_severity, 2),
            "risk_level": risk_level,
            "ranked_constraints": ranked_constraints,
            "engine_severities": severity_map,
            "confidence": round(confidence, 2),
            "scope": "video",
        }

        logger.info(
            f"[VideoOrchestrator] primary={result['primary_constraint']}, "
            f"severity={result['primary_severity']}, scope=video"
        )

        return result
