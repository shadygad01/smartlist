"""
EGX Constitutional Opportunity Timeline — Dashboard V1
Event-driven, append-only. No portfolio capacity. No R2 degradation.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from presentation.presentation_snapshot import PresentationSnapshot, build_presentation_snapshot

# ── Theme ─────────────────────────────────────────────────────────────────────
G   = "#4caf50"
R   = "#f44336"
A   = "#f0b840"
B   = "#50d8d0"
P   = "#9c6fff"   # purple for RE_ACCUMULATION
DIM = "#8b8fa8"
FG  = "#d0d4e8"
BG0 = "#0b0c1a"
BG1 = "#10112a"
BG2 = "#181930"
BOR = "#252645"
W   = "#ffffff"

CSS = f"""
body{{margin:0;padding:0;background:{BG0};font-family:'Segoe UI',Arial,sans-serif;color:{FG};}}
.wrap{{max-width:1200px;margin:0 auto;padding:24px 16px;}}
.card{{background:{BG1};border:1px solid {BOR};border-radius:10px;padding:20px;margin-bottom:18px;}}
.section-title{{font-size:13px;font-weight:700;letter-spacing:0.6px;text-transform:uppercase;
  color:{DIM};margin-bottom:14px;border-bottom:1px solid {BOR};padding-bottom:8px;}}
.badge{{display:inline-block;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:700;}}
.chip{{display:inline-block;padding:4px 12px;border-radius:14px;font-size:12px;
  background:{BG2};border:1px solid {BOR};color:{FG};margin:3px;}}
table{{width:100%;border-collapse:collapse;font-size:13px;}}
th{{text-align:left;padding:8px 10px;color:{DIM};font-size:11px;font-weight:700;
  letter-spacing:0.4px;text-transform:uppercase;border-bottom:1px solid {BOR};}}
td{{padding:7px 10px;border-bottom:1px solid {BOR};color:{FG};}}
tr:last-child td{{border-bottom:none;}}
.pos{{color:{G};font-weight:700;}} .neg{{color:{R};font-weight:700;}} .neu{{color:{A};font-weight:700;}}
.bar-bg{{background:{BG2};border-radius:4px;height:8px;overflow:hidden;margin-top:4px;}}
.bar-fill{{height:8px;border-radius:4px;}}
.metric-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px;}}
.metric-cell{{background:{BG2};border:1px solid {BOR};border-radius:8px;padding:14px;}}
.metric-val{{font-size:22px;font-weight:700;margin-bottom:4px;}}
.metric-lbl{{font-size:11px;color:{DIM};text-transform:uppercase;letter-spacing:0.4px;}}
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _star_color(stars: str) -> str:
    n = stars.count("★")
    if n >= 4: return G
    if n == 3: return A
    return R

def _rc(r: float) -> str:
    return "pos" if r > 0 else ("neg" if r < 0 else "neu")

def _sign(r: float) -> str:
    return "+" if r >= 0 else ""

def _status_badge(status: str) -> str:
    if status == "PREMIUM_NOW":
        return f'<span class="badge" style="background:{G}22;color:{G};">🏆 PREMIUM</span>'
    if status == "ACTIVE_OPPORTUNITY":
        return f'<span class="badge" style="background:{A}22;color:{A};">🟢 ACTIVE</span>'
    return f'<span class="badge" style="background:{R}22;color:{R};">🔴 REVIEW</span>'

def _type_badge(etype: str) -> str:
    if etype == "FIRST_BUY":
        return f'<span class="badge" style="background:{B}22;color:{B};">FIRST</span>'
    return f'<span class="badge" style="background:{P}22;color:{P};">RE-ACCUM</span>'


# ── Sections ──────────────────────────────────────────────────────────────────

