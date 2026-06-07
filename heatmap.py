#!/usr/bin/env python3
"""
heatmap.py — EGX SMC Signal Score Heatmap (interactive HTML).
Run: python heatmap.py  →  heatmap.html
"""

import json
import os
from datetime import date, datetime

BASE    = os.path.dirname(os.path.abspath(__file__))
WEB_OUT = os.environ.get('WEB_OUT', BASE)   # CI sets WEB_OUT=./web_deploy


def load(name):
    p = os.path.join(BASE, name)
    return json.load(open(p)) if os.path.exists(p) else {}


history      = load('signal_history.json')
scan_results = load('scan_results.json')
positions    = load('open_positions.json')

SECTORS = [
    ('Real Estate',  ['TMGH.CA', 'EMFD.CA', 'PHDC.CA', 'ORHD.CA', 'HELI.CA']),
    ('Industrial',   ['EAST.CA', 'ABUK.CA', 'ORAS.CA', 'EFID.CA', 'HRHO.CA',
                      'JUFO.CA', 'ARCC.CA', 'ORWE.CA', 'CCAP.CA']),
    ('Healthcare',   ['MCQE.CA', 'ISPH.CA', 'RMDA.CA']),
    ('Finance/Tech', ['FWRY.CA', 'EFIH.CA', 'RAYA.CA', 'BTFH.CA']),
    ('Banking',      ['COMI.CA', 'EGAL.CA', 'ADIB.CA']),
    ('Telecom/Auto', ['ETEL.CA', 'GBCO.CA', 'OIH.CA']),
]

today_str = date.today().isoformat()
all_dates = sorted({sig['date'] for sigs in history.values() for sig in sigs})
lookup    = {stock: {sig['date']: sig for sig in sigs}
             for stock, sigs in history.items()}

today_scores = {
    t: {'score':  d.get('score', 0), 'price':  d.get('price', 0),
        'signal': d.get('signal', '-'), 'r1': d.get('r1', 0)}
    for t, d in scan_results.items()
}

# ── Peak scores ───────────────────────────────────────────────────────────
peak_scores = {}
for stock, sigs in history.items():
    if sigs:
        pk = max(sigs, key=lambda s: s['score'])
        peak_scores[stock] = {'score': pk['score'], 'date': pk['date']}

# ── Position data with return % ───────────────────────────────────────────
pos_data = {}
for t, pos in positions.items():
    ep = pos.get('entry_price', 0)
    cp = scan_results.get(t, {}).get('price', 0)
    ret = round((cp - ep) / ep * 100, 1) if ep else 0
    pos_data[t] = {
        'entry_price':   ep,
        'entry_date':    pos.get('entry_date', '')[:10],
        'current_price': cp,
        'return_pct':    ret,
        'current_level': pos.get('current_level', 0),
        'fib_targets':   [round(x, 2) for x in pos.get('fib_targets', [])],
        'entry_score':   pos.get('entry_score', 0),
        'status':        pos.get('status', 'open'),
    }

rets     = [d['return_pct'] for d in pos_data.values()]
avg_ret  = round(sum(rets) / len(rets), 1) if rets else 0
best_ret = max((d['return_pct'] for d in pos_data.values()), default=0)
best_ret_ticker = next(
    (t for t, d in pos_data.items() if d['return_pct'] == best_ret), '—'
)

# ── Pending signals (signal = "Wait") ────────────────────────────────────
pending = [
    {'ticker': t, 'score': d.get('score', 0), 'price': d.get('price', 0),
     'signal': d.get('signal', '-'), 'r1': d.get('r1', 0)}
    for t, d in scan_results.items()
    if d.get('signal', '').lower() == 'wait'
]
pending.sort(key=lambda x: x['score'], reverse=True)

stocks_with_history = [s for s in history if history[s]]
max_score_stock = max(
    ((s, peak_scores[s]['score']) for s in peak_scores),
    key=lambda x: x[1], default=('—', 0)
)

# ── data.json — state snapshot for PWA change detection ──────────────────
data_snapshot = {
    'timestamp': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
    'pending':   pending,
    'open_count': len(positions),
    'avg_return': avg_ret,
    'positions': {
        t: {'level': d['current_level'], 'return_pct': d['return_pct']}
        for t, d in pos_data.items()
    },
}

# ── Serialise for JS ──────────────────────────────────────────────────────
def js(obj): return json.dumps(obj, ensure_ascii=False, separators=(',', ':'))


HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<meta name="theme-color" content="#161b22">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="SMC">
<link rel="manifest" href="./manifest.json">
<link rel="apple-touch-icon" href="./icon.svg">
<title>EGX SMC — Signal Score Heatmap</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0d1117;color:#c9d1d9;font-family:'Segoe UI',system-ui,sans-serif;font-size:13px;min-height:100vh}}

