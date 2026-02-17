"""
fetch_analytics MCP Tool.

Fetches real YouTube Analytics data including extended metrics,
normalizes it, and persists it as an AnalyticsSnapshot to the database.
"""

import logging
from typing import Any
from uuid import UUID

from analytics.fetcher import fetch_analytics_for_channel
from analytics.normalizer import normalize_analytics_response
from db.models.analytics_snapshot import AnalyticsSnapshot
from memory.postgres_store import postgres_store
from registry.base import ToolResult

logger = logging.getLogger(__name__)


async def handle_fetch_analytics(input_data: dict[str, Any]) -> dict[str, Any]:
    """
    Handle the fetch_analytics tool execution.
    
    Fetches real YouTube Analytics data using the OAuth access_token
    from context["channel"], normalizes the response (including CTR,
    retention, and traffic sources), and persists it as an AnalyticsSnapshot.
    
    Args:
        input_data: Dictionary containing:
            - context: Dict with "channel" key containing OAuth tokens
            
    Returns:
        Dict with normalized analytics data.
    """
    # Extract channel from context (injected by executor)
    context = input_data.get("context", {})
    channel_data = context.get("channel")
    
    if not channel_data:
        logger.warning("fetch_analytics called without channel context")
        raise ValueError("No channel context available. Please connect a YouTube channel first.")
    
    channel_id = channel_data.get("id")
    access_token = channel_data.get("access_token")
    channel_name = channel_data.get("channel_name", "Unknown")
    
    if not channel_id:
        logger.error("Channel context missing 'id' field")
        raise ValueError("Channel context is incomplete (missing id)")
    
    if not access_token:
        logger.error(f"No access_token for channel {channel_name}")
        raise ValueError("Channel has no access_token. Please reconnect YouTube.")
    
    # Convert to UUID if string
    if isinstance(channel_id, str):
        channel_uuid = UUID(channel_id)
    else:
        channel_uuid = channel_id
    
    logger.info(f"Fetching analytics for channel {channel_name} ({channel_uuid})")
    
    # Extract refresh_token for automatic token refresh
    refresh_token = channel_data.get("refresh_token")
    
    # Determine period — default 7d, planner may request 28d
    period = input_data.get("period", "7d")
    
    # Step 1: Fetch analytics from YouTube Analytics API
    try:
        raw_response = fetch_analytics_for_channel(
            access_token=access_token,
            refresh_token=refresh_token,
            period=period
        )
        logger.info(f"API response received: core metrics and traffic sources fetched (period={period})")
    except Exception as api_error:
        logger.error(f"YouTube Analytics API error: {api_error}")
        raise RuntimeError(f"YouTube Analytics API error: {str(api_error)}")
    
    # Step 2: Normalize the response
    normalized = normalize_analytics_response(raw_response, period=period)
    
    if not normalized:
        logger.warning(f"No analytics data available for channel {channel_uuid}")
        return {
            "message": "No analytics data available yet. "
                       "Data may take 24-48 hours to appear for new channels.",
            "data": {}
        }
    
    # Step 2b: If compare_periods is set, also fetch 7d data for comparison
    normalized_7d = None
    if input_data.get("compare_periods") and period == "28d":
        try:
            raw_response_7d = fetch_analytics_for_channel(
                access_token=access_token,
                refresh_token=refresh_token,
                period="7d"
            )
            normalized_7d = normalize_analytics_response(raw_response_7d, period="last_7_days")
            logger.info("Also fetched 7d data for period comparison")
        except Exception as e:
            logger.warning(f"Failed to fetch 7d comparison data: {e}")
    
    # Log fetched metrics
    logger.info(
        f"Fetched analytics: views={normalized.get('views')} "
        f"ctr={normalized.get('avg_ctr')} "
        f"retention={normalized.get('avg_view_percentage')}"
    )
    
    # Step 3: Create and persist AnalyticsSnapshot
    snapshot = AnalyticsSnapshot(
        channel_id=channel_uuid,
        period=normalized["period"],
        views=normalized["views"],
        subscribers=normalized["subscribers"],
        avg_ctr=normalized.get("avg_ctr"),
        avg_watch_time_minutes=normalized["avg_watch_time_minutes"],
        impressions=normalized.get("impressions"),
        avg_view_percentage=normalized.get("avg_view_percentage"),
        traffic_sources=normalized.get("traffic_sources")
    )
    
    postgres_store.save_analytics_snapshot(snapshot)
    logger.info(f"Analytics snapshot persisted for channel {channel_uuid}")
    
    # Build output with optional comparison data
    output_data = {
        "message": "Analytics fetched and persisted successfully",
        "data": normalized
    }
    if normalized_7d:
        output_data["data_7d"] = normalized_7d
    
    return output_data
