"""
DEPRECATED — DO NOT USE FOR MORNING REPORTS.
Canonical builder is egx_email.py → build_email(snap).
This file is preserved for reference only and is not imported by any active code path.
"""
# ruff: noqa
# pylint: skip-file
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path

from presentation.presentation_snapshot import PresentationSnapshot, build_presentation_snapshot

_CAIRO_TZ = timezone(timedelta(hours=2))

# ── Palette ────────────────────────────────────────────────────────────────────
_NAVY  = "#1a3a5c"
_GREEN = "#155724"
_RED   = "#721c24"
_AMBER = "#856404"
_LIGHT = "#f8f9fb"
_BORDER= "#d0d7e2"
_MUTED = "#666666"
_TEXT  = "#333333"
_WHITE = "#ffffff"


def _ret_color(r: float) -> str:
    if r > 0:  return _GREEN
    if r < 0:  return _RED
    return _MUTED


def _star_color(stars: str) -> str:
    n = stars.count("★")
    if n >= 4: return _GREEN
    if n == 3: return _AMBER
    return _RED


# ── Constitutional data helpers (no SQL — derive from snap fields only) ────────

def _near(snap: PresentationSnapshot) -> list[dict]:
    return snap.approaching_entries


def _active(snap: PresentationSnapshot) -> list[dict]:
    return [u for u in snap.universe_snapshot if u["status"] in ("ACTIVE", "PREMIUM", "UNDER_REVIEW")]


def _re_acc(snap: PresentationSnapshot) -> list[dict]:
    return snap.re_accumulations


def _future(snap: PresentationSnapshot) -> list[dict]:
    near_t   = {e["ticker"] for e in snap.approaching_entries}
    active_t = {u["ticker"] for u in snap.universe_snapshot
                if u["status"] in ("ACTIVE", "PREMIUM", "UNDER_REVIEW")}
    return [u for u in snap.universe_snapshot
            if u["ticker"] not in near_t and u["ticker"] not in active_t]


# ── Sections ──────────────────────────────────────────────────────────────────

def _hdr(date_str: str) -> str:
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
    near_count   = len(_near(snap))
    active_count = len(_active(snap))
    re_count     = len(_re_acc(snap))
    return (
        _section_title("📋 Executive Summary") +
        f"""<table width="100%" cellpadding="12" cellspacing="0" border="0"
          style="background:{_LIGHT};border:1px solid {_BORDER};border-radius:6px;">
  <tr><td style="font-family:Arial,sans-serif;">
    <div style="font-size:18px;font-weight:700;color:{sc};">
      {snap.health_stars} {snap.health_label}</div>
    <div style="font-size:13px;color:#444;margin-top:6px;">{snap.health_narrative}</div>
    <div style="margin-top:10px;font-size:12px;color:{_MUTED};">
      <b>{active_count}</b> active · <b>{near_count}</b> near entry ·
      <b>{re_count}</b> re-accumulation · <b>{snap.total_events}</b> total events
    </div>
  </td></tr>
</table>"""
    )


def _near_constitutional(snap: PresentationSnapshot) -> str:
    items = _near(snap)
    if not items:
        return (
            _section_title("🎯 Near Constitutional Entry") +
            f'<div style="font-family:Arial,sans-serif;font-size:13px;color:{_MUTED};">'
            'No tickers at entry zone today.</div>'
        )
    rows = ""
    for r in items:
        dist   = r.get("distance_to_constitutional", 0)
        r2     = r.get("r2_score", 0)
        score  = r.get("final_score", 0)
        ep     = r.get("entry_price") or 0
        cp     = r.get("current_price") or 0
        move   = r.get("need_move_pct", 0)
        rows += f"""
<tr style="border-bottom:1px solid #e8f0f8;">
  <td style="padding:9px 12px;font-family:Arial,sans-serif;font-size:13px;
    font-weight:700;color:{_NAVY};">{r['ticker']}</td>
  <td style="padding:9px 12px;font-family:Arial,sans-serif;font-size:12px;
    color:{_MUTED};">{r.get('sector','')}</td>
  <td style="padding:9px 12px;font-family:Arial,sans-serif;font-size:12px;">
    R2 {r2:.1f} · Score {score:.1f}</td>
  <td style="padding:9px 12px;font-family:Arial,sans-serif;font-size:12px;">
    {cp:.2f} / {ep:.2f} EGP</td>
  <td style="padding:9px 12px;font-family:Arial,sans-serif;font-size:12px;
    color:{_AMBER};font-weight:600;">{dist:.1f} pts to gate</td>
</tr>"""

    return (
        _section_title(f"🎯 Near Constitutional Entry ({len(items)})") +
        f"""<table width="100%" cellpadding="0" cellspacing="0" border="0"
          style="border:1px solid #c8daf5;border-collapse:collapse;">
  <tr style="background:{_NAVY};">
    <th align="left" style="padding:8px 12px;font-family:Arial,sans-serif;
      font-size:11px;color:{_WHITE};">Ticker</th>
    <th align="left" style="padding:8px 12px;font-family:Arial,sans-serif;
      font-size:11px;color:{_WHITE};">Sector</th>
    <th align="left" style="padding:8px 12px;font-family:Arial,sans-serif;
      font-size:11px;color:{_WHITE};">R2 / Score</th>
    <th align="left" style="padding:8px 12px;font-family:Arial,sans-serif;
      font-size:11px;color:{_WHITE};">Price / Entry</th>
    <th align="left" style="padding:8px 12px;font-family:Arial,sans-serif;
      font-size:11px;color:{_WHITE};">Distance</th>
  </tr>
  {rows}
</table>"""
    )


