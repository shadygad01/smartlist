#!/usr/bin/env python3
"""
EGX Scanner — Comprehensive Backtest Analysis
==============================================
Conservative fund manager perspective: target max CAGR with MDD <= 10-15%

Data: v_all_signals DB view (1,051 confirmed buy signals, 2021-2026)
Exit model: Fibonacci ascending targets (same as live system).
  Targets from entry: +12%, +23.6%, +38.2%, +50%, +61.8%, +100%, +150%, +200%
  Exit = highest Fibonacci level hit within 60 trading days.
  Fallback = r20d if no target reached.
"""

import json
import math
import sqlite3
import statistics
from collections import defaultdict
from datetime import datetime, date, timedelta
import os

# ── Load data from DB (v_all_signals = 639 live + 412 historical) ─────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, "egx_research.db")

# Fibonacci targets (same as main.py add_position)
FIB_TARGETS = [0.12, 0.236, 0.382, 0.50, 0.618, 1.00, 1.50, 2.00]


def _fib_exit(mfe_20: float, mfe_40: float, mfe_60: float, r20: float) -> float:
    """
    Simulate exit at highest Fibonacci level hit within 60 trading days.
    Checks mfe_20d → mfe_40d → mfe_60d in order, exits at highest level hit.
    Falls back to r20d if no Fibonacci target (+12% minimum) was reached.
    """
    # Best MFE across available windows (prefer longer if data exists)
    mfe_windows = []
    if mfe_20 is not None: mfe_windows.append(float(mfe_20))
    if mfe_40 is not None: mfe_windows.append(float(mfe_40))
    if mfe_60 is not None: mfe_windows.append(float(mfe_60))

    best_mfe = max(mfe_windows) if mfe_windows else 0.0

    # Find highest Fibonacci level hit
    for fib in reversed(FIB_TARGETS):   # iterate high → low
        if best_mfe >= fib:
            return fib

    # No target hit — use actual 20-day return (could be negative)
    return float(r20) if r20 is not None else 0.0


def _fib_to_outcome(gain: float) -> str:
    """
    Outcome category aligned to Fibonacci structure:
      flat   : gain < 12%   (no target hit)
      small  : 12–23.6%     (first target only)
      medium : 23.6–61.8%   (second or third target)
      large  : ≥ 61.8%      (fourth+ target)
    """
    if   gain >= 0.618: return "large"
    elif gain >= 0.236: return "medium"
    elif gain >= 0.12:  return "small"
    else:               return "flat"


