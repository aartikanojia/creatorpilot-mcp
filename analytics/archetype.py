"""
Phase 1.4 — Channel Archetype Classification Engine

Deterministic, signal-driven classification layer.

This module derives structural channel identity using:
- Pattern Engine outputs (Phase 1.3)
- Diagnostics outputs (Phase 1.1)
- Channel-level metrics

No LLM logic.
No hardcoded channel assumptions.
Fully reusable across any connected YouTube channel.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional


# ============================================================
# Data Model
# ============================================================

@dataclass
class ChannelArchetype:
    format_type: str
    theme_type: str
    growth_constraint: str
    performance_type: str


# ============================================================
# Archetype Analyzer
# ============================================================

class ArchetypeAnalyzer:

    # --------------------------------------------------------
    # Public Entry Point
    # --------------------------------------------------------

    def classify(
        self,
        pattern_data: Dict,
        diagnostics_data: Dict,
        channel_metrics: Dict
    ) -> ChannelArchetype:
        """
        Classify a channel into structural archetypes.

        Args:
            pattern_data: Output from Phase 1.3 Pattern Intelligence
            diagnostics_data: Output from Phase 1.1 Diagnostics
            channel_metrics: Channel-level metrics (retention, subs, etc.)

        Returns:
            ChannelArchetype object
        """

        format_type = self._classify_format(pattern_data)
        theme_type = self._classify_theme(pattern_data)
        growth_constraint = self._classify_growth(diagnostics_data, channel_metrics)
        performance_type = self._classify_performance(diagnostics_data)

        return ChannelArchetype(
            format_type=format_type,
            theme_type=theme_type,
            growth_constraint=growth_constraint,
            performance_type=performance_type,
        )

    # --------------------------------------------------------
    # Format Classification
    # --------------------------------------------------------

    def _classify_format(self, pattern_data: Dict) -> str:
        """
        Determine format dominance using median comparison.
        """

        shorts = pattern_data.get("shorts_median")
        standard = pattern_data.get("standard_median")

        if not shorts or not standard:
            return "Insufficient Data"

        if standard == 0:
            return "Insufficient Data"

        ratio = shorts / standard

        if ratio >= 1.5:
            return "Shorts-Dominant"
        elif ratio <= 0.67:
            return "Long-Form Dominant"
        else:
            return "Format Balanced"

    # --------------------------------------------------------
    # Theme Concentration Classification
    # --------------------------------------------------------

    def _classify_theme(self, pattern_data: Dict) -> str:
        """
        Detect whether channel is concentrated around a dominant theme.
        """

        top = pattern_data.get("top_median")
        second = pattern_data.get("second_median")

        if not top or not second:
            return "Insufficient Data"

        if second == 0:
            return "Theme-Concentrated"

        if top >= second * 2:
            return "Theme-Concentrated"
        else:
            return "Multi-Theme"

    # --------------------------------------------------------
    # Growth Constraint Classification
    # --------------------------------------------------------

    def _classify_growth(
        self,
        diagnostics_data: Dict,
        channel_metrics: Dict
    ) -> str:
        """
        Identify primary growth bottleneck.
        """

        retention = channel_metrics.get("avg_view_pct")
        sub_conversion = channel_metrics.get("sub_conversion_rate")
        momentum = diagnostics_data.get("momentum_status")

        # Explicit numeric validation
        if isinstance(retention, (int, float)):
            if retention < 45:
                return "Retention-Constrained"

        if isinstance(sub_conversion, (int, float)):
            if sub_conversion < 0.05:
                return "Conversion-Constrained"

        if momentum == "Declining":
            return "Momentum-Declining"

        return "Healthy-Growth"

    # --------------------------------------------------------
    # Performance Distribution Classification
    # --------------------------------------------------------

    def _classify_performance(self, diagnostics_data: Dict) -> str:
        """
        Evaluate library-wide performance distribution.
        """

        percentiles: Optional[List[float]] = diagnostics_data.get(
            "percentile_distribution", []
        )

        if not percentiles:
            return "Insufficient Data"

        if len(percentiles) == 0:
            return "Insufficient Data"

        low_count = len([p for p in percentiles if p < 40])

        if low_count / len(percentiles) > 0.7:
            return "Underperforming Library"

        return "Stable Library"