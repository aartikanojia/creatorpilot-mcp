"""
Response quality validators — Category 10.

Structural checks on LLM output format. Validates that responses
follow premium formatting rules with NO data leakage, NO generic
advice, and correct section structure.

Scoring System:
  Each test evaluates a response on a 1-5 scale across dimensions:
  - Intent accuracy
  - Tool correctness
  - Strategic depth
  - Guardrail compliance
  - UX polish
"""

import re
import pytest
from dataclasses import dataclass, field
from typing import Optional


# =============================================================================
# QUALITY SCORE DATA MODEL
# =============================================================================

@dataclass
class QualityScore:
    """Score for a single response evaluation."""
    intent_accuracy: int = 0      # 1-5
    tool_correctness: int = 0     # 1-5
    strategic_depth: int = 0      # 1-5
    guardrail_compliance: int = 0 # 1-5
    ux_polish: int = 0            # 1-5
    violations: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return (
            self.intent_accuracy
            + self.tool_correctness
            + self.strategic_depth
            + self.guardrail_compliance
            + self.ux_polish
        )

    @property
    def max_score(self) -> int:
        return 25

    @property
    def percentage(self) -> float:
        return round((self.total / self.max_score) * 100, 1)

    def __repr__(self):
        return (
            f"QualityScore({self.total}/{self.max_score} = {self.percentage}% | "
            f"violations={len(self.violations)})"
        )


# =============================================================================
# QUALITY VALIDATORS
# =============================================================================

