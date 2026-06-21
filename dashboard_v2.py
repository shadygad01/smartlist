"""
EGX Constitutional Opportunity Intelligence Platform — Dashboard V4
Runtime header · No portfolio · No capacity · No R2 degradation.
Health stars → System Diagnostics (last section only).
"""
from __future__ import annotations

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
ORG = "#ff8c42"

CSS = f"""
body{{margin:0;padding:0;background:{BG0};font-family:'Segoe UI',Arial,sans-serif;color:{FG};}}
.wrap{{max-width:1240px;margin:0 auto;padding:24px 16px;}}
.card{{background:{BG1};border:1px solid {BOR};border-radius:10px;padding:20px;margin-bottom:18px;}}
.section-title{{font-size:13px;font-weight:700;letter-spacing:0.6px;text-transform:uppercase;
  color:{DIM};margin-bottom:14px;border-bottom:1px solid {BOR};padding-bottom:8px;}}
.badge{{display:inline-block;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:700;}}
table{{width:100%;border-collapse:collapse;font-size:13px;}}
th{{text-align:left;padding:8px 10px;color:{DIM};font-size:11px;font-weight:700;
  letter-spacing:0.4px;text-transform:uppercase;border-bottom:1px solid {BOR};}}
td{{padding:7px 10px;border-bottom:1px solid {BOR};color:{FG};}}
tr:last-child td{{border-bottom:none;}}
.pos{{color:{G};font-weight:700;}} .neg{{color:{R};font-weight:700;}} .neu{{color:{A};font-weight:700;}}
.metric-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:12px;}}
.metric-cell{{background:{BG2};border:1px solid {BOR};border-radius:8px;padding:14px;}}
.metric-val{{font-size:22px;font-weight:700;margin-bottom:4px;}}
.metric-lbl{{font-size:11px;color:{DIM};text-transform:uppercase;letter-spacing:0.4px;}}
.bar-bg{{background:{BG2};border-radius:4px;height:8px;overflow:hidden;margin-top:4px;}}
.bar-fill{{height:8px;border-radius:4px;}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:18px;}}
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

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

def _confidence_badge(conf: str) -> str:
    colors = {"ELITE": G, "STRONG": B, "CONFIRMED": A, "DEVELOPING": DIM}
    c = colors.get(conf, DIM)
    icons = {"ELITE": "★★★★", "STRONG": "★★★☆", "CONFIRMED": "★★☆☆", "DEVELOPING": "★☆☆☆"}
    icon = icons.get(conf, "★☆☆☆")
    return f'<span class="badge" style="background:{c}22;color:{c};">{icon} {conf}</span>'

def _market_color(status: str) -> str:
    if "OPEN" in status and "PRE" not in status: return G
    if "PRE" in status: return A
    return DIM

def _cairo_now() -> str:
    tz = timezone(timedelta(hours=2))
    return datetime.now(tz).strftime("%H:%M Cairo")


# ── Section 1: Runtime Header ─────────────────────────────────────────────────

def _s_runtime_header(snap: PresentationSnapshot) -> str:
    now_str = datetime.now().strftime("%A, %d %B %Y")
    mcolor  = _market_color(snap.market_status)
    premium = sum(1 for e in snap.timeline if e.get("status") == "PREMIUM_NOW")
    active  = sum(1 for e in snap.timeline if e.get("status") == "ACTIVE_OPPORTUNITY")
    review  = sum(1 for e in snap.timeline if e.get("status") == "UNDER_REVIEW")
    new_tag = (
        f'<span style="background:{G}22;color:{G};padding:3px 10px;border-radius:12px;'
        f'font-size:12px;font-weight:700;margin-left:10px;">⚡ {len(snap.new_events_today)} NEW TODAY</span>'
    ) if snap.new_events_today else ""
    approach_tag = (
        f'<span style="background:{A}22;color:{A};padding:3px 10px;border-radius:12px;'
        f'font-size:12px;font-weight:700;margin-left:6px;">🔍 {len(snap.approaching_entries)} APPROACHING</span>'
    ) if snap.approaching_entries else ""

    scan_str = ""
    if snap.last_scan_ts:
        try:
            ts = snap.last_scan_ts.replace("T", " ")[:16]
            scan_str = f'Last scan: {ts}'
        except Exception:
            scan_str = snap.last_scan_ts[:16]

    return f"""
