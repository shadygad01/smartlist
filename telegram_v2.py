"""
EGX Constitutional Investment Platform — Telegram V2
Constitutional Morning Brief. Consumes PresentationSnapshot only — no own SQL.
"""
from __future__ import annotations

import os
import requests
from datetime import datetime, timezone, timedelta

from presentation.presentation_snapshot import PresentationSnapshot, build_presentation_snapshot

_CAIRO_TZ = timezone(timedelta(hours=2))

TG_HEADER = "📋 *EGX Constitutional Morning Brief*"
SEP       = "━━━━━━━━━━━━━━━━━━━━━"
MAX_CHARS = 4000


def _health_icon(stars: str) -> str:
    n = stars.count("★")
    if n >= 4: return "🟢"
    if n == 3: return "🟡"
    return "🔴"


def _near(snap: PresentationSnapshot) -> list[dict]:
    return snap.approaching_entries


def _active(snap: PresentationSnapshot) -> list[dict]:
    return [u for u in snap.universe_snapshot if u["status"] in ("ACTIVE", "PREMIUM", "UNDER_REVIEW")]


def _future(snap: PresentationSnapshot) -> list[dict]:
    near_t   = {e["ticker"] for e in snap.approaching_entries}
    active_t = {u["ticker"] for u in snap.universe_snapshot
                if u["status"] in ("ACTIVE", "PREMIUM", "UNDER_REVIEW")}
    return [u for u in snap.universe_snapshot
            if u["ticker"] not in near_t and u["ticker"] not in active_t]


def build_morning_brief(snap: PresentationSnapshot, date_str: str) -> str:
    lines = [
        TG_HEADER,
        f"*{date_str}*",
        SEP,
    ]

    # Health
    icon = _health_icon(snap.health_stars)
    lines.append(f"{icon} *{snap.health_stars} {snap.health_label}*")
    if snap.health_narrative:
        lines.append(f"_{snap.health_narrative[:120]}_")
    lines.append("")

    # Statistics summary
    near_items   = _near(snap)
    active_items = _active(snap)
    re_items     = snap.re_accumulations
    future_items = _future(snap)
    lines.append(
        f"📊 Universe: *{snap.universe_size}* tickers · "
        f"*{len(near_items)}* near entry · "
        f"*{len(active_items)}* active · "
        f"*{len(re_items)}* re-acc"
    )
    lines.append("")

    # Near Constitutional Entry
    if near_items:
        lines.append(SEP)
        lines.append("🎯 *Near Constitutional Entry*\n")
        for r in near_items:
            r2   = r.get("r2_score", 0)
            dist = r.get("distance_to_constitutional", 0)
            cp   = r.get("current_price") or 0
            ep   = r.get("entry_price") or 0
            lines.append(
                f"• *{r['ticker']}*  R2 {r2:.1f}  ({dist:.1f} pts to gate)"
            )
            lines.append(f"   Price {cp:.2f} / Entry {ep:.2f} EGP")
        lines.append("")

    # Active Positions
    if active_items:
        lines.append(SEP)
        lines.append("⭐ *Active Constitutional Positions*\n")
        for u in active_items:
            ret  = u.get("return_pct") or 0.0
            sign = "+" if ret > 0 else ""
            icon = "🏆" if u["status"] == "PREMIUM" else ("⚠" if u["status"] == "UNDER_REVIEW" else "✓")
            lines.append(f"{icon} *{u['ticker']}*  {sign}{ret:.1f}%  ({u['status']})")
        lines.append("")

    # Re-Accumulation
    near_t   = {e["ticker"] for e in near_items}
    active_t = {u["ticker"] for u in active_items}
    re_candidates = [e for e in re_items if e["ticker"] in near_t or e["ticker"] in active_t]
    if re_candidates:
        lines.append(SEP)
        chips = "  ·  ".join(f"*{e['ticker']}*" for e in re_candidates)
        lines.append(f"🔄 *Re-Accumulation:* {chips}")
        lines.append("")

    # Future / Watch
    fut_show = [u for u in future_items if u["status"] in ("APPROACHING", "BELOW_THRESHOLD")][:6]
    if fut_show:
        lines.append(SEP)
        lines.append("🔍 *Future Watch List*\n")
        for u in fut_show:
            r2 = u.get("r2_score") or 0
            ez = u.get("entry_zone")
            ez_s = f"{ez:.2f}" if ez else "No entry zone"
            lines.append(f"• *{u['ticker']}*  R2 {r2:.1f}  Entry {ez_s}")
        lines.append("")

    # New events today
    if snap.new_events_today:
        lines.append(SEP)
        events_str = "  ·  ".join(
            f"*{e['ticker']}* ({e['event_type'].replace('_', ' ')})"
            for e in snap.new_events_today[:5]
        )
        lines.append(f"🆕 *Today's Events:* {events_str}")
        lines.append("")

    # Research
    if snap.research_insights:
        ins        = snap.research_insights[0]
        conclusion = (ins.get("conclusion") or "")[:120]
        lines.append(SEP)
        lines.append(f"🔬 *Research:* {conclusion}")
        lines.append("")

    lines.append(SEP)
    lines.append(f"⏰ {datetime.now(_CAIRO_TZ).strftime('%H:%M  |  %d %b %Y')} Cairo")
    lines.append(f"_Timeline: {snap.total_events} events · {snap.total_tickers} tickers_")

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
    """Send constitutional morning brief to Telegram."""
    token   = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("Telegram V2: TELEGRAM_TOKEN or TELEGRAM_CHAT_ID not set — skipping.")
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
                print(f"Telegram V2: chunk sent ({len(chunk)} chars)")
            else:
                print(f"Telegram V2: error {resp.status_code} — {resp.text[:200]}")
        except Exception as e:
            print(f"Telegram V2: exception — {e}")
