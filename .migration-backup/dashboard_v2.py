"""
EGX Constitutional Investment Platform — Dashboard V2
Constitutional portfolio management view. No scanner. No signal engine.
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
.chip{{display:inline-block;padding:4px 12px;border-radius:14px;font-size:12px;
  background:{BG2};border:1px solid {BOR};color:{FG};margin:3px;}}
table{{width:100%;border-collapse:collapse;font-size:13px;}}
th{{text-align:left;padding:8px 10px;color:{DIM};font-size:11px;font-weight:700;
  letter-spacing:0.4px;text-transform:uppercase;border-bottom:1px solid {BOR};}}
td{{padding:8px 10px;border-bottom:1px solid {BOR};color:{FG};}}
tr:last-child td{{border-bottom:none;}}
.pos{{color:{G};font-weight:700;}} .neg{{color:{R};font-weight:700;}} .neu{{color:{A};}}
.bar-bg{{background:{BG2};border-radius:4px;height:8px;overflow:hidden;margin-top:4px;}}
.bar-fill{{height:8px;border-radius:4px;}}
.metric-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px;}}
.metric-cell{{background:{BG2};border:1px solid {BOR};border-radius:8px;padding:14px;}}
.metric-val{{font-size:22px;font-weight:700;margin-bottom:4px;}}
.metric-lbl{{font-size:11px;color:{DIM};text-transform:uppercase;letter-spacing:0.4px;}}
"""

# ── Helper ────────────────────────────────────────────────────────────────────
def _star_color(stars: str) -> str:
    count = stars.count("★")
    if count >= 4: return G
    if count == 3: return A
    return R


def _pct_color(pct: float, warn: float = 25.0, danger: float = 35.0) -> str:
    if pct >= danger: return R
    if pct >= warn:   return A
    return G


def _ret_class(r: float) -> str:
    if r > 0:  return "pos"
    if r < 0:  return "neg"
    return "neu"


# ── Sections ──────────────────────────────────────────────────────────────────

def _s_header(snap: PresentationSnapshot) -> str:
    sc = _star_color(snap.health_stars)
    now = datetime.now().strftime("%A, %d %B %Y")
    cap_warn = f'<span style="color:{R};margin-left:12px;">⚠ Capacity {snap.capacity_used_pct:.0f}%</span>' \
               if snap.capacity_used_pct > 100 else \
               f'<span style="color:{G};margin-left:12px;">Capacity {snap.capacity_used_pct:.0f}%</span>'
    cap_sec = f'<span style="color:{R};margin-left:12px;">⚠ Sector cap exceeded</span>' \
              if not snap.sector_cap_ok else ""

    return f"""
<div style="background:{BG1};border:1px solid {BOR};border-radius:10px;padding:24px;margin-bottom:18px;">
  <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;">
    <div>
      <div style="font-size:11px;color:{DIM};text-transform:uppercase;letter-spacing:0.8px;margin-bottom:6px;">
        EGX Constitutional Investment Platform
      </div>
      <div style="font-size:22px;font-weight:700;color:{sc};">{snap.health_stars} {snap.health_label}</div>
      <div style="font-size:13px;color:{DIM};margin-top:6px;">{snap.health_narrative}</div>
    </div>
    <div style="text-align:right;font-size:12px;color:{DIM};">
      <div>{now}</div>
      <div style="margin-top:4px;">{snap.held_count} positions held{cap_warn}{cap_sec}</div>
    </div>
  </div>
</div>"""