<div style="background:linear-gradient(135deg,{BG1} 0%,#0d0f22 100%);
     border:1px solid {BOR};border-radius:12px;padding:28px;margin-bottom:18px;">
  <div style="display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:12px;">
    <div>
      <div style="font-size:10px;color:{DIM};text-transform:uppercase;letter-spacing:1.2px;margin-bottom:8px;">
        EGX Constitutional Opportunity Intelligence Platform
      </div>
      <div style="font-size:26px;font-weight:700;color:{W};letter-spacing:-0.5px;">
        Constitutional Opportunity Timeline
      </div>
      <div style="margin-top:10px;display:flex;flex-wrap:wrap;gap:6px;align-items:center;">
        {new_tag}{approach_tag}
      </div>
    </div>
    <div style="text-align:right;font-size:12px;">
      <div style="color:{W};font-size:14px;font-weight:600;">{now_str} &nbsp;·&nbsp; {_cairo_now()}</div>
      <div style="margin-top:6px;">
        <span style="color:{mcolor};font-weight:700;">⬤ EGX {snap.market_status}</span>
      </div>
      <div style="margin-top:8px;color:{DIM};font-size:11px;">{scan_str}</div>
      <div style="margin-top:6px;color:{DIM};font-size:11px;">
        Universe: <span style="color:{B};font-weight:700;">{snap.universe_size}</span> tickers
      </div>
    </div>
  </div>
  <div style="margin-top:18px;display:grid;grid-template-columns:repeat(6,1fr);gap:10px;">
    {''.join([
        f'<div style="background:{BG2};border:1px solid {BOR};border-radius:8px;padding:12px;text-align:center;">'
        f'<div style="font-size:20px;font-weight:700;color:{col};">{val}</div>'
        f'<div style="font-size:10px;color:{DIM};text-transform:uppercase;letter-spacing:0.4px;margin-top:3px;">{lbl}</div>'
        f'</div>'
        for val, lbl, col in [
            (snap.total_events, "Total Events", W),
            (snap.total_tickers, "Tickers", B),
            (len(snap.first_buys), "First BUYs", B),
            (len(snap.re_accumulations), "Re-Accum", P),
            (premium, "Premium", G),
            (active, "Active", A),
        ]
    ])}
  </div>
</div>"""


# ── Section 2: Executive Summary ──────────────────────────────────────────────

def _s_exec_summary(snap: PresentationSnapshot) -> str:
    tl = snap.timeline
    best_e = max(tl, key=lambda e: e["return_pct"]) if tl else None
    most_rep = snap.leaderboards.get("most_repeated", [{}])[0] if snap.leaderboards else {}
    top_leader = snap.constitutional_leaders[0] if snap.constitutional_leaders else {}
    rets = [e["return_pct"] for e in tl] if tl else []
    avg_ret = sum(rets) / len(rets) if rets else 0.0
    wins = sum(1 for r in rets if r > 0)
    win_rate = wins / len(rets) * 100 if rets else 0.0

    best_block = ""
    if best_e:
        best_block = (
            f'<div style="background:{G}11;border:1px solid {G}44;border-radius:8px;padding:12px;margin-top:10px;">'
            f'<div style="font-size:11px;color:{DIM};text-transform:uppercase;letter-spacing:0.4px;margin-bottom:4px;">'
            f'Best Performing Event</div>'
            f'<span style="font-size:16px;font-weight:700;color:{G};">{best_e["ticker"]}</span>'
            f'&nbsp;<span style="color:{G};font-weight:700;">{_sign(best_e["return_pct"])}{best_e["return_pct"]:.1f}%</span>'
            f'&nbsp;<span style="color:{DIM};font-size:11px;">from {best_e["event_date"]}'
            f' · entry {best_e["entry_price"]:.2f} EGP · peak {_sign(best_e["peak_return_pct"])}{best_e["peak_return_pct"]:.1f}%</span>'
            f'</div>'
        )

    most_rep_block = ""
    if most_rep:
        most_rep_block = (
            f'<div style="background:{P}11;border:1px solid {P}44;border-radius:8px;padding:12px;margin-top:10px;">'
            f'<div style="font-size:11px;color:{DIM};text-transform:uppercase;letter-spacing:0.4px;margin-bottom:4px;">'
            f'Most Repeated Constitutional Opportunity</div>'
            f'<span style="font-size:16px;font-weight:700;color:{P};">{most_rep.get("ticker","—")}</span>'
            f'&nbsp;<span style="color:{DIM};font-size:12px;">{most_rep.get("total_events",0)} events'
            f' · avg {_sign(most_rep.get("avg_return_pct",0))}{most_rep.get("avg_return_pct",0):.1f}%</span>'
            f'</div>'
        )

    conf_block = ""
    if top_leader:
        conf_block = (
            f'<div style="background:{B}11;border:1px solid {B}44;border-radius:8px;padding:12px;margin-top:10px;">'
            f'<div style="font-size:11px;color:{DIM};text-transform:uppercase;letter-spacing:0.4px;margin-bottom:4px;">'
            f'Highest Constitutional Confidence</div>'
            f'<span style="font-size:16px;font-weight:700;color:{B};">{top_leader.get("ticker","—")}</span>'
            f'&nbsp;{_confidence_badge(top_leader.get("confidence","DEVELOPING"))}'
            f'&nbsp;<span style="color:{DIM};font-size:11px;">{top_leader.get("total_events",0)} events'
            f' · win rate {top_leader.get("win_rate",0)*100:.0f}%</span>'
            f'</div>'
        )

    avg_c = G if avg_ret >= 0 else R
    return f"""
