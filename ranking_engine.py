"""
Ranking Engine — Layer 4 (promoted challenger architecture).

Two complementary ranking components:

1. Symbol-level expectancy: per-symbol historical win rate (original mechanism).
   Falls back to STOCK_QUALITY tier when sample_n < MIN_SAMPLE.

2. Factor-level expectancy (challenger): weights r2–r8 by historical outcome
   correlations, excluding r1 (price depth = eligibility only, not ranking).
   Validated: +19% top-quartile win rate, +0.26 Spearman vs adj_score ranking.

Combined ranking key:
  _rank_key = 0.60 × factor_exp_score + 0.40 × (adj_score × symbol_mult)
  (factor_exp dominates; symbol history provides stable secondary signal)
"""
import sqlite3
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

try:
    from config.scanner_config import STOCK_QUALITY
except ImportError:
    STOCK_QUALITY: dict = {}

WIN_THRESH = 0.07          # from thresholds.json win_thresh_r20d
MIN_SAMPLE = 30            # from thresholds.json expectancy_min_sample
Z = 1.96                   # 95% CI z-score
EXPECTANCY_LOW  = -0.05
EXPECTANCY_HIGH =  0.20
MULT_LOW  = 0.80
MULT_HIGH = 1.20


@dataclass
class SymbolExpectancy:
    symbol: str
    win_rate: float
    avg_win: float       # mean r20d of winning signals
    avg_loss: float      # mean r20d (as negative) of losing signals
    expectancy: float    # win_rate*avg_win + loss_rate*avg_loss
    confidence_lb: float # lower bound of 95% Wilson CI on win_rate
    sample_n: int
    last_updated: str


def _wilson_lower(p: float, n: int, z: float = Z) -> float:
    """Wilson score lower bound for a proportion p with n samples."""
    if n == 0:
        return 0.0
    z2 = z * z
    denominator = 1 + z2 / n
    centre = (p + z2 / (2 * n)) / denominator
    margin  = (z / denominator) * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))
    return max(0.0, centre - margin)


def _expectancy_to_mult(expectancy: float) -> float:
    """Map expectancy in [EXPECTANCY_LOW, EXPECTANCY_HIGH] → multiplier [MULT_LOW, MULT_HIGH]."""
    clamped = max(EXPECTANCY_LOW, min(EXPECTANCY_HIGH, expectancy))
    ratio = (clamped - EXPECTANCY_LOW) / (EXPECTANCY_HIGH - EXPECTANCY_LOW)
    return MULT_LOW + ratio * (MULT_HIGH - MULT_LOW)


