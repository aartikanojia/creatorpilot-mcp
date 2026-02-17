"""
Shared pytest fixtures for the MCP test suite.

Provides reusable fixtures for:
- ExecutionPlanner instances
- Mock channel/memory contexts
- Mock analytics data
- Mock Redis clients
- Mock LLM responses
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from executor.planner import ExecutionPlanner


# =============================================================================
# Planner Fixtures
# =============================================================================

@pytest.fixture
def planner():
    """Fresh ExecutionPlanner instance."""
    return ExecutionPlanner()


@pytest.fixture
def available_tools():
    """List of all registered tool names."""
    return [
        "fetch_analytics",
        "compute_metrics",
        "generate_chart",
        "analyze_data",
        "generate_insight",
        "get_recommendations",
        "generate_report",
        "summarize_data",
        "recall_context",
        "search_history",
        "execute_action",
        "schedule_task",
        "search_data",
        "fetch_last_video_analytics",
    ]


# =============================================================================
# Memory Context Fixtures
# =============================================================================

@pytest.fixture
def empty_context():
    """Empty memory context — no channel connected."""
    return {}


@pytest.fixture
def channel_context():
    """Memory context with an active channel connection."""
    return {
        "channel": {
            "id": "test-channel-uuid",
            "youtube_channel_id": "UC_test_channel",
            "channel_name": "Aarti Kanojia",
            "access_token": "ya29.test-token",
            "refresh_token": "1//test-refresh",
        }
    }


# =============================================================================
# Analytics Data Fixtures
# =============================================================================

@pytest.fixture
def mock_analytics_data():
    """Realistic analytics data fixture."""
    return {
        "current_period": {
            "period": "last_28_days",
            "views": 8801,
            "subscribers_gained": 5,
            "avg_view_percentage": 52.9,
            "avg_watch_time_minutes": 0.4,
            "traffic_sources": {
                "YT_SHORTS": 7200,
                "SUBSCRIBER": 800,
                "EXT_URL": 500,
                "YT_SEARCH": 200,
                "NOTIFICATION": 101,
            },
        },
        "period_7d": {
            "period": "last_7_days",
            "views": 1802,
            "subscribers_gained": 2,
            "avg_view_percentage": 48.5,
            "avg_watch_time_minutes": 0.3,
        },
    }


@pytest.fixture
def mock_video_analytics():
    """Realistic last-video analytics fixture."""
    return {
        "video_id": "37wyGQMw9Q4",
        "title": "Mihir ki masti #play",
        "published_at": "2025-02-10T08:00:00Z",
        "views": 1802,
        "avg_view_percentage": 52.9,
        "avg_watch_time_minutes": 0.1,
        "subscribers_gained": 2,
        "likes": 45,
        "comments": 3,
    }


# =============================================================================
# Response Quality Fixtures
# =============================================================================

@pytest.fixture
def sample_good_response():
    """A well-formed response following the premium template."""
    return """**Why This Video Took Off**

This video significantly outperformed your recent uploads, doubling its reach compared to last week. The momentum suggests strong topic-market alignment and improved discoverability.

**Performance Snapshot**

The video accumulated 1,802 views over the past seven days, representing a 100% growth rate over the prior period. This velocity indicates that the content resonated beyond your existing subscriber base, pulling in external traffic at a meaningful scale.

**Why It Worked**

The title "Mihir ki masti #play" taps into a playful, relatable theme that performs well in the Shorts ecosystem. The informal, personal framing likely drove curiosity clicks from browse and Shorts feed surfaces. The hashtag usage improved discoverability within YouTube's topic clustering.

The timing also contributed — uploading during a period of lower competition in your niche allowed the algorithm to surface the content more aggressively. The strong initial retention signal likely triggered a recommendation loop.

**Replication Strategy**

Repeat the personal, informal hook style in your next upload. The "masti" framing works because it sets an emotional expectation — viewers know they are getting lighthearted content.

Test a variation: keep the same emotional register but shift the subject matter slightly. For example, "Mihir ki masti #cooking" or "Mihir ki masti #travel" to see if the format transfers across topics.

Build a three-video arc around this theme. Release them within 10 days of each other to compound algorithmic momentum.

**Next Move**

Produce a follow-up within 5 days using the same title structure and emotional angle. The algorithm is currently favoring this content style for your channel — capitalize on this window before the signal decays."""


@pytest.fixture
def sample_bad_response():
    """A response with multiple quality violations."""
    return """Great question! 🎉 Let me analyze video ID 37wyGQMw9Q4 for you!

| Metric | Value |
|--------|-------|
| Views  | 1,802 |
| Growth | 100%  |

Here are the analytics data from fetch_analytics tool:
```json
{"views": 1802, "growth": 100}
```

You asked me to "Analyze my top video from the last 7 days" so here is my analysis.

The views are 1,802. The growth is 100%. The views are 1,802 which means you got 1,802 views.

You might want to consider improving your thumbnails. It could be that your titles need work. Perhaps you should post more often. I think you should try to make better content."""
"""
"""