def _s_opportunities(snap: PresentationSnapshot) -> str:
    rows = ""
    for r in snap.opportunities:
        conf_color = G if r.get("confidence") == "HIGH" else A
        rows += f"""
<tr>
  <td style="font-weight:700;color:{B};">{r['ticker']}</td>
  <td style="color:{DIM};">{r.get('sector','')}</td>
  <td><span class="badge" style="background:{conf_color}22;color:{conf_color};">
    {r.get('decision','Constitutional BUY')}</span></td>
  <td style="color:{DIM};font-size:12px;">{r.get('reason','')}</td>
</tr>"""

    if not rows:
        rows = f'<tr><td colspan=4 style="color:{DIM};text-align:center;padding:20px;">No active opportunities today.</td></tr>'

    return f"""
<div class="card">
  <div class="section-title">🎯 Today's Opportunities</div>
  <table>
    <tr><th>Ticker</th><th>Sector</th><th>Decision</th><th>Reason</th></tr>
    {rows}
  </table>
</div>"""


def _s_future(snap: PresentationSnapshot) -> str:
    if not snap.future_priorities:
        return ""
    chips = "".join(
        f'<span class="chip">'
        f'<span style="color:{B};font-weight:700;">{r["ticker"]}</span>'
        f'<span style="color:{DIM};font-size:11px;margin-left:6px;">{r.get("sector","")}</span>'
        f'</span>'
        for r in snap.future_priorities
    )
    return f"""
<div class="card">
  <div class="section-title">⏳ Future Priorities</div>
  <div style="font-size:12px;color:{DIM};margin-bottom:10px;">
    Buy when portfolio capacity opens. Currently blocked by sector concentration.
  </div>
  {chips}
</div>"""


def _s_portfolio(snap: PresentationSnapshot) -> str:
    rows = ""
    for p in snap.held_positions:
        rc = _ret_class(p["return_pct"])
        sign = "+" if p["return_pct"] > 0 else ""
        rows += f"""
<tr>
  <td style="font-weight:700;color:{FG};">{p['ticker']}</td>
  <td style="color:{DIM};">{p['sector']}</td>
  <td style="color:{DIM};">{p['entry_price']:.2f} EGP</td>
  <td style="color:{DIM};">{p['current_price']:.2f} EGP</td>
  <td class="{rc}">{sign}{p['return_pct']:.1f}%</td>
</tr>"""

    if not rows:
        rows = f'<tr><td colspan=5 style="color:{DIM};text-align:center;padding:20px;">No positions held.</td></tr>'

    return f"""
<div class="card">
  <div class="section-title">📂 Current Portfolio ({snap.held_count} positions)</div>
  <table>
    <tr><th>Ticker</th><th>Sector</th><th>Entry</th><th>Current</th><th>Return</th></tr>
    {rows}
  </table>
</div>"""


def _s_health(snap: PresentationSnapshot) -> str:
    sector_bars = ""
    cap_limit = 25.0
    for sec, pct in sorted(snap.sector_allocation.items(), key=lambda x: -x[1]):
        color = _pct_color(pct)
        warn  = " ⚠" if pct >= cap_limit else ""
        sector_bars += f"""
<div style="margin-bottom:12px;">
  <div style="display:flex;justify-content:space-between;font-size:12px;">
    <span style="color:{FG};">{sec}</span>
    <span style="color:{color};font-weight:700;">{pct:.1f}%{warn}</span>
  </div>
  <div class="bar-bg">
    <div class="bar-fill" style="width:{min(pct/50*100,100):.0f}%;background:{color};"></div>
  </div>
</div>"""

    corr_color = G if snap.max_correlation < 0.6 else (A if snap.max_correlation < 0.75 else R)
    cap_color  = G if snap.capacity_used_pct <= 100 else R

    metrics = f"""
<div class="metric-grid" style="margin-top:16px;">
  <div class="metric-cell">
    <div class="metric-val" style="color:{corr_color};">{snap.max_correlation:.2f}</div>
    <div class="metric-lbl">Max Correlation</div>
  </div>
  <div class="metric-cell">
    <div class="metric-val" style="color:{cap_color};">{snap.capacity_used_pct:.0f}%</div>
    <div class="metric-lbl">Capacity Used</div>
  </div>
  <div class="metric-cell">
    <div class="metric-val" style="color:{G if snap.sector_cap_ok else R};">
      {'Within Limits' if snap.sector_cap_ok else 'Exceeded'}</div>
    <div class="metric-lbl">Sector Cap</div>
  </div>
</div>"""

    return f"""
<div class="card">
  <div class="section-title">⚖️ Portfolio Health Metrics</div>
  {sector_bars}
  {metrics}
</div>"""


