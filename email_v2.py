"""
EGX Constitutional Investment Platform — Email V2
Constitutional Morning Letter. No scanner. No signal engine.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from presentation.presentation_snapshot import PresentationSnapshot, build_presentation_snapshot

# ── Palette ───────────────────────────────────────────────────────────────────
_NAVY  = "#1a3a5c"
_GREEN = "#155724"
_RED   = "#721c24"
_AMBER = "#856404"
_LIGHT = "#f8f9fb"
_BORDER= "#d0d7e2"
_MUTED = "#666666"
_TEXT  = "#333333"
_WHITE = "#ffffff"

_CAP_WARN = 25.0


def _pct_color(pct: float) -> str:
    if pct >= 35: return _RED
    if pct >= _CAP_WARN: return _AMBER
    return _GREEN


def _ret_color(r: float) -> str:
    if r > 0: return _GREEN
    if r < 0: return _RED
    return _MUTED


def _star_color(stars: str) -> str:
    n = stars.count("★")
    if n >= 4: return _GREEN
    if n == 3: return _AMBER
    return _RED


# ── Sections ──────────────────────────────────────────────────────────────────

def _hdr(snap: PresentationSnapshot, date_str: str) -> str:
    return f"""
<table width="100%" cellpadding="0" cellspacing="0" border="0"
  style="background:{_NAVY};">
  <tr><td style="padding:22px 28px;">
    <div style="font-family:Arial,sans-serif;color:{_WHITE};font-size:20px;
      font-weight:700;letter-spacing:0.3px;">EGX Constitutional Morning Brief</div>
    <div style="font-family:Arial,sans-serif;color:#8fb8d8;font-size:12px;
      margin-top:6px;letter-spacing:0.3px;">{date_str}</div>
  </td></tr>
</table>"""


def _section_title(title: str) -> str:
    return (
        f'<div style="font-family:Arial,sans-serif;font-size:13px;font-weight:700;'
        f'color:{_NAVY};margin:20px 0 8px 0;letter-spacing:0.4px;'
        f'border-left:4px solid {_NAVY};padding-left:8px;">{title}</div>'
    )


def _exec_summary(snap: PresentationSnapshot) -> str:
    sc      = _star_color(snap.health_stars)
    premium = sum(1 for b in snap.constitutional_buys if b.get("status") == "PREMIUM_NOW")
    active  = sum(1 for b in snap.constitutional_buys if b.get("status") == "ACTIVE_OPPORTUNITY")
    review  = sum(1 for b in snap.constitutional_buys if b.get("status") == "UNDER_REVIEW")
    new_note = f"&nbsp;·&nbsp;<b style='color:#155724;'>+{len(snap.new_buys_today)} new today</b>" \
               if snap.new_buys_today else ""
    return (
        _section_title("📋 Executive Summary") +
        f"""<table width="100%" cellpadding="12" cellspacing="0" border="0"
          style="background:{_LIGHT};border:1px solid {_BORDER};border-radius:6px;">
  <tr><td style="font-family:Arial,sans-serif;">
    <div style="font-size:18px;font-weight:700;color:{sc};">
      {snap.health_stars} {snap.health_label}</div>
    <div style="font-size:13px;color:#444;margin-top:6px;">{snap.health_narrative}</div>
    <div style="margin-top:10px;font-size:12px;color:{_MUTED};">
      <b>{snap.total_buys}</b> Constitutional Opportunities{new_note} &nbsp;·&nbsp;
      <b style="color:{_GREEN};">Premium: {premium}</b> &nbsp;·&nbsp;
      Active: {active} &nbsp;·&nbsp; Review: {review}
    </div>
  </td></tr>
</table>"""
    )


def _opportunities(snap: PresentationSnapshot) -> str:
    all_opps = snap.opportunities + snap.future_priorities
    if not all_opps:
        return (
            _section_title("🎯 Today's Opportunities") +
            f'<div style="font-family:Arial,sans-serif;font-size:13px;color:{_MUTED};">No active opportunities today.</div>'
        )

    rows = ""
    for r in all_opps:
        rows += f"""
