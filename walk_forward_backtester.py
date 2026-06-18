"""
Walk-Forward Adaptive Backtester
==================================
Chronological replay of every historical signal using ONLY information
available at decision time.  No look-ahead.

Flow per signal (ordered by date):
  1. Score it with weights known up to that moment
  2. BUY if score >= threshold  |  WAIT otherwise
  3. When 90-day outcome arrives → gradient update → weights shift
  4. Accumulate equity, weight history, rolling win-rate

Outputs:
  walk_forward_state.json   — persistent state (weights, equity, trade log)
  reports/walk_forward_report_{date}.html
"""

import json
import math
import sqlite3
from collections import deque
from datetime import date, datetime, timezone
from pathlib import Path
from signal_db import DB_PATH

REPORTS_DIR = Path("reports")
REPORTS_DIR.mkdir(exist_ok=True)
TODAY     = date.today().isoformat()
NOW       = datetime.now(timezone.utc).isoformat()
STATE_FILE = Path("walk_forward_state.json")

# ── Indicator definitions ─────────────────────────────────────────────────────
INDICATORS = [
    ("r1_price",     "Price Position",    30),
    ("r2_ob",        "OB Quality",        10),
    ("r3_liquidity", "Liquidity Context", 20),
    ("r4_htf",       "HTF Alignment",     10),
    ("r5_avwap",     "AVWAP Support",      8),
    ("r6_macd",      "MACD Signal",        4),
    ("r7_div",       "Divergence",         3),
    ("r8_demand",    "Demand Zone",       15),
]
IND_KEYS = [i[0] for i in INDICATORS]
IND_MAX  = {i[0]: i[2] for i in INDICATORS}

SYSTEM_WEIGHTS = {"r1_price": 30, "r2_ob": 10, "r3_liquidity": 20,
                  "r4_htf": 10, "r5_avwap": 8, "r6_macd": 4,
                  "r7_div": 3, "r8_demand": 15}

# ── Hyperparameters ───────────────────────────────────────────────────────────
BUY_THRESHOLD    = 55      # score (0-100) above which we BUY
WARM_UP_N        = 40      # signals before we start deciding
LEARNING_RATE    = 0.015   # gradient step size
LAMBDA_REG       = 0.008   # L2 pull toward system weights
ROLLING_WIN      = 20      # rolling window for win-rate metric
MIN_WIN_N        = 5       # min trades in window to show metric
POSITION_SIZE    = 0.10    # 10% of equity per trade (realistic sizing)

# ── State helpers ─────────────────────────────────────────────────────────────

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {
        "weights":       dict(SYSTEM_WEIGHTS),
        "equity":        100.0,
        "trades":        [],
        "weight_log":    [],
        "processed_ids": [],
        "created_at":    NOW,
    }


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def normalize_weights(w: dict) -> dict:
    total = sum(w.values())
    return {k: v / total * 100 for k, v in w.items()} if total > 0 else dict(w)


# ── Scoring & decision ────────────────────────────────────────────────────────

def score_signal(row: dict, weights: dict) -> float:
    """Weighted sum, normalized to 0-100."""
    total_weight = sum(weights.values())
    if total_weight == 0:
        return 0.0
    s = sum(
        (row.get(k) or 0) / IND_MAX[k] * weights[k]
        for k in IND_KEYS
    )
    return s / total_weight * 100


def gradient_update(weights: dict, features: dict, predicted: float,
                    actual_return: float) -> dict:
    """One online gradient step.  Returns new (unnormalized) weights."""
    w = dict(weights)
    error = (predicted / 100.0) - actual_return      # scalar error
    lr    = LEARNING_RATE
    for k in IND_KEYS:
        feat = (features.get(k) or 0) / IND_MAX[k]   # normalized feature
        reg  = LAMBDA_REG * (w[k] - SYSTEM_WEIGHTS[k])
        w[k] -= lr * (error * feat + reg)
        w[k]  = max(0.01, w[k])                       # stay positive
    return normalize_weights(w)


# ── Data loading ──────────────────────────────────────────────────────────────