def _s_header(snap: PresentationSnapshot) -> str:
    sc      = _star_color(snap.health_stars)
    now     = datetime.now().strftime("%A, %d %B %Y")
    premium = sum(1 for e in snap.timeline if e.get("status") == "PREMIUM_NOW")
    active  = sum(1 for e in snap.timeline if e.get("status") == "ACTIVE_OPPORTUNITY")
    review  = sum(1 for e in snap.timeline if e.get("status") == "UNDER_REVIEW")
    new_tag = (
        f'<span style="color:{G};margin-left:12px;font-weight:700;">'
        f'⚡ {len(snap.new_events_today)} NEW EVENT{"S" if len(snap.new_events_today)!=1 else ""} TODAY</span>'
    ) if snap.new_events_today else ""

    return f"""
<div style="background:{BG1};border:1px solid {BOR};border-radius:10px;padding:24px;margin-bottom:18px;">
  <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;">
    <div>
      <div style="font-size:11px;color:{DIM};text-transform:uppercase;letter-spacing:0.8px;margin-bottom:6px;">
        EGX Constitutional Opportunity Timeline
      </div>
      <div style="font-size:22px;font-weight:700;color:{sc};">{snap.health_stars} {snap.health_label}</div>
      <div style="font-size:13px;color:{DIM};margin-top:4px;">{snap.health_narrative}</div>
    </div>
    <div style="text-align:right;font-size:12px;color:{DIM};">
      <div>{now}{new_tag}</div>
      <div style="margin-top:6px;">
        <span style="color:{G};font-weight:700;">{snap.total_events}</span> Events &nbsp;·&nbsp;
        <span style="color:{B};">{snap.total_tickers}</span> Tickers &nbsp;·&nbsp;
        <span style="color:{B};">{len(snap.first_buys)}</span> First Buys &nbsp;·&nbsp;
        <span style="color:{P};">{len(snap.re_accumulations)}</span> Re-Accumulations
      </div>
      <div style="margin-top:4px;font-size:11px;">
        <span style="color:{G};">🏆 Premium: {premium}</span> &nbsp;·&nbsp;
        <span style="color:{A};">Active: {active}</span> &nbsp;·&nbsp;
        <span style="color:{R};">Review: {review}</span>
      </div>
    </div>
  </div>
</div>"""


def _s_new_today(snap: PresentationSnapshot) -> str:
    if not snap.new_events_today:
        return ""
    rows = ""
    for e in snap.new_events_today:
        rows += f"""
<tr>
  <td>{_type_badge(e['event_type'])}</td>
  <td style="font-weight:700;color:{G};">{e['ticker']}</td>
  <td style="color:{DIM};">{e['sector']}</td>
  <td style="color:{FG};">R2={e['buy_r2']:.1f}</td>
  <td style="color:{FG};">{e['entry_price']:.2f} EGP</td>
  <td style="color:{FG};">{e['buy_score']:.1f}</td>
</tr>"""
    return f"""
<div class="card" style="border-color:{G};">
  <div class="section-title" style="color:{G};">⚡ New Constitutional Events Today</div>
  <table>
    <tr><th>Type</th><th>Ticker</th><th>Sector</th><th>R2</th><th>Entry</th><th>Score</th></tr>
    {rows}
  </table>
</div>"""


def _event_rows(events: list[dict]) -> str:
    rows = ""
    for e in events:
        rows += f"""
<tr>
  <td>{_type_badge(e['event_type'])}</td>
  <td style="font-weight:700;color:{B};">{e['ticker']}</td>
  <td style="color:{DIM};font-size:11px;">{e['event_date']}</td>
  <td style="color:{DIM};">{e['sector']}</td>
  <td style="color:{DIM};">{e['entry_price']:.2f}</td>
  <td style="color:{DIM};">{e['current_price']:.2f}</td>
  <td class="{_rc(e['return_pct'])}">{_sign(e['return_pct'])}{e['return_pct']:.1f}%</td>
  <td style="color:{G};font-size:12px;">{_sign(e['peak_return_pct'])}{e['peak_return_pct']:.1f}%</td>
  <td style="color:{DIM};font-size:11px;">{e['days_active']}d</td>
  <td>{_status_badge(e['status'])}</td>
</tr>"""
    return rows


def _event_table_header() -> str:
    return "<tr><th>Type</th><th>Ticker</th><th>Date</th><th>Sector</th><th>Entry</th><th>Current</th><th>Return</th><th>Peak</th><th>Days</th><th>Status</th></tr>"


def _s_timeline(snap: PresentationSnapshot) -> str:
    if not snap.timeline:
        return f'<div class="card"><div style="color:{DIM};">No constitutional events recorded.</div></div>'
    rows = _event_rows(snap.timeline)
    return f"""
<div class="card">
  <div class="section-title">📋 Constitutional Opportunity Timeline — {snap.total_events} Events
    <span style="font-size:11px;color:{DIM};font-weight:400;margin-left:8px;">
      Append-only · Immutable · No capacity · No R2 degradation
    </span>
  </div>
  <table>{_event_table_header()}{rows}</table>
</div>"""


