"""
EGX Constitutional Command Center — Dashboard V7
Sections: Header → Stats → Near Entry → Future → Universe → Market Map → DNA → Timeline → Diagnostics
Cairo timezone throughout. Smart version-check refresh. Mutually-exclusive section assertions.
"""
from __future__ import annotations

import hashlib
import json as _json
import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from presentation.presentation_snapshot import PresentationSnapshot, build_presentation_snapshot

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))
from time_authority import now_cairo as _now_cairo, build_time as _build_time, _EET as _CAIRO_TZ

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
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{background:{BG0};font-family:'Segoe UI',system-ui,Arial,sans-serif;color:{FG};overflow-x:hidden;}}
.sticky-header{{position:sticky;top:0;z-index:100;background:{BG1};border-bottom:2px solid {BOR};
  padding:12px 20px;padding-left:max(20px,env(safe-area-inset-left));
  padding-right:max(20px,env(safe-area-inset-right));}}
.wrap{{max-width:1100px;margin:0 auto;padding:20px 16px;
  padding-left:max(16px,env(safe-area-inset-left));
  padding-right:max(16px,env(safe-area-inset-right));
  padding-bottom:max(20px,env(safe-area-inset-bottom));}}
.card{{background:{BG1};border:1px solid {BOR};border-radius:10px;padding:20px;margin-bottom:18px;overflow:hidden;}}
.section-title{{font-size:13px;font-weight:700;letter-spacing:0.6px;text-transform:uppercase;
  color:{DIM};margin-bottom:14px;border-bottom:1px solid {BOR};padding-bottom:8px;}}
.badge{{display:inline-block;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:700;white-space:nowrap;}}
.signal-card{{background:{BG2};border:1px solid {G}44;border-radius:10px;padding:18px;margin-bottom:14px;position:relative;}}
.signal-card.reaccum{{border-color:{P}44;}}
.signal-card-header{{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;margin-bottom:14px;}}
.signal-ticker{{font-size:22px;font-weight:800;color:{W};letter-spacing:1px;}}
.signal-action-btn{{display:inline-block;padding:8px 18px;border-radius:8px;font-size:13px;font-weight:800;
  letter-spacing:0.5px;text-transform:uppercase;border:2px solid;cursor:default;}}
.signal-grid{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:14px;}}
.signal-grid-4{{display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:10px;margin-bottom:14px;}}
.signal-box{{background:{BG1};border:1px solid {BOR};border-radius:7px;padding:10px 12px;}}
.signal-box-lbl{{font-size:10px;color:{DIM};text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px;}}
.signal-box-val{{font-size:16px;font-weight:700;color:{W};}}
.signal-box-sub{{font-size:11px;color:{DIM};margin-top:2px;}}
.signal-reasons{{background:{BG1};border:1px solid {BOR};border-radius:7px;padding:12px 14px;margin-bottom:14px;}}
.signal-reason-row{{display:flex;align-items:center;gap:8px;font-size:13px;color:{FG};padding:3px 0;}}
.signal-hist{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px;}}
.signal-meta{{display:flex;flex-wrap:wrap;gap:6px 20px;font-size:11px;color:{DIM};}}
.signal-meta span b{{color:{FG};}}
.conf-high{{color:{G};font-weight:700;}} .conf-med{{color:{A};font-weight:700;}} .conf-low{{color:{R};font-weight:700;}}
@keyframes pulse{{0%,100%{{opacity:1;}}50%{{opacity:.55;}}}}
@media(max-width:700px){{
  .signal-grid{{grid-template-columns:1fr 1fr;}}
  .signal-grid-4{{grid-template-columns:1fr 1fr;}}
  .signal-hist{{grid-template-columns:1fr 1fr;}}
  .signal-card-header{{flex-direction:column;align-items:flex-start;}}
}}
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
.ts-row{{display:flex;flex-wrap:wrap;gap:6px 20px;font-size:11px;color:{DIM};margin-top:6px;}}
.ts-row span{{white-space:nowrap;}} .ts-row b{{color:{FG};}}
.hdr-top{{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;}}
.hdr-left{{display:flex;align-items:center;gap:10px;flex-wrap:wrap;}}
.hdr-right{{display:flex;align-items:center;gap:8px;flex-wrap:wrap;}}
.btn{{border-radius:6px;padding:6px 12px;font-size:11px;cursor:pointer;font-weight:600;border:1px solid;background:transparent;transition:opacity .15s;}}
.btn:hover{{opacity:.8;}}
.btn-b{{color:{B};border-color:{B};background:{B}22;}}
.btn-a{{color:{A};border-color:{A};background:{A}22;}}
.btn-g{{color:{G};border-color:{G};background:{G}22;}}
#update-banner{{display:none;background:{A}22;border:1px solid {A}44;border-radius:6px;
  padding:8px 14px;font-size:12px;color:{A};margin:8px auto;max-width:1100px;text-align:center;}}
#update-banner a{{color:{A};font-weight:700;}}
@media(max-width:700px){{
  .grid6{{grid-template-columns:repeat(3,1fr);}}
  .sticky-header{{padding:10px 12px;}}
  td,th{{padding:7px 6px;font-size:12px;}}
  .stat-val{{font-size:16px;}}
}}
@media(max-width:420px){{
  .grid6{{grid-template-columns:repeat(2,1fr);}}
  .hdr-top{{flex-direction:column;align-items:flex-start;}}
  .hdr-right{{width:100%;justify-content:flex-start;}}
}}
.rank-badge{{display:inline-flex;align-items:center;justify-content:center;width:26px;height:26px;border-radius:50%;font-size:11px;font-weight:800;flex-shrink:0;border:1px solid;}}
.rank-1{{background:{G}22;color:{G};border-color:{G}55;}}
.rank-2{{background:{B}22;color:{B};border-color:{B}55;}}
.rank-3{{background:{A}22;color:{A};border-color:{A}55;}}
.rank-n{{background:{P}22;color:{P};border-color:{P}55;}}
.top-opp-card{{background:linear-gradient(135deg,{BG0} 0%,{BG2} 100%);border:2px solid {G}88;border-radius:12px;padding:22px;margin-bottom:20px;box-shadow:0 0 24px {G}22;}}
.buy-block-hdr{{font-size:12px;font-weight:700;letter-spacing:0.6px;padding:10px 14px;border-radius:7px;margin:14px 0 10px;display:flex;align-items:center;gap:8px;}}
"""

JS = """
<script>
// ── Cairo live clock ─────────────────────────────────────────────────────────
(function tick(){
  var now=new Date();
  var opts={timeZone:'Africa/Cairo',hour12:false};
  var t=now.toLocaleTimeString('en-US',Object.assign({},opts,{hour:'2-digit',minute:'2-digit',second:'2-digit'}));
  var d=now.toLocaleDateString('en-US',Object.assign({},opts,{weekday:'long',day:'numeric',month:'long',year:'numeric'}));
  var el=document.getElementById('cairo-clock'); if(el) el.textContent=t+' Cairo';
  var dl=document.getElementById('cairo-date');  if(dl) dl.textContent=d;
  setTimeout(tick,1000);
})();

// ── Version check ─────────────────────────────────────────────────────────────
var _currentHash = document.body.dataset.hash || '';
function _fetchVersion(){
  return fetch('version.json?_='+Date.now(),{cache:'no-store'}).then(function(r){return r.json();});
}
function checkUpdates(){
  var btn=document.getElementById('btn-check');
  if(btn){btn.textContent='⏳ Checking...';btn.disabled=true;}
  _fetchVersion().then(function(v){
    if(btn){btn.textContent='🔍 Check Updates';btn.disabled=false;}
    var same=(v.build_hash===_currentHash);
    var banner=document.getElementById('update-banner');
    if(same){
      banner.style.display='block';
      banner.innerHTML='✓ Already up to date — v'+v.version+' · '+v.generated_at+' · commit '+v.commit;
      setTimeout(function(){banner.style.display='none';},5000);
    } else {
      banner.style.display='block';
      banner.innerHTML='⚡ New version available ('+v.generated_at+') · commit '+v.commit
        +' — <a href="?v='+v.build_hash+'">Click to reload</a>';
    }
  }).catch(function(){
    if(btn){btn.textContent='🔍 Check Updates';btn.disabled=false;}
    alert('Could not fetch version.json.');
  });
}
// Auto-check every 90 seconds silently
setInterval(function(){
  _fetchVersion().then(function(v){
    if(v.build_hash && v.build_hash!==_currentHash){
      var banner=document.getElementById('update-banner');
      if(banner && banner.style.display==='none'){
        banner.style.display='block';
        banner.innerHTML='⚡ New version available ('+v.generated_at+') · commit '+v.commit
          +' — <a href="?v='+v.build_hash+'">Click to reload</a>';
      }
    }
  }).catch(function(){});
},90000);

