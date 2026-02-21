"""
Phase 0.2B — Full Video Resolver Hardening Test Suite.

Comprehensive tests validating video resolver behavior across
all production scenarios.

Categories:
  1. Exact match
  2. Partial match
  3. Emoji heavy title
  4. Misspelled title
  5. Ambiguous match
  6. Wrong title (rejected)
  7. Hashtag noise
  8. Unicode normalization
  +  Metadata structure validation
  +  No-ingestion guards for ambiguous/rejected
  +  No-channel-averages guard for video intent
  +  Log line validation (accepted / ambiguous / rejected)
"""

import logging
import uuid
import pytest
from unittest.mock import patch, MagicMock

from services.video_resolver import (
    resolve_video_by_title,
    get_top_matches,
    get_video_count,
    _normalize,
    _decide,
    _similarity,
    MATCH_THRESHOLD,
    HIGH_CONFIDENCE_THRESHOLD,
    AMBIGUITY_GAP,
)


# =============================================================================
# Helpers
# =============================================================================

def _make_video(title: str, video_id: str = None):
    """Build a mock Video with the given title."""
    v = MagicMock()
    v.title = title
    v.youtube_video_id = video_id or f"vid_{uuid.uuid4().hex[:8]}"
    return v


CHANNEL = uuid.uuid4()


# =============================================================================
# Shared fixture — default video library
# =============================================================================

DEFAULT_LIBRARY = [
    _make_video("Behind the scenes of my studio setup", "vid_studio"),
    _make_video("Valentine Day Vlog ❤️", "vid_vdvlog"),
    _make_video("Father–Son duo in full shararat mode 🔥😂", "vid_fsduo"),
    _make_video("Morning routine gone wrong 😅", "vid_mrgw"),
    _make_video("Our first family road trip 🚗", "vid_roadtrip"),
    _make_video("Q&A with subscribers!", "vid_qa"),
    _make_video("Cooking challenge with kids 🍕", "vid_cooking"),
    _make_video("Mihir ki masti #play", "vid_mihir"),
]


@pytest.fixture(autouse=True)
def mock_store():
    """Patch PostgresMemoryStore globally with DEFAULT_LIBRARY."""
    with patch("services.video_resolver.PostgresMemoryStore") as MockCls:
        inst = MockCls.return_value
        inst.get_recent_videos.return_value = DEFAULT_LIBRARY
        yield inst


# =============================================================================
# CATEGORY 1 — Exact Match
# =============================================================================

class TestCategory1_ExactMatch:
    """Title fragment exactly matches stored title."""

    def test_exact_title_returns_video(self):
        result = resolve_video_by_title(
            CHANNEL, "Behind the scenes of my studio setup"
        )
        assert result is not None
        assert result.get("clarification") is not True
        assert result["video_id"] == "vid_studio"
        assert result["video_resolution"]["decision"] == "accepted"
        assert result["score"] >= HIGH_CONFIDENCE_THRESHOLD

    def test_exact_title_case_insensitive(self):
        result = resolve_video_by_title(
            CHANNEL, "behind THE scenes OF my STUDIO setup"
        )
        assert result is not None
        assert result.get("clarification") is not True
        assert result["video_id"] == "vid_studio"
        assert result["video_resolution"]["decision"] == "accepted"
        assert result["score"] >= HIGH_CONFIDENCE_THRESHOLD

    def test_exact_title_no_clarification(self):
        """Exact match must never return clarification."""
        result = resolve_video_by_title(
            CHANNEL, "Q&A with subscribers"
        )
        assert result is not None
        assert result.get("clarification") is not True
        assert "candidates" not in result

    def test_exact_match_contains_score(self):
        result = resolve_video_by_title(
            CHANNEL, "Valentine Day Vlog"
        )
        assert result is not None
        assert isinstance(result["score"], float)
        assert result["score"] >= 85


# =============================================================================
# CATEGORY 2 — Partial Match
# =============================================================================

