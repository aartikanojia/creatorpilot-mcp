"""
UnifiedEngineOrchestrator — Unit Tests.

Validates severity aggregation, primary constraint selection,
ranking, risk level, confidence, determinism, validation, no-narrative.
"""

import pytest
from analytics.unified_engine_orchestrator import UnifiedEngineOrchestrator


@pytest.fixture
def engine():
    return UnifiedEngineOrchestrator()


def _make_result(severity=0.0, confidence=0.85, **extra):
    """Helper: build a minimal engine result dict."""
    d = {"severity": severity, "confidence": confidence}
    d.update(extra)
    return d


def _make_ctr_result(severity=0.0, confidence=0.85):
    return {"ctr_severity": severity, "confidence": confidence}


def _make_conversion_result(severity=0.0, confidence=0.85):
    return {"conversion_severity": severity, "confidence": confidence}


# ── OUTPUT STRUCTURE ──

class TestOutputStructure:
    def test_returns_dict(self, engine):
        r = engine.orchestrate(
            _make_result(0.9), _make_ctr_result(0.3),
            _make_conversion_result(0.5), _make_result(0.2), _make_result(0.1),
        )
        assert isinstance(r, dict)

    def test_required_keys(self, engine):
        r = engine.orchestrate(
            _make_result(0.9), _make_ctr_result(0.3),
            _make_conversion_result(0.5), _make_result(0.2), _make_result(0.1),
        )
        assert set(r.keys()) == {
            "primary_constraint", "primary_severity", "risk_level",
            "ranked_constraints", "engine_severities", "confidence",
            "next_video_blueprint"
        }


# ── PRIMARY CONSTRAINT SELECTION ──

class TestPrimaryConstraint:
    def test_retention_highest(self, engine):
        r = engine.orchestrate(
            _make_result(0.95), _make_ctr_result(0.3),
            _make_conversion_result(0.5), _make_result(0.2), _make_result(0.1),
        )
        assert r["primary_constraint"] == "retention"
        assert r["primary_severity"] == 0.95

    def test_ctr_highest(self, engine):
        r = engine.orchestrate(
            _make_result(0.3), _make_ctr_result(0.9),
            _make_conversion_result(0.5), _make_result(0.2), _make_result(0.1),
        )
        assert r["primary_constraint"] == "ctr"
        assert r["primary_severity"] == 0.9

    def test_conversion_highest(self, engine):
        r = engine.orchestrate(
            _make_result(0.3), _make_ctr_result(0.3),
            _make_conversion_result(0.95), _make_result(0.2), _make_result(0.1),
        )
        assert r["primary_constraint"] == "conversion"
        assert r["primary_severity"] == 0.95

    def test_shorts_highest(self, engine):
        r = engine.orchestrate(
            _make_result(0.3), _make_ctr_result(0.3),
            _make_conversion_result(0.2), _make_result(0.9), _make_result(0.1),
        )
        assert r["primary_constraint"] == "shorts"
        assert r["primary_severity"] == 0.9

    def test_growth_highest(self, engine):
        r = engine.orchestrate(
            _make_result(0.1), _make_ctr_result(0.1),
            _make_conversion_result(0.1), _make_result(0.1), _make_result(0.95),
        )
        assert r["primary_constraint"] == "growth"
        assert r["primary_severity"] == 0.95


# ── RISK LEVEL ──

class TestRiskLevel:
    def test_critical(self, engine):
        r = engine.orchestrate(
            _make_result(0.95), _make_ctr_result(0.3),
            _make_conversion_result(0.2), _make_result(0.1), _make_result(0.1),
        )
        assert r["risk_level"] == "critical"

    def test_high(self, engine):
        r = engine.orchestrate(
            _make_result(0.7), _make_ctr_result(0.3),
            _make_conversion_result(0.2), _make_result(0.1), _make_result(0.1),
        )
        assert r["risk_level"] == "high"

    def test_moderate(self, engine):
        r = engine.orchestrate(
            _make_result(0.6), _make_ctr_result(0.3),
            _make_conversion_result(0.2), _make_result(0.1), _make_result(0.1),
        )
        assert r["risk_level"] == "moderate"

    def test_low(self, engine):
        r = engine.orchestrate(
            _make_result(0.3), _make_ctr_result(0.3),
            _make_conversion_result(0.2), _make_result(0.1), _make_result(0.1),
        )
        assert r["risk_level"] == "low"


# ── RANKED CONSTRAINTS ──

class TestRankedConstraints:
    def test_descending_order(self, engine):
        r = engine.orchestrate(
            _make_result(0.9), _make_ctr_result(0.5),
            _make_conversion_result(0.7), _make_result(0.3), _make_result(0.1),
        )
        ranked = r["ranked_constraints"]
        severities = [s for _, s in ranked]
        assert severities == sorted(severities, reverse=True)

    def test_all_five_present(self, engine):
        r = engine.orchestrate(
            _make_result(0.9), _make_ctr_result(0.5),
            _make_conversion_result(0.7), _make_result(0.3), _make_result(0.1),
        )
        assert len(r["ranked_constraints"]) == 5

    def test_first_is_primary(self, engine):
        r = engine.orchestrate(
            _make_result(0.9), _make_ctr_result(0.5),
            _make_conversion_result(0.7), _make_result(0.3), _make_result(0.1),
        )
        assert r["ranked_constraints"][0][0] == r["primary_constraint"]


# ── ENGINE SEVERITIES ──

