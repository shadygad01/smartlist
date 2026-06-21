"""
EGX Constitutional Opportunity Timeline — Email V1
Event-driven morning letter. No portfolio capacity. No HELD/WATCH/RESERVE.
"""
from __future__ import annotations

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


def _ret_color(r: float) -> str:
    return _GREEN if r > 0 else (_RED if r < 0 else _MUTED)

def _star_color(stars: str) -> str:
    n = stars.count("★")
    return _GREEN if n >= 4 else (_AMBER if n == 3 else _RED)

def _sign(r: float) -> str:
    return "+" if r >= 0 else ""

def _status_color(status: str) -> str:
    return _GREEN if status == "PREMIUM_NOW" else (_AMBER if status == "ACTIVE_OPPORTUNITY" else _RED)

def _status_label(status: str) -> str:
    return status.replace("_", " ")

def _type_color(etype: str) -> str:
    return _BLUE if etype == "FIRST_BUY" else _PURPL


def _section_title(title: str) -> str:
    return (
        f'<div style="font-family:Arial,sans-serif;font-size:13px;font-weight:700;'
        f'color:{_NAVY};margin:20px 0 8px 0;letter-spacing:0.4px;'
        f'border-left:4px solid {_NAVY};padding-left:8px;">{title}</div>'
    )


def _hdr(snap: PresentationSnapshot, date_str: str) -> str:
    return f"""
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{_NAVY};">
  <tr><td style="padding:22px 28px;">
    <div style="font-family:Arial,sans-serif;color:{_WHITE};font-size:20px;font-weight:700;">
      EGX Constitutional Opportunity Timeline</div>
    <div style="font-family:Arial,sans-serif;color:#8fb8d8;font-size:12px;margin-top:6px;">
      {date_str}</div>
  </td></tr>
</table>"""


def _exec_summary(snap: PresentationSnapshot) -> str:
    sc      = _star_color(snap.health_stars)
    premium = sum(1 for e in snap.timeline if e.get("status") == "PREMIUM_NOW")
    active  = sum(1 for e in snap.timeline if e.get("status") == "ACTIVE_OPPORTUNITY")
    review  = sum(1 for e in snap.timeline if e.get("status") == "UNDER_REVIEW")
    new_note = (
        f"&nbsp;·&nbsp;<b style='color:{_GREEN};'>⚡ {len(snap.new_events_today)} NEW TODAY</b>"
        if snap.new_events_today else ""
    )
    return (
        _section_title("📋 Executive Summary") +
        f"""<table width="100%" cellpadding="12" cellspacing="0" border="0"
          style="background:{_LIGHT};border:1px solid {_BORD};border-radius:6px;">
  <tr><td style="font-family:Arial,sans-serif;">
    <div style="font-size:18px;font-weight:700;color:{sc};">{snap.health_stars} {snap.health_label}</div>
    <div style="font-size:13px;color:#444;margin-top:6px;">{snap.health_narrative}</div>
    <div style="margin-top:10px;font-size:12px;color:{_MUTED};">
      <b>{snap.total_events}</b> Constitutional Events{new_note} &nbsp;·&nbsp;
      <b>{snap.total_tickers}</b> Tickers &nbsp;·&nbsp;
      <b>{len(snap.first_buys)}</b> First Buys &nbsp;·&nbsp;
      <b>{len(snap.re_accumulations)}</b> Re-Accumulations &nbsp;·&nbsp;
      <b style="color:{_GREEN};">🏆 Premium: {premium}</b> &nbsp;·&nbsp;
      Active: {active} &nbsp;·&nbsp; Review: {review}
    </div>
  </td></tr>
</table>"""
    )


def _new_events_section(snap: PresentationSnapshot) -> str:
    if not snap.new_events_today:
        return ""
    first = [e for e in snap.new_events_today if e["event_type"] == "FIRST_BUY"]
    reac  = [e for e in snap.new_events_today if e["event_type"] == "RE_ACCUMULATION"]

    rows = ""
    for e in snap.new_events_today:
        tc = _type_color(e["event_type"])
        label = "🟢 FIRST BUY" if e["event_type"] == "FIRST_BUY" else "🔵 RE-ACCUMULATION"
        rows += (
            f'<tr style="border-bottom:1px solid #e8f0f8;">'
            f'<td style="padding:8px 12px;font-family:Arial,sans-serif;font-size:12px;'
            f'font-weight:700;color:{tc};">{label}</td>'
            f'<td style="padding:8px 12px;font-family:Arial,sans-serif;font-size:13px;'
            f'font-weight:700;color:{_NAVY};">{e["ticker"]}</td>'
            f'<td style="padding:8px 12px;font-family:Arial,sans-serif;font-size:12px;'
            f'color:{_MUTED};">{e["sector"]}</td>'
            f'<td style="padding:8px 12px;font-family:Arial,sans-serif;font-size:12px;">'
            f'R2={e["buy_r2"]:.1f}</td>'
            f'<td style="padding:8px 12px;font-family:Arial,sans-serif;font-size:12px;'
            f'color:#444;">{e["entry_price"]:.2f} EGP</td>'
            f'</tr>'
        )
    th = (
        f'<tr style="background:{_NAVY};">'
        + "".join(
            f'<th align="left" style="padding:8px 12px;font-family:Arial,sans-serif;'
            f'font-size:11px;color:{_WHITE};">{h}</th>'
            for h in ["Type", "Ticker", "Sector", "R2", "Entry"]
        ) + "</tr>"
    )
    return (
        _section_title(f"⚡ New Constitutional Events Today ({len(snap.new_events_today)})") +
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0"'
        f' style="border:1px solid #c8f0c8;border-collapse:collapse;background:#f0fff0;">'
        f'{th}{rows}</table>'
    )


