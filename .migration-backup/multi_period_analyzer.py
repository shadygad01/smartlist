"""
Multi-period performance analysis: 20d, 90d, 120d, 180d, 252d.
Uses hist_signals table (r_90d, r_120d, r_180d, r_252d already populated).
Output: reports/multi_period_report_{date}.html
"""

import sqlite3
import json
from datetime import date
from pathlib import Path
from signal_db import DB_PATH, get_conn

REPORTS_DIR = Path("reports")
REPORTS_DIR.mkdir(exist_ok=True)
TODAY = date.today().isoformat()

INDICATORS = {
    "r1_price":     {"name": "Price Position",    "max": 30},
    "r2_ob":        {"name": "OB Quality",         "max": 10},
    "r3_liquidity": {"name": "Liquidity Context",  "max": 20},
    "r4_htf":       {"name": "HTF Alignment",      "max": 10},
    "r5_avwap":     {"name": "AVWAP Support",      "max": 8},
    "r6_macd":      {"name": "MACD Signal",        "max": 4},
    "r7_div":       {"name": "Divergence",         "max": 3},
    "r8_demand":    {"name": "Demand Zone",        "max": 15},
}

PERIODS = [
    ("20d",   "r20d",   "bq_gain"),
    ("90d",   "r_90d",  "mfe_90d"),
    ("120d",  "r_120d", "mfe_120d"),
    ("180d",  "r_180d", "mfe_180d"),
    ("252d",  "r_252d", "mfe_252d"),
]

PERIOD_LABELS = [p[0] for p in PERIODS]
PERIOD_COLS   = [p[1] for p in PERIODS]
MFE_COLS      = [p[2] for p in PERIODS]


def _bucket(value, max_val):
    """Return 'High', 'Mid', or 'Low' bucket."""
    if value is None:
        return None
    pct = value / max_val
    if pct >= 0.75:
        return "High"
    if pct >= 0.4:
        return "Mid"
    return "Low"


def _safe_pct(v):
    return round(v * 100, 1) if v is not None else None


def analyze_indicators(conn):
    """For each indicator, compute avg return & win-rate per bucket per period."""
    results = {}
    for col, meta in INDICATORS.items():
        buckets = {}
        for label in ("High", "Mid", "Low"):
            row_data = {"n": [], "avg_ret": [], "win_rate": [], "avg_mfe": []}
            for (period_label, ret_col, mfe_col) in PERIODS:
                # filter rows with data
                if ret_col == "r20d":
                    # r20d is in hist_signals directly
                    rows = conn.execute(f"""
                        SELECT {col}, {ret_col},
                               COALESCE({mfe_col}, 0)
                        FROM hist_signals
                        WHERE {col} IS NOT NULL AND {ret_col} IS NOT NULL
                    """).fetchall()
                else:
                    rows = conn.execute(f"""
                        SELECT {col}, {ret_col},
                               COALESCE({mfe_col}, 0)
                        FROM hist_signals
                        WHERE {col} IS NOT NULL AND {ret_col} IS NOT NULL
                    """).fetchall()

                filtered = [
                    (r[1], r[2]) for r in rows
                    if _bucket(r[0], meta["max"]) == label
                ]
                if not filtered:
                    row_data["n"].append(0)
                    row_data["avg_ret"].append(None)
                    row_data["win_rate"].append(None)
                    row_data["avg_mfe"].append(None)
                    continue

                rets = [r[0] for r in filtered]
                mfes = [r[1] for r in filtered]
                n = len(rets)
                avg_ret = sum(rets) / n
                win_rate = sum(1 for r in rets if r > 0.03) / n
                avg_mfe = sum(mfes) / n if mfes else 0

                row_data["n"].append(n)
                row_data["avg_ret"].append(_safe_pct(avg_ret))
                row_data["win_rate"].append(round(win_rate * 100, 1))
                row_data["avg_mfe"].append(_safe_pct(avg_mfe))

            buckets[label] = row_data
        results[col] = {"meta": meta, "buckets": buckets}
    return results


