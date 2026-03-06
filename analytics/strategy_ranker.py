"""
Strategy Ranking Engine — Deterministic Python Module.

Completely removes ranking logic from prompt space.
LLM only formats pre-computed output.

Priority order (STRICT):
1. Critical metric severity (≥ 0.9) — Retention > CTR > Conversion
2. Moderate metric severity (≥ 0.6) — Retention > CTR > Conversion
3. Structural risks — Theme Risk, Format Risk (only if metrics stable)
4. Default — Pattern Scaling

Metrics ALWAYS override structure.
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

        # Compute all severities (0-1 scale)
        severity_map = self._calculate_severity(metrics)

        retention_sev = severity_map.get("Retention", 0)
        ctr_sev = severity_map.get("CTR", 0)
        conversion_sev = severity_map.get("Conversion", 0)
        format_sev = severity_map.get("Format Risk", 0)
        theme_sev = severity_map.get("Theme Risk", 0)

        # ── STRICT PRIORITY ORDER ──
        # Metrics always override structural risks.

        # 1. CRITICAL metrics (≥ 0.9)
        if retention_sev >= 0.9:
            primary_constraint = "Retention"
        elif ctr_sev >= 0.9:
            primary_constraint = "CTR"
        elif conversion_sev >= 0.9:
            primary_constraint = "Conversion"

        # 2. MODERATE metrics (≥ 0.6)
        elif retention_sev >= 0.6:
            primary_constraint = "Retention"
        elif ctr_sev >= 0.6:
            primary_constraint = "CTR"
        elif conversion_sev >= 0.6:
            primary_constraint = "Conversion"

        # 3. MILD metrics (≥ 0.3) — still metrics first
        elif retention_sev >= 0.3:
            primary_constraint = "Retention"
        elif ctr_sev >= 0.3:
            primary_constraint = "CTR"
        elif conversion_sev >= 0.3:
            primary_constraint = "Conversion"

        # 4. STRUCTURAL risks (only if all metrics are stable)
        elif format_sev >= 0.5:
            primary_constraint = "Format Risk"
        elif theme_sev >= 0.5:
            primary_constraint = "Theme Risk"

        # 5. DEFAULT
        else:
            # Pick highest from whatever is available
            if severity_map:
                primary_constraint = max(severity_map, key=severity_map.get)
            else:
                primary_constraint = "Retention"

        severity_score = round(severity_map.get(primary_constraint, 0), 2)

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
    # Severity Calculation (0-1 scale)
    # -------------------------

    def _calculate_severity(self, m: ChannelMetrics) -> Dict[str, float]:
        severity = {}

        # Retention: lower % → higher severity
        if m.retention is not None:
            if m.retention >= 55:
                severity["Retention"] = 0.05
            elif m.retention >= 45:
                severity["Retention"] = 0.25
            elif m.retention >= 35:
                severity["Retention"] = 0.50
            elif m.retention >= 30:
                severity["Retention"] = 0.65
            elif m.retention >= 25:
                severity["Retention"] = 0.80
            elif m.retention >= 20:
                severity["Retention"] = 0.90
            else:
                severity["Retention"] = 0.95

        # CTR: lower % → higher severity
        if m.ctr is not None:
            if m.ctr >= 8:
                severity["CTR"] = 0.10
            elif m.ctr >= 5:
                severity["CTR"] = 0.35
            elif m.ctr >= 3:
                severity["CTR"] = 0.65
            elif m.ctr >= 2:
                severity["CTR"] = 0.80
            else:
                severity["CTR"] = 0.90

        # Conversion: lower % → higher severity
        if m.conversion is not None:
            if m.conversion >= 0.5:
                severity["Conversion"] = 0.05
            elif m.conversion >= 0.3:
                severity["Conversion"] = 0.30
            elif m.conversion >= 0.1:
                severity["Conversion"] = 0.60
            elif m.conversion >= 0.05:
                severity["Conversion"] = 0.75
            else:
                severity["Conversion"] = 0.90

        # Format Risk: higher shorts ratio → higher risk (structural)
        if m.shorts_ratio is not None:
            if m.shorts_ratio >= 90:
                severity["Format Risk"] = 0.80
            elif m.shorts_ratio >= 80:
                severity["Format Risk"] = 0.60
            elif m.shorts_ratio >= 70:
                severity["Format Risk"] = 0.40
            else:
                severity["Format Risk"] = 0.10

        # Theme Risk: higher concentration → higher risk (structural)
        if m.theme_concentration is not None:
            if m.theme_concentration >= 90:
                severity["Theme Risk"] = 0.80
            elif m.theme_concentration >= 80:
                severity["Theme Risk"] = 0.60
            elif m.theme_concentration >= 70:
                severity["Theme Risk"] = 0.40
            else:
                severity["Theme Risk"] = 0.10

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
