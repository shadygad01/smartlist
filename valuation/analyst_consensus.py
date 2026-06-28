"""
valuation.analyst_consensus — Aggregate analyst consensus from multiple sources.

Sources (Layer 3 priority):
  yfinance_mean  — yfinance consensus target (primary)
  yfinance_low   — yfinance low target
  yfinance_high  — yfinance high target
  mubasher       — Mubasher Finance (future hook)
  alpha_spread   — AlphaSpread (future hook)
  market_screener — MarketScreener (future hook)

Each source stored independently in analyst_consensus table.
Never averaged before storing (per data architecture spec).
Never called during scanner execution.
"""
from __future__ import annotations
import sqlite3


def compute_consensus_summary(
    conn: sqlite3.Connection, ticker: str
) -> dict | None:
    """Return aggregated consensus summary for a ticker.

    Returns dict with: mean_target, low_target, high_target, source_count, recommendation.
    """
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM analyst_consensus WHERE ticker=? ORDER BY date DESC",
        (ticker,),
    ).fetchall()

    if not rows:
        return None

    rows = [dict(r) for r in rows]

    # Deduplicate by source (take most recent per source)
    by_source: dict[str, dict] = {}
    for r in rows:
        src = r.get("source", "unknown")
        if src not in by_source:
            by_source[src] = r

    targets = [v["target_price"] for v in by_source.values() if v.get("target_price")]
    if not targets:
        return None

    recs = [v.get("recommendation", "") for v in by_source.values() if v.get("recommendation")]
    rec_agg = _aggregate_recs(recs)

    return {
        "mean_target":   round(sum(targets) / len(targets), 2),
        "low_target":    round(min(targets), 2),
        "high_target":   round(max(targets), 2),
        "source_count":  len(targets),
        "recommendation": rec_agg,
    }


def _aggregate_recs(recs: list[str]) -> str:
    """Aggregate recommendation strings to a single consensus label."""
    if not recs:
        return ""
    score = 0.0
    mapping = {
        "strong_buy": 2, "buy": 1, "outperform": 1,
        "hold": 0, "neutral": 0,
        "underperform": -1, "sell": -1, "strong_sell": -2,
    }
    for r in recs:
        score += mapping.get((r or "").lower().replace(" ", "_"), 0)
    avg = score / len(recs)
    if avg >= 1.5:  return "Strong Buy"
    if avg >= 0.5:  return "Buy"
    if avg >= -0.5: return "Hold"
    if avg >= -1.5: return "Sell"
    return "Strong Sell"
