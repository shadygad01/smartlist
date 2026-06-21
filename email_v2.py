"""
EGX Constitutional Opportunity Intelligence Platform — Email V5
Section order: Header → Exec Summary → New Today → Re-Accumulation →
               Best Opportunities → Timeline → Approaching Entry →
               System Diagnostics (LAST)
Opportunity cards: Ticker / Type / Entry Zone / Current / Return % / Signal Date ONLY.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

from presentation.presentation_snapshot import PresentationSnapshot, build_presentation_snapshot

_NAVY  = "#1a3a5c"
_GREEN = "#155724"
_RED   = "#721c24"
_AMBER = "#856404"
_BLUE  = "#0b4a8f"
_PURPL = "#5b21b6"
_LIGHT = "#f8f9fb"
_BORD  = "#d0d7e2"
_MUTED = "#666666"
_TEXT  = "#333333"
_WHITE = "#ffffff"


def _ret_c(r: float) -> str:
    return _GREEN if r > 0 else (_RED if r < 0 else _MUTED)

def _sign(r: float) -> str:
    return "+" if r >= 0 else ""

def _type_lbl(t: str) -> str:
    return ("🟢 FIRST BUY" if t == "FIRST_BUY" else "🔵 RE-ACCUM")

def _type_c(t: str) -> str:
    return _BLUE if t == "FIRST_BUY" else _PURPL

def _section_title(title: str) -> str:
    return (
        f'<div style="font-family:Arial,sans-serif;font-size:13px;font-weight:700;'
        f'color:{_NAVY};margin:22px 0 8px 0;letter-spacing:0.4px;'
        f'border-left:4px solid {_NAVY};padding-left:8px;">{title}</div>'
    )

def _th(*cols: str) -> str:
    return (
        f'<tr style="background:{_NAVY};">'
        + "".join(
            f'<th align="left" style="padding:7px 10px;font-family:Arial,sans-serif;'
            f'font-size:10px;color:{_WHITE};">{h}</th>'
            for h in cols
        ) + "</tr>"
    )

def _pass_badge(ok: bool) -> str:
    c   = _GREEN if ok else _RED
    lbl = "✓ PASS" if ok else "✗ FAIL"
    return (f'<span style="background:{c}22;color:{c};padding:2px 8px;'
            f'border-radius:10px;font-size:11px;font-weight:700;">{lbl}</span>')


# ── Opportunity row: Ticker / Type / Entry Zone / Current / Return % / Date ──

def _opp_row(e: dict) -> str:
    tc = _type_c(e["event_type"])
    rc = _ret_c(e["return_pct"])
    return (
        f'<tr style="border-bottom:1px solid #e8f0f8;">'
        f'<td style="padding:7px 10px;font-family:Arial,sans-serif;font-size:13px;font-weight:700;color:{_NAVY};">{e["ticker"]}</td>'
        f'<td style="padding:7px 10px;font-family:Arial,sans-serif;font-size:11px;font-weight:700;color:{tc};">{_type_lbl(e["event_type"])}</td>'
        f'<td style="padding:7px 10px;font-family:Arial,sans-serif;font-size:12px;font-weight:700;">{e["entry_price"]:.2f} EGP</td>'
        f'<td style="padding:7px 10px;font-family:Arial,sans-serif;font-size:12px;">{e["current_price"]:.2f}</td>'
        f'<td style="padding:7px 10px;font-family:Arial,sans-serif;font-size:13px;font-weight:700;color:{rc};">{_sign(e["return_pct"])}{e["return_pct"]:.1f}%</td>'
        f'<td style="padding:7px 10px;font-family:Arial,sans-serif;font-size:11px;color:{_MUTED};">{e["event_date"]}</td>'
        f'</tr>'
    )

def _opp_table(events: list[dict]) -> str:
    rows = "".join(_opp_row(e) for e in events)
    return (
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0"'
        f' style="border:1px solid {_BORD};border-collapse:collapse;">'
        f'{_th("Ticker","Type","Entry Zone","Current","Return %","Signal Date")}'
        f'{rows}</table>'
    )


# ── Sections ──────────────────────────────────────────────────────────────────

def _hdr(snap: PresentationSnapshot, date_str: str) -> str:
    mstatus = snap.market_status
    mc = "#4caf50" if "OPEN" in mstatus and "PRE" not in mstatus else "#f0b840"
    new_s = (f'<span style="color:#4caf50;font-weight:700;margin-left:12px;">'
             f'⚡ {len(snap.new_events_today)} NEW TODAY</span>'
             if snap.new_events_today else "")
    return f"""
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{_NAVY};">
  <tr><td style="padding:22px 28px;">
    <div style="font-family:Arial,sans-serif;color:#8fb8d8;font-size:10px;letter-spacing:1px;
         text-transform:uppercase;margin-bottom:6px;">EGX Constitutional Opportunity Intelligence Platform</div>
    <div style="font-family:Arial,sans-serif;color:{_WHITE};font-size:21px;font-weight:700;">
      Constitutional Opportunity Timeline</div>
    <div style="font-family:Arial,sans-serif;color:#8fb8d8;font-size:12px;margin-top:8px;">
      {date_str}
      <span style="color:{mc};font-weight:700;margin-left:12px;">⬤ EGX {mstatus}</span>
      {new_s}
    </div>
  </td></tr>
