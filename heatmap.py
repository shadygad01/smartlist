#!/usr/bin/env python3
"""
heatmap.py — Generate an interactive HTML heatmap of EGX SMC signal scores.
Run: python heatmap.py  →  opens heatmap.html
"""

import json
import os
from datetime import date

BASE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    path = os.path.join(BASE, name)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


history     = load('signal_history.json')
scan_results = load('scan_results.json')
positions   = load('open_positions.json')

# ── Sector grouping (display order) ───────────────────────────────────────
SECTORS = [
    ('Real Estate',  ['TMGH.CA', 'EMFD.CA', 'PHDC.CA', 'ORHD.CA', 'HELI.CA']),
    ('Industrial',   ['EAST.CA', 'ABUK.CA', 'ORAS.CA', 'EFID.CA', 'HRHO.CA',
                      'JUFO.CA', 'ARCC.CA', 'ORWE.CA', 'CCAP.CA']),
    ('Healthcare',   ['MCQE.CA', 'ISPH.CA', 'RMDA.CA']),
    ('Finance/Tech', ['FWRY.CA', 'EFIH.CA', 'RAYA.CA', 'BTFH.CA']),
    ('Banking',      ['COMI.CA', 'EGAL.CA', 'ADIB.CA']),
    ('Telecom/Auto', ['ETEL.CA', 'GBCO.CA', 'OIH.CA']),
]

# ── Collect all dates ──────────────────────────────────────────────────────
all_dates = sorted({
    sig['date']
    for signals in history.values()
    for sig in signals
})

# ── Build per-stock per-date lookup ───────────────────────────────────────
lookup = {
    stock: {sig['date']: sig for sig in signals}
    for stock, signals in history.items()
}

# ── Current scan snapshot ─────────────────────────────────────────────────
today_str = date.today().isoformat()
today_scores = {
    t: {
        'score':  d.get('score', 0),
        'price':  d.get('price', 0),
        'signal': d.get('signal', '-'),
        'r1':     d.get('r1', 0),
    }
    for t, d in scan_results.items()
}

# ── Stats ─────────────────────────────────────────────────────────────────
stocks_with_history = [s for s in history if history[s]]
open_count = len(positions)
max_score_stock = max(
    (
        (s, max(sig['score'] for sig in history[s]))
        for s in stocks_with_history
    ),
    key=lambda x: x[1],
    default=('—', 0),
)

# ── Build data for JS ─────────────────────────────────────────────────────
js_history     = json.dumps(lookup,      ensure_ascii=False, separators=(',', ':'))
js_today       = json.dumps(today_scores, ensure_ascii=False, separators=(',', ':'))
js_dates       = json.dumps(all_dates,    separators=(',', ':'))
js_positions   = json.dumps(list(positions.keys()), separators=(',', ':'))
js_sectors     = json.dumps(SECTORS,      ensure_ascii=False, separators=(',', ':'))
js_today_str   = json.dumps(today_str)

# ─────────────────────────────────────────────────────────────────────────
HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>EGX SMC — Signal Score Heatmap</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0d1117;color:#c9d1d9;font-family:'Segoe UI',system-ui,sans-serif;font-size:13px;min-height:100vh}}

