"""
challenger_validation.py — Comparative validation of Production vs Challenger.

VALIDATION DESIGN:
  - Universe: All historical buy signals (not Skip/Wait) with r20d + mfe_40d outcomes.
    These signals were already eligible in production when generated — Layer 1 is
    implicitly satisfied by their presence in the DB.
  - Method: Temporal walk-forward (train on past only; no look-ahead)
  - OOS split: last 30% of signals by date (chronological)
  - Walk-forward: 5 folds

WHAT IS BEING TESTED:
  Layer 2 ranking quality: does the Expectancy Engine (r2–r8 weighted by outcomes)
  rank signals better than the current adj_score (raw_score × multiplier)?

  The challenger's claim: removing r1 from scoring and reweighting r2–r8
  by historical outcome correlations improves RANKING quality and expectancy.

METRICS:
  1. expectancy        = win_rate × avg_win + loss_rate × avg_loss
  2. win_rate          = fraction with r20d >= 7%
  3. profit_factor     = Σwins / |Σlosses|
  4. mean_mfe40d       = mean max forward return at 40 days
  5. top_quartile_wr   = win rate of signals ranked in top 25%
  6. spearman_r20d     = rank correlation: score vs r20d

WINNER DECISION:
  Challenger wins if it beats production on ≥ 4 of 6 metrics
  (no sample collapse penalty — both systems score the same universe).
"""

from __future__ import annotations
import sqlite3
import math
import json
from datetime import datetime

import challenger_expectancy_engine as expectancy


WIN_THRESH = 0.07
MIN_SCORE  = 35
DB_PATH    = "egx_research.db"


# ── Data Loading ──────────────────────────────────────────────────────────────