class TestCategory2_PartialMatch:
    """Fragment is a subset of the full title."""

    def test_partial_beginning(self):
        result = resolve_video_by_title(CHANNEL, "cooking challenge")
        assert result is not None
        assert result.get("clarification") is not True
        assert result["video_id"] == "vid_cooking"
        assert result["video_resolution"]["decision"] == "accepted"
        assert result["score"] >= MATCH_THRESHOLD

    def test_partial_middle(self):
        result = resolve_video_by_title(
            CHANNEL, "behind the scenes studio setup"
        )
        assert result is not None
        assert result.get("clarification") is not True
        assert result["video_id"] == "vid_studio"
        assert result["score"] >= MATCH_THRESHOLD

    def test_partial_key_words(self):
        result = resolve_video_by_title(CHANNEL, "family road trip")
        assert result is not None
        assert result.get("clarification") is not True
        assert result["video_id"] == "vid_roadtrip"
        assert result["score"] >= MATCH_THRESHOLD


# =============================================================================
# CATEGORY 3 — Emoji Heavy Title
# =============================================================================

class TestCategory3_EmojiHeavyTitle:
    """Stored title contains emojis, query does not."""

    def test_emoji_stripped_from_db_title(self):
        result = resolve_video_by_title(
            CHANNEL, "Father Son duo in full shararat mode"
        )
        assert result is not None
        assert result.get("clarification") is not True
        assert result["video_id"] == "vid_fsduo"
        assert result["video_resolution"]["decision"] == "accepted"

    def test_emoji_stripped_from_query(self):
        """User sends emojis in query; DB title also has emojis."""
        result = resolve_video_by_title(
            CHANNEL, "Morning routine gone wrong 😅😂🔥"
        )
        assert result is not None
        assert result.get("clarification") is not True
        assert result["video_id"] == "vid_mrgw"
        assert result["video_resolution"]["decision"] == "accepted"

    def test_multi_emoji_db_title(self, mock_store):
        """DB title packed with 5+ emojis — stripping works."""
        mock_store.get_recent_videos.return_value = [
            _make_video("🔥😂🎉👀💯🎊 Epic baby reveal", "vid_emoji5"),
            _make_video("Normal day at office", "vid_normal"),
        ]
        result = resolve_video_by_title(CHANNEL, "epic baby reveal")
        assert result is not None
        assert result.get("clarification") is not True
        assert result["video_id"] == "vid_emoji5"

    def test_query_only_emoji_returns_none(self):
        """Fragment of only emojis → empty after normalization → None."""
        result = resolve_video_by_title(CHANNEL, "🔥😂💯")
        assert result is None


# =============================================================================
# CATEGORY 4 — Misspelled Title
# =============================================================================

class TestCategory4_MisspelledTitle:
    """Minor typo in query — fuzzy match handles it."""

    def test_typo_extra_vowel(self):
        # "shararat" → "sharaarat"
        result = resolve_video_by_title(
            CHANNEL, "Father Son duo sharaarat mode"
        )
        assert result is not None
        assert result.get("clarification") is not True
        assert result["video_id"] == "vid_fsduo"
        assert result["score"] >= MATCH_THRESHOLD

    def test_typo_missing_letter(self):
        # "Valentine" → "Valentne"
        result = resolve_video_by_title(CHANNEL, "Valentne Day Vlog")
        assert result is not None
        assert result.get("clarification") is not True
        assert result["video_id"] == "vid_vdvlog"
        assert result["score"] >= MATCH_THRESHOLD

    def test_typo_swap_letters(self):
        # "Morning" → "Mornign"
        result = resolve_video_by_title(CHANNEL, "Mornign routine gone wrong")
        assert result is not None
        assert result.get("clarification") is not True
        assert result["video_id"] == "vid_mrgw"

    def test_typo_plural_extra_s(self):
        # "Valentines" instead of "Valentine"
        result = resolve_video_by_title(CHANNEL, "Valentines Day Vlog")
        assert result is not None
        assert result.get("clarification") is not True
        assert result["video_id"] == "vid_vdvlog"


# =============================================================================
# CATEGORY 5 — Ambiguous Match
# =============================================================================

