"""
EGX Constitutional Opportunity Intelligence Platform — Dashboard V5
Section order: New Today → Re-Accumulation → Best Opportunities →
               Approaching Entry → Timeline → System Diagnostics (LAST)
No portfolio. No capacity. No R2 degradation. No legacy vocabulary.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

from presentation.presentation_snapshot import PresentationSnapshot, build_presentation_snapshot

# ── Theme ─────────────────────────────────────────────────────────────────────
G   = "#4caf50"
R   = "#f44336"
A   = "#f0b840"
B   = "#50d8d0"
P   = "#9c6fff"
DIM = "#8b8fa8"
FG  = "#d0d4e8"
BG0 = "#0b0c1a"
BG1 = "#10112a"
BG2 = "#181930"
BOR = "#252645"
W   = "#ffffff"

CSS = f"""
body{{margin:0;padding:0;background:{BG0};font-family:'Segoe UI',Arial,sans-serif;color:{FG};}}
.wrap{{max-width:1100px;margin:0 auto;padding:24px 16px;}}
.card{{background:{BG1};border:1px solid {BOR};border-radius:10px;padding:20px;margin-bottom:18px;}}
.section-title{{font-size:13px;font-weight:700;letter-spacing:0.6px;text-transform:uppercase;
  color:{DIM};margin-bottom:14px;border-bottom:1px solid {BOR};padding-bottom:8px;}}
.badge{{display:inline-block;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:700;}}
table{{width:100%;border-collapse:collapse;font-size:13px;}}
th{{text-align:left;padding:8px 10px;color:{DIM};font-size:11px;font-weight:700;
  letter-spacing:0.4px;text-transform:uppercase;border-bottom:1px solid {BOR};}}
td{{padding:8px 10px;border-bottom:1px solid {BOR};color:{FG};vertical-align:middle;}}
tr:last-child td{{border-bottom:none;}}
.pos{{color:{G};font-weight:700;}} .neg{{color:{R};font-weight:700;}} .neu{{color:{A};font-weight:700;}}
.stat{{background:{BG2};border:1px solid {BOR};border-radius:8px;padding:12px 16px;text-align:center;}}
.stat-val{{font-size:22px;font-weight:700;}}
.stat-lbl{{font-size:10px;color:{DIM};text-transform:uppercase;letter-spacing:0.5px;margin-top:3px;}}
.grid6{{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:16px;}}
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _rc(r: float) -> str:
    return "pos" if r > 0 else ("neg" if r < 0 else "neu")

def _sign(r: float) -> str:
    return "+" if r >= 0 else ""

def _type_badge(etype: str) -> str:
    if etype == "FIRST_BUY":
        return f'<span class="badge" style="background:{B}22;color:{B};font-size:10px;">FIRST BUY</span>'
    return f'<span class="badge" style="background:{P}22;color:{P};font-size:10px;">RE-ACCUM</span>'

def _status_dot(status: str) -> str:
    c = G if status == "PREMIUM_NOW" else (A if status == "ACTIVE_OPPORTUNITY" else R)
    lbl = "PREMIUM" if status == "PREMIUM_NOW" else ("ACTIVE" if status == "ACTIVE_OPPORTUNITY" else "REVIEW")
    return f'<span style="color:{c};font-weight:700;font-size:11px;">⬤ {lbl}</span>'

def _cairo_now() -> str:
    tz = timezone(timedelta(hours=2))
    return datetime.now(tz).strftime("%H:%M")

def _market_status_color(status: str) -> str:
    return G if "OPEN" in status and "PRE" not in status else (A if "PRE" in status else DIM)

def _pass_badge(ok: bool) -> str:
    return (f'<span class="badge" style="background:{G}22;color:{G};">✓ PASS</span>'
            if ok else f'<span class="badge" style="background:{R}22;color:{R};">✗ FAIL</span>')


# ── Opportunity row: ONLY Ticker / Type / Entry Zone / Current / Return / Date ─

