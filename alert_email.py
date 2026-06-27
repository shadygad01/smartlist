"""
EGX Constitutional Command Center — Alert Email V2
Triggered on FIRST_BUY or RE_ACCUMULATION events only.
One email per constitutional event.
Visual style matches Morning Financial Brief.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from time_authority import today_iso as _today_iso, now_cairo as _now_cairo_ta

BASE = Path(__file__).parent

_NAVY  = "#1a3a5c"
_WHITE = "#ffffff"
_BLUE  = "#0b4a8f"
_PURPL = "#5b21b6"
_GREEN = "#155724"
_G     = "#28a745"
_R     = "#dc3545"
_A     = "#f0b840"
_MUTED = "#888888"
_BORD  = "#d0d7e2"
_LIGHT = "#f8f9fb"


def _sign(r: float) -> str:
    """Return '+' for non-negative values, '' otherwise."""
    return "+" if r >= 0 else ""

def _ret_c(r: float) -> str:
    """Return HTML color code based on return sign."""
    return _G if r > 0 else (_R if r < 0 else _MUTED)

def _fib_targets(entry: float) -> list[tuple[str, float]]:
    """Return list of (label, price) Fibonacci extension targets from entry."""
    return [
        ("1.236x", round(entry * 1.236, 2)),
        ("1.382x", round(entry * 1.382, 2)),
        ("1.618x", round(entry * 1.618, 2)),
        ("2.000x", round(entry * 2.000, 2)),
    ]

def _load_dna(ticker: str) -> dict:
    """Load stock DNA row for ticker from stock_dna.db; returns empty dict on miss."""
    db_path = BASE / "stock_dna.db"
    if not db_path.exists():
        return {}
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM stock_dna WHERE ticker=?", (ticker,)
        ).fetchone()
        conn.close()
        return dict(row) if row else {}
    except Exception:
        return {}

def _load_nearest_cluster(ticker: str) -> str:
    """Return nearest upcoming event_date from constitutional_opportunity_events for ticker."""
    db_path = BASE / "constitutional_opportunity_events.db"
    if not db_path.exists():
        return ""
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT event_date, event_type, constitutional_entry_price FROM constitutional_opportunity_events "
            "WHERE ticker=? ORDER BY event_date DESC LIMIT 1",
            (ticker,)
        ).fetchone()
        conn.close()
        if row:
            return f'{row["event_date"]} @ {float(row["constitutional_entry_price"]):.2f} EGP'
        return ""
    except Exception:
        return ""


def build_alert_email(event: dict) -> tuple[str, str]:
    """Returns (subject, html_body) for a single constitutional event."""
    ticker     = event.get("ticker", "TICKER")
    etype      = event.get("event_type", "FIRST_BUY")
    event_date = event.get("event_date", _today_iso())
    entry      = float(event.get("constitutional_entry_price", 0.0))
    current    = float(event.get("current_price", 0.0))
    ret_pct    = float(event.get("return_pct", 0.0))
    sector     = event.get("sector", "")
    reason     = event.get("reason", event.get("signal_reason", ""))

    is_buy     = etype == "FIRST_BUY"
    type_label = "BUY SIGNAL" if is_buy else "RE-ACCUMULATION SIGNAL"
    type_color = _BLUE if is_buy else _PURPL
    ret_c      = _ret_c(ret_pct)

    subject = f"{'⚡' if is_buy else '♻️'} [{ticker}] CONSTITUTIONAL {type_label} — {event_date}"

    dna            = _load_dna(ticker)
    has_memory     = bool(dna and dna.get("constitutional_memory_hits", 0) >= 1)
    mem_hits       = dna.get("constitutional_memory_hits", 0) if dna else 0
    mem_avg        = dna.get("avg_return_pct", 0.0) if dna else 0.0
    mem_best       = dna.get("best_return_pct", 0.0) if dna else 0.0
    mem_conf       = dna.get("constitutional_memory_confidence", "DEVELOPING") if dna else "DEVELOPING"
    zone_l         = dna.get("historical_buy_zone_low", 0.0) if dna else 0.0
    zone_h         = dna.get("historical_buy_zone_high", 0.0) if dna else 0.0
    first_buy_date = dna.get("first_buy_date", "") if dna else ""
    nearest_cluster= _load_nearest_cluster(ticker)

    conf_c   = _G if mem_conf in ("STRONG", "CONFIRMED") else (_A if mem_hits >= 2 else _MUTED)
    zone_s   = f'{zone_l:.2f}–{zone_h:.2f} EGP' if zone_l and zone_h else "—"

    now_s = _now_cairo_ta().strftime("%d %b %Y %H:%M Cairo")

    chip = (
        f'background:{_LIGHT};border:1px solid {_BORD};border-radius:6px;'
        f'padding:12px;text-align:center;'
    )
    chip_lbl = (
        f'font-family:Arial,sans-serif;font-size:10px;color:{_MUTED};'
        f'text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px;'
    )
    chip_val = (
        f'font-family:Arial,sans-serif;font-size:18px;font-weight:700;color:{_NAVY};'
    )

    # ── Constitutional Memory block ────────────────────────────────────────────
    if has_memory:
        mem_block = f"""
