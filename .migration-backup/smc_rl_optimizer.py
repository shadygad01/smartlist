"""
RL-light SMC Weight Optimizer.

Uses hist_signals DB data (r_90d as primary reward) to run an online
policy-gradient update on r1-r8 indicator weights + pattern_score + context.
Saves historical weight snapshots and performance history to smc_rl_weights.json.
Output: reports/smc_rl_report_{date}.html
"""
# Constitution §AUTOMATIC ARCHIVING RULE — Research only; no path to production without r1-r8 mapping
RESEARCH_ONLY_LAB = True

import json
import math
import random
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

from signal_db import DB_PATH, get_conn

REPORTS_DIR = Path("reports")
REPORTS_DIR.mkdir(exist_ok=True)
TODAY  = date.today().isoformat()
NOW    = datetime.now(timezone.utc).isoformat()

WEIGHTS_FILE = Path("smc_rl_weights.json")

# ── Indicator definitions ────────────────────────────────────────────────────
INDICATORS = {
    "r1_price":     {"name": "Price Position",   "max": 30, "current": 30},
    "r2_ob":        {"name": "OB Quality",        "max": 10, "current": 10},
    "r3_liquidity": {"name": "Liquidity Context", "max": 20, "current": 20},
    "r4_htf":       {"name": "HTF Alignment",     "max": 10, "current": 10},
    "r5_avwap":     {"name": "AVWAP Support",     "max":  8, "current":  8},
    "r6_macd":      {"name": "MACD Signal",       "max":  4, "current":  4},
    "r7_div":       {"name": "Divergence",        "max":  3, "current":  3},
    "r8_demand":    {"name": "Demand Zone",       "max": 15, "current": 15},
    "pattern_score":{"name": "Pattern Score",     "max": 20, "current": 10},
}
IND_KEYS = list(INDICATORS.keys())

# ── Hyperparameters ──────────────────────────────────────────────────────────
LEARNING_RATE   = 0.05      # per-epoch step size
EPOCHS          = 40        # gradient descent passes
REGULARIZE_W    = 0.01      # L2 reg toward current system weights
PRIMARY_PERIOD  = "r_90d"   # primary reward signal
BONUS_PERIODS   = ["r_180d", "r_252d"]
BONUS_WEIGHTS   = [0.2, 0.1]


# ── Load / save persistent weights ──────────────────────────────────────────

def load_weights() -> dict:
    """Load saved weights. Returns dict with history + current weights."""
    if WEIGHTS_FILE.exists():
        try:
            with open(WEIGHTS_FILE, encoding="utf-8") as f:
                data = json.load(f)
            print(f"[RL] Loaded {len(data.get('history', []))} historical weight snapshots")
            return data
        except Exception as exc:
            print(f"[RL] Warning loading weights file: {exc}")
    # Initialize from current system weights
    return {
        "version": 1,
        "created_at": NOW,
        "history": [],
        "current_weights": {k: INDICATORS[k]["current"] for k in IND_KEYS},
        "performance_history": [],
    }


def save_weights(data: dict) -> None:
    with open(WEIGHTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"[RL] Weights saved → {WEIGHTS_FILE}")


# ── Data loading ─────────────────────────────────────────────────────────────

