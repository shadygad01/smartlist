"""
EGX Constitutional Opportunity Intelligence Platform — Email V4
8-section order: exec summary → new events → re-accum → leaders →
timeline → approaching → research → system diagnostics.
No portfolio capacity. No HELD/WATCH/RESERVE.
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
_CYAN  = "#0a5f6e"
_LIGHT = "#f8f9fb"
_BORD  = "#d0d7e2"
_MUTED = "#666666"
_TEXT  = "#333333"
_WHITE = "#ffffff"


def _ret_c(r: float) -> str:
    return _GREEN if r > 0 else (_RED if r < 0 else _MUTED)

def _sign(r: float) -> str:
    return "+" if r >= 0 else ""

def _status_c(s: str) -> str:
    return _GREEN if s == "PREMIUM_NOW" else (_AMBER if s == "ACTIVE_OPPORTUNITY" else _RED)

def _status_lbl(s: str) -> str:
    return s.replace("_", " ")

def _type_c(t: str) -> str:
    return _BLUE if t == "FIRST_BUY" else _PURPL

def _confidence_c(conf: str) -> str:
    return {"ELITE": _GREEN, "STRONG": _CYAN, "CONFIRMED": _AMBER, "DEVELOPING": _MUTED}.get(conf, _MUTED)

def _section_title(title: str) -> str:
    return (
        f'<div style="font-family:Arial,sans-serif;font-size:13px;font-weight:700;'
        f'color:{_NAVY};margin:24px 0 8px 0;letter-spacing:0.4px;'
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


# ── Section 1: Header ─────────────────────────────────────────────────────────

def _hdr(snap: PresentationSnapshot, date_str: str) -> str:
    mstatus = snap.market_status
    mcolor  = "#4caf50" if "OPEN" in mstatus and "PRE" not in mstatus else "#f0b840"
    return f"""
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{_NAVY};">
  <tr><td style="padding:24px 28px;">
    <div style="font-family:Arial,sans-serif;color:#8fb8d8;font-size:10px;
         letter-spacing:1px;text-transform:uppercase;margin-bottom:6px;">
      EGX Constitutional Opportunity Intelligence Platform</div>
    <div style="font-family:Arial,sans-serif;color:{_WHITE};font-size:22px;font-weight:700;">
      Constitutional Opportunity Timeline</div>
    <div style="font-family:Arial,sans-serif;color:#8fb8d8;font-size:12px;margin-top:8px;
         display:flex;gap:16px;flex-wrap:wrap;">
      <span>{date_str}</span>
      <span style="color:{mcolor};font-weight:700;">⬤ EGX {mstatus}</span>
      {'<span style="color:#4caf50;font-weight:700;">⚡ ' + str(len(snap.new_events_today)) + ' NEW TODAY</span>' if snap.new_events_today else ''}
    </div>
  </td></tr>