<table width="100%" cellpadding="0" cellspacing="0" border="0"
  style="background:#f0f8ff;border:1px solid #b8d4e8;border-radius:8px;
         margin:18px 0 0 0;">
  <tr>
    <td style="padding:16px 18px;">
      <div style="font-family:Arial,sans-serif;font-size:12px;font-weight:700;
           color:{_NAVY};margin-bottom:12px;letter-spacing:0.4px;">
        &#9733; CONSTITUTIONAL MEMORY — This ticker has history
      </div>
      <table width="100%" cellpadding="0" cellspacing="0" border="0">
        <tr>
          <td width="50%" style="vertical-align:top;padding-right:12px;">
            <table cellpadding="0" cellspacing="0" border="0" width="100%">
              <tr><td style="padding:4px 0;font-family:Arial,sans-serif;font-size:11px;color:{_MUTED};">
                Historical Validation
              </td><td style="padding:4px 0;">
                <span style="background:{conf_c}22;color:{conf_c};padding:2px 8px;
                      border-radius:10px;font-size:10px;font-weight:700;">
                  {mem_hits}&#xD7; &nbsp; Avg {_sign(mem_avg)}{mem_avg:.0f}%
                </span>
              </td></tr>
              <tr><td style="padding:4px 0;font-family:Arial,sans-serif;font-size:11px;color:{_MUTED};">
                Best Historical Return
              </td><td style="padding:4px 0;font-family:Arial,sans-serif;font-size:12px;
                font-weight:700;color:{_G};">
                {_sign(mem_best)}{mem_best:.1f}%
              </td></tr>
              <tr><td style="padding:4px 0;font-family:Arial,sans-serif;font-size:11px;color:{_MUTED};">
                Seen Before
              </td><td style="padding:4px 0;font-family:Arial,sans-serif;font-size:12px;
                font-weight:700;color:{_NAVY};">
                {mem_hits} time{"s" if mem_hits != 1 else ""}
              </td></tr>
            </table>
          </td>
          <td width="50%" style="vertical-align:top;padding-left:12px;
               border-left:1px solid {_BORD};">
            <table cellpadding="0" cellspacing="0" border="0" width="100%">
              <tr><td style="padding:4px 0;font-family:Arial,sans-serif;font-size:11px;color:{_MUTED};">
                Nearest Historical Cluster
              </td><td style="padding:4px 0;font-family:Arial,sans-serif;font-size:12px;
                font-weight:700;color:{_NAVY};">
                {nearest_cluster or "—"}
              </td></tr>
              <tr><td style="padding:4px 0;font-family:Arial,sans-serif;font-size:11px;color:{_MUTED};">
                Historical Zone
              </td><td style="padding:4px 0;font-family:Arial,sans-serif;font-size:12px;
                color:{_MUTED};">
                {zone_s}
              </td></tr>
              <tr><td style="padding:4px 0;font-family:Arial,sans-serif;font-size:11px;color:{_MUTED};">
                First Constitutional Signal
              </td><td style="padding:4px 0;font-family:Arial,sans-serif;font-size:12px;
                color:{_MUTED};">
                {first_buy_date or "—"}
              </td></tr>
            </table>
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>"""
    else:
        mem_block = f"""
<div style="background:{_LIGHT};border:1px solid {_BORD};border-radius:6px;
     padding:12px 16px;margin:14px 0 0 0;font-family:Arial,sans-serif;
     font-size:12px;color:{_MUTED};">
  &#9675; New Ticker — No constitutional history yet. First signal.
