"""
Channel Orchestrator — Channel-scope intelligence aggregation.

Runs all channel-level diagnostic engines and produces unified state.
Strictly channel-scope. Never merges with video-scope data.

No strategy. No LLM. No narrative.
"""

import logging
from analytics.retention_diagnosis import RetentionDiagnosisEngine
from analytics.ctr_diagnosis import CTRDiagnosisEngine
from analytics.conversion_rate_analyzer import ConversionRateAnalyzer
from analytics.shorts_impact_analyzer import ShortsImpactAnalyzer
from analytics.growth_trend_engine import GrowthTrendExplanationEngine
from analytics.unified_engine_orchestrator import UnifiedEngineOrchestrator

logger = logging.getLogger(__name__)


class ChannelOrchestrator:
    """
    Channel-scope orchestrator.

    Runs: Retention, CTR, Conversion, Shorts, Growth engines.
    Produces: Unified channel intelligence state.

    Never touches video-scope data.
    """

    def __init__(self):
        self.retention_engine = RetentionDiagnosisEngine()
        self.ctr_engine = CTRDiagnosisEngine()
        self.conversion_engine = ConversionRateAnalyzer()
        self.shorts_engine = ShortsImpactAnalyzer()
        self.growth_engine = GrowthTrendExplanationEngine()
        self.orchestrator = UnifiedEngineOrchestrator()

    def run(self, analytics_data: dict) -> dict:
        """
        Run all channel-level engines and return unified state.

        Args:
            analytics_data: Channel analytics dict with keys:
                - avg_view_percentage (float)
                - avg_watch_minutes (float)
                - avg_video_length_minutes (float)
                - shorts_ratio (float, 0-1)
                - ctr_percent (float)
                - channel_avg_ctr (float)
                - impressions (int)
                - views (int)
                - subscribers_gained (int)
                - channel_avg_conversion_rate (float)
                - total_views (int)
                - shorts_views (int)
                - long_views (int)
                - shorts_avg_retention (float)
                - long_avg_retention (float)
                - current_period_views (int)
                - previous_period_views (int)
                - current_period_subs (int)
                - previous_period_subs (int)

        Returns:
            Unified intelligence state dict.
        """
        # ── Retention ──
        retention_result = {"severity": 0, "confidence": 0.5}
        try:
            avg_view_pct = analytics_data.get("avg_view_percentage")
            avg_watch = analytics_data.get("avg_watch_minutes", 0)
            avg_length = analytics_data.get("avg_video_length_minutes", 0)
            shorts_ratio = analytics_data.get("shorts_ratio", 0)

            if avg_view_pct is not None and avg_view_pct > 0:
                ret_raw = self.retention_engine.diagnose(
                    avg_view_percentage=avg_view_pct,
                    avg_watch_time_minutes=avg_watch,
                    avg_video_length_minutes=avg_length,
                    shorts_ratio=shorts_ratio,
                    long_form_ratio=max(0, 1.0 - shorts_ratio),
                )
                # Map severity_score → severity for orchestrator compatibility
                retention_result = {
                    "severity": ret_raw.get("severity_score", 0),
                    "confidence": ret_raw.get("confidence", 0.5),
                }
        except Exception as e:
            logger.warning(f"[ChannelOrchestrator] Retention engine failed: {e}")

        # ── CTR ──
        ctr_result = {"ctr_severity": 0, "confidence": 0.5}
        try:
            ctr_pct = analytics_data.get("ctr_percent")
            ch_avg_ctr = analytics_data.get("channel_avg_ctr", 0)
            impressions = analytics_data.get("impressions", 0)

            if ctr_pct is not None:
                ctr_result = self.ctr_engine.diagnose(
                    ctr_percent=ctr_pct,
                    channel_avg_ctr=ch_avg_ctr,
                    impressions=impressions,
                )
        except Exception as e:
            logger.warning(f"[ChannelOrchestrator] CTR engine failed: {e}")

        # ── Conversion ──
        conversion_result = {"conversion_severity": 0, "confidence": 0.5}
        try:
            views = analytics_data.get("views", 0)
            subs = analytics_data.get("subscribers_gained", 0)
            ch_avg_conv = analytics_data.get("channel_avg_conversion_rate", 0)

            if views > 0:
                conversion_result = self.conversion_engine.diagnose(
                    views=views,
                    subscribers_gained=subs,
                    channel_avg_conversion_rate=ch_avg_conv,
                )
        except Exception as e:
            logger.warning(f"[ChannelOrchestrator] Conversion engine failed: {e}")

        # ── Shorts ──
        shorts_result = {"severity": 0, "confidence": 0.5}
        try:
            total_v = analytics_data.get("total_views", 0)
            shorts_v = analytics_data.get("shorts_views", 0)
            long_v = analytics_data.get("long_views", 0)
            s_ret = analytics_data.get("shorts_avg_retention", 0)
            l_ret = analytics_data.get("long_avg_retention", 0)

            if total_v > 0:
                shorts_result = self.shorts_engine.diagnose(
                    total_views=total_v,
                    shorts_views=shorts_v,
                    long_views=long_v,
                    shorts_avg_retention=s_ret,
                    long_avg_retention=l_ret,
                )
        except Exception as e:
            logger.warning(f"[ChannelOrchestrator] Shorts engine failed: {e}")

        # ── Growth ──
        growth_result = {"severity": 0, "confidence": 0.5}
        try:
            curr_views = analytics_data.get("current_period_views", 0)
            prev_views = analytics_data.get("previous_period_views", 0)
            curr_subs = analytics_data.get("current_period_subs", 0)
            prev_subs = analytics_data.get("previous_period_subs", 0)

            if curr_views > 0 or prev_views > 0:
                growth_result = self.growth_engine.diagnose(
                    current_period_views=curr_views,
                    previous_period_views=prev_views,
                    current_period_subs=curr_subs,
                    previous_period_subs=prev_subs,
                )
        except Exception as e:
            logger.warning(f"[ChannelOrchestrator] Growth engine failed: {e}")

        # ── Orchestrate ──
        unified = self.orchestrator.orchestrate(
            retention_result=retention_result,
            ctr_result=ctr_result,
            conversion_result=conversion_result,
            shorts_result=shorts_result,
            growth_result=growth_result,
        )

        unified["scope"] = "channel"

        logger.info(
            f"[ChannelOrchestrator] primary={unified['primary_constraint']}, "
            f"severity={unified['primary_severity']}, scope=channel"
        )

        return unified
