"""
Pydantic schemas for MCP server.

Defines all request/response models and tool input/output schemas.
"""

from datetime import datetime
from typing import Any, Optional, Union

from pydantic import BaseModel, Field


# =============================================================================
# Request/Response Schemas
# =============================================================================

class ExecuteRequest(BaseModel):
    """
    Request schema for the /execute endpoint.

    Contains all information needed to process a user's context request.
    """

    user_id: str = Field(
        ...,
        description="Unique identifier for the user making the request",
        min_length=1,
        max_length=128,
        examples=["user_abc123"]
    )

    channel_id: str = Field(
        ...,
        description="Channel/conversation context identifier",
        min_length=1,
        max_length=128,
        examples=["channel_xyz789"]
    )

    message: str = Field(
        ...,
        description="User's input message to process",
        min_length=1,
        max_length=10000,
        examples=["Show me the performance metrics for last week"]
    )

    metadata: Optional[dict[str, Any]] = Field(
        default=None,
        description="Optional additional context for the request",
        examples=[{"user_plan": "pro", "timezone": "UTC"}]
    )

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "user_abc123",
                "channel_id": "channel_xyz789",
                "message": "Give me insights on my channel's growth this month",
                "metadata": {"user_plan": "pro"}
            }
        }


class ExecuteResponse(BaseModel):
    """
    Response schema for the /execute endpoint.

    Contains the processed result along with execution metadata.
    """

    success: bool = Field(
        ...,
        description="Whether the execution completed successfully"
    )

    content: Optional[str] = Field(
        default=None,
        description="Main response content for the user"
    )

    content_type: str = Field(
        default="text",
        description="Type of content: text, analytics, insight, report, error"
    )

    tools_used: list[str] = Field(
        default_factory=list,
        description="List of tool names that were executed"
    )

    tool_outputs: Optional[dict[str, Any]] = Field(
        default=None,
        description="Structured outputs from tool executions"
    )

    metadata: Optional[dict[str, Any]] = Field(
        default=None,
        description="Execution metadata including timing and planning info"
    )

    error: Optional[Union[str, dict[str, Any]]] = Field(
        default=None,
        description="Error message or structured error object if execution failed"
    )

    structured_data: Optional[dict[str, Any]] = Field(
        default=None,
        description="Machine-readable structured data (e.g. analytics metrics, traffic sources)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "content": "Your channel grew by 15% this month...",
                "content_type": "insight",
                "tools_used": ["fetch_analytics", "generate_insight"],
                "tool_outputs": {
                    "data": {"growth": 15.2, "subscribers": 1250},
                    "insights": ["Strong growth in engagement"]
                },
                "metadata": {
                    "intent": "insight",
                    "confidence": 0.92
                }
            }
        }


class HealthResponse(BaseModel):
    """Response schema for health check endpoint."""

    status: str = Field(
        ...,
        description="Server health status"
    )

    version: str = Field(
        ...,
        description="API version"
    )

    llm_provider: str = Field(
        ...,
        description="Configured LLM provider"
    )


# =============================================================================
# Channel Connect Schemas (OAuth forwarding from API)
# =============================================================================

from uuid import UUID


class ChannelConnectRequest(BaseModel):
    """Request schema for /channels/connect endpoint.
    
    Receives OAuth channel connection data forwarded from the API
    after a successful YouTube OAuth flow.
    """

    user_id: UUID = Field(
        ...,
        description="User's unique identifier"
    )

    youtube_channel_id: str = Field(
        ...,
        description="YouTube channel ID",
        min_length=1,
        max_length=255
    )

    channel_name: str = Field(
        ...,
        description="YouTube channel display name",
        min_length=1,
        max_length=255
    )

    access_token: str = Field(
        ...,
        description="OAuth access token"
    )

    refresh_token: Optional[str] = Field(
        default=None,
        description="OAuth refresh token"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "550e8400-e29b-41d4-a716-446655440000",
                "youtube_channel_id": "UC_x5XG1OV2P6uZZ5FSM9Ttw",
                "channel_name": "My YouTube Channel",
                "access_token": "ya29.xxx...",
                "refresh_token": "1//xxx..."
            }
        }