def _s_leaderboards(snap: PresentationSnapshot) -> str:
    lb = snap.leaderboards
    if not lb:
        return ""

    # Most repeated
    most_rep = lb.get("most_repeated", [])[:8]
    rep_rows = ""
    for i, a in enumerate(most_rep, 1):
        rep_rows += f"""
<tr>
  <td style="color:{DIM};">{i}</td>
  <td style="font-weight:700;color:{B};">{a['ticker']}</td>
  <td style="color:{DIM};">{a['sector']}</td>
  <td style="color:{P};font-weight:700;">{a['total_events']}</td>
  <td class="{_rc(a['avg_return_pct'])}">{_sign(a['avg_return_pct'])}{a['avg_return_pct']:.1f}%</td>
  <td class="{_rc(a['best_return_pct'])}">{_sign(a['best_return_pct'])}{a['best_return_pct']:.1f}%</td>
</tr>"""

    # Top compound return
    compound = lb.get("compound_return", [])[:8]
    comp_rows = ""
    for i, c in enumerate(compound, 1):
        comp_rows += f"""
<tr>
  <td style="color:{DIM};">{i}</td>
  <td style="font-weight:700;color:{B};">{c['ticker']}</td>
  <td style="color:{DIM};">{c['sector']}</td>
  <td style="color:{DIM};">{c['total_events']}</td>
  <td style="color:{DIM};">{c['first_entry']:.2f}</td>
  <td style="color:{DIM};">{c['current_price']:.2f}</td>
  <td class="{_rc(c['compound_return_pct'])}">{_sign(c['compound_return_pct'])}{c['compound_return_pct']:.1f}%</td>
</tr>"""

    # Highest peak events
    peak_events = lb.get("highest_peak", [])[:5]
    peak_rows = ""
    for e in peak_events:
        peak_rows += f"""
<tr>
  <td style="font-weight:700;color:{B};">{e['ticker']}</td>
  <td style="color:{DIM};font-size:11px;">{e['event_date']}</td>
  <td>{_type_badge(e['event_type'])}</td>
  <td style="color:{DIM};">{e['entry_price']:.2f}</td>
  <td class="pos">{_sign(e['peak_return_pct'])}{e['peak_return_pct']:.1f}%</td>
  <td class="{_rc(e['return_pct'])}">{_sign(e['return_pct'])}{e['return_pct']:.1f}%</td>
</tr>"""

    return f"""
<div class="card">
  <div class="section-title">🏆 Leaderboards</div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:18px;flex-wrap:wrap;">
    <div>
      <div style="font-size:12px;color:{P};font-weight:700;margin-bottom:8px;">Most Repeated Constitutional Opportunities</div>
      <table>
        <tr><th>#</th><th>Ticker</th><th>Sector</th><th>Events</th><th>Avg Ret</th><th>Best</th></tr>
        {rep_rows}
      </table>
    </div>
    <div>
      <div style="font-size:12px;color:{G};font-weight:700;margin-bottom:8px;">Highest Compound Return (First Entry → Today)</div>
      <table>
        <tr><th>#</th><th>Ticker</th><th>Sector</th><th>Events</th><th>First Entry</th><th>Now</th><th>Compound</th></tr>
        {comp_rows}
      </table>
    </div>
  </div>
  <div style="margin-top:18px;">
    <div style="font-size:12px;color:{A};font-weight:700;margin-bottom:8px;">Highest Peak Return Events</div>
    <table>
      <tr><th>Ticker</th><th>Event Date</th><th>Type</th><th>Entry</th><th>Peak Ret</th><th>Current Ret</th></tr>
      {peak_rows}
    </table>
  </div>
</div>"""


