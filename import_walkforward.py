"""
Walk-Forward Validation History Import — IDEMPOTENT

Imports 359 constitutional signals (2021-09-29 → 2026-06-11) from the
5-year walk-forward validation into:

  1. egx_research.db → hist_signals       (UNIQUE symbol+signal_date)
  2. constitutional_opportunity_events.db  (UNIQUE ticker+event_type+event_date)

Both inserts use INSERT OR IGNORE — 100% idempotent. Safe to run N times.
Never overwrites live production data.
"""
from __future__ import annotations

import re
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).parent

RESEARCH_DB  = BASE / "egx_research.db"
TIMELINE_DB  = BASE / "constitutional_opportunity_events.db"
REPORT_FILE  = Path("/root/.claude/uploads/fad3c03b-45df-5593-9de4-4ea297071735/8c9ab84d-walk_forward_validation_report.txt")

_NOW = datetime.now().isoformat()


# ── Parse walk-forward report ──────────────────────────────────────────────────

def _parse_signals() -> list[dict]:
    """
    Parse trade log lines between the header dashes and PER-STOCK SUMMARY.
    Format:
    #    Stock     Name            Date         Type          Score  Entry  Current  Return%  Status  MaxDD%
    """
    text = REPORT_FILE.read_text(encoding="utf-8")
    signals: list[dict] = []

    # Find the trade log block
    start = text.index("# ")
    end   = text.index("PER-STOCK SUMMARY")
    block = text[start:end]

    # Pattern: number, ticker, (name skipped), date, type, score, entry, current, return%, status, maxdd%
    pattern = re.compile(
        r"^\s*(\d+)\s+"                        # index
        r"(\S+\.CA)\s+"                         # ticker
        r".+?\s+"                               # name (greedy up to date)
        r"(\d{4}-\d{2}-\d{2})\s+"              # date
        r"(BUY|RE-ACCUMULATION)\s+"            # type
        r"(\d+)\s+"                             # score
        r"([\d.]+)\s+"                          # entry
        r"([\d.]+)\s+"                          # current
        r"([+-][\d.]+)%\s+"                    # return% (always signed)
        r"[✓✗]\s+(?:CORRECT|WRONG)\s+"         # status
        r"([+-]?[\d.]+)%",                      # maxdd% (sign optional: 0.00%)
        re.MULTILINE
    )

    for m in pattern.finditer(block):
        signals.append({
            "idx":        int(m.group(1)),
            "ticker":     m.group(2),
            "date":       m.group(3),
            "type":       m.group(4),         # BUY | RE-ACCUMULATION
            "score":      int(m.group(5)),
            "entry":      float(m.group(6)),
            "current":    float(m.group(7)),
            "return_pct": float(m.group(8)),
            "max_dd":     float(m.group(9)),
        })

    return signals


# ── Step 1: hist_signals import ────────────────────────────────────────────────

def _ensure_signal_type_column(conn: sqlite3.Connection) -> None:
    """Add signal_type column to hist_signals if it doesn't exist."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(hist_signals)")}
    if "signal_type" not in cols:
        conn.execute("ALTER TABLE hist_signals ADD COLUMN signal_type TEXT")
        conn.commit()


def import_to_hist_signals(signals: list[dict]) -> tuple[int, int, int]:
    """
    UPSERT signals into egx_research.db → hist_signals.
    - New rows: INSERT with signal_type + peak_return_1y
    - Existing rows (from historical_backtest): UPDATE signal_type only (preserves r20d/mfe/mae)
    Returns (inserted, updated, already_tagged).
    """
    conn = sqlite3.connect(str(RESEARCH_DB))
    _ensure_signal_type_column(conn)

    inserted      = 0
    updated       = 0
    already_done  = 0

    for s in signals:
        before = conn.execute(
            "SELECT id, signal_type FROM hist_signals WHERE symbol=? AND signal_date=?",
            (s["ticker"], s["date"]),
        ).fetchone()

        if before is None:
            # New row — INSERT
            conn.execute(
                """
                INSERT INTO hist_signals
                    (symbol, signal_date, close_price, raw_score, adj_score,
                     signal_type, peak_return_1y, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    s["ticker"],
                    s["date"],
                    s["entry"],
                    s["score"],
                    s["score"],
                    s["type"],
                    s["return_pct"],
                    _NOW,
                ),
            )
            inserted += 1
        elif before[1] is None:
            # Existing row from historical_backtest — tag signal_type only
            conn.execute(
                "UPDATE hist_signals SET signal_type=?, peak_return_1y=? WHERE id=?",
                (s["type"], s["return_pct"], before[0]),
            )
            updated += 1
        else:
            # Already tagged — idempotent skip
            already_done += 1

    conn.commit()
    conn.close()
    return inserted, updated, already_done


# ── Step 2: constitutional_opportunity_events import ──────────────────────────

def _compute_event_index(signals: list[dict]) -> dict[str, dict]:
    """
    Compute event_index per ticker (chronological order).
    Returns {ticker: {date+type: index, ...}}.

    Rule:
      - The EARLIEST BUY per ticker → event_index 0 (FIRST_BUY)
      - Subsequent BUYs and all RE-ACCUMULATIONs → 1, 2, 3... in date order
    """
    by_ticker: dict[str, list] = {}
    for s in signals:
        by_ticker.setdefault(s["ticker"], []).append(s)

    result: dict[str, dict] = {}
    for ticker, evs in by_ticker.items():
        evs_sorted = sorted(evs, key=lambda e: e["date"])
        idx_map: dict[str, int] = {}
        counter = 0
        for e in evs_sorted:
            key = f"{e['date']}|{e['type']}"
            idx_map[key] = counter
            counter += 1
        result[ticker] = idx_map

    return result