def _active_positions(snap: PresentationSnapshot) -> str:
    items = _active(snap)
    if not items:
        return (
            _section_title("⭐ Active Constitutional Positions") +
            f'<div style="font-family:Arial,sans-serif;font-size:13px;color:{_MUTED};">'
            'No active positions.</div>'
        )
    rows = ""
    for u in items:
        ret   = u.get("return_pct") or 0.0
        rc    = _ret_color(ret)
        sign  = "+" if ret > 0 else ""
        ep    = u.get("entry_zone") or 0
        cp    = u.get("current_price") or 0
        label = "PREMIUM 🏆" if u["status"] == "PREMIUM" else (
                "UNDER REVIEW ⚠" if u["status"] == "UNDER_REVIEW" else "ACTIVE ✓")
        rows += f"""
<tr style="border-bottom:1px solid #e8f0f8;">
  <td style="padding:9px 12px;font-family:Arial,sans-serif;font-size:13px;
    font-weight:700;color:{_NAVY};">{u['ticker']}</td>
  <td style="padding:9px 12px;font-family:Arial,sans-serif;font-size:12px;
    color:{_MUTED};">{label}</td>
  <td style="padding:9px 12px;font-family:Arial,sans-serif;font-size:12px;">
    {ep:.2f} EGP</td>
  <td style="padding:9px 12px;font-family:Arial,sans-serif;font-size:12px;">
    {cp:.2f} EGP</td>
  <td style="padding:9px 12px;font-family:Arial,sans-serif;font-size:13px;
    font-weight:700;color:{rc};">{sign}{ret:.1f}%</td>
</tr>"""

    return (
        _section_title(f"⭐ Active Constitutional Positions ({len(items)})") +
        f"""<table width="100%" cellpadding="0" cellspacing="0" border="0"
          style="border:1px solid #c8daf5;border-collapse:collapse;">
  <tr style="background:{_NAVY};">
    <th align="left" style="padding:8px 12px;font-family:Arial,sans-serif;
      font-size:11px;color:{_WHITE};">Ticker</th>
    <th align="left" style="padding:8px 12px;font-family:Arial,sans-serif;
      font-size:11px;color:{_WHITE};">Status</th>
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


def _re_accumulation(snap: PresentationSnapshot) -> str:
    items = _re_acc(snap)
    if not items:
        return ""
    near_t   = {e["ticker"] for e in snap.approaching_entries}
    active_t = {u["ticker"] for u in snap.universe_snapshot
                if u["status"] in ("ACTIVE", "PREMIUM", "UNDER_REVIEW")}
    # Only show re-accumulation candidates that are near entry OR active
    candidates = [e for e in items if e["ticker"] in near_t or e["ticker"] in active_t]
    if not candidates:
        return ""
    tickers_html = " &nbsp;·&nbsp; ".join(
        f'<b style="color:{_NAVY};">{e["ticker"]}</b>'
        + (f'&nbsp;<span style="color:{_MUTED};font-size:11px;">'
           f'+{e["return_pct"]:.1f}%</span>' if e.get("return_pct") else "")
        for e in candidates
    )
    return (
        _section_title(f"🔄 Re-Accumulation Candidates ({len(candidates)})") +
        f"""<table width="100%" cellpadding="10" cellspacing="0" border="0"
          style="background:#f0fff4;border:1px solid #b7e4c7;border-radius:4px;">
  <tr><td style="font-family:Arial,sans-serif;font-size:13px;color:{_TEXT};">
    {tickers_html}</td></tr>
</table>"""
    )


def _future_watchlist(snap: PresentationSnapshot) -> str:
    items = _future(snap)
    near_t = {e["ticker"] for e in snap.approaching_entries}
    # Split: APPROACHING without candidate_pool entry still go to future
    if not items:
        return ""

    approaching = [u for u in items if u["status"] == "APPROACHING"]
    watching    = [u for u in items if u["status"] == "BELOW_THRESHOLD"][:8]
    no_hist     = [u for u in items if u["status"] in ("NO_HISTORY",)][:5]

    rows = ""
    for u in approaching + watching:
        r2    = u.get("r2_score") or 0
        score = u.get("final_score") or 0
        cp    = u.get("current_price") or 0
        ez    = u.get("entry_zone")
        ez_s  = f"{ez:.2f}" if ez else "Awaiting Entry Zone"
        reason = (u.get("reason") or "")[:80]
        rows += f"""
<tr style="border-bottom:1px solid #eef3f8;">
  <td style="padding:7px 10px;font-family:Arial,sans-serif;font-size:12px;
    font-weight:700;color:{_NAVY};">{u['ticker']}</td>
  <td style="padding:7px 10px;font-family:Arial,sans-serif;font-size:11px;
    color:{_MUTED};">{u.get('status','')}</td>
  <td style="padding:7px 10px;font-family:Arial,sans-serif;font-size:11px;">
    R2 {r2:.1f}</td>
  <td style="padding:7px 10px;font-family:Arial,sans-serif;font-size:11px;">
    {cp:.2f} / {ez_s}</td>
  <td style="padding:7px 10px;font-family:Arial,sans-serif;font-size:11px;
    color:{_MUTED};">{reason}</td>
</tr>"""

    if not rows:
        return ""

    watchlist_tickers = " · ".join(f"<b>{u['ticker']}</b>" for u in approaching + watching)

    return (
        _section_title(f"🔍 Future Opportunities / Watch List ({len(approaching + watching)})") +
        f"""<table width="100%" cellpadding="0" cellspacing="0" border="0"
          style="border:1px solid #d0e4f7;border-collapse:collapse;">
  <tr style="background:#0B5394;">
    <th align="left" style="padding:7px 10px;font-family:Arial,sans-serif;
      font-size:11px;color:{_WHITE};">Ticker</th>
    <th align="left" style="padding:7px 10px;font-family:Arial,sans-serif;
      font-size:11px;color:{_WHITE};">Status</th>
    <th align="left" style="padding:7px 10px;font-family:Arial,sans-serif;
      font-size:11px;color:{_WHITE};">R2</th>
    <th align="left" style="padding:7px 10px;font-family:Arial,sans-serif;
      font-size:11px;color:{_WHITE};">Price / Entry Zone</th>
    <th align="left" style="padding:7px 10px;font-family:Arial,sans-serif;
      font-size:11px;color:{_WHITE};">Waiting For</th>
  </tr>
  {rows}
</table>"""
    )


def _timeline_summary(snap: PresentationSnapshot) -> str:
    if not snap.total_events:
        return ""
    new_today = snap.new_events_today
    new_html  = ""
    if new_today:
        items = " &nbsp;·&nbsp; ".join(
            f'<b>{e["ticker"]}</b> ({e["event_type"].replace("_", " ")})'
            for e in new_today[:5]
        )
        new_html = f'<div style="margin-top:6px;font-size:12px;color:{_GREEN};">New today: {items}</div>'
    an = snap.analytics or {}
    best = max(an.items(), key=lambda x: x[1].get("best_return_pct", 0), default=None)
    best_html = ""
    if best:
        best_html = (
            f'<span style="color:{_MUTED};">Best: <b>{best[0]}</b> '
            f'+{best[1].get("best_return_pct", 0):.1f}%</span>'
        )
    return (
        _section_title(f"📈 Constitutional Timeline ({snap.total_events} events, {snap.total_tickers} tickers)") +
        f"""<table width="100%" cellpadding="10" cellspacing="0" border="0"
          style="background:{_LIGHT};border:1px solid {_BORDER};border-radius:4px;">
  <tr><td style="font-family:Arial,sans-serif;font-size:13px;color:{_TEXT};">
    {best_html}
    {new_html}
  </td></tr>
</table>"""
    )


def _statistics(snap: PresentationSnapshot) -> str:
    near_count   = len(_near(snap))
    active_count = len(_active(snap))
    re_count     = len(_re_acc(snap))
    fut_count    = len(_future(snap))
    return (
        _section_title("📊 Universe Statistics") +
        f"""<table width="100%" cellpadding="8" cellspacing="0" border="0"
          style="background:{_LIGHT};border:1px solid {_BORDER};border-radius:4px;">
  <tr>
    <td style="font-family:Arial,sans-serif;font-size:12px;color:{_MUTED};width:50%;">
      Universe size</td>
    <td style="font-family:Arial,sans-serif;font-size:12px;font-weight:700;">
      {snap.universe_size}</td>
  </tr>
  <tr>
    <td style="font-family:Arial,sans-serif;font-size:12px;color:{_MUTED};">
      Near constitutional entry</td>
    <td style="font-family:Arial,sans-serif;font-size:12px;font-weight:700;
      color:{_AMBER};">{near_count}</td>
  </tr>
  <tr>
    <td style="font-family:Arial,sans-serif;font-size:12px;color:{_MUTED};">
      Active positions</td>
    <td style="font-family:Arial,sans-serif;font-size:12px;font-weight:700;
      color:{_GREEN};">{active_count}</td>
  </tr>
  <tr>
    <td style="font-family:Arial,sans-serif;font-size:12px;color:{_MUTED};">
      Re-accumulation candidates</td>
    <td style="font-family:Arial,sans-serif;font-size:12px;font-weight:700;">
      {re_count}</td>
  </tr>
  <tr>
    <td style="font-family:Arial,sans-serif;font-size:12px;color:{_MUTED};">
      Future watch candidates</td>
    <td style="font-family:Arial,sans-serif;font-size:12px;font-weight:700;">
      {fut_count}</td>
  </tr>
  <tr>
    <td style="font-family:Arial,sans-serif;font-size:12px;color:{_MUTED};">
      Total timeline events</td>
    <td style="font-family:Arial,sans-serif;font-size:12px;font-weight:700;">
      {snap.total_events}</td>
  </tr>
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
        _section_title(f"🔬 Research Insights ({snap.knowledge_count} verified findings)") +
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


# ── Count/set consistency assertion ───────────────────────────────────────────

def assert_presentation_consistency(snap: PresentationSnapshot) -> None:
    """Raise ValueError if computed section counts are inconsistent."""
    near_t   = {e["ticker"] for e in snap.approaching_entries}
    active_t = {u["ticker"] for u in snap.universe_snapshot
                if u["status"] in ("ACTIVE", "PREMIUM", "UNDER_REVIEW")}
    overlap = near_t & active_t
    # Near ∩ Active is allowed (re-accumulation) — assert no ticker in future AND near
    future_t = {u["ticker"] for u in snap.universe_snapshot
                if u["ticker"] not in near_t and u["ticker"] not in active_t}
    if near_t & future_t:
        raise ValueError(
            f"Near ∩ Future not empty: {near_t & future_t}"
        )
    if active_t & future_t:
        raise ValueError(
            f"Active ∩ Future not empty: {active_t & future_t}"
        )


# ── Public API ────────────────────────────────────────────────────────────────

def build_email(snap: PresentationSnapshot | None = None) -> str:
    """Return full HTML email string."""
    if snap is None:
        snap = build_presentation_snapshot()

    assert_presentation_consistency(snap)

    date_str = datetime.now(_CAIRO_TZ).strftime("%A, %d %B %Y  ·  %H:%M Cairo")

    parts = [
        _hdr(date_str),
        _exec_summary(snap),
        _near_constitutional(snap),
        _active_positions(snap),
        _re_accumulation(snap),
        _future_watchlist(snap),
        _timeline_summary(snap),
        _statistics(snap),
        _research(snap),
        _footer(),
    ]

    inner = "\n".join(p for p in parts if p)
    return (
        '<!DOCTYPE html><html><body style="margin:0;padding:20px;background:#eef2f7;">'
        '<table width="680" cellpadding="0" cellspacing="0" border="0" align="center"'
        ' style="background:#ffffff;border:1px solid #d0d7e2;">'
        f'<tr><td style="padding:0 24px 24px 24px;">{inner}</td></tr>'
        '</table></body></html>'
    )
