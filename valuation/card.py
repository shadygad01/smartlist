"""
valuation.card — Institutional Valuation Card HTML renderers.

Two rendering modes:
  render_email_card(ticker, current_price)   → HTML for email (light theme)
  render_dashboard_card(ticker, current_price) → HTML for dashboard (dark theme)

Both call get_valuation_card() exactly once per ticker — one DB read.
Return empty string when no valuation data is available (graceful degradation).

Card content (spec-mandated):
  Current Price | Fair Value | Upside % | Bull Case | Base Case | Bear Case
  Analyst Consensus | Last Financial Statement Date | Valuation Date
"""
from __future__ import annotations
from valuation.db import get_valuation_card


def _upside(fair: float, current: float) -> float | None:
    if not current or not fair:
        return None
    return round((fair - current) / current * 100, 1)


def _fmt(v: float | None, decimals: int = 2) -> str:
    if v is None:
        return "—"
    return f"{v:,.{decimals}f}"


def render_email_card(ticker: str, current_price: float | None) -> str:
    """Return light-theme HTML valuation card for email, or '' if no data."""
    card = get_valuation_card(ticker)
    if not card:
        return ""

    fv       = card.get("weighted_fair_value")
    bull     = card.get("bull_case")
    base     = card.get("base_case")
    bear     = card.get("bear_case")
    consensus = card.get("analyst_consensus_price")
    last_yr  = card.get("last_stmt_year")
    val_date = card.get("valuation_date", "")

    if not fv:
        return ""

    cp       = current_price or 0.0
    upside   = _upside(fv, cp)
    up_sign  = "+" if (upside or 0) >= 0 else ""
    up_color = "#155724" if (upside or 0) >= 0 else "#721c24"
    up_bg    = "#d4edda" if (upside or 0) >= 0 else "#f8d7da"

    # Color: green if price < fair value, amber otherwise
    price_vs_fair = "DISCOUNT" if cp < (fv or 0) else "PREMIUM"
    pvf_color = "#155724" if price_vs_fair == "DISCOUNT" else "#856404"

    rows = [
        ("Current Price",             f"{_fmt(cp)} EGP"),
        ("Fair Value (IVE)",          f"{_fmt(fv)} EGP"),
        ("Upside / Downside",         f'{up_sign}{_fmt(upside, 1)}%' if upside is not None else "—"),
        ("Bull Case",                 f"{_fmt(bull)} EGP"),
        ("Base Case",                 f"{_fmt(base)} EGP"),
        ("Bear Case",                 f"{_fmt(bear)} EGP"),
        ("Analyst Consensus Target",  f"{_fmt(consensus)} EGP" if consensus else "—"),
        ("Last Financial Statement",  str(last_yr) if last_yr else "—"),
        ("Valuation Date",            val_date or "—"),
    ]

    rows_html = ""
    for lbl, val in rows:
        rows_html += (
            f'<tr style="border-bottom:1px solid #e0e8f0;">'
            f'<td style="padding:5px 10px;font-family:Arial,sans-serif;font-size:11px;'
            f'color:#888888;white-space:nowrap;">{lbl}</td>'
            f'<td style="padding:5px 10px;font-family:Arial,sans-serif;font-size:12px;'
            f'font-weight:600;color:#1a3a5c;">{val}</td>'
            f'</tr>'
        )

    return (
        f'<div style="background:#f0f4ff;border:1px solid #b8cce4;border-radius:7px;'
        f'margin:8px 0 4px 0;padding:0;overflow:hidden;">'
        f'<div style="background:#e8eef8;padding:6px 10px;display:flex;'
        f'align-items:center;justify-content:space-between;">'
        f'<span style="font-family:Arial,sans-serif;font-size:10px;font-weight:700;'
        f'color:#1a3a5c;letter-spacing:0.6px;text-transform:uppercase;">'
        f'&#127974; Institutional Valuation</span>'
        f'<span style="background:{up_bg};color:{up_color};padding:2px 8px;'
        f'border-radius:10px;font-size:10px;font-weight:700;">'
        f'{price_vs_fair} &nbsp; {up_sign}{_fmt(upside, 1)}%</span>'
        f'</div>'
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0">'
        f'{rows_html}'
        f'</table>'
        f'<div style="font-family:Arial,sans-serif;font-size:9px;color:#aaaaaa;'
        f'padding:4px 10px;text-align:right;">'
        f'IVE — information only &middot; not a recommendation</div>'
        f'</div>'
    )


def render_dashboard_card(ticker: str, current_price: float | None) -> str:
    """Return dark-theme HTML valuation card for dashboard, or '' if no data."""
    card = get_valuation_card(ticker)
    if not card:
        return ""

    fv        = card.get("weighted_fair_value")
    bull      = card.get("bull_case")
    base      = card.get("base_case")
    bear      = card.get("bear_case")
    consensus = card.get("analyst_consensus_price")
    last_yr   = card.get("last_stmt_year")
    val_date  = card.get("valuation_date", "")

    if not fv:
        return ""

    cp      = current_price or 0.0
    upside  = _upside(fv, cp)
    up_sign = "+" if (upside or 0) >= 0 else ""
    up_color = "#4caf50" if (upside or 0) >= 0 else "#f44336"
    upside_str = f"{up_sign}{_fmt(upside, 1)}%" if upside is not None else "—"

    cells = [
        ("Fair Value",  f"{_fmt(fv)} EGP", "#50d8d0"),
        ("Upside",      upside_str,         up_color),
        ("Bull Case",   f"{_fmt(bull)} EGP", "#4caf50"),
        ("Base Case",   f"{_fmt(base)} EGP", "#50d8d0"),
        ("Bear Case",   f"{_fmt(bear)} EGP", "#f0b840"),
        ("Consensus",   f"{_fmt(consensus)} EGP" if consensus else "—", "#9c6fff"),
    ]

    boxes = ""
    for lbl, val, col in cells:
        boxes += (
            f'<div style="background:#0b0c1a;border:1px solid #252645;border-radius:6px;'
            f'padding:8px 10px;min-width:90px;">'
            f'<div style="font-size:9px;color:#8b8fa8;text-transform:uppercase;'
            f'letter-spacing:0.5px;margin-bottom:3px;">{lbl}</div>'
            f'<div style="font-size:13px;font-weight:700;color:{col};">{val}</div>'
            f'</div>'
        )

    meta = (
        f'<span style="font-size:10px;color:#8b8fa8;">Stmt: {last_yr or "—"}'
        f' &nbsp;&middot;&nbsp; Valued: {val_date or "—"}'
        f' &nbsp;&middot;&nbsp; Info only</span>'
    )

    return (
        f'<div style="margin-top:10px;">'
        f'<div style="font-size:11px;font-weight:700;color:#50d8d0;'
        f'letter-spacing:0.5px;display:flex;align-items:center;gap:6px;'
        f'margin-bottom:8px;">'
        f'<span>&#127974;</span> Institutional Valuation'
        f'</div>'
        f'<div style="padding:10px;background:#10112a;'
        f'border:1px solid #252645;border-radius:7px;">'
        f'<div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:8px;">'
        f'{boxes}'
        f'</div>'
        f'{meta}'
        f'</div>'
        f'</div>'
    )
