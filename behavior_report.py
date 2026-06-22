"""
Behavior Report Generator
==========================
يُنتج تقرير HTML تفصيلي بكل المتغيرات والنتائج،
ثم يُرسله على الإيميل أو يحفظه كملف.

التشغيل:
    python behavior_report.py               ← يُنتج + يُرسل بالإيميل
    python behavior_report.py --no-email    ← يُنتج ويحفظ بدون إيميل
    python behavior_report.py --days 30     ← آخر 30 يوم فقط
"""

import json
import os
import sys
import argparse
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta

EXTENDED_LOG  = "extended_signal_log.json"
REPORT_FILE   = "reports/behavior_report.html"
TO_EMAIL      = "shady.gad@live.com"
WIN_THRESHOLD = 0.07   # r20d >= 7% = win


# ── I/O ───────────────────────────────────────────────────────────────────────

def _outcome_cat(r20d: float) -> str:
    if r20d >= 0.20: return "large"
    if r20d >= 0.08: return "medium"
    if r20d >= 0.04: return "small"
    return "flat"


def _load_signals_from_db(days_back: int = 0) -> list:
    """Read resolved signals from egx_research.db — uses v_all_signals when available."""
    try:
        from signal_db import DB_PATH, get_conn
    except ImportError:
        return []

    try:
        conn = get_conn(DB_PATH)
        has_view = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='view' AND name='v_all_signals'"
        ).fetchone()

        if has_view:
            where = ""
            if days_back > 0:
                cutoff = (date.today() - timedelta(days=days_back)).isoformat()
                where = f"WHERE signal_date >= '{cutoff}'"
            rows = conn.execute(f"""
                SELECT
                    id, symbol, signal_date,
                    NULL AS signal_type, raw_score,
                    r1_price, r2_ob, r3_liquidity, r4_htf,
                    r5_avwap, r6_macd, r7_div, r8_demand,
                    close_price AS price, NULL AS discount_depth,
                    NULL AS is_ramadan, NULL AS is_cbe,
                    NULL AS stock_tier, NULL AS sector,
                    r20d, mfe_20d, mae_20d
                FROM v_all_signals
                {where}
                ORDER BY signal_date
            """).fetchall()
        else:
            where = ""
            if days_back > 0:
                cutoff = (date.today() - timedelta(days=days_back)).isoformat()
                where = f"WHERE s.signal_date >= '{cutoff}'"
            rows = conn.execute(f"""
                SELECT
                    s.id, s.symbol, s.signal_date, s.signal_type, s.raw_score,
                    s.r1_price, s.r2_ob, s.r3_liquidity, s.r4_htf,
                    s.r5_avwap, s.r6_macd, s.r7_div, s.r8_demand,
                    s.price, s.discount_depth,
                    s.is_ramadan, s.is_cbe, s.stock_tier, s.sector,
                    b.r20d, b.mfe_20d, b.mae_20d
                FROM signals s
                JOIN bottom_quality b ON b.signal_id = s.id
                {where}
                ORDER BY s.signal_date
            """).fetchall()
        conn.close()
    except Exception as e:
        print(f"[Report] DB load error: {e}")
        return []

    signals = []
    for row in rows:
        (sig_id, symbol, sig_date, sig_type, raw_score,
         r1, r2, r3, r4, r5, r6, r7, r8,
         price, disc_depth,
         is_ram, is_cbe, stock_tier, sector,
         r20d, mfe, mae) = row

        if r20d is None:
            continue

        r20d_f = float(r20d)
        signals.append({
            "id":        sig_id,
            "symbol":    symbol,
            "date":      sig_date,
            "signal":    sig_type or "buy",
            "raw_score": int(raw_score) if raw_score is not None else 0,
            "outcome":   _outcome_cat(r20d_f),
            "r20d":      r20d_f,
            "mfe":       float(mfe) if mfe is not None else None,
            "mae":       float(mae) if mae is not None else None,
            "category":  _outcome_cat(r20d_f),
            "smc": {
                "r1_price":    int(r1) if r1 is not None else 0,
                "r2_ob":       int(r2) if r2 is not None else 0,
                "r3_liquidity":int(r3) if r3 is not None else 0,
                "r4_htf":      int(r4) if r4 is not None else 0,
                "r5_avwap":    int(r5) if r5 is not None else 0,
                "r6_macd":     int(r6) if r6 is not None else 0,
                "r7_div":      int(r7) if r7 is not None else 0,
                "r8_demand":   int(r8) if r8 is not None else 0,
            },
            "context": {
                "is_ramadan":  bool(is_ram),
                "is_cbe":      bool(is_cbe),
                "stock_tier":  float(stock_tier) if stock_tier else 1.0,
                "sector":      sector or "",
            },
            "price_ctx": {
                "discount_depth": float(disc_depth) if disc_depth is not None else 0.0,
            },
        })
    return signals


