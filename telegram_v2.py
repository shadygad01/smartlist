"""
EGX Constitutional Opportunity Timeline — Telegram V1
Event-driven brief. No portfolio capacity. No HELD/WATCH/RESERVE.
"""
from __future__ import annotations

import os
import requests
from datetime import datetime

from presentation.presentation_snapshot import PresentationSnapshot, build_presentation_snapshot

TG_HEADER = "📋 *EGX Constitutional Opportunity Timeline*"
SEP       = "━━━━━━━━━━━━━━━━━━━━━"
MAX_CHARS = 4000


def _health_icon(stars: str) -> str:
    n = stars.count("★")
    return "🟢" if n >= 4 else ("🟡" if n == 3 else "🔴")


def _status_icon(status: str) -> str:
    return "🏆" if status == "PREMIUM_NOW" else ("🟢" if status == "ACTIVE_OPPORTUNITY" else "🔴")


def _sign(r: float) -> str:
    return "+" if r >= 0 else ""


def build_morning_brief(snap: PresentationSnapshot, date_str: str) -> str:
    lines = [TG_HEADER, f"*{date_str}*", SEP]

    # Summary
    icon    = _health_icon(snap.health_stars)
    premium = sum(1 for e in snap.timeline if e.get("status") == "PREMIUM_NOW")
    active  = sum(1 for e in snap.timeline if e.get("status") == "ACTIVE_OPPORTUNITY")
    review  = sum(1 for e in snap.timeline if e.get("status") == "UNDER_REVIEW")

    lines.append(f"{icon} *{snap.health_stars} {snap.health_label}*")
    lines.append(
        f"   *{snap.total_events}* Events · *{snap.total_tickers}* Tickers"
        f" · First: {len(snap.first_buys)} · Re-Accum: {len(snap.re_accumulations)}"
    )
    lines.append(f"   🏆 Premium: {premium} · 🟢 Active: {active} · 🔴 Review: {review}")
    lines.append("")

    # New events today
    if snap.new_events_today:
        lines.append(SEP)
        lines.append(f"⚡ *New Constitutional Events Today ({len(snap.new_events_today)})*\n")
        for e in snap.new_events_today:
            label = "🟢 *FIRST BUY*" if e["event_type"] == "FIRST_BUY" else "🔵 *RE-ACCUMULATION*"
            lines.append(f"{label}  *{e['ticker']}*  {e['sector']}")
            lines.append(f"   Entry: {e['entry_price']:.2f} EGP  · R2={e['buy_r2']:.1f} · Score={e['buy_score']:.1f}")
            lines.append("")

    # Full timeline
    lines.append(SEP)
    lines.append(f"📋 *Constitutional Opportunity Timeline ({snap.total_events} events)*\n")

    for e in snap.timeline:
        si    = _status_icon(e["status"])
        etype = "🟢" if e["event_type"] == "FIRST_BUY" else "🔵"
        lines.append(
            f"{si}{etype} *{e['ticker']}*  {e['event_date']}"
            f"  Entry={e['entry_price']:.2f}"
            f"  Now={e['current_price']:.2f}"
            f"  Ret={_sign(e['return_pct'])}{e['return_pct']:.1f}%"
            f"  Peak={_sign(e['peak_return_pct'])}{e['peak_return_pct']:.1f}%"
            f"  {e['days_active']}d"
        )
    lines.append("")

    # Leaderboards
    lb = snap.leaderboards
    if lb:
        lines.append(SEP)
        lines.append("🏆 *Most Repeated Constitutional Opportunities*\n")
        for i, a in enumerate(lb.get("most_repeated", [])[:5], 1):
            lines.append(
                f"   {i}. *{a['ticker']}*  {a['total_events']} events"
                f"  avg={_sign(a['avg_return_pct'])}{a['avg_return_pct']:.1f}%"
                f"  best={_sign(a['best_return_pct'])}{a['best_return_pct']:.1f}%"
            )
        lines.append("")

        lines.append("📈 *Highest Compound Return*\n")
        for i, c in enumerate(lb.get("compound_return", [])[:5], 1):
            lines.append(
                f"   {i}. *{c['ticker']}*  {_sign(c['compound_return_pct'])}{c['compound_return_pct']:.1f}%"
                f"  ({c['total_events']} events)"
            )
        lines.append("")

    # Research (top insight)
    if snap.research_insights:
        ins = snap.research_insights[0]
        lines.append(SEP)
        lines.append(f"🔬 *Research:* {(ins.get('conclusion') or '')[:120]}")
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
        print("Telegram V1: TELEGRAM_TOKEN or TELEGRAM_CHAT_ID not set — skipping.")
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
                print(f"Telegram V1: chunk sent ({len(chunk)} chars)")
            else:
                print(f"Telegram V1: error {resp.status_code} — {resp.text[:200]}")
        except Exception as e:
            print(f"Telegram V1: exception — {e}")