<div class="card">
  <div class="section-title">📊 Executive Summary — Constitutional Opportunity Intelligence</div>
  <div class="metric-grid">
    <div class="metric-cell">
      <div class="metric-val" style="color:{W};">{snap.universe_size}</div>
      <div class="metric-lbl">Universe (Tracked)</div>
    </div>
    <div class="metric-cell">
      <div class="metric-val" style="color:{B};">{len(snap.first_buys)}</div>
      <div class="metric-lbl">First BUY Events</div>
    </div>
    <div class="metric-cell">
      <div class="metric-val" style="color:{P};">{len(snap.re_accumulations)}</div>
      <div class="metric-lbl">Re-Accumulations</div>
    </div>
    <div class="metric-cell">
      <div class="metric-val" style="color:{snap.universe_size and A};">{len(snap.approaching_entries)}</div>
      <div class="metric-lbl">Approaching Entry</div>
    </div>
    <div class="metric-cell">
      <div class="metric-val" style="color:{avg_c};">{avg_ret:+.1f}%</div>
      <div class="metric-lbl">Avg Return / Event</div>
    </div>
    <div class="metric-cell">
      <div class="metric-val" style="color:{G};">{win_rate:.0f}%</div>
      <div class="metric-lbl">Win Rate</div>
    </div>
  </div>
  {best_block}
  <div class="grid2" style="margin-top:0;">
    <div>{most_rep_block}</div>
    <div>{conf_block}</div>
  </div>
</div>"""


# ── Section 3: New Events Today ───────────────────────────────────────────────

def _s_new_today(snap: PresentationSnapshot) -> str:
    if not snap.new_events_today:
        return ""
    rows = ""
    for e in snap.new_events_today:
        ret_c = G if e.get("return_pct", 0) >= 0 else R
        rows += f"""
<tr>
  <td>{_type_badge(e['event_type'])}</td>
  <td style="font-weight:700;color:{G};font-size:14px;">{e['ticker']}</td>
  <td style="color:{DIM};">{e['sector']}</td>
  <td style="color:{W};font-weight:700;">R2={e['buy_r2']:.1f}</td>
  <td style="color:{FG};">Score={e['buy_score']:.1f}</td>
  <td style="color:{W};font-weight:700;">{e['entry_price']:.2f} EGP</td>
  <td style="color:{FG};">{e.get('current_price', e['entry_price']):.2f} EGP</td>
  <td class="{_rc(e.get('return_pct',0))}">{_sign(e.get('return_pct',0))}{e.get('return_pct',0):.1f}%</td>
</tr>"""
    return f"""
<div class="card" style="border-color:{G}44;background:{G}08;">
  <div class="section-title" style="color:{G};">⚡ New Constitutional Events Today ({len(snap.new_events_today)})</div>
  <table>
    <tr><th>Type</th><th>Ticker</th><th>Sector</th><th>R2</th><th>Score</th>
        <th>Entry Zone</th><th>Current</th><th>Return</th></tr>
    {rows}
  </table>