def _load_signals(days_back: int = 0) -> list:
    # Try extended_signal_log.json first (live signals logged by extended_logger)
    if os.path.exists(EXTENDED_LOG):
        try:
            with open(EXTENDED_LOG, "r", encoding="utf-8") as f:
                data = json.load(f)
            signals = data.get("signals", [])
            if days_back > 0:
                cutoff = (date.today() - timedelta(days=days_back)).isoformat()
                signals = [s for s in signals if s.get("date", "") >= cutoff]
            if signals:
                return signals
        except Exception:
            pass

    # Fallback: read from egx_research.db (historical + live signals with BQ)
    return _load_signals_from_db(days_back)


# ── Statistics Helpers ────────────────────────────────────────────────────────

def _stats(group: list) -> dict:
    """
    يحسب إحصاءات أساسية لمجموعة من الإشارات المحسومة.
    """
    if not group:
        return {"n": 0}

    rets = [s["r20d"] for s in group if s.get("r20d") is not None]
    mfes = [s["mfe"]  for s in group if s.get("mfe")  is not None]
    maes = [s["mae"]  for s in group if s.get("mae")  is not None]

    if not rets:
        return {"n": len(group)}

    wins   = [r for r in rets if r >= WIN_THRESHOLD]
    losses = [r for r in rets if r <  WIN_THRESHOLD]

    avg_ret = statistics.mean(rets)
    win_rate = len(wins) / len(rets) if rets else 0

    gross_profit = sum(r for r in rets if r > 0)
    gross_loss   = abs(sum(r for r in rets if r < 0))
    pf = round(gross_profit / gross_loss, 2) if gross_loss > 0 else 999

    cats = defaultdict(int)
    for s in group:
        cats[s.get("category", "?")] += 1

    return {
        "n":        len(group),
        "n_ret":    len(rets),
        "win_rate": round(win_rate * 100, 1),
        "avg_ret":  round(avg_ret * 100, 2),
        "avg_mfe":  round(statistics.mean(mfes) * 100, 2) if mfes else None,
        "avg_mae":  round(statistics.mean(maes) * 100, 2) if maes else None,
        "pf":       pf,
        "cats":     dict(cats),
    }


def _color_wr(wr):
    if wr >= 45: return "#155724"
    if wr >= 30: return "#856404"
    return "#721c24"

def _color_ret(ret):
    if ret is None: return "#888"
    if ret >= 10: return "#155724"
    if ret >= 4:  return "#856404"
    if ret >= 0:  return "#444"
    return "#721c24"

def _fmt_pct(v, decimals=1):
    if v is None: return "—"
    return f"{v:+.{decimals}f}%"

def _fmt_n(v):
    return "—" if v is None else str(v)


# ── HTML Building Blocks ──────────────────────────────────────────────────────

