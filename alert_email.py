"""
EGX Constitutional Command Center — Alert Email
Triggered on FIRST_BUY or RE_ACCUMULATION events only.
One email per constitutional event.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys as _sys
_sys.path.insert(0, str(Path(__file__).parent))
from time_authority import now_cairo as _now_cairo_ta, today_cairo as _today_cairo_ta

BASE = Path(__file__).parent

_NAVY  = "#1a3a5c"
_WHITE = "#ffffff"
_BLUE  = "#0b4a8f"
_PURPL = "#5b21b6"
_GREEN = "#155724"
_G     = "#4caf50"
_R     = "#f44336"
_A     = "#f0b840"
_MUTED = "#666666"
_BORD  = "#d0d7e2"


def _sign(r: float) -> str:
    return "+" if r >= 0 else ""

def _ret_c(r: float) -> str:
    return _GREEN if r > 0 else (_R if r < 0 else _MUTED)

def _fib_targets(entry: float) -> list[tuple[str, float]]:
    return [
        ("1.236x", round(entry * 1.236, 2)),
        ("1.382x", round(entry * 1.382, 2)),
        ("1.618x", round(entry * 1.618, 2)),
        ("2.000x", round(entry * 2.000, 2)),
    ]

def _load_dna(ticker: str) -> dict:
    dna_path = BASE / "stock_dna.db"
    if not dna_path.exists():
        return {}
    try:
        import sqlite3
        conn = sqlite3.connect(str(dna_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM stock_dna WHERE ticker=?", (ticker,)).fetchone()
        conn.close()
        return dict(row) if row else {}
    except Exception:
        return {}


def build_alert_email(event: dict) -> tuple[str, str]:
    """Returns (subject, html_body) for a single constitutional event."""
    ticker     = event.get("ticker", "TICKER")
    etype      = event.get("event_type", "FIRST_BUY")
    event_date = event.get("event_date", _today_cairo_ta().isoformat())
    entry      = float(event.get("entry_price", 0.0))
    current    = float(event.get("current_price", 0.0))
    ret_pct    = float(event.get("return_pct", 0.0))
    sector     = event.get("sector", "")
    reason     = event.get("reason", event.get("signal_reason", ""))

    type_label = "FIRST BUY" if etype == "FIRST_BUY" else "RE-ACCUMULATION"
    type_color = _BLUE if etype == "FIRST_BUY" else _PURPL
    ret_c      = _ret_c(ret_pct)

    # Subject
    subject = f"⚡ [{ticker}] CONSTITUTIONAL {type_label} — {event_date}"

    # DNA memory
    dna = _load_dna(ticker)
    mem_html = ""
    if dna and dna.get("memory_hits", 0) >= 2:
        conf   = dna.get("memory_confidence", "DEVELOPING")
        hits   = dna.get("memory_hits", 0)
        avg_r  = dna.get("avg_return_pct", 0.0)
        best_r = dna.get("best_return_pct", 0.0)
        conf_c = _G if conf == "STRONG" else (_A if conf == "CONFIRMED" else _MUTED)
        mem_html = f"""
<div style="background:#f0f8ff;border:1px solid #b8d4e8;border-radius:6px;padding:14px;margin:16px 0;">
  <div style="font-family:Arial,sans-serif;font-size:12px;font-weight:700;color:{_NAVY};margin-bottom:8px;">
    &#9733; Memory: This ticker has constitutional history
  </div>
  <table width="100%" cellpadding="0" cellspacing="0" border="0">
    <tr>
      <td style="font-family:Arial,sans-serif;font-size:12px;color:{_MUTED};padding:3px 0;">Historical Hits</td>
      <td style="font-family:Arial,sans-serif;font-size:12px;font-weight:700;color:{_NAVY};padding:3px 0;">{hits}</td>
    </tr>
    <tr>
      <td style="font-family:Arial,sans-serif;font-size:12px;color:{_MUTED};padding:3px 0;">Avg Historical Return</td>
      <td style="font-family:Arial,sans-serif;font-size:12px;font-weight:700;color:{_G};padding:3px 0;">{_sign(avg_r)}{avg_r:.1f}%</td>
    </tr>
    <tr>
      <td style="font-family:Arial,sans-serif;font-size:12px;color:{_MUTED};padding:3px 0;">Best Historical Return</td>
      <td style="font-family:Arial,sans-serif;font-size:12px;font-weight:700;color:{_G};padding:3px 0;">{_sign(best_r)}{best_r:.1f}%</td>
    </tr>
    <tr>
      <td style="font-family:Arial,sans-serif;font-size:12px;color:{_MUTED};padding:3px 0;">Memory Confidence</td>
      <td style="font-family:Arial,sans-serif;font-size:12px;font-weight:700;color:{conf_c};padding:3px 0;">{conf}</td>
    </tr>
  </table>
</div>"""

    # Fib targets
    fibs = _fib_targets(entry) if entry > 0 else []
    fib_rows = ""
    for label, price in fibs:
        fib_rows += (
            f'<tr>'
            f'<td style="font-family:Arial,sans-serif;font-size:12px;color:{_MUTED};padding:4px 0;">{label}</td>'
            f'<td style="font-family:Arial,sans-serif;font-size:12px;font-weight:700;color:{_NAVY};padding:4px 0;">{price:.2f} EGP</td>'
            f'</tr>'
        )
    fib_html = ""
    if fib_rows:
        fib_html = f"""
<div style="background:#f8faf8;border:1px solid {_BORD};border-radius:6px;padding:14px;margin:16px 0;">
  <div style="font-family:Arial,sans-serif;font-size:12px;font-weight:700;color:{_NAVY};margin-bottom:8px;">
    Next Fibonacci Targets
  </div>
  <table width="100%" cellpadding="0" cellspacing="0" border="0">{fib_rows}</table>