</div>"""


# ── Section 4: Constitutional Leaders ────────────────────────────────────────

def _s_leaders(snap: PresentationSnapshot) -> str:
    if not snap.constitutional_leaders:
        return ""
    rows = ""
    for i, ldr in enumerate(snap.constitutional_leaders, 1):
        ret_c = _rc(ldr["current_ret"])
        rows += f"""
<tr>
  <td style="color:{DIM};font-size:11px;">{i}</td>
  <td style="font-weight:700;color:{B};font-size:14px;">{ldr['ticker']}</td>
  <td style="color:{DIM};font-size:11px;">{ldr['sector']}</td>
  <td style="color:{P};font-weight:700;">{ldr['total_events']}</td>
  <td class="{_rc(ldr['avg_return_pct'])}">{_sign(ldr['avg_return_pct'])}{ldr['avg_return_pct']:.1f}%</td>
  <td style="color:{FG};">{ldr['current_price']:.2f}</td>
  <td class="{ret_c}">{_sign(ldr['current_ret'])}{ldr['current_ret']:.1f}%</td>
  <td style="color:{G};">{_sign(ldr['peak_ret'])}{ldr['peak_ret']:.1f}%</td>
  <td style="color:{G};">{ldr['win_rate']*100:.0f}%</td>
  <td>{_confidence_badge(ldr['confidence'])}</td>
</tr>"""
    return f"""
<div class="card">
  <div class="section-title">🏆 Constitutional Leaders — Track Record by Ticker</div>
  <table>
    <tr><th>#</th><th>Ticker</th><th>Sector</th><th>Events</th>
        <th>Avg Return</th><th>Current</th><th>Latest Ret</th>
        <th>Peak Ret</th><th>Win Rate</th><th>Confidence</th></tr>
    {rows}
  </table>
</div>"""


# ── Section 5: Approaching Constitutional Entry ───────────────────────────────

def _s_approaching(snap: PresentationSnapshot) -> str:
    if not snap.approaching_entries:
        return ""
    rows = ""
    for e in snap.approaching_entries:
        dist = e["distance_to_constitutional"]
        urgency_c = G if dist <= 0.3 else (A if dist <= 1.0 else DIM)
        already_constitutional = any(l["ticker"] == e["ticker"] for l in snap.constitutional_leaders)
        note = f'<span style="color:{P};font-size:10px;">Has constitutional history</span>' if already_constitutional else ""
        rows += f"""
<tr>
  <td style="font-weight:700;color:{B};font-size:14px;">{e['ticker']}</td>
  <td style="color:{DIM};">{e['sector']}</td>
  <td style="color:{W};font-weight:700;">R2={e['r2_score']:.1f}</td>
  <td style="color:{FG};">Score={e['final_score']:.1f}</td>
  <td style="color:{urgency_c};font-weight:700;">–{dist:.1f} pts</td>
  <td style="color:{FG};">{e['entry_price']:.2f} EGP</td>
  <td style="color:{FG};">{e['current_price']:.2f} EGP</td>
  <td>{note}</td>
</tr>"""
    return f"""
<div class="card" style="border-color:{A}44;">
  <div class="section-title" style="color:{A};">🔍 Approaching Constitutional Entry — R2 50–59.9 + Score ≥ 35</div>
  <div style="font-size:11px;color:{DIM};margin-bottom:12px;">
    Constitutional threshold: R2 ≥ 60 AND Score ≥ 35 simultaneously. These tickers meet the score bar — only R2 gap remains.
  </div>
  <table>
    <tr><th>Ticker</th><th>Sector</th><th>Current R2</th><th>Score</th>
        <th>Distance to Entry</th><th>Entry Zone</th><th>Current Price</th><th>Note</th></tr>
    {rows}
  </table>
</div>"""


# ── Section 6: Full Timeline ──────────────────────────────────────────────────

def _s_timeline(snap: PresentationSnapshot) -> str:
    if not snap.timeline:
        return f'<div class="card"><div style="color:{DIM};">No constitutional events recorded.</div></div>'
    rows = ""
    for e in snap.timeline:
        rows += f"""
