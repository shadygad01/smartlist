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
        if rsi_d:   evidence.append("rsi_div")
        if macd_d:  evidence.append("macd_div")
        if sweep:   evidence.append("sweep_detected")  # collect sweep if present — was dropped by greedy exit
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

    # Early Markup: HTF uptrend with meaningful HTF score (above config cutoff)
    htf_r4_th = float(_cfg().get("phase_thresholds", {}).get("htf_uptrend_r4_cutoff", 0.5))
    if htf_up and r4 >= htf_r4_th:
        evidence.append("htf_uptrend")
        return "Early Markup", evidence

    # Fear: in discount zone, no demand confirmation yet
    if sv:
        evidence.append("sv_hit")
        return "Fear", evidence

    if hvn:
        evidence.append("hvn_hit")
        return "Fear", evidence

    # Sweep detected — volume confirmation pending.
    # Sweep alone is a meaningful structural signal (liquidity run without
    # volume absorption yet). Include HTF uptrend when present to push
    # confidence past the display threshold for unlocked tickers.
    if sweep and htf_up:
        evidence += ["sweep_detected", "htf_uptrend"]
        return "Fear", evidence

    if sweep:
        evidence.append("sweep_detected")
        return "Fear", evidence

    return "Neutral", []


# ── Investor Behavior Inference ────────────────────────────────────────────────

