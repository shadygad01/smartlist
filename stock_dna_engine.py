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
    """Read constitutional timeline + full universe, build stock_dna.db with 27 rows."""
    from config.scanner_config import get_constitutional_universe
    universe = get_constitutional_universe()

    tl = _get_timeline()

    # Group timeline by ticker
    by_ticker: dict[str, list] = {}
    for e in tl:
        by_ticker.setdefault(e["ticker"], []).append(e)

    # Try to get current prices from universe_snapshot for non-timeline tickers
    snap_prices: dict[str, float] = {}
    snap_entries: dict[str, float] = {}
    try:
        from universe_snapshot import load_universe_snapshot
        for row in load_universe_snapshot():
            if row.get("current_price"):
                snap_prices[row["ticker"]] = row["current_price"]
            if row.get("constitutional_entry_price"):
                snap_entries[row["ticker"]] = row["constitutional_entry_price"]
    except Exception:
        pass

    dna_rows = []
    now_str = datetime.now().isoformat()

    for ticker in universe:
        if ticker in by_ticker:
            events = sorted(by_ticker[ticker], key=lambda e: e["event_date"])
            first   = events[0]
            buys    = [e for e in events if e["event_type"] == "FIRST_BUY"]
            re_acc  = [e for e in events if e["event_type"] == "RE_ACCUMULATION"]
            prices  = [e["constitutional_entry_price"] for e in events if e.get("constitutional_entry_price")]
            returns = [e["return_pct"] for e in events if "return_pct" in e]

            avg_entry = mean(prices) if prices else 0.0
            avg_ret   = mean(returns) if returns else 0.0
            best_ret  = max(returns) if returns else 0.0
            worst_ret = min(returns) if returns else 0.0
            zone_low  = min(prices) if prices else 0.0
            zone_high = max(prices) if prices else 0.0
            last_event_date = events[-1]["event_date"]

            buy_count = len(buys)
            re_count  = len(re_acc)
            constitutional_memory_hits  = len(events)

            if buy_count >= 3:
                confidence = "STRONG"
            elif buy_count >= 2:
                confidence = "CONFIRMED"
            else:
                confidence = "DEVELOPING"

            current_price = events[-1].get("current_price", 0.0) or 0.0
            if not current_price:
                current_price = snap_prices.get(ticker, 0.0)

            dna_rows.append((
                ticker,
                first["event_date"],
                first["constitutional_entry_price"],
                buy_count,
                re_count,
                round(avg_entry, 4),
                round(current_price, 4),
                round(avg_ret, 4),
                round(best_ret, 4),
                round(worst_ret, 4),
                round(zone_low, 4),
                round(zone_high, 4),
                constitutional_memory_hits,
                confidence,
                last_event_date,
                now_str,
            ))
        else:
            # Ticker not in constitutional timeline — monitoring only
            current_price = snap_prices.get(ticker, 0.0)
            entry_price   = snap_entries.get(ticker, 0.0)
            dna_rows.append((
                ticker,
                None,           # first_buy_date
                entry_price,    # first_buy_price (use entry zone as proxy)
                0,              # buy_count
                0,              # re_accum_count
                entry_price,    # avg_entry_price
                current_price,  # current_price
                0.0,            # avg_return_pct
                0.0,            # best_return_pct
                0.0,            # worst_return_pct
                entry_price,    # historical_buy_zone_low
                entry_price,    # historical_buy_zone_high
                0,              # constitutional_memory_hits
                "MONITORING",   # constitutional_memory_confidence
                None,           # last_event_date
                now_str,
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
            worst_return_pct REAL,
            historical_buy_zone_low REAL,
            historical_buy_zone_high REAL,
            constitutional_memory_hits INTEGER,
            constitutional_memory_confidence TEXT,
            last_event_date TEXT,
            last_updated TEXT
        )
    """)
    conn.executemany(
        "INSERT OR REPLACE INTO stock_dna VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        dna_rows
    )
    conn.commit()
    conn.close()
    print(f"[StockDNA] Built stock_dna.db — {len(dna_rows)} tickers (27 universe).")


if __name__ == "__main__":
    build_stock_dna()
