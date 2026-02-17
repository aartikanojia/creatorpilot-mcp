"""
Comprehensive planner unit tests — Categories 1-6, 8-9.

Pure unit tests for ExecutionPlanner. No mocks, no LLM, no network.
Validates intent classification, tool selection, and parameter detection
across all user query types.

Scoring: Each test validates dimensions on a 1-5 scale:
  - Intent accuracy
  - Tool correctness
  - Strategic depth (parameter selection)
  - Guardrail compliance
"""

import pytest
from executor.planner import ExecutionPlanner, ExecutionPlan


# =============================================================================
# CATEGORY 1: BASIC IDENTITY & GENERAL QUESTIONS
# =============================================================================

class TestCategory1Identity:
    """Tests for identity, profile, and general non-analytics queries."""

    def test_1_1_what_is_my_name(self, planner, available_tools, channel_context):
        """
        Input: "What is my name?"
        Expected:
        - account intent (not analytics)
        - No tools triggered (no fetch_analytics)
        - Direct answer from channel context
        """
        plan = planner.create_plan(
            "What is my name?", channel_context, available_tools
        )
        assert plan.intent_classification == "account"
        assert len(plan.tools_to_execute) == 0
        assert "fetch_analytics" not in plan.tools_to_execute

    def test_1_1b_whats_my_name_contraction(self, planner, available_tools, channel_context):
        """Contraction variant: "What's my name?" """
        plan = planner.create_plan(
            "What's my name?", channel_context, available_tools
        )
        assert plan.intent_classification == "account"
        assert len(plan.tools_to_execute) == 0

    def test_1_2_how_many_subscribers(self, planner, available_tools, channel_context):
        """
        Input: "How many subscribers do I have?"
        Expected:
        - account intent takes priority (contains "subscribers" + "my")
        - No tools triggered (account queries are tool-free)
        """
        plan = planner.create_plan(
            "How many subscribers do I have?", channel_context, available_tools
        )
        # "my subscribers" pattern matches account intent with priority
        assert plan.intent_classification == "account"
        assert len(plan.tools_to_execute) == 0

    def test_1_3_am_i_connected(self, planner, available_tools, channel_context):
        """
        Input: "Am I connected?"
        Expected:
        - No analytics triggered
        - Simple channel status query
        """
        plan = planner.create_plan(
            "Am I connected?", channel_context, available_tools
        )
        # Should NOT be analytics — no analytics keyword
        assert plan.intent_classification != "analytics"
        assert "fetch_analytics" not in plan.tools_to_execute

    def test_1_4_who_am_i(self, planner, available_tools, channel_context):
        """Input: "Who am I?" → account intent, no tools."""
        plan = planner.create_plan(
            "Who am I?", channel_context, available_tools
        )
        assert plan.intent_classification == "account"
        assert len(plan.tools_to_execute) == 0

    def test_1_5_channel_info(self, planner, available_tools, channel_context):
        """Input: "Channel info" → account intent."""
        plan = planner.create_plan(
            "Give me my channel info", channel_context, available_tools
        )
        assert plan.intent_classification == "account"
        assert len(plan.tools_to_execute) == 0

    def test_1_6_account_intent_never_has_tools(self, planner, available_tools, channel_context):
        """Safety guardrail: account intent MUST never execute any tools."""
        account_queries = [
            "What is my name?",
            "Who am I?",
            "My channel name",
            "Tell me about my channel",
            "My profile",
            "My account",
        ]
        for query in account_queries:
            plan = planner.create_plan(query, channel_context, available_tools)
            assert plan.intent_classification == "account", (
                f"'{query}' should be account intent, got {plan.intent_classification}"
            )
            assert len(plan.tools_to_execute) == 0, (
                f"'{query}' should have 0 tools, got {plan.tools_to_execute}"
            )

    def test_1_7_account_confidence_high(self, planner, available_tools, channel_context):
        """Account intent should have high confidence (>=0.9)."""
        plan = planner.create_plan(
            "What is my name?", channel_context, available_tools
        )
        assert plan.confidence >= 0.9


# =============================================================================
# CATEGORY 2: VIDEO-SPECIFIC ANALYSIS
# =============================================================================