_PHASE_BEHAVIOR: dict[str, dict] = {
    # Each entry describes observable market state inferred from confirmed evidence.
    # Participant attribution ("institutional"/"retail" field names are schema-fixed)
    # describes market-observable conditions, not unverifiable participant intent.
    "Capitulation": {
        "institutional":   "Supply absorption initiating at depressed price levels.",
        "retail":          "Net selling pressure dominant; price testing structural lows.",
        "buying_pressure": "Weak",
        "selling_pressure":"Strong",
        "supply_absorption":"Early-stage",
        "distribution_prob": "Low",
    },
    "Late Capitulation": {
        "institutional":   "Supply absorption strengthening at confirmed demand zone.",
        "retail":          "Net selling pressure diminishing near volume exhaustion.",
        "buying_pressure": "Strengthening",
        "selling_pressure":"Weakening",
        "supply_absorption":"Active",
        "distribution_prob": "Low",
    },
    "Silent Accumulation": {
        # Observable: sv_hit + hvn_hit without sweep = volume absorption at a
        # historical demand node, no liquidity disruption. "Without price disruption"
        # is directly observable; participant identity is not.
        "institutional":   "Supply absorption progressing at structural demand levels without price disruption.",
        "retail":          "Price holding at demand zone; no significant selling volume spikes.",
        "buying_pressure": "Moderate",
        "selling_pressure":"Declining",
        "supply_absorption":"Progressive",
        "distribution_prob": "Very Low",
    },
    "Accumulation": {
        # Observable: sweep + sv (+ optional OB quality). Liquidity run triggered
        # stops; volume absorption followed. "Structural support" is the OB/demand level.
        "institutional":   "Demand absorption confirmed at structural support after liquidity sweep.",
        "retail":          "Selling pressure abating as price stabilises at demand zone.",
        "buying_pressure": "Building",
        "selling_pressure":"Declining",
        "supply_absorption":"Strong",
        "distribution_prob": "Very Low",
    },
    "Confidence Building": {
        # Observable: htf higher highs/lows + MACD above zero = improving price
        # structure on higher timeframe with positive momentum. No causal psychology.
        "institutional":   "Price structure improving; momentum turning positive on higher timeframe.",
        "retail":          "Buying activity increasing as price recovers above key structural levels.",
        "buying_pressure": "Growing",
        "selling_pressure":"Subdued",
        "supply_absorption":"Established",
        "distribution_prob": "Low",
    },
    "Early Markup": {
        # Observable: htf uptrend (HH+HL) with meaningful HTF score. Price advancing
        # above demand zone. No claim about who is buying.
        "institutional":   "Higher-timeframe uptrend structure intact; demand zone holding.",
        "retail":          "Price advancing above demand zone with positive higher-timeframe structure.",
        "buying_pressure": "Strong",
        "selling_pressure":"Minimal",
        "supply_absorption":"Complete",
        "distribution_prob": "Low",
    },
    "Markup": {
        "institutional":   "Broad participation in markup phase; trend structure intact.",
        "retail":          "Buying activity accelerating as price advances.",
        "buying_pressure": "Strong",
        "selling_pressure":"Minimal",
        "supply_absorption":"Complete",
        "distribution_prob": "Low",
    },
    "Fear": {
        # Observable: one or two demand signals present but insufficient confluence.
        # "Demand confirmation insufficient" is directly supported by evidence count.
        "institutional":   "Demand confirmation insufficient — fewer than two confluent structural signals.",
        "retail":          "Price in potential discount zone; single-factor signal only.",
        "buying_pressure": "Weak",
        "selling_pressure":"Moderate",
        "supply_absorption":"Unconfirmed",
        "distribution_prob": "Moderate",
    },
    "Neutral": {
        "institutional":   "Market direction indeterminate — insufficient evidence for phase assignment.",
        "retail":          "Mixed activity; no dominant directional pressure observable.",
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

    # Historical bonus: scales proportionally to hist_weight in config.
    # hist_bonus_fraction in [0.0, 1.0] represents fraction of max historical credit earned.
    # Max contribution = hist_weight (consistent with configured evidence weight).
    if historical_cases >= 10:
        hist_bonus_fraction = 1.00
    elif historical_cases >= 5:
        hist_bonus_fraction = 0.70
    elif historical_cases >= 3:
        hist_bonus_fraction = 0.40
    else:
        hist_bonus_fraction = 0.0
    hist_weight = weights.get("historical_match", 0.05)
    score += hist_bonus_fraction * hist_weight

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

_ROWS_LABEL_TO_KEY = {
    "Price Position":      "r1_price",
    "Order Block Quality": "r2_ob",
    "Liquidity Context":   "r3_liquidity",
    "Higher Timeframe":    "r4_htf",
    "Anchored VWAP":       "r5_avwap",
    "MACD vs Zero":        "r6_macd",
    "Divergence":          "r7_div",
    "Demand Zone (SV+VP)": "r8_demand",
}


def _extract_r_scores_from_feat(feat: dict) -> dict:
    """
    Extract R1-R8 scores from the scan result dict.

    analyze() in main.py stores only `r1` as a named key; r2-r8 live in
    `rows` as (label, score, weight, desc) tuples. This function reads
    `rows` and returns a flat dict keyed by r1_price..r8_demand so that
    MPI has a complete R-score vector even when only `rows` is present.

    The `r1` shorthand (= r1_price) is also accepted as a fallback.
    """
    out: dict[str, float] = {}
    rows = feat.get("rows") or []
    for entry in rows:
        if len(entry) >= 2:
            label = entry[0]
            score = entry[1]
            key   = _ROWS_LABEL_TO_KEY.get(label)
            if key and score is not None:
                out[key] = float(score)
    # Fallback: r1 shorthand if rows didn't provide it
    if "r1_price" not in out:
        r1 = feat.get("r1_price") or feat.get("r1")
        if r1 is not None:
            out["r1_price"] = float(r1)
    return out


def _behavioral_cosine(cur_b: dict, hist_b: dict, b_weights: dict) -> float:
    """
    Weighted cosine similarity on binary behavioral features.
    Binary features are treated as 0/1 floats; weights handle scaling.
    """
    import math
    dot = norm_cur = norm_hist = 0.0
    for k, w in b_weights.items():
        c = float(bool(cur_b.get(k, False))) * w
        h = float(bool(hist_b.get(k, False))) * w
        dot       += c * h
        norm_cur  += c * c
        norm_hist += h * h
    if norm_cur <= 0 or norm_hist <= 0:
        return 0.0
    return dot / (math.sqrt(norm_cur) * math.sqrt(norm_hist))


def _r_score_cosine(cur_r: dict, hist_r: dict, r_weights: dict) -> float:
    """
    Weighted cosine similarity on R1-R8 continuous scores.
    R scores are already normalized [0,100]; cosine handles relative alignment.
    """
    import math
    dot = norm_cur = norm_hist = 0.0
    for k, w in r_weights.items():
        c = cur_r.get(k, 0.0) * w
        h = hist_r.get(k, 0.0) * w
        dot       += c * h
        norm_cur  += c * c
        norm_hist += h * h
    if norm_cur <= 0 or norm_hist <= 0:
        return 0.0
    return dot / (math.sqrt(norm_cur) * math.sqrt(norm_hist))


def _fetch_historical_analogs(ticker: str, feat: dict) -> dict:
    """
    Search egx_research.db for historical signals with similar behavioral profiles.

    Similarity vector = blended score of two components:
      1. R-score cosine  (R1-R8 weighted by r_score_weights in config)  — 70% blend
      2. Behavioral cosine (sv_hit, hvn_hit, sweep_detected, rsi_div,
                           macd_div, htf_hh, htf_hl weighted by
                           behavioral_feature_weights in config)          — 30% blend

    Outcome metric: mfe_40d and mae_40d from bottom_quality table.
    avg_holding_days: derived from days_to_peak in bottom_quality.
    Returns stats dict. Never uses future data.
    """
    import math

    db_path = BASE / "egx_research.db"
    if not db_path.exists():
        return {"cases": 0, "similarity": 0.0, "avg_mfe40": 0.0,
                "avg_drawdown": 0.0, "avg_holding_days": 0.0, "confidence": "LOW"}

    hist_cfg = _cfg().get("historical_comparison", {})

    r_weights_cfg = hist_cfg.get("r_score_weights", {})
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

    b_weights_cfg = hist_cfg.get("behavioral_feature_weights", {})
    b_weights = {
        "sweep_detected": b_weights_cfg.get("sweep_detected", 0.20),
        "sv_hit":         b_weights_cfg.get("sv_hit",         0.20),
        "hvn_hit":        b_weights_cfg.get("hvn_hit",        0.15),
        "rsi_div":        b_weights_cfg.get("rsi_div",        0.10),
        "macd_div":       b_weights_cfg.get("macd_div",       0.10),
        "htf_hh":         b_weights_cfg.get("htf_hh",         0.125),
        "htf_hl":         b_weights_cfg.get("htf_hl",         0.125),
    }

    r_blend = float(hist_cfg.get("r_score_blend", 0.70))
    b_blend = float(hist_cfg.get("behavioral_blend", 0.30))

    # Build complete R-score vector.
    # analyze() in main.py only puts r1 as a named key; r2-r8 are in the
    # `rows` list. _extract_r_scores_from_feat() recovers all 8 values.
    _extracted = _extract_r_scores_from_feat(feat)
    cur_r = {
        "r1": float(_extracted.get("r1_price") or feat.get("r1_price") or feat.get("r1") or 0),
        "r2": float(_extracted.get("r2_ob")       or feat.get("r2_ob")       or feat.get("r2") or 0),
        "r3": float(_extracted.get("r3_liquidity") or feat.get("r3_liquidity") or feat.get("r3") or 0),
        "r4": float(_extracted.get("r4_htf")       or feat.get("r4_htf")       or feat.get("r4") or 0),
        "r5": float(_extracted.get("r5_avwap")     or feat.get("r5_avwap")     or feat.get("r5") or 0),
        "r6": float(_extracted.get("r6_macd")      or feat.get("r6_macd")      or feat.get("r6") or 0),
        "r7": float(_extracted.get("r7_div")       or feat.get("r7_div")       or feat.get("r7") or 0),
        "r8": float(_extracted.get("r8_demand")    or feat.get("r8_demand")    or feat.get("r8") or 0),
    }

    cur_b = {
        "sweep_detected": feat.get("sweep_detected", False),
        "sv_hit":         feat.get("sv_hit", False),
        "hvn_hit":        feat.get("hvn_hit", False),
        "rsi_div":        feat.get("rsi_div", False),
        "macd_div":       feat.get("macd_div", False),
        "htf_hh":         feat.get("htf_hh", False),
        "htf_hl":         feat.get("htf_hl", False),
    }

    min_sim  = float(hist_cfg.get("min_similarity", 0.50))
    min_n    = int(hist_cfg.get("min_sample_size", 3))
    max_days = int(hist_cfg.get("max_lookback_days", 730))

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cutoff = (datetime.now() - timedelta(days=max_days)).date().isoformat()
        rows = conn.execute(
            """
            SELECT s.r1_price, s.r2_ob, s.r3_liquidity, s.r4_htf,
                   s.r5_avwap, s.r6_macd, s.r7_div, s.r8_demand,
                   s.sv_hit, s.hvn_hit, s.sweep_detected,
                   s.rsi_div, s.macd_div, s.htf_hh, s.htf_hl,
                   b.mfe_40d, b.mae_40d, b.days_to_peak
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

    matched_mfe:  list[float] = []
    matched_dd:   list[float] = []
    matched_days: list[float] = []
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
        hist_b = {
            "sweep_detected": bool(row["sweep_detected"]),
            "sv_hit":         bool(row["sv_hit"]),
            "hvn_hit":        bool(row["hvn_hit"]),
            "rsi_div":        bool(row["rsi_div"]),
            "macd_div":       bool(row["macd_div"]),
            "htf_hh":         bool(row["htf_hh"]),
            "htf_hl":         bool(row["htf_hl"]),
        }

        r_sim = _r_score_cosine(cur_r, hist_r, r_weights)
        b_sim = _behavioral_cosine(cur_b, hist_b, b_weights)
        sim   = r_blend * r_sim + b_blend * b_sim

        if sim < min_sim:
            continue

        similarity_sum += sim
        mfe = float(row["mfe_40d"] or 0)
        mae = float(row["mae_40d"] or 0)
        dtp = row["days_to_peak"]
        matched_mfe.append(mfe)
        matched_dd.append(mae)
        if dtp is not None:
            matched_days.append(float(dtp))

    n = len(matched_mfe)
    if n < min_n:
        return {"cases": 0, "similarity": 0.0, "avg_mfe40": 0.0,
                "avg_drawdown": 0.0, "avg_holding_days": 0.0, "confidence": "LOW"}

    avg_sim  = similarity_sum / n
    avg_mfe  = sum(matched_mfe) / n * 100  # fraction → %
    avg_dd   = abs(sum(matched_dd) / n * 100) if matched_dd else 0.0
    avg_days = sum(matched_days) / len(matched_days) if matched_days else 0.0

    if n >= 10 and avg_sim >= 0.75:
        hist_conf = "HIGH"
    elif n >= 5 and avg_sim >= 0.60:
        hist_conf = "MEDIUM"
    else:
        hist_conf = "LOW"

    return {
        "cases":            n,
        "similarity":       round(avg_sim, 4),
        "avg_mfe40":        round(avg_mfe, 1),
        "avg_drawdown":     round(avg_dd, 1),
        "avg_holding_days": round(avg_days, 1),
        "confidence":       hist_conf,
    }


# ── Explanation Templates ──────────────────────────────────────────────────────

_PHASE_INTRO: dict[str, str] = {
    "Capitulation":        "Early-stage capitulation pattern detected.",
    "Late Capitulation":   "Late-stage capitulation pattern detected.",
    "Silent Accumulation": "Silent accumulation pattern identified.",
    "Accumulation":        "Active accumulation phase confirmed.",
    "Confidence Building": "Confidence-building phase in progress.",
    "Early Markup":        "Early markup phase initiated.",
    "Markup":              "Markup phase in progress.",
    # "Fear" replaces causal psychological label ("fear-driven") with observable state.
    "Fear":                "Price in discount zone — demand confirmation pending.",
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
    # LOW: a single or minimal signal is present; "partially aligns" overstates the inference.
    "LOW":    "Behavioral evidence is preliminary — additional confirmation recommended.",
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
                k: v for k, v in _extract_r_scores_from_feat(feat).items()
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

        # Always store the real explanation — renderers gate on confidence vs display_threshold.
        # Overwriting with the unavailable sentinel here would corrupt stored records when
        # the threshold changes in config (stale DB records could never render correct text).

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

def render_historical_context_html(snap: Optional[dict], theme: str = "dark") -> str:
    """
    Render a compact Historical Context block when behavioral confidence is
    below the display threshold but historical similarity is still meaningful.

    This block is strictly informational — no behavioral phase, no conclusions.
    Shown only when: historical_cases >= min_cases AND similarity >= min_similarity.
    """
    if not snap:
        return ""
    hist_n   = int(snap.get("historical_cases", 0))
    sim      = float(snap.get("similarity_score", 0.0))
    avg_mfe  = float(snap.get("avg_mfe40", 0.0))
    avg_dd   = float(snap.get("avg_drawdown", 0.0))
    avg_days = float(snap.get("avg_holding_days", 0.0))

    ctx_cfg  = _cfg().get("historical_context", {})
    min_n    = int(ctx_cfg.get("min_cases", 3))
    min_sim  = float(ctx_cfg.get("min_similarity", 0.60))

    if hist_n < min_n or sim < min_sim:
        return ""

    if theme == "dark":
        border = "#252645"
        bg     = "#0e0f28"
        title  = "#6b6f88"
        fg     = "#9095b0"
        val_c  = "#c0c4d8"
    else:
        border = "#d8dde8"
        bg     = "#f8fafd"
        title  = "#999999"
        fg     = "#666666"
        val_c  = "#333333"

    sim_pct = int(round(sim * 100))
    days_s  = f" · Avg hold: {avg_days:.0f}d" if avg_days > 0 else ""

    return (
        f'<div style="background:{bg};border:1px solid {border};border-radius:6px;'
        f'padding:8px 12px;margin-top:8px;">'
        f'<div style="font-size:9px;font-weight:700;text-transform:uppercase;'
        f'letter-spacing:0.6px;color:{title};margin-bottom:4px;">📊 Historical Context</div>'
        f'<div style="font-size:11px;color:{fg};line-height:1.5;">'
        f'<strong style="color:{val_c};">{hist_n}</strong> comparable constitutional signals '
        f'({sim_pct}% structural similarity) &nbsp;·&nbsp; '
        f'Avg MFE40: <strong style="color:{val_c};">{avg_mfe:+.0f}%</strong> &nbsp;·&nbsp; '
        f'Avg drawdown: <strong style="color:{val_c};">{avg_dd:.0f}%</strong>'
        f'{days_s}'
        f'</div>'
        f'</div>'
    )


def _render_phase_fallback_html(snap: dict, theme: str) -> str:
    """
    Mandatory fallback block rendered when neither behavioral confidence nor
    historical similarity meets their display thresholds.

    Contract: always returns non-empty HTML for a non-None snap.
    Renders phase name + accumulating data notice so consumers never receive "".
    """
    phase = snap.get("phase") or "Neutral"
    if theme == "dark":
        border = "#252645"; bg = "#0d0e26"; title = "#5a5e78"; fg = "#7a7e98"
    else:
        border = "#e0e5ef"; bg = "#f8fafd"; title = "#aaaaaa"; fg = "#888888"
    return (
        f'<div style="background:{bg};border:1px solid {border};border-radius:6px;'
        f'padding:8px 12px;margin-top:8px;">'
        f'<div style="font-size:9px;font-weight:700;text-transform:uppercase;'
        f'letter-spacing:0.6px;color:{title};margin-bottom:4px;">🧠 Behavior Phase</div>'
        f'<div style="font-size:11px;color:{fg};">'
        f'{phase} — Behavioral data accumulating for this signal.</div>'
        f'</div>'
    )


def render_behavior_insight_html(snap: Optional[dict], theme: str = "dark") -> str:
    """
    Render a self-contained Behavior Insight HTML block.
    theme='dark'  → dashboard color scheme
    theme='light' → email color scheme

    Contract: returns empty string ONLY when snap is None.
    For any valid (non-None) snap, always returns non-empty HTML.
    """
    if not snap:
        return ""

    # Gate on current config threshold — not the stored explanation sentinel.
    # Records stored under a different threshold may have a stale explanation string;
    # re-evaluating here makes the renderer config-threshold-aware on every render.
    confidence = float(snap.get("confidence", 0.0))
    if confidence < _conf_threshold():
        hist = render_historical_context_html(snap, theme=theme)
        return hist if hist else _render_phase_fallback_html(snap, theme)

    explanation = snap.get("explanation", "")
    if not explanation or explanation == _UNAVAILABLE_EXPLANATION:
        hist = render_historical_context_html(snap, theme=theme)
        return hist if hist else _render_phase_fallback_html(snap, theme)

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
    Falls back to compact Historical Context line when confidence is below threshold
    but historical data is meaningful (cases ≥ min and similarity ≥ 0.60).
    Final fallback: phase-only line so consumers never receive empty string.

    Contract: returns empty string ONLY when snap is None.
    For any valid (non-None) snap, always returns non-empty text.
    """
    if not snap:
        return ""
    # Gate on current config threshold before using stored explanation text.
    confidence = float(snap.get("confidence", 0.0))
    if confidence >= _conf_threshold():
        compact = snap.get("explanation_compact", "")
        if compact and compact != _UNAVAILABLE_COMPACT:
            return f"🧠 *Behavior*\n{compact}"

    # Fallback: compact historical context
    ctx_cfg = _cfg().get("historical_context", {})
    hist_n  = int(snap.get("historical_cases", 0))
    sim     = float(snap.get("similarity_score", 0.0))
    avg_mfe = float(snap.get("avg_mfe40", 0.0))
    min_n   = int(ctx_cfg.get("min_cases", 3))
    min_sim = float(ctx_cfg.get("min_similarity", 0.60))
    if hist_n >= min_n and sim >= min_sim:
        sim_pct = int(round(sim * 100))
        return f"📊 *Historical* ({hist_n} signals, {sim_pct}% similarity · MFE40 {avg_mfe:+.0f}%)"

    # Final fallback — phase-only line. Contract: never return "" for valid snap.
    phase = snap.get("phase") or "Neutral"
    return f"🧠 *Behavior Phase*: {phase}"