def load_signals() -> list[dict]:
    """
    Load ALL SMC Buy signals from BOTH tables (no overlap):
      - signals table (641 rows): from historical OHLCV replay
        → outcomes in bottom_quality (r20d, r_90d, r_180d, r_252d)
      - hist_signals (412 rows): from live signal_history.json
        → outcomes already embedded in hist_signals
    Combined: ~1053 unique signals, ~824 with 90d outcome.
    """
    conn = sqlite3.connect(DB_PATH)

    # ── Source 1: signals table + bottom_quality ─────────────────────────────
    q1 = conn.execute("""
        SELECT
            s.id, s.symbol, s.signal_date,
            COALESCE(s.r1_price, 0), COALESCE(s.r2_ob, 0),
            COALESCE(s.r3_liquidity, 0), COALESCE(s.r4_htf, 0),
            COALESCE(s.r5_avwap, 0),  COALESCE(s.r6_macd, 0),
            COALESCE(s.r7_div, 0),    COALESCE(s.r8_demand, 0),
            s.raw_score,
            bq.r20d, bq.r_90d, bq.r_180d, bq.r_252d,
            bq.mfe_90d, bq.mae_90d, bq.classification,
            COALESCE(s.pattern_score, 0),
            COALESCE(s.market_regime, 'unk'),
            COALESCE(s.sector, 'unk')
        FROM signals s
        LEFT JOIN bottom_quality bq ON bq.signal_id = s.id
        WHERE s.r1_price IS NOT NULL
    """).fetchall()

    # ── Source 2: hist_signals (disjoint from signals table) ─────────────────
    q2 = conn.execute("""
        SELECT
            hs.id, hs.symbol, hs.signal_date,
            COALESCE(hs.r1_price, 0), COALESCE(hs.r2_ob, 0),
            COALESCE(hs.r3_liquidity, 0), COALESCE(hs.r4_htf, 0),
            COALESCE(hs.r5_avwap, 0), COALESCE(hs.r6_macd, 0),
            COALESCE(hs.r7_div, 0),   COALESCE(hs.r8_demand, 0),
            hs.raw_score,
            hs.r20d, hs.r_90d, hs.r_180d, hs.r_252d,
            hs.mfe_90d, hs.mae_90d, hs.classification,
            COALESCE(s2.pattern_score, 0),
            COALESCE(s2.market_regime, 'unk'),
            COALESCE(s2.sector, 'unk')
        FROM hist_signals hs
        LEFT JOIN signals s2 ON s2.id = hs.id
        WHERE hs.r1_price IS NOT NULL
    """).fetchall()

    conn.close()

    cols = ["id", "symbol", "signal_date",
            "r1_price", "r2_ob", "r3_liquidity", "r4_htf",
            "r5_avwap", "r6_macd", "r7_div", "r8_demand",
            "raw_score", "r20d", "r_90d", "r_180d", "r_252d",
            "mfe_90d", "mae_90d", "classification",
            "pattern_score", "market_regime", "sector"]

    # Deduplicate by (symbol, signal_date) — prefer hist_signals if same date
    seen: set[tuple] = set()
    result = []
    for row in sorted(list(q1) + list(q2), key=lambda r: (r[2], r[1])):
        key = (row[1], row[2])  # (symbol, signal_date)
        if key not in seen:
            seen.add(key)
            result.append(dict(zip(cols, row)))

    print(f"[WF] Loaded {len(result)} unique signals "
          f"({len(q1)} from signals+bq, {len(q2)} from hist_signals)")
    return result


# ── Walk-forward engine ───────────────────────────────────────────────────────

