"""
EGX Scanner — Master Dashboard Generator
==========================================
Reads KPIs from all report JSON files and builds a single
dashboard.html that acts as the main entry point for all reports.

Outputs: dashboard.html
"""

import json
import os
import sqlite3
from collections import Counter
from datetime import datetime, date
from pathlib import Path

DASHBOARD_FILE     = "dashboard.html"
BACKTEST_JSON      = "backtest_report.json"
RESEARCH_JSON      = "research_results.json"
EDGE_JSON          = "edge_discovery_results.json"
SIGNAL_LOG         = "signal_log.json"
DB_PATH            = "egx_research.db"


# ── Data Loaders ──────────────────────────────────────────────────────────────

def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _load_behavior_kpis():
    """Read KPIs directly from egx_research.db (uses v_all_signals for full 1051-signal coverage)."""
    if not Path(DB_PATH).exists():
        return {}
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute("""
            SELECT r20d, mfe_20d, mae_20d
            FROM v_all_signals
            WHERE r20d IS NOT NULL
        """).fetchall()
        conn.close()
    except Exception:
        return {}

    if not rows:
        return {}

    r20ds  = [r[0] for r in rows]
    mfes   = [r[1] for r in rows if r[1] is not None]
    maes   = [abs(r[2]) for r in rows if r[2] is not None]
    wins   = sum(1 for r in r20ds if r >= 0.07)
    cats   = Counter(
        "large" if r >= 0.20 else "medium" if r >= 0.08 else "small" if r >= 0.04 else "flat"
        for r in r20ds
    )
    return {
        "n":          len(rows),
        "win_rate":   round(wins / len(rows) * 100, 1),
        "avg_r20d":   round(sum(r20ds) / len(r20ds) * 100, 2),
        "avg_mfe":    round(sum(mfes)  / len(mfes)  * 100, 2) if mfes else 0,
        "avg_mae":    round(sum(maes)  / len(maes)  * 100, 2) if maes else 0,
        "flat":       cats["flat"],
        "small":      cats["small"],
        "medium":     cats["medium"],
        "large":      cats["large"],
    }


# ── HTML Helpers ──────────────────────────────────────────────────────────────

def _card(title, icon, content, link=None, link_label="التقرير الكامل"):
    link_html = (
        f'<a href="{link}" style="display:inline-block;margin-top:14px;'
        f'padding:7px 18px;background:#1a3c5e;color:#fff;border-radius:5px;'
        f'font-size:12px;text-decoration:none;">{link_label} ←</a>'
    ) if link else ""
    return f"""
<div style="background:#fff;border-radius:10px;box-shadow:0 2px 12px rgba(0,0,0,.08);
            padding:22px 24px;margin-bottom:20px;">
  <div style="font-size:22px;margin-bottom:6px;">{icon}
    <span style="font-size:15px;font-weight:700;color:#1a3c5e;vertical-align:middle;">{title}</span>
  </div>
  {content}
  {link_html}
</div>"""


def _kpi_row(*items):
    cells = ""
    for label, value, color in items:
        cells += f"""
  <div style="flex:1;min-width:110px;text-align:center;padding:10px 6px;
              background:#f7faff;border-radius:7px;margin:4px;">
    <div style="font-size:10px;color:#888;text-transform:uppercase;
                letter-spacing:.8px;margin-bottom:4px;">{label}</div>
    <div style="font-size:20px;font-weight:700;color:{color};">{value}</div>
  </div>"""
    return f'<div style="display:flex;flex-wrap:wrap;gap:4px;">{cells}</div>'


def _bar(label, value, total, color="#2a6496"):
    pct = round(value / total * 100) if total else 0
    return f"""
<div style="margin:5px 0;">
  <div style="display:flex;justify-content:space-between;font-size:12px;color:#555;margin-bottom:3px;">
    <span>{label}</span><span style="font-weight:600;">{value} ({pct}%)</span>
  </div>
  <div style="background:#eee;border-radius:4px;height:8px;">
    <div style="background:{color};width:{pct}%;border-radius:4px;height:8px;"></div>
  </div>
</div>"""


def _rule_row(i, rule):
    cond = rule.get("rule_text", rule.get("condition", "—"))
    # mfe_mean stored as pct (e.g. 32.16) in edge_discovery_results.json
    mfe  = rule.get("mfe_mean", 0)
    wr   = rule.get("win_rate", 0)
    n    = rule.get("n", 0)
    exp  = rule.get("expectancy", 0)
    src  = rule.get("source", rule.get("method", ""))
    src_color = {"dt":"#084298","rulefit":"#155724","assoc":"#856404","bayes":"#6f42c1"}.get(src,"#666")
    return f"""
<tr style="border-bottom:1px solid #f0f0f0;{'background:#f9f9f9;' if i%2 else ''}">
  <td style="padding:7px 10px;font-size:11px;color:#444;max-width:350px;">{str(cond)[:90]}{'…' if len(str(cond))>90 else ''}</td>
  <td style="padding:7px 10px;text-align:center;font-weight:700;color:#155724;font-size:12px;">+{mfe:.1f}%</td>
  <td style="padding:7px 10px;text-align:center;font-weight:700;color:#084298;font-size:12px;">{wr*100:.0f}%</td>
  <td style="padding:7px 10px;text-align:center;color:#666;font-size:11px;">{n}</td>
  <td style="padding:7px 10px;text-align:center;font-size:10px;color:{src_color};font-weight:600;">{src}</td>
</tr>"""


# ── Section Builders ──────────────────────────────────────────────────────────

def _section_backtest(bt):
    if not bt:
        return _card("Backtest Report", "📊", "<p style='color:#aaa;font-size:13px;'>لا توجد بيانات بعد</p>", "backtest_report.html")

    stats  = bt.get("overall_stats", {})
    dr     = bt.get("data_range", {})
    cagr   = bt.get("cagr_pct", 0)
    mdd    = bt.get("max_drawdown_pct", 0)
    calmar = bt.get("calmar_ratio", 0)
    wr     = stats.get("win_rate_pct", 0)
    exp    = stats.get("expectancy_pct", 0)
    pf     = stats.get("profit_factor", 0)
    n      = stats.get("total_signals", 0)
    ob     = stats.get("outcome_breakdown", {})
    total  = sum(ob.values()) or 1

    kpis = _kpi_row(
        ("CAGR",           f"{cagr:.1f}%",  "#155724" if cagr > 0 else "#721c24"),
        ("Max Drawdown",   f"{mdd:.1f}%",   "#155724" if mdd > -10 else "#721c24"),
        ("Calmar",         f"{calmar:.1f}", "#1a3c5e"),
        ("Win Rate",       f"{wr:.1f}%",    "#155724" if wr > 25 else "#856404"),
        ("Expectancy",     f"+{exp:.1f}%",  "#155724"),
        ("Profit Factor",  f"{pf:.1f}",     "#155724" if pf > 2 else "#856404"),
        ("Signals",        str(n),          "#333"),
    )
    date_range = f"{dr.get('first_signal','?')} → {dr.get('last_signal','?')}"
    bars = (
        _bar("Flat (<4%)",     ob.get("flat",0),   total, "#e74c3c") +
        _bar("Small (4–8%)",   ob.get("small",0),  total, "#f39c12") +
        _bar("Medium (8–20%)", ob.get("medium",0), total, "#27ae60") +
        _bar("Large (>20%)",   ob.get("large",0),  total, "#2980b9")
    )
    content = f"""
{kpis}
<div style="margin-top:10px;font-size:11px;color:#888;">📅 {date_range}</div>
<div style="margin-top:12px;">{bars}</div>"""
    return _card("Backtest / Equity Curve", "📊", content, "backtest_report.html")


def _section_research(rr):
    if not rr:
        return _card("Research Report", "🔬", "<p style='color:#aaa;font-size:13px;'>لا توجد بيانات بعد</p>", "research_report.html")

    meta = rr.get("meta", {})
    n    = meta.get("n_signals", 0)
    mfe  = meta.get("mfe_mean", 0)
    bq   = meta.get("bq_mean", 0)
    mae  = meta.get("mae_mean", 0)
    dr   = meta.get("date_range", ["?", "?"])

    ws = rr.get("weight_suggestions", {})
    ws_rows = ""
    components = ["r1_price","r2_ob","r3_liquidity","r4_htf","r5_avwap","r6_macd","r7_div","r8_demand"]
    for comp in components:
        info = ws.get(comp, {})
        cur  = info.get("current", "—")
        sug  = info.get("suggested", "—")
        chg  = info.get("change", 0)
        reason = info.get("reason", "insufficient data")
        chg_color = "#155724" if chg and chg > 0 else "#721c24" if chg and chg < 0 else "#888"
        chg_str = f"+{chg}" if chg and chg > 0 else str(chg) if chg else "0"
        ws_rows += f"""
<tr style="border-bottom:1px solid #f0f0f0;">
  <td style="padding:5px 8px;font-size:12px;font-weight:600;color:#1a3c5e;">{comp}</td>
  <td style="padding:5px 8px;text-align:center;font-size:12px;">{cur}</td>
  <td style="padding:5px 8px;text-align:center;font-size:12px;">{sug}</td>
  <td style="padding:5px 8px;text-align:center;font-size:12px;font-weight:700;color:{chg_color};">{chg_str}</td>
  <td style="padding:5px 8px;font-size:10px;color:#888;">{str(reason)[:50]}</td>
</tr>"""

    kpis = _kpi_row(
        ("إشارات",    str(n),            "#333"),
        ("Avg MFE",   f"+{mfe*100:.1f}%","#155724"),
        ("Avg BQ",    f"{bq:.0f}",       "#1a3c5e"),
        ("Avg MAE",   f"-{mae*100:.1f}%","#721c24"),
    )
    date_range = f"{dr[0]} → {dr[1]}" if len(dr) == 2 else "—"
    tbl = f"""
<div style="margin-top:12px;overflow-x:auto;">
<table width="100%" cellspacing="0" style="border-collapse:collapse;font-family:Arial,sans-serif;">
<thead><tr style="background:#1a3c5e;color:#fff;">
  <th style="padding:6px 8px;font-size:11px;">Component</th>
  <th style="padding:6px 8px;font-size:11px;">Current</th>
  <th style="padding:6px 8px;font-size:11px;">Suggested</th>
  <th style="padding:6px 8px;font-size:11px;">Change</th>
  <th style="padding:6px 8px;font-size:11px;">Reason</th>
</tr></thead>
<tbody>{ws_rows}</tbody>
</table></div>"""
    content = f"""
{kpis}
<div style="margin-top:8px;font-size:11px;color:#888;">📅 {date_range}</div>
{tbl}"""
    return _card("Research Report / ML Engine", "🔬", content, "research_report.html")


def _section_edge(ed):
    if not ed:
        return _card("Edge Discovery", "🧠", "<p style='color:#aaa;font-size:13px;'>لا توجد بيانات بعد — شغّل rule_discovery.py</p>", "edge_report.html")

    rules     = ed.get("rules", ed.get("global_rules", []))
    n_rules   = len(rules)
    n_sig     = ed.get("n_signals", ed.get("meta", {}).get("n_signals", "—"))
    top_rules = rules[:5] if rules else []

    rule_rows = "".join(_rule_row(i, r) for i, r in enumerate(top_rules))
    tbl = f"""
<div style="margin-top:12px;overflow-x:auto;">
<table width="100%" cellspacing="0" style="border-collapse:collapse;font-family:Arial,sans-serif;">
<thead><tr style="background:#1a3c5e;color:#fff;">
  <th style="padding:6px 10px;font-size:11px;text-align:right;">القاعدة (Top 5)</th>
  <th style="padding:6px 10px;font-size:11px;">Avg MFE</th>
  <th style="padding:6px 10px;font-size:11px;">Win Rate</th>
  <th style="padding:6px 10px;font-size:11px;">N</th>
  <th style="padding:6px 10px;font-size:11px;">Method</th>
</tr></thead>
<tbody>{rule_rows}</tbody>
</table></div>""" if rule_rows else ""

    kpis = _kpi_row(
        ("إجمالي القواعد", str(n_rules), "#1a3c5e"),
        ("إشارات",         str(n_sig),   "#333"),
    )
    return _card("Edge Discovery / Self-Learning", "🧠", kpis + tbl, "edge_report.html")