class TestCategory2VideoAnalysis:
    """Tests for video-specific analysis queries."""

    def test_2_1_analyze_last_video(self, planner, available_tools, channel_context):
        """
        Input: "Analyze my last video."
        Expected:
        - video_analysis intent
        - fetch_last_video_analytics triggered
        - Must analyze THIS video only
        """
        plan = planner.create_plan(
            "Analyze my last video", channel_context, available_tools
        )
        assert plan.intent_classification == "video_analysis"
        assert "fetch_last_video_analytics" in plan.tools_to_execute

    def test_2_1b_latest_video_variant(self, planner, available_tools, channel_context):
        """Variant: "How is my latest video performing?" """
        plan = planner.create_plan(
            "How is my latest video performing?", channel_context, available_tools
        )
        assert plan.intent_classification == "video_analysis"
        assert "fetch_last_video_analytics" in plan.tools_to_execute

    def test_2_2_analyze_named_video_performance(self, planner, available_tools, channel_context):
        """
        Input: "Analyze why my video 'Valentine Day Vlog' performed well."
        Expected:
        - Analytics/insight intent (growth analysis)
        - fetch_analytics triggered for data context
        """
        plan = planner.create_plan(
            "Analyze why my video 'Valentine Day Vlog' performed well",
            channel_context,
            available_tools,
        )
        # Should trigger analytics-related tools (performance keyword)
        has_analytics_tool = (
            "fetch_analytics" in plan.tools_to_execute
            or "fetch_last_video_analytics" in plan.tools_to_execute
        )
        assert has_analytics_tool

    def test_2_3_why_video_flopped(self, planner, available_tools, channel_context):
        """
        Input: "Why did my video flop?"
        Expected:
        - insight intent (contains "why")
        - Bottleneck diagnosis tools triggered
        """
        plan = planner.create_plan(
            "Why did my video flop?", channel_context, available_tools
        )
        # Should trigger insight or analytics intent
        assert plan.intent_classification in {"insight", "analytics", "video_analysis"}
        assert len(plan.tools_to_execute) > 0

    def test_2_4_last_upload_performance(self, planner, available_tools, channel_context):
        """Input: "How did my last upload perform?" → video_analysis."""
        plan = planner.create_plan(
            "How did my last upload perform?", channel_context, available_tools
        )
        assert plan.intent_classification == "video_analysis"
        assert "fetch_last_video_analytics" in plan.tools_to_execute


# =============================================================================
# CATEGORY 3: GROWTH STRATEGY QUESTIONS
# =============================================================================

class TestCategory3GrowthStrategy:
    """Tests for growth and content strategy queries."""

    def test_3_1_improve_video_views(self, planner, available_tools, channel_context):
        """
        Input: "Help me improve views for my video Valentine Day Vlog."
        Expected:
        - Detects growth intent
        - fetch_analytics triggered
        - Strategic growth path
        """
        plan = planner.create_plan(
            "Help me improve views for my video Valentine Day Vlog",
            channel_context,
            available_tools,
        )
        # "views" keyword with channel context should trigger analytics
        assert "fetch_analytics" in plan.tools_to_execute

    def test_3_2_grow_faster(self, planner, available_tools, channel_context):
        """
        Input: "How can I grow faster?"
        Expected:
        - Channel-level strategic intent (analytics/insight)
        - fetch_analytics triggered
        - Period should be 28d for growth queries
        """
        plan = planner.create_plan(
            "How can I grow faster?", channel_context, available_tools
        )
        assert "fetch_analytics" in plan.tools_to_execute
        # Growth queries should use 28d period for trend context
        assert plan.parameters.get("period") == "28d"

    def test_3_3_what_to_upload_next(self, planner, available_tools, channel_context):
        """
        Input: "What should I upload next?"
        Expected:
        - Content strategy detection
        - fetch_analytics triggered
        - period=28d, compare_periods=True, fetch_library=True
        """
        plan = planner.create_plan(
            "What should I upload next?", channel_context, available_tools
        )
        assert "fetch_analytics" in plan.tools_to_execute
        assert plan.parameters.get("period") == "28d"
        assert plan.parameters.get("fetch_library") is True

    def test_3_3b_content_strategy_query(self, planner, available_tools, channel_context):
        """Variant: "What content should I make?" """
        plan = planner.create_plan(
            "What content should I make?", channel_context, available_tools
        )
        assert plan.parameters.get("fetch_library") is True

    def test_3_4_video_ideas(self, planner, available_tools, channel_context):
        """Input: "Give me some video ideas" → fetch_library param."""
        plan = planner.create_plan(
            "Give me some video ideas based on my performance",
            channel_context,
            available_tools,
        )
        # Should detect content strategy and fetch library
        assert plan.parameters.get("fetch_library") is True


# =============================================================================
# CATEGORY 4: RETENTION-SPECIFIC QUESTIONS
# =============================================================================

