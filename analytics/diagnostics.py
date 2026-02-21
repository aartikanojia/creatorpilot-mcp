"""
Video Performance Diagnostics — Phase 1.1

Deterministic, pure-Python diagnostics module.
All functions are stateless, require no external dependencies,
and accept None gracefully (returns "Unknown" for missing data).

Used by execute.py to attach structured diagnostic fields to the
video_analysis LLM prompt so the LLM reasons from labels, not raw numbers.
"""

import logging
import statistics
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Retention Classification
# ---------------------------------------------------------------------------

def classify_retention(avg_view_percentage: Optional[float]) -> str:
    """
    Classify retention quality from avg_view_percentage.

    Thresholds (YouTube creator benchmark):
        ≥60  → "Strong Hook"
        45–59 → "Healthy Retention"
        30–44 → "Moderate Drop-off"
        <30   → "Weak Retention"
        None  → "Unknown"

    Args:
        avg_view_percentage: 0–100 float, or None if unavailable.

    Returns:
        Human-readable retention category string.
    """
    if avg_view_percentage is None:
        return "Unknown"

    pct = float(avg_view_percentage)
    if pct >= 60:
        return "Strong Hook"
    elif pct >= 45:
        return "Healthy Retention"
    elif pct >= 30:
        return "Moderate Drop-off"
    else:
        return "Weak Retention"


# ---------------------------------------------------------------------------
# Channel Median
# ---------------------------------------------------------------------------

def compute_channel_median(videos: list) -> dict:
    """
    Compute median view_count (and avg_view_percentage if available)
    for the last N videos.

    Args:
        videos: List of Video ORM objects (or dicts with 'view_count').
                Expects up to 30 most-recent videos.

    Returns:
        dict with keys:
            "median_views" (int|None)
            "median_avg_view_pct" (float|None)
    """
    if not videos:
        return {"median_views": None, "median_avg_view_pct": None}

    view_counts = []
    view_pcts = []

    for v in videos:
        # Support both ORM objects and plain dicts
        if isinstance(v, dict):
            vc = v.get("view_count") or v.get("views")
            vp = v.get("avg_view_percentage")
        else:
            vc = getattr(v, "view_count", None)
            vp = getattr(v, "avg_view_percentage", None)

        if vc is not None:
            try:
                view_counts.append(int(vc))
            except (TypeError, ValueError):
                pass
        if vp is not None:
            try:
                view_pcts.append(float(vp))
            except (TypeError, ValueError):
                pass

    return {
        "median_views": int(statistics.median(view_counts)) if view_counts else None,
        "median_avg_view_pct": round(statistics.median(view_pcts), 2) if view_pcts else None,
    }


# ---------------------------------------------------------------------------
# Percentile Rank
# ---------------------------------------------------------------------------

def compute_percentile_rank(
    video_views: int,
    channel_views_list: list[int],
) -> Optional[float]:
    """
    Compute what percentile this video's view count is within the channel.

    Formula: (# of channel videos with views LESS THAN video_views / total) * 100

    Scale: 100 = best performer (beats all others)
           0   = worst performer (beats none)

    Args:
        video_views: View count for the video being analysed.
        channel_views_list: View counts for all other channel videos.

    Returns:
        Float 0.0–100.0 (rounded to 1dp), or None if list is empty.

    Examples:
        video_views=500, channel=[100,200,400,600,800] → 60.0
        (beats 3 out of 5 videos: 100, 200, 400)
    """
    if not channel_views_list:
        return None

    below = sum(1 for v in channel_views_list if v < video_views)
    percentile = (below / len(channel_views_list)) * 100
    return round(percentile, 1)


# ---------------------------------------------------------------------------
# Momentum Detection
# ---------------------------------------------------------------------------

def detect_momentum(
    last_7_days_views: Optional[int],
    previous_28_day_total: Optional[int],
) -> str:
    """
    Detect whether a video's viewership is Rising, Stable, or Declining.

    Compares last-7-day views to a weekly baseline derived from the
    previous 28-day total (previous_28 / 4 ≈ weekly average).

    Thresholds:
        ratio > 1.2 → "Rising"
        ratio 0.8–1.2 → "Stable"
        ratio < 0.8 → "Declining"
        missing data → "Unknown"

    Args:
        last_7_days_views: Views in the most recent 7 days.
        previous_28_day_total: Total views in the prior 28 days.

    Returns:
        Momentum category string.
    """
    if last_7_days_views is None or previous_28_day_total is None:
        return "Unknown"

    # Weekly baseline from the prior 28-day window
    weekly_baseline = previous_28_day_total / 4.0
    if weekly_baseline <= 0:
        return "Unknown"

    ratio = last_7_days_views / weekly_baseline
    logger.debug(
        f"[Diagnostics] Momentum ratio={ratio:.2f} "
        f"(last7={last_7_days_views}, baseline={weekly_baseline:.1f})"
    )

    if ratio > 1.2:
        return "Rising"
    elif ratio >= 0.8:
        return "Stable"
    else:
        return "Declining"


# ---------------------------------------------------------------------------
# Format Classification
# ---------------------------------------------------------------------------

def classify_format(
    duration_seconds: Optional[int],
    traffic_sources: Optional[dict],
) -> str:
    """
    Classify the video format based on duration and dominant traffic source.

    Logic:
        1. If Shorts traffic (SHORTS key) is dominant (≥50% of total), → "Shorts"
        2. Else by duration:
            < 65s   → "Short"
            65–480s → "Standard"
            > 480s  → "Long-form"
        3. Unknown if no data.

    Args:
        duration_seconds: Video length in seconds (from YouTube Data API).
        traffic_sources: Dict of traffic source → view count (may be None).

    Returns:
        Format label string.
    """
    # Check for Shorts-dominant traffic first (overrides duration)
    if traffic_sources and isinstance(traffic_sources, dict):
        total = sum(traffic_sources.values())
        shorts_views = traffic_sources.get("SHORTS", 0)
        if total > 0 and (shorts_views / total) >= 0.5:
            return "Shorts"

    if duration_seconds is None:
        return "Unknown"

    secs = int(duration_seconds)
    if secs < 65:
        return "Short"
    elif secs <= 480:
        return "Standard"
    else:
        return "Long-form"


# ---------------------------------------------------------------------------
# Performance Tier (composite)
# ---------------------------------------------------------------------------

def compute_performance_tier(
    percentile_rank: Optional[float],
    retention_category: str,
) -> str:
    """
    Compute overall performance tier — PERCENTILE IS PRIMARY.

    Percentile rank alone determines the tier boundary.
    Retention provides interpretive colour but MUST NOT contradict the
    percentile-based assignment (e.g. percentile=100 is always Top Performer
    regardless of retention; percentile=0 is always Underperformer).

    Tier mapping:
        ≥75  → "Top Performer"
        50–74 → "Above Average"
        25–49 → "Average"
        <25   → "Underperformer"
        None  → "Unknown"

    Args:
        percentile_rank: 0–100 percentile within channel (or None).
        retention_category: Output of classify_retention() — informational only.

    Returns:
        Performance tier label.
    """
    if percentile_rank is None:
        return "Unknown"

    if percentile_rank >= 75:
        return "Top Performer"
    elif percentile_rank >= 50:
        return "Above Average"
    elif percentile_rank >= 25:
        return "Average"
    else:
        return "Underperformer"