class ResponseQualityValidator:
    """
    Validates LLM response quality against structural rules.
    Each check returns (passed: bool, violation_detail: str).
    """

    # YouTube video ID regex: 11 chars of [A-Za-z0-9_-]
    VIDEO_ID_PATTERN = re.compile(r"\b[A-Za-z0-9_-]{11}\b")

    # Known internal tool names that must never appear in output
    INTERNAL_TOOL_NAMES = [
        "fetch_analytics",
        "compute_metrics",
        "generate_chart",
        "analyze_data",
        "generate_insight",
        "get_recommendations",
        "generate_report",
        "summarize_data",
        "recall_context",
        "search_history",
        "execute_action",
        "schedule_task",
        "search_data",
        "fetch_last_video_analytics",
    ]

    # Top-video premium template required sections
    TOP_VIDEO_SECTIONS = [
        "Why This Video Took Off",
        "Performance Snapshot",
        "Why It Worked",
        "Replication Strategy",
        "Next Move",
    ]

    @classmethod
    def check_no_video_ids(cls, response: str) -> tuple[bool, str]:
        """Check that no YouTube video IDs are exposed."""
        # Find potential video IDs (11-char alphanumeric)
        matches = cls.VIDEO_ID_PATTERN.findall(response)

        # Filter false positives: common English words that are 11 chars
        false_positives = {
            "performance", "subscribers", "impressions", "discoverabi",
            "recommenda", "information", "significant", "comprehen",
            "three-video"
        }
        real_ids = [m for m in matches if m.lower() not in false_positives]

        # Heuristic: video IDs contain mixed case + digits/hyphens
        suspicious = []
        for candidate in real_ids:
            has_upper = any(c.isupper() for c in candidate)
            has_lower = any(c.islower() for c in candidate)
            has_digit = any(c.isdigit() for c in candidate)
            has_special = any(c in "-_" for c in candidate)

            if (has_upper and has_lower and has_digit) or has_special:
                suspicious.append(candidate)

        if suspicious:
            return False, f"Possible video IDs found: {suspicious}"
        return True, ""

    @classmethod
    def check_no_markdown_tables(cls, response: str) -> tuple[bool, str]:
        """Check that response does not contain markdown tables."""
        if "|---" in response or "| ---" in response:
            return False, "Markdown table detected (|--- pattern)"
        return True, ""

    @classmethod
    def check_no_raw_json(cls, response: str) -> tuple[bool, str]:
        """Check that response does not contain raw JSON blocks."""
        # Check for JSON code blocks
        if "```json" in response:
            return False, "Raw JSON code block detected"

        # Check for JSON-like structures (key-value pairs with quotes)
        json_pattern = re.compile(r'\{["\'][\w]+["\']:\s*[\d"\']')
        if json_pattern.search(response):
            return False, "JSON-like structure detected in response"

        return True, ""

    @classmethod
    def check_no_internal_tool_names(cls, response: str) -> tuple[bool, str]:
        """Check that no internal tool names are exposed."""
        response_lower = response.lower()
        found = []
        for tool in cls.INTERNAL_TOOL_NAMES:
            if tool in response_lower:
                found.append(tool)

        if found:
            return False, f"Internal tool names leaked: {found}"
        return True, ""

    @classmethod
    def check_no_prompt_echo(
        cls, response: str, user_message: str
    ) -> tuple[bool, str]:
        """Check that the response doesn't echo back the user's prompt."""
        if len(user_message) > 20 and user_message in response:
            return False, "User prompt echoed in response"
        return True, ""

    @classmethod
    def check_no_emojis(cls, response: str) -> tuple[bool, str]:
        """Check that response does not contain emojis."""
        emoji_pattern = re.compile(
            "[\U0001F600-\U0001F64F"  # emoticons
            "\U0001F300-\U0001F5FF"   # symbols & pictographs
            "\U0001F680-\U0001F6FF"   # transport & map
            "\U0001F1E0-\U0001F1FF"   # flags
            "\U00002702-\U000027B0"
            "\U000024C2-\U0001F251"
            "\U0001F900-\U0001F9FF"   # supplemental
            "\U0001FA00-\U0001FA6F"   # chess/extended-A
            "\U0001FA70-\U0001FAFF"   # extended-b
            "]+",
            flags=re.UNICODE,
        )
        emojis = emoji_pattern.findall(response)
        if emojis:
            return False, f"Emojis found: {emojis[:5]}"
        return True, ""

    @classmethod
    def check_no_metric_repetition(cls, response: str) -> tuple[bool, str]:
        """Check that the same metric value isn't repeated 3+ times."""
        # Find all numbers in the response
        numbers = re.findall(r"\b\d{3,}\b", response)
        from collections import Counter
        counts = Counter(numbers)

        repeated = {n: c for n, c in counts.items() if c >= 3}
        if repeated:
            return False, f"Metric values repeated 3+ times: {repeated}"
        return True, ""

    @classmethod
    def check_no_generic_advice(cls, response: str) -> tuple[bool, str]:
        """
        Check for generic blog-style advice patterns.
        These are vague suggestions that don't reference actual data.
        """
        generic_patterns = [
            r"you might want to consider",
            r"it could be that",
            r"perhaps you should",
            r"I think you should",
            r"you should try to make better content",
            r"try posting more often",
            r"be consistent with your uploads",
        ]

        found = []
        response_lower = response.lower()
        for pattern in generic_patterns:
            if re.search(pattern, response_lower):
                found.append(pattern)

        if found:
            return False, f"Generic advice patterns detected: {found}"
        return True, ""

    @classmethod
    def check_no_analytics_comment_markers(cls, response: str) -> tuple[bool, str]:
        """Check for internal HTML comment markers in output."""
        if "<!-- ANALYTICS_DATA -->" in response:
            return False, "Internal analytics comment marker found"
        if "<!-- " in response and " -->" in response:
            return False, "HTML comment markers found in response"
        return True, ""

    @classmethod
    def check_top_video_sections(cls, response: str) -> tuple[bool, str]:
        """Check that all 5 premium sections are present for top-video analysis."""
        missing = []
        for section in cls.TOP_VIDEO_SECTIONS:
            if section.lower() not in response.lower():
                missing.append(section)

        if missing:
            return False, f"Missing premium sections: {missing}"
        return True, ""

    @classmethod
    def check_response_structure(cls, response: str) -> tuple[bool, str]:
        """
        Validate Insight → Diagnosis → Action → Direction structure.
        At minimum, the response should have 2+ distinct sections.
        """
        # Count bold headers (** ... ** pattern)
        headers = re.findall(r"\*\*[^*]+\*\*", response)
        if len(headers) < 2:
            return False, f"Only {len(headers)} section headers found (need ≥2)"
        return True, ""


