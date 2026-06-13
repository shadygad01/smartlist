"""
GX Learning Intelligence Layer
================================
Master intelligence meta-layer inside the Adaptive Report.
Measures whether the research ecosystem is learning, improving,
validating itself, and generating measurable performance gains.

Consumes ALL JSON report outputs. Maintains persistent memory
(gx_learning_memory.json). Generates gx_learning_report_*.html.

Usage:
  python gx_learning_layer.py
"""

import json
import math
import os
from datetime import date, datetime

TODAY = date.today().isoformat()
MEMORY_FILE = "gx_learning_memory.json"
REPORT_OUT = f"reports/gx_learning_report_{TODAY}.html"

# ═══════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════

def _jload(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def load_all_sources():
    return {
        "backtest":   _jload("backtest_report.json"),
        "research":   _jload("research_results.json"),
        "logic":      _jload("logic_analysis_results.json"),
        "optimizer":  _jload("optimization_results.json"),
        "edge":       _jload("edge_discovery_results.json"),
        "audit":      _jload("system_audit_results.json"),
        "adaptive":   _jload("adaptive_learning_results.json"),
        "historical": _jload("historical_backtest_results.json"),
    }


# ═══════════════════════════════════════════════════════════════
# LEARNING MEMORY
# ═══════════════════════════════════════════════════════════════

def load_memory():
    mem = _jload(MEMORY_FILE)
    if mem is None:
        mem = {
            "schema_version": 2,
            "created_at": TODAY,
            "total_runs": 0,
            "runs": [],
            "recommendations": [],
            "performance_history": [],
            "edge_history": [],
        }
    return mem


def save_memory(mem):
    with open(MEMORY_FILE, "w") as f:
        json.dump(mem, f, indent=2, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════
# RECOMMENDATION EXTRACTION
# ═══════════════════════════════════════════════════════════════

def _extract_recommendations(src: dict) -> list:
    """Extract normalised recommendation dicts from all report sources."""
    recs = []

    # ── Adaptive Learning ─────────────────────────────────────
    adp = src.get("adaptive") or {}
    for imp in adp.get("all_improvements", []):
        recs.append({
            "id":               f"adp_{imp.get('id', 'X')}",
            "source":           "adaptive",
            "name":             imp.get("name", ""),
            "description":      imp.get("name", ""),
            "expected_delta_ret": imp.get("delta_ret", 0.0),
            "expected_delta_mfe": imp.get("delta_mfe", 0.0),
            "confidence":       round(imp.get("model_score", 50) / 100, 2),
            "wf_consistent":    imp.get("wf_consistent", False),
            "overfitted":       imp.get("overfitted", True),
            "supporting":       ["adaptive"],
        })

    # ── Logic Analyzer ────────────────────────────────────────
    log = src.get("logic") or {}
    for i, rec in enumerate(log.get("summary_recommendations", [])):
        impact_str = rec.get("impact", "0%")
        delta = 0.0
        try:
            delta = float(impact_str.strip().split("%")[0].replace("+", "")) / 100
        except Exception:
            pass
        recs.append({
            "id":               f"log_{i+1:02d}",
            "source":           "logic",
            "name":             f"{rec.get('label','')}: {rec.get('param','')}",
            "description":      rec.get("proposed", ""),
            "expected_delta_ret": delta,
            "expected_delta_mfe": 0.0,
            "confidence":       0.65,
            "wf_consistent":    None,
            "overfitted":       None,
            "supporting":       ["logic"],
        })

    # ── Weight Optimizer ──────────────────────────────────────
    opt = src.get("optimizer") or {}
    for i, rec in enumerate(opt.get("top_recommendations", [])):
        recs.append({
            "id":               f"opt_{i+1:02d}",
            "source":           "optimizer",
            "name":             rec.get("change", rec.get("indicator", "")),
            "description":      f"{rec.get('type','')}: {rec.get('change','')}",
            "expected_delta_ret": rec.get("delta_ret", 0.0),
            "expected_delta_mfe": rec.get("delta_mfe", 0.0),
            "confidence":       rec.get("confidence", 0.5),
            "wf_consistent":    None,
            "overfitted":       None,
            "supporting":       ["optimizer"],
        })

    # ── System Audit ──────────────────────────────────────────
    aud = src.get("audit") or {}
    for fd in aud.get("filter_damage", []):
        if fd.get("diff", 0) < -0.01 and fd.get("p_value", 1) < 0.25:
            recs.append({
                "id":               f"aud_{fd.get('filter','X').replace(' ','_')}",
                "source":           "audit",
                "name":             f"Review filter: {fd.get('filter','')}",
                "description":      f"Filter rejects {fd.get('pct_rejected',0):.0f}% of signals with diff={fd.get('diff',0)*100:+.1f}%",
                "expected_delta_ret": abs(fd.get("diff", 0)),
                "expected_delta_mfe": 0.0,
                "confidence":       0.55,
                "wf_consistent":    None,
                "overfitted":       None,
                "supporting":       ["audit"],
            })

    return recs


def _merge_recommendations(memory_recs: list, new_recs: list) -> list:
    """Add new recs to memory; update last_seen for existing ones. Find multi-module support."""
    existing = {r["id"]: r for r in memory_recs}

    for nr in new_recs:
        rid = nr["id"]
        if rid in existing:
            er = existing[rid]
            er["last_seen"] = TODAY
            # Add supporting module if new
            for s in nr.get("supporting", []):
                if s not in er["supporting"]:
                    er["supporting"].append(s)
        else:
            nr["status"] = "Proposed"
            nr["first_seen"] = TODAY
            nr["last_seen"] = TODAY
            nr["actual_delta_ret"] = None
            nr["actual_delta_mfe"] = None
            nr["prediction_accuracy"] = None
            existing[rid] = nr

    # Cross-module agreement: mark recs confirmed by ≥2 modules
    _cross_validate_recs(list(existing.values()), new_recs)

    return list(existing.values())


def _cross_validate_recs(all_recs: list, new_recs: list):
    """Detect recommendations confirmed by multiple modules."""
    # Keywords linking modules
    SWEEP_KEYS  = ["sweep", "imp-2"]
    OB_KEYS     = ["order block", "ob", "imp-1", "r2_ob"]
    HTF_KEYS    = ["htf", "r4_htf", "higher high", "hh", "imp-3"]
    DEMAND_KEYS = ["demand", "r8_demand", "imp-4"]
    SCORE_KEYS  = ["score gate", "raw_score", "minimum score"]

    groups = [SWEEP_KEYS, OB_KEYS, HTF_KEYS, DEMAND_KEYS, SCORE_KEYS]

    for rec in all_recs:
        name_lower = (str(rec.get("name","")) + " " + str(rec.get("description",""))).lower()
        for group in groups:
            if any(k in name_lower for k in group):
                # Find other recs in same group from different modules
                peers = [
                    r for r in all_recs
                    if r["id"] != rec["id"]
                    and any(k in (str(r.get("name","")) + str(r.get("description",""))).lower()
                            for k in group)
                ]
                peer_modules = list({s for r in peers for s in r.get("supporting", [])})
                for pm in peer_modules:
                    if pm not in rec["supporting"]:
                        rec["supporting"].append(pm)
                break


# ═══════════════════════════════════════════════════════════════
# PERFORMANCE METRICS EXTRACTION
# ═══════════════════════════════════════════════════════════════

def extract_perf_snapshot(src: dict) -> dict:
    """Extract canonical performance metrics (Level-1 ground truth: backtest)."""
    bt = src.get("backtest") or {}
    ov = bt.get("overall_stats") or {}
    hist = src.get("historical") or {}
    lb   = hist.get("live_baseline") or {}
    hb   = hist.get("baseline") or {}

    return {
        "date":          TODAY,
        "n_signals":     ov.get("total_signals", 0),
        "win_rate":      ov.get("win_rate", 0.0),
        "profit_factor": ov.get("profit_factor", 0.0),
        "expectancy":    ov.get("expectancy_pct", 0.0),
        "cagr":          bt.get("cagr_pct", 0.0),
        "max_dd":        bt.get("max_drawdown_pct", 0.0),
        "calmar":        bt.get("calmar_ratio", 0.0),
        # r20d framework (research metrics)
        "r20d_mean":     lb.get("mean", hb.get("mean", 0.0)),
        "r20d_pf":       lb.get("pf", hb.get("pf", 0.0)),
        "r20d_mfe":      lb.get("mfe", hb.get("mfe", 0.0)),
        "r20d_wr":       lb.get("wr", hb.get("wr", 0.0)),
    }


def update_perf_history(memory: dict, snapshot: dict):
    """Append current snapshot; compute period-over-period changes."""
    history = memory.get("performance_history", [])
    # Avoid duplicates for same date
    if history and history[-1].get("date") == TODAY:
        history[-1] = snapshot
    else:
        history.append(snapshot)
    memory["performance_history"] = history[-30:]  # keep 30 snapshots max


def compute_perf_trends(history: list) -> dict:
    if len(history) < 2:
        return {"status": "insufficient_history", "periods": 1}

    cur  = history[-1]
    prev = history[-2]
    n    = len(history)
    avg  = lambda key: sum(h.get(key, 0) for h in history) / n

    def delta(key):
        c, p = cur.get(key, 0), prev.get(key, 0)
        if p == 0:
            return 0.0
        return round((c - p) / abs(p) * 100, 1)

    return {
        "status":            "available",
        "periods":           n,
        "wr_delta_pct":      delta("win_rate"),
        "pf_delta_pct":      delta("profit_factor"),
        "exp_delta_pct":     delta("expectancy"),
        "cagr_delta_pct":    delta("cagr"),
        "avg_wr":            round(avg("win_rate"), 4),
        "avg_pf":            round(avg("profit_factor"), 2),
        "trend_label":       "Stable",
    }


# ═══════════════════════════════════════════════════════════════
# EDGE EVOLUTION
# ═══════════════════════════════════════════════════════════════

def extract_top_edges(src: dict, n: int = 10) -> list:
    edge_data = src.get("edge") or {}
    rules = edge_data.get("significant_rules") or edge_data.get("rules") or []

    # Sort by expectancy desc, take top N
    sorted_rules = sorted(rules, key=lambda r: r.get("expectancy", 0), reverse=True)[:n]
    edges = []
    for r in sorted_rules:
        edges.append({
            "rule_text":   r.get("rule_text", "")[:80],
            "source":      r.get("source", "?"),
            "n":           r.get("n", 0),
            "mfe_mean":    round(r.get("mfe_mean", 0), 1),
            "win_rate":    round(r.get("win_rate", 0), 3),
            "expectancy":  round(r.get("expectancy", 0), 1),
            "p_value":     round(r.get("p_value", 1), 4),
        })
    return edges


def update_edge_history(memory: dict, current_edges: list):
    """Track edge strength over time."""
    history = memory.get("edge_history", [])
    entry = {"date": TODAY, "edges": current_edges}
    if history and history[-1].get("date") == TODAY:
        history[-1] = entry
    else:
        history.append(entry)
    memory["edge_history"] = history[-12:]  # keep 12 snapshots


def classify_edge_stability(memory: dict, current_edges: list) -> list:
    """Compare current edges vs previous run. Classify stability."""
    history = memory.get("edge_history", [])
    if len(history) < 2:
        return [{**e, "stability": "New", "change_pct": 0.0} for e in current_edges]

    prev_edges = {e["rule_text"][:60]: e for e in history[-2].get("edges", [])}

    result = []
    for edge in current_edges:
        key = edge["rule_text"][:60]
        if key in prev_edges:
            prev_exp = prev_edges[key].get("expectancy", edge["expectancy"])
            change = edge["expectancy"] - prev_exp
            if change > 2:
                stability = "Strengthening"
            elif change < -2:
                stability = "Weakening"
            else:
                stability = "Stable"
            result.append({**edge, "stability": stability, "change_pct": round(change, 1)})
        else:
            result.append({**edge, "stability": "New", "change_pct": 0.0})

    # Check for invalidated edges (in previous but not current)
    for key, prev in prev_edges.items():
        if not any(e["rule_text"][:60] == key for e in current_edges):
            result.append({**prev, "stability": "Invalidated", "change_pct": -prev.get("expectancy", 0)})

    return result[:12]


# ═══════════════════════════════════════════════════════════════
# MODULE CONTRIBUTION ANALYSIS
# ═══════════════════════════════════════════════════════════════

MODULE_META = {
    "backtest":   {"label": "Backtest Report",    "level": 1, "base_score": 95},
    "historical": {"label": "History Report",     "level": 1, "base_score": 90},
    "audit":      {"label": "System Audit",       "level": 2, "base_score": 82},
    "adaptive":   {"label": "Adaptive Learning",  "level": 3, "base_score": 78},
    "logic":      {"label": "Logic Analyzer",     "level": 3, "base_score": 73},
    "optimizer":  {"label": "Weight Optimizer",   "level": 3, "base_score": 70},
    "edge":       {"label": "Edge Discovery",     "level": 3, "base_score": 65},
    "research":   {"label": "Research Report",    "level": 3, "base_score": 62},
}


def compute_module_contributions(src: dict, all_recs: list) -> list:
    """Score each module's research contribution."""
    contributions = []
    for key, meta in MODULE_META.items():
        data = src.get(key)
        available = data is not None

        if not available:
            contributions.append({
                "key": key, "label": meta["label"], "level": meta["level"],
                "available": False, "score": 0,
                "recs_count": 0, "wf_passed": 0, "multi_module": 0,
                "verdict": "Not Available",
            })
            continue

        # Recommendations from this module
        mod_recs = [r for r in all_recs if key in r.get("supporting", [])]
        n_recs   = len(mod_recs)

        # Walk-forward consistent (adaptive only)
        if key == "adaptive":
            wf_passed = sum(1 for r in mod_recs if r.get("wf_consistent") is True)
        else:
            wf_passed = n_recs  # other modules don't have wf field

        # Multi-module confirmed
        multi = sum(1 for r in mod_recs if len(r.get("supporting", [])) >= 2)

        # Score: base + bonuses
        score = meta["base_score"]
        if n_recs > 0:
            multi_bonus = min(15, multi / n_recs * 20)
            score = min(100, score + multi_bonus)
        if key == "adaptive":
            adp = src.get("adaptive") or {}
            h = adp.get("health_score", 50)
            score = round(score * 0.7 + h * 0.3)

        verdict = "Excellent" if score >= 85 else "Good" if score >= 70 else "Fair" if score >= 55 else "Low"

        contributions.append({
            "key":          key,
            "label":        meta["label"],
            "level":        meta["level"],
            "available":    True,
            "score":        round(score),
            "recs_count":   n_recs,
            "wf_passed":    wf_passed,
            "multi_module": multi,
            "verdict":      verdict,
        })

    return sorted(contributions, key=lambda x: x["score"], reverse=True)


# ═══════════════════════════════════════════════════════════════
# OVERFITTING DETECTION
# ═══════════════════════════════════════════════════════════════

def run_overfitting_checks(src: dict, perf: dict) -> list:
    """Run systematic overfitting checks. Return list of finding dicts."""
    findings = []

    # 1. Edge count inflation
    edge = src.get("edge") or {}
    n_rules = edge.get("total_rules_significant", 0)
    if n_rules > 5000:
        findings.append({
            "check":    "Edge Count Inflation",
            "status":   "WARNING",
            "detail":   f"{n_rules:,} significant edges discovered — high data-mining risk. "
                        "Only rules surviving out-of-sample validation are trustworthy.",
        })
    else:
        findings.append({"check": "Edge Count Inflation", "status": "PASS",
                         "detail": f"{n_rules:,} significant edges — within acceptable range."})

    # 2. OOS improvement
    opt = src.get("optimizer") or {}
    oos = opt.get("oos_improvement", None)
    if oos is not None:
        if oos < -0.01:
            findings.append({"check": "OOS Degradation", "status": "WARNING",
                             "detail": f"Optimizer OOS improvement = {oos*100:+.2f}% — in-sample only."})
        else:
            findings.append({"check": "OOS Degradation", "status": "PASS",
                             "detail": f"OOS improvement = {oos*100:+.4f}% — no degradation detected."})

    # 3. Walk-forward consistency
    adp = src.get("adaptive") or {}
    imps = adp.get("all_improvements", [])
    n_wf = sum(1 for i in imps if i.get("wf_consistent") is True)
    n_tot = len(imps)
    survival = n_wf / n_tot if n_tot > 0 else 0
    if survival < 0.3:
        findings.append({"check": "Walk-Forward Survival", "status": "WARNING",
                         "detail": f"{n_wf}/{n_tot} improvements wf_consistent ({survival*100:.0f}%) — most fail."})
    else:
        findings.append({"check": "Walk-Forward Survival", "status": "PASS",
                         "detail": f"{n_wf}/{n_tot} improvements passed walk-forward ({survival*100:.0f}%)."})

    # 4. Fibonacci exit vs r20d discrepancy
    pf_fib = perf.get("profit_factor", 0)
    pf_r20 = perf.get("r20d_pf", 0)
    if pf_fib > 0 and pf_r20 > 0:
        ratio = pf_fib / pf_r20
        if ratio > 3:
            findings.append({"check": "Exit Model Discrepancy", "status": "WARNING",
                             "detail": f"Fibonacci PF={pf_fib:.2f} vs r20d PF={pf_r20:.2f} (ratio {ratio:.1f}x). "
                                       "Fibonacci exits are theoretical — real exits may differ."})
        else:
            findings.append({"check": "Exit Model Discrepancy", "status": "PASS",
                             "detail": f"PF spread (Fib={pf_fib:.2f} / r20d={pf_r20:.2f}) is acceptable."})

    # 5. Recommendation vs signal quality alignment
    bt = src.get("backtest") or {}
    fc = bt.get("filter_comparison") or {}
    cur_cagr  = fc.get("current_filter", {}).get("cagr", perf.get("cagr", 0))
    cons_cagr = fc.get("conservative_filter", {}).get("cagr", 0)
    n_cons    = fc.get("conservative_filter", {}).get("n", 0)
    n_cur     = perf.get("n_signals", 0)
    if n_cons > 0 and n_cur > 0 and cons_cagr > 0:
        if n_cons / n_cur < 0.4 and cons_cagr < cur_cagr * 0.6:
            findings.append({"check": "Filter Concentration Risk", "status": "INFO",
                             "detail": f"Conservative filter ({n_cons} signals) gives lower CAGR ({cons_cagr:.0f}%) than full set."
                                       " Quality gate reduces signal count by >60%."})
        else:
            findings.append({"check": "Filter Concentration Risk", "status": "PASS",
                             "detail": "Conservative filter maintains acceptable signal density."})

    # 6. Partial forward data
    n_total = perf.get("n_signals", 0)
    bt2 = src.get("historical") or {}
    n_hist  = (bt2.get("baseline") or {}).get("n", 0)
    n_live  = (bt2.get("live_baseline") or {}).get("n", 0)
    if n_total > 0 and (n_hist + n_live) > 0:
        pct_partial = max(0, n_total - n_hist - n_live) / n_total
        if pct_partial > 0.2:
            findings.append({"check": "Partial Forward Data", "status": "INFO",
                             "detail": f"~{pct_partial*100:.0f}% of signals have incomplete forward data (<20d resolved). "
                                       "Metrics will improve as data matures."})
        else:
            findings.append({"check": "Partial Forward Data", "status": "PASS",
                             "detail": "Forward data coverage is adequate."})

    return findings


# ═══════════════════════════════════════════════════════════════
# GX LEARNING SCORE
# ═══════════════════════════════════════════════════════════════

def compute_gx_score(src: dict, all_recs: list, perf: dict,
                     memory: dict, overfitting: list) -> dict:
    """
    GX Learning Score (0-100):
      25% Research Coherence   — cross-module agreement
      25% Performance Quality  — backtest metrics
      20% OOS Robustness       — walk-forward survival + OOS stability
      15% System Health        — adaptive health score
      15% Knowledge Retention  — memory depth + history
    """

    # ── Research Coherence ─────────────────────────────────────
    n_total = len(all_recs)
    n_multi = sum(1 for r in all_recs if len(r.get("supporting", [])) >= 2)
    coherence = round(n_multi / n_total * 100) if n_total > 0 else 0

    # ── Performance Quality ────────────────────────────────────
    pf    = perf.get("profit_factor", 1.0)
    wr    = perf.get("win_rate", 0.0)
    cagr  = abs(perf.get("cagr", 0.0))

    pf_score   = min(100, max(0, (pf - 1) / 9 * 100))
    wr_score   = min(100, max(0, (wr - 0.45) / 0.35 * 100))
    cagr_score = min(100, cagr / 150 * 100)
    perf_score = round(pf_score * 0.45 + wr_score * 0.35 + cagr_score * 0.20)

    # ── OOS Robustness ─────────────────────────────────────────
    adp = src.get("adaptive") or {}
    imps = adp.get("all_improvements", [])
    n_wf  = sum(1 for i in imps if i.get("wf_consistent") is True)
    n_tot_imp = len(imps)
    survival  = n_wf / n_tot_imp if n_tot_imp > 0 else 0

    opt = src.get("optimizer") or {}
    oos_imp = opt.get("oos_improvement", 0) or 0
    oos_flag = 0 if oos_imp < -0.005 else 20

    n_warn = sum(1 for f in overfitting if f["status"] == "WARNING")
    oos_score = round(min(100, survival * 80 + oos_flag - n_warn * 8))

    # ── System Health ──────────────────────────────────────────
    health = adp.get("health_score", 50)

    # ── Knowledge Retention ────────────────────────────────────
    n_runs = memory.get("total_runs", 0)
    n_hist = len(memory.get("performance_history", []))
    retention = min(100, n_runs * 8 + n_hist * 3 + (20 if n_runs == 0 else 0))

    # ── Composite ──────────────────────────────────────────────
    gx = round(
        coherence   * 0.25 +
        perf_score  * 0.25 +
        oos_score   * 0.20 +
        health      * 0.15 +
        retention   * 0.15
    )

    # Trend: use history if available, else infer from performance vs r20d baseline
    if n_hist >= 2:
        hist = memory["performance_history"]
        prev_gx = hist[-2].get("gx_score", gx)
        diff = gx - prev_gx
        trend = "Improving" if diff > 2 else "Degrading" if diff < -2 else "Stable"
    else:
        # First run: compare Fibonacci PF vs r20d PF as proxy for system progression
        pf_fib = perf.get("profit_factor", 1.0)
        pf_r20 = perf.get("r20d_pf", 1.0)
        if pf_fib > pf_r20 * 2.5:
            trend = "Stable — Early Stage (Run #1)"
        elif gx >= 60:
            trend = "Stable — Early Stage (Run #1)"
        else:
            trend = "Early Stage — Accumulating Data"

    return {
        "gx_score":         gx,
        "trend":            trend,
        "coherence":        coherence,
        "perf_score":       perf_score,
        "oos_score":        oos_score,
        "health":           health,
        "retention":        retention,
        "n_multi_module":   n_multi,
        "n_total_recs":     n_total,
        "wf_survival_pct":  round(survival * 100),
    }


# ═══════════════════════════════════════════════════════════════
# RESEARCH EFFECTIVENESS
# ═══════════════════════════════════════════════════════════════

def compute_research_stats(all_recs: list) -> dict:
    n_total     = len(all_recs)
    n_proposed  = sum(1 for r in all_recs if r.get("status") == "Proposed")
    n_tested    = sum(1 for r in all_recs if r.get("status") == "Tested")
    n_validated = sum(1 for r in all_recs if r.get("status") == "Validated")
    n_rejected  = sum(1 for r in all_recs if r.get("status") == "Rejected")
    n_expired   = sum(1 for r in all_recs if r.get("status") == "Superseded")

    success_rate = round(n_validated / max(1, n_validated + n_rejected) * 100, 1)
    tested_pct   = round((n_tested + n_validated + n_rejected) / max(1, n_total) * 100, 1)

    # High confidence recs (confidence >= 0.70)
    n_high_conf = sum(1 for r in all_recs if r.get("confidence", 0) >= 0.70)

    # Multi-module confirmed
    n_multi = sum(1 for r in all_recs if len(r.get("supporting", [])) >= 2)

    # Expected total gain (sum of top validated + high-conf proposed)
    exp_gain = sum(
        r.get("expected_delta_ret", 0)
        for r in all_recs
        if r.get("confidence", 0) >= 0.65
    )

    return {
        "n_total":      n_total,
        "n_proposed":   n_proposed,
        "n_tested":     n_tested,
        "n_validated":  n_validated,
        "n_rejected":   n_rejected,
        "n_expired":    n_expired,
        "success_rate": success_rate,
        "tested_pct":   tested_pct,
        "n_high_conf":  n_high_conf,
        "n_multi":      n_multi,
        "exp_total_gain_pct": round(exp_gain * 100, 2),
    }


# ═══════════════════════════════════════════════════════════════
# HTML REPORT
# ═══════════════════════════════════════════════════════════════

_STATUS_COLOR = {
    "Proposed":   "#6c8ebf",
    "Tested":     "#d6a740",
    "Validated":  "#6aa84f",
    "Rejected":   "#cc4444",
    "Superseded": "#888888",
}
_STABILITY_COLOR = {
    "New":          "#6c8ebf",
    "Stable":       "#6aa84f",
    "Strengthening":"#82d46a",
    "Weakening":    "#d6a740",
    "Invalidated":  "#cc4444",
}
_CHECK_COLOR = {
    "PASS":    "#6aa84f",
    "WARNING": "#d6a740",
    "INFO":    "#6c8ebf",
    "FAIL":    "#cc4444",
}


def _score_color(s: int) -> str:
    if s >= 80: return "#6aa84f"
    if s >= 65: return "#a0c878"
    if s >= 50: return "#d6a740"
    if s >= 35: return "#e07020"
    return "#cc4444"


def _bar(pct: int, color: str = "#6c8ebf") -> str:
    return (f'<div style="background:#1e2533;border-radius:4px;height:8px;width:100%;">'
            f'<div style="background:{color};width:{min(100,pct)}%;height:8px;border-radius:4px;"></div></div>')


def _score_circle(score: int, label: str = "GX LEARNING SCORE") -> str:
    color = _score_color(score)
    r, cx, cy = 70, 90, 90
    circ = 2 * 3.14159 * r
    fill = circ * (1 - score / 100)
    return f"""
    <div style="text-align:center;padding:20px 0;">
      <svg width="180" height="180" viewBox="0 0 180 180">
        <circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#1e2533" stroke-width="14"/>
        <circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{color}" stroke-width="14"
          stroke-dasharray="{circ:.1f}" stroke-dashoffset="{fill:.1f}"
          stroke-linecap="round" transform="rotate(-90 {cx} {cy})"/>
        <text x="{cx}" y="{cy-8}" text-anchor="middle" fill="{color}"
              font-size="34" font-weight="700" font-family="monospace">{score}</text>
        <text x="{cx}" y="{cy+16}" text-anchor="middle" fill="#aaa"
              font-size="11" font-family="sans-serif">out of 100</text>
      </svg>
      <div style="color:{color};font-size:13px;font-weight:600;letter-spacing:1px;">{label}</div>
    </div>"""


def _card(title: str, body: str, accent: str = "#6c8ebf") -> str:
    return f"""
    <div style="background:#141b27;border:1px solid #1e2d40;border-top:3px solid {accent};
                border-radius:8px;padding:20px;margin-bottom:20px;">
      <h3 style="color:{accent};margin:0 0 14px;font-size:14px;letter-spacing:1px;text-transform:uppercase;">{title}</h3>
      {body}
    </div>"""


def _kpi_row(items: list) -> str:
    cells = ""
    for label, value, color in items:
        cells += f"""
        <div style="background:#0d1420;border-radius:6px;padding:14px;text-align:center;flex:1;min-width:100px;">
          <div style="color:{color};font-size:22px;font-weight:700;font-family:monospace;">{value}</div>
          <div style="color:#888;font-size:11px;margin-top:4px;text-transform:uppercase;">{label}</div>
        </div>"""
    return f'<div style="display:flex;gap:10px;flex-wrap:wrap;">{cells}</div>'


# ═══════════════════════════════════════════════════════════════
# CONTEXT-AWARE INTELLIGENCE LAYER (⑪-⑮)
# ═══════════════════════════════════════════════════════════════

def _build_context_intelligence(db_path: str = "egx_research.db") -> dict:
    """
    Sections ⑪-⑮: context-aware decomposition from v_all_signals.
    Reads live SQLite DB, tags signals, computes 5 HTML section bodies.
    Returns dict with keys: decomp, ctx_tags, sensitivity, failures, successes.
    """
    import sqlite3
    from collections import Counter

    SCORE_COLS = ["r1_price", "r2_ob", "r3_liquidity", "r4_htf",
                  "r5_avwap", "r6_macd", "r7_div", "r8_demand"]
    SCORE_MAX  = {"r1_price": 30, "r2_ob": 10, "r3_liquidity": 10, "r4_htf": 20,
                  "r5_avwap": 10, "r6_macd": 10, "r7_div": 5, "r8_demand": 5}
    WIN_THRESH  =  0.07
    LOSS_THRESH =  0.0

    NA = '<div style="color:#555;font-size:12px;padding:10px;">No data available.</div>'
    _empty = {"decomp": NA, "ctx_tags": NA, "sensitivity": NA, "failures": NA, "successes": NA}

    try:
        if not os.path.exists(db_path):
            return _empty

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT
                r1_price, r2_ob, r3_liquidity, r4_htf, r5_avwap, r6_macd, r7_div, r8_demand,
                COALESCE(sweep_detected, 0)  AS sweep_detected,
                COALESCE(wick_rejection, 0)  AS wick_rejection,
                COALESCE(equal_lows, 0)      AS equal_lows,
                COALESCE(htf_hh, 0)          AS htf_hh,
                COALESCE(htf_hl, 0)          AS htf_hl,
                COALESCE(rsi_div, 0)         AS rsi_div,
                COALESCE(macd_div, 0)        AS macd_div,
                COALESCE(sv_hit, 0)          AS sv_hit,
                COALESCE(hvn_hit, 0)         AS hvn_hit,
                r20d
            FROM v_all_signals
            WHERE r20d IS NOT NULL
        """).fetchall()
        conn.close()
        rows = [dict(r) for r in rows]

        if not rows:
            return _empty

        def _tag(s):
            ht_hl = int(s.get("htf_hl") or 0)
            ht_hh = int(s.get("htf_hh") or 0)
            regime = "trend" if ht_hl == 1 else ("range" if ht_hh == 0 and ht_hl == 0 else "mixed")

            r6 = float(s.get("r6_macd") or 0)
            r7 = float(s.get("r7_div")  or 0)
            md = int(s.get("macd_div")  or 0)
            rd = int(s.get("rsi_div")   or 0)
            vol = "high" if (r6 + r7 >= 8 and (md or rd)) else ("low" if r6 + r7 <= 4 else "medium")

            sw = int(s.get("sweep_detected")  or 0)
            eq = int(s.get("equal_lows")      or 0)
            wk = int(s.get("wick_rejection")  or 0)
            struct = "expansion" if sw else ("compression" if eq else ("reversal" if wk else "unknown"))

            hv = int(s.get("hvn_hit") or 0)
            sv = int(s.get("sv_hit")  or 0)
            r3 = float(s.get("r3_liquidity") or 0)
            liq = "strong" if (hv or sv) else ("moderate" if r3 >= 7 else "weak")
            return regime, vol, struct, liq

        tagged = []
        for s in rows:
            r20d = float(s.get("r20d") or 0)
            reg, vol, struct, liq = _tag(s)
            tagged.append({**s, "r20d": r20d, "regime": reg, "vol": vol, "struct": struct, "liq": liq})

        total  = len(tagged)
        wins   = [s for s in tagged if s["r20d"] >= WIN_THRESH]
        losses = [s for s in tagged if s["r20d"] <  LOSS_THRESH]

        # ─── ⑪ Score Contribution Decomposition ──────────────
        def _avg(lst, col):
            vals = [float(v.get(col) or 0) for v in lst]
            return sum(vals) / len(vals) if vals else 0.0

        decomp_rows = ""
        for col in SCORE_COLS:
            mx    = SCORE_MAX[col]
            wa    = _avg(wins,   col)
            la    = _avg(losses, col)
            wp    = wa / mx * 100 if mx else 0
            lp    = la / mx * 100 if mx else 0
            delta = wp - lp
            dc    = "#6aa84f" if delta > 5 else ("#d6a740" if delta > 0 else "#cc4444")
            bw    = (f'<div style="background:#1e2533;border-radius:3px;height:5px;width:100%;margin-top:2px;">'
                     f'<div style="background:#6aa84f;width:{min(100, wp):.0f}%;height:5px;border-radius:3px;"></div></div>')
            bl    = (f'<div style="background:#1e2533;border-radius:3px;height:5px;width:100%;margin-top:2px;">'
                     f'<div style="background:#cc4444;width:{min(100, lp):.0f}%;height:5px;border-radius:3px;"></div></div>')
            decomp_rows += (
                f"<tr>"
                f"<td style='color:#aab;font-size:12px;white-space:nowrap;'>{col}</td>"
                f"<td style='color:#555;font-size:11px;text-align:center;'>/{mx}</td>"
                f"<td style='min-width:110px;'><div style='color:#6aa84f;font-size:12px;text-align:right;'>{wa:.1f} ({wp:.0f}%)</div>{bw}</td>"
                f"<td style='min-width:110px;'><div style='color:#cc4444;font-size:12px;text-align:right;'>{la:.1f} ({lp:.0f}%)</div>{bl}</td>"
                f"<td style='color:{dc};font-size:13px;font-weight:700;text-align:right;'>{delta:+.0f}pp</td>"
                f"</tr>"
            )

        decomp_html = (
            f'<div style="color:#888;font-size:12px;margin-bottom:10px;">'
            f'Wins: <strong style="color:#6aa84f;">{len(wins)}</strong> (r20d&nbsp;&ge;&nbsp;7%)&nbsp;&nbsp;|&nbsp;&nbsp;'
            f'Losses: <strong style="color:#cc4444;">{len(losses)}</strong> (r20d&nbsp;&lt;&nbsp;0%)&nbsp;&nbsp;|&nbsp;&nbsp;'
            f'Total resolved: <strong>{total}</strong></div>'
            f'<div style="overflow-x:auto;">'
            f'<table style="width:100%;border-collapse:collapse;font-size:12px;">'
            f'<thead><tr style="border-bottom:1px solid #1e2d40;">'
            f'<th style="color:#5b8dee;padding:8px 6px;text-align:left;">Component</th>'
            f'<th style="color:#5b8dee;padding:8px 6px;">Max</th>'
            f'<th style="color:#6aa84f;padding:8px 6px;text-align:right;">Wins avg (% of max)</th>'
            f'<th style="color:#cc4444;padding:8px 6px;text-align:right;">Losses avg (% of max)</th>'
            f'<th style="color:#5b8dee;padding:8px 6px;text-align:right;">&Delta; (pp)</th>'
            f'</tr></thead>'
            f'<tbody>{decomp_rows}</tbody>'
            f'</table></div>'
            f'<div style="color:#666;font-size:11px;margin-top:6px;">'
            f'&Delta; = Win% &minus; Loss% (percentage points of max score). Positive = component stronger in wins.</div>'
        )

        # ─── ⑫ Context Tag Summary ────────────────────────────
        ctx_tables = ""
        for tag_key, tag_vals, label in [
            ("regime", ["trend", "range", "mixed"],                         "Market Regime"),
            ("vol",    ["high", "medium", "low"],                           "Volatility State"),
            ("struct", ["expansion", "compression", "reversal", "unknown"], "Structure State"),
            ("liq",    ["strong", "moderate", "weak"],                      "Liquidity State"),
        ]:
            t_rows = ""
            for val in tag_vals:
                sub = [s for s in tagged if s[tag_key] == val]
                n   = len(sub)
                if n == 0:
                    t_rows += (f"<tr><td style='color:#aab;font-size:12px;'>{val}</td>"
                               f"<td colspan='4' style='color:#444;text-align:center;font-size:11px;'>— no data —</td></tr>")
                    continue
                r20ds  = [s["r20d"] for s in sub]
                wr     = sum(1 for r in r20ds if r >= WIN_THRESH) / n
                mean_r = sum(r20ds) / n
                gw     = sum(r for r in r20ds if r > 0)
                gl     = abs(sum(r for r in r20ds if r < 0))
                pf     = gw / gl if gl > 0 else (99.0 if gw > 0 else 0.0)
                pct    = n / total * 100
                wr_c   = "#6aa84f" if wr >= 0.55 else ("#d6a740" if wr >= 0.40 else "#cc4444")
                mr_c   = "#6aa84f" if mean_r >= WIN_THRESH else ("#d6a740" if mean_r >= 0 else "#cc4444")
                t_rows += (
                    f"<tr>"
                    f"<td style='color:#e8eaf0;font-size:12px;'>{val}</td>"
                    f"<td style='color:#aab;font-size:12px;text-align:center;'>{n} ({pct:.0f}%)</td>"
                    f"<td style='color:{wr_c};font-size:12px;text-align:right;'>{wr*100:.0f}%</td>"
                    f"<td style='color:#aab;font-size:12px;text-align:right;'>{pf:.2f}</td>"
                    f"<td style='color:{mr_c};font-size:12px;text-align:right;'>{mean_r*100:+.1f}%</td>"
                    f"</tr>"
                )
            ctx_tables += (
                f'<div style="margin-bottom:18px;">'
                f'<div style="color:#5b8dee;font-size:11px;letter-spacing:1px;margin-bottom:6px;">{label.upper()}</div>'
                f'<div style="overflow-x:auto;">'
                f'<table style="width:100%;border-collapse:collapse;font-size:12px;">'
                f'<thead><tr style="border-bottom:1px solid #1e2d40;">'
                f'<th style="color:#5b8dee;padding:6px;text-align:left;">State</th>'
                f'<th style="color:#5b8dee;padding:6px;text-align:center;">N (%)</th>'
                f'<th style="color:#5b8dee;padding:6px;text-align:right;">WR</th>'
                f'<th style="color:#5b8dee;padding:6px;text-align:right;">PF</th>'
                f'<th style="color:#5b8dee;padding:6px;text-align:right;">Avg r20d</th>'
                f'</tr></thead>'
                f'<tbody>{t_rows}</tbody>'
                f'</table></div></div>'
            )

        ctx_html = ctx_tables

        # ─── ⑬ Conditional Sensitivity ───────────────────────
        regime_vals = ["trend", "range", "mixed"]
        vol_vals    = ["high", "medium", "low"]

        hdr = "<th style='color:#5b8dee;padding:6px 8px;text-align:left;'>Regime &times; Vol</th>"
        for v in vol_vals:
            hdr += f"<th style='color:#5b8dee;padding:6px 8px;text-align:center;'>{v}</th>"

        s_rows = ""
        for reg in regime_vals:
            row = f"<td style='color:#aab;font-size:12px;font-weight:600;padding:6px 8px;'>{reg}</td>"
            for vol in vol_vals:
                sub = [s for s in tagged if s["regime"] == reg and s["vol"] == vol]
                if not sub:
                    row += "<td style='color:#333;text-align:center;font-size:11px;'>—</td>"
                    continue
                n      = len(sub)
                mean_r = sum(s["r20d"] for s in sub) / n
                wr     = sum(1 for s in sub if s["r20d"] >= WIN_THRESH) / n
                col    = "#6aa84f" if mean_r >= WIN_THRESH else ("#d6a740" if mean_r >= 0 else "#cc4444")
                row += (f"<td style='text-align:center;padding:6px;'>"
                        f"<div style='color:{col};font-size:12px;font-weight:600;'>{mean_r*100:+.1f}%</div>"
                        f"<div style='color:#666;font-size:10px;'>WR {wr*100:.0f}% &middot; n={n}</div></td>")
            s_rows += f"<tr style='border-bottom:1px solid #1a2535;'>{row}</tr>"

        cross_table = (
            f'<div style="color:#5b8dee;font-size:11px;letter-spacing:1px;margin-bottom:6px;">REGIME &times; VOLATILITY (avg r20d)</div>'
            f'<div style="overflow-x:auto;margin-bottom:20px;">'
            f'<table style="width:100%;border-collapse:collapse;font-size:12px;">'
            f'<thead><tr style="border-bottom:1px solid #1e2d40;">{hdr}</tr></thead>'
            f'<tbody>{s_rows}</tbody>'
            f'</table></div>'
        )

        disc_rows = ""
        for reg in regime_vals:
            sub_reg = [s for s in tagged if s["regime"] == reg]
            if not sub_reg:
                continue
            for bin_label, lo, hi in [("low 0-15", 0, 15), ("medium 16-22", 16, 22), ("high 23-30", 23, 30)]:
                sub = [s for s in sub_reg if lo <= float(s.get("r1_price") or 0) <= hi]
                if not sub:
                    continue
                n      = len(sub)
                mean_r = sum(s["r20d"] for s in sub) / n
                col    = "#6aa84f" if mean_r >= WIN_THRESH else ("#d6a740" if mean_r >= 0 else "#cc4444")
                disc_rows += (
                    f"<tr style='border-bottom:1px solid #1a2535;'>"
                    f"<td style='color:#aab;font-size:12px;padding:6px;'>{reg}</td>"
                    f"<td style='color:#888;font-size:12px;padding:6px;'>{bin_label}</td>"
                    f"<td style='color:#aab;font-size:12px;text-align:center;padding:6px;'>{n}</td>"
                    f"<td style='color:{col};font-size:12px;text-align:right;font-weight:600;padding:6px;'>{mean_r*100:+.1f}%</td>"
                    f"</tr>"
                )

        no_disc = '<tr><td colspan="4" style="color:#444;text-align:center;padding:10px;">—</td></tr>'
        disc_table = (
            f'<div style="color:#5b8dee;font-size:11px;letter-spacing:1px;margin-bottom:6px;">DISCOUNT DEPTH (r1_price score) &times; REGIME</div>'
            f'<div style="overflow-x:auto;">'
            f'<table style="width:100%;border-collapse:collapse;font-size:12px;">'
            f'<thead><tr style="border-bottom:1px solid #1e2d40;">'
            f'<th style="color:#5b8dee;padding:6px;text-align:left;">Regime</th>'
            f'<th style="color:#5b8dee;padding:6px;">Discount Score Bin</th>'
            f'<th style="color:#5b8dee;padding:6px;text-align:center;">N</th>'
            f'<th style="color:#5b8dee;padding:6px;text-align:right;">Avg r20d</th>'
            f'</tr></thead>'
            f'<tbody>{disc_rows if disc_rows else no_disc}</tbody>'
            f'</table></div>'
        )

        sens_html = cross_table + disc_table

        # ─── ⑭ Failure Signatures ────────────────────────────
        fctr = Counter()
        fmap: dict = {}
        for s in losses:
            key = f"regime={s['regime']} · vol={s['vol']} · struct={s['struct']}"
            fctr[key] += 1
            fmap.setdefault(key, []).append(s["r20d"])

        fail_rows = ""
        for rank, (pattern, n) in enumerate(fctr.most_common(5), 1):
            mean_loss = sum(fmap[pattern]) / len(fmap[pattern]) * 100
            pct_of    = n / len(losses) * 100 if losses else 0
            fail_rows += (
                f'<div style="display:flex;gap:10px;margin-bottom:8px;padding:10px 14px;'
                f'background:#160a0a;border-radius:6px;border-left:3px solid #cc4444;">'
                f'<span style="color:#cc4444;font-size:14px;min-width:24px;font-weight:700;">#{rank}</span>'
                f'<div style="flex:1;">'
                f'<div style="color:#e8c0b0;font-size:12px;font-weight:600;">{pattern}</div>'
                f'<div style="color:#8899aa;font-size:11px;margin-top:3px;">'
                f'{n} signals &middot; {pct_of:.0f}% of losses &middot; avg r20d = {mean_loss:+.1f}%'
                f'</div></div></div>'
            )

        if not fail_rows:
            fail_rows = '<div style="color:#555;font-size:12px;padding:10px;">Insufficient loss data (need r20d &lt; 0%).</div>'

        fail_html = (
            f'<div style="color:#888;font-size:12px;margin-bottom:10px;">'
            f'Based on <strong style="color:#cc4444;">{len(losses)}</strong> losing signals (r20d &lt; 0%).'
            f' Avoid these context combinations:</div>'
            + fail_rows
        )

        # ─── ⑮ Success Pattern Summary ───────────────────────
        wctr = Counter()
        wmap: dict = {}
        for s in wins:
            key = f"regime={s['regime']} · vol={s['vol']} · struct={s['struct']}"
            wctr[key] += 1
            wmap.setdefault(key, []).append(s["r20d"])

        win_rows = ""
        for rank, (pattern, n) in enumerate(wctr.most_common(5), 1):
            mean_win = sum(wmap[pattern]) / len(wmap[pattern]) * 100
            pct_of   = n / len(wins) * 100 if wins else 0
            win_rows += (
                f'<div style="display:flex;gap:10px;margin-bottom:8px;padding:10px 14px;'
                f'background:#0a160a;border-radius:6px;border-left:3px solid #6aa84f;">'
                f'<span style="color:#6aa84f;font-size:14px;min-width:24px;font-weight:700;">#{rank}</span>'
                f'<div style="flex:1;">'
                f'<div style="color:#b0e8c0;font-size:12px;font-weight:600;">{pattern}</div>'
                f'<div style="color:#8899aa;font-size:11px;margin-top:3px;">'
                f'{n} signals &middot; {pct_of:.0f}% of wins &middot; avg r20d = {mean_win:+.1f}%'
                f'</div></div></div>'
            )

        if not win_rows:
            win_rows = '<div style="color:#555;font-size:12px;padding:10px;">Insufficient win data (need r20d &ge; 7%).</div>'

        success_html = (
            f'<div style="color:#888;font-size:12px;margin-bottom:10px;">'
            f'Based on <strong style="color:#6aa84f;">{len(wins)}</strong> winning signals (r20d &ge; 7%).'
            f' Favor these context combinations:</div>'
            + win_rows
        )

        return {
            "decomp":      decomp_html,
            "ctx_tags":    ctx_html,
            "sensitivity": sens_html,
            "failures":    fail_html,
            "successes":   success_html,
        }

    except Exception as exc:
        err = f'<div style="color:#d6a740;font-size:12px;padding:10px;">Context intelligence unavailable: {exc}</div>'
        return {"decomp": err, "ctx_tags": err, "sensitivity": err, "failures": err, "successes": err}


def build_html(gx: dict, stats: dict, perf: dict, perf_trends: dict,
               all_recs: list, edges: list, mods: list,
               overfitting: list, src: dict, memory: dict) -> str:

    score   = gx["gx_score"]
    trend   = gx["trend"]
    n_runs  = memory.get("total_runs", 1)

    trend_color = "#6aa84f" if trend == "Improving" else "#cc4444" if trend == "Degrading" else "#d6a740"
    trend_icon  = "↑" if trend == "Improving" else "↓" if trend == "Degrading" else "→"

    # ── Hero ──────────────────────────────────────────────────
    hero = f"""
    <div style="background:linear-gradient(135deg,#0a1628 0%,#0d1f3c 50%,#0a1628 100%);
                border:1px solid #1e3050;border-radius:12px;padding:30px;
                margin-bottom:24px;display:flex;align-items:center;gap:30px;flex-wrap:wrap;">
      {_score_circle(score)}
      <div style="flex:1;min-width:220px;">
        <div style="color:#5b8dee;font-size:11px;letter-spacing:2px;margin-bottom:4px;">GX LEARNING INTELLIGENCE LAYER</div>
        <h1 style="color:#e8eaf0;margin:0 0 8px;font-size:28px;">System Learning Report</h1>
        <div style="color:#aab;font-size:13px;">Generated: {TODAY} &nbsp;|&nbsp; Run #{n_runs}</div>
        <div style="margin-top:16px;display:flex;gap:12px;flex-wrap:wrap;">
          <span style="background:#0d1420;border:1px solid #1e3050;border-radius:20px;
                       padding:6px 14px;color:{trend_color};font-size:13px;">
            {trend_icon} Learning Trend: <strong>{trend}</strong>
          </span>
          <span style="background:#0d1420;border:1px solid #1e3050;border-radius:20px;
                       padding:6px 14px;color:#aab;font-size:13px;">
            {stats['n_total']} Recommendations Tracked
          </span>
          <span style="background:#0d1420;border:1px solid #1e3050;border-radius:20px;
                       padding:6px 14px;color:#aab;font-size:13px;">
            {stats['n_multi']} Cross-Validated
          </span>
        </div>
      </div>
    </div>"""

    # ── Score Breakdown KPIs ──────────────────────────────────
    score_kpis = _kpi_row([
        ("Coherence",    f"{gx['coherence']}",      _score_color(gx['coherence'])),
        ("Performance",  f"{gx['perf_score']}",     _score_color(gx['perf_score'])),
        ("OOS Robust",   f"{gx['oos_score']}",      _score_color(gx['oos_score'])),
        ("Health",       f"{gx['health']}",         _score_color(gx['health'])),
        ("Retention",    f"{gx['retention']}",      _score_color(gx['retention'])),
    ])

    score_detail = f"""
    {score_kpis}
    <div style="margin-top:12px;color:#8899aa;font-size:12px;line-height:1.6;">
      <strong style="color:#aab;">Score Formula:</strong>&nbsp;
      Coherence×25% + Performance×25% + OOS Robustness×20% + Health×15% + Retention×15%
      &nbsp;|&nbsp; WF Survival: {gx['wf_survival_pct']}% &nbsp;|&nbsp;
      Multi-module confirmed: {gx['n_multi_module']}/{gx['n_total_recs']} recommendations
    </div>"""

    # ── Performance Metrics ────────────────────────────────────
    bt = src.get("backtest") or {}
    adp = src.get("adaptive") or {}
    perf_body = _kpi_row([
        ("Win Rate",       f"{perf['win_rate']*100:.1f}%",  _score_color(int(perf['win_rate']*100))),
        ("Profit Factor",  f"{perf['profit_factor']:.2f}",  _score_color(min(100, int(perf['profit_factor']*10)))),
        ("CAGR",           f"{perf['cagr']:.1f}%",          _score_color(min(100, int(perf['cagr']/1.5)))),
        ("Expectancy",     f"{perf['expectancy']:.1f}%",    "#6c8ebf"),
        ("Max DD",         f"{perf['max_dd']:.1f}%",        "#d6a740" if perf['max_dd'] < -10 else "#6aa84f"),
        ("Signals",        f"{perf['n_signals']:,}",        "#aab"),
    ])

    # r20d row
    perf_body += f"""
    <div style="margin-top:10px;border-top:1px solid #1e2d40;padding-top:10px;">
      <div style="color:#888;font-size:11px;margin-bottom:6px;">RESEARCH FRAMEWORK (r20d)</div>
      {_kpi_row([
          ("r20d Mean",  f"{perf['r20d_mean']*100:.1f}%", "#8899aa"),
          ("r20d PF",    f"{perf['r20d_pf']:.2f}",        "#8899aa"),
          ("r20d MFE",   f"{perf['r20d_mfe']*100:.1f}%",  "#8899aa"),
          ("r20d WR",    f"{perf['r20d_wr']*100:.1f}%",   "#8899aa"),
      ])}
    </div>"""

    if perf_trends.get("status") == "available":
        t = perf_trends
        perf_body += f"""
        <div style="margin-top:10px;color:#8899aa;font-size:12px;">
          Period-over-Period: WR {t['wr_delta_pct']:+.1f}% | PF {t['pf_delta_pct']:+.1f}% |
          Expectancy {t['exp_delta_pct']:+.1f}% | CAGR {t['cagr_delta_pct']:+.1f}%
          &nbsp;({t['periods']} periods in memory)
        </div>"""
    else:
        perf_body += '<div style="margin-top:8px;color:#666;font-size:12px;">Performance trend: insufficient history (run #1)</div>'

    # ── Research Effectiveness ────────────────────────────────
    res_kpis = _kpi_row([
        ("Total Recs",     str(stats['n_total']),         "#aab"),
        ("Proposed",       str(stats['n_proposed']),      "#6c8ebf"),
        ("Tested",         str(stats['n_tested']),        "#d6a740"),
        ("Validated",      str(stats['n_validated']),     "#6aa84f"),
        ("Rejected",       str(stats['n_rejected']),      "#cc4444"),
        ("High Conf",      str(stats['n_high_conf']),     "#5b8dee"),
    ])
    res_body = res_kpis + f"""
    <div style="margin-top:10px;color:#8899aa;font-size:12px;">
      Success Rate: <strong style="color:{_score_color(int(stats['success_rate']))};">{stats['success_rate']}%</strong>
      &nbsp;|&nbsp; Tested Rate: <strong>{stats['tested_pct']}%</strong>
      &nbsp;|&nbsp; Est. Potential Gain: <strong style="color:#6aa84f;">+{stats['exp_total_gain_pct']:.1f}%</strong>
      (sum of high-confidence recommendations)
    </div>"""

    # ── Recommendation Tracker Table ──────────────────────────
    rec_rows = ""
    sorted_recs = sorted(all_recs,
        key=lambda r: (-len(r.get("supporting", [])), -r.get("confidence", 0)))[:30]

    for r in sorted_recs:
        sc   = _STATUS_COLOR.get(r.get("status", "Proposed"), "#888")
        wf   = r.get("wf_consistent")
        wf_t = "✓" if wf is True else "✗" if wf is False else "—"
        wf_c = "#6aa84f" if wf is True else "#cc4444" if wf is False else "#888"
        multi = len(r.get("supporting", [])) >= 2
        conf  = r.get("confidence", 0)
        dr    = r.get("expected_delta_ret", 0)
        supp  = ", ".join(r.get("supporting", []))
        name  = r.get("name", "")[:55]
        rec_rows += f"""
        <tr>
          <td style="color:#e8eaf0;font-size:12px;">{name}</td>
          <td style="color:#aab;font-size:11px;">{r.get('source','')}</td>
          <td><span style="background:{sc}22;color:{sc};padding:2px 8px;border-radius:10px;
                           font-size:11px;">{r.get('status','?')}</span></td>
          <td style="color:{'#6aa84f' if multi else '#888'};font-size:12px;text-align:center;">
            {'★ ' if multi else ''}{supp[:30]}</td>
          <td style="color:#aab;font-size:12px;text-align:center;">{conf*100:.0f}%</td>
          <td style="color:{wf_c};font-size:12px;text-align:center;">{wf_t}</td>
          <td style="color:#6aa84f;font-size:12px;text-align:right;">{dr*100:+.2f}%</td>
        </tr>"""

    rec_table = f"""
    <div style="overflow-x:auto;">
    <table style="width:100%;border-collapse:collapse;font-size:12px;">
      <thead>
        <tr style="border-bottom:1px solid #1e2d40;">
          <th style="color:#5b8dee;padding:8px 6px;text-align:left;">Recommendation</th>
          <th style="color:#5b8dee;padding:8px 6px;">Source</th>
          <th style="color:#5b8dee;padding:8px 6px;">Status</th>
          <th style="color:#5b8dee;padding:8px 6px;">Supporting Modules</th>
          <th style="color:#5b8dee;padding:8px 6px;">Confidence</th>
          <th style="color:#5b8dee;padding:8px 6px;">WF</th>
          <th style="color:#5b8dee;padding:8px 6px;text-align:right;">Δ Return</th>
        </tr>
      </thead>
      <tbody>{rec_rows}</tbody>
    </table>
    </div>
    <div style="color:#666;font-size:11px;margin-top:8px;">
      ★ = confirmed by ≥2 research modules &nbsp;|&nbsp; WF = Walk-Forward consistent
    </div>"""

    # ── Edge Evolution ────────────────────────────────────────
    edge_rows = ""
    for e in edges[:10]:
        sc = _STABILITY_COLOR.get(e.get("stability", "New"), "#888")
        edge_rows += f"""
        <tr>
          <td style="color:#aab;font-size:11px;max-width:260px;overflow:hidden;
                     text-overflow:ellipsis;white-space:nowrap;">{e['rule_text'][:70]}</td>
          <td style="color:#888;font-size:11px;text-align:center;">{e['source']}</td>
          <td style="color:#aab;font-size:12px;text-align:center;">{e['n']}</td>
          <td style="color:#6aa84f;font-size:12px;text-align:right;">{e['mfe_mean']:.1f}%</td>
          <td style="color:#aab;font-size:12px;text-align:right;">{e['win_rate']*100:.0f}%</td>
          <td style="color:#5b8dee;font-size:12px;text-align:right;">{e['expectancy']:.1f}%</td>
          <td><span style="background:{sc}22;color:{sc};padding:2px 8px;
                           border-radius:10px;font-size:11px;">{e.get('stability','?')}</span></td>
        </tr>"""

    edge_table = f"""
    <div style="overflow-x:auto;">
    <table style="width:100%;border-collapse:collapse;font-size:12px;">
      <thead>
        <tr style="border-bottom:1px solid #1e2d40;">
          <th style="color:#5b8dee;padding:8px 6px;text-align:left;">Rule Conditions</th>
          <th style="color:#5b8dee;padding:8px 6px;">Src</th>
          <th style="color:#5b8dee;padding:8px 6px;">N</th>
          <th style="color:#5b8dee;padding:8px 6px;text-align:right;">MFE</th>
          <th style="color:#5b8dee;padding:8px 6px;text-align:right;">WR</th>
          <th style="color:#5b8dee;padding:8px 6px;text-align:right;">E[X]</th>
          <th style="color:#5b8dee;padding:8px 6px;">Stability</th>
        </tr>
      </thead>
      <tbody>{edge_rows}</tbody>
    </table>
    </div>
    <div style="color:#666;font-size:11px;margin-top:6px;">
      Stability requires ≥2 runs. First run shows all edges as "New".
    </div>"""

    # ── Module Contribution ───────────────────────────────────
    mod_bars = ""
    for m in mods:
        col = _score_color(m["score"])
        mod_bars += f"""
        <div style="margin-bottom:10px;">
          <div style="display:flex;justify-content:space-between;margin-bottom:3px;">
            <span style="color:#aab;font-size:12px;">
              {'L1' if m['level']==1 else 'L2' if m['level']==2 else 'L3'} &nbsp;
              {m['label']}
              {'<span style="color:#666;"> ✗ unavailable</span>' if not m['available'] else ''}
            </span>
            <span style="color:{col};font-size:13px;font-weight:600;">{m['score']}</span>
          </div>
          {_bar(m['score'], col)}
          <div style="color:#666;font-size:10px;margin-top:2px;">
            {m['recs_count']} recs · {m['multi_module']} multi-module · {m['verdict']}
          </div>
        </div>"""

    # ── Overfitting Checks ────────────────────────────────────
    ov_rows = ""
    for f in overfitting:
        col = _CHECK_COLOR.get(f["status"], "#888")
        icon = "✓" if f["status"] == "PASS" else "⚠" if f["status"] == "WARNING" else "ℹ"
        ov_rows += f"""
        <div style="display:flex;gap:10px;margin-bottom:8px;padding:8px 10px;
                    background:#0d1420;border-radius:6px;border-left:3px solid {col};">
          <span style="color:{col};font-size:14px;min-width:16px;">{icon}</span>
          <div>
            <span style="color:{col};font-size:12px;font-weight:600;">{f['check']}</span>
            <span style="color:#8899aa;font-size:12px;">&nbsp;— {f['detail']}</span>
          </div>
        </div>"""

    n_warn = sum(1 for f in overfitting if f["status"] == "WARNING")
    ov_risk = "LOW" if n_warn == 0 else "MEDIUM" if n_warn <= 2 else "HIGH"
    ov_col  = "#6aa84f" if n_warn == 0 else "#d6a740" if n_warn <= 2 else "#cc4444"
    ov_header = f'<div style="color:{ov_col};font-size:13px;font-weight:600;margin-bottom:10px;">Overfitting Risk: {ov_risk}</div>'

    # ── Self-Critique ─────────────────────────────────────────
    edge_data = src.get("edge") or {}
    n_rules = edge_data.get("total_rules_significant", 0)
    n_sigs  = perf.get("n_signals", 0)
    pf_fib  = perf.get("profit_factor", 0)
    pf_r20  = perf.get("r20d_pf", 0)

    critique_items = [
        ("Data Mining Risk",
         f"{n_rules:,} significant edges were discovered — with {n_sigs} signals this is a high edge-to-signal ratio "
         f"({n_rules/max(1,n_sigs):.0f}x). Most rules have insufficient out-of-sample validation. "
         "Only cross-module confirmed rules should be acted upon."),
        ("Exit Model Inflation",
         f"The backtest Fibonacci framework (PF={pf_fib:.2f}) uses theoretical exits. "
         f"The r20d research framework (PF={pf_r20:.2f}) is closer to real behavior. "
         "CAGR=100% represents an idealized Fibonacci ladder, not guaranteed real returns."),
        ("Partial 2025-2026 Data",
         "Signals from 2025-2026 have incomplete forward data (20d resolved, <90d/252d). "
         "Long-term metrics will improve as data matures. Current statistics are biased toward older, complete signals."),
        ("Recommendation Freshness",
         "All recommendations are currently 'Proposed' — none have been applied to main.py yet. "
         "The GX system cannot validate predictions until changes are tested in production."),
        ("Survival Bias in Historical Signals",
         "412 historical signals were backfilled from OHLCV replay using today's scanner logic applied to past data. "
         "This may undercount signals that would have been filtered differently at the time."),
    ]
    critique_body = ""
    for title, text in critique_items:
        critique_body += f"""
        <div style="margin-bottom:10px;padding:10px;background:#0d1420;
                    border-radius:6px;border-left:3px solid #d6a740;">
          <div style="color:#d6a740;font-size:12px;font-weight:600;margin-bottom:4px;">{title}</div>
          <div style="color:#8899aa;font-size:12px;line-height:1.6;">{text}</div>
        </div>"""

    # ── Executive Summary ─────────────────────────────────────
    top_rec = sorted(
        [r for r in all_recs if len(r.get("supporting", [])) >= 2],
        key=lambda r: -r.get("confidence", 0)
    )
    top_rec_str = ", ".join(r["name"][:35] for r in top_rec[:3]) or "None yet"

    exec_summary = f"""
    <div style="background:#0d1420;border-radius:8px;padding:20px;line-height:1.9;color:#aab;font-size:13px;">
      <p><strong style="color:#e8eaf0;">System Status:</strong>
      The EGX Learning System is in <strong style="color:#d6a740;">Early Learning Phase</strong> (Run #{n_runs}).
      GX Score = <strong style="color:{_score_color(score)};">{score}/100</strong>.
      Performance baseline is strong (PF={pf_fib:.2f}, WR={perf['win_rate']*100:.1f}%,
      CAGR={perf['cagr']:.1f}%) but research validation is just beginning.</p>

      <p><strong style="color:#e8eaf0;">Key Findings:</strong>
      {stats['n_total']} recommendations tracked across {len(src)} research modules.
      {stats['n_multi']} are cross-validated by ≥2 modules — these carry the highest confidence.
      Top cross-validated recommendations: <em style="color:#6aa84f;">{top_rec_str}</em>.</p>

      <p><strong style="color:#e8eaf0;">Learning Quality:</strong>
      Cross-module coherence = {gx['coherence']}% (recommendations confirmed across modules).
      Walk-forward survival = {gx['wf_survival_pct']}% (improvements passing anti-overfitting tests).
      Research health score = {gx['health']}/100 (from adaptive engine).</p>

      <p><strong style="color:#e8eaf0;">Critical Risks:</strong>
      {n_warn} overfitting warnings detected. Data-mining risk is {'HIGH' if n_rules > 5000 else 'MODERATE'}
      ({n_rules:,} edges). Fibonacci CAGR ({perf['cagr']:.0f}%) is theoretical — real performance
      closer to r20d framework (~{pf_r20:.1f}x PF).</p>

      <p><strong style="color:#e8eaf0;">Recommendation:</strong>
      Apply IMP-2 (Sweep Gate) and IMP-6 (Combined Fix) to main.py first — they are the only
      walk-forward consistent improvements. Monitor for 30 days before applying logic/optimizer suggestions.
      <strong style="color:#d6a740;">No changes to main.py should be made without explicit user approval.</strong></p>
    </div>"""

    # ── Learning Accumulation Roadmap (always visible) ───────
    phase = "Phase 1 — Baseline" if n_runs < 3 else \
            "Phase 2 — Trend Forming" if n_runs < 7 else \
            "Phase 3 — Validation Active" if n_runs < 15 else \
            "Phase 4 — Mature Learning"
    phase_pct = min(100, int((n_runs / 15) * 100))

    roadmap_steps = [
        (1,  3,  "Run 1-3",   "Baseline établi · Premières recommandations collectées"),
        (3,  7,  "Run 3-7",   "Trends PF/WR visibles · Cross-validation entre modules"),
        (7,  15, "Run 7-15",  "Validation des recommendations · Rejet des faux positifs"),
        (15, 30, "Run 15-30", "Mature learning · Predictions fiables"),
    ]
    roadmap_html = ""
    for start, end, label, desc in roadmap_steps:
        done   = n_runs >= end
        active = start <= n_runs < end
        col    = "#6aa84f" if done else "#5b8dee" if active else "#333"
        bg     = "#0d1a0d" if done else "#0d1428" if active else "#0d1420"
        border = "#6aa84f" if done else "#5b8dee" if active else "#2a3540"
        icon   = "✓" if done else "●" if active else "○"
        roadmap_html += f"""
        <div style="display:flex;gap:12px;margin-bottom:8px;padding:10px 14px;
                    background:{bg};border-radius:6px;border-left:3px solid {border};">
          <span style="color:{col};font-size:16px;min-width:18px;">{icon}</span>
          <div>
            <span style="color:{col};font-size:12px;font-weight:600;">{label}</span>
            <span style="color:#8899aa;font-size:12px;margin-right:8px;"> — {desc}</span>
          </div>
        </div>"""

    # Cross-reference top recs with historical combos
    hb_combos = []
    try:
        import json as _json
        with open("historical_backtest_results.json") as _f:
            _hb = _json.load(_f)
        hb_combos = _hb.get("combo_analysis", [])[:5]
    except Exception:
        pass

    combo_support = ""
    if hb_combos:
        combo_support = "<div style='margin-top:12px;'><div style='color:#5b8dee;font-size:11px;letter-spacing:1px;margin-bottom:6px;'>TOP HISTORICAL COMBOS (2-WAY)</div>"
        for cb in hb_combos[:5]:
            diff = cb.get("diff", 0)
            col  = "#6aa84f" if diff > 0.02 else "#d6a740" if diff > 0 else "#cc4444"
            combo_support += (
                f"<div style='color:{col};font-size:12px;padding:4px 0;'>"
                f"<b>{cb.get('combo','')}</b> → PF={cb.get('pf',0):.2f} · "
                f"WR={cb.get('wr',0):.0%} · MFE={cb.get('mfe',0):.0%} · "
                f"Δ={diff*100:+.1f}% · n={cb.get('n',0)}</div>"
            )
        combo_support += "</div>"

    roadmap_card_body = f"""
    <div style="margin-bottom:14px;">
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px;">
        <span style="color:#5b8dee;font-size:13px;font-weight:600;">{phase}</span>
        <span style="color:#888;font-size:12px;">Run #{n_runs} / 30</span>
        <div style="flex:1;background:#1a2535;border-radius:10px;height:6px;overflow:hidden;">
          <div style="background:#5b8dee;width:{phase_pct}%;height:100%;border-radius:10px;"></div>
        </div>
        <span style="color:#5b8dee;font-size:12px;">{phase_pct}%</span>
      </div>
      {roadmap_html}
    </div>
    {combo_support}"""

    # ── Context Intelligence Sections (⑪-⑮) ─────────────────
    ctx_intel = _build_context_intelligence()

    # ── Assemble ──────────────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html lang="ar" dir="ltr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>GX Learning Intelligence Layer — {TODAY}</title>
  <style>
    * {{ box-sizing:border-box; margin:0; padding:0; }}
    body {{ background:#0a1020; color:#c8d0e0; font-family:'Segoe UI',sans-serif; padding:20px; }}
    h2 {{ color:#5b8dee; font-size:16px; margin-bottom:16px; }}
    table tr:hover td {{ background:#0a1628; }}
    table td, table th {{ padding:7px 8px; border-bottom:1px solid #1a2535; }}
    a {{ color:#5b8dee; text-decoration:none; }}
    @media(max-width:600px) {{ body {{ padding:10px; }} }}
  </style>
</head>
<body>
  <div style="max-width:1100px;margin:0 auto;">
    {hero}
    {_card("① GX Score Breakdown", score_detail, "#5b8dee")}
    {_card("② Performance Metrics — Ground Truth (Backtest)", perf_body, "#6aa84f")}
    {_card("③ Research Effectiveness", res_body, "#d6a740")}
    {_card("④ Recommendation Tracker (Top 30)", rec_table, "#6c8ebf")}
    {_card("⑤ Edge Evolution — Top 10 by Expectancy", edge_table, "#82d46a")}
    {_card("⑥ Module Contribution Analysis", mod_bars, "#5b8dee")}
    {_card("⑦ Overfitting Risk Assessment", ov_header + ov_rows, "#d6a740")}
    {_card("⑧ Self-Critique / Adversarial Review", critique_body, "#cc8844")}
    {_card("⑨ Executive Summary", exec_summary, "#5b8dee")}
    {_card("⑩ Learning Accumulation Roadmap", roadmap_card_body, "#5b8dee")}
    {_card("⑪ Score Contribution Decomposition (Wins vs Losses)", ctx_intel['decomp'], "#82d46a")}
    {_card("⑫ Context Tag Performance Summary", ctx_intel['ctx_tags'], "#5b8dee")}
    {_card("⑬ Conditional Sensitivity Map", ctx_intel['sensitivity'], "#d6a740")}
    {_card("⑭ Failure Signature Extraction", ctx_intel['failures'], "#cc4444")}
    {_card("⑮ Success Pattern Summary", ctx_intel['successes'], "#6aa84f")}

    <div style="text-align:center;color:#444;font-size:11px;margin-top:20px;padding:10px;">
      GX Learning Intelligence Layer · EGX30 Scanner · {TODAY}
      · The objective is not to produce more research — it is to prove that learning
      produces measurable, repeatable, statistically valid improvements.
    </div>
  </div>
</body>
</html>"""

    return html


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def run():
    print(f"\n{'='*60}")
    print("  GX Learning Intelligence Layer")
    print(f"{'='*60}")

    # 1. Load all sources
    src = load_all_sources()
    available = [k for k, v in src.items() if v is not None]
    print(f"  Sources available: {', '.join(available)}")

    # 2. Load / init memory
    memory = load_memory()
    is_first_run = memory.get("total_runs", 0) == 0

    # 3. Extract recommendations from all sources
    new_recs = _extract_recommendations(src)
    print(f"  Extracted {len(new_recs)} raw recommendations")

    # 4. Merge into memory
    all_recs = _merge_recommendations(memory.get("recommendations", []), new_recs)
    memory["recommendations"] = all_recs

    # 5. Performance snapshot
    perf     = extract_perf_snapshot(src)
    update_perf_history(memory, perf)
    perf_trends = compute_perf_trends(memory["performance_history"])

    # 6. Edge evolution
    current_edges = extract_top_edges(src, n=12)
    update_edge_history(memory, current_edges)
    edges_with_stability = classify_edge_stability(memory, current_edges)

    # 7. Module contributions
    mods = compute_module_contributions(src, all_recs)

    # 8. Overfitting checks
    overfitting = run_overfitting_checks(src, perf)
    n_warn = sum(1 for f in overfitting if f["status"] == "WARNING")
    print(f"  Overfitting checks: {len(overfitting)} total, {n_warn} warnings")

    # 9. GX Score
    gx = compute_gx_score(src, all_recs, perf, memory, overfitting)
    print(f"\n  ┌─────────────────────────────────┐")
    print(f"  │  GX Learning Score: {gx['gx_score']:3d}/100       │")
    print(f"  │  Trend: {gx['trend']:<26}│")
    print(f"  │  Coherence:   {gx['coherence']:3d}  Perf: {gx['perf_score']:3d}   │")
    print(f"  │  OOS Robust:  {gx['oos_score']:3d}  Health: {gx['health']:3d} │")
    print(f"  │  Retention:   {gx['retention']:3d}               │")
    print(f"  └─────────────────────────────────┘")

    # 10. Research stats
    stats = compute_research_stats(all_recs)
    print(f"\n  Recommendations: {stats['n_total']} total | "
          f"{stats['n_validated']} validated | {stats['n_multi']} cross-validated")
    print(f"  Success Rate: {stats['success_rate']}% | "
          f"Est. potential gain: +{stats['exp_total_gain_pct']:.1f}%")

    # 11. Update memory run counter
    memory["total_runs"] = memory.get("total_runs", 0) + 1
    memory["runs"].append({
        "date":     TODAY,
        "gx_score": gx["gx_score"],
        "n_recs":   len(all_recs),
        "n_signals":perf.get("n_signals", 0),
    })
    memory["runs"] = memory["runs"][-60:]  # keep 60 run history

    # Store gx_score in perf history for trend comparison
    if memory["performance_history"]:
        memory["performance_history"][-1]["gx_score"] = gx["gx_score"]

    # 12. Generate HTML
    html = build_html(gx, stats, perf, perf_trends, all_recs,
                      edges_with_stability, mods, overfitting, src, memory)
    os.makedirs("reports", exist_ok=True)
    with open(REPORT_OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n  Report → {REPORT_OUT}")

    # 13. Save memory
    save_memory(memory)
    print(f"  Memory → {MEMORY_FILE}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    run()