class TestCategory4Retention:
    """Tests for retention and watch-time specific queries."""

    def test_4_1_low_watch_time(self, planner, available_tools, channel_context):
        """
        Input: "Why is my watch time low?"
        Expected:
        - insight intent (why + improve)
        - fetch_analytics triggered
        """
        plan = planner.create_plan(
            "Why is my watch time low?", channel_context, available_tools
        )
        assert plan.intent_classification in {"insight", "analytics"}
        assert "fetch_analytics" in plan.tools_to_execute

    def test_4_2_retention_dropping(self, planner, available_tools, channel_context):
        """
        Input: "Why is my retention dropping?"
        Expected:
        - insight intent
        - fetch_analytics triggered
        - Should compare periods for trend detection
        """
        plan = planner.create_plan(
            "Why is my retention dropping?", channel_context, available_tools
        )
        assert plan.intent_classification in {"insight", "analytics"}
        assert "fetch_analytics" in plan.tools_to_execute

    def test_4_3_improve_retention(self, planner, available_tools, channel_context):
        """Input: "How can I improve my retention?" → insight intent."""
        plan = planner.create_plan(
            "How can I improve my retention?", channel_context, available_tools
        )
        assert "fetch_analytics" in plan.tools_to_execute


# =============================================================================
# CATEGORY 5: CTR & DISCOVERY QUESTIONS
# =============================================================================

class TestCategory5CTRDiscovery:
    """Tests for CTR, impressions, and discoverability queries."""

    def test_5_1_views_decreasing(self, planner, available_tools, channel_context):
        """
        Input: "Why are my views decreasing?"
        Expected:
        - analytics intent (views keyword + channel context)
        - fetch_analytics triggered
        """
        plan = planner.create_plan(
            "Why are my views decreasing?", channel_context, available_tools
        )
        assert "fetch_analytics" in plan.tools_to_execute

    def test_5_2_not_getting_impressions(self, planner, available_tools, channel_context):
        """
        Input: "My video is not getting impressions."
        Expected:
        - Must focus on discoverability
        - fetch_analytics triggered
        """
        plan = planner.create_plan(
            "My video is not getting impressions",
            channel_context,
            available_tools,
        )
        # Should trigger analytics to diagnose the issue
        assert len(plan.tools_to_execute) > 0

    def test_5_3_low_ctr(self, planner, available_tools, channel_context):
        """Input: "My CTR is very low, how do I fix it?" """
        plan = planner.create_plan(
            "My CTR is very low, how do I fix it?",
            channel_context,
            available_tools,
        )
        assert plan.intent_classification in {"insight", "analytics"}
        assert "fetch_analytics" in plan.tools_to_execute


# =============================================================================
# CATEGORY 6: SUBSCRIBER CONVERSION
# =============================================================================

class TestCategory6SubscriberConversion:
    """Tests for subscriber conversion and growth queries."""

    def test_6_1_not_gaining_subscribers(self, planner, available_tools, channel_context):
        """
        Input: "Why am I not gaining subscribers?"
        Expected:
        - insight intent (why + subscribers)
        - fetch_analytics triggered for conversion analysis
        """
        plan = planner.create_plan(
            "Why am I not gaining subscribers?",
            channel_context,
            available_tools,
        )
        # "subscribers" + "why" should trigger analytics or insight
        assert len(plan.tools_to_execute) > 0

    def test_6_2_convert_shorts_viewers(self, planner, available_tools, channel_context):
        """
        Input: "How can I convert Shorts viewers into subscribers?"
        Expected:
        - insight intent
        - fetch_analytics triggered
        - Funnel strategy expected
        """
        plan = planner.create_plan(
            "How can I convert Shorts viewers into subscribers?",
            channel_context,
            available_tools,
        )
        assert plan.intent_classification in {"insight", "analytics"}
        assert "fetch_analytics" in plan.tools_to_execute


# =============================================================================
# CATEGORY 8: NON-ANALYTICS QUESTIONS
# =============================================================================