</table>"""


# ── Section 2: Executive Summary ─────────────────────────────────────────────

def _exec_summary(snap: PresentationSnapshot) -> str:
    premium = sum(1 for e in snap.timeline if e.get("status") == "PREMIUM_NOW")
    active  = sum(1 for e in snap.timeline if e.get("status") == "ACTIVE_OPPORTUNITY")
    review  = sum(1 for e in snap.timeline if e.get("status") == "UNDER_REVIEW")
    tl = snap.timeline
    rets = [e["return_pct"] for e in tl] if tl else []
    avg_ret  = sum(rets) / len(rets) if rets else 0.0
    wins     = sum(1 for r in rets if r > 0)
    win_rate = wins / len(rets) * 100 if rets else 0.0
    best_e   = max(tl, key=lambda e: e["return_pct"]) if tl else None
    most_rep = snap.leaderboards.get("most_repeated", [{}])[0] if snap.leaderboards else {}

    best_str = ""
    if best_e:
        best_str = (
            f'&nbsp;·&nbsp; Best: <b style="color:{_GREEN};">{best_e["ticker"]}'
            f' {_sign(best_e["return_pct"])}{best_e["return_pct"]:.1f}%</b>'
        )
    most_rep_str = ""
    if most_rep:
        most_rep_str = (
            f'&nbsp;·&nbsp; Most Repeated: <b style="color:#5b21b6;">{most_rep.get("ticker","—")}'
            f' ({most_rep.get("total_events",0)} events)</b>'
        )

    return (
        _section_title("📊 Executive Summary") +
        f"""<table width="100%" cellpadding="14" cellspacing="0" border="0"
          style="background:{_LIGHT};border:1px solid {_BORD};border-radius:6px;">
  <tr><td style="font-family:Arial,sans-serif;">
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:12px;">
      {''.join([
          f'<div style="background:#ffffff;border:1px solid {_BORD};border-radius:6px;padding:10px;text-align:center;">'
          f'<div style="font-size:20px;font-weight:700;color:{col};">{val}</div>'
          f'<div style="font-size:10px;color:{_MUTED};text-transform:uppercase;margin-top:3px;">{lbl}</div></div>'
          for val, lbl, col in [
              (snap.universe_size, "Universe", _NAVY),
              (snap.total_events, "Total Events", _BLUE),
              (len(snap.first_buys), "First BUYs", _BLUE),
              (len(snap.re_accumulations), "Re-Accum", _PURPL),
          ]
      ])}
    </div>
    <div style="font-size:12px;color:{_MUTED};">
      <b style="color:{_GREEN};">🏆 Premium: {premium}</b> &nbsp;·&nbsp;
      Active: {active} &nbsp;·&nbsp; Review: {review}
      &nbsp;·&nbsp; Avg Return: <b style="color:{_ret_c(avg_ret)};">{avg_ret:+.1f}%</b>
      &nbsp;·&nbsp; Win Rate: <b>{win_rate:.0f}%</b>
      {best_str}{most_rep_str}
    </div>
    {'<div style="margin-top:8px;font-size:12px;color:#856404;font-weight:700;">🔍 ' + str(len(snap.approaching_entries)) + ' tickers approaching constitutional entry</div>' if snap.approaching_entries else ''}
  </td></tr>
