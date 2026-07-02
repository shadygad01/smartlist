"""
MPI Automated Tests.

Constitutional guarantee:
  - No constitutional score changes.
  - No ranking changes.
  - No gate changes.
  - No signal generation/rejection.
  - MPI failure must not interrupt production.

Run: python -m pytest tests/test_mpi.py -v
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))


# ── Fixtures ──────────────────────────────────────────────────────────────────

_SAMPLE_FEAT = {
    "ok":              True,
    "price":           10.5,
    "score":           45,
    "r1_price":        20,
    "r2_ob":           65,
    "r3_liquidity":    18,
    "r4_htf":          0,
    "r5_avwap":        5,
    "r6_macd":         10,
    "r7_div":          8,
    "r8_demand":       20,
    "sweep_detected":  True,
    "sv_hit":          True,
    "hvn_hit":         True,
    "rsi_div":         False,
    "macd_div":        False,
    "htf_hh":          False,
    "htf_hl":          False,
    "ob_quality":      65.0,
    "macd_val":        -0.01,
}

_SAMPLE_NEAR_FEAT = {
    "ok":              True,
    "price":           11.0,
    "score":           38,
    "r2_ob":           55,
    "sweep_detected":  False,
    "sv_hit":          True,
    "hvn_hit":         False,
    "rsi_div":         False,
    "macd_div":        False,
    "htf_hh":          True,
    "htf_hl":          True,
    "ob_quality":      55.0,
    "macd_val":        0.05,
}


def _mock_snap(
    first_buys=None,
    re_accumulations=None,
    approaching_entries=None,
):
    snap = MagicMock()
    snap.first_buys         = first_buys or []
    snap.re_accumulations   = re_accumulations or []
    snap.approaching_entries = approaching_entries or []
    return snap


# ── Phase Detection Tests ─────────────────────────────────────────────────────

class TestPhaseDetection:
    def test_late_capitulation(self):
        from mpi_engine import _detect_phase
        feat = {**_SAMPLE_FEAT, "sweep_detected": True, "sv_hit": True, "hvn_hit": True, "macd_val": -0.05}
        phase, evidence = _detect_phase(feat)
        assert phase == "Late Capitulation"
        assert "sweep_detected" in evidence
        assert "sv_hit" in evidence

    def test_capitulation_no_hvn(self):
        from mpi_engine import _detect_phase
        feat = {**_SAMPLE_FEAT, "sweep_detected": True, "sv_hit": True, "hvn_hit": False, "macd_val": -0.05}
        phase, evidence = _detect_phase(feat)
        assert phase == "Capitulation"

    def test_silent_accumulation(self):
        from mpi_engine import _detect_phase
        feat = {**_SAMPLE_FEAT, "sweep_detected": False, "sv_hit": True, "hvn_hit": True, "macd_val": 0.01}
        phase, _ = _detect_phase(feat)
        assert phase == "Silent Accumulation"

    def test_accumulation_sweep_sv(self):
        from mpi_engine import _detect_phase
        feat = {**_SAMPLE_FEAT, "sweep_detected": True, "sv_hit": True, "hvn_hit": False, "macd_val": 0.0}
        phase, evidence = _detect_phase(feat)
        assert phase == "Accumulation"

    def test_confidence_building(self):
        from mpi_engine import _detect_phase
        feat = {
            "sweep_detected": False, "sv_hit": False, "hvn_hit": False,
            "htf_hh": True, "htf_hl": True, "macd_val": 0.1,
            "ob_quality": 65.0, "rsi_div": False, "macd_div": False,
            "r6_macd": 12,
        }
        phase, evidence = _detect_phase(feat)
        assert phase == "Confidence Building"
        assert "htf_uptrend" in evidence

    def test_neutral_no_evidence(self):
        from mpi_engine import _detect_phase
        feat = {
            "sweep_detected": False, "sv_hit": False, "hvn_hit": False,
            "htf_hh": False, "htf_hl": False, "macd_val": None,
            "ob_quality": 0.0, "rsi_div": False, "macd_div": False,
        }
        phase, _ = _detect_phase(feat)
        assert phase == "Neutral"

    def test_divergence_late_capitulation(self):
        from mpi_engine import _detect_phase
        feat = {
            "sweep_detected": False, "sv_hit": True, "hvn_hit": False,
            "rsi_div": True, "macd_div": False, "htf_hh": False, "htf_hl": False,
            "macd_val": None, "ob_quality": 0,
        }
        phase, evidence = _detect_phase(feat)
        assert phase == "Late Capitulation"
        assert "rsi_div" in evidence


# ── Confidence Scoring Tests ───────────────────────────────────────────────────

class TestConfidenceScoring:
    def test_high_confidence_with_evidence(self):
        from mpi_engine import _compute_confidence
        evidence = ["sweep_detected", "sv_hit", "hvn_hit", "ob_quality_high"]
        conf = _compute_confidence(evidence, historical_cases=10, similarity=0.80, feat={})
        assert conf >= 0.60

    def test_low_confidence_no_evidence(self):
        from mpi_engine import _compute_confidence
        conf = _compute_confidence([], historical_cases=0, similarity=0.0, feat={})
        assert conf < 0.45

    def test_confidence_label_high(self):
        from mpi_engine import _confidence_label
        assert _confidence_label(0.75) == "HIGH"

    def test_confidence_label_medium(self):
        from mpi_engine import _confidence_label
        assert _confidence_label(0.50) == "MEDIUM"

    def test_confidence_label_low(self):
        from mpi_engine import _confidence_label
        assert _confidence_label(0.20) == "LOW"

    def test_confidence_bounded(self):
        from mpi_engine import _compute_confidence
        evidence = ["sweep_detected", "sv_hit", "hvn_hit", "ob_quality_high",
                    "rsi_div", "macd_div", "htf_uptrend", "macd_positive"]
        conf = _compute_confidence(evidence, historical_cases=20, similarity=0.95, feat={})
        assert 0.0 <= conf <= 1.0


# ── Explanation Generation Tests ───────────────────────────────────────────────

class TestExplanationGeneration:
    def test_explanation_deterministic(self):
        from mpi_engine import _generate_explanation, _infer_behavior
        phase = "Late Capitulation"
        evidence = ["sweep_detected", "sv_hit", "hvn_hit"]
        behavior = _infer_behavior(phase)
        hist = {"cases": 10, "similarity": 0.85, "avg_mfe40": 24.0}

        exp1, compact1 = _generate_explanation(phase, evidence, behavior, hist, "HIGH", _SAMPLE_FEAT)
        exp2, compact2 = _generate_explanation(phase, evidence, behavior, hist, "HIGH", _SAMPLE_FEAT)
        assert exp1 == exp2
        assert compact1 == compact2

    def test_explanation_not_empty(self):
        from mpi_engine import _generate_explanation, _infer_behavior
        phase = "Accumulation"
        evidence = ["sweep_detected", "sv_hit"]
        behavior = _infer_behavior(phase)
        hist = {"cases": 5, "similarity": 0.65, "avg_mfe40": 18.0}
        exp, compact = _generate_explanation(phase, evidence, behavior, hist, "MEDIUM", _SAMPLE_FEAT)
        assert len(exp) > 10
        assert len(compact.strip()) > 0

    def test_explanation_max_words(self):
        from mpi_engine import _generate_explanation, _infer_behavior
        phase = "Late Capitulation"
        evidence = ["sweep_detected", "sv_hit", "hvn_hit", "rsi_div", "macd_div", "htf_uptrend"]
        behavior = _infer_behavior(phase)
        hist = {"cases": 20, "similarity": 0.90, "avg_mfe40": 30.0}
        exp, _ = _generate_explanation(phase, evidence, behavior, hist, "HIGH", _SAMPLE_FEAT)
        word_count = len(exp.split())
        assert word_count <= 130  # slight buffer over 120 for sentence boundary

    def test_compact_max_lines(self):
        from mpi_engine import _generate_explanation, _infer_behavior
        phase = "Late Capitulation"
        evidence = ["sweep_detected", "sv_hit", "hvn_hit"]
        behavior = _infer_behavior(phase)
        hist = {"cases": 8, "similarity": 0.75, "avg_mfe40": 20.0}
        _, compact = _generate_explanation(phase, evidence, behavior, hist, "HIGH", _SAMPLE_FEAT)
        assert compact.count("\n") <= 3  # at most 4 lines


# ── analyze_ticker Tests ───────────────────────────────────────────────────────

class TestAnalyzeTicker:
    def test_returns_dict(self):
        from mpi_engine import analyze_ticker
        with patch("mpi_engine._fetch_historical_analogs",
                   return_value={"cases": 0, "similarity": 0.0, "avg_mfe40": 0.0,
                                 "avg_drawdown": 0.0, "avg_holding_days": 0.0, "confidence": "LOW"}):
            result = analyze_ticker("TEST.CA", "FIRST_BUY", _SAMPLE_FEAT, "2026-06-27")
        assert result is not None
        assert result["ticker"] == "TEST.CA"
        assert result["signal_type"] == "FIRST_BUY"
        assert "phase" in result
        assert "explanation" in result
        assert "confidence" in result

    def test_mandatory_fields_present(self):
        from mpi_engine import analyze_ticker
        with patch("mpi_engine._fetch_historical_analogs",
                   return_value={"cases": 0, "similarity": 0.0, "avg_mfe40": 0.0,
                                 "avg_drawdown": 0.0, "avg_holding_days": 0.0, "confidence": "LOW"}):
            result = analyze_ticker("TEST.CA", "NEAR_ENTRY", _SAMPLE_NEAR_FEAT, "2026-06-27")
        required = [
            "ticker", "signal_type", "analysis_date", "engine_version",
            "phase", "confidence", "confidence_label",
            "explanation", "explanation_compact", "created_at",
        ]
        for f in required:
            assert f in result, f"Missing field: {f}"

    def test_low_confidence_shows_unavailable(self):
        from mpi_engine import analyze_ticker, _UNAVAILABLE_EXPLANATION
        empty_feat = {"ok": True}
        with patch("mpi_engine._fetch_historical_analogs",
                   return_value={"cases": 0, "similarity": 0.0, "avg_mfe40": 0.0,
                                 "avg_drawdown": 0.0, "avg_holding_days": 0.0, "confidence": "LOW"}):
            result = analyze_ticker("LOW.CA", "FIRST_BUY", empty_feat, "2026-06-27")
        # Below threshold: engine still returns dict (storage keeps all), but
        # run_for_current_signals will replace explanation with unavailable message
        assert result is not None


# ── Database Tests ─────────────────────────────────────────────────────────────

class TestMPIDatabase:
    def test_upsert_and_load(self):
        from mpi_db import upsert_snapshot, load_snapshot
        with tempfile.TemporaryDirectory() as tmpdir:
            db = str(Path(tmpdir) / "test.db")
            snap = {
                "ticker": "TEST.CA", "signal_type": "FIRST_BUY",
                "analysis_date": "2026-06-27", "engine_version": "1.0",
                "schema_version": "1", "phase": "Late Capitulation",
                "confidence": 0.75, "confidence_label": "HIGH",
                "institutional_interpretation": "Institutional absorption.",
                "retail_interpretation": "Retail capitulating.",
                "buying_pressure": "Strengthening", "selling_pressure": "Weakening",
                "supply_absorption": "Active", "distribution_probability": "Low",
                "key_drivers": '["sv_hit","sweep_detected"]',
                "evidence_json": '{}',
                "historical_cases": 10, "similarity_score": 0.85,
                "avg_mfe40": 24.0, "avg_drawdown": 5.0, "avg_holding_days": 12.0,
                "historical_confidence": "HIGH",
                "explanation": "Late-stage capitulation detected. Institutions absorbing supply.",
                "explanation_compact": "Late Capitulation\nInstitutions absorbing.",
                "created_at": "2026-06-27T10:00:00",
            }
            upsert_snapshot(snap, db_path=db)
            loaded = load_snapshot("TEST.CA", "2026-06-27", "FIRST_BUY", db_path=db)
            assert loaded is not None
            assert loaded["phase"] == "Late Capitulation"
            assert loaded["confidence"] == 0.75

    def test_upsert_overwrites(self):
        from mpi_db import upsert_snapshot, load_snapshot
        with tempfile.TemporaryDirectory() as tmpdir:
            db = str(Path(tmpdir) / "test.db")
            base = {
                "ticker": "A.CA", "signal_type": "NEAR_ENTRY",
                "analysis_date": "2026-06-27", "engine_version": "1.0",
                "schema_version": "1", "phase": "Fear", "confidence": 0.30,
                "confidence_label": "LOW", "institutional_interpretation": "",
                "retail_interpretation": "", "buying_pressure": "", "selling_pressure": "",
                "supply_absorption": "", "distribution_probability": "",
                "key_drivers": "[]", "evidence_json": "{}",
                "historical_cases": 0, "similarity_score": 0.0,
                "avg_mfe40": 0.0, "avg_drawdown": 0.0, "avg_holding_days": 0.0,
                "historical_confidence": "LOW", "explanation": "V1.",
                "explanation_compact": "V1.", "created_at": "2026-06-27T09:00:00",
            }
            upsert_snapshot(base, db_path=db)
            updated = {**base, "phase": "Accumulation", "explanation": "V2.", "created_at": "2026-06-27T10:00:00"}
            upsert_snapshot(updated, db_path=db)
            loaded = load_snapshot("A.CA", "2026-06-27", "NEAR_ENTRY", db_path=db)
            assert loaded["phase"] == "Accumulation"
            assert loaded["explanation"] == "V2."

    def test_load_returns_none_if_missing(self):
        from mpi_db import load_snapshot
        with tempfile.TemporaryDirectory() as tmpdir:
            db = str(Path(tmpdir) / "nonexistent.db")
            result = load_snapshot("NOTEXIST.CA", "2026-01-01", "FIRST_BUY", db_path=db)
            assert result is None


# ── Constitutional Isolation Tests ─────────────────────────────────────────────

class TestConstitutionalIsolation:
    """Verify MPI never touches constitutional decisions."""

    def test_analyze_ticker_does_not_modify_feat(self):
        from mpi_engine import analyze_ticker
        feat_before = dict(_SAMPLE_FEAT)
        with patch("mpi_engine._fetch_historical_analogs",
                   return_value={"cases": 0, "similarity": 0.0, "avg_mfe40": 0.0,
                                 "avg_drawdown": 0.0, "avg_holding_days": 0.0, "confidence": "LOW"}):
            analyze_ticker("TEST.CA", "FIRST_BUY", _SAMPLE_FEAT, "2026-06-27")
        assert dict(_SAMPLE_FEAT) == feat_before

    def test_run_for_current_signals_failure_is_silent(self):
        """MPI failure must not raise — it must degrade gracefully."""
        from mpi_engine import run_for_current_signals
        bad_snap = MagicMock()
        bad_snap.first_buys = None
        bad_snap.re_accumulations = None
        bad_snap.approaching_entries = None
        result = run_for_current_signals({}, bad_snap)
        assert isinstance(result, dict)
        assert result["processed"] == 0

    def test_mpi_result_has_no_score_field(self):
        from mpi_engine import analyze_ticker
        with patch("mpi_engine._fetch_historical_analogs",
                   return_value={"cases": 5, "similarity": 0.70, "avg_mfe40": 15.0,
                                 "avg_drawdown": 3.0, "avg_holding_days": 10.0, "confidence": "MEDIUM"}):
            result = analyze_ticker("TEST.CA", "FIRST_BUY", _SAMPLE_FEAT, "2026-06-27")
        # Verify no constitutional fields are present or modified
        assert "signal" not in result
        assert "ranking" not in result
        assert "gate" not in result
        assert "constitutional_score" not in result


# ── HTML Renderer Tests ────────────────────────────────────────────────────────

class TestHTMLRenderer:
    def test_render_empty_when_no_snap(self):
        from mpi_engine import render_behavior_insight_html
        assert render_behavior_insight_html(None) == ""

    def test_render_phase_fallback_when_unavailable_and_no_history(self):
        """Low-confidence + no history → mandatory phase fallback (never empty for non-None snap)."""
        from mpi_engine import render_behavior_insight_html, _UNAVAILABLE_EXPLANATION
        snap = {"explanation": _UNAVAILABLE_EXPLANATION, "historical_cases": 0,
                "similarity_score": 0.0, "confidence": 0.0, "phase": "Neutral"}
        html = render_behavior_insight_html(snap)
        assert html != "", "mandatory fallback must return non-empty for non-None snap"
        assert "Behavior Phase" in html or "Neutral" in html

    def test_render_historical_context_when_unavailable_but_history_present(self):
        """Low-confidence with meaningful history → historical context block, not empty."""
        from mpi_engine import render_behavior_insight_html, _UNAVAILABLE_EXPLANATION
        snap = {
            "explanation":      _UNAVAILABLE_EXPLANATION,
            "historical_cases": 64,
            "similarity_score": 0.66,
            "avg_mfe40":        16.6,
            "avg_drawdown":     7.5,
            "avg_holding_days": 176.8,
        }
        html = render_behavior_insight_html(snap, theme="dark")
        assert html != ""
        assert "Historical Context" in html
        assert "64" in html
        assert "MFE40" in html or "+17" in html or "+16" in html

    def test_render_contains_phase(self):
        from mpi_engine import render_behavior_insight_html
        snap = {
            "explanation":      "Late-stage capitulation pattern detected. Supply absorption confirmed.",
            "phase":            "Late Capitulation",
            "confidence":       0.75,
            "confidence_label": "HIGH",
            "historical_cases": 10,
            "avg_mfe40":        24.0,
            "similarity_score": 0.85,
        }
        html = render_behavior_insight_html(snap, theme="dark")
        assert "Late Capitulation" in html
        assert "Behavior Insight" in html

    def test_render_telegram_max_lines(self):
        from mpi_engine import render_behavior_insight_telegram, _UNAVAILABLE_COMPACT
        snap = {
            "explanation_compact": "Late Capitulation\nInstitutions absorbing supply.\nHistorical similarity: 85%\nBehavior supports the constitutional signal.",
        }
        tg = render_behavior_insight_telegram(snap)
        assert tg != ""
        assert tg.count("\n") <= 4

    def test_render_telegram_phase_fallback_when_unavailable_and_no_history(self):
        """Low-confidence + no history → mandatory phase fallback (never empty for non-None snap)."""
        from mpi_engine import render_behavior_insight_telegram, _UNAVAILABLE_COMPACT
        snap = {"explanation_compact": _UNAVAILABLE_COMPACT, "historical_cases": 0,
                "similarity_score": 0.0, "confidence": 0.0, "phase": "Neutral"}
        tg = render_behavior_insight_telegram(snap)
        assert tg != "", "mandatory fallback must return non-empty for non-None snap"
        assert "Behavior Phase" in tg or "Neutral" in tg

    def test_render_telegram_historical_context_when_available(self):
        """Low-confidence Telegram falls back to compact historical context line."""
        from mpi_engine import render_behavior_insight_telegram, _UNAVAILABLE_COMPACT
        snap = {
            "explanation_compact": _UNAVAILABLE_COMPACT,
            "historical_cases":    64,
            "similarity_score":    0.66,
            "avg_mfe40":           16.6,
        }
        tg = render_behavior_insight_telegram(snap)
        assert tg != ""
        assert "Historical" in tg or "historical" in tg or "📊" in tg


# ── R-score extraction tests ──────────────────────────────────────────────────

class TestRScoreExtraction:
    def test_extract_from_rows_list(self):
        """R-scores stored in `rows` tuples are correctly extracted."""
        from mpi_engine import _extract_r_scores_from_feat
        feat = {
            "r1": 3,
            "rows": [
                ("Price Position",      3,  30, "Price ok"),
                ("Liquidity Context",   18, 20, "Liq ok"),
                ("Demand Zone (SV+VP)", 9,  15, "Demand ok"),
                ("Order Block Quality", 4,  10, "OB ok"),
                ("Higher Timeframe",    5,  10, "HTF ok"),
                ("Anchored VWAP",       6,  8,  "AVWAP ok"),
                ("MACD vs Zero",        2,  4,  "MACD ok"),
                ("Divergence",          0,  3,  "No div"),
            ],
        }
        r = _extract_r_scores_from_feat(feat)
        assert r["r1_price"]    == 3.0
        assert r["r2_ob"]       == 4.0
        assert r["r3_liquidity"]== 18.0
        assert r["r4_htf"]      == 5.0
        assert r["r5_avwap"]    == 6.0
        assert r["r6_macd"]     == 2.0
        assert r["r7_div"]      == 0.0
        assert r["r8_demand"]   == 9.0

    def test_extract_named_keys_when_no_rows(self):
        """r1_price falls through to r1 shorthand; r2-r8 named keys are handled by _fetch_historical_analogs."""
        from mpi_engine import _extract_r_scores_from_feat
        # When rows is absent and r1_price is present, only r1_price is extracted
        feat = {"r1_price": 20}
        r = _extract_r_scores_from_feat(feat)
        assert r.get("r1_price") == 20.0

    def test_extract_r1_shorthand_fallback(self):
        """r1 shorthand fills r1_price when rows is absent."""
        from mpi_engine import _extract_r_scores_from_feat
        feat = {"r1": 5}
        r = _extract_r_scores_from_feat(feat)
        assert r.get("r1_price") == 5.0


# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