def _s_watch(snap: PresentationSnapshot) -> str:
    if not snap.watch_list:
        return ""
    chips = "".join(f'<span class="chip">{t}</span>' for t in snap.watch_list)
    return f"""
<div class="card">
  <div class="section-title">👁 Watch List</div>
  <div style="font-size:12px;color:{DIM};margin-bottom:10px;">
    Track for future portfolio additions.
  </div>
  {chips}
</div>"""


def _s_research(snap: PresentationSnapshot) -> str:
    if not snap.research_insights:
        return ""
    rows = ""
    for ins in snap.research_insights[:5]:
        conf_color = G if ins["confidence"] == "HIGH" else (A if ins["confidence"] == "MEDIUM" else DIM)
        rows += f"""
<tr>
  <td style="color:{DIM};font-size:12px;">{ins['question']}</td>
  <td style="color:{FG};font-size:12px;">{ins['conclusion']}</td>
  <td><span class="badge" style="background:{conf_color}22;color:{conf_color};">{ins['confidence']}</span></td>
</tr>"""

    return f"""
<div class="card">
  <div class="section-title">🔬 Research Insight ({snap.knowledge_count} verified findings)</div>
  <table>
    <tr><th>Question</th><th>Conclusion</th><th>Confidence</th></tr>
    {rows}
  </table>
</div>"""


def _s_system() -> str:
    base = Path(__file__).parent
    items = []
    for fname, label in [
        ("scheduler_state.json", "Scheduler"),
        ("scan_status.json",     "Last Scan"),
    ]:
        fp = base / fname
        if fp.exists():
            try:
                data = json.loads(fp.read_text())
                ts   = data.get("last_run") or data.get("last_scan") or data.get("timestamp") or "—"
                ok   = data.get("status", "ok")
                color = G if str(ok).lower() in ("ok","success","complete","done") else A
                items.append(
                    f'<div style="margin-bottom:6px;font-size:12px;">'
                    f'<span style="color:{DIM};">{label}:</span> '
                    f'<span style="color:{color};">{ts}</span></div>'
                )
            except Exception:
                pass

    body = "".join(items) if items else f'<div style="color:{DIM};font-size:12px;">System status unavailable.</div>'
    return f"""
<div class="card">
  <div class="section-title">🔧 System Health</div>
  {body}
</div>"""


# ── Build ─────────────────────────────────────────────────────────────────────

def build_dashboard() -> str:
    snap = build_presentation_snapshot()

    body = (
        _s_header(snap) +
        _s_opportunities(snap) +
        _s_future(snap) +
        _s_portfolio(snap) +
        _s_health(snap) +
        _s_watch(snap) +
        _s_research(snap) +
        _s_system()
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>EGX Constitutional Investment Platform</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
{body}
<div style="text-align:center;font-size:11px;color:{DIM};padding:16px 0;margin-top:8px;
     border-top:1px solid {BOR};">
  EGX Constitutional Investment Platform &nbsp;·&nbsp;
  Research-Driven &nbsp;·&nbsp; Constitutionally Governed &nbsp;·&nbsp;
  {datetime.now().strftime('%d %b %Y %H:%M')}
</div>
</div>
</body>
</html>"""


if __name__ == "__main__":
    out = Path(__file__).parent / "dashboard.html"
    html = build_dashboard()
    out.write_text(html, encoding="utf-8")
    print(f"[Dashboard V2] Saved → dashboard.html ({len(html)//1024} KB)")
