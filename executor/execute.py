"""
Main orchestration entry point for MCP request execution.

This module coordinates:
- Memory loading (short-term and long-term)
- Tool planning and execution
- LLM invocation
- Response formatting
- Persistence of chat history and insights

All business logic flows through here.
"""

import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional, Tuple
from uuid import UUID

from config import config
from executor.planner import ExecutionPlanner, ExecutionPlan
from executor.formatter import ResponseFormatter
from registry.tools import ToolRegistry, ToolResult
from registry.schemas import ExecuteResponse
from registry.policies import PolicyEngine
from memory.redis_store import RedisMemoryStore
from memory.postgres_store import PostgresMemoryStore
from db.models.analytics_snapshot import AnalyticsSnapshot
from db.models.weekly_insight import WeeklyInsight
from db.models.chat_session import ChatSession
from llm.langchain_gemini import LangChainGeminiClient
from llm.langchain_azure import LangChainAzureClient
from analytics.context_builder import AnalyticsContextBuilder
from analytics.diagnostics import (
    classify_retention,
    compute_channel_median,
    compute_percentile_rank,
    detect_momentum,
    classify_format,
    compute_performance_tier,
)
from analytics.strategy import compute_strategy_framework
from analytics.patterns import (
    cluster_by_keyword,
    detect_top_theme,
    detect_underperforming_theme,
    detect_format_bias,
)
from analytics.archetype import ArchetypeAnalyzer
from analytics.strategy_ranker import StrategyRankingEngine, ChannelMetrics
from analytics.retention_diagnosis import RetentionDiagnosisEngine
from analytics.video_diagnosis import VideoDiagnosisEngine
from analytics.scope_guard import ScopeGuardLayer
from services.video_resolver import resolve_video_by_title, get_top_matches, get_video_count, get_latest_video_from_db

logger = logging.getLogger(__name__)


