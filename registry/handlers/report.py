"""
Report tool handlers.

Handles report generation and data summarization.
Uses real analytics data from the execution context instead of hardcoded values.
"""

from datetime import datetime
from typing import Any


class ReportHandlers:
    """Handler implementations for report tools."""

    @staticmethod
    async def generate_report(input_data: dict[str, Any]) -> dict[str, Any]:
        """
        Generate a performance report from available analytics context.

        Args:
            input_data: Contains message, context (with analytics data)

        Returns:
            Report with title, summary, sections, and timestamp
        """
        context = input_data.get("context", {})
        analytics = context.get("analytics", {})
        current = analytics.get("current_period", {})

        # Build dynamic summary from real data
        views = current.get("views", 0)
        subs = current.get("subscribers_gained", 0)
        period = current.get("period", "last_7_days")

        period_label = "7-day" if "7" in str(period) else "28-day"

        summary_parts = []
        if views:
            summary_parts.append(f"{views:,} views")
        if subs:
            summary_parts.append(f"{subs:,} new subscribers")

        summary_text = f"{period_label} period: {', '.join(summary_parts)}" if summary_parts else "No analytics data available for this period"

        # Build sections from whatever data is available
        sections = []
        sections.append({
            "name": "Overview",
            "content": summary_text
        })

        if current.get("avg_view_percentage"):
            sections.append({
                "name": "Engagement",
                "content": f"Average view percentage: {current['avg_view_percentage']:.1f}%"
            })

        if current.get("traffic_sources"):
            top_sources = sorted(
                current["traffic_sources"].items(),
                key=lambda x: x[1],
                reverse=True
            )[:3]
            source_text = ", ".join(f"{k}: {v:,}" for k, v in top_sources)
            sections.append({
                "name": "Traffic Sources",
                "content": f"Top sources: {source_text}"
            })

        sections.append({
            "name": "Growth",
            "content": f"Subscribers gained: {subs:,}, Total views: {views:,}"
        })

        return {
            "title": f"{period_label.title()} Performance Report",
            "summary": summary_text,
            "sections": sections,
            "generated_at": datetime.utcnow().isoformat()
        }

    @staticmethod
    async def summarize_data(input_data: dict[str, Any]) -> dict[str, Any]:
        """
        Create a concise summary from available analytics data.

        Args:
            input_data: Contains message, context (with analytics data)

        Returns:
            Summary with highlights and word count
        """
        context = input_data.get("context", {})
        analytics = context.get("analytics", {})
        current = analytics.get("current_period", {})

        views = current.get("views", 0)
        subs = current.get("subscribers_gained", 0)
        avg_view_pct = current.get("avg_view_percentage")
        watch_time = current.get("avg_watch_time_minutes", 0)

        highlights = []
        if views:
            highlights.append(f"{views:,} total views")
        if subs:
            highlights.append(f"{subs:,} new subscribers")
        if avg_view_pct is not None:
            highlights.append(f"{avg_view_pct:.1f}% average view percentage")
        if watch_time:
            highlights.append(f"{watch_time:.1f} min average watch time")

        if not highlights:
            summary = "No analytics data available for summarization."
            highlights = ["Analytics data not yet loaded"]
        else:
            summary = f"Your channel had {views:,} views and {subs:,} new subscribers."

        return {
            "summary": summary,
            "highlights": highlights,
            "word_count": len(summary.split())
        }