def _s_performance_metrics(snap: PresentationSnapshot) -> str:
    tl = snap.timeline
    if not tl:
        return ""

    rets     = [e["return_pct"] for e in tl]
    avg      = sum(rets) / len(rets)
    wins     = sum(1 for r in rets if r > 0)
    best_e   = max(tl, key=lambda e: e["return_pct"])
    worst_e  = min(tl, key=lambda e: e["return_pct"])
    avg_days = sum(e["days_active"] for e in tl) / len(tl)

    sec_cnts: dict[str, int] = {}
    for e in tl:
        s = e.get("sector") or "Other"
        sec_cnts[s] = sec_cnts.get(s, 0) + 1

    sector_bars = ""
    for sec, cnt in sorted(sec_cnts.items(), key=lambda x: -x[1]):
        pct = cnt / len(tl) * 100
        sector_bars += f"""
<div style="margin-bottom:10px;">
  <div style="display:flex;justify-content:space-between;font-size:12px;">
    <span>{sec}</span>
    <span style="color:{B};font-weight:700;">{cnt} events ({pct:.0f}%)</span>
  </div>
  <div class="bar-bg"><div class="bar-fill" style="width:{min(pct*2,100):.0f}%;background:{B};"></div></div>
</div>"""

    avg_c = G if avg >= 0 else R
    return f"""
<div class="card">
  <div class="section-title">📊 Performance Metrics</div>
  <div class="metric-grid" style="margin-bottom:16px;">
    <div class="metric-cell">
      <div class="metric-val" style="color:{avg_c};">{avg:+.1f}%</div>
      <div class="metric-lbl">Avg Return / Event</div>
    </div>
    <div class="metric-cell">
      <div class="metric-val" style="color:{G};">{wins}/{len(rets)}</div>
      <div class="metric-lbl">Win Rate</div>
    </div>
    <div class="metric-cell">
      <div class="metric-val" style="color:{G};">{best_e['return_pct']:+.1f}%</div>
      <div class="metric-lbl">Best ({best_e['ticker']})</div>
    </div>
    <div class="metric-cell">
      <div class="metric-val" style="color:{R};">{worst_e['return_pct']:+.1f}%</div>
      <div class="metric-lbl">Worst ({worst_e['ticker']})</div>
    </div>
    <div class="metric-cell">
      <div class="metric-val" style="color:{FG};">{snap.total_events}</div>
      <div class="metric-lbl">Total Events</div>
    </div>
    <div class="metric-cell">
      <div class="metric-val" style="color:{DIM};">{avg_days:.0f}d</div>
      <div class="metric-lbl">Avg Days Active</div>
    </div>
  </div>
  <div class="section-title" style="margin-top:0;">Sector Distribution (no cap enforced)</div>
  {sector_bars}
</div>"""


def _s_research(snap: PresentationSnapshot) -> str:
    if not snap.research_insights:
        return ""
    rows = ""
    for ins in snap.research_insights[:5]:
        cc = G if ins["confidence"] == "HIGH" else (A if ins["confidence"] == "MEDIUM" else DIM)
        rows += f"""
<tr>
  <td style="color:{DIM};font-size:12px;">{ins['question']}</td>
  <td style="color:{FG};font-size:12px;">{ins['conclusion']}</td>
  <td><span class="badge" style="background:{cc}22;color:{cc};">{ins['confidence']}</span></td>
</tr>"""
    return f"""
<div class="card">
  <div class="section-title">🔬 Research Insights ({snap.knowledge_count} verified findings)</div>
  <table>
    <tr><th>Question</th><th>Conclusion</th><th>Confidence</th></tr>
    {rows}
  </table>
</div>"""


def _s_system() -> str:
    base  = Path(__file__).parent
    items = []
    for fname, label in [("scheduler_state.json", "Scheduler"), ("scan_status.json", "Last Scan")]:
        fp = base / fname
        if fp.exists():
            try:
                data  = json.loads(fp.read_text())
                ts    = data.get("last_run") or data.get("last_scan") or data.get("timestamp") or "—"
                ok    = data.get("status", "ok")
                color = G if str(ok).lower() in ("ok", "success", "complete", "done") else A
                items.append(
                    f'<div style="font-size:12px;margin-bottom:4px;">'
                    f'<span style="color:{DIM};">{label}:</span> '
                    f'<span style="color:{color};">{ts}</span></div>'
                )
            except Exception:
                pass
    body = "".join(items) or f'<div style="color:{DIM};font-size:12px;">System status unavailable.</div>'
    return f'<div class="card"><div class="section-title">🔧 System Health</div>{body}</div>'


# ── Build ─────────────────────────────────────────────────────────────────────

def build_dashboard() -> str:
    snap = build_presentation_snapshot()
    body = (
        _s_header(snap) +
        _s_new_today(snap) +
        _s_timeline(snap) +
        _s_leaderboards(snap) +
        _s_performance_metrics(snap) +
        _s_research(snap) +
        _s_system()
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>EGX Constitutional Opportunity Timeline</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
{body}
<div style="text-align:center;font-size:11px;color:{DIM};padding:16px 0;margin-top:8px;
     border-top:1px solid {BOR};">
  EGX Constitutional Opportunity Timeline &nbsp;·&nbsp;
  Append-Only &nbsp;·&nbsp; Immutable Events &nbsp;·&nbsp;
  {datetime.now().strftime('%d %b %Y %H:%M')}
</div>
</div>
</body>
</html>"""


if __name__ == "__main__":
    out  = Path(__file__).parent / "dashboard.html"
    html = build_dashboard()
    out.write_text(html, encoding="utf-8")
    print(f"[Dashboard V1 Timeline] Saved → dashboard.html ({len(html)//1024} KB)")