class ChannelConnectResponse(BaseModel):
    """Response schema for /channels/connect endpoint."""

    success: bool = Field(
        ...,
        description="Whether the channel was connected successfully"
    )

    channel_id: str = Field(
        ...,
        description="YouTube channel ID"
    )

    channel_name: str = Field(
        ...,
        description="YouTube channel display name"
    )

    message: Optional[str] = Field(
        default=None,
        description="Additional status message"
    )


# =============================================================================
# Tool Input/Output Schemas
# =============================================================================

class ToolInputBase(BaseModel):
    """Base schema for tool inputs."""

    message: str = Field(
        ...,
        description="Original user message"
    )

    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Memory context for the tool"
    )


class AnalyticsInput(ToolInputBase):
    """Input schema for analytics-related tools."""

    time_range: Optional[str] = Field(
        default="7d",
        description="Time range for data: 1d, 7d, 30d, 90d, 1y"
    )

    metrics: Optional[list[str]] = Field(
        default=None,
        description="Specific metrics to fetch"
    )


class AnalyticsOutput(BaseModel):
    """Output schema for analytics tools."""

    data: dict[str, Any] = Field(
        ...,
        description="Raw analytics data"
    )

    period: str = Field(
        ...,
        description="Time period covered"
    )

    metrics: dict[str, float] = Field(
        default_factory=dict,
        description="Computed metrics"
    )


class InsightInput(ToolInputBase):
    """Input schema for insight generation tools."""

    data_source: Optional[str] = Field(
        default=None,
        description="Specific data source to analyze"
    )

    focus_area: Optional[str] = Field(
        default=None,
        description="Area to focus insights on"
    )


class InsightOutput(BaseModel):
    """Output schema for insight tools."""

    insights: list[str] = Field(
        ...,
        description="Generated insights"
    )

    recommendations: list[str] = Field(
        default_factory=list,
        description="Actionable recommendations"
    )

    confidence: float = Field(
        default=0.0,
        description="Confidence score for insights"
    )


class ReportInput(ToolInputBase):
    """Input schema for report generation tools."""

    report_type: str = Field(
        default="summary",
        description="Type of report: summary, detailed, executive"
    )

    time_range: str = Field(
        default="7d",
        description="Time range for report"
    )

    include_charts: bool = Field(
        default=False,
        description="Whether to include chart data"
    )


class ReportOutput(BaseModel):
    """Output schema for report tools."""

    title: str = Field(
        ...,
        description="Report title"
    )

    summary: str = Field(
        ...,
        description="Executive summary"
    )

    sections: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Report sections"
    )

    generated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Report generation timestamp"
    )


class MemoryInput(ToolInputBase):
    """Input schema for memory/context tools."""

    lookup_type: str = Field(
        default="conversation",
        description="Type of memory lookup: conversation, historical, search"
    )

    query: Optional[str] = Field(
        default=None,
        description="Search query for memory lookup"
    )

    limit: int = Field(
        default=10,
        description="Maximum number of results"
    )


class MemoryOutput(BaseModel):
    """Output schema for memory tools."""

    results: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Memory lookup results"
    )

    total_count: int = Field(
        default=0,
        description="Total available results"
    )

    has_more: bool = Field(
        default=False,
        description="Whether more results are available"
    )


class ActionInput(ToolInputBase):
    """Input schema for action execution tools."""

    action_type: str = Field(
        ...,
        description="Type of action to execute"
    )

    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Action parameters"
    )

    confirm: bool = Field(
        default=False,
        description="Whether action was confirmed by user"
    )


class ActionOutput(BaseModel):
    """Output schema for action tools."""

    executed: bool = Field(
        ...,
        description="Whether action was executed"
    )

    result: Optional[Any] = Field(
        default=None,
        description="Action result if executed"
    )

    message: str = Field(
        ...,
        description="Human-readable result message"
    )


# =============================================================================
# Channel Snapshot Schemas
# =============================================================================

from enum import Enum


