"""
Phase 1.3 — Pattern Intelligence Engine

Deterministic cross-video pattern analysis layer.
Extracts keywords from video titles, clusters them by dominant token, and computes theme/format biases without any LLM reasoning.
"""

import re
import statistics
from collections import defaultdict
from typing import Any, Optional

# Expanded stop words — nouns should dominate, not adjectives or descriptors
_STOP_WORDS = {
    "the", "a", "an", "and", "or", "to", "of", "in", "on",
    "with", "for", "is", "are", "was", "were",
    "my", "your", "our", "this", "that",
    # Format words
    "video", "shorts", "short",
    # Adjective-based anchors — prevent descriptor-dominated themes
    "little", "big", "small", "full", "fun",
    "epic", "amazing", "cute", "happy",
    # Generic filler
    "like", "just", "really", "very", "much", "more",
    # Pronouns and common verbs
    "if", "but", "so", "up", "be", "do", "we", "us",
    "they", "them", "he", "she", "it", "as", "by",
    "will", "not", "all", "out", "about", "get", "make",
    "new", "best", "top",
    # Creator name
    "mihir",
    # Format words extended
    "videos", "vlog", "vlogs",
    # Generic emotional
    "love",
}


def tokenize_title(title: str) -> list[str]:
    """
    Lowercase, strip emojis/punctuation, remove stopwords & hashtags,
    and keep only tokens > 3 characters.
    """
    if not title:
        return []

    # Lowercase and remove anything that isn't alphanumeric or whitespace
    clean_title = re.sub(r'[^\w\s]', ' ', title.lower())
    
    tokens = []
    for word in clean_title.split():
        # Keep words > 3 chars that are not common stop words
        if len(word) > 3 and word not in _STOP_WORDS:
            tokens.append(word)

    return tokens


def cluster_by_keyword(videos: list[dict]) -> dict[str, list[dict]]:
    """
    Group videos by semantic topic categories.

    Layer 1: Match videos to predefined topic categories using keyword groups.
    Layer 2: Fall back to dominant token clustering for uncategorized videos.

    Returns: {theme_label: [video_dict, ...]}
    """
    # Semantic topic categories — keyword groups mapped to human-readable labels
    TOPIC_CATEGORIES = {
        "playground adventure": [
            "play", "playground", "park", "zone", "swing", "slide",
            "playzone", "adventure", "outdoor", "climbing",
            "level", "next", "kidsmasti", "vanicemall",
            "vanicemallgreaternoida",
        ],
        "school morning routine": [
            "school", "morning", "routine", "uniform", "homework",
            "study", "padaku", "intelligent",
        ],
        "dance performance": [
            "dance", "dancer", "dancing", "danceindiadance",
            "dhurandhar", "moves",
        ],
        "family celebration": [
            "birthday", "celebration", "party", "festival", "gift",
            "diwali", "surprise", "excited",
        ],
        "creative activity": [
            "drawing", "animation", "creation", "imagination", "craft",
            "sketch", "animate", "painting",
        ],
        "outdoor exploration": [
            "cycling", "garden", "chameleon", "flowers", "nature",
            "home", "society", "walk", "freshness",
        ],
        "food adventure": [
            "eating", "food", "foodie", "kabab", "streetfood",
            "restaurant", "taste", "recipe", "cook", "laphing",
        ],
        "travel vlog": [
            "travel", "trip", "visit", "mall", "metro",
            "noida", "delhi", "california", "zoo", "venice",
            "greaternoida", "greaternoidavlog", "galgotiauniversity",
            "vlogger", "dailyvlog", "dailyvideo",
        ],
        "family fun": [
            "masti", "shararat", "monkey", "crazy", "funny",
            "karting", "race", "enjoy", "balloon",
            "familytime", "familyvlog",
        ],
    }

    clusters = defaultdict(list)
    uncategorized = []

    for v in videos:
        title = v.get("title", "")
        tokens = set(tokenize_title(title))
        matched = False

        # Layer 1: Semantic category matching
        best_category = None
        best_score = 0

        for category, keywords in TOPIC_CATEGORIES.items():
            score = len(tokens & set(keywords))
            if score > best_score:
                best_score = score
                best_category = category

        if best_category and best_score >= 1:
            clusters[best_category].append(v)
            matched = True

        if not matched:
            uncategorized.append(v)

    # Layer 2: Keyword fallback for uncategorized videos
    if uncategorized:
        token_freqs = defaultdict(int)
        video_tokens = []

        for v in uncategorized:
            title = v.get("title", "")
            tokens = tokenize_title(title)
            video_tokens.append((v, tokens))
            for token in set(tokens):
                token_freqs[token] += 1

        valid_tokens = {t for t, f in token_freqs.items() if f >= 3}

        for v, tokens in video_tokens:
            candidates = [t for t in set(tokens) if t in valid_tokens]
            if not candidates:
                continue
            best = max(candidates, key=lambda t: token_freqs[t])
            clusters[best].append(v)

    return dict(clusters)