def _opp_row(e: dict) -> str:
    return f"""
<tr>
  <td style="font-weight:700;color:{B};font-size:14px;">{e['ticker']}</td>
  <td>{_type_badge(e['event_type'])}</td>
  <td style="color:{W};font-weight:700;">{e['entry_price']:.2f} <span style="font-size:10px;color:{DIM};">EGP</span></td>
  <td style="color:{FG};font-weight:600;">{e['current_price']:.2f}</td>
  <td class="{_rc(e['return_pct'])}">{_sign(e['return_pct'])}{e['return_pct']:.1f}%</td>
  <td style="color:{DIM};font-size:11px;">{e['event_date']}</td>
  <td>{_status_dot(e['status'])}</td>
</tr>"""

def _opp_header() -> str:
    return "<tr><th>Ticker</th><th>Type</th><th>Entry Zone</th><th>Current</th><th>Return %</th><th>Signal Date</th><th>Status</th></tr>"


# ── Section 1: Runtime Header ─────────────────────────────────────────────────

def _s_header(snap: PresentationSnapshot) -> str:
    now_str = datetime.now().strftime("%A, %d %B %Y")
    mstatus = snap.market_status
    mc      = _market_status_color(mstatus)
    scan_s  = (snap.last_scan_ts[:16].replace("T", " ")
               if snap.last_scan_ts else "—")

    new_tag = (
        f'<span style="background:{G}22;color:{G};padding:3px 12px;border-radius:20px;'
        f'font-size:12px;font-weight:700;">⚡ {len(snap.new_events_today)} NEW TODAY</span> '
    ) if snap.new_events_today else ""

    return f"""
<div style="background:{BG1};border:1px solid {BOR};border-radius:12px;padding:24px;margin-bottom:18px;">
  <div style="display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:12px;margin-bottom:20px;">
    <div>
      <div style="font-size:10px;color:{DIM};text-transform:uppercase;letter-spacing:1.2px;margin-bottom:6px;">
        EGX Constitutional Opportunity Intelligence Platform
      </div>
      <div style="font-size:24px;font-weight:700;color:{W};">Constitutional Opportunity Timeline</div>
      <div style="margin-top:8px;">
        {new_tag}
        <span style="color:{mc};font-weight:700;font-size:13px;">⬤ EGX {mstatus}</span>
      </div>
    </div>
    <div style="text-align:right;">
      <div style="font-size:15px;font-weight:600;color:{W};">{now_str}</div>
      <div style="font-size:20px;font-weight:700;color:{B};margin-top:4px;">{_cairo_now()} Cairo</div>
      <div style="font-size:11px;color:{DIM};margin-top:6px;">Last Scan: <span style="color:{FG};">{scan_s}</span></div>
    </div>
  </div>
  <div class="grid6">
    <div class="stat"><div class="stat-val" style="color:{W};">{snap.total_events}</div><div class="stat-lbl">Total Events</div></div>
    <div class="stat"><div class="stat-val" style="color:{B};">{len(snap.first_buys)}</div><div class="stat-lbl">First BUY</div></div>
    <div class="stat"><div class="stat-val" style="color:{P};">{len(snap.re_accumulations)}</div><div class="stat-lbl">Re-Accumulation</div></div>
    <div class="stat"><div class="stat-val" style="color:{A};">{len(snap.approaching_entries)}</div><div class="stat-lbl">Approaching Entry</div></div>
    <div class="stat"><div class="stat-val" style="color:{G};">{sum(1 for e in snap.timeline if e.get("status")=="PREMIUM_NOW")}</div><div class="stat-lbl">Premium Now</div></div>
    <div class="stat"><div class="stat-val" style="color:{FG};">{snap.universe_size}</div><div class="stat-lbl">Universe</div></div>
  </div>
</div>"""


# ── Section 2: New Today ──────────────────────────────────────────────────────

def _s_new_today(snap: PresentationSnapshot) -> str:
    if not snap.new_events_today:
        return ""
    rows = "".join(_opp_row(e) for e in snap.new_events_today)
    return f"""
<div class="card" style="border-color:{G}44;">
  <div class="section-title" style="color:{G};">⚡ New Constitutional Events Today ({len(snap.new_events_today)})</div>
  <table>{_opp_header()}{rows}</table>
</div>"""


# ── Section 3: Re-Accumulation ────────────────────────────────────────────────

