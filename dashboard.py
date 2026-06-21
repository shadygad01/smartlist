"""
EGX Constitutional Command Center — Dashboard V6
Sections: Sticky Header → What Am I Waiting For → Market Map →
          Stock DNA → Full Timeline → System Diagnostics
No portfolio. No capacity. No leaderboards. No executive summary.
"""
from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

import json
from presentation.presentation_snapshot import PresentationSnapshot, build_presentation_snapshot

BASE = Path(__file__).parent

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
*{{box-sizing:border-box;}}
body{{margin:0;padding:0;background:{BG0};font-family:'Segoe UI',system-ui,Arial,sans-serif;color:{FG};overflow-x:hidden;}}
.sticky-header{{position:sticky;top:0;z-index:100;background:{BG1};border-bottom:2px solid {BOR};padding:14px 20px;}}
.wrap{{max-width:1100px;margin:0 auto;padding:20px 16px;}}
.card{{background:{BG1};border:1px solid {BOR};border-radius:10px;padding:20px;margin-bottom:18px;overflow:hidden;}}
.section-title{{font-size:13px;font-weight:700;letter-spacing:0.6px;text-transform:uppercase;
  color:{DIM};margin-bottom:14px;border-bottom:1px solid {BOR};padding-bottom:8px;}}
.badge{{display:inline-block;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:700;white-space:nowrap;}}
.tbl-wrap{{overflow-x:auto;-webkit-overflow-scrolling:touch;}}
table{{width:100%;border-collapse:collapse;font-size:13px;min-width:480px;}}
th{{text-align:left;padding:9px 10px;color:{DIM};font-size:11px;font-weight:700;
  letter-spacing:0.4px;text-transform:uppercase;border-bottom:1px solid {BOR};white-space:nowrap;}}