</table>"""
    )


# ── Section 3: New Events Today ───────────────────────────────────────────────

def _new_events_section(snap: PresentationSnapshot) -> str:
    new_first = [e for e in snap.new_events_today if e["event_type"] == "FIRST_BUY"]
    new_reac  = [e for e in snap.new_events_today if e["event_type"] == "RE_ACCUMULATION"]
    if not snap.new_events_today:
        return ""

    rows = ""
    for e in snap.new_events_today:
        tc    = _type_c(e["event_type"])
        label = "🟢 FIRST BUY" if e["event_type"] == "FIRST_BUY" else "🔵 RE-ACCUMULATION"
        rows += (
            f'<tr style="border-bottom:1px solid #e8f0f8;">'
            f'<td style="padding:8px 10px;font-family:Arial,sans-serif;font-size:11px;font-weight:700;color:{tc};">{label}</td>'
            f'<td style="padding:8px 10px;font-family:Arial,sans-serif;font-size:13px;font-weight:700;color:{_NAVY};">{e["ticker"]}</td>'
            f'<td style="padding:8px 10px;font-family:Arial,sans-serif;font-size:12px;color:{_MUTED};">{e["sector"]}</td>'
            f'<td style="padding:8px 10px;font-family:Arial,sans-serif;font-size:12px;font-weight:700;">R2={e["buy_r2"]:.1f}</td>'
            f'<td style="padding:8px 10px;font-family:Arial,sans-serif;font-size:12px;">Score={e["buy_score"]:.1f}</td>'
            f'<td style="padding:8px 10px;font-family:Arial,sans-serif;font-size:12px;font-weight:700;color:{_NAVY};">{e["entry_price"]:.2f} EGP</td>'
            f'</tr>'
        )
    note = (
        f'({len(new_first)} First BUY · {len(new_reac)} Re-Accumulation)'
        if new_first and new_reac else ""
    )
    return (
        _section_title(f"⚡ New Constitutional Events Today ({len(snap.new_events_today)}) {note}") +
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0"'
        f' style="border:1px solid #c8f0c8;border-collapse:collapse;background:#f0fff0;">'
        f'{_th("Type","Ticker","Sector","R2","Score","Entry Zone")}{rows}</table>'
    )


# ── Section 4: Constitutional Leaders ────────────────────────────────────────

def _leaders_section(snap: PresentationSnapshot) -> str:
    if not snap.constitutional_leaders:
        return ""
    rows = ""
    for i, ldr in enumerate(snap.constitutional_leaders, 1):
        conf_c = _confidence_c(ldr["confidence"])
        rows += (
            f'<tr style="border-bottom:1px solid #e8f0f8;">'
            f'<td style="padding:6px 10px;font-family:Arial,sans-serif;font-size:11px;color:{_MUTED};">{i}</td>'
            f'<td style="padding:6px 10px;font-family:Arial,sans-serif;font-size:13px;font-weight:700;color:{_NAVY};">{ldr["ticker"]}</td>'
            f'<td style="padding:6px 10px;font-family:Arial,sans-serif;font-size:12px;color:{_MUTED};">{ldr["sector"]}</td>'
            f'<td style="padding:6px 10px;font-family:Arial,sans-serif;font-size:12px;font-weight:700;color:{_PURPL};">{ldr["total_events"]}</td>'
            f'<td style="padding:6px 10px;font-family:Arial,sans-serif;font-size:12px;font-weight:700;color:{_ret_c(ldr["avg_return_pct"])};">{_sign(ldr["avg_return_pct"])}{ldr["avg_return_pct"]:.1f}%</td>'
            f'<td style="padding:6px 10px;font-family:Arial,sans-serif;font-size:12px;color:#333;">{ldr["current_price"]:.2f}</td>'
            f'<td style="padding:6px 10px;font-family:Arial,sans-serif;font-size:12px;font-weight:700;color:{_ret_c(ldr["current_ret"])};">{_sign(ldr["current_ret"])}{ldr["current_ret"]:.1f}%</td>'
            f'<td style="padding:6px 10px;font-family:Arial,sans-serif;font-size:12px;color:{_GREEN};">{_sign(ldr["peak_ret"])}{ldr["peak_ret"]:.1f}%</td>'
            f'<td style="padding:6px 10px;font-family:Arial,sans-serif;font-size:12px;">{ldr["win_rate"]*100:.0f}%</td>'
            f'<td style="padding:6px 10px;font-family:Arial,sans-serif;font-size:11px;font-weight:700;color:{conf_c};">{ldr["confidence"]}</td>'
            f'</tr>'
        )
    return (
        _section_title("🏆 Constitutional Leaders — Track Record by Ticker") +
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0"'
        f' style="border:1px solid #c8daf5;border-collapse:collapse;">'
        f'{_th("#","Ticker","Sector","Events","Avg Return","Current","Latest Ret","Peak Ret","Win Rate","Confidence")}'
        f'{rows}</table>'
    )


# ── Section 5: Full Timeline ──────────────────────────────────────────────────

def _full_timeline(snap: PresentationSnapshot) -> str:
    if not snap.timeline:
        return (
            _section_title("📋 Constitutional Opportunity Timeline") +
            f'<div style="font-family:Arial,sans-serif;font-size:13px;color:{_MUTED};">No events recorded.</div>'
        )
    rows = ""
    for e in snap.timeline:
        rc    = _ret_c(e["return_pct"])
        sc    = _status_c(e["status"])
        tc    = _type_c(e["event_type"])
        label = "🟢 FIRST" if e["event_type"] == "FIRST_BUY" else "🔵 RE"
        rows += (
            f'<tr style="border-bottom:1px solid #e8f0f8;">'
            f'<td style="padding:5px 8px;font-family:Arial,sans-serif;font-size:11px;font-weight:700;color:{tc};">{label}</td>'
            f'<td style="padding:5px 8px;font-family:Arial,sans-serif;font-size:13px;font-weight:700;color:{_NAVY};">{e["ticker"]}</td>'
            f'<td style="padding:5px 8px;font-family:Arial,sans-serif;font-size:11px;color:{_MUTED};">{e["event_date"]}</td>'
            f'<td style="padding:5px 8px;font-family:Arial,sans-serif;font-size:11px;color:{_MUTED};">{e["sector"]}</td>'
            f'<td style="padding:5px 8px;font-family:Arial,sans-serif;font-size:12px;">{e["entry_price"]:.2f}</td>'
            f'<td style="padding:5px 8px;font-family:Arial,sans-serif;font-size:12px;">{e["current_price"]:.2f}</td>'
            f'<td style="padding:5px 8px;font-family:Arial,sans-serif;font-size:12px;font-weight:700;color:{rc};">{_sign(e["return_pct"])}{e["return_pct"]:.1f}%</td>'
            f'<td style="padding:5px 8px;font-family:Arial,sans-serif;font-size:12px;color:{_GREEN};">{_sign(e["peak_return_pct"])}{e["peak_return_pct"]:.1f}%</td>'
            f'<td style="padding:5px 8px;font-family:Arial,sans-serif;font-size:11px;color:{_MUTED};">{e["days_active"]}d</td>'
            f'<td style="padding:5px 8px;font-family:Arial,sans-serif;font-size:11px;font-weight:700;color:{sc};">{_status_lbl(e["status"])}</td>'
            f'</tr>'
        )
    return (
        _section_title(f"📋 Constitutional Opportunity Timeline — {snap.total_events} Events (Immutable · Append-Only)") +
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0"'
        f' style="border:1px solid #c8daf5;border-collapse:collapse;">'
        f'{_th("Type","Ticker","Signal Date","Sector","Entry","Current","Return","Peak","Days","Status")}'
        f'{rows}</table>'
    )


# ── Section 6: Approaching Constitutional Entry ───────────────────────────────

def _approaching_section(snap: PresentationSnapshot) -> str:
    if not snap.approaching_entries:
        return ""
    rows = ""
    for e in snap.approaching_entries:
        dist = e["distance_to_constitutional"]
        urg_c = _GREEN if dist <= 0.3 else (_AMBER if dist <= 1.0 else _MUTED)
        has_history = any(l["ticker"] == e["ticker"] for l in snap.constitutional_leaders)
        note = "Has constitutional history" if has_history else ""
        rows += (
            f'<tr style="border-bottom:1px solid #e8f0f8;">'
            f'<td style="padding:6px 10px;font-family:Arial,sans-serif;font-size:13px;font-weight:700;color:{_NAVY};">{e["ticker"]}</td>'
            f'<td style="padding:6px 10px;font-family:Arial,sans-serif;font-size:12px;color:{_MUTED};">{e["sector"]}</td>'
            f'<td style="padding:6px 10px;font-family:Arial,sans-serif;font-size:12px;font-weight:700;">R2={e["r2_score"]:.1f}</td>'
            f'<td style="padding:6px 10px;font-family:Arial,sans-serif;font-size:12px;">Score={e["final_score"]:.1f}</td>'
            f'<td style="padding:6px 10px;font-family:Arial,sans-serif;font-size:12px;font-weight:700;color:{urg_c};">–{dist:.1f} pts</td>'
            f'<td style="padding:6px 10px;font-family:Arial,sans-serif;font-size:12px;">{e["entry_price"]:.2f} EGP</td>'
            f'<td style="padding:6px 10px;font-family:Arial,sans-serif;font-size:11px;color:{_PURPL};">{note}</td>'
            f'</tr>'
        )
    return (
        _section_title(f"🔍 Approaching Constitutional Entry ({len(snap.approaching_entries)} tickers — R2 50–59.9 · Score ≥ 35)") +
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0"'
        f' style="border:1px solid #e8d5a0;border-collapse:collapse;background:#fffcf0;">'
        f'{_th("Ticker","Sector","Current R2","Score","Distance to Entry","Entry Zone","Note")}'
        f'{rows}</table>'
    )


# ── Section 7: Research ───────────────────────────────────────────────────────

def _research(snap: PresentationSnapshot) -> str:
    if not snap.research_insights:
        return ""
    rows = ""
    for ins in snap.research_insights[:3]:
        cc = _GREEN if ins["confidence"] == "HIGH" else (_AMBER if ins["confidence"] == "MEDIUM" else _MUTED)
        rows += (
            f'<tr style="border-bottom:1px solid #e8f0f8;">'
            f'<td style="padding:7px 10px;font-family:Arial,sans-serif;font-size:12px;color:#444;">{ins["question"]}</td>'
            f'<td style="padding:7px 10px;font-family:Arial,sans-serif;font-size:12px;color:#222;">{ins["conclusion"]}</td>'
            f'<td style="padding:7px 10px;font-family:Arial,sans-serif;font-size:11px;font-weight:700;color:{cc};">{ins["confidence"]}</td>'
            f'</tr>'
        )
    return (
        _section_title(f"🔬 Research Insights ({snap.knowledge_count} verified findings)") +
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0"'
        f' style="border:1px solid #c8daf5;border-collapse:collapse;">'
        f'{_th("Question","Conclusion","Confidence")}{rows}</table>'
    )


# ── Section 8: System Diagnostics (LAST) ─────────────────────────────────────

def _system_diagnostics(snap: PresentationSnapshot) -> str:
    sc  = _GREEN if snap.health_stars.count("★") >= 4 else (_AMBER if snap.health_stars.count("★") == 3 else _RED)
    tl_ok  = len(snap.timeline) > 0
    scan_s = snap.last_scan_ts[:19].replace("T", " ") if snap.last_scan_ts else "—"
    gen_s  = snap.generated_at[:19].replace("T", " ") if snap.generated_at else "—"

    checks = [
        ("Timeline DB",         f'{snap.total_events} events · {snap.total_tickers} tickers',  tl_ok),
        ("Universe",            f'{snap.universe_size} tickers in candidate_pool',              snap.universe_size > 0),
        ("First BUY Events",    str(len(snap.first_buys)),                                     True),
        ("Re-Accumulations",    str(len(snap.re_accumulations)),                               True),
        ("Approaching Entry",   str(len(snap.approaching_entries)),                            True),
        ("Knowledge Base",      f'{snap.knowledge_count} verified findings',                   True),
        ("Last Scan",           scan_s,                                                        True),
        ("Generated At",        gen_s,                                                         True),
        ("Market Status",       snap.market_status,                                            True),
    ]

    rows = ""
    for label, val, ok in checks:
        c = _GREEN if ok else _RED
        rows += (
            f'<tr style="border-bottom:1px solid #e8f0f8;">'
            f'<td style="padding:6px 10px;font-family:Arial,sans-serif;font-size:12px;color:{_MUTED};">{label}</td>'
            f'<td style="padding:6px 10px;font-family:Arial,sans-serif;font-size:12px;font-weight:600;color:{c};">{val}</td>'
            f'</tr>'
        )

    return (
        _section_title("🔧 System Diagnostics") +
        f'<table width="50%" cellpadding="0" cellspacing="0" border="0"'
        f' style="border:1px solid {_BORD};border-collapse:collapse;margin-bottom:12px;">'
        f'{rows}</table>'
        f'<div style="font-family:Arial,sans-serif;font-size:12px;color:{_MUTED};'
        f'background:{_LIGHT};border:1px solid {_BORD};border-radius:6px;padding:12px;">'
        f'<b style="color:{sc};">{snap.health_stars} {snap.health_label}</b> &nbsp;·&nbsp; '
        f'<span style="font-size:11px;">{snap.health_narrative}</span><br>'
        f'<span style="font-size:10px;color:{_MUTED};">Portfolio advisor health — informational only. '
        f'Constitutional BUY status does not depend on health stars.</span>'
        f'</div>'
    )


# ── Footer ────────────────────────────────────────────────────────────────────

def _footer() -> str:
    return f"""
<table width="100%" cellpadding="0" cellspacing="0" border="0"
  style="margin-top:40px;border-top:1px solid #e8eaed;">
  <tr><td align="center" style="padding:16px;font-family:Arial,sans-serif;
    font-size:11px;color:#bbb;letter-spacing:0.4px;">
    EGX Constitutional Opportunity Intelligence Platform &nbsp;·&nbsp;
    Append-Only &nbsp;·&nbsp; Immutable Events &nbsp;·&nbsp; No Portfolio Dependency
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
        _leaders_section(snap),
        _full_timeline(snap),
        _approaching_section(snap),
        _research(snap),
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
    print(f"[Email V4] Saved → email.html ({len(html)//1024} KB)")
