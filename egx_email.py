"""
EGX Constitutional Command Center — Email V6
Section order: Header → Today's Opportunities → Market Status →
               All Active Opportunities → Watch List → Footer
No executive summary, no portfolio advisor, no leaderboards.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone, timedelta
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
_G     = "#4caf50"
_R     = "#f44336"
_A     = "#f0b840"


def _ret_c(r):
    return _GREEN if r > 0 else (_RED if r < 0 else _MUTED)

def _sign(r):
    return "+" if r >= 0 else ""

def _type_lbl(t):
    return "FIRST BUY" if t == "FIRST_BUY" else "RE-ACCUM"

def _type_c(t):
    return _BLUE if t == "FIRST_BUY" else _PURPL

def _section_title(title):
    return (
        f'<div style="font-family:Arial,sans-serif;font-size:13px;font-weight:700;'
        f'color:{_NAVY};margin:22px 0 8px 0;letter-spacing:0.4px;'
        f'border-left:4px solid {_NAVY};padding-left:8px;">{title}</div>'
    )

def _th(*cols):
    return (
        f'<tr style="background:{_NAVY};">'
        + "".join(
            f'<th align="left" style="padding:7px 10px;font-family:Arial,sans-serif;'
            f'font-size:10px;color:{_WHITE};">{h}</th>'
            for h in cols
        ) + "</tr>"
    )

def _opp_row(e):
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

def _opp_table(events):
    rows = "".join(_opp_row(e) for e in events)
    return (
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0"'
        f' style="border:1px solid {_BORD};border-collapse:collapse;">'
        f'{_th("Ticker","Type","Entry Zone","Current","Return %","Signal Date")}'
        f'{rows}</table>'
    )


# ── Sections ──────────────────────────────────────────────────────────────────

def _hdr(snap, date_str):
    mstatus = snap.market_status
    mc = "#4caf50" if "OPEN" in mstatus and "PRE" not in mstatus else "#f0b840"
    new_s = (f'<span style="color:#4caf50;font-weight:700;margin-left:12px;">'
             f'&#9889; {len(snap.new_events_today)} NEW TODAY</span>'
             if snap.new_events_today else "")
    return f"""
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{_NAVY};">
  <tr><td style="padding:22px 28px;">
    <div style="font-family:Arial,sans-serif;color:#8fb8d8;font-size:10px;letter-spacing:1px;
         text-transform:uppercase;margin-bottom:6px;">EGX Constitutional Command Center</div>
    <div style="font-family:Arial,sans-serif;color:{_WHITE};font-size:21px;font-weight:700;">
      Daily Constitutional Report</div>
    <div style="font-family:Arial,sans-serif;color:#8fb8d8;font-size:12px;margin-top:8px;">
      {date_str}
      <span style="color:{mc};font-weight:700;margin-left:12px;">&#11044; EGX {mstatus}</span>
      {new_s}
    </div>
  </td></tr>
