"""
Fibonacci Execution Engine — Phase 4.

Computes per-signal Fibonacci level achievement from hist_signals historical data.
Uses mfe_40d (40-day window) for short Fib levels and mfe_252d/peak_return_1y for
full expansion levels.

Fib levels tracked:
  23.6%  — first confirmation pullback
  38.2%  — intermediate recovery
  50.0%  — mid-range target
  61.8%  — golden ratio target
  78.6%  — near full-range target
  100%   — full-range expansion

Output: fib_outcomes table in egx_research.db + summary report.
"""
import sqlite3
from datetime import datetime

DB_PATH = "egx_research.db"

FIB_LEVELS = [0.236, 0.382, 0.500, 0.618, 0.786, 1.000]
FIB_LABELS = ["23.6%", "38.2%", "50%", "61.8%", "78.6%", "100%"]

# Short-window (40d) MFE covers 23.6–38.2 reliably.
# Long-window (252d) MFE needed for 50%–100%.
# peak_return_1y is the ceiling proxy for full-range.
FIB_WINDOWS = {
    0.236: "mfe_40d",
    0.382: "mfe_40d",
    0.500: "mfe_252d",
    0.618: "mfe_252d",
    0.786: "peak_return_1y",
    1.000: "peak_return_1y",
}


def init_fib_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fib_outcomes (
            signal_id   TEXT PRIMARY KEY,
            symbol      TEXT,
            signal_date TEXT,
            adj_score   INTEGER,
            signal_class TEXT,
            fib_236     INTEGER DEFAULT 0,
            fib_382     INTEGER DEFAULT 0,
            fib_500     INTEGER DEFAULT 0,
            fib_618     INTEGER DEFAULT 0,
            fib_786     INTEGER DEFAULT 0,
            fib_100     INTEGER DEFAULT 0,
            max_fib_reached TEXT,
            days_to_peak_1y INTEGER,
            peak_return_1y  REAL,
            computed_at TEXT
        )
    """)
    conn.commit()


def _classify(adj_score):
    if adj_score is None:
        return "Unknown"
    if adj_score >= 85:
        return "Institutional Buy"
    if adj_score >= 70:
        return "Very Strong Buy"
    if adj_score >= 55:
        return "Strong Buy"
    if adj_score >= 35:
        return "Buy"
    return "Skip"


def compute_fib_outcomes(db_path: str = DB_PATH) -> dict:
    """
    Processes all hist_signals with mfe_40d populated and writes fib_outcomes.
    Returns summary dict.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    init_fib_table(conn)

    rows = conn.execute("""
        SELECT id, symbol, signal_date, adj_score, price_ok,
               mfe_40d, mae_40d, mfe_252d, mae_252d,
               peak_return_1y, days_to_peak_1y, mfe_120d
        FROM hist_signals
        WHERE price_ok = 1 AND adj_score >= 35 AND mfe_40d IS NOT NULL
    """).fetchall()

    now = datetime.now().isoformat()
    inserted = 0
    updated  = 0

    for r in rows:
        sig_id = r["id"]
        adj    = r["adj_score"] or 0
        cls    = _classify(adj)

        # resolve each Fib level against the appropriate window
        def _reached(level):
            col = FIB_WINDOWS[level]
            val = r[col]
            if val is None:
                return 0
            return 1 if float(val) >= level else 0

        fib_236 = _reached(0.236)
        fib_382 = _reached(0.382)
        fib_500 = _reached(0.500)
        fib_618 = _reached(0.618)
        fib_786 = _reached(0.786)
        fib_100 = _reached(1.000)

        # highest confirmed level
        if fib_100: max_fib = "100%"
        elif fib_786: max_fib = "78.6%"
        elif fib_618: max_fib = "61.8%"
        elif fib_500: max_fib = "50%"
        elif fib_382: max_fib = "38.2%"
        elif fib_236: max_fib = "23.6%"
        else: max_fib = "None"

        existing = conn.execute(
            "SELECT 1 FROM fib_outcomes WHERE signal_id=?", (sig_id,)
        ).fetchone()

        if existing:
            conn.execute("""
                UPDATE fib_outcomes SET
                    fib_236=?, fib_382=?, fib_500=?, fib_618=?, fib_786=?, fib_100=?,
                    max_fib_reached=?, days_to_peak_1y=?, peak_return_1y=?, computed_at=?
                WHERE signal_id=?
            """, (fib_236, fib_382, fib_500, fib_618, fib_786, fib_100,
                  max_fib, r["days_to_peak_1y"], r["peak_return_1y"], now, sig_id))
            updated += 1
        else:
            conn.execute("""
                INSERT OR IGNORE INTO fib_outcomes (
                    signal_id, symbol, signal_date, adj_score, signal_class,
                    fib_236, fib_382, fib_500, fib_618, fib_786, fib_100,
                    max_fib_reached, days_to_peak_1y, peak_return_1y, computed_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (sig_id, r["symbol"], r["signal_date"], adj, cls,
                  fib_236, fib_382, fib_500, fib_618, fib_786, fib_100,
                  max_fib, r["days_to_peak_1y"], r["peak_return_1y"], now))
            inserted += 1

    conn.commit()

    # ── Summary statistics ────────────────────────────────────────────────────
    summary_rows = conn.execute("""
        SELECT
            signal_class,
            COUNT(*) as n,
            SUM(fib_236)*100.0/COUNT(*) as rate_236,
            SUM(fib_382)*100.0/COUNT(*) as rate_382,
            SUM(fib_500)*100.0/COUNT(*) as rate_500,
            SUM(fib_618)*100.0/COUNT(*) as rate_618,
            SUM(fib_786)*100.0/COUNT(*) as rate_786,
            SUM(fib_100)*100.0/COUNT(*) as rate_100,
            AVG(days_to_peak_1y) as avg_days_peak,
            AVG(peak_return_1y)  as avg_peak1y
        FROM fib_outcomes
        GROUP BY signal_class
        ORDER BY MIN(adj_score) DESC
    """).fetchall()

    total_row = conn.execute("""
        SELECT COUNT(*) as n,
               SUM(fib_236)*100.0/COUNT(*) as rate_236,
               SUM(fib_382)*100.0/COUNT(*) as rate_382,
               SUM(fib_500)*100.0/COUNT(*) as rate_500,
               SUM(fib_618)*100.0/COUNT(*) as rate_618,
               SUM(fib_786)*100.0/COUNT(*) as rate_786,
               SUM(fib_100)*100.0/COUNT(*) as rate_100
        FROM fib_outcomes
    """).fetchone()

    conn.close()

    result = {
        "inserted": inserted,
        "updated":  updated,
        "total":    inserted + updated,
        "by_class": [dict(r) for r in summary_rows],
        "overall":  dict(total_row) if total_row else {},
    }
    return result


def print_report(summary: dict):
    print("\n" + "═" * 70)
    print("FIBONACCI EXECUTION ENGINE — OUTCOME REPORT")
    print("═" * 70)
    print(f"Signals processed: {summary['total']} "
          f"(+{summary['inserted']} new, {summary['updated']} updated)")
    ov = summary.get("overall", {})
    print(f"\nOVERALL ({ov.get('n', 0)} signals):")
    for label, key in zip(FIB_LABELS, ["rate_236","rate_382","rate_500","rate_618","rate_786","rate_100"]):
        print(f"  Fib {label:6s} reach rate: {ov.get(key, 0):.1f}%")

    print("\nBY CLASS:")
    for row in summary.get("by_class", []):
        print(f"\n  {row['signal_class']} (n={row['n']}):")
        for label, key in zip(FIB_LABELS, ["rate_236","rate_382","rate_500","rate_618","rate_786","rate_100"]):
            rate = row.get(key) or 0
            bar = "█" * int(rate / 5) + "░" * (20 - int(rate / 5))
            print(f"    Fib {label:6s} {bar} {rate:.1f}%")
        pk = row.get("avg_peak1y")
        dy = row.get("avg_days_peak")
        if pk is not None:
            print(f"    Avg peak 1y: {pk*100:.1f}% | Avg days to peak: {dy:.0f}d" if dy else f"    Avg peak 1y: {pk*100:.1f}%")
    print("═" * 70 + "\n")


if __name__ == "__main__":
    summary = compute_fib_outcomes()
    print_report(summary)