class TestCategory8NonAnalytics:
    """Tests for non-analytics, conversational queries."""

    def test_8_1_whats_my_name(self, planner, available_tools, channel_context):
        """
        Input: "What's my name?"
        Expected:
        - account intent
        - No analytics
        - No metrics
        - Simple direct answer
        """
        plan = planner.create_plan(
            "What's my name?", channel_context, available_tools
        )
        assert plan.intent_classification == "account"
        assert len(plan.tools_to_execute) == 0

    def test_8_2_tell_me_a_joke(self, planner, available_tools, channel_context):
        """
        Input: "Tell me a joke."
        Expected:
        - general intent (no analytics patterns)
        - Should NOT hallucinate analytics
        - No fetch_analytics tool
        """
        plan = planner.create_plan(
            "Tell me a joke", channel_context, available_tools
        )
        # Should NOT be analytics or insight
        assert plan.intent_classification not in {"analytics", "video_analysis"}
        assert "fetch_analytics" not in plan.tools_to_execute

    def test_8_3_hello_greeting(self, planner, available_tools, channel_context):
        """Input: "Hello" → general intent, minimal tools."""
        plan = planner.create_plan(
            "Hello", channel_context, available_tools
        )
        assert plan.intent_classification not in {"analytics", "video_analysis"}
        assert "fetch_analytics" not in plan.tools_to_execute


# =============================================================================
# CATEGORY 9: IRRELEVANT / EDGE CASES
# =============================================================================

class TestCategory9EdgeCases:
    """Tests for irrelevant, off-topic, and boundary queries."""

    def test_9_1_cook_pasta(self, planner, available_tools, channel_context):
        """
        Input: "How to cook pasta?"
        Expected:
        - general intent (no analytics keywords)
        - No analytics tools triggered
        - Guardrail redirect expected
        """
        plan = planner.create_plan(
            "How to cook pasta?", channel_context, available_tools
        )
        assert plan.intent_classification not in {"analytics", "video_analysis"}
        assert "fetch_analytics" not in plan.tools_to_execute

    def test_9_2_political_advice(self, planner, available_tools, channel_context):
        """
        Input: "Give me political advice."
        Expected:
        - general intent
        - No analytics tools triggered
        - Should stay within YouTube domain
        """
        plan = planner.create_plan(
            "Give me political advice", channel_context, available_tools
        )
        assert plan.intent_classification not in {"analytics", "video_analysis"}
        assert "fetch_analytics" not in plan.tools_to_execute

    def test_9_3_empty_message(self, planner, available_tools, channel_context):
        """Edge case: empty string message."""
        plan = planner.create_plan("", channel_context, available_tools)
        assert plan.intent_classification == "general"

    def test_9_4_very_long_message(self, planner, available_tools, channel_context):
        """Edge case: very long message should not crash."""
        long_msg = "analyze my channel " * 500
        plan = planner.create_plan(long_msg, channel_context, available_tools)
        assert plan.intent_classification is not None
        assert isinstance(plan.tools_to_execute, list)

    def test_9_5_special_characters(self, planner, available_tools, channel_context):
        """Edge case: special characters in message."""
        plan = planner.create_plan(
            "What's my 📈 growth rate? <script>alert('xss')</script>",
            channel_context,
            available_tools,
        )
        assert plan is not None
        assert isinstance(plan.tools_to_execute, list)

    def test_9_6_no_channel_context(self, planner, available_tools, empty_context):
        """Edge case: analytics query without channel context."""
        plan = planner.create_plan(
            "Show me my analytics", empty_context, available_tools
        )
        # Without channel context, analytics override should NOT fire
        # But keyword match still classifies intent
        assert isinstance(plan.tools_to_execute, list)

    def test_9_7_no_available_tools(self, planner, channel_context):
        """Edge case: no tools available."""
        plan = planner.create_plan(
            "Analyze my channel", channel_context, []
        )
        assert len(plan.tools_to_execute) == 0


# =============================================================================
# CROSS-CUTTING: PARAMETER DETECTION TESTS
# =============================================================================

class TestParameterDetection:
    """Tests for execution parameter determination."""

    def test_28d_period_for_growth(self, planner, available_tools, channel_context):
        """Growth queries should use 28d period."""
        plan = planner.create_plan(
            "How can I grow my channel?", channel_context, available_tools
        )
        assert plan.parameters.get("period") == "28d"

    def test_28d_period_explicit(self, planner, available_tools, channel_context):
        """Explicit 28-day mention → 28d period."""
        plan = planner.create_plan(
            "Show me 28 day analytics", channel_context, available_tools
        )
        assert plan.parameters.get("period") == "28d"

    def test_library_fetch_for_content_queries(self, planner, available_tools, channel_context):
        """Content strategy queries should set fetch_library=True."""
        content_queries = [
            "What should I upload next?",
            "What content should I make?",
            "Give me video ideas",
            "What's been working for me?",
        ]
        for query in content_queries:
            plan = planner.create_plan(query, channel_context, available_tools)
            assert plan.parameters.get("fetch_library") is True, (
                f"'{query}' should have fetch_library=True"
            )

    def test_compare_periods_for_strategy(self, planner, available_tools, channel_context):
        """Content strategy queries should enable period comparison."""
        plan = planner.create_plan(
            "What should I upload next?", channel_context, available_tools
        )
        assert plan.parameters.get("compare_periods") is True

    def test_deep_analysis_for_analyze(self, planner, available_tools, channel_context):
        """'analyze' keyword triggers deep analysis mode."""
        plan = planner.create_plan(
            "Analyze my channel in detail", channel_context, available_tools
        )
        assert plan.requires_deep_analysis is True

    def test_deep_analysis_for_reports(self, planner, available_tools, channel_context):
        """Report intent always triggers deep analysis."""
        plan = planner.create_plan(
            "Give me a weekly report", channel_context, available_tools
        )
        assert plan.requires_deep_analysis is True