/* ── Header ───────────────────────────────── */
.header{{background:#161b22;border-bottom:1px solid #30363d;padding:14px 24px;display:flex;align-items:center;gap:12px;flex-wrap:wrap}}
.header h1{{font-size:17px;font-weight:600;color:#e6edf3;flex:1 0 auto}}
.badge{{background:#21262d;border:1px solid #30363d;border-radius:6px;padding:3px 10px;font-size:11px;color:#8b949e;white-space:nowrap}}
.badge.green{{border-color:#238636;color:#3fb950}}
.badge.yellow{{border-color:#9e6a03;color:#d29922}}
.badge.blue{{border-color:#1f6feb;color:#58a6ff}}
.badge.red{{border-color:#da3633;color:#f85149}}

/* ── Stats bar ────────────────────────────── */
.stats{{display:flex;gap:1px;background:#30363d;border-bottom:1px solid #30363d}}
.stat{{flex:1;background:#161b22;padding:10px 16px;text-align:center;min-width:0}}
.stat .val{{font-size:16px;font-weight:700;color:#e6edf3;line-height:1}}
.stat .val.pos{{color:#3fb950}}
.stat .val.neg{{color:#f85149}}
.stat .lbl{{font-size:10px;color:#8b949e;margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}

/* ── Controls ─────────────────────────────── */
.controls{{padding:10px 24px;display:flex;align-items:center;gap:10px;flex-wrap:wrap;background:#0d1117;border-bottom:1px solid #21262d}}
.ctrl-label{{font-size:10px;color:#8b949e;text-transform:uppercase;letter-spacing:.06em;white-space:nowrap}}
.btn-group{{display:flex;gap:3px}}
.btn{{background:#21262d;border:1px solid #30363d;border-radius:6px;padding:4px 11px;font-size:12px;color:#c9d1d9;cursor:pointer;transition:all .12s}}
.btn:hover{{background:#30363d;border-color:#8b949e}}
.btn.active{{background:#238636;border-color:#2ea043;color:#fff}}
.btn.active.ret{{background:#1f6feb;border-color:#388bfd}}
.btn.active.r1c{{background:#9e6a03;border-color:#d29922}}

/* ── Legend ───────────────────────────────── */
.legend{{padding:7px 24px;display:flex;align-items:center;gap:8px;flex-wrap:wrap;border-bottom:1px solid #21262d}}
.legend-text{{font-size:10px;color:#6e7681;white-space:nowrap}}
.leg-cells{{display:flex;gap:2px;align-items:center}}
.leg-cell{{width:18px;height:12px;border-radius:2px}}
.leg-sep{{width:12px;height:1px;background:#30363d;margin:0 4px}}
.ind{{display:flex;align-items:center;gap:4px;font-size:10px;color:#8b949e;margin-left:8px}}
.ind-dot{{width:7px;height:7px;border-radius:50%;flex-shrink:0}}
.pend-dot{{background:#d29922}}
.pos-dot{{background:#f78166}}

/* ── Heatmap ──────────────────────────────── */
.hm-outer{{overflow-x:auto;padding:20px 24px 12px}}
.hm-table{{border-collapse:collapse;white-space:nowrap}}
.sector-row td{{padding:10px 6px 3px;font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:#6e7681;font-weight:600;border:none!important}}
.stock-name{{position:sticky;left:0;z-index:2;background:#0d1117;padding:0 8px 0 0;text-align:right;font-size:11px;font-weight:500;width:82px;min-width:82px;cursor:default}}
.stock-name .sn-ticker{{display:block}}
.stock-name .sn-badge{{font-size:9px;color:#6e7681}}
.sn-open{{color:#f78166!important}}
.sn-pend{{color:#d29922!important}}
.sn-sig{{color:#3fb950!important}}

.hm-cell{{height:25px;border-radius:2px;cursor:pointer;position:relative;transition:transform .1s,outline .1s}}
.hm-cell:hover{{transform:scale(1.5);z-index:10;outline:2px solid #e6edf3}}
.pos-marker{{position:absolute;bottom:2px;right:1px;width:4px;height:4px;border-radius:50%;background:#f78166}}
.pend-marker{{position:absolute;bottom:2px;right:1px;width:4px;height:4px;border-radius:50%;background:#d29922}}

/* ── Today column ─────────────────────────── */
.today-sep{{width:6px}}
.today-cell{{width:70px;min-width:70px;height:25px;border-radius:4px;cursor:pointer;font-size:10px;font-weight:700;transition:transform .1s;display:flex;align-items:center;justify-content:center;overflow:hidden;white-space:nowrap}}
.today-cell:hover{{transform:scale(1.06);z-index:10;outline:2px solid #e6edf3}}
.date-header{{font-size:9px;color:#6e7681;text-align:center;padding:0;transform:rotate(-55deg) translateX(3px);transform-origin:center bottom;height:46px;vertical-align:bottom;width:17px}}
.today-header{{font-size:9px;color:#3fb950;font-weight:700;text-align:center;vertical-align:bottom;padding-bottom:4px;letter-spacing:.03em}}

/* ── Tooltip ──────────────────────────────── */
#tooltip{{position:fixed;pointer-events:none;background:#1c2128;border:1px solid #30363d;border-radius:8px;padding:10px 13px;font-size:12px;line-height:1.5;z-index:9999;min-width:170px;max-width:260px;box-shadow:0 8px 24px #0009;display:none}}
.tt-head{{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:6px}}
.tt-ticker{{font-size:14px;font-weight:700;color:#e6edf3}}
.tt-date{{font-size:10px;color:#8b949e;text-align:right}}
.tt-score-big{{font-size:26px;font-weight:800;line-height:1}}
.tt-score-lbl{{font-size:10px;color:#8b949e;margin-bottom:6px}}
.tt-divider{{border:none;border-top:1px solid #30363d;margin:6px 0}}
.tt-row{{display:flex;justify-content:space-between;gap:12px;font-size:11px}}
.tt-lbl{{color:#8b949e}}
.tt-val{{color:#e6edf3;font-weight:600;text-align:right}}
.tt-tag{{font-size:10px;margin-top:5px;padding:2px 7px;border-radius:4px;display:inline-block}}
.tt-open{{background:#21262d;color:#f78166;border:1px solid #f7816633}}
.tt-pend{{background:#21262d;color:#d29922;border:1px solid #d2992233}}
.tt-peak{{background:#21262d;color:#58a6ff;border:1px solid #388bfd33}}

/* ── Bottom panels ────────────────────────── */
.panels{{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:#30363d;border-top:1px solid #30363d}}
.panel{{background:#0d1117;padding:20px 24px}}
.panel-title{{font-size:11px;font-weight:600;color:#8b949e;text-transform:uppercase;letter-spacing:.06em;margin-bottom:12px;display:flex;align-items:center;gap:8px}}
.panel-title .cnt{{background:#21262d;border:1px solid #30363d;border-radius:10px;padding:1px 8px;font-size:10px;color:#c9d1d9;font-weight:700}}

/* Position cards */
.pos-cards{{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:10px}}
.pos-card{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:11px 14px;cursor:default;transition:border-color .15s}}
.pos-card:hover{{border-color:#58a6ff44}}
.pc-top{{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:6px}}
.pc-ticker{{font-size:13px;font-weight:700;color:#e6edf3}}
.pc-ret{{font-size:14px;font-weight:800}}
.pc-ret.pos{{color:#3fb950}}
.pc-ret.neg{{color:#f85149}}
.pc-meta{{font-size:10px;color:#8b949e;display:flex;gap:8px;margin-bottom:6px;flex-wrap:wrap}}
.pc-meta span{{white-space:nowrap}}
.pc-fib{{display:flex;gap:2px;margin-top:4px}}
.pc-fib-cell{{flex:1;height:5px;border-radius:1px}}

/* Pending cards */
.pend-cards{{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:8px}}
.pend-card{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:10px 13px}}
.pend-card:hover{{border-color:#d2992233}}
.pend-top{{display:flex;justify-content:space-between;align-items:center;margin-bottom:4px}}
.pend-ticker{{font-size:13px;font-weight:700;color:#e6edf3}}
.pend-score{{font-size:16px;font-weight:800}}
.pend-meta{{font-size:10px;color:#8b949e}}
.empty-state{{color:#6e7681;font-size:12px;font-style:italic;padding:8px 0}}

@media(max-width:700px){{
  .panels{{grid-template-columns:1fr}}
  .stats .lbl{{font-size:9px}}
}}
</style>
</head>
<body>

<!-- ── Header ──────────────────────────────────────────────────────── -->
<div class="header">
  <h1>EGX SMC — Signal Score Heatmap</h1>
  <span class="badge green">Generated: {today_str}</span>
  <span class="badge yellow">{len(positions)} Open Positions</span>
  <span class="badge">EGX · Cairo Time</span>
  <button id="btn-install" style="display:none;align-items:center;gap:6px;background:#238636;border:1px solid #2ea043;border-radius:6px;padding:5px 12px;font-size:12px;color:#fff;cursor:pointer">
    ＋ Install App
  </button>
</div>

<!-- ── Stats bar ───────────────────────────────────────────────────── -->
<div class="stats">
  <div class="stat">
    <div class="val" id="pend-stat-val">{len(pending)}</div>
    <div class="lbl">Pending Signals</div>
  </div>
  <div class="stat">
    <div class="val">{len(positions)}</div>
    <div class="lbl">Open Positions</div>
  </div>
  <div class="stat">
    <div class="val {'pos' if avg_ret >= 0 else 'neg'}" id="avg-ret-val">{'+' if avg_ret >= 0 else ''}{avg_ret}%</div>
    <div class="lbl">Avg Return</div>
  </div>
  <div class="stat">
    <div class="val pos" id="best-ret-val">+{best_ret}%</div>
    <div class="lbl">Best Return ({best_ret_ticker.replace('.CA','')})</div>
  </div>
</div>

<!-- ── Controls ────────────────────────────────────────────────────── -->
<div class="controls">
  <span class="ctrl-label">Range</span>
  <div class="btn-group">
    <button class="btn" id="btn-all" onclick="setRange('all')">All</button>
    <button class="btn active" id="btn-90" onclick="setRange(90)">90d</button>
    <button class="btn" id="btn-60" onclick="setRange(60)">60d</button>
    <button class="btn" id="btn-30" onclick="setRange(30)">30d</button>
  </div>
  <span id="days-count" style="font-size:10px;color:#6e7681;margin-left:4px"></span>
  <span class="ctrl-label" style="margin-left:8px">View</span>
  <div class="btn-group">
    <button class="btn active" id="view-score"  onclick="setView('score')">Score</button>
    <button class="btn ret"    id="view-return" onclick="setView('return')">Return %</button>
  </div>
</div>

<!-- ── Legend ──────────────────────────────────────────────────────── -->
<div class="legend" id="legend-bar">
  <span class="legend-text" id="leg-label">Score:</span>
  <div class="leg-cells" id="leg-cells"></div>
  <span class="legend-text" id="leg-range">35 → 100</span>
  <div class="leg-sep"></div>
  <div class="ind"><div class="ind-dot pos-dot"></div><span>Open Position</span></div>
  <div class="ind"><div class="ind-dot pend-dot"></div><span>Pending Signal</span></div>
</div>

<!-- ── Heatmap ─────────────────────────────────────────────────────── -->
<div class="hm-outer">
  <table class="hm-table" id="hm-table"></table>
</div>

<!-- ── Bottom panels ───────────────────────────────────────────────── -->
<div class="panels">
  <div class="panel">
    <div class="panel-title">Open Positions <span class="cnt" id="op-cnt">{len(positions)}</span></div>
    <div class="pos-cards" id="pos-cards"></div>
  </div>
  <div class="panel">
    <div class="panel-title">Pending Signals <span class="cnt" id="pend-cnt">{len(pending)}</span></div>
    <div class="pend-cards" id="pend-cards"></div>
  </div>
</div>

<!-- ── Tooltip ─────────────────────────────────────────────────────── -->
<div id="tooltip"></div>

<script>
// ── Embedded data ────────────────────────────────────────────────────────
const HISTORY   = {js(lookup)};
const TODAY_SC  = {js(today_scores)};
const ALL_DATES = {js(all_dates)};
const OPEN_POS  = new Set({js(list(positions.keys()))});
const PENDING   = new Set({js([p['ticker'] for p in pending])});
const POS_DATA  = {js(pos_data)};
const PEAK      = {js(peak_scores)};
const SECTORS   = {js(SECTORS)};
const PENDING_LIST = {js(pending)};
const TODAY     = {js(today_str)};

let currentRange = 90;
let currentView  = 'score';

// ── Color helpers ─────────────────────────────────────────────────────────
function scoreColor(v) {{
    if (!v || v < 35) return '#1c2128';
    const t = Math.min((v - 35) / 65, 1);
    return `rgb(${{r(27,64,t)}},${{r(58,210,t)}},${{r(46,100,t)}})`;
}}
function r1Color(v) {{
    if (!v || v < 12) return '#1c2128';
    const t = Math.min((v - 12) / 20, 1);
    return `rgb(${{r(80,220,t)}},${{r(55,160,t)}},${{r(15,40,t)}})`;
}}
function returnColor(pct) {{
    if (pct === null || pct === undefined) return '#1c2128';
    if (pct >= 0) {{
        const t = Math.min(pct / 100, 1);
        return `rgb(${{r(27,64,t)}},${{r(58,210,t)}},${{r(46,100,t)}})`;
    }}
    const t = Math.min(-pct / 30, 1);
    return `rgb(${{r(80,220,t)}},${{r(30,40,t)}},${{r(30,40,t)}})`;
}}
function r(a,b,t) {{ return Math.round(a + t*(b-a)); }}
function darkText(t) {{ return t > 0.6 ? '#0d1117' : '#8b949e'; }}
function scoreTextColor(v) {{ return darkText(Math.min((v-35)/65,1)); }}
function retTextColor(pct) {{
    if (pct >= 0) return darkText(Math.min(pct/100,1));
    return darkText(Math.min(-pct/30,1));
}}

// ── Current view color ────────────────────────────────────────────────────
function cellColor(stock, entry, dateStr) {{
    if (!entry) return '#1c2128';
    if (currentView === 'score')  return scoreColor(entry.score);
    if (currentView === 'r1')     return r1Color(entry.r1);
    // return view
    const pd = POS_DATA[stock];
    if (!pd) return '#1c2128';
    if (dateStr < pd.entry_date) return '#1c2128';
    return returnColor((entry.price - pd.entry_price) / pd.entry_price * 100);
}}
function todayColor(stock) {{
    const td = TODAY_SC[stock] || {{}};
    if (currentView === 'score')  return scoreColor(td.score);
    if (currentView === 'r1')     return r1Color(td.r1);
    const pd = POS_DATA[stock];
    if (!pd) return '#1c2128';
    return returnColor(pd.return_pct);
}}
function todayLabel(stock) {{
    const td = TODAY_SC[stock] || {{}};
    if (currentView === 'score')  return td.score || '—';
    if (currentView === 'r1')     return td.r1    || '—';
    const pd = POS_DATA[stock];
    if (!pd) return '—';
    return (pd.return_pct >= 0 ? '+' : '') + pd.return_pct + '%';
}}
function todayLabelColor(stock) {{
    const td = TODAY_SC[stock] || {{}};
    if (currentView === 'score') {{
        const s = td.score || 0;
        return s >= 35 ? scoreTextColor(s) : '#484f58';
    }}
    if (currentView === 'r1') {{
        const rv = td.r1 || 0;
        return rv >= 12 ? darkText(Math.min((rv-12)/20,1)) : '#484f58';
    }}
    const pd = POS_DATA[stock];
    if (!pd) return '#484f58';
    return retTextColor(pd.return_pct);
}}

// ── Date filter ───────────────────────────────────────────────────────────
function filteredDates() {{
    if (currentRange === 'all') return ALL_DATES;
    const d = new Date(TODAY);
    d.setDate(d.getDate() - currentRange);
    const cut = d.toISOString().slice(0,10);
    return ALL_DATES.filter(x => x >= cut);
}}

// ── Legend ────────────────────────────────────────────────────────────────
function buildLegend() {{
    const cells = document.getElementById('leg-cells');
    const lbl   = document.getElementById('leg-label');
    const rng   = document.getElementById('leg-range');
    cells.innerHTML = '';
    let steps, colorFn, label, range;
    if (currentView === 'score') {{
        steps = [0,35,45,55,65,75,85,95]; colorFn = v => v===0?'#1c2128':scoreColor(v);
        label = 'Score:'; range = '35 → 100';
    }} else if (currentView === 'r1') {{
        steps = [0,12,16,20,24,28]; colorFn = v => v===0?'#1c2128':r1Color(v);
        label = 'R1:'; range = '12 → 30';
    }} else {{
        steps = [-30,-20,-10,0,10,25,50,80]; colorFn = v => v===0?'#21262d':returnColor(v);
        label = 'Return:'; range = '-30% → +80%';
    }}
    lbl.textContent = label; rng.textContent = range;
    steps.forEach(v => {{
        const d = document.createElement('div');
        d.className = 'leg-cell';
        d.style.background = colorFn(v);
        d.title = currentView==='return' ? (v>0?'+':'')+v+'%' : (v===0?'No data':'≥'+v);
        cells.appendChild(d);
    }});
}}

// ── Dynamic cell width based on available space ───────────────────────────
function calcCellW(numDates) {{
    const available = (window.innerWidth || 800) - 82 - 76 - 56;
    const ideal = Math.floor(available / numDates);
    return Math.max(14, Math.min(ideal, 48));
}}

// ── Heatmap ───────────────────────────────────────────────────────────────
function buildHeatmap() {{
    const dates = filteredDates();
    const CW    = calcCellW(dates.length);
    const tbl   = document.getElementById('hm-table');
    tbl.innerHTML = '';

    // Header row
    const hRow = document.createElement('tr');
    const corner = document.createElement('td');
    corner.style.cssText = 'width:82px;min-width:82px';
    hRow.appendChild(corner);
    dates.forEach((d, i) => {{
        const prev  = dates[i-1] || '';
        const th    = document.createElement('td');
        th.className = 'date-header';
        th.style.width = CW + 'px';
        if (d.slice(0,7) !== prev.slice(0,7) || i===0 || CW >= 22) {{
            th.textContent = d.slice(5);
        }}
        hRow.appendChild(th);
    }});
    document.getElementById('days-count').textContent = `(${{dates.length}} days)`;
    const sep0 = document.createElement('td'); sep0.className='today-sep'; hRow.appendChild(sep0);
    const thToday = document.createElement('td'); thToday.className='today-header'; thToday.textContent='TODAY'; hRow.appendChild(thToday);
    tbl.appendChild(hRow);

    SECTORS.forEach(([sector, stocks]) => {{
        // Sector label
        const sr = document.createElement('tr');
        sr.className = 'sector-row';
        const sTd = document.createElement('td');
        sTd.setAttribute('colspan', dates.length + 3);
        sTd.textContent = sector;
        sr.appendChild(sTd);
        tbl.appendChild(sr);

        stocks.forEach(stock => {{
            const stockData = HISTORY[stock] || {{}};
            const hasPos    = OPEN_POS.has(stock);
            const isPend    = PENDING.has(stock);
            const todayInfo = TODAY_SC[stock] || {{}};

            const tr = document.createElement('tr');

            // Stock name (sticky)
            const nameTd = document.createElement('td');
            nameTd.className = 'stock-name';
            const ticker = stock.replace('.CA','');
            let badgeText = '';
            let cls = '';
            if (hasPos)   {{ cls = 'sn-open'; badgeText = 'open'; }}
            else if (isPend) {{ cls = 'sn-pend'; badgeText = 'pending'; }}
            else if ((todayInfo.score||0) >= 35) {{ cls = 'sn-sig'; badgeText = 'signal'; }}
            nameTd.innerHTML = `<span class="sn-ticker ${{cls}}">${{ticker}}</span>${{badgeText?`<span class="sn-badge">${{badgeText}}</span>`:''}}`;
            nameTd.title = stock;
            tr.appendChild(nameTd);

            // Date cells
            dates.forEach(d => {{
                const entry = stockData[d];
                const td    = document.createElement('td');
                td.style.padding = '1px';
                const cell  = document.createElement('div');
                cell.className = 'hm-cell';
                cell.style.width  = CW + 'px';
                cell.style.background = cellColor(stock, entry, d);

                if (entry) {{
                    if (hasPos) {{ const dot=document.createElement('div'); dot.className='pos-marker'; cell.appendChild(dot); }}
                    else if (isPend) {{ const dot=document.createElement('div'); dot.className='pend-marker'; cell.appendChild(dot); }}
                    cell.addEventListener('mouseenter', e => showTip(e, stock, d, entry, hasPos, isPend));
                    cell.addEventListener('mousemove',  e => moveTip(e));
                    cell.addEventListener('mouseleave', hideTip);
                }}
                td.appendChild(cell); tr.appendChild(td);
            }});

            // Today separator
            const sep = document.createElement('td'); sep.className='today-sep'; tr.appendChild(sep);

            // Today cell
            const tTd = document.createElement('td'); tTd.style.padding='2px 0';
            const bg  = todayColor(stock);
            const lbl = todayLabel(stock);
            const fg  = todayLabelColor(stock);
            const tCell = document.createElement('div');
            tCell.className = 'today-cell';
            tCell.style.cssText = `background:${{bg}};color:${{fg}}`;
            tCell.textContent = lbl;
            if (hasPos || (todayInfo.score||0) >= 35 || POS_DATA[stock]) {{
                tCell.addEventListener('mouseenter', e => showTip(e, stock, TODAY,
                    {{score:todayInfo.score,r1:todayInfo.r1,price:todayInfo.price,signal:todayInfo.signal}},
                    hasPos, isPend));
                tCell.addEventListener('mousemove',  e => moveTip(e));
                tCell.addEventListener('mouseleave', hideTip);
            }}
            tTd.appendChild(tCell); tr.appendChild(tTd);
            tbl.appendChild(tr);
        }});
    }});
}}

// ── Tooltip ───────────────────────────────────────────────────────────────
const tip = document.getElementById('tooltip');

function showTip(e, stock, dt, entry, hasPos, isPend) {{
    const s   = entry.score || 0;
    const rv  = entry.r1    || 0;
    const p   = entry.price || 0;
    const sig = entry.signal || '—';
    const sc  = scoreColor(s);
    const pd  = POS_DATA[stock];
    const pk  = PEAK[stock];

    let retRow = '';
    if (pd) {{
        const ret = dt === TODAY
            ? pd.return_pct
            : p && pd.entry_price ? ((p - pd.entry_price) / pd.entry_price * 100) : null;
        if (ret !== null) {{
            const retStr = (ret>=0?'+':'')+ret.toFixed(1)+'%';
            const retC   = returnColor(ret);
            retRow = `<div class="tt-row"><span class="tt-lbl">Return</span><span class="tt-val" style="color:${{retC}}">${{retStr}}</span></div>`;
        }}
    }}

    let posBlock = '';
    if (pd) {{
        const lvl  = pd.current_level;
        const nxt  = pd.fib_targets[lvl] ?? '—';
        const ep   = pd.entry_price;
        posBlock = `
          <hr class="tt-divider">
          <div class="tt-row"><span class="tt-lbl">Entry</span><span class="tt-val">EGP ${{ep.toFixed(2)}} (${{pd.entry_date}})</span></div>
          <div class="tt-row"><span class="tt-lbl">Level</span><span class="tt-val">${{lvl+1}} / 8</span></div>
          <div class="tt-row"><span class="tt-lbl">Next Target</span><span class="tt-val">EGP ${{typeof nxt==='number'?nxt.toFixed(2):nxt}}</span></div>`;
    }}

    let peakBlock = '';
    if (pk) {{
        peakBlock = `<span class="tt-tag tt-peak">Peak: ${{pk.score}} on ${{pk.date}}</span>`;
    }}
    let tagBlock = '';
    if (hasPos)  tagBlock += `<span class="tt-tag tt-open">● Open Position</span> `;
    if (isPend)  tagBlock += `<span class="tt-tag tt-pend">⚡ Pending Signal</span> `;

    tip.innerHTML = `
      <div class="tt-head">
        <div>
          <div class="tt-ticker">${{stock}}</div>
          <div style="font-size:10px;color:#8b949e">${{dt}}</div>
        </div>
        <div style="text-align:right">
          <div class="tt-score-big" style="color:${{sc}}">${{s||'—'}}</div>
          <div class="tt-score-lbl">SMC Score</div>
        </div>
      </div>
      <div class="tt-row"><span class="tt-lbl">Price</span><span class="tt-val">EGP ${{p.toFixed(2)}}</span></div>
      <div class="tt-row"><span class="tt-lbl">R1</span><span class="tt-val">${{rv}}</span></div>
      <div class="tt-row"><span class="tt-lbl">Signal</span><span class="tt-val" style="color:${{sc}}">${{sig}}</span></div>
      ${{retRow}}
      ${{posBlock}}
      ${{tagBlock || peakBlock ? `<hr class="tt-divider"><div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:2px">${{tagBlock}}${{peakBlock}}</div>` : ''}}
    `;
    tip.style.display = 'block';
    moveTip(e);
}}
function moveTip(e) {{
    const x=e.clientX+16, y=e.clientY+16;
    const tw=tip.offsetWidth, th=tip.offsetHeight;
    tip.style.left=(x+tw>innerWidth  ? e.clientX-tw-8 : x)+'px';
    tip.style.top =(y+th>innerHeight ? e.clientY-th-8 : y)+'px';
}}
function hideTip() {{ tip.style.display='none'; }}

// ── Open Positions cards ──────────────────────────────────────────────────
function buildPositions() {{
    const el = document.getElementById('pos-cards');
    el.innerHTML = '';
    if (!OPEN_POS.size) {{ el.innerHTML='<div class="empty-state">No open positions.</div>'; return; }}

    // sort by return desc
    const sorted = [...OPEN_POS].map(t => ({{t, ...POS_DATA[t]}}))
        .sort((a,b) => (b.return_pct||0)-(a.return_pct||0));

    sorted.forEach(pd => {{
        if (!pd) return;
        const s  = TODAY_SC[pd.t] || {{}};
        const ret = pd.return_pct;
        const retStr = (ret>=0?'+':'')+ret+'%';
        const retCls = ret>=0 ? 'pos' : 'neg';
        const sc = scoreColor(s.score||0);
        const lvl = pd.current_level;
        // Fibonacci progress cells (8 levels)
        let fibCells = '';
        for (let i=0;i<8;i++) {{
            const filled = i < lvl;
            const current = i === lvl;
            const bg = filled ? '#3fb950' : current ? '#58a6ff' : '#21262d';
            fibCells += `<div class="pc-fib-cell" style="background:${{bg}}" title="Target ${{i+1}}: EGP ${{pd.fib_targets[i]?.toFixed(2)||'?'}}"></div>`;
        }}
        const card = document.createElement('div');
        card.className = 'pos-card';
        card.innerHTML = `
          <div class="pc-top">
            <div class="pc-ticker">${{pd.t}}</div>
            <div class="pc-ret ${{retCls}}">${{retStr}}</div>
          </div>
          <div class="pc-meta">
            <span>Entry EGP ${{pd.entry_price.toFixed(2)}}</span>
            <span>Now EGP ${{pd.current_price.toFixed(2)}}</span>
            <span>Lvl ${{lvl+1}}/8</span>
            <span style="color:${{sc}}">Score ${{s.score||'—'}}</span>
          </div>
          <div class="pc-fib">${{fibCells}}</div>
        `;
        el.appendChild(card);
    }});
}}

// ── Pending cards ─────────────────────────────────────────────────────────
function buildPending() {{
    const el = document.getElementById('pend-cards');
    el.innerHTML = '';
    if (!PENDING_LIST.length) {{
        el.innerHTML = '<div class="empty-state">No new pending signals right now.</div>';
        return;
    }}
    PENDING_LIST.forEach(p => {{
        const sc = scoreColor(p.score);
        const card = document.createElement('div');
        card.className = 'pend-card';
        card.innerHTML = `
          <div class="pend-top">
            <div class="pend-ticker">${{p.ticker}}</div>
            <div class="pend-score" style="color:${{sc}}">${{p.score}}</div>
          </div>
          <div class="pend-meta">
            EGP ${{p.price.toFixed(2)}} &nbsp;·&nbsp; R1: ${{p.r1}} &nbsp;·&nbsp;
            <span style="color:${{sc}}">${{p.signal}}</span>
          </div>
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
    document.querySelector('.hm-outer').scrollLeft = 0;
}}
function setView(v) {{
    currentView = v;
    ['score','return'].forEach(x => document.getElementById('view-'+x).classList.remove('active'));
    document.getElementById('view-'+v).classList.add('active');
    buildLegend();
    buildHeatmap();
}}

// ── Init ──────────────────────────────────────────────────────────────────
buildLegend();
buildHeatmap();
buildPositions();
buildPending();

// ── PWA: Service Worker registration ──────────────────────────────────────
if ('serviceWorker' in navigator) {{
    navigator.serviceWorker.register('./sw.js').catch(() => {{}});
}}

// ── iOS: Show "Add to Home Screen" banner ────────────────────────────────
const isIOS = /iphone|ipad|ipod/i.test(navigator.userAgent);
const isInStandalone = window.navigator.standalone === true;
if (isIOS && !isInStandalone && !localStorage.getItem('ios_banner_dismissed')) {{
    const banner = document.createElement('div');
    banner.id = 'ios-banner';
    banner.style.cssText = `
        position:fixed;bottom:0;left:0;right:0;z-index:9999;
        background:#161b22;border-top:1px solid #30363d;
        padding:14px 20px;display:flex;align-items:center;gap:12px;
        box-shadow:0 -4px 20px #0009;
    `;
    banner.innerHTML = `
        <img src="./icon.svg" style="width:36px;height:36px;border-radius:8px;flex-shrink:0">
        <div style="flex:1;min-width:0">
            <div style="font-size:13px;font-weight:600;color:#e6edf3">Install EGX SMC App</div>
            <div style="font-size:11px;color:#8b949e;margin-top:2px">
                Tap <strong style="color:#c9d1d9">Share</strong>
                <span style="font-size:14px">⎋</span> then
                <strong style="color:#c9d1d9">Add to Home Screen</strong>
            </div>
        </div>
        <button onclick="localStorage.setItem('ios_banner_dismissed','1');document.getElementById('ios-banner').remove()"
            style="background:none;border:none;color:#8b949e;font-size:20px;cursor:pointer;padding:4px;flex-shrink:0">✕</button>
    `;
    document.body.appendChild(banner);
}}

// ── PWA: Install prompt ────────────────────────────────────────────────────
let _deferredPrompt = null;
window.addEventListener('beforeinstallprompt', e => {{
    e.preventDefault();
    _deferredPrompt = e;
    document.getElementById('btn-install').style.display = 'inline-flex';
}});
document.getElementById('btn-install').addEventListener('click', async () => {{
    if (!_deferredPrompt) return;
    _deferredPrompt.prompt();
    const {{ outcome }} = await _deferredPrompt.userChoice;
    if (outcome === 'accepted') document.getElementById('btn-install').style.display = 'none';
    _deferredPrompt = null;
}});
window.addEventListener('appinstalled', () => {{
    document.getElementById('btn-install').style.display = 'none';
}});

// ── PWA: Change detection + Notifications ─────────────────────────────────
const DATA_URL = './data.json';
const STORE_KEY = 'egx_smc_state';

async function checkChanges() {{
    try {{
        const res = await fetch(DATA_URL + '?t=' + Date.now());
        if (!res.ok) return;
        const curr = await res.json();
        const prev = JSON.parse(localStorage.getItem(STORE_KEY) || 'null');
        localStorage.setItem(STORE_KEY, JSON.stringify(curr));
        if (!prev) return;   // first visit — nothing to compare

        const alerts = [];

        // New pending signals
        const prevTickers = new Set((prev.pending || []).map(p => p.ticker));
        (curr.pending || []).forEach(p => {{
            if (!prevTickers.has(p.ticker))
                alerts.push(`⏳ ${{p.ticker}} — Wait (score ${{p.score}})`);
        }});

        // Fibonacci level advances
        Object.entries(curr.positions || {{}}).forEach(([t, d]) => {{
            const pd = (prev.positions || {{}})[t];
            if (pd && d.level > pd.level)
                alerts.push(`🎯 ${{t}} hit Target ${{d.level + 1}}/8 (+${{d.return_pct}}%)`);
        }});

        // New open position
        const prevOpen = new Set(Object.keys(prev.positions || {{}}));
        Object.keys(curr.positions || {{}}).forEach(t => {{
            if (!prevOpen.has(t))
                alerts.push(`🟢 New position opened: ${{t}}`);
        }});

        if (alerts.length && Notification.permission === 'granted') {{
            alerts.forEach(msg => {{
                new Notification('EGX SMC Alert', {{
                    body: msg,
                    icon: './icon.svg',
                    badge: './icon.svg',
                    tag: msg,
                }});
            }});
        }}
    }} catch(e) {{}}
}}

async function initNotifications() {{
    if (!('Notification' in window)) return;
    if (Notification.permission === 'default') {{
        await Notification.requestPermission();
    }}
    checkChanges();
    setInterval(checkChanges, 5 * 60 * 1000);   // re-check every 5 min
}}

window.addEventListener('load', () => setTimeout(initNotifications, 1500));
</script>
</body>
</html>
"""

os.makedirs(WEB_OUT, exist_ok=True)

# Write heatmap.html
html_path = os.path.join(WEB_OUT, 'heatmap.html')
with open(html_path, 'w', encoding='utf-8') as f:
    f.write(HTML)

# Write data.json
data_path = os.path.join(WEB_OUT, 'data.json')
with open(data_path, 'w', encoding='utf-8') as f:
    json.dump(data_snapshot, f, ensure_ascii=False, separators=(',', ':'))

# Also write heatmap.html locally if WEB_OUT differs (for local preview)
if WEB_OUT != BASE:
    with open(os.path.join(BASE, 'heatmap.html'), 'w', encoding='utf-8') as f:
        f.write(HTML)

print(f"✅  heatmap.html  ({os.path.getsize(html_path)//1024} KB)")
print(f"   Stocks w/ history : {len(stocks_with_history)}")
print(f"   Date range         : {all_dates[0] if all_dates else '—'} → {all_dates[-1] if all_dates else '—'} ({len(all_dates)} days)")
print(f"   Open positions     : {len(positions)}  avg return: {avg_ret:+.1f}%")
print(f"   Pending signals    : {len(pending)}")
print(f"   Peak score         : {max_score_stock[1]} ({max_score_stock[0]})")