// ── Refresh (smart: navigate to ?v=hash to bust cache) ───────────────────────
function refreshDash(){
  var btn=document.getElementById('btn-refresh');
  if(btn){btn.textContent='⏳ Checking...';btn.disabled=true;}
  _fetchVersion().then(function(v){
    if(btn){btn.textContent='♻ Refresh';btn.disabled=false;}
    if(v.build_hash && v.build_hash===_currentHash){
      var banner=document.getElementById('update-banner');
      banner.style.display='block';
      banner.innerHTML='✓ Already up to date — last generated '+v.generated_at;
      setTimeout(function(){banner.style.display='none';},4000);
    } else {
      window.location.href=window.location.pathname+'?v='+(v.build_hash||Date.now());
    }
  }).catch(function(){
    if(btn){btn.textContent='♻ Refresh';btn.disabled=false;}
    window.location.href=window.location.pathname+'?v='+Date.now();
  });
}

// ── Run Scan (workflow_dispatch — opens GitHub Actions) ───────────────────────
function triggerScan(){
  if(confirm('This will open GitHub Actions.\\nClick "Run workflow" on the page that opens.\\n\\nNote: scan takes ~30 minutes to complete.')){
    window.open('https://github.com/shadygad01/smartlist/actions/workflows/full_production_scan.yml','_blank');
  }
}
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