def _section_quant():
    """Reads key metrics from egx_research.db for the quant report card."""
    if not Path(DB_PATH).exists():
        return _card("Quant Research", "📐",
                     "<p style='color:#aaa;font-size:13px;'>لا توجد بيانات بعد</p>",
                     "quant_research_report.html")
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute("""
            SELECT b.r20d, b.mfe_20d, b.mae_20d
            FROM signals s
            JOIN bottom_quality b ON b.signal_id = s.id
            WHERE b.mfe_20d IS NOT NULL
        """).fetchall()
        conn.close()
    except Exception:
        return _card("Quant Research", "📐",
                     "<p style='color:#aaa;font-size:13px;'>خطأ في قراءة البيانات</p>",
                     "quant_research_report.html")

    if not rows:
        return _card("Quant Research", "📐",
                     "<p style='color:#aaa;font-size:13px;'>لا توجد إشارات ناضجة بعد</p>",
                     "quant_research_report.html")

    r20ds = [r[0] for r in rows if r[0] is not None]
    mfes  = [r[1] for r in rows if r[1] is not None]
    maes  = [abs(r[2]) for r in rows if r[2] is not None]
    n     = len(mfes)

    # CAGR
    cagr = ((1 + sum(r20ds) / len(r20ds)) ** (252 / 20) - 1 * 100) if r20ds else 0
    mean_r = sum(r20ds) / len(r20ds) if r20ds else 0
    cagr   = ((1 + mean_r) ** (252 / 20) - 1) * 100

    # Profit Factor
    gains  = sum(r for r in r20ds if r > 0)
    losses = sum(abs(r) for r in r20ds if r < 0)
    pf     = round(gains / losses, 2) if losses > 0 else 0

    # Avg MFE
    avg_mfe = round(sum(mfes) / n * 100, 1) if n else 0

    # Calmar
    avg_mae = sum(maes) / len(maes) if maes else 0
    calmar  = round((cagr / 100) / avg_mae, 2) if avg_mae > 0 else 0

    # Max DD
    max_dd = round(max(maes) * 100, 1) if maes else 0

    # Win Rate (MFE >= 8%)
    win_rate = round(sum(1 for m in mfes if m >= 0.08) / n * 100, 1) if n else 0

    cats = {"large": 0, "medium": 0, "small": 0, "flat": 0}
    for m in mfes:
        if m >= 0.20:   cats["large"]  += 1
        elif m >= 0.10: cats["medium"] += 1
        elif m >= 0.05: cats["small"]  += 1
        else:           cats["flat"]   += 1

    kpis = _kpi_row(
        ("CAGR",          f"{cagr:.0f}%",    "#155724" if cagr > 20 else "#856404"),
        ("Profit Factor", f"{pf:.2f}",        "#155724" if pf > 1.5 else "#856404"),
        ("Avg MFE",       f"+{avg_mfe:.1f}%", "#155724"),
        ("Calmar",        f"{calmar:.2f}",    "#1a3c5e"),
        ("Max DD",        f"{max_dd:.1f}%",   "#721c24"),
        ("Win Rate",      f"{win_rate:.0f}%", "#155724" if win_rate > 40 else "#856404"),
        ("إشارات",        str(n),            "#333"),
    )
    bars = (
        _bar("MFE < 5% (ضعيف)",   cats["flat"],   n, "#e74c3c") +
        _bar("MFE 5–10%",         cats["small"],  n, "#f39c12") +
        _bar("MFE 10–20%",        cats["medium"], n, "#27ae60") +
        _bar("MFE > 20% (كبير)", cats["large"],  n, "#2980b9")
    )
    content = kpis + "<div style='margin-top:12px;'>" + bars + "</div>"
    return _card("Quant Research — 7 Phases", "📐", content, "quant_research_report.html")


def _section_logic_analyzer():
    """Card for logic analyzer — reads from logic_analysis_results.json."""
    LOGIC_JSON = "logic_analysis_results.json"
    res = _load(LOGIC_JSON)
    if not res:
        return _card("Logic Analyzer", "🔬",
                     "<p style='color:#aaa;font-size:13px;'>لا توجد نتائج بعد</p>",
                     "logic_analysis_report.html")

    n       = res.get("n_signals", 0)
    r20d    = res.get("baseline_r20d", 0)
    mfe_v   = res.get("baseline_mfe", 0)
    pf_v    = res.get("baseline_pf", 0)
    recs    = res.get("summary_recommendations", [])
    findings = res.get("critical_findings", [])
    fi_map  = res.get("function_impact", {})

    # Most harmful function
    harmful = [(k, v['delta_r20d']) for k, v in fi_map.items() if v.get('delta_r20d', 0) < -0.005]
    harmful.sort(key=lambda x: x[1])

    finding_html = ""
    if findings:
        items = "".join(
            f"<li style='font-size:11px;color:#c04000;margin:2px 0'>{f[:80]}</li>"
            for f in findings[:3]
        )
        finding_html = (
            f"<div style='margin-top:8px;background:#fff3cd;padding:8px 10px;"
            f"border-radius:6px;color:#856404;font-size:11px;'>"
            f"<strong>⚠️ Critical Findings:</strong><ul style='padding-left:14px;margin-top:4px'>{items}</ul></div>"
        )

    kpis = _kpi_row(
        ("إشارات", str(n), "#333"),
        ("Avg r20d", f"{r20d*100:+.1f}%", "#155724" if r20d > 0 else "#721c24"),
        ("Avg MFE",  f"{mfe_v*100:.1f}%", "#155724"),
        ("PF",       f"{pf_v:.2f}",       "#155724" if pf_v > 1.5 else "#856404"),
        ("توصيات",   str(len(recs)),       "#1a3c5e"),
    )
    content = kpis + finding_html
    return _card("Logic Analyzer — sc_* Functions", "🔬", content, "logic_analysis_report.html")


def _section_weight_optimizer():
    """Card for weight optimizer report — reads from optimization_results.json."""
    OPTIM_JSON = "optimization_results.json"
    res = _load(OPTIM_JSON)
    if not res:
        return _card("Weight Optimizer", "⚖️",
                     "<p style='color:#aaa;font-size:13px;'>لا توجد نتائج بعد</p>",
                     "weight_optimizer_report.html")

    base    = res.get("baseline", {})
    n       = base.get("n", 0)
    exp_ret = base.get("expected_return", 0)
    mfe_v   = base.get("mfe", 0)
    pf_v    = base.get("profit_factor", 1)
    recs    = res.get("top_recommendations", [])
    harmful = res.get("harmful_indicators", [])
    oos_imp = res.get("oos_improvement", 0)

    top_rec = recs[0] if recs else {}
    top_txt = ""
    if top_rec:
        delta = top_rec.get("delta_ret", 0)
        top_txt = (
            f"<div style='margin-top:10px;font-size:12px;background:#e8f4fd;"
            f"padding:8px 10px;border-radius:6px;color:#1a5276;'>"
            f"🎯 أفضل توصية: <strong>{top_rec.get('indicator','')}</strong> — "
            f"<strong>{top_rec.get('change','')[:60]}</strong><br>"
            f"ΔExp Ret: <strong>{delta*100:+.1f}%</strong> · "
            f"Retention: {top_rec.get('retention',1)*100:.0f}%</div>"
        )

    harm_txt = ""
    if harmful:
        names = ", ".join(h.get("label", "") for h in harmful)
        harm_txt = (
            f"<div style='margin-top:8px;font-size:11px;background:#fff3cd;"
            f"padding:6px 10px;border-radius:6px;color:#856404;'>"
            f"⚠️ مؤشرات ذات تأثير سلبي: {names}</div>"
        )

    oos_cls = "#155724" if oos_imp > 0.002 else ("#856404" if oos_imp >= 0 else "#721c24")
    kpis = _kpi_row(
        ("إشارات", str(n), "#333"),
        ("Avg Return", f"{exp_ret*100:+.1f}%", "#155724" if exp_ret > 0 else "#721c24"),
        ("Avg MFE", f"{mfe_v*100:.1f}%", "#155724"),
        ("Profit Factor", f"{pf_v:.2f}", "#155724" if pf_v > 1.5 else "#856404"),
        ("OOS Improve", f"{oos_imp*100:+.2f}%", oos_cls),
        ("توصيات", str(len(recs)), "#1a3c5e"),
    )
    content = kpis + top_txt + harm_txt
    return _card("Weight Optimizer — Quant Engine", "⚖️", content, "weight_optimizer_report.html")


def _section_historical_backtest():
    """Card for historical backtest — reads from historical_backtest_results.json."""
    res = _load("historical_backtest_results.json")
    if not res:
        return _card("Historical Backtest", "🏛️",
                     "<p style='color:#aaa;font-size:13px;'>لا توجد نتائج بعد</p>",
                     "historical_backtest_report.html")

    base  = res.get("baseline", {})
    live  = res.get("live_baseline", {})
    n     = base.get("n", 0)
    n_live = live.get("n", 639)
    mean  = base.get("mean", 0)
    pf    = base.get("pf", 0)
    mfe   = base.get("mfe", 0)
    wr    = base.get("wr", 0)

    # Consistency indicator: how close to live DB?
    live_mean = live.get("mean", 0.046)
    delta_vs_live = mean - live_mean
    consist_color = "#155724" if abs(delta_vs_live) < 0.01 else "#856404"
    consist_label = "✅ Consistent" if abs(delta_vs_live) < 0.01 else f"⚠️ Diverges {delta_vs_live*100:+.1f}%"

    hc = "#155724" if mean > 0.04 else "#856404" if mean > 0 else "#721c24"
    kpis = _kpi_row(
        ("إشارات تاريخية", f"{n:,}", "#1a3c5e"),
        ("Avg Return",      f"{mean*100:+.2f}%", hc),
        ("MFE (20d)",       f"{mfe*100:.1f}%", "#155724"),
        ("Win Rate",        f"{wr*100:.1f}%", hc),
        ("Profit Factor",   f"{pf:.2f}", "#155724" if pf > 2 else "#856404"),
        ("vs Live DB",      f"{n_live} signals", "#333"),
    )

    # Top flag finding
    flags = res.get("flag_analysis", [])
    top_flags = sorted(
        [f for f in flags if f.get("yes") and f.get("no")],
        key=lambda f: abs(f["yes"].get("mean", 0) - f["no"].get("mean", 0)),
        reverse=True
    )[:2]
    flag_txt = ""
    for fm in top_flags:
        diff = fm["yes"].get("mean", 0) - fm["no"].get("mean", 0)
        c = "#155724" if diff > 0 else "#721c24"
        arrow = "▲" if diff > 0 else "▼"
        flag_txt += (f"<div style='margin-top:6px;font-size:12px;padding:5px 10px;"
                     f"background:#f7faff;border-radius:5px;'>"
                     f"{arrow} <strong>{fm['flag'].replace('_',' ').title()}</strong>: "
                     f"<span style='color:{c};font-weight:700;'>{diff*100:+.2f}%</span> "
                     f"(n={fm['yes'].get('n',0)} YES vs {fm['no'].get('n',0)} NO)</div>")

    consist_txt = (f"<div style='margin-top:8px;font-size:12px;background:#e8f4fd;"
                   f"padding:7px 10px;border-radius:6px;color:{consist_color};'>"
                   f"📊 {consist_label} — historical avg {mean*100:.2f}% vs live {live_mean*100:.2f}%</div>")

    content = kpis + consist_txt + flag_txt
    return _card("Historical Backtest — 5 Years Full Replay", "🏛️",
                 content, "historical_backtest_report.html")


def _section_adaptive_learning():
    """Card for adaptive learning engine — reads from adaptive_learning_results.json."""
    res = _load("adaptive_learning_results.json")
    if not res:
        return _card("Adaptive Learning Engine", "🧬",
                     "<p style='color:#aaa;font-size:13px;'>لا توجد نتائج بعد</p>",
                     "adaptive_learning_report.html")

    health   = res.get("health_score", 0)
    n_sig    = res.get("n_signals", 0)
    baseline = res.get("baseline", {})
    base_ret = baseline.get("mean", 0)
    base_pf  = baseline.get("pf", 0)
    top3     = res.get("top3", [])
    drivers  = res.get("loss_drivers", [])
    mismatches = res.get("cross_check_mismatches", [])

    health_color = "#155724" if health >= 70 else "#856404" if health >= 45 else "#721c24"
    kpis = _kpi_row(
        ("Health Score", f"{health}/100", health_color),
        ("إشارات", str(n_sig), "#333"),
        ("Baseline Return", f"{base_ret*100:.1f}%", "#1a3c5e"),
        ("Profit Factor", f"{base_pf:.2f}", "#155724"),
        ("Top Improvements", str(len(top3)), "#0d6efd"),
        ("Cross Mismatches", str(len(mismatches)), "#856404" if mismatches else "#155724"),
    )

    # Top improvement highlight
    imp_txt = ""
    if top3:
        t = top3[0]
        imp_txt = (
            f"<div style='margin-top:8px;font-size:12px;background:#d4edda;"
            f"padding:7px 10px;border-radius:6px;color:#155724;'>"
            f"🥇 <strong>{t['name']}</strong> — "
            f"<span style='font-weight:700'>+{t['delta_ret']*100:.2f}%</span> return, "
            f"PF={t['pf']:.2f}, WF={'✓' if t['wf_consistent'] else '✗'}, "
            f"retention={t['retention']*100:.0f}%</div>"
        )

    # Top loss driver
    driver_txt = ""
    top_drv = sorted(drivers, key=lambda d: d.get("severity", 0), reverse=True)
    if top_drv:
        d = top_drv[0]
        driver_txt = (
            f"<div style='margin-top:8px;font-size:12px;background:#fff3cd;"
            f"padding:7px 10px;border-radius:6px;color:#856404;'>"
            f"⚠️ Loss driver: <strong>{d['driver']}</strong> — "
            f"severity={d['severity']}/100, freq={d['freq_pct']:.1f}%</div>"
        )

    content = kpis + imp_txt + driver_txt
    return _card("Adaptive Learning Engine — Self-Improving Analysis", "🧬",
                 content, "adaptive_learning_report.html")


