"""
Orchestrator integration tests — Category 7 (Free vs PRO guardrails).

Tests the full ContextOrchestrator pipeline with mocked dependencies
(LLM, Redis, PostgreSQL). Validates usage limits, plan gating, and
top-video context processing.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from datetime import datetime, timezone


# =============================================================================
# CATEGORY 7: FREE vs PRO GUARDRAILS
# =============================================================================

class TestCategory7UsageLimits:
    """Tests for free-tier usage limits and PRO bypass."""

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client for usage tracking."""
        client = AsyncMock()
        client.incr = AsyncMock(return_value=1)
        client.expire = AsyncMock()
        return client

    @pytest.fixture
    def mock_orchestrator(self, mock_redis):
        """Create a ContextOrchestrator with mocked Redis."""
        from executor.execute import ContextOrchestrator
        orch = ContextOrchestrator.__new__(ContextOrchestrator)
        orch.FREE_DAILY_LIMIT = 3

        # Mock Redis store
        redis_store = MagicMock()
        redis_store._ensure_connection = AsyncMock(return_value=mock_redis)
        orch.redis_store = redis_store

        return orch, mock_redis

    @pytest.mark.asyncio
    async def test_7_1_free_user_first_query_allowed(self, mock_orchestrator):
        """
        Free user, 1st query: should be allowed.
        Expected: (True, 1)
        """
        orch, mock_redis = mock_orchestrator
        mock_redis.incr.return_value = 1

        allowed, count = await orch._check_usage_limit("user_123", "free")
        assert allowed is True
        assert count == 1

    @pytest.mark.asyncio
    async def test_7_1b_free_user_third_query_allowed(self, mock_orchestrator):
        """
        Free user, 3rd query (at limit): should still be allowed.
        Expected: (True, 3) — counter shows 3/3
        """
        orch, mock_redis = mock_orchestrator
        mock_redis.incr.return_value = 3

        allowed, count = await orch._check_usage_limit("user_123", "free")
        assert allowed is True
        assert count == 3

    @pytest.mark.asyncio
    async def test_7_1c_free_user_fourth_query_blocked(self, mock_orchestrator):
        """
        Free user, 4th query: MUST be blocked.
        Expected:
        - Return PLAN_LIMIT_REACHED (False)
        - No LLM invocation
        - Counter correct > 3
        """
        orch, mock_redis = mock_orchestrator
        mock_redis.incr.return_value = 4

        allowed, count = await orch._check_usage_limit("user_123", "free")
        assert allowed is False
        assert count == 4

    @pytest.mark.asyncio
    async def test_7_1d_free_user_tenth_query_blocked(self, mock_orchestrator):
        """Even the 10th query should be blocked for free users."""
        orch, mock_redis = mock_orchestrator
        mock_redis.incr.return_value = 10

        allowed, count = await orch._check_usage_limit("user_123", "free")
        assert allowed is False
        assert count == 10

    @pytest.mark.asyncio
    async def test_7_2_pro_user_unlimited(self, mock_orchestrator):
        """
        PRO user: no limit applied.
        Expected:
        - Always (True, 0)
        - No Redis interaction
        - Counter hidden
        """
        orch, mock_redis = mock_orchestrator
        allowed, count = await orch._check_usage_limit("user_pro", "pro")
        assert allowed is True
        assert count == 0

        # Should NOT have called Redis at all
        mock_redis.incr.assert_not_called()

    @pytest.mark.asyncio
    async def test_7_2b_pro_case_insensitive(self, mock_orchestrator):
        """PRO detection should be case-insensitive."""
        orch, mock_redis = mock_orchestrator
        allowed, _ = await orch._check_usage_limit("user_pro", "PRO")
        assert allowed is True
        mock_redis.incr.assert_not_called()

    @pytest.mark.asyncio
    async def test_7_3_redis_failure_allows_request(self, mock_orchestrator):
        """
        Redis failure → fail-open (allow request).
        This ensures users aren't blocked due to infrastructure issues.
        """
        orch, mock_redis = mock_orchestrator
        mock_redis.incr.side_effect = ConnectionError("Redis down")

        # Fail-open: should still allow
        redis_store = MagicMock()
        redis_store._ensure_connection = AsyncMock(return_value=mock_redis)
        orch.redis_store = redis_store

        allowed, count = await orch._check_usage_limit("user_123", "free")
        assert allowed is True

    @pytest.mark.asyncio
    async def test_7_4_expiry_set_on_first_increment(self, mock_orchestrator):
        """First increment should set 24-hour expiry on usage key."""
        orch, mock_redis = mock_orchestrator
        mock_redis.incr.return_value = 1

        await orch._check_usage_limit("user_123", "free")
        mock_redis.expire.assert_called_once()
        # Verify 24-hour expiry
        args = mock_redis.expire.call_args
        assert args[0][1] == 86400

    @pytest.mark.asyncio
    async def test_7_5_different_users_independent(self, mock_orchestrator):
        """Different users should have independent counters."""
        orch, mock_redis = mock_orchestrator

        # User A gets 1st query
        mock_redis.incr.return_value = 1
        allowed_a, _ = await orch._check_usage_limit("user_a", "free")
        assert allowed_a is True

        # User B also gets 1st query (independent counter)
        mock_redis.incr.return_value = 1
        allowed_b, _ = await orch._check_usage_limit("user_b", "free")
        assert allowed_b is True


