"""
MCP Server - FastAPI Application

This is the main entry point for the Model Context Protocol server.
It exposes HTTP endpoints for context orchestration and tool execution.

Business logic is delegated to the executor module - this file only handles:
- API routing
- Request/response handling
- Middleware configuration
- Health checks
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from config import config
from registry.schemas import ExecuteRequest, ExecuteResponse, HealthResponse
from executor.execute import execute_context_request


# Configure logging
logging.basicConfig(
    level=getattr(logging, config.server.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan handler for startup/shutdown events.

    Initializes connections and validates configuration on startup.
    Cleans up resources on shutdown.
    """
    # Startup
    logger.info("Starting MCP Server...")

    # Validate configuration
    warnings = config.validate()
    for warning in warnings:
        logger.warning(f"Config warning: {warning}")

    logger.info(f"Server configured for {config.llm.provider} LLM provider")
    logger.info(f"Debug mode: {config.server.debug}")

    yield

    # Shutdown
    logger.info("Shutting down MCP Server...")


# Initialize FastAPI application
app = FastAPI(
    title="Context Hub MCP Server",
    description="Model Context Protocol server for AI agent context orchestration",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if config.server.debug else None,
    redoc_url="/redoc" if config.server.debug else None,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.server.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check() -> HealthResponse:
    """
    Health check endpoint for container orchestration.

    Returns:
        HealthResponse with server status
    """
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        llm_provider=config.llm.provider
    )