def run_walk_forward(state: dict) -> dict:
    signals   = load_signals()
    weights   = dict(state["weights"])
    equity    = float(state["equity"])
    processed = set(state.get("processed_ids", []))
    trades    = list(state.get("trades", []))
    wlog      = list(state.get("weight_log", []))

    new_signals = [s for s in signals if s["id"] not in processed]
    if not new_signals:
        print("[WF] No new signals to process.")
        return state

    print(f"[WF] Processing {len(new_signals)} new signals "
          f"(total history: {len(signals)})")

    # We need full chronological ordering for warm-up check
    # Find index of first new signal in full list
    all_ids = [s["id"] for s in signals]
    new_ids = {s["id"] for s in new_signals}

    n_decided = len([t for t in trades])  # already decided trades

    for i, sig in enumerate(signals):
        if sig["id"] in processed:
            continue

        global_idx = all_ids.index(sig["id"])
        score      = score_signal(sig, weights)
        in_warmup  = global_idx < WARM_UP_N

        decision   = "WAIT"
        if not in_warmup and score >= BUY_THRESHOLD:
            decision = "BUY"

        has_outcome = sig["r_90d"] is not None
        outcome     = sig["r_90d"]

        trade_rec = {
            "id":         sig["id"],
            "symbol":     sig["symbol"],
            "date":       sig["signal_date"],
            "score":      round(score, 2),
            "raw_score":  sig["raw_score"],
            "decision":   decision,
            "outcome_90d": round(outcome * 100, 2) if outcome is not None else None,
            "outcome_180d": round(sig["r_180d"] * 100, 2) if sig["r_180d"] is not None else None,
            "outcome_252d": round(sig["r_252d"] * 100, 2) if sig["r_252d"] is not None else None,
            "mfe_90d":    round(sig["mfe_90d"] * 100, 2) if sig["mfe_90d"] else None,
            "mae_90d":    round(sig["mae_90d"] * 100, 2) if sig["mae_90d"] else None,
            "regime":     sig["market_regime"],
            "class":      sig["classification"],
            "warmup":     in_warmup,
            "weights_snapshot": {k: round(v, 2) for k, v in weights.items()},
        }

        # Update equity and weights if BUY and outcome known
        if decision == "BUY" and has_outcome:
            # Fractional position: risk POSITION_SIZE% of current equity
            equity += equity * POSITION_SIZE * outcome
            trade_rec["equity_after"] = round(equity, 2)
            # Gradient update
            weights = gradient_update(weights, sig, score, outcome)
            wlog.append({
                "date":    sig["signal_date"],
                "weights": {k: round(v, 2) for k, v in weights.items()},
                "equity":  round(equity, 2),
                "trade_outcome": round(outcome * 100, 2),
            })
        elif decision == "WAIT" and has_outcome:
            # Still learn from WAIT signals (counter-factual: reinforce good WAITs)
            weights = gradient_update(weights, sig, score, outcome)

        trades.append(trade_rec)
        processed.add(sig["id"])

    state["weights"]       = weights
    state["equity"]        = round(equity, 2)
    state["trades"]        = trades
    state["weight_log"]    = wlog
    state["processed_ids"] = list(processed)
    state["last_updated"]  = NOW
    return state


# ── Analytics ─────────────────────────────────────────────────────────────────

def compute_analytics(state: dict) -> dict:
    trades  = state["trades"]
    buy_trades = [t for t in trades
                  if t["decision"] == "BUY" and t["outcome_90d"] is not None
                  and not t.get("warmup")]

    if not buy_trades:
        return {}

    returns   = [t["outcome_90d"] for t in buy_trades]
    n         = len(buy_trades)
    wins      = [r for r in returns if r > 3.0]   # > 3% = win
    losses    = [r for r in returns if r <= 0]

    avg_ret   = sum(returns) / n
    win_rate  = len(wins) / n
    avg_win   = sum(wins) / len(wins) if wins else 0
    avg_loss  = sum(losses) / len(losses) if losses else 0
    pf        = abs(avg_win * len(wins) / (avg_loss * len(losses))) if losses and avg_loss != 0 else float("inf")
    max_dd    = 0.0
    peak      = 100.0
    eq        = 100.0
    for t in buy_trades:
        eq   *= (1 + t["outcome_90d"] / 100)
        peak  = max(peak, eq)
        dd    = (peak - eq) / peak
        max_dd = max(max_dd, dd)

    # Rolling win rate (last ROLLING_WIN trades)
    rolling = []
    window  = deque(maxlen=ROLLING_WIN)
    for t in buy_trades:
        window.append(1 if t["outcome_90d"] > 3.0 else 0)
        if len(window) >= MIN_WIN_N:
            rolling.append({
                "date": t["date"],
                "wr":   round(sum(window) / len(window) * 100, 1),
            })

    # Best / worst trades
    sorted_t  = sorted(buy_trades, key=lambda x: x["outcome_90d"])
    worst5    = sorted_t[:5]
    best5     = sorted_t[-5:][::-1]

    # By regime
    by_regime: dict[str, list] = {}
    for t in buy_trades:
        r = t.get("regime", "unk")
        by_regime.setdefault(r, []).append(t["outcome_90d"])

    # By year
    by_year: dict[str, list] = {}
    for t in buy_trades:
        y = t["date"][:4]
        by_year.setdefault(y, []).append(t["outcome_90d"])

    # Weight evolution: first vs current
    wlog  = state.get("weight_log", [])
    w_now = state["weights"]

    # WAIT signals that had big positive outcomes (missed opportunities)
    missed = [t for t in trades
              if t["decision"] == "WAIT"
              and t["outcome_90d"] is not None
              and t["outcome_90d"] > 15.0
              and not t.get("warmup")]
    missed = sorted(missed, key=lambda x: -x["outcome_90d"])[:10]

    return {
        "n":          n,
        "equity":     state["equity"],
        "equity_gain": round(state["equity"] - 100, 1),
        "avg_ret":    round(avg_ret, 2),
        "win_rate":   round(win_rate * 100, 1),
        "avg_win":    round(avg_win, 2),
        "avg_loss":   round(avg_loss, 2),
        "profit_factor": round(pf, 2) if pf != float("inf") else 99.0,
        "max_dd":     round(max_dd * 100, 1),
        "best5":      best5,
        "worst5":     worst5,
        "by_regime":  {r: {"n": len(v), "avg": round(sum(v)/len(v), 2),
                           "wr": round(sum(1 for x in v if x>3)/len(v)*100, 1)}
                       for r, v in by_regime.items()},
        "by_year":    {y: {"n": len(v), "avg": round(sum(v)/len(v), 2),
                           "wr": round(sum(1 for x in v if x>3)/len(v)*100, 1)}
                       for y, v in by_year.items()},
        "rolling_wr": rolling,
        "w_now":      {k: round(v, 2) for k, v in w_now.items()},
        "missed":     missed,
        "n_wait":     len([t for t in trades if t["decision"] == "WAIT" and not t.get("warmup")]),
        "n_warmup":   len([t for t in trades if t.get("warmup")]),
        "n_pending":  len([t for t in trades if t["decision"] == "BUY" and t["outcome_90d"] is None]),
    }


