"""
Execution planner for MCP tool selection.

This module is responsible for deterministic, explainable planning
of which tools to execute based on user intent. It does NOT call
the LLM directly - planning is rule-based and transparent.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class ExecutionPlan:
    """
    Represents a planned execution sequence.

    Contains the tools to execute, reasoning for each decision,
    and metadata about the planning process.
    """

    tools_to_execute: list[str] = field(default_factory=list)
    reasoning: dict[str, str] = field(default_factory=dict)
    intent_classification: str = "general"
    confidence: float = 0.0
    requires_deep_analysis: bool = False
    context_requirements: list[str] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)

    def add_tool(self, tool_name: str, reason: str) -> None:
        """Add a tool to the execution plan with reasoning."""
        if tool_name not in self.tools_to_execute:
            self.tools_to_execute.append(tool_name)
            self.reasoning[tool_name] = reason

    def to_dict(self) -> dict[str, Any]:
        """Convert plan to dictionary representation."""
        return {
            "tools": self.tools_to_execute,
            "reasoning": self.reasoning,
            "intent": self.intent_classification,
            "confidence": self.confidence,
            "deep_analysis": self.requires_deep_analysis,
            "context_requirements": self.context_requirements,
            "parameters": self.parameters
        }


class ExecutionPlanner:
    """
    Deterministic planner for tool selection.

    Uses rule-based intent classification and pattern matching
    to decide which tools should be executed. All decisions are
    explainable and logged.
    """

    # Intent patterns - maps regex patterns to intent classifications
    # Account patterns — checked with priority boost before analytics
    ACCOUNT_PATTERNS: list[str] = [
        r"\bwho am i\b",
        r"\bwhat(?:'?s|\s+is) my name\b",
        r"\bmy channel name\b",
        r"\bchannel info\b",
        r"\bmy profile\b",
        r"\bmy subscribers\b",
        r"\bsubscriber count\b",
        r"\bhow many subscribers\b",
        r"\bmy account\b",
        r"\btell me (?:about )?my (?:channel|name|account|profile)\b",
        r"\bwho(?:'?s| is) (?:the )?(?:channel )?(?:owner|creator)\b",
    ]

    INTENT_PATTERNS: dict[str, list[str]] = {
        "account": ACCOUNT_PATTERNS,
        "analytics": [
            r"\b(analytic|metric|stat|performance|grow\w*|trend)\b",
            r"\b(how many|how much|count|total|average)\b",
            r"\b(compare|comparison|versus|vs)\b",
            r"\b(ctr|click through rate|impression|retention|watch time)\b"
        ],
        "insight": [
            r"\b(insight|recommend|suggest|advice|should|best)\b",
            r"\b(why|reason|explain|understand)\b",
            r"\b(improve|optimize|better|increase|decrease)\b"
        ],
        "report": [
            r"\b(report|summary|overview|digest|recap)\b",
            r"\b(weekly|monthly|daily|last week|last month)\b",
            r"\b(what happened|update me|catch me up)\b"
        ],
        "memory": [
            r"\b(remember|recall|history|previous|last time)\b",
            r"\b(we discussed|you said|i told you)\b",
            r"\b(context|background|earlier)\b"
        ],
        "action": [
            r"\b(do|create|make|set|configure|update)\b",
            r"\b(schedule|plan|execute|run|trigger)\b",
            r"\b(send|post|publish|notify)\b"
        ],
        "search": [
            r"\b(find|search|look for|where|locate)\b",
            r"\b(show me|get|fetch|retrieve)\b",
            r"\b(list|display|what are)\b"
        ],
        "video_analysis": [
            r"\b(last|latest|recent|newest)\s+(video|upload|content)\b",
            r"\b(my|the)\s+(last|latest|recent)\s+video\b",
            r"\b(how|what).*(last|latest|recent)\s+video.*(perform|doing)\b",
            r"\bnext video\s+(improve|ideas?|suggestion|tip)\b",
            r"\b(improve|better)\s+(next|my)\s+video\b",
            r"\blast upload.*(perform|analyz|review)\b",
            r"\b(latest|last|recent|newest) video\b",
            # Title-based video queries
            r'"[^"]+?"',                                     # quoted title
            r"\b(this|my)\s+video\b",                        # "this video", "my video"
            r"\b(tell me about|analyze|how.*(did|is)).*video\b",  # title fragment
        ]
    }

    # Maps intents to relevant tools
    INTENT_TOOL_MAP: dict[str, list[str]] = {
        "account": [],  # No tools — answered from profile context only
        "analytics": ["fetch_analytics", "compute_metrics", "generate_chart"],
        "insight": ["fetch_analytics", "analyze_data", "generate_insight", "get_recommendations"],
        "report": ["generate_report", "summarize_data", "fetch_analytics"],
        "memory": ["recall_context", "search_history"],
        "action": ["execute_action", "schedule_task"],
        "search": ["fetch_analytics", "search_data", "recall_context"],
        "video_analysis": ["fetch_last_video_analytics", "recall_context"],
        "general": ["recall_context"]
    }

    def __init__(self) -> None:
        """Initialize the planner."""
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Pre-compile regex patterns for performance."""
        self._compiled_patterns: dict[str, list[re.Pattern]] = {}
        for intent, patterns in self.INTENT_PATTERNS.items():
            self._compiled_patterns[intent] = [
                re.compile(p, re.IGNORECASE) for p in patterns
            ]

    def create_plan(
        self,
        message: str,
        memory_context: dict[str, Any],
        available_tools: list[str]
    ) -> ExecutionPlan:
        """
        Create an execution plan based on user message and context.

        This is the main planning method. It:
        1. Classifies user intent
        2. Selects relevant tools
        3. Filters by availability
        4. Builds explainable plan

        Args:
            message: User's input message
            memory_context: Available memory context
            available_tools: List of currently available tool names

        Returns:
            ExecutionPlan with tools and reasoning
        """
        plan = ExecutionPlan()

        # Step 1: Classify intent
        intent, confidence = self._classify_intent(message)
        plan.intent_classification = intent
        plan.confidence = confidence

        logger.info(
            f"Intent classified as '{intent}' with confidence {confidence:.2f}")

        # Step 1b: Rule-based override for analytics intent
        # Force analytics intent when channel context exists and message
        # contains analytics-related keywords
        intent, confidence = self._apply_analytics_override(
            message, memory_context, intent, confidence
        )
        if plan.intent_classification != intent:
            logger.info(
                f"Intent overridden to '{intent}' via analytics rule")
            plan.intent_classification = intent
            plan.confidence = confidence

        # Step 2: Check if deep analysis is needed
        plan.requires_deep_analysis = self._needs_deep_analysis(
            message, intent)

        # Step 3: Determine context requirements
        plan.context_requirements = self._determine_context_needs(
            message, memory_context)

        # Step 4: Select tools based on intent
        candidate_tools = self.INTENT_TOOL_MAP.get(
            intent, self.INTENT_TOOL_MAP["general"])

        # Step 5: Filter by availability and add with reasoning
        for tool_name in candidate_tools:
            if tool_name in available_tools:
                reason = self._generate_tool_reason(tool_name, intent, message)
                plan.add_tool(tool_name, reason)

        # Step 6: Add context-based tools
        if "conversation_history" in plan.context_requirements:
            if "recall_context" in available_tools and "recall_context" not in plan.tools_to_execute:
                plan.add_tool("recall_context",
                              "Required for conversation continuity")

        # Safety check: account intent must never have tools
        if intent == "account":
            plan.tools_to_execute = []
            plan.reasoning = {}

        # Step 7: Determine execution parameters (period, flags)
        plan.parameters = self._determine_parameters(message, intent)

        # Step 8: Extract video title for title-based queries
        if intent == "video_analysis":
            extracted_title = self._extract_video_title(message)
            if extracted_title:
                plan.parameters["extracted_title"] = extracted_title
                logger.info(f"[Planner] Extracted title: \"{extracted_title}\"")

        logger.info(
            f"Plan created: {len(plan.tools_to_execute)} tools selected. "
            f"Params: {plan.parameters}"
        )

        return plan

    def _classify_intent(self, message: str) -> tuple[str, float]:
        """
        Classify the user's intent from their message.

        Uses pattern matching to determine the primary intent.
        Returns the intent with the highest match score.

        Args:
            message: User's message text

        Returns:
            Tuple of (intent_name, confidence_score)
        """
        scores: dict[str, int] = {}


        # 0. Guardrail: Detect irrelevant / off-topic queries immediately
        irrelevant_patterns = [
            r"\b(political|election|vote|government|policy)\b",
            r"\b(recipe|cook|food|pasta|ingredients)\b",
            r"\b(weather|sports|news|celebrity)\b"
        ]
        for pattern in irrelevant_patterns:
            if re.search(pattern, message, re.IGNORECASE):
                logger.info("Irrelevant intent detected — defaulting to general")
                return ("general", 0.5)

        # 1. Score intents based on pattern matches
        for intent, patterns in self._compiled_patterns.items():
            score = 0
            for pattern in patterns:
                matches = pattern.findall(message)
                score += len(matches)
            scores[intent] = score

        # Account intent takes absolute priority — if any account
        # pattern matched, return immediately regardless of other scores.
        if scores.get("account", 0) > 0:
            logger.info("Account intent detected — skipping analytics")
            return ("account", 0.95)

        # Find the highest scoring intent
        if not any(scores.values()):
            return ("general", 0.5)

        best_intent = max(scores, key=scores.get)  # type: ignore
        total_matches = sum(scores.values())
        confidence = scores[best_intent] / max(total_matches, 1)

        # Normalize confidence to 0.5-1.0 range
        confidence = 0.5 + (confidence * 0.5)

        return (best_intent, round(confidence, 2))

    def _apply_analytics_override(
        self,
        message: str,
        memory_context: dict[str, Any],
        current_intent: str,
        current_confidence: float
    ) -> tuple[str, float]:
        """
        Apply rule-based override to force analytics intent when appropriate.

        Forces 'analytics' intent when:
        - Channel context is present in memory_context
        - Message contains analytics-related keywords

        Args:
            message: User's message text
            memory_context: Available memory context
            current_intent: The initially classified intent
            current_confidence: The initial confidence score

        Returns:
            Tuple of (intent_name, confidence_score) - may be unchanged
        """
        # Check if channel context exists
        # Primary: OAuth channel context injected by executor (Step 1c)
        has_channel_context = memory_context.get("channel") is not None
        
        # Fallback: historical data from PostgreSQL
        if not has_channel_context:
            historical = memory_context.get("historical", {})
            has_channel_context = (
                historical.get("latest_snapshot") is not None or
                historical.get("recent_insights") is not None
            )

        if not has_channel_context:
            # No channel context - no override
            return (current_intent, current_confidence)

        # Never override account or video_analysis intent
        if current_intent in ["account", "video_analysis"]:
            return (current_intent, current_confidence)

        # Analytics keywords that should trigger override
        analytics_keywords = [
            r"\bperformance\b",
            r"\bviews\b",
            r"\bsubscribers\b",
            r"\bgrowth\b",
            r"\bengagement\b",
            r"\banalytics\b",
            r"\bthis week\b",
            r"\blast week\b",
            r"\bmetrics\b",
            r"\bperforming\b",
            r"\bhow.*(did|is|was|are).*channel\b",
            r"\bchannel.*(doing|perform|growth)\b"
        ]

        message_lower = message.lower()
        keyword_found = False

        for pattern in analytics_keywords:
            if re.search(pattern, message_lower, re.IGNORECASE):
                keyword_found = True
                logger.debug(
                    f"Analytics keyword matched: {pattern}")
                break

        if keyword_found:
            # Force analytics intent with high confidence
            return ("analytics", 0.95)

        return (current_intent, current_confidence)

    def _needs_deep_analysis(self, message: str, intent: str) -> bool:
        """
        Determine if the request requires deep analysis mode.

        Args:
            message: User's message
            intent: Classified intent

        Returns:
            True if deep analysis is needed
        """
        deep_triggers = [
            r"\b(deep|thorough|detailed|comprehensive|in-depth)\b",
            r"\b(analyze|analysis|investigate|audit)\b",
            r"\b(report|postmortem|retrospective)\b"
        ]

        for pattern in deep_triggers:
            if re.search(pattern, message, re.IGNORECASE):
                return True

        # Reports always need deep analysis
        if intent == "report":
            return True

        return False

    def _determine_context_needs(
        self,
        message: str,
        memory_context: dict[str, Any]
    ) -> list[str]:
        """
        Determine what context is needed for this request.

        Args:
            message: User's message
            memory_context: Available memory context

        Returns:
            List of required context types
        """
        needs = []

        # Check for references to past conversations
        if re.search(r"\b(earlier|before|previous|last time|remember)\b", message, re.IGNORECASE):
            needs.append("conversation_history")

        # Check for historical data needs
        if re.search(r"\b(week|month|trend|over time|history)\b", message, re.IGNORECASE):
            needs.append("historical_data")

        # Check for analytics needs
        if re.search(r"\b(metric|stat|number|performance|data)\b", message, re.IGNORECASE):
            needs.append("analytics")

        # Default: always need conversation history for continuity
        if "conversation_history" not in needs and memory_context.get("conversation_history"):
            needs.append("conversation_history")

        return needs

    def _generate_tool_reason(self, tool_name: str, intent: str, message: str) -> str:
        """
        Generate a human-readable reason for selecting a tool.

        Args:
            tool_name: Name of the selected tool
            intent: Classified intent
            message: Original message (for context)

        Returns:
            Explanation string
        """
        reasons = {
            "fetch_analytics": f"Required for '{intent}' intent - need to retrieve data metrics",
            "compute_metrics": f"Required for '{intent}' intent - need to calculate statistics",
            "generate_chart": f"Required for '{intent}' intent - visual representation requested",
            "analyze_data": f"Required for '{intent}' intent - data analysis needed",
            "generate_insight": f"Required for '{intent}' intent - actionable insights requested",
            "get_recommendations": f"Required for '{intent}' intent - recommendations requested",
            "generate_report": f"Required for '{intent}' intent - report generation requested",
            "summarize_data": f"Required for '{intent}' intent - summarization needed",
            "recall_context": f"Required for '{intent}' intent - historical context needed",
            "search_history": f"Required for '{intent}' intent - searching past data",
            "execute_action": f"Required for '{intent}' intent - action execution requested",
            "schedule_task": f"Required for '{intent}' intent - task scheduling requested",
            "search_data": f"Required for '{intent}' intent - data search requested",
            "fetch_last_video_analytics": f"Required for '{intent}' intent - analyzing latest video performance"
        }

        return reasons.get(tool_name, f"Selected for '{intent}' intent processing")

    def _determine_parameters(self, message: str, intent: str) -> dict[str, Any]:
        """
        Determine execution parameters like time period and flags.

        Args:
            message: User's message
            intent: Classified intent

        Returns:
            Dictionary of parameter overrides
        """
        params = {}
        msg_lower = message.lower()

        # 1. Determine period (default to 7d)
        if re.search(r"\b(28 day|month|4 week)\b", msg_lower):
            params["period"] = "28d"
        elif re.search(r"\b(grow\w*|trend)\b", msg_lower):
            # Growth queries often benefit from longer context
            params["period"] = "28d"
        elif re.search(
            r"\b(what|which).*(upload|post|make|create)\b"
            r"|\bcontent strategy\b"
            r"|\b(next|future).*(video|topic)\b"
            r"|\bshould i (upload|post|make)\b",
            msg_lower
        ):
            # Content strategy queries need both periods for trend comparison
            params["period"] = "28d"
            params["compare_periods"] = True
        
        # 2. Determine if video library is needed
        # Triggers: "what should I post", "content strategy", "video ideas"
        library_triggers = [
            r"\b(what|which).*(post|upload|video|content)\b",
            r"\b(next|future).*(video|topic|idea)\b",
            r"\bcontent strategy\b",
            r"\blibrary\b",
            r"\bpast videos\b",
            r"\bwhat.*work(ing|ed)\b",
            r"\bupload next\b",
            r"\bshould i (make|create|film|record)\b",
            r"\bvideo ideas?\b"
        ]
        
        if any(re.search(p, msg_lower) for p in library_triggers):
            params["fetch_library"] = True
            
        return params

    def _extract_video_title(self, message: str) -> Optional[str]:
        """
        Extract a video title or title fragment from the user's message.

        Priority:
          1. Quoted text → exact title intent
          2. Text after "video" keyword → title fragment

        Args:
            message: User's raw message

        Returns:
            Extracted title string, or None
        """
        # 1. Look for quoted text
        quoted = re.findall(r'["\u201c\u201d]([^"\u201c\u201d]+)["\u201c\u201d]', message)
        if quoted:
            # Return the longest quoted segment (most likely to be a title)
            return max(quoted, key=len).strip()

        # 2. Look for text after "video" keyword
        # Patterns: "this video <title>", "my video <title>"
        match = re.search(
            r'\b(?:this|my)\s+video\s+(.+)',
            message,
            re.IGNORECASE
        )
        if match:
            fragment = match.group(1).strip()
            # Remove trailing punctuation/question marks
            fragment = re.sub(r'[?.!]+$', '', fragment).strip()
            if len(fragment) > 2:  # Ignore very short fragments
                return fragment

        # 3. Look for "tell me about ... video <title>" or "analyze ... video <title>"
        match = re.search(
            r'\bvideo\s+(.{3,})$',
            message,
            re.IGNORECASE
        )
        if match:
            fragment = match.group(1).strip()
            fragment = re.sub(r'[?.!]+$', '', fragment).strip()
            if len(fragment) > 2:
                return fragment

        return None