def _full_timeline(snap: PresentationSnapshot) -> str:
    if not snap.timeline:
        return (
            _section_title("📋 Constitutional Opportunity Timeline") +
            f'<div style="font-family:Arial,sans-serif;font-size:13px;color:{_MUTED};">No events recorded.</div>'
        )

    rows = ""
    for e in snap.timeline:
        rc     = _ret_color(e["return_pct"])
        sc     = _status_color(e["status"])
        tc     = _type_color(e["event_type"])
        label  = "🟢 FIRST" if e["event_type"] == "FIRST_BUY" else "🔵 RE"
        rows += (
            f'<tr style="border-bottom:1px solid #e8f0f8;">'
            f'<td style="padding:6px 10px;font-family:Arial,sans-serif;font-size:11px;'
            f'font-weight:700;color:{tc};">{label}</td>'
            f'<td style="padding:6px 10px;font-family:Arial,sans-serif;font-size:13px;'
            f'font-weight:700;color:{_NAVY};">{e["ticker"]}</td>'
            f'<td style="padding:6px 10px;font-family:Arial,sans-serif;font-size:11px;'
            f'color:{_MUTED};">{e["event_date"]}</td>'
            f'<td style="padding:6px 10px;font-family:Arial,sans-serif;font-size:12px;'
            f'color:{_MUTED};">{e["sector"]}</td>'
            f'<td style="padding:6px 10px;font-family:Arial,sans-serif;font-size:12px;'
            f'color:#444;">{e["entry_price"]:.2f}</td>'
            f'<td style="padding:6px 10px;font-family:Arial,sans-serif;font-size:12px;'
            f'color:#444;">{e["current_price"]:.2f}</td>'
            f'<td style="padding:6px 10px;font-family:Arial,sans-serif;font-size:13px;'
            f'font-weight:700;color:{rc};">{_sign(e["return_pct"])}{e["return_pct"]:.1f}%</td>'
            f'<td style="padding:6px 10px;font-family:Arial,sans-serif;font-size:12px;'
            f'color:{_GREEN};">{_sign(e["peak_return_pct"])}{e["peak_return_pct"]:.1f}%</td>'
            f'<td style="padding:6px 10px;font-family:Arial,sans-serif;font-size:11px;'
            f'color:{_MUTED};">{e["days_active"]}d</td>'
            f'<td style="padding:6px 10px;font-family:Arial,sans-serif;font-size:11px;'
            f'font-weight:700;color:{sc};">{_status_label(e["status"])}</td>'
            f'</tr>'
        )
    th = (
        f'<tr style="background:{_NAVY};">'
        + "".join(
            f'<th align="left" style="padding:7px 10px;font-family:Arial,sans-serif;'
            f'font-size:10px;color:{_WHITE};">{h}</th>'
            for h in ["Type", "Ticker", "Date", "Sector", "Entry", "Current", "Return", "Peak", "Days", "Status"]
        ) + "</tr>"
    )
    return (
        _section_title(f"📋 Constitutional Opportunity Timeline — {snap.total_events} Events (Immutable)") +
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0"'
        f' style="border:1px solid #c8daf5;border-collapse:collapse;">{th}{rows}</table>'
    )