# =============================================================================
# CROSS-CUTTING: ANALYTICS OVERRIDE TESTS
# =============================================================================

class TestAnalyticsOverride:
    """Tests for the analytics override mechanism."""

    def test_override_with_channel_context(self, planner, available_tools, channel_context):
        """Analytics keywords + channel context → analytics override."""
        plan = planner.create_plan(
            "How is my channel performing?", channel_context, available_tools
        )
        assert plan.intent_classification == "analytics"
        assert "fetch_analytics" in plan.tools_to_execute

    def test_no_override_without_channel(self, planner, available_tools, empty_context):
        """Analytics keywords without channel context → no override."""
        plan = planner.create_plan(
            "Show me performance data", empty_context, available_tools
        )
        # Without channel context, override doesn't fire
        # Intent still classified by patterns, but no forced analytics
        assert isinstance(plan, ExecutionPlan)

    def test_account_never_overridden(self, planner, available_tools, channel_context):
        """Account intent must NEVER be overridden to analytics."""
        plan = planner.create_plan(
            "What is my name?", channel_context, available_tools
        )
        assert plan.intent_classification == "account"
        assert len(plan.tools_to_execute) == 0

    def test_views_keyword_triggers_override(self, planner, available_tools, channel_context):
        """'views' keyword with channel context → analytics."""
        plan = planner.create_plan(
            "Show me views data", channel_context, available_tools
        )
        assert "fetch_analytics" in plan.tools_to_execute


# =============================================================================
# TOP VIDEO CONTEXT PARSING TESTS
# =============================================================================

class TestTopVideoDetection:
    """Tests for top video query detection and context parsing."""

    def test_top_video_query_detected(self):
        """'Analyze my top video' should be detected."""
        from executor.execute import ContextOrchestrator
        orch = ContextOrchestrator.__new__(ContextOrchestrator)
        assert orch._is_top_video_query(
            'Analyze my top video "Mihir ki masti #play" from the last 7 days'
        ) is True

    def test_non_top_video_not_detected(self):
        """Regular queries should not match top video pattern."""
        from executor.execute import ContextOrchestrator
        orch = ContextOrchestrator.__new__(ContextOrchestrator)
        assert orch._is_top_video_query("How is my channel performing?") is False
        assert orch._is_top_video_query("Analyze my last video") is False

    def test_parse_top_video_context(self):
        """[TOP_VIDEO_CONTEXT] marker should be parsed and stripped."""
        from executor.execute import ContextOrchestrator
        orch = ContextOrchestrator.__new__(ContextOrchestrator)
        raw = (
            'Analyze my top video "Mihir ki masti" from the last 7 days\n'
            '[TOP_VIDEO_CONTEXT]{"views":1802,"growth":100.0,"title":"Mihir ki masti"}'
        )
        clean, meta = orch._parse_top_video_context(raw)
        assert clean == 'Analyze my top video "Mihir ki masti" from the last 7 days'
        assert meta is not None
        assert meta["views"] == 1802
        assert meta["growth"] == 100.0
        assert meta["title"] == "Mihir ki masti"

    def test_parse_no_marker(self):
        """Messages without marker return original + None."""
        from executor.execute import ContextOrchestrator
        orch = ContextOrchestrator.__new__(ContextOrchestrator)
        clean, meta = orch._parse_top_video_context("Regular message")
        assert clean == "Regular message"
        assert meta is None

    def test_parse_invalid_json(self):
        """Malformed JSON after marker returns clean message + None."""
        from executor.execute import ContextOrchestrator
        orch = ContextOrchestrator.__new__(ContextOrchestrator)
        raw = "Analyze my top video\n[TOP_VIDEO_CONTEXT]{invalid json}"
        clean, meta = orch._parse_top_video_context(raw)
        assert clean == "Analyze my top video"
        assert meta is None