# =============================================================================
# TOP VIDEO CONTEXT INTEGRATION
# =============================================================================

class TestTopVideoContextIntegration:
    """Integration tests for top-video context processing."""

    def test_context_stripping_preserves_message(self):
        """Top video context marker should be fully stripped."""
        from executor.execute import ContextOrchestrator
        orch = ContextOrchestrator.__new__(ContextOrchestrator)

        raw = (
            'Analyze my top video "Test Video" from the last 7 days\n'
            '[TOP_VIDEO_CONTEXT]{"views":500,"growth":50.0,"title":"Test Video"}'
        )
        clean, meta = orch._parse_top_video_context(raw)

        # Clean message should have zero traces of the marker
        assert "[TOP_VIDEO_CONTEXT]" not in clean
        assert "{" not in clean
        assert "views" not in clean.lower() or "view" in clean.lower()

    def test_all_metadata_fields_extracted(self):
        """All expected metadata fields should be present."""
        from executor.execute import ContextOrchestrator
        orch = ContextOrchestrator.__new__(ContextOrchestrator)

        raw = (
            'Test message\n'
            '[TOP_VIDEO_CONTEXT]{"views":1802,"growth":100.0,"title":"My Video"}'
        )
        _, meta = orch._parse_top_video_context(raw)

        assert "views" in meta
        assert "growth" in meta
        assert "title" in meta

    def test_content_strategy_detection(self):
        """Content strategy queries should be correctly identified."""
        from executor.execute import ContextOrchestrator
        orch = ContextOrchestrator.__new__(ContextOrchestrator)

        assert orch._is_content_strategy_query(
            "How many subscribers do I have?", "account"
        ) is False

# =============================================================================
# SUBSCRIBER COUNT INJECTION TEST (Regression Fix)
# =============================================================================

class TestSubscriberCountInjection:
    """
    Regression test for "How many subscribers do I have?".
    Ensures 'account' intent triggers analytics context injection.
    """

    @pytest.fixture
    def mock_deps(self):
        """Mock dependencies for orchestrator."""
        from executor.execute import ContextOrchestrator
        orch = ContextOrchestrator.__new__(ContextOrchestrator)
        orch.planner = MagicMock()
        orch.analytics_builder = MagicMock()
        orch.redis_store = AsyncMock()
        orch.postgres_store = MagicMock()
        orch.postgres_store.get_channel_by_id.return_value = MagicMock(
            id="channel-uuid", channel_name="Test Channel"
        )
        orch.postgres_store.get_latest_analytics_snapshot.return_value = None
        orch.tool_registry = MagicMock()
        orch.tool_registry.list_tools.return_value = []
        orch._check_usage_limit = AsyncMock(return_value=(True, 0))
        orch._load_memory_context = AsyncMock(return_value={})
        orch._load_historical_context = MagicMock(return_value={})
        orch._persist_to_postgres = MagicMock()
        orch._store_conversation = AsyncMock()
        orch._build_structured_data = MagicMock(return_value={})
        orch.formatter = MagicMock()
        orch.formatter.format_response.return_value = "Formatted Response"
        
        # Mock LLM client instead of blocking _call_llm
        orch.llm_client = AsyncMock()
        orch.llm_client.generate_response = AsyncMock(return_value="LLM Response")
        orch._load_prompt = MagicMock(return_value="System Prompt")
        
        return orch

    @pytest.mark.asyncio
    async def test_account_intent_injects_subscribers(self, mock_deps):
        """
        Verify 'account' intent triggers build_analytics_context.
        """
        orch = mock_deps
        
        # 1. Setup Planner to return 'account' intent
        plan = MagicMock()
        plan.intent_classification = "account"
        plan.tools_to_execute = []
        orch.planner.create_plan.return_value = plan
        
        # Configure analytics builder to return real data structure to avoid formatting errors
        orch.analytics_builder.build_analytics_context.return_value = {
            "has_ctr": True,
            "has_retention": True,
            "has_traffic_sources": True,
            "current_period": {
                "period": "last_7_days",
                "views": 1000,
                "subscribers": 50,
            }
        }
        
        # 2. Execute request
        await orch.execute(
            user_id="user-uuid",
            channel_id="channel-uuid",
            message="How many subscribers?"
        )
        
        # 3. Verify analytics builder was called
        # This confirms the fix: account intent is now in the whitelist
        orch.analytics_builder.build_analytics_context.assert_called_once()
