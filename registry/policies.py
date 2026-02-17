"""
Policy engine for plan-based access control.

Enforces subscription-based restrictions on tool access.
Plans: FREE, PRO, AGENCY

This module provides a simple, extensible policy engine that:
- Defines plan hierarchy (FREE < PRO < AGENCY)
- Maps tools to minimum required plan
- Exposes can_execute(tool_name, user_plan) -> bool
- Provides rate limiting and feature flags per plan
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class Plan(str, Enum):
    """Subscription plan tiers."""
    FREE = "free"
    PRO = "pro"
    AGENCY = "agency"


@dataclass
class PlanLimits:
    """Limits for a subscription plan."""

    name: str
    tool_access: set[str]
    daily_requests: int
    max_context_length: int
    deep_analysis_enabled: bool
    priority_support: bool


class PolicyEngine:
    """
    Enforces plan-based access control for tool execution.

    Determines whether a user can execute a specific tool based on
    their subscription plan. Also provides rate limiting info and
    feature flags.

    Usage:
        engine = PolicyEngine()
        
        # Check if user can execute a tool
        if engine.can_execute("video_post_mortem", "free"):
            # Execute tool
        else:
            # Suggest upgrade
            upgrade_to = engine.get_upgrade_suggestion("video_post_mortem", "free")
    """

    # Plan hierarchy for comparison (index = level)
    PLAN_HIERARCHY: list[str] = [Plan.FREE.value, Plan.PRO.value, Plan.AGENCY.value]

    # Tool requirements - minimum plan needed for each tool
    # This is the single source of truth for tool access control
    TOOL_REQUIREMENTS: dict[str, str] = {
        # =====================================================================
        # FREE tier tools - Basic analytics and memory
        # =====================================================================
        "fetch_analytics": Plan.FREE.value,
        "summarize_data": Plan.FREE.value,
        "recall_context": Plan.FREE.value,
        "search_data": Plan.FREE.value,
        "get_channel_snapshot": Plan.FREE.value,  # Basic channel overview
        "get_top_videos": Plan.FREE.value,        # Top videos list

        # =====================================================================
        # PRO tier tools - Advanced analytics, insights, and reports
        # =====================================================================
        "compute_metrics": Plan.PRO.value,
        "generate_chart": Plan.PRO.value,
        "analyze_data": Plan.PRO.value,
        "generate_insight": Plan.PRO.value,
        "generate_report": Plan.PRO.value,
        "search_history": Plan.PRO.value,
        "video_post_mortem": Plan.PRO.value,      # Video performance analysis
        "weekly_growth_report": Plan.PRO.value,   # Weekly growth reports
        "fetch_last_video_analytics": Plan.PRO.value,  # Last video analysis

        # =====================================================================
        # AGENCY tier tools - Actions, automation, and premium features
        # =====================================================================
        "get_recommendations": Plan.AGENCY.value,
        "execute_action": Plan.AGENCY.value,
        "schedule_task": Plan.AGENCY.value,
    }

    # Plan definitions with full feature sets
    PLANS: dict[str, PlanLimits] = {
        Plan.FREE.value: PlanLimits(
            name=Plan.FREE.value,
            tool_access={
                "fetch_analytics", "summarize_data", "recall_context", 
                "search_data", "get_channel_snapshot", "get_top_videos"
            },
            daily_requests=50,
            max_context_length=4000,
            deep_analysis_enabled=False,
            priority_support=False
        ),
        Plan.PRO.value: PlanLimits(
            name=Plan.PRO.value,
            tool_access={
                # All FREE tools
                "fetch_analytics", "summarize_data", "recall_context", 
                "search_data", "get_channel_snapshot", "get_top_videos",
                "compute_metrics", "generate_chart", "analyze_data", 
                "generate_insight", "generate_report", "search_history",
                "video_post_mortem", "weekly_growth_report",
                "fetch_last_video_analytics"
            },
            daily_requests=500,
            max_context_length=16000,
            deep_analysis_enabled=True,
            priority_support=False
        ),
        Plan.AGENCY.value: PlanLimits(
            name=Plan.AGENCY.value,
            tool_access={
                # All FREE tools
                "fetch_analytics", "summarize_data", "recall_context", 
                "search_data", "get_channel_snapshot", "get_top_videos",
                "compute_metrics", "generate_chart", "analyze_data", 
                "generate_insight", "generate_report", "search_history",
                "video_post_mortem", "weekly_growth_report",
                "fetch_last_video_analytics",
                # AGENCY tools
                "get_recommendations", "execute_action", "schedule_task"
            },
            daily_requests=5000,
            max_context_length=32000,
            deep_analysis_enabled=True,
            priority_support=True
        )
    }

    def __init__(self) -> None:
        """Initialize the policy engine."""
        self._validate_configuration()

    def _validate_configuration(self) -> None:
        """Validate that TOOL_REQUIREMENTS and PLANS are consistent."""
        for tool_name, required_plan in self.TOOL_REQUIREMENTS.items():
            # Ensure tool is in the correct plan's tool_access
            for plan_name, limits in self.PLANS.items():
                plan_level = self.PLAN_HIERARCHY.index(plan_name)
                required_level = self.PLAN_HIERARCHY.index(required_plan)
                
                if plan_level >= required_level:
                    if tool_name not in limits.tool_access:
                        logger.warning(
                            f"Configuration mismatch: {tool_name} should be in {plan_name} "
                            f"tool_access (requires {required_plan})"
                        )

    def can_execute(self, tool_name: str, user_plan: str) -> bool:
        """
        Check if a tool can be executed under a user's plan.

        This is the primary access control function. It compares the user's
        plan level against the tool's minimum required plan.

        Args:
            tool_name: Name of the tool to check
            user_plan: User's subscription plan (free, pro, or agency)

        Returns:
            True if execution is allowed, False otherwise

        Examples:
            >>> engine = PolicyEngine()
            >>> engine.can_execute("fetch_analytics", "free")
            True
            >>> engine.can_execute("video_post_mortem", "free")
            False
            >>> engine.can_execute("video_post_mortem", "pro")
            True
        """
        # Get the required plan for this tool
        required_plan = self.TOOL_REQUIREMENTS.get(tool_name)

        if required_plan is None:
            # Unknown tool - deny by default for security
            logger.warning(f"Unknown tool in policy check: {tool_name}")
            return False

        # Check if user's plan meets the requirement
        return self._plan_meets_requirement(user_plan, required_plan)

    def _plan_meets_requirement(self, user_plan: str, required_plan: str) -> bool:
        """
        Check if user's plan meets or exceeds the required plan.

        Args:
            user_plan: User's current plan
            required_plan: Minimum required plan

        Returns:
            True if user_plan >= required_plan in hierarchy
        """
        try:
            user_level = self.PLAN_HIERARCHY.index(user_plan.lower())
            required_level = self.PLAN_HIERARCHY.index(required_plan.lower())
            return user_level >= required_level
        except ValueError:
            # Unknown plan - assume free
            logger.warning(f"Unknown plan: {user_plan}")
            return required_plan == "free"

    def get_plan_limits(self, user_plan: str) -> PlanLimits:
        """
        Get the limits for a subscription plan.

        Args:
            user_plan: Plan name

        Returns:
            PlanLimits for the plan (defaults to free if unknown)
        """
        return self.PLANS.get(user_plan.lower(), self.PLANS["free"])

    def get_available_tools(self, user_plan: str) -> list[str]:
        """
        Get list of tools available to a plan.

        Args:
            user_plan: Plan name

        Returns:
            List of tool names accessible under this plan
        """
        limits = self.get_plan_limits(user_plan)
        return sorted(list(limits.tool_access))

    def get_blocked_tools(self, user_plan: str) -> list[str]:
        """
        Get list of tools blocked for a plan.

        Args:
            user_plan: Plan name

        Returns:
            List of tool names NOT accessible under this plan
        """
        limits = self.get_plan_limits(user_plan)
        all_tools = set(self.TOOL_REQUIREMENTS.keys())
        blocked = all_tools - limits.tool_access
        return sorted(list(blocked))

    def get_upgrade_suggestion(self, tool_name: str, user_plan: str) -> Optional[str]:
        """
        Get a suggestion for which plan to upgrade to for a tool.

        Args:
            tool_name: Tool that was blocked
            user_plan: Current user plan

        Returns:
            Name of the plan needed, or None if already has access
        """
        if self.can_execute(tool_name, user_plan):
            return None

        required_plan = self.TOOL_REQUIREMENTS.get(tool_name, "agency")
        return required_plan

    def check_rate_limit(self, user_plan: str, current_usage: int) -> tuple[bool, int]:
        """
        Check if user has exceeded their daily rate limit.

        Args:
            user_plan: User's plan
            current_usage: Number of requests made today

        Returns:
            Tuple of (is_allowed, remaining_requests)
        """
        limits = self.get_plan_limits(user_plan)
        remaining = limits.daily_requests - current_usage

        return (remaining > 0, max(0, remaining))

    def validate_context_length(self, user_plan: str, context_length: int) -> bool:
        """
        Check if context length is within plan limits.

        Args:
            user_plan: User's plan
            context_length: Length of context in characters

        Returns:
            True if within limits
        """
        limits = self.get_plan_limits(user_plan)
        return context_length <= limits.max_context_length

    def can_use_deep_analysis(self, user_plan: str) -> bool:
        """
        Check if deep analysis is available for a plan.

        Args:
            user_plan: User's plan

        Returns:
            True if deep analysis is enabled
        """
        limits = self.get_plan_limits(user_plan)
        return limits.deep_analysis_enabled