def load_training_data(conn) -> list[dict]:
    """Load all hist_signals rows with indicator scores + multi-period outcomes."""
    rows = conn.execute(f"""
        SELECT hs.id, hs.symbol, hs.signal_date,
               hs.r1_price, hs.r2_ob, hs.r3_liquidity, hs.r4_htf,
               hs.r5_avwap, hs.r6_macd, hs.r7_div, hs.r8_demand,
               COALESCE(s.pattern_score, 0) as pattern_score,
               COALESCE(s.market_regime, 'range') as market_regime,
               COALESCE(s.sector, 'unknown') as sector,
               hs.{PRIMARY_PERIOD},
               hs.r_180d,
               hs.r_252d,
               hs.classification
        FROM hist_signals hs
        LEFT JOIN signals s ON s.id = hs.id
        WHERE hs.{PRIMARY_PERIOD} IS NOT NULL
          AND hs.r1_price IS NOT NULL
        ORDER BY hs.signal_date
    """).fetchall()

    cols = ["id", "symbol", "signal_date",
            "r1_price", "r2_ob", "r3_liquidity", "r4_htf",
            "r5_avwap", "r6_macd", "r7_div", "r8_demand",
            "pattern_score", "market_regime", "sector",
            "r_90d", "r_180d", "r_252d", "classification"]

    data = []
    for row in rows:
        d = dict(zip(cols, row))
        # Composite reward = primary + bonus periods
        reward = d["r_90d"]
        if d["r_180d"] is not None:
            reward += d["r_180d"] * BONUS_WEIGHTS[0]
        if d["r_252d"] is not None:
            reward += d["r_252d"] * BONUS_WEIGHTS[1]
        d["reward"] = reward
        # Normalize indicator scores to [0,1]
        d["features"] = {}
        for k in IND_KEYS:
            raw = d.get(k) or 0
            d["features"][k] = raw / INDICATORS[k]["max"]
        data.append(d)
    return data


# ── Gradient descent ──────────────────────────────────────────────────────────

def normalize_weights(w: dict) -> dict:
    """Ensure weights sum to 100."""
    total = sum(w.values())
    if total <= 0:
        return {k: 100 / len(w) for k in w}
    return {k: v / total * 100 for k, v in w.items()}


def predict(features: dict, weights: dict) -> float:
    """Weighted sum prediction (0-100 scale)."""
    return sum(features[k] * weights[k] for k in IND_KEYS)


def run_gradient_descent(data: list[dict], init_weights: dict) -> tuple[dict, list]:
    """Run N epochs of stochastic gradient descent. Returns (final_weights, loss_history)."""
    weights = {k: float(v) for k, v in init_weights.items()}
    system_weights = {k: float(INDICATORS[k]["current"]) for k in IND_KEYS}
    loss_history = []

    for epoch in range(EPOCHS):
        # Shuffle for stochastic GD
        batch = list(data)
        random.shuffle(batch)

        epoch_loss = 0.0
        for sample in batch:
            features = sample["features"]
            reward   = sample["reward"]
            pred     = predict(features, weights) / 100.0  # normalize to reward scale

            # Gradient: dL/dw_k = (pred - reward) * feature_k
            error = pred - reward
            epoch_loss += error ** 2

            # Decay learning rate
            lr = LEARNING_RATE / (1 + epoch * 0.1)

            for k in IND_KEYS:
                grad = error * features[k]
                # L2 regularization toward system weights
                reg  = REGULARIZE_W * (weights[k] - system_weights[k])
                weights[k] -= lr * (grad + reg)
                # Clip to non-negative
                weights[k] = max(0.01, weights[k])

        mse = epoch_loss / max(len(batch), 1)
        loss_history.append(round(mse, 6))
        if epoch % 10 == 0:
            print(f"  Epoch {epoch:2d}: MSE={mse:.5f}")

    # Normalize so weights sum to 100
    weights = normalize_weights(weights)
    return weights, loss_history


# ── Performance analysis ──────────────────────────────────────────────────────

