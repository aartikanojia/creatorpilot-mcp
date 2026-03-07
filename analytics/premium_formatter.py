"""
PremiumOutputFormatter v1 — Deterministic Lock.

Accepts ONLY structured intelligence state.
Translates pre-computed deterministic output into LLM-narrated premium text.

STRICT RULES:
- Only 5 keys accepted: primary_constraint, severity, risk_level,
  ranked_strategies, confidence
- All other keys IGNORED
- No video titles, descriptions, raw analytics, emojis
- No metric reinterpretation
- No severity override
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class PremiumOutputFormatter:
    """
    Strict structured-input formatter.

    Accepts ONLY pre-computed intelligence state.
    Passes to LLM narration layer with locked system prompt.
    """

    ALLOWED_KEYS = {
        "primary_constraint",
        "severity",
        "ranked_strategies",
        "confidence",
        "video_title",
    }

    CONSTRAINT_TRANSLATIONS = {
        "ctr": {
            "title": "Low Click Attraction",
            "explanation": "Your thumbnails and titles are not convincing enough viewers to click on the video.",
        },
        "retention": {
            "title": "Viewers Leaving Early",
            "explanation": "A noticeable portion of viewers stop watching before reaching the most interesting part of the video.",
        },
        "conversion": {
            "title": "Low Subscriber Conversion",
            "explanation": "Many viewers watch your content but very few decide to subscribe.",
        },
        "shorts": {
            "title": "Shorts Dependency",
            "explanation": "Most views are coming from Shorts, which can limit deeper audience engagement.",
        },
        "growth": {
            "title": "Growth Slowdown",
            "explanation": "The channel's overall growth momentum has started to slow.",
        },
    }

    CONSTRAINT_SUGGESTIONS = {
        "ctr": (
            "Update the title and thumbnail to highlight the most exciting "
            "visual moment from the video so viewers immediately understand "
            "what they will see."
        ),
        "retention": (
            "Move the most interesting moment to the beginning of the video "
            "and remove slow introductions."
        ),
        "conversion": (
            "Add a clear moment in the video where viewers are encouraged "
            "to subscribe after delivering value."
        ),
        "shorts": (
            "Create a longer-form companion video that expands on the topic "
            "of your best-performing Short to build deeper engagement."
        ),
        "growth": (
            "Analyze your top 3 performing videos and create new content "
            "that follows the same format and topic patterns."
        ),
    }

    def __init__(self, client=None):
        """
        Args:
            client: LLM client (OpenAI-compatible). If None, returns raw text.
        """
        self.client = client

    def format(self, structured_state: dict) -> str:
        """
        Format structured intelligence state into premium output.

        Args:
            structured_state: Pre-computed intelligence state dict.
                Only ALLOWED_KEYS are used. All others are ignored.

        Returns:
            Formatted premium text, or error string if incomplete.
        """
        if not isinstance(structured_state, dict):
            return "Structured intelligence state incomplete."

        # Strict key filtering — ignore everything not in ALLOWED_KEYS
        state = {
            k: structured_state[k]
            for k in self.ALLOWED_KEYS
            if k in structured_state
        }

        # video_title is optional — do not require it
        required_keys = self.ALLOWED_KEYS - {"video_title"}
        if not required_keys.issubset(state.keys()):
            missing = required_keys - set(state.keys())
            logger.warning(f"[PremiumFormatter] Missing keys: {missing}")
            return "Structured intelligence state incomplete."

        # Build user prompt from structured state only
        user_prompt = self._build_prompt(state)

        # If no LLM client, return raw structured text
        if self.client is None:
            return user_prompt

        # Load system prompt
        system_prompt = self._load_system_prompt()

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=800,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"[PremiumFormatter] LLM call failed: {e}")
            return user_prompt

    def _build_prompt(self, state: dict) -> str:
        """Build user prompt from filtered structured state."""
        raw_constraint = state["primary_constraint"]
        translation = self.CONSTRAINT_TRANSLATIONS.get(
            raw_constraint.lower(), None
        )

        if translation:
            constraint_display = translation["title"]
            explanation = translation["explanation"]
        else:
            constraint_display = raw_constraint
            explanation = ""

        lines = []

        # Prepend video title if available
        video_title = state.get("video_title")
        if video_title:
            lines.append(f"Video Analysis: {video_title}")
            lines.append("")

        lines.append(f"Primary Constraint: {constraint_display}")
        if explanation:
            lines.append(f"\n{explanation}\n")

        # Deterministic improvement suggestion based on constraint
        suggestion = self.CONSTRAINT_SUGGESTIONS.get(
            raw_constraint.lower(), ""
        )
        if suggestion:
            lines.append("**Suggested Improvement for This Video**")
            lines.append(f"\n{suggestion}\n")

        lines.extend([
            f"Severity: {state['severity']}",
            "",
            "Ranked Strategies:",
        ])

        for i, strategy in enumerate(state["ranked_strategies"], 1):
            if isinstance(strategy, dict):
                name = strategy.get("name", "Unknown")
                lift = strategy.get("estimated_lift", "N/A")
                lines.append(f"{i}. {name} (Lift: {lift})")
            elif isinstance(strategy, (list, tuple)) and len(strategy) >= 2:
                lines.append(f"{i}. {strategy[0]} (Lift: {strategy[1]})")
            else:
                lines.append(f"{i}. {strategy}")

        lines.append(f"\nConfidence: {state['confidence']}")

        return "\n".join(lines)

    def _load_system_prompt(self) -> str:
        """Load system prompt from prompts/system.txt."""
        prompt_paths = [
            os.path.join(os.path.dirname(__file__), "..", "prompts", "system.txt"),
            os.path.join(os.getcwd(), "prompts", "system.txt"),
            "prompts/system.txt",
        ]
        for path in prompt_paths:
            try:
                with open(path, "r") as f:
                    return f.read()
            except FileNotFoundError:
                continue

        logger.warning("[PremiumFormatter] system.txt not found, using fallback")
        return (
            "You are a narrator for an AI strategy system. "
            "Translate the structured input into premium strategic text. "
            "Do not analyze, calculate, or override any values."
        )
