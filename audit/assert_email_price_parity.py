"""
CI Email Price Parity Assertion — Phase 9 gate.

Builds one PresentationSnapshot, renders email HTML and dashboard HTML from it,
then verifies that every current_price in the snapshot appears verbatim in BOTH
rendered outputs.  Fails with exit code 1 if any price differs by even 0.01.

This catches the architecture defect where email reads stale universe_snapshot.db
prices while dashboard reads freshly rebuilt ones.

Usage:
    python audit/assert_email_price_parity.py
"""
from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

failures: list[str] = []
AUDIT_TICKERS = {"EAST.CA", "MCQE.CA", "OIH.CA", "FWRY.CA", "BTFH.CA", "HELI.CA"}


def _price_in_html(px: float, html: str) -> bool:
    """Return True if the formatted price string appears anywhere in the HTML."""
    return f"{px:.2f}" in html


def main() -> int:
    from presentation.presentation_snapshot import build_presentation_snapshot
    from egx_email import build_email
    from dashboard import build_dashboard
    from price_authority import get_all_prices

    snap     = build_presentation_snapshot()
    email_html = build_email(snap)
    dash_html  = build_dashboard()
    auth_prices = get_all_prices()

    all_entries = (
        list(snap.approaching_entries) +
        list(snap.opportunities) +
        list(snap.re_accumulations)
    )
    checked = set()

    print(f"Email Price Parity Audit — {len(all_entries)} entries from snapshot")
    print(f"{'Ticker':12s} {'snap_px':10s} {'auth_px':10s} {'in_email':10s} {'in_dash':10s} {'status':12s}")
    print("-" * 70)

    for entry in all_entries:
        ticker   = entry.get("ticker", "")
        snap_px  = entry.get("current_price")
        if not ticker or snap_px is None or ticker in checked:
            continue
        checked.add(ticker)

        auth_px      = auth_prices.get(ticker)
        in_email     = _price_in_html(snap_px, email_html)
        in_dash      = _price_in_html(snap_px, dash_html)
        auth_mismatch = auth_px is not None and abs(auth_px - snap_px) > 0.01

        if auth_mismatch:
            failures.append(
                f"{ticker}: snap={snap_px:.2f} auth(universe_db)={auth_px:.2f} "
                f"diff={abs(auth_px - snap_px):.4f} — stale price in universe_snapshot.db"
            )
            status = "AUTH_MISMATCH"
        elif not in_email:
            failures.append(f"{ticker}: current_price {snap_px:.2f} not found in email HTML")
            status = "EMAIL_MISS"
        elif not in_dash:
            failures.append(f"{ticker}: current_price {snap_px:.2f} not found in dashboard HTML")
            status = "DASH_MISS"
        else:
            status = "PASS"

        auth_str   = f"{auth_px:.2f}" if auth_px is not None else "—"
        email_str  = "YES" if in_email else "NO"
        dash_str   = "YES" if in_dash  else "NO"
        print(f"{ticker:12s} {snap_px:10.2f} {auth_str:10s} {email_str:10s} {dash_str:10s} {status}")

    # Extra check for the 6 audit tickers by name
    for ticker in sorted(AUDIT_TICKERS):
        if ticker in checked:
            continue
        auth_px = auth_prices.get(ticker)
        if auth_px is not None:
            print(f"{ticker:12s} {'—':10s} {auth_px:10.2f} {'—':10s} {'—':10s} NOT_IN_SNAP")

    print(f"\nTotal checked: {len(checked)}, failures: {len(failures)}")

    if failures:
        print("\nEMAIL PRICE PARITY VIOLATIONS:")
        for f in failures:
            print(f"  ✗ {f}")
        print("\nASSERTION FAILED — email/dashboard price divergence detected.")
        return 1

    print("\nASSERTION PASSED — email, dashboard, and universe_snapshot.db prices are identical.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
