"""
Production Consistency Checker — operations/consistency_check.py

Asserts that all output channels derive from the same PresentationSnapshot.
Fails with exit code 1 if any assertion fails.

Usage:
    python operations/consistency_check.py
    python -c "from operations.consistency_check import run_checks; run_checks()"
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))


def run_checks() -> dict:
    """
    Build one PresentationSnapshot and verify all consumers report identical values.
    Returns dict with results. Raises AssertionError on any mismatch.
    """
    from presentation.presentation_snapshot import build_presentation_snapshot
    from time_authority import now_cairo, market_state

    snap = build_presentation_snapshot()

    near_count     = len(snap.approaching_entries)
    market_status  = snap.market_status
    last_scan      = snap.last_scan_ts

    # ── 1. Email near count ───────────────────────────────────────────────────
    from egx_email import build_email
    html = build_email(snap)
    # Count how many ticker rows appear in the near entry section
    # The section title contains the count explicitly: "NEAR CONSTITUTIONAL ENTRY (N tickers)"
    import re
    email_near_match = re.search(r'NEAR CONSTITUTIONAL ENTRY \((\d+) tickers\)', html)
    email_near_count = int(email_near_match.group(1)) if email_near_match else 0

    # ── 2. Dashboard near count ───────────────────────────────────────────────
    # Pass the same `snap` used for the email/Telegram checks below — building a
    # second, independent snapshot here previously let live-data drift between
    # the two builds surface as a false-positive "near count mismatch".
    from dashboard import build_dashboard
    dash_html = build_dashboard(snap=snap)
    # The Near Entry section's own count badge is the only "float:right ... N tickers"
    # span in the dashboard. A bare "NEAR CONSTITUTIONAL ENTRY.*?N tickers" search is not
    # scoped to the section: when there are zero near entries the section renders a plain
    # "No tickers..." empty state with no count at all, so a non-greedy DOTALL match spills
    # past it into the next section's unrelated "N tickers" badge (e.g. Future Opportunities)
    # and reports that count instead — a false-positive mismatch.
    dash_near_match = re.search(
        r'NEAR CONSTITUTIONAL ENTRY.*?float:right[^>]*>(\d+) tickers</span>', dash_html, re.DOTALL
    )
    dash_near_count = int(dash_near_match.group(1)) if dash_near_match else 0

    # ── 3. Telegram near count ────────────────────────────────────────────────
    from telegram import build_morning_brief
    from time_authority import today_iso
    tg_text = build_morning_brief(snap, today_iso())
    tg_near_match = re.search(r'APPROACHING \((\d+) total', tg_text)
    tg_near_count = int(tg_near_match.group(1)) if tg_near_match else 0

    # ── 4. public_status.json market_status ─────────────────────────────────
    pub_path = BASE / "operations" / "public_status.json"
    pub_market = None
    if pub_path.exists():
        try:
            pub_data = json.loads(pub_path.read_text())
            pub_market = pub_data.get("market_status") or pub_data.get("system_health")
        except Exception:
            pass

    # ── 5. Market status: must derive from time_authority, not scan state ────
    ta_market = market_state()  # canonical
    expected_status_str = {
        "OPEN": "OPEN",
        "PRE_OPEN": "PRE-MARKET",
        "WEEKEND": "CLOSED (Weekend)",
        "CLOSED": "CLOSED (After Hours)",
    }.get(ta_market, ta_market)
    market_status_ok = snap.market_status.startswith(expected_status_str.split()[0])

    # ── Per-ticker price assertions ────────────────────────────────────────────
    # All channels share the same snap object — verify each renderer embeds the
    # canonical current_price (not an independently fetched value).
    price_mismatches = []
    for entry in snap.approaching_entries:
        ticker  = entry["ticker"]
        snap_px = entry["current_price"]
        # Email: current price appears as first number in the ticker's row,
        # before "EGP" (which marks entry price, not current)
        email_row_match = re.search(
            rf'>{re.escape(ticker)}<.*?<td[^>]*>({re.escape(f"{snap_px:.2f}")}|(\d+\.\d+))<',
            html, re.DOTALL
        )
        # Simpler: verify price string appears in email HTML
        px_str = f"{snap_px:.2f}"
        if px_str not in html:
            price_mismatches.append(f"{ticker}: current_price {px_str} not found in email HTML")
        if px_str not in dash_html:
            price_mismatches.append(f"{ticker}: current_price {px_str} not found in dashboard HTML")

    # ── Assertions ─────────────────────────────────────────────────────────────
    errors = []

    if email_near_count != near_count:
        errors.append(
            f"Near count mismatch: snapshot={near_count} email={email_near_count}"
        )
    if dash_near_count != near_count:
        errors.append(
            f"Near count mismatch: snapshot={near_count} dashboard={dash_near_count}"
        )
    if tg_near_count not in (near_count, 0) and near_count > 0:
        if tg_near_count != near_count:
            errors.append(
                f"Near count mismatch: snapshot={near_count} telegram={tg_near_count}"
            )
    if not market_status_ok:
        errors.append(
            f"Market status mismatch: time_authority={ta_market} snap={snap.market_status}"
        )
    errors.extend(price_mismatches)

    # Timestamp assertions
    price_data_as_of = getattr(snap, "price_data_as_of", "")
    if not price_data_as_of:
        errors.append("price_data_as_of is empty — CSV price date not set")

    results = {
        "near_count_snapshot": near_count,
        "near_count_email":    email_near_count,
        "near_count_dashboard": dash_near_count,
        "near_count_telegram": tg_near_count,
        "market_status_snapshot": snap.market_status,
        "market_status_time_authority": ta_market,
        "market_status_ok": market_status_ok,
        "last_scan": last_scan,
        "price_data_as_of": price_data_as_of,
        "generated_at": snap.generated_at,
        "price_mismatches": price_mismatches,
        "errors": errors,
        "passed": len(errors) == 0,
    }

    if errors:
        for e in errors:
            print(f"[ConsistencyCheck] FAIL: {e}", file=sys.stderr)
        raise AssertionError(f"Consistency check failed: {errors}")

    print(f"[ConsistencyCheck] PASS — near={near_count} market={snap.market_status}")
    return results


if __name__ == "__main__":
    try:
        results = run_checks()
        print(json.dumps(results, indent=2, default=str))
        sys.exit(0)
    except AssertionError as e:
        print(f"FAILED: {e}", file=sys.stderr)
        sys.exit(1)