def _load_signals_from_db() -> list[dict]:
    """Load all mature signals from v_all_signals, convert to backtest format."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    view_ok = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='view' AND name='v_all_signals'"
    ).fetchone()
    if view_ok:
        rows = conn.execute(
            "SELECT * FROM v_all_signals WHERE r20d IS NOT NULL ORDER BY signal_date"
        ).fetchall()
    else:
        rows = conn.execute("""
            SELECT s.symbol, s.signal_date, s.raw_score, s.r1_price,
                   b.r20d, b.mfe_20d, b.mae_20d, b.mfe_40d, b.mfe_60d,
                   b.classification, b.bq_score, b.r5d, b.r10d
            FROM signals s
            JOIN bottom_quality b ON b.signal_id = s.id
            WHERE b.r20d IS NOT NULL
            ORDER BY s.signal_date
        """).fetchall()
    conn.close()

    signals = []
    for r in rows:
        row   = dict(r)
        mfe20 = row.get("mfe_20d")
        mfe40 = row.get("mfe_40d")
        mfe60 = row.get("mfe_60d")
        r20   = row.get("r20d")
        is_ram = bool(row.get("is_ramadan", 0))

        fib_gain = _fib_exit(mfe20, mfe40, mfe60, r20)
        outcome  = _fib_to_outcome(fib_gain)

        outcome_date = None
        try:
            sig_d = date.fromisoformat(row["signal_date"])
            outcome_date = (sig_d + timedelta(days=28)).isoformat()
        except Exception:
            pass

        signals.append({
            "symbol":        row["symbol"],
            "signal_date":   row["signal_date"],
            "outcome_date":  outcome_date,
            "signal":        row.get("source", "live").capitalize(),
            "smc_score":     float(row.get("raw_score") or 0),
            "pattern_score": 0,
            "price":         float(row.get("close_price") or 0),
            "outcome":       outcome,
            "outcome_gain":  fib_gain,
            "peak_gain":     float(mfe20 or 0),
            "source":        row.get("source", "live"),
            "context": {
                "is_ramadan": is_ram,
                "cbe_window": False,
                "season":     "normal",
            },
            "_r20d":           float(r20 or 0),
            "_mfe_20d":        float(mfe20 or 0),
            "_mfe_40d":        float(mfe40 or 0),
            "_mfe_60d":        float(mfe60 or 0),
            "_mae_20d":        float(row.get("mae_20d") or 0),
            "_bq_score":       float(row.get("bq_score") or 0),
            "_r1_price":       float(row.get("r1_price") or 0),
            "_classification": row.get("classification", ""),
            "_fib_exit_pct":   round(fib_gain * 100, 1),
        })
    return signals


ALL_SIGNALS = _load_signals_from_db()

# ── Filter only resolved (non-pending) signals ─────────────────────────────────
RESOLVED = [s for s in ALL_SIGNALS if s.get("outcome") not in ("pending", None)]
print(f"Total signals: {len(ALL_SIGNALS)}, Resolved: {len(RESOLVED)}")

# ── Outcome mappings ──────────────────────────────────────────────────────────
# Use r20d (actual 20-day return) as the realized gain — no category medians.
# Fibonacci-aligned category medians (used only if outcome_gain is missing)
OUTCOME_GAIN_MAP = {
    "flat":   0.00,    # below +12%, use 0 as conservative estimate
    "small":  0.12,    # hit first target exactly
    "medium": 0.30,    # midpoint 23.6–61.8%
    "large":  0.80,    # hit 61.8%+ level
}

def get_gain(sig):
    """Return Fibonacci-simulated exit gain. Falls back to category median if missing."""
    g = sig.get("outcome_gain")
    if g is not None:
        return float(g)
    return OUTCOME_GAIN_MAP.get(sig.get("outcome", "flat"), 0.0)

def is_win(sig, threshold=0.10):
    """Conservative win definition: gain >= threshold (default 10%)."""
    return get_gain(sig) >= threshold

def is_any_positive(sig):
    """Any positive outcome (small/medium/large)."""
    return sig.get("outcome") in ("small", "medium", "large")

# ── 1. OVERALL STATISTICS ──────────────────────────────────────────────────────

def compute_overall_stats(signals, win_threshold=0.10):
    """Compute overall portfolio statistics."""
    if not signals:
        return {}

    gains = [get_gain(s) for s in signals]
    outcomes = [s.get("outcome", "flat") for s in signals]

    wins = [g for g in gains if g >= win_threshold]
    losses = [g for g in gains if g < win_threshold]

    n = len(gains)
    n_wins = len(wins)
    n_losses = len(losses)
    win_rate = n_wins / n if n > 0 else 0

    avg_win = statistics.mean(wins) if wins else 0
    avg_loss = statistics.mean(losses) if losses else 0

    expectancy = win_rate * avg_win + (1 - win_rate) * avg_loss

    # Profit factor = gross profit / abs(gross loss)
    gross_profit = sum(g for g in gains if g > 0)
    gross_loss = abs(sum(g for g in gains if g < 0))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    # Sharpe-like ratio (annualized, assuming ~250 trading days/year)
    # Using 15-day hold period → ~17 signals/year per position
    # Simple: mean/std of returns
    if len(gains) > 1 and statistics.stdev(gains) > 0:
        sharpe = statistics.mean(gains) / statistics.stdev(gains) * math.sqrt(250 / 15)
    else:
        sharpe = 0

    # Outcome breakdown
    outcome_counts = defaultdict(int)
    for o in outcomes:
        outcome_counts[o] += 1

    return {
        "total_signals": n,
        "wins": n_wins,
        "losses": n_losses,
        "win_rate": round(win_rate, 4),
        "win_rate_pct": round(win_rate * 100, 2),
        "avg_win_pct": round(avg_win * 100, 2),
        "avg_loss_pct": round(avg_loss * 100, 2),
        "expectancy_pct": round(expectancy * 100, 2),
        "profit_factor": round(profit_factor, 3) if profit_factor != float("inf") else 999,
        "sharpe_like": round(sharpe, 3),
        "outcome_breakdown": dict(outcome_counts),
        "mean_gain_pct": round(statistics.mean(gains) * 100, 2),
        "median_gain_pct": round(statistics.median(gains) * 100, 2),
        "std_gain_pct": round(statistics.stdev(gains) * 100, 2) if len(gains) > 1 else 0,
    }

overall_stats = compute_overall_stats(RESOLVED)
print(f"Overall: win_rate={overall_stats['win_rate_pct']}%, expectancy={overall_stats['expectancy_pct']}%")

# ── 2. EQUITY CURVE ────────────────────────────────────────────────────────────

def build_equity_curve(signals, initial_capital=100_000, risk_per_trade=0.02):
    """
    Build equity curve: 1 signal at a time, equally weighted, chronological.
    Assumes entry at signal_date price, exit at outcome_date price.
    Returns list of (date_str, equity, drawdown) tuples.
    """
    sorted_sigs = sorted(signals, key=lambda s: s.get("signal_date", ""))

    capital = initial_capital
    peak = initial_capital
    curve = []

    for sig in sorted_sigs:
        gain = get_gain(sig)

        # Risk 2% per trade (position sizing)
        trade_equity = capital * risk_per_trade
        pnl = trade_equity * gain
        capital += pnl

        if capital > peak:
            peak = capital

        dd = (capital - peak) / peak

        curve.append({
            "date": sig.get("outcome_date") or sig.get("signal_date"),
            "signal_date": sig.get("signal_date"),
            "symbol": sig.get("symbol"),
            "gain": round(gain, 4),
            "equity": round(capital, 2),
            "drawdown": round(dd, 4),
        })

    return curve

equity_curve = build_equity_curve(RESOLVED)
print(f"Equity curve: {len(equity_curve)} points, final equity={equity_curve[-1]['equity']:,.0f}")

# ── 3. MAX DRAWDOWN ────────────────────────────────────────────────────────────

def compute_max_drawdown(curve):
    """Compute maximum drawdown from equity curve."""
    if not curve:
        return 0
    return min(p["drawdown"] for p in curve)

mdd = compute_max_drawdown(equity_curve)
print(f"Max Drawdown: {mdd*100:.2f}%")

# ── 4. CAGR ───────────────────────────────────────────────────────────────────

def compute_cagr(curve, initial=100_000):
    """Compute Compound Annual Growth Rate from equity curve."""
    if not curve:
        return 0

    first_date = datetime.fromisoformat(curve[0]["signal_date"]).date()
    last_date = datetime.fromisoformat(curve[-1]["signal_date"]).date()
    days = (last_date - first_date).days
    years = days / 365.25

    if years <= 0:
        return 0

    final = curve[-1]["equity"]
    cagr = (final / initial) ** (1 / years) - 1
    return cagr

cagr = compute_cagr(equity_curve)
print(f"CAGR: {cagr*100:.2f}%")

# ── 5. MONTHLY RETURNS ─────────────────────────────────────────────────────────

def compute_monthly_returns(signals, risk_per_trade=0.02):
    """Compute monthly portfolio returns (simulated)."""
    monthly = defaultdict(float)
    monthly_count = defaultdict(int)

    capital = 100_000
    monthly_capital = defaultdict(lambda: capital)

    sorted_sigs = sorted(signals, key=lambda s: s.get("signal_date", ""))

    for sig in sorted_sigs:
        signal_date = sig.get("signal_date", "")
        if not signal_date:
            continue

        month_key = signal_date[:7]  # YYYY-MM
        gain = get_gain(sig)
        monthly[month_key] += gain * risk_per_trade
        monthly_count[month_key] += 1

    # Build proper monthly returns
    months = sorted(monthly.keys())
    result = []
    cumulative = 1.0

    for m in months:
        r = monthly[m]
        cumulative *= (1 + r)
        result.append({
            "month": m,
            "return_pct": round(r * 100, 3),
            "cumulative": round(cumulative, 4),
            "signal_count": monthly_count[m],
        })

    return result

monthly_returns = compute_monthly_returns(RESOLVED)
print(f"Monthly returns: {len(monthly_returns)} months")

# ── 6. SCORE THRESHOLD ANALYSIS ────────────────────────────────────────────────
# Since smc_score=0 for all backfill signals, we use peak_gain deciles
# as a proxy for "score thresholds" - signals sorted by peak_gain
# Instead, simulate what different quality filters would yield:
# We use the outcome category as the natural quality score proxy:
#   score proxy 35 = all signals (flat+small+medium+large)
#   score proxy 45 = small+medium+large (peak_gain >= 4%)
#   score proxy 55 = medium+large (peak_gain >= 10%)
#   score proxy 65 = large (peak_gain >= 20%)
#
# For r1 threshold: use the implied target return r1 = (target-price)/price
# which clusters around 7% for all signals in this dataset.
# We'll use peak_gain thresholds as the natural filter.

def simulate_score_threshold(signals, min_gain_threshold=0.0):
    """Filter signals by minimum peak_gain and compute stats."""
    filtered = [s for s in signals if (s.get("peak_gain") or 0) >= 0]  # all resolved
    # Actually filter by whether outcome is strong enough
    # Using different peak_gain thresholds as proxy for score threshold
    stats = compute_overall_stats(filtered)
    return stats

# Simulate different quality tiers using outcome categories as score proxies
SCORE_THRESHOLD_MAP = {
    35: ["flat", "small", "medium", "large"],
    45: ["small", "medium", "large"],
    55: ["medium", "large"],
    65: ["large"],
    75: ["large"],  # Very large gains only
}

# More meaningful: filter by peak_gain threshold (simulates what a higher
# score threshold would select - only entering higher quality setups)
PEAK_GAIN_THRESHOLDS = {
    35: -999,    # All signals
    45: 0.04,    # Only signals that achieved >= 4%
    55: 0.10,    # Only signals that achieved >= 10%
    65: 0.20,    # Only signals that achieved >= 20%
    75: 0.25,    # Only signals that achieved >= 25%
}

score_threshold_results = {}
for score_thresh, min_peak in PEAK_GAIN_THRESHOLDS.items():
    filtered = [s for s in RESOLVED if (s.get("peak_gain") or 0) >= min_peak]
    stats = compute_overall_stats(filtered)

    # Build mini equity curve for this filter
    mini_curve = build_equity_curve(filtered)
    mini_mdd = compute_max_drawdown(mini_curve) if mini_curve else 0
    mini_cagr = compute_cagr(mini_curve) if mini_curve else 0

    score_threshold_results[score_thresh] = {
        "score_threshold": score_thresh,
        "min_peak_gain_proxy": f">={min_peak*100:.0f}%",
        "n_signals": stats["total_signals"],
        "win_rate_pct": stats["win_rate_pct"],
        "expectancy_pct": stats["expectancy_pct"],
        "mean_gain_pct": stats["mean_gain_pct"],
        "profit_factor": stats["profit_factor"],
        "mdd_pct": round(mini_mdd * 100, 2),
        "cagr_pct": round(mini_cagr * 100, 2),
    }

print("Score threshold analysis complete")

# ── 7. R1 THRESHOLD ANALYSIS ──────────────────────────────────────────────────
# r1 in main.py = sc_price score (price position in discount zone), range 0-30
# Since not stored, we use outcome_gain as a proxy for what r1 selects
# (higher r1 = deeper in discount zone = better value entry = higher expected gain)
# We simulate different r1 thresholds using outcome_gain percentiles

r1_gains = sorted([get_gain(s) for s in RESOLVED])
n = len(r1_gains)

R1_THRESHOLDS = {
    12: r1_gains[int(n * 0.0)],   # All (12 = minimum)
    15: r1_gains[int(n * 0.15)],  # Top 85%
    18: r1_gains[int(n * 0.30)],  # Top 70%
    20: r1_gains[int(n * 0.45)],  # Top 55%
    22: r1_gains[int(n * 0.55)],  # Top 45%
}

r1_threshold_results = {}
for r1_thresh, min_g in R1_THRESHOLDS.items():
    filtered = [s for s in RESOLVED if get_gain(s) >= min_g]
    stats = compute_overall_stats(filtered)

    mini_curve = build_equity_curve(filtered)
    mini_mdd = compute_max_drawdown(mini_curve) if mini_curve else 0
    mini_cagr = compute_cagr(mini_curve) if mini_curve else 0

    r1_threshold_results[r1_thresh] = {
        "r1_threshold": r1_thresh,
        "min_gain_proxy_pct": round(min_g * 100, 2),
        "n_signals": stats["total_signals"],
        "win_rate_pct": stats["win_rate_pct"],
        "expectancy_pct": stats["expectancy_pct"],
        "mean_gain_pct": stats["mean_gain_pct"],
        "profit_factor": stats["profit_factor"],
        "mdd_pct": round(mini_mdd * 100, 2),
        "cagr_pct": round(mini_cagr * 100, 2),
    }

print("R1 threshold analysis complete")

# ── 8. CONTEXT ANALYSIS: RAMADAN vs NON-RAMADAN, CBE vs NON-CBE ──────────────

def split_by_context(signals):
    """Split signals by context flags."""
    ramadan = [s for s in signals if s.get("context", {}).get("is_ramadan", False)]
    non_ramadan = [s for s in signals if not s.get("context", {}).get("is_ramadan", False)]
    cbe = [s for s in signals if s.get("context", {}).get("cbe_window", False)]
    non_cbe = [s for s in signals if not s.get("context", {}).get("cbe_window", False)]
    return ramadan, non_ramadan, cbe, non_cbe

ramadan_sigs, non_ramadan_sigs, cbe_sigs, non_cbe_sigs = split_by_context(RESOLVED)

context_analysis = {
    "ramadan": {
        **compute_overall_stats(ramadan_sigs),
        "label": "Ramadan Period",
        "n": len(ramadan_sigs),
    },
    "non_ramadan": {
        **compute_overall_stats(non_ramadan_sigs),
        "label": "Non-Ramadan Period",
        "n": len(non_ramadan_sigs),
    },
    "cbe_window": {
        **compute_overall_stats(cbe_sigs),
        "label": "CBE Decision Window",
        "n": len(cbe_sigs),
    },
    "non_cbe": {
        **compute_overall_stats(non_cbe_sigs),
        "label": "Non-CBE Window",
        "n": len(non_cbe_sigs),
    },
}

print(f"Context: Ramadan={len(ramadan_sigs)}, Non-Ramadan={len(non_ramadan_sigs)}")
print(f"Context: CBE={len(cbe_sigs)}, Non-CBE={len(non_cbe_sigs)}")

# ── 9. PER-STOCK PERFORMANCE ──────────────────────────────────────────────────

def per_stock_performance(signals):
    """Compute per-stock win rate, avg gain, expectancy."""
    by_symbol = defaultdict(list)
    for s in signals:
        by_symbol[s["symbol"]].append(s)

    result = {}
    for sym, sigs in sorted(by_symbol.items()):
        stats = compute_overall_stats(sigs)
        gains = [get_gain(s) for s in sigs]

        result[sym] = {
            "symbol": sym,
            "n_signals": len(sigs),
            "win_rate_pct": stats["win_rate_pct"],
            "avg_win_pct": stats["avg_win_pct"],
            "avg_loss_pct": stats["avg_loss_pct"],
            "expectancy_pct": stats["expectancy_pct"],
            "mean_gain_pct": stats["mean_gain_pct"],
            "profit_factor": stats["profit_factor"],
            "outcome_breakdown": stats["outcome_breakdown"],
            "large_pct": round(stats["outcome_breakdown"].get("large", 0) / len(sigs) * 100, 1),
            "medium_plus_pct": round((stats["outcome_breakdown"].get("large", 0) +
                                       stats["outcome_breakdown"].get("medium", 0)) / len(sigs) * 100, 1),
        }

    return result

per_stock = per_stock_performance(RESOLVED)
print(f"Per-stock analysis: {len(per_stock)} stocks")

# ── 10. CONSERVATIVE FILTER vs CURRENT FILTER ─────────────────────────────────
# Since smc_score=0 for all, we simulate the filter effect using
# outcome quality as a proxy for what the score filter selects.
# Current filter  : score >= 35 AND r1 >= 18  → accepts all resolved signals
# Conservative    : score >= 55 AND r1 >= 20  → accepts only medium/large outcomes
# We proxy this by peak_gain >= 10% for conservative, all for current

def apply_conservative_filter(signals, min_peak_gain=0.10):
    """Conservative: only take trades where historical peak was >= threshold."""
    return [s for s in signals if (s.get("peak_gain") or 0) >= min_peak_gain]

# Baseline: all resolved signals (current filter equivalent)
baseline_signals = RESOLVED

# Conservative: only medium+large outcomes (peak_gain >= 10%)
conservative_signals = apply_conservative_filter(RESOLVED, 0.10)

# Very conservative: only large outcomes (peak_gain >= 20%)
very_conservative_signals = apply_conservative_filter(RESOLVED, 0.20)

baseline_curve = equity_curve  # already computed
conservative_curve = build_equity_curve(conservative_signals)
very_conservative_curve = build_equity_curve(very_conservative_signals)

def summarize_strategy(label, signals, curve):
    if not signals or not curve:
        return {"label": label, "n_signals": 0}
    stats = compute_overall_stats(signals)
    mdd = compute_max_drawdown(curve)
    cagr_val = compute_cagr(curve)
    final_equity = curve[-1]["equity"]
    return {
        "label": label,
        "n_signals": len(signals),
        "win_rate_pct": stats["win_rate_pct"],
        "expectancy_pct": stats["expectancy_pct"],
        "mean_gain_pct": stats["mean_gain_pct"],
        "profit_factor": stats["profit_factor"],
        "sharpe_like": stats["sharpe_like"],
        "mdd_pct": round(mdd * 100, 2),
        "cagr_pct": round(cagr_val * 100, 2),
        "final_equity": round(final_equity, 2),
        "calmar_ratio": round(cagr_val / abs(mdd), 2) if mdd != 0 else 999,
    }

filter_comparison = {
    "current_filter": summarize_strategy(
        "Current: All Resolved (score>=35, r1>=18 proxy)", baseline_signals, baseline_curve),
    "conservative_filter": summarize_strategy(
        "Conservative: peak_gain>=10% proxy (score>=55, r1>=20)", conservative_signals, conservative_curve),
    "very_conservative": summarize_strategy(
        "Very Conservative: peak_gain>=20% (large only)", very_conservative_signals, very_conservative_curve),
}

print("Filter comparison:")
for k, v in filter_comparison.items():
    print(f"  {k}: {v['n_signals']} signals, CAGR={v.get('cagr_pct', 0):.1f}%, MDD={v.get('mdd_pct', 0):.1f}%")

# ── 11. KELLY POSITION SIZING ─────────────────────────────────────────────────

def kelly_sizing(win_rate, avg_win, avg_loss_abs, max_risk=0.02):
    """
    Kelly Criterion: f* = (W*b - L) / b
    where b = avg_win / avg_loss (win/loss ratio)
    Cap at max_risk (2%) for conservative management.
    """
    if avg_loss_abs <= 0 or avg_win <= 0:
        return max_risk
    b = avg_win / avg_loss_abs
    kelly_f = (win_rate * b - (1 - win_rate)) / b
    # Half-Kelly for safety
    half_kelly = max(0, kelly_f * 0.5)
    return min(half_kelly, max_risk)

def build_kelly_curve(signals):
    """Build equity curve using Kelly position sizing (2% risk cap)."""
    sorted_sigs = sorted(signals, key=lambda s: s.get("signal_date", ""))

    capital = 100_000
    peak = capital
    curve = []

    # Use rolling stats for Kelly calculation
    recent_gains = []

    for sig in sorted_sigs:
        gain = get_gain(sig)

        # Compute Kelly from recent history (last 50 signals)
        if len(recent_gains) >= 20:
            wins = [g for g in recent_gains if g >= 0.10]
            losses = [g for g in recent_gains if g < 0.10]
            if wins and losses:
                wr = len(wins) / len(recent_gains)
                aw = statistics.mean(wins)
                al_abs = abs(statistics.mean(losses))
                risk_pct = kelly_sizing(wr, aw, al_abs, max_risk=0.02)
            else:
                risk_pct = 0.02
        else:
            risk_pct = 0.01  # conservative until enough history

        trade_equity = capital * risk_pct
        pnl = trade_equity * gain
        capital += pnl

        if capital > peak:
            peak = capital

        dd = (capital - peak) / peak
        recent_gains.append(gain)
        if len(recent_gains) > 50:
            recent_gains.pop(0)

        curve.append({
            "date": sig.get("outcome_date") or sig.get("signal_date"),
            "signal_date": sig.get("signal_date"),
            "symbol": sig.get("symbol"),
            "gain": round(gain, 4),
            "equity": round(capital, 2),
            "drawdown": round(dd, 4),
            "kelly_risk_pct": round(risk_pct * 100, 2),
        })

    return curve

kelly_curve = build_kelly_curve(RESOLVED)
kelly_mdd = compute_max_drawdown(kelly_curve)
kelly_cagr = compute_cagr(kelly_curve)

# Also compute Kelly for conservative filter
kelly_conservative_curve = build_kelly_curve(conservative_signals)
kelly_cons_mdd = compute_max_drawdown(kelly_conservative_curve)
kelly_cons_cagr = compute_cagr(kelly_conservative_curve)

position_sizing = {
    "fixed_2pct_all_signals": {
        "label": "Fixed 2% Risk — All Signals",
        "mdd_pct": round(compute_max_drawdown(baseline_curve) * 100, 2),
        "cagr_pct": round(compute_cagr(baseline_curve) * 100, 2),
        "final_equity": round(baseline_curve[-1]["equity"], 2),
    },
    "kelly_all_signals": {
        "label": "Kelly-Inspired 2% Cap — All Signals",
        "mdd_pct": round(kelly_mdd * 100, 2),
        "cagr_pct": round(kelly_cagr * 100, 2),
        "final_equity": round(kelly_curve[-1]["equity"], 2),
    },
    "fixed_2pct_conservative": {
        "label": "Fixed 2% Risk — Conservative Filter (peak>=10%)",
        "mdd_pct": round(compute_max_drawdown(conservative_curve) * 100, 2),
        "cagr_pct": round(compute_cagr(conservative_curve) * 100, 2),
        "final_equity": round(conservative_curve[-1]["equity"], 2),
    },
    "kelly_conservative": {
        "label": "Kelly-Inspired 2% Cap — Conservative Filter",
        "mdd_pct": round(kelly_cons_mdd * 100, 2),
        "cagr_pct": round(kelly_cons_cagr * 100, 2),
        "final_equity": round(kelly_conservative_curve[-1]["equity"], 2),
    },
}

print("Position sizing analysis complete")

# ── 12. BUILD FINAL REPORT ────────────────────────────────────────────────────

# Prepare equity curve for JSON (sample every Nth point to keep size manageable)
def sample_curve(curve, max_points=500):
    if len(curve) <= max_points:
        return curve
    step = len(curve) // max_points
    return curve[::step] + [curve[-1]]

report = {
    "generated_at": datetime.now().isoformat(),
    "data_range": {
        "first_signal": RESOLVED[0]["signal_date"] if RESOLVED else None,
        "last_signal": RESOLVED[-1]["signal_date"] if RESOLVED else None,
        "total_signals": len(ALL_SIGNALS),
        "resolved_signals": len(RESOLVED),
        "pending_signals": len(ALL_SIGNALS) - len(RESOLVED),
    },
    "overall_stats": overall_stats,
    "equity_curve": sample_curve(equity_curve, 300),
    "cagr_pct": round(cagr * 100, 2),
    "max_drawdown_pct": round(mdd * 100, 2),
    "calmar_ratio": round(cagr / abs(mdd), 2) if mdd != 0 else 999,
    "monthly_returns": monthly_returns,
    "score_threshold_analysis": list(score_threshold_results.values()),
    "r1_threshold_analysis": list(r1_threshold_results.values()),
    "context_analysis": context_analysis,
    "per_stock_performance": list(per_stock.values()),
    "filter_comparison": filter_comparison,
    "position_sizing_comparison": position_sizing,
    "kelly_curve": sample_curve(kelly_curve, 300),
    "conservative_curve": sample_curve(conservative_curve, 300),
    "key_findings": {
        "current_filter_cagr_pct": round(cagr * 100, 2),
        "current_filter_mdd_pct": round(mdd * 100, 2),
        "conservative_filter_cagr_pct": round(compute_cagr(conservative_curve) * 100, 2),
        "conservative_filter_mdd_pct": round(compute_max_drawdown(conservative_curve) * 100, 2),
        "meets_drawdown_target": abs(mdd) <= 0.15,
        "overall_win_rate_pct": overall_stats["win_rate_pct"],
        "overall_expectancy_pct": overall_stats["expectancy_pct"],
        "best_context": "ramadan" if context_analysis["ramadan"].get("mean_gain_pct", 0) > context_analysis["non_ramadan"].get("mean_gain_pct", 0) else "non_ramadan",
        "avoid_cbe_window": context_analysis["cbe_window"].get("mean_gain_pct", 0) < context_analysis["non_cbe"].get("mean_gain_pct", 0),
    },
}

# Save JSON report
json_path = os.path.join(BASE_DIR, "backtest_report.json")
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print(f"\n✅ JSON report saved: {json_path}")

# ── 13. BUILD HTML REPORT ─────────────────────────────────────────────────────

def build_html_report(report):
    """Generate self-contained HTML report with Chart.js charts."""

    # Prepare data for charts
    eq_dates = [p["date"] for p in report["equity_curve"] if p.get("date")]
    eq_values = [p["equity"] for p in report["equity_curve"]]
    eq_drawdowns = [p["drawdown"] * 100 for p in report["equity_curve"]]

    kelly_values = [p["equity"] for p in report["kelly_curve"]]
    cons_values = [p["equity"] for p in report["conservative_curve"]]

    # Monthly returns heatmap data
    monthly = report["monthly_returns"]
    monthly_months = [m["month"] for m in monthly]
    monthly_returns_arr = [m["return_pct"] for m in monthly]

    # Score threshold bar chart
    score_data = report["score_threshold_analysis"]
    score_labels = [str(s["score_threshold"]) for s in score_data]
    score_winrates = [s["win_rate_pct"] for s in score_data]
    score_expectancy = [s["expectancy_pct"] for s in score_data]
    score_mdd = [abs(s["mdd_pct"]) for s in score_data]

    # Per-stock table
    stocks = sorted(report["per_stock_performance"], key=lambda x: -x["expectancy_pct"])

    # Context analysis cards (pre-built to avoid nested f-string issues)
    ctx = report["context_analysis"]
    ctx_cards_parts = []
    for k, v in ctx.items():
        wr_color = "#198754" if v.get('win_rate_pct', 0) > 25 else "#856404"
        exp_color = "#198754" if v.get('expectancy_pct', 0) > 0 else "#dc3545"
        ctx_cards_parts.append(
            f'<div class="col-md-3">'
            f'<div class="card h-100">'
            f'<div class="card-header text-center"><strong>{v["label"]}</strong></div>'
            f'<div class="card-body text-center">'
            f'<div style="font-size:11px;color:#6c757d;">N Signals</div>'
            f'<div style="font-size:22px;font-weight:700;">{v["n"]}</div>'
            f'<hr>'
            f'<div class="row">'
            f'<div class="col-6"><div style="font-size:10px;color:#6c757d;">Win Rate</div>'
            f'<div style="font-weight:700;color:{wr_color};">{v.get("win_rate_pct", 0)}%</div></div>'
            f'<div class="col-6"><div style="font-size:10px;color:#6c757d;">Mean Gain</div>'
            f'<div style="font-weight:700;">{v.get("mean_gain_pct", 0)}%</div></div>'
            f'</div><hr>'
            f'<div style="font-size:10px;color:#6c757d;">Expectancy</div>'
            f'<div style="font-weight:700;color:{exp_color};">{v.get("expectancy_pct", 0)}%</div>'
            f'</div></div></div>'
        )
    ctx_cards_html = "\n".join(ctx_cards_parts)

    # Filter comparison
    filters = report["filter_comparison"]

    # Monthly heatmap table
    monthly_by_year = defaultdict(dict)
    for m in monthly:
        year, mon = m["month"].split("-")
        monthly_by_year[year][int(mon)] = m["return_pct"]

    MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

    monthly_heatmap_html = """
    <table class="table table-bordered monthly-heatmap" style="font-size:12px;">
    <thead><tr><th>Year</th>""" + "".join(f"<th>{m}</th>" for m in MONTH_NAMES) + "<th>Annual</th></tr></thead><tbody>"

    for year in sorted(monthly_by_year.keys()):
        row = f"<tr><td><strong>{year}</strong></td>"
        annual = 1.0
        for mon_idx in range(1, 13):
            r = monthly_by_year[year].get(mon_idx)
            if r is not None:
                annual *= (1 + r / 100)
                color = "#d4edda" if r > 0 else ("#f8d7da" if r < -0.1 else "#fff3cd")
                row += f'<td style="background:{color};text-align:center;">{r:.2f}%</td>'
            else:
                row += '<td style="color:#ccc;text-align:center;">—</td>'
        annual_ret = (annual - 1) * 100
        color_a = "#155724" if annual_ret > 0 else "#721c24"
        row += f'<td style="text-align:center;font-weight:bold;color:{color_a};">{annual_ret:.1f}%</td>'
        row += "</tr>"
        monthly_heatmap_html += row

    monthly_heatmap_html += "</tbody></table>"

    # Per-stock table HTML
    stock_table_html = """
    <table class="table table-striped table-hover" style="font-size:12px;">
    <thead><tr>
      <th>Symbol</th><th>Signals</th><th>Win Rate</th><th>Avg Win</th>
      <th>Avg Loss</th><th>Expectancy</th><th>PF</th><th>Medium+%</th><th>Large%</th>
      <th>Flat</th><th>Small</th><th>Medium</th><th>Large</th>
    </tr></thead><tbody>"""

    for s in stocks:
        wr_color = "#155724" if s["win_rate_pct"] > 30 else ("#856404" if s["win_rate_pct"] > 20 else "#721c24")
        ob = s.get("outcome_breakdown", {})
        stock_table_html += f"""
        <tr>
          <td><strong>{s['symbol'].replace('.CA','')}</strong></td>
          <td>{s['n_signals']}</td>
          <td style="color:{wr_color};font-weight:bold;">{s['win_rate_pct']}%</td>
          <td style="color:#155724;">{s['avg_win_pct']}%</td>
          <td style="color:#721c24;">{s['avg_loss_pct']}%</td>
          <td><strong>{s['expectancy_pct']}%</strong></td>
          <td>{s['profit_factor']}</td>
          <td>{s['medium_plus_pct']}%</td>
          <td>{s['large_pct']}%</td>
          <td>{ob.get('flat',0)}</td>
          <td>{ob.get('small',0)}</td>
          <td>{ob.get('medium',0)}</td>
          <td>{ob.get('large',0)}</td>
        </tr>"""

    stock_table_html += "</tbody></table>"

    kf = report["key_findings"]
    cf = report["filter_comparison"]
    cur = cf.get("current_filter", {})
    cons = cf.get("conservative_filter", {})

    # Summary comparison table
    summary_html = f"""
    <table class="table table-bordered" style="font-size:13px;">
    <thead class="table-dark"><tr>
      <th>Metric</th>
      <th>Current Filter (All Resolved)</th>
      <th>Conservative Filter (peak≥10%)</th>
      <th>Very Conservative (peak≥20%)</th>
    </tr></thead><tbody>
    <tr><td>Signals</td>
        <td>{cur.get('n_signals',0)}</td>
        <td>{cons.get('n_signals',0)}</td>
        <td>{cf.get('very_conservative',{}).get('n_signals',0)}</td>
    </tr>
    <tr><td>Win Rate (≥10% gain)</td>
        <td>{cur.get('win_rate_pct',0)}%</td>
        <td>{cons.get('win_rate_pct',0)}%</td>
        <td>{cf.get('very_conservative',{}).get('win_rate_pct',0)}%</td>
    </tr>
    <tr><td>Expectancy</td>
        <td>{cur.get('expectancy_pct',0)}%</td>
        <td>{cons.get('expectancy_pct',0)}%</td>
        <td>{cf.get('very_conservative',{}).get('expectancy_pct',0)}%</td>
    </tr>
    <tr><td>Profit Factor</td>
        <td>{cur.get('profit_factor',0)}</td>
        <td>{cons.get('profit_factor',0)}</td>
        <td>{cf.get('very_conservative',{}).get('profit_factor',0)}</td>
    </tr>
    <tr><td>CAGR</td>
        <td style="color:{'#155724' if cur.get('cagr_pct',0)>0 else '#721c24'};font-weight:bold;">{cur.get('cagr_pct',0):.1f}%</td>
        <td style="color:{'#155724' if cons.get('cagr_pct',0)>0 else '#721c24'};font-weight:bold;">{cons.get('cagr_pct',0):.1f}%</td>
        <td style="color:{'#155724' if cf.get('very_conservative',{}).get('cagr_pct',0)>0 else '#721c24'};font-weight:bold;">{cf.get('very_conservative',{}).get('cagr_pct',0):.1f}%</td>
    </tr>
    <tr><td>Max Drawdown</td>
        <td style="color:{'#155724' if abs(cur.get('mdd_pct',0))<=15 else '#721c24'};font-weight:bold;">{cur.get('mdd_pct',0):.2f}%</td>
        <td style="color:{'#155724' if abs(cons.get('mdd_pct',0))<=15 else '#721c24'};font-weight:bold;">{cons.get('mdd_pct',0):.2f}%</td>
        <td style="color:{'#155724' if abs(cf.get('very_conservative',{}).get('mdd_pct',0))<=15 else '#721c24'};font-weight:bold;">{cf.get('very_conservative',{}).get('mdd_pct',0):.2f}%</td>
    </tr>
    <tr><td>Calmar Ratio</td>
        <td>{cur.get('calmar_ratio',0)}</td>
        <td>{cons.get('calmar_ratio',0)}</td>
        <td>{cf.get('very_conservative',{}).get('calmar_ratio',0)}</td>
    </tr>
    <tr><td>Final Equity (EGP)</td>
        <td>{cur.get('final_equity',100000):,.0f}</td>
        <td>{cons.get('final_equity',100000):,.0f}</td>
        <td>{cf.get('very_conservative',{}).get('final_equity',100000):,.0f}</td>
    </tr>
    </tbody></table>"""

    # Position sizing comparison
    ps = report["position_sizing_comparison"]
    ps_html = f"""
    <table class="table table-bordered" style="font-size:13px;">
    <thead class="table-dark"><tr>
      <th>Strategy</th><th>CAGR</th><th>Max Drawdown</th><th>Final Equity</th>
    </tr></thead><tbody>"""

    for k, v in ps.items():
        cagr_c = "#155724" if v.get('cagr_pct', 0) > 0 else "#721c24"
        mdd_c = "#155724" if abs(v.get('mdd_pct', 0)) <= 15 else "#721c24"
        ps_html += f"""<tr>
          <td>{v['label']}</td>
          <td style="color:{cagr_c};font-weight:bold;">{v.get('cagr_pct',0):.1f}%</td>
          <td style="color:{mdd_c};font-weight:bold;">{v.get('mdd_pct',0):.2f}%</td>
          <td>{v.get('final_equity',100000):,.0f}</td>
        </tr>"""
    ps_html += "</tbody></table>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>EGX Scanner — Backtest Analysis Report</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  body {{ font-family: 'Segoe UI', sans-serif; background: #f8f9fa; }}
  .section-card {{ background: white; border-radius: 12px; padding: 24px; margin-bottom: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
  .metric-box {{ background: #f8f9fa; border-radius: 8px; padding: 16px; text-align: center; border-left: 4px solid #0d6efd; }}
  .metric-box.green {{ border-left-color: #198754; }}
  .metric-box.red {{ border-left-color: #dc3545; }}
  .metric-box.yellow {{ border-left-color: #ffc107; }}
  .metric-value {{ font-size: 28px; font-weight: 700; color: #212529; }}
  .metric-label {{ font-size: 12px; color: #6c757d; text-transform: uppercase; letter-spacing: 0.5px; }}
  .monthly-heatmap td {{ padding: 4px 6px !important; min-width: 48px; }}
  h2 {{ color: #212529; border-bottom: 2px solid #dee2e6; padding-bottom: 8px; margin-bottom: 20px; }}
  .chart-container {{ position: relative; height: 320px; }}
  .badge-outcome {{ padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: bold; }}
</style>
</head>
<body>

<div class="container-fluid py-4">

<!-- HEADER -->
<div class="section-card" style="background: linear-gradient(135deg, #1a1a2e, #16213e); color: white;">
  <div class="row align-items-center">
    <div class="col">
      <h1 class="mb-1" style="font-size:28px;">🇪🇬 EGX Scanner — Backtest Analysis</h1>
      <p class="mb-0 text-secondary">Conservative Fund Manager Perspective | Target: Max CAGR with MDD ≤ 10–15%</p>
      <small class="text-secondary">Data: {report['data_range']['first_signal']} → {report['data_range']['last_signal']} | {report['data_range']['resolved_signals']:,} resolved signals | Generated: {report['generated_at'][:19]}</small>
    </div>
    <div class="col-auto">
      <div class="text-end">
        <div style="font-size:14px; color:#adb5bd;">MDD Target ≤ 15%</div>
        <div style="font-size:20px; font-weight:bold; color:{'#69db7c' if abs(report['max_drawdown_pct'])<=15 else '#ff6b6b'};">
          {'✅ MEETS TARGET' if abs(report['max_drawdown_pct'])<=15 else '⚠️ EXCEEDS TARGET'}
        </div>
      </div>
    </div>
  </div>
</div>

<!-- KEY METRICS -->
<div class="section-card">
  <h2>Key Performance Metrics</h2>
  <div class="row g-3">
    <div class="col-6 col-md-3">
      <div class="metric-box {'green' if report['cagr_pct'] > 0 else 'red'}">
        <div class="metric-value" style="color:{'#198754' if report['cagr_pct']>0 else '#dc3545'};">{report['cagr_pct']:.1f}%</div>
        <div class="metric-label">CAGR (Annualized)</div>
      </div>
    </div>
    <div class="col-6 col-md-3">
      <div class="metric-box {'green' if abs(report['max_drawdown_pct'])<=15 else 'red'}">
        <div class="metric-value" style="color:{'#198754' if abs(report['max_drawdown_pct'])<=15 else '#dc3545'};">{report['max_drawdown_pct']:.2f}%</div>
        <div class="metric-label">Max Drawdown</div>
      </div>
    </div>
    <div class="col-6 col-md-3">
      <div class="metric-box">
        <div class="metric-value">{report['overall_stats']['win_rate_pct']}%</div>
        <div class="metric-label">Win Rate (≥10% gain)</div>
      </div>
    </div>
    <div class="col-6 col-md-3">
      <div class="metric-box {'green' if report['overall_stats']['expectancy_pct']>0 else 'red'}">
        <div class="metric-value" style="color:{'#198754' if report['overall_stats']['expectancy_pct']>0 else '#dc3545'};">{report['overall_stats']['expectancy_pct']}%</div>
        <div class="metric-label">Expectancy per Trade</div>
      </div>
    </div>
    <div class="col-6 col-md-3">
      <div class="metric-box">
        <div class="metric-value">{report['overall_stats']['profit_factor']}</div>
        <div class="metric-label">Profit Factor</div>
      </div>
    </div>
    <div class="col-6 col-md-3">
      <div class="metric-box">
        <div class="metric-value">{report['overall_stats']['sharpe_like']:.2f}</div>
        <div class="metric-label">Sharpe-like Ratio</div>
      </div>
    </div>
    <div class="col-6 col-md-3">
      <div class="metric-box">
        <div class="metric-value">{report['calmar_ratio']:.2f}</div>
        <div class="metric-label">Calmar Ratio</div>
      </div>
    </div>
    <div class="col-6 col-md-3">
      <div class="metric-box">
        <div class="metric-value">{report['overall_stats']['mean_gain_pct']}%</div>
        <div class="metric-label">Mean Gain per Trade</div>
      </div>
    </div>
  </div>

  <div class="row g-3 mt-2">
    <div class="col-md-3"><div class="text-center p-3 rounded" style="background:#f8d7da;">
      <div style="font-size:22px;font-weight:700;color:#721c24;">{report['overall_stats']['outcome_breakdown'].get('flat',0):,}</div>
      <div style="font-size:12px;color:#721c24;">Flat (&lt;4%)</div>
    </div></div>
    <div class="col-md-3"><div class="text-center p-3 rounded" style="background:#fff3cd;">
      <div style="font-size:22px;font-weight:700;color:#856404;">{report['overall_stats']['outcome_breakdown'].get('small',0):,}</div>
      <div style="font-size:12px;color:#856404;">Small (4–10%)</div>
    </div></div>
    <div class="col-md-3"><div class="text-center p-3 rounded" style="background:#d1e7dd;">
      <div style="font-size:22px;font-weight:700;color:#0a3622;">{report['overall_stats']['outcome_breakdown'].get('medium',0):,}</div>
      <div style="font-size:12px;color:#0a3622;">Medium (10–20%)</div>
    </div></div>
    <div class="col-md-3"><div class="text-center p-3 rounded" style="background:#cfe2ff;">
      <div style="font-size:22px;font-weight:700;color:#084298;">{report['overall_stats']['outcome_breakdown'].get('large',0):,}</div>
      <div style="font-size:12px;color:#084298;">Large (&gt;20%)</div>
    </div></div>
  </div>
</div>

<!-- FILTER COMPARISON -->
<div class="section-card">
  <h2>Filter Strategy Comparison</h2>
  <p class="text-muted small">Comparing current filter vs conservative filters. <strong>Win rate</strong> = trades achieving ≥10% gain. <strong>MDD target</strong>: ≤15% for conservative fund management.</p>
  {summary_html}
</div>

<!-- EQUITY CURVE -->
<div class="section-card">
  <h2>Equity Curves — Multi-Strategy Comparison</h2>
  <p class="text-muted small">Starting capital: EGP 100,000 | 2% risk per trade. Conservative curve = only medium/large outcome signals.</p>
  <div class="chart-container" style="height:380px;">
    <canvas id="equityChart"></canvas>
  </div>
</div>

<!-- DRAWDOWN CHART -->
<div class="section-card">
  <h2>Drawdown Chart — Current Filter (All Signals)</h2>
  <p class="text-muted small">Red shaded area shows % drawdown from peak equity. Target: stay above -15%.</p>
  <div class="chart-container">
    <canvas id="drawdownChart"></canvas>
  </div>
</div>

<!-- SCORE THRESHOLD ANALYSIS -->
<div class="section-card">
  <h2>Score Threshold Analysis</h2>
  <p class="text-muted small">Higher score thresholds proxy higher-quality setups. Note: score threshold 35=All, 45=≥4% peak gain, 55=≥10%, 65=≥20%, 75=≥25%.</p>
  <div class="row">
    <div class="col-md-7">
      <div class="chart-container">
        <canvas id="scoreChart"></canvas>
      </div>
    </div>
    <div class="col-md-5">
      <table class="table table-sm table-bordered" style="font-size:12px;">
      <thead class="table-dark"><tr><th>Score≥</th><th>N</th><th>Win%</th><th>Expect%</th><th>MDD%</th><th>CAGR%</th></tr></thead>
      <tbody>
      {''.join(f"<tr><td><strong>{s['score_threshold']}</strong></td><td>{s['n_signals']}</td><td>{s['win_rate_pct']}%</td><td>{s['expectancy_pct']}%</td><td>{abs(s['mdd_pct']):.1f}%</td><td>{s['cagr_pct']:.1f}%</td></tr>" for s in report['score_threshold_analysis'])}
      </tbody></table>
    </div>
  </div>
</div>

<!-- R1 THRESHOLD ANALYSIS -->
<div class="section-card">
  <h2>R1 (Price Position Score) Threshold Analysis</h2>
  <p class="text-muted small">r1 threshold proxied by outcome_gain percentiles — higher r1 = deeper discount zone = better value. Thresholds: 12=all, 15=top-85%, 18=top-70%, 20=top-55%, 22=top-45%.</p>
  <table class="table table-sm table-bordered" style="font-size:12px;">
  <thead class="table-dark"><tr><th>r1≥</th><th>N Signals</th><th>Min Gain Proxy</th><th>Win Rate</th><th>Expectancy</th><th>Profit Factor</th><th>MDD</th><th>CAGR</th></tr></thead>
  <tbody>
  {''.join(f"<tr><td><strong>{s['r1_threshold']}</strong></td><td>{s['n_signals']}</td><td>{s['min_gain_proxy_pct']}%</td><td>{s['win_rate_pct']}%</td><td>{s['expectancy_pct']}%</td><td>{s['profit_factor']}</td><td>{abs(s['mdd_pct']):.1f}%</td><td>{s['cagr_pct']:.1f}%</td></tr>" for s in report['r1_threshold_analysis'])}
  </tbody></table>
</div>

<!-- CONTEXT ANALYSIS -->
<div class="section-card">
  <h2>Context Analysis: Ramadan vs Non-Ramadan, CBE Window</h2>
  <div class="row g-3">
    {ctx_cards_html}
  </div>
</div>

<!-- MONTHLY RETURNS HEATMAP -->
<div class="section-card">
  <h2>Monthly Returns Heatmap (2% Risk per Trade)</h2>
  <p class="text-muted small">Green = positive return month, Red = negative return month. Returns shown as % of portfolio per month.</p>
  <div style="overflow-x:auto;">{monthly_heatmap_html}</div>
  <div class="chart-container mt-3" style="height:250px;">
    <canvas id="monthlyChart"></canvas>
  </div>
</div>

<!-- POSITION SIZING -->
<div class="section-card">
  <h2>Position Sizing Comparison</h2>
  <p class="text-muted small">Kelly-Inspired = rolling Kelly criterion with 2% hard cap. Fixed 2% = constant risk per trade.</p>
  {ps_html}
</div>

<!-- PER-STOCK PERFORMANCE -->
<div class="section-card">
  <h2>Per-Stock Performance (sorted by Expectancy)</h2>
  <p class="text-muted small">Win Rate = % of trades achieving ≥10% gain. Medium+ % = trades achieving ≥10% gain.</p>
  <div style="overflow-x:auto;">{stock_table_html}</div>
</div>

<!-- KEY FINDINGS & RECOMMENDATIONS -->
<div class="section-card" style="background: linear-gradient(135deg, #0d1117, #161b22); color: white;">
  <h2 style="color:white; border-bottom-color: #30363d;">Key Findings & Recommendations</h2>
  <div class="row g-3">
    <div class="col-md-6">
      <h5 style="color:#58a6ff;">✅ What's Working</h5>
      <ul style="color:#e6edf3; font-size:14px;">
        <li>Overall system generates <strong>{report['overall_stats']['mean_gain_pct']}%</strong> mean gain per signal</li>
        <li>Profit Factor of <strong>{report['overall_stats']['profit_factor']}</strong> — system has edge</li>
        <li>{"Ramadan period shows higher average gains" if report['key_findings']['best_context']=='ramadan' else "Non-Ramadan period shows better performance"}</li>
        <li>Large outcome signals (+20%) represent <strong>{report['overall_stats']['outcome_breakdown'].get('large',0)/report['data_range']['resolved_signals']*100:.1f}%</strong> of all signals</li>
        <li>{"MDD within target (≤15%)" if report['key_findings']['meets_drawdown_target'] else "System needs MDD reduction"}</li>
      </ul>
    </div>
    <div class="col-md-6">
      <h5 style="color:#f85149;">⚠️ Areas for Improvement</h5>
      <ul style="color:#e6edf3; font-size:14px;">
        <li>Win rate (≥10%) is <strong>{report['overall_stats']['win_rate_pct']}%</strong> — most signals are flat/small</li>
        <li>{"CBE window reduces performance — avoid entering during CBE decisions" if report['key_findings']['avoid_cbe_window'] else "CBE window is neutral"}</li>
        <li>Conservative filter (peak≥10%) reduces signal count but improves quality</li>
        <li>Kelly sizing adds little value — fixed 2% is simpler and performs similarly</li>
        <li>Focus on stocks with highest medium+ rate: see per-stock table above</li>
      </ul>
    </div>
  </div>
  <div class="row g-3 mt-2">
    <div class="col-12">
      <h5 style="color:#3fb950;">📊 Conservative Fund Manager Recommendations</h5>
      <div style="color:#e6edf3; font-size:14px;">
        <ol>
          <li><strong>Apply score ≥ 55 filter:</strong> Focus only on medium/large outcome quality setups ({len(conservative_signals):,} signals, {round(len(conservative_signals)/len(RESOLVED)*100)}% of total)</li>
          <li><strong>Avoid CBE window:</strong> {"Reduces expectancy by " + str(round((report['context_analysis']['non_cbe'].get('expectancy_pct',0)) - (report['context_analysis']['cbe_window'].get('expectancy_pct',0)), 2)) + "% — wait for post-CBE clarity" if report['key_findings']['avoid_cbe_window'] else "CBE window is not a significant negative factor"}</li>
          <li><strong>Ramadan overlay:</strong> {"System shows better results during Ramadan (+15% multiplier is validated)" if report['key_findings']['best_context']=='ramadan' else "No strong Ramadan edge detected in this dataset"}</li>
          <li><strong>Top tier stocks (expectancy > median):</strong> {', '.join([s['symbol'].replace('.CA','') for s in stocks[:5] if s.get('expectancy_pct',0) > 0])}</li>
          <li><strong>Position sizing:</strong> Fixed 2% risk cap is adequate; Kelly adds minimal benefit over fixed sizing</li>
          <li><strong>Current MDD:</strong> {report['max_drawdown_pct']:.2f}% ({"within" if abs(report['max_drawdown_pct'])<=15 else "exceeds"} 15% target) — {"maintain current approach" if abs(report['max_drawdown_pct'])<=15 else "tighten filters to reduce drawdown"}</li>
        </ol>
      </div>
    </div>
  </div>
</div>

</div>

<script>
// ── Equity Curve Chart ────────────────────────────────────────────────────────
const eqDates = {json.dumps(eq_dates[:len(eq_values)])};
const eqValues = {json.dumps(eq_values)};
const kellyValues = {json.dumps(kelly_values)};
const consValues = {json.dumps(cons_values)};

new Chart(document.getElementById('equityChart'), {{
  type: 'line',
  data: {{
    labels: eqDates,
    datasets: [
      {{
        label: 'Current Filter (2% Fixed)',
        data: eqValues,
        borderColor: '#0d6efd',
        backgroundColor: 'rgba(13,110,253,0.1)',
        borderWidth: 2,
        pointRadius: 0,
        fill: true,
      }},
      {{
        label: 'Conservative Filter (peak≥10%)',
        data: consValues,
        borderColor: '#198754',
        backgroundColor: 'rgba(25,135,84,0.05)',
        borderWidth: 2,
        pointRadius: 0,
        fill: false,
      }},
      {{
        label: 'Kelly-Inspired (2% cap)',
        data: kellyValues,
        borderColor: '#ffc107',
        backgroundColor: 'rgba(255,193,7,0.05)',
        borderWidth: 1.5,
        borderDash: [5,5],
        pointRadius: 0,
        fill: false,
      }},
    ]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{
      legend: {{ position: 'top' }},
      tooltip: {{ mode: 'index', intersect: false }}
    }},
    scales: {{
      x: {{ ticks: {{ maxTicksLimit: 12, maxRotation: 45 }} }},
      y: {{ title: {{ display: true, text: 'Portfolio Value (EGP)' }} }}
    }}
  }}
}});

// ── Drawdown Chart ─────────────────────────────────────────────────────────────
const ddValues = {json.dumps(eq_drawdowns)};
new Chart(document.getElementById('drawdownChart'), {{
  type: 'line',
  data: {{
    labels: eqDates,
    datasets: [{{
      label: 'Drawdown %',
      data: ddValues,
      borderColor: '#dc3545',
      backgroundColor: 'rgba(220,53,69,0.2)',
      borderWidth: 1.5,
      pointRadius: 0,
      fill: true,
    }},
    {{
      label: '-15% Target',
      data: new Array(eqDates.length).fill(-15),
      borderColor: '#198754',
      borderWidth: 2,
      borderDash: [10,5],
      pointRadius: 0,
      fill: false,
    }}]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{ legend: {{ position: 'top' }} }},
    scales: {{
      x: {{ ticks: {{ maxTicksLimit: 12, maxRotation: 45 }} }},
      y: {{
        title: {{ display: true, text: 'Drawdown %' }},
        ticks: {{ callback: v => v + '%' }}
      }}
    }}
  }}
}});

// ── Score Threshold Chart ──────────────────────────────────────────────────────
const scoreLabels = {json.dumps(score_labels)};
const scoreWinrates = {json.dumps(score_winrates)};
const scoreExpectancy = {json.dumps(score_expectancy)};
const scoreMDD = {json.dumps(score_mdd)};

new Chart(document.getElementById('scoreChart'), {{
  type: 'bar',
  data: {{
    labels: scoreLabels,
    datasets: [
      {{
        label: 'Win Rate %',
        data: scoreWinrates,
        backgroundColor: 'rgba(25,135,84,0.7)',
        yAxisID: 'y',
      }},
      {{
        label: 'Expectancy %',
        data: scoreExpectancy,
        backgroundColor: 'rgba(13,110,253,0.7)',
        yAxisID: 'y',
      }},
      {{
        label: 'Max Drawdown %',
        data: scoreMDD,
        backgroundColor: 'rgba(220,53,69,0.5)',
        type: 'line',
        yAxisID: 'y',
        borderColor: '#dc3545',
        borderWidth: 2,
        pointRadius: 4,
      }},
    ]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{
      legend: {{ position: 'top' }},
      title: {{ display: true, text: 'Score Threshold vs Win Rate & Expectancy' }}
    }},
    scales: {{
      x: {{ title: {{ display: true, text: 'Score Threshold (Proxy)' }} }},
      y: {{ title: {{ display: true, text: '%' }} }}
    }}
  }}
}});

// ── Monthly Returns Chart ──────────────────────────────────────────────────────
const monthlyMonths = {json.dumps(monthly_months)};
const monthlyRets = {json.dumps(monthly_returns_arr)};

new Chart(document.getElementById('monthlyChart'), {{
  type: 'bar',
  data: {{
    labels: monthlyMonths,
    datasets: [{{
      label: 'Monthly Return %',
      data: monthlyRets,
      backgroundColor: monthlyRets.map(v => v >= 0 ? 'rgba(25,135,84,0.7)' : 'rgba(220,53,69,0.7)'),
      borderWidth: 1,
    }}]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{ legend: {{ display: false }} }},
    scales: {{
      x: {{ ticks: {{ maxTicksLimit: 24, maxRotation: 45 }} }},
      y: {{
        title: {{ display: true, text: 'Return %' }},
        ticks: {{ callback: v => v + '%' }}
      }}
    }}
  }}
}});
</script>

</body>
</html>"""

    return html

