"""
EGX Constitutional Opportunity Intelligence Platform — Telegram V4
Format: 🟢 FIRST BUY / 🔵 RE-ACCUMULATION / 🔍 APPROACHING ENTRY / 🏆 CONSTITUTIONAL LEADER
No portfolio capacity. No HELD/WATCH/RESERVE.
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

def _status_icon(status: str) -> str:
    return "🏆" if status == "PREMIUM_NOW" else ("🟢" if status == "ACTIVE_OPPORTUNITY" else "🔴")

def _confidence_icon(conf: str) -> str:
    return {"ELITE": "★★★★", "STRONG": "★★★☆", "CONFIRMED": "★★☆☆", "DEVELOPING": "★☆☆☆"}.get(conf, "★☆☆☆")


def build_morning_brief(snap: PresentationSnapshot, date_str: str) -> str:
    lines = [TG_HEADER, f"*{date_str}*", SEP]

    # ── Runtime Header ────────────────────────────────────────────────────────
    premium = sum(1 for e in snap.timeline if e.get("status") == "PREMIUM_NOW")
    active  = sum(1 for e in snap.timeline if e.get("status") == "ACTIVE_OPPORTUNITY")
    review  = sum(1 for e in snap.timeline if e.get("status") == "UNDER_REVIEW")
    micon   = _market_icon(snap.market_status)

    lines.append(f"{micon} *EGX {snap.market_status}*   Universe: {snap.universe_size} tickers")
    lines.append(
        f"   *{snap.total_events}* Events · *{snap.total_tickers}* Tickers"
        f" · 🟢 First: {len(snap.first_buys)} · 🔵 Re-Accum: {len(snap.re_accumulations)}"
    )
    lines.append(f"   🏆 Premium: {premium} · Active: {active} · Review: {review}")
    if snap.approaching_entries:
        lines.append(f"   🔍 Approaching Entry: {len(snap.approaching_entries)} tickers")
    lines.append("")

    # ── New Events Today ──────────────────────────────────────────────────────
    if snap.new_events_today:
        lines.append(SEP)
        lines.append(f"⚡ *New Constitutional Events Today ({len(snap.new_events_today)})*\n")
        for e in snap.new_events_today:
            if e["event_type"] == "FIRST_BUY":
                lines.append(f"🟢 *FIRST BUY*  *{e['ticker']}*  {e['sector']}")
            else:
                lines.append(f"🔵 *RE-ACCUMULATION*  *{e['ticker']}*  {e['sector']}")
            lines.append(
                f"   Entry Zone: {e['entry_price']:.2f} EGP"
                f"  ·  R2={e['buy_r2']:.1f}"
                f"  ·  Score={e['buy_score']:.1f}"
            )
            if e.get("return_pct") is not None:
                lines.append(f"   Return: {_sign(e['return_pct'])}{e.get('return_pct',0):.1f}%")
            lines.append("")

    # ── Constitutional Leaders ────────────────────────────────────────────────
    if snap.constitutional_leaders:
        lines.append(SEP)
        lines.append(f"🏆 *Constitutional Leaders*\n")
        for i, ldr in enumerate(snap.constitutional_leaders[:8], 1):
            conf_icon = _confidence_icon(ldr["confidence"])
            lines.append(
                f"   {i}. *{ldr['ticker']}*  {conf_icon} {ldr['confidence']}"
                f"  ·  {ldr['total_events']} events"
                f"  ·  avg {_sign(ldr['avg_return_pct'])}{ldr['avg_return_pct']:.1f}%"
                f"  ·  win {ldr['win_rate']*100:.0f}%"
                f"  ·  now {_sign(ldr['current_ret'])}{ldr['current_ret']:.1f}%"
            )
        lines.append("")

    # ── Full Timeline ─────────────────────────────────────────────────────────
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

    # ── Approaching Constitutional Entry ──────────────────────────────────────
    if snap.approaching_entries:
        lines.append(SEP)
        lines.append(f"🔍 *Approaching Constitutional Entry ({len(snap.approaching_entries)} tickers)*\n")
        for e in snap.approaching_entries[:10]:
            dist = e["distance_to_constitutional"]
            urgency = "🔥" if dist <= 0.3 else ("⚠️" if dist <= 1.0 else "📍")
            has_hist = any(l["ticker"] == e["ticker"] for l in snap.constitutional_leaders)
            note = " *(has history)*" if has_hist else ""
            lines.append(
                f"   {urgency} *{e['ticker']}*{note}"
                f"  R2={e['r2_score']:.1f}  Score={e['final_score']:.1f}"
                f"  Dist=–{dist:.1f}pts"
                f"  Zone={e['entry_price']:.2f} EGP"
            )
        lines.append("")

    # ── Leaderboard Snapshot ──────────────────────────────────────────────────
    lb = snap.leaderboards
    if lb:
        lines.append(SEP)
        lines.append("📈 *Most Repeated Constitutional Opportunities*\n")
        for i, a in enumerate(lb.get("most_repeated", [])[:5], 1):
            lines.append(
                f"   {i}. *{a['ticker']}*  {a['total_events']} events"
                f"  avg={_sign(a['avg_return_pct'])}{a['avg_return_pct']:.1f}%"
                f"  best={_sign(a['best_return_pct'])}{a['best_return_pct']:.1f}%"
            )
        lines.append("")

        lines.append("💰 *Highest Compound Return (First Entry → Today)*\n")
        for i, c in enumerate(lb.get("compound_return", [])[:5], 1):
            lines.append(
                f"   {i}. *{c['ticker']}*"
                f"  {_sign(c['compound_return_pct'])}{c['compound_return_pct']:.1f}%"
                f"  ({c['total_events']} events)"
            )
        lines.append("")

    # ── Research ──────────────────────────────────────────────────────────────
    if snap.research_insights:
        ins = snap.research_insights[0]
        lines.append(SEP)
        lines.append(f"🔬 *Research:* {(ins.get('conclusion') or '')[:120]}")
        lines.append("")

    # ── System Diagnostics ────────────────────────────────────────────────────
    lines.append(SEP)
    scan_s = snap.last_scan_ts[:16].replace("T", " ") if snap.last_scan_ts else "—"
    lines.append(f"🔧 *System Diagnostics*")
    lines.append(f"   Timeline: {snap.total_events} events · {snap.total_tickers} tickers")
    lines.append(f"   Universe: {snap.universe_size} · Knowledge: {snap.knowledge_count} findings")
    lines.append(f"   Last scan: {scan_s}")
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
        print("Telegram V4: TELEGRAM_TOKEN or TELEGRAM_CHAT_ID not set — skipping.")
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
                print(f"Telegram V4: chunk sent ({len(chunk)} chars)")
            else:
                print(f"Telegram V4: error {resp.status_code} — {resp.text[:200]}")
        except Exception as e:
            print(f"Telegram V4: exception — {e}")