def _to_cairo(ts_str: str) -> str:
    """Convert any ISO timestamp string to Cairo local time string."""
    if not ts_str:
        return "--"
    try:
        dt = datetime.fromisoformat(ts_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt_cairo = dt.astimezone(_CAIRO_TZ)
        return dt_cairo.strftime("%Y-%m-%d %H:%M Cairo")
    except Exception:
        return ts_str[:16].replace("T", " ")


def _conviction_score(e: dict, leader: dict, an: dict) -> float:
    """Composite signal conviction: R2(35%) + Score(25%) + WinRate(20%) + AvgReturn(15%) + Discount(5%)."""
    r2      = e.get("buy_r2",  0.0) or 0.0
    score   = e.get("buy_score", 0.0) or 0.0
    wr      = leader.get("win_rate", 0.0) or 0.0
    avg_ret = an.get("avg_return_pct", 0.0) or 0.0
    entry_p = e.get("entry_price", 0.0) or 0.0
    cur_p   = e.get("current_price", 0.0) or 0.0
    disc    = max(0.0, (entry_p - cur_p) / entry_p * 100.0) if entry_p else 0.0
    return r2 * 0.35 + score * 0.25 + wr * 20.0 + avg_ret * 0.15 + disc * 0.25


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


# ── Header ────────────────────────────────────────────────────────────────────
def _s_sticky_header(snap, build_hash: str = ""):
    mstatus = snap.market_status
    mc = _market_status_color(mstatus)
    # Three distinct timestamps — semantically distinct
    scan_cairo = _to_cairo(snap.last_scan_ts)
    gen_cairo  = _to_cairo(snap.generated_at)
    # Data As Of = date of latest CSV close — authoritative price date (not scan time)
    data_as_of = getattr(snap, "price_data_as_of", "") or scan_cairo
    new_tag = ""
    if snap.new_events_today:
        new_tag = (f'<span class="badge" style="background:{G}22;color:{G};">'
                   f'&#9889; {len(snap.new_events_today)} NEW TODAY</span>')
    return f"""
<div class="sticky-header">
  <div id="update-banner"></div>
  <div class="hdr-top" style="max-width:1100px;margin:0 auto;">
    <div class="hdr-left">
      <span style="font-size:16px;font-weight:700;color:{W};">&#127963; EGX Constitutional Command Center</span>
      <span class="badge" style="background:{mc}22;color:{mc};">&#11044; EGX {mstatus}</span>
      {new_tag}
    </div>
    <div class="hdr-right">
      <div style="text-align:right;min-width:140px;">
        <div style="font-size:10px;color:{DIM};" id="cairo-date"></div>
        <div style="font-size:13px;font-weight:700;color:{B};" id="cairo-clock">--:-- Cairo</div>
      </div>
      <button class="btn btn-b" onclick="triggerScan()">&#128260; Run Scan</button>
      <button class="btn btn-g" id="btn-refresh" onclick="refreshDash()">&#9851; Refresh</button>
      <button class="btn btn-a" id="btn-check" onclick="checkUpdates()">&#128269; Check Updates</button>
    </div>
  </div>
  <div class="ts-row" style="max-width:1100px;margin:6px auto 0;">
    <span>&#128337; Last Scan: <b>{scan_cairo}</b></span>
    <span>&#128197; Generated: <b>{gen_cairo}</b></span>
    <span>&#128202; Data As Of: <b>{data_as_of}</b></span>
    <span style="opacity:.6;">v7 · <span style="font-family:monospace;">$COMMIT_MARKER$</span></span>
  </div>
</div>"""


# ── Stats bar ─────────────────────────────────────────────────────────────────
def _s_stats(snap):
    uni = snap.universe_snapshot or []
    premium_count   = sum(1 for r in uni if r.get("status") == "PREMIUM")
    active_count    = sum(1 for r in uni if r.get("status") == "ACTIVE")
    near_count      = len(snap.approaching_entries)
    return f"""
<div class="card" style="padding:16px;">
  <div class="grid6">
    <div class="stat"><div class="stat-val" style="color:{W};">{snap.total_events}</div><div class="stat-lbl">Total Events</div></div>
    <div class="stat"><div class="stat-val" style="color:{B};">{len(snap.first_buys)}</div><div class="stat-lbl">First BUY</div></div>
    <div class="stat"><div class="stat-val" style="color:{P};">{len(snap.re_accumulations)}</div><div class="stat-lbl">Re-Accum</div></div>
    <div class="stat"><div class="stat-val" style="color:{A};">{near_count}</div><div class="stat-lbl">Near Entry</div></div>
    <div class="stat"><div class="stat-val" style="color:{G};">{premium_count}</div><div class="stat-lbl">Premium</div></div>
    <div class="stat"><div class="stat-val" style="color:{FG};">{snap.universe_size}</div><div class="stat-lbl">Universe</div></div>
  </div>
</div>"""


# ── Constitutional Buy Signals ────────────────────────────────────────────────
def _s_buy_signals(snap) -> tuple:
    """
    HIGHEST PRIORITY section. Returns (html_str, signal_tickers_frozenset).
    Callers pass signal_tickers_frozenset to _s_near_entry and _s_future_opportunities
    so no ticker appears in more than one decision section.

    Block 1 — NEW CONSTITUTIONAL BUY SIGNALS  (FIRST_BUY events fired today)
    Block 2 — RE-ACCUMULATION SIGNALS         (RE_ACCUMULATION events today
                                               + timeline holders at/below entry)
    """
    leaders_by_t = {l["ticker"]: l for l in (snap.constitutional_leaders or [])}
    analytics    = snap.analytics or {}
    market_open  = "OPEN" in snap.market_status and "PRE" not in snap.market_status
    market_pre   = "PRE" in snap.market_status
    gen_cairo    = _to_cairo(snap.generated_at)

    # ── 1. Today's confirmed events ───────────────────────────────────────────
    today_events  = list(snap.new_events_today or [])
    today_tickers = {e["ticker"] for e in today_events}
    today_new_buy  = [e for e in today_events if e["event_type"] == "FIRST_BUY"]
    today_re_today = [e for e in today_events if e["event_type"] != "FIRST_BUY"]

    # ── 2. Historical re-accumulation candidates ──────────────────────────────
    by_ticker_latest: dict[str, dict] = {}
    for e in (snap.timeline or []):
        t = e["ticker"]
        if t not in by_ticker_latest or e["event_date"] > by_ticker_latest[t]["event_date"]:
            by_ticker_latest[t] = e
    seen = set(today_tickers)
    reaccum_hist = []
    for ticker, e in sorted(by_ticker_latest.items(), key=lambda x: x[1]["return_pct"]):
        if ticker in seen:
            continue
        if e["return_pct"] <= 0:
            seen.add(ticker)
            reaccum_hist.append(e)

    # ── 3. Build blocks with conviction ranking ───────────────────────────────
    def _conv(e: dict) -> float:
        return _conviction_score(
            e, leaders_by_t.get(e["ticker"], {}), analytics.get(e["ticker"], {})
        )

    new_buy_block  = sorted(today_new_buy,              key=_conv, reverse=True)
    re_accum_block = sorted(today_re_today + reaccum_hist, key=_conv, reverse=True)
    all_signals    = new_buy_block + re_accum_block
    all_sig_tickers = frozenset(e["ticker"] for e in all_signals)

    # ── Empty state ───────────────────────────────────────────────────────────
    if not all_signals:
        tl = snap.timeline or []
        if tl:
            last = max(tl, key=lambda e: e["event_date"])
            last_html = f"""
<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-top:14px;">
  <div class="signal-box"><div class="signal-box-lbl">Last Ticker</div>
    <div class="signal-box-val" style="color:{B};">{last['ticker']}</div></div>
  <div class="signal-box"><div class="signal-box-lbl">Last Signal Date</div>
    <div class="signal-box-val" style="font-size:14px;">{last['event_date']}</div></div>
  <div class="signal-box"><div class="signal-box-lbl">Return Since Signal</div>
    <div class="signal-box-val" class="{_rc(last['return_pct'])}">{_sign(last['return_pct'])}{last['return_pct']:.1f}%</div></div>
</div>"""
        else:
            last_html = f'<div style="color:{DIM};font-size:13px;">No constitutional events recorded yet.</div>'
        return (f"""
<div class="card" style="border:2px solid {BOR}66;border-radius:12px;
  background:linear-gradient(135deg,{BG1} 0%,{BG2} 100%);padding:22px;">
  <div class="section-title" style="color:{DIM};border-color:{BOR}33;
    display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;">
    <span>&#128994; CONSTITUTIONAL BUY SIGNALS &nbsp;<span style="font-size:12px;font-weight:400;">— no active signals</span></span>
    <span style="font-size:11px;color:{DIM};font-weight:400;">{gen_cairo}</span>
  </div>
  <div style="text-align:center;padding:24px 0;">
    <div style="font-size:32px;margin-bottom:10px;">&#128274;</div>
    <div style="font-size:16px;font-weight:700;color:{DIM};margin-bottom:4px;">No Constitutional Buy Signals Available</div>
    <div style="font-size:12px;color:{DIM};margin-bottom:16px;">No tickers currently meet R2&#8805;60 + Score&#8805;35 + Price&#8804;Entry simultaneously.</div>
    {last_html}
  </div>
</div>""", frozenset())

    # ── Rank badge ────────────────────────────────────────────────────────────
    def _rank_badge(rank: int) -> str:
        cls = {1: "rank-1", 2: "rank-2", 3: "rank-3"}.get(rank, "rank-n")
        return f'<span class="rank-badge {cls}">#{rank}</span>'

    # ── Signal card ───────────────────────────────────────────────────────────
    def _signal_card(e: dict, is_today: bool, rank: int) -> str:
        ticker     = e["ticker"]
        etype      = e["event_type"]
        is_new_buy = etype == "FIRST_BUY"
        entry_p    = e["entry_price"]
        cur_p      = e["current_price"]
        r2         = e.get("buy_r2", 0.0) or 0.0
        score      = e.get("buy_score", 0.0) or 0.0
        ev_date    = e.get("event_date", "")
        sector     = e.get("sector", "")
        days_held  = e.get("days_active", 0)

        dist_pct     = round((cur_p - entry_p) / entry_p * 100, 2) if entry_p else 0.0
        discount_pct = round((entry_p - cur_p) / entry_p * 100, 2) if entry_p and cur_p < entry_p else 0.0

        leader     = leaders_by_t.get(ticker, {})
        an         = analytics.get(ticker, {})
        n_prev     = an.get("total_events", 0)
        avg_ret    = an.get("avg_return_pct", 0.0) or 0.0
        best_ret   = an.get("best_return_pct", 0.0) or 0.0
        win_rate   = leader.get("win_rate", 0.0) or 0.0
        confidence = leader.get("confidence", "DEVELOPING")
        conf_cls   = "conf-high" if confidence in ("ELITE","STRONG") else ("conf-med" if confidence == "CONFIRMED" else "conf-low")

        if is_today and market_open:
            action_lbl, action_c = "BUY NOW", G
        elif is_today and market_pre:
            action_lbl, action_c = "BUY ON OPEN", A
        elif is_today:
            action_lbl, action_c = f"BUY LIMIT @ {entry_p:.2f}", B
        elif is_new_buy and discount_pct > 0:
            action_lbl, action_c = f"BUY LIMIT @ {entry_p:.2f}", B
        else:
            action_lbl, action_c = "RE-ACCUMULATE", P

        type_lbl = "NEW BUY" if is_new_buy else "RE-ACCUMULATION"
        type_c   = B if is_new_buy else P
        live_tag = (
            f'<span class="badge" style="background:{R}22;color:{R};animation:pulse 1.5s infinite;">&#128308; LIVE SIGNAL</span> '
            if is_today else ""
        )
        card_cls = "signal-card" if is_new_buy else "signal-card reaccum"
        border_c = G if is_new_buy else P

        reasons = []
        if r2 >= 60:    reasons.append(("✓", f"R2 Constitutional Gate cleared ({r2:.1f} / 60)", G))
        elif r2 >= 55:  reasons.append(("◎", f"R2 approaching gate ({r2:.1f} / 60)", A))
        if score >= 35: reasons.append(("✓", f"Constitutional Score met ({score:.1f} / 35+)", G))
        if discount_pct > 0:
            reasons.append(("✓", f"Discount Zone confirmed (price {discount_pct:.1f}% below entry)", G))
        elif dist_pct <= 0.5:
            reasons.append(("✓", "At Entry Zone (price at constitutional gate)", G))
        if n_prev >= 2:
            reasons.append(("✓", f"Proven track record: {n_prev} prior signals, avg return {avg_ret:+.1f}%", G))
        elif n_prev == 1:
            reasons.append(("◎", "First constitutional event for this ticker", A))
        if win_rate >= 0.7:
            reasons.append(("✓", f"High historical win rate ({win_rate*100:.0f}%)", G))
        if not reasons:
            reasons.append(("◎", "Constitutional criteria met (R2 + Score + Discount Zone)", A))

        reasons_html = "".join(
            f'<div class="signal-reason-row">'
            f'<span style="color:{rc};font-size:14px;flex-shrink:0;">{icon}</span>'
            f'<span>{txt}</span></div>'
            for icon, txt, rc in reasons
        )

        dist_html = (
            f'<span class="neg">{dist_pct:+.1f}%</span>'
            if dist_pct < 0 else
            f'<span class="pos">{dist_pct:+.1f}%</span>'
        )
        disc_html = (
            f'<span class="pos">{discount_pct:.1f}% below entry</span>'
            if discount_pct > 0 else
            f'<span class="neg">+{abs(discount_pct):.1f}% above entry</span>'
        )

        hist_win_s  = f"{win_rate*100:.0f}%" if win_rate else "—"
        hist_avg_s  = f"{avg_ret:+.1f}%" if avg_ret else "—"
        hist_best_s = f"{best_ret:+.1f}%" if best_ret else "—"
        hist_n_s    = str(n_prev) if n_prev else "1st"

        pulse_style = f"box-shadow:0 0 0 2px {border_c}88,0 0 18px {border_c}44;" if is_today else ""

        return f"""
<div class="{card_cls}" style="{pulse_style}">
  <div class="signal-card-header">
    <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
      {_rank_badge(rank)}
      {live_tag}
      <span class="signal-ticker">{ticker}</span>
      <span style="font-size:10px;color:{DIM};text-transform:uppercase;letter-spacing:.5px;margin-right:2px;">Signal Type:</span><span class="badge" style="background:{type_c}22;color:{type_c};font-size:12px;">{type_lbl}</span>
      <span style="font-size:12px;color:{DIM};">{sector}</span>
    </div>
    <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
      <span style="font-size:10px;color:{DIM};text-transform:uppercase;letter-spacing:.5px;">Confidence:</span>&nbsp;<span class="{conf_cls}" style="font-size:12px;">{confidence}</span>
      <span class="signal-action-btn" style="color:{action_c};border-color:{action_c};background:{action_c}18;">{action_lbl}</span>
    </div>
  </div>

  <div class="signal-grid">
    <div class="signal-box">
      <div class="signal-box-lbl">Entry Price</div>
      <div class="signal-box-val" style="color:{W};">{entry_p:.2f} <span style="font-size:12px;color:{DIM};">EGP</span></div>
      <div class="signal-box-sub">Constitutional buy zone</div>
    </div>
    <div class="signal-box">
      <div class="signal-box-lbl">Current Price</div>
      <div class="signal-box-val" style="color:{FG};">{cur_p:.2f} <span style="font-size:12px;color:{DIM};">EGP</span></div>
      <div class="signal-box-sub">Distance: {dist_html}</div>
    </div>
    <div class="signal-box">
      <div class="signal-box-lbl">Discount</div>
      <div class="signal-box-val" style="color:{G if discount_pct > 0 else A};">{discount_pct:.1f}%</div>
      <div class="signal-box-sub">{disc_html}</div>
    </div>
  </div>

  <div class="signal-grid-4">
    <div class="signal-box">
      <div class="signal-box-lbl">Constitutional Score</div>
      <div class="signal-box-val" style="color:{G};">{score:.1f}</div>
      <div class="signal-box-sub">Threshold: 35+</div>
    </div>
    <div class="signal-box">
      <div class="signal-box-lbl">R2 Score</div>
      <div class="signal-box-val" style="color:{G if r2>=60 else A};">{r2:.1f} <span style="font-size:11px;color:{DIM};">/ 60</span></div>
      <div class="signal-box-sub">Gate: &#8805; 60</div>
    </div>
    <div class="signal-box">
      <div class="signal-box-lbl">Signal Date</div>
      <div class="signal-box-val" style="font-size:14px;">{ev_date}</div>
      <div class="signal-box-sub">{days_held}d active · Cairo</div>
    </div>
    <div class="signal-box">
      <div class="signal-box-lbl">Signal Status</div>
      <div class="signal-box-val" style="font-size:13px;color:{'#4caf50' if is_today else A};">{'🔴 TODAY' if is_today else '📌 ACTIVE'}</div>
      <div class="signal-box-sub">Scan: {gen_cairo[:10]}</div>
    </div>
  </div>

  <div class="signal-reasons">
    <div style="font-size:11px;color:{DIM};text-transform:uppercase;letter-spacing:0.5px;margin-bottom:8px;">Why This Signal Exists</div>
    {reasons_html}
  </div>

  <div class="signal-hist">
    <div class="signal-box">
      <div class="signal-box-lbl">Win Rate</div>
      <div class="signal-box-val" style="color:{G if win_rate>=0.7 else (A if win_rate>=0.5 else R)};">{hist_win_s}</div>
      <div class="signal-box-sub">Historical signals</div>
    </div>
    <div class="signal-box">
      <div class="signal-box-lbl">Avg Return</div>
      <div class="signal-box-val" style="color:{G if avg_ret>0 else R};">{hist_avg_s}</div>
      <div class="signal-box-sub">Per event</div>
    </div>
    <div class="signal-box">
      <div class="signal-box-lbl">Best Return</div>
      <div class="signal-box-val" style="color:{G};">{hist_best_s}</div>
      <div class="signal-box-sub">Max historical</div>
    </div>
    <div class="signal-box">
      <div class="signal-box-lbl">Prior Signals</div>
      <div class="signal-box-val" style="color:{FG};">{hist_n_s}</div>
      <div class="signal-box-sub">Similar setups</div>
    </div>
  </div>
</div>"""

    # ── Top Opportunity card ──────────────────────────────────────────────────
    def _top_opportunity_card(e: dict) -> str:
        ticker     = e["ticker"]
        etype      = e["event_type"]
        is_new_buy = etype == "FIRST_BUY"
        entry_p    = e["entry_price"]
        cur_p      = e["current_price"]
        r2         = e.get("buy_r2", 0.0) or 0.0
        score      = e.get("buy_score", 0.0) or 0.0
        sector     = e.get("sector", "")
        discount_pct = round((entry_p - cur_p) / entry_p * 100, 2) if entry_p and cur_p < entry_p else 0.0

        leader     = leaders_by_t.get(ticker, {})
        an         = analytics.get(ticker, {})
        n_prev     = an.get("total_events", 0)
        avg_ret    = an.get("avg_return_pct", 0.0) or 0.0
        best_ret   = an.get("best_return_pct", 0.0) or 0.0
        win_rate   = leader.get("win_rate", 0.0) or 0.0
        confidence = leader.get("confidence", "DEVELOPING")
        conf_cls   = "conf-high" if confidence in ("ELITE","STRONG") else ("conf-med" if confidence == "CONFIRMED" else "conf-low")
        type_lbl   = "NEW BUY" if is_new_buy else "RE-ACCUMULATION"
        type_c     = B if is_new_buy else P
        is_today_t = ticker in today_tickers

        if is_today_t and market_open:
            action_lbl, action_c = "BUY NOW", G
        elif is_today_t and market_pre:
            action_lbl, action_c = "BUY ON OPEN", A
        elif is_today_t:
            action_lbl, action_c = f"BUY LIMIT @ {entry_p:.2f}", B
        elif is_new_buy and discount_pct > 0:
            action_lbl, action_c = f"BUY LIMIT @ {entry_p:.2f}", B
        else:
            action_lbl, action_c = "RE-ACCUMULATE", P

        hist_win_s = f"{win_rate*100:.0f}%" if win_rate else "—"
        hist_avg_s = f"{avg_ret:+.1f}%" if avg_ret else "—"
        hist_n_s   = str(n_prev) if n_prev else "1st"
        exp_reward = f"{avg_ret:+.1f}% avg · {best_ret:+.1f}% best" if avg_ret else "Insufficient history"

        reason_parts = []
        if r2 >= 60:         reason_parts.append(f"R2={r2:.1f} &#10003;")
        if score >= 35:      reason_parts.append(f"Score={score:.1f} &#10003;")
        if discount_pct > 0: reason_parts.append(f"{discount_pct:.1f}% discount &#10003;")
        if win_rate >= 0.7:  reason_parts.append(f"{win_rate*100:.0f}% win rate &#10003;")
        reason_str = "  &middot;  ".join(reason_parts) if reason_parts else "Constitutional criteria met"
        sector_html = f'<span style="font-size:11px;color:{DIM};">{sector}</span>' if sector else ""

        return f"""
<div class="top-opp-card">
  <div style="display:flex;align-items:center;gap:10px;margin-bottom:18px;flex-wrap:wrap;">
    <span style="font-size:18px;">&#11088;</span>
    <span style="font-size:13px;font-weight:700;letter-spacing:0.8px;color:{G};text-transform:uppercase;">Today's Top Constitutional Opportunity</span>
    <span style="margin-left:auto;font-size:11px;color:{DIM};">{gen_cairo}</span>
  </div>
  <div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin-bottom:18px;">
    <span style="font-size:34px;font-weight:800;color:{W};letter-spacing:1px;">{ticker}</span>
    <span class="rank-badge rank-1">#1</span>
    <span class="badge" style="background:{type_c}22;color:{type_c};">{type_lbl}</span>
    {sector_html}
    <span class="{conf_cls}" style="font-size:13px;">&#9733; {confidence}</span>
    <span class="signal-action-btn" style="color:{action_c};border-color:{action_c};background:{action_c}18;margin-left:auto;">{action_lbl}</span>
  </div>
  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:14px;">
    <div class="signal-box">
      <div class="signal-box-lbl">Entry Price</div>
      <div class="signal-box-val" style="color:{W};">{entry_p:.2f} <span style="font-size:12px;color:{DIM};">EGP</span></div>
      <div class="signal-box-sub">Constitutional buy zone</div>
    </div>
    <div class="signal-box">
      <div class="signal-box-lbl">Current Price</div>
      <div class="signal-box-val" style="color:{FG};">{cur_p:.2f} <span style="font-size:12px;color:{DIM};">EGP</span></div>
      <div class="signal-box-sub">vs entry zone</div>
    </div>
    <div class="signal-box">
      <div class="signal-box-lbl">Discount</div>
      <div class="signal-box-val" style="color:{G if discount_pct > 0 else A};">{discount_pct:.1f}%</div>
      <div class="signal-box-sub">{'Below entry' if discount_pct > 0 else 'At entry zone'}</div>
    </div>
  </div>
  <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px;">
    <div class="signal-box">
      <div class="signal-box-lbl">Win Rate</div>
      <div class="signal-box-val" style="color:{G if win_rate>=0.7 else (A if win_rate>=0.5 else DIM)};">{hist_win_s}</div>
      <div class="signal-box-sub">Historical</div>
    </div>
    <div class="signal-box">
      <div class="signal-box-lbl">Avg Return</div>
      <div class="signal-box-val" style="color:{G if avg_ret>0 else R};">{hist_avg_s}</div>
      <div class="signal-box-sub">Per signal</div>
    </div>
    <div class="signal-box">
      <div class="signal-box-lbl">Expected Reward</div>
      <div class="signal-box-val" style="font-size:12px;color:{G};">{exp_reward}</div>
      <div class="signal-box-sub">Based on {hist_n_s} prior signals</div>
    </div>
    <div class="signal-box">
      <div class="signal-box-lbl">Historical Signals</div>
      <div class="signal-box-val" style="color:{FG};">{hist_n_s}</div>
      <div class="signal-box-sub">Similar setups</div>
    </div>
  </div>
  <div class="signal-reasons" style="margin-bottom:0;">
    <div style="font-size:11px;color:{DIM};text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px;">Why This Is #1 — Highest Constitutional Conviction</div>
    <div style="font-size:13px;color:{FG};">{reason_str}</div>
  </div>
</div>"""

    # ── Build blocks ──────────────────────────────────────────────────────────
    n_new = len(new_buy_block)
    n_re  = len(re_accum_block)
    parts = []
    if n_new: parts.append(f"{n_new} NEW BUY")
    if n_re:  parts.append(f"{n_re} RE-ACCUM")
    count_tag  = f'<span style="font-size:12px;color:{G};font-weight:700;">{" &nbsp;&middot;&nbsp; ".join(parts)}</span>'
    border_col = G if new_buy_block else P
    title_c    = G if new_buy_block else P

    # Block 1
    block1_hdr = f"""
<div class="buy-block-hdr" style="background:{G}11;border:1px solid {G}33;color:{G};">
  &#128994; NEW CONSTITUTIONAL BUY SIGNALS
  <span style="margin-left:auto;font-size:11px;font-weight:400;color:{DIM};">{n_new} signal{"s" if n_new != 1 else ""}</span>
</div>"""
    if new_buy_block:
        block1_cards = "".join(_signal_card(e, True, i + 1) for i, e in enumerate(new_buy_block))
    else:
        block1_cards = f"""
<div style="padding:14px 16px;background:{BG2};border-radius:8px;border:1px dashed {G}33;
  color:{DIM};font-size:13px;text-align:center;">
  No New Constitutional Buy Signals today
</div>"""

    # Block 2
    block2_hdr = f"""
<div class="buy-block-hdr" style="background:{P}11;border:1px solid {P}33;color:{P};margin-top:16px;">
  &#128309; RE-ACCUMULATION SIGNALS
  <span style="margin-left:auto;font-size:11px;font-weight:400;color:{DIM};">{n_re} signal{"s" if n_re != 1 else ""}</span>
</div>"""
    if re_accum_block:
        block2_cards = "".join(
            _signal_card(e, e["ticker"] in today_tickers, i + 1)
            for i, e in enumerate(re_accum_block)
        )
    else:
        block2_cards = f"""
<div style="padding:14px 16px;background:{BG2};border-radius:8px;border:1px dashed {P}33;
  color:{DIM};font-size:13px;text-align:center;">
  No Re-Accumulation Signals today
</div>"""

    top_card = _top_opportunity_card(all_signals[0])
    inner    = top_card + block1_hdr + block1_cards + block2_hdr + block2_cards

    html = f"""
<div class="card" style="border:2px solid {border_col}66;border-radius:12px;
  background:linear-gradient(135deg,{BG1} 0%,{BG2} 100%);padding:22px;">
  <div class="section-title" style="color:{title_c};border-color:{border_col}33;
    display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;">
    <span>&#128994; CONSTITUTIONAL BUY SIGNALS &nbsp;{count_tag}</span>
    <span style="font-size:11px;color:{DIM};font-weight:400;">{gen_cairo}</span>
  </div>
  {inner}
</div>"""

    return (html, all_sig_tickers)


# ── Near Constitutional Entry ─────────────────────────────────────────────────
# Single source of truth: snap.approaching_entries (from PresentationSnapshot).
# Criteria: R2 50–59.9, current_price ≤ entry_price, final_score ≥ 35.
# buy_signal_tickers excluded — those already appear in the buy signals section.
def _s_near_entry(snap, excluded: frozenset = frozenset()) -> str:
    candidates = sorted(
        [e for e in snap.approaching_entries if e["ticker"] not in excluded],
        key=lambda e: e["distance_to_constitutional"]
    )

    if not candidates:
        return f"""
<div class="card" style="border-color:{A}44;">
  <div class="section-title" style="color:{A};">&#127919; NEAR CONSTITUTIONAL ENTRY</div>
  <div style="color:{DIM};font-size:13px;padding:6px 0;">
    No tickers in the discount zone within 10 R2-points of the constitutional gate right now.
  </div>
</div>"""

    rows = ""
    for e in candidates:
        ticker    = e["ticker"]
        cur       = e["current_price"]
        ez        = e["entry_price"]
        dist_pts  = e["distance_to_constitutional"]
        need_pct  = e["need_move_pct"]
        cur_s     = f'{cur:.2f}' if cur else "—"
        ez_s      = f'{ez:.2f}' if ez else "—"
        zone_s    = "AT ZONE" if need_pct < 0.5 else f'+{need_pct:.1f}% above current'
        waiting   = f"−{dist_pts:.1f} pts to R2 gate"
        urg_c     = G if dist_pts <= 2 else (A if dist_pts <= 5 else DIM)
        rows += f"""
<tr>
  <td style="font-weight:700;color:{B};font-size:14px;">{ticker}</td>
  <td style="color:{FG};">{cur_s}</td>
  <td style="color:{W};font-weight:700;">{ez_s}</td>
  <td style="color:{urg_c};font-weight:700;">{60-dist_pts:.1f} / 60 &nbsp;(&#8722;{dist_pts:.1f})</td>
  <td style="color:{A};font-size:12px;">{zone_s}</td>
  <td style="color:{DIM};font-size:11px;max-width:200px;">{waiting}</td>
</tr>"""

    return f"""
<div class="card" style="border-color:{A}44;">
  <div class="section-title" style="color:{A};">
    &#127919; NEAR CONSTITUTIONAL ENTRY &nbsp;<span style="font-weight:400;font-size:11px;">
    — price &#8804; entry zone &amp; R2 within 10 pts of gate</span>
    &nbsp;<span style="float:right;font-size:11px;color:{DIM};">{len(candidates)} tickers</span>
  </div>
  <div class="tbl-wrap">
    <table>
      <tr><th>Ticker</th><th>Current</th><th>Entry Zone</th><th>R2 Progress</th><th>Zone Position</th><th>Waiting For</th></tr>
      {rows}
    </table>
  </div>
</div>"""


# ── Future Opportunities ──────────────────────────────────────────────────────
# Universe members below constitutional threshold: not yet in discount + R2 range.
# buy_signal_tickers and near_tickers excluded — each ticker appears once only.
def _s_future_opportunities(snap, excluded: frozenset = frozenset()) -> str:
    uni = snap.universe_snapshot or []
    near_tickers = {e["ticker"] for e in snap.approaching_entries}

    def _qualifies(r):
        status  = r.get("status", "")
        ticker  = r["ticker"]
        if ticker in near_tickers or ticker in excluded:
            return False
        if status in ("PREMIUM", "ACTIVE"):
            return False
        if status in ("BELOW_THRESHOLD", "APPROACHING", "NO_HISTORY", "NO_DATA"):
            return True
        return False

    candidates = sorted(
        [r for r in uni if _qualifies(r)],
        key=lambda r: (60 - (r.get("r2_score") or 0))
    )

    if not candidates:
        return ""

    rows = ""
    for r in candidates:
        ticker  = r["ticker"]
        cur     = r.get("current_price")
        ez      = r.get("entry_zone")
        r2      = r.get("r2_score") or 0.0
        score   = r.get("final_score") or 0.0
        cur_s   = f'{cur:.2f}' if cur else "—"
        if ez:
            ez_s = f'{ez:.2f}'
            if cur and cur > 0:
                need_pct = (ez - cur) / cur * 100
                need_s = f'{need_pct:+.1f}%' if abs(need_pct) >= 0.5 else "AT ZONE"
            else:
                need_s = "—"
        else:
            ez_s   = "Awaiting Entry Zone"
            need_s = "—"
        r2_s    = f'{r2:.1f}' if r2 else "—"
        score_s = f'{score:.1f}' if score else "—"
        reason  = r.get("reason") or "—"
        mem_s   = "&#9733;" if r.get("memory") else ""
        rows += f"""
<tr>
  <td style="font-weight:700;color:{B};font-size:13px;">{ticker}</td>
  <td style="color:{FG};">{cur_s}</td>
  <td style="color:{W};">{ez_s}</td>
  <td style="color:{DIM};">{need_s}</td>
  <td style="color:{P};">{r2_s}</td>
  <td style="color:{DIM};">{score_s}</td>
  <td style="color:{DIM};font-size:11px;max-width:180px;">{reason}</td>
  <td style="color:{A};font-size:13px;">{mem_s}</td>
</tr>"""

    return f"""
<div class="card" style="border-color:{P}44;">
  <details>
    <summary>
      <div class="section-title" style="margin-bottom:0;cursor:pointer;color:{P};display:flex;align-items:center;justify-content:space-between;">
        <span>&#128197; FUTURE CONSTITUTIONAL CANDIDATES &nbsp;<span style="font-weight:400;font-size:11px;">— building R2 / awaiting discount</span></span>
        <span style="font-size:11px;color:{DIM};">{len(candidates)} tickers &nbsp;&#9660;</span>
      </div>
    </summary>
    <div style="margin-top:12px;" class="tbl-wrap">
      <table>
        <tr><th>Ticker</th><th>Current</th><th>Entry Zone</th><th>Need Move</th><th>R2</th><th>Score</th><th>Waiting For</th><th>Mem</th></tr>
        {rows}
      </table>
    </div>
  </details>
</div>"""


# ── Universe Status ───────────────────────────────────────────────────────────
def _s_universe_status(snap) -> str:
    rows_data = snap.universe_snapshot
    if not rows_data:
        return ""
    total = len(rows_data)

    def _status_badge(status):
        color_map = {
            "PREMIUM":         G,
            "ACTIVE":          B,
            "UNDER_REVIEW":    A,
            "APPROACHING":     P,
            "BELOW_THRESHOLD": DIM,
            "NO_DATA":         DIM,
            "NO_HISTORY":      DIM,
        }
        c = color_map.get(status, DIM)
        label = status.replace("_", " ")
        return f'<span class="badge" style="background:{c}22;color:{c};">{label}</span>'

    rows_html = ""
    for r in sorted(rows_data, key=lambda x: (
        {"PREMIUM": 0, "ACTIVE": 1, "UNDER_REVIEW": 2, "APPROACHING": 3,
         "BELOW_THRESHOLD": 4, "NO_DATA": 5, "NO_HISTORY": 6}.get(x["status"], 9)
    )):
        cur     = f'{r["current_price"]:.2f}' if r.get("current_price") else "—"
        ez      = f'{r["entry_zone"]:.2f}' if r.get("entry_zone") else "Awaiting EZ"
        dist    = f'{r["distance"]:+.1f}%' if r.get("distance") is not None else "—"
        ret     = r.get("return_pct")
        ret_html = (
            f'<span class="{_rc(ret)}">{_sign(ret)}{ret:.1f}%</span>'
            if ret is not None else "—"
        )
        reason  = r.get("reason") or ""
        action  = r.get("action") or "—"
        mem     = "&#9733;" if r.get("memory") else ""
        upd     = (r.get("last_price_update") or "")[:10]
        rows_html += f"""
<tr>
  <td style="font-weight:700;color:{B};font-size:13px;">{r['ticker']}</td>
  <td style="color:{FG};">{cur}</td>
  <td>{_status_badge(r['status'])}</td>
  <td style="color:{W};font-weight:600;">{ez}</td>
  <td>{ret_html}</td>
  <td style="color:{DIM};font-size:11px;max-width:200px;">{reason}</td>
  <td style="color:{A};font-size:13px;">{mem}</td>
  <td style="color:{FG};font-size:12px;">{action}</td>
  <td style="color:{DIM};font-size:11px;">{upd}</td>
</tr>"""

    return f"""
<div class="card">
  <details>
    <summary>
      <div class="section-title" style="margin-bottom:0;cursor:pointer;display:flex;align-items:center;justify-content:space-between;">
        <span>&#127758; Universe Status ({total} / 27)</span>
        <span style="font-size:11px;color:{DIM};">&#9660; expand</span>
      </div>
    </summary>
    <div style="margin-top:12px;" class="tbl-wrap">
      <table>
        <tr>
          <th>Ticker</th><th>Current</th><th>Status</th><th>Entry Zone</th>
          <th>Return %</th><th>Reason / Waiting For</th><th>Mem</th>
          <th>Action</th><th>Last Update</th>
        </tr>
        {rows_html}
      </table>
    </div>
  </details>
</div>"""


# ── Market Map (constitutional holders) ──────────────────────────────────────
def _s_market_map(snap, dna):
    if not snap.timeline:
        return ""
    by_ticker = {}
    for e in snap.timeline:
        t = e["ticker"]
        if t not in by_ticker or e["event_date"] > by_ticker[t]["event_date"]:
            by_ticker[t] = e

    def _status(ret):
        if ret >= 50:  return ("PREMIUM", G)
        elif ret >= 0: return ("ACTIVE", B)
        else:          return ("UNDER REVIEW", R)

    def _action(ret):
        if ret >= 50:  return f'<span style="color:{G};font-weight:700;">HOLD — TARGET HIT</span>'
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
        rows += f"""
<tr>
  <td style="font-weight:700;color:{B};font-size:14px;">{ticker}</td>
  <td><span class="badge" style="background:{sc}22;color:{sc};">{lbl}</span></td>
  <td style="color:{W};font-weight:700;">{e['entry_price']:.2f} EGP</td>
  <td style="color:{FG};">{e['current_price']:.2f}</td>
  <td class="{_rc(ret)}">{_sign(ret)}{ret:.1f}%</td>
  <td>{_action(ret)}</td>
  <td style="color:{A};font-size:13px;">{_memory(ticker)}</td>
</tr>"""

    return f"""
<div class="card">
  <details>
    <summary>
      <div class="section-title" style="margin-bottom:0;cursor:pointer;display:flex;align-items:center;justify-content:space-between;">
        <span>&#128506; Constitutional Holders — Market Map ({len(by_ticker)} tickers)</span>
        <span style="font-size:11px;color:{DIM};">&#9660; expand</span>
      </div>
    </summary>
    <div style="margin-top:12px;" class="tbl-wrap">
      <table>
        <tr><th>Ticker</th><th>Status</th><th>Entry</th><th>Current</th><th>Return %</th><th>Action</th><th>Memory</th></tr>
        {rows}
      </table>
    </div>
  </details>
</div>"""


# ── Stock DNA ─────────────────────────────────────────────────────────────────
def _s_stock_dna(snap, dna):
    if not snap.timeline:
        return ""
    by_ticker = {}
    for e in snap.timeline:
        by_ticker.setdefault(e["ticker"], []).append(e)

    cards = ""
    for ticker, events in sorted(by_ticker.items()):
        ev_sorted = sorted(events, key=lambda e: e["event_date"])
        first_buy = next((e for e in ev_sorted if e["event_type"] == "FIRST_BUY"), ev_sorted[0])
        re_accums = [e for e in ev_sorted if e["event_type"] == "RE_ACCUMULATION"]
        prices    = [e["entry_price"] for e in ev_sorted if e["entry_price"]]
        returns   = [e["return_pct"] for e in ev_sorted]
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
                f'→ <span class="{_rc(re["return_pct"])}">{_sign(re["return_pct"])}{re["return_pct"]:.1f}%</span>'
                f'</div>'
            )
        current = ev_sorted[-1]["current_price"]
        sector  = ev_sorted[0].get("sector", "")
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
    &nbsp;·&nbsp; <span style="color:{FG};">Avg Entry:</span> {avg_entry:.2f} EGP
    &nbsp;·&nbsp; <span style="color:{FG};">Current:</span> {current:.2f}
    &nbsp;·&nbsp; <span class="{_rc(avg_ret)}">Avg Return: {_sign(avg_ret)}{avg_ret:.1f}%</span>
  </div>
  <div class="dna-meta">
    <span style="color:{FG};">Buy Zone:</span> {zone_low:.2f} – {zone_high:.2f} EGP
    &nbsp;·&nbsp; <span style="color:{FG};">Events:</span> {len(events)} ({n_buy} BUY · {len(re_accums)} Re-Accum)
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


