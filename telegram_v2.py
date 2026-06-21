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

    # Registry summary
    icon    = _health_icon(snap.health_stars)
    premium = sum(1 for b in snap.constitutional_buys if b.get("status") == "PREMIUM_NOW")
    active  = sum(1 for b in snap.constitutional_buys if b.get("status") == "ACTIVE_OPPORTUNITY")
    review  = sum(1 for b in snap.constitutional_buys if b.get("status") == "UNDER_REVIEW")

    lines.append(f"{icon} *{snap.health_stars} {snap.health_label}*")
    lines.append(
        f"   *{snap.total_buys}* Constitutional Opportunities"
        f" · Premium: {premium} · Active: {active} · Review: {review}"
    )
    lines.append("")

    # New BUYs today
    if snap.new_buys_today:
        lines.append(SEP)
        lines.append(f"🆕 *NEW Constitutional BUYs Today*\n")
        for b in snap.new_buys_today:
            lines.append(f"🟢 *{b['ticker']}*  {b['sector']}  R2={b['buy_r2']:.1f}")
            lines.append(f"   Entry: {b['buy_price']:.2f} EGP  · Score: {b['buy_score']:.1f}")
            lines.append("")

    # Constitutional BUY Registry — all N entries
    lines.append(SEP)
    lines.append(f"📋 *Constitutional BUY Registry ({snap.total_buys})*\n")
    for b in snap.constitutional_buys:
        sign       = "+" if b["return_pct"] >= 0 else ""
        peak_sign  = "+" if b["peak_return_pct"] >= 0 else ""
        status_icon = "🏆" if b["status"] == "PREMIUM_NOW" else \
                      "🟢" if b["status"] == "ACTIVE_OPPORTUNITY" else "🔴"
        lines.append(
            f"{status_icon} *{b['ticker']}*  {b['buy_date']}"
            f"  Entry={b['buy_price']:.2f}  Now={b['current_price']:.2f}"
            f"  Ret={sign}{b['return_pct']:.1f}%  Peak={peak_sign}{b['peak_return_pct']:.1f}%"
            f"  {b['days_since_buy']}d"
        )
    lines.append("")

    # New opportunities from advisor (today's new signals)
    if snap.opportunities:
        lines.append(SEP)
        lines.append("🎯 *Advisor Opportunities*\n")
        for r in snap.opportunities[:5]:
            conf_icon = "🟢" if r.get("confidence") == "HIGH" else "🟡"
            reason    = (r.get("reason") or "")[:80]
            lines.append(f"{conf_icon} *{r['ticker']}*  {r.get('sector','')}")
            lines.append(f"   {r.get('decision','')}")
            if reason:
                lines.append(f"   _{reason}_")
            lines.append("")

    # Research (top insight only)
    if snap.research_insights:
        ins        = snap.research_insights[0]
        conclusion = (ins.get("conclusion") or "")[:120]
        lines.append(SEP)
        lines.append(f"🔬 *Research:* {conclusion}")
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
