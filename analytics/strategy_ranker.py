"""
Strategy Ranking Engine — Deterministic Python Module.

Completely removes ranking logic from prompt space.
LLM only formats pre-computed output.
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


# -------------------------
# Data Models
# -------------------------

@dataclass
class ChannelMetrics:
    retention: Optional[float] = None              # %
    ctr: Optional[float] = None                    # %
    conversion: Optional[float] = None             # %
    shorts_ratio: Optional[float] = None           # %
    theme_concentration: Optional[float] = None    # %


@dataclass
class StrategyResult:
    primary_constraint: str
    severity_score: float
    ranked_strategies: List[Tuple[str, str]]  # (strategy_name, lift_range)
    confidence: float


# -------------------------
# Strategy Ranking Engine
# -------------------------

class StrategyRankingEngine:

    def __init__(self) -> None:
        pass

    # -------------------------
    # Public Entry Point
    # -------------------------

    def rank(self, metrics: ChannelMetrics) -> StrategyResult:

        if not self._has_minimum_data(metrics):
            raise ValueError("Insufficient structured data for strategy ranking.")

        severity_map = self._calculate_severity(metrics)
        primary_constraint = max(severity_map, key=severity_map.get)
        severity_score = round(severity_map[primary_constraint], 2)

        ranked_strategies = self._map_strategies(primary_constraint)
        lift_range = self._estimate_lift(primary_constraint, metrics)

        # Attach lift to each strategy
        ranked_with_lift = [(s, lift_range) for s in ranked_strategies]

        confidence = self._calculate_confidence(metrics)

        logger.info(
            f"[StrategyRanker] Primary={primary_constraint}, "
            f"Severity={severity_score}, Confidence={confidence}, "
            f"Strategies={ranked_strategies}"
        )

        return StrategyResult(
            primary_constraint=primary_constraint,
            severity_score=severity_score,
            ranked_strategies=ranked_with_lift,
            confidence=confidence
        )

    # -------------------------
    # Validation
    # -------------------------

    def _has_minimum_data(self, metrics: ChannelMetrics) -> bool:
        return any([
            metrics.retention is not None,
            metrics.ctr is not None,
            metrics.conversion is not None,
            metrics.shorts_ratio is not None,
            metrics.theme_concentration is not None
        ])

    # -------------------------
    # Severity Calculation
    # -------------------------

    def _calculate_severity(self, m: ChannelMetrics) -> Dict[str, float]:
        severity = {}

        # Retention
        if m.retention is not None:
            severity["Retention"] = max(0, min(10, (40 - m.retention) / 4))

        # CTR
        if m.ctr is not None:
            severity["CTR"] = max(0, min(10, (5 - m.ctr) * 2))

        # Conversion
        if m.conversion is not None:
            severity["Conversion"] = max(0, min(10, (0.5 - m.conversion) * 15))

        # Format Risk
        if m.shorts_ratio is not None:
            severity["Format Risk"] = max(0, min(10, (m.shorts_ratio - 75) / 2))

        # Theme Risk
        if m.theme_concentration is not None:
            severity["Theme Risk"] = max(0, min(10, (m.theme_concentration - 60) / 4))

        return severity

    # -------------------------
    # Strategy Mapping
    # -------------------------

    def _map_strategies(self, constraint: str) -> List[str]:

        mapping = {
            "Retention": [
                "Hook Optimization",
                "Pacing Compression",
                "Series Structuring",
                "Pattern Replication"
            ],
            "Conversion": [
                "CTA Optimization",
                "Value Framing",
                "Subscriber Loop Creation",
                "Community Hooks"
            ],
            "CTR": [
                "Title Optimization",
                "Thumbnail Rework",
                "Curiosity Gap Engineering",
                "Packaging Alignment"
            ],
            "Format Risk": [
                "Format Diversification",
                "Long-Form Expansion",
                "Cross-Format Funnel",
                "Upload Distribution Balance"
            ],
            "Theme Risk": [
                "Theme Expansion",
                "Adjacent Topic Testing",
                "Controlled Diversification",
                "Content Radar Buildout"
            ]
        }

        return mapping.get(constraint, [])[:4]

    # -------------------------
    # Lift Estimation
    # -------------------------

    def _estimate_lift(self, constraint: str, m: ChannelMetrics) -> str:

        if constraint == "Retention":
            if m.retention is not None and m.retention < 30:
                return "10–20%"
            return "5–12%"

        if constraint == "Conversion":
            return "3–8%"

        if constraint == "CTR":
            return "6–15%"

        if constraint == "Format Risk":
            return "4–10%"

        if constraint == "Theme Risk":
            return "5–12%"

        return "3–8%"

    # -------------------------
    # Confidence Model
    # -------------------------

    def _calculate_confidence(self, m: ChannelMetrics) -> float:
        confidence = 1.0

        missing_count = sum([
            m.retention is None,
            m.ctr is None,
            m.conversion is None,
            m.shorts_ratio is None,
            m.theme_concentration is None
        ])

        confidence -= 0.1 * missing_count

        return round(max(0.5, confidence), 2)

    # -------------------------
    # Render for LLM (minimal)
    # -------------------------

    def render(self, result: StrategyResult) -> str:
        """Render pre-computed result for LLM formatting. No commentary."""
        lines = [
            f"Primary Constraint: {result.primary_constraint}",
            f"Severity Score: {result.severity_score}",
            "",
            "Strategies:",
        ]
        for i, (name, lift) in enumerate(result.ranked_strategies, 1):
            lines.append(f"{i}. {name} — Estimated Lift: {lift}")
        lines.append("")
        lines.append(f"Confidence: {result.confidence}")
        return "\n".join(lines)