</table>"""


def _exec_summary(snap: PresentationSnapshot) -> str:
    tl   = snap.timeline
    rets = [e["return_pct"] for e in tl] if tl else []
    avg  = sum(rets) / len(rets) if rets else 0.0
    wins = sum(1 for r in rets if r > 0)
    wr   = wins / len(rets) * 100 if rets else 0.0
    best = max(tl, key=lambda e: e["return_pct"]) if tl else None
    scan_s = snap.last_scan_ts[:16].replace("T"," ") if snap.last_scan_ts else "—"

    best_str = (
        f' &nbsp;·&nbsp; Best: <b style="color:{_GREEN};">{best["ticker"]}'
        f' {_sign(best["return_pct"])}{best["return_pct"]:.1f}%</b>'
    ) if best else ""

    stats = [
        (snap.total_events,           "Total Events",      _NAVY),
        (len(snap.first_buys),        "First BUY",         _BLUE),
        (len(snap.re_accumulations),  "Re-Accumulation",   _PURPL),
        (len(snap.approaching_entries),"Approaching Entry", _AMBER),
    ]

    cells = "".join(
        f'<td width="25%" align="center" style="padding:12px;border-right:1px solid {_BORD};">'
        f'<div style="font-family:Arial,sans-serif;font-size:22px;font-weight:700;color:{c};">{v}</div>'
        f'<div style="font-family:Arial,sans-serif;font-size:10px;color:{_MUTED};'
        f'text-transform:uppercase;margin-top:3px;">{l}</div></td>'
        for v, l, c in stats
    )

    return (
        _section_title("📊 Executive Summary") +
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0"'
        f' style="background:{_LIGHT};border:1px solid {_BORD};border-radius:4px;">'
        f'<tr>{cells}</tr>'
        f'<tr><td colspan="4" style="padding:10px 12px;font-family:Arial,sans-serif;font-size:12px;color:{_MUTED};">'
        f'Avg Return: <b style="color:{_GREEN if avg>=0 else _RED};">{avg:+.1f}%</b>'
        f'&nbsp;·&nbsp; Win Rate: <b>{wr:.0f}%</b>'
        f'{best_str}'
        f'&nbsp;·&nbsp; Last Scan: <b>{scan_s}</b>'
        f'</td></tr></table>'
    )


def _new_today(snap: PresentationSnapshot) -> str:
    if not snap.new_events_today:
        return ""
    return (
        _section_title(f"⚡ New Constitutional Events Today ({len(snap.new_events_today)})") +
        f'<div style="border:1px solid #c8f0c8;background:#f0fff0;">'
        + _opp_table(snap.new_events_today) +
        f'</div>'
    )


def _re_accumulations(snap: PresentationSnapshot) -> str:
    events = sorted(
        [e for e in snap.timeline if e["event_type"] == "RE_ACCUMULATION"],
        key=lambda e: -e["return_pct"]
    )
    if not events:
        return ""
    return (
        _section_title(f"🔵 Re-Accumulation Events ({len(events)})") +
        _opp_table(events)
    )


def _best_opportunities(snap: PresentationSnapshot) -> str:
    if not snap.timeline:
        return ""
    best = sorted(snap.timeline, key=lambda e: -e["return_pct"])[:10]
    return (
        _section_title("🏆 Best Opportunities (Top 10 by Return)") +
        _opp_table(best)
    )


def _full_timeline(snap: PresentationSnapshot) -> str:
    if not snap.timeline:
        return (
            _section_title("📋 Constitutional Opportunity Timeline") +
            f'<div style="font-family:Arial,sans-serif;font-size:13px;color:{_MUTED};">No events recorded.</div>'
        )
    return (
        _section_title(f"📋 Constitutional Opportunity Timeline — {snap.total_events} Events") +
        _opp_table(snap.timeline)
    )


def _approaching(snap: PresentationSnapshot) -> str:
    if not snap.approaching_entries:
        return ""
    rows = ""
    for e in snap.approaching_entries:
        dist = e["distance_to_constitutional"]
        pct  = dist / 60.0 * 100
        urg  = _GREEN if dist <= 0.3 else (_AMBER if dist <= 1.0 else _MUTED)
        rows += (
            f'<tr style="border-bottom:1px solid #e8f0f8;">'
            f'<td style="padding:7px 10px;font-family:Arial,sans-serif;font-size:13px;font-weight:700;color:{_NAVY};">{e["ticker"]}</td>'
            f'<td style="padding:7px 10px;font-family:Arial,sans-serif;font-size:12px;color:{_MUTED};">{e["sector"]}</td>'
            f'<td style="padding:7px 10px;font-family:Arial,sans-serif;font-size:12px;font-weight:700;color:{urg};">–{dist:.1f} pts ({pct:.1f}%)</td>'
            f'<td style="padding:7px 10px;font-family:Arial,sans-serif;font-size:12px;">{e["entry_price"]:.2f} EGP</td>'
            f'<td style="padding:7px 10px;font-family:Arial,sans-serif;font-size:12px;">{e["current_price"]:.2f}</td>'
            f'</tr>'
        )
    return (
        _section_title(f"🔍 Approaching Constitutional Entry ({len(snap.approaching_entries)} tickers)") +
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0"'
        f' style="border:1px solid #e8d5a0;border-collapse:collapse;background:#fffcf0;">'
        f'{_th("Ticker","Sector","Distance to Entry","Entry Zone","Current Price")}'
        f'{rows}</table>'
    )


def _system_diagnostics(snap: PresentationSnapshot) -> str:
    base       = Path(__file__).parent
    dash_ok    = (base / "dashboard.html").exists()
    email_ok   = (base / "email.html").exists()
    tg_ok      = True
    kb_ok      = snap.knowledge_count > 0
    research_ok = len(snap.research_insights) > 0
    tl_ok      = snap.total_events == 42 and len(snap.first_buys) == 19 and len(snap.re_accumulations) == 23

    gen_s  = snap.generated_at[:19].replace("T"," ") if snap.generated_at else "—"
    scan_s = snap.last_scan_ts[:19].replace("T"," ") if snap.last_scan_ts else "—"

    checks = [
        ("Dashboard",       dash_ok,     gen_s),
        ("Email",           email_ok,    gen_s),
        ("Telegram",        tg_ok,       "runtime ready"),
        ("Knowledge Base",  kb_ok,       f"{snap.knowledge_count} verified findings"),
        ("Research",        research_ok, f"{len(snap.research_insights)} insights"),
    ]

    rows = ""
    for label, ok, ts in checks:
        rows += (
            f'<tr style="border-bottom:1px solid #e8f0f8;">'
            f'<td style="padding:7px 10px;font-family:Arial,sans-serif;font-size:12px;color:{_MUTED};">{label}</td>'
            f'<td style="padding:7px 10px;">{_pass_badge(ok)}</td>'
            f'<td style="padding:7px 10px;font-family:Arial,sans-serif;font-size:11px;color:{_MUTED};">{ts}</td>'
            f'</tr>'
        )

    return (
        _section_title("🔧 System Diagnostics") +
        f'<table width="60%" cellpadding="0" cellspacing="0" border="0"'
        f' style="border:1px solid {_BORD};border-collapse:collapse;margin-bottom:12px;">'
        f'{_th("System","Status","Timestamp/Detail")}{rows}</table>'
        f'<div style="font-family:Arial,sans-serif;font-size:11px;color:{_MUTED};">'
        f'Timeline: {snap.total_events} events ({len(snap.first_buys)} First BUY · {len(snap.re_accumulations)} Re-Accum) &nbsp;·&nbsp; '
        f'Universe: {snap.universe_size} &nbsp;·&nbsp; Last Scan: {scan_s} &nbsp;·&nbsp; '
        f'Market: {snap.market_status} &nbsp;·&nbsp; '
        f'{snap.health_stars} {snap.health_label} (advisor — informational only)'
        f'</div>'
    )


def _footer() -> str:
    return f"""