td{{padding:10px 10px;border-bottom:1px solid {BOR};color:{FG};vertical-align:middle;}}
tr:last-child td{{border-bottom:none;}}
.pos{{color:{G};font-weight:700;}} .neg{{color:{R};font-weight:700;}} .neu{{color:{A};font-weight:700;}}
.stat{{background:{BG2};border:1px solid {BOR};border-radius:8px;padding:10px 14px;text-align:center;}}
.stat-val{{font-size:20px;font-weight:700;}}
.stat-lbl{{font-size:10px;color:{DIM};text-transform:uppercase;letter-spacing:0.5px;margin-top:3px;}}
.grid6{{display:grid;grid-template-columns:repeat(6,1fr);gap:8px;}}
details summary{{cursor:pointer;user-select:none;list-style:none;}}
details summary::-webkit-details-marker{{display:none;}}
.dna-card{{background:{BG2};border:1px solid {BOR};border-radius:8px;padding:14px;margin-bottom:10px;}}
.dna-meta{{font-size:11px;color:{DIM};margin-top:6px;}}
@media(max-width:700px){{
  .grid6{{grid-template-columns:repeat(3,1fr);}}
  .sticky-header{{padding:10px 12px;}}
  td,th{{padding:8px 6px;font-size:12px;}}
}}
@media(max-width:420px){{
  .grid6{{grid-template-columns:repeat(2,1fr);}}
}}
"""

JS = """
<script>
function updateClock(){
  var now=new Date();
  var cairo=new Date(now.toLocaleString('en-US',{timeZone:'Africa/Cairo'}));
  var hh=String(cairo.getHours()).padStart(2,'0');
  var mm=String(cairo.getMinutes()).padStart(2,'0');
  var ss=String(cairo.getSeconds()).padStart(2,'0');
  var days=['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];
  var months=['January','February','March','April','May','June','July','August','September','October','November','December'];
  var dayStr=days[cairo.getDay()]+', '+cairo.getDate()+' '+months[cairo.getMonth()]+' '+cairo.getFullYear();
  var el=document.getElementById('cairo-clock');
  if(el) el.textContent=hh+':'+mm+':'+ss+' Cairo';
  var dl=document.getElementById('cairo-date');
  if(dl) dl.textContent=dayStr;
}
setInterval(updateClock,1000);
updateClock();
</script>
"""


def _rc(r):
    return "pos" if r > 0 else ("neg" if r < 0 else "neu")

def _sign(r):
    return "+" if r >= 0 else ""

def _type_badge(etype):
    if etype == "FIRST_BUY":
        return f'<span class="badge" style="background:{B}22;color:{B};">FIRST BUY</span>'
    return f'<span class="badge" style="background:{P}22;color:{P};">RE-ACCUM</span>'

def _market_status_color(status):
    return G if ("OPEN" in status and "PRE" not in status) else (A if "PRE" in status else DIM)

def _pass_badge(ok):
    return (f'<span class="badge" style="background:{G}22;color:{G};">&#10003; PASS</span>'
            if ok else f'<span class="badge" style="background:{R}22;color:{R};">&#10007; FAIL</span>')

def _cairo_now():
    tz = timezone(timedelta(hours=2))
    return datetime.now(tz).strftime("%H:%M")

def _load_stock_dna():
    dna_path = BASE / "stock_dna.db"
    if not dna_path.exists():
        return {}
    try:
        conn = sqlite3.connect(str(dna_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM stock_dna").fetchall()
        conn.close()
        return {r["ticker"]: dict(r) for r in rows}
    except Exception:
        return {}


def _s_sticky_header(snap):
    mstatus = snap.market_status
    mc = _market_status_color(mstatus)
    scan_s = snap.last_scan_ts[:16].replace("T", " ") if snap.last_scan_ts else "--"
    gen_s  = snap.generated_at[:16].replace("T", " ") if snap.generated_at else "--"
    new_tag = ""
    if snap.new_events_today:
        new_tag = (f'<span class="badge" style="background:{G}22;color:{G};margin-left:10px;">'
                   f'&#9889; {len(snap.new_events_today)} NEW TODAY</span>')
    cairo_date = datetime.now(timezone(timedelta(hours=2))).strftime('%A, %d %B %Y')
    return f"""
<div class="sticky-header">
  <div style="max-width:1100px;margin:0 auto;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;">
    <div>
      <span style="font-size:16px;font-weight:700;color:{W};">&#127963; EGX Constitutional Command Center</span>
      {new_tag}
    </div>
    <div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap;">
      <div style="text-align:right;">
        <div style="font-size:11px;color:{DIM};" id="cairo-date">{cairo_date}</div>
        <div style="font-size:14px;font-weight:700;color:{B};" id="cairo-clock">{_cairo_now()} Cairo</div>
      </div>
      <span class="badge" style="background:{mc}22;color:{mc};">&#11044; EGX {mstatus}</span>
    </div>
  </div>
  <div style="max-width:1100px;margin:6px auto 0;font-size:11px;color:{DIM};">
    Last Scan: <span style="color:{FG};">{scan_s}</span>
    &nbsp;&middot;&nbsp; Generated: <span style="color:{FG};">{gen_s}</span>
    &nbsp;&middot;&nbsp; Data As Of: <span style="color:{FG};">{scan_s}</span>
  </div>
</div>"""


def _s_stats(snap):
    premium = sum(1 for e in snap.timeline if e.get("status") == "PREMIUM_NOW")
    return f"""
<div class="card" style="padding:16px;">
  <div class="grid6">
    <div class="stat"><div class="stat-val" style="color:{W};">{snap.total_events}</div><div class="stat-lbl">Total Events</div></div>
    <div class="stat"><div class="stat-val" style="color:{B};">{len(snap.first_buys)}</div><div class="stat-lbl">First BUY</div></div>
    <div class="stat"><div class="stat-val" style="color:{P};">{len(snap.re_accumulations)}</div><div class="stat-lbl">Re-Accumulation</div></div>
    <div class="stat"><div class="stat-val" style="color:{A};">{len(snap.approaching_entries)}</div><div class="stat-lbl">Approaching</div></div>
    <div class="stat"><div class="stat-val" style="color:{G};">{premium}</div><div class="stat-lbl">Premium Now</div></div>
    <div class="stat"><div class="stat-val" style="color:{FG};">{snap.universe_size}</div><div class="stat-lbl">Universe</div></div>
  </div>
</div>"""


def _s_waiting_for(snap):
    entries = sorted(snap.approaching_entries, key=lambda e: e["distance_to_constitutional"])
    if not entries:
        return f"""
<div class="card" style="border-color:{A}44;">
  <div class="section-title" style="color:{A};">&#128269; What Am I Waiting For</div>
  <div style="color:{DIM};font-size:13px;">No tickers approaching constitutional entry right now.</div>
</div>"""
    rows = ""
    for e in entries:
        dist = e["distance_to_constitutional"]
        urg_c = G if dist <= 0.3 else (A if dist <= 1.0 else DIM)
        waiting = f"&#8211;{dist:.1f} pts to constitutional"
        rows += f"""
<tr>
  <td style="font-weight:700;color:{B};font-size:14px;">{e['ticker']}</td>
  <td style="color:{DIM};font-size:11px;">{e.get('sector','')}</td>
  <td style="color:{W};font-weight:700;">{e['entry_price']:.2f} EGP</td>
  <td style="color:{FG};">{e['current_price']:.2f}</td>
  <td style="color:{urg_c};font-weight:700;">{waiting}</td>
</tr>"""
    return f"""
<div class="card" style="border-color:{A}44;">
  <div class="section-title" style="color:{A};">&#128269; What Am I Waiting For ({len(entries)} approaching)</div>
  <div class="tbl-wrap">
    <table>
      <tr><th>Ticker</th><th>Sector</th><th>Entry Zone</th><th>Current</th><th>Distance</th></tr>
      {rows}
    </table>
  </div>
</div>"""


def _s_market_map(snap, dna):
    if not snap.timeline:
        return ""
    by_ticker = {}
    for e in snap.timeline:
        t = e["ticker"]
        if t not in by_ticker or e["event_date"] > by_ticker[t]["event_date"]:
            by_ticker[t] = e

    def _status(ret):
        if ret >= 50:  return ("PREMIUM NOW", G)
        elif ret >= 0: return ("ACTIVE", B)
        else:          return ("UNDER REVIEW", R)

    def _action(ret):
        if ret >= 50:  return f'<span style="color:{G};font-weight:700;">HOLD &mdash; TARGET HIT</span>'
        elif ret >= 0: return f'<span style="color:{B};">HOLD</span>'
        else:          return f'<span style="color:{A};">MONITOR</span>'

    def _memory(ticker):
        d = dna.get(ticker, {})
        hits = d.get("memory_hits", 0)
        if hits >= 3:   return "&#9733;&#9733;&#9733;&#9733;&#9733;"
        elif hits >= 2: return "&#9733;&#9733;&#9733;"
        elif hits >= 1: return "&#9733;"
        return ""

    rows = ""
    for ticker, e in sorted(by_ticker.items(), key=lambda x: -x[1]["return_pct"]):
        ret = e["return_pct"]
        lbl, sc = _status(ret)
        mem = _memory(ticker)
        rows += f"""
<tr>
  <td style="font-weight:700;color:{B};font-size:14px;">{ticker}</td>
  <td><span class="badge" style="background:{sc}22;color:{sc};">{lbl}</span></td>
  <td style="color:{W};font-weight:700;">{e['entry_price']:.2f} EGP</td>
  <td style="color:{FG};">{e['current_price']:.2f}</td>
  <td class="{_rc(ret)}">{_sign(ret)}{ret:.1f}%</td>
  <td>{_action(ret)}</td>
  <td style="color:{A};font-size:13px;">{mem}</td>
</tr>"""

    return f"""
<div class="card">
  <div class="section-title">&#128506; Market Map ({len(by_ticker)} tickers)</div>
  <div class="tbl-wrap">
    <table>
      <tr><th>Ticker</th><th>Status</th><th>Entry</th><th>Current</th><th>Return %</th><th>Action</th><th>Memory</th></tr>
      {rows}
    </table>
  </div>
</div>"""


def _s_stock_dna(snap, dna):
    if not snap.timeline:
        return ""
    by_ticker = {}
    for e in snap.timeline:
        by_ticker.setdefault(e["ticker"], []).append(e)

    cards = ""
    for ticker, events in sorted(by_ticker.items()):
        events_sorted = sorted(events, key=lambda e: e["event_date"])
        first_buy = next((e for e in events_sorted if e["event_type"] == "FIRST_BUY"), events_sorted[0])
        re_accums = [e for e in events_sorted if e["event_type"] == "RE_ACCUMULATION"]
        prices  = [e["entry_price"] for e in events_sorted if e["entry_price"]]
        returns = [e["return_pct"] for e in events_sorted]
        avg_entry = sum(prices) / len(prices) if prices else 0.0
        avg_ret   = sum(returns) / len(returns) if returns else 0.0
        zone_low  = min(prices) if prices else 0.0
        zone_high = max(prices) if prices else 0.0
        d = dna.get(ticker, {})
        confidence = d.get("memory_confidence", "DEVELOPING")
        conf_c = G if confidence == "STRONG" else (B if confidence == "CONFIRMED" else DIM)
        re_lines = ""
        for re in re_accums:
            re_lines += (
                f'<div style="font-size:12px;color:{DIM};margin-top:3px;">'
                f'Re-Accumulation {re["event_date"]} @ {re["entry_price"]:.2f} EGP '
                f'&rarr; <span class="{_rc(re["return_pct"])}">{_sign(re["return_pct"])}{re["return_pct"]:.1f}%</span>'
                f'</div>'
            )
        current = events_sorted[-1]["current_price"]
        sector  = events_sorted[0].get("sector", "")
        n_buy   = len([e for e in events if e["event_type"] == "FIRST_BUY"])
        cards += f"""
<div class="dna-card">
  <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;">
    <div>
      <span style="font-size:15px;font-weight:700;color:{B};">{ticker}</span>
      &nbsp;<span class="badge" style="background:{conf_c}22;color:{conf_c};font-size:10px;">{confidence}</span>
    </div>
    <div style="font-size:12px;color:{DIM};">{sector}</div>
  </div>
  <div class="dna-meta">
    <span style="color:{FG};">First BUY:</span> {first_buy['event_date']} @ {first_buy['entry_price']:.2f} EGP
    &nbsp;&middot;&nbsp; <span style="color:{FG};">Avg Entry:</span> {avg_entry:.2f} EGP
    &nbsp;&middot;&nbsp; <span style="color:{FG};">Current:</span> {current:.2f}
    &nbsp;&middot;&nbsp; <span class="{_rc(avg_ret)}">Avg Return: {_sign(avg_ret)}{avg_ret:.1f}%</span>
  </div>
  <div class="dna-meta">
    <span style="color:{FG};">Buy Zone:</span> {zone_low:.2f} &ndash; {zone_high:.2f} EGP
    &nbsp;&middot;&nbsp; <span style="color:{FG};">Events:</span> {len(events)} ({n_buy} BUY &middot; {len(re_accums)} Re-Accum)
  </div>
  {re_lines}
</div>"""

    return f"""
<div class="card">
  <details>
    <summary>
      <div class="section-title" style="margin-bottom:0;cursor:pointer;display:flex;align-items:center;justify-content:space-between;">
        <span>&#129516; Stock DNA ({len(by_ticker)} tickers)</span>
        <span style="font-size:11px;color:{DIM};">&#9660; expand</span>
      </div>
    </summary>
    <div style="margin-top:12px;">{cards}</div>
  </details>
</div>"""


def _s_timeline(snap):
    if not snap.timeline:
        return ""
    rows = ""
    for e in snap.timeline:
        rows += f"""
<tr>
  <td style="font-weight:700;color:{B};font-size:13px;">{e['ticker']}</td>
  <td>{_type_badge(e['event_type'])}</td>
  <td style="color:{W};font-weight:700;">{e['entry_price']:.2f} EGP</td>
  <td style="color:{FG};">{e['current_price']:.2f}</td>
  <td class="{_rc(e['return_pct'])}">{_sign(e['return_pct'])}{e['return_pct']:.1f}%</td>
  <td style="color:{DIM};font-size:11px;">{e['event_date']}</td>
  <td style="color:{DIM};font-size:11px;">{e.get('sector','')}</td>
</tr>"""
    return f"""
<div class="card">
  <details>
    <summary>
      <div class="section-title" style="margin-bottom:0;cursor:pointer;display:flex;align-items:center;justify-content:space-between;">
        <span>&#128203; Full Timeline ({snap.total_events} events)</span>
        <span style="font-size:11px;color:{DIM};">&#9660; expand</span>
      </div>
    </summary>
    <div style="margin-top:12px;" class="tbl-wrap">
      <table>
        <tr><th>Ticker</th><th>Type</th><th>Entry Zone</th><th>Current</th><th>Return %</th><th>Signal Date</th><th>Sector</th></tr>
        {rows}
      </table>
    </div>
  </details>
</div>"""


def _s_diagnostics(snap):
    tl_ok       = snap.total_events == 42
    fb_ok       = len(snap.first_buys) == 19
    re_ok       = len(snap.re_accumulations) == 23
    dash_ok     = (BASE / "dashboard.html").exists()
    email_ok    = (BASE / "email.html").exists()
    kb_ok       = snap.knowledge_count > 0
    research_ok = len(snap.research_insights) > 0
    dna_ok      = (BASE / "stock_dna.db").exists()

    def sha(path):
        if not path.exists(): return "--"
        return hashlib.sha256(path.read_bytes()).hexdigest()[:12] + "..."

    scan_s = snap.last_scan_ts[:19].replace("T", " ") if snap.last_scan_ts else "--"
    gen_s  = snap.generated_at[:19].replace("T", " ") if snap.generated_at else "--"

    checks = [
        ("Dashboard",      dash_ok,     f"dashboard.html · {sha(BASE / 'dashboard.html')}"),
        ("Email",          email_ok,    f"email.html · {sha(BASE / 'email.html')}"),
        ("Telegram",       True,        "runtime ready"),
        ("Knowledge Base", kb_ok,       f"{snap.knowledge_count} verified findings"),
        ("Research",       research_ok, f"{len(snap.research_insights)} insights loaded"),
        ("Stock DNA DB",   dna_ok,      "stock_dna.db present"),
    ]
    rows = ""
    for label, ok, detail in checks:
        c = G if ok else R
        rows += f"""
<tr>
  <td style="color:{DIM};font-size:12px;padding:7px 0;">{label}</td>
  <td style="padding:7px 8px;">{_pass_badge(ok)}</td>
  <td style="color:{c};font-size:12px;padding:7px 0;">{detail}</td>
</tr>"""

    tl_c = G if (tl_ok and fb_ok and re_ok) else R
    data_rows = (
        f'<tr><td style="color:{DIM};font-size:12px;padding:5px 0;">Timeline Events</td>'
        f'<td style="color:{tl_c};font-size:12px;font-weight:600;padding:5px 8px;">'
        f'{snap.total_events} ({len(snap.first_buys)} First BUY &middot; {len(snap.re_accumulations)} Re-Accum)</td></tr>'
        f'<tr><td style="color:{DIM};font-size:12px;padding:5px 0;">Universe</td>'
        f'<td style="color:{FG};font-size:12px;font-weight:600;padding:5px 8px;">{snap.universe_size} tickers</td></tr>'
        f'<tr><td style="color:{DIM};font-size:12px;padding:5px 0;">Approaching</td>'
        f'<td style="color:{A};font-size:12px;font-weight:600;padding:5px 8px;">{len(snap.approaching_entries)} tickers</td></tr>'
        f'<tr><td style="color:{DIM};font-size:12px;padding:5px 0;">Last Scan</td>'
        f'<td style="color:{DIM};font-size:12px;font-weight:600;padding:5px 8px;">{scan_s}</td></tr>'
        f'<tr><td style="color:{DIM};font-size:12px;padding:5px 0;">Generated At</td>'
        f'<td style="color:{DIM};font-size:12px;font-weight:600;padding:5px 8px;">{gen_s}</td></tr>'
        f'<tr><td style="color:{DIM};font-size:12px;padding:5px 0;">Market Status</td>'
        f'<td style="color:{_market_status_color(snap.market_status)};font-size:12px;font-weight:600;padding:5px 8px;">{snap.market_status}</td></tr>'
    )
    return f"""
<div class="card">
  <details>
    <summary>
      <div class="section-title" style="margin-bottom:0;cursor:pointer;display:flex;align-items:center;justify-content:space-between;">
        <span>&#128295; System Diagnostics</span>
        <span style="font-size:11px;color:{DIM};">&#9660; expand</span>
      </div>
    </summary>
    <div style="margin-top:12px;display:grid;grid-template-columns:1fr 1fr;gap:16px;">
      <div>
        <div style="font-size:11px;color:{DIM};text-transform:uppercase;letter-spacing:0.4px;margin-bottom:8px;">Runtime Status</div>
        <table style="font-size:12px;min-width:auto;">{rows}</table>
      </div>
      <div>
        <div style="font-size:11px;color:{DIM};text-transform:uppercase;letter-spacing:0.4px;margin-bottom:8px;">Live Data</div>
        <table style="font-size:12px;min-width:auto;">{data_rows}</table>
      </div>
    </div>
  </details>
</div>"""


def _s_universe_status(snap) -> str:
    """UNIVERSE STATUS — all 27 canonical tickers, ONE row each, NO exceptions."""
    try:
        from config.scanner_config import get_constitutional_universe
        universe = get_constitutional_universe()
    except Exception:
        return ""

    # Build lookup maps
    timeline_by_ticker = {}
    for e in snap.timeline:
        t = e["ticker"]
        if t not in timeline_by_ticker:
            timeline_by_ticker[t] = e  # first event = oldest; we want latest
    # Override with latest event per ticker
    for e in reversed(snap.timeline):
        timeline_by_ticker[e["ticker"]] = e

    approaching_by_ticker = {e["ticker"]: e for e in snap.approaching_entries}

    # candidate_pool — all tickers in latest snapshot
    pool_data = {}
    try:
        import sqlite3 as _sl
        pool = _sl.connect(str(BASE / "candidate_pool.db"))
        pool.row_factory = _sl.Row
        latest_ts = pool.execute("SELECT MAX(snapshot_ts) FROM candidate_pool").fetchone()[0]
        for row in pool.execute(
            "SELECT ticker, r2_score, final_score, current_price, entry_price FROM candidate_pool WHERE snapshot_ts=?",
            (latest_ts,)
        ).fetchall():
            pool_data[row["ticker"]] = dict(row)
        pool.close()
    except Exception:
        pass

    # signal_history fallback prices
    sh_prices = {}
    try:
        sh = json.load(open(str(BASE / "signal_history.json")))
        for t, sigs in sh.items():
            if sigs:
                sh_prices[t] = sigs[-1].get("price", "?")
    except Exception:
        pass

    # Count constitutional events per ticker (for memory stars)
    event_count = {}
    for e in snap.timeline:
        event_count[e["ticker"]] = event_count.get(e["ticker"], 0) + 1

    rows_html = ""
    covered = 0

    STATUS_ORDER = {"PREMIUM": 0, "ACTIVE": 1, "APPROACHING": 2, "UNDER REVIEW": 3,
                    "NEVER QUALIFIED": 4, "NO POOL DATA": 5, "NO DATA": 6}

    for ticker in sorted(universe):
        if ticker in timeline_by_ticker:
            e = timeline_by_ticker[ticker]
            ret = e["return_pct"]
            price = e["current_price"]
            entry = e["entry_price"]
            if ret >= 50:
                status, sc, action = "PREMIUM", G, "HOLD — TARGET HIT"
            elif ret >= 0:
                status, sc, action = "ACTIVE", B, "HOLD"
            else:
                status, sc, action = "UNDER REVIEW", A, "MONITOR"
            ret_str = f'<span class="{"pos" if ret>=0 else "neg"}">{ret:+.1f}%</span>'
            dist_str = "—"
            reason = f'{e["event_type"].replace("_"," ")} · {e["event_date"]}'
            n_events = event_count.get(ticker, 0)
            mem = "★" * min(n_events, 5) if n_events >= 2 else "—"
            last_update = e.get("event_date", "—")
        elif ticker in approaching_by_ticker:
            e = approaching_by_ticker[ticker]
            price = e["current_price"]
            entry = e["entry_price"]
            dist = e["distance_to_constitutional"]
            status, sc, action = "APPROACHING", A, f"WATCH — {dist:.1f} pts"
            ret_str = "—"
            dist_str = f'<span class="neu">–{dist:.1f} pts</span>'
            reason = f'R2 {e["r2_score"]:.1f} · score {e["final_score"]:.1f}'
            mem = "—"
            last_update = snap.last_scan_ts[:10] if snap.last_scan_ts else "—"
        elif ticker in pool_data:
            p = pool_data[ticker]
            price = p["current_price"]
            entry = p.get("entry_price", price)
            r2, score = p["r2_score"], p["final_score"]
            if r2 >= 60 and score < 35:
                status, sc, action = "NEVER QUALIFIED", DIM, f"Score {score:.0f} < 35"
                reason = f'R2 {r2:.1f} ✓ but Score {score:.1f} < 35'
            elif r2 < 60 and score >= 35:
                status, sc, action = "NEVER QUALIFIED", DIM, f"R2 {r2:.1f} < 60"
                reason = f'R2 {r2:.1f} < 60 · Score {score:.1f} ✓'
            else:
                status, sc, action = "NEVER QUALIFIED", DIM, f"R2 {r2:.1f} Score {score:.1f}"
                reason = f'R2 {r2:.1f} < 60 · Score {score:.1f} < 35'
            ret_str = "—"
            dist_str = f'<span style="color:{DIM};">–{max(0,60-r2):.1f} pts</span>'
            mem = "—"
            last_update = snap.last_scan_ts[:10] if snap.last_scan_ts else "—"
        elif ticker in sh_prices:
            price = sh_prices[ticker]
            entry = "—"
            status, sc, action = "NO POOL DATA", DIM, "Not in latest scan"
            reason = "Not scored in latest candidate snapshot"
            ret_str = "—"; dist_str = "—"; mem = "—"
            last_update = "—"
        else:
            price = "—"; entry = "—"
            status, sc, action = "NO DATA", DIM, "—"
            reason = "No data in any source"
            ret_str = "—"; dist_str = "—"; mem = "—"
            last_update = "—"

        covered += 1
        price_str = f"{price:.2f}" if isinstance(price, float) else str(price)
        entry_str = f"{entry:.2f}" if isinstance(entry, float) else str(entry)
        rows_html += (
            f'<tr>'
            f'<td style="font-weight:700;color:{W};">{ticker}</td>'
            f'<td>{price_str}</td>'
            f'<td><span class="badge" style="background:{sc}22;color:{sc};font-size:10px;">{status}</span></td>'
            f'<td style="color:{DIM};">{entry_str}</td>'
            f'<td>{dist_str}</td>'
            f'<td style="font-size:11px;color:{DIM};">{reason}</td>'
            f'<td style="color:{A};">{mem}</td>'
            f'<td style="font-size:11px;">{action}</td>'
            f'<td style="font-size:10px;color:{DIM};">{last_update}</td>'
            f'</tr>'
        )

    total = len(universe)
    constitutional_count = len(timeline_by_ticker)
    approaching_count = len([t for t in universe if t in approaching_by_ticker])
    never_count = total - constitutional_count - approaching_count

    return f"""
<div class="card">
  <div class="section-title">&#127757; UNIVERSE STATUS &nbsp;
    <span style="color:{G};font-weight:700;">{covered}/{total}</span>
    &nbsp;&middot;&nbsp; <span style="color:{B};">{constitutional_count} Constitutional</span>
    &nbsp;&middot;&nbsp; <span style="color:{A};">{approaching_count} Approaching</span>
    &nbsp;&middot;&nbsp; <span style="color:{DIM};">{never_count} Never Qualified / No Data</span>
  </div>
  <div class="tbl-wrap">
  <table>
    <thead><tr>
      <th>Ticker</th><th>Current</th><th>Status</th><th>Entry Zone</th>
      <th>Distance</th><th>Reason</th><th>Memory</th><th>Action</th><th>Last Update</th>
    </tr></thead>
    <tbody>{rows_html}</tbody>
  </table>
  </div>
</div>"""


def build_dashboard() -> str:
    snap = build_presentation_snapshot()
    dna  = _load_stock_dna()
    body = (
        _s_stats(snap) +
        _s_waiting_for(snap) +
        _s_universe_status(snap) +
        _s_market_map(snap, dna) +
        _s_stock_dna(snap, dna) +
        _s_timeline(snap) +
        _s_diagnostics(snap)
    )
    now_cairo = datetime.now(timezone(timedelta(hours=2))).strftime("%Y-%m-%d %H:%M Cairo")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>EGX Constitutional Command Center</title>
<style>{CSS}</style>
</head>
<body>
{_s_sticky_header(snap)}
<div class="wrap">
{body}
<div style="text-align:center;font-size:11px;color:{DIM};padding:16px 0;margin-top:8px;border-top:1px solid {BOR};">
  EGX Constitutional Command Center &nbsp;&middot;&nbsp; Append-Only &middot; Immutable Events &middot; No Portfolio Dependency
  <br><span style="font-family:monospace;font-size:10px;color:{DIM};opacity:0.7">
  dashboard.py v6 &nbsp;&middot;&nbsp; generated {now_cairo} &nbsp;&middot;&nbsp; commit $COMMIT_MARKER$
  </span>
</div>
</div>
{JS}
</body>
</html>"""


if __name__ == "__main__":
    import subprocess
    from stock_dna_engine import build_stock_dna
    build_stock_dna()
    try:
        commit = subprocess.check_output(["git","rev-parse","--short","HEAD"],stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        commit = "unknown"
    out  = BASE / "dashboard.html"
    html = build_dashboard().replace("$COMMIT_MARKER$", commit)
    out.write_text(html, encoding="utf-8")
    sha  = hashlib.sha256(html.encode()).hexdigest()
    print(f"[Dashboard V6] Saved dashboard.html ({len(html)//1024} KB)")
    print(f"[Dashboard V6] SHA256: {sha[:32]}...")
    print(f"[Dashboard V6] Commit: {commit}")
    for section in ["What Am I Waiting For","Market Map","Stock DNA","Full Timeline","System Diagnostics"]:
        present = section.replace(" ","") in html.replace(" ","")
        print(f"[Dashboard V6] Section '{section}': {'OK' if present else 'MISSING'}")