# =============================================================================
# CATEGORY 10: RESPONSE QUALITY TESTS
# =============================================================================

class TestResponseQualityGoodResponse:
    """Validate that a well-formed response passes all quality checks."""

    def test_no_video_ids(self, sample_good_response):
        passed, detail = ResponseQualityValidator.check_no_video_ids(
            sample_good_response
        )
        assert passed, detail

    def test_no_markdown_tables(self, sample_good_response):
        passed, detail = ResponseQualityValidator.check_no_markdown_tables(
            sample_good_response
        )
        assert passed, detail

    def test_no_raw_json(self, sample_good_response):
        passed, detail = ResponseQualityValidator.check_no_raw_json(
            sample_good_response
        )
        assert passed, detail

    def test_no_internal_tool_names(self, sample_good_response):
        passed, detail = ResponseQualityValidator.check_no_internal_tool_names(
            sample_good_response
        )
        assert passed, detail

    def test_no_prompt_echo(self, sample_good_response):
        user_msg = 'Analyze my top video "Mihir ki masti #play" from the last 7 days'
        passed, detail = ResponseQualityValidator.check_no_prompt_echo(
            sample_good_response, user_msg
        )
        assert passed, detail

    def test_no_emojis(self, sample_good_response):
        passed, detail = ResponseQualityValidator.check_no_emojis(
            sample_good_response
        )
        assert passed, detail

    def test_no_metric_repetition(self, sample_good_response):
        passed, detail = ResponseQualityValidator.check_no_metric_repetition(
            sample_good_response
        )
        assert passed, detail

    def test_no_generic_advice(self, sample_good_response):
        passed, detail = ResponseQualityValidator.check_no_generic_advice(
            sample_good_response
        )
        assert passed, detail

    def test_no_analytics_markers(self, sample_good_response):
        passed, detail = ResponseQualityValidator.check_no_analytics_comment_markers(
            sample_good_response
        )
        assert passed, detail

    def test_top_video_sections_present(self, sample_good_response):
        passed, detail = ResponseQualityValidator.check_top_video_sections(
            sample_good_response
        )
        assert passed, detail

    def test_response_structure(self, sample_good_response):
        passed, detail = ResponseQualityValidator.check_response_structure(
            sample_good_response
        )
        assert passed, detail


class TestResponseQualityBadResponse:
    """Validate that a poorly-formed response FAILS quality checks."""

    def test_detects_markdown_tables(self, sample_bad_response):
        passed, _ = ResponseQualityValidator.check_no_markdown_tables(
            sample_bad_response
        )
        assert passed is False

    def test_detects_raw_json(self, sample_bad_response):
        passed, _ = ResponseQualityValidator.check_no_raw_json(
            sample_bad_response
        )
        assert passed is False

    def test_detects_internal_tool_names(self, sample_bad_response):
        passed, _ = ResponseQualityValidator.check_no_internal_tool_names(
            sample_bad_response
        )
        assert passed is False

    def test_detects_emojis(self, sample_bad_response):
        passed, _ = ResponseQualityValidator.check_no_emojis(
            sample_bad_response
        )
        assert passed is False

    def test_detects_metric_repetition(self, sample_bad_response):
        passed, _ = ResponseQualityValidator.check_no_metric_repetition(
            sample_bad_response
        )
        assert passed is False

    def test_detects_generic_advice(self, sample_bad_response):
        passed, _ = ResponseQualityValidator.check_no_generic_advice(
            sample_bad_response
        )
        assert passed is False


# =============================================================================
# SCORING SYSTEM
# =============================================================================