def _kpi(label, value, color="#1a3a5c", bg="#f4f8ff", note=""):
    return (
        f'<td style="padding:14px 18px;background:{bg};border:1px solid #d0e4f7;'
        f'text-align:center;min-width:120px;">'
        f'<div style="font-family:Arial,sans-serif;font-size:10px;color:#888;'
        f'text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;">{label}</div>'
        f'<div style="font-family:Arial,sans-serif;font-size:22px;font-weight:bold;color:{color};">{value}</div>'
        f'{"<div style=font-family:Arial,sans-serif;font-size:10px;color:#aaa;margin-top:2px;>" + note + "</div>" if note else ""}'
        f'</td>'
    )

def _section(title):
    return (
        f'<tr><td style="padding:22px 0 6px 0;">'
        f'<div style="font-family:Arial,sans-serif;font-size:13px;font-weight:bold;'
        f'color:#1a3a5c;border-left:4px solid #1a3a5c;padding-left:8px;'
        f'letter-spacing:0.5px;">{title}</div>'
        f'</td></tr>'
    )

def _table_header(*cols):
    ths = "".join(
        f'<th style="padding:8px 12px;font-family:Arial,sans-serif;font-size:11px;'
        f'color:#fff;text-align:left;white-space:nowrap;">{c}</th>'
        for c in cols
    )
    return f'<thead><tr style="background:#1a3a5c;">{ths}</tr></thead>'

def _stats_row(label, st, bg="#fff"):
    if st.get("n", 0) == 0:
        return ""
    wr_c  = _color_wr(st.get("win_rate", 0))
    ret_c = _color_ret(st.get("avg_ret"))
    cats  = st.get("cats", {})
    cat_str = (
        f'<span style="color:#721c24;">F:{cats.get("flat",0)}</span> '
        f'<span style="color:#856404;">S:{cats.get("small",0)}</span> '
        f'<span style="color:#0a3622;">M:{cats.get("medium",0)}</span> '
        f'<span style="color:#084298;">L:{cats.get("large",0)}</span>'
    )
    return (
        f'<tr style="background:{bg};border-bottom:1px solid #eee;">'
        f'<td style="padding:8px 12px;font-family:Arial,sans-serif;font-size:12px;font-weight:600;">{label}</td>'
        f'<td style="padding:8px 12px;font-family:Arial,sans-serif;font-size:12px;text-align:center;">{st["n"]}</td>'
        f'<td style="padding:8px 12px;font-family:Arial,sans-serif;font-size:12px;text-align:center;font-weight:bold;color:{wr_c};">{st.get("win_rate","—")}%</td>'
        f'<td style="padding:8px 12px;font-family:Arial,sans-serif;font-size:12px;text-align:center;font-weight:bold;color:{ret_c};">{_fmt_pct(st.get("avg_ret"))}</td>'
        f'<td style="padding:8px 12px;font-family:Arial,sans-serif;font-size:12px;text-align:center;color:#155724;">{_fmt_pct(st.get("avg_mfe"))}</td>'
        f'<td style="padding:8px 12px;font-family:Arial,sans-serif;font-size:12px;text-align:center;color:#721c24;">{_fmt_pct(st.get("avg_mae"))}</td>'
        f'<td style="padding:8px 12px;font-family:Arial,sans-serif;font-size:12px;text-align:center;">{st.get("pf","—")}</td>'
        f'<td style="padding:8px 12px;font-family:Arial,sans-serif;font-size:11px;">{cat_str}</td>'
        f'</tr>'
    )


def _analysis_table(title, groups_data, bg_alt="#f9fafb"):
    """
    groups_data: list of (label, stats_dict)
    يبني جدول تحليلي كامل.
    """
    rows_html = ""
    for i, (label, st) in enumerate(groups_data):
        bg = bg_alt if i % 2 else "#fff"
        rows_html += _stats_row(label, st, bg=bg)

    if not rows_html:
        return ""

    header = _table_header(
        title, "الإشارات", "Win Rate", "Avg R20d", "Avg MFE", "Avg MAE", "Profit Factor", "F / S / M / L"
    )
    return (
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="border:1px solid #d0e4f7;border-collapse:collapse;margin-bottom:6px;">'
        f'{header}<tbody>{rows_html}</tbody></table>'
    )