@app.post("/execute", response_model=ExecuteResponse, tags=["Execution"])
async def execute(request: ExecuteRequest) -> ExecuteResponse:
    """
    Main execution endpoint for MCP context requests.

    Accepts a user message and context identifiers, orchestrates tool execution,
    memory retrieval, and LLM processing to produce a contextual response.

    Args:
        request: ExecuteRequest containing user_id, channel_id, and message

    Returns:
        ExecuteResponse with the processed result and metadata

    Raises:
        HTTPException: On validation or processing errors
    """
    logger.info(
        f"Execute request: user={request.user_id}, "
        f"channel={request.channel_id}, "
        f"message_length={len(request.message)}"
    )

    try:
        response = await execute_context_request(
            user_id=request.user_id,
            channel_id=request.channel_id,
            message=request.message,
            metadata=request.metadata
        )

        logger.info(
            f"Execute completed: tools_used={response.tools_used}, "
            f"success={response.success}"
        )

        return response

    except ValueError as e:
        logger.warning(f"Validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except PermissionError as e:
        logger.warning(f"Access denied: {e}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except Exception as e:
        logger.exception(f"Execution error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during execution"
        )


@app.get("/", tags=["System"])
async def root() -> dict[str, str]:
    """Root endpoint with API information."""
    return {
        "service": "Context Hub MCP Server",
        "version": "1.0.0",
        "docs": "/docs" if config.server.debug else "Disabled in production"
    }


# =============================================================================
# User Plan Status Endpoint (lightweight, no usage increment)
# =============================================================================

FREE_DAILY_LIMIT = 3  # Must match executor/execute.py

@app.get("/api/v1/user/status", tags=["User"])
async def get_user_status(user_id: str):
    """
    Return user plan and current usage without incrementing.
    Called on frontend mount so the UI badge is correct immediately.
    """
    user_plan = "free"

    # FORCE_PRO_MODE override
    if config.flags.force_pro_mode:
        user_plan = "pro"

    if user_plan == "pro":
        return {
            "user_plan": "pro",
            "usage": None
        }

    # Read current usage from Redis (GET, not INCR)
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    usage_key = f"usage:{user_id}:{today}"

    usage_count = 0
    try:
        from memory.redis_store import ShortTermMemory
        store = ShortTermMemory()
        client = await store._ensure_connection()
        raw = await client.get(usage_key)
        if raw is not None:
            usage_count = int(raw)
    except Exception as e:
        logger.error(f"Redis read failed for user status (allowing default): {e}")

    is_exhausted = usage_count >= FREE_DAILY_LIMIT

    return {
        "user_plan": user_plan,
        "usage": {
            "used": min(usage_count, FREE_DAILY_LIMIT),
            "limit": FREE_DAILY_LIMIT,
            "exhausted": is_exhausted
        }
    }


# =============================================================================
# Channel Connect Endpoint (OAuth forwarding from API)
# =============================================================================

from datetime import datetime
from fastapi import Depends
from sqlalchemy.orm import Session
from db.session import get_db
from db.models.channel import Channel
from registry.schemas import ChannelConnectRequest, ChannelConnectResponse


@app.post(
    "/channels/connect",
    response_model=ChannelConnectResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Channels"]
)
def connect_channel(
    request: ChannelConnectRequest,
    db: Session = Depends(get_db),
) -> ChannelConnectResponse:
    """Connect a YouTube channel after OAuth flow.
    
    Receives OAuth channel data forwarded from the API and persists
    the channel connection. Uses upsert logic to handle reconnections.
    
    Args:
        request: ChannelConnectRequest with OAuth tokens and channel info
        db: Database session
    
    Returns:
        ChannelConnectResponse with connection status
    """
    logger.info(
        f"Channel connect request: user={request.user_id}, "
        f"channel_id={request.youtube_channel_id}"
    )
    
    try:
        # Check if channel already exists for this user
        existing_channel = db.query(Channel).filter(
            Channel.user_id == request.user_id,
            Channel.youtube_channel_id == request.youtube_channel_id
        ).first()
        
        if existing_channel:
            # Update existing channel with new tokens
            existing_channel.channel_name = request.channel_name
            existing_channel.access_token = request.access_token
            if request.refresh_token:
                existing_channel.refresh_token = request.refresh_token
            existing_channel.updated_at = datetime.utcnow()
            
            db.commit()
            logger.info(f"Updated existing channel for user_id={request.user_id}")
            
            return ChannelConnectResponse(
                success=True,
                channel_id=request.youtube_channel_id,
                channel_name=request.channel_name,
                message="Channel reconnected successfully"
            )
        else:
            # Create new channel connection
            new_channel = Channel(
                user_id=request.user_id,
                youtube_channel_id=request.youtube_channel_id,
                channel_name=request.channel_name,
                access_token=request.access_token,
                refresh_token=request.refresh_token,
            )
            db.add(new_channel)
            db.commit()
            
            logger.info(f"Created new channel for user_id={request.user_id}")
            
            return ChannelConnectResponse(
                success=True,
                channel_id=request.youtube_channel_id,
                channel_name=request.channel_name,
                message="Channel connected successfully"
            )
    
    except Exception as e:
        db.rollback()
        logger.exception(f"Channel connect failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to connect channel"
        )


# =============================================================================
# Channel Stats Endpoint (Real YouTube Data)
# =============================================================================

import os
import httpx
from analytics.fetcher import AnalyticsFetcher
from clients.youtube_analytics import YouTubeAnalyticsClient

YOUTUBE_DATA_API_URL = "https://www.googleapis.com/youtube/v3/channels"


@app.get(
    "/channels/{user_id}/stats",
    tags=["Channels"],
    summary="Get real YouTube channel statistics",
)
async def get_channel_stats(
    user_id: str,
    period: str = "7d",
    db: Session = Depends(get_db),
) -> dict:
    """Fetch real YouTube channel statistics for dashboard KPI cards.

    Queries:
    1. YouTube Data API for subscriber count, total views, video count
    2. YouTube Analytics API for daily views and avg watch time

    Args:
        user_id: User UUID
        period: Time period — "7d", "30d", or "6m"
        db: Database session

    Returns:
        Dictionary with subscriberCount, viewCount, videoCount, avgWatchTimeMinutes, dailyViews
    """
    import uuid as uuid_mod

    # Validate user_id
    try:
        user_uuid = uuid_mod.UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user_id format",
        )

    # Map period to days
    period_days_map = {"7d": 7, "30d": 30, "6m": 180}
    days = period_days_map.get(period, 7)

    # Look up connected channel
    channel = db.query(Channel).filter(
        Channel.user_id == user_uuid
    ).first()

    if not channel or not channel.access_token:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No connected YouTube channel found",
        )

    # --- Step 1: Fetch channel statistics from YouTube Data API ---
    subscriber_count = 0
    view_count = 0
    video_count = 0

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                YOUTUBE_DATA_API_URL,
                params={"part": "statistics", "mine": "true"},
                headers={"Authorization": f"Bearer {channel.access_token}"},
            )

            if resp.status_code == 200:
                items = resp.json().get("items", [])
                if items:
                    stats = items[0].get("statistics", {})
                    subscriber_count = int(stats.get("subscriberCount", 0))
                    view_count = int(stats.get("viewCount", 0))
                    video_count = int(stats.get("videoCount", 0))
            else:
                logger.warning(
                    f"YouTube Data API returned {resp.status_code}: {resp.text[:200]}"
                )
    except Exception as e:
        logger.warning(f"Failed to fetch YouTube Data API stats: {e}")

    # --- Step 2: Fetch analytics from YouTube Analytics API ---
    avg_watch_time_minutes = 0.0
    daily_views: list[dict] = []
    daily_subscribers: list[dict] = []

    try:
        google_client_id = os.getenv("GOOGLE_CLIENT_ID")
        google_client_secret = os.getenv("GOOGLE_CLIENT_SECRET")

        yt_client = YouTubeAnalyticsClient(
            access_token=channel.access_token,
            refresh_token=channel.refresh_token,
            client_id=google_client_id,
            client_secret=google_client_secret,
        )
        fetcher = AnalyticsFetcher(yt_client)

        # Use _get_date_range with the requested number of days
        start_str, end_str = fetcher._get_date_range(days=days)
        response = fetcher.client.query_reports(
            start_date=start_str,
            end_date=end_str,
            metrics="views,averageViewDuration,averageViewPercentage,estimatedMinutesWatched,subscribersGained",
            dimensions="day",
            sort="day",
        )

        rows = response.get("rows", [])
        headers = [h.get("name") for h in response.get("columnHeaders", [])]

        # Extract avg watch time
        if rows and "averageViewDuration" in headers:
            avg_idx = headers.index("averageViewDuration")
            total_duration = sum(row[avg_idx] for row in rows)
            avg_watch_time_minutes = round(total_duration / len(rows) / 60, 1)

        # Extract daily views for chart
        if rows and "day" in headers and "views" in headers:
            day_idx = headers.index("day")
            views_idx = headers.index("views")
            daily_views = [
                {"date": row[day_idx], "views": int(row[views_idx])}
                for row in rows
            ]

        # Extract daily subscribers for sparkline chart
        if rows and "day" in headers and "subscribersGained" in headers:
            day_idx = headers.index("day")
            subs_idx = headers.index("subscribersGained")
            daily_subscribers = [
                {"date": row[day_idx], "subscribers": int(row[subs_idx])}
                for row in rows
            ]

        # --- Step 3: Fetch traffic sources ---
        try:
            from analytics.normalizer import normalize_traffic_sources

            raw_traffic = fetcher.fetch_traffic_sources(days=days)
            normalized = normalize_traffic_sources(raw_traffic)

            if normalized:
                total_views_traffic = sum(normalized.values())
                traffic_sources = [
                    {
                        "name": source,
                        "views": views,
                        "percentage": round(views / total_views_traffic * 100, 1)
                        if total_views_traffic > 0
                        else 0,
                    }
                    for source, views in sorted(
                        normalized.items(), key=lambda x: x[1], reverse=True
                    )
                ]
            else:
                traffic_sources = []
        except Exception as e:
            logger.warning(f"Failed to fetch traffic sources: {e}")
            traffic_sources = []

    except Exception as e:
        logger.warning(f"Failed to fetch YouTube Analytics stats: {e}")
        traffic_sources = []

    return {
        "subscriberCount": subscriber_count,
        "viewCount": view_count,
        "videoCount": video_count,
        "avgWatchTimeMinutes": avg_watch_time_minutes,
        "dailyViews": daily_views,
        "dailySubscribers": daily_subscribers,
        "trafficSources": traffic_sources,
        "period": period,
    }