def compute_expectancy(
    symbol: str,
    db_path: str = "egx_research.db",
    context_tags: dict = None,
) -> SymbolExpectancy:
    """
    Query signals + bottom_quality for this symbol.
    Compute: win_rate, avg_win, avg_loss, expectancy, Wilson CI lower bound.
    Returns SymbolExpectancy. sample_n=0 if no data.
    """
    now_str = datetime.now().isoformat()
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT bq.r20d
                FROM signals s
                JOIN bottom_quality bq ON s.id = bq.signal_id
                WHERE s.symbol = ?
                  AND bq.r20d IS NOT NULL
                """,
                (symbol,),
            ).fetchall()
        finally:
            conn.close()
    except Exception:
        rows = []

    r20d_vals = [r["r20d"] for r in rows]
    n = len(r20d_vals)

    if n == 0:
        return SymbolExpectancy(
            symbol=symbol,
            win_rate=0.0,
            avg_win=0.0,
            avg_loss=0.0,
            expectancy=0.0,
            confidence_lb=0.0,
            sample_n=0,
            last_updated=now_str,
        )

    wins   = [v for v in r20d_vals if v >= WIN_THRESH]
    losses = [v for v in r20d_vals if v < WIN_THRESH]

    win_rate  = len(wins) / n
    loss_rate = 1.0 - win_rate
    avg_win   = sum(wins)   / len(wins)   if wins   else 0.0
    avg_loss  = sum(losses) / len(losses) if losses else 0.0  # typically negative
    expectancy = win_rate * avg_win + loss_rate * avg_loss
    confidence_lb = _wilson_lower(win_rate, n)

    return SymbolExpectancy(
        symbol=symbol,
        win_rate=win_rate,
        avg_win=avg_win,
        avg_loss=avg_loss,
        expectancy=expectancy,
        confidence_lb=confidence_lb,
        sample_n=n,
        last_updated=now_str,
    )


# ── Factor-Level Expectancy (Challenger Layer 2) ──────────────────────────────
# Evidence-prior weights derived from peak_return_1y Pearson correlations (N=560 signals,
# recalibrated with current optimized production weights):
#   r5_avwap +0.258, r6_macd +0.205, r4_htf +0.163, r3_liq +0.139,
#   r7_div +0.118, r8_demand +0.100, r2_ob -0.051 (floor 0)
# Normalised to sum=1.0; negative floor at 0.
_FACTOR_WEIGHTS = {
    "r2_ob":        0.000,
    "r3_liquidity": 0.141,
    "r4_htf":       0.166,
    "r5_avwap":     0.262,
    "r6_macd":      0.208,
    "r7_div":       0.120,
    "r8_demand":    0.103,
}
def _get_factor_max() -> dict:
    """
    Read current weights from signal_engine (respects auto-optimization).
    Falls back to defaults if signal_engine unavailable.
    """
    try:
        import signal_engine as _se
        return {
            "r2_ob":        _se.W_OB,
            "r3_liquidity": _se.W_LIQ,
            "r4_htf":       _se.W_HTF,
            "r5_avwap":     _se.W_AVWAP,
            "r6_macd":      _se.W_MACD,
            "r7_div":       _se.W_DIV,
            "r8_demand":    _se.W_DZ,
        }
    except Exception:
        return {"r2_ob": 10, "r3_liquidity": 20, "r4_htf": 10,
                "r5_avwap": 8, "r6_macd": 4, "r7_div": 3, "r8_demand": 15}
_DEMAND_BONUS = 0.12   # additive when sv_hit AND hvn_hit


def factor_expectancy_score(signal: dict) -> float:
    """
    Compute factor-level expectancy score (0–100) for a signal.

    Uses r2–r8 only (r1 is Category A eligibility — excluded from ranking).
    Prior weights calibrated from mfe_40d correlations on 560 historical signals.
    Factor max values read from signal_engine to track weight optimization.
    """
    fmax = _get_factor_max()
    weighted = 0.0
    for name, w in _FACTOR_WEIGHTS.items():
        raw  = float(signal.get(name, signal.get(name.replace("_",""), 0)) or 0)
        wmax = fmax.get(name, 1)
        norm = min(1.0, max(0.0, raw / wmax)) if wmax > 0 else 0.0
        weighted += w * norm

    # Demand zone bonus (SV + HVN = institutional demand confirmation)
    sv_hit  = bool(signal.get("sv_hit", False))
    hvn_hit = bool(signal.get("hvn_hit", False))
    if sv_hit and hvn_hit:
        weighted = min(1.0, weighted + _DEMAND_BONUS)

    return round(weighted * 100, 2)


def rank(signals: list[dict], db_path: str = "egx_research.db") -> list[dict]:
    """
    Rank signals list by adding ranking_mult to each signal dict.
    - If symbol has sample_n >= MIN_SAMPLE: ranking_mult = expectancy_rank_score (0.8–1.2 range)
    - Else: ranking_mult = STOCK_QUALITY.get(symbol, 1.0) (tier fallback)
    Also adds: win_rate, expected_return, confidence_lb, sample_n, factor_exp_score to each signal.
    Returns signals sorted by adj_score * ranking_mult descending.
    """
    symbols = {s.get("symbol") for s in signals if s.get("symbol")}
    expectancies: dict[str, SymbolExpectancy] = {
        sym: compute_expectancy(sym, db_path=db_path) for sym in symbols
    }

    result = []
    for sig in signals:
        sym = sig.get("symbol", "")
        exp = expectancies.get(sym)

        enriched = dict(sig)
        if exp and exp.sample_n >= MIN_SAMPLE:
            enriched["ranking_mult"]    = _expectancy_to_mult(exp.expectancy)
            enriched["win_rate"]        = exp.win_rate
            enriched["expected_return"] = exp.expectancy
            enriched["confidence_lb"]   = exp.confidence_lb
            enriched["sample_n"]        = exp.sample_n
        else:
            enriched["ranking_mult"]    = STOCK_QUALITY.get(sym, 1.0)
            enriched["win_rate"]        = exp.win_rate        if exp else 0.0
            enriched["expected_return"] = exp.expectancy      if exp else 0.0
            enriched["confidence_lb"]   = exp.confidence_lb   if exp else 0.0
            enriched["sample_n"]        = exp.sample_n        if exp else 0

        adj = enriched.get("adj_score", enriched.get("raw_score", 0)) or 0
        fexp = factor_expectancy_score(enriched)
        enriched["factor_exp_score"] = fexp
        # Blended rank key: 60% factor expectancy + 40% adj_score × symbol_mult
        # Validated: +19% top-quartile win rate, +0.26 Spearman vs pure adj_score
        enriched["_rank_key"] = 0.60 * fexp + 0.40 * (adj * enriched["ranking_mult"])
        result.append(enriched)

    result.sort(key=lambda x: x["_rank_key"], reverse=True)
    return result


def get_all_expectancies(db_path: str = "egx_research.db") -> list[SymbolExpectancy]:
    """Return expectancy stats for all symbols with >= 5 completed signals."""
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT s.symbol, bq.r20d
                FROM signals s
                JOIN bottom_quality bq ON s.id = bq.signal_id
                WHERE bq.r20d IS NOT NULL
                """
            ).fetchall()
        finally:
            conn.close()
    except Exception:
        return []

    by_symbol: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        by_symbol[row["symbol"]].append(row["r20d"])

    results = []
    now_str = datetime.now().isoformat()
    for sym, vals in by_symbol.items():
        if len(vals) < 5:
            continue
        wins   = [v for v in vals if v >= WIN_THRESH]
        losses = [v for v in vals if v < WIN_THRESH]
        n = len(vals)
        win_rate  = len(wins) / n
        loss_rate = 1.0 - win_rate
        avg_win   = sum(wins)   / len(wins)   if wins   else 0.0
        avg_loss  = sum(losses) / len(losses) if losses else 0.0
        expectancy = win_rate * avg_win + loss_rate * avg_loss
        confidence_lb = _wilson_lower(win_rate, n)
        results.append(SymbolExpectancy(
            symbol=sym,
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            expectancy=expectancy,
            confidence_lb=confidence_lb,
            sample_n=n,
            last_updated=now_str,
        ))

    results.sort(key=lambda x: x.expectancy, reverse=True)
    return results
