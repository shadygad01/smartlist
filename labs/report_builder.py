"""
report_builder.py — HTML Report Builder for Labs
Delegates to edge_report, quant_research_report, research_report.
"""

import json
import sqlite3
from datetime import datetime

try:
    import edge_report
    _HAS_EDGE_REPORT = True
except Exception as e:
    _HAS_EDGE_REPORT = False
    print(f"[warn] edge_report import failed: {e}")

try:
    import quant_research_report
    _HAS_QUANT_REPORT = True
except Exception as e:
    _HAS_QUANT_REPORT = False
    print(f"[warn] quant_research_report import failed: {e}")

try:
    import research_report
    _HAS_RESEARCH_REPORT = True
except Exception as e:
    _HAS_RESEARCH_REPORT = False
    print(f"[warn] research_report import failed: {e}")


def build_html(results: dict, lab: str) -> str:
    """
    Generate an HTML report for a lab's results by delegating to existing report functions.

    For known labs (factor, interaction, parameter, regime, drift) tries the most
    relevant report module first, then falls back to a simple JSON dump.
    """
    html = ""

    # For factor / interaction labs — try research_report
    if lab in ("factor", "interaction") and _HAS_RESEARCH_REPORT:
        try:
            # research_report.build_report() loads from DB internally;
            # results dict is passed for reference only
            db_path = results.get("db_path", "egx_research.db")
            html = research_report.build_report(db_path=db_path)
            if html:
                return html
        except Exception as e:
            print(f"[warn] research_report.build_report failed: {e}")

    # For interaction lab — try edge_report with rule_discovery results
    if lab == "interaction" and _HAS_EDGE_REPORT:
        try:
            import os, json as _json
            edge_json = edge_report.EDGE_JSON_PATH
            if os.path.exists(edge_json):
                with open(edge_json, encoding="utf-8") as f:
                    edge_data = _json.load(f)
                html = edge_report.generate_edge_report(edge_data)
                if html:
                    return html
        except Exception as e:
            print(f"[warn] edge_report.generate_edge_report failed: {e}")

    # For any lab — try quant_research_report
    if _HAS_QUANT_REPORT:
        try:
            html = quant_research_report.build_report()
            if html:
                return html
        except Exception as e:
            print(f"[warn] quant_research_report.build_report failed: {e}")

    # Fallback: minimal HTML wrapping the JSON results
    now = datetime.now().isoformat()
    safe_json = json.dumps(results, default=str, indent=2)
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>{lab.capitalize()} Lab Report — {now[:10]}</title>
  <style>
    body {{ background:#0d1117; color:#c9d1d9; font-family:monospace; padding:20px; }}
    h1   {{ color:#58a6ff; }}
    pre  {{ background:#161b22; padding:16px; border-radius:6px;
            overflow:auto; font-size:12px; border:1px solid #30363d; }}
  </style>
</head>
<body>
  <h1>{lab.capitalize()} Lab Report</h1>
  <p style="color:#8b949e;">Generated: {now}</p>
  <pre>{safe_json}</pre>
</body>
</html>"""
    return html


def maybe_run_weekly(db_path="egx_research.db"):
    """
    Run the weekly research report if it is due, delegating to
    research_report.maybe_run_weekly_report().
    """
    if _HAS_RESEARCH_REPORT:
        try:
            return research_report.maybe_run_weekly_report(db_path=db_path)
        except Exception as e:
            print(f"[warn] maybe_run_weekly_report failed: {e}")
    return False


if __name__ == "__main__":
    import sys
    lab_name = sys.argv[1] if len(sys.argv) > 1 else "factor"
    db = sys.argv[2] if len(sys.argv) > 2 else "egx_research.db"
    html_out = build_html({"db_path": db}, lab_name)
    out_file = f"reports/{lab_name}_lab_report.html"
    import os
    os.makedirs("reports", exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(html_out)
    print(f"[report_builder] Saved → {out_file}")