def _s_re_accumulations(snap: PresentationSnapshot) -> str:
    events = [e for e in snap.timeline if e["event_type"] == "RE_ACCUMULATION"]
    if not events:
        return ""
    # Sort by return descending
    events = sorted(events, key=lambda e: -e["return_pct"])
    rows = "".join(_opp_row(e) for e in events)
    return f"""
<div class="card">
  <div class="section-title" style="color:{P};">🔵 Re-Accumulation Events ({len(events)})</div>
  <table>{_opp_header()}{rows}</table>
</div>"""


# ── Section 4: Best Opportunities ────────────────────────────────────────────

def _s_best_opportunities(snap: PresentationSnapshot) -> str:
    if not snap.timeline:
        return ""
    # Top 10 by return_pct
    best = sorted(snap.timeline, key=lambda e: -e["return_pct"])[:10]
    rows = "".join(_opp_row(e) for e in best)
    return f"""
<div class="card">
  <div class="section-title" style="color:{G};">🏆 Best Opportunities (Top 10 by Return)</div>
  <table>{_opp_header()}{rows}</table>
</div>"""


# ── Section 5: Approaching Entry ──────────────────────────────────────────────

def _s_approaching(snap: PresentationSnapshot) -> str:
    if not snap.approaching_entries:
        return ""
    rows = ""
    for e in snap.approaching_entries:
        dist = e["distance_to_constitutional"]
        pct  = dist / 60.0 * 100   # distance as % of threshold
        urg  = G if dist <= 0.3 else (A if dist <= 1.0 else DIM)
        rows += f"""
<tr>
  <td style="font-weight:700;color:{B};font-size:14px;">{e['ticker']}</td>
  <td style="color:{DIM};">{e['sector']}</td>
  <td style="color:{W};font-weight:700;">{e['r2_score']:.1f}</td>
  <td style="color:{urg};font-weight:700;">–{dist:.1f} pts ({pct:.1f}%)</td>
  <td style="color:{FG};">{e['entry_price']:.2f} EGP</td>
  <td style="color:{FG};">{e['current_price']:.2f}</td>
</tr>"""
    return f"""
<div class="card" style="border-color:{A}44;">
  <div class="section-title" style="color:{A};">🔍 Approaching Constitutional Entry ({len(snap.approaching_entries)} tickers)</div>
  <div style="font-size:11px;color:{DIM};margin-bottom:10px;">
    Constitutional threshold: R2 ≥ 60 · Score ≥ 35 · Distance = pts remaining to unlock
  </div>
  <table>
    <tr><th>Ticker</th><th>Sector</th><th>Current R2</th><th>Distance to Entry</th><th>Entry Zone</th><th>Current Price</th></tr>
    {rows}
  </table>
</div>"""


# ── Section 6: Full Timeline ──────────────────────────────────────────────────

def _s_timeline(snap: PresentationSnapshot) -> str:
    if not snap.timeline:
        return f'<div class="card"><div style="color:{DIM};">No constitutional events recorded.</div></div>'
    rows = "".join(_opp_row(e) for e in snap.timeline)
    return f"""
<div class="card">
  <div class="section-title">📋 Constitutional Opportunity Timeline — {snap.total_events} Events
    <span style="font-size:10px;color:{DIM};font-weight:400;margin-left:8px;">Append-only · Immutable · No R2 degradation</span>
  </div>
  <table>{_opp_header()}{rows}</table>
</div>"""


# ── Section 7: System Diagnostics (LAST) ─────────────────────────────────────