def compute_performance_stats(data: list[dict], weights: dict) -> dict:
    """Compute performance metrics with the current weights."""
    predictions = []
    for sample in data:
        pred = predict(sample["features"], weights)
        predictions.append((pred, sample["r_90d"], sample.get("r_252d")))

    # Sort by predicted score — top quartile
    predictions.sort(reverse=True)
    n = len(predictions)
    top_q = predictions[:n // 4]
    bot_q = predictions[3 * n // 4:]

    top_ret = sum(p[1] for p in top_q) / len(top_q) if top_q else 0
    bot_ret = sum(p[1] for p in bot_q) / len(bot_q) if bot_q else 0
    top_wr  = sum(1 for p in top_q if p[1] > 0.03) / len(top_q) if top_q else 0
    all_wr  = sum(1 for p in predictions if p[1] > 0.03) / n if n else 0

    top_252 = [p[2] for p in top_q if p[2] is not None]
    avg_252 = sum(top_252) / len(top_252) if top_252 else None

    return {
        "n": n,
        "top_q_avg_90d": round(top_ret * 100, 2),
        "bot_q_avg_90d": round(bot_ret * 100, 2),
        "top_q_win_rate": round(top_wr * 100, 1),
        "all_win_rate":   round(all_wr * 100, 1),
        "top_q_avg_252d": round(avg_252 * 100, 2) if avg_252 is not None else None,
        "discrimination": round((top_ret - bot_ret) * 100, 2),
    }


def analyze_indicator_importance(data: list[dict], weights: dict) -> list[dict]:
    """For each indicator, compute importance via permutation test."""
    base_loss = sum(
        (predict(s["features"], weights) / 100 - s["reward"]) ** 2
        for s in data
    ) / max(len(data), 1)

    importance = []
    for k in IND_KEYS:
        # Permute this indicator's feature
        shuffled_feats = [s["features"][k] for s in data]
        random.shuffle(shuffled_feats)

        perm_loss = 0.0
        for i, sample in enumerate(data):
            feats = dict(sample["features"])
            feats[k] = shuffled_feats[i]
            pred = predict(feats, weights) / 100
            perm_loss += (pred - sample["reward"]) ** 2
        perm_loss /= max(len(data), 1)

        importance.append({
            "key":        k,
            "name":       INDICATORS[k]["name"],
            "importance": round((perm_loss - base_loss) * 100, 4),
            "weight":     round(weights[k], 2),
        })

    importance.sort(key=lambda x: -x["importance"])
    return importance


def analyze_regime_performance(data: list[dict], weights: dict) -> dict:
    """Performance breakdown by market regime."""
    regimes: dict[str, list] = {}
    for sample in data:
        regime = sample.get("market_regime") or "unknown"
        if regime not in regimes:
            regimes[regime] = []
        pred = predict(sample["features"], weights)
        regimes[regime].append((pred, sample["r_90d"]))

    results = {}
    for regime, items in regimes.items():
        rets = [x[1] for x in items]
        results[regime] = {
            "n": len(rets),
            "avg_ret_90d": round(sum(rets) / len(rets) * 100, 1),
            "win_rate": round(sum(1 for r in rets if r > 0.03) / len(rets) * 100, 1),
        }
    return results


# ── HTML Report ───────────────────────────────────────────────────────────────

def _bar(value, max_val=100, color="#58a6ff"):
    pct = min(100, value / max_val * 100)
    return f'<div style="background:#30363d;border-radius:4px;height:8px;width:100%;margin-top:4px"><div style="background:{color};height:8px;border-radius:4px;width:{pct:.1f}%"></div></div>'


def build_html(weights_data: dict, new_weights: dict, loss_history: list,
               perf_stats: dict, importance: list, regime_perf: dict,
               n_data: int) -> str:
    history = weights_data.get("history", [])
    current = weights_data.get("current_weights", {})

    # Weight comparison table
    weight_rows = ""
    for k, meta in INDICATORS.items():
        old_w = current.get(k, meta["current"])
        new_w = new_weights.get(k, old_w)
        sys_w = meta["current"]
        delta = new_w - old_w
        delta_str = f"+{delta:.1f}" if delta >= 0 else f"{delta:.1f}"
        delta_color = "#64dd17" if delta >= 0 else "#ff5252"
        weight_rows += f"""
        <tr>
          <td>{meta['name']}</td>
          <td>{meta['max']}</td>
          <td>{sys_w:.0f}</td>
          <td>{old_w:.1f}</td>
          <td style="color:{delta_color}">{new_w:.1f} ({delta_str})</td>
          <td>{_bar(new_w, 40)}</td>
        </tr>"""

    # Importance table
    imp_rows = ""
    for item in importance:
        color = "#64dd17" if item["importance"] > 0 else "#ff5252"
        imp_rows += f"""
        <tr>
          <td>{item['name']}</td>
          <td>{item['weight']:.1f}</td>
          <td style="color:{color}">{item['importance']:.4f}</td>
          <td>{_bar(max(0, item['importance']), 0.02, '#64dd17')}</td>
        </tr>"""

    # Loss curve (mini sparkline as text)
    loss_mini = " → ".join(str(x) for x in loss_history[::8])

    # Regime performance
    regime_rows = ""
    for regime, stats in sorted(regime_perf.items(), key=lambda x: -x[1]["avg_ret_90d"]):
        color = "#64dd17" if stats["avg_ret_90d"] > 10 else "#ffd600" if stats["avg_ret_90d"] > 0 else "#ff5252"
        regime_rows += f"""
        <tr>
          <td>{regime}</td>
          <td>{stats['n']}</td>
          <td style="color:{color}">{stats['avg_ret_90d']}%</td>
          <td>{stats['win_rate']}%</td>
        </tr>"""

    # History chart (last 10 snapshots)
    hist_rows = ""
    for snap in history[-10:]:
        snap_date = snap.get("date", "")
        snap_perf = snap.get("perf", {})
        top_q = snap_perf.get("top_q_avg_90d", "—")
        disc  = snap_perf.get("discrimination", "—")
        color = "#64dd17" if isinstance(top_q, (int, float)) and top_q > 15 else "#ffd600"
        hist_rows += f"""
        <tr>
          <td>{snap_date}</td>
          <td>{snap.get('n_data', '—')}</td>
          <td style="color:{color}">{top_q}%</td>
          <td>{disc}%</td>
          <td>{snap.get('epochs', '—')}</td>
        </tr>"""

    disc_color = "#64dd17" if perf_stats["discrimination"] > 5 else "#ffd600"

    if hist_rows:
        history_section = (
            "<table><tr><th>Date</th><th>Data Points</th><th>Top Q 90d</th>"
            "<th>Discrimination</th><th>Epochs</th></tr>"
            + hist_rows + "</table>"
        )
    else:
        history_section = "<p style='color:#8b949e'>No history yet — this is the first run.</p>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>SMC RL Weight Optimizer — {TODAY}</title>
<style>
  body {{ font-family:'Segoe UI',sans-serif; background:#0d1117; color:#c9d1d9; margin:0; padding:20px; }}
  h1 {{ color:#58a6ff; text-align:center; }}
  h2 {{ color:#79c0ff; border-bottom:1px solid #30363d; padding-bottom:8px; margin-top:40px; }}
  table {{ border-collapse:collapse; width:100%; margin:12px 0; font-size:13px; }}
  th {{ background:#161b22; color:#8b949e; padding:8px 10px; text-align:left; border:1px solid #30363d; }}
  td {{ padding:6px 10px; border:1px solid #30363d; }}
  .kpi-grid {{ display:flex; gap:12px; flex-wrap:wrap; margin:20px 0; }}
  .kpi {{ background:#161b22; border:1px solid #30363d; border-radius:8px; padding:16px 20px; flex:1; min-width:150px; text-align:center; }}
  .kpi .val {{ font-size:2em; font-weight:bold; }}
  .kpi .lbl {{ font-size:11px; color:#8b949e; margin-top:4px; }}
  .badge {{ display:inline-block; padding:2px 8px; border-radius:12px; font-size:11px; }}
  .green {{ background:#0d2318; color:#64dd17; }}
  .yellow {{ background:#1a1a00; color:#ffd600; }}
  .red {{ background:#1a0000; color:#ff5252; }}
  .formula-box {{ background:#161b22; border:1px solid #30363d; border-radius:8px; padding:16px; margin:16px 0; font-family:monospace; }}
</style>
</head>
<body>
<h1>🤖 SMC RL Weight Optimizer</h1>
<p style="text-align:center;color:#8b949e;">Generated: {TODAY} | Training data: {n_data} signals | Epochs: {EPOCHS} | LR: {LEARNING_RATE}</p>

<div class="kpi-grid">
  <div class="kpi">
    <div class="val" style="color:#58a6ff">{perf_stats['top_q_avg_90d']}%</div>
    <div class="lbl">Top Quartile 90d Return</div>
  </div>
  <div class="kpi">
    <div class="val" style="color:#64dd17">{perf_stats['top_q_win_rate']}%</div>
    <div class="lbl">Top Quartile Win Rate</div>
  </div>
  <div class="kpi">
    <div class="val" style="color:{disc_color}">{perf_stats['discrimination']}%</div>
    <div class="lbl">Top vs Bottom Q Spread</div>
  </div>
  <div class="kpi">
    <div class="val" style="color:#c9d1d9">{perf_stats['all_win_rate']}%</div>
    <div class="lbl">Overall Win Rate</div>
  </div>
  <div class="kpi">
    <div class="val" style="color:#79c0ff">{perf_stats.get('top_q_avg_252d', '—')}%</div>
    <div class="lbl">Top Quartile 252d Return</div>
  </div>
</div>

<div class="formula-box">
  <b style="color:#58a6ff">RL Update Rule:</b><br>
  predicted_score = Σ (w_i × normalized_score_i)<br>
  error = predicted_score − actual_return_90d<br>
  Δw_i = −lr × (error × score_i + λ × (w_i − system_w_i))<br>
  <small style="color:#8b949e">λ={REGULARIZE_W} (L2 reg toward system weights) | Reward = r_90d + 0.2×r_180d + 0.1×r_252d</small>
</div>

<h2>Weight Comparison: System → Previous → New RL</h2>
<table>
  <tr><th>Indicator</th><th>Max Score</th><th>System Weight</th><th>Previous RL</th><th>New RL Weight</th><th>Magnitude</th></tr>
  {weight_rows}
</table>

<h2>Indicator Importance (Permutation Test)</h2>
<p style="color:#8b949e">Importance = MSE increase when indicator values are randomly shuffled — higher = more critical</p>
<table>
  <tr><th>Indicator</th><th>RL Weight</th><th>Importance Score</th><th>Impact</th></tr>
  {imp_rows}
</table>

<h2>Performance by Market Regime</h2>
<table>
  <tr><th>Regime</th><th>N</th><th>Avg Return 90d</th><th>Win Rate</th></tr>
  {regime_rows}
</table>

<h2>Training Loss History</h2>
<p style="color:#8b949e">MSE over {EPOCHS} epochs: {loss_mini}</p>

<h2>Historical Weight Evolution</h2>
{history_section}

<p style="color:#30363d;text-align:center;margin-top:40px">EGX Scanner · SMC RL Optimizer · {TODAY}</p>
</body>
</html>"""


# ── Main ─────────────────────────────────────────────────────────────────────

def run():
    random.seed(42)

    conn = get_conn(DB_PATH)
    print("[RL] Loading training data...")
    data = load_training_data(conn)
    conn.close()

    if not data:
        print("[RL] No training data found — skipping")
        return

    print(f"[RL] {len(data)} training samples loaded")

    # Load persistent state
    weights_data = load_weights()
    init_weights = weights_data["current_weights"]

    # Run gradient descent
    print(f"[RL] Running {EPOCHS} epochs...")
    new_weights, loss_history = run_gradient_descent(data, init_weights)

    # Compute performance stats
    perf = compute_performance_stats(data, new_weights)
    imp  = analyze_indicator_importance(data, new_weights)
    regime_perf = analyze_regime_performance(data, new_weights)

    print(f"[RL] Top-Q 90d return: {perf['top_q_avg_90d']}%  |  discrimination: {perf['discrimination']}%")

    # Save snapshot to history
    snapshot = {
        "date":       TODAY,
        "timestamp":  NOW,
        "n_data":     len(data),
        "epochs":     EPOCHS,
        "final_weights": {k: round(v, 3) for k, v in new_weights.items()},
        "loss_final": loss_history[-1] if loss_history else None,
        "perf":       perf,
    }
    weights_data["history"].append(snapshot)
    weights_data["current_weights"] = {k: round(v, 3) for k, v in new_weights.items()}
    weights_data["last_updated"] = NOW
    weights_data["last_perf"]    = perf

    save_weights(weights_data)

    # Build HTML report
    html = build_html(
        weights_data  = weights_data,
        new_weights   = new_weights,
        loss_history  = loss_history,
        perf_stats    = perf,
        importance    = imp,
        regime_perf   = regime_perf,
        n_data        = len(data),
    )

    out = REPORTS_DIR / f"smc_rl_report_{TODAY}.html"
    out.write_text(html, encoding="utf-8")
    print(f"[RL] Report saved → {out}")
    return str(out)


if __name__ == "__main__":
    run()