# ── Report Sections ───────────────────────────────────────────────────────────

def _section_score_buckets(resolved):
    buckets = [
        ("Score 35–45",  [s for s in resolved if 35 <= s["raw_score"] < 45]),
        ("Score 45–55",  [s for s in resolved if 45 <= s["raw_score"] < 55]),
        ("Score 55–65",  [s for s in resolved if 55 <= s["raw_score"] < 65]),
        ("Score 65–75",  [s for s in resolved if 65 <= s["raw_score"] < 75]),
        ("Score 75+",    [s for s in resolved if s["raw_score"] >= 75]),
    ]
    return _analysis_table("Score Range", [(lbl, _stats(grp)) for lbl, grp in buckets])


def _section_r3_liquidity(resolved):
    groups = [
        ("r3 = 20 (Sweep & Reverse ✓)",  [s for s in resolved if s.get("smc", {}).get("r3_liquidity", 0) == 20]),
        ("r3 = 12 (Rejection Wick)",      [s for s in resolved if s.get("smc", {}).get("r3_liquidity", 0) == 12]),
        ("r3 = 8  (Equal Lows)",          [s for s in resolved if s.get("smc", {}).get("r3_liquidity", 0) == 8]),
        ("r3 = 0  (No Liquidity Event)",  [s for s in resolved if s.get("smc", {}).get("r3_liquidity", 0) == 0]),
    ]
    return _analysis_table("Liquidity (r3)", [(lbl, _stats(grp)) for lbl, grp in groups])


def _section_r8_demand(resolved):
    groups = [
        ("r8 = 15 (SV + HVN كليهما)",    [s for s in resolved if s.get("smc", {}).get("r8_demand", 0) >= 15]),
        ("r8 = 9–14 (SV أو HVN فقط)",    [s for s in resolved if 9 <= s.get("smc", {}).get("r8_demand", 0) < 15]),
        ("r8 = 1–8  (جزئي)",              [s for s in resolved if 1 <= s.get("smc", {}).get("r8_demand", 0) < 9]),
        ("r8 = 0    (لا Demand Zone)",    [s for s in resolved if s.get("smc", {}).get("r8_demand", 0) == 0]),
    ]
    return _analysis_table("Demand Zone (r8)", [(lbl, _stats(grp)) for lbl, grp in groups])


def _section_r1_price(resolved):
    groups = [
        ("r1 ≥ 24 (Deep Discount)",     [s for s in resolved if s.get("smc", {}).get("r1_price", 0) >= 24]),
        ("r1 = 18–23 (Buy Zone)",       [s for s in resolved if 18 <= s.get("smc", {}).get("r1_price", 0) < 24]),
        ("r1 = 15–17 (Border)",         [s for s in resolved if 15 <= s.get("smc", {}).get("r1_price", 0) < 18]),
        ("r1 < 15    (Mid-Discount)",   [s for s in resolved if s.get("smc", {}).get("r1_price", 0) < 15]),
    ]
    return _analysis_table("Price Position (r1)", [(lbl, _stats(grp)) for lbl, grp in groups])


def _section_htf(resolved):
    groups = [
        ("r4 = 10 (كل مكونات HTF ✓)",  [s for s in resolved if s.get("smc", {}).get("r4_htf", 0) >= 9]),
        ("r4 = 5–8 (جزئي)",            [s for s in resolved if 5 <= s.get("smc", {}).get("r4_htf", 0) < 9]),
        ("r4 = 0–4 (ضعيف/هابط)",       [s for s in resolved if s.get("smc", {}).get("r4_htf", 0) < 5]),
    ]
    return _analysis_table("Higher Timeframe (r4)", [(lbl, _stats(grp)) for lbl, grp in groups])


def _section_signal_type(resolved):
    types = sorted({s.get("signal", "?") for s in resolved})
    groups = [(t, [s for s in resolved if s.get("signal") == t]) for t in types]
    return _analysis_table("Signal Type", [(lbl, _stats(grp)) for lbl, grp in groups])


