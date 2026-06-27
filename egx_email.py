"""
EGX Constitutional Command Center — Email V7
Morning Financial Brief — Constitutional Design System

Section order:
  Header → Meta Strip → (1) What Happened Yesterday →
  (2) Last Week Summary → (3) New Since Yesterday →
  (4) Near Constitutional Entry [+Historical Validation +Memory Badge] →
  (5) Active Opportunities [Full Width, Memory Badge] →
  (6) Re-Accumulation Events [Full Width, Memory Badge] →
  (7) Portfolio Health → (8) Constitutional Timeline →
  (9) Constitutional Memory → Footer

Single Source Of Truth: presentation_snapshot (PresentationSnapshot object).
All displayed values flow from build_presentation_snapshot().
Historical validation augmented from stock_dna.db (read-only).
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from presentation.presentation_snapshot import PresentationSnapshot, build_presentation_snapshot
from time_authority import now_cairo as _now_cairo

BASE = Path(__file__).parent

# ── Palette ───────────────────────────────────────────────────────────────────
_NAVY  = "#1a3a5c"
_NAVY2 = "#0d2140"
_GREEN = "#155724"
_G     = "#28a745"
_RED   = "#721c24"
_R     = "#dc3545"
_AMBER = "#856404"
_A     = "#f0b840"
_BLUE  = "#0b4a8f"
_PURPL = "#5b21b6"
_LIGHT = "#f8f9fb"
_BORD  = "#d0d7e2"
_MUTED = "#888888"
_TEXT  = "#333333"
_WHITE = "#ffffff"
_BG    = "#eef2f7"


# ── Core Helpers ──────────────────────────────────────────────────────────────

def _sign(r: float) -> str:
    """Return '+' for non-negative values, '' otherwise."""
    return "+" if r >= 0 else ""

def _ret_c(r: float) -> str:
    """Return HTML color constant for a return value (green/red/muted)."""
    return _G if r > 0 else (_R if r < 0 else _MUTED)

def _type_lbl(t: str) -> str:
    """Return human-readable event type label from event_type string."""
    return "FIRST BUY" if t == "FIRST_BUY" else "RE-ACCUM"

def _type_c(t: str) -> str:
    """Return HTML color constant for event type (blue=first buy, purple=re-accum)."""
    return _BLUE if t == "FIRST_BUY" else _PURPL

def _status_badge_html(status: str) -> str:
    """Return an inline HTML status badge span for a constitutional event status."""
    color = {
        "ACTIVE":       _G,
        "PREMIUM":      _A,
        "UNDER_REVIEW": _R,
        "APPROACHING":  _BLUE,
    }.get(status, _MUTED)
    return (
        f'<span style="background:{color}22;color:{color};padding:2px 8px;'
        f'border-radius:10px;font-size:10px;font-weight:700;white-space:nowrap;">'
        f'{status}</span>'
    )


# ── Data Helpers ──────────────────────────────────────────────────────────────

def _load_stock_dna() -> dict[str, dict]:
    """Load all stock DNA rows from stock_dna.db and return as ticker-keyed dict."""
    db_path = BASE / "stock_dna.db"
    if not db_path.exists():
        return {}
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM stock_dna").fetchall()
        conn.close()
        return {r["ticker"]: dict(r) for r in rows}
    except Exception:
        return {}


def _yesterday_events(snap: PresentationSnapshot) -> list[dict]:
    """Events active on yesterday — uses event_end_date (most recent activity day).
    event_date is the cluster start; event_end_date is the last day the signal qualified.
    Both are checked so a single-day cluster (event_end_date == event_date) is found too.
    """
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    return [
        e for e in (snap.timeline or [])
        if (e.get("event_end_date") or e.get("event_date")) == yesterday
    ]


def _week_events(snap: PresentationSnapshot) -> list[dict]:
    """Events whose most recent activity fell in the last 7 calendar days.
    Uses event_end_date so extended clusters are included for any day they were active.
    """
    today    = date.today().isoformat()
    week_ago = (date.today() - timedelta(days=7)).isoformat()
    return [
        e for e in (snap.timeline or [])
        if week_ago <= (e.get("event_end_date") or e.get("event_date", "")) < today
    ]


# ── Badge Helpers ─────────────────────────────────────────────────────────────

def _hist_val_badge(dna_entry: dict | None) -> str:
    """Historical validation pill badge for a single ticker."""
    if not dna_entry or not dna_entry.get("memory_hits", 0):
        return f'<span style="color:{_MUTED};font-size:10px;">New</span>'
    hits  = dna_entry["memory_hits"]
    avg_r = dna_entry.get("avg_return_pct", 0.0)
    conf  = dna_entry.get("memory_confidence", "DEVELOPING")
    c     = _G if conf in ("STRONG", "CONFIRMED") else (_A if hits >= 2 else _MUTED)
    return (
        f'<span style="background:{c}22;color:{c};padding:2px 8px;'
        f'border-radius:10px;font-size:10px;font-weight:700;white-space:nowrap;">'
        f'&#9733; {hits}x &nbsp;{_sign(avg_r)}{avg_r:.0f}%</span>'
    )


def _mem_badge(dna_entry: dict | None) -> str:
    """Compact memory count badge for table columns."""
    if not dna_entry or not dna_entry.get("memory_hits", 0):
        return f'<span style="color:#ccc;font-size:10px;">&#8212;</span>'
    hits = dna_entry["memory_hits"]
    conf = dna_entry.get("memory_confidence", "DEVELOPING")
    c    = _G if conf in ("STRONG", "CONFIRMED") else (_A if hits >= 2 else _MUTED)
    return (
        f'<span style="background:{c}22;color:{c};padding:2px 7px;'
        f'border-radius:8px;font-size:10px;font-weight:700;">{hits}&#xD7;</span>'
    )


# ── Layout Primitives ─────────────────────────────────────────────────────────

def _section_hdr(num: int, title: str, badge: str = "") -> str:
    """Return an HTML section header block with numbered label, title, and optional badge."""
    badge_part = (
        f'<span style="float:right;margin-top:-2px;">{badge}</span>'
        if badge else ""
    )
    return (
        f'<div style="font-family:Arial,sans-serif;font-size:11px;font-weight:700;'
        f'color:{_MUTED};letter-spacing:1.2px;text-transform:uppercase;'
        f'margin:28px 0 4px 0;">{num}</div>'
        f'<div style="font-family:Arial,sans-serif;font-size:15px;font-weight:700;'
        f'color:{_NAVY};margin-bottom:12px;border-bottom:2px solid {_NAVY};'
        f'padding-bottom:6px;overflow:hidden;">'
        f'{badge_part}{title}'
        f'</div>'
    )


def _th(*cols: str) -> str:
    """Return an HTML table header row with navy background for the given column names."""
    cells = "".join(
        f'<td style="padding:7px 10px;font-family:Arial,sans-serif;font-size:10px;'
        f'font-weight:700;color:{_WHITE};letter-spacing:0.4px;text-transform:uppercase;'
        f'white-space:nowrap;">{h}</td>'
        for h in cols
    )
    return f'<tr style="background:{_NAVY};">{cells}</tr>'


def _divider() -> str:
    """Return an HTML horizontal divider div."""
    return (
        f'<div style="border-top:1px solid {_BORD};margin:24px 0 0 0;"></div>'
    )


def _stat_card(value: str | int, label: str, color: str) -> str:
    """Return an HTML stat card div with a large colored value and a muted label."""
    return (
        f'<div style="background:{color}0d;border:1px solid {color}33;'
        f'border-radius:8px;padding:14px 10px;text-align:center;">'
        f'<div style="font-family:Arial,sans-serif;font-size:28px;font-weight:700;'
        f'color:{color if str(value) != "0" else _MUTED};">{value}</div>'
        f'<div style="font-family:Arial,sans-serif;font-size:10px;color:{_MUTED};'
        f'text-transform:uppercase;letter-spacing:0.5px;margin-top:4px;">{label}</div>'
        f'</div>'
    )


# ── HEADER ────────────────────────────────────────────────────────────────────

def _hdr(snap: PresentationSnapshot, date_str: str) -> str:
    """Return the full HTML email header block with market status badge and stat cards."""
    mstatus = snap.market_status
    is_open = "OPEN" in mstatus and "PRE" not in mstatus
    is_pre  = "PRE" in mstatus
    mc      = _G if is_open else (_A if is_pre else _R)
    dot     = "&#11044;"

    status_badge = (
        f'<span style="background:{mc}33;border:1px solid {mc}66;color:{mc};'
        f'padding:5px 14px;border-radius:20px;font-family:Arial,sans-serif;'
        f'font-size:11px;font-weight:700;display:inline-block;">'
        f'{dot} EGX {mstatus}</span>'
    )

    scan_s  = snap.last_scan_ts[:16].replace("T", " ") if snap.last_scan_ts else "&#8212;"
    data_as = snap.price_data_as_of or "&#8212;"
    univ_s  = str(snap.universe_size)

    chip = (
        'background:#ffffff1a;border-radius:6px;padding:5px 14px;'
        'font-family:Arial,sans-serif;font-size:11px;color:#a8c8e8;'
        'display:inline-block;'
    )
    chip_val = f'font-weight:700;color:{_WHITE};'

    return f"""
