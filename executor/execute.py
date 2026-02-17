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

        # Step 3: Check policy permissions
        approved_tools = self._filter_by_policy(plan, user_plan)

        # HARD GUARDRAIL: account intent must never execute tools
        if plan.intent_classification == "account":
            approved_tools = []
            tool_results = []
            logger.info("Account intent — skipping all tool execution")

        # Step 4: Execute approved tools
        if approved_tools:
            logger.debug(f"Executing {len(approved_tools)} tools")
            tool_results = await self._execute_tools(
                approved_tools, message, memory_context, plan.parameters
            )

        # Step 5: Call LLM with full context (including historical)
        logger.debug("Calling LLM")
        llm_response = await self._call_llm(
            message=message,
            memory_context=memory_context,
            tool_results=tool_results,
            plan=plan,
            channel_uuid=channel_uuid
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
        analytics_intents = {"analytics", "video_analysis", "insight", "report"}
        # Broader set: intents that need channel data context (e.g. subscriber count)
        context_intents = analytics_intents | {"account"}
        
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
        history = memory_context.get("conversation_history", [])
        if history:
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
        recent_chats = historical.get("recent_chats", [])
        if recent_chats:
            context_parts.append("\nPrevious conversations:")
            for chat in recent_chats[:3]:  # Limit to 3 for context
                user_msg = chat.get("user_message", "")[:100]  # Truncate
                context_parts.append(f"- User: {user_msg}...")

        # Add tool results
        if tool_results:
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

        # Build structured analytics section
        # HARD GUARDRAIL: Only inject analytics prompt section for analytics intents
        if plan.intent_classification in analytics_intents:
            analytics_section = self._build_analytics_prompt_section(analytics_context)
        else:
            analytics_section = ""

        # Build video analytics section from tool results
        video_analytics_section = self._build_video_analytics_prompt_section(tool_results)

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

            instructions_block = (
                "Instructions:\n"
                "- Follow the top video analysis template EXACTLY\n"
                "- Use ONLY the video metrics provided above\n"
                "- Do NOT mention video IDs or internal metadata\n"
                "- Do NOT echo the user's prompt back to them\n"
                "- Do NOT use markdown tables or raw JSON\n"
                "- Do NOT compare to channel-wide stats"
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

            if plan.intent_classification in analytics_intents:
                if is_content_strategy:
                    instructions_block = """Instructions:
- The user is asking a CONTENT STRATEGY question — "What should I upload next?"
- Follow the CONTENT STRATEGY TEMPLATE from the analysis prompt.
- Lead with the Data Signal: what does the data reveal about audience behavior?
- Give a decisive Strategic Direction: should the creator double down or pivot?
- Propose a concrete Next Video Concept with an emotional angle, not a vague theme.
- Include a Hook Script (first 5 seconds), 3 Title Options, and Thumbnail Direction.
- Recommend Format + Duration based on retention data.
- Set measurable Success Metrics.
- Do NOT start with a Growth Bottleneck Diagnosis — this is a creative strategy response.
- Do NOT use generic suggestions like "try trending topics."
- No markdown tables. No raw JSON. No emoji.
- Tone: creative strategist who knows the data inside-out."""
                elif is_growth_query:
                    instructions_block = """Instructions:
- The user is asking a GROWTH question — "How can I grow faster?"
- Follow the GROWTH ANALYSIS TEMPLATE from the analysis prompt.
- Lead with the Growth Bottleneck Diagnosis: name the #1 constraint with its metric.
- Then cover Leverage What's Working: identify the replicable content pattern or traffic source.
- Give 2–3 Targeted Growth Moves that directly address the diagnosed bottleneck.
- End with Strategic Expansion: how to scale beyond the current pattern (series, formats, cross-platform).
- Each move must pass: "Is this specific to THIS channel's data, or could it apply to anyone?"
- Do NOT suggest generic phrases like "improve thumbnails" or "engage your audience."
- No markdown tables. No raw JSON. No emoji.
- Tone: strategic growth advisor reviewing a performance dashboard."""
                else:
                    instructions_block = """Instructions:
- DIAGNOSE FIRST: Identify the #1 bottleneck (retention, CTR, traffic source, subscriber conversion, or distribution) before any recommendation.
- State the bottleneck explicitly in the first paragraph.
- Do NOT list metrics without interpreting them. Metrics are evidence, not the response.
- Every recommendation must directly address the diagnosed bottleneck.
- If retention > 50%, do NOT suggest retention improvements. Focus on distribution/packaging.
- If traffic is Shorts-dominated, apply Shorts-specific strategy — not long-form logic.
- Give 2–3 high-impact moves MAXIMUM. No spray-and-pray advice lists.
- Each recommendation must pass: "Is this specific to THIS channel's data, or could it apply to anyone?"
- Do NOT use generic phrases like "improve thumbnails" or "engage your audience."
- No markdown tables. No raw JSON. No emoji.
- Tone: strategic growth advisor reviewing a performance dashboard.

When analyzing a specific video (if LAST VIDEO ANALYTICS data is present):
- Follow the Video Analysis Template from the analysis prompt.
- Focus on the ONE metric that tells the story — do not list all metrics.
- Identify the replication pattern: what structural element should the next video copy?
- Include concrete examples: rewritten titles, hook scripts, thumbnail descriptions.
- Do NOT repeat the same metric in multiple sections."""
            else:
                instructions_block = """Instructions:
- This is a conversational or account query — NOT a deep analytics request.
- Answer the user's question directly using the Context and analytics data provided.
- If the user asks about subscribers, views, or basic stats, quote the exact number from the analytics data.
- Use the channel name and profile information from the Context section.
- Do NOT provide a full analytics diagnosis or bottleneck analysis.
- Do NOT mention tools or data sources.
- Keep the response short, friendly, and helpful.
- Do NOT use emoji."""

            full_prompt = f"""
{system_prompt}

{analysis_section_prompt}

{analytics_section}

{video_analytics_section}

Context:
{full_context}

User message: {clean_message}

{instructions_block}
"""

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