def analyze_correlations(conn):
    """Pearson-like correlation of each indicator with each period return."""
    corrs = {}
    for col in INDICATORS:
        corrs[col] = {}
        for (period_label, ret_col, _) in PERIODS:
            rows = conn.execute(f"""
                SELECT CAST({col} AS REAL), CAST({ret_col} AS REAL)
                FROM hist_signals
                WHERE {col} IS NOT NULL AND {ret_col} IS NOT NULL
            """).fetchall()
            if len(rows) < 10:
                corrs[col][period_label] = None
                continue
            xs = [r[0] for r in rows]
            ys = [r[1] for r in rows]
            n = len(xs)
            mx = sum(xs) / n
            my = sum(ys) / n
            cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / n
            sx = (sum((x - mx) ** 2 for x in xs) / n) ** 0.5
            sy = (sum((y - my) ** 2 for y in ys) / n) ** 0.5
            corr = (cov / (sx * sy)) if sx * sy > 0 else 0
            corrs[col][period_label] = round(corr, 3)
    return corrs


def analyze_total_score(conn):
    """Analyze total SMC score (raw_score) vs multi-period returns."""
    results = {}
    for (period_label, ret_col, mfe_col) in PERIODS:
        rows = conn.execute(f"""
            SELECT raw_score, {ret_col}
            FROM hist_signals
            WHERE raw_score IS NOT NULL AND {ret_col} IS NOT NULL
            ORDER BY raw_score
        """).fetchall()
        if not rows:
            results[period_label] = []
            continue
        # Split into quintiles
        n = len(rows)
        q = n // 5
        quintiles = []
        for i in range(5):
            start = i * q
            end = (i + 1) * q if i < 4 else n
            chunk = rows[start:end]
            rets = [r[1] for r in chunk]
            scores = [r[0] for r in chunk]
            quintiles.append({
                "label": f"Q{i+1}",
                "score_range": f"{min(scores):.0f}-{max(scores):.0f}",
                "n": len(chunk),
                "avg_ret": _safe_pct(sum(rets) / len(rets)),
                "win_rate": round(sum(1 for r in rets if r > 0.03) / len(rets) * 100, 1),
            })
        results[period_label] = quintiles
    return results


def analyze_combined_best(conn):
    """Find best indicator combinations (top-2) for each period."""
    # Use r7_div (divergence, often highest predictor) + other indicators
    combos = {}
    for (period_label, ret_col, _) in PERIODS:
        # Find which indicator (when at max=High) gives best avg return
        best = []
        for col, meta in INDICATORS.items():
            rows = conn.execute(f"""
                SELECT {ret_col}
                FROM hist_signals
                WHERE {col} IS NOT NULL AND {ret_col} IS NOT NULL
                  AND CAST({col} AS REAL) / {meta['max']} >= 0.75
            """).fetchall()
            if not rows:
                continue
            rets = [r[0] for r in rows]
            best.append({
                "indicator": col,
                "name": meta["name"],
                "n": len(rets),
                "avg_ret": _safe_pct(sum(rets) / len(rets)),
            })
        best.sort(key=lambda x: x["avg_ret"] or -99, reverse=True)
        combos[period_label] = best[:4]
    return combos


def analyze_classifications(conn):
    """Winner/Loser classification distribution by total score quintile."""
    rows = conn.execute("""
        SELECT raw_score, classification, r_90d, r_252d
        FROM hist_signals
        WHERE raw_score IS NOT NULL AND classification IS NOT NULL
        ORDER BY raw_score
    """).fetchall()
    if not rows:
        return {}

    # Group into High/Mid/Low score bands
    bands = {}
    for r in rows:
        score, cls, r90, r252 = r
        if score >= 70:
            band = "High (70+)"
        elif score >= 50:
            band = "Mid (50-69)"
        else:
            band = "Low (<50)"
        if band not in bands:
            bands[band] = {}
        bands[band][cls] = bands[band].get(cls, 0) + 1

    return bands


