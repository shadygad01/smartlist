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


# ── Main Builder ──────────────────────────────────────────────────────────────

def build_dashboard() -> str:
    bt  = _load(BACKTEST_JSON)
    rr  = _load(RESEARCH_JSON)
    ed  = _load(EDGE_JSON)
    beh = _load_behavior_kpis()

    now = datetime.now().strftime("%A, %d %B %Y — %H:%M Cairo")

    nav_links = " &nbsp;|&nbsp; ".join([
        '<a href="heatmap.html" style="color:#8fb8d8;text-decoration:none;">🗺️ Heatmap</a>',
        '<a href="backtest_report.html" style="color:#8fb8d8;text-decoration:none;">📊 Backtest</a>',
        '<a href="research_report.html" style="color:#8fb8d8;text-decoration:none;">🔬 Research</a>',
        '<a href="edge_report.html" style="color:#8fb8d8;text-decoration:none;">🧠 Edge</a>',
        '<a href="behavior_report.html" style="color:#8fb8d8;text-decoration:none;">🔍 Behavior</a>',
    ])

    body = f"""
{_section_backtest(bt)}
{_section_behavior(beh)}
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

let reloading = false;
function tick() {{
  if (reloading) return;
  const {{ time, label }} = nextScanTime();
  const diffMs = time - new Date();
  const diffSec = Math.max(0, Math.floor(diffMs / 1000));

  document.getElementById('cdtimer').textContent = fmt(diffSec);
  document.getElementById('cdstatus').textContent = label;

  if (diffSec <= 0) {{
    reloading = true;
    document.getElementById('cdtimer').textContent = '⏳';
    document.getElementById('cdstatus').textContent = 'جاري تحميل التحديث...';
    // Wait 3 min after scheduled time for workflow + Pages deploy
    setTimeout(() => location.reload(true), 3 * 60 * 1000);
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