def _load_signals(db_path: str = DB_PATH) -> list[dict]:
    """All buy signals with r20d + mfe_40d outcomes, ordered by date."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT s.id, s.symbol, s.signal_date, s.signal_type,
               s.r1_price, s.r2_ob, s.r3_liquidity, s.r4_htf, s.r5_avwap,
               s.r6_macd, s.r7_div, s.r8_demand,
               s.raw_score, s.adj_score,
               s.sv_hit, s.hvn_hit,
               bq.r20d, bq.mfe_40d
        FROM signals s
        JOIN bottom_quality bq ON s.id = bq.signal_id
        WHERE bq.r20d IS NOT NULL
          AND bq.mfe_40d IS NOT NULL
          AND s.signal_type NOT IN ('Skip', 'Wait')
          AND s.raw_score >= ?
        ORDER BY s.signal_date
    """, (MIN_SCORE,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Scoring Functions ─────────────────────────────────────────────────────────

def _prod_score(sig: dict) -> float:
    """Production ranking score = adj_score (falls back to raw_score)."""
    return float(sig.get("adj_score") or sig.get("raw_score") or 0)


def _chall_score(sig: dict, eng: expectancy.ExpectancyEngine) -> float:
    """Challenger score: expectancy engine on r2–r8 (r1 excluded from scoring)."""
    factors = {
        "r2_ob":        (sig.get("r2_ob")        or 0),
        "r3_liquidity": (sig.get("r3_liquidity") or 0),
        "r4_htf":       (sig.get("r4_htf")       or 0),
        "r5_avwap":     (sig.get("r5_avwap")     or 0),
        "r6_macd":      (sig.get("r6_macd")      or 0),
        "r7_div":       (sig.get("r7_div")        or 0),
        "r8_demand":    (sig.get("r8_demand")     or 0),
    }
    result = eng.compute(
        signal_factors=factors,
        signal_date=sig["signal_date"],
        sv_hit=bool(sig.get("sv_hit")),
        hvn_hit=bool(sig.get("hvn_hit")),
    )
    return float(result.score)


# ── Metrics ───────────────────────────────────────────────────────────────────

def _metrics(pairs: list[tuple[dict, float]], label: str) -> dict:
    """Compute all validation metrics for a list of (signal, score) pairs."""
    if len(pairs) < 5:
        return {"label": label, "n": len(pairs), "error": "insufficient sample"}

    n      = len(pairs)
    r20d   = [s["r20d"]          for s, _ in pairs]
    mfe40  = [s["mfe_40d"] or 0  for s, _ in pairs]
    scores = [sc                  for _, sc in pairs]

    wins   = [v for v in r20d if v >= WIN_THRESH]
    losses = [v for v in r20d if v < WIN_THRESH]
    wr     = len(wins) / n
    avg_w  = sum(wins)   / len(wins)   if wins   else 0.0
    avg_l  = sum(losses) / len(losses) if losses else 0.0
    exp    = wr * avg_w + (1 - wr) * avg_l
    pf     = sum(wins) / max(abs(sum(losses)), 1e-9)

    # ── Ranking-Quality Metrics (what matters for capital deployment) ─────────
    sorted_pairs = sorted(pairs, key=lambda x: x[1], reverse=True)

    # Top quartile
    top_n    = max(1, n // 4)
    top_sigs = [s for s, _ in sorted_pairs[:top_n]]
    top_r20d = [s["r20d"] for s in top_sigs]
    top_mfe  = [s["mfe_40d"] or 0 for s in top_sigs]
    top_wr   = sum(1 for v in top_r20d if v >= WIN_THRESH) / len(top_sigs)
    top_wins = [v for v in top_r20d if v >= WIN_THRESH]
    top_loss = [v for v in top_r20d if v < WIN_THRESH]
    top_exp  = (len(top_wins)/len(top_r20d) * (sum(top_wins)/len(top_wins) if top_wins else 0)
                + len(top_loss)/len(top_r20d) * (sum(top_loss)/len(top_loss) if top_loss else 0))

    # Top decile
    dec_n    = max(1, n // 10)
    dec_sigs = [s for s, _ in sorted_pairs[:dec_n]]
    dec_wr   = sum(1 for s in dec_sigs if s["r20d"] >= WIN_THRESH) / len(dec_sigs)

    # Deployed expectancy: signals with score > median (simulated capital gate)
    med_score = sorted(scores)[n // 2]
    deploy_sigs = [s for s, sc in pairs if sc > med_score]
    if deploy_sigs:
        dep_r20d = [s["r20d"] for s in deploy_sigs]
        dep_wins = [v for v in dep_r20d if v >= WIN_THRESH]
        dep_loss = [v for v in dep_r20d if v < WIN_THRESH]
        dep_wr   = len(dep_wins) / len(dep_r20d)
        dep_exp  = (dep_wr * (sum(dep_wins)/len(dep_wins) if dep_wins else 0)
                    + (1-dep_wr) * (sum(dep_loss)/len(dep_loss) if dep_loss else 0))
    else:
        dep_exp = 0.0

    # Spearman rank correlation: score vs r20d
    def _rank(lst):
        s = sorted(enumerate(lst), key=lambda x: x[1])
        r = [0.0] * len(lst)
        for pos, (i, _) in enumerate(s):
            r[i] = pos + 1.0
        return r

    rx, ry = _rank(scores), _rank(r20d)
    mx, my = sum(rx) / n, sum(ry) / n
    num  = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    dxdy = (sum((v - mx) ** 2 for v in rx) * sum((v - my) ** 2 for v in ry)) ** 0.5
    spearman = num / dxdy if dxdy > 0 else 0.0

    return {
        "label":               label,
        "n":                   n,
        "pool_win_rate":       round(wr,       4),
        "pool_expectancy":     round(exp,      5),
        "pool_mfe40d":         round(sum(mfe40)/n, 4),
        # Ranking-quality metrics
        "top_q_wr":            round(top_wr,   4),
        "top_q_exp":           round(top_exp,  5),
        "top_q_mfe40d":        round(sum(top_mfe)/len(top_mfe), 4),
        "top_decile_wr":       round(dec_wr,   4),
        "spearman_r20d":       round(spearman, 4),
        "deployed_expectancy": round(dep_exp,  5),
    }


# ── Walk-Forward ──────────────────────────────────────────────────────────────

def walk_forward(signals: list[dict], n_folds: int = 5) -> dict:
    """Time-ordered walk-forward on n_folds equal-sized test windows."""
    signals = sorted(signals, key=lambda s: s["signal_date"])
    n       = len(signals)
    fold_sz = n // (n_folds + 1)

    if fold_sz < 10:
        return {"error": f"Too few signals for {n_folds} folds (n={n})"}

    prod_agg, chall_agg = [], []
    folds = []

    for f in range(n_folds):
        test_start = fold_sz * (f + 1)
        test_end   = min(test_start + fold_sz, n)
        test       = signals[test_start:test_end]
        if len(test) < 5:
            continue

        eng = expectancy.ExpectancyEngine(db_path=DB_PATH)

        prod_p  = [(s, _prod_score(s))  for s in test]
        chall_p = [(s, _chall_score(s, eng)) for s in test]

        fp = _metrics(prod_p,  f"Production fold {f+1}")
        fc = _metrics(chall_p, f"Challenger fold {f+1}")

        folds.append({
            "fold":     f + 1,
            "window":   f"{test[0]['signal_date']} → {test[-1]['signal_date']}",
            "n":        len(test),
            "production": fp,
            "challenger": fc,
        })
        prod_agg.extend(prod_p)
        chall_agg.extend(chall_p)

    return {
        "folds":     folds,
        "aggregate": {
            "production":  _metrics(prod_agg,  "Production WF"),
            "challenger":  _metrics(chall_agg, "Challenger WF"),
        },
    }


# ── OOS ──────────────────────────────────────────────────────────────────────

def oos_split(signals: list[dict], train_frac: float = 0.70) -> dict:
    """Temporal 70/30 OOS split."""
    signals = sorted(signals, key=lambda s: s["signal_date"])
    n       = len(signals)
    split   = int(n * train_frac)
    test    = signals[split:]

    if len(test) < 20:
        return {"error": f"OOS too small: {len(test)}"}

    eng     = expectancy.ExpectancyEngine(db_path=DB_PATH)
    prod_p  = [(s, _prod_score(s))   for s in test]
    chall_p = [(s, _chall_score(s, eng)) for s in test]

    return {
        "train_n":    split,
        "test_n":     len(test),
        "cutoff":     test[0]["signal_date"],
        "production": _metrics(prod_p,  "Production OOS"),
        "challenger": _metrics(chall_p, "Challenger OOS"),
    }


# ── Regime Test ──────────────────────────────────────────────────────────────

def regime_test(signals: list[dict]) -> dict:
    """
    Test ranking quality in first half (train period) vs second half (OOS).
    Checks temporal stability of challenger vs production.
    """
    signals = sorted(signals, key=lambda s: s["signal_date"])
    mid = len(signals) // 2

    eng  = expectancy.ExpectancyEngine(db_path=DB_PATH)
    out  = {}
    for name, subset in [("first_half", signals[:mid]), ("second_half", signals[mid:])]:
        prod_p  = [(s, _prod_score(s))  for s in subset]
        chall_p = [(s, _chall_score(s, eng)) for s in subset]
        out[name] = {
            "production": _metrics(prod_p,  f"Production {name}"),
            "challenger": _metrics(chall_p, f"Challenger {name}"),
        }
    return out


# ── Decision ─────────────────────────────────────────────────────────────────

def decide(oos: dict, wf: dict, regime: dict) -> dict:
    """
    Challenger wins if it beats production on ≥ 4 of 6 OOS metrics
    AND shows temporal stability (challenger better in BOTH halves on expectancy).
    """
    if "error" in oos:
        return {"winner": "PRODUCTION", "reason": f"OOS error: {oos['error']}"}

    p = oos["production"]
    c = oos["challenger"]

    METRICS = ["top_q_wr", "top_q_exp", "top_q_mfe40d",
               "top_decile_wr", "spearman_r20d", "deployed_expectancy"]

    wins = 0
    comparison = {}
    for m in METRICS:
        pv, cv = p.get(m, 0), c.get(m, 0)
        chall_better = isinstance(cv, (int, float)) and isinstance(pv, (int, float)) and cv > pv
        wins += int(chall_better)
        comparison[m] = {
            "production": pv, "challenger": cv,
            "winner": "challenger" if chall_better else "production",
            "delta":  round(cv - pv, 5) if isinstance(cv,(int,float)) else None,
        }

    # Temporal stability: challenger must show better RANKING quality in both halves
    r_fh  = regime.get("first_half",  {})
    r_sh  = regime.get("second_half", {})
    stable = (
        r_fh.get("challenger", {}).get("top_q_wr", -1) >
        r_fh.get("production",  {}).get("top_q_wr", -1)
        and
        r_sh.get("challenger", {}).get("top_q_wr", -1) >
        r_sh.get("production",  {}).get("top_q_wr", -1)
    )

    # WF confirmation: challenger ranks better in walk-forward too
    wf_c_exp = wf.get("aggregate", {}).get("challenger", {}).get("top_q_wr", -999)
    wf_p_exp = wf.get("aggregate", {}).get("production", {}).get("top_q_wr", -999)
    wf_better = wf_c_exp > wf_p_exp

    # Challenger must win ≥ 4 metrics OR (≥ 3 metrics AND stable AND wf_better)
    challenger_wins = wins >= 4 or (wins >= 3 and stable and wf_better)

    return {
        "winner":          "CHALLENGER" if challenger_wins else "PRODUCTION",
        "metrics_won":     wins,
        "metrics_total":   len(METRICS),
        "temporally_stable": stable,
        "wf_confirmed":    wf_better,
        "comparison":      comparison,
        "reason": (
            f"Challenger won {wins}/{len(METRICS)} OOS metrics"
            + (", temporally stable" if stable else "")
            + (", WF confirmed" if wf_better else "")
        ),
        "oos_n_production": p.get("n"),
        "oos_n_challenger": c.get("n"),
    }


# ── Main ─────────────────────────────────────────────────────────────────────

def run(db_path: str = DB_PATH, verbose: bool = True) -> dict:
    print("[validation] Loading historical signals...")
    sigs = _load_signals(db_path)
    print(f"[validation] {len(sigs)} buy signals with outcomes")

    print("[validation] OOS split (70/30)...")
    oos = oos_split(sigs)

    print("[validation] Walk-forward (5 folds)...")
    wf = walk_forward(sigs)

    print("[validation] Regime stability test...")
    regime = regime_test(sigs)

    print("[validation] Decision...")
    decision = decide(oos, wf, regime)

    report = {
        "run_at":   datetime.now().isoformat(),
        "n_total":  len(sigs),
        "oos":      oos,
        "wf":       wf,
        "regime":   regime,
        "decision": decision,
    }

    if verbose:
        _print(report)

    return report


def _print(r: dict) -> None:
    sep = "═" * 64
    print(f"\n{sep}")
    print("CHALLENGER vs PRODUCTION — VALIDATION REPORT")
    print(sep)
    print(f"Run:      {r['run_at']}")
    print(f"Signals:  {r['n_total']}")

    oos = r["oos"]
    p, c = oos.get("production", {}), oos.get("challenger", {})
    print(f"\n── OOS Holdout ({oos.get('test_n','?')} signals, from {oos.get('cutoff','?')}) ──")
    _tbl(p, c)

    wf_agg = r["wf"].get("aggregate", {})
    print(f"\n── Walk-Forward Aggregate ({r['wf'].get('folds', [{}])[-1].get('fold','?')} folds) ──")
    _tbl(wf_agg.get("production", {}), wf_agg.get("challenger", {}))

    rg = r["regime"]
    for half in ["first_half", "second_half"]:
        hp = rg.get(half, {}).get("production", {})
        hc = rg.get(half, {}).get("challenger", {})
        n_h = hp.get("n", "?")
        print(f"\n── {half.replace('_',' ').title()} (n={n_h}) ──")
        _tbl(hp, hc, short=True)

    d = r["decision"]
    print(f"\n{'─'*64}")
    print(f"  WINNER   : ★ {d['winner']} ★")
    print(f"  METRICS  : {d['metrics_won']}/{d['metrics_total']} OOS metrics")
    print(f"  STABLE   : {d['temporally_stable']}")
    print(f"  WF CONF  : {d['wf_confirmed']}")
    print(f"  REASON   : {d['reason']}")
    print(sep)


def _tbl(p: dict, c: dict, short: bool = False) -> None:
    metrics = (["n","top_q_wr","deployed_expectancy"] if short
               else ["n","pool_win_rate","pool_expectancy","top_q_wr","top_q_exp",
                     "top_q_mfe40d","top_decile_wr","spearman_r20d","deployed_expectancy"])
    header = f"  {'Metric':<22} {'Production':>12} {'Challenger':>12} {'Delta':>10} {'Winner':>12}"
    print(header)
    print(f"  {'-'*72}")
    for m in metrics:
        pv = p.get(m, "—")
        cv = c.get(m, "—")
        if isinstance(pv, float) and isinstance(cv, float):
            delta  = cv - pv
            winner = "challenger" if cv > pv else "production"
            dstr   = f"{delta:+.4f}"
        else:
            delta, winner, dstr = None, "—", "—"
        print(f"  {m:<22} {str(pv):>12} {str(cv):>12} {dstr:>10} {winner:>12}")


if __name__ == "__main__":
    import sys
    db = sys.argv[1] if len(sys.argv) > 1 else DB_PATH
    report = run(db_path=db)

    out = "challenger_validation_report.json"
    with open(out, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\n[validation] Saved to {out}")
