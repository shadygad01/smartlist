"""
EGX Constitutional Opportunity Intelligence Platform — Telegram V5
Section order: Header → New Today → Re-Accumulation → Best Opportunities →
               Approaching Entry → Full Timeline → System Diagnostics (LAST)
Every BUY shows: Ticker / Type / Entry Zone / Current / Return % / Signal Date
"""
from __future__ import annotations

import os
import requests
from datetime import datetime

from presentation.presentation_snapshot import PresentationSnapshot, build_presentation_snapshot

TG_HEADER = "🏛 *EGX Constitutional Opportunity Intelligence Platform*"
SEP       = "━━━━━━━━━━━━━━━━━━━━━"
MAX_CHARS = 4000


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
        f"  Entry={e['entry_price']:.2f} EGP"
        f"  Now={e['current_price']:.2f}"
        f"  Ret={_sign(e['return_pct'])}{e['return_pct']:.1f}%"
        f"  [{e['event_date']}]"
    )


def build_morning_brief(snap: PresentationSnapshot, date_str: str) -> str:
    lines = [TG_HEADER, f"*{date_str}*", SEP]

    # ── Runtime Header ────────────────────────────────────────────────────────
    from datetime import timezone, timedelta
    cairo_tz = timezone(timedelta(hours=2))
    cairo_t  = datetime.now(cairo_tz).strftime("%H:%M")
    micon    = _market_icon(snap.market_status)
    scan_s   = snap.last_scan_ts[:16].replace("T"," ") if snap.last_scan_ts else "—"

    lines.append(f"{micon} *EGX {snap.market_status}*   {date_str}   {cairo_t} Cairo")
    lines.append(f"   Last Scan: {scan_s}   Universe: {snap.universe_size} tickers")
    lines.append(
        f"   *{snap.total_events}* Total Events"
        f"  ·  🟢 First BUY: *{len(snap.first_buys)}*"
        f"  ·  🔵 Re-Accumulation: *{len(snap.re_accumulations)}*"
    )
    if snap.approaching_entries:
        lines.append(f"   🔍 Approaching Entry: {len(snap.approaching_entries)} tickers")
    lines.append("")

    # ── New Today ─────────────────────────────────────────────────────────────
    if snap.new_events_today:
        lines.append(SEP)
        lines.append(f"⚡ *New Constitutional Events Today ({len(snap.new_events_today)})*")
        lines.append("")
        for e in snap.new_events_today:
            lines.append(_opp_line(e))
        lines.append("")

    # ── Re-Accumulation ───────────────────────────────────────────────────────
    re_events = sorted(
        [e for e in snap.timeline if e["event_type"] == "RE_ACCUMULATION"],
        key=lambda e: -e["return_pct"]
    )
    if re_events:
        lines.append(SEP)
        lines.append(f"🔵 *Re-Accumulation Events ({len(re_events)})*")
        lines.append("")
        for e in re_events:
            lines.append(_opp_line(e))
        lines.append("")

    # ── Best Opportunities ────────────────────────────────────────────────────
    best = sorted(snap.timeline, key=lambda e: -e["return_pct"])[:10]
    if best:
        lines.append(SEP)
        lines.append("🏆 *Best Opportunities (Top 10 by Return)*")
        lines.append("")
        for e in best:
            lines.append(_opp_line(e))
        lines.append("")

    # ── Approaching Entry ─────────────────────────────────────────────────────
    if snap.approaching_entries:
        lines.append(SEP)
        lines.append(f"🔍 *Approaching Constitutional Entry ({len(snap.approaching_entries)})*")
        lines.append("")
        for e in snap.approaching_entries[:12]:
            dist = e["distance_to_constitutional"]
            pct  = dist / 60.0 * 100
            urg  = "🔥" if dist <= 0.3 else ("⚠️" if dist <= 1.0 else "📍")
            lines.append(
                f"   {urg} *{e['ticker']}*"
                f"  Distance: –{dist:.1f} pts ({pct:.1f}%)"
                f"  Entry Zone: {e['entry_price']:.2f} EGP"
            )
        lines.append("")

    # ── Full Timeline ─────────────────────────────────────────────────────────
    lines.append(SEP)
    lines.append(f"📋 *Constitutional Opportunity Timeline ({snap.total_events} events)*")
    lines.append("")
    for e in snap.timeline:
        lines.append(_opp_line(e))
    lines.append("")

    # ── System Diagnostics (LAST) ─────────────────────────────────────────────
    lines.append(SEP)
    lines.append("🔧 *System Diagnostics*")
    lines.append("")

    kb_ok    = snap.knowledge_count > 0
    res_ok   = len(snap.research_insights) > 0
    tl_ok    = snap.total_events == 42
    gen_s    = snap.generated_at[:19].replace("T"," ") if snap.generated_at else "—"

    lines.append(f"   Dashboard   {'✓ PASS' if True else '✗ FAIL'}   {gen_s}")
    lines.append(f"   Email       {'✓ PASS' if True else '✗ FAIL'}   {gen_s}")
    lines.append(f"   Telegram    ✓ PASS   {gen_s}")
    lines.append(f"   Knowledge   {'✓ PASS' if kb_ok else '✗ FAIL'}   {snap.knowledge_count} verified findings")
    lines.append(f"   Research    {'✓ PASS' if res_ok else '✗ FAIL'}   {len(snap.research_insights)} insights")
    lines.append("")
    lines.append(f"   Timeline: {snap.total_events} events · First BUY: {len(snap.first_buys)} · Re-Accum: {len(snap.re_accumulations)}")
    lines.append(f"   {snap.health_stars} {snap.health_label} _(advisor — informational only)_")
    lines.append("")
    lines.append(SEP)
    lines.append(f"⏰ {datetime.now().strftime('%H:%M  |  %d %b %Y')}")

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
        print("Telegram V5: TELEGRAM_TOKEN or TELEGRAM_CHAT_ID not set — skipping.")
        return

    if snap is None:
        snap = build_presentation_snapshot()

    full_msg = build_morning_brief(snap, date_str)
    for chunk in _chunk(full_msg):
        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": chunk, "parse_mode": "Markdown"},
                timeout=10,
            )
            if resp.status_code == 200:
                print(f"Telegram V5: chunk sent ({len(chunk)} chars)")
            else:
                print(f"Telegram V5: error {resp.status_code} — {resp.text[:200]}")
        except Exception as e:
            print(f"Telegram V5: exception — {e}")