def _section_context(resolved):
    groups = [
        ("رمضان",            [s for s in resolved if s.get("context", {}).get("is_ramadan")]),
        ("خارج رمضان",       [s for s in resolved if not s.get("context", {}).get("is_ramadan")]),
        ("نافذة CBE",        [s for s in resolved if s.get("context", {}).get("is_cbe")]),
        ("خارج نافذة CBE",   [s for s in resolved if not s.get("context", {}).get("is_cbe")]),
        ("Tier A  (×1.15)",  [s for s in resolved if s.get("context", {}).get("stock_tier", 1.0) == 1.15]),
        ("Tier B  (×1.07)",  [s for s in resolved if s.get("context", {}).get("stock_tier", 1.0) == 1.07]),
        ("Default (×1.00)",  [s for s in resolved if s.get("context", {}).get("stock_tier", 1.0) == 1.0]),
        ("Tier D  (×0.88)",  [s for s in resolved if s.get("context", {}).get("stock_tier", 1.0) == 0.88]),
    ]
    return _analysis_table("Context & Tier", [(lbl, _stats(grp)) for lbl, grp in groups])


def _section_per_stock(resolved):
    by_sym = defaultdict(list)
    for s in resolved:
        by_sym[s["symbol"]].append(s)

    rows_sorted = sorted(
        [(sym, _stats(sigs)) for sym, sigs in by_sym.items()],
        key=lambda x: x[1].get("win_rate", 0),
        reverse=True,
    )
    return _analysis_table("Per Stock (sorted by Win Rate)", rows_sorted)


def _section_discount_depth(resolved):
    groups = [
        ("عمق 80–100% (قريب جداً من Low)",  [s for s in resolved if s.get("price_ctx", {}).get("discount_depth", 0) >= 0.80]),
        ("عمق 60–80%",                       [s for s in resolved if 0.60 <= s.get("price_ctx", {}).get("discount_depth", 0) < 0.80]),
        ("عمق 40–60%",                       [s for s in resolved if 0.40 <= s.get("price_ctx", {}).get("discount_depth", 0) < 0.60]),
        ("عمق < 40%  (قريب من EQ)",          [s for s in resolved if s.get("price_ctx", {}).get("discount_depth", 0) < 0.40]),
    ]
    return _analysis_table("Discount Depth", [(lbl, _stats(grp)) for lbl, grp in groups])