class ContextOrchestrator:
    """
    Core orchestrator for MCP context requests.

    Coordinates all components to process a user request:
    1. Load relevant context from memory stores
    2. Plan tool execution based on user intent
    3. Execute approved tools
    4. Call LLM with full context
    5. Format and return response
    """

    # Request limits by plan
    FREE_DAILY_LIMIT = 3

    # Identity query patterns — deterministic archetype rendering, no LLM
    IDENTITY_PATTERNS = [
        r"\bwhat type of channel\b",
        r"\bchannel identity\b",
        r"\bdiagnose my channel\b",
        r"\bstructurally\b",
        r"\bwhat kind of channel\b",
        r"\bchannel archetype\b",
    ]

    # Conversational patterns — answer naturally without analytics
    CONVERSATIONAL_NAME_PATTERNS = [
        r"\bwhat(?:'s| is) my name\b",
        r"\bwhat(?:'s| is) my channel name\b",
        r"\bwho am i\b",
        r"\bmy channel name\b",
        r"\bwhat(?:'s| is) my channel called\b",
    ]

    @staticmethod
    def severity_label(score) -> str:
        """Translate numeric severity (0.0–1.0) to a creator-friendly label."""
        try:
            score = float(score)
        except (TypeError, ValueError):
            return str(score)
        if score >= 0.9:
            return "Critical"
        elif score >= 0.7:
            return "High"
        elif score >= 0.5:
            return "Moderate"
        elif score >= 0.3:
            return "Early Warning"
        else:
            return "Stable"

    def __init__(self) -> None:
        """Initialize orchestrator with all required components."""
        self.planner = ExecutionPlanner()
        self.formatter = ResponseFormatter()
        self.tool_registry = ToolRegistry()
        self.policy_engine = PolicyEngine()
        self.redis_store = RedisMemoryStore()
        self.postgres_store = PostgresMemoryStore()
        self.analytics_builder = AnalyticsContextBuilder()

        # Initialize LLM client based on provider config
        if config.llm.provider == "azure_openai":
            self.llm_client = LangChainAzureClient()
            logger.info("LLM provider initialized: azure_openai")
        elif config.llm.provider == "gemini":
            self.llm_client = LangChainGeminiClient()
            logger.info("LLM provider initialized: gemini")
        else:
            raise ValueError(
                f"Unsupported LLM provider: {config.llm.provider}. "
                "Supported: 'azure_openai', 'gemini'"
            )

    async def _check_usage_limit(
        self,
        user_id: str,
        user_plan: str
    ) -> Tuple[bool, int]:
        """
        Check and increment usage count for a user.

        Args:
            user_id: Unique identifier for the user
            user_plan: User's subscription plan (free/pro)

        Returns:
            Tuple of (is_allowed, current_count)
        """
        # PRO users have unlimited access
        if user_plan.lower() == "pro":
            return (True, 0)

        # Build Redis key: usage:{user_id}:{YYYY-MM-DD}
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        usage_key = f"usage:{user_id}:{today}"

        try:
            client = await self.redis_store._ensure_connection()

            # Increment and get the new count
            current_count = await client.incr(usage_key)

            # Set expiry to 24 hours on first increment
            if current_count == 1:
                await client.expire(usage_key, 86400)  # 24 hours

            # Check if limit exceeded
            if current_count > self.FREE_DAILY_LIMIT:
                logger.warning(
                    f"User {user_id} exceeded free daily limit "
                    f"({current_count}/{self.FREE_DAILY_LIMIT})"
                )
                return (False, current_count)

            return (True, current_count)

        except Exception as e:
            # Fail-open: allow request if Redis is unavailable
            logger.error(f"Usage limit check failed (allowing request): {e}")
            return (True, 0)

    async def execute(
        self,
        user_id: str,
        channel_id: str,
        message: str,
        metadata: Optional[dict[str, Any]] = None
    ) -> ExecuteResponse:
        """
        Execute a full context request cycle.

        Args:
            user_id: Unique identifier for the user
            channel_id: Channel/conversation context identifier
            message: User's input message
            metadata: Optional additional context

        Returns:
            ExecuteResponse with result and metadata
        """
        metadata = metadata or {}
        tool_results: list[ToolResult] = []

        # Get user plan early for usage limit check
        user_plan = metadata.get("user_plan", "free")

        # FORCE_PRO_MODE override for testing
        if config.flags.force_pro_mode:
            user_plan = "pro"
            logger.info("FORCE_PRO_MODE enabled — user treated as PRO")

        # Step 0: Check usage limits (BEFORE any tool/LLM execution)
        is_allowed, usage_count = await self._check_usage_limit(user_id, user_plan)
        
        # Prepare usage metadata (None for PRO users)
        if user_plan == "pro":
            usage_metadata = None
        else:
            is_exhausted = not is_allowed or usage_count >= self.FREE_DAILY_LIMIT
            usage_metadata = {
                "used": min(usage_count, self.FREE_DAILY_LIMIT),
                "limit": self.FREE_DAILY_LIMIT,
                "exhausted": is_exhausted
            }
        
        # Store user_plan in metadata so formatter can propagate it
        metadata["user_plan"] = user_plan
        
        if not is_allowed:
            return ExecuteResponse(
                success=False,
                error={
                    "code": "PLAN_LIMIT_REACHED",
                    "message": "You've reached your free analysis limit for today. "
                               "Upgrade to PRO to unlock unlimited insights."
                },
                metadata={
                    "user_plan": user_plan,
                    "usage": usage_metadata
                }
            )

        # Convert string IDs to UUIDs for database operations
        user_uuid = self._safe_parse_uuid(user_id)
        channel_uuid = self._safe_parse_uuid(channel_id)

        # Step 1: Load memory context (short-term + long-term)
        logger.debug(
            f"Loading memory for user={user_id}, channel={channel_id}")
        memory_context = await self._load_memory_context(user_id, channel_id)

        # Step 1b: Load historical context from PostgreSQL
        historical_context = self._load_historical_context(
            channel_uuid, user_uuid)
        memory_context["historical"] = historical_context

        # Step 1c: Inject channel context for tools (OAuth + analytics)
        # Try to load channel by UUID first, then fall back to YouTube channel ID
        channel = None
        try:
            if channel_uuid:
                channel = self.postgres_store.get_channel_by_id(channel_uuid)
            
            # Fallback: If UUID lookup failed, try by YouTube channel ID
            if not channel and channel_id:
                channel = self.postgres_store.get_channel_by_youtube_id(channel_id)
                if channel:
                    # Update channel_uuid for later use in historical context
                    channel_uuid = channel.id
                    logger.debug(f"Channel resolved by YouTube ID: {channel_id} -> {channel_uuid}")
            
            if channel:
                # SECURITY: Verify channel ownership before proceeding
                # Prevents cross-account data leaks
                if user_uuid and channel.user_id != user_uuid:
                    logger.warning(
                        f"Channel ownership mismatch: channel {channel.id} belongs to "
                        f"user {channel.user_id}, but request is from user {user_uuid}"
                    )
                    return ExecuteResponse(
                        success=False,
                        error={
                            "code": "CHANNEL_ACCESS_DENIED",
                            "message": "You do not have access to this channel. "
                                       "Please connect your own YouTube channel."
                        }
                    )
                
                memory_context["channel"] = {
                    "id": str(channel.id),
                    "user_id": str(channel.user_id),
                    "youtube_channel_id": channel.youtube_channel_id,
                    "channel_name": channel.channel_name,
                    "access_token": channel.access_token,
                    "refresh_token": channel.refresh_token,
                }
                logger.info(f"Channel context injected for {channel.channel_name}")
            else:
                logger.warning(f"No channel found for channel_id={channel_id}")
        except Exception as e:
            logger.error(f"Failed to load channel context: {e}")

        # Step 2: Plan tool execution (with historical context)
        logger.debug("Planning tool execution")
        plan = self.planner.create_plan(
            message=message,
            memory_context=memory_context,
            available_tools=self.tool_registry.list_tools()
        )

        # ──────────────────────────────────────────────
        # PLANNER LOCK — Video Keyword Override
        # Force video_analysis intent if message contains video keywords.
        # Prevents planner misclassification → neutralizes scope leakage.
        # ──────────────────────────────────────────────
        _VIDEO_KEYWORDS = [
            "last video", "my video", "analyze video", "analyze my",
            "how did", "this upload", "last upload",
            "latest video", "recent video", "my last",
        ]
        _msg_lower = message.lower()
        if any(kw in _msg_lower for kw in _VIDEO_KEYWORDS):
            if plan.intent_classification != "video_analysis":
                logger.info(
                    f"[PlannerLock] Overriding intent "
                    f"'{plan.intent_classification}' → 'video_analysis' "
                    f"(video keyword detected in message)"
                )
                plan.intent_classification = "video_analysis"
                plan.tools_to_execute = []
                plan.reasoning = {}
                video_tools = ["fetch_last_video_analytics", "recall_context"]
                available = self.tool_registry.list_tools()
                for t in video_tools:
                    if t in available:
                        plan.add_tool(t, "Re-selected for video_analysis after planner lock")

        # Step 2a: Relative video reference detection
        # Handle "last video", "latest video", "my last upload" etc.
        # by fetching the most recent video from DB directly,
        # bypassing the fuzzy resolver entirely.
        _RELATIVE_PATTERNS = [
            r"\b(last|latest|recent|newest)\s+(video|upload|content)\b",
            r"\b(my|the)\s+(last|latest|recent)\s+(video|upload)\b",
            r"\b(my|the)\s+last\s+upload\b",
            r"\b(previous)\s+(video|upload)\b",
        ]
        is_relative_ref = any(
            re.search(p, message, re.IGNORECASE) for p in _RELATIVE_PATTERNS
        )

        if is_relative_ref and channel_uuid:
            logger.info(
                "[VideoResolver] Skipped — relative reference detected"
            )
            resolved = get_latest_video_from_db(channel_uuid, offset=0)
            if resolved:
                plan.parameters["resolved_video_id"] = resolved["video_id"]
                plan.parameters["resolved_video_title"] = resolved["title"]
                plan.parameters["video_resolution"] = resolved["video_resolution"]
                plan.parameters["reference_type"] = "relative"

                # Ensure intent is video_analysis so correct tools run
                if plan.intent_classification != "video_analysis":
                    logger.info(
                        f"[Resolver] Upgrading intent from "
                        f"'{plan.intent_classification}' → 'video_analysis' "
                        f"(relative reference)"
                    )
                    plan.intent_classification = "video_analysis"
                    plan.tools_to_execute = []
                    plan.reasoning = {}
                    available = self.tool_registry.list_tools()
                    for t in ["fetch_last_video_analytics", "recall_context"]:
                        if t in available:
                            plan.add_tool(t, "Selected for video_analysis (relative reference)")

                logger.info(
                    f"[Resolver] Relative video resolved: {resolved['video_id']} "
                    f"- \"{resolved['title']}\""
                )
            else:
                # No videos in DB at all
                logger.info(
                    "[Resolver] Relative reference but no videos in DB"
                )
                return ExecuteResponse(
                    success=True,
                    content="No videos found for your channel yet. "
                            "Please make sure your channel is connected and "
                            "has at least one uploaded video.",
                    metadata={
                        "intent": "video_analysis",
                        "clarification": True,
                        "reference_type": "relative",
                        "user_plan": user_plan,
                        "usage": usage_metadata,
                    }
                )

        # Step 2b: Video resolution for title-based queries
        # SKIP if Step 2a (relative reference) already resolved a video.
        # GUARDRAIL: If user mentions a specific video title, resolve it
        # BEFORE any tool execution. Never fall back to channel averages.
        #
        # Three entry paths:
        #   A) Planner says video_analysis + extracted_title  → use title
        #   B) Planner says video_analysis but no title       → use full message
        #   C) Planner says other intent but message has video keywords
        #      → proactive fallback to catch misclassified title queries
        extracted_title = None
        is_video_intent = plan.intent_classification == "video_analysis"
        already_resolved = plan.parameters.get("reference_type") == "relative"

        if not already_resolved and is_video_intent and plan.parameters.get("extracted_title"):
            # Path A: planner extracted a title
            extracted_title = plan.parameters["extracted_title"]
        elif not already_resolved and is_video_intent and not plan.parameters.get("extracted_title"):
            # Path B: video_analysis but no title — use cleaned message
            # Strip common preambles to get the title fragment
            cleaned = re.sub(
                r"^(please\s+)?(tell me about|analyze|how did|how is|what about)\s+",
                "", message, flags=re.IGNORECASE,
            ).strip()
            cleaned = re.sub(r"\s*\?\s*$", "", cleaned).strip()
            if len(cleaned) > 3:
                extracted_title = cleaned
                logger.info(
                    f"[Resolver] No extracted_title from planner — "
                    f"using cleaned message: \"{extracted_title}\""
                )
        elif (
            not already_resolved
            and not is_video_intent
            and channel_uuid
            and re.search(
                r"\b(tell me about|analyze|how did|how is)\b",
                message, re.IGNORECASE,
            )
        ):
            # Path C: planner misclassified, but message looks like
            # a title-based query. Try proactive resolution.
            cleaned = re.sub(
                r"^(please\s+)?(tell me about|analyze|how did|how is|what about)\s+",
                "", message, flags=re.IGNORECASE,
            ).strip()
            cleaned = re.sub(r"\s*\?\s*$", "", cleaned).strip()
            if len(cleaned) > 5:
                extracted_title = cleaned
                logger.info(
                    f"[Resolver] Proactive fallback — intent was "
                    f"'{plan.intent_classification}', attempting resolution "
                    f"with: \"{extracted_title}\""
                )

        if extracted_title and channel_uuid:
            logger.info(
                f"[Resolver] Resolving title: \"{extracted_title}\""
            )
            plan.parameters["extracted_title"] = extracted_title

            resolved = resolve_video_by_title(channel_uuid, extracted_title)

            # Cold-start: ONLY if videos table is empty (count == 0),
            # proactively fetch from YouTube API and retry.
            # NEVER triggers when DB has videos but title doesn't match.
            if resolved is None:
                video_count = get_video_count(channel_uuid)
                if video_count == 0:
                    channel_ctx = memory_context.get("channel", {})
                    access_token = channel_ctx.get("access_token")
                    if access_token:
                        logger.info(
                            "[VideoResolver] Triggering initial video sync "
                            "(table empty)"
                        )
                        resolved = await self._populate_and_resolve(
                            channel_uuid=channel_uuid,
                            channel_ctx=channel_ctx,
                            title_fragment=extracted_title,
                        )
                else:
                    logger.info(
                        f"[VideoResolver] Skipping sync "
                        f"(videos already present: {video_count})"
                    )

            # Handle resolver response (accepted / ambiguous / rejected / None)
            if resolved and resolved.get("clarification"):
                # Ambiguous or rejected — return clarification to user
                clarification_msg = resolved.get("message", "")
                candidates = resolved.get("candidates", [])
                resolution_meta = resolved.get("video_resolution", {})
                logger.info(
                    f"[Resolver] {resolution_meta.get('decision', 'unknown')} "
                    f"for \"{extracted_title}\" — "
                    f"returning clarification with {len(candidates)} candidates"
                )
                return ExecuteResponse(
                    success=True,
                    content=clarification_msg,
                    metadata={
                        "intent": "video_analysis",
                        "clarification": True,
                        "video_resolution": resolution_meta,
                        "user_plan": user_plan,
                        "usage": usage_metadata,
                    }
                )
            elif resolved and not resolved.get("clarification"):
                # Accepted match — attach resolved video info for tools
                plan.parameters["resolved_video_id"] = resolved["video_id"]
                plan.parameters["resolved_video_title"] = resolved["title"]
                resolution_meta = resolved.get("video_resolution", {})
                plan.parameters["video_resolution"] = resolution_meta

                # If planner misclassified, upgrade intent to video_analysis
                # so the correct tools (fetch_last_video_analytics) run.
                if plan.intent_classification != "video_analysis":
                    logger.info(
                        f"[Resolver] Upgrading intent from "
                        f"'{plan.intent_classification}' → 'video_analysis' "
                        f"(proactive resolution succeeded)"
                    )
                    plan.intent_classification = "video_analysis"
                    plan.tools_to_execute = []
                    plan.reasoning = {}
                    # Re-select tools for video_analysis intent
                    video_tools = ["fetch_last_video_analytics", "recall_context"]
                    available = self.tool_registry.list_tools()
                    for t in video_tools:
                        if t in available:
                            plan.add_tool(t, f"Re-selected for video_analysis after proactive resolution")

                logger.info(
                    f"[Resolver] Video resolved: {resolved['video_id']} "
                    f"- \"{resolved['title']}\" (score: {resolved['score']}, "
                    f"decision: {resolution_meta.get('decision', 'N/A')})"
                )
            else:
                # None — no videos in DB at all
                top_matches = get_top_matches(channel_uuid, extracted_title)
                clarification_msg = self._build_clarification_message(
                    extracted_title, top_matches
                )
                logger.info(
                    f"[Resolver] No match for \"{extracted_title}\" — "
                    f"returning clarification with {len(top_matches)} candidates"
                )
                return ExecuteResponse(
                    success=True,
                    content=clarification_msg,
                    metadata={
                        "intent": "video_analysis",
                        "clarification": True,
                        "user_plan": user_plan,
                        "usage": usage_metadata,
                    }
                )

        # Step 3: Check policy permissions
        approved_tools = self._filter_by_policy(plan, user_plan)

        # HARD GUARDRAIL: account intent must never execute tools
        if plan.intent_classification == "account":
            approved_tools = []
            tool_results = []
            logger.info("Account intent — skipping all tool execution")

        # HARD GUARDRAIL: video_analysis intent MUST have a resolved video.
        # If no video was resolved (no extracted_title, no channel_uuid,
        # or resolver returned ambiguous/rejected), block ALL tool execution
        # and LLM reasoning. Never fall back to channel averages.
        if (
            plan.intent_classification == "video_analysis"
            and not plan.parameters.get("resolved_video_id")
        ):
            logger.warning(
                "[VideoGuard] video_analysis intent but no resolved video — "
                "blocking all tools and LLM to prevent channel-average fallback"
            )
            return ExecuteResponse(
                success=True,
                content=(
                    "I couldn't find a specific video matching that title. "
                    "Please try with the exact video title or a longer portion "
                    "of it so I can analyze the right video."
                ),
                metadata={
                    "intent": "video_analysis",
                    "clarification": True,
                    "video_guard": "no_resolved_video",
                    "user_plan": user_plan,
                    "usage": usage_metadata,
                }
            )

        # HARD GUARDRAIL: compare_videos intent MUST have at least 2 resolved video_ids.
        # If fewer than 2, block tools and ask for clarification — never guess.
        if plan.intent_classification == "compare_videos":
            resolved_ids = plan.parameters.get("resolved_video_ids", [])
            if not isinstance(resolved_ids, list):
                resolved_ids = []
            if len(resolved_ids) < 2:
                logger.warning(
                    "[VideoGuard] compare_videos intent but only "
                    f"{len(resolved_ids)} resolved video_id(s) — "
                    "blocking tools, returning clarification"
                )
                return ExecuteResponse(
                    success=True,
                    content=(
                        "To compare videos, I need you to name both videos. "
                        "Please provide the titles of the two videos you'd "
                        "like me to compare."
                    ),
                    metadata={
                        "intent": "compare_videos",
                        "clarification": True,
                        "video_guard": "insufficient_resolved_videos",
                        "resolved_count": len(resolved_ids),
                        "user_plan": user_plan,
                        "usage": usage_metadata,
                    }
                )

        # Step 4: Execute approved tools
        if approved_tools:
            logger.debug(f"Executing {len(approved_tools)} tools")
            tool_results = await self._execute_tools(
                approved_tools, message, memory_context, plan.parameters
            )

        # Step 4.5a: Conversational name query intercept — no analytics needed
        if self._is_conversational_name_query(message):
            logger.info("[ConversationalRoute] Name query detected — no analytics")

            # Try to retrieve channel name from loaded context
            _ch = memory_context.get("channel", {}) or {}
            _ch_name = _ch.get("channel_name") if isinstance(_ch, dict) else None

            if _ch_name:
                response = f"Your channel name is **{_ch_name}**."
            else:
                response = (
                    "I don't have your channel name yet. "
                    "Please connect your YouTube channel so I can access your profile."
                )

            try:
                await self._store_conversation(
                    user_id=user_id,
                    channel_id=channel_id,
                    message=message,
                    response=response,
                    tools_used=[]
                )
            except Exception:
                pass
            return ExecuteResponse(
                success=True,
                content=response,
                metadata={
                    "intent": "conversational",
                    "confidence": 1.0,
                    "deterministic": True,
                    "user_plan": user_plan,
                    "usage": usage_metadata,
                }
            )

        # Step 4.5b: Identity intercept — deterministic archetype, no LLM
        if channel_uuid and self._is_identity_query(message):
            logger.info("[IdentityRoute] Identity query detected — deterministic render")
            try:
                archetype_response = self._compute_and_render_archetype(channel_uuid)
                if archetype_response:
                    # Store conversation
                    await self._store_conversation(
                        user_id=user_id,
                        channel_id=channel_id,
                        message=message,
                        response=archetype_response,
                        tools_used=[t.tool_name for t in tool_results]
                    )
                    self._persist_to_postgres(
                        user_uuid=user_uuid,
                        channel_uuid=channel_uuid,
                        message=message,
                        response=archetype_response,
                        tool_results=tool_results,
                        confidence=plan.confidence if hasattr(plan, "confidence") else None
                    )
                    metadata["usage"] = usage_metadata
                    return ExecuteResponse(
                        success=True,
                        content=archetype_response,
                        metadata={
                            "intent": "identity",
                            "confidence": 1.0,
                            "deterministic": True,
                            "user_plan": user_plan,
                            "usage": usage_metadata,
                        }
                    )
            except Exception as e:
                logger.warning(f"[IdentityRoute] Archetype render failed, falling through to LLM: {e}")

        # Step 4.6: Structural analysis intercept — unified through StrategyRankingEngine
        # NO SEPARATE RISK COMPUTATION. ALL risk goes through ONE engine.
        if plan.intent_classification == "structural_analysis" and channel_uuid:
            logger.info("[StructuralRoute] Structural analysis detected — routing through StrategyRankingEngine")
            try:
                archetype = self._compute_archetype(channel_uuid)
                # Build ChannelMetrics from snapshot (same as strategy block)
                retention_val = None
                conversion_pct = None
                shorts_pct = None
                try:
                    snapshot = self.postgres_store.get_latest_analytics_snapshot(channel_uuid)
                    if snapshot:
                        retention_val = snapshot.avg_view_percentage or None
                        views = snapshot.views or 0
                        subs = snapshot.subscribers_gained or 0
                        if views > 0:
                            conversion_pct = round((subs / views) * 100, 4)
                except Exception:
                    pass

                metrics = ChannelMetrics(
                    retention=retention_val,
                    conversion=conversion_pct,
                    shorts_ratio=shorts_pct,
                    theme_concentration=80,
                )
                ranker = StrategyRankingEngine()
                result = ranker.rank(metrics)

                # Build response: archetype identity + strategy ranking
                identity_block = ""
                if archetype:
                    identity_block = (
                        f"**Channel Identity**\n\n"
                        f"- **Format Type:** {archetype.format_type}\n"
                        f"- **Theme Type:** {archetype.theme_type}\n"
                        f"- **Growth Constraint:** {archetype.growth_constraint}\n"
                        f"- **Performance Type:** {archetype.performance_type}\n\n"
                    )

                structural_response = (
                    f"{identity_block}"
                    f"## Strategy Ranking\n\n"
                    f"{ranker.render(result)}"
                )

                logger.info(
                    f"[StructuralRoute] Unified: Primary={result.primary_constraint}, "
                    f"Severity={result.severity_score} — NO LLM call"
                )

                # Store conversation
                await self._store_conversation(
                    user_id=user_id,
                    channel_id=channel_id,
                    message=message,
                    response=structural_response,
                    tools_used=[]
                )
                self._persist_to_postgres(
                    user_uuid=user_uuid,
                    channel_uuid=channel_uuid,
                    message=message,
                    response=structural_response,
                    tool_results=[],
                    confidence=plan.confidence if hasattr(plan, "confidence") else None
                )
                metadata["usage"] = usage_metadata
                return ExecuteResponse(
                    success=True,
                    content=structural_response,
                    metadata={
                        "intent": "structural_analysis",
                        "confidence": 0.98,
                        "deterministic": True,
                        "user_plan": user_plan,
                        "usage": usage_metadata,
                    }
                )
            except Exception as e:
                logger.warning(f"[StructuralRoute] Strategy ranking failed, falling through to LLM: {e}")

        # Step 4.7: Report/weekly summary intercept — fully deterministic, NO LLM
        # HARD GUARDRAIL: report intent MUST NEVER reach the LLM.
        if plan.intent_classification == "report":
            logger.info("[ReportRoute] Report intent detected — deterministic only, NO LLM")
            try:
                from analytics.weekly_summary_generator import WeeklySummaryGenerator

                snapshot = None
                if channel_uuid:
                    try:
                        snapshot = self.postgres_store.get_latest_analytics_snapshot(channel_uuid)
                    except Exception as snap_err:
                        logger.warning(f"[ReportRoute] Snapshot fetch failed: {snap_err}")

                if snapshot:
                    analytics_data = {
                        "avg_view_percentage": getattr(snapshot, "avg_view_percentage", None) or 0,
                        "avg_watch_minutes": getattr(snapshot, "avg_watch_time_minutes", None) or 0,
                        "avg_video_length_minutes": getattr(snapshot, "avg_video_length_minutes", 0) or 0,
                        "shorts_ratio": getattr(snapshot, "shorts_ratio", 0) or 0,
                        "ctr_percent": getattr(snapshot, "avg_ctr", None) or 0,
                        "channel_avg_ctr": getattr(snapshot, "avg_ctr", None) or 0,
                        "impressions": getattr(snapshot, "impressions", None) or 0,
                        "views": getattr(snapshot, "views", None) or 0,
                        "subscribers_gained": getattr(snapshot, "subscribers_gained", 0) or 0,
                        "channel_avg_conversion_rate": 0,
                        "total_views": getattr(snapshot, "views", None) or 0,
                        "shorts_views": 0,
                        "long_views": getattr(snapshot, "views", None) or 0,
                        "shorts_avg_retention": 0,
                        "long_avg_retention": getattr(snapshot, "avg_view_percentage", None) or 0,
                        "current_period_views": getattr(snapshot, "views", None) or 0,
                        "previous_period_views": getattr(snapshot, "previous_views", None) or getattr(snapshot, "views", 0) or 0,
                        "current_period_subs": getattr(snapshot, "subscribers_gained", 0) or 0,
                        "previous_period_subs": getattr(snapshot, "previous_subs", 0) or 0,
                    }

                    generator = WeeklySummaryGenerator()
                    weekly_result = generator.generate(analytics_data)

                    # Constraint display translations
                    _ct = {
                        "ctr": "Low Click Attraction", "retention": "Viewers Leaving Early",
                        "conversion": "Low Subscriber Conversion", "shorts": "Shorts Dependency",
                        "growth": "Growth Slowdown",
                    }
                    _raw_pc = weekly_result['primary_constraint']
                    _display_pc = _ct.get(_raw_pc, _raw_pc)

                    # Format deterministic response
                    report_lines = [
                        f"**Primary Constraint:** {_display_pc}",
                        f"**Severity:** {self.severity_label(weekly_result['primary_severity'])}",
                        f"**Confidence:** {weekly_result['confidence']}",
                        "",
                        "**Constraint Ranking:**",
                    ]
                    for constraint, sev in weekly_result["ranked_constraints"]:
                        report_lines.append(f"- {_ct.get(constraint, constraint)}: {sev}")

                    if weekly_result.get("ranked_strategies"):
                        report_lines.append("")
                        report_lines.append("**Ranked Strategies:**")
                        for i, strat in enumerate(weekly_result["ranked_strategies"], 1):
                            name = strat.get("name", strat) if isinstance(strat, dict) else strat
                            lift = strat.get("estimated_lift", "") if isinstance(strat, dict) else ""
                            report_lines.append(f"{i}. {name}" + (f" (Lift: {lift})" if lift else ""))

                    report_response = "\n".join(report_lines)
                else:
                    # No snapshot available — return structured error, NOT LLM
                    report_response = (
                        "**Weekly Summary**\n\n"
                        "No analytics data available yet. "
                        "Please connect your YouTube channel to generate a weekly summary."
                    )

                # Persist (best-effort — must never crash the response)
                try:
                    await self._store_conversation(
                        user_id=user_id,
                        channel_id=channel_id,
                        message=message,
                        response=report_response,
                        tools_used=[]
                    )
                    self._persist_to_postgres(
                        user_uuid=user_uuid,
                        channel_uuid=channel_uuid,
                        message=message,
                        response=report_response,
                        tool_results=[],
                        confidence=plan.confidence if hasattr(plan, "confidence") else None
                    )
                except Exception as persist_err:
                    logger.warning(f"[ReportRoute] Persistence failed (non-fatal): {persist_err}")
                metadata["usage"] = usage_metadata
                return ExecuteResponse(
                    success=True,
                    content=report_response,
                    metadata={
                        "intent": "report",
                        "confidence": 0.98,
                        "deterministic": True,
                        "user_plan": user_plan,
                        "usage": usage_metadata,
                    }
                )
            except Exception as e:
                # Even on failure, return structured error — NEVER fall through to LLM
                logger.error(f"[ReportRoute] WeeklySummaryGenerator failed: {e}")
                metadata["usage"] = usage_metadata
                return ExecuteResponse(
                    success=True,
                    content=(
                        "**Weekly Summary**\n\n"
                        "Unable to generate weekly summary at this time. "
                        "Please try again shortly."
                    ),
                    metadata={
                        "intent": "report",
                        "confidence": 0.98,
                        "deterministic": True,
                        "user_plan": user_plan,
                        "usage": usage_metadata,
                    }
                )

        # Step 5: Call LLM with full context (including historical)
        logger.debug("Calling LLM")
        try:
            llm_response = await self._call_llm(
                message=message,
                memory_context=memory_context,
                tool_results=tool_results,
                plan=plan,
                channel_uuid=channel_uuid
            )
        except Exception as llm_err:
            logger.error(f"LLM call failed: {llm_err}")
            metadata["usage"] = usage_metadata
            return ExecuteResponse(
                success=False,
                content="",
                error=f"AI generation failed. Please try again.",
                metadata={
                    "intent": plan.intent_classification,
                    "user_plan": user_plan,
                    "usage": usage_metadata,
                }
            )

        # Step 6: Store conversation in short-term memory (Redis)
        await self._store_conversation(
            user_id=user_id,
            channel_id=channel_id,
            message=message,
            response=llm_response,
            tools_used=[t.tool_name for t in tool_results]
        )

        # Step 7: Persist to long-term memory (PostgreSQL) - non-blocking
        self._persist_to_postgres(
            user_uuid=user_uuid,
            channel_uuid=channel_uuid,
            message=message,
            response=llm_response,
            tool_results=tool_results,
            confidence=plan.confidence if hasattr(plan, "confidence") else None
        )

        # Step 8: Build structured analytics data for the response
        structured_data = self._build_structured_data(tool_results)

        # Inject usage metadata into request metadata
        # so _build_metadata can propagate it to the response
        metadata["usage"] = usage_metadata

        # Step 9: Format and return response
        return self.formatter.format_response(
            llm_response=llm_response,
            tool_results=tool_results,
            plan=plan,
            metadata=metadata,
            structured_data=structured_data
        )

    def _safe_parse_uuid(self, id_str: str) -> Optional[UUID]:
        """
        Safely parse a string to UUID.

        Args:
            id_str: String representation of UUID

        Returns:
            UUID object or None if invalid
        """
        try:
            return UUID(id_str)
        except (ValueError, AttributeError):
            logger.warning(f"Invalid UUID format: {id_str}")
            return None

    def _load_historical_context(
        self,
        channel_uuid: Optional[UUID],
        user_uuid: Optional[UUID]
    ) -> dict[str, Any]:
        """
        Load historical context from PostgreSQL long-term memory.

        Args:
            channel_uuid: Channel UUID for analytics and insights
            user_uuid: User UUID for chat history

        Returns:
            Dictionary containing historical context
        """
        historical_context: dict[str, Any] = {
            "latest_snapshot": None,
            "recent_insights": [],
            "recent_chats": []
        }

        # Load latest analytics snapshot for channel
        if channel_uuid:
            try:
                snapshot = self.postgres_store.get_latest_analytics_snapshot(
                    channel_uuid
                )
                if snapshot:
                    historical_context["latest_snapshot"] = {
                        "period": snapshot.period,
                        "subscribers": snapshot.subscribers,
                        "views": snapshot.views,
                        "avg_ctr": snapshot.avg_ctr,
                        "avg_watch_time_minutes": snapshot.avg_watch_time_minutes,
                        "created_at": snapshot.created_at.isoformat()
                        if snapshot.created_at else None
                    }
            except Exception as e:
                logger.error(f"Failed to load analytics snapshot: {e}")

            # Load recent weekly insights (limit 3)
            try:
                insights = self.postgres_store.get_recent_weekly_insights(
                    channel_uuid, limit=3
                )
                historical_context["recent_insights"] = [
                    {
                        "week_start": insight.week_start.isoformat()
                        if insight.week_start else None,
                        "summary": insight.summary,
                        "wins": insight.wins,
                        "losses": insight.losses,
                        "next_actions": insight.next_actions
                    }
                    for insight in insights
                ]
            except Exception as e:
                logger.error(f"Failed to load weekly insights: {e}")

        # Load recent chat sessions for user (limit 5)
        if user_uuid:
            try:
                chats = self.postgres_store.get_recent_chat_sessions(
                    user_uuid, channel_id=channel_uuid, limit=5
                )
                historical_context["recent_chats"] = [
                    {
                        "user_message": chat.user_message,
                        "assistant_response": chat.assistant_response,
                        "tools_used": chat.tools_used,
                        "created_at": chat.created_at.isoformat()
                        if chat.created_at else None
                    }
                    for chat in chats
                ]
            except Exception as e:
                logger.error(f"Failed to load chat sessions: {e}")

        return historical_context

    def _persist_to_postgres(
        self,
        user_uuid: Optional[UUID],
        channel_uuid: Optional[UUID],
        message: str,
        response: str,
        tool_results: list[ToolResult],
        confidence: Optional[float] = None
    ) -> None:
        """
        Persist execution results to PostgreSQL long-term memory.

        This method handles:
        - Chat session persistence
        - Conditional analytics snapshot persistence
        - Conditional weekly insight persistence

        Args:
            user_uuid: User UUID
            channel_uuid: Channel UUID
            message: User's message
            response: Assistant's response
            tool_results: Results from tool execution
            confidence: Confidence score of the response
        """
        # Persist chat session (requires valid user_uuid)
        if user_uuid:
            try:
                tools_used_list = [
                    t.tool_name for t in tool_results if t.success]
                chat_session = ChatSession(
                    user_id=user_uuid,
                    channel_id=channel_uuid,
                    user_message=message,
                    assistant_response=response,
                    tools_used={
                        "tools": tools_used_list} if tools_used_list else None,
                    confidence=confidence
                )
                self.postgres_store.save_chat_session(chat_session)
                logger.debug("Chat session persisted to PostgreSQL")
            except Exception as e:
                # Non-blocking: log error but don't fail the request
                logger.error(f"Failed to persist chat session: {e}")
        else:
            logger.warning(
                "Skipping chat session persistence: invalid user_id")

        # Conditional persistence based on tool outputs
        if channel_uuid:
            self._persist_tool_outputs(channel_uuid, tool_results)

    def _persist_tool_outputs(
        self,
        channel_uuid: UUID,
        tool_results: list[ToolResult]
    ) -> None:
        """
        Conditionally persist analytics and insights from tool outputs.

        Args:
            channel_uuid: Channel UUID
            tool_results: Results from tool execution
        """
        for result in tool_results:
            if not result.success or not result.output:
                continue

            output = result.output

            # Check for analytics snapshot data
            if self._is_analytics_snapshot_output(result.tool_name, output):
                try:
                    snapshot = AnalyticsSnapshot(
                        channel_id=channel_uuid,
                        period=output.get("period", "unknown"),
                        subscribers=output.get("subscribers", 0),
                        views=output.get("views", 0),
                        avg_ctr=output.get("avg_ctr", 0.0),
                        avg_watch_time_minutes=output.get(
                            "avg_watch_time_minutes", 0.0
                        )
                    )
                    self.postgres_store.save_analytics_snapshot(snapshot)
                    logger.debug(
                        f"Analytics snapshot persisted from {result.tool_name}"
                    )
                except Exception as e:
                    logger.error(f"Failed to persist analytics snapshot: {e}")

            # Check for weekly insight data
            if self._is_weekly_insight_output(result.tool_name, output):
                try:
                    from datetime import date as date_type
                    week_start = output.get("week_start")
                    if isinstance(week_start, str):
                        week_start = date_type.fromisoformat(week_start)

                    insight = WeeklyInsight(
                        channel_id=channel_uuid,
                        week_start=week_start or date_type.today(),
                        summary=output.get("summary"),
                        wins=output.get("wins"),
                        losses=output.get("losses"),
                        next_actions=output.get("next_actions")
                    )
                    self.postgres_store.save_weekly_insight(insight)
                    logger.debug(
                        f"Weekly insight persisted from {result.tool_name}"
                    )
                except Exception as e:
                    logger.error(f"Failed to persist weekly insight: {e}")

    def _is_analytics_snapshot_output(
        self, tool_name: str, output: Any
    ) -> bool:
        """
        Check if tool output contains analytics snapshot data.

        Args:
            tool_name: Name of the executed tool
            output: Tool output data

        Returns:
            True if output contains analytics snapshot data
        """
        analytics_tools = {
            "fetch_analytics",
            "get_channel_snapshot",
            "compute_metrics"
        }

        if tool_name in analytics_tools and isinstance(output, dict):
            # Check for required analytics fields
            return any(
                key in output
                for key in ["subscribers", "views", "avg_ctr"]
            )
        return False

    def _is_weekly_insight_output(self, tool_name: str, output: Any) -> bool:
        """
        Check if tool output contains weekly insight data.

        Args:
            tool_name: Name of the executed tool
            output: Tool output data

        Returns:
            True if output contains weekly insight data
        """
        insight_tools = {
            "weekly_growth_report",
            "generate_insight",
            "analyze_data"
        }

        if tool_name in insight_tools and isinstance(output, dict):
            # Check for weekly insight structure
            return any(
                key in output
                for key in ["summary", "wins", "losses", "next_actions"]
            )
        return False

    async def _load_memory_context(
        self,
        user_id: str,
        channel_id: str
    ) -> dict[str, Any]:
        """
        Load relevant context from short-term memory (Redis).

        Long-term context is loaded separately via _load_historical_context.

        Args:
            user_id: User identifier
            channel_id: Channel identifier

        Returns:
            Memory context dictionary with short-term data
        """
        # Load short-term context (recent conversation from Redis)
        short_term = await self.redis_store.get_conversation_context(
            user_id=user_id,
            channel_id=channel_id
        )

        return {
            "conversation_history": short_term.get("messages", []),
            "session_state": short_term.get("state", {}),
            # Historical context is added in execute() via _load_historical_context
        }

    def _filter_by_policy(
        self,
        plan: ExecutionPlan,
        user_plan: str
    ) -> list[str]:
        """
        Filter planned tools by user's subscription plan.

        Args:
            plan: Execution plan from planner
            user_plan: User's subscription tier

        Returns:
            List of tool names approved for execution
        """
        approved = []
        for tool_name in plan.tools_to_execute:
            if self.policy_engine.can_execute(tool_name, user_plan):
                approved.append(tool_name)
            else:
                logger.info(
                    f"Tool {tool_name} blocked by policy for plan {user_plan}")

        return approved

    async def _execute_tools(
        self,
        tool_names: list[str],
        message: str,
        context: dict[str, Any],
        parameters: dict[str, Any] = None
    ) -> list[ToolResult]:
        """
        Execute a list of tools and collect results.

        Args:
            tool_names: Names of tools to execute
            message: Original user message
            context: Memory context for tool execution
            parameters: Optional execution parameters from planner

        Returns:
            List of tool execution results
        """
        results = []
        parameters = parameters or {}
        
        for tool_name in tool_names:
            try:
                # Base input data
                input_data = {
                    "message": message,
                    "context": context
                }
                
                # Merge planner parameters (e.g. period="28d", fetch_library=True)
                input_data.update(parameters)
                
                result = await self.tool_registry.execute_tool(
                    tool_name=tool_name,
                    input_data=input_data
                )
                results.append(result)
            except Exception as e:
                logger.error(f"Tool {tool_name} execution failed: {e}")
                results.append(ToolResult(
                    tool_name=tool_name,
                    success=False,
                    output=None,
                    error=str(e)
                ))

        return results

    async def _call_llm(
        self,
        message: str,
        memory_context: dict[str, Any],
        tool_results: list[ToolResult],
        plan: ExecutionPlan,
        channel_uuid: Optional[UUID] = None
    ) -> str:
        """
        Call the LLM with full context to generate response.

        Args:
            message: User's input message
            memory_context: Loaded memory context (including historical)
            tool_results: Results from tool execution
            plan: Execution plan for context
            channel_uuid: Channel UUID for analytics context

        Returns:
            LLM-generated response string
        """
        # Load system prompt
        system_prompt = self._load_prompt("system")
        
        # Load analysis prompt (includes content strategy template)
        analysis_prompt = self._load_prompt("analysis")

        # HARD GUARDRAIL: Only build analytics context for analytics intents
        analytics_intents = {"analytics", "video_analysis", "insight", "report", "compare_videos"}
        # Broader set: intents that need channel data context (e.g. subscriber count, video library)
        context_intents = analytics_intents | {"account", "pattern_analysis"}
        
        if plan.intent_classification in context_intents:
            analytics_context = self.analytics_builder.build_analytics_context(
                channel_uuid
            )
            # If fetch_analytics tool returned fresh data, use it
            # to override stale/empty DB context for this request
            analytics_context = self._merge_tool_analytics(
                analytics_context, tool_results
            )
        else:
            analytics_context = {}
            logger.info(f"Skipping analytics injection for intent: {plan.intent_classification}")

        # Build context for LLM
        context_parts = []

        # Add conversation history (short-term from Redis)
        # SKIP for pattern_analysis — old conversation contains stale pattern responses
        # that the LLM would copy instead of using the fresh pre-computed pattern data
        history = memory_context.get("conversation_history", [])
        if history and plan.intent_classification != "pattern_analysis":
            context_parts.append("Recent conversation:")
            for msg in history[-5:]:  # Last 5 messages
                context_parts.append(
                    f"- {msg.get('role', 'user')}: {msg.get('content', '')}")

        # Add historical context from PostgreSQL
        historical = memory_context.get("historical", {})

        # Add latest analytics snapshot
        latest_snapshot = historical.get("latest_snapshot")
        if latest_snapshot:
            context_parts.append("\nLatest channel analytics:")
            context_parts.append(
                f"- Period: {latest_snapshot.get('period')}"
            )
            context_parts.append(
                f"- Subscribers: {latest_snapshot.get('subscribers'):,}"
            )
            context_parts.append(
                f"- Views: {latest_snapshot.get('views'):,}"
            )
            context_parts.append(
                f"- Avg CTR: {latest_snapshot.get('avg_ctr', 0):.2f}%"
            )
            context_parts.append(
                f"- Avg Watch Time: {latest_snapshot.get('avg_watch_time_minutes', 0):.1f} min"
            )

        # Add recent weekly insights
        recent_insights = historical.get("recent_insights", [])
        if recent_insights:
            context_parts.append("\nRecent weekly insights:")
            for insight in recent_insights:
                if insight.get("summary"):
                    context_parts.append(
                        f"- Week {insight.get('week_start')}: {insight.get('summary')}"
                    )
                if insight.get("wins"):
                    wins = insight['wins']
                    wins_str = ', '.join(wins) if isinstance(
                        wins, list) else str(wins)
                    context_parts.append(f"  Wins: {wins_str}")

        # Add recent chat history from PostgreSQL
        # SKIP for pattern_analysis — old chat history contains stale pattern responses
        # that contaminate the LLM output
        recent_chats = historical.get("recent_chats", [])
        if recent_chats and plan.intent_classification != "pattern_analysis":
            context_parts.append("\nPrevious conversations:")
            for chat in recent_chats[:3]:  # Limit to 3 for context
                user_msg = chat.get("user_message", "")[:100]  # Truncate
                context_parts.append(f"- User: {user_msg}...")

        # Add tool results
        # SKIP for pattern_analysis — pattern engine uses pre-computed data only
        if tool_results and plan.intent_classification != "pattern_analysis":
            context_parts.append("\nTool execution results:")
            for result in tool_results:
                if result.success:
                    context_parts.append(
                        f"- {result.tool_name}: {result.output}")
                else:
                    context_parts.append(
                        f"- {result.tool_name}: Error - {result.error}")

        full_context = "\n".join(
            context_parts) if context_parts else "No additional context."

        # For insight intent, replace bloated context with minimal structured metrics
        if plan.intent_classification == "insight":
            retention = analytics_context.get("avg_view_pct") or analytics_context.get("averageViewPercentage") or 0
            views = analytics_context.get("views") or analytics_context.get("total_views") or 0
            subs_gained = analytics_context.get("subscribersGained") or analytics_context.get("subscribers_gained") or 0
            traffic = analytics_context.get("traffic_sources", {})
            shorts_views = traffic.get("SHORTS", 0) if isinstance(traffic, dict) else 0
            total_views = max(views, 1)
            shorts_ratio = round(shorts_views / total_views, 2) if shorts_views else 0

            full_context = f"""[METRICS]
Retention: {retention}
Views (7d): {views}
Shorts Ratio: {shorts_ratio}"""
            # Strip competing bottleneck signals from context
            # If archetype is available and constraint is NOT conversion, hide sub data
            logger.info(f"[InsightOptim] Compact context: {len(full_context)} chars (retention={retention}, views={views})")

        # Build structured analytics section
        # HARD GUARDRAIL: Only inject analytics prompt section for analytics intents
        if plan.intent_classification in analytics_intents:
            analytics_section = self._build_analytics_prompt_section(analytics_context)
        else:
            analytics_section = ""

        # Build video analytics section from tool results
        # Only inject for video_analysis — all other intents use structured context
        if plan.intent_classification == "video_analysis":
            video_analytics_section = self._build_video_analytics_prompt_section(tool_results)

            # ──────────────────────────────────────────────
            # LLM BYPASS — Video Diagnosis Engine
            # ScopeGuard enforced: video scope validated before engine runs.
            # ──────────────────────────────────────────────
            scope_guard = ScopeGuardLayer()
            try:
                for tr in tool_results:
                    logger.info(f"[VideoDiagnosisBypass] Checking tool: {tr.tool_name}, success={tr.success}, output_type={type(tr.output).__name__}")
                    if tr.tool_name == "fetch_last_video_analytics" and tr.success:
                        vdata = tr.output.get("data", {}) if isinstance(tr.output, dict) else {}
                        logger.info(f"[VideoDiagnosisBypass] vdata keys: {list(vdata.keys()) if vdata else 'EMPTY'}, has_library={'library' in vdata if vdata else False}")
                        if vdata and "library" not in vdata:
                            v_title = vdata.get("title", "Unknown")
                            v_views = vdata.get("views", 0)
                            v_retention = vdata.get("avg_view_percentage", 0)
                            v_watch_sec = vdata.get("avg_watch_time_seconds", 0)
                            v_watch_min = v_watch_sec / 60.0 if v_watch_sec else 0
                            v_duration_sec = vdata.get("duration_seconds", 0)
                            v_duration_min = v_duration_sec / 60.0 if v_duration_sec else 0
                            v_likes = vdata.get("likes", 0)
                            v_comments = vdata.get("comments", 0)
                            v_engagement = vdata.get("engagement_rate", 0)

                            # Fallback 1: estimate retention from watch time / duration
                            if not v_retention and v_watch_sec and v_duration_sec:
                                v_retention = (v_watch_sec / v_duration_sec) * 100

                            # Fallback 2: use channel-level retention from analytics snapshot
                            if not v_retention:
                                # Try all known key paths in analytics_context
                                cp = analytics_context.get("current_period") or {}
                                channel_retention = (
                                    cp.get("avg_view_percentage")       # Primary: from _merge_tool_analytics
                                    or cp.get("averageViewPercentage")  # Alt YouTube API key
                                    or analytics_context.get("avg_view_pct")  # From archetype snapshot
                                    or analytics_context.get("averageViewPercentage")
                                    or 0
                                )
                                logger.info(
                                    f"[VideoDiagnosisBypass] Fallback 2: "
                                    f"current_period keys={list(cp.keys())[:8]}, "
                                    f"channel_retention={channel_retention}"
                                )
                                if channel_retention:
                                    v_retention = float(channel_retention)
                                    logger.info(f"[VideoDiagnosisBypass] Using channel-level retention fallback: {v_retention}%")

                            # Fallback for duration: default to 1 min if unknown
                            if not v_duration_min:
                                v_duration_min = 1.0

                            logger.info(f"[VideoDiagnosisBypass] v_retention={v_retention}, v_duration_min={v_duration_min}, v_watch_sec={v_watch_sec}, v_duration_sec={v_duration_sec}")
                            if v_retention > 0 and v_duration_min > 0:
                                v_format = "short" if v_duration_min <= 1 else "long"
                                # Scope guard: validate inputs before engine
                                scope_data = {
                                    "video_avg_view_percentage": min(v_retention, 100),
                                    "video_watch_time_minutes": max(v_watch_min, 0),
                                    "video_length_minutes": max(v_duration_min, 0.1),
                                    "video_ctr": 0,
                                    "impressions": 0,
                                    "format_type": v_format,
                                }
                                scope_check = scope_guard.enforce("video_analysis", scope_data)
                                if scope_check.get("status") != "ok":
                                    logger.warning(f"[ScopeGuard] Video scope blocked: {scope_check}")
                                    break

                                vd_engine = VideoDiagnosisEngine()
                                vd_result = vd_engine.diagnose(**scope_data)

                                # Cold-start guard — insufficient data
                                if vd_result.get('primary_constraint') == 'insufficient_data':
                                    direct = (
                                        f"## Video Analysis: {v_title}\n\n"
                                        f"{vd_result['message']}\n\n"
                                        f"Allow the video to gather more viewer activity before analyzing its performance."
                                    )
                                    logger.info(f"[VideoDiagnosisBypass] Cold-start: insufficient data for {v_title}")
                                    return direct

                                # Sanitize output — strip any non-video keys
                                vd_result = scope_guard.sanitize_for_llm("video", vd_result)

                                _ct = {
                                    "ctr": "Low Click Attraction", "retention": "Viewers Leaving Early",
                                    "conversion": "Low Subscriber Conversion", "shorts": "Shorts Dependency",
                                    "growth": "Growth Slowdown",
                                }
                                _ce = {
                                    "ctr": "Your thumbnails and titles are not convincing enough viewers to click on the video.",
                                    "retention": "A noticeable portion of viewers stop watching before reaching the most interesting part of the video.",
                                    "conversion": "Many viewers watch your content but very few decide to subscribe.",
                                    "shorts": "Most views are coming from Shorts, which can limit deeper audience engagement.",
                                    "growth": "The channel's overall growth momentum has started to slow.",
                                }
                                _raw_vd = vd_result['primary_constraint']
                                _display_vd = _ct.get(_raw_vd, _raw_vd)
                                _explain_vd = _ce.get(_raw_vd, "")
                                direct = (
                                    f"## Video Analysis: {v_title}\n\n"
                                    f"**Performance Data**\n"
                                    f"- Views: {v_views:,}\n"
                                    f"- Avg View Percentage: {round(v_retention, 1)}%\n"
                                    f"- Avg Watch Time: {round(v_watch_min, 1)} min\n"
                                    f"- Duration: {round(v_duration_min, 1)} min\n"
                                    f"- Likes: {v_likes:,}\n"
                                    f"- Comments: {v_comments:,}\n"
                                    f"- Engagement Rate: {round(v_engagement, 2)}%\n"
                                    f"\n**Video Diagnosis**\n"
                                    f"- Primary Constraint: {_display_vd}\n"
                                )
                                if _explain_vd:
                                    direct += f"\n{_explain_vd}\n\n"
                                direct += (
                                    f"- Severity: {self.severity_label(vd_result['severity_score'])}\n"
                                    f"- Confidence: {vd_result['confidence']}\n"
                                )

                                logger.info(
                                    f"[VideoDiagnosisBypass] constraint={vd_result['primary_constraint']}, "
                                    f"severity={vd_result['severity_score']} — NO LLM call"
                                )
                                return direct
                        break
            except Exception as e:
                logger.warning(f"[VideoDiagnosisBypass] Failed, falling back to LLM: {e}")
        else:
            video_analytics_section = ""

        # Build video library section from DB
        # Only inject for video_analysis and search — these need per-video data
        # All other intents skip this to keep prompt compact
        if plan.intent_classification in ("video_analysis", "search"):
            video_library_section = self._build_video_library_from_db(channel_uuid)
        else:
            video_library_section = ""

        # Build deterministic diagnostics for video_analysis intent
        diagnostics_section = ""
        if plan.intent_classification == "video_analysis" and channel_uuid:
            diagnostics_section = self._build_diagnostics_section(
                analytics_context=analytics_context,
                tool_results=tool_results,
                channel_uuid=channel_uuid,
            )

        # Build pattern intelligence for pattern_analysis intent
        pattern_section = ""
        if plan.intent_classification == "pattern_analysis" and channel_uuid:
            logger.info("[PatternRoute] Building pattern section for pattern_analysis intent")
            pattern_section = self._build_pattern_section(
                channel_uuid=channel_uuid,
            )
            logger.info(f"[PatternRoute] Pattern section length: {len(pattern_section)} chars")
            if pattern_section:
                logger.info(f"[PatternRoute] Preview: {pattern_section[:200]}")
        else:
            logger.info(f"[PatternRoute] Skipped — intent={plan.intent_classification}, channel_uuid={channel_uuid}")

        # Build archetype context for strategy intents (Phase 1.5)
        archetype_section = ""
        strategy_ranking_section = ""
        retention_diagnosis_section = ""
        next_video_blueprint_section = ""
        if plan.intent_classification in ("insight", "analytics", "structural_analysis") and channel_uuid:
            try:
                archetype = self._compute_archetype(channel_uuid)
                if archetype:
                    # Deterministic guard: force primary focus based on constraint
                    primary_focus = "General Growth"
                    if archetype.growth_constraint == "Retention-Constrained":
                        primary_focus = "Retention Optimization"
                    elif archetype.growth_constraint == "Conversion-Constrained":
                        primary_focus = "Subscriber Conversion"
                    elif archetype.growth_constraint == "Momentum-Declining":
                        primary_focus = "Momentum Recovery"

                    archetype_section = f"""## Channel Context (pre-computed diagnostics)

Primary Growth Constraint: {archetype.growth_constraint}
This is the primary bottleneck identified by the diagnostics layer.
Base your response on this constraint.

Channel Identity:
- Format Type: {archetype.format_type}
- Theme Type: {archetype.theme_type}
- Growth Constraint: {archetype.growth_constraint}
- Performance Type: {archetype.performance_type}
- Primary Focus: {primary_focus}

Strategy Guidance:

1. If Growth Constraint = Retention-Constrained:
   Lead with hook engineering and pacing optimization.

2. If Growth Constraint = Conversion-Constrained:
   Focus on CTA, subscriber psychology, loyalty mechanics.

3. If Theme Type = Theme-Concentrated:
   Note creative fragility and suggest controlled thematic expansion.

4. If Format Type contains Dominant:
   Suggest diversification testing.

5. If Performance Type = Underperforming Library:
   Focus on packaging, topic-market mismatch, title/thumbnail testing.

6. If Performance Type = Stable Library:
   Recommend scaling winning patterns.

Constraint Priority (from diagnostics layer):
1. Retention (affects distribution)
2. Conversion (affects scaling)
3. Momentum (affects trajectory)

Primary Focus: {primary_focus}"""
                    plan.parameters["growth_constraint"] = archetype.growth_constraint
                    plan.parameters["archetype"] = {
                        "format_type": archetype.format_type,
                        "theme_type": archetype.theme_type,
                        "growth_constraint": archetype.growth_constraint,
                        "performance_type": archetype.performance_type,
                    }
                    logger.info(f"[ArchetypeRoute] Archetype injected: {archetype.format_type}, {archetype.theme_type}, {archetype.growth_constraint}, {archetype.performance_type}")
                    self._last_archetype = plan.parameters["archetype"]

                    # Compute deterministic strategy ranking
                    try:
                        retention_val = None
                        conversion_pct = None
                        shorts_pct = None

                        try:
                            snapshot = self.postgres_store.get_latest_analytics_snapshot(channel_uuid)
                            if snapshot:
                                retention_val = snapshot.avg_view_percentage or None
                                views = snapshot.views or 0
                                subs = snapshot.subscribers_gained or 0
                                if views > 0:
                                    conversion_pct = round((subs / views) * 100, 4)
                                # Compute shorts ratio from traffic sources
                                traffic = analytics_context.get("traffic_sources", {})
                                shorts_views = traffic.get("SHORTS", 0) if isinstance(traffic, dict) else 0
                                total_views = max(views, 1)
                                if shorts_views:
                                    shorts_pct = round((shorts_views / total_views) * 100, 1)
                        except Exception:
                            pass

                        metrics = ChannelMetrics(
                            retention=retention_val,
                            conversion=conversion_pct,
                            shorts_ratio=shorts_pct,
                            theme_concentration=80,  # TODO: compute from pattern data
                        )
                        ranker = StrategyRankingEngine()
                        result = ranker.rank(metrics)
                        strategy_ranking_section = ranker.render(result)
                        logger.info(f"[StrategyRanker] {result.primary_constraint}, severity={result.severity_score}, confidence={result.confidence}")

                        # Generate deterministic next-video blueprint
                        try:
                            from analytics.next_video_blueprint_engine import NextVideoBlueprintEngine
                            blueprint_engine = NextVideoBlueprintEngine()
                            blueprint = blueprint_engine.generate(result.primary_constraint)
                            next_video_blueprint_section = (
                                "\n## Next Video Blueprint\n\n"
                                f"Direction: {blueprint['next_video_direction']}\n"
                                f"Opening Approach: {blueprint['opening_approach']}\n"
                                f"Content Structure: {blueprint['content_structure']}\n"
                                f"Creator Action: {blueprint['creator_action']}\n"
                            )
                            logger.info(f"[NextVideoBlueprint] constraint={result.primary_constraint}, generated")
                        except Exception as bp_err:
                            logger.warning(f"[NextVideoBlueprint] Failed: {bp_err}")
                            next_video_blueprint_section = ""

                    except Exception as e:
                        logger.warning(f"[StrategyRanker] Failed: {e}")
                        strategy_ranking_section = ""

                    # Compute deterministic retention diagnosis
                    retention_diagnosis_section = ""
                    try:
                        if retention_val is not None and retention_val > 0:
                            # Get watch time and video length from snapshot
                            avg_watch_minutes = 0.0
                            avg_video_length = 0.0
                            shorts_ratio_decimal = 0.0

                            try:
                                if snapshot:
                                    avg_duration_sec = snapshot.average_view_duration or 0
                                    avg_watch_minutes = avg_duration_sec / 60.0
                                    # Estimate avg video length from watch time and retention
                                    if retention_val > 0:
                                        avg_video_length = (avg_watch_minutes / (retention_val / 100.0))
                                    # Shorts ratio as decimal (0-1)
                                    if shorts_pct is not None:
                                        shorts_ratio_decimal = shorts_pct / 100.0
                            except Exception:
                                pass

                            diag_engine = RetentionDiagnosisEngine()
                            diagnosis = diag_engine.diagnose(
                                avg_view_percentage=retention_val,
                                avg_watch_time_minutes=avg_watch_minutes,
                                avg_video_length_minutes=max(avg_video_length, 0),
                                shorts_ratio=min(shorts_ratio_decimal, 1.0),
                                long_form_ratio=max(0, 1.0 - min(shorts_ratio_decimal, 1.0)),
                            )
                            retention_diagnosis_section = (
                                f"Retention Diagnosis:\n"
                                f"- Severity: {self.severity_label(diagnosis['severity_score'])}\n"
                                f"- Confidence: {diagnosis['confidence']}"
                            )
                            logger.info(f"[RetentionDiagnosis] severity={diagnosis['severity_score']}, risk={diagnosis['risk_level']}")
                    except Exception as e:
                        logger.warning(f"[RetentionDiagnosis] Failed: {e}")
            except Exception as e:
                logger.warning(f"[ArchetypeRoute] Failed to build archetype section: {e}")

        # Parse and strip [TOP_VIDEO_CONTEXT] metadata from message
        clean_message, top_video_meta = self._parse_top_video_context(message)
        is_top_video = self._is_top_video_query(clean_message)

        # Build the prompt
        if is_top_video and top_video_meta:
            # --- DEDICATED TOP VIDEO ANALYSIS PATH ---
            top_video_prompt = self._load_prompt("top_video_analysis")

            # Build video metrics section from parsed metadata
            tv_views = top_video_meta.get("views", 0)
            tv_growth = top_video_meta.get("growth", 0)
            tv_title = top_video_meta.get("title", "Unknown")
            video_metrics_section = (
                f"\nVideo Performance Data (last 7 days):\n"
                f"- Title: {tv_title}\n"
                f"- Views: {tv_views:,}\n"
                f"- Growth vs previous 7 days: {'+' if tv_growth > 0 else ''}{tv_growth}%\n"
            )

            # Compute deterministic video diagnosis
            video_diagnosis_block = ""
            try:
                tv_retention = top_video_meta.get("avg_view_percentage", 0)
                tv_watch_time = top_video_meta.get("watch_time_minutes", 0)
                tv_length = top_video_meta.get("video_length_minutes", 0)
                tv_ctr = top_video_meta.get("ctr", 0)
                tv_impressions = top_video_meta.get("impressions", 0)
                tv_format = "short" if tv_length and tv_length <= 1 else "long"

                if tv_retention and tv_length and tv_length > 0:
                    vd_engine = VideoDiagnosisEngine()
                    vd_result = vd_engine.diagnose(
                        video_avg_view_percentage=tv_retention,
                        video_watch_time_minutes=max(tv_watch_time, 0),
                        video_length_minutes=max(tv_length, 0.1),
                        video_ctr=max(tv_ctr, 0),
                        impressions=max(int(tv_impressions), 0),
                        format_type=tv_format,
                    )

                    # Cold-start guard — insufficient data
                    if vd_result.get('primary_constraint') == 'insufficient_data':
                        video_diagnosis_block = (
                            f"\nVideo Analysis:\n"
                            f"{vd_result['message']}\n\n"
                            f"Allow the video to gather more viewer activity before analyzing its performance.\n"
                        )
                        logger.info(f"[VideoDiagnosis] Cold-start: insufficient data")
                    else:
                        _ct = {
                            "ctr": "Low Click Attraction", "retention": "Viewers Leaving Early",
                            "conversion": "Low Subscriber Conversion", "shorts": "Shorts Dependency",
                            "growth": "Growth Slowdown",
                        }
                        _ce = {
                            "ctr": "Your thumbnails and titles are not convincing enough viewers to click on the video.",
                            "retention": "A noticeable portion of viewers stop watching before reaching the most interesting part of the video.",
                            "conversion": "Many viewers watch your content but very few decide to subscribe.",
                            "shorts": "Most views are coming from Shorts, which can limit deeper audience engagement.",
                            "growth": "The channel's overall growth momentum has started to slow.",
                        }
                        _raw_vd2 = vd_result['primary_constraint']
                        _display_vd2 = _ct.get(_raw_vd2, _raw_vd2)
                        _explain_vd2 = _ce.get(_raw_vd2, "")
                        video_diagnosis_block = (
                            f"\nVideo Diagnosis:\n"
                            f"- Primary Constraint: {_display_vd2}\n"
                        )
                        if _explain_vd2:
                            video_diagnosis_block += f"\n{_explain_vd2}\n\n"
                        video_diagnosis_block += (
                            f"- Severity: {self.severity_label(vd_result['severity_score'])}\n"
                            f"- Confidence: {vd_result['confidence']}\n"
                        )
                        logger.info(f"[VideoDiagnosis] constraint={vd_result['primary_constraint']}, severity={vd_result['severity_score']}")
            except Exception as e:
                logger.warning(f"[VideoDiagnosis] Failed: {e}")

            # ──────────────────────────────────────────────
            # LLM BYPASS — Video Diagnosis Engine
            # If we have a pre-computed video diagnosis, return directly. No LLM.
            # ──────────────────────────────────────────────
            if video_diagnosis_block:
                direct_response = (
                    f"## Video Analysis: {tv_title}\n\n"
                    f"**Performance Data (last 7 days)**\n"
                    f"- Views: {tv_views:,}\n"
                    f"- Growth vs previous 7 days: {'+' if tv_growth > 0 else ''}{tv_growth}%\n"
                )

                # Add available metrics
                if tv_retention:
                    direct_response += f"- Avg View Percentage: {round(tv_retention, 1)}%\n"
                if tv_ctr:
                    direct_response += f"- CTR: {round(tv_ctr, 1)}%\n"
                if tv_impressions:
                    direct_response += f"- Impressions: {int(tv_impressions):,}\n"

                direct_response += f"\n{video_diagnosis_block}"

                logger.info(f"[VideoDiagnosisBypass] Returning pre-computed video diagnosis directly — NO LLM call")
                return direct_response

            # Fallback: if diagnosis couldn't be computed, use LLM
            instructions_block = (
                "Instructions:\n"
                "- Follow the top video analysis template EXACTLY\n"
                "- Use ONLY the video metrics provided above\n"
                "- Do NOT mention video IDs or internal metadata\n"
                "- Do NOT echo the user's prompt back to them\n"
                "- Do NOT use markdown tables or raw JSON\n"
                "- Do NOT compare to channel-wide stats\n"
                "- Do NOT generate strategy suggestions\n"
                "- Keep response under 150 words"
            )

            full_prompt = f"""
{system_prompt}

{top_video_prompt}

{video_metrics_section}

Context:
{full_context}

User message: {clean_message}

{instructions_block}
"""
        else:
            # --- STANDARD ANALYSIS PATH ---
            # Detect content strategy queries
            is_content_strategy = self._is_content_strategy_query(
                clean_message, plan.intent_classification
            )

            # Detect pattern intelligence queries
            is_pattern_query = self._is_pattern_query(
                clean_message, plan.intent_classification
            )

            # Build analysis section — include full template for content strategy queries
            analysis_section_prompt = ""
            if analysis_prompt:
                if is_content_strategy:
                    analysis_section_prompt = f"\n{analysis_prompt}\n"
                else:
                    # Include only benchmarks and partial data rules for non-strategy queries
                    analysis_section_prompt = f"\n{analysis_prompt}\n"

            # Build intent-appropriate instructions
            # Detect query sub-type for analytics intents
            is_growth_query = self._is_growth_query(
                clean_message, plan.intent_classification
            )

            if plan.intent_classification == "pattern_analysis":
                instructions_block = """You are the Pattern Intelligence Engine.

STRICT RULES:
- DO NOT generate strategy
- DO NOT generate video ideas
- DO NOT generate hook scripts
- DO NOT generate thumbnail advice
- DO NOT generate success metrics
- DO NOT suggest what to scale
- DO NOT suggest what to improve
- DO NOT give growth recommendations

Only return:
1. Top Performing Theme (by median views)
2. Underperforming Theme
3. Format Bias (Shorts vs Standard)
4. Retention Bias (if applicable)

Output format:

**Pattern Intelligence**

Top Performing Theme: <copy from PATTERN INTELLIGENCE>
Median Views: <copy from PATTERN INTELLIGENCE>

Underperforming Theme: <copy from PATTERN INTELLIGENCE>
Median Views: <copy from PATTERN INTELLIGENCE>

Format Bias:
Shorts Median Views: <copy from PATTERN INTELLIGENCE>
Standard Median Views: <copy from PATTERN INTELLIGENCE>

Keep response analytical and neutral.
No paragraphs.
No advice.
No emoji.
No markdown tables.
No raw JSON.
No summary paragraph. No closing question. No call-to-action.
End after the Pattern Intelligence section. Do NOT add anything after it."""
            elif plan.intent_classification in analytics_intents:
                if plan.intent_classification == "compare_videos":
                    instructions_block = """Instructions:
- The user wants to COMPARE two videos side-by-side.
- Use ONLY the data from the VIDEO LIBRARY section for both videos.
- Compare the two videos on: views, likes, comments, engagement (likes+comments/views), and published date.
- State clearly which video performed better on each metric.
- Give ONE actionable insight: what made the better-performing video work, and how to apply it to future content.
- Do NOT reference channel-wide averages, subscriber totals, or other videos not named.
- Do NOT suggest comparing more than the 2 requested videos.
- No markdown tables. No raw JSON. No emoji.
- Tone: data-driven advisor comparing two experiments."""
                elif is_pattern_query and plan.intent_classification in ("video_analysis", "channel_analysis", "general_analytics"):
                    instructions_block = """You are a Pattern Intelligence Engine.
Your output MUST follow this EXACT structure with no deviations.

---

**Pattern Intelligence**

Top Performing Theme: <copy from PATTERN INTELLIGENCE>
Median Views: <copy from PATTERN INTELLIGENCE>

Underperforming Theme: <copy from PATTERN INTELLIGENCE>
Median Views: <copy from PATTERN INTELLIGENCE>

Format Bias:
Shorts Median Views: <copy from PATTERN INTELLIGENCE>
Standard Median Views: <copy from PATTERN INTELLIGENCE>

[PATTERN INTELLIGENCE — RULES]
- Use the Pattern Intelligence section exactly as provided.
- Do not invent themes.
- Do not provide emotional reasoning.
- Do not give content ideas unless explicitly requested.
- Do not add Diagnostics or Strategy sections.
- Do not recompute themes or format biases.
- Do not use emojis.
- Keep professional tone.
- Keep concise.
- No summary paragraph. No closing question. No call-to-action.
- End after the Pattern Intelligence section. Do not add anything after it.

[OUTPUT BOUNDARIES]
Do not:
- Hallucinate themes or format biases not in the data
- Add motivational language or encouragement
- Use phrases: "you should", "consider doing", "to improve", "I recommend"
- Add any sections beyond Pattern Intelligence"""
                elif plan.intent_classification == "video_analysis":
                    instructions_block = """You are a Video Performance Diagnostic and Strategy Engine.
Your output MUST follow this EXACT structure with no deviations.

---

**Video Health Overview**

- Performance Tier: <copy exact value from VIDEO DIAGNOSTICS>
- Percentile Rank: <copy exact percentile text from VIDEO DIAGNOSTICS — do NOT rephrase or invert>
- Retention Category: <copy exact value from VIDEO DIAGNOSTICS>
- Momentum Status: <copy exact value from VIDEO DIAGNOSTICS>
- Format Type: <copy exact value from VIDEO DIAGNOSTICS>

**Diagnostic Interpretation**

Exactly 2 paragraphs. No more.

Paragraph 1 — Performance position (2–3 sentences):
Synthesize Performance Tier + Percentile Rank. Explain where this video sits relative to the channel's content library. Reference the percentile value naturally without repeating the label.

Paragraph 2 — Engagement and distribution (2–3 sentences):
Synthesize Retention Category + Momentum Status + Format Type. Explain what the retention pattern and momentum signal about algorithmic distribution, factoring in format expectations.

**Strategic Direction**

Strategy Mode: <copy exact value from STRATEGY FRAMEWORK>
Risk Level: <copy exact value from STRATEGY FRAMEWORK>
Primary Focus: <copy exact value from STRATEGY FRAMEWORK>
Secondary Focus: <copy exact value from STRATEGY FRAMEWORK>

Copy all four values exactly as provided. Do NOT reinterpret, recompute, or add additional focus areas. Do NOT prepend hyphens or bullets.

**High-Impact Actions**

List the Recommended Actions from the STRATEGY FRAMEWORK section as a numbered list. Copy them exactly — do NOT rephrase, add, or remove any.

**Execution Pattern**

Copy the Execution Pattern text from the STRATEGY FRAMEWORK section as a single paragraph. Do NOT modify it.

**Pattern Intelligence**

Top Performing Theme: <copy from PATTERN INTELLIGENCE>
Underperforming Theme: <copy from PATTERN INTELLIGENCE>

Format Bias:
Shorts Median Views: <copy from PATTERN INTELLIGENCE>
Standard Median Views: <copy from PATTERN INTELLIGENCE>

[TONE GUIDELINES]
- Use neutral, product-grade vocabulary: "indicates", "suggests", "signals", "reflects", "positions the video"
- Do not use emotional or dramatic language: "significant disconnect", "risks being overlooked", "challenging landscape", "critical", "compounds the issue", "unfortunately", "struggles"
- Do not use subjective adjectives: "impressive", "concerning", "disappointing", "remarkable"
- Do not repeat the percentile explanation more than once
- Tone: SaaS analytics product — clean, neutral, factual

[SCOPE ISOLATION — STRATEGY ENGINE]
- Use the structured strategy fields from STRATEGY FRAMEWORK directly.
- Do NOT recompute strategy — it is pre-computed.
- Do NOT restate percentile numbers in the strategy sections.
- Do NOT repeat retention explanation in strategy sections.
- Do NOT include subscriber totals or channel-wide averages.
- Keep strategy sections concise and verbatim.

[STRICT RULES]
- Use the EXACT bold headings shown above. No other headings.
- Always include ALL five diagnostic fields in the exact order shown.
- Copy diagnostic and strategy values WORD FOR WORD from the provided sections.
- Do NOT invert percentile values. If diagnostics say "outperformed 0%", write "outperformed 0%" — NEVER restate as "top 100%".
- Do not recompute any fields from raw numbers.
- If a field is Unknown, state it is unavailable — do not infer or estimate.
- No emoji. No markdown tables. No raw JSON.
- No summary paragraph. No closing question. No call-to-action.
- End after the Pattern Intelligence section. Do not add anything after it.

[OUTPUT BOUNDARIES]
Do not:
- Hallucinate CTR, subscriber totals, or view counts not in the diagnostics
- Mix channel-level analytics into video-level analysis
- Recompute or invent missing themes or format biases
- Ask follow-up questions (e.g. "Would you like...")
- Add motivational language or encouragement
- Use phrases: "you should", "consider doing", "to improve", "I recommend"
- Add any sections beyond the six specified above"""
                elif is_content_strategy:
                    instructions_block = """Instructions:
- The user is asking a CONTENT STRATEGY question.
- Use ONLY the Next Video Blueprint section provided above to answer.
- Translate each blueprint field into a clear creator-friendly explanation.
- Respond with these sections only: Strategic Direction, Next Upload Focus, Opening, Structure, Action Step.
- Each section should be 1-2 sentences translating the corresponding blueprint field.
- Do not invent video titles, hook scripts, thumbnail concepts, or hypothetical video ideas.
- Do not introduce metrics or numbers not present in the data.
- Do not use phrases like "Top 5", "You Won't Believe", or any clickbait examples.
- No markdown tables. No raw JSON. No emoji.
- Tone: strategic advisor translating a performance blueprint into practical guidance."""
                elif is_growth_query:
                    instructions_block = """Format this cleanly.
Describe the channel's current growth challenge in plain language. Do not use internal classification labels.
Then output the strategy ranking section exactly as provided.
No additional commentary. No expansion. No motivational content. No examples.
Stop after Confidence line."""
                else:
                    instructions_block = """Format this cleanly.
Describe the channel's current growth challenge in plain language. Do not use internal classification labels.
Then output the strategy ranking section exactly as provided.
No additional commentary. No expansion. No motivational content. No examples.
Stop after Confidence line."""
            else:
                # If archetype context is available, use minimal formatting
                if archetype_section:
                    instructions_block = """Format this cleanly.
Describe the channel's current growth challenge in plain language. Do not use internal classification labels.
Then output the strategy ranking section exactly as provided.
No additional commentary. No expansion. No motivational content. No examples.
Stop after Confidence line."""
                else:
                    instructions_block = """Instructions:
- Answer the user's question directly and confidently.
- If the user asks about video performance (most watched, most liked, best performing, recent videos), ALWAYS use the VIDEO LIBRARY section above — it contains title, date, views, likes, and comments for all stored videos.
- To answer "most watched in last X days": look at the VIDEO LIBRARY, filter by published date, and rank by views. State the answer directly.
- If the user asks about subscribers, views, or basic channel stats, quote the exact number from the analytics data.
- Do NOT say you don't have the data if it appears in VIDEO LIBRARY or Context.
- Do NOT provide a full analytics diagnosis or bottleneck analysis.
- Do NOT mention tools or data sources.
- Keep the response short, friendly, and direct.
- Do NOT use emoji.

[SCOPE ISOLATION — CHANNEL SUMMARY]
Forbidden in channel-level responses:
- Do NOT include per-video analytics (engagement rate, avg watch time per video, or likes per video) unless the user explicitly asked about a specific video.
- Do NOT reference individual video IDs or specific video performance metrics in a channel summary."""

        # ──────────────────────────────────────────────
        # LLM BYPASS — Strategy Ranking Engine
        # If we have a pre-computed strategy ranking AND this is a
        # strategy/growth/insight query, return directly. No LLM.
        # ──────────────────────────────────────────────
        if strategy_ranking_section and not is_top_video:
            # Only bypass for strategy-relevant queries (not video_analysis, not content_strategy)
            is_strategy_bypass = (
                is_growth_query
                or plan.intent_classification in ("insight", "analytics")
            ) and not is_content_strategy

            if is_strategy_bypass:
                # Scope guard: enforce channel scope before strategy rendering
                sg = ScopeGuardLayer()
                sg_scope = sg.determine_scope(plan.intent_classification)
                if sg_scope != "channel":
                    logger.warning(f"[ScopeGuard] Strategy bypass blocked: scope={sg_scope} (expected channel)")
                # Build direct output — no LLM
                archetype_opening = ""
                if archetype_section and hasattr(self, '_last_archetype'):
                    a = self._last_archetype
                    archetype_opening = self._translate_archetype(a) + "\n\n"

                direct_response = f"{archetype_opening}## Strategy Ranking\n\n{strategy_ranking_section}"
                logger.info(f"[StrategyBypass] Returning pre-computed ranking directly — NO LLM call")
                return direct_response

        # ──────────────────────────────────────────────
        # LLM BYPASS — Content Strategy with Blueprint
        # If blueprint is available for content strategy queries, return directly.
        # ──────────────────────────────────────────────
        if is_content_strategy and next_video_blueprint_section and strategy_ranking_section:
            archetype_opening = ""
            if archetype_section and hasattr(self, '_last_archetype'):
                a = self._last_archetype
                archetype_opening = self._translate_archetype(a) + "\n\n"
            diag_block = ""
            if retention_diagnosis_section:
                diag_block = f"\n\n{retention_diagnosis_section}"
            direct_response = f"{archetype_opening}## Strategy Ranking\n\n{strategy_ranking_section}\n{next_video_blueprint_section}{diag_block}"
            logger.info(f"[ContentStrategyBypass] Returning blueprint + ranking directly — NO LLM call")
            return direct_response

        # ──────────────────────────────────────────────
        # Standard LLM path (non-strategy queries)
        # ──────────────────────────────────────────────

        full_prompt = f"""
{system_prompt}

{analysis_section_prompt}

{analytics_section}

{video_analytics_section}

{diagnostics_section}

{pattern_section}

{archetype_section}

{strategy_ranking_section}

{next_video_blueprint_section}

{retention_diagnosis_section}

{video_library_section}

Context:
{full_context}

User message: {clean_message}

{instructions_block}
"""

        # Prompt size guardrail
        if len(full_prompt) > 15000:
            logger.warning(f"Prompt too large ({len(full_prompt)} chars) — compressing")
            lines = full_prompt.split("\n")
            filtered = [
                line for line in lines
                if not line.strip().startswith("Video Library:")
                and not line.strip().startswith("- Video:")
            ]
            full_prompt = "\n".join(filtered[:400])  # hard cap at 400 lines
            logger.info(f"Compressed prompt to {len(full_prompt)} chars")

        # Call LLM
        response = await self._invoke_llm(full_prompt)

        return response

    def _merge_tool_analytics(
        self,
        analytics_context: dict[str, Any],
        tool_results: list[ToolResult]
    ) -> dict[str, Any]:
        """
        Merge fresh analytics from tool results into analytics context.

        When fetch_analytics returns live data, ALWAYS use it to build
        the analytics context and availability flags — regardless of
        whether the DB already had a snapshot. The live data from the
        current request is always more authoritative than stale DB data.

        Args:
            analytics_context: Context from AnalyticsContextBuilder (may be empty/stale).
            tool_results: Results from tool execution.

        Returns:
            Updated analytics context with live data merged in.
        """
        # Find fetch_analytics result with live data
        for result in tool_results:
            if result.tool_name == "fetch_analytics" and result.success:
                output = result.output
                if isinstance(output, dict) and output.get("data"):
                    data = output["data"]
                    if not data:
                        continue

                    # Always prefer fresh tool data over DB snapshot
                    impressions = data.get("impressions") or 0
                    analytics_context["current_period"] = {
                        "period": data.get("period", "last_7_days"),
                        "views": data.get("views", 0),
                        "subscribers_gained": data.get("subscribers", 0),
                        "avg_watch_time_minutes": data.get(
                            "avg_watch_time_minutes", 0.0
                        ),
                        "impressions": data.get("impressions"),
                        "ctr": data.get("avg_ctr"),
                        "avg_view_percentage": data.get("avg_view_percentage"),
                        "traffic_sources": data.get("traffic_sources"),
                    }

                    # Set availability flags from live data
                    analytics_context["has_ctr"] = impressions > 0
                    analytics_context["has_retention"] = (
                        data.get("avg_view_percentage") is not None
                    )
                    analytics_context["has_traffic_sources"] = bool(
                        data.get("traffic_sources")
                    )

                    # Merge 7d comparison data if available (dual-period fetch)
                    data_7d = output.get("data_7d")
                    if data_7d and isinstance(data_7d, dict):
                        analytics_context["period_7d"] = {
                            "period": data_7d.get("period", "last_7_days"),
                            "views": data_7d.get("views", 0),
                            "subscribers_gained": data_7d.get("subscribers", 0),
                            "avg_watch_time_minutes": data_7d.get(
                                "avg_watch_time_minutes", 0.0
                            ),
                            "impressions": data_7d.get("impressions"),
                            "ctr": data_7d.get("avg_ctr"),
                            "avg_view_percentage": data_7d.get("avg_view_percentage"),
                            "traffic_sources": data_7d.get("traffic_sources"),
                        }
                        logger.info(
                            f"Merged 7d comparison data: "
                            f"views_7d={data_7d.get('views')}, "
                            f"avg_view_%_7d={data_7d.get('avg_view_percentage')}"
                        )

                    logger.info(
                        f"Merged live analytics into context: "
                        f"has_ctr={analytics_context['has_ctr']}, "
                        f"has_retention={analytics_context['has_retention']}, "
                        f"has_traffic_sources={analytics_context['has_traffic_sources']}"
                    )
                    break

        return analytics_context

    def _build_analytics_prompt_section(
        self,
        analytics_context: dict[str, Any]
    ) -> str:
        """
        Build the structured analytics section for the LLM prompt.

        Args:
            analytics_context: Dictionary with current_period, previous_period data,
                             and availability flags (has_ctr, has_retention, has_traffic_sources).

        Returns:
            Formatted analytics section string with availability status.
        """
        lines = []
        
        # Always include availability flags first (required by prompt rules)
        has_ctr = analytics_context.get("has_ctr", False)
        has_retention = analytics_context.get("has_retention", False)
        has_traffic_sources = analytics_context.get("has_traffic_sources", False)
        
        lines.append("ANALYTICS AVAILABILITY STATUS:")
        lines.append(f"- CTR available: {has_ctr}")
        lines.append(f"- Audience retention available: {has_retention}")
        lines.append(f"- Traffic source data available: {has_traffic_sources}")
        lines.append("")
        
        current = analytics_context.get("current_period")
        if not current:
            lines.append("## STRUCTURED ANALYTICS DATA")
            lines.append("")
            lines.append("No analytics data available for this channel.")
            return "\n".join(lines)

        lines.append("## STRUCTURED ANALYTICS DATA (USE THESE EXACT NUMBERS)")

        # Current period
        lines.append(f"\nCurrent Period ({current.get('period', 'last_7_days')}):")
        lines.append(f"- Views: {current.get('views', 0):,}")
        lines.append(f"- Subscribers gained: {current.get('subscribers_gained', 0):,}")
        
        # Extended metrics (only if available)
        if current.get('impressions') is not None:
            lines.append(f"- Impressions: {current.get('impressions'):,}")
        
        if current.get('ctr') is not None:
            ctr_pct = current['ctr'] * 100 if current['ctr'] < 1 else current['ctr']
            lines.append(f"- CTR: {ctr_pct:.1f}%")
        
        lines.append(f"- Avg watch time: {current.get('avg_watch_time_minutes', 0):.1f} minutes")
        
        if current.get('avg_view_percentage') is not None:
            lines.append(f"- Avg view percentage: {current.get('avg_view_percentage'):.1f}%")
        
        # Traffic sources (only if available)
        if has_traffic_sources and current.get('traffic_sources'):
            lines.append("\nTraffic Sources:")
            traffic = current['traffic_sources']
            total_traffic = sum(traffic.values()) if traffic else 0
            if total_traffic > 0:
                sorted_sources = sorted(traffic.items(), key=lambda x: x[1], reverse=True)
                for source, views in sorted_sources[:5]:
                    pct = (views / total_traffic) * 100
                    lines.append(f"- {source}: {pct:.0f}%")

        # Previous period
        previous = analytics_context.get("previous_period")
        if previous:
            lines.append(f"\nPrevious Period ({previous.get('period', 'previous_7_days')}):")
            lines.append(f"- Views: {previous.get('views', 0):,}")
            lines.append(f"- Subscribers gained: {previous.get('subscribers_gained', 0):,}")
            
            if previous.get('impressions') is not None:
                lines.append(f"- Impressions: {previous.get('impressions'):,}")
            
            if previous.get('ctr') is not None:
                ctr_pct = previous['ctr'] * 100 if previous['ctr'] < 1 else previous['ctr']
                lines.append(f"- CTR: {ctr_pct:.1f}%")
            
            lines.append(f"- Avg watch time: {previous.get('avg_watch_time_minutes', 0):.1f} minutes")

        # 7-day comparison period (for content strategy dual-period analysis)
        period_7d = analytics_context.get("period_7d")
        if period_7d:
            lines.append(f"\n7-Day Period ({period_7d.get('period', 'last_7_days')}):")
            lines.append(f"- Views: {period_7d.get('views', 0):,}")
            lines.append(f"- Subscribers gained: {period_7d.get('subscribers_gained', 0):,}")
            lines.append(f"- Avg watch time: {period_7d.get('avg_watch_time_minutes', 0):.1f} minutes")
            
            if period_7d.get('avg_view_percentage') is not None:
                lines.append(f"- Avg view percentage: {period_7d['avg_view_percentage']:.1f}%")
            
            # Compute and display deltas between 28d and 7d
            if current and period_7d:
                lines.append("\nPERIOD COMPARISON (7d vs 28d):")
                
                avp_28d = current.get('avg_view_percentage')
                avp_7d = period_7d.get('avg_view_percentage')
                if avp_28d is not None and avp_7d is not None:
                    delta = avp_7d - avp_28d
                    direction = "+" if delta >= 0 else ""
                    lines.append(
                        f"- Avg view percentage: 28d={avp_28d:.1f}%, 7d={avp_7d:.1f}%, "
                        f"delta={direction}{delta:.2f}%"
                    )
                
                wt_28d = current.get('avg_watch_time_minutes', 0)
                wt_7d = period_7d.get('avg_watch_time_minutes', 0)
                if wt_28d > 0:
                    wt_delta = wt_7d - wt_28d
                    direction = "+" if wt_delta >= 0 else ""
                    lines.append(
                        f"- Avg watch time: 28d={wt_28d:.1f}min, 7d={wt_7d:.1f}min, "
                        f"delta={direction}{wt_delta:.1f}min"
                    )
                
                views_28d = current.get('views', 0)
                views_7d = period_7d.get('views', 0)
                if views_28d > 0:
                    # Normalize 28d views to 7d equivalent for fair comparison
                    views_28d_weekly = views_28d / 4
                    views_delta_pct = ((views_7d - views_28d_weekly) / views_28d_weekly) * 100
                    direction = "+" if views_delta_pct >= 0 else ""
                    lines.append(
                        f"- Views: 28d total={views_28d:,}, 7d total={views_7d:,}, "
                        f"7d vs weekly avg={direction}{views_delta_pct:.1f}%"
                    )

        return "\n".join(lines)

    def _build_video_analytics_prompt_section(
        self,
        tool_results: list[ToolResult]
    ) -> str:
        """
        Build the last video analytics section for the LLM prompt.

        Extracts video analytics from fetch_last_video_analytics tool results
        and formats them for the LLM.

        Args:
            tool_results: List of tool execution results.

        Returns:
            Formatted video analytics section string, or empty if not available.
        """
        # Find the fetch_last_video_analytics result
        video_data = None
        for result in tool_results:
            if result.tool_name == "fetch_last_video_analytics" and result.success:
                output = result.output
                if isinstance(output, dict) and output.get("data"):
                    video_data = output["data"]
                    break

        if not video_data:
            return ""

        # Handle Video Library (List of videos)
        if "library" in video_data:
            library = video_data["library"]
            if not library:
                return "## VIDEO LIBRARY\nNo recent videos found."
                
            lines = ["## VIDEO LIBRARY CONTEXT (Use to recommend next steps)"]
            lines.append("Recent videos performance:")
            
            for vid in library:
                title = vid.get("title", "Untitled")
                views = vid.get("views", 0)
                pub_date = vid.get("published_at", "")[:10]  # First 10 chars (YYYY-MM-DD)
                lines.append(f"- '{title}' ({pub_date}): {views:,} views")
                
            return "\n".join(lines)

        # Handle Single Video Analytics
        lines = ["## LAST VIDEO ANALYTICS (USE EXACT NUMBERS)"]
        
        # Video info
        lines.append(f"\nVideo: {video_data.get('title', 'Unknown')}")
        lines.append(f"Video ID: {video_data.get('video_id', 'N/A')}")
        lines.append(f"Published: {video_data.get('published_at', 'N/A')}")
        
        # Performance metrics
        lines.append("\nPerformance Metrics:")
        views = video_data.get('views', 0)
        lines.append(f"- Views: {views:,}")
        
        avg_watch_seconds = video_data.get('avg_watch_time_seconds', 0)
        avg_watch_minutes = avg_watch_seconds / 60 if avg_watch_seconds else 0
        lines.append(f"- Avg Watch Time: {avg_watch_minutes:.1f} minutes ({avg_watch_seconds:.0f} seconds)")
        
        engagement_rate = video_data.get('engagement_rate', 0)
        lines.append(f"- Engagement Rate: {engagement_rate:.2f}%")
        
        likes = video_data.get('likes', 0)
        comments = video_data.get('comments', 0)
        lines.append(f"- Likes: {likes:,}")
        lines.append(f"- Comments: {comments:,}")

        return "\n".join(lines)

    def _build_video_library_from_db(
        self,
        channel_uuid: Optional[UUID],
    ) -> str:
        """
        Build a video library context section from the DB videos table.

        Returns a formatted string listing all stored videos with their
        metrics (views, likes, comments, published_at) so the LLM can
        answer ranking/comparison queries like "most watched video".

        Args:
            channel_uuid: Channel UUID to query videos for.

        Returns:
            Formatted video library section, or empty string.
        """
        if not channel_uuid:
            return ""

        try:
            videos = self.postgres_store.get_recent_videos(
                channel_uuid, limit=50
            )
            if not videos:
                return ""

            lines = [
                "## VIDEO LIBRARY (from DB — use for ranking/comparison queries)",
                f"Total videos stored: {len(videos)}",
                "",
            ]
            for i, v in enumerate(videos, 1):
                pub = str(v.published_at)[:10] if v.published_at else "N/A"
                views = v.view_count or 0
                likes = v.like_count or 0
                comments = v.comment_count or 0
                lines.append(
                    f"{i}. \"{v.title}\" ({pub}) — "
                    f"{views:,} views, {likes:,} likes, "
                    f"{comments:,} comments"
                )

            logger.debug(
                f"[VideoLibrary] Injected {len(videos)} videos into LLM context"
            )
            return "\n".join(lines)

        except Exception as e:
            logger.warning(f"Failed to build video library context: {e}")
            return ""

    def _build_diagnostics_section(
        self,
        analytics_context: dict,
        tool_results: list,
        channel_uuid,
    ) -> str:
        """
        Compute deterministic diagnostic labels for a video_analysis prompt.

        Extracts available metrics from analytics_context and tool results,
        runs all diagnostic functions, and formats output as a structured
        block for the LLM to use directly without recalculation.

        Returns:
            Formatted diagnostics section string, or empty string on failure.
        """
        try:
            # --- Collect inputs ---
            current = analytics_context.get("current_period") or {}
            avg_view_pct = current.get("avg_view_percentage")
            traffic_sources = current.get("traffic_sources")

            # Pull video-specific fields from tool result
            video_views = None
            duration_seconds = None
            last_7_views = None
            prev_28_views = None

            for result in tool_results:
                if result.tool_name == "fetch_last_video_analytics" and result.success:
                    data = (result.output or {}).get("data", {})
                    if data and "library" not in data:
                        video_views = data.get("views")
                        # duration comes from DB; try to pull from tool output
                        duration_seconds = data.get("duration_seconds")
                        last_7_views = data.get("views")  # best proxy available
                    break

            # Channel video library for median / percentile
            channel_videos = []
            channel_view_counts = []
            try:
                channel_videos = self.postgres_store.get_recent_videos(
                    channel_uuid, limit=30
                )
                channel_view_counts = [
                    v.view_count for v in channel_videos
                    if v.view_count is not None
                ]
                # Pull duration_seconds from DB if not in tool result
                if duration_seconds is None and video_views is not None:
                    for v in channel_videos:
                        if v.view_count == video_views:
                            duration_seconds = v.duration_seconds
                            break
            except Exception as e:
                logger.warning(f"[Diagnostics] Could not load channel videos: {e}")

            # channel median
            median = compute_channel_median(channel_videos)
            median_views = median["median_views"]

            # Previous-28-day baseline: use median_views * 4 as proxy
            # (each of last 30 videos represents ~1 week of content)
            prev_28_estimate = (
                median_views * 4 if median_views else None
            )

            # --- Run diagnostics ---
            retention_category = classify_retention(avg_view_pct)
            percentile_rank = compute_percentile_rank(
                video_views or 0, channel_view_counts
            ) if channel_view_counts and video_views is not None else None
            performance_tier = compute_performance_tier(
                percentile_rank, retention_category
            )
            momentum_status = detect_momentum(last_7_views, prev_28_estimate)
            format_type = classify_format(duration_seconds, traffic_sources)

            # --- Format section ---
            lines = ["## VIDEO DIAGNOSTICS (pre-computed — COPY THESE VALUES EXACTLY, do not recalculate or rephrase)"]
            lines.append(f"- Performance Tier: {performance_tier}")
            lines.append(f"- Retention Category: {retention_category}"
                         + (f" ({avg_view_pct:.1f}% avg view)" if avg_view_pct is not None else ""))
            lines.append(f"- Momentum Status: {momentum_status}")
            lines.append(f"- Format Type: {format_type}")
            if percentile_rank is not None:
                # Include explicit human interpretation — prevent LLM inversion
                if percentile_rank >= 75:
                    rank_interpretation = "ABOVE most channel videos"
                elif percentile_rank >= 50:
                    rank_interpretation = "above the channel median"
                elif percentile_rank >= 25:
                    rank_interpretation = "below the channel median"
                else:
                    rank_interpretation = "BELOW most channel videos"
                lines.append(
                    f"- Percentile Rank: {percentile_rank:.0f}th percentile — "
                    f"this video outperformed {percentile_rank:.0f}% of channel videos "
                    f"({rank_interpretation})"
                )
            else:
                lines.append("- Percentile Rank: Unknown (insufficient channel data)")
            if median_views:
                lines.append(f"- Channel Median Views: {median_views:,}")

            # --- Strategy framework ---
            strategy = compute_strategy_framework(
                performance_tier, retention_category, momentum_status, format_type
            )
            lines.append("")
            lines.append("## STRATEGY FRAMEWORK (pre-computed — use directly, do not recalculate)")
            lines.append(f"- Strategy Mode: {strategy['strategy_mode']}")
            lines.append(f"- Primary Focus: {strategy['primary_focus']}")
            lines.append(f"- Secondary Focus: {strategy['secondary_focus']}")
            lines.append(f"- Risk Level: {strategy['risk_level']}")
            lines.append("- Recommended Actions:")
            for i, action in enumerate(strategy['recommended_actions'], 1):
                lines.append(f"  {i}. {action}")
            lines.append(f"- Execution Pattern: {strategy['execution_pattern']}")

            # --- Pattern Intelligence (Cross-Video) ---
            try:
                # Fetch videos directly from DB for pattern analysis
                pattern_videos_orm = self.postgres_store.get_recent_videos(
                    channel_uuid, limit=50
                )
                recent_videos = []
                for v in pattern_videos_orm:
                    recent_videos.append({
                        "title": v.title or "",
                        "views": v.view_count or 0,
                        "duration_seconds": v.duration_seconds or 0,
                        "format_type": "",
                    })

                clusters = cluster_by_keyword(recent_videos)
                top_theme, top_stats = detect_top_theme(clusters)
                worst_theme, worst_stats = detect_underperforming_theme(clusters)
                format_bias = detect_format_bias(recent_videos)

                lines.append("")
                lines.append("## PATTERN INTELLIGENCE (pre-computed — use directly)")
                if top_theme:
                    lines.append(f"- Top Performing Theme: '{top_theme}' (Median Views: {top_stats['median_views']:,})")
                else:
                    lines.append("- Top Performing Theme: Insufficient data")
                
                if worst_theme:
                    lines.append(f"- Underperforming Theme: '{worst_theme}' (Median Views: {worst_stats['median_views']:,})")
                else:
                    lines.append("- Underperforming Theme: Insufficient data")
                    
                lines.append("- Format Bias:")
                lines.append(f"  - Bias Type: {format_bias['bias']}")
                shorts_val = format_bias['shorts_median']
                standard_val = format_bias['standard_median']
                lines.append(f"  - Shorts Median Views: {shorts_val:,}" if shorts_val is not None else "  - Shorts Median Views: Insufficient data")
                lines.append(f"  - Standard Median Views: {standard_val:,}" if standard_val is not None else "  - Standard Median Views: Insufficient data")
                
            except Exception as pe:
                logger.warning(f"[Diagnostics] Failed to build pattern intelligence: {pe}")

            # --- Channel Archetype Classification (Phase 1.4) ---
            try:
                pattern_data = {
                    "shorts_median": format_bias.get("shorts_median") if 'format_bias' in dir() else None,
                    "standard_median": format_bias.get("standard_median") if 'format_bias' in dir() else None,
                    "top_median": top_stats["median_views"] if 'top_stats' in dir() and top_stats else None,
                    "second_median": worst_stats["median_views"] if 'worst_stats' in dir() and worst_stats else None,
                }
                diagnostics_data_for_arch = {
                    "momentum_status": momentum_status,
                    "percentile_distribution": [percentile_rank] if percentile_rank is not None else [],
                }
                channel_metrics_for_arch = self._build_channel_metrics(channel_uuid)
                archetype = ArchetypeAnalyzer().classify(
                    pattern_data=pattern_data,
                    diagnostics_data=diagnostics_data_for_arch,
                    channel_metrics=channel_metrics_for_arch,
                )
                lines.append("")
                lines.append("## CHANNEL IDENTITY (pre-computed — use directly)")
                lines.append(f"- Format Type: {archetype.format_type}")
                lines.append(f"- Theme Type: {archetype.theme_type}")
                lines.append(f"- Growth Constraint: {archetype.growth_constraint}")
                lines.append(f"- Performance Type: {archetype.performance_type}")
            except Exception as ae:
                logger.warning(f"[Diagnostics] Failed to build archetype: {ae}")

            logger.debug(
                f"[Diagnostics] tier={performance_tier}, retention={retention_category}, "
                f"momentum={momentum_status}, format={format_type}, "
                f"percentile={percentile_rank}, strategy_mode={strategy['strategy_mode']}"
            )
            return "\n".join(lines)

        except Exception as e:
            logger.warning(f"[Diagnostics] Failed to build section: {e}")
            return ""

    def _build_pattern_section(
        self,
        channel_uuid,
    ) -> str:
        """
        Build a standalone Pattern Intelligence section from video library.

        Used exclusively for pattern_analysis intent — does NOT call
        diagnostics or strategy. Pure pattern extraction only.

        Returns:
            Formatted pattern intelligence section string, or empty string on failure.
        """
        try:
            videos_orm = self.postgres_store.get_recent_videos(
                channel_uuid, limit=50
            )
            if not videos_orm:
                return ""

            recent_videos = []
            for v in videos_orm:
                recent_videos.append({
                    "title": v.title or "",
                    "views": v.view_count or 0,
                    "duration_seconds": v.duration_seconds or 0,
                    "format_type": "",
                })

            clusters = cluster_by_keyword(recent_videos)
            top_theme, top_stats = detect_top_theme(clusters)
            worst_theme, worst_stats = detect_underperforming_theme(clusters)
            format_bias = detect_format_bias(recent_videos)

            lines = ["## PATTERN INTELLIGENCE (pre-computed — use directly, do not recompute)"]
            if top_theme:
                lines.append(f"- Top Performing Theme: '{top_theme}' (Median Views: {top_stats['median_views']:,})")
            else:
                lines.append("- Top Performing Theme: Insufficient data")

            if worst_theme:
                lines.append(f"- Underperforming Theme: '{worst_theme}' (Median Views: {worst_stats['median_views']:,})")
            else:
                lines.append("- Underperforming Theme: Insufficient data")

            lines.append("- Format Bias:")
            lines.append(f"  - Bias Type: {format_bias['bias']}")
            shorts_val = format_bias['shorts_median']
            standard_val = format_bias['standard_median']
            lines.append(f"  - Shorts Median Views: {shorts_val:,}" if shorts_val is not None else "  - Shorts Median Views: Insufficient data")
            lines.append(f"  - Standard Median Views: {standard_val:,}" if standard_val is not None else "  - Standard Median Views: Insufficient data")

            # --- Channel Archetype Classification (Phase 1.4) ---
            try:
                # Build pattern_data from computed signals
                pattern_data = {
                    "shorts_median": format_bias.get("shorts_median"),
                    "standard_median": format_bias.get("standard_median"),
                    "top_median": top_stats["median_views"] if top_stats else None,
                    "second_median": worst_stats["median_views"] if worst_stats else None,
                }
                # Fetch channel-level metrics from latest analytics snapshot
                diagnostics_data_for_arch = {
                    "momentum_status": None,
                    "percentile_distribution": [
                        compute_percentile_rank(v.get("views", 0), [vid.get("views", 0) for vid in recent_videos])
                        for v in recent_videos if v.get("views") is not None
                    ],
                }
                channel_metrics_for_arch = self._build_channel_metrics(channel_uuid)

                archetype = ArchetypeAnalyzer().classify(
                    pattern_data=pattern_data,
                    diagnostics_data=diagnostics_data_for_arch,
                    channel_metrics=channel_metrics_for_arch,
                )
                lines.append("")
                lines.append("## CHANNEL IDENTITY (pre-computed — use directly)")
                lines.append(f"- Format Type: {archetype.format_type}")
                lines.append(f"- Theme Type: {archetype.theme_type}")
                lines.append(f"- Growth Constraint: {archetype.growth_constraint}")
                lines.append(f"- Performance Type: {archetype.performance_type}")
            except Exception as ae:
                logger.warning(f"[PatternIntelligence] Failed to build archetype: {ae}")

            logger.debug(
                f"[PatternIntelligence] top_theme={top_theme}, worst_theme={worst_theme}, "
                f"bias={format_bias['bias']}"
            )
            return "\n".join(lines)

        except Exception as e:
            logger.warning(f"[PatternIntelligence] Failed to build section: {e}")
            return ""

    def _is_identity_query(self, message: str) -> bool:
        """
        Check if the user's message is an identity/archetype query.

        Returns True if any IDENTITY_PATTERNS match.
        """
        for pattern in self.IDENTITY_PATTERNS:
            if re.search(pattern, message, re.IGNORECASE):
                return True
        return False

    def _is_conversational_name_query(self, message: str) -> bool:
        """Check if user is asking about their name/channel name."""
        lower = message.lower().strip()
        for pattern in self.CONVERSATIONAL_NAME_PATTERNS:
            if re.search(pattern, lower):
                return True
        return False

    def _compute_and_render_archetype(self, channel_uuid) -> Optional[str]:
        """
        Compute channel archetype and render as deterministic text block.

        Fetches videos and analytics snapshot from DB, runs all classifiers,
        and returns a formatted archetype block. No LLM involved.

        Returns:
            Formatted archetype string, or None on failure.
        """
        # Fetch videos for pattern data
        videos_orm = self.postgres_store.get_recent_videos(
            channel_uuid, limit=50
        )
        if not videos_orm:
            return None

        recent_videos = []
        for v in videos_orm:
            recent_videos.append({
                "title": v.title or "",
                "views": v.view_count or 0,
                "duration_seconds": v.duration_seconds or 0,
                "format_type": "",
            })

        # Compute pattern signals
        clusters = cluster_by_keyword(recent_videos)
        top_theme, top_stats = detect_top_theme(clusters)
        worst_theme, worst_stats = detect_underperforming_theme(clusters)
        format_bias = detect_format_bias(recent_videos)

        # Build pattern_data for archetype
        pattern_data = {
            "shorts_median": format_bias.get("shorts_median"),
            "standard_median": format_bias.get("standard_median"),
            "top_median": top_stats["median_views"] if top_stats else None,
            "second_median": worst_stats["median_views"] if worst_stats else None,
        }

        channel_metrics = self._build_channel_metrics(channel_uuid)
        diagnostics_data = {
            "momentum_status": None,
            "percentile_distribution": [
                compute_percentile_rank(v.get("views", 0), [vid.get("views", 0) for vid in recent_videos])
                for v in recent_videos if v.get("views") is not None
            ],
        }

        # Classify
        archetype = ArchetypeAnalyzer().classify(
            pattern_data=pattern_data,
            diagnostics_data=diagnostics_data,
            channel_metrics=channel_metrics,
        )

        # Render deterministic block
        return (
            f"**Channel Identity**\n\n"
            f"- **Format Type:** {archetype.format_type}\n"
            f"- **Theme Type:** {archetype.theme_type}\n"
            f"- **Growth Constraint:** {archetype.growth_constraint}\n"
            f"- **Performance Type:** {archetype.performance_type}"
        )

    def _build_channel_metrics(self, channel_uuid) -> dict:
        """
        Build channel metrics from latest analytics snapshot.

        Single source of truth for retention and conversion.
        Always uses snapshot (stable) — not live per-request analytics.
        """
        channel_metrics = {
            "avg_view_pct": 0,
            "sub_conversion_rate": 0,
        }
        try:
            snapshot = self.postgres_store.get_latest_analytics_snapshot(channel_uuid)
            if snapshot:
                channel_metrics["avg_view_pct"] = snapshot.avg_view_percentage or 0
                # Compute sub_conversion_rate if data available
                if hasattr(snapshot, 'subscribers_gained') and hasattr(snapshot, 'views'):
                    views = snapshot.views or 0
                    subs = snapshot.subscribers_gained or 0
                    if views > 0:
                        channel_metrics["sub_conversion_rate"] = round(subs / views, 4)
        except Exception as e:
            logger.warning(f"Failed to fetch channel metrics from snapshot: {e}")
        return channel_metrics

    def _compute_archetype(self, channel_uuid):
        """
        Compute channel archetype from DB data.

        Returns a ChannelArchetype object, or None on failure.
        """
        # Fetch videos for pattern data
        videos_orm = self.postgres_store.get_recent_videos(
            channel_uuid, limit=50
        )
        if not videos_orm:
            return None

        recent_videos = []
        for v in videos_orm:
            recent_videos.append({
                "title": v.title or "",
                "views": v.view_count or 0,
                "duration_seconds": v.duration_seconds or 0,
                "format_type": "",
            })

        clusters = cluster_by_keyword(recent_videos)
        top_theme, top_stats = detect_top_theme(clusters)
        worst_theme, worst_stats = detect_underperforming_theme(clusters)
        format_bias = detect_format_bias(recent_videos)

        pattern_data = {
            "shorts_median": format_bias.get("shorts_median"),
            "standard_median": format_bias.get("standard_median"),
            "top_median": top_stats["median_views"] if top_stats else None,
            "second_median": worst_stats["median_views"] if worst_stats else None,
        }

        channel_metrics = self._build_channel_metrics(channel_uuid)
        diagnostics_data = {
            "momentum_status": None,
            "percentile_distribution": [
                compute_percentile_rank(v.get("views", 0), [vid.get("views", 0) for vid in recent_videos])
                for v in recent_videos if v.get("views") is not None
            ],
        }

        return ArchetypeAnalyzer().classify(
            pattern_data=pattern_data,
            diagnostics_data=diagnostics_data,
            channel_metrics=channel_metrics,
        )

    @staticmethod
    def _render_structural_response(archetype, message: str) -> str:
        """
        Render a context-sensitive structural response from an archetype.

        No LLM. No narrative. Pure structural output.
        """
        msg = message.lower()

        # Library-specific query
        if "library" in msg:
            return (
                f"**Library Performance Status**\n\n"
                f"- **Performance Type:** {archetype.performance_type}"
            )

        # Weakness-specific query
        if "weakness" in msg:
            weaknesses = []

            if archetype.theme_type == "Theme-Concentrated":
                weaknesses.append("Theme concentration risk")

            if "Dominant" in archetype.format_type:
                weaknesses.append("Format dependency risk")

            if archetype.growth_constraint == "Retention-Constrained":
                weaknesses.append("Retention constraint")

            if archetype.performance_type == "Underperforming Library":
                weaknesses.append("Library performance weakness")

            if not weaknesses:
                weaknesses.append("No structural weakness detected")

            bullet_lines = "\n".join(f"- {w}" for w in weaknesses)
            return f"**Structural Weakness**\n\n{bullet_lines}"

        # Default: full identity block
        return (
            f"**Channel Identity**\n\n"
            f"- **Format Type:** {archetype.format_type}\n"
            f"- **Theme Type:** {archetype.theme_type}\n"
            f"- **Growth Constraint:** {archetype.growth_constraint}\n"
            f"- **Performance Type:** {archetype.performance_type}"
        )


    async def _invoke_llm(self, prompt: str) -> str:
        """
        Invoke the configured LLM provider.

        Delegates to the active LLM client (Azure OpenAI or Gemini)
        based on config.llm.provider.

        Args:
            prompt: Full prompt to send to LLM

        Returns:
            LLM response string
        """
        logger.info(f"LLM invocation using provider={config.llm.provider}")

        return self.llm_client.generate(prompt)

    def _build_structured_data(
        self,
        tool_results: list[ToolResult]
    ) -> Optional[dict[str, Any]]:
        """
        Build structured analytics data from tool results.

        Extracts analytics metrics from fetch_analytics tool output
        and returns them as a clean dict for the structured_data response field.

        Args:
            tool_results: List of tool execution results

        Returns:
            Dict with analytics data, or None if no analytics available.
        """
        # Find the fetch_analytics result
        analytics_output = None
        for result in tool_results:
            if result.tool_name == "fetch_analytics" and result.success and result.output:
                analytics_output = result.output
                break

        if not analytics_output:
            return None

        current = analytics_output.get("current_period")
        if not current:
            return None

        structured: dict[str, Any] = {
            "period": current.get("period", "last_28_days"),
            "views": current.get("views", 0),
            "subscribers_gained": current.get("subscribers_gained", 0),
            "avg_view_percentage": current.get("avg_view_percentage"),
            "avg_watch_time_minutes": current.get("avg_watch_time_minutes", 0),
        }

        # Traffic sources
        traffic = current.get("traffic_sources")
        if traffic and isinstance(traffic, dict):
            total = sum(traffic.values())
            if total > 0:
                sources = []
                for source, views in sorted(
                    traffic.items(), key=lambda x: x[1], reverse=True
                )[:5]:
                    sources.append({
                        "name": source,
                        "views": views,
                        "percentage": round((views / total) * 100, 1)
                    })
                structured["traffic_sources"] = sources

        # 7d comparison data
        period_7d = analytics_output.get("period_7d")
        if period_7d and isinstance(period_7d, dict):
            comparison: dict[str, Any] = {
                "period": "last_7_days",
                "views": period_7d.get("views", 0),
                "avg_view_percentage": period_7d.get("avg_view_percentage"),
                "avg_watch_time_minutes": period_7d.get("avg_watch_time_minutes", 0),
            }
            avp_28d = current.get("avg_view_percentage")
            avp_7d = period_7d.get("avg_view_percentage")
            if avp_28d is not None and avp_7d is not None:
                comparison["avg_view_percentage_delta"] = round(avp_7d - avp_28d, 2)

            wt_28d = current.get("avg_watch_time_minutes", 0)
            wt_7d = period_7d.get("avg_watch_time_minutes", 0)
            if wt_28d > 0:
                comparison["avg_watch_time_delta"] = round(wt_7d - wt_28d, 2)

            structured["comparison_7d"] = comparison

        return structured

    def _translate_archetype(self, archetype: dict) -> str:
        """
        Translate internal archetype labels into creator-friendly language.

        Internal labels like Theme-Concentrated or Retention-Constrained
        are diagnostic terms that should not appear in user-facing responses.
        """
        constraint_translations = {
            "Retention-Constrained": "Your channel is currently struggling to keep viewers watching through the video.",
            "Conversion-Constrained": "Your channel receives views but converts very few viewers into subscribers.",
            "CTR-Constrained": "Your channel struggles to attract clicks from impressions.",
            "Shorts-Dominant": "Your channel relies heavily on Shorts, which limits longer-form growth.",
            "Growth-Stalled": "Your channel growth has plateaued and needs a strategic shift.",
        }

        theme_translations = {
            "Theme-Concentrated": "focused on a single content theme",
            "Theme-Diverse": "exploring multiple content themes",
            "Theme-Emerging": "still establishing a content direction",
        }

        growth_constraint = archetype.get("growth_constraint", "")
        theme_type = archetype.get("theme_type", "")

        # Use constraint translation if available
        if growth_constraint in constraint_translations:
            return constraint_translations[growth_constraint]

        # Fallback: build from parts without internal labels
        theme_desc = theme_translations.get(theme_type, "")
        if theme_desc and growth_constraint:
            # Generic fallback for unknown constraint
            return f"Your channel is {theme_desc} and facing growth challenges."
        elif growth_constraint:
            return f"Your channel is currently facing {growth_constraint.lower().replace('-', ' ')} challenges."
        elif theme_desc:
            return f"Your channel is {theme_desc}."

        return "Your channel is facing growth challenges that require strategic focus."

    def _is_content_strategy_query(
        self, message: str, intent: str
    ) -> bool:
        """
        Detect if the user is asking a content strategy question.

        Args:
            message: User's input message
            intent: Classified intent from planner

        Returns:
            True if this is a content strategy / "what to upload" query
        """
        import re
        msg_lower = message.lower()
        strategy_patterns = [
            r"\b(what|which).*(upload|post|make|create|content)\b",
            r"\b(next|future).*(video|topic|idea|content)\b",
            r"\bcontent strategy\b",
            r"\bwhat should i (upload|post|make|film|record)\b",
            r"\bvideo idea\b",
            r"\bwhat.*work(ing|ed)\b",
        ]
        return any(re.search(p, msg_lower) for p in strategy_patterns)

    def _is_growth_query(
        self, message: str, intent: str
    ) -> bool:
        """
        Detect if the user is asking a growth / improvement question.

        Args:
            message: User's input message
            intent: Classified intent from planner

        Returns:
            True if this is a growth-oriented query like "How can I grow?"
        """
        import re
        msg_lower = message.lower()
        growth_patterns = [
            r"\b(how).*(grow|scale|expand|blow up|take off)\b",
            r"\b(grow|increase|boost)\s+(my\s+)?(channel|subscribers|views|audience)\b",
            r"\b(help me|how to|tips for).*(grow|improv|better|more views|more subs)\b",
            r"\bgrowth (strategy|plan|advice|tips)\b",
            r"\bgrow faster\b",
            r"\bget more (subscribers|views|watch time)\b",
            r"\bscale my (channel|content)\b",
        ]
        return any(re.search(p, msg_lower) for p in growth_patterns)

    def _is_pattern_query(
        self, message: str, intent: str
    ) -> bool:
        """
        Detect if the user is asking about cross-video patterns, themes, or format bias.

        Args:
            message: User's input message
            intent: Classified intent from planner

        Returns:
            True if this is a pattern/theme query
        """
        import re
        msg_lower = message.lower()
        pattern_keywords = [
            r"\btheme\b",
            r"\bpattern\b",
            r"\bacross videos\b",
            r"\busually\b",
            r"\btends? to\b",
            r"\btype of content\b",
            r"\bformat bias\b",
            r"\b(what|which).*(theme|pattern|type|format).*(best|worst|perform|work)\b",
            r"\b(best|worst|top|underperform).*(theme|pattern|type|topic)\b",
            r"\bshorts vs\b",
            r"\bstandard vs\b",
        ]
        return any(re.search(p, msg_lower) for p in pattern_keywords)

    def _is_top_video_query(self, message: str) -> bool:
        """
        Detect if the message is a top-video analysis request.

        Args:
            message: User's input message (already cleaned of metadata)

        Returns:
            True if this is a top-video analysis query
        """
        import re
        msg_lower = message.lower()
        patterns = [
            r"\banalyze my top video\b",
            r"\btop video.*last \d+ days\b",
            r"\banalyze.*top.*(video|performer)\b",
            r"\bwhy.*top video.*(took off|performed)\b",
        ]
        return any(re.search(p, msg_lower) for p in patterns)

    def _parse_top_video_context(
        self, message: str
    ) -> tuple[str, dict | None]:
        """
        Extract and strip [TOP_VIDEO_CONTEXT] metadata from the message.

        The frontend appends a JSON block after [TOP_VIDEO_CONTEXT]
        which contains video metrics. This method extracts that data
        and returns the clean message without the marker.

        Args:
            message: Raw message potentially containing metadata marker

        Returns:
            Tuple of (clean_message, metadata_dict or None)
        """
        import json as json_mod

        marker = "[TOP_VIDEO_CONTEXT]"
        if marker not in message:
            return message, None

        parts = message.split(marker, 1)
        clean_message = parts[0].strip()

        try:
            metadata = json_mod.loads(parts[1].strip())
            logger.info(f"Parsed top video context: {metadata}")
            return clean_message, metadata
        except (json_mod.JSONDecodeError, IndexError) as e:
            logger.warning(f"Failed to parse top video context: {e}")
            return clean_message, None

    def _load_prompt(self, prompt_type: str) -> str:
        """
        Load a prompt template from the prompts directory.

        Args:
            prompt_type: Type of prompt ("system" or "analysis")

        Returns:
            Prompt template string
        """
        import os

        prompt_file = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "prompts",
            f"{prompt_type}.txt"
        )

        try:
            with open(prompt_file, "r") as f:
                return f.read().strip()
        except FileNotFoundError:
            logger.warning(f"Prompt file not found: {prompt_file}")
            return ""

    async def _store_conversation(
        self,
        user_id: str,
        channel_id: str,
        message: str,
        response: str,
        tools_used: list[str]
    ) -> None:
        """
        Store the conversation turn in short-term memory (Redis).

        Args:
            user_id: User identifier
            channel_id: Channel identifier
            message: User's message
            response: Generated response
            tools_used: List of tools that were executed
        """
        await self.redis_store.store_message(
            user_id=user_id,
            channel_id=channel_id,
            message=message,
            response=response,
            tools_used=tools_used
        )

    @staticmethod
    def _build_clarification_message(
        title_fragment: str,
        top_matches: list[dict],
    ) -> str:
        """
        Build a clarification response when video title cannot be resolved.

        Args:
            title_fragment: The user's original title fragment.
            top_matches: Top N candidates from the resolver.

        Returns:
            Human-readable clarification message.
        """
        msg = (
            f"I couldn't find an exact match for \"{title_fragment}\". "
        )

        if top_matches:
            msg += "Did you mean one of these?\n\n"
            for i, match in enumerate(top_matches, 1):
                msg += (
                    f"{i}. **{match['title']}** "
                    f"(similarity: {match['score']}%)\n"
                )
            msg += (
                "\nPlease reply with the exact title or number "
                "so I can analyze the right video."
            )
        else:
            msg += (
                "I don't have any recent videos on file for your channel. "
                "Please make sure your channel is connected and has uploaded videos."
            )

        return msg

    async def _populate_and_resolve(
        self,
        channel_uuid: UUID,
        channel_ctx: dict[str, Any],
        title_fragment: str,
    ) -> Optional[dict]:
        """
        Cold-start handler: fetch videos from YouTube API, upsert into DB,
        then retry fuzzy title resolution.

        Called when the resolver finds 0 videos in the DB — typically on
        the very first title-based query before any analytics fetch has run.

        Args:
            channel_uuid: Channel UUID.
            channel_ctx: Channel context dict with OAuth tokens.
            title_fragment: User's title fragment.

        Returns:
            Resolved video dict or None.
        """
        try:
            from registry.tool_handlers.fetch_last_video_analytics import (
                YouTubeVideoFetcher,
            )
            from memory.postgres_store import postgres_store

            access_token = channel_ctx.get("access_token", "")
            refresh_token = channel_ctx.get("refresh_token")
            user_id = channel_ctx.get("user_id")

            # Need user_id — get it from the channel record
            if not user_id:
                channel = self.postgres_store.get_channel_by_id(channel_uuid)
                if channel:
                    user_id = channel.user_id

            if not user_id:
                logger.warning("[Resolver] Cannot populate: no user_id")
                return None

            user_uuid = UUID(str(user_id)) if isinstance(user_id, str) else user_id

            logger.info(
                "[Resolver] Videos table empty — fetching from YouTube API"
            )

            fetcher = YouTubeVideoFetcher(
                access_token=access_token,
                refresh_token=refresh_token,
            )
            recent_videos = fetcher.get_recent_videos(limit=20)

            if not recent_videos:
                logger.info("[Resolver] YouTube API returned 0 videos")
                return None

            result = postgres_store.upsert_videos(
                channel_id=channel_uuid,
                user_id=user_uuid,
                videos_data=recent_videos,
            )
            logger.info(
                f"[Resolver] Cold-start populate: {result['inserted']} inserted, "
                f"{result['updated']} updated"
            )

            # Retry resolution with freshly populated data
            return resolve_video_by_title(channel_uuid, title_fragment)

        except Exception as e:
            logger.warning(f"[Resolver] Cold-start populate failed: {e}")
            return None


# Global orchestrator instance
_orchestrator: Optional[ContextOrchestrator] = None


def get_orchestrator() -> ContextOrchestrator:
    """Get or create the global orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = ContextOrchestrator()
    return _orchestrator


async def execute_context_request(
    user_id: str,
    channel_id: str,
    message: str,
    metadata: Optional[dict[str, Any]] = None
) -> ExecuteResponse:
    """
    Public API for executing a context request.

    This is the main entry point called by the server endpoint.

    Args:
        user_id: Unique identifier for the user
        channel_id: Channel/conversation context identifier
        message: User's input message
        metadata: Optional additional context

    Returns:
        ExecuteResponse with processed result
    """
    orchestrator = get_orchestrator()
    return await orchestrator.execute(
        user_id=user_id,
        channel_id=channel_id,
        message=message,
        metadata=metadata
    )
