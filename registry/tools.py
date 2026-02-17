"""
MCP Tool Registry.

Registers all available tools with their definitions, schemas,
and handler implementations. Each tool has:
- name: Unique identifier
- description: Human-readable description
- input_schema: Expected input format
- output_schema: Expected output format
- handler: Async function that executes the tool

Tool Categories:
- analytics: Data fetching and metric computation
- insight: Data analysis and recommendations
- report: Report and summary generation
- memory: Context recall and history search
- action: Task execution and scheduling
- search: Data search across sources

Handler implementations are organized in the handlers/ subpackage.
"""

import logging
from typing import Any, Optional

from .base import ToolResult, ToolDefinition
from .handlers import (
    AnalyticsHandlers,
    InsightHandlers,
    ReportHandlers,
    MemoryHandlers,
    ActionHandlers,
    SearchHandlers,
    YouTubeHandlers,
)
from .tool_handlers import handle_fetch_analytics, handle_fetch_last_video_analytics

logger = logging.getLogger(__name__)

# Re-export for backwards compatibility
__all__ = ["ToolResult", "ToolDefinition", "ToolRegistry"]


class ToolRegistry:
    """
    Central registry for all MCP tools.

    Manages tool registration, discovery, and execution.
    Tools are registered at initialization with their schemas
    and handler functions.

    Usage:
        registry = ToolRegistry()
        tools = registry.list_tools()
        result = await registry.execute_tool("fetch_analytics", input_data)
    """

    def __init__(self) -> None:
        """Initialize the registry and register all tools."""
        self._tools: dict[str, ToolDefinition] = {}
        self._register_all_tools()

    def _register_all_tools(self) -> None:
        """Register all available MCP tools."""
        self._register_analytics_tools()
        self._register_insight_tools()
        self._register_report_tools()
        self._register_memory_tools()
        self._register_action_tools()
        self._register_search_tools()
        self._register_youtube_tools()

    # =========================================================================
    # Analytics Tools
    # =========================================================================

    def _register_analytics_tools(self) -> None:
        """Register analytics-related tools."""
        # Real YouTube Analytics ingestion tool
        self._register_tool(ToolDefinition(
            name="fetch_analytics",
            description="Fetch real YouTube Analytics data for the connected channel. Uses OAuth access_token from context to call YouTube Analytics API, normalizes the response, and persists an AnalyticsSnapshot to the database.",
            input_schema={
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "context": {
                        "type": "object",
                        "description": "Context containing channel OAuth tokens (injected by executor)"
                    }
                },
                "required": ["context"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "data": {
                        "type": "object",
                        "properties": {
                            "period": {"type": "string"},
                            "views": {"type": "integer"},
                            "subscribers": {"type": "integer"},
                            "avg_ctr": {"type": "number"},
                            "avg_watch_time_minutes": {"type": "number"}
                        }
                    }
                }
            },
            handler=handle_fetch_analytics,
            category="analytics",
            requires_plan="free"
        ))

        self._register_tool(ToolDefinition(
            name="compute_metrics",
            description="Compute derived metrics from raw analytics data",
            input_schema={
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "context": {"type": "object"},
                    "data": {"type": "object"}
                },
                "required": ["message", "context"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "growth_rate": {"type": "number"},
                    "engagement_rate": {"type": "number"},
                    "trends": {"type": "array"}
                }
            },
            handler=AnalyticsHandlers.compute_metrics,
            category="analytics",
            requires_plan="pro"
        ))

        self._register_tool(ToolDefinition(
            name="generate_chart",
            description="Generate chart data for visualization",
            input_schema={
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "context": {"type": "object"},
                    "chart_type": {"type": "string", "enum": ["line", "bar", "pie"]},
                    "data": {"type": "object"}
                },
                "required": ["message", "context"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "chart_type": {"type": "string"},
                    "labels": {"type": "array"},
                    "datasets": {"type": "array"}
                }
            },
            handler=AnalyticsHandlers.generate_chart,
            category="analytics",
            requires_plan="pro"
        ))

    # =========================================================================
    # Insight Tools
    # =========================================================================

    def _register_insight_tools(self) -> None:
        """Register insight-related tools."""
        self._register_tool(ToolDefinition(
            name="analyze_data",
            description="Perform deep analysis on channel data",
            input_schema={
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "context": {"type": "object"},
                    "data_source": {"type": "string"},
                    "focus_area": {"type": "string"}
                },
                "required": ["message", "context"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "analysis": {"type": "string"},
                    "key_findings": {"type": "array"},
                    "confidence": {"type": "number"}
                }
            },
            handler=InsightHandlers.analyze_data,
            category="insight",
            requires_plan="pro"
        ))

        self._register_tool(ToolDefinition(
            name="generate_insight",
            description="Generate actionable insights from analyzed data",
            input_schema={
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "context": {"type": "object"},
                    "analysis_results": {"type": "object"}
                },
                "required": ["message", "context"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "insights": {"type": "array"},
                    "priority": {"type": "string"},
                    "action_items": {"type": "array"}
                }
            },
            handler=InsightHandlers.generate_insight,
            category="insight",
            requires_plan="pro"
        ))

        self._register_tool(ToolDefinition(
            name="get_recommendations",
            description="Get personalized recommendations based on data",
            input_schema={
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "context": {"type": "object"},
                    "goal": {"type": "string"}
                },
                "required": ["message", "context"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "recommendations": {"type": "array"},
                    "rationale": {"type": "string"},
                    "expected_impact": {"type": "string"}
                }
            },
            handler=InsightHandlers.get_recommendations,
            category="insight",
            requires_plan="agency"
        ))

    # =========================================================================
    # Report Tools
    # =========================================================================

    def _register_report_tools(self) -> None:
        """Register report-related tools."""
        self._register_tool(ToolDefinition(
            name="generate_report",
            description="Generate a comprehensive report",
            input_schema={
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "context": {"type": "object"},
                    "report_type": {"type": "string"},
                    "time_range": {"type": "string"}
                },
                "required": ["message", "context"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "sections": {"type": "array"},
                    "generated_at": {"type": "string"}
                }
            },
            handler=ReportHandlers.generate_report,
            category="report",
            requires_plan="pro"
        ))

        self._register_tool(ToolDefinition(
            name="summarize_data",
            description="Create a concise summary of data",
            input_schema={
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "context": {"type": "object"},
                    "data": {"type": "object"},
                    "max_length": {"type": "integer"}
                },
                "required": ["message", "context"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "highlights": {"type": "array"},
                    "word_count": {"type": "integer"}
                }
            },
            handler=ReportHandlers.summarize_data,
            category="report",
            requires_plan="free"
        ))

    # =========================================================================
    # Memory Tools
    # =========================================================================

    def _register_memory_tools(self) -> None:
        """Register memory-related tools."""
        self._register_tool(ToolDefinition(
            name="recall_context",
            description="Recall relevant context from conversation history",
            input_schema={
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "context": {"type": "object"},
                    "lookup_type": {"type": "string"},
                    "limit": {"type": "integer"}
                },
                "required": ["message", "context"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "results": {"type": "array"},
                    "total_count": {"type": "integer"},
                    "has_more": {"type": "boolean"}
                }
            },
            handler=MemoryHandlers.recall_context,
            category="memory",
            requires_plan="free"
        ))

        self._register_tool(ToolDefinition(
            name="search_history",
            description="Search through historical data and conversations",
            input_schema={
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "context": {"type": "object"},
                    "query": {"type": "string"},
                    "filters": {"type": "object"}
                },
                "required": ["message", "context"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "results": {"type": "array"},
                    "total_count": {"type": "integer"},
                    "relevance_scores": {"type": "array"}
                }
            },
            handler=MemoryHandlers.search_history,
            category="memory",
            requires_plan="pro"
        ))

    # =========================================================================
    # Action Tools
    # =========================================================================

    def _register_action_tools(self) -> None:
        """Register action-related tools."""
        self._register_tool(ToolDefinition(
            name="execute_action",
            description="Execute a specific action on behalf of the user",
            input_schema={
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "context": {"type": "object"},
                    "action_type": {"type": "string"},
                    "parameters": {"type": "object"}
                },
                "required": ["message", "context", "action_type"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "executed": {"type": "boolean"},
                    "result": {},
                    "message": {"type": "string"}
                }
            },
            handler=ActionHandlers.execute_action,
            category="action",
            requires_plan="agency"
        ))

        self._register_tool(ToolDefinition(
            name="schedule_task",
            description="Schedule a task for future execution",
            input_schema={
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "context": {"type": "object"},
                    "task_type": {"type": "string"},
                    "schedule": {"type": "string"},
                    "parameters": {"type": "object"}
                },
                "required": ["message", "context", "task_type"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "scheduled": {"type": "boolean"},
                    "task_id": {"type": "string"},
                    "next_run": {"type": "string"}
                }
            },
            handler=ActionHandlers.schedule_task,
            category="action",
            requires_plan="agency"
        ))

    # =========================================================================
    # Search Tools
    # =========================================================================

    def _register_search_tools(self) -> None:
        """Register search-related tools."""
        self._register_tool(ToolDefinition(
            name="search_data",
            description="Search across all available data sources",
            input_schema={
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "context": {"type": "object"},
                    "query": {"type": "string"},
                    "sources": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["message", "context"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "results": {"type": "array"},
                    "sources_searched": {"type": "array"},
                    "total_matches": {"type": "integer"}
                }
            },
            handler=SearchHandlers.search_data,
            category="search",
            requires_plan="free"
        ))

    # =========================================================================
    # YouTube Tools
    # =========================================================================

    def _register_youtube_tools(self) -> None:
        """Register YouTube-specific analytics tools."""
        self._register_tool(ToolDefinition(
            name="get_channel_snapshot",
            description="Provide a summarized snapshot of a YouTube channel's performance for a given time period. Returns key metrics including subscribers, views, video count, CTR, and watch time.",
            input_schema={
                "type": "object",
                "properties": {
                    "channel_id": {
                        "type": "string",
                        "description": "The YouTube channel ID to get snapshot for"
                    },
                    "period": {
                        "type": "string",
                        "enum": ["last_7_days", "last_30_days", "last_90_days"],
                        "description": "Time period for the snapshot"
                    }
                },
                "required": ["channel_id", "period"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "subscribers": {"type": "integer", "description": "Total subscriber count"},
                    "views": {"type": "integer", "description": "Total views in the period"},
                    "videos": {"type": "integer", "description": "Number of videos published in the period"},
                    "avg_ctr": {"type": "number", "description": "Average click-through rate (percentage)"},
                    "avg_watch_time_minutes": {"type": "number", "description": "Average watch time in minutes"},
                    "period": {"type": "string", "description": "The time period for this snapshot"}
                },
                "required": ["subscribers", "views", "videos", "avg_ctr", "avg_watch_time_minutes", "period"]
            },
            handler=YouTubeHandlers.get_channel_snapshot,
            category="analytics",
            requires_plan="free"
        ))

        self._register_tool(ToolDefinition(
            name="get_top_videos",
            description="Return top-performing videos for a YouTube channel over a time period. Enables cross-video reasoning by providing detailed metrics for each video sorted by the specified criteria.",
            input_schema={
                "type": "object",
                "properties": {
                    "channel_id": {
                        "type": "string",
                        "description": "The YouTube channel ID to get top videos for"
                    },
                    "period": {
                        "type": "string",
                        "enum": ["last_7_days", "last_30_days"],
                        "description": "Time period for video performance analysis"
                    },
                    "sort_by": {
                        "type": "string",
                        "enum": ["views", "engagement", "ctr"],
                        "description": "Metric to sort videos by"
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 50,
                        "default": 10,
                        "description": "Maximum number of videos to return"
                    }
                },
                "required": ["channel_id", "period", "sort_by", "limit"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "videos": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "video_id": {"type": "string", "description": "YouTube video ID"},
                                "title": {"type": "string", "description": "Video title"},
                                "views": {"type": "integer", "description": "Total view count"},
                                "likes": {"type": "integer", "description": "Total like count"},
                                "comments": {"type": "integer", "description": "Total comment count"},
                                "engagement_rate": {"type": "number", "description": "Engagement rate as percentage"},
                                "published_at": {"type": "string", "format": "date-time", "description": "Video publish date in ISO format"}
                            },
                            "required": ["video_id", "title", "views", "likes", "comments", "engagement_rate", "published_at"]
                        },
                        "description": "List of top-performing videos"
                    }
                },
                "required": ["videos"]
            },
            handler=YouTubeHandlers.get_top_videos,
            category="analytics",
            requires_plan="free"
        ))

        self._register_tool(ToolDefinition(
            name="video_post_mortem",
            description="Analyze why a specific video underperformed or overperformed compared to a baseline. Provides data-driven reasons and actionable recommendations without hallucinating causes.",
            input_schema={
                "type": "object",
                "properties": {
                    "video_id": {
                        "type": "string",
                        "description": "The YouTube video ID to analyze"
                    },
                    "compare_with": {
                        "type": "string",
                        "enum": ["channel_average", "last_5_videos"],
                        "description": "Baseline to compare the video against"
                    }
                },
                "required": ["video_id", "compare_with"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "verdict": {
                        "type": "string",
                        "enum": ["underperformed", "overperformed", "average"],
                        "description": "Overall performance verdict compared to baseline"
                    },
                    "reasons": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Data-driven reasons explaining the verdict"
                    },
                    "action_items": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Actionable recommendations mapped one-to-one with reasons"
                    }
                },
                "required": ["verdict", "reasons", "action_items"]
            },
            handler=YouTubeHandlers.video_post_mortem,
            category="insight",
            requires_plan="pro"
        ))

        self._register_tool(ToolDefinition(
            name="weekly_growth_report",
            description="Generate a concise weekly growth analysis for a YouTube channel. Provides week-over-week comparison with concrete wins, losses, and strategic next actions.",
            input_schema={
                "type": "object",
                "properties": {
                    "channel_id": {
                        "type": "string",
                        "description": "The YouTube channel ID to analyze"
                    },
                    "week_start": {
                        "type": "string",
                        "format": "date",
                        "description": "Start date of the week to analyze (YYYY-MM-DD format)"
                    }
                },
                "required": ["channel_id", "week_start"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Concise summary with week-over-week change metrics"
                    },
                    "wins": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Concrete, metric-based wins from the week"
                    },
                    "losses": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Concrete, metric-based losses from the week"
                    },
                    "next_actions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Strategic and actionable recommendations for next week"
                    }
                },
                "required": ["summary", "wins", "losses", "next_actions"]
            },
            handler=YouTubeHandlers.weekly_growth_report,
            category="report",
            requires_plan="pro"
        ))

        # PRO-only: Fetch last video analytics for performance analysis
        self._register_tool(ToolDefinition(
            name="fetch_last_video_analytics",
            description="Fetch performance analytics for the most recently published video. Returns structured metrics including views, watch time, and engagement rate for AI-powered video analysis and recommendations. PRO-only feature.",
            input_schema={
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "context": {
                        "type": "object",
                        "description": "Context containing channel OAuth tokens (injected by executor)"
                    }
                },
                "required": ["context"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "data": {
                        "type": "object",
                        "properties": {
                            "video_id": {"type": "string", "description": "YouTube video ID"},
                            "title": {"type": "string", "description": "Video title"},
                            "published_at": {"type": "string", "format": "date-time", "description": "ISO format publish date"},
                            "views": {"type": "integer", "description": "Total view count"},
                            "avg_watch_time_seconds": {"type": "number", "description": "Average watch time in seconds"},
                            "engagement_rate": {"type": "number", "description": "Engagement rate as percentage ((likes + comments) / views * 100)"},
                            "likes": {"type": "integer", "description": "Total like count"},
                            "comments": {"type": "integer", "description": "Total comment count"}
                        },
                        "required": ["video_id", "title", "published_at", "views", "avg_watch_time_seconds", "engagement_rate"]
                    }
                }
            },
            handler=handle_fetch_last_video_analytics,
            category="analytics",
            requires_plan="pro"
        ))

    # =========================================================================
    # Registry Methods
    # =========================================================================

    def _register_tool(self, tool: ToolDefinition) -> None:
        """Register a tool in the registry."""
        self._tools[tool.name] = tool
        logger.debug(f"Registered tool: {tool.name}")

    def list_tools(self) -> list[str]:
        """Return list of all registered tool names."""
        return list(self._tools.keys())

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """Get a tool definition by name."""
        return self._tools.get(name)

    def get_tools_by_category(self, category: str) -> list[ToolDefinition]:
        """Get all tools in a specific category."""
        return [t for t in self._tools.values() if t.category == category]

    def get_tool_schema(self, name: str) -> Optional[dict[str, Any]]:
        """Get the combined input/output schema for a tool."""
        tool = self.get_tool(name)
        if not tool:
            return None

        return {
            "name": tool.name,
            "description": tool.description,
            "input": tool.input_schema,
            "output": tool.output_schema,
            "category": tool.category,
            "requires_plan": tool.requires_plan
        }

    async def execute_tool(
        self,
        tool_name: str,
        input_data: dict[str, Any]
    ) -> ToolResult:
        """
        Execute a tool by name.

        Args:
            tool_name: Name of the tool to execute
            input_data: Input data matching the tool's input schema

        Returns:
            ToolResult with success status and output
        """
        tool = self.get_tool(tool_name)
        if not tool:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error=f"Tool not found: {tool_name}"
            )

        try:
            output = await tool.handler(input_data)
            return ToolResult(
                tool_name=tool_name,
                success=True,
                output=output
            )
        except Exception as e:
            logger.exception(f"Tool execution failed: {tool_name}")
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error=str(e)
            )