def _section_full_table(resolved):
    """جدول كامل بكل الإشارات المحسومة وكل متغيراتها."""
    if not resolved:
        return "<p style='font-family:Arial;font-size:12px;color:#888;'>No resolved signals.</p>"

    sorted_sigs = sorted(resolved, key=lambda s: s.get("date", ""), reverse=True)

    header = (
        '<table width="100%" cellpadding="0" cellspacing="0" border="0" '
        'style="border:1px solid #d0e4f7;border-collapse:collapse;font-size:11px;">'
        '<thead><tr style="background:#1a3a5c;">'
    )
    for col in ["Date", "Symbol", "Signal", "Score", "r1", "r3", "r8",
                "Depth", "Pattern", "Sector", "Context",
                "R5d", "R10d", "R20d", "MFE", "MAE", "Category"]:
        header += (
            f'<th style="padding:6px 8px;color:#fff;font-family:Arial;'
            f'font-size:10px;white-space:nowrap;">{col}</th>'
        )
    header += '</tr></thead><tbody>'

    rows_html = ""
    for i, s in enumerate(sorted_sigs):
        bg   = "#fff" if i % 2 == 0 else "#f9fafb"
        smc  = s.get("smc", {})
        pc   = s.get("price_ctx", {})
        ctx  = s.get("context", {})
        cat  = s.get("category", "—")
        cat_c = {"large": "#084298", "medium": "#0a3622",
                 "small": "#856404", "flat": "#721c24"}.get(cat, "#888")

        r20_raw = s.get("r20d")
        r20_c = _color_ret(r20_raw * 100 if r20_raw is not None else None)

        rows_html += (
            f'<tr style="background:{bg};border-bottom:1px solid #eee;">'
            f'<td style="padding:5px 8px;white-space:nowrap;">{s.get("date","")}</td>'
            f'<td style="padding:5px 8px;font-weight:600;color:#1a3a5c;">{s["symbol"].replace(".CA","")}</td>'
            f'<td style="padding:5px 8px;white-space:nowrap;">{s.get("signal","")}</td>'
            f'<td style="padding:5px 8px;text-align:center;font-weight:bold;">{s.get("raw_score","")}</td>'
            f'<td style="padding:5px 8px;text-align:center;">{smc.get("r1_price","")}</td>'
            f'<td style="padding:5px 8px;text-align:center;">{smc.get("r3_liquidity","")}</td>'
            f'<td style="padding:5px 8px;text-align:center;">{smc.get("r8_demand","")}</td>'
            f'<td style="padding:5px 8px;text-align:center;">{round(pc.get("discount_depth",0)*100)}%</td>'
            f'<td style="padding:5px 8px;text-align:center;">{s.get("pattern",{}).get("score","")}</td>'
            f'<td style="padding:5px 8px;white-space:nowrap;">{ctx.get("sector","")[:16]}</td>'
            f'<td style="padding:5px 8px;white-space:nowrap;font-size:10px;">'
            f'{"R" if ctx.get("is_ramadan") else ""}{"C" if ctx.get("is_cbe") else ""}'
            f'{ctx.get("stock_tier",1.0)}</td>'
            f'<td style="padding:5px 8px;text-align:center;color:{_color_ret(s.get("r5d",0) and s["r5d"]*100)};">{_fmt_pct(s.get("r5d") and s["r5d"]*100, 1)}</td>'
            f'<td style="padding:5px 8px;text-align:center;color:{_color_ret(s.get("r10d",0) and s["r10d"]*100)};">{_fmt_pct(s.get("r10d") and s["r10d"]*100, 1)}</td>'
            f'<td style="padding:5px 8px;text-align:center;font-weight:bold;color:{r20_c};">{_fmt_pct(r20_raw and r20_raw*100, 1)}</td>'
            f'<td style="padding:5px 8px;text-align:center;color:#155724;">{_fmt_pct(s.get("mfe") and s["mfe"]*100, 1)}</td>'
            f'<td style="padding:5px 8px;text-align:center;color:#721c24;">{_fmt_pct(s.get("mae") and s["mae"]*100, 1)}</td>'
            f'<td style="padding:5px 8px;text-align:center;font-weight:bold;color:{cat_c};">{cat.upper()}</td>'
            f'</tr>'
        )

    return header + rows_html + "</tbody></table>"