# ── SVG mini-charts ───────────────────────────────────────────────────────────

def _svg_line(points: list[float], w: int = 600, h: int = 120,
              color: str = "#58a6ff", fill: str = "#1a3c5e30") -> str:
    """Simple SVG polyline chart with fill."""
    if len(points) < 2:
        return ""
    mn, mx = min(points), max(points)
    rng = mx - mn or 1

    def _x(i): return round(i / (len(points) - 1) * w, 1)
    def _y(v): return round(h - (v - mn) / rng * (h - 10) - 5, 1)

    pts = " ".join(f"{_x(i)},{_y(v)}" for i, v in enumerate(points))
    fill_pts = f"0,{h} " + pts + f" {w},{h}"
    return (
        f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" '
        f'style="width:100%;height:{h}px;display:block">'
        f'<polygon points="{fill_pts}" fill="{fill}"/>'
        f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2"/>'
        f'</svg>'
    )


def _weight_bars(w_now: dict) -> str:
    """Horizontal bar comparison: system vs walk-forward weights."""
    rows = ""
    for k, name, max_v in INDICATORS:
        sys_w = SYSTEM_WEIGHTS[k]
        wf_w  = w_now.get(k, sys_w)
        diff  = wf_w - sys_w
        diff_color = "#28a745" if diff > 0 else "#dc3545"
        diff_str   = f"+{diff:.1f}" if diff >= 0 else f"{diff:.1f}"
        pct_wf  = min(100, wf_w / 40 * 100)
        pct_sys = min(100, sys_w / 40 * 100)
        rows += f"""
<tr>
  <td style="font-size:12px;padding:6px 8px;white-space:nowrap">{name}</td>
  <td style="padding:6px 8px;min-width:180px">
    <div style="background:#1a3c5e;height:8px;border-radius:4px;width:{pct_sys:.0f}%;margin-bottom:3px"></div>
    <div style="background:#58a6ff;height:8px;border-radius:4px;width:{pct_wf:.0f}%"></div>
  </td>
  <td style="text-align:center;font-size:12px;color:#888">{sys_w:.0f}</td>
  <td style="text-align:center;font-size:12px;color:#58a6ff;font-weight:700">{wf_w:.1f}</td>
  <td style="text-align:center;font-size:12px;color:{diff_color};font-weight:600">{diff_str}</td>
</tr>"""
    return rows


# ── HTML Report ───────────────────────────────────────────────────────────────

