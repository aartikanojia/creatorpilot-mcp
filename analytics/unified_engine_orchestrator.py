"""
Unified Engine Orchestrator v1 — Channel Intelligence Aggregator.

Aggregates outputs from all diagnostic engines into a single
unified channel intelligence state:
- Normalized severities
- Primary constraint selection
- Ranked constraints
- Unified risk level
- Aggregated confidence

Rules:
- Uses only pre-computed engine outputs
- Produces strict JSON-compatible dict
- Never calls LLM
- Never injects strategy
- Never produces narrative text
"""

import logging

from analytics.next_video_blueprint_engine import NextVideoBlueprintEngine

logger = logging.getLogger(__name__)


class UnifiedEngineOrchestrator:
    """
    Unified Engine Orchestrator v1.

    Aggregates:
    - RetentionDiagnosisEngine
    - CTRDiagnosisEngine
    - ConversionRateAnalyzer
    - ShortsImpactAnalyzer
    - GrowthTrendExplanationEngine
    - ThumbnailScoringModule (optional)
    - NextVideoBlueprintEngine

    Produces ONE primary constraint and ONE severity for ALL queries.
    No strategy. No LLM. No narrative.
    """

    def __init__(self):
        self.next_video_engine = NextVideoBlueprintEngine()

    def orchestrate(
        self,
        retention_result: dict,
        ctr_result: dict,
        conversion_result: dict,
        shorts_result: dict,
        growth_result: dict,
        thumbnail_result: dict = None,
    ) -> dict:

        self._validate_inputs(
            retention_result, ctr_result, conversion_result,
            shorts_result, growth_result,
        )

        # ── 1. Collect Severities ──

        severity_map = {
            "retention": retention_result.get("severity", 0),
            "ctr": ctr_result.get("ctr_severity", 0),
            "conversion": conversion_result.get("conversion_severity", 0),
            "shorts": shorts_result.get("severity", 0),
            "growth": growth_result.get("severity", 0),
        }

        # Optional: ThumbnailScoringModule
        if thumbnail_result and isinstance(thumbnail_result, dict):
            severity_map["packaging"] = thumbnail_result.get("severity", 0)

        # ── 2. Primary Constraint ──

        primary_constraint = max(severity_map, key=severity_map.get)
        primary_severity = severity_map[primary_constraint]

        # ── 3. Risk Level ──

        if primary_severity >= 0.85:
            unified_risk = "critical"
        elif primary_severity >= 0.7:
            unified_risk = "high"
        elif primary_severity >= 0.5:
            unified_risk = "moderate"
        else:
            unified_risk = "low"

        # ── 4. Ranked Constraints ──

        ranked_constraints = sorted(
            severity_map.items(),
            key=lambda x: x[1],
            reverse=True,
        )

        # ── 5. Confidence ──

        confidence_values = [
            retention_result.get("confidence", 0),
            ctr_result.get("confidence", 0),
            conversion_result.get("confidence", 0),
            shorts_result.get("confidence", 0),
            growth_result.get("confidence", 0),
        ]
        if thumbnail_result and isinstance(thumbnail_result, dict):
            confidence_values.append(thumbnail_result.get("confidence", 0))

        confidence = sum(confidence_values) / len(confidence_values)

        # ── 6. Next Video Blueprint ──

        next_video_blueprint = self.next_video_engine.generate(primary_constraint)

        result = {
            "primary_constraint": primary_constraint,
            "primary_severity": round(primary_severity, 2),
            "risk_level": unified_risk,
            "ranked_constraints": ranked_constraints,
            "engine_severities": severity_map,
            "confidence": round(confidence, 2),
            "next_video_blueprint": next_video_blueprint,
        }

        logger.info(
            f"[Orchestrator] primary={result['primary_constraint']}, "
            f"severity={result['primary_severity']}, risk={result['risk_level']}, "
            f"confidence={result['confidence']}"
        )

        return result

    # ── Validation ──

    def _validate_inputs(self, *results):
        for i, r in enumerate(results):
            if not isinstance(r, dict):
                raise ValueError(f"Engine result {i} must be a dict, got {type(r).__name__}")
