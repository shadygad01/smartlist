"""
EGX Constitutional Command Center — Telegram V6
Morning brief: action-only, max 3 per section, 24h debounce.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    import requests as _requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

from presentation.presentation_snapshot import PresentationSnapshot, build_presentation_snapshot

BASE          = Path(__file__).parent
_DEBOUNCE_F   = BASE / "telegram_debounce.json"
SEP           = "━━━━━━━━━━━━━━━━━━━━━"
MAX_CHARS     = 4000
_CAIRO_TZ     = timezone(timedelta(hours=2))


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
        f"  Entry={e['entry_price']:.2f}"
        f"  Now={e['current_price']:.2f}"
        f"  {_sign(e['return_pct'])}{e['return_pct']:.1f}%"
    )

def _load_debounce() -> dict:
    if not _DEBOUNCE_F.exists():
        return {}
    try:
        return json.loads(_DEBOUNCE_F.read_text())
    except Exception:
        return {}

def _save_debounce(data: dict) -> None:
    _DEBOUNCE_F.write_text(json.dumps(data, indent=2))

def _debounce_ok(ticker: str, db: dict) -> bool:
    """Return True if ticker has NOT been sent in last 24h."""
    if ticker not in db:
        return True
    last = datetime.fromisoformat(db[ticker])
    now  = datetime.now(_CAIRO_TZ)
    return (now - last).total_seconds() > 86400

def _mark_sent(ticker: str, db: dict) -> None:
    db[ticker] = datetime.now(_CAIRO_TZ).isoformat()


def build_morning_brief(snap: PresentationSnapshot, date_str: str) -> str:
    cairo_t = datetime.now(_CAIRO_TZ).strftime("%H:%M")
    micon   = _market_icon(snap.market_status)
    scan_s  = snap.last_scan_ts[:16].replace("T", " ") if snap.last_scan_ts else "--"

    lines = [
        "🏛 *EGX Constitutional Command Center*",
        f"*{date_str}* | {cairo_t} Cairo | {micon} {snap.market_status}",
        "",
    ]

    # New today (all — these are rare events)
    if snap.new_events_today:
        lines.append(f"⚡ *NEW TODAY ({len(snap.new_events_today)})*")
        for e in snap.new_events_today:
            lines.append(_opp_line(e))
        lines.append("")

    # Approaching — top 3 by distance asc
    if snap.approaching_entries:
        top3 = sorted(snap.approaching_entries, key=lambda e: e["distance_to_constitutional"])[:3]
        lines.append(f"🔍 *APPROACHING ({len(snap.approaching_entries)} total — top 3)*")
        for e in top3:
            dist = e["distance_to_constitutional"]
            urg  = "🔥" if dist <= 0.3 else ("⚠️" if dist <= 1.0 else "📍")
            lines.append(
                f"   {urg} *{e['ticker']}*  –{dist:.1f} pts  Zone {e['entry_price']:.2f} EGP"
            )
        lines.append("")

    # Active — top 3 by return desc
    if snap.timeline:
        top3 = sorted(snap.timeline, key=lambda e: -e["return_pct"])[:3]
        lines.append(f"📊 *ACTIVE ({snap.total_events} total — top 3 by return)*")
        for e in top3:
            lines.append(_opp_line(e))
        lines.append("")

    lines.append(SEP)
    lines.append(f"⏰ {scan_s} | Last Scan")

    return "\n".join(lines)


def _chunk(text: str) -> list[str]:
    chunks, current = [], ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > MAX_CHARS:
            chunks.append(current)
            current = line + "\n"
        else:
            current += line + "\n"
    if current:
        chunks.append(current)
    return chunks


def send_morning_brief(date_str: str, snap: PresentationSnapshot | None = None) -> None:
    token   = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("Telegram V6: TELEGRAM_TOKEN or TELEGRAM_CHAT_ID not set — skipping.")
        return
    if snap is None:
        snap = build_presentation_snapshot()
    full_msg = build_morning_brief(snap, date_str)
    _send_chunks(full_msg, token, chat_id)


def send_alert(event: dict, snap: PresentationSnapshot | None = None) -> None:
    """Send a single constitutional event alert with 24h debounce."""
    token   = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("Telegram V6: credentials not set — skipping alert.")
        return

    ticker = event.get("ticker", "")
    db     = _load_debounce()
    if not _debounce_ok(ticker, db):
        print(f"Telegram V6: {ticker} debounced (sent < 24h ago).")
        return

    etype  = event.get("event_type", "")
    entry  = float(event.get("entry_price", 0))
    cur    = float(event.get("current_price", 0))
    ret    = float(event.get("return_pct", 0))
    date_s = event.get("event_date", "")
    type_l = "🟢 FIRST BUY" if etype == "FIRST_BUY" else "🔵 RE-ACCUMULATION"
    cairo_t = datetime.now(_CAIRO_TZ).strftime("%H:%M Cairo")

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
    _send_chunks(msg, token, chat_id)
    _mark_sent(ticker, db)
    _save_debounce(db)


def _send_chunks(text: str, token: str, chat_id: str) -> None:
    if not _HAS_REQUESTS:
        print("Telegram V6: requests not installed — cannot send.")
        return
    for chunk in _chunk(text):
        try:
            resp = _requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": chunk, "parse_mode": "Markdown"},
                timeout=10,
            )
            if resp.status_code == 200:
                print(f"Telegram V6: chunk sent ({len(chunk)} chars)")
            else:
                print(f"Telegram V6: error {resp.status_code} — {resp.text[:200]}")
        except Exception as e:
            print(f"Telegram V6: exception — {e}")