<tr>
  <td>{_type_badge(e['event_type'])}</td>
  <td style="font-weight:700;color:{B};">{e['ticker']}</td>
  <td style="color:{DIM};font-size:11px;">{e['event_date']}</td>
  <td style="color:{DIM};">{e['sector']}</td>
  <td style="color:{FG};">{e['entry_price']:.2f}</td>
  <td style="color:{FG};">{e['current_price']:.2f}</td>
  <td class="{_rc(e['return_pct'])}">{_sign(e['return_pct'])}{e['return_pct']:.1f}%</td>
  <td style="color:{G};font-size:12px;">{_sign(e['peak_return_pct'])}{e['peak_return_pct']:.1f}%</td>
  <td style="color:{DIM};font-size:11px;">{e['days_active']}d</td>
  <td>R2={e['buy_r2']:.0f} S={e['buy_score']:.0f}</td>
  <td>{_status_badge(e['status'])}</td>
</tr>"""
    return f"""
<div class="card">
  <div class="section-title">📋 Constitutional Opportunity Timeline — {snap.total_events} Events
    <span style="font-size:11px;color:{DIM};font-weight:400;margin-left:8px;">
      Append-only · Immutable · No capacity · No R2 degradation
    </span>
  </div>
  <table>
    <tr><th>Type</th><th>Ticker</th><th>Signal Date</th><th>Sector</th>
        <th>Entry Zone</th><th>Current</th><th>Return</th>
        <th>Peak Return</th><th>Days</th><th>Signal</th><th>Status</th></tr>
    {rows}
  </table>
</div>"""


# ── Section 7: Leaderboards ───────────────────────────────────────────────────

def _s_leaderboards(snap: PresentationSnapshot) -> str:
    lb = snap.leaderboards
    if not lb:
        return ""

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

    compound = lb.get("compound_return", [])[:8]
    comp_rows = ""
    for i, c in enumerate(compound, 1):
        comp_rows += f"""
<tr>
  <td style="color:{DIM};">{i}</td>
  <td style="font-weight:700;color:{B};">{c['ticker']}</td>
  <td style="color:{DIM};">{c['total_events']}ev</td>
  <td style="color:{DIM};">{c['first_entry']:.2f}</td>
  <td style="color:{FG};">{c['current_price']:.2f}</td>
  <td class="{_rc(c['compound_return_pct'])}">{_sign(c['compound_return_pct'])}{c['compound_return_pct']:.1f}%</td>
</tr>"""

    peak_events = lb.get("highest_peak", [])[:5]
    peak_rows = ""
    for e in peak_events:
        peak_rows += f"""
<tr>
  <td style="font-weight:700;color:{B};">{e['ticker']}</td>
  <td style="color:{DIM};font-size:11px;">{e['event_date']}</td>
  <td>{_type_badge(e['event_type'])}</td>
  <td class="pos">{_sign(e['peak_return_pct'])}{e['peak_return_pct']:.1f}%</td>
  <td class="{_rc(e['return_pct'])}">{_sign(e['return_pct'])}{e['return_pct']:.1f}%</td>
</tr>"""

    return f"""
<div class="card">
  <div class="section-title">📈 Leaderboards</div>
  <div class="grid2">
    <div>
      <div style="font-size:12px;color:{P};font-weight:700;margin-bottom:8px;">Most Repeated Constitutional Opportunities</div>
      <table>
        <tr><th>#</th><th>Ticker</th><th>Sector</th><th>Events</th><th>Avg</th><th>Best</th></tr>
        {rep_rows}
      </table>
    </div>
    <div>
      <div style="font-size:12px;color:{G};font-weight:700;margin-bottom:8px;">Highest Compound Return (First Entry → Today)</div>
      <table>
        <tr><th>#</th><th>Ticker</th><th>Events</th><th>First Entry</th><th>Now</th><th>Compound</th></tr>
        {comp_rows}
      </table>
    </div>
  </div>
  <div style="margin-top:18px;">
    <div style="font-size:12px;color:{A};font-weight:700;margin-bottom:8px;">Highest Peak Return Events</div>
    <table>
      <tr><th>Ticker</th><th>Event Date</th><th>Type</th><th>Peak Ret</th><th>Current Ret</th></tr>
      {peak_rows}
    </table>
  </div>
</div>"""


# ── Section 8: Performance Metrics ───────────────────────────────────────────

def _s_performance(snap: PresentationSnapshot) -> str:
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
<div style="margin-bottom:8px;">
  <div style="display:flex;justify-content:space-between;font-size:12px;">
    <span>{sec}</span>
    <span style="color:{B};font-weight:700;">{cnt} events ({pct:.0f}%)</span>
  </div>
  <div class="bar-bg"><div class="bar-fill" style="width:{min(pct*2,100):.0f}%;background:{B};"></div></div>
</div>"""

    avg_c = G if avg >= 0 else R
    return f"""
<div class="card">
  <div class="section-title">📊 Performance Analytics</div>
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
  <div style="font-size:11px;color:{DIM};text-transform:uppercase;letter-spacing:0.4px;margin-bottom:8px;">
    Sector Distribution (Constitutional Events Only)
  </div>
  {sector_bars}
</div>"""