</div>"""

    # ── Fibonacci targets ──────────────────────────────────────────────────────
    fib_rows = ""
    if entry > 0:
        for lbl, price in _fib_targets(entry):
            pct  = ((price - entry) / entry * 100)
            fib_rows += (
                f'<tr style="border-bottom:1px solid {_BORD};">'
                f'<td style="padding:6px 10px;font-family:Arial,sans-serif;font-size:12px;'
                f'color:{_MUTED};">{lbl}</td>'
                f'<td style="padding:6px 10px;font-family:Arial,sans-serif;font-size:12px;'
                f'font-weight:700;color:{_NAVY};">{price:.2f} EGP</td>'
                f'<td style="padding:6px 10px;font-family:Arial,sans-serif;font-size:11px;'
                f'color:{_G};">+{pct:.0f}%</td>'
                f'</tr>'
            )

    fib_block = ""
    if fib_rows:
        fib_block = f"""
<div style="margin-top:18px;">
  <div style="font-family:Arial,sans-serif;font-size:12px;font-weight:700;
       color:{_NAVY};margin-bottom:8px;letter-spacing:0.4px;">
    &#128200; FIBONACCI TARGETS
  </div>
  <table width="100%" cellpadding="0" cellspacing="0" border="0"
    style="border:1px solid {_BORD};border-collapse:collapse;background:{_LIGHT};">
    {fib_rows}
  </table>
</div>"""

    # ── Signal reason ──────────────────────────────────────────────────────────
    reason_block = ""
    if reason:
        reason_block = f"""
<div style="background:#fffcf0;border:1px solid #e8d5a0;border-radius:6px;
     padding:12px 16px;margin-top:16px;">
  <div style="font-family:Arial,sans-serif;font-size:10px;font-weight:700;
       color:{_MUTED};margin-bottom:6px;letter-spacing:0.5px;text-transform:uppercase;">
    WHY — Constitutional Signal Reason
  </div>
  <div style="font-family:Arial,sans-serif;font-size:13px;color:#333;line-height:1.5;">
    {reason}
  </div>
