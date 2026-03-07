"""
TopicPatternAnalyzer v1 — Deterministic Theme Detection.

Analyzes a creator's video library to detect top-performing themes.

Input: video_library (list of dicts with title and views)
Output: top_theme, top_theme_median_views, weakest_theme,
        weakest_theme_median_views, theme_concentration

No LLM. No external APIs. Fully deterministic.
"""

import logging
import statistics
from collections import defaultdict

logger = logging.getLogger(__name__)


class TopicPatternAnalyzer:
    """
    Deterministic theme pattern analyzer.

    Groups videos by extracted theme keywords, computes median views
    per theme, and identifies top/weakest themes with concentration level.
    """

    # Common stop words to skip when extracting themes
    STOP_WORDS = frozenset({
        "a", "an", "the", "my", "i", "me", "we", "our", "you", "your",
        "is", "are", "was", "were", "be", "been",
        "in", "on", "at", "to", "for", "of", "with", "by", "from",
        "and", "or", "but", "not", "no", "so", "if", "as",
        "this", "that", "it", "its", "how", "what", "why", "when",
        "who", "which", "do", "does", "did", "has", "have", "had",
        "will", "would", "can", "could", "should",
        "new", "vs", "part", "ep", "episode",
    })

    def extract_theme(self, title: str) -> str:
        """
        Extract a simple theme from a video title.

        Uses first 2 meaningful (non-stop) words as the theme key.

        Args:
            title: Video title string.

        Returns:
            Theme string (lowercased, 1-2 words).
        """
        words = title.lower().split()
        # Filter out stop words and very short tokens
        meaningful = [w for w in words if w not in self.STOP_WORDS and len(w) > 1]

        if len(meaningful) >= 2:
            return " ".join(meaningful[:2])
        elif meaningful:
            return meaningful[0]
        elif words:
            return " ".join(words[:2]) if len(words) >= 2 else words[0]
        return "unknown"

    def analyze(self, video_library: list) -> dict:
        """
        Analyze video library for theme patterns.

        Args:
            video_library: List of dicts, each with 'title' (str)
                and 'views' (int).

        Returns:
            Dict with top_theme, top_theme_median_views,
            weakest_theme, weakest_theme_median_views,
            theme_concentration.
        """
        if not isinstance(video_library, list):
            raise ValueError(
                f"video_library must be a list, got {type(video_library).__name__}"
            )

        if not video_library:
            return {
                "top_theme": "unknown",
                "top_theme_median_views": 0,
                "weakest_theme": "unknown",
                "weakest_theme_median_views": 0,
                "theme_concentration": "low",
            }

        # Group views by theme
        theme_views = defaultdict(list)

        for video in video_library:
            if not isinstance(video, dict):
                continue
            title = video.get("title", "")
            views = video.get("views", 0)
            if not isinstance(views, (int, float)):
                views = 0
            theme = self.extract_theme(str(title))
            theme_views[theme].append(views)

        if not theme_views:
            return {
                "top_theme": "unknown",
                "top_theme_median_views": 0,
                "weakest_theme": "unknown",
                "weakest_theme_median_views": 0,
                "theme_concentration": "low",
            }

        # Compute median views per theme
        theme_medians = {
            theme: statistics.median(views)
            for theme, views in theme_views.items()
        }

        # Sort by median views descending
        sorted_themes = sorted(
            theme_medians.items(),
            key=lambda x: x[1],
            reverse=True,
        )

        top_theme, top_views = sorted_themes[0]
        weakest_theme, weak_views = sorted_themes[-1]

        # Determine concentration
        num_themes = len(theme_views)
        if num_themes <= 2:
            concentration = "high"
        elif num_themes <= 4:
            concentration = "moderate"
        else:
            concentration = "low"

        result = {
            "top_theme": top_theme,
            "top_theme_median_views": int(top_views),
            "weakest_theme": weakest_theme,
            "weakest_theme_median_views": int(weak_views),
            "theme_concentration": concentration,
        }

        logger.info(
            f"[TopicPattern] themes={num_themes}, "
            f"top={top_theme} ({int(top_views)} views), "
            f"concentration={concentration}"
        )

        return result