<table width="100%" cellpadding="0" cellspacing="0" border="0"
  style="background:{_NAVY};">
  <tr>
    <td style="padding:24px 28px 0 28px;">
      <table width="100%" cellpadding="0" cellspacing="0" border="0">
        <tr>
          <td valign="top">
            <div style="font-family:Arial,sans-serif;color:#7aafce;font-size:10px;
                 letter-spacing:1.5px;text-transform:uppercase;margin-bottom:10px;">
              EGX Constitutional Command Center
            </div>
            <div style="font-family:Arial,sans-serif;color:{_WHITE};font-size:24px;
                 font-weight:700;letter-spacing:-0.3px;">
              Morning Financial Brief
            </div>
          </td>
          <td valign="top" align="right">
            {status_badge}
            <div style="font-family:Arial,sans-serif;color:#7aafce;font-size:11px;
                 margin-top:8px;text-align:right;">{date_str}</div>
          </td>
        </tr>
      </table>
    </td>
  </tr>
  <tr>
    <td style="padding:16px 28px 22px 28px;">
      <table cellpadding="0" cellspacing="0" border="0">
        <tr>
          <td style="{chip}">
            &#128337;&nbsp;<span style="color:#7aafce;">Last Scan</span>
            &nbsp;<span style="{chip_val}">{scan_s}</span>
          </td>
          <td width="10"></td>
          <td style="{chip}">
            &#128197;&nbsp;<span style="color:#7aafce;">Data As Of</span>
            &nbsp;<span style="{chip_val}">{data_as}</span>
          </td>
          <td width="10"></td>
          <td style="{chip}">
            &#127759;&nbsp;<span style="color:#7aafce;">Universe</span>
            &nbsp;<span style="{chip_val}">{univ_s} Tickers</span>
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>"""


# ── SECTION 1: WHAT HAPPENED YESTERDAY ───────────────────────────────────────

def _what_happened_yesterday(snap: PresentationSnapshot) -> str:
    """Return HTML for the 'What Happened Yesterday' email section."""
    yest_events = _yesterday_events(snap)
    buys  = [e for e in yest_events if e["event_type"] == "FIRST_BUY"]
    reacs = [e for e in yest_events if e["event_type"] == "RE_ACCUMULATION"]
    total = len(yest_events)

    cards_html = (
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0"'
        f' style="margin-bottom:14px;">'
        f'<tr>'
        f'<td width="33%" style="padding-right:6px;">'
        f'{_stat_card(len(buys), "BUY Signals", _BLUE)}'
        f'</td>'
        f'<td width="33%" style="padding:0 3px;">'
        f'{_stat_card(len(reacs), "Re-Accumulation", _PURPL)}'
        f'</td>'
        f'<td width="33%" style="padding-left:6px;">'
        f'{_stat_card(total, "Total Alerts", _NAVY)}'
        f'</td>'
        f'</tr></table>'
    )

    if not yest_events:
        body = (
            f'<div style="font-family:Arial,sans-serif;font-size:13px;color:{_MUTED};'
            f'text-align:center;padding:16px 0;background:{_LIGHT};'
            f'border:1px solid {_BORD};border-radius:6px;">'
            f'No constitutional events recorded yesterday.</div>'
        )
    else:
        rows = ""
        for e in yest_events:
            tc = _type_c(e["event_type"])
            rows += (
                f'<tr style="border-bottom:1px solid #e8f0f8;">'
                f'<td style="padding:7px 10px;font-family:Arial,sans-serif;font-size:13px;'
                f'font-weight:700;color:{_NAVY};">{e["ticker"]}</td>'
                f'<td style="padding:7px 10px;font-family:Arial,sans-serif;font-size:11px;'
                f'font-weight:700;color:{tc};">{_type_lbl(e["event_type"])}</td>'
                f'<td style="padding:7px 10px;font-family:Arial,sans-serif;font-size:12px;">'
                f'{float(e["constitutional_entry_price"]):.2f} EGP</td>'
                f'<td style="padding:7px 10px;font-family:Arial,sans-serif;font-size:11px;'
                f'color:{_MUTED};">{e.get("sector","")}</td>'
                f'<td style="padding:7px 10px;font-family:Arial,sans-serif;font-size:11px;'
                f'color:{_MUTED};">{e.get("event_end_date") or e.get("event_date","")}</td>'
                f'</tr>'
            )
        body = (
            f'<table width="100%" cellpadding="0" cellspacing="0" border="0"'
            f' style="border:1px solid {_BORD};border-collapse:collapse;">'
            f'{_th("Ticker","Type","Entry Zone","Sector","Date")}'
            f'{rows}</table>'
        )

    return _section_hdr(1, "WHAT HAPPENED YESTERDAY") + cards_html + body


# ── SECTION 2: LAST WEEK SUMMARY ─────────────────────────────────────────────

def _last_week_summary(snap: PresentationSnapshot) -> str:
    """Return HTML for the 'Last Week Summary' email section."""
    week_events = _week_events(snap)
    w_buys  = [e for e in week_events if e["event_type"] == "FIRST_BUY"]
    w_reacs = [e for e in week_events if e["event_type"] == "RE_ACCUMULATION"]

    active_list = [
        u for u in snap.universe_snapshot
        if u.get("status") in ("ACTIVE", "PREMIUM", "UNDER_REVIEW")
    ]
    winners = [a for a in active_list if (a.get("return_pct") or 0) > 0]
    win_rate = round(len(winners) / len(active_list) * 100) if active_list else 0

    stats = [
        ("Active Positions",        len(active_list),      _G),
        ("Re-Accumulation Events",  len(snap.re_accumulations or []), _PURPL),
        ("Timeline Events (Total)", snap.total_events,     _NAVY),
        ("Unique Tickers",          snap.total_tickers,    _BLUE),
        ("BUY Signals (7 days)",    len(w_buys),           _G),
        ("Re-Accum (7 days)",       len(w_reacs),          _PURPL),
        ("Win Rate (Active)",       f"{win_rate}%",        _G if win_rate >= 70 else _A),
        ("Universe Size",            f"{snap.universe_size} tickers", _NAVY),
    ]

    rows = ""
    for label, val, color in stats:
        rows += (
            f'<tr style="border-bottom:1px solid {_BORD};">'
            f'<td style="padding:8px 10px;font-family:Arial,sans-serif;font-size:12px;'
            f'color:{_MUTED};">{label}</td>'
            f'<td style="padding:8px 10px;font-family:Arial,sans-serif;font-size:14px;'
            f'font-weight:700;color:{color};">{val}</td>'
            f'</tr>'
        )

    return (
        _section_hdr(2, "LAST WEEK SUMMARY") +
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0"'
        f' style="border:1px solid {_BORD};border-collapse:collapse;">{rows}</table>'
    )


# ── SECTION 3: NEW SINCE YESTERDAY ───────────────────────────────────────────

def _new_since_yesterday(snap: PresentationSnapshot) -> str:
    """Return HTML for the 'New Since Yesterday' email section listing new constitutional signals."""
    events = snap.new_events_today or []
    count  = len(events)

    if not events:
        body = (
            f'<div style="font-family:Arial,sans-serif;font-size:13px;color:{_MUTED};'
            f'padding:14px 16px;background:{_LIGHT};border:1px solid {_BORD};'
            f'border-radius:6px;text-align:center;">'
            f'No new constitutional signals since yesterday.</div>'
        )
    else:
        rows = ""
        for e in events:
            tc  = _type_c(e["event_type"])
            rows += (
                f'<tr style="border-bottom:1px solid #d4edda;">'
                f'<td style="padding:8px 10px;font-family:Arial,sans-serif;font-size:13px;'
                f'font-weight:700;color:{_NAVY};">{e["ticker"]}</td>'
                f'<td style="padding:8px 10px;font-family:Arial,sans-serif;font-size:11px;'
                f'font-weight:700;color:{tc};">{_type_lbl(e["event_type"])}</td>'
                f'<td style="padding:8px 10px;font-family:Arial,sans-serif;font-size:12px;">'
                f'{float(e.get("constitutional_entry_price",0)):.2f} EGP</td>'
                f'<td style="padding:8px 10px;font-family:Arial,sans-serif;font-size:11px;'
                f'color:{_MUTED};">{e.get("event_date","")}</td>'
                f'</tr>'
            )
        body = (
            f'<div style="background:#f0fff4;border:1px solid #c3e6cb;">'
            f'<table width="100%" cellpadding="0" cellspacing="0" border="0">'
            f'{_th("Ticker","Type","Entry Zone","Signal Date")}'
            f'{rows}</table></div>'
        )

    return _section_hdr(3, f"NEW SINCE YESTERDAY ({count})") + body


# ── SECTION 3b: CONSTITUTIONAL BUY SIGNALS (from production snapshot) ─────────

def _constitutional_buy_signals(dna: dict) -> str:
    """Return HTML for live constitutional BUY SIGNALS from production_decision_snapshot."""
    snap_path = BASE / "production_decision_snapshot.json"
    if not snap_path.exists():
        return ""
    try:
        prod = json.loads(snap_path.read_text())
        eligible = [d for d in prod.get("decisions", []) if d.get("eligible")]
    except Exception:
        return ""

    if not eligible:
        return ""

    rows = ""
    for d in sorted(eligible, key=lambda x: -(x.get("constitutional_r2") or 0)):
        ticker = d["ticker"]
        ep     = float(d.get("constitutional_entry_price") or 0)
        cp     = float(d.get("current_price") or 0)
        r2     = float(d.get("constitutional_r2") or 0)
        score  = float(d.get("constitutional_score") or 0)
        reason = d.get("reason", "")
        hv     = _hist_val_badge(dna.get(ticker))
        rows += (
            f'<tr style="border-bottom:1px solid #c3e6cb;">'
            f'<td style="padding:10px;font-family:Arial,sans-serif;font-size:14px;'
            f'font-weight:700;color:{_NAVY};">{ticker}</td>'
            f'<td style="padding:10px;font-family:Arial,sans-serif;font-size:12px;">'
            f'{cp:.2f} EGP</td>'
            f'<td style="padding:10px;font-family:Arial,sans-serif;font-size:12px;'
            f'font-weight:700;color:{_G};">BUY LIMIT @ {ep:.2f} EGP</td>'
            f'<td style="padding:10px;font-family:Arial,sans-serif;font-size:11px;'
            f'color:{_BLUE};">{r2:.1f}/100 &bull; Score {score:.1f}</td>'
            f'<td style="padding:10px;">{hv}</td>'
            f'</tr>'
        )

    count = len(eligible)
    return (
        _section_hdr(3, f"&#128994; CONSTITUTIONAL BUY SIGNALS ({count} active)") +
        f'<div style="background:#f0fff4;border:2px solid {_G};border-radius:6px;">'
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0">'
        f'{_th("Ticker","Current Price","Entry Zone","R2 / Score","Hist. Val.")}'
        f'{rows}</table>'
        f'<div style="font-family:Arial,sans-serif;font-size:10px;color:{_MUTED};'
        f'padding:8px 12px;">Source: production_decision_snapshot — R2&#8805;60 &bull; '
        f'Score&#8805;35 &bull; Price&#8804;Entry</div>'
        f'</div>'
    )


# ── SECTION 4: NEAR CONSTITUTIONAL ENTRY ─────────────────────────────────────

def _near_constitutional_entry(snap: PresentationSnapshot, dna: dict) -> str:
    """Return HTML for the 'Near Constitutional Entry' email section."""
    entries = snap.approaching_entries or []

    if not entries:
        return (
            _section_hdr(4, "NEAR CONSTITUTIONAL ENTRY") +
            f'<div style="font-family:Arial,sans-serif;font-size:13px;color:{_MUTED};'
            f'padding:14px 0;">No tickers approaching constitutional entry right now.</div>'
        )

    with_mem  = sum(1 for e in entries if dna.get(e["ticker"], {}).get("memory_hits", 0) > 0)
    total_e   = len(entries)
    mem_pct   = round(with_mem / total_e * 100) if total_e else 0
    mem_badge = (
        f'<span style="background:{_G}22;color:{_G};padding:3px 10px;border-radius:12px;'
        f'font-size:11px;font-weight:700;">&#9733; {with_mem}/{total_e} {mem_pct}%</span>'
    )

    rows = ""
    for e in sorted(entries, key=lambda x: x["distance_to_constitutional"]):
        dist   = e["distance_to_constitutional"]
        need   = e["need_move_pct"]
        cur_s  = f'{e["current_price"]:.2f}' if e["current_price"] else "&#8212;"
        ez_s   = f'{e["candidate_entry_zone"]:.2f} EGP' if e.get("candidate_entry_zone") else "&#8212;"
        r2_s   = f'{60 - dist:.1f}/60 (&#8722;{dist:.1f})'
        zone_s = "AT ZONE" if need < 0.5 else f'+{need:.1f}% above'
        wait_s = f'&#8722;{dist:.1f} pts to R2'
        urg_c  = _G if dist <= 2 else (_A if dist <= 5 else _MUTED)
        hv     = _hist_val_badge(dna.get(e["ticker"]))

        rows += (
            f'<tr style="border-bottom:1px solid #f0e8c0;">'
            f'<td style="padding:8px 10px;font-family:Arial,sans-serif;font-size:13px;'
            f'font-weight:700;color:{_NAVY};">{e["ticker"]}</td>'
            f'<td style="padding:8px 10px;font-family:Arial,sans-serif;font-size:12px;">'
            f'{cur_s}</td>'
            f'<td style="padding:8px 10px;font-family:Arial,sans-serif;font-size:12px;">'
            f'{ez_s}</td>'
            f'<td style="padding:8px 10px;font-family:Arial,sans-serif;font-size:12px;'
            f'color:{urg_c};font-weight:700;">{r2_s}</td>'
            f'<td style="padding:8px 10px;font-family:Arial,sans-serif;font-size:12px;'
            f'color:{_A};">{zone_s}</td>'
            f'<td style="padding:8px 10px;font-family:Arial,sans-serif;font-size:12px;'
            f'color:{urg_c};font-weight:700;">{wait_s}</td>'
            f'<td style="padding:8px 10px;">{hv}</td>'
            f'</tr>'
        )

    return (
        _section_hdr(4, f"NEAR CONSTITUTIONAL ENTRY ({total_e} tickers)", badge=mem_badge) +
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0"'
        f' style="border:1px solid #e8d5a0;border-collapse:collapse;background:#fffcf0;">'
        f'{_th("Ticker","Current","Entry Zone","R2 Progress","Zone Position","Waiting For","Hist. Val.")}'
        f'{rows}</table>'
    )


# ── SECTION 5: ACTIVE OPPORTUNITIES ──────────────────────────────────────────

def _active_opportunities(snap: PresentationSnapshot, dna: dict) -> str:
    """Return HTML for the 'Active Opportunities' email section."""
    active = [
        u for u in snap.universe_snapshot
        if u.get("status") in ("ACTIVE", "PREMIUM", "UNDER_REVIEW")
    ]
    active_sorted = sorted(active, key=lambda x: -(x.get("return_pct") or 0))

    total     = len(active_sorted)
    with_pos  = sum(1 for a in active_sorted if (a.get("return_pct") or 0) > 0)
    win_rate  = round(with_pos / total * 100) if total else 0
    mem_badge = (
        f'<span style="background:{_G}22;color:{_G};padding:3px 10px;border-radius:12px;'
        f'font-size:11px;font-weight:700;">&#9733; {with_pos}/{total} {win_rate}%</span>'
    )

    if not active_sorted:
        return (
            _section_hdr(5, "ACTIVE OPPORTUNITIES") +
            f'<div style="font-family:Arial,sans-serif;font-size:13px;color:{_MUTED};'
            f'padding:12px 0;">No active opportunities.</div>'
        )

    rows = ""
    for a in active_sorted:
        ret    = a.get("return_pct") or 0
        rc     = _ret_c(ret)
        action = a.get("action", "")
        act_c  = _G if action.startswith("HOLD") else (_A if action.startswith("MONITOR") else _MUTED)
        mem    = _mem_badge(dna.get(a["ticker"]))
        ez     = a.get("constitutional_entry_price") or 0
        cp     = a.get("current_price") or 0

        rows += (
            f'<tr style="border-bottom:1px solid #e8f0f8;">'
            f'<td style="padding:8px 10px;font-family:Arial,sans-serif;font-size:13px;'
            f'font-weight:700;color:{_NAVY};white-space:nowrap;">{a["ticker"]}</td>'
            f'<td style="padding:8px 10px;">{_status_badge_html(a.get("status",""))}</td>'
            f'<td style="padding:8px 10px;font-family:Arial,sans-serif;font-size:12px;">'
            f'{ez:.2f} EGP</td>'
            f'<td style="padding:8px 10px;font-family:Arial,sans-serif;font-size:12px;">'
            f'{cp:.2f}</td>'
            f'<td style="padding:8px 10px;font-family:Arial,sans-serif;font-size:13px;'
            f'font-weight:700;color:{rc};">{_sign(ret)}{ret:.1f}%</td>'
            f'<td style="padding:8px 10px;font-family:Arial,sans-serif;font-size:11px;'
            f'color:{act_c};font-weight:700;white-space:nowrap;">{action}</td>'
            f'<td style="padding:8px 10px;text-align:center;">{mem}</td>'
            f'</tr>'
        )

    return (
        _section_hdr(5, f"ACTIVE OPPORTUNITIES ({total} positions)", badge=mem_badge) +
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0"'
        f' style="border:1px solid {_BORD};border-collapse:collapse;">'
        f'{_th("Ticker","Status","Entry Zone","Current","Return %","Action","Memory")}'
        f'{rows}</table>'
    )


# ── SECTION 6: RE-ACCUMULATION EVENTS ────────────────────────────────────────

def _re_accumulation_events(snap: PresentationSnapshot, dna: dict) -> str:
    """Return HTML for the 'Re-Accumulation Events' email section."""
    reacs       = snap.re_accumulations or []
    reacs_sort  = sorted(reacs, key=lambda x: -(x.get("return_pct") or 0))

    total     = len(reacs_sort)
    with_pos  = sum(1 for e in reacs_sort if (e.get("return_pct") or 0) > 0)
    win_rate  = round(with_pos / total * 100) if total else 0
    mem_badge = (
        f'<span style="background:{_PURPL}22;color:{_PURPL};padding:3px 10px;'
        f'border-radius:12px;font-size:11px;font-weight:700;">'
        f'&#9733; {with_pos}/{total} {win_rate}%</span>'
    )

    if not reacs_sort:
        return (
            _section_hdr(6, "RE-ACCUMULATION EVENTS") +
            f'<div style="font-family:Arial,sans-serif;font-size:13px;color:{_MUTED};'
            f'padding:12px 0;">No re-accumulation events.</div>'
        )

    rows = ""
    for e in reacs_sort:
        ret  = e.get("return_pct") or 0
        rc   = _ret_c(ret)
        idx  = e.get("event_index", 1)
        ep   = e.get("constitutional_entry_price") or 0
        cp   = e.get("current_price") or 0
        mem  = _mem_badge(dna.get(e["ticker"]))

        rows += (
            f'<tr style="border-bottom:1px solid #e8f0f8;">'
            f'<td style="padding:8px 10px;font-family:Arial,sans-serif;font-size:13px;'
            f'font-weight:700;color:{_NAVY};white-space:nowrap;">{e["ticker"]}</td>'
            f'<td style="padding:8px 10px;font-family:Arial,sans-serif;font-size:11px;'
            f'font-weight:700;color:{_PURPL};">RE-ACCUM #{idx}</td>'
            f'<td style="padding:8px 10px;font-family:Arial,sans-serif;font-size:12px;">'
            f'{ep:.2f} EGP</td>'
            f'<td style="padding:8px 10px;font-family:Arial,sans-serif;font-size:12px;">'
            f'{cp:.2f}</td>'
            f'<td style="padding:8px 10px;font-family:Arial,sans-serif;font-size:13px;'
            f'font-weight:700;color:{rc};">{_sign(ret)}{ret:.1f}%</td>'
            f'<td style="padding:8px 10px;font-family:Arial,sans-serif;font-size:11px;'
            f'color:{_MUTED};">{e.get("event_date","")}</td>'
            f'<td style="padding:8px 10px;text-align:center;">{mem}</td>'
            f'</tr>'
        )

    return (
        _section_hdr(6, f"RE-ACCUMULATION EVENTS ({total} events)", badge=mem_badge) +
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0"'
        f' style="border:1px solid {_BORD};border-collapse:collapse;">'
        f'{_th("Ticker","Type","Entry Zone","Current","Return %","Signal Date","Memory")}'
        f'{rows}</table>'
    )


# ── SECTION 7: PORTFOLIO HEALTH ───────────────────────────────────────────────

def _portfolio_health(snap: PresentationSnapshot) -> str:
    """Return HTML for the 'Portfolio Health' email section with star rating and metrics."""
    stars_c = (
        _G if snap.health_stars.count("★") >= 4
        else (_A if snap.health_stars.count("★") >= 3 else _R)
    )

    active_list = [
        u for u in snap.universe_snapshot
        if u.get("status") in ("ACTIVE", "PREMIUM", "UNDER_REVIEW")
    ]
    premium     = [u for u in active_list if u.get("status") == "PREMIUM"]
    with_pos    = [u for u in active_list if (u.get("return_pct") or 0) > 0]
    win_rate    = round(len(with_pos) / len(active_list) * 100) if active_list else 0
    avg_return  = (
        sum(u.get("return_pct") or 0 for u in active_list) / len(active_list)
        if active_list else 0
    )

    metrics = [
        (str(len(active_list)), "Positions",   _G),
        (str(len(premium)),     "Premium",      _A),
        (f"{win_rate}%",        "Win Rate",     _G if win_rate >= 70 else _A),
        (f"{_sign(avg_return)}{avg_return:.1f}%", "Avg Return", _ret_c(avg_return)),
    ]

    metric_cells = "".join(
        f'<td align="center" style="padding:14px 10px;border-right:1px solid {_BORD};">'
        f'<div style="font-family:Arial,sans-serif;font-size:22px;font-weight:700;'
        f'color:{c};">{v}</div>'
        f'<div style="font-family:Arial,sans-serif;font-size:10px;color:{_MUTED};'
        f'text-transform:uppercase;letter-spacing:0.4px;margin-top:4px;">{l}</div>'
        f'</td>'
        for v, l, c in metrics
    )

    narrative_html = (
        f'<div style="font-family:Arial,sans-serif;font-size:12px;color:{_MUTED};'
        f'margin-top:8px;line-height:1.5;">'
        + snap.health_narrative.replace("\n", "<br>") +
        f'</div>'
        if snap.health_narrative else ""
    )

    return (
        _section_hdr(7, "PORTFOLIO HEALTH") +
        f'<div style="background:{_LIGHT};border:1px solid {_BORD};border-radius:8px;'
        f'padding:16px 18px;margin-bottom:12px;">'
        f'<div style="font-family:Arial,sans-serif;font-size:20px;color:{stars_c};">'
        f'{snap.health_stars}'
        f'<span style="font-family:Arial,sans-serif;font-size:14px;font-weight:700;'
        f'color:{_TEXT};margin-left:10px;">{snap.health_label}</span></div>'
        f'{narrative_html}'
        f'</div>'
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0"'
        f' style="border:1px solid {_BORD};border-collapse:collapse;">'
        f'<tr>{metric_cells}</tr></table>'
    )


# ── SECTION 8: CONSTITUTIONAL TIMELINE ───────────────────────────────────────

def _constitutional_timeline(snap: PresentationSnapshot) -> str:
    """Return HTML for the 'Constitutional Timeline' email section (most recent 20 events)."""
    tl = snap.timeline or []
    if not tl:
        return (
            _section_hdr(8, "CONSTITUTIONAL TIMELINE") +
            f'<div style="font-family:Arial,sans-serif;font-size:13px;color:{_MUTED};'
            f'padding:12px 0;">No timeline events available.</div>'
        )

    sorted_tl = sorted(tl, key=lambda x: x.get("event_date", ""), reverse=True)
    shown     = sorted_tl[:20]

    rows = ""
    for e in shown:
        tc  = _type_c(e["event_type"])
        ret = e.get("return_pct") or 0
        rc  = _ret_c(ret)
        ep  = e.get("constitutional_entry_price") or 0
        cp  = e.get("current_price") or 0

        rows += (
            f'<tr style="border-bottom:1px solid #e8f0f8;">'
            f'<td style="padding:6px 10px;font-family:Arial,sans-serif;font-size:11px;'
            f'color:{_MUTED};white-space:nowrap;">{e.get("event_date","")}</td>'
            f'<td style="padding:6px 10px;font-family:Arial,sans-serif;font-size:12px;'
            f'font-weight:700;color:{_NAVY};">{e["ticker"]}</td>'
            f'<td style="padding:6px 10px;font-family:Arial,sans-serif;font-size:11px;'
            f'font-weight:700;color:{tc};">{_type_lbl(e["event_type"])}</td>'
            f'<td style="padding:6px 10px;font-family:Arial,sans-serif;font-size:12px;">'
            f'{ep:.2f} EGP</td>'
            f'<td style="padding:6px 10px;font-family:Arial,sans-serif;font-size:12px;">'
            f'{cp:.2f}</td>'
            f'<td style="padding:6px 10px;font-family:Arial,sans-serif;font-size:12px;'
            f'font-weight:700;color:{rc};">{_sign(ret)}{ret:.1f}%</td>'
            f'<td style="padding:6px 10px;font-family:Arial,sans-serif;font-size:10px;'
            f'color:{_MUTED};">{e.get("days_active","")}d</td>'
            f'</tr>'
        )

    footer_note = (
        f'<div style="font-family:Arial,sans-serif;font-size:11px;color:{_MUTED};'
        f'text-align:center;padding:8px 0;">'
        f'Showing latest {len(shown)} of {len(tl)} total events</div>'
        if len(tl) > len(shown) else ""
    )

    return (
        _section_hdr(8, f"CONSTITUTIONAL TIMELINE ({len(tl)} total events)") +
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0"'
        f' style="border:1px solid {_BORD};border-collapse:collapse;">'
        f'{_th("Date","Ticker","Type","Entry","Current","Return %","Active")}'
        f'{rows}</table>'
        f'{footer_note}'
    )


# ── SECTION 9: CONSTITUTIONAL MEMORY ─────────────────────────────────────────

def _constitutional_memory(snap: PresentationSnapshot, dna: dict) -> str:
    """Return HTML for the 'Constitutional Memory' email section with stock DNA insights."""
    tl = snap.timeline or []

    ticker_events: dict[str, list] = {}
    for e in tl:
        ticker_events.setdefault(e["ticker"], []).append(e)

    mem_entries = sorted(
        [(ticker, data) for ticker, data in dna.items()
         if data.get("memory_hits", 0) > 0],
        key=lambda x: (-x[1].get("memory_hits", 0), -x[1].get("avg_return_pct", 0))
    )

    if not mem_entries:
        return (
            _section_hdr(9, "CONSTITUTIONAL MEMORY") +
            f'<div style="font-family:Arial,sans-serif;font-size:13px;color:{_MUTED};'
            f'padding:14px 0;text-align:center;">'
            f'No constitutional memory yet. System is building its knowledge base.</div>'
        )

    rows = ""
    for ticker, data in mem_entries:
        hits    = data.get("memory_hits", 0)
        avg_r   = data.get("avg_return_pct", 0.0)
        best_r  = data.get("best_return_pct", 0.0)
        conf    = data.get("memory_confidence", "DEVELOPING")
        buy_c   = data.get("buy_count", 0)
        reac_c  = data.get("re_accum_count", 0)
        first_d = data.get("first_buy_date", "")
        zone_l  = data.get("historical_buy_zone_low", 0.0)
        zone_h  = data.get("historical_buy_zone_high", 0.0)

        badge_c  = _G if conf in ("STRONG", "CONFIRMED") else (_A if hits >= 3 else _MUTED)
        hv_badge = (
            f'<span style="background:{badge_c}22;color:{badge_c};padding:3px 9px;'
            f'border-radius:10px;font-size:10px;font-weight:700;display:inline-block;">'
            f'&#9733; {hits}&#xD7; &nbsp;Avg {_sign(avg_r)}{avg_r:.0f}%</span>'
        )

        t_events  = ticker_events.get(ticker, [])
        nearest   = max((e.get("event_date","") for e in t_events), default="—")
        zone_s    = f'{zone_l:.2f}&#8211;{zone_h:.2f} EGP' if zone_l and zone_h else "&#8212;"

        nearest_cluster = (
            f'<span style="font-family:Arial,sans-serif;font-size:12px;color:{_TEXT};">'
            f'{nearest}</span><br>'
            f'<span style="font-family:Arial,sans-serif;font-size:10px;color:{_MUTED};">'
            f'Zone: {zone_s}</span>'
        )

        summary = (
            f'<span style="font-family:Arial,sans-serif;font-size:11px;color:{_MUTED};">'
            f'{buy_c} BUY{"s" if buy_c != 1 else ""} &bull; '
            f'{reac_c} Re-Acc. &bull; '
            f'Best {_sign(best_r)}{best_r:.0f}% &bull; '
            f'Since {first_d}</span>'
        )

        rows += (
            f'<tr style="border-bottom:1px solid #e8f0f8;">'
            f'<td style="padding:10px 10px;font-family:Arial,sans-serif;font-size:13px;'
            f'font-weight:700;color:{_NAVY};white-space:nowrap;">{ticker}</td>'
            f'<td style="padding:10px 10px;">{hv_badge}</td>'
            f'<td style="padding:10px 10px;">{nearest_cluster}</td>'
            f'<td style="padding:10px 10px;">{summary}</td>'
            f'</tr>'
        )

    return (
        _section_hdr(9, f"CONSTITUTIONAL MEMORY ({len(mem_entries)} tickers)") +
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0"'
        f' style="border:1px solid {_BORD};border-collapse:collapse;">'
        f'{_th("Ticker","Historical Validation","Nearest Historical Cluster","Summary")}'
        f'{rows}</table>'
    )


# ── FOOTER ────────────────────────────────────────────────────────────────────

def _footer() -> str:
    """Return the HTML email footer block with attribution and disclaimer."""
    return f"""