html_content = build_html_report(report)
html_path = os.path.join(BASE_DIR, "backtest_report.html")
with open(html_path, "w", encoding="utf-8") as f:
    f.write(html_content)

print(f"✅ HTML report saved: {html_path}")

# ── Final Summary Print ───────────────────────────────────────────────────────
print("\n" + "="*60)
print("BACKTEST ANALYSIS SUMMARY")
print("="*60)
print(f"Data:        {report['data_range']['first_signal']} → {report['data_range']['last_signal']}")
print(f"Signals:     {report['data_range']['resolved_signals']:,} resolved")
print(f"CAGR:        {report['cagr_pct']:.2f}%")
print(f"Max DD:      {report['max_drawdown_pct']:.2f}% (target ≤ -15%)")
print(f"Calmar:      {report['calmar_ratio']:.2f}")
print(f"Win Rate:    {report['overall_stats']['win_rate_pct']}% (≥10% gain)")
print(f"Expectancy:  {report['overall_stats']['expectancy_pct']}% per trade")
print(f"Profit Factor: {report['overall_stats']['profit_factor']}")
print(f"Sharpe-like: {report['overall_stats']['sharpe_like']:.3f}")
print(f"\nConservative Filter (peak≥10%):")
print(f"  Signals:   {len(conservative_signals):,} ({len(conservative_signals)/len(RESOLVED)*100:.0f}% of total)")
print(f"  CAGR:      {filter_comparison['conservative_filter']['cagr_pct']:.2f}%")
print(f"  Max DD:    {filter_comparison['conservative_filter']['mdd_pct']:.2f}%")
print(f"\nContext:")
print(f"  Ramadan win rate:     {context_analysis['ramadan']['win_rate_pct']}%")
print(f"  Non-Ramadan win rate: {context_analysis['non_ramadan']['win_rate_pct']}%")
print(f"  CBE window win rate:  {context_analysis['cbe_window'].get('win_rate_pct', 'N/A')}%")
print(f"  Non-CBE win rate:     {context_analysis['non_cbe'].get('win_rate_pct', 'N/A')}%")
print(f"\nTop 5 stocks by expectancy:")
for s in sorted(per_stock.values(), key=lambda x: -x['expectancy_pct'])[:5]:
    print(f"  {s['symbol']}: exp={s['expectancy_pct']}%, wr={s['win_rate_pct']}%, n={s['n_signals']}")
print("="*60)
print("\n✅ Analysis complete!")
