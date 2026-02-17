"""
Analytics Context Builder for MCP.

Builds structured analytics context for LLM prompts by fetching
current and previous period snapshots from the database.
Includes availability flags for metrics.
"""

import logging
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import desc

from db.session import SessionLocal
from db.models.analytics_snapshot import AnalyticsSnapshot

logger = logging.getLogger(__name__)


class AnalyticsContextBuilder:
    """
    Builds structured analytics context for LLM prompts.
    
    Fetches analytics snapshots from the database and returns
    a strictly structured dictionary with current and previous
    period data for comparison, plus availability flags.
    """

    def __init__(self) -> None:
        """Initialize the analytics context builder."""
        logger.info("AnalyticsContextBuilder initialized")

    def _get_session(self):
        """Create a new database session."""
        return SessionLocal()

    def build_analytics_context(
        self,
        channel_uuid: Optional[UUID]
    ) -> dict[str, Any]:
        """
        Build structured analytics context for a channel.
        
        Fetches the two most recent analytics snapshots to provide
        current and previous period data for comparison.
        
        Args:
            channel_uuid: The UUID of the channel to fetch analytics for.
            
        Returns:
            Dictionary with:
            - current_period: Current period data or None
            - previous_period: Previous period data or None
            - has_ctr: True if CTR data (impressions > 0) is available
            - has_retention: True if retention data is available
            - has_traffic_sources: True if traffic source data is available
        """
        # Default context with availability flags always present
        context: dict[str, Any] = {
            "current_period": None,
            "previous_period": None,
            "has_ctr": False,
            "has_retention": False,
            "has_traffic_sources": False
        }
        
        if not channel_uuid:
            logger.debug("No channel_uuid provided, returning empty context")
            return context
        
        try:
            snapshots = self._fetch_recent_snapshots(channel_uuid, limit=2)
            
            if not snapshots:
                logger.debug(f"No analytics snapshots found for channel {channel_uuid}")
                return context
            
            # Build period data
            period_context = self._build_context_dict(snapshots)
            context.update(period_context)
            
            # Compute availability flags from current period
            if context["current_period"]:
                current = context["current_period"]
                
                # has_ctr: impressions > 0
                impressions = current.get("impressions", 0) or 0
                context["has_ctr"] = impressions > 0
                
                # has_retention: avg_view_percentage is not None
                context["has_retention"] = current.get("avg_view_percentage") is not None
                
                # has_traffic_sources: traffic_sources not empty
                traffic = current.get("traffic_sources")
                context["has_traffic_sources"] = bool(traffic and len(traffic) > 0)
            
            logger.debug(
                f"Analytics context built: has_ctr={context['has_ctr']}, "
                f"has_retention={context['has_retention']}, "
                f"has_traffic_sources={context['has_traffic_sources']}"
            )
            
            return context
            
        except Exception as e:
            logger.error(f"Error building analytics context: {e}")
            return context

    def _fetch_recent_snapshots(
        self,
        channel_uuid: UUID,
        limit: int = 2
    ) -> list[AnalyticsSnapshot]:
        """
        Fetch the most recent analytics snapshots for a channel.
        
        Args:
            channel_uuid: The UUID of the channel.
            limit: Maximum number of snapshots to fetch (default: 2).
            
        Returns:
            List of AnalyticsSnapshot objects ordered by created_at descending.
        """
        session = self._get_session()
        try:
            snapshots = (
                session.query(AnalyticsSnapshot)
                .filter(AnalyticsSnapshot.channel_id == channel_uuid)
                .order_by(desc(AnalyticsSnapshot.created_at))
                .limit(limit)
                .all()
            )
            return snapshots
        except Exception as e:
            logger.error(f"Error fetching analytics snapshots: {e}")
            raise
        finally:
            session.close()

    def _build_context_dict(
        self,
        snapshots: list[AnalyticsSnapshot]
    ) -> dict[str, Any]:
        """
        Build the structured context dictionary from snapshots.
        
        Args:
            snapshots: List of AnalyticsSnapshot objects (most recent first).
            
        Returns:
            Dictionary with current_period and optionally previous_period.
        """
        context: dict[str, Any] = {}
        
        # Current period (most recent snapshot)
        if len(snapshots) >= 1:
            current = snapshots[0]
            context["current_period"] = self._snapshot_to_dict(
                current, period_label="last_7_days"
            )
        
        # Previous period (second most recent snapshot)
        if len(snapshots) >= 2:
            previous = snapshots[1]
            context["previous_period"] = self._snapshot_to_dict(
                previous, period_label="previous_7_days"
            )
        
        logger.debug(f"Analytics context resolved: {context}")
        return context

    def _snapshot_to_dict(
        self,
        snapshot: AnalyticsSnapshot,
        period_label: str
    ) -> dict[str, Any]:
        """
        Convert an AnalyticsSnapshot to a structured dictionary.
        
        Args:
            snapshot: The AnalyticsSnapshot object.
            period_label: Label for the period (e.g., "last_7_days").
            
        Returns:
            Dictionary with analytics metrics including extended fields.
        """
        result = {
            "period": snapshot.period or period_label,
            "views": snapshot.views or 0,
            "subscribers_gained": snapshot.subscribers or 0,
            "avg_watch_time_minutes": snapshot.avg_watch_time_minutes or 0.0,
        }
        
        # Add extended metrics (may be None for older snapshots)
        result["impressions"] = snapshot.impressions
        result["ctr"] = snapshot.avg_ctr
        result["avg_view_percentage"] = snapshot.avg_view_percentage
        result["traffic_sources"] = snapshot.traffic_sources
        
        return result

    def build_structured_analytics_text(
        self,
        channel_uuid: Optional[UUID]
    ) -> str:
        """
        Build structured analytics text for LLM consumption.
        
        Formats analytics data in a human-readable text format
        that LLMs can use directly in their responses.
        
        Args:
            channel_uuid: The UUID of the channel to fetch analytics for.
            
        Returns:
            Formatted text string with analytics data and availability status.
        """
        context = self.build_analytics_context(channel_uuid)
        
        lines = []
        
        # Always include availability status first
        lines.append("ANALYTICS AVAILABILITY STATUS:")
        lines.append(f"- CTR available: {context['has_ctr']}")
        lines.append(f"- Audience retention available: {context['has_retention']}")
        lines.append(f"- Traffic source data available: {context['has_traffic_sources']}")
        lines.append("")
        
        if not context["current_period"]:
            lines.append("No analytics data available for this channel.")
            return "\n".join(lines)
        
        lines.append("## STRUCTURED ANALYTICS DATA (USE EXACT NUMBERS)")
        lines.append("")
        
        # Current period
        current = context["current_period"]
        lines.append("**Current Period (Last 7 Days):**")
        lines.append(f"- Views: {current.get('views', 0):,}")
        
        if current.get("impressions") is not None:
            lines.append(f"- Impressions: {current['impressions']:,}")
        
        if current.get("ctr") is not None:
            ctr_pct = current['ctr'] * 100 if current['ctr'] < 1 else current['ctr']
            lines.append(f"- CTR: {ctr_pct:.1f}%")
        
        lines.append(f"- Avg Watch Time: {current.get('avg_watch_time_minutes', 0):.2f} min")
        
        if current.get("avg_view_percentage") is not None:
            lines.append(f"- Avg View Percentage: {current['avg_view_percentage']:.1f}%")
        
        lines.append(f"- Subscribers Gained: {current.get('subscribers_gained', 0):,}")
        
        # Traffic sources
        if context["has_traffic_sources"] and current.get("traffic_sources"):
            lines.append("")
            lines.append("**Traffic Sources:**")
            traffic = current["traffic_sources"]
            total_traffic = sum(traffic.values())
            
            if total_traffic > 0:
                sorted_sources = sorted(
                    traffic.items(), 
                    key=lambda x: x[1], 
                    reverse=True
                )
                for source, views in sorted_sources[:5]:
                    pct = (views / total_traffic) * 100
                    source_label = self._format_traffic_source_label(source)
                    lines.append(f"- {source_label}: {pct:.0f}%")
        
        lines.append("")
        
        # Previous period (for comparison)
        if context["previous_period"]:
            previous = context["previous_period"]
            lines.append("**Previous Period (7 Days Prior):**")
            lines.append(f"- Views: {previous.get('views', 0):,}")
            
            if previous.get("impressions") is not None:
                lines.append(f"- Impressions: {previous['impressions']:,}")
            
            if previous.get("ctr") is not None:
                ctr_pct = previous['ctr'] * 100 if previous['ctr'] < 1 else previous['ctr']
                lines.append(f"- CTR: {ctr_pct:.1f}%")
            
            lines.append(f"- Avg Watch Time: {previous.get('avg_watch_time_minutes', 0):.2f} min")
            lines.append(f"- Subscribers Gained: {previous.get('subscribers_gained', 0):,}")
        
        return "\n".join(lines)
    
    def _format_traffic_source_label(self, source: str) -> str:
        """
        Format traffic source key to human-readable label.
        
        Args:
            source: Traffic source key (e.g., "YT_SEARCH").
            
        Returns:
            Human-readable label (e.g., "YouTube Search").
        """
        labels = {
            "YT_SEARCH": "YouTube Search",
            "SUGGESTED": "Suggested Videos",
            "BROWSE_FEATURES": "Browse Features",
            "EXTERNAL": "External",
            "NOTIFICATION": "Notifications",
            "PLAYLIST": "Playlists",
            "END_SCREEN": "End Screens",
            "CHANNEL": "Channel Page",
            "SHORTS": "Shorts",
            "SUBSCRIBER": "Subscribers",
            "OTHER": "Other"
        }
        return labels.get(source, source.replace("_", " ").title())


# Global instance for convenience
analytics_context_builder = AnalyticsContextBuilder()