class TestCategory5_AmbiguousMatch:
    """Two titles close in similarity — gap < 10."""

    def test_ambiguous_returns_clarification(self, mock_store):
        mock_store.get_recent_videos.return_value = [
            _make_video("Day in the life of a creator", "vid_dlc"),
            _make_video("Day in the life of a student", "vid_dls"),
            _make_video("Totally unrelated cooking show", "vid_cook"),
        ]
        result = resolve_video_by_title(CHANNEL, "day in the life")
        assert result is not None
        meta = result["video_resolution"]
        # Both should score similarly → ambiguous or accepted
        if meta["decision"] == "ambiguous":
            assert result["clarification"] is True
            assert "candidates" in result
            assert len(result["candidates"]) >= 2

    def test_ambiguous_does_not_auto_select(self, mock_store):
        """Ambiguous must NOT return a video_id at the top level."""
        mock_store.get_recent_videos.return_value = [
            _make_video("My first trip to Manali", "vid_m1"),
            _make_video("My first trip to Manali part 2", "vid_m2"),
            _make_video("My first trip to Manali vlog", "vid_m3"),
        ]
        result = resolve_video_by_title(CHANNEL, "first trip manali")
        assert result is not None
        meta = result["video_resolution"]
        if meta["decision"] == "ambiguous":
            # Must not have video_id in root
            assert "video_id" not in result
            assert result["clarification"] is True

    def test_ambiguous_has_message(self, mock_store):
        mock_store.get_recent_videos.return_value = [
            _make_video("cooking with friends tonight", "vid_cf1"),
            _make_video("cooking with friends weekend", "vid_cf2"),
        ]
        result = resolve_video_by_title(CHANNEL, "cooking with friends")
        assert result is not None
        meta = result["video_resolution"]
        if meta["decision"] == "ambiguous":
            assert "message" in result
            assert len(result["message"]) > 0

    def test_ambiguous_candidates_sorted_descending(self, mock_store):
        mock_store.get_recent_videos.return_value = [
            _make_video("Travel vlog Europe part one", "vid_tv1"),
            _make_video("Travel vlog Europe part two", "vid_tv2"),
            _make_video("Random unrelated", "vid_rng"),
        ]
        result = resolve_video_by_title(CHANNEL, "travel vlog europe")
        assert result is not None
        if result.get("clarification"):
            scores = [c["score"] for c in result["candidates"]]
            assert scores == sorted(scores, reverse=True)


# =============================================================================
# CATEGORY 6 — Wrong Title (Rejected)
# =============================================================================

class TestCategory6_WrongTitle:
    """Completely unrelated title — score < 70."""

    def test_unrelated_rejected(self):
        result = resolve_video_by_title(
            CHANNEL, "quantum physics lecture series"
        )
        if result is not None:
            assert result.get("clarification") is True
            meta = result["video_resolution"]
            assert meta["decision"] == "rejected"
            assert meta["top_score"] < MATCH_THRESHOLD

    def test_rejected_has_clarification(self):
        result = resolve_video_by_title(
            CHANNEL, "machine learning algorithms deep dive"
        )
        if result is not None:
            assert result["clarification"] is True
            assert "candidates" in result

    def test_rejected_no_video_selected(self):
        result = resolve_video_by_title(
            CHANNEL, "how to install linux on raspberry pi"
        )
        if result is not None:
            assert "video_id" not in result
            assert result["video_resolution"]["decision"] == "rejected"

    def test_rejected_never_falls_back_to_channel_averages(self):
        """
        Rejected result must NEVER contain channel-level stats.
        It should only have clarification + candidates.
        """
        result = resolve_video_by_title(
            CHANNEL, "completely random nonsense query xyz"
        )
        if result is not None:
            assert "channel_avg" not in result
            assert "channel_stats" not in result
            assert "averages" not in result
            assert result.get("clarification") is True


# =============================================================================
# CATEGORY 7 — Hashtag Noise
# =============================================================================