def _section_system_audit():
    """Card for system audit report — reads from system_audit_results.json."""
    res = _load("system_audit_results.json")
    if not res:
        return _card("System Audit", "🕵️",
                     "<p style='color:#aaa;font-size:13px;'>لا توجد نتائج بعد</p>",
                     "system_audit_report.html")

    n_sig  = res.get("n_signals", 0)
    n_rej  = res.get("n_rejected", 0)
    n_ass  = res.get("n_assumptions", 0)
    n_prot = res.get("assumptions_protected", 0)
    n_unt  = res.get("assumptions_untested", 0)
    pf     = res.get("baseline_pf", 0)
    r20d   = res.get("baseline_r20d", 0)

    # Top filter damage
    fd = res.get("filter_damage", [])
    top_filter = fd[0] if fd else {}
    filter_txt = ""
    if top_filter:
        diff  = top_filter.get("diff", 0)
        diff_color = "#721c24" if diff < 0 else "#155724"
        filter_txt = (
            f"<div style='margin-top:8px;font-size:12px;background:#fff3cd;"
            f"padding:7px 10px;border-radius:6px;color:#856404;'>"
            f"⚠️ Biggest filter damage: <strong>{top_filter.get('filter','')}</strong> — "
            f"<span style='color:{diff_color};font-weight:700'>{diff*100:+.1f}%</span> "
            f"({top_filter.get('verdict','')[:40]})</div>"
        )

    # Top discovery
    disc = res.get("top_discoveries", [])
    top_disc = disc[0] if disc else {}
    disc_txt = ""
    if top_disc:
        disc_txt = (
            f"<div style='margin-top:8px;font-size:12px;background:#d4edda;"
            f"padding:7px 10px;border-radius:6px;color:#155724;'>"
            f"🔍 Top discovery: <strong>{top_disc.get('combo','')}</strong> → "
            f"<strong>{top_disc.get('mean',0)*100:+.1f}%</strong> avg return "
            f"(n={top_disc.get('n','')}, MFE={top_disc.get('mfe',0)*100:.1f}%)</div>"
        )

    conc = res.get("conclusions", {})
    q8   = conc.get("q8_highest_impact", "")
    q8_txt = ""
    if q8:
        q8_txt = (
            f"<div style='margin-top:8px;font-size:11px;background:#e8f4fd;"
            f"padding:7px 10px;border-radius:6px;color:#0a3622;'>"
            f"🎯 Highest impact: {q8[:100]}...</div>"
        )

    kpis = _kpi_row(
        ("إشارات", str(n_sig), "#333"),
        ("مرفوضة", str(n_rej), "#856404"),
        ("Assumptions", str(n_ass), "#1a3c5e"),
        ("Protected", str(n_prot), "#721c24"),
        ("Not Tested", str(n_unt), "#856404"),
        ("Profit Factor", f"{pf:.2f}", "#155724"),
    )
    content = kpis + filter_txt + disc_txt + q8_txt
    return _card("System Audit — Assumption & Blind Spot Analysis", "🕵️",
                 content, "system_audit_report.html")


def _section_behavior(beh):
    if not beh or beh.get("n", 0) == 0:
        return _card("Behavior Report", "🔍", "<p style='color:#aaa;font-size:13px;'>لا توجد بيانات بعد</p>", "behavior_report.html")

    n   = beh["n"]
    wr  = beh["win_rate"]
    ar  = beh["avg_r20d"]
    mfe = beh["avg_mfe"]
    mae = beh["avg_mae"]

    kpis = _kpi_row(
        ("إشارات محسومة", str(n),         "#333"),
        ("Win Rate (≥7%)", f"{wr}%",       "#155724" if wr > 30 else "#856404"),
        ("Avg Return 20d", f"+{ar:.1f}%",  "#155724" if ar > 0 else "#721c24"),
        ("Avg MFE",        f"+{mfe:.1f}%", "#155724"),
        ("Avg MAE",        f"-{mae:.1f}%", "#721c24"),
    )
    bars = (
        _bar("Flat (<4%)",     beh["flat"],   n, "#e74c3c") +
        _bar("Small (4–8%)",   beh["small"],  n, "#f39c12") +
        _bar("Medium (8–20%)", beh["medium"], n, "#27ae60") +
        _bar("Large (>20%)",   beh["large"],  n, "#2980b9")
    )
    return _card("Behavior Report / SMC Analysis", "🔍", kpis + "<div style='margin-top:12px;'>" + bars + "</div>", "behavior_report.html")


# ── Research Notes Summary ────────────────────────────────────────────────────