class SnapshotPeriod(str, Enum):
    """Valid time periods for channel snapshots."""
    LAST_7_DAYS = "last_7_days"
    LAST_30_DAYS = "last_30_days"
    LAST_90_DAYS = "last_90_days"


class ChannelSnapshotInput(BaseModel):
    """
    Input schema for get_channel_snapshot tool.
    
    Provides a summarized snapshot of a YouTube channel's performance
    for a given time period.
    """

    channel_id: str = Field(
        ...,
        description="The YouTube channel ID to get snapshot for",
        min_length=1,
        max_length=128,
        examples=["UC_x5XG1OV2P6uZZ5FSM9Ttw"]
    )

    period: SnapshotPeriod = Field(
        ...,
        description="Time period for the snapshot",
        examples=["last_7_days", "last_30_days", "last_90_days"]
    )

    class Config:
        json_schema_extra = {
            "example": {
                "channel_id": "UC_x5XG1OV2P6uZZ5FSM9Ttw",
                "period": "last_30_days"
            }
        }


class ChannelSnapshotOutput(BaseModel):
    """
    Output schema for get_channel_snapshot tool.
    
    Contains key performance metrics for a YouTube channel
    over the specified time period.
    """

    subscribers: int = Field(
        ...,
        description="Total subscriber count",
        ge=0,
        examples=[12500]
    )

    views: int = Field(
        ...,
        description="Total views in the period",
        ge=0,
        examples=[85420]
    )

    videos: int = Field(
        ...,
        description="Number of videos published in the period",
        ge=0,
        examples=[8]
    )

    avg_ctr: float = Field(
        ...,
        description="Average click-through rate (percentage)",
        ge=0.0,
        le=100.0,
        examples=[5.75]
    )

    avg_watch_time_minutes: float = Field(
        ...,
        description="Average watch time in minutes",
        ge=0.0,
        examples=[7.25]
    )

    period: str = Field(
        ...,
        description="The time period for this snapshot",
        examples=["last_30_days"]
    )

    class Config:
        json_schema_extra = {
            "example": {
                "subscribers": 12500,
                "views": 85420,
                "videos": 8,
                "avg_ctr": 5.75,
                "avg_watch_time_minutes": 7.25,
                "period": "last_30_days"
            }
        }


# =============================================================================
# Top Videos Schemas
# =============================================================================

class TopVideosPeriod(str, Enum):
    """Valid time periods for top videos analysis."""
    LAST_7_DAYS = "last_7_days"
    LAST_30_DAYS = "last_30_days"


class TopVideosSortBy(str, Enum):
    """Valid sort criteria for top videos."""
    VIEWS = "views"
    ENGAGEMENT = "engagement"
    CTR = "ctr"


class TopVideosInput(BaseModel):
    """
    Input schema for get_top_videos tool.
    
    Returns top-performing videos for a channel over a time period
    to enable cross-video reasoning.
    """

    channel_id: str = Field(
        ...,
        description="The YouTube channel ID to get top videos for",
        min_length=1,
        max_length=128,
        examples=["UC_x5XG1OV2P6uZZ5FSM9Ttw"]
    )

    period: TopVideosPeriod = Field(
        ...,
        description="Time period for video performance analysis",
        examples=["last_7_days", "last_30_days"]
    )

    sort_by: TopVideosSortBy = Field(
        ...,
        description="Metric to sort videos by",
        examples=["views", "engagement", "ctr"]
    )

    limit: int = Field(
        default=10,
        description="Maximum number of videos to return",
        ge=1,
        le=50,
        examples=[10]
    )

    class Config:
        json_schema_extra = {
            "example": {
                "channel_id": "UC_x5XG1OV2P6uZZ5FSM9Ttw",
                "period": "last_30_days",
                "sort_by": "views",
                "limit": 10
            }
        }