def compute_theme_stats(theme_videos: list[dict]) -> dict[str, Any]:
    """
    Compute aggregate statistics for a cluster of videos.
    Requires at least 1 video.
    """
    if not theme_videos:
        return {
            "median_views": 0,
            "median_avg_view_pct": 0.0,
            "avg_percentile_rank": 0.0,
            "performance_tier_distribution": {},
            "video_count": 0
        }
        
    views = [v.get("views", 0) or 0 for v in theme_videos]
    # Handle cases where avg_view_pct might be missing or None
    view_pcts = [v.get("averageViewPercentage", 0.0) or 0.0 for v in theme_videos]
    ranks = [v.get("percentile_rank", 0.0) or 0.0 for v in theme_videos]
    
    tiers = [v.get("performance_tier", "Unknown") for v in theme_videos]
    tier_dist = defaultdict(int)
    for t in tiers:
        tier_dist[t] += 1

    return {
        "median_views": int(statistics.median(views)),
        "median_avg_view_pct": round(statistics.median(view_pcts), 1),
        "avg_percentile_rank": round(sum(ranks) / len(ranks), 1) if ranks else 0.0,
        "performance_tier_distribution": dict(tier_dist),
        "video_count": len(theme_videos),
    }


def detect_top_theme(clusters: dict[str, list[dict]]) -> tuple[Optional[str], dict[str, Any]]:
    """
    Find the cluster with the highest median views.
    Only considers clusters with size >= 3.
    """
    best_theme = None
    best_stats = None
    max_median = -1

    for theme, videos in clusters.items():
        if len(videos) < 3:
            continue
            
        stats = compute_theme_stats(videos)
        if stats["median_views"] > max_median:
            max_median = stats["median_views"]
            best_theme = theme
            best_stats = stats

    if not best_theme:
        return None, {}
        
    return best_theme, best_stats


def detect_underperforming_theme(clusters: dict[str, list[dict]]) -> tuple[Optional[str], dict[str, Any]]:
    """
    Find the cluster with the lowest median views.
    Only considers clusters with size >= 3.
    """
    worst_theme = None
    worst_stats = None
    min_median = float('inf')

    for theme, videos in clusters.items():
        if len(videos) < 3:
            continue
            
        stats = compute_theme_stats(videos)
        if stats["median_views"] < min_median:
            min_median = stats["median_views"]
            worst_theme = theme
            worst_stats = stats

    if not worst_theme or min_median == float('inf'):
        return None, {}
        
    return worst_theme, worst_stats


def detect_format_bias(videos: list[dict]) -> dict[str, Any]:
    """
    Compare Shorts vs Standard videos by median views.
    Uses duration_seconds <= 60 as the Shorts classifier.
    Returns None for medians when a side has no data.
    """
    shorts = []
    standard = []

    for v in videos:
        # Classify purely by duration — <= 60s is a Short
        duration = v.get("duration_seconds", 0) or 0
        if duration > 0 and duration <= 60:
            shorts.append(v)
        elif duration > 60:
            standard.append(v)
        # If duration is 0/missing, skip — can't classify

    shorts_views = [v.get("views", 0) or 0 for v in shorts]
    standard_views = [v.get("views", 0) or 0 for v in standard]

    shorts_median = int(statistics.median(shorts_views)) if shorts_views else None
    standard_median = int(statistics.median(standard_views)) if standard_views else None

    if shorts_median is None or standard_median is None:
        return {
            "bias": "Insufficient Data",
            "shorts_median": shorts_median,
            "standard_median": standard_median,
            "shorts_count": len(shorts),
            "standard_count": len(standard)
        }

    if shorts_median > standard_median * 1.5:
        bias = "Strong Shorts Bias"
    elif standard_median > shorts_median * 1.5:
        bias = "Strong Standard Bias"
    elif shorts_median > standard_median:
        bias = "Slight Shorts Bias"
    else:
        bias = "Slight Standard Bias"

    return {
        "bias": bias,
        "shorts_median": shorts_median,
        "standard_median": standard_median,
        "shorts_count": len(shorts),
        "standard_count": len(standard)
    }