/* ── Header ───────────────────────────────────── */
.header{{background:#161b22;border-bottom:1px solid #30363d;padding:16px 24px;display:flex;align-items:center;gap:16px;flex-wrap:wrap}}
.header h1{{font-size:18px;font-weight:600;color:#e6edf3;flex:1 0 auto}}
.badge{{background:#21262d;border:1px solid #30363d;border-radius:6px;padding:3px 10px;font-size:11px;color:#8b949e}}
.badge.green{{border-color:#238636;color:#3fb950}}
.badge.yellow{{border-color:#9e6a03;color:#d29922}}

/* ── Stats bar ────────────────────────────────── */
.stats{{display:flex;gap:1px;background:#30363d;border-bottom:1px solid #30363d}}
.stat{{flex:1;background:#161b22;padding:10px 20px;text-align:center}}
.stat .val{{font-size:22px;font-weight:700;color:#e6edf3;line-height:1}}
.stat .lbl{{font-size:11px;color:#8b949e;margin-top:3px}}

/* ── Controls ─────────────────────────────────── */
.controls{{padding:12px 24px;display:flex;align-items:center;gap:12px;flex-wrap:wrap;background:#0d1117;border-bottom:1px solid #21262d}}
.ctrl-label{{font-size:11px;color:#8b949e;text-transform:uppercase;letter-spacing:.05em}}
.btn-group{{display:flex;gap:4px}}
.btn{{background:#21262d;border:1px solid #30363d;border-radius:6px;padding:5px 12px;font-size:12px;color:#c9d1d9;cursor:pointer;transition:all .15s}}
.btn:hover{{background:#30363d;border-color:#8b949e}}
.btn.active{{background:#238636;border-color:#2ea043;color:#fff}}

/* ── Legend ───────────────────────────────────── */
.legend{{padding:8px 24px;display:flex;align-items:center;gap:10px;border-bottom:1px solid #21262d;background:#0d1117}}
.legend-text{{font-size:11px;color:#8b949e}}
.legend-gradient{{display:flex;gap:2px;align-items:center}}
.legend-cell{{width:20px;height:14px;border-radius:2px}}
.legend-pos{{display:flex;align-items:center;gap:5px;margin-left:16px;font-size:11px;color:#8b949e}}
.pos-dot{{width:8px;height:8px;border-radius:50%;background:#f78166;display:inline-block}}

/* ── Heatmap wrapper ──────────────────────────── */
.hm-outer{{overflow-x:auto;padding:24px}}
.hm-table{{border-collapse:collapse;white-space:nowrap}}

/* ── Sector header ────────────────────────────── */
.sector-row td{{padding:10px 8px 4px;font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:#6e7681;font-weight:600;border:none!important}}

/* ── Row header (stock name) ──────────────────── */
.stock-name{{position:sticky;left:0;z-index:2;background:#0d1117;padding:0 10px 0 0;text-align:right;font-size:12px;font-weight:500;width:86px;min-width:86px}}
.stock-name.has-pos{{color:#f78166}}
.stock-name.has-signal{{color:#3fb950}}

/* ── Heatmap cells ────────────────────────────── */
.hm-cell{{width:16px;height:26px;border-radius:2px;cursor:pointer;position:relative;transition:transform .1s,outline .1s}}
.hm-cell:hover{{transform:scale(1.4);z-index:10;outline:2px solid #e6edf3}}
.pos-marker{{position:absolute;bottom:2px;right:2px;width:4px;height:4px;border-radius:50%;background:#f78166}}

/* ── Today column ─────────────────────────────── */
.today-sep{{width:8px}}
.today-cell{{width:54px;min-width:54px;height:26px;border-radius:4px;cursor:pointer;text-align:center;font-size:10px;font-weight:600;line-height:26px;transition:transform .1s}}
.today-cell:hover{{transform:scale(1.05);z-index:10;outline:2px solid #e6edf3}}

/* ── Date header ──────────────────────────────── */
.date-header{{font-size:9px;color:#6e7681;text-align:center;padding:0 1px;transform:rotate(-55deg) translateX(4px);transform-origin:center bottom;height:50px;vertical-align:bottom}}
.today-header{{font-size:10px;color:#3fb950;font-weight:600;text-align:center;vertical-align:bottom;padding-bottom:4px}}

/* ── Tooltip ──────────────────────────────────── */
#tooltip{{position:fixed;pointer-events:none;background:#1c2128;border:1px solid #30363d;border-radius:8px;padding:10px 14px;font-size:12px;line-height:1.6;z-index:999;min-width:160px;box-shadow:0 8px 24px #0008;display:none}}
#tooltip .tt-stock{{font-size:13px;font-weight:700;color:#e6edf3;margin-bottom:4px}}
#tooltip .tt-row{{display:flex;justify-content:space-between;gap:16px}}
#tooltip .tt-label{{color:#8b949e}}
#tooltip .tt-val{{color:#e6edf3;font-weight:600}}
#tooltip .tt-score{{font-size:20px;font-weight:800;margin-top:4px}}
#tooltip .tt-pos{{color:#f78166;font-size:11px;margin-top:4px}}

/* ── Summary section ──────────────────────────── */
.summary{{padding:20px 24px;border-top:1px solid #21262d;display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px}}
.pos-card{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px 16px}}
.pos-card.has-signal{{border-color:#238636}}
.pos-card .pc-ticker{{font-size:14px;font-weight:700;color:#e6edf3}}
.pos-card .pc-level{{font-size:11px;color:#8b949e}}
.pos-card .pc-bar{{height:6px;background:#21262d;border-radius:3px;margin:8px 0;overflow:hidden}}
.pos-card .pc-fill{{height:100%;border-radius:3px;background:linear-gradient(90deg,#238636,#3fb950)}}
</style>
</head>
<body>

<!-- ── Header ─────────────────────────────────────────────────────── -->
<div class="header">
  <h1>📊 EGX SMC Signal Score Heatmap</h1>
  <span class="badge">EGX Egyptian Stock Exchange</span>
  <span class="badge green" id="gen-date">Generated: {today_str}</span>
  <span class="badge yellow" id="open-badge">{open_count} Open Positions</span>
</div>

<!-- ── Stats bar ──────────────────────────────────────────────────── -->
<div class="stats">
  <div class="stat"><div class="val">{len(stocks_with_history)}</div><div class="lbl">Stocks w/ Signals</div></div>
  <div class="stat"><div class="val">{len(all_dates)}</div><div class="lbl">Signal Days</div></div>
  <div class="stat"><div class="val">{open_count}</div><div class="lbl">Open Positions</div></div>
  <div class="stat"><div class="val" id="max-score-val">{max_score_stock[1]}</div><div class="lbl">Peak Score ({max_score_stock[0]})</div></div>
</div>

<!-- ── Controls ───────────────────────────────────────────────────── -->
<div class="controls">
  <span class="ctrl-label">Date Range</span>
  <div class="btn-group">
    <button class="btn" id="btn-all" onclick="setRange('all')">All Time</button>
    <button class="btn active" id="btn-90" onclick="setRange(90)">90 Days</button>
    <button class="btn" id="btn-60" onclick="setRange(60)">60 Days</button>
    <button class="btn" id="btn-30" onclick="setRange(30)">30 Days</button>
  </div>
  <span class="ctrl-label" style="margin-left:12px">View</span>
  <div class="btn-group">
    <button class="btn active" id="view-score" onclick="setView('score')">Score</button>
    <button class="btn" id="view-r1" onclick="setView('r1')">R1</button>
  </div>
</div>

<!-- ── Legend ─────────────────────────────────────────────────────── -->
<div class="legend">
  <span class="legend-text">Score:</span>
  <div class="legend-gradient" id="legend-gradient"></div>
  <span class="legend-text">35 → 100+</span>
  <div class="legend-pos">
    <span class="pos-dot"></span>
    <span>Open Position</span>
  </div>
</div>

<!-- ── Heatmap ─────────────────────────────────────────────────────── -->
<div class="hm-outer">
  <table class="hm-table" id="hm-table"></table>
</div>

<!-- ── Open Positions Summary ─────────────────────────────────────── -->
<div class="summary" id="pos-summary"></div>

<!-- ── Tooltip ────────────────────────────────────────────────────── -->
<div id="tooltip"></div>

<script>
// ── Embedded data ────────────────────────────────────────────────────────
const HISTORY   = {js_history};
const TODAY_SC  = {js_today};
const ALL_DATES = {js_dates};
const OPEN_POS  = new Set({js_positions});
const SECTORS   = {js_sectors};
const TODAY     = {js_today_str};

// ── State ────────────────────────────────────────────────────────────────
let currentRange = 90;
let currentView  = 'score';

// ── Colour helpers ───────────────────────────────────────────────────────
function scoreColor(val) {{
    if (!val || val < 35) return '#1c2128';
    const t = Math.min((val - 35) / 65, 1);
    const r = Math.round(27  + t * (64  - 27));
    const g = Math.round(58  + t * (210 - 58));
    const b = Math.round(46  + t * (100 - 46));
    return `rgb(${{r}},${{g}},${{b}})`;
}}
function r1Color(val) {{
    if (!val || val < 12) return '#1c2128';
    const t = Math.min((val - 12) / 20, 1);
    const r = Math.round(100 + t * (120 - 100));
    const g = Math.round(65  + t * (180 - 65));
    const b = Math.round(20  + t * (50  - 20));
    return `rgb(${{r}},${{g}},${{b}})`;
}}
function textForBg(val, isR1) {{
    const t = isR1
        ? Math.min((val - 12) / 20, 1)
        : Math.min((val - 35) / 65, 1);
    return t > 0.65 ? '#0d1117' : '#8b949e';
}}

// ── Date filter ──────────────────────────────────────────────────────────
function filteredDates() {{
    if (currentRange === 'all') return ALL_DATES;
    const cutoff = new Date(TODAY);
    cutoff.setDate(cutoff.getDate() - currentRange);
    const cut = cutoff.toISOString().slice(0, 10);
    return ALL_DATES.filter(d => d >= cut);
}}

// ── Build legend ─────────────────────────────────────────────────────────
function buildLegend() {{
    const el = document.getElementById('legend-gradient');
    el.innerHTML = '';
    const steps = [0, 35, 45, 55, 65, 75, 85, 95];
    steps.forEach(v => {{
        const d = document.createElement('div');
        d.className = 'legend-cell';
        d.style.background = v === 0 ? '#1c2128' : scoreColor(v);
        d.title = v === 0 ? 'No signal' : `Score ≥ ${{v}}`;
        el.appendChild(d);
    }});
}}

// ── Build heatmap ────────────────────────────────────────────────────────
function buildHeatmap() {{
    const dates = filteredDates();
    const table = document.getElementById('hm-table');
    table.innerHTML = '';

    // ── Date header row ──────────────────────────────────────────────────
    const hRow = document.createElement('tr');
    // Empty corner cell
    const corner = document.createElement('td');
    corner.style.cssText = 'width:86px;min-width:86px';
    hRow.appendChild(corner);
    // Date columns
    dates.forEach((d, i) => {{
        const prev = dates[i - 1] || '';
        const th = document.createElement('td');
        th.className = 'date-header';
        // Show label only every ~7 dates or on month change
        const dMonth = d.slice(0, 7);
        const pMonth = prev.slice(0, 7);
        if (dMonth !== pMonth || i === 0) {{
            th.textContent = d.slice(5); // MM-DD
            th.style.color = '#8b949e';
        }}
        hRow.appendChild(th);
    }});
    // Today separator + header
    const sep = document.createElement('td'); sep.className = 'today-sep'; hRow.appendChild(sep);
    const todayTh = document.createElement('td'); todayTh.className = 'today-header'; todayTh.textContent = 'Today'; hRow.appendChild(todayTh);
    table.appendChild(hRow);

    // ── Sector rows ──────────────────────────────────────────────────────
    let totalSignals = 0;
    SECTORS.forEach(([sector, stocks]) => {{
        // Sector label row
        const sRow = document.createElement('tr');
        sRow.className = 'sector-row';
        const sTd = document.createElement('td');
        sTd.setAttribute('colspan', dates.length + 3);
        sTd.textContent = sector;
        sRow.appendChild(sTd);
        table.appendChild(sRow);

        // Stock rows
        stocks.forEach(stock => {{
            const stockData = HISTORY[stock] || {{}};
            const hasPos    = OPEN_POS.has(stock);
            const todayInfo = TODAY_SC[stock] || {{}};
            const hasSignal = (todayInfo.score || 0) >= 35;

            const tr = document.createElement('tr');

            // Stock name cell (sticky)
            const nameTd = document.createElement('td');
            nameTd.className = 'stock-name' + (hasPos ? ' has-pos' : hasSignal ? ' has-signal' : '');
            nameTd.textContent = stock.replace('.CA', '');
            nameTd.title = stock + (hasPos ? ' — Open Position' : '');
            tr.appendChild(nameTd);

            // Historical date cells
            dates.forEach(d => {{
                const entry = stockData[d];
                const val   = entry ? (currentView === 'score' ? entry.score : entry.r1) : 0;
                const td    = document.createElement('td');
                td.style.padding = '1px';

                const cell = document.createElement('div');
                cell.className = 'hm-cell';
                cell.style.background = currentView === 'score' ? scoreColor(val) : r1Color(val);

                if (entry) {{
                    totalSignals++;
                    // Open-position dot
                    if (hasPos) {{
                        const dot = document.createElement('div');
                        dot.className = 'pos-marker';
                        cell.appendChild(dot);
                    }}
                    // Tooltip
                    cell.addEventListener('mouseenter', e => showTip(e, stock, d, entry, hasPos));
                    cell.addEventListener('mousemove',  e => moveTip(e));
                    cell.addEventListener('mouseleave', hideTip);
                }}
                td.appendChild(cell);
                tr.appendChild(td);
            }});

            // Today separator
            const sepTd = document.createElement('td'); sepTd.className = 'today-sep'; tr.appendChild(sepTd);

            // Today cell
            const tTd = document.createElement('td'); tTd.style.padding = '2px 0';
            const tVal  = currentView === 'score' ? (todayInfo.score || 0) : (todayInfo.r1 || 0);
            const tCell = document.createElement('div');
            tCell.className = 'today-cell';
            tCell.style.background = currentView === 'score' ? scoreColor(tVal) : r1Color(tVal);
            if (tVal >= 35) {{
                tCell.style.color = textForBg(tVal, currentView === 'r1');
                tCell.textContent = tVal;
            }} else {{
                tCell.style.color = '#484f58';
                tCell.textContent = tVal || '—';
            }}
            if (todayInfo.price) {{
                tCell.addEventListener('mouseenter', e => showTip(e, stock, TODAY,
                    {{score: todayInfo.score, r1: todayInfo.r1, price: todayInfo.price, signal: todayInfo.signal}}, hasPos));
                tCell.addEventListener('mousemove',  e => moveTip(e));
                tCell.addEventListener('mouseleave', hideTip);
            }}
            tTd.appendChild(tCell);
            tr.appendChild(tTd);
            table.appendChild(tr);
        }});
    }});
}}

// ── Tooltip ──────────────────────────────────────────────────────────────
const tip = document.getElementById('tooltip');
function showTip(e, stock, dt, entry, hasPos) {{
    const s = entry.score || 0;
    const r = entry.r1   || 0;
    const p = entry.price || 0;
    const sig = entry.signal || '—';
    const color = scoreColor(s);
    tip.innerHTML = `
      <div class="tt-stock">${{stock}}</div>
      <div style="font-size:10px;color:#8b949e;margin-bottom:6px">${{dt}}</div>
      <div class="tt-score" style="color:${{color}}">${{s}}</div>
      <div style="font-size:10px;color:#8b949e;margin-bottom:6px">SMC Score</div>
      <div class="tt-row"><span class="tt-label">Price</span><span class="tt-val">EGP ${{p.toFixed(2)}}</span></div>
      <div class="tt-row"><span class="tt-label">R1</span><span class="tt-val">${{r}}</span></div>
      <div class="tt-row"><span class="tt-label">Signal</span><span class="tt-val" style="color:${{color}}">${{sig}}</span></div>
      ${{hasPos ? '<div class="tt-pos">● Open Position</div>' : ''}}
    `;
    tip.style.display = 'block';
    moveTip(e);
}}
function moveTip(e) {{
    const x = e.clientX + 16;
    const y = e.clientY + 16;
    const tw = tip.offsetWidth, th = tip.offsetHeight;
    tip.style.left = (x + tw > window.innerWidth  ? e.clientX - tw - 8 : x) + 'px';
    tip.style.top  = (y + th > window.innerHeight ? e.clientY - th - 8 : y) + 'px';
}}
function hideTip() {{ tip.style.display = 'none'; }}

// ── Build positions summary ───────────────────────────────────────────────
function buildSummary() {{
    const el = document.getElementById('pos-summary');
    if (!OPEN_POS.size) {{ el.style.display = 'none'; return; }}
    el.innerHTML = '<div style="grid-column:1/-1;font-size:13px;font-weight:600;color:#8b949e;padding:0 0 8px;text-transform:uppercase;letter-spacing:.05em">Open Positions</div>';
    OPEN_POS.forEach(stock => {{
        const td  = TODAY_SC[stock] || {{}};
        const score = td.score || 0;
        const pct   = Math.min(score, 100);
        const card  = document.createElement('div');
        card.className = 'pos-card' + (score >= 35 ? ' has-signal' : '');
        card.innerHTML = `
          <div class="pc-ticker">${{stock}}</div>
          <div class="pc-level" style="margin-top:2px">Today Score: <strong style="color:${{scoreColor(score)}}">${{score || '—'}}</strong>
            &nbsp;|&nbsp; Signal: <strong>${{td.signal || '—'}}</strong>
            &nbsp;|&nbsp; EGP ${{(td.price || 0).toFixed(2)}}
          </div>
          <div class="pc-bar"><div class="pc-fill" style="width:${{pct}}%;background:${{scoreColor(score)}}"></div></div>
        `;
        el.appendChild(card);
    }});
}}

// ── Controls ──────────────────────────────────────────────────────────────
function setRange(r) {{
    currentRange = r;
    ['all','90','60','30'].forEach(x => document.getElementById('btn-'+x).classList.remove('active'));
    document.getElementById('btn-'+r).classList.add('active');
    buildHeatmap();
}}
function setView(v) {{
    currentView = v;
    ['score','r1'].forEach(x => document.getElementById('view-'+x).classList.remove('active'));
    document.getElementById('view-'+v).classList.add('active');
    buildHeatmap();
}}

// ── Init ──────────────────────────────────────────────────────────────────
buildLegend();
buildHeatmap();
buildSummary();
</script>
</body>
</html>
"""

out_path = os.path.join(BASE, 'heatmap.html')
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(HTML)

print(f"✅  Heatmap generated → {out_path}")
print(f"   Stocks with history : {len(stocks_with_history)}")
print(f"   Total signal dates  : {len(all_dates)} ({all_dates[0] if all_dates else '—'} → {all_dates[-1] if all_dates else '—'})")
print(f"   Open positions      : {open_count}")
