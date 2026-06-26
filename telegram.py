"""
EGX Constitutional Command Center — Telegram V6
Morning brief + constitutional event alerts.
All sends go through notifications.notification_router → notifications.telegram_sender.
telegram_debounce.json replaced by telegram_delivery SQLite table (exactly-once).
"""
from __future__ import annotations

from presentation.presentation_snapshot import PresentationSnapshot, build_presentation_snapshot
from notifications.notification_router import (
    route as _route,
    MORNING_BRIEF, FIRST_BUY, NEAR_CONSTITUTIONAL,
)
from time_authority import now_cairo as _now_cairo

SEP = "━━━━━━━━━━━━━━━━━━━━━"


def _sign(r: float) -> str:
    return "+" if r >= 0 else ""


def _market_icon(status: str) -> str:
    if "OPEN" in status and "PRE" not in status: return "🟢"
    if "PRE" in status: return "🟡"
    return "⚫"


def _opp_line(e: dict) -> str:
    etype = "🟢 FIRST BUY" if e["event_type"] == "FIRST_BUY" else "🔵 RE-ACCUM"
    return (
        f"   {etype}  *{e['ticker']}*"
        f"  Entry={e['constitutional_entry_price']:.2f}"
        f"  Now={e['current_price']:.2f}"
        f"  {_sign(e['return_pct'])}{e['return_pct']:.1f}%"
    )


def build_morning_brief(snap: PresentationSnapshot, date_str: str) -> str:
    cairo_t    = _now_cairo().strftime("%H:%M")
    micon      = _market_icon(snap.market_status)
    scan_s     = snap.last_scan_ts[:16].replace("T", " ") if snap.last_scan_ts else "--"
    data_as_of = getattr(snap, "price_data_as_of", "") or scan_s[:10]

    lines = [
        "🏛 *EGX Constitutional Command Center*",
        f"*{date_str}* | {cairo_t} Cairo | {micon} {snap.market_status}",
        "",
    ]

    if snap.new_events_today:
        lines.append(f"⚡ *NEW TODAY ({len(snap.new_events_today)})*")
        for e in snap.new_events_today:
            lines.append(_opp_line(e))
        lines.append("")

    if snap.approaching_entries:
        top3 = sorted(snap.approaching_entries, key=lambda e: e["distance_to_constitutional"])[:3]
        lines.append(f"🔍 *APPROACHING ({len(snap.approaching_entries)} total — top 3)*")
        for e in top3:
            dist = e["distance_to_constitutional"]
            urg  = "🔥" if dist <= 0.3 else ("⚠️" if dist <= 1.0 else "📍")
            lines.append(
                f"   {urg} *{e['ticker']}*  –{dist:.1f} pts  Zone {e['candidate_entry_zone']:.2f} EGP"
            )
        lines.append("")

    if snap.timeline:
        top3 = sorted(snap.timeline, key=lambda e: -e["return_pct"])[:3]
        lines.append(f"📊 *ACTIVE ({snap.total_events} total — top 3 by return)*")
        for e in top3:
            lines.append(_opp_line(e))
        lines.append("")

    lines.append(SEP)
    lines.append(f"⏰ {scan_s} | Last Scan | Data As Of: {data_as_of}")

    return "\n".join(lines)


def send_morning_brief(date_str: str, snap: PresentationSnapshot | None = None) -> None:
    """Send constitutional morning brief via the notification router."""
    if snap is None:
        snap = build_presentation_snapshot()
    full_msg = build_morning_brief(snap, date_str)
    _route(MORNING_BRIEF, full_msg, symbol="", event_date=date_str[:10] if len(date_str) >= 10 else None)


def send_alert(event: dict, snap: PresentationSnapshot | None = None) -> None:
    """
    Send a single constitutional event alert (FIRST_BUY or RE_ACCUMULATION).
    Exactly-once per (event_type, ticker, event_date) via telegram_delivery table.
    """
    ticker  = event.get("ticker", "")
    etype   = event.get("event_type", "FIRST_BUY")
    entry   = float(event.get("constitutional_entry_price", 0))
    cur     = float(event.get("current_price", 0))
    ret     = float(event.get("return_pct", 0))
    date_s  = event.get("event_date", "")
    type_l  = "🟢 FIRST BUY" if etype == "FIRST_BUY" else "🔵 RE-ACCUMULATION"
    cairo_t = _now_cairo().strftime("%H:%M Cairo")

    msg = (
        f"⚡ *CONSTITUTIONAL ALERT*\n"
        f"{type_l}  *{ticker}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"   Entry Zone: {entry:.2f} EGP\n"
        f"   Current:    {cur:.2f}\n"
        f"   Return:     {_sign(ret)}{ret:.1f}%\n"
        f"   Date:       {date_s}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"Dashboard: https://shadygad01.github.io/smartlist/\n"
        f"⏰ {cairo_t}"
    )
    _route(FIRST_BUY, msg, symbol=ticker, event_date=date_s or None)