def _color(val):
    """CSS color for a return value."""
    if val is None:
        return "#666"
    if val >= 30:
        return "#00c853"
    if val >= 10:
        return "#64dd17"
    if val >= 0:
        return "#ffd600"
    return "#ff1744"


def _corr_color(val):
    if val is None:
        return "#666"
    if val >= 0.3:
        return "#00c853"
    if val >= 0.1:
        return "#64dd17"
    if val >= -0.1:
        return "#ffd600"
    return "#ff1744"


def build_html(ind_data, corr_data, score_data, combo_data, cls_data):
    period_headers = "".join(f"<th>{p}</th>" for p in PERIOD_LABELS)

    # === Indicator bucket table ===
    indicator_rows_html = ""
    for col, data in ind_data.items():
        meta = data["meta"]
        for bucket, bdata in data["buckets"].items():
            cells = ""
            for i, period in enumerate(PERIOD_LABELS):
                ret = bdata["avg_ret"][i]
                wr  = bdata["win_rate"][i]
                n   = bdata["n"][i]
                color = _color(ret)
                cells += f'<td style="color:{color}" title="n={n}, WR={wr}%">{ret if ret is not None else "—"}%<br><small>{wr if wr is not None else "—"}% WR</small></td>'
            bucket_class = bucket.lower()
            indicator_rows_html += f"""
            <tr class="bucket-{bucket_class}">
                <td><b>{meta['name']}</b></td>
                <td class="max">{meta['max']}</td>
                <td class="bucket-label">{bucket}</td>
                {cells}
            </tr>"""

    # === Correlation table ===
    corr_rows = ""
    for col, meta in INDICATORS.items():
        cells = ""
        for period in PERIOD_LABELS:
            val = corr_data.get(col, {}).get(period)
            color = _corr_color(val)
            cells += f'<td style="color:{color}">{val if val is not None else "—"}</td>'
        corr_rows += f"<tr><td><b>{meta['name']}</b></td>{cells}</tr>"

    # === Score quintiles ===
    quintile_blocks = ""
    for period, quintiles in score_data.items():
        rows_html = ""
        for q in quintiles:
            color = _color(q["avg_ret"])
            rows_html += f"""
            <tr>
                <td>{q['label']}</td>
                <td>{q['score_range']}</td>
                <td>{q['n']}</td>
                <td style="color:{color}">{q['avg_ret']}%</td>
                <td>{q['win_rate']}%</td>
            </tr>"""
        quintile_blocks += f"""
        <div class="quintile-block">
            <h4>{period} Returns by Score Quintile</h4>
            <table><tr><th>Quintile</th><th>Score</th><th>N</th><th>Avg Return</th><th>Win Rate</th></tr>
            {rows_html}</table>
        </div>"""

    # === Best indicators per period ===
    best_html = ""
    for period, items in combo_data.items():
        best_html += f"<div class='best-block'><h4>Best Indicators → {period}</h4><ol>"
        for item in items:
            color = _color(item['avg_ret'])
            best_html += f"<li><b>{item['name']}</b>: <span style='color:{color}'>{item['avg_ret']}%</span> avg ({item['n']} signals)</li>"
        best_html += "</ol></div>"

    # === Classification by score band ===
    cls_html = ""
    for band, cls_counts in cls_data.items():
        total = sum(cls_counts.values())
        cls_html += f"<div class='cls-block'><h4>{band}</h4><ul>"
        for cls, cnt in sorted(cls_counts.items(), key=lambda x: -x[1]):
            pct = round(cnt / total * 100, 1)
            cls_html += f"<li>{cls}: {cnt} ({pct}%)</li>"
        cls_html += "</ul></div>"

    return f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<title>Multi-Period Performance Analysis — {TODAY}</title>
