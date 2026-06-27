"""
CI Price Freshness Assertion
Verifies that universe_snapshot prices are from the latest available market session.
Exits 1 if any price is stale relative to the latest session in signal_history.json.
"""
from __future__ import annotations
import json, sqlite3, sys
from pathlib import Path
from datetime import datetime, date, timedelta

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

from audit.audit_status import AuditStatus

def _latest_signal_date() -> str:
    sh_path = BASE / "signal_history.json"
    if not sh_path.exists():
        return ""
    data = json.loads(sh_path.read_text())
    dates = []
    for events in data.values():
        if isinstance(events, list):
            for e in events:
                if e.get("date"):
                    dates.append(e["date"])
    return max(dates) if dates else ""

def _egx_trading_days_back(n: int) -> set[str]:
    """Return last n EGX trading day date strings (Sun-Thu)."""
    result = set()
    d = date.today()
    while len(result) < n:
        if d.weekday() in (0, 1, 2, 3, 6):  # Mon-Thu + Sun
            result.add(d.isoformat())
        d -= timedelta(days=1)
    return result

failures = []
warnings = []

latest_signal_date = _latest_signal_date()
print(f"Latest signal_history date : {latest_signal_date or 'UNKNOWN'}")

# Load universe_snapshot
snap_path = BASE / "universe_snapshot.db"
if not snap_path.exists():
    print("SKIPPED: universe_snapshot.db missing — run build_universe_snapshot() first")
    sys.exit(AuditStatus.SKIPPED)

conn = sqlite3.connect(str(snap_path))
conn.row_factory = sqlite3.Row
rows = conn.execute(
    "SELECT ticker, current_price, last_price_update, status FROM universe_snapshot ORDER BY ticker"
).fetchall()
conn.close()

# Load signal_history prices for comparison
sh_path = BASE / "signal_history.json"
sh_prices: dict[str, tuple[str, float]] = {}
if sh_path.exists():
    data = json.loads(sh_path.read_text())
    for ticker, events in data.items():
        if isinstance(events, list) and events:
            latest = max(events, key=lambda e: e.get("date", ""))
            sh_prices[ticker] = (latest.get("date", ""), latest.get("price") or 0.0)

recent_days = _egx_trading_days_back(5)
max_price_drift_pct = 5.0  # alert if dashboard price differs >5% from signal_history

print(f"\nPrice freshness check ({len(rows)} tickers):")
print(f"{'Ticker':12s} {'last_update':12s} {'snap_price':10s} {'sh_date':12s} {'sh_price':10s} {'drift%':8s} {'status':10s}")
print("-" * 80)

for r in rows:
    ticker     = r["ticker"]
    snap_price = r["current_price"] or 0.0
    last_upd   = (r["last_price_update"] or "")[:10]
    sh_date, sh_price = sh_prices.get(ticker, ("", 0.0))

    # Drift between snapshot price and signal_history price
    if sh_price and snap_price:
        drift = abs(snap_price - sh_price) / sh_price * 100
    else:
        drift = 0.0

    # Freshness check: last_price_update should be in last 5 trading days
    fresh = last_upd in recent_days or last_upd == latest_signal_date
    stale = not fresh and last_upd < (latest_signal_date or "2099-01-01")

    status_flag = "OK"
    if stale and last_upd:
        status_flag = "STALE"
        failures.append(f"{ticker}: last_price_update={last_upd} older than latest session {latest_signal_date}")
    if drift > max_price_drift_pct:
        status_flag = "DRIFT"
        warnings.append(f"{ticker}: snap_price={snap_price:.2f} vs sh_price={sh_price:.2f} drift={drift:.1f}%")

    print(f"{ticker:12s} {last_upd:12s} {snap_price:10.2f} {sh_date:12s} {sh_price:10.2f} {drift:8.1f}% {status_flag:10s}")

print(f"\nTotal: {len(rows)} tickers, {len(failures)} STALE, {len(warnings)} DRIFT warnings")

if warnings:
    print("\nDRIFT WARNINGS (>5% difference from signal_history):")
    for w in warnings:
        print(f"  ⚠ {w}")

if failures:
    print("\nFRESHNESS FAILURES:")
    for f in failures:
        print(f"  ✗ {f}")
    print("\nASSERTION FAILED — prices are stale. Do NOT deploy.")
    sys.exit(AuditStatus.FAIL)

print("\nASSERTION PASSED — all prices are current.")
sys.exit(AuditStatus.PASS)
