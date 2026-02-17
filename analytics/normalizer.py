"""
YouTube Analytics Data Normalizer.

Converts raw YouTube Analytics API responses into snapshot-compatible format,
including extended metrics (CTR, retention, traffic sources).
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def normalize_traffic_sources(traffic_response: dict[str, Any]) -> dict[str, int] | None:
    """
    Normalize traffic source data from YouTube Analytics API.
    
    Args:
        traffic_response: Raw traffic source response from API.
        
    Returns:
        Dictionary mapping traffic source types to view counts,
        or None if data is unavailable.
        
    Example return value:
        {
            "YT_SEARCH": 1500,
            "SUGGESTED": 1200,
            "BROWSE_FEATURES": 800,
            "EXTERNAL": 357
        }
    """
    rows = traffic_response.get("rows", [])
    column_headers = traffic_response.get("columnHeaders", [])
    
    if not rows:
        logger.info("No traffic source data available")
        return None
    
    # Build column mapping
    column_map = {
        header["name"]: idx 
        for idx, header in enumerate(column_headers)
    }
    
    source_idx = column_map.get("insightTrafficSourceType")
    views_idx = column_map.get("views")
    
    if source_idx is None or views_idx is None:
        logger.info("Traffic source columns not found in response")
        return None
    
    # Aggregate views by traffic source
    traffic_sources: dict[str, int] = {}
    for row in rows:
        source_type = row[source_idx]
        views = int(row[views_idx])
        
        # Normalize source type names
        normalized_source = source_type.upper().replace(" ", "_")
        
        # Map common source types
        source_mapping = {
            "YT_SEARCH": "YT_SEARCH",
            "SUGGESTED": "SUGGESTED",
            "EXT_URL": "EXTERNAL",
            "EXTERNAL": "EXTERNAL",
            "BROWSE_FEATURES": "BROWSE_FEATURES",
            "NOTIFICATION": "NOTIFICATION",
            "PLAYLIST": "PLAYLIST",
            "END_SCREEN": "END_SCREEN",
            "CHANNEL": "CHANNEL",
            "SHORTS": "SHORTS",
            "NO_LINK_OTHER": "OTHER",
            "SUBSCRIBER": "SUBSCRIBER"
        }
        
        mapped_source = source_mapping.get(normalized_source, normalized_source)
        traffic_sources[mapped_source] = traffic_sources.get(mapped_source, 0) + views
    
    logger.info(f"Traffic sources normalized: {list(traffic_sources.keys())}")
    return traffic_sources


def normalize_analytics_response(
    raw_response: dict[str, Any],
    period: str = "last_7_days"
) -> dict[str, Any]:
    """
    Normalize raw YouTube Analytics API response to snapshot format.
    
    Converts the raw API response (with daily rows) into an aggregated
    snapshot format compatible with AnalyticsSnapshot model.
    
    Args:
        raw_response: Raw response from YouTube Analytics API.
            Can be either:
            - Simple response with 'rows' and 'columnHeaders'
            - Extended response with 'core_response' and 'traffic_response'
        period: The period that was fetched (default: "last_7_days").
        
    Returns:
        Normalized dictionary with aggregated metrics:
        {
            "period": period,
            "views": int,
            "impressions": int | None,
            "avg_ctr": float | None,
            "avg_watch_time_minutes": float,
            "avg_view_percentage": float | None,
            "subscribers": int,
            "traffic_sources": dict | None
        }
        
        Returns empty dict if no data available.
        
    Note:
        - Sums views, impressions, and subscribers across all days
        - Calculates weighted averages for CTR and view percentage
        - Missing metrics are set to None and logged at INFO level
    """
    # Handle extended response format
    if "core_response" in raw_response:
        core_response = raw_response["core_response"]
        traffic_response = raw_response.get("traffic_response", {})
        traffic_sources = normalize_traffic_sources(traffic_response)
        # Use period from response if available (it might be "7d" or "28d")
        response_period = raw_response.get("period")
        if response_period:
            period = "last_28_days" if response_period == "28d" else "last_7_days"
    else:
        core_response = raw_response
        traffic_sources = None
    
    rows = core_response.get("rows", [])
    column_headers = core_response.get("columnHeaders", [])
    
    if not rows:
        logger.warning("No analytics rows found in response, returning empty dict")
        return {}
    
    # Build column name to index mapping
    column_map = {
        header["name"]: idx 
        for idx, header in enumerate(column_headers)
    }
    
    logger.debug(f"Column headers: {list(column_map.keys())}")
    
    # Initialize aggregators
    total_views = 0
    total_impressions = 0
    total_watch_minutes = 0.0
    total_subscribers_gained = 0
    
    # For weighted average calculations
    weighted_ctr_sum = 0.0
    weighted_view_pct_sum = 0.0
    total_impressions_for_ctr = 0
    total_views_for_avg = 0
    
    # Track which metrics are available
    has_impressions = "videoThumbnailImpressions" in column_map
    has_ctr = "videoThumbnailImpressionsClickRate" in column_map
    has_view_percentage = "averageViewPercentage" in column_map
    
    if not has_impressions:
        logger.info("Missing metric detected: videoThumbnailImpressions")
    if not has_ctr:
        logger.info("Missing metric detected: videoThumbnailImpressionsClickRate")
    
    for row in rows:
        # Extract values using column indices
        views_idx = column_map.get("views")
        impressions_idx = column_map.get("videoThumbnailImpressions")
        watch_idx = column_map.get("estimatedMinutesWatched")
        subs_idx = column_map.get("subscribersGained")
        ctr_idx = column_map.get("videoThumbnailImpressionsClickRate")
        view_pct_idx = column_map.get("averageViewPercentage")
        
        # Aggregate core metrics
        day_views = 0
        if views_idx is not None:
            day_views = int(row[views_idx])
            total_views += day_views
            total_views_for_avg += day_views
            
        if impressions_idx is not None:
            day_impressions = int(row[impressions_idx])
            total_impressions += day_impressions
            total_impressions_for_ctr += day_impressions
            
            # Weight CTR by impressions
            if ctr_idx is not None:
                day_ctr = float(row[ctr_idx])
                weighted_ctr_sum += day_ctr * day_impressions
                
        if watch_idx is not None:
            total_watch_minutes += float(row[watch_idx])
            
        if subs_idx is not None:
            total_subscribers_gained += int(row[subs_idx])
            
        # Weight view percentage by views
        if view_pct_idx is not None and day_views > 0:
            day_view_pct = float(row[view_pct_idx])
            weighted_view_pct_sum += day_view_pct * day_views
    
    # Calculate averages
    if total_views > 0:
        avg_watch_time_minutes = total_watch_minutes / total_views
    else:
        avg_watch_time_minutes = 0.0
        logger.warning("Total views is 0, setting avg_watch_time_minutes to 0.0")
    
    # Calculate weighted average CTR
    avg_ctr: float | None = None
    if has_ctr and total_impressions_for_ctr > 0:
        avg_ctr = weighted_ctr_sum / total_impressions_for_ctr
    elif has_ctr:
        avg_ctr = 0.0
        
    # Calculate weighted average view percentage
    avg_view_percentage: float | None = None
    if has_view_percentage and total_views_for_avg > 0:
        avg_view_percentage = weighted_view_pct_sum / total_views_for_avg
    elif has_view_percentage:
        avg_view_percentage = 0.0
    
    normalized = {
        "period": period,
        "views": total_views,
        "impressions": total_impressions if has_impressions else None,
        "subscribers": total_subscribers_gained,
        "avg_ctr": round(avg_ctr, 4) if avg_ctr is not None else None,
        "avg_watch_time_minutes": round(avg_watch_time_minutes, 2),
        "avg_view_percentage": round(avg_view_percentage, 2) if avg_view_percentage is not None else None,
        "traffic_sources": traffic_sources
    }
    
    logger.info(
        f"Fetched analytics: views={total_views} ctr={avg_ctr} retention={avg_view_percentage}"
    )
    logger.info(f"Analytics snapshot persisted for normalized data")
    
    return normalized