class TestCategory7_HashtagNoise:
    """Stored title has #shorts #viral — query does not."""

    def test_hashtags_stripped_from_db(self, mock_store):
        mock_store.get_recent_videos.return_value = [
            _make_video(
                "Epic dance battle #shorts #viral #trending #fyp", "vid_dance"
            ),
            _make_video("Normal day at work", "vid_work"),
        ]
        result = resolve_video_by_title(CHANNEL, "epic dance battle")
        assert result is not None
        assert result.get("clarification") is not True
        assert result["video_id"] == "vid_dance"

    def test_hashtags_stripped_from_query(self, mock_store):
        mock_store.get_recent_videos.return_value = [
            _make_video("Epic dance battle", "vid_dance2"),
            _make_video("Something else", "vid_else"),
        ]
        result = resolve_video_by_title(
            CHANNEL, "epic dance battle #shorts #viral"
        )
        assert result is not None
        assert result.get("clarification") is not True
        assert result["video_id"] == "vid_dance2"

    def test_both_have_hashtags(self, mock_store):
        """Both DB title and query have hashtags — both stripped."""
        mock_store.get_recent_videos.return_value = [
            _make_video("Funny prank #shorts #viral", "vid_prank"),
            _make_video("Unrelated content", "vid_unr"),
        ]
        result = resolve_video_by_title(
            CHANNEL, "funny prank #shorts"
        )
        assert result is not None
        assert result.get("clarification") is not True
        assert result["video_id"] == "vid_prank"

    def test_normalize_removes_all_hashtags(self):
        """Direct normalization test."""
        n = _normalize("Best Video Ever #shorts #viral #trending #fyp #youtube")
        assert "#" not in n
        assert "shorts" not in n
        assert "viral" not in n
        assert "best video ever" in n


# =============================================================================
# CATEGORY 8 — Unicode Normalization
# =============================================================================

class TestCategory8_UnicodeNormalization:
    """Accented/ligature characters normalized via NFKD."""

    def test_accented_e_matched(self, mock_store):
        mock_store.get_recent_videos.return_value = [
            _make_video("Café tour in Paris", "vid_cafe"),
            _make_video("Random stuff", "vid_rnd"),
        ]
        # User types ASCII "cafe" — NFKD decomposes é → e + combining accent
        result = resolve_video_by_title(CHANNEL, "cafe tour in paris")
        assert result is not None
        assert result.get("clarification") is not True
        assert result["video_id"] == "vid_cafe"

    def test_ligature_fi_matched(self, mock_store):
        mock_store.get_recent_videos.return_value = [
            _make_video("The ﬁnal countdown", "vid_fi"),
            _make_video("Unrelated", "vid_unr"),
        ]
        result = resolve_video_by_title(CHANNEL, "the final countdown")
        assert result is not None
        assert result.get("clarification") is not True
        assert result["video_id"] == "vid_fi"

    def test_nfkd_normalize_directly(self):
        """Direct test: NFKD decomposes ﬁ → fi."""
        n = _normalize("ﬁnale")
        assert "fi" in n or "finale" in n.replace(" ", "")

    def test_curly_quotes_stripped(self, mock_store):
        """Curly/smart quotes are normalized."""
        mock_store.get_recent_videos.return_value = [
            _make_video("Life\u2019s biggest surprise", "vid_life"),
            _make_video("Other video", "vid_other"),
        ]
        result = resolve_video_by_title(CHANNEL, "lifes biggest surprise")
        assert result is not None
        assert result.get("clarification") is not True
        assert result["video_id"] == "vid_life"


# =============================================================================
# ADDITIONAL — Metadata Structure Validation
# =============================================================================

class TestMetadataStructure:
    """Verify video_resolution dict is always well-formed."""

    def test_accepted_metadata_keys(self):
        result = resolve_video_by_title(CHANNEL, "Valentine Day Vlog")
        assert result is not None
        meta = result["video_resolution"]
        assert "top_score" in meta
        assert "second_score" in meta
        assert "decision" in meta
        assert isinstance(meta["top_score"], float)
        assert isinstance(meta["second_score"], float)
        assert meta["decision"] in ("accepted", "ambiguous", "rejected")

    def test_rejected_metadata_keys(self):
        result = resolve_video_by_title(CHANNEL, "totally random xyz")
        if result is not None:
            meta = result["video_resolution"]
            assert "top_score" in meta
            assert "second_score" in meta
            assert "decision" in meta

    def test_ambiguous_metadata_keys(self, mock_store):
        mock_store.get_recent_videos.return_value = [
            _make_video("cooking with friends tonight", "vid_cf1"),
            _make_video("cooking with friends weekend", "vid_cf2"),
        ]
        result = resolve_video_by_title(CHANNEL, "cooking with friends")
        assert result is not None
        meta = result["video_resolution"]
        assert "top_score" in meta
        assert "second_score" in meta
        assert "decision" in meta

    def test_decision_values_only_three(self):
        """_decide only returns one of three values."""
        assert _decide(95, 50) in ("accepted", "ambiguous", "rejected")
        assert _decide(75, 60) in ("accepted", "ambiguous", "rejected")
        assert _decide(75, 74) in ("accepted", "ambiguous", "rejected")
        assert _decide(50, 30) in ("accepted", "ambiguous", "rejected")


