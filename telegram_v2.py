"""
EGX Constitutional Investment Platform — Telegram V2
Constitutional 15-second Morning Brief. No scanner. No signal engine.
"""
from __future__ import annotations

import os
import requests

from presentation.presentation_snapshot import PresentationSnapshot, build_presentation_snapshot

TG_HEADER = "📋 *EGX Constitutional Morning Brief*"
SEP       = "━━━━━━━━━━━━━━━━━━━━━"
MAX_CHARS = 4000


def _health_icon(stars: str) -> str:
    n = stars.count("★")
    if n >= 4: return "🟢"
    if n == 3: return "🟡"
    return "🔴"


def build_morning_brief(snap: PresentationSnapshot, date_str: str) -> str:
    from datetime import datetime
    lines = [
        TG_HEADER,
        f"*{date_str}*",
        SEP,
    ]

    # Portfolio Health
    icon = _health_icon(snap.health_stars)
    lines.append(f"{icon} Portfolio Health: *{snap.health_stars} {snap.health_label}*")
    lines.append(
        f"   {snap.held_count} positions"
        f" · Capacity {snap.capacity_used_pct:.0f}%"
        f" · Corr {snap.max_correlation:.2f}"
    )
    lines.append("")

    # Opportunities
    all_opps = snap.opportunities + snap.future_priorities
    if all_opps:
        lines.append(SEP)
        lines.append("🎯 *Today's Opportunities*\n")
        for r in all_opps:
            conf_icon = "🟢" if r.get("confidence") == "HIGH" else "🟡"
            reason    = (r.get("reason") or "")[:80]
            lines.append(f"{conf_icon} *{r['ticker']}*  {r.get('sector','')}")
            lines.append(f"   {r.get('decision','')}")
            if reason:
                lines.append(f"   _{reason}_")
            lines.append("")

    # Future Priorities (brief chip line)
    fp_tickers = [r["ticker"] for r in snap.future_priorities]
    if fp_tickers:
        fp_str = "  ·  ".join(f"*{t}*" for t in fp_tickers)
        lines.append(f"⏳ *Future Priority:* {fp_str}")
        lines.append("")

    # Watch List
    if snap.watch_list:
        lines.append(SEP)
        watch_str = "  ·  ".join(snap.watch_list)
        lines.append(f"👁 *Watch List:* {watch_str}")
        lines.append("")

    # Research (top insight only)
    if snap.research_insights:
        ins        = snap.research_insights[0]
        conclusion = (ins.get("conclusion") or "")[:120]
        question   = (ins.get("question") or "")[:80]
        lines.append(SEP)
        lines.append(f"🔬 *Research:* {conclusion}")
        if question:
            lines.append(f"   _{question}_")
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
    """Send constitutional morning brief to Telegram."""
    if snap is None:
        snap = build_presentation_snapshot()

    full_msg = build_morning_brief(snap, date_str)

    from notifications.telegram_sender import send as _tg
    _tg(full_msg, subject="MorningBrief")