# ── Full Timeline ─────────────────────────────────────────────────────────────
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
        <span>&#128203; Full Constitutional Timeline ({snap.total_events} events)</span>
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


# ── System Diagnostics ────────────────────────────────────────────────────────
def _s_diagnostics(snap):
    tl_ok       = snap.total_events > 0
    fb_ok       = len(snap.first_buys) > 0
    re_ok       = len(snap.re_accumulations) > 0
    dash_ok     = (BASE / "dashboard.html").exists()
    kb_ok       = snap.knowledge_count > 0
    research_ok = len(snap.research_insights) > 0
    dna_ok      = (BASE / "stock_dna.db").exists()

    def sha(path):
        if not path.exists(): return "--"
        return hashlib.sha256(path.read_bytes()).hexdigest()[:12] + "..."

    scan_cairo = _to_cairo(snap.last_scan_ts)
    gen_cairo  = _to_cairo(snap.generated_at)

    checks = [
        ("Dashboard",      dash_ok,     f"dashboard.html · {sha(BASE / 'dashboard.html')}"),
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

    data_rows = (
        f'<tr><td style="color:{DIM};font-size:12px;padding:5px 0;">Timeline Events</td>'
        f'<td style="color:{G if tl_ok else R};font-size:12px;font-weight:600;padding:5px 8px;">'
        f'{snap.total_events} ({len(snap.first_buys)} First BUY · {len(snap.re_accumulations)} Re-Accum)</td></tr>'
        f'<tr><td style="color:{DIM};font-size:12px;padding:5px 0;">Universe</td>'
        f'<td style="color:{FG};font-size:12px;font-weight:600;padding:5px 8px;">{snap.universe_size} tickers</td></tr>'
        f'<tr><td style="color:{DIM};font-size:12px;padding:5px 0;">Approaching</td>'
        f'<td style="color:{A};font-size:12px;font-weight:600;padding:5px 8px;">{len(snap.approaching_entries)} tickers</td></tr>'
        f'<tr><td style="color:{DIM};font-size:12px;padding:5px 0;">Last Scan (Cairo)</td>'
        f'<td style="color:{DIM};font-size:12px;font-weight:600;padding:5px 8px;">{scan_cairo}</td></tr>'
        f'<tr><td style="color:{DIM};font-size:12px;padding:5px 0;">Generated (Cairo)</td>'
        f'<td style="color:{DIM};font-size:12px;font-weight:600;padding:5px 8px;">{gen_cairo}</td></tr>'
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


# ── Operations Center ─────────────────────────────────────────────────────────
def _s_operations_center() -> str:
    """Operations Center — collapsed when HEALTHY, auto-expanded on WARNING+."""
    try:
        from operations.heartbeat import read_heartbeat, compute_next_scan
        from operations.incident  import list_open_incidents, incident_summary, list_recent
        from operations.health    import system_health
        from operations.sla       import compute_metrics, reliability_label
        hb       = read_heartbeat()
        open_inc = list_open_incidents()
        health   = system_health(hb, open_inc)
        sla30    = compute_metrics(30)
        recent_i = list_recent(5)
    except Exception:
        hb = {}; open_inc = []; health = {"status": "UNKNOWN", "reasons": [], "checks": {}}
        sla30 = {}; recent_i = []

    status     = health.get("status", "UNKNOWN")
    status_c   = {
        "HEALTHY": G, "WARNING": A, "DEGRADED": R, "CRITICAL": R, "UNKNOWN": DIM
    }.get(status, DIM)
    status_icon = {"HEALTHY": "✅", "WARNING": "⚠️", "DEGRADED": "🔴", "CRITICAL": "🚨"}.get(status, "❓")

    # ── Minimal footer (always visible) ───────────────────────────────────────
    last_scan  = _to_cairo(hb.get("last_scan", ""))
    last_email = _to_cairo(hb.get("last_email", ""))
    last_dash  = _to_cairo(hb.get("last_dashboard", ""))
    next_scan  = _to_cairo(compute_next_scan())  # always live from time_authority, never stale heartbeat
    rel_pct    = sla30.get("overall_pct")
    rel_label  = reliability_label(rel_pct)
    snap_fresh = "✓ Fresh" if hb.get("last_snapshot") else "—"
    data_fresh = "✓ Fresh" if hb.get("last_scan") else "—"

    footer_html = f"""
<div style="display:flex;flex-wrap:wrap;gap:16px;justify-content:center;
  font-family:monospace;font-size:11px;color:{DIM};padding:12px 0;">
  <span>{status_icon} <b style="color:{status_c};">{status}</b></span>
  <span>🕐 Last Scan: <b style="color:{FG};">{last_scan or '—'}</b></span>
  <span>⏭ Next: <b style="color:{FG};">{next_scan or '—'}</b></span>
  <span>📧 Morning Report: <b style="color:{FG};">{last_email or '—'}</b></span>
  <span>📊 Data: <b style="color:{G if hb.get('last_scan') else DIM};">{data_fresh}</b></span>
  <span>📈 Reliability: <b style="color:{G if rel_pct and rel_pct>=99 else (A if rel_pct and rel_pct>=95 else DIM)};">{rel_label}</b></span>
</div>"""

    if status == "HEALTHY" and not open_inc:
        return f"""
<div style="border-top:1px solid {BOR};margin-top:8px;">
  {footer_html}
</div>"""

    # ── Expanded operations center (WARNING / DEGRADED / CRITICAL) ─────────────
    reasons_html = ""
    if health.get("reasons"):
        reasons_html = "".join(
            f'<div style="color:{R};font-size:12px;padding:2px 0;">⚠ {r}</div>'
            for r in health["reasons"]
        )

    # Incidents table
    inc_rows = ""
    for i in open_inc:
        t_c  = R if i["status"] in ("OPEN", "DIAGNOSED") else A
        inc_rows += (
            f'<tr><td style="font-size:11px;padding:4px 6px;color:{t_c};">{i["type"]}</td>'
            f'<td style="font-size:11px;padding:4px 6px;color:{DIM};">{i["status"]}</td>'
            f'<td style="font-size:11px;padding:4px 6px;color:{DIM};">'
            f'{_to_cairo(i["opened_at"])}</td>'
            f'<td style="font-size:11px;padding:4px 6px;color:{DIM};">'
            f'{i["notes"][-1][:60] if i["notes"] else ""}</td></tr>'
        )
    if not inc_rows:
        inc_rows = f'<tr><td colspan=4 style="color:{G};font-size:11px;padding:4px;">No open incidents</td></tr>'
    inc_table = f"""
<div style="font-size:11px;color:{DIM};text-transform:uppercase;letter-spacing:.4px;margin:10px 0 4px;">Open Incidents ({len(open_inc)})</div>
<div class="tbl-wrap"><table style="min-width:400px;">
  <tr><th>Type</th><th>Status</th><th>Opened</th><th>Note</th></tr>
  {inc_rows}
</table></div>"""

    # Recent incident history
    hist_rows = ""
    for i in recent_i:
        c = G if i["status"] == "CLOSED" else (R if i["status"] == "OPEN" else A)
        hist_rows += (
            f'<tr><td style="font-size:11px;padding:3px 6px;color:{c};">{i["type"]}</td>'
            f'<td style="font-size:11px;padding:3px 6px;color:{DIM};">{i["status"]}</td>'
            f'<td style="font-size:11px;padding:3px 6px;color:{DIM};">'
            f'{_to_cairo(i["opened_at"])[:16]}</td></tr>'
        )
    if hist_rows:
        hist_rows = f"""
<div style="font-size:11px;color:{DIM};text-transform:uppercase;letter-spacing:.4px;margin:10px 0 4px;">Recent History</div>
<div class="tbl-wrap"><table style="min-width:300px;">
  <tr><th>Type</th><th>Status</th><th>Time</th></tr>{hist_rows}
</table></div>"""

    # SLA metrics
    def _sla_row(label, m):
        if not m or m.get("total", 0) == 0:
            return f'<tr><td style="font-size:11px;color:{DIM};padding:3px 6px;">{label}</td><td style="font-size:11px;color:{DIM};padding:3px 6px;">No data</td></tr>'
        pct = m.get("pct")
        c   = G if pct and pct >= 99 else (A if pct and pct >= 95 else R)
        return (
            f'<tr><td style="font-size:11px;color:{DIM};padding:3px 6px;">{label}</td>'
            f'<td style="font-size:11px;color:{c};font-weight:700;padding:3px 6px;">'
            f'{pct:.1f}% ({m["success"]}/{m["total"]})</td></tr>'
        )
    sla_table = f"""
<div style="font-size:11px;color:{DIM};text-transform:uppercase;letter-spacing:.4px;margin:10px 0 4px;">SLA (30d)</div>
<table style="min-width:200px;">
  {_sla_row("Morning Reports", sla30.get("morning"))}
  {_sla_row("Scans", sla30.get("scans"))}
  {_sla_row("Dashboards", sla30.get("dashboards"))}
  {_sla_row("Deployments", sla30.get("deployments"))}
  {_sla_row("Validations", sla30.get("validations"))}
  {_sla_row("Recoveries", sla30.get("recoveries"))}
</table>"""

    # Heartbeat details
    hb_html = (
        f'<div style="font-size:11px;color:{DIM};text-transform:uppercase;letter-spacing:.4px;margin:10px 0 4px;">Heartbeat</div>'
        f'<table style="min-width:200px;">'
        + "".join(
            f'<tr><td style="font-size:11px;color:{DIM};padding:3px 6px;">{k}</td>'
            f'<td style="font-size:11px;color:{FG};padding:3px 6px;font-family:monospace;">'
            f'{_to_cairo(str(v)) if "at" in k or "scan" in k or "email" in k or "dashboard" in k or "snapshot" in k or "validation" in k else v}</td></tr>'
            for k, v in hb.items()
            if k not in ("notes",)
        )
        + "</table>"
    )

    open_attr = ' open' if status != "HEALTHY" else ''
    return f"""
<div class="card" style="border-color:{status_c}30;">
  <details{open_attr}>
    <summary style="cursor:pointer;list-style:none;">
      <div class="section-title" style="margin-bottom:0;display:flex;align-items:center;justify-content:space-between;">
        <span>⚙️ Operations Center
          <span class="badge" style="background:{status_c}22;color:{status_c};margin-left:8px;">{status_icon} {status}</span>
          {f'<span class="badge" style="background:{R}22;color:{R};margin-left:4px;">{len(open_inc)} incidents</span>' if open_inc else ''}
        </span>
        <span style="font-size:11px;color:{DIM};">▼ expand</span>
      </div>
    </summary>
    <div style="margin-top:14px;">
      {reasons_html}
      {footer_html}
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:12px;">
        <div>{inc_table}{hist_rows}</div>
        <div>{sla_table}{hb_html}</div>
      </div>
    </div>
  </details>
</div>"""


# ── Section mutual-exclusivity assertion ─────────────────────────────────────
def _assert_sections(snap) -> None:
    uni = snap.universe_snapshot or []
    near_tickers = {e["ticker"] for e in snap.approaching_entries}
    future_tickers = {
        r["ticker"] for r in uni
        if r["ticker"] not in near_tickers
        and r.get("status") in ("BELOW_THRESHOLD", "APPROACHING", "NO_HISTORY", "NO_DATA")
    }
    premium_active = {
        r["ticker"] for r in uni
        if r.get("status") in ("PREMIUM", "ACTIVE")
    }

    overlap_nf = near_tickers & future_tickers
    # Near ∩ Premium/Active overlap is valid: active constitutional holders
    # can simultaneously approach the gate again for re-accumulation.
    assert not overlap_nf, f"Near ∩ Future overlap: {overlap_nf}"


# ── Build ─────────────────────────────────────────────────────────────────────
def build_dashboard(build_hash: str = "") -> str:
    snap = build_presentation_snapshot()
    dna  = _load_stock_dna()

    _assert_sections(snap)

    buy_html, buy_tickers = _s_buy_signals(snap)
    body = (
        _s_stats(snap) +
        buy_html +
        _s_near_entry(snap, buy_tickers) +
        _s_future_opportunities(snap, buy_tickers) +
        _s_universe_status(snap) +
        _s_market_map(snap, dna) +
        _s_stock_dna(snap, dna) +
        _s_timeline(snap) +
        _s_diagnostics(snap) +
        _s_operations_center()
    )
    gen_cairo = _build_time()
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<meta http-equiv="Pragma" content="no-cache">
<meta http-equiv="Expires" content="0">
<title>EGX Constitutional Command Center</title>
<style>{CSS}</style>
</head>
<body data-hash="{build_hash}">
{_s_sticky_header(snap, build_hash)}
<div class="wrap">
{body}
<div style="text-align:center;font-size:11px;color:{DIM};padding:16px 0;margin-top:8px;border-top:1px solid {BOR};">
  EGX Constitutional Command Center &nbsp;·&nbsp; Append-Only · Immutable Events · No Portfolio Dependency
  <br><span style="font-family:monospace;font-size:10px;opacity:.6;">
  dashboard.py v7 &nbsp;·&nbsp; {gen_cairo} &nbsp;·&nbsp; commit $COMMIT_MARKER$
  </span>
</div>
</div>
{JS}
</body>
</html>"""


if __name__ == "__main__":
    import subprocess
    from universe_snapshot import build_universe_snapshot
    from stock_dna_engine import build_stock_dna

    build_universe_snapshot()
    build_stock_dna()

    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        commit = "unknown"

    html_raw = build_dashboard()
    html     = html_raw.replace("$COMMIT_MARKER$", commit)

    build_hash = hashlib.sha256(html.encode()).hexdigest()[:16]
    # Embed hash in data-hash attribute and header
    html = html.replace('data-hash=""', f'data-hash="{build_hash}"')

    out = BASE / "dashboard.html"
    out.write_text(html, encoding="utf-8")

    version_data = {
        "version": "7.0",
        "commit": commit,
        "build_hash": build_hash,
        "generated_at": _build_time(),
        "universe_count": 27,
    }
    (BASE / "version.json").write_text(_json.dumps(version_data, indent=2))

    sha256 = hashlib.sha256(html.encode()).hexdigest()
    print(f"[Dashboard V7] Saved dashboard.html ({len(html)//1024} KB)")
    print(f"[Dashboard V7] build_hash: {build_hash}")
    print(f"[Dashboard V7] SHA256: {sha256[:32]}...")
    print(f"[Dashboard V7] Commit: {commit}")
    print(f"[Dashboard V7] version.json written (v7.0)")

    # Write canonical presentation_snapshot.json
    from presentation.presentation_snapshot import build_presentation_snapshot, write_presentation_snapshot_json
    snap_check = build_presentation_snapshot()
    write_presentation_snapshot_json(snap_check, build_hash=build_hash)
    uni = snap_check.universe_snapshot or []
    snap_check = snap_check  # already assigned above
    near = [r["ticker"] for r in uni if (60-(r.get("r2_score") or 0))<=10
            and not (r.get("current_price") and r.get("entry_zone") and r["current_price"] > r["entry_zone"])]
    bad = [t for t in ["COMI.CA","ORHD.CA","HELI.CA","EMFD.CA","JUFO.CA","PHDC.CA","ARCC.CA"] if t in near]
    print(f"[Dashboard V7] Near Entry tickers: {near}")
    print(f"[Dashboard V7] Removed tickers in Near Entry (MUST BE EMPTY): {bad}")
    assert not bad, f"VIOLATION: removed tickers still in Near Entry: {bad}"
    print(f"[Dashboard V7] ✓ All assertions PASS")