<tr style="border-bottom:1px solid #e8f0f8;">
  <td style="padding:9px 12px;font-family:Arial,sans-serif;font-size:13px;
    font-weight:700;color:{_NAVY};">{r['ticker']}</td>
  <td style="padding:9px 12px;font-family:Arial,sans-serif;font-size:12px;
    color:{_MUTED};">{r.get('sector','')}</td>
  <td style="padding:9px 12px;font-family:Arial,sans-serif;font-size:12px;
    color:{_GREEN};font-weight:600;">{r.get('decision','')}</td>
  <td style="padding:9px 12px;font-family:Arial,sans-serif;font-size:11px;
    color:#555;">{(r.get('reason') or '')[:120]}</td>
</tr>"""

    return (
        _section_title("🎯 Today's Opportunities") +
        f"""<table width="100%" cellpadding="0" cellspacing="0" border="0"
          style="border:1px solid #c8daf5;border-collapse:collapse;">
  <tr style="background:{_NAVY};">
    <th align="left" style="padding:8px 12px;font-family:Arial,sans-serif;
      font-size:11px;color:{_WHITE};">Ticker</th>
    <th align="left" style="padding:8px 12px;font-family:Arial,sans-serif;
      font-size:11px;color:{_WHITE};">Sector</th>
    <th align="left" style="padding:8px 12px;font-family:Arial,sans-serif;
      font-size:11px;color:{_WHITE};">Decision</th>
    <th align="left" style="padding:8px 12px;font-family:Arial,sans-serif;
      font-size:11px;color:{_WHITE};">Notes</th>
  </tr>
  {rows}
</table>"""
    )


def _future_priorities(snap: PresentationSnapshot) -> str:
    if not snap.future_priorities:
        return ""
    tickers = "&nbsp;·&nbsp;".join(f"<b>{r['ticker']}</b>" for r in snap.future_priorities)
    return (
        _section_title("⏳ Future Priorities") +
        f"""<table width="100%" cellpadding="10" cellspacing="0" border="0"
          style="background:#f0f7ff;border:1px solid #d0e4f7;border-radius:4px;">
  <tr><td style="font-family:Arial,sans-serif;font-size:13px;color:#0B5394;">
    {tickers}
  </td></tr>