class VideoPerformance(BaseModel):
    """Schema for individual video performance data."""

    video_id: str = Field(
        ...,
        description="YouTube video ID",
        examples=["dQw4w9WgXcQ"]
    )

    title: str = Field(
        ...,
        description="Video title",
        examples=["How to Grow Your YouTube Channel in 2026"]
    )

    views: int = Field(
        ...,
        description="Total view count",
        ge=0,
        examples=[125000]
    )

    likes: int = Field(
        ...,
        description="Total like count",
        ge=0,
        examples=[8500]
    )

    comments: int = Field(
        ...,
        description="Total comment count",
        ge=0,
        examples=[1200]
    )

    engagement_rate: float = Field(
        ...,
        description="Engagement rate as percentage ((likes + comments) / views * 100)",
        ge=0.0,
        examples=[7.76]
    )

    published_at: str = Field(
        ...,
        description="Video publish date in ISO format",
        examples=["2026-01-01T12:00:00Z"]
    )


class TopVideosOutput(BaseModel):
    """
    Output schema for get_top_videos tool.
    
    Contains a list of top-performing videos sorted by the specified metric.
    """

    videos: list[VideoPerformance] = Field(
        ...,
        description="List of top-performing videos"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "videos": [
                    {
                        "video_id": "dQw4w9WgXcQ",
                        "title": "How to Grow Your YouTube Channel in 2026",
                        "views": 125000,
                        "likes": 8500,
                        "comments": 1200,
                        "engagement_rate": 7.76,
                        "published_at": "2026-01-01T12:00:00Z"
                    },
                    {
                        "video_id": "abc123xyz",
                        "title": "Top 10 Content Creation Tips for Beginners",
                        "views": 98000,
                        "likes": 7200,
                        "comments": 890,
                        "engagement_rate": 8.26,
                        "published_at": "2025-12-28T10:30:00Z"
                    }
                ]
            }
        }


# =============================================================================
# Video Post-Mortem Schemas
# =============================================================================

class PostMortemCompareWith(str, Enum):
    """Valid baseline comparison options for video post-mortem."""
    CHANNEL_AVERAGE = "channel_average"
    LAST_5_VIDEOS = "last_5_videos"


class PostMortemVerdict(str, Enum):
    """Performance verdict options."""
    UNDERPERFORMED = "underperformed"
    OVERPERFORMED = "overperformed"
    AVERAGE = "average"


class VideoPostMortemInput(BaseModel):
    """
    Input schema for video_post_mortem tool.
    
    Analyzes why a specific video underperformed or overperformed
    compared to a baseline.
    """

    video_id: str = Field(
        ...,
        description="The YouTube video ID to analyze",
        min_length=1,
        max_length=64,
        examples=["dQw4w9WgXcQ"]
    )

    compare_with: PostMortemCompareWith = Field(
        ...,
        description="Baseline to compare the video against",
        examples=["channel_average", "last_5_videos"]
    )

    class Config:
        json_schema_extra = {
            "example": {
                "video_id": "dQw4w9WgXcQ",
                "compare_with": "channel_average"
            }
        }


class VideoPostMortemOutput(BaseModel):
    """
    Output schema for video_post_mortem tool.
    
    Contains data-driven analysis of video performance with
    actionable recommendations. Each reason maps one-to-one
    with an action item.
    
    Note: This output is designed for paid reports and avoids
    hallucinating causes not supported by actual data.
    """

    verdict: PostMortemVerdict = Field(
        ...,
        description="Overall performance verdict compared to baseline",
        examples=["underperformed", "overperformed", "average"]
    )

    reasons: list[str] = Field(
        ...,
        description="Data-driven reasons explaining the verdict. Each reason cites specific metrics.",
        min_length=1,
        examples=[
            [
                "CTR was 2.8% compared to channel average of 5.2% (-46% below baseline)",
                "Average view duration was 3.2 minutes vs channel average of 5.8 minutes (-45% retention drop)"
            ]
        ]
    )

    action_items: list[str] = Field(
        ...,
        description="Actionable recommendations mapped one-to-one with reasons",
        min_length=1,
        examples=[
            [
                "Test alternative thumbnail designs with A/B testing to improve CTR above 4%",
                "Analyze first 30 seconds of video for hook strength; consider restructuring intro"
            ]
        ]
    )

    class Config:
        json_schema_extra = {
            "example": {
                "verdict": "underperformed",
                "reasons": [
                    "CTR was 2.8% compared to channel average of 5.2% (-46% below baseline)",
                    "Average view duration was 3.2 minutes vs channel average of 5.8 minutes (-45% retention drop)",
                    "Impressions were 40% lower than channel average, indicating reduced algorithmic reach"
                ],
                "action_items": [
                    "Test alternative thumbnail designs with A/B testing to improve CTR above 4%",
                    "Analyze first 30 seconds of video for hook strength; consider restructuring intro",
                    "Review title keywords against trending search terms; optimize for discoverability"
                ]
            }
        }