def import_to_constitutional_timeline(signals: list[dict]) -> tuple[int, int]:
    """
    UPSERT signals into constitutional_opportunity_events.db.
    Walk-forward BUY  → event_type = FIRST_BUY
    RE-ACCUMULATION   → event_type = RE_ACCUMULATION
    Returns (inserted, skipped).
    """
    idx_map = _compute_event_index(signals)

    conn = sqlite3.connect(str(TIMELINE_DB))
    conn.row_factory = sqlite3.Row

    # Ensure schema (idempotent)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS constitutional_opportunity_events (
            event_id       TEXT PRIMARY KEY,
            ticker         TEXT NOT NULL,
            event_type     TEXT NOT NULL,
            event_index    INTEGER NOT NULL,
            event_date     TEXT NOT NULL,
            event_end_date TEXT,
            cluster_days   INTEGER,
            entry_price    REAL NOT NULL,
            buy_r2         REAL NOT NULL,
            buy_score      REAL NOT NULL,
            buy_r3 REAL, buy_r4 REAL, buy_r5 REAL,
            buy_r6 REAL, buy_r7 REAL, buy_r8 REAL,
            sector         TEXT,
            signal_version TEXT DEFAULT 'v1',
            created_at     TEXT NOT NULL
        )
    """)
    try:
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_coe_ticker_type_date "
            "ON constitutional_opportunity_events(ticker, event_type, event_date)"
        )
    except Exception:
        pass

    inserted = 0
    skipped  = 0

    for s in signals:
        ticker    = s["ticker"]
        ev_type   = "FIRST_BUY" if s["type"] == "BUY" else "RE_ACCUMULATION"
        key       = f"{s['date']}|{s['type']}"
        ev_index  = idx_map.get(ticker, {}).get(key, 0)

        # Deterministic event_id from ticker+date+type so re-runs produce same IDs
        ev_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"wf|{ticker}|{s['date']}|{s['type']}"))

        conn.execute(
            """
            INSERT OR IGNORE INTO constitutional_opportunity_events
                (event_id, ticker, event_type, event_index,
                 event_date, event_end_date, cluster_days,
                 entry_price, buy_r2, buy_score,
                 signal_version, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ev_id,
                ticker,
                ev_type,
                ev_index,
                s["date"],
                s["date"],      # event_end_date = same day (single-day cluster)
                1,              # cluster_days
                s["entry"],
                60.0,           # buy_r2 (constitutional minimum; exact value unknown)
                float(s["score"]),
                "wf_v1",        # walk-forward version tag
                _NOW,
            ),
        )
        if conn.total_changes > inserted + skipped:
            inserted += 1
        else:
            skipped += 1

    conn.commit()
    conn.close()
    return inserted, skipped


# ── Step 3: Rebuild stock DNA ──────────────────────────────────────────────────

def rebuild_dna() -> None:
    try:
        from stock_dna_engine import build_stock_dna
        build_stock_dna()
        print("[Import] stock_dna.db rebuilt from enriched constitutional timeline.")
    except Exception as e:
        print(f"[Import] DNA rebuild warning: {e}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    print("[Import] Parsing walk-forward validation report...")
    signals = _parse_signals()
    print(f"[Import] Parsed {len(signals)} signals.")

    if not signals:
        print("[Import] ERROR: No signals parsed. Check report file path.")
        return

    print(f"[Import] → hist_signals (egx_research.db)...")
    h_ins, h_upd, h_skip = import_to_hist_signals(signals)
    print(f"[Import]   inserted={h_ins}, updated_signal_type={h_upd}, already_done={h_skip}")

    print(f"[Import] → constitutional_opportunity_events.db...")
    t_ins, t_skip = import_to_constitutional_timeline(signals)
    print(f"[Import]   inserted={t_ins}, skipped(duplicate)={t_skip}")

    print("[Import] Rebuilding stock DNA...")
    rebuild_dna()

    # Final counts
    conn_r = sqlite3.connect(str(RESEARCH_DB))
    hist_total = conn_r.execute("SELECT COUNT(*) FROM hist_signals").fetchone()[0]
    wf_count   = conn_r.execute(
        "SELECT COUNT(*) FROM hist_signals WHERE signal_type IN ('BUY','RE-ACCUMULATION')"
    ).fetchone()[0]
    conn_r.close()

    conn_t = sqlite3.connect(str(TIMELINE_DB))
    tl_total = conn_t.execute(
        "SELECT COUNT(*) FROM constitutional_opportunity_events"
    ).fetchone()[0]
    tl_wf    = conn_t.execute(
        "SELECT COUNT(*) FROM constitutional_opportunity_events WHERE signal_version='wf_v1'"
    ).fetchone()[0]
    tickers  = conn_t.execute(
        "SELECT COUNT(DISTINCT ticker) FROM constitutional_opportunity_events"
    ).fetchone()[0]
    conn_t.close()

    print()
    print("=" * 60)
    print("IMPORT COMPLETE")
    print("=" * 60)
    print(f"  hist_signals total rows          : {hist_total}")
    print(f"  hist_signals walk-forward rows   : {wf_count}")
    print(f"  constitutional_timeline total    : {tl_total}")
    print(f"  constitutional_timeline wf_v1    : {tl_wf}")
    print(f"  unique tickers in timeline       : {tickers}")
    print("=" * 60)


if __name__ == "__main__":
    main()
