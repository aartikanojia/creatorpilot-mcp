"""
Tool handlers for MCP Registry.

Each module contains handler implementations for a specific category of tools.
Handlers are async functions that process input and return structured output.

Modules:
- analytics: Analytics data fetching and metric computation
- insight: Data analysis and recommendation generation
- report: Report and summary generation
- memory: Context recall and history search
- action: Task execution and scheduling
- search: Data search across sources
- youtube: YouTube-specific analytics tools
"""

from .analytics import AnalyticsHandlers
from .insight import InsightHandlers
from .report import ReportHandlers
from .memory import MemoryHandlers
from .action import ActionHandlers
from .search import SearchHandlers
from .youtube import YouTubeHandlers

__all__ = [
    "AnalyticsHandlers",
    "InsightHandlers",
    "ReportHandlers",
    "MemoryHandlers",
    "ActionHandlers",
    "SearchHandlers",
    "YouTubeHandlers",
]