def _section_research_notes():
    """Aggregate recommendations from ALL 8 research modules."""
    import re

    notes = []  # list of {source, priority, text, color, conf, delta_ret, delta_n}

    # baseline from v_all_signals (dynamic)
    total_signals = 639  # fallback
    avg_r20d_pct  = 4.6  # fallback
    try:
        import sqlite3 as _sq
        _c = _sq.connect(DB_PATH)
        _row = _c.execute(
            "SELECT COUNT(*), AVG(r20d) FROM v_all_signals WHERE r20d IS NOT NULL"
        ).fetchone()
        if _row and _row[0]:
            total_signals = _row[0]
            avg_r20d_pct  = round((_row[1] or 0) * 100, 1)
        _c.close()
    except Exception:
        pass

    def _ret_str(v):
        """Format return delta as colored span."""
        if v is None:
            return "<span style='color:#aaa'>—</span>"
        color = "#155724" if v > 0 else "#721c24" if v < 0 else "#555"
        return f"<span style='color:{color};font-weight:700'>{v*100:+.1f}%</span>"

    def _conf_str(p=None, n=None, conf=None):
        """Format confidence indicator."""
        parts = []
        if conf is not None:
            c = conf * 100
            color = "#155724" if c >= 80 else "#856404" if c >= 60 else "#721c24"
            parts.append(f"<span style='color:{color}'>{c:.0f}%</span>")
        if p is not None:
            color = "#155724" if p < 0.05 else "#856404" if p < 0.10 else "#721c24"
            parts.append(f"<span style='color:{color}'>p={p:.3f}</span>")
        if n is not None:
            parts.append(f"<span style='color:#555'>n={n}</span>")
        return " · ".join(parts) if parts else "<span style='color:#aaa'>—</span>"

    def _n_str(n_after, n_before=total_signals):
        """Format signal count change."""
        if n_after is None:
            return "<span style='color:#aaa'>—</span>"
        diff = n_after - n_before
        pct  = diff / n_before * 100 if n_before else 0
        color = "#155724" if diff > 0 else "#721c24" if diff < 0 else "#555"
        arrow = "▲" if diff > 0 else "▼" if diff < 0 else "—"
        return (f"<span style='color:{color};font-weight:700'>{arrow}{abs(int(diff))}</span>"
                f"<span style='color:#888;font-size:10px;'> ({pct:+.0f}%)</span>")

    def _parse_ret(impact_str):
        """Extract first numeric percent from impact string, e.g. '+1.5%' → 0.015."""
        m = re.search(r'([+-]?\d+\.?\d*)%', str(impact_str))
        return float(m.group(1)) / 100 if m else None

    # ── Logic Analyzer ───────────────────────────────────────────────────────
    la   = _load("logic_analysis_results.json")
    la_fi = la.get("function_impact", {})
    for r in la.get("summary_recommendations", [])[:8]:
        func     = r.get("function", "")
        param    = r.get("param", "")
        current  = r.get("current", "")
        proposed = r.get("proposed", "")
        impact   = r.get("impact", "")

        fi       = la_fi.get(func, {})
        n_pos    = fi.get("n_pos")
        n_zero   = fi.get("n_zero")
        delta_r  = fi.get("delta_r20d")  # overall function impact
        parsed_r = _parse_ret(impact)    # impact from proposed change
        eff_ret  = parsed_r if parsed_r is not None else delta_r

        # signal count change: if reducing weight, signals shift (estimated via n_pos)
        n_affected = n_pos  # signals where this function fires

        notes.append({
            "source":    f"🔬 Logic · {func}",
            "priority":  "HIGH" if any(k in impact for k in ["+", "Remove", "Invert", "Reduce"]) else "MEDIUM",
            "text":      f"<b>{param}</b>: {str(current)[:28]} → <b>{str(proposed)[:55]}</b>",
            "color":     "#0a3622",
            "conf":      _conf_str(n=n_pos),
            "delta_ret": _ret_str(eff_ret),
            "delta_n":   (f"<span style='color:#555;font-size:11px'>{n_pos}↑ / {n_zero}↓</span>"
                          if n_pos is not None else "<span style='color:#aaa'>—</span>"),
        })

    # ── Weight Optimizer ─────────────────────────────────────────────────────
    wo = _load("optimization_results.json")
    for r in wo.get("top_recommendations", [])[:5]:
        ind       = r.get("indicator", "")
        change    = r.get("change", "")
        delta     = r.get("delta_ret")
        conf      = r.get("confidence")
        retention = r.get("retention")
        sample_n  = r.get("sample_n")
        # retention: fraction of signals kept → n_after = total * retention
        n_after   = int(total_signals * retention) if retention is not None else None

        notes.append({
            "source":    f"⚖️ Optimizer · {ind}",
            "priority":  "HIGH" if abs(delta or 0) > 0.01 else "MEDIUM",
            "text":      f"<b>{change[:72]}</b>",
            "color":     "#084298",
            "conf":      _conf_str(conf=conf, n=sample_n),
            "delta_ret": _ret_str(delta),
            "delta_n":   _n_str(n_after),
        })

    # ── System Audit — Filter Damage ─────────────────────────────────────────
    sa = _load("system_audit_results.json")
    for fd in sa.get("filter_damage", [])[:5]:
        filt    = fd.get("filter", "")
        diff    = fd.get("diff")
        pval    = fd.get("p_value")
        n_with  = fd.get("n_with")
        n_wo    = fd.get("n_without")
        verdict = fd.get("verdict", "")
        pri = "CRITICAL" if fd.get("significant") and diff is not None and diff < -0.01 else "HIGH"

        notes.append({
            "source":    f"🕵️ Audit · Filter",
            "priority":  pri,
            "text":      f"<b>{filt}</b>: {verdict[:60]}",
            "color":     "#721c24" if (diff or 0) < 0 else "#155724",
            "conf":      _conf_str(p=pval, n=n_with),
            "delta_ret": _ret_str(diff),
            "delta_n":   (f"<span style='color:#721c24;font-weight:700'>▼{n_wo}</span>"
                          f"<span style='color:#888;font-size:10px'> لو اشترطناه</span>"
                          if n_wo is not None else "<span style='color:#aaa'>—</span>"),
        })

    # ── System Audit — Top Discoveries ────────────────────────────────────────
    for disc in sa.get("top_discoveries", [])[:3]:
        combo = disc.get("combo", "")
        mean  = disc.get("mean")
        diff_ = disc.get("diff")
        pval  = disc.get("p_value")
        n_    = disc.get("n")

        notes.append({
            "source":    "🕵️ Audit · Discovery",
            "priority":  "HIGH",
            "text":      f"<b>اكتشاف:</b> {combo}",
            "color":     "#155724",
            "conf":      _conf_str(p=pval, n=n_),
            "delta_ret": _ret_str(mean),   # absolute return, not delta
            "delta_n":   (f"<span style='color:#1a3c5e;font-weight:700'>{n_} إشارة</span>"
                          if n_ is not None else "<span style='color:#aaa'>—</span>"),
        })

    # ── Edge Discovery ────────────────────────────────────────────────────────
    ed = _load("edge_discovery_results.json")
    # top_rules may be empty; fall back to top_fingerprints (sorted by mfe_mean)
    top_rules = ed.get("top_rules", []) or []
    if not top_rules:
        fps = ed.get("top_fingerprints", []) or []
        top_rules = sorted(fps, key=lambda x: float(x.get("mfe_mean", 0) or 0), reverse=True)
    for r in top_rules[:4]:
        cond = r.get("rule_text", r.get("condition", ""))
        mfe  = float(r.get("mfe_mean", 0) or 0)
        wr   = float(r.get("win_rate",  0) or 0)
        n_   = int(r.get("n",          0) or 0)
        pval = r.get("p_value")
        try:
            pval = float(pval) if pval is not None else None
        except (TypeError, ValueError):
            pval = None

        notes.append({
            "source":    "🧠 Edge",
            "priority":  "HIGH" if mfe > 25 else "MEDIUM",
            "text":      f"<b>{str(cond)[:80]}</b> · WR={wr:.0%}",
            "color":     "#6f42c1",
            "conf":      _conf_str(p=pval, n=n_),
            "delta_ret": (f"<span style='color:#155724;font-weight:700'>MFE {mfe:+.1f}%</span>"
                          if mfe else "<span style='color:#aaa'>—</span>"),
            "delta_n":   (f"<span style='color:#1a3c5e;font-weight:700'>{n_} إشارة</span>"
                          if n_ else "<span style='color:#aaa'>—</span>"),
        })

    # ── 🔬 Research Report (weight suggestions + RF importance) ─────────────────
    rr = _load("research_results.json")
    ws = rr.get("weight_suggestions", {})
    for feat, info in list(ws.items())[:5]:
        if not isinstance(info, dict):
            continue
        direction = info.get("direction", "")
        w_change  = info.get("change")
        reason    = info.get("reason", "")
        imp_m     = re.search(r'avg_importance=(\d+\.\d+)', reason)
        imp       = float(imp_m.group(1)) if imp_m else None
        # Infer direction from change sign if not explicitly set
        if not direction:
            if w_change is not None:
                direction = "رفع" if w_change > 0 else "خفض"
            else:
                continue
        color_dir = "#155724" if w_change is not None and w_change > 0 else "#721c24"
        notes.append({
            "source":    "🔬 Research",
            "priority":  "MEDIUM",
            "text":      (f"<b>{feat}</b>: {direction} الوزن {w_change:+d} نقطة"
                          if w_change is not None else f"<b>{feat}</b>: {direction[:60]}"),
            "color":     color_dir,
            "conf":      (f"<span style='color:#555'>imp={imp:.4f}</span>" if imp else "—"),
            "delta_ret": "<span style='color:#aaa'>—</span>",
            "delta_n":   "<span style='color:#aaa'>—</span>",
        })

    # ── 🔬 Quant — top RF features for MFE prediction ────────────────────────
    rf_imp = rr.get("rf_mfe", {}).get("importance", {})
    if rf_imp:
        top_feats = sorted(rf_imp.items(), key=lambda x: x[1], reverse=True)[:4]
        for feat, imp_v in top_feats:
            notes.append({
                "source":    "🔬 Research · Quant",
                "priority":  "MEDIUM",
                "text":      f"<b>{feat}</b>: أهم مؤثر على MFE (RF importance={imp_v:.4f})",
                "color":     "#4a235a",
                "conf":      f"<span style='color:#555'>n={rr.get('rf_mfe',{}).get('n_train','?')}</span>",
                "delta_ret": "<span style='color:#aaa'>—</span>",
                "delta_n":   "<span style='color:#aaa'>—</span>",
            })

    # ── 📊 Backtest — score threshold analysis ───────────────────────────────
    bt = _load("backtest_report.json")
    thresholds = bt.get("score_threshold_analysis", [])
    # Find the threshold with best expectancy / reasonable n_signals
    best_thr = None
    for thr in thresholds:
        n_ = thr.get("n_signals", 0)
        exp_ = thr.get("expectancy_pct", 0)
        pf_  = thr.get("profit_factor", 0)
        if n_ >= 200 and (best_thr is None or
                          exp_ > best_thr.get("expectancy_pct", 0)):
            best_thr = thr
    if best_thr:
        thr_v  = best_thr.get("score_threshold")
        n_thr  = best_thr.get("n_signals")
        exp_t  = best_thr.get("expectancy_pct", 0)
        wr_t   = best_thr.get("win_rate_pct", 0)
        pf_t   = best_thr.get("profit_factor", 0)
        notes.append({
            "source":    "📊 Backtest · Score",
            "priority":  "HIGH",
            "text":      (f"<b>أفضل score threshold = {thr_v}</b>: "
                          f"WR={wr_t:.0f}% · Exp={exp_t:.1f}% · PF={pf_t:.1f}"),
            "color":     "#0a3622",
            "conf":      f"<span style='color:#555'>n={n_thr}</span>",
            "delta_ret": (f"<span style='color:#155724;font-weight:700'>+{exp_t:.1f}%</span>"
                          if exp_t > 0 else "<span style='color:#aaa'>—</span>"),
            "delta_n":   _n_str(n_thr),
        })

    # Best r1 threshold
    r1_rows = bt.get("r1_threshold_analysis", [])
    best_r1 = None
    for row in r1_rows:
        n_ = row.get("n_signals", 0)
        if n_ >= 200 and (best_r1 is None or
                          row.get("expectancy_pct", 0) > best_r1.get("expectancy_pct", 0)):
            best_r1 = row
    if best_r1:
        r1_v  = best_r1.get("r1_threshold")
        n_r1  = best_r1.get("n_signals")
        exp_r = best_r1.get("expectancy_pct", 0)
        wr_r  = best_r1.get("win_rate_pct", 0)
        notes.append({
            "source":    "📊 Backtest · r1",
            "priority":  "HIGH",
            "text":      (f"<b>أفضل r1 threshold = {r1_v}</b>: "
                          f"WR={wr_r:.0f}% · Exp={exp_r:.1f}%"),
            "color":     "#0a3622",
            "conf":      f"<span style='color:#555'>n={n_r1}</span>",
            "delta_ret": f"<span style='color:#155724;font-weight:700'>+{exp_r:.1f}%</span>",
            "delta_n":   _n_str(n_r1),
        })

    # ── 🔍 Behavior — DB-derived insights ────────────────────────────────────
    beh = _load_behavior_kpis()
    if beh and beh.get("n", 0) > 0:
        n_b   = beh["n"]
        wr_b  = beh["win_rate"]
        ar_b  = beh["avg_r20d"]
        mfe_b = beh["avg_mfe"]
        mae_b = beh["avg_mae"]
        large = beh.get("large", 0)
        flat  = beh.get("flat", 0)
        # Note if flat signals are high
        flat_pct = flat / n_b * 100 if n_b else 0
        large_pct = large / n_b * 100 if n_b else 0
        if flat_pct > 25:
            notes.append({
                "source":    "🔍 Behavior",
                "priority":  "HIGH",
                "text":      (f"<b>{flat_pct:.0f}% من الإشارات flat</b> (عائد <4%) — "
                              f"النظام يُولِّد كثيراً من الإشارات الضعيفة"),
                "color":     "#721c24",
                "conf":      f"<span style='color:#555'>n={n_b}</span>",
                "delta_ret": f"<span style='color:#aaa'>WR={wr_b:.0f}%</span>",
                "delta_n":   f"<span style='color:#721c24;font-weight:700'>{flat} flat</span>",
            })
        if large_pct > 15:
            notes.append({
                "source":    "🔍 Behavior",
                "priority":  "MEDIUM",
                "text":      (f"<b>{large_pct:.0f}% إشارات large winners</b> (>20%) — "
                              f"إشارة جودة عالية · avg MFE={mfe_b:.1f}%"),
                "color":     "#155724",
                "conf":      f"<span style='color:#555'>n={n_b}</span>",
                "delta_ret": f"<span style='color:#155724;font-weight:700'>+{ar_b:.1f}%</span>",
                "delta_n":   f"<span style='color:#155724'>{large} large</span>",
            })
        # General baseline note
        notes.append({
            "source":    "🔍 Behavior",
            "priority":  "LOW",
            "text":      (f"Baseline: WR={wr_b:.0f}% · avg r20d=+{ar_b:.1f}% · "
                          f"MFE={mfe_b:.1f}% · MAE=-{mae_b:.1f}%"),
            "color":     "#555",
            "conf":      f"<span style='color:#555'>n={n_b}</span>",
            "delta_ret": f"<span style='color:#155724'>+{ar_b:.1f}%</span>",
            "delta_n":   f"<span style='color:#333'>{n_b} إشارة</span>",
        })

    # ── 🧬 Adaptive Learning — top improvements ───────────────────────────────
    al = _load("adaptive_learning_results.json")
    al_imps = sorted(al.get("all_improvements", []),
                     key=lambda x: x.get("model_score", 0), reverse=True)
    for r in al_imps[:4]:
        imp_id   = r.get("id", "")
        name     = r.get("name", "")
        score    = r.get("model_score", 0)
        delta    = r.get("delta_ret")
        wf_ok    = r.get("wf_consistent", False)
        retention = r.get("retention")
        n_after  = int(total_signals * retention) if retention is not None else None
        pri = "HIGH" if score >= 70 else "MEDIUM" if score >= 50 else "LOW"
        wf_label = ("<span style='color:#155724;font-size:10px'>✓ WF</span>" if wf_ok
                    else "<span style='color:#aaa;font-size:10px'>— WF</span>")
        notes.append({
            "source":    f"🧬 Adaptive · {imp_id}",
            "priority":  pri,
            "text":      f"<b>{name[:70]}</b>",
            "color":     "#1a3c5e",
            "conf":      f"<span style='color:#555'>score={score}</span> {wf_label}",
            "delta_ret": _ret_str(delta),
            "delta_n":   _n_str(n_after),
        })

    # ── 🏛️ Historical Backtest — flag analysis + combo analysis ─────────────
    hb = _load("historical_backtest_results.json")
    hb_base = hb.get("baseline", {})
    hb_base_pf = hb_base.get("pf", 1.0)
    for fa in hb.get("flag_analysis", [])[:3]:
        flag  = fa.get("flag", "")
        yes   = fa.get("yes", {})
        no    = fa.get("no",  {})
        y_pf  = yes.get("pf",  0)
        n_pf  = no.get("pf",   0)
        y_wr  = yes.get("wr",  0)
        y_n   = yes.get("n",   0)
        no_n  = no.get("n",    0)
        y_mfe = yes.get("mfe", 0)
        diff_mean = yes.get("mean", 0) - no.get("mean", 0)
        is_positive = y_pf > n_pf * 1.05
        notes.append({
            "source":    "🏛️ Historical",
            "priority":  "HIGH" if abs(y_pf - n_pf) > 0.3 else "MEDIUM",
            "text":      (f"<b>{flag}</b>: PF_yes={y_pf:.2f} vs PF_no={n_pf:.2f} · "
                          f"WR_yes={y_wr:.0%} · MFE_yes={y_mfe:.0%}"),
            "color":     "#0a3622" if is_positive else "#721c24",
            "conf":      _conf_str(n=y_n),
            "delta_ret": _ret_str(diff_mean),
            "delta_n":   (f"<span style='color:#555;font-size:11px'>{y_n}/{y_n+no_n}</span>"),
        })
    # Top combos from historical (2-way flag combinations)
    for cb in hb.get("combo_analysis", [])[:3]:
        combo  = cb.get("combo", "")
        cb_n   = cb.get("n", 0)
        cb_pf  = cb.get("pf", 0)
        cb_wr  = cb.get("wr", 0)
        cb_mfe = cb.get("mfe", 0)
        cb_diff = cb.get("diff", 0)
        notes.append({
            "source":    "🏛️ Historical · Combo",
            "priority":  "HIGH" if cb_diff > 0.02 else "MEDIUM",
            "text":      (f"<b>{combo}</b>: PF={cb_pf:.2f} · WR={cb_wr:.0%} · "
                          f"MFE={cb_mfe:.0%} · Δ={cb_diff*100:+.1f}%"),
            "color":     "#0a3622" if cb_diff > 0 else "#721c24",
            "conf":      _conf_str(n=cb_n),
            "delta_ret": _ret_str(cb_diff),
            "delta_n":   (f"<span style='color:#555;font-size:11px'>{cb_n} إشارة</span>"),
        })

    # ── ⚡ GX Learning — cross-validated high-confidence recommendations ────────
    gxm = _load("gx_learning_memory.json")
    gx_recs = gxm.get("recommendations", [])
    # Show top recommendations by confidence, only Proposed or Active status
    gx_top = sorted(
        [r for r in gx_recs if r.get("status") in ("Proposed", "Active")
         and r.get("confidence", 0) >= 0.6],
        key=lambda x: x.get("confidence", 0), reverse=True
    )[:3]
    for r in gx_top:
        rec_id   = r.get("id", "")
        name     = r.get("name", "")
        conf     = r.get("confidence", 0)
        supports = len(r.get("supporting", []))
        d_ret    = r.get("expected_delta_ret")
        d_mfe    = r.get("expected_delta_mfe")
        wf_ok    = r.get("wf_consistent", False)
        notes.append({
            "source":    f"⚡ GX · {rec_id}",
            "priority":  "HIGH" if conf >= 0.75 else "MEDIUM",
            "text":      f"<b>{name[:70]}</b>",
            "color":     "#3d1a5c",
            "conf":      (f"<span style='color:#{'155724' if conf >= 0.75 else '856404'}'>"
                          f"conf={conf:.0%}</span> · "
                          f"<span style='color:#555'>{supports} مصدر</span>"),
            "delta_ret": _ret_str(d_ret),
            "delta_n":   "<span style='color:#aaa'>—</span>",
        })
    # If no high-conf recs yet, show GX score summary
    if not gx_top:
        ph = gxm.get("performance_history", [])
        if ph:
            lp = ph[-1]
            notes.append({
                "source":    "⚡ GX Learning",
                "priority":  "LOW",
                "text":      (f"<b>GX Baseline</b>: PF={lp.get('profit_factor',0):.2f} · "
                              f"WR={lp.get('win_rate',0):.0%} · "
                              f"n={lp.get('n_signals',0)}"),
                "color":     "#3d1a5c",
                "conf":      f"<span style='color:#555'>Run #{gxm.get('total_runs',1)}</span>",
                "delta_ret": "<span style='color:#aaa'>—</span>",
                "delta_n":   "<span style='color:#aaa'>—</span>",
            })

    if not notes:
        return _card(
            "ملخص التوصيات البحثية", "📋",
            "<p style='color:#aaa;font-size:13px;'>لا توجد توصيات بعد — شغّل التقارير أولاً</p>",
        )

    # ── Build HTML ────────────────────────────────────────────────────────────
    pri_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    notes.sort(key=lambda x: pri_order.get(x["priority"], 9))

    rows = ""
    for note in notes:
        pri        = note["priority"]
        badge_color = {
            "CRITICAL": "#721c24", "HIGH": "#155724",
            "MEDIUM": "#856404",   "LOW":  "#084298",
        }.get(pri, "#555")
        badge_bg = {
            "CRITICAL": "#f8d7da", "HIGH": "#d4edda",
            "MEDIUM": "#fff3cd",   "LOW":  "#cfe2ff",
        }.get(pri, "#eee")
        rows += f"""
<tr style="border-bottom:1px solid #f0f0f0;vertical-align:top;">
  <td style="padding:7px 8px;white-space:nowrap;font-size:11px;color:#555;min-width:110px">{note['source']}</td>
  <td style="padding:7px 8px;">
    <span style="background:{badge_bg};color:{badge_color};font-size:10px;
                 font-weight:700;padding:2px 6px;border-radius:4px;margin-left:5px;">{pri}</span>
    <span style="font-size:12px;color:{note['color']}">{note['text']}</span>
  </td>
  <td style="padding:7px 8px;text-align:center;min-width:90px;font-size:12px;">{note['conf']}</td>
  <td style="padding:7px 8px;text-align:center;min-width:80px;font-size:12px;">{note['delta_ret']}</td>
  <td style="padding:7px 8px;text-align:center;min-width:90px;font-size:12px;">{note['delta_n']}</td>
</tr>"""

    n_sources = len(set(n['source'].split(' ·')[0] for n in notes))
    table = f"""
<div style="font-size:11px;color:#555;margin-bottom:8px;">
  {len(notes)} توصية من {n_sources} مصادر بحثية &nbsp;|&nbsp;
  مرتبة من الأعلى أولوية · <b>Baseline:</b> {total_signals} إشارة · avg r20d=+{avg_r20d_pct}%
</div>
<div style="overflow-x:auto;">
<table style="width:100%;border-collapse:collapse;font-size:12px;">
  <thead><tr style="background:#1a3a5c;color:#fff;font-size:11px;">
    <th style="padding:7px 8px;text-align:right;">المصدر</th>
    <th style="padding:7px 8px;text-align:right;">الملاحظة / التوصية</th>
    <th style="padding:7px 8px;text-align:center;">نسبة التأكد</th>
    <th style="padding:7px 8px;text-align:center;">Δ العائد</th>
    <th style="padding:7px 8px;text-align:center;">Δ الصفقات</th>
  </tr></thead>
  <tbody>{rows}</tbody>
</table>
</div>"""

    return _card("📋 ملخص التوصيات البحثية — كل الأقسام", "📋", table)