def _leaderboards(snap: PresentationSnapshot) -> str:
    lb = snap.leaderboards
    if not lb:
        return ""

    # Most repeated
    rep_rows = ""
    for i, a in enumerate(lb.get("most_repeated", [])[:6], 1):
        rep_rows += (
            f'<tr style="border-bottom:1px solid #e8f0f8;">'
            f'<td style="padding:6px 10px;font-family:Arial,sans-serif;font-size:11px;color:{_MUTED};">{i}</td>'
            f'<td style="padding:6px 10px;font-family:Arial,sans-serif;font-size:13px;font-weight:700;color:{_NAVY};">{a["ticker"]}</td>'
            f'<td style="padding:6px 10px;font-family:Arial,sans-serif;font-size:12px;color:{_MUTED};">{a["sector"]}</td>'
            f'<td style="padding:6px 10px;font-family:Arial,sans-serif;font-size:12px;color:{_PURPL};font-weight:700;">{a["total_events"]}</td>'
            f'<td style="padding:6px 10px;font-family:Arial,sans-serif;font-size:12px;font-weight:700;color:{_ret_color(a["avg_return_pct"])};">{_sign(a["avg_return_pct"])}{a["avg_return_pct"]:.1f}%</td>'
            f'</tr>'
        )

    # Compound return
    comp_rows = ""
    for i, c in enumerate(lb.get("compound_return", [])[:6], 1):
        comp_rows += (
            f'<tr style="border-bottom:1px solid #e8f0f8;">'
            f'<td style="padding:6px 10px;font-family:Arial,sans-serif;font-size:11px;color:{_MUTED};">{i}</td>'
            f'<td style="padding:6px 10px;font-family:Arial,sans-serif;font-size:13px;font-weight:700;color:{_NAVY};">{c["ticker"]}</td>'
            f'<td style="padding:6px 10px;font-family:Arial,sans-serif;font-size:12px;color:{_MUTED};">{c["total_events"]} events</td>'
            f'<td style="padding:6px 10px;font-family:Arial,sans-serif;font-size:12px;font-weight:700;color:{_ret_color(c["compound_return_pct"])};">{_sign(c["compound_return_pct"])}{c["compound_return_pct"]:.1f}%</td>'
            f'</tr>'
        )

    rep_th = (
        f'<tr style="background:{_NAVY};">'
        + "".join(f'<th align="left" style="padding:6px 10px;font-family:Arial,sans-serif;font-size:10px;color:{_WHITE};">{h}</th>'
                  for h in ["#", "Ticker", "Sector", "Events", "Avg Ret"])
        + "</tr>"
    )
    comp_th = (
        f'<tr style="background:{_NAVY};">'
        + "".join(f'<th align="left" style="padding:6px 10px;font-family:Arial,sans-serif;font-size:10px;color:{_WHITE};">{h}</th>'
                  for h in ["#", "Ticker", "Events", "Compound"])
        + "</tr>"
    )

    return (
        _section_title("🏆 Leaderboards") +
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0">'
        f'<tr><td width="50%" valign="top" style="padding-right:10px;">'
        f'<div style="font-family:Arial,sans-serif;font-size:11px;color:{_PURPL};font-weight:700;margin-bottom:6px;">'
        f'Most Repeated Constitutional Opportunities</div>'
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0"'
        f' style="border:1px solid {_BORD};border-collapse:collapse;">{rep_th}{rep_rows}</table>'
        f'</td><td width="50%" valign="top" style="padding-left:10px;">'
        f'<div style="font-family:Arial,sans-serif;font-size:11px;color:{_GREEN};font-weight:700;margin-bottom:6px;">'
        f'Highest Compound Return</div>'
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0"'
        f' style="border:1px solid {_BORD};border-collapse:collapse;">{comp_th}{comp_rows}</table>'
        f'</td></tr></table>'
    )


def _research(snap: PresentationSnapshot) -> str:
    if not snap.research_insights:
        return ""
    rows = ""
    for ins in snap.research_insights[:3]:
        rows += (
            f'<tr style="border-bottom:1px solid #e8f0f8;">'
            f'<td style="padding:7px 10px;font-family:Arial,sans-serif;font-size:12px;color:#444;">{ins["question"]}</td>'
            f'<td style="padding:7px 10px;font-family:Arial,sans-serif;font-size:12px;color:{_TEXT};">{ins["conclusion"]}</td>'
            f'<td style="padding:7px 10px;font-family:Arial,sans-serif;font-size:11px;color:{_MUTED};">{ins["confidence"]}</td>'
            f'</tr>'
        )
    th = (
        f'<tr style="background:{_NAVY};">'
        + "".join(f'<th align="left" style="padding:7px 10px;font-family:Arial,sans-serif;font-size:11px;color:{_WHITE};">{h}</th>'
                  for h in ["Question", "Conclusion", "Confidence"])
        + "</tr>"
    )
    return (
        _section_title(f"🔬 Research Insights ({snap.knowledge_count} verified findings)") +
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0"'
        f' style="border:1px solid #c8daf5;border-collapse:collapse;">{th}{rows}</table>'
    )


def _footer() -> str:
    return f"""
<table width="100%" cellpadding="0" cellspacing="0" border="0"
  style="margin-top:40px;border-top:1px solid #e8eaed;">
  <tr><td align="center" style="padding:16px;font-family:Arial,sans-serif;
    font-size:11px;color:#bbb;letter-spacing:0.4px;">
    EGX Constitutional Opportunity Timeline &nbsp;·&nbsp; Append-Only &nbsp;·&nbsp;
    Immutable Events &nbsp;·&nbsp; Research-Driven
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
        _new_events_section(snap),
        _full_timeline(snap),
        _leaderboards(snap),
        _research(snap),
        _footer(),
    ])
    return (
        '<!DOCTYPE html><html><body style="margin:0;padding:20px;background:#eef2f7;">'
        '<table width="760" cellpadding="0" cellspacing="0" border="0" align="center"'
        ' style="background:#ffffff;border:1px solid #d0d7e2;">'
        f'<tr><td style="padding:0 24px 24px 24px;">{inner}</td></tr>'
        '</table></body></html>'
    )
