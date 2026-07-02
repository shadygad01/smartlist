"""
early_buy_tracker.py — Research Shadow Tracking for EARLY BUY signals.

RESEARCH ONLY. Does not affect production entry decisions, open_positions,
portfolio, or performance metrics.

Rule for EARLY BUY classification:
    signal == "Wait"  AND  r1 > 0  AND  raw_score >= 65

Promotion policy (auto-promotion to production is NOT implemented here):
    N >= 100
    AND WR >= BUY WR
    AND Expectancy >= BUY Expectancy
    AND Sharpe >= BUY Sharpe
    AND OOS validation passes
    AND Walk-forward validation passes
    AND Results stable across time periods

Auto-disable policy:
    OOS deterioration OR Expectancy deterioration OR WF failure OR instability
    → disabled=1, historical records preserved
"""

import sqlite3
import json
from datetime import datetime, date

DB_PATH = "egx_research.db"
WIN_THRESH = 0.07
MIN_N_PROMOTION = 100


# ─────────────────────────────────────────────────────────────────────────────
# LOG
# ─────────────────────────────────────────────────────────────────────────────

def log_early_buy_signal(symbol: str, signal_date: str, result: dict) -> bool:
    """
    Log a new EARLY BUY research signal.
    Called from main.py after classification when early_buy_research=True.
    Returns True if newly inserted, False if already exists.
    """
    signal_id = f"{symbol}_{signal_date}"
    conn = sqlite3.connect(DB_PATH)
    try:
        price = result.get("price")
        target = round(price * 1.12, 2) if price else None
        r1 = result.get("r1", 0)
        w_price = result.get("price_gate", 0)
        # r1_frac: r1 / W_PRICE (current scale)
        r1_frac = round(r1 / w_price, 4) if w_price and w_price > 0 else None

        conn.execute("""
            INSERT OR IGNORE INTO early_buy_research
            (signal_id, symbol, signal_date, raw_score, adj_score, r1_price, r1_frac,
             price, target, logged_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (
            signal_id, symbol, signal_date,
            result.get("raw_score"), result.get("score"),
            r1, r1_frac, price, target,
            datetime.utcnow().isoformat()
        ))
        inserted = conn.total_changes > 0
        conn.commit()
        return inserted
    except Exception as e:
        print(f"[EarlyBuy] log error for {signal_id}: {e}")
        return False
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# OUTCOME ENRICHMENT
# ─────────────────────────────────────────────────────────────────────────────

def enrich_outcomes() -> int:
    """
    Join early_buy_research with bottom_quality to fill in outcome fields.
    Returns number of records updated.
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        updated = conn.execute("""
            UPDATE early_buy_research
            SET
                r20d           = (SELECT b.r20d FROM bottom_quality b
                                  JOIN signals s ON s.id = b.signal_id
                                  WHERE s.symbol = early_buy_research.symbol
                                    AND s.signal_date = early_buy_research.signal_date
                                  LIMIT 1),
                mfe_40d        = (SELECT b.mfe_40d FROM bottom_quality b
                                  JOIN signals s ON s.id = b.signal_id
                                  WHERE s.symbol = early_buy_research.symbol
                                    AND s.signal_date = early_buy_research.signal_date
                                  LIMIT 1),
                mae_40d        = (SELECT b.mae_40d FROM bottom_quality b
                                  JOIN signals s ON s.id = b.signal_id
                                  WHERE s.symbol = early_buy_research.symbol
                                    AND s.signal_date = early_buy_research.signal_date
                                  LIMIT 1),
                peak_return_1y = (SELECT b.peak_return_1y FROM bottom_quality b
                                  JOIN signals s ON s.id = b.signal_id
                                  WHERE s.symbol = early_buy_research.symbol
                                    AND s.signal_date = early_buy_research.signal_date
                                  LIMIT 1),
                outcome_date   = (SELECT s.signal_date FROM signals s
                                  JOIN bottom_quality b ON s.id = b.signal_id
                                  WHERE s.symbol = early_buy_research.symbol
                                    AND s.signal_date = early_buy_research.signal_date
                                  LIMIT 1)
            WHERE mfe_40d IS NULL
              AND disabled = 0
        """).rowcount
        conn.commit()
        return updated
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# PERFORMANCE SNAPSHOT
# ─────────────────────────────────────────────────────────────────────────────

def snapshot_performance() -> dict:
    """
    Compute current EARLY BUY performance metrics and log a snapshot.
    Returns metrics dict.
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        # BUY baseline from production signals
        buy_row = conn.execute("""
            SELECT
                AVG(CASE WHEN b.mfe_40d >= ? THEN 1.0 ELSE 0.0 END) as buy_wr,
                AVG(b.mfe_40d) as buy_exp
            FROM signals s
            JOIN bottom_quality b ON s.id = b.signal_id
            WHERE s.price_ok = 1
              AND b.mfe_40d IS NOT NULL
        """, (WIN_THRESH,)).fetchone()
        buy_wr  = buy_row[0] or 0
        buy_exp = buy_row[1] or 0

        # EARLY BUY metrics
        rows = conn.execute("""
            SELECT mfe_40d FROM early_buy_research
            WHERE mfe_40d IS NOT NULL AND disabled = 0
        """).fetchall()
        mfes = [r[0] for r in rows]

        n_total   = conn.execute("SELECT COUNT(*) FROM early_buy_research WHERE disabled=0").fetchone()[0]
        n_outcome = len(mfes)

        if n_outcome < 5:
            metrics = {
                "n_total": n_total, "n_outcome": n_outcome,
                "win_rate": None, "expectancy": None, "sharpe": None,
                "buy_wr": buy_wr, "buy_exp": buy_exp,
                "meets_promotion": False,
                "note": f"Insufficient outcomes ({n_outcome} < 5)"
            }
        else:
            import statistics, math
            wins    = sum(1 for m in mfes if m >= WIN_THRESH)
            wr      = wins / n_outcome
            exp     = statistics.mean(mfes)
            std     = statistics.stdev(mfes) if n_outcome > 1 else 0
            sharpe  = (exp / std * math.sqrt(12)) if std > 0 else 0

            meets = (
                n_total >= MIN_N_PROMOTION
                and wr   >= buy_wr
                and exp  >= buy_exp
            )
            metrics = {
                "n_total": n_total, "n_outcome": n_outcome,
                "win_rate": round(wr, 4), "expectancy": round(exp, 4), "sharpe": round(sharpe, 3),
                "buy_wr": round(buy_wr, 4), "buy_exp": round(buy_exp, 4),
                "meets_promotion": meets,
                "note": "OK"
            }

        # Log snapshot
        conn.execute("""
            INSERT INTO early_buy_performance_log
            (snapshot_date, n_total, n_with_outcome, win_rate, expectancy, sharpe,
             buy_wr_at_time, buy_exp_at_time, meets_promotion_criteria, note)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (
            date.today().isoformat(),
            metrics["n_total"], metrics["n_outcome"],
            metrics.get("win_rate"), metrics.get("expectancy"), metrics.get("sharpe"),
            metrics["buy_wr"], metrics["buy_exp"],
            int(metrics["meets_promotion"]),
            metrics["note"]
        ))
        conn.commit()
        return metrics
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# AUTO-DISABLE CHECK
# ─────────────────────────────────────────────────────────────────────────────