def _section_pending(pending):
    """جدول الإشارات التي لم تُحسَم بعد."""
    if not pending:
        return "<p style='font-family:Arial;font-size:12px;color:#888;'>No pending signals.</p>"

    sorted_p = sorted(pending, key=lambda s: s.get("date", ""), reverse=True)

    header = (
        '<table width="100%" cellpadding="0" cellspacing="0" border="0" '
        'style="border:1px solid #ffeeba;border-collapse:collapse;font-size:11px;">'
        '<thead><tr style="background:#856404;">'
    )
    for col in ["Date", "Symbol", "Signal", "Score", "r1", "r3", "r8", "Depth", "Pattern", "Sector"]:
        header += (
            f'<th style="padding:6px 8px;color:#fff;font-family:Arial;'
            f'font-size:10px;white-space:nowrap;">{col}</th>'
        )
    header += "</tr></thead><tbody>"

    rows_html = ""
    for i, s in enumerate(sorted_p):
        bg  = "#fff" if i % 2 == 0 else "#fffdf0"
        smc = s.get("smc", {})
        pc  = s.get("price_ctx", {})
        ctx = s.get("context", {})
        rows_html += (
            f'<tr style="background:{bg};border-bottom:1px solid #ffeeba;">'
            f'<td style="padding:5px 8px;white-space:nowrap;">{s.get("date","")}</td>'
            f'<td style="padding:5px 8px;font-weight:600;color:#856404;">{s["symbol"].replace(".CA","")}</td>'
            f'<td style="padding:5px 8px;white-space:nowrap;">{s.get("signal","")}</td>'
            f'<td style="padding:5px 8px;text-align:center;font-weight:bold;">{s.get("raw_score","")}</td>'
            f'<td style="padding:5px 8px;text-align:center;">{smc.get("r1_price","")}</td>'
            f'<td style="padding:5px 8px;text-align:center;">{smc.get("r3_liquidity","")}</td>'
            f'<td style="padding:5px 8px;text-align:center;">{smc.get("r8_demand","")}</td>'
            f'<td style="padding:5px 8px;text-align:center;">{round(pc.get("discount_depth",0)*100)}%</td>'
            f'<td style="padding:5px 8px;text-align:center;">{s.get("pattern",{}).get("score","")}</td>'
            f'<td style="padding:5px 8px;white-space:nowrap;">{ctx.get("sector","")[:16]}</td>'
            f'</tr>'
        )
    return header + rows_html + "</tbody></table>"


# ── Main Report Builder ───────────────────────────────────────────────────────

def build_report(days_back: int = 0) -> str:
    """يبني HTML التقرير الكامل."""
    all_signals = _load_signals(days_back)
    resolved    = [s for s in all_signals if s.get("outcome") not in ("pending", None)]
    pending     = [s for s in all_signals if s.get("outcome") == "pending"]

    now_str  = datetime.now().strftime("%A, %d %B %Y  |  %H:%M")
    period   = f"آخر {days_back} يوم" if days_back else "كل الفترة"
    date_range = ""
    if resolved:
        dates = [s["date"] for s in resolved if s.get("date")]
        if dates:
            date_range = f"{min(dates)} → {max(dates)}"

    # ── KPI Summary ──────────────────────────────────────────────────
    st_all = _stats(resolved)
    n      = st_all.get("n", 0)
    wr     = st_all.get("win_rate", 0)
    ar     = st_all.get("avg_ret")
    am     = st_all.get("avg_mfe")
    amae   = st_all.get("avg_mae")
    pf     = st_all.get("pf", 0)

    kpi_row = (
        f'<table cellpadding="0" cellspacing="4" border="0" width="100%"><tr>'
        f'{_kpi("Resolved Signals", str(n))}'
        f'{_kpi("Win Rate (r20d≥7%)", f"{wr}%", color=_color_wr(wr))}'
        f'{_kpi("Avg Return 20d", _fmt_pct(ar), color=_color_ret(ar))}'
        f'{_kpi("Avg MFE", _fmt_pct(am), color="#155724", bg="#f0fff4")}'
        f'{_kpi("Avg MAE", _fmt_pct(amae), color="#721c24", bg="#fff5f5")}'
        f'{_kpi("Profit Factor", str(pf))}'
        f'{_kpi("Pending", str(len(pending)), color="#856404", bg="#fffdf0")}'
        f'</tr></table>'
    )

    # ── Category Breakdown ───────────────────────────────────────────
    cats = st_all.get("cats", {})
    cat_html = (
        '<table cellpadding="0" cellspacing="4" border="0" width="100%"><tr>'
        f'{_kpi("Flat (<4%)",     str(cats.get("flat",0)),   color="#721c24", bg="#fff5f5")}'
        f'{_kpi("Small (4–10%)",  str(cats.get("small",0)),  color="#856404", bg="#fffdf0")}'
        f'{_kpi("Medium (10–20%)",str(cats.get("medium",0)), color="#0a3622", bg="#f0fff4")}'
        f'{_kpi("Large (>20%)",   str(cats.get("large",0)),  color="#084298", bg="#f0f4ff")}'
        '</tr></table>'
    )

    # ── Build Sections ────────────────────────────────────────────────
    def wrap(section_html, title):
        return (
            f'<tr>{_section(title)[len("<tr>"):-len("</tr>")]}</tr>'
            f'<tr><td>{section_html}</td></tr>'
        ) if section_html else ""

    body = f"""
    {wrap(kpi_row, "ملخص الأداء")}
    {wrap(cat_html, "توزيع النتائج")}
    {wrap(_section_score_buckets(resolved),   "تحليل Score Buckets")}
    {wrap(_section_signal_type(resolved),     "تحليل نوع الإشارة")}
    {wrap(_section_r3_liquidity(resolved),    "Liquidity Context (r3) — أكثر المكونات تأثيراً")}
    {wrap(_section_r8_demand(resolved),       "Demand Zone Confluence (r8)")}
    {wrap(_section_r1_price(resolved),        "Price Position / Discount Depth (r1)")}
    {wrap(_section_htf(resolved),             "Higher Timeframe Trend (r4)")}
    {wrap(_section_discount_depth(resolved),  "عمق السعر داخل Discount Zone")}
    {wrap(_section_context(resolved),         "السياق الماكرو — رمضان / CBE / Tier")}
    {wrap(_section_per_stock(resolved),       "الأداء لكل سهم (مرتّب بـ Win Rate)")}
    """

    if resolved:
        body += wrap(_section_full_table(resolved), f"جميع الإشارات المحسومة ({len(resolved)})")

    if pending:
        body += wrap(_section_pending(pending), f"إشارات قيد الانتظار ({len(pending)})")

    html = f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>EGX — Behavior Report</title>