# ── Section 9: Research ───────────────────────────────────────────────────────

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


# ── Section 10: System Diagnostics (LAST) ────────────────────────────────────

def _s_system_diagnostics(snap: PresentationSnapshot) -> str:
    sc = G if snap.health_stars.count("★") >= 4 else (A if snap.health_stars.count("★") == 3 else R)
    mcolor = _market_color(snap.market_status)

    # Timeline DB validation
    tl_ok = len(snap.timeline) > 0
    tl_c  = G if tl_ok else R
    tl_status = f"✓ {snap.total_events} events · {snap.total_tickers} tickers" if tl_ok else "✗ No events"

    # Universe validation
    univ_ok = snap.universe_size > 0
    univ_c  = G if univ_ok else R

    # Scan timestamp
    scan_str = snap.last_scan_ts[:19].replace("T", " ") if snap.last_scan_ts else "—"

    items = [
        ("Timeline DB",        tl_status,                  tl_c),
        ("Universe",           f"{snap.universe_size} tickers in candidate_pool", G if univ_ok else R),
        ("First BUY Events",   str(len(snap.first_buys)),  B),
        ("Re-Accumulations",   str(len(snap.re_accumulations)), P),
        ("Approaching Entry",  str(len(snap.approaching_entries)), A),
        ("Knowledge Base",     f"{snap.knowledge_count} verified findings", DIM),
        ("Experiments",        str(snap.experiments_running), DIM),
        ("Last Scan",          scan_str,                    DIM),
        ("Market Status",      snap.market_status,          mcolor),
        ("Generated At",       snap.generated_at[:19].replace("T", " "), DIM),
    ]

    rows = ""
    for label, val, col in items:
        rows += (
            f'<tr><td style="color:{DIM};font-size:12px;padding:6px 0;">{label}</td>'
            f'<td style="color:{col};font-size:12px;font-weight:600;padding:6px 8px;">{val}</td></tr>'
        )

    return f"""
<div class="card" style="border-color:{BOR};">
  <div class="section-title">🔧 System Diagnostics</div>
  <div class="grid2">
    <div>
      <table style="font-size:13px;">{rows}</table>
    </div>
    <div>
      <div style="background:{BG2};border:1px solid {BOR};border-radius:8px;padding:16px;">
        <div style="font-size:11px;color:{DIM};text-transform:uppercase;letter-spacing:0.4px;margin-bottom:8px;">
          Portfolio Advisor Health (Informational Only)
        </div>
        <div style="font-size:20px;font-weight:700;color:{sc};">{snap.health_stars} {snap.health_label}</div>
        <div style="font-size:12px;color:{DIM};margin-top:6px;">{snap.health_narrative}</div>
        <div style="margin-top:10px;font-size:10px;color:{DIM};">
          Health stars do not affect constitutional opportunity classification.
          Constitutional BUY status depends only on R2 and Score at signal date.
        </div>
      </div>
    </div>
  </div>
</div>"""


# ── Build ─────────────────────────────────────────────────────────────────────

def build_dashboard() -> str:
    snap = build_presentation_snapshot()
    body = (
        _s_runtime_header(snap) +
        _s_exec_summary(snap) +
        _s_new_today(snap) +
        _s_leaders(snap) +
        _s_approaching(snap) +
        _s_timeline(snap) +
        _s_leaderboards(snap) +
        _s_performance(snap) +
        _s_research(snap) +
        _s_system_diagnostics(snap)
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
  Append-Only &nbsp;·&nbsp; Immutable Events &nbsp;·&nbsp; No Portfolio Dependency &nbsp;·&nbsp;
  {datetime.now().strftime('%d %b %Y %H:%M')}
</div>
</div>
</body>
</html>"""


if __name__ == "__main__":
    out  = Path(__file__).parent / "dashboard.html"
    html = build_dashboard()
    out.write_text(html, encoding="utf-8")
    print(f"[Dashboard V4] Saved → dashboard.html ({len(html)//1024} KB)")