def check_auto_disable() -> bool:
    """
    Evaluate whether EARLY BUY research should be disabled.
    Criteria: consistent OOS deterioration vs BUY baseline across last 3 snapshots.
    Returns True if disabled, False if still active.
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        snaps = conn.execute("""
            SELECT win_rate, buy_wr_at_time FROM early_buy_performance_log
            WHERE win_rate IS NOT NULL
            ORDER BY snapshot_date DESC LIMIT 3
        """).fetchall()

        if len(snaps) < 3:
            return False  # not enough history to evaluate

        # Disable if EARLY BUY WR < BUY WR in all 3 recent snapshots
        deteriorated = all(s[0] < s[1] for s in snaps)
        if deteriorated:
            conn.execute("""
                UPDATE early_buy_research
                SET disabled=1,
                    disable_reason='Auto-disabled: OOS WR < BUY WR in 3 consecutive snapshots'
                WHERE disabled=0
            """)
            conn.commit()
            print("[EarlyBuy] AUTO-DISABLED: consistent OOS deterioration detected.")
            return True
        return False
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# DAILY RUN
# ─────────────────────────────────────────────────────────────────────────────

def daily_run(results: dict = None, signal_date: str = None) -> dict:
    """
    Main entry point — called from main.py workflow.
    1. Log any new EARLY BUY signals from today's scan.
    2. Enrich outcomes from bottom_quality.
    3. Snapshot performance.
    4. Check auto-disable.
    Returns performance metrics dict.
    """
    logged = 0
    if results and signal_date:
        from main import STOCKS  # avoid circular import at module level
        for sym in STOCKS:
            r = results.get(sym, {})
            if r.get("ok") and r.get("early_buy_research"):
                if log_early_buy_signal(sym, signal_date, r):
                    logged += 1
                    print(f"[EarlyBuy] Logged: {sym} {signal_date} score={r.get('raw_score')}")

    enriched = enrich_outcomes()
    metrics  = snapshot_performance()
    disabled = check_auto_disable()

    print(
        f"[EarlyBuy] daily_run: logged={logged} enriched={enriched} "
        f"n={metrics['n_total']} outcomes={metrics['n_outcome']} "
        f"WR={metrics.get('win_rate')} Exp={metrics.get('expectancy')} "
        f"disabled={disabled}"
    )
    return metrics


# ─────────────────────────────────────────────────────────────────────────────
# REPORT
# ─────────────────────────────────────────────────────────────────────────────

def get_report() -> str:
    """Return a compact text report of EARLY BUY research status."""
    m = snapshot_performance()
    lines = [
        "═══ EARLY BUY RESEARCH STATUS ═══",
        f"N (total logged):  {m['n_total']}",
        f"N (with outcomes): {m['n_outcome']}",
        f"Win Rate:          {m['win_rate']:.4f}" if m.get('win_rate') else "Win Rate:          —",
        f"Expectancy:        {m['expectancy']:.4f}" if m.get('expectancy') else "Expectancy:        —",
        f"Sharpe:            {m['sharpe']:.3f}" if m.get('sharpe') else "Sharpe:            —",
        "───",
        f"BUY WR (baseline): {m['buy_wr']:.4f}",
        f"BUY Exp (baseline):{m['buy_exp']:.4f}",
        "───",
        f"Meets promotion:   {'YES — review manually' if m['meets_promotion'] else 'NO'}",
        f"Promotion req:     N>={MIN_N_PROMOTION}, WR>=BUY WR, Exp>=BUY Exp,",
        "                   Sharpe>=BUY Sharpe, OOS+WF pass",
        "═══════════════════════════════════",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    enrich_outcomes()
    print(get_report())
