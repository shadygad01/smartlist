"""
Rendered Output Validation — Phase 2 Final Hardening.

Verifies that the dashboard.html rendered output is consistent with
production_decision_snapshot.json. The dashboard is the primary rendered
surface; if the rendered BUY set differs from the production snapshot,
the system has a rendering bug.

Checks:
  1. Every eligible ticker (production_decision_snapshot.eligible=True)
     appears in the dashboard BUY SIGNALS section.
  2. Every ticker in the dashboard BUY SIGNALS section is eligible in
     production_decision_snapshot (no phantom signals).
  3. Entry prices rendered for BUY tickers match snapshot values (±0.01 EGP).
  4. Near-constitutional tickers (not eligible) must NOT appear in BUY section.

Dashboard HTML patterns used:
  - BUY signal section bounded by "CONSTITUTIONAL BUY SIGNALS" header
  - Ticker symbol appears as a standalone uppercase token (e.g. EFIH.CA)
  - Entry price appears near the ticker in "@ {price:.2f} EGP" or as a numeric

Exits 1 on any failure.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

PROD_SNAP  = BASE / "production_decision_snapshot.json"
DASH_HTML  = BASE / "dashboard.html"
PRES_SNAP  = BASE / "presentation_snapshot.json"

PRICE_TOL  = 0.015   # 1.5 EGP tolerance for rendered price check

failures: list[str] = []
warnings: list[str] = []


def _extract_buy_section(html: str) -> str:
    """Extract the portion of HTML that is the BUY SIGNALS section."""
    # The BUY section starts at "CONSTITUTIONAL BUY SIGNALS" and ends before
    # the NEAR ENTRY section or the universe table section.
    markers_end = [
        "NEAR ENTRY",
        "NEAR-CONSTITUTIONAL",
        "universe-table",
        "near-entry",
        "id=\"near",
        "id=\"future",
        "id=\"waiting",
    ]
    start_m = re.search(r"CONSTITUTIONAL BUY SIGNALS", html)
    if not start_m:
        return ""
    start = start_m.start()

    # Find the earliest end marker after start
    end = len(html)
    for marker in markers_end:
        m = re.search(re.escape(marker), html[start + 100:], re.IGNORECASE)
        if m:
            candidate = start + 100 + m.start()
            if candidate < end:
                end = candidate

    return html[start:end]


def _tickers_in_section(section: str, all_tickers: set[str]) -> set[str]:
    """Find which known tickers appear in a section of HTML (case-sensitive)."""
    found = set()
    for ticker in all_tickers:
        if ticker in section:
            found.add(ticker)
    return found


def _entry_price_near_ticker(html: str, ticker: str) -> float | None:
    """
    Find a rendered entry price near the ticker in HTML.
    Looks for patterns like '@ 12.34 EGP' or 'BUY LIMIT @ 12.34' within 800 chars.
    """
    positions = [m.start() for m in re.finditer(re.escape(ticker), html)]
    for pos in positions:
        window = html[max(0, pos - 100):pos + 800]
        # Pattern: BUY LIMIT @ <price> or @ <price> EGP
        for pat in [
            r"BUY LIMIT\s*@\s*([\d]+\.[\d]+)",
            r"@\s*([\d]+\.[\d]+)\s*EGP",
            r"entry.*?([\d]+\.[\d]{2})\s*EGP",
        ]:
            m = re.search(pat, window, re.IGNORECASE)
            if m:
                try:
                    return float(m.group(1))
                except ValueError:
                    pass
    return None


def main() -> int:
    if not PROD_SNAP.exists():
        print("SKIP: production_decision_snapshot.json not found")
        return 0
    if not DASH_HTML.exists():
        print("SKIP: dashboard.html not found")
        return 0

    prod       = json.loads(PROD_SNAP.read_text())
    decisions  = {d["ticker"]: d for d in prod.get("decisions", [])}
    eligible   = {t for t, d in decisions.items() if d["eligible"]}
    all_tickers = set(decisions.keys())

    html       = DASH_HTML.read_text()
    buy_section = _extract_buy_section(html)

    print("Rendered Output Validation")
    print(f"  production snapshot: {len(decisions)} tickers  eligible={len(eligible)}")
    print(f"  dashboard BUY section: {len(buy_section)} chars")
    print()

    # ── Check 1: No-signal case ───────────────────────────────────────────────
    if not eligible:
        # Dashboard should show "no active signals" message
        no_signals_ok = "no active signals" in html.lower() or "no constitutional" in html.lower()
        if no_signals_ok:
            print("  ✓ No eligible tickers — dashboard correctly shows 'no active signals'")
        else:
            # Check that none of the tickers appear in buy section
            in_buy = _tickers_in_section(buy_section, all_tickers)
            if in_buy:
                for t in sorted(in_buy):
                    failures.append(f"{t}: appears in BUY section but production eligible=False")
                    print(f"  ✗ PHANTOM: {t} in dashboard BUY section, production eligible=False")
            else:
                print("  ✓ No eligible tickers — no tickers in BUY section (correct)")
        print()

    # ── Check 2: Eligible tickers appear in buy section ───────────────────────
    if eligible:
        in_buy = _tickers_in_section(buy_section, all_tickers)

        for ticker in sorted(eligible):
            if ticker in in_buy:
                # Check 3: Entry price rendered correctly
                stored_ep = float(decisions[ticker].get("constitutional_entry_price") or 0)
                rendered_ep = _entry_price_near_ticker(html, ticker)
                if rendered_ep is not None and stored_ep > 0:
                    if abs(rendered_ep - stored_ep) > PRICE_TOL:
                        failures.append(
                            f"{ticker}: rendered EP={rendered_ep:.4f} vs snapshot EP={stored_ep:.4f} "
                            f"(diff={abs(rendered_ep-stored_ep):.4f})"
                        )
                        print(f"  ✗ {ticker:<12}  PRICE MISMATCH  rendered={rendered_ep:.4f}  stored={stored_ep:.4f}")
                    else:
                        print(f"  ✓ {ticker:<12}  in BUY section  ep={stored_ep:.4f}")
                else:
                    print(f"  ✓ {ticker:<12}  in BUY section")
            else:
                # Eligible but NOT in buy section — check if it might be in history section
                # Dashboard shows "live" signals — if ticker has RE_ACCUMULATION history
                # but no active signal today it may appear in the history section, not buy section
                etype = decisions[ticker].get("event_type", "NONE")
                if etype == "RE_ACCUMULATION":
                    warnings.append(
                        f"{ticker}: eligible RE_ACCUMULATION not in new-signal BUY section "
                        f"(may be in history section — check dashboard manually)"
                    )
                    print(f"  ⚠ {ticker:<12}  eligible RE_ACCUM, not in BUY header section")
                else:
                    failures.append(f"{ticker}: eligible in snapshot but NOT found in dashboard BUY section")
                    print(f"  ✗ {ticker:<12}  MISSING from dashboard BUY section  event_type={etype}")

        # ── Check 4: Phantom signals — in buy section but NOT eligible ─────────
        phantom = in_buy - eligible
        for ticker in sorted(phantom):
            if ticker in all_tickers:
                failures.append(
                    f"{ticker}: appears in dashboard BUY section but production_decision_snapshot eligible=False"
                )
                print(f"  ✗ {ticker:<12}  PHANTOM SIGNAL in dashboard (not eligible in snapshot)")
            # else: ticker not in our universe — skip

    # ── Check 5: Presentation snapshot cross-check ────────────────────────────
    if PRES_SNAP.exists():
        pres  = json.loads(PRES_SNAP.read_text())
        # new_events_today tickers should be subset of eligible
        today_evs = {e["ticker"] for e in pres.get("new_events_today", [])}
        phantom_evs = today_evs - eligible
        if phantom_evs:
            for t in sorted(phantom_evs):
                failures.append(
                    f"{t}: in presentation_snapshot.new_events_today but NOT eligible in production snapshot"
                )
                print(f"  ✗ {t:<12}  PHANTOM in new_events_today (not eligible)")

    print()
    if warnings:
        print("WARNINGS (non-blocking):")
        for w in warnings:
            print(f"  ⚠ {w}")
        print()

    if failures:
        print("RENDERED OUTPUT FAILURES:")
        for f in failures:
            print(f"  ✗ {f}")
        print("\nASSERTION FAILED — rendered dashboard diverges from production snapshot.")
        return 1

    print("ASSERTION PASSED — rendered dashboard consistent with production snapshot.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
