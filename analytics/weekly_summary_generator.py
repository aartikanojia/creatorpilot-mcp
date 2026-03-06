"""
Deterministic Weekly Summary Generator v1.

Generates fully deterministic weekly channel intelligence
using ChannelOrchestrator and StrategyRankingEngine.

No GPT. No narrative. No formatting. No narration.
"""

import logging
from analytics.channel_orchestrator import ChannelOrchestrator
from analytics.strategy_ranker import StrategyRankingEngine, ChannelMetrics

logger = logging.getLogger(__name__)


class WeeklySummaryGenerator:
    """
    Deterministic Weekly Summary Generator.

    Produces structured intelligence state from:
    - ChannelOrchestrator (5 diagnostic engines)
    - StrategyRankingEngine (metric-first priority)

    No LLM. No narrative. No formatting.
    """

    def __init__(self):
        self.channel_orchestrator = ChannelOrchestrator()
        self.strategy_engine = StrategyRankingEngine()

    def generate(self, analytics_data: dict) -> dict:
        """
        Generate deterministic weekly summary.

        Args:
            analytics_data: Channel analytics dict.

        Returns:
            Structured weekly intelligence state. No narrative.
        """
        # ── 1. Run ChannelOrchestrator ──
        unified_state = self.channel_orchestrator.run(analytics_data)

        # ── 2. Build ChannelMetrics for StrategyRankingEngine ──
        channel_metrics = ChannelMetrics(
            retention=analytics_data.get("avg_view_percentage"),
            ctr=analytics_data.get("ctr_percent"),
            conversion=self._compute_conversion(analytics_data),
            shorts_ratio=analytics_data.get("shorts_ratio"),
            theme_concentration=analytics_data.get("theme_concentration"),
        )

        try:
            strategy_result = self.strategy_engine.rank(channel_metrics)
            strategies = [
                {"name": name, "estimated_lift": lift}
                for name, lift in strategy_result.ranked_strategies
            ]
        except (ValueError, Exception) as e:
            logger.warning(f"[WeeklySummary] Strategy ranking failed: {e}")
            strategies = []

        # ── 3. Build deterministic output ──
        result = {
            "primary_constraint": unified_state["primary_constraint"],
            "primary_severity": unified_state["primary_severity"],
            "risk_level": unified_state["risk_level"],
            "ranked_constraints": unified_state["ranked_constraints"],
            "engine_severities": unified_state["engine_severities"],
            "ranked_strategies": strategies,
            "confidence": unified_state["confidence"],
            "scope": "channel",
            "report_type": "weekly_summary",
        }

        logger.info(
            f"[WeeklySummary] primary={result['primary_constraint']}, "
            f"severity={result['primary_severity']}, "
            f"risk={result['risk_level']}"
        )

        return result

    def _compute_conversion(self, data: dict) -> float:
        """Compute conversion rate from views and subs."""
        views = data.get("views", 0)
        subs = data.get("subscribers_gained", 0)
        if views > 0:
            return (subs / views) * 100
        return 0.0