</div>"""

    html_body = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin:0;padding:16px;background:#eef2f7;">
<table width="600" cellpadding="0" cellspacing="0" border="0" align="center"
  style="background:{_WHITE};border:1px solid {_BORD};max-width:600px;width:100%;">

  <!-- Header -->
  <tr>
    <td style="background:{_NAVY};padding:22px 28px 18px 28px;">
      <table width="100%" cellpadding="0" cellspacing="0" border="0">
        <tr>
          <td>
            <div style="font-family:Arial,sans-serif;color:#7aafce;font-size:10px;
                 letter-spacing:1.5px;text-transform:uppercase;margin-bottom:8px;">
              EGX Constitutional Command Center
            </div>
            <div style="font-family:Arial,sans-serif;color:{_WHITE};font-size:20px;
                 font-weight:700;">
              Constitutional Alert
            </div>
          </td>
          <td align="right" valign="top">
            <div style="font-family:Arial,sans-serif;color:#7aafce;font-size:11px;">
              {now_s}
            </div>
          </td>
        </tr>
      </table>
    </td>
  </tr>

  <!-- Signal Type Badge -->
  <tr>
    <td style="padding:22px 28px 0 28px;text-align:center;">
      <span style="background:{type_color}1a;color:{type_color};padding:7px 24px;
            border-radius:24px;font-family:Arial,sans-serif;font-size:14px;
            font-weight:700;border:1px solid {type_color}44;display:inline-block;">
        {'&#9889;' if is_buy else '&#9854;'} {type_label}
      </span>
    </td>
  </tr>

  <!-- Ticker -->
  <tr>
    <td style="padding:16px 28px 20px 28px;text-align:center;">
      <div style="font-family:Arial,sans-serif;font-size:36px;font-weight:700;
           color:{_NAVY};">{ticker}</div>
      <div style="font-family:Arial,sans-serif;font-size:12px;color:{_MUTED};margin-top:4px;">
        {sector + ' &nbsp;&middot;&nbsp; ' if sector else ''}{event_date}
      </div>
    </td>
  </tr>

  <!-- Key Metrics -->
  <tr>
    <td style="padding:0 28px;">
      <table width="100%" cellpadding="0" cellspacing="0" border="0"
        style="border:1px solid {_BORD};border-collapse:collapse;">
        <tr>
          <td width="33%" style="{chip}border-right:1px solid {_BORD};">
            <div style="{chip_lbl}">Constitutional Zone</div>
            <div style="{chip_val}">{entry:.2f} EGP</div>
          </td>
          <td width="33%" style="{chip}border-right:1px solid {_BORD};">
            <div style="{chip_lbl}">Current Price</div>
            <div style="{chip_val}">{current:.2f}</div>
          </td>
          <td width="33%" style="{chip}">
            <div style="{chip_lbl}">Signal Type</div>
            <div style="font-family:Arial,sans-serif;font-size:14px;font-weight:700;
                 color:{type_color};">{'FIRST BUY' if is_buy else 'RE-ACCUM'}</div>
          </td>
        </tr>
        <tr>
          <td colspan="3" style="padding:0;">
            <table width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr>
                <td width="50%" style="{chip}border-right:1px solid {_BORD};
                     border-top:1px solid {_BORD};">
                  <div style="{chip_lbl}">Return Since Signal</div>
                  <div style="font-family:Arial,sans-serif;font-size:18px;font-weight:700;
                       color:{ret_c};">{_sign(ret_pct)}{ret_pct:.1f}%</div>
                </td>
                <td width="50%" style="{chip}border-top:1px solid {_BORD};">
                  <div style="{chip_lbl}">Historical Validation</div>
                  <div style="font-family:Arial,sans-serif;font-size:18px;font-weight:700;
                       color:{conf_c if has_memory else _MUTED};">
                    {'Seen ' + str(mem_hits) + 'x' if has_memory else 'First Signal'}
                  </div>
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>
    </td>
  </tr>

  <!-- Constitutional Memory -->
  <tr>
    <td style="padding:0 28px;">
      {mem_block}
    </td>
  </tr>

  <!-- Signal Reason -->
  <tr>
    <td style="padding:0 28px;">
      {reason_block}
    </td>
  </tr>

  <!-- Fibonacci Targets -->
  <tr>
    <td style="padding:0 28px;">
      {fib_block}
    </td>
  </tr>

  <!-- Call To Action -->
  <tr>
    <td style="padding:24px 28px;text-align:center;">
      <a href="https://shadygad01.github.io/smartlist/"
         style="background:{_NAVY};color:{_WHITE};padding:13px 32px;
                border-radius:6px;font-family:Arial,sans-serif;font-size:13px;
                font-weight:700;text-decoration:none;display:inline-block;
                letter-spacing:0.3px;">
        Open Dashboard &#8594;
      </a>
    </td>
  </tr>

  <!-- Footer -->
  <tr>
    <td style="background:{_NAVY};padding:18px 28px;text-align:center;">
      <div style="font-family:Arial,sans-serif;font-size:12px;color:#8fb8d8;
           font-weight:700;margin-bottom:4px;">
        Powered by Constitutional Snapshot Engine
      </div>
      <div style="font-family:Arial,sans-serif;font-size:11px;color:#4a7a9b;">
        Append&nbsp;Only &bull; Immutable &bull; Verifiable
      </div>
      <div style="font-family:Arial,sans-serif;font-size:10px;color:#2a5073;margin-top:10px;">
        For informational purposes only. Not financial advice.
        Past signals do not guarantee future returns.
      </div>
    </td>
  </tr>

</table>
</body>
</html>"""

    return subject, html_body


if __name__ == "__main__":
    # Generate Morning BUY alert sample
    subj_buy, html_buy = build_alert_email({
        "ticker":        "HELI.CA",
        "event_type":    "FIRST_BUY",
        "event_date":    "2026-06-24",
        "constitutional_entry_price":   3.1657,
        "current_price": 6.56,
        "return_pct":    107.22,
        "sector":        "Real Estate",
        "reason":        "Constitutional threshold crossed: R2=60.41, Score=38.11, Momentum confirmed."
    })
    out_buy = Path(__file__).parent / "alert_email.html"
    out_buy.write_text(html_buy, encoding="utf-8")
    print(f"[Alert BUY]  Subject: {subj_buy}")
    print(f"[Alert BUY]  Saved alert_email.html ({len(html_buy)//1024} KB)")

    # Generate RE-ACCUMULATION alert sample
    subj_re, html_re = build_alert_email({
        "ticker":        "ORHD.CA",
        "event_type":    "RE_ACCUMULATION",
        "event_date":    "2026-06-24",
        "constitutional_entry_price":   24.62,
        "current_price": 39.30,
        "return_pct":    59.63,
        "sector":        "Real Estate",
        "reason":        "Re-accumulation signal: R2=63.35, Score=58.52, cluster 6 days."
    })
    out_re = Path(__file__).parent / "alert_email_reaccum.html"
    out_re.write_text(html_re, encoding="utf-8")
    print(f"[Alert RE]   Subject: {subj_re}")
    print(f"[Alert RE]   Saved alert_email_reaccum.html ({len(html_re)//1024} KB)")