</table>"""
    )


def _constitutional_registry(snap: PresentationSnapshot) -> str:
    if not snap.constitutional_buys:
        return (
            _section_title("📋 Constitutional BUY Registry") +
            f'<div style="font-family:Arial,sans-serif;font-size:13px;color:{_MUTED};">No constitutional BUYs recorded yet.</div>'
        )

    new_section = ""
    if snap.new_buys_today:
        new_rows = ""
        for b in snap.new_buys_today:
            new_rows += (
                f'<tr><td style="padding:7px 12px;font-family:Arial,sans-serif;'
                f'font-size:13px;font-weight:700;color:{_NAVY};">{b["ticker"]}</td>'
                f'<td style="padding:7px 12px;font-family:Arial,sans-serif;'
                f'font-size:12px;color:{_MUTED};">{b["sector"]}</td>'
                f'<td style="padding:7px 12px;font-family:Arial,sans-serif;'
                f'font-size:12px;">R2={b["buy_r2"]:.1f}</td>'
                f'<td style="padding:7px 12px;font-family:Arial,sans-serif;'
                f'font-size:12px;color:{_GREEN};font-weight:700;">NEW CONSTITUTIONAL BUY</td>'
                f'</tr>'
            )
        new_section = (
            _section_title("🆕 NEW Constitutional BUYs Today") +
            f'<table width="100%" cellpadding="0" cellspacing="0" border="0"'
            f' style="border:1px solid #c8f0c8;border-collapse:collapse;background:#f0fff0;">'
            f'<tr style="background:{_GREEN};">'
            f'<th align="left" style="padding:7px 12px;font-family:Arial,sans-serif;font-size:11px;color:{_WHITE};">Ticker</th>'
            f'<th align="left" style="padding:7px 12px;font-family:Arial,sans-serif;font-size:11px;color:{_WHITE};">Sector</th>'
            f'<th align="left" style="padding:7px 12px;font-family:Arial,sans-serif;font-size:11px;color:{_WHITE};">R2</th>'
            f'<th align="left" style="padding:7px 12px;font-family:Arial,sans-serif;font-size:11px;color:{_WHITE};">Signal</th>'
            f'</tr>{new_rows}</table>'
        )

    rows = ""
    for b in snap.constitutional_buys:
        ret_color  = _ret_color(b["return_pct"])
        sign       = "+" if b["return_pct"] >= 0 else ""
        peak_sign  = "+" if b["peak_return_pct"] >= 0 else ""
        status_color = _GREEN if b["status"] == "PREMIUM_NOW" else \
                       _AMBER if b["status"] == "ACTIVE_OPPORTUNITY" else _RED
        rows += (
            f'<tr style="border-bottom:1px solid #e8f0f8;">'
            f'<td style="padding:7px 12px;font-family:Arial,sans-serif;font-size:13px;'
            f'font-weight:700;color:{_NAVY};">{b["ticker"]}</td>'
            f'<td style="padding:7px 12px;font-family:Arial,sans-serif;font-size:11px;'
            f'color:{_MUTED};">{b["buy_date"]}</td>'
            f'<td style="padding:7px 12px;font-family:Arial,sans-serif;font-size:12px;'
            f'color:{_MUTED};">{b["sector"]}</td>'
            f'<td style="padding:7px 12px;font-family:Arial,sans-serif;font-size:12px;'
            f'color:#444;">{b["buy_price"]:.2f}</td>'
            f'<td style="padding:7px 12px;font-family:Arial,sans-serif;font-size:12px;'
            f'color:#444;">{b["current_price"]:.2f}</td>'
            f'<td style="padding:7px 12px;font-family:Arial,sans-serif;font-size:13px;'
            f'font-weight:700;color:{ret_color};">{sign}{b["return_pct"]:.1f}%</td>'
            f'<td style="padding:7px 12px;font-family:Arial,sans-serif;font-size:12px;'
            f'color:{_GREEN};">{peak_sign}{b["peak_return_pct"]:.1f}%</td>'
            f'<td style="padding:7px 12px;font-family:Arial,sans-serif;font-size:11px;'
            f'color:{_MUTED};">{b["days_since_buy"]}d</td>'
            f'<td style="padding:7px 12px;font-family:Arial,sans-serif;font-size:11px;'
            f'font-weight:700;color:{status_color};">{b["status"].replace("_"," ")}</td>'
            f'</tr>'
        )

    th = (
        f'<tr style="background:{_NAVY};">'
        + "".join(
            f'<th align="left" style="padding:7px 12px;font-family:Arial,sans-serif;'
            f'font-size:11px;color:{_WHITE};">{h}</th>'
            for h in ["Ticker", "BUY Date", "Sector", "Entry", "Current", "Return", "Peak", "Days", "Status"]
        )
        + "</tr>"
    )

    return (
        new_section +
        _section_title(f"📋 Constitutional BUY Registry — {snap.total_buys} Opportunities (Immutable)") +
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0"'
        f' style="border:1px solid #c8daf5;border-collapse:collapse;">'
        f'{th}{rows}</table>'
    )


def _health_metrics(snap: PresentationSnapshot) -> str:
    sector_rows = ""
    for sec, pct in sorted(snap.sector_allocation.items(), key=lambda x: -x[1]):
        color = _pct_color(pct)
        warn  = " ⚠" if pct >= _CAP_WARN else ""
        sector_rows += (
            f'<tr><td style="font-family:Arial,sans-serif;font-size:12px;'
            f'padding:5px 12px;color:#444;width:140px;">{sec}</td>'
            f'<td style="padding:5px 12px;font-family:Arial,sans-serif;font-size:12px;'
            f'font-weight:700;color:{color};">{pct:.1f}%{warn}</td></tr>'
        )

    return (
        _section_title("⚖️ Portfolio Health") +
        f"""<table width="100%" cellpadding="0" cellspacing="0" border="0"
          style="border:1px solid {_BORDER};border-collapse:collapse;">
  <tr style="background:{_LIGHT};">
    <td colspan=2 style="padding:8px 12px;font-family:Arial,sans-serif;font-size:11px;
      font-weight:700;color:#5b6c82;text-transform:uppercase;letter-spacing:0.5px;">
      Sector Allocation</td></tr>
  {sector_rows}
  <tr style="background:{_LIGHT};border-top:1px solid {_BORDER};">
    <td style="padding:8px 12px;font-family:Arial,sans-serif;font-size:12px;color:#444;">
      Max Correlation</td>
    <td style="padding:8px 12px;font-family:Arial,sans-serif;font-size:12px;
      font-weight:700;">{snap.max_correlation:.3f}</td>
  </tr>
  <tr>
    <td style="padding:8px 12px;font-family:Arial,sans-serif;font-size:12px;color:#444;">
      Capacity Used</td>
    <td style="padding:8px 12px;font-family:Arial,sans-serif;font-size:12px;
      font-weight:700;">{snap.capacity_used_pct:.0f}%</td>
  </tr>
