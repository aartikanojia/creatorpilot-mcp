"""
YouTube Analytics Data Fetcher.

Fetches analytics data from the YouTube Analytics API for the last 7 days,
including extended metrics (CTR, retention, traffic sources).
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from clients.youtube_analytics import YouTubeAnalyticsClient

logger = logging.getLogger(__name__)

# Core metrics for channel/video performance
# Note: Impression/CTR metrics (videoThumbnailImpressions,
# videoThumbnailImpressionsClickRate) are NOT supported in the
# YouTube Analytics API v2 basic channel report with day dimension.
# They are only available via the YouTube Reporting API (bulk).
METRICS_CORE = (
    "views,"
    "averageViewDuration,"
    "averageViewPercentage,"
    "estimatedMinutesWatched,"
    "subscribersGained"
)

# Traffic source metrics
METRICS_TRAFFIC = "views"
DIMENSIONS_TRAFFIC = "insightTrafficSourceType"


class AnalyticsFetcher:
    """
    Fetches YouTube Analytics data for a channel.
    
    Uses the YouTube Analytics API to retrieve metrics for the last 7 days,
    including impressions, CTR, view percentage, and traffic sources.
    """
    
    def __init__(self, client: YouTubeAnalyticsClient) -> None:
        """
        Initialize the fetcher with a YouTube Analytics client.
        
        Args:
            client: Authenticated YouTubeAnalyticsClient instance.
        """
        self.client = client
        logger.debug("AnalyticsFetcher initialized")
    
    def _get_date_range(
        self, days: int = 7
    ) -> tuple[str, str]:
        """
        Calculate date range for the last N days (excluding today).
        
        Args:
            days: Number of days to look back (default: 7).
        
        Returns:
            Tuple of (start_date, end_date) in YYYY-MM-DD format.
        """
        today = datetime.utcnow().date()
        # YouTube Analytics has a 2-3 day lag.
        # shifting the window back by 3 days ensures we get a complete dataset
        # closer to the requested 'days' count, rather than missing the last few days.
        end_date = today - timedelta(days=3)
        start_date = end_date - timedelta(days=days - 1)  # inclusive range
        return start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")
    
    def fetch_last_7_days(self) -> dict[str, Any]:
        """
        Fetch analytics data for the last 7 days.
        
        Retrieves views, impressions, CTR, watch time, view percentage,
        and subscribers gained for each day in the period.
        
        Returns:
            Raw API response with daily analytics data.
            
        Note:
            The date range excludes today (as data may be incomplete)
            and includes the 7 previous days.
        """
        start_str, end_str = self._get_date_range()
        
        logger.info(
            f"Fetching YouTube Analytics for last 7 days: "
            f"{start_str} to {end_str}"
        )
        logger.info(f"API request start: metrics={METRICS_CORE}")
        
        response = self.client.query_reports(
            start_date=start_str,
            end_date=end_str,
            metrics=METRICS_CORE,
            dimensions="day",
            sort="day"
        )
        
        row_count = len(response.get("rows", []))
        logger.info(f"Fetched {row_count} days of analytics data")
        
        # Log which metrics were returned
        column_headers = response.get("columnHeaders", [])
        returned_metrics = [h.get("name") for h in column_headers]
        logger.info(f"Metrics returned: {returned_metrics}")
        
        return response
    
    def fetch_last_28_days(self) -> dict[str, Any]:
        """
        Fetch analytics data for the last 28 days.
        
        Used for growth and content strategy queries where broader
        trends are needed.
        
        Returns:
            Raw API response with daily analytics data.
        """
        start_str, end_str = self._get_date_range(days=28)
        
        logger.info(
            f"Fetching YouTube Analytics for last 28 days: "
            f"{start_str} to {end_str}"
        )
        logger.info(f"API request start: metrics={METRICS_CORE}")
        
        response = self.client.query_reports(
            start_date=start_str,
            end_date=end_str,
            metrics=METRICS_CORE,
            dimensions="day",
            sort="day"
        )
        
        row_count = len(response.get("rows", []))
        logger.info(f"Fetched {row_count} days of analytics data (28d)")
        
        return response
    
    def fetch_traffic_sources(self, days: int = 7) -> dict[str, Any]:
        """
        Fetch traffic source breakdown for the specified number of days.
        
        Queries the YouTube Analytics API with insightTrafficSourceType
        dimension to break down views by traffic source.
        
        Args:
            days: Number of days to look back (default: 7).
        
        Returns:
            Raw API response with traffic source breakdown.
            Returns empty dict if query fails.
        """
        start_str, end_str = self._get_date_range(days=days)
        
        logger.info(
            f"Fetching traffic sources for last {days} days: "
            f"{start_str} to {end_str}"
        )
        logger.info(
            f"API request start: metrics={METRICS_TRAFFIC}, "
            f"dimensions={DIMENSIONS_TRAFFIC}"
        )
        
        try:
            response = self.client.query_reports(
                start_date=start_str,
                end_date=end_str,
                metrics=METRICS_TRAFFIC,
                dimensions=DIMENSIONS_TRAFFIC
            )
            
            row_count = len(response.get("rows", []))
            logger.info(f"Fetched {row_count} traffic source entries")
            
            return response
            
        except Exception as e:
            logger.warning(f"Failed to fetch traffic sources: {e}")
            return {}
    
    def fetch_extended_analytics(
        self, period: str = "7d"
    ) -> dict[str, Any]:
        """
        Fetch all analytics data including traffic sources.
        
        Combines core metrics and traffic source data into a single
        response dictionary.
        
        Args:
            period: Time period to fetch — "7d" or "28d".
        
        Returns:
            Dictionary containing:
            - core_response: Raw API response with daily metrics
            - traffic_response: Raw API response with traffic sources
            - period: The period that was fetched
        """
        logger.info(
            f"Fetching extended analytics (core + traffic sources, period={period})"
        )
        
        days = 28 if period == "28d" else 7
        
        if period == "28d":
            core_response = self.fetch_last_28_days()
        else:
            core_response = self.fetch_last_7_days()
        
        traffic_response = self.fetch_traffic_sources(days=days)
        
        logger.info("Extended analytics fetch complete")
        
        return {
            "core_response": core_response,
            "traffic_response": traffic_response,
            "period": period
        }


def fetch_analytics_for_channel(
    access_token: str,
    refresh_token: str | None = None,
    period: str = "7d"
) -> dict[str, Any]:
    """
    Convenience function to fetch analytics for a channel.
    
    Creates a client and fetcher, then retrieves analytics data
    including extended metrics and traffic sources.
    
    Args:
        access_token: OAuth access token for the channel.
        refresh_token: Optional OAuth refresh token for automatic token refresh.
        period: Time period — "7d" (default) or "28d" for growth queries.
        
    Returns:
        Dictionary with core_response and traffic_response from the API.
    """
    client = YouTubeAnalyticsClient(
        access_token=access_token,
        refresh_token=refresh_token
    )
    fetcher = AnalyticsFetcher(client)
    return fetcher.fetch_extended_analytics(period=period)
