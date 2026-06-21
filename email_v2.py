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
    sc = _star_color(snap.health_stars)
    cap_note = f"Capacity <b>{snap.capacity_used_pct:.0f}%</b>" + \
               (" ⚠" if snap.capacity_used_pct > 100 else "")
    sector_note = "" if snap.sector_cap_ok else "&nbsp;·&nbsp;<b style='color:#721c24;'>Sector cap exceeded</b>"
    return (
        _section_title("📋 Executive Summary") +
        f"""<table width="100%" cellpadding="12" cellspacing="0" border="0"
          style="background:{_LIGHT};border:1px solid {_BORDER};border-radius:6px;">
  <tr><td style="font-family:Arial,sans-serif;">
    <div style="font-size:18px;font-weight:700;color:{sc};">
      {snap.health_stars} {snap.health_label}</div>
    <div style="font-size:13px;color:#444;margin-top:6px;">{snap.health_narrative}</div>
    <div style="margin-top:10px;font-size:12px;color:{_MUTED};">
      <b>{snap.held_count}</b> positions held &nbsp;·&nbsp;
      {cap_note} &nbsp;·&nbsp;
      Max Correlation <b>{snap.max_correlation:.2f}</b>{sector_note}
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


def _portfolio(snap: PresentationSnapshot) -> str:
    rows = ""
    for p in snap.held_positions:
        rc = _ret_color(p["return_pct"])
        sign = "+" if p["return_pct"] > 0 else ""
        rows += f"""
<tr style="border-bottom:1px solid #e8f0f8;">
  <td style="padding:8px 12px;font-family:Arial,sans-serif;font-size:13px;
    font-weight:700;color:{_NAVY};">{p['ticker']}</td>
  <td style="padding:8px 12px;font-family:Arial,sans-serif;font-size:12px;
    color:{_MUTED};">{p['sector']}</td>
  <td style="padding:8px 12px;font-family:Arial,sans-serif;font-size:12px;
    color:#444;">{p['entry_price']:.2f} EGP</td>
  <td style="padding:8px 12px;font-family:Arial,sans-serif;font-size:12px;
    color:#444;">{p['current_price']:.2f} EGP</td>
  <td style="padding:8px 12px;font-family:Arial,sans-serif;font-size:13px;
    font-weight:700;color:{rc};">{sign}{p['return_pct']:.1f}%</td>
</tr>"""

    if not rows:
        rows = f'<tr><td colspan=5 style="padding:12px;color:{_MUTED};text-align:center;">No positions held.</td></tr>'

    return (
        _section_title(f"📂 Current Portfolio ({snap.held_count} positions)") +
        f"""<table width="100%" cellpadding="0" cellspacing="0" border="0"
          style="border:1px solid #c8daf5;border-collapse:collapse;">
  <tr style="background:#0B5394;">
    <th align="left" style="padding:8px 12px;font-family:Arial,sans-serif;
      font-size:11px;color:{_WHITE};">Ticker</th>
    <th align="left" style="padding:8px 12px;font-family:Arial,sans-serif;
      font-size:11px;color:{_WHITE};">Sector</th>
    <th align="left" style="padding:8px 12px;font-family:Arial,sans-serif;
      font-size:11px;color:{_WHITE};">Entry</th>
    <th align="left" style="padding:8px 12px;font-family:Arial,sans-serif;
      font-size:11px;color:{_WHITE};">Current</th>
    <th align="left" style="padding:8px 12px;font-family:Arial,sans-serif;
      font-size:11px;color:{_WHITE};">Return</th>
  </tr>
  {rows}
</table>"""
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
        _opportunities(snap),
        _future_priorities(snap),
        _portfolio(snap),
        _health_metrics(snap),
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