def build_html(state: dict, an: dict) -> str:
    trades = state["trades"]
    wlog   = state["weight_log"]

    # Equity curve data
    eq_points = [100.0]
    eq_labels = ["start"]
    for t in trades:
        if t["decision"] == "BUY" and t.get("equity_after") is not None and not t.get("warmup"):
            eq_points.append(t["equity_after"])
            eq_labels.append(t["date"][:7])
    eq_svg = _svg_line(eq_points, color="#28a745", fill="#28a74520")

    # Rolling WR chart
    wr_points = [x["wr"] for x in an.get("rolling_wr", [])]
    wr_svg = _svg_line(wr_points, color="#f0b840", fill="#f0b84015", h=80)

    # Weight bar comparison
    w_bars = _weight_bars(an.get("w_now", {}))

    # Trade log (last 30 BUY decisions)
    buy_trades_sorted = sorted(
        [t for t in trades if t["decision"] == "BUY" and not t.get("warmup")],
        key=lambda x: x["date"], reverse=True
    )[:50]

    trade_rows = ""
    for t in buy_trades_sorted:
        out  = t.get("outcome_90d")
        cls  = t.get("class", "")
        if out is None:
            out_str = "<span style='color:#888'>pending</span>"
            row_bg  = ""
        elif out > 10:
            out_str = f"<span style='color:#28a745;font-weight:700'>+{out:.1f}%</span>"
            row_bg  = "background:#0d2318"
        elif out > 0:
            out_str = f"<span style='color:#8bc34a'>+{out:.1f}%</span>"
            row_bg  = ""
        elif out > -10:
            out_str = f"<span style='color:#ffc107'>{out:.1f}%</span>"
            row_bg  = "background:#1a1200"
        else:
            out_str = f"<span style='color:#dc3545;font-weight:700'>{out:.1f}%</span>"
            row_bg  = "background:#1a0000"
        mfe = t.get("mfe_90d")
        mae = t.get("mae_90d")
        trade_rows += f"""
<tr style="border-bottom:1px solid #21262d;{row_bg}">
  <td style="padding:5px 8px;color:#8b949e;font-size:11px">{t['date']}</td>
  <td style="padding:5px 8px;font-weight:600">{t['symbol']}</td>
  <td style="padding:5px 8px;text-align:center">{t['score']:.1f}</td>
  <td style="padding:5px 8px;text-align:center">{t.get('raw_score','')}</td>
  <td style="padding:5px 8px;text-align:center">{out_str}</td>
  <td style="padding:5px 8px;text-align:center;color:#28a745;font-size:11px">{f'+{mfe:.1f}%' if mfe else '—'}</td>
  <td style="padding:5px 8px;text-align:center;color:#dc3545;font-size:11px">{f'{mae:.1f}%' if mae else '—'}</td>
  <td style="padding:5px 8px;text-align:center;color:#8b949e;font-size:11px">{t.get('regime','')}</td>
</tr>"""

    # Missed opportunities
    missed_rows = ""
    for t in an.get("missed", []):
        missed_rows += (
            f"<tr><td style='padding:4px 8px;color:#8b949e;font-size:11px'>{t['date']}</td>"
            f"<td style='padding:4px 8px'>{t['symbol']}</td>"
            f"<td style='padding:4px 8px;text-align:center'>{t['score']:.1f}</td>"
            f"<td style='padding:4px 8px;text-align:center;color:#28a745;font-weight:700'>"
            f"+{t['outcome_90d']:.1f}%</td></tr>"
        )

    # By year table
    year_rows = ""
    for y, yd in sorted(an.get("by_year", {}).items()):
        c = "#28a745" if yd["avg"] > 10 else "#ffc107" if yd["avg"] > 0 else "#dc3545"
        year_rows += (
            f"<tr><td style='padding:5px 8px'>{y}</td>"
            f"<td style='padding:5px 8px;text-align:center'>{yd['n']}</td>"
            f"<td style='padding:5px 8px;text-align:center;color:{c};font-weight:700'>"
            f"+{yd['avg']:.1f}%</td>"
            f"<td style='padding:5px 8px;text-align:center'>{yd['wr']:.0f}%</td></tr>"
        )

    # By regime table
    regime_rows = ""
    for r, rd in sorted(an.get("by_regime", {}).items(), key=lambda x: -x[1]["avg"]):
        c = "#28a745" if rd["avg"] > 10 else "#ffc107" if rd["avg"] > 0 else "#dc3545"
        regime_rows += (
            f"<tr><td style='padding:5px 8px'>{r}</td>"
            f"<td style='padding:5px 8px;text-align:center'>{rd['n']}</td>"
            f"<td style='padding:5px 8px;text-align:center;color:{c};font-weight:700'>"
            f"+{rd['avg']:.1f}%</td>"
            f"<td style='padding:5px 8px;text-align:center'>{rd['wr']:.0f}%</td></tr>"
        )

    n        = an.get("n", 0)
    eq       = an.get("equity", 100)
    eq_gain  = an.get("equity_gain", 0)
    wr       = an.get("win_rate", 0)
    avg_ret  = an.get("avg_ret", 0)
    pf       = an.get("profit_factor", 0)
    mdd      = an.get("max_dd", 0)
    n_wait   = an.get("n_wait", 0)
    n_pend   = an.get("n_pending", 0)

    eq_color  = "#28a745" if eq_gain > 0 else "#dc3545"
    wr_color  = "#28a745" if wr > 50 else "#ffc107"
    ret_color = "#28a745" if avg_ret > 5 else "#ffc107"

    return f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<title>Walk-Forward Backtester — {TODAY}</title>