# =============================================================================
# Weekly Growth Report Schemas
# =============================================================================

class WeeklyGrowthReportInput(BaseModel):
    """
    Input schema for weekly_growth_report tool.
    
    Generates a concise weekly growth analysis for a YouTube channel
    with week-over-week comparisons.
    """

    channel_id: str = Field(
        ...,
        description="The YouTube channel ID to analyze",
        min_length=1,
        max_length=128,
        examples=["UC_x5XG1OV2P6uZZ5FSM9Ttw"]
    )

    week_start: str = Field(
        ...,
        description="Start date of the week to analyze (YYYY-MM-DD format)",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        examples=["2026-01-01"]
    )

    class Config:
        json_schema_extra = {
            "example": {
                "channel_id": "UC_x5XG1OV2P6uZZ5FSM9Ttw",
                "week_start": "2026-01-01"
            }
        }


class WeeklyGrowthReportOutput(BaseModel):
    """
    Output schema for weekly_growth_report tool.
    
    Contains a structured weekly growth analysis with concrete,
    metric-based wins and losses, plus strategic next actions.
    """

    summary: str = Field(
        ...,
        description="Concise summary with week-over-week change metrics",
        examples=[
            "Week of Jan 01 - Jan 07, 2026: Your channel showed positive momentum with 48,000 views (+12.5% WoW) and 125 net subscribers (+8.7% WoW). Watch time totaled 2,250 hours."
        ]
    )

    wins: list[str] = Field(
        ...,
        description="Concrete, metric-based wins from the week",
        min_length=1,
        examples=[
            [
                "Views increased 12.5% week-over-week (42,000 → 48,000)",
                "Net subscriber growth up 8.7% (115 → 125 net new)",
                "CTR improved by 0.4 percentage points (5.1% → 5.5%)"
            ]
        ]
    )

    losses: list[str] = Field(
        ...,
        description="Concrete, metric-based losses from the week",
        min_length=1,
        examples=[
            [
                "Watch time declined 3.2% (2,100 → 2,033 hours)",
                "Average view duration decreased 0.3 minutes (5.8 → 5.5 min)"
            ]
        ]
    )

    next_actions: list[str] = Field(
        ...,
        description="Strategic and actionable recommendations for next week",
        min_length=1,
        examples=[
            [
                "A/B test 2-3 new thumbnail designs on your next upload to improve CTR",
                "Review retention graphs for top videos; strengthen intro hooks",
                "Capitalize on momentum by promoting top performer across social platforms"
            ]
        ]
    )

    class Config:
        json_schema_extra = {
            "example": {
                "summary": "Week of Jan 01 - Jan 07, 2026: Your channel showed positive momentum with 48,000 views (+12.5% WoW) and 125 net subscribers (+8.7% WoW). Watch time totaled 2,250 hours.",
                "wins": [
                    "Views increased 12.5% week-over-week (42,000 → 48,000)",
                    "Net subscriber growth up 8.7% (115 → 125 net new)",
                    "CTR improved by 0.4 percentage points (5.1% → 5.5%)"
                ],
                "losses": [
                    "Watch time declined 3.2% (2,100 → 2,033 hours)",
                    "Average view duration decreased 0.3 minutes (5.8 → 5.5 min)"
                ],
                "next_actions": [
                    "A/B test 2-3 new thumbnail designs on your next upload to improve CTR",
                    "Review retention graphs for top videos; strengthen intro hooks in next content",
                    "Capitalize on momentum by promoting top performer across social platforms",
                    "Add stronger CTAs for subscription in video outros and descriptions"
                ]
            }
        }