</table>"""
    )


def _watch(snap: PresentationSnapshot) -> str:
    if not snap.watch_list:
        return ""
    tickers = " &nbsp;·&nbsp; ".join(f"<b>{t}</b>" for t in snap.watch_list)
    return (
        _section_title("👁 Watch List") +
        f"""<table width="100%" cellpadding="10" cellspacing="0" border="0"
          style="background:{_LIGHT};border:1px solid {_BORDER};border-radius:4px;">
  <tr><td style="font-family:Arial,sans-serif;font-size:13px;color:{_TEXT};">
    {tickers}</td></tr>
</table>"""
    )


def _research(snap: PresentationSnapshot) -> str:
    if not snap.research_insights:
        return ""
    rows = ""
    for ins in snap.research_insights[:3]:
        rows += f"""
<tr style="border-bottom:1px solid #e8f0f8;">
  <td style="padding:8px 12px;font-family:Arial,sans-serif;font-size:12px;color:#444;">
    {ins['question']}</td>
  <td style="padding:8px 12px;font-family:Arial,sans-serif;font-size:12px;color:{_TEXT};">
    {ins['conclusion']}</td>
  <td style="padding:8px 12px;font-family:Arial,sans-serif;font-size:11px;color:{_MUTED};">
    {ins['confidence']}</td>
</tr>"""

    return (
        _section_title(f"🔬 Research Insight ({snap.knowledge_count} verified findings)") +
        f"""<table width="100%" cellpadding="0" cellspacing="0" border="0"
          style="border:1px solid #c8daf5;border-collapse:collapse;">
  <tr style="background:{_NAVY};">
    <th align="left" style="padding:8px 12px;font-family:Arial,sans-serif;
      font-size:11px;color:{_WHITE};">Question</th>
    <th align="left" style="padding:8px 12px;font-family:Arial,sans-serif;
      font-size:11px;color:{_WHITE};">Conclusion</th>
    <th align="left" style="padding:8px 12px;font-family:Arial,sans-serif;
      font-size:11px;color:{_WHITE};">Confidence</th>
  </tr>
  {rows}
</table>"""
    )


def _footer() -> str:
    return f"""
<table width="100%" cellpadding="0" cellspacing="0" border="0"
  style="margin-top:40px;border-top:1px solid #e8eaed;">
  <tr><td align="center" style="padding:16px;font-family:Arial,sans-serif;
    font-size:11px;color:#bbb;letter-spacing:0.4px;">
    EGX Constitutional Investment Platform &nbsp;·&nbsp; Research-Driven &nbsp;·&nbsp;
    Constitutionally Governed
  </td></tr>
</table>"""


# ── Public API ────────────────────────────────────────────────────────────────

def build_email(snap: PresentationSnapshot | None = None) -> str:
    """Return full HTML email string."""
    if snap is None:
        snap = build_presentation_snapshot()

    now_str = datetime.now().strftime("%A, %d %B %Y  ·  %H:%M Cairo")

    parts = [
        _hdr(snap, now_str),
        _exec_summary(snap),
        _constitutional_registry(snap),
        _opportunities(snap),
        _future_priorities(snap),
        _watch(snap),
        _research(snap),
        _footer(),
    ]

    inner = "\n".join(parts)
    return (
        '<!DOCTYPE html><html><body style="margin:0;padding:20px;background:#eef2f7;">'
        '<table width="680" cellpadding="0" cellspacing="0" border="0" align="center"'
        ' style="background:#ffffff;border:1px solid #d0d7e2;">'
        f'<tr><td style="padding:0 24px 24px 24px;">{inner}</td></tr>'
        '</table></body></html>'
    )