<table width="100%" cellpadding="0" cellspacing="0" border="0"
  style="margin-top:32px;background:{_NAVY};">
  <tr>
    <td align="center" style="padding:22px 28px;">
      <div style="font-family:Arial,sans-serif;font-size:12px;color:#8fb8d8;
           font-weight:700;letter-spacing:0.6px;margin-bottom:6px;">
        Powered by Constitutional Snapshot Engine
      </div>
      <div style="font-family:Arial,sans-serif;font-size:11px;color:#4a7a9b;
           letter-spacing:0.4px;">
        Append&nbsp;Only &nbsp;&bull;&nbsp; Immutable &nbsp;&bull;&nbsp; Verifiable
      </div>
      <div style="font-family:Arial,sans-serif;font-size:10px;color:#2a5073;
           margin-top:14px;line-height:1.5;">
        This report is for informational purposes only and does not constitute financial advice.<br>
        Past constitutional signals do not guarantee future returns. All investments carry risk.
      </div>
    </td>
  </tr>
</table>"""


# ── BUILD ─────────────────────────────────────────────────────────────────────

def build_email(snap: PresentationSnapshot | None = None) -> str:
    """Build and return the full HTML morning email from the current presentation snapshot."""
    if snap is None:
        snap = build_presentation_snapshot()

    dna      = _load_stock_dna()
    now      = _now_cairo()
    date_str = now.strftime("%A, %d %B %Y")

    buy_signals_html = _constitutional_buy_signals(dna)
    sections = [
        _hdr(snap, date_str),
        '<div style="padding:0 24px 8px 24px;">',
        _divider(),
        _what_happened_yesterday(snap),
        _divider(),
        _last_week_summary(snap),
        _divider(),
        _new_since_yesterday(snap),
        *([_divider(), buy_signals_html] if buy_signals_html else []),
        _divider(),
        _near_constitutional_entry(snap, dna),
        _divider(),
        _active_opportunities(snap, dna),
        _divider(),
        _re_accumulation_events(snap, dna),
        _divider(),
        _portfolio_health(snap),
        _divider(),
        _constitutional_timeline(snap),
        _divider(),
        _constitutional_memory(snap, dna),
        '</div>',
        _footer(),
    ]

    inner = "\n".join(sections)
    return (
        '<!DOCTYPE html>'
        '<html lang="en">'
        '<head>'
        '<meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1.0">'
        '<meta name="color-scheme" content="light">'
        '</head>'
        '<body style="margin:0;padding:16px;background:#eef2f7;">'
        '<table width="700" cellpadding="0" cellspacing="0" border="0" align="center"'
        ' style="background:#ffffff;border:1px solid #d0d7e2;max-width:700px;width:100%;">'
        f'<tr><td style="padding:0;">{inner}</td></tr>'
        '</table>'
        '</body></html>'
    )


if __name__ == "__main__":
    out  = Path(__file__).parent / "email.html"
    html = build_email()
    out.write_text(html, encoding="utf-8")
    sha  = hashlib.sha256(html.encode()).hexdigest()
    print(f"[Email V7] Saved email.html ({len(html)//1024} KB)")
    print(f"[Email V7] SHA256: {sha[:32]}...")
