Create a new deterministic module named next_video_blueprint_engine.py.

Purpose:
Generate structured next-upload guidance based on the primary constraint.

The engine must NOT use LLMs.

Class name:
NextVideoBlueprintEngine

Method:
generate(primary_constraint)

Output format:

{
  "next_video_direction": "",
  "opening_approach": "",
  "content_structure": "",
  "creator_action": ""
}

Rules:

RETENTION constraint:
direction → focus on strong opening moment
opening → start with exciting moment immediately
structure → deliver payoff early
action → ensure first 3 seconds show value

CTR constraint:
direction → improve packaging
opening → introduce clear curiosity immediately
structure → align video promise with thumbnail/title
action → make viewer understand value instantly

CONVERSION constraint:
direction → increase perceived value
opening → explain what viewer will gain
structure → highlight transformation or takeaway
action → remind viewer why channel is worth subscribing

SHORTS constraint:
direction → experiment with longer storytelling
opening → show context quickly
structure → develop narrative beyond short clip
action → test longer watch sessions

GROWTH constraint:
direction → explore adjacent topic
opening → connect to existing audience interest
structure → expand theme gradually
action → test new topic while keeping familiar format

Return structured blueprint dictionary.
Example Python Implementation

Your Antigravity IDE will generate something like this:
class NextVideoBlueprintEngine:

    def generate(self, primary_constraint):

        if primary_constraint == "retention":
            return {
                "next_video_direction": "Create a video where the most exciting moment appears immediately.",
                "opening_approach": "Start the video with the most surprising or engaging moment.",
                "content_structure": "Deliver the key payoff early and remove slow introductions.",
                "creator_action": "Ensure the first 3 seconds clearly show why the viewer should keep watching."
            }

        elif primary_constraint == "ctr":
            return {
                "next_video_direction": "Improve video packaging so viewers instantly understand the value.",
                "opening_approach": "Open with a moment that confirms the promise of the video.",
                "content_structure": "Align the content with the curiosity created by the title and thumbnail.",
                "creator_action": "Make the video's purpose obvious in the first few seconds."
            }

        elif primary_constraint == "conversion":
            return {
                "next_video_direction": "Focus on delivering strong value that encourages viewers to subscribe.",
                "opening_approach": "Start by explaining what the viewer will gain from watching.",
                "content_structure": "Highlight transformation, learning, or entertainment payoff.",
                "creator_action": "Remind viewers why the channel consistently delivers value."
            }

        elif primary_constraint == "shorts":
            return {
                "next_video_direction": "Experiment with longer storytelling instead of short clips.",
                "opening_approach": "Introduce context quickly so viewers understand the story.",
                "content_structure": "Develop a narrative rather than a quick moment.",
                "creator_action": "Test videos that encourage longer watch sessions."
            }

        else:
            return {
                "next_video_direction": "Explore an adjacent topic connected to your current content.",
                "opening_approach": "Connect the topic to something your audience already enjoys.",
                "content_structure": "Expand the theme gradually without changing the core style.",
                "creator_action": "Test a slightly new direction while maintaining familiar elements."
            }
            Where It Fits

Add to UnifiedEngineOrchestrator:
RetentionDiagnosisEngine
CTRDiagnosisEngine
ConversionRateAnalyzer
ShortsImpactAnalyzer
GrowthTrendExplanationEngine
StrategyRankingEngine
NextVideoBlueprintEngine   ← NEW