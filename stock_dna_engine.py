"""
Stock DNA Engine — builds stock_dna.db from the constitutional timeline.
Uses the timeline engine (same data as presentation_snapshot) for current prices.
Read-only source. No signal engine modification.
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from statistics import mean

BASE = Path(__file__).parent
_DNA_DB = BASE / "stock_dna.db"


def _get_timeline() -> list[dict]:
    """Load constitutional timeline (same source as presentation_snapshot)."""
    sys.path.insert(0, str(BASE))
    try:
        from constitutional_timeline_engine import get_timeline
        return get_timeline()
    except Exception as e:
        print(f"[StockDNA] Failed to load timeline: {e}")
        return []


def build_stock_dna() -> None:
    """Read constitutional timeline, build stock_dna.db"""
    tl = _get_timeline()
    if not tl:
        print("[StockDNA] No timeline events — nothing to build.")
        return

    # Group by ticker
    by_ticker: dict[str, list] = {}
    for e in tl:
        by_ticker.setdefault(e["ticker"], []).append(e)

    dna_rows = []
    for ticker, events in by_ticker.items():
        events.sort(key=lambda e: e["event_date"])
        first   = events[0]
        buys    = [e for e in events if e["event_type"] == "FIRST_BUY"]
        re_acc  = [e for e in events if e["event_type"] == "RE_ACCUMULATION"]
        prices  = [e["entry_price"] for e in events if e.get("entry_price")]
        returns = [e["return_pct"] for e in events if "return_pct" in e]

        avg_entry = mean(prices) if prices else 0.0
        avg_ret   = mean(returns) if returns else 0.0
        best_ret  = max(returns) if returns else 0.0
        zone_low  = min(prices) if prices else 0.0
        zone_high = max(prices) if prices else 0.0

        buy_count = len(buys)
        re_count  = len(re_acc)
        mem_hits  = len(events)

        if buy_count >= 3:
            confidence = "STRONG"
        elif buy_count >= 2:
            confidence = "CONFIRMED"
        else:
            confidence = "DEVELOPING"

        current_price = events[-1].get("current_price", 0.0) or 0.0

        dna_rows.append((
            ticker,
            first["event_date"],
            first["entry_price"],
            buy_count,
            re_count,
            round(avg_entry, 4),
            round(current_price, 4),
            round(avg_ret, 4),
            round(best_ret, 4),
            round(zone_low, 4),
            round(zone_high, 4),
            mem_hits,
            confidence,
            datetime.now().isoformat(),
        ))

    conn = sqlite3.connect(str(_DNA_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS stock_dna (
            ticker TEXT PRIMARY KEY,
            first_buy_date TEXT,
            first_buy_price REAL,
            buy_count INTEGER,
            re_accum_count INTEGER,
            avg_entry_price REAL,
            current_price REAL,
            avg_return_pct REAL,
            best_return_pct REAL,
            historical_buy_zone_low REAL,
            historical_buy_zone_high REAL,
            memory_hits INTEGER,
            memory_confidence TEXT,
            last_updated TEXT
        )
    """)
    conn.executemany(
        "INSERT OR REPLACE INTO stock_dna VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        dna_rows
    )
    conn.commit()
    conn.close()
    print(f"[StockDNA] Built stock_dna.db — {len(dna_rows)} tickers.")


if __name__ == "__main__":
    build_stock_dna()
