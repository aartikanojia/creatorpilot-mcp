"""
Base classes for MCP Tool Registry.

Defines core data structures used across all tool modules:
- ToolResult: Execution result container
- ToolDefinition: Tool specification with schema and handler
"""

import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional, Awaitable

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    """Result from a tool execution."""

    tool_name: str
    success: bool
    output: Optional[Any] = None
    error: Optional[str] = None


@dataclass
class ToolDefinition:
    """
    Definition of an MCP tool.

    Attributes:
        name: Unique identifier for the tool
        description: Human-readable description
        input_schema: JSON Schema for expected input
        output_schema: JSON Schema for expected output
        handler: Async function that executes the tool
        category: Tool category for grouping (analytics, insight, report, etc.)
        requires_plan: Minimum subscription plan required (free, pro, agency)
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], Awaitable[Any]]
    category: str = "general"
    requires_plan: str = "free"