</head>
<body style="margin:0;padding:16px;background:#eef2f7;direction:rtl;">
<table width="760" cellpadding="0" cellspacing="0" border="0" align="center"
       style="background:#fff;border:1px solid #d0d7e2;">
<tr><td style="background:#1a3a5c;padding:20px 24px;">
  <div style="font-family:Arial,sans-serif;color:#fff;font-size:20px;font-weight:700;">
    EGX Scanner — Behavior Analysis Report
  </div>
  <div style="font-family:Arial,sans-serif;color:#8fb8d8;font-size:12px;margin-top:4px;">
    {now_str} Cairo &nbsp;·&nbsp; {period} &nbsp;·&nbsp; {date_range}
  </div>
</td></tr>
<tr><td style="padding:0 20px 20px 20px;">
<table width="100%" cellpadding="0" cellspacing="0" border="0">
{body}
<tr><td style="padding-top:24px;border-top:1px solid #eee;">
  <div style="font-family:Arial,sans-serif;font-size:10px;color:#bbb;text-align:center;">
    Extended Signal Logger — EGX Institutional Scanner
  </div>
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""

    return html


# ── Email ─────────────────────────────────────────────────────────────────────

def send_report_email(html: str, days_back: int = 0) -> bool:
    period = f" — آخر {days_back} يوم" if days_back else ""
    subject = f"EGX Behavior Report{period} — {date.today()}"

    from notifications.email_sender import send as _send_email
    ok = _send_email(subject=subject, html=html, to=TO_EMAIL)
    if ok:
        print(f"[Report] Email sent → {TO_EMAIL}")
    return ok


# ── Entry Point ───────────────────────────────────────────────────────────────

def run(days_back: int = 0, send_email: bool = True):
    """يُنتج التقرير، يحفظه، ويُرسله بالإيميل."""
    print("[Report] Building behavior report...")
    html = build_report(days_back)

    os.makedirs("reports", exist_ok=True)
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[Report] Saved → {REPORT_FILE}")

    if send_email:
        send_report_email(html, days_back)

    return html


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EGX Behavior Report")
    parser.add_argument("--no-email", action="store_true", help="لا ترسل إيميل")
    parser.add_argument("--days",     type=int, default=0,  help="آخر N يوم (0=كل الفترة)")
    args = parser.parse_args()
    run(days_back=args.days, send_email=not args.no_email)