</table>"""


def _today_opportunities(snap):
    if not snap.new_events_today:
        return ""
    return (
        _section_title(f"&#9889; Today's Opportunities ({len(snap.new_events_today)} new events)") +
        f'<div style="border:1px solid #c8f0c8;background:#f0fff0;">'
        + _opp_table(snap.new_events_today) + '</div>'
    )


def _market_status_section(snap):
    mstatus = snap.market_status
    mc = _G if "OPEN" in mstatus and "PRE" not in mstatus else (_A if "PRE" in mstatus else _MUTED)
    scan_s = snap.last_scan_ts[:16].replace("T"," ") if snap.last_scan_ts else "--"
    return (
        _section_title("&#127973; Market Status") +
        f'<div style="font-family:Arial,sans-serif;font-size:13px;color:{_TEXT};padding:10px 0;">'
        f'<span style="color:{mc};font-weight:700;">&#11044; EGX {mstatus}</span>'
        f'&nbsp;&nbsp;&middot;&nbsp;&nbsp;Last Scan: <b>{scan_s}</b>'
        f'&nbsp;&nbsp;&middot;&nbsp;&nbsp;Universe: <b>{snap.universe_size}</b> tickers'
        f'</div>'
    )


def _all_active(snap):
    if not snap.timeline:
        return ""
    sorted_tl = sorted(snap.timeline, key=lambda e: -e["return_pct"])
    return (
        _section_title(f"&#128202; All Active Opportunities ({len(snap.timeline)} events)") +
        _opp_table(sorted_tl)
    )


def _watch_list(snap):
    if not snap.approaching_entries:
        return ""
    rows = ""
    for e in snap.approaching_entries:
        dist = e["distance_to_constitutional"]
        urg  = _GREEN if dist <= 0.3 else (_AMBER if dist <= 1.0 else _MUTED)
        waiting = f"&#8211;{dist:.1f} pts to constitutional"
        rows += (
            f'<tr style="border-bottom:1px solid #e8f0f8;">'
            f'<td style="padding:7px 10px;font-family:Arial,sans-serif;font-size:13px;font-weight:700;color:{_NAVY};">{e["ticker"]}</td>'
            f'<td style="padding:7px 10px;font-family:Arial,sans-serif;font-size:12px;color:{_MUTED};">{e.get("sector","")}</td>'
            f'<td style="padding:7px 10px;font-family:Arial,sans-serif;font-size:12px;">{e["current_price"]:.2f}</td>'
            f'<td style="padding:7px 10px;font-family:Arial,sans-serif;font-size:12px;">{e["entry_price"]:.2f} EGP</td>'
            f'<td style="padding:7px 10px;font-family:Arial,sans-serif;font-size:12px;color:{urg};font-weight:700;">{waiting}</td>'
            f'</tr>'
        )
    return (
        _section_title(f"&#128269; Watch List ({len(snap.approaching_entries)} approaching)") +
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0"'
        f' style="border:1px solid #e8d5a0;border-collapse:collapse;background:#fffcf0;">'
        f'{_th("Ticker","Sector","Current","Entry Zone","Waiting For")}'
        f'{rows}</table>'
    )


def _footer():
    return f"""
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:32px;border-top:1px solid #e8eaed;">
  <tr><td align="center" style="padding:14px;font-family:Arial,sans-serif;font-size:11px;color:#bbb;">
    EGX Constitutional Command Center &nbsp;&middot;&nbsp; Append-Only &middot; Immutable Events<br>
    <span style="font-size:10px;color:#ccc;">
      This report is for informational purposes only and does not constitute financial advice.
      Past constitutional signals do not guarantee future returns.
      All investments carry risk. Consult a licensed financial advisor before making investment decisions.
    </span>
  </td></tr>
</table>"""


def build_email(snap: PresentationSnapshot | None = None) -> str:
    if snap is None:
        snap = build_presentation_snapshot()
    cairo_tz = timezone(timedelta(hours=2))
    now_str  = datetime.now(cairo_tz).strftime("%A, %d %B %Y  &#183;  %H:%M Cairo")
    inner = "\n".join([
        _hdr(snap, now_str),
        _today_opportunities(snap),
        _market_status_section(snap),
        _all_active(snap),
        _watch_list(snap),
        _footer(),
    ])
    return (
        '<!DOCTYPE html><html><body style="margin:0;padding:20px;background:#eef2f7;">'
        '<table width="600" cellpadding="0" cellspacing="0" border="0" align="center"'
        ' style="background:#ffffff;border:1px solid #d0d7e2;max-width:600px;">'
        f'<tr><td style="padding:0 24px 24px 24px;">{inner}</td></tr>'
        '</table></body></html>'
    )


if __name__ == "__main__":
    out  = Path(__file__).parent / "email.html"
    html = build_email()
    out.write_text(html, encoding="utf-8")
    sha  = hashlib.sha256(html.encode()).hexdigest()
    print(f"[Email V6] Saved email.html ({len(html)//1024} KB)")
    print(f"[Email V6] SHA256: {sha[:32]}...")
