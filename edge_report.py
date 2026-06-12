"""
Edge Discovery Report Generator
=================================
Generates the EDGE DISCOVERY REPORT HTML from rule_discovery results.

Usage:
    python edge_report.py                     # reads edge_discovery_results.json
    python edge_report.py --json=custom.json  # custom JSON path
    python edge_report.py --out=./web_deploy  # custom output directory
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path

from rule_discovery import EDGE_JSON_PATH, run_rule_discovery, DB_PATH

# ─────────────────────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────────────────────

_CSS = """
<style>
  :root {
    --dark:   #0d1117;
    --panel:  #161b22;
    --border: #30363d;
    --accent: #f0883e;
    --green:  #3fb950;
    --red:    #f85149;
    --blue:   #58a6ff;
    --purple: #d2a8ff;
    --text:   #e6edf3;
    --muted:  #8b949e;
  }
  * { box-sizing: border-box; }
  body {
    background: var(--dark);
    color: var(--text);
    font-family: 'Segoe UI', system-ui, sans-serif;
    margin: 0;
    direction: ltr;
  }
  .container { max-width: 1100px; margin: 0 auto; padding: 0 16px 60px; }

  /* Header */
  .top-bar {
    background: linear-gradient(135deg, #161b22, #0d1117);
    border-bottom: 1px solid var(--border);
    padding: 24px 32px;
  }
  .top-bar .badge {
    display: inline-block;
    background: var(--accent);
    color: #000;
    font-size: .72em;
    font-weight: 800;
    letter-spacing: .06em;
    padding: 3px 10px;
    border-radius: 20px;
    margin-bottom: 8px;
  }
  .top-bar h1 { margin: 6px 0 4px; font-size: 2em; color: var(--text); }
  .top-bar p  { margin: 0; color: var(--muted); font-size: .9em; }

  /* Sections */
  .section { margin-top: 28px; }
  .section-title {
    font-size: 1.05em;
    font-weight: 700;
    color: var(--accent);
    text-transform: uppercase;
    letter-spacing: .08em;
    border-left: 3px solid var(--accent);
    padding-left: 12px;
    margin-bottom: 14px;
  }

  /* KPI cards */
  .kpi-row   { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 6px; }
  .kpi       {
    flex: 1; min-width: 140px;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px 18px;
    text-align: center;
  }
  .kpi .val  { font-size: 2em; font-weight: 700; }
  .kpi .lbl  { font-size: .75em; color: var(--muted); margin-top: 4px; }
  .kpi.green .val { color: var(--green);  }
  .kpi.red   .val { color: var(--red);    }
  .kpi.blue  .val { color: var(--blue);   }
  .kpi.amber .val { color: var(--accent); }

  /* Tables */
  .tbl-wrap { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; font-size: .85em; }
  th {
    background: var(--panel);
    color: var(--muted);
    padding: 9px 12px;
    text-align: left;
    border-bottom: 1px solid var(--border);
    white-space: nowrap;
    font-weight: 600;
    font-size: .80em;
    text-transform: uppercase;
    letter-spacing: .04em;
  }
  td { padding: 9px 12px; border-bottom: 1px solid #21262d; vertical-align: top; }
  tr:hover td { background: #1c2128; }

  /* Source badges */
  .src { display:inline-block; padding:2px 7px; border-radius:12px;
         font-size:.72em; font-weight:700; }
  .src-dt      { background:#1f3a5f; color:#58a6ff; }
  .src-rulefit { background:#3a2a5f; color:#d2a8ff; }
  .src-assoc   { background:#1a4a2a; color:#3fb950; }
  .src-bayes   { background:#4a2a1a; color:#f0883e; }

  /* Value pills */
  .pill-green  { color: var(--green);  font-weight: 600; }
  .pill-red    { color: var(--red);    font-weight: 600; }
  .pill-amber  { color: var(--accent); font-weight: 600; }
  .pill-blue   { color: var(--blue);   font-weight: 600; }

  /* Rule text */
  .rule-text { font-family: monospace; font-size: .82em;
               color: #e6edf3; line-height: 1.5; }
  .rule-text span { color: var(--accent); font-weight: 700; }

  /* DNA bars */
  .dna-bar-wrap { width: 160px; display: inline-block; vertical-align: middle; }
  .dna-bar-bg   { background: #21262d; border-radius: 4px; height: 8px; width: 100%; }
  .dna-bar-fill { height: 8px; border-radius: 4px; }

  /* Rank badge */
  .rank { display:inline-flex; align-items:center; justify-content:center;
          width:28px; height:28px; border-radius:50%;
          font-weight:700; font-size:.85em; flex-shrink:0; }
  .rank-1  { background:#f0883e; color:#000; }
  .rank-2  { background:#c0c0c0; color:#000; }
  .rank-3  { background:#cd7f32; color:#000; }
  .rank-n  { background:#21262d; color:var(--muted); }

  /* Per-stock accordion */
  details { border: 1px solid var(--border); border-radius: 8px;
            margin-bottom: 8px; }
  details > summary {
    padding: 12px 16px;
    cursor: pointer;
    font-weight: 600;
    list-style: none;
    display: flex;
    align-items: center;
    gap: 10px;
    background: var(--panel);
    border-radius: 8px;
  }
  details[open] > summary { border-radius: 8px 8px 0 0; }
  details > div { padding: 16px; }

  /* Info box */
  .info-box {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px 20px;
    color: var(--muted);
    font-size: .88em;
    margin-bottom: 18px;
  }
  .info-box strong { color: var(--text); }

  /* Significance star */
  .sig-yes { color: var(--green); }
  .sig-no  { color: var(--red);   }

  /* Scrollable code */
  pre {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 14px;
    font-size: .82em;
    overflow-x: auto;
    color: var(--text);
  }
</style>
"""


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _pct(v, digits=1, pos_sign=True) -> str:
    if v is None:
        return "<span style='color:#555'>—</span>"
    sign = "+" if v > 0 and pos_sign else ""
    return f"{sign}{v:.{digits}f}%"


def _src_badge(src: str) -> str:
    cls = {
        "dt": "src-dt", "rulefit": "src-rulefit",
        "assoc": "src-assoc", "bayes": "src-bayes",
    }.get(src, "src-dt")
    label = {"dt": "DT", "rulefit": "RuleFit",
             "assoc": "Assoc", "bayes": "Bayes"}.get(src, src)
    return f'<span class="src {cls}">{label}</span>'


def _mfe_color(v) -> str:
    if v is None:
        return "pill-blue"
    if v >= 15:
        return "pill-green"
    if v >= 8:
        return "pill-amber"
    return "pill-red"


def _wr_color(v) -> str:
    if v is None:
        return "pill-blue"
    pct = v * 100
    if pct >= 70:
        return "pill-green"
    if pct >= 50:
        return "pill-amber"
    return "pill-red"


def _rule_html(rule_text: str) -> str:
    parts = rule_text.split("  AND  ")
    lines = []
    for i, p in enumerate(parts):
        sep = '<span style="color:#8b949e"> AND </span>' if i > 0 else ""
        lines.append(f'{sep}<span>{p.strip()}</span>')
    return '<div class="rule-text">' + "<br>".join(lines) + "</div>"


def _rank_badge(i: int) -> str:
    cls = {1: "rank-1", 2: "rank-2", 3: "rank-3"}.get(i, "rank-n")
    return f'<span class="rank {cls}">{i}</span>'


# ─────────────────────────────────────────────────────────────────────────────
# Section builders
# ─────────────────────────────────────────────────────────────────────────────

def _build_header(res: dict) -> str:
    gen_date = res.get("date", date.today().isoformat())
    n_sig    = res.get("n_signals", 0)
    n_feat   = res.get("n_features", 0)
    n_rules  = res.get("total_rules_significant", 0)
    return f"""
<div class="top-bar">
  <div class="container">
    <div class="badge">ALPHA RESEARCH</div>
    <h1>⚡ Edge Discovery Report</h1>
    <p>
      {gen_date} &nbsp;·&nbsp;
      {n_sig} signals &nbsp;·&nbsp;
      {n_feat} features &nbsp;·&nbsp;
      {n_rules} significant rules discovered
    </p>
  </div>
</div>"""


def _build_kpis(res: dict) -> str:
    wr    = res.get("global_win_rate", 0) * 100
    mfe   = res.get("global_mfe_mean", 0)
    mae   = res.get("global_mae_mean", 0)
    bq    = res.get("global_bq_mean", 0)
    n_fp  = len(res.get("top_fingerprints", []))
    n_rules = res.get("total_rules_significant", 0)
    top_rule = res.get("top_fingerprints", [{}])[0] if res.get("top_fingerprints") else {}
    top_mfe = top_rule.get("mfe_mean", 0)
    sc = res.get("source_counts", {})
    return f"""
<div class="section">
  <div class="section-title">Overview</div>
  <div class="kpi-row">
    <div class="kpi blue"><div class="val">{res.get('n_signals',0)}</div><div class="lbl">Total Signals</div></div>
    <div class="kpi amber"><div class="val">{n_rules}</div><div class="lbl">Significant Rules</div></div>
    <div class="kpi green"><div class="val">{n_fp}</div><div class="lbl">Top Fingerprints</div></div>
    <div class="kpi green"><div class="val">{mfe:+.1f}%</div><div class="lbl">Avg MFE (Global)</div></div>
    <div class="kpi amber"><div class="val">{wr:.0f}%</div><div class="lbl">Win Rate (≥8%)</div></div>
    <div class="kpi blue"><div class="val">{bq:.0f}</div><div class="lbl">Avg BQ Score</div></div>
    <div class="kpi green"><div class="val">{top_mfe:+.1f}%</div><div class="lbl">Best Rule MFE</div></div>
  </div>
  <div class="info-box" style="margin-top:12px">
    <strong>Purpose:</strong> Not prediction — discovering repeatable market edges hidden in historical signals.
    &nbsp;|&nbsp; Methods: <strong>DT ({sc.get('dt',0)})</strong>
    · <strong>RuleFit ({sc.get('rulefit',0)})</strong>
    · <strong>Assoc ({sc.get('assoc',0)})</strong>
    · <strong>Bayes ({sc.get('bayes',0)})</strong>
    &nbsp;|&nbsp; Filters: n≥15 · p≤0.10
  </div>
</div>"""


def _rules_table(rules: list[dict], limit: int = 50, show_rank: bool = False) -> str:
    if not rules:
        return '<p style="color:var(--muted);font-style:italic">No qualifying rules found.</p>'
    rows = ""
    for i, r in enumerate(rules[:limit], 1):
        rank_cell = f"<td>{_rank_badge(i)}</td>" if show_rank else ""
        mfe_v  = r.get("mfe_mean")
        mae_v  = r.get("mae_mean")
        wr_v   = r.get("win_rate")
        exp_v  = r.get("expectancy")
        bq_v   = r.get("bq_mean")
        p_v    = r.get("p_value")
        n_v    = r.get("n")
        sig    = r.get("significant", False)
        sig_marker = '<span class="sig-yes">✓</span>' if sig else '<span class="sig-no">✗</span>'

        mfe_cls = _mfe_color(mfe_v)
        wr_cls  = _wr_color(wr_v)

        rows += f"""
<tr>
  {rank_cell}
  <td style="min-width:320px">{_rule_html(r.get('rule_text',''))}</td>
  <td><span class="{mfe_cls}">{_pct(mfe_v)}</span></td>
  <td><span class="{wr_cls}">{(wr_v*100):.0f}%</span></td>
  <td><span class="{'pill-green' if (exp_v or 0)>0 else 'pill-red'}">{_pct(exp_v)}</span></td>
  <td style="color:var(--muted)">{_pct(mae_v)}</td>
  <td style="color:var(--muted)">{bq_v:.0f}</td>
  <td><strong>{n_v}</strong></td>
  <td style="color:var(--muted);font-size:.8em">{p_v:.3f}&nbsp;{sig_marker}</td>
  <td>{_src_badge(r.get('source',''))}</td>
</tr>"""

    rank_th = "<th>#</th>" if show_rank else ""
    return f"""
<div class="tbl-wrap">
<table>
<thead><tr>
  {rank_th}
  <th>Rule (IF … THEN)</th>
  <th>Avg MFE</th><th>Win Rate</th><th>Expectancy</th>
  <th>Avg MAE</th><th>BQ</th><th>N</th>
  <th>p-value</th><th>Source</th>
</tr></thead>
<tbody>{rows}</tbody>
</table>
</div>"""


def _build_top_fingerprints(res: dict) -> str:
    fps = res.get("top_fingerprints", [])
    if not fps:
        return ""
    return f"""
<div class="section">
  <div class="section-title">🏆 Top {len(fps)} Profitable Bottom Fingerprints</div>
  <p style="color:var(--muted);font-size:.88em;margin-top:-6px;margin-bottom:14px">
    Ranked by expectancy — minimum {res.get('n_signals',0)//14}+ trades, p≤0.10
  </p>
  {_rules_table(fps, limit=20, show_rank=True)}
</div>"""


def _build_global_rules(res: dict) -> str:
    all_rules  = res.get("significant_rules", [])
    by_source: dict[str, list] = {}
    for r in all_rules:
        src = r.get("source", "dt")
        by_source.setdefault(src, []).append(r)

    source_meta = [
        ("dt",      "Decision Tree Rules",   "Path extraction from depth-limited trees"),
        ("rulefit", "RuleFit Rules",          "Friedman-Popescu: linear combination of tree rules"),
        ("assoc",   "Association Rules",      "Apriori algorithm on discretized features"),
        ("bayes",   "Bayesian Rule Learning", "Sequential covering with posterior maximization"),
    ]
    html = '<div class="section"><div class="section-title">📐 Global Rule Sets by Method</div>'
    for src, title, desc in source_meta:
        rules = by_source.get(src, [])
        count = len(rules)
        color = {"dt": "#58a6ff", "rulefit": "#d2a8ff",
                 "assoc": "#3fb950", "bayes": "#f0883e"}.get(src, "#888")
        html += f"""
<details>
<summary>
  {_src_badge(src)}
  <span style="flex:1">{title}</span>
  <span style="color:{color};font-weight:700">{count} rules</span>
  <span style="color:var(--muted);font-size:.8em;margin-left:8px">— {desc}</span>
</summary>
<div>{_rules_table(rules, limit=30)}</div>
</details>"""
    html += "</div>"
    return html


def _build_per_stock(res: dict) -> str:
    ps = res.get("per_stock_rules", {})
    qualifying = {s: r for s, r in ps.items() if r}
    if not qualifying:
        return f"""
<div class="section">
  <div class="section-title">📊 Per-Stock Rules</div>
  <div class="info-box">
    No stock has ≥{res.get('n_signals',209)//14} signals with significant rules.
    Per-stock rules require at least 15 qualifying samples per symbol.
  </div>
</div>"""

    html = f'<div class="section"><div class="section-title">📊 Per-Stock Rules ({len(qualifying)} stocks)</div>'
    for symbol, rules in sorted(qualifying.items(),
                                 key=lambda x: (x[1][0].get("mfe_mean", 0)
                                                if x[1] else 0), reverse=True):
        top_mfe  = rules[0].get("mfe_mean", 0) if rules else 0
        n_rules  = len(rules)
        html += f"""
<details>
<summary>
  <span style="font-family:monospace;color:var(--blue)">{symbol}</span>
  <span style="flex:1"></span>
  <span style="color:var(--green)">{n_rules} rules</span>
  <span style="color:var(--muted);font-size:.82em;margin-left:8px">
    best MFE {top_mfe:+.1f}%
  </span>
</summary>
<div>{_rules_table(rules, limit=10)}</div>
</details>"""
    html += "</div>"
    return html


def _build_bottom_dna(res: dict) -> str:
    dna = res.get("bottom_dna", {})
    if not dna:
        return ""

    top = dna.get("top_10_pct", {})
    bot = dna.get("bot_10_pct", {})
    feats = dna.get("features", {})
    ranges = dna.get("high_return_ranges", {})

    # Sort features by |top_vs_bot|, significant first
    sorted_feats = sorted(
        feats.items(),
        key=lambda x: (int(x[1].get("significant", False)),
                       abs(x[1].get("top_vs_bot", 0))),
        reverse=True,
    )

    # ── Summary cards
    html = f"""
<div class="section">
  <div class="section-title">🧬 Bottom DNA Report</div>
  <div class="kpi-row">
    <div class="kpi green">
      <div class="val">{top.get('mfe_mean',0):+.1f}%</div>
      <div class="lbl">Top 10% avg MFE<br>(n={top.get('n',0)})</div>
    </div>
    <div class="kpi red">
      <div class="val">{bot.get('mfe_mean',0):+.1f}%</div>
      <div class="lbl">Worst 10% avg MFE<br>(n={bot.get('n',0)})</div>
    </div>
    <div class="kpi blue">
      <div class="val">{top.get('bq_mean',0):.0f}</div>
      <div class="lbl">Top 10% BQ score</div>
    </div>
    <div class="kpi red">
      <div class="val">{bot.get('bq_mean',0):.0f}</div>
      <div class="lbl">Worst 10% BQ score</div>
    </div>
  </div>"""

    # ── Feature comparison table
    html += """
  <div style="margin-top:18px">
  <div style="color:var(--muted);font-size:.82em;margin-bottom:10px">
    Comparing feature distributions between top 10% and worst 10% trades.
    ✓ = statistically significant (p≤0.10, Mann-Whitney U)
  </div>
  <div class="tbl-wrap">
  <table>
  <thead><tr>
    <th>Feature</th>
    <th>Top 10% Mean</th>
    <th>Worst 10% Mean</th>
    <th>Global Mean</th>
    <th>Top − Bot</th>
    <th>p-value</th>
    <th>Relative Scale</th>
  </tr></thead>
  <tbody>"""

    for col, v in sorted_feats[:40]:
        sig = v.get("significant", False)
        sig_mark = '<span class="sig-yes">✓</span>' if sig else '<span class="sig-no">·</span>'
        top_m   = v.get("top_mean", 0)
        bot_m   = v.get("bot_mean", 0)
        glob_m  = v.get("global_mean", 0)
        delta   = v.get("top_vs_bot", 0)
        p_v     = v.get("p_value", 1.0)

        # Bar: top vs bot visual
        max_delta = max(abs(delta), 0.0001)
        # Normalize bar width based on magnitude
        all_deltas = [abs(vv.get("top_vs_bot", 0)) for vv in feats.values() if vv.get("top_vs_bot")]
        global_max = max(all_deltas) if all_deltas else 1
        bar_pct = min(100, abs(delta) / global_max * 100) if global_max else 0
        bar_color = "#3fb950" if delta > 0 else "#f85149"

        delta_cls = "pill-green" if delta > 0 else "pill-red"
        html += f"""
<tr>
  <td style="font-family:monospace;font-size:.80em">{col}&nbsp;{sig_mark}</td>
  <td class="pill-green">{top_m:.4g}</td>
  <td class="pill-red">{bot_m:.4g}</td>
  <td style="color:var(--muted)">{glob_m:.4g}</td>
  <td class="{delta_cls}" style="font-weight:700">{delta:+.4g}</td>
  <td style="color:var(--muted);font-size:.8em">{p_v:.3f}</td>
  <td>
    <div class="dna-bar-wrap">
      <div class="dna-bar-bg">
        <div class="dna-bar-fill"
             style="width:{bar_pct:.0f}%;background:{bar_color}"></div>
      </div>
    </div>
  </td>
</tr>"""

    html += "</tbody></table></div></div>"

    # ── Feature ranges for high returns
    if ranges:
        sorted_ranges = sorted(
            [(k, v) for k, v in ranges.items() if k in feats and feats[k].get("significant")],
            key=lambda x: abs(feats[x[0]].get("top_vs_bot", 0)),
            reverse=True,
        )[:20]

        if sorted_ranges:
            html += """
  <div style="margin-top:24px">
  <div class="section-title" style="font-size:.9em">📍 Feature Ranges Associated with High Returns (Top 10%)</div>
  <div class="tbl-wrap">
  <table>
  <thead><tr>
    <th>Feature</th>
    <th>P25</th><th>Median</th><th>P75</th>
    <th>Top 10% Mean</th><th>vs Global</th>
  </tr></thead>
  <tbody>"""
            for col, rng in sorted_ranges:
                fv   = feats.get(col, {})
                t_m  = fv.get("top_mean", 0)
                t_vg = fv.get("top_vs_global", 0)
                html += f"""
<tr>
  <td style="font-family:monospace;font-size:.80em">{col}</td>
  <td style="color:var(--muted)">{rng['p25']:.4g}</td>
  <td style="color:var(--blue)">{rng['median']:.4g}</td>
  <td style="color:var(--muted)">{rng['p75']:.4g}</td>
  <td class="pill-green">{t_m:.4g}</td>
  <td class="{'pill-green' if t_vg>0 else 'pill-red'}">{t_vg:+.4g}</td>
</tr>"""
            html += "</tbody></table></div></div>"

    html += "</div>"
    return html


def _build_footer(res: dict) -> str:
    gen = res.get("generated_at", "")
    return f"""
<div style="text-align:center;padding:40px;color:#555;font-size:.8em;border-top:1px solid var(--border);margin-top:40px">
  Edge Discovery Report &nbsp;·&nbsp; Generated {gen[:10]} &nbsp;·&nbsp;
  {res.get('n_signals',0)} signals · {res.get('n_features',0)} features ·
  {res.get('total_rules_significant',0)} significant rules
  <br><br>
  <span style="color:#333">
    Purpose: discovering repeatable market edges — not prediction.
    Rules require n≥15 and p≤0.10.
  </span>
</div>"""


# ─────────────────────────────────────────────────────────────────────────────
# Main builder
# ─────────────────────────────────────────────────────────────────────────────

def generate_edge_report(results: dict) -> str:
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Edge Discovery Report — {results.get('date', '')}</title>
  {_CSS}
</head>
<body>
{_build_header(results)}
<div class="container">
{_build_kpis(results)}
{_build_top_fingerprints(results)}
{_build_global_rules(results)}
{_build_per_stock(results)}
{_build_bottom_dna(results)}
{_build_footer(results)}
</div>
</body>
</html>"""
    return html


def save_edge_report(results: dict, out_dir: str = ".") -> str:
    today     = results.get("date", date.today().isoformat())
    filename  = f"edge_discovery_report_{today}.html"
    out_path  = Path(out_dir) / filename
    out_path.parent.mkdir(parents=True, exist_ok=True)
    html = generate_edge_report(results)
    out_path.write_text(html, encoding="utf-8")
    print(f"[Edge Report] Saved → {out_path}  ({len(html)//1024} KB)")
    return str(out_path)


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--json",  default=EDGE_JSON_PATH)
    p.add_argument("--out",   default=".")
    p.add_argument("--force", action="store_true",
                   help="re-run discovery even if JSON exists")
    p.add_argument("--db",    default=DB_PATH)
    args = p.parse_args()

    json_path = Path(args.json)
    results: dict = {}

    if json_path.exists() and not args.force:
        with open(json_path, encoding="utf-8") as f:
            results = json.load(f)
        print(f"[Edge Report] Loaded {json_path}")
    else:
        results = run_rule_discovery(db_path=args.db)

    if not results:
        print("[Edge Report] No results — cannot generate report.")
        return

    save_edge_report(results, out_dir=args.out)


if __name__ == "__main__":
    main()
