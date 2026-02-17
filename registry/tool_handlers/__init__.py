"""
MCP Tool Handlers Module.

Contains individual tool handler implementations for the MCP registry.
"""

from .fetch_analytics import handle_fetch_analytics
from .fetch_last_video_analytics import handle_fetch_last_video_analytics

__all__ = ["handle_fetch_analytics", "handle_fetch_last_video_analytics"]
