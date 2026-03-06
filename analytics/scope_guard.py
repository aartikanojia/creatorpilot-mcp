"""
ScopeGuardLayer v1 — Deterministic Scope Firewall.

Enforces strict separation between:
- Video-level diagnostics
- Channel-level diagnostics
- Strategy ranking

Rules:
1. Scope must be determined before engine execution.
2. Video scope must NEVER access channel aggregates.
3. Channel scope must NEVER access video-specific metrics.
4. If required metrics are missing, return structured error.
5. LLM must only receive sanitized structured outputs.
6. No engine mixing allowed.
7. No fallback to generic insight if scope mismatch occurs.
"""

import logging

logger = logging.getLogger(__name__)


class ScopeGuardLayer:
    """
    ScopeGuardLayer v1

    Enforces strict separation between:
    - video diagnostics
    - channel diagnostics
    - strategy ranking

    This is a firewall. Not a router.
    """

    VIDEO_REQUIRED_FIELDS = [
        "video_avg_view_percentage",
        "video_watch_time_minutes",
        "video_length_minutes",
        "video_ctr",
        "impressions",
        "format_type",
    ]

    CHANNEL_REQUIRED_FIELDS = [
        "avg_view_percentage",
        "avg_watch_time_minutes",
        "avg_video_length_minutes",
        "shorts_ratio",
        "long_form_ratio",
    ]

    VIDEO_SANITIZE_KEYS = frozenset([
        "scope",
        "primary_constraint",
        "severity_score",
        "risk_vector",
        "format_type",
        "confidence",
    ])

    CHANNEL_SANITIZE_KEYS = frozenset([
        "constraint",
        "severity_score",
        "risk_level",
        "amplifiers",
        "confidence",
    ])

    # ─── Scope Detection ───

    def determine_scope(self, intent: str) -> str:
        """
        Determine execution scope from intent classifier output.

        Returns: "video" | "channel" | "strategy" | "general" | "unknown"
        """
        if intent in ("video_analysis", "analyze_last_video", "analyze_this_video"):
            scope = "video"
        elif intent in ("insight", "analytics", "structural_analysis"):
            scope = "channel"
        elif intent in ("strategy_ranking",):
            scope = "strategy"
        elif intent in ("general",):
            scope = "general"
        else:
            scope = "unknown"

        logger.info(f"[ScopeGuard] intent={intent} → scope={scope}")
        return scope

    # ─── Validation ───

    def validate_scope_inputs(self, scope: str, data: dict) -> dict:
        """
        Validate that required fields for the given scope are present in data.

        Returns:
            {"status": "ok"} if valid.
            {"error": "...", "confidence": float} if invalid.
        """
        if scope == "video":
            return self._validate_required_fields(data, self.VIDEO_REQUIRED_FIELDS)

        if scope == "channel":
            return self._validate_required_fields(data, self.CHANNEL_REQUIRED_FIELDS)

        if scope == "strategy":
            if "primary_constraint" not in data:
                return self._error("Missing constraint for strategy ranking")
            return {"status": "ok"}

        if scope == "general":
            # General scope: pure LLM, no engine validation needed
            return {"status": "ok"}

        return self._error("Ambiguous scope")

    # ─── Sanitization ───

    def sanitize_for_llm(self, scope: str, diagnosis_output: dict) -> dict:
        """
        Strip any unrelated data before passing to LLM.
        Only whitelisted keys pass through.
        """
        if scope == "video":
            allowed = self.VIDEO_SANITIZE_KEYS
        elif scope == "channel":
            allowed = self.CHANNEL_SANITIZE_KEYS
        else:
            return diagnosis_output

        sanitized = {k: v for k, v in diagnosis_output.items() if k in allowed}

        logger.info(
            f"[ScopeGuard] Sanitized {scope} output: "
            f"kept {len(sanitized)}/{len(diagnosis_output)} keys"
        )
        return sanitized

    # ─── Single Entry Point ───

    def enforce(self, intent: str, data: dict) -> dict:
        """
        Full enforcement pipeline:
        1. Determine scope
        2. Validate inputs
        3. Return scope or error

        Returns:
            {"status": "ok", "scope": "video"|"channel"|"strategy"|"general"}
            or
            {"error": "...", "confidence": float}
        """
        scope = self.determine_scope(intent)

        if scope == "unknown":
            logger.warning(
                f"[ScopeGuard] Blocked: ambiguous scope for intent={intent}"
            )
            return self._error("Ambiguous scope")

        validation = self.validate_scope_inputs(scope, data)

        if validation.get("status") != "ok":
            logger.warning(
                f"[ScopeGuard] Blocked: validation failed for "
                f"scope={scope}, error={validation.get('error')}"
            )
            return validation

        logger.info(f"[ScopeGuard] Passed: scope={scope}, intent={intent}")
        return {"status": "ok", "scope": scope}

    # ─── Internal ───

    def _validate_required_fields(self, data: dict, required_fields: list) -> dict:
        missing = [f for f in required_fields if f not in data]
        if missing:
            return {
                "error": f"Missing required fields: {missing}",
                "confidence": 0.2,
            }
        return {"status": "ok"}

    def _error(self, message: str) -> dict:
        return {
            "error": message,
            "confidence": 0.3,
        }
