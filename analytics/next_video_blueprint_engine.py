"""
NextVideoBlueprintEngine v1 — Deterministic Next-Upload Guidance.

Generates structured next-upload direction based on the primary constraint.

Input: primary_constraint (str)
Output: next_video_direction, opening_approach, content_structure, creator_action

No LLM. No narrative. Fully deterministic.
"""

import logging

logger = logging.getLogger(__name__)


class NextVideoBlueprintEngine:
    """
    Deterministic next-video blueprint generator.

    Maps primary constraint to structured upload guidance.
    No LLM. No speculation. No creative content generation.
    """

    def generate(self, primary_constraint: str) -> dict:
        """
        Generate next-upload blueprint from primary constraint.

        Args:
            primary_constraint: The primary growth constraint
                (retention, ctr, conversion, shorts, growth).

        Returns:
            Structured blueprint dict with 4 keys.
        """
        if not isinstance(primary_constraint, str):
            raise ValueError(
                f"primary_constraint must be a string, got {type(primary_constraint).__name__}"
            )

        constraint = primary_constraint.lower().strip()

        if constraint == "retention":
            blueprint = {
                "next_video_direction": "Create a video where the most exciting moment appears immediately.",
                "opening_approach": "Start the video with the most surprising or engaging moment.",
                "content_structure": "Deliver the key payoff early and remove slow introductions.",
                "creator_action": "Ensure the first 3 seconds clearly show why the viewer should keep watching.",
            }

        elif constraint == "ctr":
            blueprint = {
                "next_video_direction": "Improve video packaging so viewers instantly understand the value.",
                "opening_approach": "Open with a moment that confirms the promise of the video.",
                "content_structure": "Align the content with the curiosity created by the title and thumbnail.",
                "creator_action": "Make the video's purpose obvious in the first few seconds.",
            }

        elif constraint == "conversion":
            blueprint = {
                "next_video_direction": "Focus on delivering strong value that encourages viewers to subscribe.",
                "opening_approach": "Start by explaining what the viewer will gain from watching.",
                "content_structure": "Highlight transformation, learning, or entertainment payoff.",
                "creator_action": "Remind viewers why the channel consistently delivers value.",
            }

        elif constraint == "shorts":
            blueprint = {
                "next_video_direction": "Experiment with longer storytelling instead of short clips.",
                "opening_approach": "Introduce context quickly so viewers understand the story.",
                "content_structure": "Develop a narrative rather than a quick moment.",
                "creator_action": "Test videos that encourage longer watch sessions.",
            }

        elif constraint == "growth":
            blueprint = {
                "next_video_direction": "Explore an adjacent topic connected to your current content.",
                "opening_approach": "Connect the topic to something your audience already enjoys.",
                "content_structure": "Expand the theme gradually without changing the core style.",
                "creator_action": "Test a slightly new direction while maintaining familiar elements.",
            }

        else:
            # Fallback for any unknown constraint
            blueprint = {
                "next_video_direction": "Explore an adjacent topic connected to your current content.",
                "opening_approach": "Connect the topic to something your audience already enjoys.",
                "content_structure": "Expand the theme gradually without changing the core style.",
                "creator_action": "Test a slightly new direction while maintaining familiar elements.",
            }

        logger.info(
            f"[NextVideoBlueprint] constraint={constraint}, "
            f"direction={blueprint['next_video_direction'][:50]}..."
        )

        return blueprint