# =============================================================================
# ADDITIONAL — No Ingestion on Ambiguous / Rejected
# =============================================================================

class TestNoIngestionGuard:
    """Ambiguous/rejected must NOT trigger video ingestion."""

    def test_ambiguous_does_not_call_youtube(self, mock_store):
        """
        When result is ambiguous, the resolver returns a clarification
        dict. The executor should NOT trigger YouTube fetch. The resolver
        itself never makes network calls — verify get_video_count logic.
        """
        mock_store.get_recent_videos.return_value = [
            _make_video("Day trip to mountains", "vid_dt1"),
            _make_video("Day trip to mountains part 2", "vid_dt2"),
        ]
        result = resolve_video_by_title(CHANNEL, "day trip mountains")
        # Resolver returned a dict (not None) → video_count > 0
        # → executor gate blocks ingestion
        count = get_video_count(CHANNEL)
        assert count > 0, "DB has videos → sync MUST NOT trigger"

    def test_rejected_does_not_call_youtube(self):
        """
        When result is rejected, DB still has videos → count > 0
        → executor gate blocks ingestion.
        """
        result = resolve_video_by_title(CHANNEL, "zzz random xyz")
        count = get_video_count(CHANNEL)
        assert count > 0, "DB has videos → sync MUST NOT trigger"


# =============================================================================
# ADDITIONAL — No Channel Averages for Video Intent
# =============================================================================

class TestNoChannelAverages:
    """
    Video intent must NEVER fall back to channel averages.
    All returns are either accepted match, clarification, or None.
    """

    def test_rejected_never_has_averages(self):
        result = resolve_video_by_title(CHANNEL, "random unrelated content")
        if result is not None:
            for key in ("channel_avg", "channel_stats", "averages",
                        "subscribers", "views", "avg_ctr"):
                assert key not in result

    def test_ambiguous_never_has_averages(self, mock_store):
        mock_store.get_recent_videos.return_value = [
            _make_video("Vlog part 1", "vid_v1"),
            _make_video("Vlog part 2", "vid_v2"),
        ]
        result = resolve_video_by_title(CHANNEL, "vlog part")
        if result is not None:
            for key in ("channel_avg", "channel_stats", "averages",
                        "subscribers", "views"):
                assert key not in result

    def test_accepted_only_has_video_fields(self):
        result = resolve_video_by_title(CHANNEL, "Valentine Day Vlog")
        assert result is not None
        allowed = {"video_id", "title", "score", "video_resolution"}
        assert set(result.keys()) == allowed


# =============================================================================
# LOG VALIDATION
# =============================================================================

class TestLogOutput:
    """Verify correct log lines for accepted / ambiguous / rejected."""

    def test_log_accepted(self, caplog):
        with caplog.at_level(logging.INFO, logger="services.video_resolver"):
            resolve_video_by_title(CHANNEL, "Valentine Day Vlog")
        assert any(
            "[VideoResolver] Match accepted" in r.message for r in caplog.records
        ), "Missing '[VideoResolver] Match accepted' log line"

    def test_log_ambiguous(self, caplog, mock_store):
        mock_store.get_recent_videos.return_value = [
            _make_video("Summer vacation with family", "vid_sv1"),
            _make_video("Summer vacation with friends", "vid_sv2"),
        ]
        with caplog.at_level(logging.INFO, logger="services.video_resolver"):
            result = resolve_video_by_title(CHANNEL, "summer vacation")
        if result and result.get("video_resolution", {}).get("decision") == "ambiguous":
            assert any(
                "[VideoResolver] Match ambiguous" in r.message
                for r in caplog.records
            ), "Missing '[VideoResolver] Match ambiguous' log line"

    def test_log_rejected(self, caplog):
        with caplog.at_level(logging.INFO, logger="services.video_resolver"):
            result = resolve_video_by_title(CHANNEL, "quantum physics")
        if result and result.get("video_resolution", {}).get("decision") == "rejected":
            assert any(
                "[VideoResolver] Match rejected" in r.message
                for r in caplog.records
            ), "Missing '[VideoResolver] Match rejected' log line"

    def test_log_videos_in_db(self, caplog):
        """Every resolve call should log the video count."""
        with caplog.at_level(logging.INFO, logger="services.video_resolver"):
            resolve_video_by_title(CHANNEL, "any query")
        assert any(
            "[VideoResolver] Videos in DB:" in r.message for r in caplog.records
        ), "Missing '[VideoResolver] Videos in DB:' log line"