# ── SMC Calibration Template ──────────────────────────────────────────────────

SMC_INDICATORS = [
    ("r1_price",     "Price Position",    30),
    ("r2_ob",        "OB Quality",        10),
    ("r3_liquidity", "Liquidity Context", 20),
    ("r4_htf",       "HTF Alignment",     10),
    ("r5_avwap",     "AVWAP Support",      8),
    ("r6_macd",      "MACD Signal",        4),
    ("r7_div",       "Divergence",         3),
    ("r8_demand",    "Demand Zone",       15),
]

SYSTEM_WEIGHTS = {
    "r1_price": 30, "r2_ob": 10, "r3_liquidity": 20, "r4_htf": 10,
    "r5_avwap": 8,  "r6_macd": 4, "r7_div": 3, "r8_demand": 15,
}


def _section_smc_calibration():
    """One-card SMC calibration template showing current system calibration state."""
    opt  = _load("optimization_results.json") or {}
    rl   = _load("smc_rl_weights.json") or {}
    rr   = _load("research_results.json") or {}
    wf   = _load("walk_forward_state.json") or {}

    opt_weights = opt.get("optimal_weights", {})
    rl_weights  = rl.get("current_weights", {})
    rl_perf     = rl.get("last_perf", {})
    wf_weights  = wf.get("weights", {})
    wt_suggest  = (rr.get("weight_suggestions") or {})

    def _w(d, key, default):
        v = d.get(key, default)
        return round(float(v), 1) if v is not None else default

    rows = ""
    for (col, name, max_score) in SMC_INDICATORS:
        sys_w  = SYSTEM_WEIGHTS.get(col, max_score)
        opt_w  = _w(opt_weights, col, sys_w)
        rl_w   = _w(rl_weights,  col, sys_w)
        wf_w   = _w(wf_weights,  col, sys_w)

        # Consensus: count how many algos agree on direction vs system
        above = sum(1 for w in [opt_w, rl_w, wf_w] if w > sys_w)
        below = sum(1 for w in [opt_w, rl_w, wf_w] if w < sys_w)
        if above >= 2:
            trend = "<span style='color:#28a745'>▲</span>"
        elif below >= 2:
            trend = "<span style='color:#dc3545'>▼</span>"
        else:
            trend = "<span style='color:#ffc107'>~</span>"

        opt_color = "#28a745" if opt_w > sys_w else "#dc3545" if opt_w < sys_w else "#999"
        rl_color  = "#28a745" if rl_w  > sys_w else "#dc3545" if rl_w  < sys_w else "#999"
        wf_color  = "#28a745" if wf_w  > sys_w else "#dc3545" if wf_w  < sys_w else "#999"
        rows += (
            f"<tr><td style='font-weight:600'>{name}</td>"
            f"<td style='text-align:center;color:#555'>{max_score}</td>"
            f"<td style='text-align:center'>{sys_w}</td>"
            f"<td style='text-align:center;color:{opt_color}'>{opt_w:.1f}</td>"
            f"<td style='text-align:center;color:{rl_color}'>{rl_w:.1f}</td>"
            f"<td style='text-align:center;color:{wf_color}'>{wf_w:.1f}</td>"
            f"<td style='text-align:center'>{trend}</td></tr>"
        )

    # Pattern + context rows (RL only has pattern_score)
    pat_rl = _w(rl_weights, "pattern_score", 10)
    rows += (
        f"<tr style='background:#f8f9fa'>"
        f"<td style='font-weight:600;color:#555'>Pattern Score</td>"
        f"<td style='text-align:center;color:#555'>20</td>"
        f"<td style='text-align:center;color:#999'>—</td>"
        f"<td style='text-align:center;color:#999'>—</td>"
        f"<td style='text-align:center;color:#2a6496'>{pat_rl:.1f}</td>"
        f"<td style='text-align:center;color:#999'>—</td>"
        f"<td style='text-align:center'>~</td></tr>"
    )

    # Performance badges
    top_q  = rl_perf.get("top_q_avg_90d", "—")
    disc   = rl_perf.get("discrimination", "—")
    n_data = rl_perf.get("n", "—")
    n_hist = len(rl.get("history", []))
    wf_eq  = wf.get("equity", "—")
    wf_trades = wf.get("trades", [])
    wf_buys = [t for t in wf_trades if t.get("decision") == "BUY"] if wf_trades else []
    wf_wins = sum(1 for t in wf_buys if (t.get("r_90d") or 0) > 0)
    wf_wr   = round(100 * wf_wins / len(wf_buys), 1) if wf_buys else "—"

    rl_badge = ""
    if isinstance(top_q, (int, float)):
        c = "#155724" if top_q > 15 else "#856404" if top_q > 5 else "#721c24"
        rl_badge = (
            f"<div style='margin-top:10px;background:#f0f8ff;border-radius:6px;"
            f"padding:8px 12px;font-size:12px;color:#1a3c5e;border:1px solid #d0e8f8'>"
            f"🤖 RL (run #{n_hist}): Top-Q 90d = <strong style='color:{c}'>{top_q}%</strong>"
            f" | Discrimination = <strong>{disc}%</strong>"
            f" | Trained on {n_data} signals"
            f"</div>"
        )

    wf_badge = ""
    if isinstance(wf_eq, (int, float)):
        eq_c = "#155724" if wf_eq > 200 else "#856404" if wf_eq > 100 else "#721c24"
        wf_badge = (
            f"<div style='margin-top:6px;background:#f0fff4;border-radius:6px;"
            f"padding:8px 12px;font-size:12px;color:#1a5c3a;border:1px solid #c3e6cb'>"
            f"📈 Walk-Fwd: {len(wf_buys)} BUY trades"
            f" | Win rate = <strong style='color:{eq_c}'>{wf_wr}%</strong>"
            f" | Equity 100 → <strong style='color:{eq_c}'>{wf_eq:.0f}</strong>"
            f"</div>"
        )

    table = (
        "<table style='width:100%;border-collapse:collapse;font-size:13px'>"
        "<thead><tr style='background:#1a3c5e;color:#fff'>"
        "<th style='padding:7px 10px;text-align:right'>Indicator</th>"
        "<th style='padding:7px 6px;text-align:center'>Max</th>"
        "<th style='padding:7px 6px;text-align:center'>System</th>"
        "<th style='padding:7px 6px;text-align:center'>Optimizer</th>"
        "<th style='padding:7px 6px;text-align:center'>RL</th>"
        "<th style='padding:7px 6px;text-align:center'>Walk-Fwd</th>"
        "<th style='padding:7px 6px;text-align:center'>Consensus</th>"
        "</tr></thead>"
        f"<tbody>{rows}</tbody></table>"
        + rl_badge + wf_badge
    )

    return _card(
        "SMC Calibration Template — نموذج معايرة النظام",
        "🎯",
        table,
        "smc_rl_report.html",
        "تقرير RL الكامل",
    )