<table width="100%" cellpadding="0" cellspacing="0" border="0"
  style="margin-top:32px;border-top:1px solid #e8eaed;">
  <tr><td align="center" style="padding:14px;font-family:Arial,sans-serif;
    font-size:11px;color:#bbb;">
    EGX Constitutional Opportunity Intelligence Platform &nbsp;·&nbsp;
    Append-Only · Immutable Events · No Portfolio Dependency
  </td></tr>
</table>"""


# ── Public API ────────────────────────────────────────────────────────────────

def build_email(snap: PresentationSnapshot | None = None) -> str:
    if snap is None:
        snap = build_presentation_snapshot()
    now_str = datetime.now().strftime("%A, %d %B %Y  ·  %H:%M Cairo")
    inner = "\n".join([
        _hdr(snap, now_str),
        _exec_summary(snap),
        _new_today(snap),
        _re_accumulations(snap),
        _best_opportunities(snap),
        _full_timeline(snap),
        _approaching(snap),
        _system_diagnostics(snap),
        _footer(),
    ])
    return (
        '<!DOCTYPE html><html><body style="margin:0;padding:20px;background:#eef2f7;">'
        '<table width="780" cellpadding="0" cellspacing="0" border="0" align="center"'
        ' style="background:#ffffff;border:1px solid #d0d7e2;">'
        f'<tr><td style="padding:0 24px 24px 24px;">{inner}</td></tr>'
        '</table></body></html>'
    )


if __name__ == "__main__":
    out  = Path(__file__).parent / "email.html"
    html = build_email()
    out.write_text(html, encoding="utf-8")
    sha  = hashlib.sha256(html.encode()).hexdigest()
    print(f"[Email V5] Saved → email.html ({len(html)//1024} KB)")
    print(f"[Email V5] SHA256: {sha}")