<style>
  body {{ font-family: 'Segoe UI', sans-serif; background:#0d1117; color:#c9d1d9; margin:0; padding:20px; }}
  h1 {{ color:#58a6ff; text-align:center; }}
  h2 {{ color:#79c0ff; border-bottom:1px solid #30363d; padding-bottom:8px; margin-top:40px; }}
  h4 {{ color:#8b949e; margin:8px 0 4px; }}
  table {{ border-collapse:collapse; width:100%; margin:12px 0; font-size:13px; }}
  th {{ background:#161b22; color:#8b949e; padding:8px 10px; text-align:center; border:1px solid #30363d; }}
  td {{ padding:6px 10px; border:1px solid #30363d; text-align:center; vertical-align:top; }}
  td small {{ font-size:10px; color:#8b949e; }}
  .bucket-high {{ background:#0d2318; }}
  .bucket-mid  {{ background:#0d1b0d; }}
  .bucket-low  {{ background:#1a0d0d; }}
  .bucket-label {{ font-weight:bold; }}
  .max {{ color:#8b949e; }}
  .grid {{ display:flex; flex-wrap:wrap; gap:16px; }}
  .quintile-block, .best-block, .cls-block {{
    background:#161b22; border:1px solid #30363d; border-radius:8px;
    padding:16px; flex:1; min-width:280px;
  }}
  .stat {{ background:#161b22; border-radius:6px; padding:12px; text-align:center; }}
  .stat .val {{ font-size:2em; color:#58a6ff; font-weight:bold; }}
  .stat .lbl {{ font-size:12px; color:#8b949e; }}
  .summary-grid {{ display:flex; gap:12px; flex-wrap:wrap; margin:20px 0; }}
</style>
</head>
<body>
<h1>📊 Multi-Period Performance Analysis</h1>
<p style="text-align:center;color:#8b949e;">Generated: {TODAY} | Periods: 20d → 252d (1Y)</p>

<h2>Average Returns by Indicator Strength</h2>
<p style="color:#8b949e;">High = top 75% of max score | Mid = 40-74% | Low = below 40%</p>
<table>
  <tr><th>Indicator</th><th>Max</th><th>Bucket</th>{period_headers}</tr>
  {indicator_rows_html}
</table>

<h2>Indicator Correlation with Period Returns</h2>
<p style="color:#8b949e;">Positive = higher indicator score → higher return | Values above 0.20 are significant</p>
<table>
  <tr><th>Indicator</th>{period_headers}</tr>
  {corr_rows}
</table>

<h2>Total Score vs Returns (Quintile Analysis)</h2>
<div class="grid">
{quintile_blocks}
</div>

<h2>Best Performing Indicators per Horizon</h2>
<p style="color:#8b949e;">Based on signals where the indicator score is in its highest bucket (≥75% of max)</p>
<div class="grid">
{best_html}
</div>

<h2>Signal Classification by Score Band</h2>
<div class="grid">
{cls_html}
</div>

<p style="color:#30363d;text-align:center;margin-top:40px;">EGX Scanner · Multi-Period Analyzer · {TODAY}</p>
</body>
</html>"""


def run():
    conn = get_conn(DB_PATH)
    print("Analyzing indicator performance across periods...")
    ind_data  = analyze_indicators(conn)
    print("Computing correlations...")
    corr_data = analyze_correlations(conn)
    print("Analyzing score quintiles...")
    score_data = analyze_total_score(conn)
    print("Finding best indicators per period...")
    combo_data = analyze_combined_best(conn)
    print("Analyzing classifications...")
    cls_data = analyze_classifications(conn)
    conn.close()

    html = build_html(ind_data, corr_data, score_data, combo_data, cls_data)
    out = REPORTS_DIR / f"multi_period_report_{TODAY}.html"
    out.write_text(html, encoding="utf-8")
    print(f"[multi_period_analyzer] Report saved → {out}")
    return str(out)


if __name__ == "__main__":
    run()