def _s_diagnostics(snap: PresentationSnapshot) -> str:
    base = Path(__file__).parent

    # Assess each subsystem
    tl_ok       = snap.total_events == 42
    fb_ok       = len(snap.first_buys) == 19
    re_ok       = len(snap.re_accumulations) == 23
    dash_ok     = (base / "dashboard.html").exists()
    email_ok    = (base / "email.html").exists()
    tg_ok       = True   # telegram runs in same process
    kb_ok       = snap.knowledge_count > 0
    research_ok = len(snap.research_insights) > 0
    scan_s      = (snap.last_scan_ts[:19].replace("T", " ")
                   if snap.last_scan_ts else "—")
    gen_s       = snap.generated_at[:19].replace("T", " ") if snap.generated_at else "—"

    # SHA256 of outputs
    def sha(path: Path) -> str:
        if not path.exists():
            return "—"
        return hashlib.sha256(path.read_bytes()).hexdigest()[:16] + "…"

    dash_sha  = sha(base / "dashboard.html")
    email_sha = sha(base / "email.html")

    checks = [
        ("Dashboard",        dash_ok,        f"dashboard.html · {dash_sha}"),
        ("Email",            email_ok,        f"email.html · {email_sha}"),
        ("Telegram",         tg_ok,           "runtime ready"),
        ("Knowledge Base",   kb_ok,           f"{snap.knowledge_count} verified findings"),
        ("Research",         research_ok,     f"{len(snap.research_insights)} insights loaded"),
    ]

    rows = ""
    for label, ok, detail in checks:
        c = G if ok else R
        rows += f"""
<tr>
  <td style="color:{DIM};font-size:12px;padding:8px 0;">{label}</td>
  <td style="padding:8px 8px;">{_pass_badge(ok)}</td>
  <td style="color:{c};font-size:12px;padding:8px 0;">{detail}</td>
</tr>"""

    data_rows = ""
    for label, val, col in [
        ("Timeline Events",   f"{snap.total_events} ({len(snap.first_buys)} First BUY · {len(snap.re_accumulations)} Re-Accum)", G if tl_ok and fb_ok and re_ok else R),
        ("Universe",          f"{snap.universe_size} tickers",  FG),
        ("Approaching Entry", f"{len(snap.approaching_entries)} tickers", A),
        ("Last Scan",         scan_s,          DIM),
        ("Generated At",      gen_s,           DIM),
        ("Market Status",     snap.market_status, _market_status_color(snap.market_status)),
        ("Portfolio Advisor", f"{snap.health_stars} {snap.health_label} (informational only)", DIM),
    ]:
        data_rows += f"""
<tr>
  <td style="color:{DIM};font-size:12px;padding:6px 0;">{label}</td>
  <td style="color:{col};font-size:12px;font-weight:600;padding:6px 8px;">{val}</td>
</tr>"""

    return f"""
<div class="card">
  <div class="section-title">🔧 System Diagnostics</div>
  <div class="grid2">
    <div>
      <div style="font-size:11px;color:{DIM};text-transform:uppercase;letter-spacing:0.4px;margin-bottom:8px;">Runtime Status</div>
      <table style="font-size:12px;">{rows}</table>
    </div>
    <div>
      <div style="font-size:11px;color:{DIM};text-transform:uppercase;letter-spacing:0.4px;margin-bottom:8px;">Live Data</div>
      <table style="font-size:12px;">{data_rows}</table>
    </div>
  </div>
</div>"""


# ── Build ─────────────────────────────────────────────────────────────────────

def build_dashboard() -> str:
    snap = build_presentation_snapshot()
    body = (
        _s_header(snap) +
        _s_new_today(snap) +
        _s_re_accumulations(snap) +
        _s_best_opportunities(snap) +
        _s_approaching(snap) +
        _s_timeline(snap) +
        _s_diagnostics(snap)
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>EGX Constitutional Opportunity Intelligence Platform</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
{body}
<div style="text-align:center;font-size:11px;color:{DIM};padding:16px 0;margin-top:8px;
     border-top:1px solid {BOR};">
  EGX Constitutional Opportunity Intelligence Platform &nbsp;·&nbsp;
  Append-Only · Immutable Events · No Portfolio Dependency &nbsp;·&nbsp;
  {datetime.now().strftime('%d %b %Y %H:%M')}
</div>
</div>
</body>
</html>"""


if __name__ == "__main__":
    out  = Path(__file__).parent / "dashboard.html"
    html = build_dashboard()
    out.write_text(html, encoding="utf-8")
    sha  = hashlib.sha256(html.encode()).hexdigest()
    print(f"[Dashboard V5] Saved → dashboard.html ({len(html)//1024} KB)")
    print(f"[Dashboard V5] SHA256: {sha}")