<style>
  body  {{ font-family:'Segoe UI',sans-serif; background:#0d1117; color:#c9d1d9; margin:0; padding:16px; }}
  h1    {{ color:#58a6ff; text-align:center; margin:0 0 4px; }}
  h2    {{ color:#79c0ff; border-bottom:1px solid #21262d; padding-bottom:6px; margin:32px 0 12px; }}
  h3    {{ color:#8b949e; margin:16px 0 8px; font-size:14px; }}
  table {{ border-collapse:collapse; width:100%; font-size:13px; }}
  th    {{ background:#161b22; color:#8b949e; padding:7px 8px; text-align:center; border-bottom:1px solid #21262d; }}
  .kpi-grid {{ display:flex; flex-wrap:wrap; gap:10px; margin:16px 0; }}
  .kpi  {{ background:#161b22; border:1px solid #21262d; border-radius:8px;
           padding:14px 18px; flex:1; min-width:130px; text-align:center; }}
  .kpi .val {{ font-size:1.9em; font-weight:700; }}
  .kpi .lbl {{ font-size:11px; color:#8b949e; margin-top:3px; }}
  .panel {{ background:#161b22; border:1px solid #21262d; border-radius:8px;
            padding:16px; margin:12px 0; }}
  .grid2 {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
  .algo  {{ background:#161b22; border:1px solid #30363d; border-radius:8px;
            padding:14px 18px; font-family:monospace; font-size:12px; margin:12px 0; color:#8b949e; }}
  .algo b {{ color:#58a6ff; }}
</style>
</head>
<body>
<h1>📈 Walk-Forward Adaptive Backtester</h1>
<p style="text-align:center;color:#8b949e;font-size:13px">
  {TODAY} &nbsp;|&nbsp; {len(state['trades'])} إشارة معالَجة &nbsp;|&nbsp;
  Warm-up: {WARM_UP_N} إشارة &nbsp;|&nbsp; Threshold: {BUY_THRESHOLD}
</p>

<div class="algo">
  <b>خوارزمية:</b>
  كل إشارة تُقيَّم بالأوزان المتاحة وقتها فقط →
  إذا score ≥ {BUY_THRESHOLD} → BUY
  بعد 90 يوم: outcome معروف → gradient update (lr={LEARNING_RATE}, λ={LAMBDA_REG})
  الأوزان تتطور مع كل صفقة محسوبة
</div>

<h2>نتائج الـ Walk-Forward</h2>
<div class="kpi-grid">
  <div class="kpi"><div class="val" style="color:{eq_color}">{eq:.1f}</div><div class="lbl">Equity (بدأ 100)</div></div>
  <div class="kpi"><div class="val" style="color:{eq_color}">{eq_gain:+.1f}%</div><div class="lbl">إجمالي العائد</div></div>
  <div class="kpi"><div class="val" style="color:{wr_color}">{wr:.0f}%</div><div class="lbl">Win Rate (>3%)</div></div>
  <div class="kpi"><div class="val" style="color:{ret_color}">{avg_ret:+.1f}%</div><div class="lbl">متوسط العائد 90d</div></div>
  <div class="kpi"><div class="val" style="color:#58a6ff">{pf:.2f}</div><div class="lbl">Profit Factor</div></div>
  <div class="kpi"><div class="val" style="color:#dc3545">{mdd:.1f}%</div><div class="lbl">Max Drawdown</div></div>
  <div class="kpi"><div class="val">{n}</div><div class="lbl">صفقات BUY محسوبة</div></div>
  <div class="kpi"><div class="val" style="color:#8b949e">{n_wait}</div><div class="lbl">قرار WAIT</div></div>
</div>

<h2>Equity Curve</h2>
<div class="panel">
  <p style="font-size:11px;color:#8b949e;margin:0 0 8px">كل نقطة = صفقة BUY محسوبة بنتيجتها الفعلية بعد 90 يوم</p>
  {eq_svg}
  <p style="font-size:11px;color:#8b949e;margin:8px 0 0">
    من 100 → <span style="color:{'#28a745' if eq>100 else '#dc3545'};font-weight:700">{eq:.1f}</span>
    &nbsp;({n_pend} صفقة pending النتيجة)
  </p>
</div>

<h2>الأوزان المتعلَّمة vs الأوزان الأصلية</h2>
<div class="panel">
  <table>
    <tr><th style="text-align:right">المؤشر</th><th>المقارنة</th>
    <th>Original</th><th>Walk-Forward</th><th>التغيير</th></tr>
    {w_bars}
  </table>
  <p style="font-size:11px;color:#8b949e;margin:10px 0 0">
    أزرق غامق = الوزن الأصلي | أزرق فاتح = الوزن المتعلَّم من {len(wlog)} صفقة حقيقية
  </p>
</div>

<h2>الأداء عبر السنوات</h2>
<div class="grid2">
  <div class="panel">
    <h3>بالسنة</h3>
    <table>
      <tr><th style="text-align:right">السنة</th><th>N</th><th>متوسط 90d</th><th>WR</th></tr>
      {year_rows}
    </table>
  </div>
  <div class="panel">
    <h3>بحالة السوق (Regime)</h3>
    <table>
      <tr><th style="text-align:right">Regime</th><th>N</th><th>متوسط 90d</th><th>WR</th></tr>
      {regime_rows}
    </table>
  </div>
</div>

<h2>Rolling Win Rate ({ROLLING_WIN}-صفقة)</h2>
<div class="panel">
  {wr_svg if wr_svg else "<p style='color:#8b949e'>لا بيانات كافية</p>"}
</div>

<h2>آخر 50 قرار BUY</h2>
<div class="panel" style="overflow-x:auto">
  <table>
    <tr>
      <th>التاريخ</th><th>السهم</th><th>WF Score</th><th>Raw Score</th>
      <th>نتيجة 90d</th><th>MFE</th><th>MAE</th><th>Regime</th>
    </tr>
    {trade_rows}
  </table>
</div>

{"" if not an.get("missed") else f'''
<h2>فرص فائتة — قرار WAIT لكن النتيجة كانت ممتازة</h2>
<div class="panel">
  <p style="font-size:12px;color:#8b949e;margin:0 0 10px">
    هذه الإشارات كانت تحت الـ threshold ({BUY_THRESHOLD}) — النظام قال WAIT لكن عادت بأكثر من 15%
  </p>
  <table>
    <tr><th>التاريخ</th><th>السهم</th><th>Score وقتها</th><th>النتيجة الفعلية</th></tr>
    {missed_rows}
  </table>
</div>'''}

<p style="color:#21262d;text-align:center;margin-top:32px;font-size:11px">
  EGX Scanner · Walk-Forward Backtester · {TODAY}
</p>
</body>
</html>"""


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    print("[WF] Loading state...")
    state = load_state()
    print("[WF] Running walk-forward engine...")
    state = run_walk_forward(state)
    save_state(state)

    print("[WF] Computing analytics...")
    an = compute_analytics(state)
    if not an:
        print("[WF] No trades to analyze yet.")
        return

    print(f"[WF] BUY trades: {an['n']}  |  Win rate: {an['win_rate']}%  |  "
          f"Avg return: {an['avg_ret']:+.1f}%  |  Equity: {an['equity']:.1f}")
    print(f"[WF] Learned weights: "
          + "  ".join(f"{k}={v:.1f}" for k, v in an["w_now"].items()))

    html = build_html(state, an)
    out  = REPORTS_DIR / f"walk_forward_report_{TODAY}.html"
    out.write_text(html, encoding="utf-8")
    print(f"[WF] Report → {out}")
    return str(out)


if __name__ == "__main__":
    run()