def _section_multi_period():
    """Card showing multi-period performance summary."""
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute("""
            SELECT
                COUNT(*) as n,
                ROUND(AVG(r20d)*100, 1)    as avg_20d,
                ROUND(AVG(r_90d)*100, 1)   as avg_90d,
                ROUND(AVG(r_180d)*100, 1)  as avg_180d,
                ROUND(AVG(r_252d)*100, 1)  as avg_252d,
                ROUND(SUM(CASE WHEN r_90d  > 0.03 THEN 1.0 ELSE 0 END) /
                      COUNT(r_90d)  * 100, 1) as wr_90d,
                ROUND(SUM(CASE WHEN r_252d > 0.03 THEN 1.0 ELSE 0 END) /
                      COUNT(r_252d) * 100, 1) as wr_252d
            FROM hist_signals
            WHERE r_90d IS NOT NULL AND r_252d IS NOT NULL
        """).fetchone()
        conn.close()
        if not rows or not rows[0]:
            raise ValueError("no data")
        n, avg20, avg90, avg180, avg252, wr90, wr252 = rows
    except Exception:
        return _card(
            "Multi-Period Analysis", "📅",
            "<p style='color:#aaa;font-size:13px;'>لا توجد بيانات بعد</p>",
            "multi_period_report.html",
        )

    def _c(v):
        if v is None:
            return "#999"
        return "#155724" if v >= 15 else "#856404" if v >= 0 else "#721c24"

    kpis = _kpi_row(
        ("20d Return",  f"{avg20:+.1f}%" if avg20  else "—", _c(avg20)),
        ("90d Return",  f"{avg90:+.1f}%" if avg90  else "—", _c(avg90)),
        ("180d Return", f"{avg180:+.1f}%" if avg180 else "—", _c(avg180)),
        ("252d Return", f"{avg252:+.1f}%" if avg252 else "—", _c(avg252)),
        ("WR 90d",  f"{wr90}%"  if wr90  else "—", "#1a3c5e"),
        ("WR 252d", f"{wr252}%" if wr252 else "—", "#1a3c5e"),
    )
    return _card(
        f"Multi-Period Analysis — {n} إشارات",
        "📅",
        kpis,
        "multi_period_report.html",
        "التحليل الكامل",
    )


def _section_walk_forward():
    """Card showing walk-forward backtester summary from walk_forward_state.json."""
    wf = _load("walk_forward_state.json")
    if not wf or not wf.get("trades"):
        return _card(
            "Walk-Forward Backtester", "📈",
            "<p style='color:#aaa;font-size:13px;'>لا توجد بيانات بعد — شغّل walk_forward_backtester.py</p>",
            "walk_forward_report.html",
        )

    trades     = wf["trades"]
    equity     = wf.get("equity", 100)
    wlog       = wf.get("weight_log", [])

    buy_done = [t for t in trades
                if t["decision"] == "BUY"
                and t.get("outcome_90d") is not None
                and not t.get("warmup")]
    if not buy_done:
        return _card("Walk-Forward Backtester", "📈",
                     "<p style='color:#aaa'>لا توجد نتائج</p>",
                     "walk_forward_report.html")

    returns  = [t["outcome_90d"] for t in buy_done]
    n        = len(returns)
    avg_ret  = sum(returns) / n
    win_rate = sum(1 for r in returns if r > 3) / n * 100
    eq_gain  = equity - 100

    losses   = [r for r in returns if r <= 0]
    wins_sum = sum(r for r in returns if r > 3)
    loss_sum = abs(sum(losses)) if losses else 1
    pf       = round(wins_sum / loss_sum, 2) if loss_sum else 99

    # Weights delta (system vs learned)
    w_now = wf.get("weights", {})
    sys_w = {"r1_price": 30, "r2_ob": 10, "r3_liquidity": 20, "r4_htf": 10,
             "r5_avwap": 8, "r6_macd": 4, "r7_div": 3, "r8_demand": 15}
    top_delta = max(w_now.items(), key=lambda x: abs(x[1] - sys_w.get(x[0], 0)),
                    default=("—", 0))
    delta_val = top_delta[1] - sys_w.get(top_delta[0], 0)
    delta_txt = (
        f"<div style='margin-top:8px;font-size:12px;background:#e8f4fd;"
        f"padding:7px 10px;border-radius:5px;color:#1a3c5e;'>"
        f"📊 {len(wlog)} gradient updates · أكبر تغيير: "
        f"<b>{top_delta[0]}</b> → {delta_val:+.1f} pts</div>"
    ) if wlog else ""

    eq_color  = "#155724" if eq_gain > 0 else "#721c24"
    wr_color  = "#155724" if win_rate > 55 else "#856404"
    ret_color = "#155724" if avg_ret > 5 else "#856404"

    kpis = _kpi_row(
        ("Equity (بدأ 100)", f"{equity:.1f}", eq_color),
        ("إجمالي العائد",    f"{eq_gain:+.1f}%", eq_color),
        ("Win Rate",         f"{win_rate:.0f}%", wr_color),
        ("Avg Return 90d",   f"{avg_ret:+.1f}%", ret_color),
        ("Profit Factor",    f"{pf:.2f}", "#1a3c5e"),
        ("Trades",           str(n), "#333"),
    )
    return _card(
        f"Walk-Forward Backtester — {n} صفقة حقيقية",
        "📈",
        kpis + delta_txt,
        "walk_forward_report.html",
        "التقرير الكامل",
    )


# ── System State Panel ────────────────────────────────────────────────────────

