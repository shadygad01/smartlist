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
    """Read KPIs directly from egx_research.db."""
    if not Path(DB_PATH).exists():
        return {}
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute("""
            SELECT b.r20d, b.mfe_20d, b.mae_20d, s.raw_score,
                   s.r3_liquidity, s.r8_demand, s.is_ramadan
            FROM signals s
            JOIN bottom_quality b ON b.signal_id = s.id
            WHERE b.r20d IS NOT NULL
        """).fetchall()
        conn.close()
    except Exception:
        return {}

    if not rows:
        return {}

    r20ds  = [r[0] for r in rows]
    mfes   = [r[1] for r in rows if r[1] is not None]
    maes   = [r[2] for r in rows if r[2] is not None]
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

    total_signals = 639  # baseline signal count

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
    for r in (ed.get("top_rules", []) or [])[:4]:
        cond = r.get("rule_text", r.get("condition", ""))
        mfe  = r.get("mfe_mean", 0)
        wr   = r.get("win_rate", 0)
        n_   = r.get("n", 0)
        exp  = r.get("expectancy", 0)

        notes.append({
            "source":    "🧠 Edge",
            "priority":  "HIGH" if mfe > 25 else "MEDIUM",
            "text":      f"<b>{str(cond)[:80]}</b>",
            "color":     "#6f42c1",
            "conf":      _conf_str(n=n_),
            "delta_ret": (f"<span style='color:#155724;font-weight:700'>MFE {mfe:+.1f}%</span>"
                          if mfe else "<span style='color:#aaa'>—</span>"),
            "delta_n":   (f"<span style='color:#1a3c5e;font-weight:700'>{n_} إشارة</span>"
                          if n_ else "<span style='color:#aaa'>—</span>"),
        })

    # ── 🔬 Research Report (weight suggestions + RF importance) ─────────────────
    rr = _load("research_results.json")
    ws = rr.get("weight_suggestions", {})
    for feat, info in list(ws.items())[:4]:
        if not isinstance(info, dict):
            continue
        direction = info.get("direction", "")
        w_change  = info.get("change")
        reason    = info.get("reason", "")
        imp_m     = re.search(r'avg_importance=(\d+\.\d+)', reason)
        imp       = float(imp_m.group(1)) if imp_m else None
        if not direction:
            continue
        notes.append({
            "source":    "🔬 Research",
            "priority":  "MEDIUM",
            "text":      (f"<b>{feat}</b>: وزن {w_change:+d} (حالي→مقترح)"
                          if w_change is not None else f"<b>{feat}</b>: {direction[:60]}"),
            "color":     "#856404",
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
                "source":    "📐 Quant · RF",
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
  مرتبة من الأعلى أولوية · <b>Baseline:</b> {total_signals} إشارة · avg r20d=+4.6%
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


# ── Main Builder ──────────────────────────────────────────────────────────────

def build_dashboard() -> str:
    bt  = _load(BACKTEST_JSON)
    rr  = _load(RESEARCH_JSON)
    ed  = _load(EDGE_JSON)
    beh = _load_behavior_kpis()

    now = datetime.now().strftime("%A, %d %B %Y — %H:%M:%S Cairo")

    nav_links = " &nbsp;|&nbsp; ".join([
        '<a href="heatmap.html" style="color:#8fb8d8;text-decoration:none;">🗺️ Heatmap</a>',
        '<a href="backtest_report.html" style="color:#8fb8d8;text-decoration:none;">📊 Backtest</a>',
        '<a href="research_report.html" style="color:#8fb8d8;text-decoration:none;">🔬 Research</a>',
        '<a href="quant_research_report.html" style="color:#8fb8d8;text-decoration:none;">📐 Quant</a>',
        '<a href="weight_optimizer_report.html" style="color:#8fb8d8;text-decoration:none;">⚖️ Optimizer</a>',
        '<a href="logic_analysis_report.html" style="color:#8fb8d8;text-decoration:none;">🔬 Logic</a>',
        '<a href="edge_report.html" style="color:#8fb8d8;text-decoration:none;">🧠 Edge</a>',
        '<a href="system_audit_report.html" style="color:#8fb8d8;text-decoration:none;">🕵️ Audit</a>',
        '<a href="behavior_report.html" style="color:#8fb8d8;text-decoration:none;">🔍 Behavior</a>',
        '<a href="adaptive_learning_report.html" style="color:#8fb8d8;text-decoration:none;">🧬 Adaptive</a>',
    ])

    body = f"""
{_section_research_notes()}
{_section_backtest(bt)}
{_section_behavior(beh)}
{_section_quant()}
{_section_weight_optimizer()}
{_section_logic_analyzer()}
{_section_system_audit()}
{_section_adaptive_learning()}
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
  <div class="sub">آخر تحديث: {now}</div>
  <div class="nav">{nav_links}</div>
  <div id="countdown-box">
    <div class="label">⏱ التحديث القادم</div>
    <div class="timer" id="cdtimer">--:--:--</div>
    <div class="status" id="cdstatus">جاري الحساب...</div>
  </div>
</div>
<div class="container">
{body}
</div>
<div class="footer">EGX30 Self-Learning Scanner &nbsp;·&nbsp; البيانات تُحدَّث مع كل scan يومي</div>

<script>
// ── EGX Scan Schedule (Cairo time = UTC+3 in summer / UTC+2 in winter) ───────
// Market scans: every 5 min, Sun-Thu 10:00-14:30 Cairo
// Daily report: Sun-Thu 07:00 Cairo
// We approximate Cairo = UTC+2 (conservative, works year-round)
const CAIRO_OFFSET = 2; // hours ahead of UTC

function cairoNow() {{
  const now = new Date();
  return new Date(now.getTime() + CAIRO_OFFSET * 3600000);
}}

function nextScanTime() {{
  const now = cairoNow();
  const dow = now.getUTCDay(); // 0=Sun,1=Mon,...,6=Sat
  const h   = now.getUTCHours();
  const m   = now.getUTCMinutes();
  const totalMin = h * 60 + m;

  const isWeekday = dow >= 0 && dow <= 4; // Sun-Thu

  // Helper: next occurrence of (target weekday + hour + min) in UTC+CAIRO_OFFSET
  function nextOccurrence(targetH, targetM, anyWeekday) {{
    const candidate = new Date(now);
    candidate.setUTCHours(targetH - CAIRO_OFFSET, targetM, 0, 0);
    if (candidate <= now || (!anyWeekday && !isWeekday)) {{
      candidate.setUTCDate(candidate.getUTCDate() + 1);
    }}
    // Advance past weekend if needed
    while (candidate.getUTCDay() > 4) {{
      candidate.setUTCDate(candidate.getUTCDate() + 1);
    }}
    return candidate;
  }}

  if (isWeekday) {{
    // During market scan window (10:00-14:30 Cairo)
    if (totalMin >= 600 && totalMin < 870) {{
      // Next 5-min mark
      const nextMin = Math.ceil((totalMin + 1) / 5) * 5;
      const t = new Date(now);
      t.setUTCHours(Math.floor(nextMin / 60) - CAIRO_OFFSET, nextMin % 60, 0, 0);
      if (t > now) return {{ time: t, label: "Scan السوق (كل 5 دقائق)" }};
    }}
    // After 14:30, next is daily report at 07:00 tomorrow
    if (totalMin >= 870) {{
      return {{ time: nextOccurrence(7, 0, false), label: "التقرير اليومي 07:00" }};
    }}
    // Before 10:00 today
    if (totalMin < 420) {{
      // Is it before 07:00 daily?
      const daily = new Date(now);
      daily.setUTCHours(7 - CAIRO_OFFSET, 0, 0, 0);
      if (daily > now) return {{ time: daily, label: "التقرير اليومي 07:00" }};
    }}
    // Between 07:00 and 10:00 → next is market open at 10:00
    const market = new Date(now);
    market.setUTCHours(10 - CAIRO_OFFSET, 0, 0, 0);
    if (market > now) return {{ time: market, label: "بداية scan السوق 10:00" }};
  }}

  // Weekend or fallback → next Sunday 07:00
  return {{ time: nextOccurrence(7, 0, false), label: "التقرير اليومي" }};
}}

function fmt(sec) {{
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  return String(h).padStart(2,'0') + ':' +
         String(m).padStart(2,'0') + ':' +
         String(s).padStart(2,'0');
}}

// Workflow takes ~10 min to run + 2 min Pages deploy
const WORKFLOW_DURATION_SEC = 12 * 60;

let scheduledTime = null;
let phase = 'countdown'; // 'countdown' | 'generating' | 'reloading'

function tick() {{
  const now_ = new Date();
  const next = nextScanTime();

  if (phase === 'countdown') {{
    if (!scheduledTime) scheduledTime = next.time;
    const diffMs  = scheduledTime - now_;
    const diffSec = Math.max(0, Math.floor(diffMs / 1000));

    document.getElementById('cdtimer').textContent = fmt(diffSec);
    document.getElementById('cdstatus').textContent = next.label;

    if (diffSec <= 0) {{
      phase = 'generating';
      scheduledTime = now_; // mark start of generating phase
    }}
  }} else if (phase === 'generating') {{
    const elapsedSec = Math.floor((now_ - scheduledTime) / 1000);
    const remainSec  = Math.max(0, WORKFLOW_DURATION_SEC - elapsedSec);
    const progress   = Math.min(100, Math.floor(elapsedSec / WORKFLOW_DURATION_SEC * 100));

    document.getElementById('cdtimer').textContent = fmt(remainSec);
    document.getElementById('cdstatus').textContent =
      `⚙️ جاري توليد التقرير... ${{progress}}%`;

    // Pulse the box orange during generation
    document.getElementById('countdown-box').style.background = 'rgba(255,165,0,0.25)';

    if (remainSec <= 0) {{
      phase = 'reloading';
      document.getElementById('cdtimer').textContent = '🔄';
      document.getElementById('cdstatus').textContent = 'جاري تحميل التحديث...';
      setTimeout(() => location.reload(true), 5000);
    }}
  }}
}}

tick();
setInterval(tick, 1000);
</script>
</body>
</html>"""


def main():
    print("[Dashboard] Building master dashboard...")
    html = build_dashboard()
    with open(DASHBOARD_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[Dashboard] Saved → {DASHBOARD_FILE}")


if __name__ == "__main__":
    main()