</div>"""

    # Reason block
    reason_html = ""
    if reason:
        reason_html = f"""
<div style="background:#fffcf0;border:1px solid #e8d5a0;border-radius:6px;padding:12px;margin:14px 0;">
  <div style="font-family:Arial,sans-serif;font-size:11px;font-weight:700;color:{_MUTED};margin-bottom:4px;">WHY — Constitutional Signal Reason</div>
  <div style="font-family:Arial,sans-serif;font-size:13px;color:#333;">{reason}</div>
</div>"""

    now_s    = _now_cairo_ta().strftime("%d %b %Y %H:%M Cairo")

    html_body = f"""<!DOCTYPE html>
<html>
<body style="margin:0;padding:20px;background:#eef2f7;">
<table width="600" cellpadding="0" cellspacing="0" border="0" align="center"
  style="background:#ffffff;border:1px solid {_BORD};max-width:600px;">
  <tr>
    <td style="background:{_NAVY};padding:20px 28px;">
      <div style="font-family:Arial,sans-serif;color:#8fb8d8;font-size:10px;letter-spacing:1px;
           text-transform:uppercase;margin-bottom:4px;">EGX Constitutional Command Center</div>
      <div style="font-family:Arial,sans-serif;color:{_WHITE};font-size:18px;font-weight:700;">
        &#9889; Constitutional Alert</div>
      <div style="font-family:Arial,sans-serif;color:#8fb8d8;font-size:11px;margin-top:6px;">{now_s}</div>
    </td>
  </tr>
  <tr>
    <td style="padding:20px 28px;">

      <!-- Event Type Badge -->
      <div style="text-align:center;margin-bottom:18px;">
        <span style="background:{type_color}22;color:{type_color};padding:6px 20px;
              border-radius:20px;font-family:Arial,sans-serif;font-size:14px;font-weight:700;
              border:1px solid {type_color}44;">
          &#9679; {type_label}
        </span>
      </div>

      <!-- Ticker + Date -->
      <div style="text-align:center;margin-bottom:18px;">
        <div style="font-family:Arial,sans-serif;font-size:32px;font-weight:700;color:{_NAVY};">{ticker}</div>
        <div style="font-family:Arial,sans-serif;font-size:12px;color:{_MUTED};">{sector} &nbsp;&middot;&nbsp; {event_date}</div>
      </div>

      <!-- Key Metrics -->
      <table width="100%" cellpadding="0" cellspacing="0" border="0"
        style="background:#f8f9fb;border:1px solid {_BORD};border-radius:6px;margin-bottom:16px;">
        <tr>
          <td width="33%" align="center" style="padding:14px;border-right:1px solid {_BORD};">
            <div style="font-family:Arial,sans-serif;font-size:11px;color:{_MUTED};text-transform:uppercase;margin-bottom:4px;">Entry Zone</div>
            <div style="font-family:Arial,sans-serif;font-size:20px;font-weight:700;color:{_NAVY};">{entry:.2f} EGP</div>
          </td>
          <td width="33%" align="center" style="padding:14px;border-right:1px solid {_BORD};">
            <div style="font-family:Arial,sans-serif;font-size:11px;color:{_MUTED};text-transform:uppercase;margin-bottom:4px;">Current Price</div>
            <div style="font-family:Arial,sans-serif;font-size:20px;font-weight:700;color:{_NAVY};">{current:.2f}</div>
          </td>
          <td width="33%" align="center" style="padding:14px;">
            <div style="font-family:Arial,sans-serif;font-size:11px;color:{_MUTED};text-transform:uppercase;margin-bottom:4px;">Return</div>
            <div style="font-family:Arial,sans-serif;font-size:20px;font-weight:700;color:{ret_c};">{_sign(ret_pct)}{ret_pct:.1f}%</div>
          </td>
        </tr>
      </table>

      {reason_html}
      {mem_html}
      {fib_html}

      <!-- Dashboard Link -->
      <div style="text-align:center;margin:20px 0;">
        <a href="https://shadygad01.github.io/smartlist/"
           style="background:{_NAVY};color:{_WHITE};padding:12px 28px;
                  border-radius:6px;font-family:Arial,sans-serif;font-size:13px;
                  font-weight:700;text-decoration:none;display:inline-block;">
          View Dashboard &#8594;
        </a>
      </div>

      <!-- Footer -->
      <div style="border-top:1px solid {_BORD};padding-top:14px;margin-top:8px;
           font-family:Arial,sans-serif;font-size:10px;color:#bbb;text-align:center;">
        EGX Constitutional Command Center &nbsp;&middot;&nbsp; Append-Only &middot; Immutable Events<br>
        This alert is for informational purposes only and does not constitute financial advice.
        Past constitutional signals do not guarantee future returns.
        All investments carry risk. Consult a licensed financial advisor before making investment decisions.
      </div>

    </td>
  </tr>
</table>
</body>
</html>"""

    return subject, html_body


if __name__ == "__main__":
    subj, html = build_alert_email({
        "ticker": "TEST",
        "event_type": "FIRST_BUY",
        "event_date": "2026-06-21",
        "entry_price": 10.0,
        "current_price": 12.5,
        "return_pct": 25.0,
        "sector": "Banks",
        "reason": "Constitutional threshold crossed: R2=60.5, Score=42.1, Momentum confirmed."
    })
    out = Path(__file__).parent / "alert_email.html"
    out.write_text(html, encoding="utf-8")
    print(f"Subject: {subj}")
    print(f"Saved alert_email.html ({len(html)//1024} KB)")