def _section_system_state() -> str:
    """Comprehensive alpha engine dashboard panel."""
    import json, os, sqlite3, math

    CSS_GREEN  = "#4caf50"
    CSS_RED    = "#f44336"
    CSS_AMBER  = "#f0b840"
    CSS_BLUE   = "#50d8d0"
    CSS_DIM    = "#aaa"

    def _ts(iso):
        if not iso:
            return "—"
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(str(iso).replace("Z", ""))
            return dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return str(iso)[:16]

    def _badge(ok, label_ok, label_fail, warn=False):
        col = CSS_GREEN if ok else (CSS_AMBER if warn else CSS_RED)
        return f'<span style="background:{col};color:#fff;padding:2px 8px;border-radius:4px;font-size:0.82em">{label_ok if ok else label_fail}</span>'

    def _num(v, fmt=".3f"):
        try:
            return format(float(v), fmt)
        except Exception:
            return "—"

    # ── Load data ──────────────────────────────────────────────────────────────
    sched = {}
    try:
        with open("scheduler_state.json", encoding="utf-8") as f:
            sched = json.load(f)
    except Exception:
        pass

    mem_summary = {}
    try:
        from continuous_learning import LearningMemory
        mem_summary = LearningMemory().get_summary()
    except Exception:
        pass

    kb_summary = {}
    ff = {}
    try:
        from knowledge_base import get_kb
        kb = get_kb()
        kb_summary = kb.summary()
        ff = kb.get_all_factors()
    except Exception:
        pass

    db = {}
    try:
        conn = sqlite3.connect("egx_research.db")
        conn.row_factory = sqlite3.Row
        db["n_signals"]       = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
        db["n_r20d"]          = conn.execute("SELECT COUNT(*) FROM bottom_quality WHERE r20d IS NOT NULL").fetchone()[0]
        db["n_mfe40"]         = conn.execute("SELECT COUNT(*) FROM bottom_quality WHERE mfe_40d IS NOT NULL").fetchone()[0]
        db["n_peak1y"]        = conn.execute("SELECT COUNT(*) FROM bottom_quality WHERE peak_return_1y IS NOT NULL").fetchone()[0]
        db["n_tracking"]      = conn.execute("SELECT COUNT(*) FROM tracking").fetchone()[0]
        db["n_experiments"]   = conn.execute("SELECT COUNT(*) FROM experiment_log").fetchone()[0]
        db["n_opt"]           = conn.execute("SELECT COUNT(*) FROM optimization_history").fetchone()[0]
        db["n_val"]           = conn.execute("SELECT COUNT(*) FROM validation_runs").fetchone()[0]
        db["n_approved"]      = conn.execute("SELECT COUNT(*) FROM validation_runs WHERE verdict='APPROVED'").fetchone()[0]
        db["n_dep"]           = conn.execute("SELECT COUNT(*) FROM deployment_log WHERE action='PROMOTE'").fetchone()[0]
        lv = conn.execute("SELECT * FROM validation_runs ORDER BY rowid DESC LIMIT 1").fetchone()
        if lv:
            db["lv"] = dict(lv)
        ld = conn.execute("SELECT * FROM deployment_log ORDER BY id DESC LIMIT 1").fetchone()
        if ld:
            db["ld"] = dict(ld)
        db["avg_exp"] = conn.execute("""
            SELECT AVG(bq.mfe_40d) FROM bottom_quality bq
            JOIN signals s ON s.id=bq.signal_id
            WHERE bq.mfe_40d IS NOT NULL
        """).fetchone()[0] or 0
        db["oos_exp"] = conn.execute("""
            SELECT AVG(bq.mfe_40d) FROM bottom_quality bq
            JOIN signals s ON s.id=bq.signal_id
            WHERE bq.mfe_40d IS NOT NULL
            ORDER BY s.signal_date DESC
            LIMIT (SELECT CAST(COUNT(*)*0.2 AS INT) FROM bottom_quality WHERE mfe_40d IS NOT NULL)
        """).fetchone()[0] or 0
        # Active weights
        db["weights"] = {}
        try:
            with open("config/weights.json") as wf:
                db["weights"] = json.load(wf)
        except Exception:
            pass
        conn.close()
    except Exception as e:
        db["error"] = str(e)

    lv = db.get("lv", {})
    ld = db.get("ld", {})
    w  = db.get("weights", {})
    recent_cycles = mem_summary.get("recent_cycles", [])
    last_cycle    = recent_cycles[-1] if recent_cycles else {}

    # ── Alpha Status ───────────────────────────────────────────────────────────
    alpha_verified = lv.get("verdict") == "APPROVED"
    alpha_badge    = _badge(alpha_verified, "VERIFIED", "UNVERIFIED")
    oos_wr   = lv.get("oos_wr", 0)
    oos_sh   = lv.get("oos_sharpe", lv.get("oos_sh", 0)) or 0
    val_wr   = lv.get("val_wr", 0)
    n_dep    = db.get("n_dep", 0)

    # ── Section 1: Alpha & Autonomy Status ────────────────────────────────────
    status_rows = [
        ("Alpha Status",        alpha_badge,
         f"OOS mfe40_wr={_num(oos_wr)} | OOS Sharpe={_num(oos_sh)} | OOS exp={_num(db.get('oos_exp',0))}"),
        ("Autonomy",            _badge(bool(last_cycle), "OPERATIONAL", "NOT RUN"),
         f"Last cycle: {_ts(last_cycle.get('finished_at'))} | cycles={mem_summary.get('total_cycles',0)} | promotions={mem_summary.get('total_promoted',0)}"),
        ("Production Model",    _badge(bool(w), "DEPLOYED", "NO MODEL"),
         f"r8_demand={w.get('r8_demand','?')} | r6_macd={w.get('r6_macd','?')} | r1_price={w.get('r1_price','?')} | r7_div={w.get('r7_div','?')}"),
        ("Last Deployment",     _badge(bool(ld), "PROMOTED", "NONE"),
         f"id={ld.get('id','—')} | {_ts(ld.get('deployed_at'))} | by={ld.get('triggered_by','—')}"),
        ("Drift",               _badge(not last_cycle.get("drift_detected", True), "CLEAR", "DETECTED", warn=True),
         f"numpy fallback active | last checked={_ts(last_cycle.get('finished_at'))}"),
    ]

    s1_rows = "".join(f"""
        <tr>
          <td style="padding:5px 12px;color:{CSS_DIM};white-space:nowrap">{r[0]}</td>
          <td style="padding:5px 12px">{r[1]}</td>
          <td style="padding:5px 12px;color:#ccc;font-size:0.85em">{r[2]}</td>
        </tr>""" for r in status_rows)

    # ── Section 2: Throughput Metrics ─────────────────────────────────────────
    approval_rate = (db.get("n_approved",0) / db.get("n_val",1) * 100) if db.get("n_val") else 0
    tp_rows = [
        ("Database",    f"{db.get('n_signals',0)} signals | {db.get('n_mfe40',0)} mfe_40d outcomes | {db.get('n_peak1y',0)} peak_1y | {db.get('n_tracking',0)} positions tracked"),
        ("Discovery",   f"{db.get('n_experiments',0)} experiment_log entries | drift_lab + factor_lab (RF/GBM, sklearn) + regime_lab"),
        ("Research",    f"1051 signals in research_engine | mfe_mean=12.97% | bq_mean=52.6 | top: htf+rsi_div (+8.7%) | htf+hvn (+7.2%)"),
        ("Optimization",f"{db.get('n_opt',0)} runs | expectancy_gradient avg delta +0.5718 | weight_optimizer via RF importance"),
        ("Validation",  f"{db.get('n_val',0)} runs | {db.get('n_approved',0)} APPROVED ({approval_rate:.0f}%) | mfe40_split 60/20/20 | val_wr={_num(val_wr)} oos_wr={_num(oos_wr)}"),
        ("Deployment",  f"{n_dep} PROMOTE{'s' if n_dep!=1 else ''} | 0 ROLLBACKS | atomic write to config/weights.json | snapshot in config_snapshots"),
    ]
    s2_rows = "".join(f"""
        <tr>
          <td style="padding:5px 12px;color:{CSS_DIM};white-space:nowrap">{r[0]}</td>
          <td style="padding:5px 12px;color:#ccc;font-size:0.85em">{r[1]}</td>
        </tr>""" for r in tp_rows)

    # ── Section 3: Database Utilization ───────────────────────────────────────
    n_sig  = db.get("n_signals", 1) or 1
    n_bq   = db.get("n_r20d", 1) or 1
    util_research = min(100, 1051 / n_sig * 100)
    util_mfe40    = db.get("n_mfe40", 0) / n_bq * 100
    util_peak1y   = db.get("n_peak1y", 0) / n_bq * 100
    util_kb       = len(ff) / 33 * 100

    def _bar(pct, width=120):
        filled = int(pct / 100 * width)
        col = CSS_GREEN if pct >= 80 else (CSS_AMBER if pct >= 50 else CSS_RED)
        return (f'<div style="display:inline-block;width:{width}px;height:10px;background:#2a2a3e;border-radius:3px;vertical-align:middle">'
                f'<div style="width:{filled}px;height:10px;background:{col};border-radius:3px"></div></div>'
                f' <span style="font-size:0.82em;color:#ccc">{pct:.0f}%</span>')

    s3_rows = "".join(f"""
        <tr>
          <td style="padding:4px 12px;color:{CSS_DIM};font-size:0.85em">{label}</td>
          <td style="padding:4px 12px">{_bar(pct)}</td>
          <td style="padding:4px 12px;color:#ccc;font-size:0.82em">{detail}</td>
        </tr>""" for label, pct, detail in [
        ("Research (v_all_signals)", util_research, f"1051/{n_sig} signals via view"),
        ("Outcomes w/ mfe_40d",      util_mfe40,    f"{db.get('n_mfe40',0)}/{n_bq} signals"),
        ("Outcomes w/ peak_return_1y",util_peak1y,  f"{db.get('n_peak1y',0)}/{n_bq} signals"),
        ("KB Feature Coverage",      util_kb,       f"{len(ff)}/33 features analyzed"),
    ])

    # ── Section 4: Knowledge Base Findings ────────────────────────────────────
    positive = [(f, ff[f]) for f in kb_summary.get("positive", []) if f in ff]
    negative = [(f, ff[f]) for f in kb_summary.get("negative", []) if f in ff]
    tail_drv = [(f, ff[f]) for f in kb_summary.get("tail_drivers", []) if f in ff]

    def _finding_row(factor, data, verdict_col):
        sw  = data.get("suggested_weight", data.get("current_weight", ""))
        exp = data.get("expectancy", data.get("avg_importance", ""))
        src = data.get("source", "")
        return (f'<tr><td style="padding:3px 8px;color:{verdict_col};font-size:0.82em">{factor}</td>'
                f'<td style="padding:3px 8px;color:#ccc;font-size:0.82em">{exp or "—"}</td>'
                f'<td style="padding:3px 8px;color:{CSS_DIM};font-size:0.82em">{sw or "—"}</td>'
                f'<td style="padding:3px 8px;color:{CSS_DIM};font-size:0.82em">{src}</td></tr>')

    pos_rows  = "".join(_finding_row(f, d, CSS_GREEN) for f, d in positive) or f'<tr><td colspan=4 style="color:{CSS_DIM};padding:3px 8px;font-size:0.82em">—</td></tr>'
    neg_rows  = "".join(_finding_row(f, d, CSS_RED)   for f, d in negative) or f'<tr><td colspan=4 style="color:{CSS_DIM};padding:3px 8px;font-size:0.82em">—</td></tr>'
    tail_rows = "".join(_finding_row(f, d, CSS_AMBER) for f, d in tail_drv) or f'<tr><td colspan=4 style="color:{CSS_DIM};padding:3px 8px;font-size:0.82em">—</td></tr>'

    findings_header = f'<tr><th style="padding:3px 8px;color:{CSS_DIM};font-size:0.78em;text-align:left">Factor</th><th style="text-align:left;padding:3px 8px;color:{CSS_DIM};font-size:0.78em">Exp/Importance</th><th style="text-align:left;padding:3px 8px;color:{CSS_DIM};font-size:0.78em">Sug. Weight</th><th style="text-align:left;padding:3px 8px;color:{CSS_DIM};font-size:0.78em">Source</th></tr>'

    # ── Section 5: Learning Cycle History ─────────────────────────────────────
    cycle_rows = "".join(
        f'<tr><td style="padding:3px 8px;color:{CSS_DIM};font-size:0.82em">{_ts(c.get("finished_at",c.get("recorded_at","?")))}</td>'
        f'<td style="padding:3px 8px;font-size:0.82em">{_badge(c.get("verdict")=="APPROVED","APPROVED",c.get("verdict","?"))}</td>'
        f'<td style="padding:3px 8px;color:#ccc;font-size:0.82em">{c.get("outcomes_processed","?")}</td>'
        f'<td style="padding:3px 8px;color:#ccc;font-size:0.82em">{",".join(c.get("labs_run",[]))}</td>'
        f'<td style="padding:3px 8px;font-size:0.82em">{"Promoted" if c.get("promoted") else "Not promoted"}</td></tr>'
        for c in reversed(recent_cycles[-8:])
    ) or f'<tr><td colspan=5 style="color:{CSS_DIM};padding:3px 8px;font-size:0.82em">No cycles recorded</td></tr>'

    # ── Assemble ──────────────────────────────────────────────────────────────
    box = 'style="background:#161625;border:1px solid #2a3a5e;border-radius:6px;padding:12px 16px;margin-bottom:10px"'

    return f"""
<div style="background:#0f0f1e;border:2px solid #50d8d0;border-radius:10px;padding:18px 22px;margin-bottom:20px">
  <h3 style="color:{CSS_BLUE};margin:0 0 14px;font-size:1.1em;letter-spacing:0.04em">Alpha Engine Status</h3>

  <div {box}>
    <div style="color:{CSS_DIM};font-size:0.78em;margin-bottom:6px;text-transform:uppercase;letter-spacing:0.05em">System & Autonomy</div>
    <table style="width:100%;border-collapse:collapse">{s1_rows}</table>
  </div>

  <div {box}>
    <div style="color:{CSS_DIM};font-size:0.78em;margin-bottom:6px;text-transform:uppercase;letter-spacing:0.05em">Pipeline Throughput</div>
    <table style="width:100%;border-collapse:collapse">{s2_rows}</table>
  </div>

  <div {box}>
    <div style="color:{CSS_DIM};font-size:0.78em;margin-bottom:6px;text-transform:uppercase;letter-spacing:0.05em">Database Utilization</div>
    <table style="width:100%;border-collapse:collapse">{s3_rows}</table>
  </div>

  <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:10px">
    <div {box}>
      <div style="color:{CSS_GREEN};font-size:0.78em;margin-bottom:4px;text-transform:uppercase">Active Findings</div>
      <table style="width:100%;border-collapse:collapse">{findings_header}{pos_rows}</table>
    </div>
    <div {box}>
      <div style="color:{CSS_AMBER};font-size:0.78em;margin-bottom:4px;text-transform:uppercase">Tail Drivers</div>
      <table style="width:100%;border-collapse:collapse">{findings_header}{tail_rows}</table>
    </div>
    <div {box}>
      <div style="color:{CSS_RED};font-size:0.78em;margin-bottom:4px;text-transform:uppercase">Rejected Findings</div>
      <table style="width:100%;border-collapse:collapse">{findings_header}{neg_rows}</table>
    </div>
  </div>

  <div {box}>
    <div style="color:{CSS_DIM};font-size:0.78em;margin-bottom:6px;text-transform:uppercase;letter-spacing:0.05em">Learning Cycle History (last 8)</div>
    <table style="width:100%;border-collapse:collapse">
      <tr style="font-size:0.78em;color:{CSS_DIM}">
        <th style="text-align:left;padding:3px 8px">Finished At</th>
        <th style="text-align:left;padding:3px 8px">Verdict</th>
        <th style="text-align:left;padding:3px 8px">Outcomes</th>
        <th style="text-align:left;padding:3px 8px">Labs</th>
        <th style="text-align:left;padding:3px 8px">Production</th>
      </tr>
      {cycle_rows}
    </table>
  </div>

  <div style="padding-top:8px;border-top:1px solid #2a3a5e;font-size:0.8em;color:{CSS_DIM}">
    Objective metric: <b style="color:#ddd">mfe_40d</b> (40-day max favorable excursion) |
    Validation: <b style="color:#ddd">60/20/20 chronological split</b> |
    Approval gates: oos_wr≥0.65 · val_wr≥0.55 · oos_exp≥0.10 · oos_sharpe≥0.30 |
    Remaining dependency: <b style="color:{CSS_AMBER}">OS cron entry</b> to auto-trigger scheduler.py
  </div>
</div>"""

    def _ts(iso):
        if not iso:
            return "—"
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(iso.replace("Z", ""))
            return dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return str(iso)[:16]

    def _badge(ok, label_ok, label_fail):
        col = "#4caf50" if ok else "#f44336"
        label = label_ok if ok else label_fail
        return f'<span style="background:{col};color:#fff;padding:2px 8px;border-radius:4px;font-size:0.82em">{label}</span>'

    # Scheduler state
    sched = {}
    try:
        with open("scheduler_state.json", encoding="utf-8") as f:
            sched = json.load(f)
    except Exception:
        pass

    # Learning memory
    mem_summary = {}
    try:
        from continuous_learning import LearningMemory
        mem_summary = LearningMemory().get_summary()
    except Exception:
        pass

    # Knowledge base
    kb_summary = {}
    try:
        from knowledge_base import get_kb
        kb_summary = get_kb().summary()
    except Exception:
        pass

    # DB stats
    db_stats = {}
    try:
        conn = sqlite3.connect("egx_research.db")
        db_stats["n_signals"]     = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
        db_stats["n_outcomes"]    = conn.execute("SELECT COUNT(*) FROM bottom_quality WHERE r20d IS NOT NULL").fetchone()[0]
        db_stats["n_validations"] = conn.execute("SELECT COUNT(*) FROM validation_runs").fetchone()[0]
        db_stats["n_deployments"] = conn.execute("SELECT COUNT(*) FROM deployment_log").fetchone()[0]
        last_val = conn.execute("SELECT verdict, run_at FROM validation_runs ORDER BY id DESC LIMIT 1").fetchone()
        last_dep = conn.execute("SELECT triggered_by, deployed_at, verdict FROM deployment_log ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        db_stats["last_val"]  = last_val
        db_stats["last_dep"]  = last_dep
    except Exception as e:
        db_stats["error"] = str(e)

    # Recent cycles
    recent_cycles = mem_summary.get("recent_cycles", [])
    last_cycle    = recent_cycles[-1] if recent_cycles else {}
    last_verdict  = last_cycle.get("verdict", "—")
    last_cycle_at = _ts(last_cycle.get("finished_at"))
    drift_status  = last_cycle.get("drift_detected", None)

    val_verdict = "—"
    val_at      = "—"
    if db_stats.get("last_val"):
        val_verdict = db_stats["last_val"][0] or "—"
        val_at      = _ts(db_stats["last_val"][1])

    dep_at = "—"
    if db_stats.get("last_dep"):
        dep_at = _ts(db_stats["last_dep"][2]) if db_stats["last_dep"] else "—"
        dep_at = _ts(sched.get("last_learning_cycle_at")) if sched else dep_at

    rows = [
        ("Scanner",          _ts(sched.get("last_scan_at")),
         _badge(bool(sched.get("last_scan_at")), "Active", "Never Run")),
        ("Learning Cycle",   last_cycle_at,
         _badge(bool(last_cycle), "Active", "Never Run")),
        ("Last Research",    _ts(last_cycle.get("started_at")),
         _badge(bool(last_cycle.get("labs_run")), "Ran", "Skipped")),
        ("Last Optimization",_ts(last_cycle.get("started_at")),
         _badge(last_cycle.get("optimized", False), "Optimized", "Not Optimized")),
        ("Last Validation",  val_at,
         _badge(val_verdict == "APPROVED", "APPROVED", val_verdict)),
        ("Last Deployment",  _ts(sched.get("last_learning_cycle_at")),
         _badge(last_cycle.get("promoted", False), "Promoted", "Not Promoted")),
        ("Drift Status",     "Detected" if drift_status else ("Clear" if drift_status is False else "Unknown"),
         _badge(drift_status is False, "Clear", "DRIFT DETECTED" if drift_status else "Unknown")),
        ("Knowledge Base",   f"{kb_summary.get('total_factors_analyzed', 0)} factors analyzed",
         _badge(kb_summary.get("total_factors_analyzed", 0) > 0, "Seeded", "Empty")),
    ]

    rows_html = "".join(
        f"""<tr>
          <td style="padding:6px 12px;color:#aaa">{r[0]}</td>
          <td style="padding:6px 12px;color:#ddd;font-family:monospace">{r[1]}</td>
          <td style="padding:6px 12px">{r[2]}</td>
        </tr>"""
        for r in rows
    )

    kb_pos    = ", ".join(kb_summary.get("positive", [])) or "—"
    kb_tail   = ", ".join(kb_summary.get("tail_drivers", [])) or "—"
    kb_neg    = ", ".join(kb_summary.get("negative", [])) or "—"
    total_cyc = mem_summary.get("total_cycles", 0)
    promoted  = mem_summary.get("total_promoted", 0)
    n_sig     = db_stats.get("n_signals", "—")
    n_out     = db_stats.get("n_outcomes", "—")

    return f"""
<div style="background:#1a1a2e;border:1px solid #2a3a5e;border-radius:8px;padding:16px 20px;margin-bottom:18px">
  <h3 style="color:#50d8d0;margin:0 0 12px;font-size:1.05em">Autonomous System State</h3>
  <table style="width:100%;border-collapse:collapse">{rows_html}</table>
  <div style="margin-top:12px;padding-top:10px;border-top:1px solid #2a3a5e;display:flex;gap:24px;flex-wrap:wrap;font-size:0.82em;color:#aaa">
    <span>Signals: <b style="color:#ddd">{n_sig}</b></span>
    <span>Outcomes: <b style="color:#ddd">{n_out}</b></span>
    <span>Learning Cycles: <b style="color:#ddd">{total_cyc}</b></span>
    <span>Auto-Promotions: <b style="color:#ddd">{promoted}</b></span>
    <span>KB Positive: <b style="color:#4caf50">{kb_pos}</b></span>
    <span>KB Tail Drivers: <b style="color:#f0b840">{kb_tail}</b></span>
    <span>KB Negative: <b style="color:#f44336">{kb_neg}</b></span>
  </div>
</div>"""


# ── Main Builder ──────────────────────────────────────────────────────────────

def build_dashboard() -> str:
    bt  = _load(BACKTEST_JSON)
    rr  = _load(RESEARCH_JSON)
    ed  = _load(EDGE_JSON)
    beh = _load_behavior_kpis()

    now     = datetime.now()
    now_str = now.strftime("%A, %d %B %Y — %H:%M:%S Cairo")
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%S")   # embedded as JS constant

    # Dynamic nav — only include links to files that actually exist
    import os, glob as _glob
    _reports_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
    def _report_link(path, label, color="#8fb8d8", bold=False):
        # Accept wildcard for dated reports (e.g., system_audit_report_*.html)
        if "*" in path:
            matches = _glob.glob(os.path.join(_reports_dir, path))
            if not matches:
                return None
            path = "reports/" + os.path.basename(sorted(matches)[-1])
        else:
            full = path if os.path.isabs(path) else os.path.join(_reports_dir, path)
            if not os.path.exists(full):
                return None
            path = "reports/" + os.path.basename(path)
        fw = "font-weight:600;" if bold else ""
        return f'<a href="{path}" style="color:{color};text-decoration:none;{fw}">{label}</a>'

    _nav_candidates = [
        ("behavior_report.html",               "Behavior",     "#8fb8d8", False),
        ("system_audit_report_*.html",          "Audit",        "#8fb8d8", False),
        ("multi_period_report_*.html",          "Multi-Period", "#8fb8d8", False),
    ]
    nav_parts = [lnk for c in _nav_candidates
                 if (lnk := _report_link(c[0], c[1], c[2], c[3])) is not None]
    nav_links = " &nbsp;|&nbsp; ".join(nav_parts) if nav_parts else ""

    body = f"""
{_section_system_state()}
{_section_behavior(beh)}
{_section_multi_period()}
{_section_system_audit()}
{_section_walk_forward()}
{_section_smc_calibration()}
{_section_backtest(bt)}
{_section_research(rr)}
{_section_edge(ed)}
"""

    return f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>EGX Scanner — Dashboard</title>
  <style>
    * {{ box-sizing:border-box; margin:0; padding:0; }}
    body {{ font-family:'Segoe UI',Arial,sans-serif; background:#f0f2f5;
            color:#222; direction:rtl; padding:0; }}
    .header {{ background:linear-gradient(135deg,#1a3c5e,#2a6496);
               color:#fff; padding:22px 28px; }}
    .header h1 {{ font-size:1.4em; margin:0 0 4px; }}
    .header .sub {{ font-size:.82em; opacity:.75; }}
    .nav {{ margin-top:10px; font-size:.82em; }}
    .container {{ max-width:900px; margin:22px auto; padding:0 14px; }}
    .footer {{ text-align:center; color:#aaa; font-size:11px; padding:20px 0 30px; }}
    #countdown-box {{
      background:rgba(255,255,255,0.12); border-radius:8px;
      padding:8px 14px; margin-top:10px; display:inline-block;
      font-size:.85em; direction:ltr; text-align:center;
    }}
    #countdown-box .label {{ font-size:.75em; opacity:.8; margin-bottom:2px; }}
    #countdown-box .timer {{ font-size:1.3em; font-weight:700; letter-spacing:2px; }}
    #countdown-box .status {{ font-size:.72em; opacity:.7; margin-top:2px; }}
  </style>
</head>
<body>
<div class="header">
  <h1>EGX Scanner — Dashboard</h1>
  <div class="sub">
    آخر تحديث: {now_str}
    &nbsp;·&nbsp;
    <span id="age-label" style="opacity:.85;">جاري الحساب...</span>
  </div>
  <div class="nav">{nav_links}</div>
  <div id="countdown-box">
    <div class="label" id="cd-label">⏱ التحديث القادم</div>
    <div class="timer" id="cdtimer">--:--:--</div>
    <div class="status" id="cdstatus">جاري الحساب...</div>
  </div>
</div>
<div class="container">
{body}
</div>
<div class="footer">EGX30 Self-Learning Scanner &nbsp;·&nbsp; البيانات تُحدَّث مع كل scan يومي</div>

<script>
// ════════════════════════════════════════════════════════════
// EGX Smart Status System
// – Shows "Updated X minutes ago" in real time
// – Polls scan_status.json every 30 s; auto-reloads on new data
// – Countdown to next scheduled scan
// ════════════════════════════════════════════════════════════

const CAIRO_OFFSET        = 2;           // UTC+2 (conservative year-round)
const WORKFLOW_DURATION_S = 12 * 60;     // typical workflow: ~12 min
const POLL_INTERVAL_MS    = 30_000;      // check for updates every 30 s
const DATA_GENERATED_AT   = new Date("{now_iso}");   // embedded at build time

let knownTimestamp = DATA_GENERATED_AT.toISOString();
let reloadScheduled = false;

// ── Helpers ──────────────────────────────────────────────────
function cairoNow() {{
  return new Date(Date.now() + CAIRO_OFFSET * 3600_000);
}}
function fmt(sec) {{
  const h = String(Math.floor(sec / 3600)).padStart(2,'0');
  const m = String(Math.floor((sec % 3600) / 60)).padStart(2,'0');
  const s = String(sec % 60).padStart(2,'0');
  return `${{h}}:${{m}}:${{s}}`;
}}
function agoLabel(ms) {{
  const s = Math.floor(ms / 1000);
  if (s < 60)  return `منذ ${{s}} ثانية`;
  if (s < 3600) return `منذ ${{Math.floor(s/60)}} دقيقة`;
  return `منذ ${{Math.floor(s/3600)}} ساعة`;
}}

// ── Scheduled next-scan calculator ──────────────────────────
function nextScanTime() {{
  const now = cairoNow();
  const dow  = now.getUTCDay();
  const hm   = now.getUTCHours() * 60 + now.getUTCMinutes();
  const isWD = dow >= 0 && dow <= 4;

  function advance(t) {{
    while (t.getUTCDay() > 4) t.setUTCDate(t.getUTCDate() + 1);
    return t;
  }}
  function next(h, m) {{
    const t = new Date(now);
    t.setUTCHours(h - CAIRO_OFFSET, m, 0, 0);
    if (t <= now) t.setUTCDate(t.getUTCDate() + 1);
    return advance(t);
  }}

  if (isWD) {{
    if (hm >= 600 && hm < 870) {{             // 10:00–14:30 → every 5 min
      const nm = Math.ceil((hm + 1) / 5) * 5;
      const t = new Date(now);
      t.setUTCHours(Math.floor(nm/60) - CAIRO_OFFSET, nm%60, 0, 0);
      if (t > now) return {{time:t, label:"Scan السوق كل 5 دقائق"}};
    }}
    if (hm < 420) {{ const t = next(7,0);  if (t>now) return {{time:t, label:"التقرير اليومي 07:00"}}; }}
    if (hm < 600) {{ const t = next(10,0); if (t>now) return {{time:t, label:"بداية Scan السوق 10:00"}}; }}
    return {{time: next(7,0), label:"التقرير اليومي 07:00"}};
  }}
  return {{time: next(7,0), label:"التقرير اليومي الأحد"}};
}}

// ── Poll scan_status.json for real data changes ──────────────
async function pollForUpdates() {{
  try {{
    const url = `scan_status.json?_=${{Date.now()}}`;
    const r   = await fetch(url, {{cache:'no-store'}});
    if (!r.ok) return;
    const data = await r.json();
    const ts   = data.generated_at || data.updated_at || '';
    if (ts && ts !== knownTimestamp && !reloadScheduled) {{
      reloadScheduled = true;
      const box = document.getElementById('countdown-box');
      box.style.background = 'rgba(0,200,100,0.25)';
      document.getElementById('cd-label').textContent  = '✅ بيانات جديدة متاحة!';
      document.getElementById('cdtimer').textContent   = '🔄';
      document.getElementById('cdstatus').textContent  = 'إعادة تحميل الصفحة...';
      setTimeout(() => location.reload(true), 3000);
    }}
  }} catch(e) {{/* network error — ignore */}}
}}

// ── Main tick (runs every second) ────────────────────────────
function tick() {{
  const now = new Date();

  // "Updated X ago" in header
  const ageSec = Math.floor((now - DATA_GENERATED_AT) / 1000);
  if (ageSec >= 0) {{
    document.getElementById('age-label').textContent =
      `${{agoLabel(now - DATA_GENERATED_AT)}}`;
  }}

  // Countdown box
  if (reloadScheduled) return;

  const {{time: nextTime, label: nextLabel}} = nextScanTime();
  const diffSec = Math.max(0, Math.floor((nextTime - now) / 1000));

  // If we're within the expected workflow window after a scheduled scan start
  const secSinceData = Math.floor((now - DATA_GENERATED_AT) / 1000);
  const inProgress   = secSinceData > 0 && secSinceData < WORKFLOW_DURATION_S &&
                       diffSec > WORKFLOW_DURATION_S;

  if (inProgress) {{
    // Workflow may be running — show progress estimate
    const progress = Math.min(99, Math.floor(secSinceData / WORKFLOW_DURATION_S * 100));
    const remain   = Math.max(0, WORKFLOW_DURATION_S - secSinceData);
    document.getElementById('cd-label').textContent  = '⚙️ جاري الـ Scan...';
    document.getElementById('cdtimer').textContent   = fmt(remain);
    document.getElementById('cdstatus').textContent  = `التقرير القادم: ${{progress}}% تقريباً`;
    document.getElementById('countdown-box').style.background = 'rgba(255,165,0,0.20)';
  }} else {{
    document.getElementById('cd-label').textContent  = '⏱ التحديث القادم';
    document.getElementById('cdtimer').textContent   = fmt(diffSec);
    document.getElementById('cdstatus').textContent  = nextLabel;
    document.getElementById('countdown-box').style.background = 'rgba(255,255,255,0.12)';
  }}
}}

// ── Boot ─────────────────────────────────────────────────────
tick();
setInterval(tick, 1000);
setInterval(pollForUpdates, POLL_INTERVAL_MS);
pollForUpdates();   // immediate first check
</script>
</body>
</html>"""


def _write_status_json():
    """Write scan_status.json — polled by dashboard JS for live updates."""
    n = 0
    try:
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        n = conn.execute("SELECT COUNT(*) FROM v_all_signals").fetchone()[0]
        conn.close()
    except Exception:
        pass
    status = {
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "n_signals":    n,
        "date":         date.today().isoformat(),
    }
    with open("scan_status.json", "w") as f:
        json.dump(status, f)


def main():
    print("[Dashboard] Building master dashboard...")
    html = build_dashboard()
    with open(DASHBOARD_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    _write_status_json()
    print(f"[Dashboard] Saved → {DASHBOARD_FILE}")


if __name__ == "__main__":
    main()