class TestScoringSystem:
    """Tests for the scoring/grading system itself."""

    def test_perfect_score(self):
        """A perfect response should score 25/25."""
        score = QualityScore(
            intent_accuracy=5,
            tool_correctness=5,
            strategic_depth=5,
            guardrail_compliance=5,
            ux_polish=5,
        )
        assert score.total == 25
        assert score.percentage == 100.0

    def test_minimum_score(self):
        """A minimal response scores 5/25."""
        score = QualityScore(
            intent_accuracy=1,
            tool_correctness=1,
            strategic_depth=1,
            guardrail_compliance=1,
            ux_polish=1,
        )
        assert score.total == 5
        assert score.percentage == 20.0

    def test_score_with_violations(self):
        """Violations should be tracked separately from scores."""
        score = QualityScore(
            intent_accuracy=5,
            tool_correctness=5,
            strategic_depth=3,
            guardrail_compliance=2,
            ux_polish=4,
            violations=["video_id_leak", "table_found"],
        )
        assert score.total == 19
        assert len(score.violations) == 2

    def test_full_quality_assessment_good_response(self, sample_good_response):
        """Run all validators on a good response and produce a score."""
        validator = ResponseQualityValidator
        score = QualityScore()
        violations = []

        # Intent accuracy: assumed correct for this unit test
        score.intent_accuracy = 5

        # Tool correctness: assumed correct
        score.tool_correctness = 5

        # Strategic depth: check for sections and structure
        passed, detail = validator.check_top_video_sections(sample_good_response)
        if passed:
            score.strategic_depth = 5
        else:
            score.strategic_depth = 2
            violations.append(detail)

        # Guardrail compliance: run all guardrail checks
        guardrail_checks = [
            validator.check_no_video_ids(sample_good_response),
            validator.check_no_raw_json(sample_good_response),
            validator.check_no_internal_tool_names(sample_good_response),
            validator.check_no_emojis(sample_good_response),
            validator.check_no_analytics_comment_markers(sample_good_response),
        ]
        guardrail_failures = sum(1 for p, _ in guardrail_checks if not p)
        score.guardrail_compliance = max(1, 5 - guardrail_failures)

        # UX polish
        ux_checks = [
            validator.check_no_markdown_tables(sample_good_response),
            validator.check_no_generic_advice(sample_good_response),
            validator.check_no_metric_repetition(sample_good_response),
            validator.check_response_structure(sample_good_response),
        ]
        ux_failures = sum(1 for p, _ in ux_checks if not p)
        score.ux_polish = max(1, 5 - ux_failures)

        score.violations = violations

        # Good response should score at least 20/25
        assert score.total >= 20, f"Score too low: {score}"
        assert score.percentage >= 80.0

    def test_full_quality_assessment_bad_response(self, sample_bad_response):
        """Run all validators on a bad response — expect low score."""
        validator = ResponseQualityValidator
        score = QualityScore()
        violations = []

        score.intent_accuracy = 3
        score.tool_correctness = 3

        # Strategic depth
        passed, detail = validator.check_top_video_sections(sample_bad_response)
        if passed:
            score.strategic_depth = 5
        else:
            score.strategic_depth = 1
            violations.append(detail)

        # Guardrail compliance
        guardrail_checks = [
            validator.check_no_video_ids(sample_bad_response),
            validator.check_no_raw_json(sample_bad_response),
            validator.check_no_internal_tool_names(sample_bad_response),
            validator.check_no_emojis(sample_bad_response),
            validator.check_no_analytics_comment_markers(sample_bad_response),
        ]
        guardrail_failures = sum(1 for p, _ in guardrail_checks if not p)
        score.guardrail_compliance = max(1, 5 - guardrail_failures)

        # UX polish
        ux_checks = [
            validator.check_no_markdown_tables(sample_bad_response),
            validator.check_no_generic_advice(sample_bad_response),
            validator.check_no_metric_repetition(sample_bad_response),
            validator.check_response_structure(sample_bad_response),
        ]
        ux_failures = sum(1 for p, _ in ux_checks if not p)
        score.ux_polish = max(1, 5 - ux_failures)

        score.violations = violations

        # Bad response should score significantly lower
        assert score.total < 20, f"Bad response scored too high: {score}"
        assert len(violations) > 0 or guardrail_failures > 0