# =============================================================================
# Top Video Endpoint — Most Watched Video in Period
# =============================================================================

YOUTUBE_VIDEOS_API_URL = "https://www.googleapis.com/youtube/v3/videos"


@app.get(
    "/analytics/top-video",
    tags=["Analytics"],
    summary="Get most watched video for a period",
)
async def get_top_video(
    user_id: str,
    period: str = "7d",
    db: Session = Depends(get_db),
) -> dict:
    """Fetch the most-watched video for the given period.

    Uses YouTube Analytics API (dimensions=video, sort=-views) to find
    the top video, then YouTube Data API to get title and thumbnail.
    """
    import uuid as uuid_mod
    from datetime import datetime as dt, timedelta, timezone

    empty = {
        "video_id": None,
        "title": None,
        "thumbnail_url": None,
        "views": 0,
        "growth_percentage": 0,
    }

    # Validate user_id
    try:
        user_uuid = uuid_mod.UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user_id format",
        )

    period_days_map = {"7d": 7, "30d": 30, "6m": 180}
    days = period_days_map.get(period, 7)

    # Look up connected channel
    channel = db.query(Channel).filter(Channel.user_id == user_uuid).first()

    if not channel or not channel.access_token:
        return empty

    try:
        google_client_id = os.getenv("GOOGLE_CLIENT_ID")
        google_client_secret = os.getenv("GOOGLE_CLIENT_SECRET")

        yt_client = YouTubeAnalyticsClient(
            access_token=channel.access_token,
            refresh_token=channel.refresh_token,
            client_id=google_client_id,
            client_secret=google_client_secret,
        )

        # Step 1: Use Analytics API to find top video by views
        end_date = dt.now(timezone.utc).date() - timedelta(days=1)
        cur_start = end_date - timedelta(days=days - 1)

        top_resp = yt_client.query_reports(
            start_date=cur_start.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d"),
            metrics="views,estimatedMinutesWatched",
            dimensions="video",
            sort="-views",
            max_results=10,
        )
        top_rows = top_resp.get("rows", [])
        if not top_rows:
            logger.info("No top video rows returned from Analytics API")
            return empty

        video_id = top_rows[0][0]
        period_views = int(top_rows[0][1])

        logger.info(f"Top video: {video_id} with {period_views} views in {days}d")

        # Step 2: Get video details via Data API (title, thumbnail)
        title = "Untitled Video"
        thumbnail_url = ""
        total_views = period_views

        auth_headers = {"Authorization": f"Bearer {channel.access_token}"}

        async with httpx.AsyncClient(timeout=10) as client:
            video_resp = await client.get(
                YOUTUBE_VIDEOS_API_URL,
                params={
                    "part": "snippet,statistics",
                    "id": video_id,
                },
                headers=auth_headers,
            )

            if video_resp.status_code == 200:
                v_items = video_resp.json().get("items", [])
                if v_items:
                    snippet = v_items[0].get("snippet", {})
                    stats = v_items[0].get("statistics", {})
                    title = snippet.get("title", "Untitled Video")
                    thumbs = snippet.get("thumbnails", {})
                    thumbnail_url = (
                        thumbs.get("medium", {}).get("url")
                        or thumbs.get("default", {}).get("url", "")
                    )
                    total_views = int(stats.get("viewCount", period_views))
            else:
                logger.warning(
                    f"YouTube Videos API returned {video_resp.status_code}: "
                    f"{video_resp.text[:200]}"
                )

        # Step 3: Compute growth % (current vs previous period)
        growth_percentage = 0.0
        try:
            prev_end = cur_start - timedelta(days=1)
            prev_start = prev_end - timedelta(days=days - 1)

            prev_resp = yt_client.query_reports(
                start_date=prev_start.strftime("%Y-%m-%d"),
                end_date=prev_end.strftime("%Y-%m-%d"),
                metrics="views",
                filters=f"video=={video_id}",
            )
            prev_rows = prev_resp.get("rows", [])
            prev_views = prev_rows[0][0] if prev_rows else 0

            if prev_views > 0:
                growth_percentage = round(
                    ((period_views - prev_views) / prev_views) * 100, 1
                )
            elif period_views > 0:
                growth_percentage = 100.0
        except Exception as e:
            logger.warning(f"Failed to compute growth % for top video: {e}")

        return {
            "video_id": video_id,
            "title": title,
            "thumbnail_url": thumbnail_url,
            "views": total_views,
            "growth_percentage": growth_percentage,
        }

    except Exception as e:
        logger.exception(f"Failed to fetch top video: {e}")
        return empty



if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "server:app",
        host=config.server.host,
        port=config.server.port,
        reload=config.server.debug,
        log_level=config.server.log_level.lower()
    )