class TestEngineSeverities:
    def test_all_engines_present(self, engine):
        r = engine.orchestrate(
            _make_result(0.9), _make_ctr_result(0.5),
            _make_conversion_result(0.7), _make_result(0.3), _make_result(0.1),
        )
        assert set(r["engine_severities"].keys()) == {
            "retention", "ctr", "conversion", "shorts", "growth"
        }

    def test_values_match_input(self, engine):
        r = engine.orchestrate(
            _make_result(0.9), _make_ctr_result(0.5),
            _make_conversion_result(0.7), _make_result(0.3), _make_result(0.1),
        )
        assert r["engine_severities"]["retention"] == 0.9
        assert r["engine_severities"]["ctr"] == 0.5
        assert r["engine_severities"]["conversion"] == 0.7
        assert r["engine_severities"]["shorts"] == 0.3
        assert r["engine_severities"]["growth"] == 0.1


# ── CONFIDENCE ──

class TestConfidence:
    def test_average(self, engine):
        """All 0.85 → avg = 0.85."""
        r = engine.orchestrate(
            _make_result(0.9, 0.85), _make_ctr_result(0.3, 0.85),
            _make_conversion_result(0.5, 0.85), _make_result(0.2, 0.85),
            _make_result(0.1, 0.85),
        )
        assert r["confidence"] == 0.85

    def test_mixed(self, engine):
        """Mixed confidences → average."""
        r = engine.orchestrate(
            _make_result(0.9, 0.5), _make_ctr_result(0.3, 0.7),
            _make_conversion_result(0.5, 0.85), _make_result(0.2, 0.75),
            _make_result(0.1, 0.6),
        )
        expected = round((0.5 + 0.7 + 0.85 + 0.75 + 0.6) / 5, 2)
        assert r["confidence"] == expected


# ── CONSISTENCY ──

class TestConsistency:
    def test_same_input_same_output(self, engine):
        """All queries with same input → same primary constraint."""
        inputs = (
            _make_result(0.9), _make_ctr_result(0.3),
            _make_conversion_result(0.5), _make_result(0.2), _make_result(0.1),
        )
        r1 = engine.orchestrate(*inputs)
        r2 = engine.orchestrate(*inputs)
        assert r1["primary_constraint"] == r2["primary_constraint"]
        assert r1["primary_severity"] == r2["primary_severity"]
        assert r1["risk_level"] == r2["risk_level"]

    def test_no_query_drift(self, engine):
        """Ten runs must produce identical results — no drift."""
        inputs = (
            _make_result(0.9), _make_ctr_result(0.5),
            _make_conversion_result(0.7), _make_result(0.3), _make_result(0.1),
        )
        results = [engine.orchestrate(*inputs) for _ in range(10)]
        for r in results:
            assert r["primary_constraint"] == results[0]["primary_constraint"]
            assert r["primary_severity"] == results[0]["primary_severity"]


# ── DETERMINISM ──

class TestDeterminism:
    def test_ten_runs_identical(self, engine):
        inputs = (
            _make_result(0.9), _make_ctr_result(0.5),
            _make_conversion_result(0.7), _make_result(0.3), _make_result(0.1),
        )
        results = [engine.orchestrate(*inputs) for _ in range(10)]
        ref = results[0]
        for r in results[1:]:
            assert r["primary_constraint"] == ref["primary_constraint"]
            assert r["primary_severity"] == ref["primary_severity"]
            assert r["risk_level"] == ref["risk_level"]
            assert r["confidence"] == ref["confidence"]


# ── VALIDATION ──

class TestValidation:
    def test_non_dict_raises(self, engine):
        with pytest.raises(ValueError, match="must be a dict"):
            engine.orchestrate(
                "not_a_dict", _make_ctr_result(0.3),
                _make_conversion_result(0.5), _make_result(0.2), _make_result(0.1),
            )

    def test_none_raises(self, engine):
        with pytest.raises(ValueError, match="must be a dict"):
            engine.orchestrate(
                None, _make_ctr_result(0.3),
                _make_conversion_result(0.5), _make_result(0.2), _make_result(0.1),
            )


# ── NO NARRATIVE ──

class TestNoNarrative:
    def test_no_advice_in_core_fields(self, engine):
        r = engine.orchestrate(
            _make_result(0.9), _make_ctr_result(0.5),
            _make_conversion_result(0.7), _make_result(0.3), _make_result(0.1),
        )
        # Check core fields only (blueprint legitimately contains strategy words)
        core = {k: v for k, v in r.items() if k != "next_video_blueprint"}
        output = str(core)
        for phrase in ["you should", "consider", "recommend"]:
            assert phrase not in output.lower()

    def test_no_strategy_in_core_fields(self, engine):
        r = engine.orchestrate(
            _make_result(0.9), _make_ctr_result(0.5),
            _make_conversion_result(0.7), _make_result(0.3), _make_result(0.1),
        )
        core = {k: v for k, v in r.items() if k != "next_video_blueprint"}
        output = str(core)
        assert "strategy" not in output.lower()


# ── FULL INTEGRATION (all engines) ──

class TestFullIntegration:
    def test_end_to_end(self, engine):
        """Simulate real engine outputs and verify orchestration."""
        retention = {"severity": 0.9, "confidence": 0.85}
        ctr = {"ctr_severity": 0.6, "confidence": 0.7}
        conversion = {"conversion_severity": 0.3, "confidence": 0.85}
        shorts = {"severity": 0.4, "confidence": 0.75}
        growth = {"severity": 0.1, "confidence": 0.85}

        r = engine.orchestrate(retention, ctr, conversion, shorts, growth)

        assert r["primary_constraint"] == "retention"
        assert r["primary_severity"] == 0.9
        assert r["risk_level"] == "critical"
        assert r["ranked_constraints"][0] == ("retention", 0.9)
        assert r["ranked_constraints"][1] == ("ctr", 0.6)
        assert r["confidence"] == 0.8