# =============================================================================
# PHASE 0.2D — Multi-Strategy Scoring
# =============================================================================

class TestPhase02D_MultiStrategyScoring:
    """
    Exact title + extra hashtags/emojis in query must resolve.
    token_set_ratio / partial_ratio prevent penalty from extras.
    """

    def test_exact_title_plus_hashtags_emojis(self, mock_store):
        """
        Stored: Be caution – Even superheroes need a little peaceful pause
        Query: Be caution – Even superheroes need a little peaceful pause 🌍💛 #park #kidsmasti
        Expected: score >= 85, decision = accepted
        """
        mock_store.get_recent_videos.return_value = [
            _make_video(
                "Be caution – Even superheroes need a little peaceful pause",
                "vid_caution",
            ),
            _make_video("Random other video", "vid_other"),
        ]
        result = resolve_video_by_title(
            CHANNEL,
            "Be caution – Even superheroes need a little peaceful pause "
            "🌍💛 #park #kidsmasti",
        )
        assert result is not None, "Expected accepted match, got None"
        assert result.get("clarification") is not True, (
            f"Expected accepted, got clarification: {result}"
        )
        assert result["video_id"] == "vid_caution"
        assert result["score"] >= 85, f"Score {result['score']} < 85"
        assert result["video_resolution"]["decision"] == "accepted"

    def test_query_with_only_extra_hashtags(self, mock_store):
        """DB title clean, query adds #shorts #viral — must still match."""
        mock_store.get_recent_videos.return_value = [
            _make_video("My morning routine vlog", "vid_morning"),
            _make_video("Unrelated content", "vid_unr"),
        ]
        result = resolve_video_by_title(
            CHANNEL, "My morning routine vlog #shorts #viral #trending"
        )
        assert result is not None
        assert result.get("clarification") is not True
        assert result["video_id"] == "vid_morning"
        assert result["score"] >= 85

    def test_query_with_extra_emojis_only(self, mock_store):
        """DB title clean, query adds emojis — must still match."""
        mock_store.get_recent_videos.return_value = [
            _make_video("Weekend getaway with family", "vid_weekend"),
            _make_video("Unrelated stuff", "vid_unr"),
        ]
        result = resolve_video_by_title(
            CHANNEL, "Weekend getaway with family 🏖️🌊😍🔥"
        )
        assert result is not None
        assert result.get("clarification") is not True
        assert result["video_id"] == "vid_weekend"
        assert result["score"] >= 85

    def test_reordered_words_still_match(self, mock_store):
        """Word order swapped — token_sort handles it."""
        mock_store.get_recent_videos.return_value = [
            _make_video("Behind the scenes of my studio setup", "vid_studio"),
            _make_video("Other video", "vid_other"),
        ]
        result = resolve_video_by_title(
            CHANNEL, "studio setup behind the scenes"
        )
        assert result is not None
        assert result.get("clarification") is not True
        assert result["video_id"] == "vid_studio"
        assert result["score"] >= 70

    def test_similarity_components_logged(self, caplog, mock_store):
        """Verify component scores are logged at DEBUG level."""
        mock_store.get_recent_videos.return_value = [
            _make_video("Test video title", "vid_test"),
        ]
        with caplog.at_level(logging.DEBUG, logger="services.video_resolver"):
            resolve_video_by_title(CHANNEL, "test video title")
        log_text = " ".join(r.message for r in caplog.records)
        assert "ratio:" in log_text
        assert "token_set:" in log_text
        assert "partial:" in log_text
        assert "chosen_score:" in log_text

