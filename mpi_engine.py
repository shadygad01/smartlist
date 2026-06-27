"""
Market Psychology Intelligence (MPI) — Core Engine v1.0.

Explanation Engine ONLY. Never modifies constitutional decisions.

Execution contract:
  - Runs ONCE per completed scan, after all signals are finalized.
  - Analyzes only: Near Entry, BUY (FIRST_BUY), RE-ACCUMULATION candidates.
  - Reads existing project data. Never duplicates stored information.
  - Stores behavioral snapshots in mpi_snapshots.db.
  - Dashboard, Email, Telegram consume stored snapshots — never recompute.

Constitutional guarantee:
  - No constitutional score is touched.
  - No gate is touched.
  - No ranking is touched.
  - No signal is generated, rejected, or modified.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

BASE = Path(__file__).parent

logger = logging.getLogger("mpi_engine")

# ── Configuration ─────────────────────────────────────────────────────────────

def _load_cfg() -> dict:
    path = BASE / "config" / "mpi_config.json"
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}

_CFG: dict = {}


def _cfg() -> dict:
    global _CFG
    if not _CFG:
        _CFG = _load_cfg()
    return _CFG


def _conf_threshold() -> float:
    return _cfg().get("confidence", {}).get("display_threshold", 0.45)


def _high_threshold() -> float:
    return _cfg().get("confidence", {}).get("high_threshold", 0.70)


def _medium_threshold() -> float:
    return _cfg().get("confidence", {}).get("medium_threshold", 0.45)


# ── Phase Detection ────────────────────────────────────────────────────────────

_PHASE_PRIORITY = [
    "Capitulation",
    "Late Capitulation",
    "Silent Accumulation",
    "Accumulation",
    "Confidence Building",
    "Early Markup",
    "Markup",
    "Fear",
    "Neutral",
]


def _detect_phase(feat: dict) -> tuple[str, list[str]]:
    """
    Derive one behavioral phase from available scan features.
    Returns (phase_name, [confirmed_evidence_keys]).
    Only uses features already computed by the constitutional engine.
    """
    sweep  = feat.get("sweep_detected", False)
    sv     = feat.get("sv_hit", False)
    hvn    = feat.get("hvn_hit", False)
    ob_q   = float(feat.get("ob_quality") or 0)
    macd   = feat.get("macd_val")
    htf_hh = feat.get("htf_hh", False)
    htf_hl = feat.get("htf_hl", False)
    rsi_d  = feat.get("rsi_div", False)
    macd_d = feat.get("macd_div", False)
    r6     = float(feat.get("r6_macd") or feat.get("r6") or 0)
    r4     = float(feat.get("r4_htf") or feat.get("r4") or 0)
    ob_th  = float(_cfg().get("phase_thresholds", {}).get("ob_quality_high_cutoff", 60.0))

    evidence: list[str] = []

    macd_pos = (macd is not None and macd > 0)
    macd_neg = (macd is not None and macd < 0)
    htf_up   = htf_hh and htf_hl

    # Capitulation: liquidity swept + stopping volume + negative momentum
    if sweep and sv and macd_neg:
        evidence += ["sweep_detected", "sv_hit", "macd_negative"]
        if hvn:
            evidence.append("hvn_hit")
            return "Late Capitulation", evidence
        return "Capitulation", evidence

    # Divergence-driven late capitulation (exhaustion without full sweep yet)
    if (rsi_d or macd_d) and sv:
        evidence += ["sv_hit"]
        if rsi_d:  evidence.append("rsi_div")
        if macd_d: evidence.append("macd_div")
        return "Late Capitulation", evidence

    # Silent Accumulation: demand zones confirmed but no sweep
    if sv and hvn and not sweep:
        evidence += ["sv_hit", "hvn_hit"]
        return "Silent Accumulation", evidence

    # Accumulation: sweep + demand + good OB quality
    if sweep and sv and ob_q >= ob_th:
        evidence += ["sweep_detected", "sv_hit", "ob_quality_high"]
        return "Accumulation", evidence

    # Accumulation: sweep + demand (OB not required)
    if sweep and sv:
        evidence += ["sweep_detected", "sv_hit"]
        return "Accumulation", evidence

    # Confidence Building: HTF uptrend + positive MACD
    if htf_up and macd_pos:
        evidence += ["htf_uptrend", "macd_positive"]
        if ob_q >= ob_th:
            evidence.append("ob_quality_high")
        return "Confidence Building", evidence

    # Early Markup: HTF uptrend without demand zone confirmation
    if htf_up and r4 > 0:
        evidence.append("htf_uptrend")
        return "Early Markup", evidence

    # Fear: in discount zone, no demand confirmation yet
    if sv:
        evidence.append("sv_hit")
        return "Fear", evidence

    if hvn:
        evidence.append("hvn_hit")
        return "Fear", evidence

    return "Neutral", []


# ── Investor Behavior Inference ────────────────────────────────────────────────

_PHASE_BEHAVIOR: dict[str, dict] = {
    "Capitulation": {
        "institutional":   "Institutions beginning early absorption of distressed supply.",
        "retail":          "Retail sellers dominating price action.",
        "buying_pressure": "Weak",
        "selling_pressure":"Strong",
        "supply_absorption":"Early-stage",
        "distribution_prob": "Low",
    },
    "Late Capitulation": {
        "institutional":   "Institutional supply absorption strengthening near demand zone.",
        "retail":          "Retail capitulation nearing exhaustion.",
        "buying_pressure": "Strengthening",
        "selling_pressure":"Weakening",
        "supply_absorption":"Active",
        "distribution_prob": "Low",
    },
    "Silent Accumulation": {
        "institutional":   "Institutional accumulation occurring without retail awareness.",
        "retail":          "Retail participation minimal.",
        "buying_pressure": "Moderate",
        "selling_pressure":"Declining",
        "supply_absorption":"Progressive",
        "distribution_prob": "Very Low",
    },
    "Accumulation": {
        "institutional":   "Institutional demand confirmed at structural support level.",
        "retail":          "Retail activity transitioning from selling to holding.",
        "buying_pressure": "Building",
        "selling_pressure":"Declining",
        "supply_absorption":"Strong",
        "distribution_prob": "Very Low",
    },
    "Confidence Building": {
        "institutional":   "Institutional positioning extending as structure improves.",
        "retail":          "Retail confidence gradually returning.",
        "buying_pressure": "Growing",
        "selling_pressure":"Subdued",
        "supply_absorption":"Established",
        "distribution_prob": "Low",
    },
    "Early Markup": {
        "institutional":   "Institutional positions being extended on confirmed uptrend.",
        "retail":          "Early retail participants beginning to re-enter.",
        "buying_pressure": "Strong",
        "selling_pressure":"Minimal",
        "supply_absorption":"Complete",
        "distribution_prob": "Low",
    },
    "Markup": {
        "institutional":   "Broad institutional participation in markup phase.",
        "retail":          "Retail re-engagement accelerating.",
        "buying_pressure": "Strong",
        "selling_pressure":"Minimal",
        "supply_absorption":"Complete",
        "distribution_prob": "Low",
    },
    "Fear": {
        "institutional":   "Institutional activity unclear — insufficient demand confirmation.",
        "retail":          "Retail selling pressure visible.",
        "buying_pressure": "Weak",
        "selling_pressure":"Moderate",
        "supply_absorption":"Unconfirmed",
        "distribution_prob": "Moderate",
    },
    "Neutral": {
        "institutional":   "Institutional direction indeterminate.",
        "retail":          "Retail activity mixed.",
        "buying_pressure": "Indeterminate",
        "selling_pressure":"Indeterminate",
        "supply_absorption":"Unconfirmed",
        "distribution_prob": "Moderate",
    },
}


def _infer_behavior(phase: str) -> dict:
    return _PHASE_BEHAVIOR.get(phase, _PHASE_BEHAVIOR["Neutral"])


# ── Confidence Scoring ─────────────────────────────────────────────────────────

def _compute_confidence(evidence: list[str], historical_cases: int,
                         similarity: float, feat: dict) -> float:
    """
    Evidence-driven confidence score [0.0, 1.0].
    Confidence does NOT affect constitutional decisions.
    It only determines whether an explanation is shown.
    """
    weights = _cfg().get("evidence_weights", {})
    score   = 0.0

    ev_set = set(evidence)
    for key, w in weights.items():
        if key == "historical_match":
            continue
        if key in ev_set:
            score += w

    # Historical bonus: up to 0.10
    if historical_cases >= 10:
        hist_bonus = 0.10
    elif historical_cases >= 5:
        hist_bonus = 0.07
    elif historical_cases >= 3:
        hist_bonus = 0.04
    else:
        hist_bonus = 0.0
    hist_weight = weights.get("historical_match", 0.05)
    score += hist_bonus * (hist_weight / 0.05)

    # Similarity boosts confidence proportionally
    if similarity >= 0.70:
        score = min(1.0, score * 1.10)

    return round(min(1.0, max(0.0, score)), 4)


def _confidence_label(c: float) -> str:
    if c >= _high_threshold():
        return "HIGH"
    if c >= _medium_threshold():
        return "MEDIUM"
    return "LOW"


# ── Historical Comparison ──────────────────────────────────────────────────────

def _fetch_historical_analogs(ticker: str, feat: dict) -> dict:
    """
    Search egx_research.db for similar behavioral situations.
    Similarity based on R-score vector distance.
    Returns stats dict. Never uses future data.
    """
    db_path = BASE / "egx_research.db"
    if not db_path.exists():
        return {"cases": 0, "similarity": 0.0, "avg_mfe40": 0.0,
                "avg_drawdown": 0.0, "avg_holding_days": 0.0, "confidence": "LOW"}

    r_weights_cfg = _cfg().get("historical_comparison", {}).get("r_score_weights", {})
    r_weights = {
        "r1": r_weights_cfg.get("r1", 0.10),
        "r2": r_weights_cfg.get("r2", 0.15),
        "r3": r_weights_cfg.get("r3", 0.20),
        "r4": r_weights_cfg.get("r4", 0.10),
        "r5": r_weights_cfg.get("r5", 0.10),
        "r6": r_weights_cfg.get("r6", 0.15),
        "r7": r_weights_cfg.get("r7", 0.10),
        "r8": r_weights_cfg.get("r8", 0.10),
    }

    cur_r = {
        "r1": float(feat.get("r1_price") or feat.get("r1") or 0),
        "r2": float(feat.get("r2_ob") or feat.get("r2") or 0),
        "r3": float(feat.get("r3_liquidity") or feat.get("r3") or 0),
        "r4": float(feat.get("r4_htf") or feat.get("r4") or 0),
        "r5": float(feat.get("r5_avwap") or feat.get("r5") or 0),
        "r6": float(feat.get("r6_macd") or feat.get("r6") or 0),
        "r7": float(feat.get("r7_div") or feat.get("r7") or 0),
        "r8": float(feat.get("r8_demand") or feat.get("r8") or 0),
    }

    min_sim = float(_cfg().get("historical_comparison", {}).get("min_similarity", 0.50))
    min_n   = int(_cfg().get("historical_comparison", {}).get("min_sample_size", 3))
    max_days = int(_cfg().get("historical_comparison", {}).get("max_lookback_days", 730))

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cutoff = (datetime.now() - timedelta(days=max_days)).date().isoformat()
        rows = conn.execute(
            """
            SELECT s.r1_price, s.r2_ob, s.r3_liquidity, s.r4_htf,
                   s.r5_avwap, s.r6_macd, s.r7_div, s.r8_demand,
                   b.mfe_20d, b.mae_20d
            FROM signals s
            LEFT JOIN bottom_quality b ON b.signal_id = s.id
            WHERE s.signal_date >= ?
              AND s.signal_type NOT IN ('SKIP','WAIT')
            """,
            (cutoff,),
        ).fetchall()
        conn.close()
    except Exception:
        return {"cases": 0, "similarity": 0.0, "avg_mfe40": 0.0,
                "avg_drawdown": 0.0, "avg_holding_days": 0.0, "confidence": "LOW"}

    matched_mfe: list[float] = []
    matched_dd:  list[float] = []
    similarity_sum = 0.0

    for row in rows:
        hist_r = {
            "r1": float(row["r1_price"] or 0),
            "r2": float(row["r2_ob"] or 0),
            "r3": float(row["r3_liquidity"] or 0),
            "r4": float(row["r4_htf"] or 0),
            "r5": float(row["r5_avwap"] or 0),
            "r6": float(row["r6_macd"] or 0),
            "r7": float(row["r7_div"] or 0),
            "r8": float(row["r8_demand"] or 0),
        }

        # Weighted cosine-style similarity on normalized R vectors
        dot, norm_cur, norm_hist = 0.0, 0.0, 0.0
        for k, w in r_weights.items():
            c = cur_r[k] * w
            h = hist_r[k] * w
            dot      += c * h
            norm_cur += c * c
            norm_hist += h * h

        if norm_cur <= 0 or norm_hist <= 0:
            continue

        import math
        sim = dot / (math.sqrt(norm_cur) * math.sqrt(norm_hist))
        if sim < min_sim:
            continue

        similarity_sum += sim
        mfe = float(row["mfe_20d"] or 0)
        mae = float(row["mae_20d"] or 0)
        matched_mfe.append(mfe)
        matched_dd.append(mae)

    n = len(matched_mfe)
    if n < min_n:
        return {"cases": 0, "similarity": 0.0, "avg_mfe40": 0.0,
                "avg_drawdown": 0.0, "avg_holding_days": 0.0, "confidence": "LOW"}

    avg_sim = similarity_sum / n
    avg_mfe = sum(matched_mfe) / n * 100  # convert fraction to %
    avg_dd  = abs(sum(matched_dd) / n * 100) if matched_dd else 0.0

    if n >= 10 and avg_sim >= 0.75:
        hist_conf = "HIGH"
    elif n >= 5 and avg_sim >= 0.60:
        hist_conf = "MEDIUM"
    else:
        hist_conf = "LOW"

    return {
        "cases":          n,
        "similarity":     round(avg_sim, 4),
        "avg_mfe40":      round(avg_mfe, 1),
        "avg_drawdown":   round(avg_dd, 1),
        "avg_holding_days": 0.0,
        "confidence":     hist_conf,
    }


# ── Explanation Templates ──────────────────────────────────────────────────────

_PHASE_INTRO: dict[str, str] = {
    "Capitulation":        "Early-stage capitulation detected.",
    "Late Capitulation":   "Late-stage capitulation detected.",
    "Silent Accumulation": "Silent accumulation pattern identified.",
    "Accumulation":        "Active accumulation phase confirmed.",
    "Confidence Building": "Confidence-building phase in progress.",
    "Early Markup":        "Early markup phase initiated.",
    "Markup":              "Markup phase in progress.",
    "Fear":                "Fear-driven selling visible in price action.",
    "Neutral":             "Behavioral state inconclusive.",
}

_DEMAND_SENTENCE: dict[str, str] = {
    "sv_hvn": (
        "Stopping volume combined with a high-volume demand node confirms "
        "institutional supply absorption at this level."
    ),
    "sv_ob": (
        "Stopping volume at a respected order block suggests demand "
        "is being absorbed by larger participants."
    ),
    "sv_only": (
        "Stopping volume indicates selling pressure is being absorbed "
        "at this discount zone."
    ),
    "hvn_only": (
        "A high-volume demand node marks institutional interest "
        "at the current price level."
    ),
    "ob_only": (
        "An intact order block is attracting buying interest "
        "at structural support."
    ),
    "none": (
        "Demand zone not yet confirmed by volume or order block evidence."
    ),
}

_SWEEP_SENTENCE = (
    "A liquidity sweep followed by a demand reaction "
    "supports the reversal thesis."
)

_DIV_SENTENCE = (
    "Momentum divergence signals selling exhaustion "
    "at the current discount level."
)

_HTF_SENTENCE = (
    "Higher-timeframe structure shows higher highs and higher lows, "
    "confirming the underlying trend."
)

_HIST_SENTENCE = (
    "This behavior resembles {n} historical constitutional reversals "
    "with an average MFE40 of {mfe:+.0f}%."
)

_CLOSING: dict[str, str] = {
    "HIGH":   "Behavior strongly supports the constitutional signal.",
    "MEDIUM": "Behavior is consistent with the constitutional signal.",
    "LOW":    "Behavioral evidence partially aligns with the constitutional signal.",
}


def _select_demand_key(evidence: list[str], ob_quality: float) -> str:
    sv  = "sv_hit"  in evidence
    hvn = "hvn_hit" in evidence
    ob  = "ob_quality_high" in evidence or ob_quality >= float(
        _cfg().get("phase_thresholds", {}).get("ob_quality_high_cutoff", 60.0))

    if sv and hvn:  return "sv_hvn"
    if sv and ob:   return "sv_ob"
    if sv:          return "sv_only"
    if hvn:         return "hvn_only"
    if ob:          return "ob_only"
    return "none"


def _generate_explanation(
    phase: str,
    evidence: list[str],
    behavior: dict,
    hist: dict,
    conf_label: str,
    feat: dict,
) -> tuple[str, str]:
    """
    Build deterministic explanation (full + compact) from stored values.
    No LLM. No external calls. Same stored data → same text every time.
    Returns (explanation, explanation_compact).
    """
    sentences: list[str] = []

    # 1. Phase intro
    sentences.append(_PHASE_INTRO.get(phase, "Behavioral state inconclusive."))

    # 2. Demand evidence
    ob_q = float(feat.get("ob_quality") or 0)
    demand_key = _select_demand_key(evidence, ob_q)
    demand_sent = _DEMAND_SENTENCE[demand_key]
    if demand_key != "none":
        sentences.append(demand_sent)

    # 3. Sweep (only when confirmed)
    if "sweep_detected" in evidence:
        sentences.append(_SWEEP_SENTENCE)

    # 4. Divergence
    if "rsi_div" in evidence or "macd_div" in evidence:
        sentences.append(_DIV_SENTENCE)

    # 5. HTF
    if "htf_uptrend" in evidence:
        sentences.append(_HTF_SENTENCE)

    # 6. Historical reference (only when meaningful)
    n = hist.get("cases", 0)
    mfe = hist.get("avg_mfe40", 0.0)
    if n >= 3:
        sentences.append(_HIST_SENTENCE.format(n=n, mfe=mfe))

    # 7. Closing
    sentences.append(_CLOSING.get(conf_label, _CLOSING["LOW"]))

    explanation = " ".join(sentences)

    # Trim to configured max words
    max_w = int(_cfg().get("explanation", {}).get("max_words", 120))
    words = explanation.split()
    if len(words) > max_w:
        explanation = " ".join(words[:max_w]) + "."

    # Compact (≤4 lines for Telegram)
    compact_lines = [
        f"{phase}",
        behavior.get("institutional", ""),
    ]
    if n >= 3:
        sim_pct = int(round(hist.get("similarity", 0.0) * 100))
        compact_lines.append(f"Historical similarity: {sim_pct}%")
    compact_lines.append(_CLOSING.get(conf_label, _CLOSING["LOW"]))

    compact = "\n".join(line for line in compact_lines[:4] if line)

    return explanation, compact


# ── Key Drivers ────────────────────────────────────────────────────────────────

def _extract_key_drivers(evidence: list[str], phase: str, feat: dict) -> list[str]:
    driver_map = {
        "sweep_detected":  "Liquidity sweep detected",
        "sv_hit":          "Stopping volume confirmed",
        "hvn_hit":         "High-volume demand node present",
        "ob_quality_high": "Order block quality confirmed",
        "rsi_div":         "RSI momentum divergence",
        "macd_div":        "MACD momentum divergence",
        "htf_uptrend":     "Higher-timeframe uptrend (HH+HL)",
        "macd_positive":   "MACD above zero",
        "macd_negative":   "MACD below zero (selling phase)",
    }
    drivers = [driver_map[e] for e in evidence if e in driver_map]

    ob_q = float(feat.get("ob_quality") or 0)
    if ob_q > 0 and "ob_quality_high" not in evidence:
        drivers.append(f"Order block quality {ob_q:.0f}%")

    return drivers


# ── Single-ticker Analysis ─────────────────────────────────────────────────────

def analyze_ticker(
    ticker: str,
    signal_type: str,
    feat: dict,
    analysis_date: str,
) -> Optional[dict]:
    """
    Perform behavioral analysis for one ticker.
    Returns a complete snapshot dict ready for mpi_db.upsert_snapshot(), or None on failure.
    signal_type: 'FIRST_BUY' | 'RE_ACCUMULATION' | 'NEAR_ENTRY'
    """
    try:
        t0 = time.monotonic()

        phase, evidence = _detect_phase(feat)
        behavior        = _infer_behavior(phase)
        hist            = _fetch_historical_analogs(ticker, feat)
        confidence      = _compute_confidence(evidence, hist["cases"], hist["similarity"], feat)
        conf_label      = _confidence_label(confidence)
        explanation, compact = _generate_explanation(
            phase, evidence, behavior, hist, conf_label, feat
        )
        drivers = _extract_key_drivers(evidence, phase, feat)

        evidence_record = {
            "phase_evidence": evidence,
            "sweep_detected": feat.get("sweep_detected", False),
            "sv_hit":         feat.get("sv_hit", False),
            "hvn_hit":        feat.get("hvn_hit", False),
            "rsi_div":        feat.get("rsi_div", False),
            "macd_div":       feat.get("macd_div", False),
            "ob_quality":     float(feat.get("ob_quality") or 0),
            "macd_val":       feat.get("macd_val"),
            "htf_hh":         feat.get("htf_hh", False),
            "htf_hl":         feat.get("htf_hl", False),
            "r_scores": {
                "r1": float(feat.get("r1_price") or feat.get("r1") or 0),
                "r2": float(feat.get("r2_ob") or feat.get("r2") or 0),
                "r3": float(feat.get("r3_liquidity") or feat.get("r3") or 0),
                "r4": float(feat.get("r4_htf") or feat.get("r4") or 0),
                "r5": float(feat.get("r5_avwap") or feat.get("r5") or 0),
                "r6": float(feat.get("r6_macd") or feat.get("r6") or 0),
                "r7": float(feat.get("r7_div") or feat.get("r7") or 0),
                "r8": float(feat.get("r8_demand") or feat.get("r8") or 0),
            },
            "historical_analogs": hist,
            "analysis_ms": round((time.monotonic() - t0) * 1000, 1),
        }

        from time_authority import now_iso
        created_at = now_iso()

        return {
            "ticker":                     ticker,
            "signal_type":                signal_type,
            "analysis_date":              analysis_date,
            "engine_version":             "1.0",
            "schema_version":             "1",
            "phase":                      phase,
            "confidence":                 confidence,
            "confidence_label":           conf_label,
            "institutional_interpretation": behavior.get("institutional", ""),
            "retail_interpretation":      behavior.get("retail", ""),
            "buying_pressure":            behavior.get("buying_pressure", ""),
            "selling_pressure":           behavior.get("selling_pressure", ""),
            "supply_absorption":          behavior.get("supply_absorption", ""),
            "distribution_probability":   behavior.get("distribution_prob", ""),
            "key_drivers":                json.dumps(drivers),
            "evidence_json":              json.dumps(evidence_record),
            "historical_cases":           hist["cases"],
            "similarity_score":           hist["similarity"],
            "avg_mfe40":                  hist["avg_mfe40"],
            "avg_drawdown":               hist["avg_drawdown"],
            "avg_holding_days":           hist["avg_holding_days"],
            "historical_confidence":      hist["confidence"],
            "explanation":                explanation,
            "explanation_compact":        compact,
            "created_at":                 created_at,
        }

    except Exception as exc:
        logger.warning("[MPI] analyze_ticker failed %s %s: %s", ticker, signal_type, exc)
        return None


# ── Public Run Interface ───────────────────────────────────────────────────────

_UNAVAILABLE_EXPLANATION = "Behavior interpretation unavailable."
_UNAVAILABLE_COMPACT     = "Behavior interpretation unavailable."


def run_for_current_signals(
    results: dict,
    snap,
    db_path: Optional[str] = None,
) -> dict:
    """
    Entry point called once per completed scan.

    results: dict produced by main.py analyze() keyed by ticker
    snap:    PresentationSnapshot after all signals are finalized

    Analyzes only: Near Entry, FIRST_BUY, RE_ACCUMULATION candidates.
    Stores results in mpi_snapshots.db. Returns execution summary.
    """
    from mpi_db import upsert_snapshot, init_db
    from time_authority import today_iso

    _db = db_path or str(BASE / "mpi_snapshots.db")
    init_db(_db)

    date_str = today_iso()
    t0 = time.monotonic()
    processed, stored, skipped, errors = 0, 0, 0, 0

    targets: list[tuple[str, str]] = []  # (ticker, signal_type)

    # Collect tickers to analyze (de-duplicate: prefer FIRST_BUY/RE_ACCUM over NEAR_ENTRY)
    priority_tickers: set[str] = set()

    for evt in (snap.first_buys or []):
        t = evt.get("ticker", "")
        if t:
            targets.append((t, "FIRST_BUY"))
            priority_tickers.add(t)

    for evt in (snap.re_accumulations or []):
        t = evt.get("ticker", "")
        if t and t not in priority_tickers:
            targets.append((t, "RE_ACCUMULATION"))
            priority_tickers.add(t)

    for entry in (snap.approaching_entries or []):
        t = entry.get("ticker", "")
        if t and t not in priority_tickers:
            targets.append((t, "NEAR_ENTRY"))

    if not targets:
        logger.info("[MPI] No targets to analyze (no BUY/RE_ACCUMULATION/NEAR_ENTRY signals today).")
        return {
            "date": date_str, "processed": 0, "stored": 0,
            "skipped": 0, "errors": 0, "elapsed_ms": 0,
        }

    logger.info("[MPI] Analyzing %d target(s) for %s", len(targets), date_str)
    print(f"[MPI] Analyzing {len(targets)} target(s) for {date_str}")

    for ticker, signal_type in targets:
        processed += 1
        feat = results.get(ticker, {})
        if not feat.get("ok"):
            # For NEAR_ENTRY, feat may be minimal; still attempt with what we have
            feat = {"ok": True}

        snapshot = analyze_ticker(ticker, signal_type, feat, date_str)
        if snapshot is None:
            errors += 1
            continue

        # Below-threshold: replace explanation with unavailable message
        threshold = _conf_threshold()
        if snapshot["confidence"] < threshold:
            snapshot["explanation"]         = _UNAVAILABLE_EXPLANATION
            snapshot["explanation_compact"] = _UNAVAILABLE_COMPACT

        try:
            upsert_snapshot(snapshot, db_path=_db)
            stored += 1
            logger.info(
                "[MPI] %s %s → phase=%s conf=%.2f",
                ticker, signal_type, snapshot["phase"], snapshot["confidence"],
            )
            print(
                f"[MPI]  {ticker:10s} {signal_type:16s} "
                f"phase={snapshot['phase']:22s} conf={snapshot['confidence']:.2f}"
            )
        except Exception as exc:
            errors += 1
            logger.warning("[MPI] DB write failed %s: %s", ticker, exc)

    elapsed_ms = round((time.monotonic() - t0) * 1000)
    logger.info(
        "[MPI] Done — processed=%d stored=%d skipped=%d errors=%d elapsed=%dms",
        processed, stored, skipped, errors, elapsed_ms,
    )
    print(
        f"[MPI] Done — processed={processed} stored={stored} "
        f"errors={errors} elapsed={elapsed_ms}ms"
    )

    return {
        "date":        date_str,
        "processed":   processed,
        "stored":      stored,
        "skipped":     skipped,
        "errors":      errors,
        "elapsed_ms":  elapsed_ms,
    }


# ── Snapshot Reader (for presentation layers) ─────────────────────────────────

def get_snapshot_for_ticker(
    ticker: str,
    date_str: str,
    signal_type: str = "",
    db_path: Optional[str] = None,
) -> Optional[dict]:
    """
    Read one stored MPI snapshot. Returns None if unavailable.
    Presentation layers use this — they never call run_for_current_signals().
    """
    from mpi_db import load_snapshot, load_snapshots_for_tickers

    _db = db_path or str(BASE / "mpi_snapshots.db")

    if signal_type:
        return load_snapshot(ticker, date_str, signal_type, db_path=_db)

    # No signal_type given: prefer FIRST_BUY > RE_ACCUMULATION > NEAR_ENTRY
    for st in ("FIRST_BUY", "RE_ACCUMULATION", "NEAR_ENTRY"):
        snap = load_snapshot(ticker, date_str, st, db_path=_db)
        if snap:
            return snap
    return None


def get_snapshots_for_date(date_str: str, db_path: Optional[str] = None) -> dict[str, dict]:
    """Return {ticker: snapshot} for all MPI records on a given date."""
    from mpi_db import load_snapshots_for_date

    _db = db_path or str(BASE / "mpi_snapshots.db")
    rows = load_snapshots_for_date(date_str, db_path=_db)
    out: dict[str, dict] = {}
    for r in rows:
        t = r.get("ticker", "")
        existing = out.get(t)
        if existing is None or r.get("signal_type") in ("FIRST_BUY", "RE_ACCUMULATION"):
            out[t] = r
    return out


# ── HTML Helpers (consumed by dashboard + email) ──────────────────────────────

def render_behavior_insight_html(snap: Optional[dict], theme: str = "dark") -> str:
    """
    Render a self-contained Behavior Insight HTML block.
    theme='dark'  → dashboard color scheme
    theme='light' → email color scheme
    Returns empty string if snap is None or explanation unavailable.
    """
    if not snap:
        return ""

    explanation = snap.get("explanation", "")
    if not explanation or explanation == _UNAVAILABLE_EXPLANATION:
        return ""

    phase      = snap.get("phase", "")
    conf_label = snap.get("confidence_label", "")
    hist_n     = int(snap.get("historical_cases", 0))
    avg_mfe    = float(snap.get("avg_mfe40", 0.0))
    sim        = float(snap.get("similarity_score", 0.0))

    if theme == "dark":
        border  = "#252645"
        bg      = "#10112a"
        bg2     = "#181930"
        title   = "#8b8fa8"
        fg      = "#d0d4e8"
        phase_c = "#50d8d0"
        conf_c  = "#4caf50" if conf_label == "HIGH" else ("#f0b840" if conf_label == "MEDIUM" else "#8b8fa8")
    else:
        border  = "#d0d7e2"
        bg      = "#f0f8ff"
        bg2     = "#ffffff"
        title   = "#888888"
        fg      = "#333333"
        phase_c = "#0b4a8f"
        conf_c  = "#28a745" if conf_label == "HIGH" else ("#f0b840" if conf_label == "MEDIUM" else "#888888")

    hist_line = ""
    if hist_n >= 3:
        sim_pct = int(round(sim * 100))
        hist_line = (
            f'<div style="font-size:11px;color:{title};margin-top:6px;">'
            f'Historical similarity: <strong style="color:{fg};">{sim_pct}%</strong> &nbsp;·&nbsp; '
            f'Avg MFE40: <strong style="color:{fg};">{avg_mfe:+.0f}%</strong> '
            f'({hist_n} cases)'
            f'</div>'
        )

    conf_badge = (
        f'<span style="background:{conf_c}22;color:{conf_c};padding:2px 8px;'
        f'border-radius:10px;font-size:10px;font-weight:700;">{conf_label}</span>'
    )

    return (
        f'<div style="background:{bg};border:1px solid {border};border-radius:8px;'
        f'padding:12px 14px;margin-top:12px;">'
        f'<div style="font-size:10px;font-weight:700;text-transform:uppercase;'
        f'letter-spacing:0.6px;color:{title};margin-bottom:6px;">'
        f'🧠 Behavior Insight &nbsp; {conf_badge}'
        f'</div>'
        f'<div style="font-size:12px;font-weight:700;color:{phase_c};margin-bottom:4px;">'
        f'{phase}'
        f'</div>'
        f'<div style="font-size:12px;color:{fg};line-height:1.5;">'
        f'{explanation}'
        f'</div>'
        f'{hist_line}'
        f'</div>'
    )


def render_behavior_insight_telegram(snap: Optional[dict]) -> str:
    """
    Render compact Telegram Behavior Insight block (≤4 lines).
    Returns empty string if snap is None or explanation unavailable.
    """
    if not snap:
        return ""
    compact = snap.get("explanation_compact", "")
    if not compact or compact == _UNAVAILABLE_COMPACT:
        return ""
    return f"🧠 *Behavior*\n{compact}"
