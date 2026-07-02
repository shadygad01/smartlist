"""
Discount Zone Pattern Miner
============================
Discovers hidden structures, correlations, and behavioral patterns
specifically inside discount zone conditions.

Does NOT change discount zone definitions or SMC logic.
Only adds pattern intelligence ON TOP of existing signals.

Reads:
  egx_research.db  (v_all_signals — discount zone signals subset)
  decision_engine_results.json  (for integration)
  gx_learning_memory.json

Writes:
  discount_zone_patterns.json
  reports/discount_zone_report_YYYY-MM-DD.html

Usage:
  python discount_zone_miner.py
"""
# Constitution §AUTOMATIC ARCHIVING RULE — Research only; no path to production without r1-r8 mapping
RESEARCH_ONLY_LAB = True

import json
import math
import os
import sqlite3
from collections import Counter, defaultdict
from datetime import date

TODAY      = date.today().isoformat()
DB_PATH    = "egx_research.db"
MEMORY_FILE = "discount_zone_patterns.json"
REPORT_OUT = f"reports/discount_zone_report_{TODAY}.html"

# Discount zone threshold: r1_price >= this value
# r1_price is 0-30; >= 18 = at least 60% of max discount score
DISC_MIN_R1 = 18

WIN_THRESH  = 0.07
LOSS_THRESH = 0.0

# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

def _jload(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def _tag(s):
    """4-dimensional context tag (identical to gx_learning_layer logic)."""
    ht_hl = int(s.get("htf_hl") or 0)
    ht_hh = int(s.get("htf_hh") or 0)
    regime = "trend" if ht_hl else ("range" if (ht_hh == 0 and ht_hl == 0) else "mixed")

    r6 = float(s.get("r6_macd") or 0)
    r7 = float(s.get("r7_div")  or 0)
    md = int(s.get("macd_div")  or 0)
    rd = int(s.get("rsi_div")   or 0)
    vol = "high" if (r6+r7 >= 8 and (md or rd)) else ("low" if r6+r7 <= 4 else "medium")

    sw = int(s.get("sweep_detected")  or 0)
    eq = int(s.get("equal_lows")      or 0)
    wk = int(s.get("wick_rejection")  or 0)
    struct = ("expansion"   if sw else
              "compression" if eq else
              "reversal"    if wk else "unknown")

    hv = int(s.get("hvn_hit") or 0)
    sv = int(s.get("sv_hit")  or 0)
    r3 = float(s.get("r3_liquidity") or 0)
    liq = "strong" if (hv or sv) else ("moderate" if r3 >= 7 else "weak")
    return regime, vol, struct, liq


def _cluster_stats(signals):
    """Compute performance statistics for a group of signals."""
    n = len(signals)
    resolved = [s for s in signals if s.get("r20d") is not None]
    nr = len(resolved)
    if nr == 0:
        return {"n": n, "n_resolved": 0, "wr": 0.0, "pf": 0.0,
                "mean_r20d": 0.0, "mean_mfe": 0.0, "mean_mae": 0.0}
    r20ds = [float(s["r20d"]) for s in resolved]
    mfes  = [float(s["mfe_20d"]) for s in resolved if s.get("mfe_20d") is not None]
    maes  = [float(s["mae_20d"]) for s in resolved if s.get("mae_20d") is not None]
    wins  = [r for r in r20ds if r >= WIN_THRESH]
    gw    = sum(r for r in r20ds if r > 0)
    gl    = abs(sum(r for r in r20ds if r < 0))
    return {
        "n":          n,
        "n_resolved": nr,
        "wr":         round(len(wins) / nr, 4),
        "pf":         round(gw / gl, 3) if gl > 0 else (99.0 if gw > 0 else 0.0),
        "mean_r20d":  round(sum(r20ds) / nr, 4),
        "mean_mfe":   round(sum(mfes) / len(mfes), 4) if mfes else 0.0,
        "mean_mae":   round(sum(maes) / len(maes), 4) if maes else 0.0,
    }


# ═══════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════

def load_discount_signals():
    """Load signals where r1_price >= DISC_MIN_R1 (deep in discount zone)."""
    if not os.path.exists(DB_PATH):
        return []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT * FROM v_all_signals
        WHERE COALESCE(r1_price, 0) >= ?
        ORDER BY signal_date DESC
    """, (DISC_MIN_R1,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def load_all_signals():
    """Load all signals for baseline comparison."""
    if not os.path.exists(DB_PATH):
        return []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM v_all_signals ORDER BY signal_date DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════════
# 1. CROSS-TRADE CLUSTERING
# ═══════════════════════════════════════════════════════════════

def build_clusters(signals):
    """
    Cluster discount zone signals by full context signature.
    Returns list of cluster dicts, sorted by mean_r20d desc.
    """
    buckets = defaultdict(list)
    for s in signals:
        regime, vol, struct, liq = _tag(s)
        key = (regime, vol, struct, liq)
        buckets[key].append(s)

    clusters = []
    for (regime, vol, struct, liq), bucket in buckets.items():
        stats = _cluster_stats(bucket)
        if stats["n_resolved"] < 5:
            continue
        pattern_type = (
            "discount_zone_success" if stats["wr"] >= 0.55 and stats["mean_r20d"] >= WIN_THRESH else
            "discount_zone_failure" if stats["wr"] < 0.38 or stats["mean_r20d"] < 0 else
            "mixed"
        )
        clusters.append({
            "pattern_id":   f"DZ_{regime.upper()}_{vol.upper()}_{struct.upper()}_{liq.upper()}",
            "pattern_type": pattern_type,
            "context_signature": {
                "market_regime":    regime,
                "volatility_state": vol,
                "structure_state":  struct,
                "liquidity_state":  liq,
            },
            "stats":       stats,
            "symbols":     sorted({s.get("symbol","") for s in bucket})[:8],
        })

    clusters.sort(key=lambda c: c["stats"]["mean_r20d"], reverse=True)
    return clusters


# ═══════════════════════════════════════════════════════════════
# 2. HIDDEN CORRELATIONS
# ═══════════════════════════════════════════════════════════════

def compute_correlations(signals):
    """
    Pearson correlation of each binary/numeric flag with r20d,
    specifically within discount zone signals.
    """
    FLAG_COLS = [
        "sweep_detected", "wick_rejection", "equal_lows",
        "htf_hh", "htf_hl", "rsi_div", "macd_div",
        "sv_hit", "hvn_hit", "price_ok",
        "r2_ob", "r3_liquidity", "r4_htf", "r5_avwap",
        "r6_macd", "r7_div", "r8_demand",
    ]

    resolved = [s for s in signals if s.get("r20d") is not None]
    if len(resolved) < 10:
        return []

    r20ds = [float(s["r20d"]) for s in resolved]
    mean_r = sum(r20ds) / len(r20ds)
    var_r  = sum((r - mean_r) ** 2 for r in r20ds)

    correlations = []
    for col in FLAG_COLS:
        vals = [float(s.get(col) or 0) for s in resolved]
        mean_v = sum(vals) / len(vals)
        var_v  = sum((v - mean_v) ** 2 for v in vals)
        cov    = sum((vals[i] - mean_v) * (r20ds[i] - mean_r)
                     for i in range(len(vals)))
        denom  = math.sqrt(var_r * var_v)
        corr   = round(cov / denom, 4) if denom > 0 else 0.0
        correlations.append({
            "feature":     col,
            "correlation": corr,
            "direction":   "positive" if corr > 0 else "negative",
            "strength":    ("strong"   if abs(corr) >= 0.20 else
                            "moderate" if abs(corr) >= 0.10 else "weak"),
        })

    correlations.sort(key=lambda x: abs(x["correlation"]), reverse=True)
    return correlations


# ═══════════════════════════════════════════════════════════════
# 3. EDGE REFINEMENT (when discount zone is valid vs not)
# ═══════════════════════════════════════════════════════════════

def edge_refinement(signals, baseline_stats):
    """
    Identify discount zone conditions that outperform or underperform baseline.
    Uses r1_price depth bins + structural conditions.
    """
    baseline_mean = baseline_stats.get("mean_r20d", 0.0)
    bins = [
        ("very_deep (25-30)", lambda s: float(s.get("r1_price") or 0) >= 25),
        ("deep (20-24)",      lambda s: 20 <= float(s.get("r1_price") or 0) < 25),
        ("moderate (18-19)",  lambda s: 18 <= float(s.get("r1_price") or 0) < 20),
    ]
    struct_conditions = [
        ("with_sweep",      lambda s: int(s.get("sweep_detected") or 0) == 1),
        ("with_wick",       lambda s: int(s.get("wick_rejection") or 0) == 1),
        ("with_hvn_sv",     lambda s: (int(s.get("hvn_hit") or 0) or int(s.get("sv_hit") or 0))),
        ("with_htf_trend",  lambda s: int(s.get("htf_hl") or 0) == 1),
        ("no_struct_conf",  lambda s: (not int(s.get("sweep_detected") or 0)
                                       and not int(s.get("wick_rejection") or 0)
                                       and not int(s.get("equal_lows") or 0))),
    ]

    refinements = []
    for bin_label, bin_fn in bins:
        bin_sigs = [s for s in signals if bin_fn(s)]
        bin_stats = _cluster_stats(bin_sigs)
        if bin_stats["n_resolved"] < 5:
            continue
        diff = bin_stats["mean_r20d"] - baseline_mean
        refinements.append({
            "condition":   bin_label,
            "type":        "depth_bin",
            "stats":       bin_stats,
            "vs_baseline": round(diff, 4),
            "verdict": ("VALID — outperforms baseline"   if diff > 0.02 else
                        "DOWNGRADE — underperforms"       if diff < -0.02 else
                        "NEUTRAL — inline with baseline"),
        })

    for cond_label, cond_fn in struct_conditions:
        cond_sigs = [s for s in signals if cond_fn(s)]
        cond_stats = _cluster_stats(cond_sigs)
        if cond_stats["n_resolved"] < 5:
            continue
        diff = cond_stats["mean_r20d"] - baseline_mean
        refinements.append({
            "condition":   cond_label,
            "type":        "structural_condition",
            "stats":       cond_stats,
            "vs_baseline": round(diff, 4),
            "verdict": ("VALID — outperforms baseline"   if diff > 0.02 else
                        "DOWNGRADE — underperforms"       if diff < -0.02 else
                        "NEUTRAL — inline with baseline"),
        })

    refinements.sort(key=lambda r: r["vs_baseline"], reverse=True)
    return refinements


# ═══════════════════════════════════════════════════════════════
# 4. PATTERN EVOLUTION (stability over runs)
# ═══════════════════════════════════════════════════════════════

def track_evolution(current_clusters, prev_memory):
    """
    Compare current cluster stats to previous run.
    Returns evolution classification per cluster.
    """
    prev_clusters = {c["pattern_id"]: c for c in (prev_memory.get("clusters") or [])}
    evolution = []

    for cluster in current_clusters:
        pid  = cluster["pattern_id"]
        prev = prev_clusters.get(pid)
        if not prev:
            status = "new"
            delta_wr   = 0.0
            delta_r20d = 0.0
        else:
            delta_wr   = round(cluster["stats"]["wr"]        - prev["stats"].get("wr", 0), 4)
            delta_r20d = round(cluster["stats"]["mean_r20d"] - prev["stats"].get("mean_r20d", 0), 4)
            if delta_r20d > 0.01 and delta_wr > 0:
                status = "strengthening"
            elif delta_r20d < -0.01 and delta_wr < 0:
                status = "decaying"
            elif abs(delta_r20d) < 0.005:
                status = "stable"
            else:
                status = "fluctuating"

        evolution.append({
            "pattern_id":    pid,
            "pattern_type":  cluster["pattern_type"],
            "stability":     status,
            "delta_wr":      delta_wr,
            "delta_r20d":    delta_r20d,
        })

    return evolution


# ═══════════════════════════════════════════════════════════════
# 5. SMC DEPENDENCY ANALYSIS
# ═══════════════════════════════════════════════════════════════

def smc_dependency_analysis(signals):
    """
    For each cluster pattern, compute structural dependency scores:
    - smc_structure_dependency: how much adj_score correlates with outcome
    - liquidity_sensitivity: hvn/sv sensitivity within discount zone
    - volatility_sensitivity: regime sensitivity
    """
    resolved = [s for s in signals if s.get("r20d") is not None]
    if len(resolved) < 10:
        return {}

    r20ds = [float(s["r20d"]) for s in resolved]
    mean_r = sum(r20ds) / len(r20ds)

    def _corr_col(col):
        vals = [float(s.get(col) or 0) for s in resolved]
        mean_v = sum(vals) / len(vals)
        var_v  = sum((v - mean_v)**2 for v in vals)
        var_r  = sum((r - mean_r)**2 for r in r20ds)
        cov    = sum((vals[i]-mean_v)*(r20ds[i]-mean_r) for i in range(len(vals)))
        denom  = math.sqrt(var_r * var_v)
        return round(abs(cov / denom), 4) if denom > 0 else 0.0

    smc_dep  = _corr_col("adj_score")
    liq_sens = max(_corr_col("hvn_score"), _corr_col("sv_score"),
                   _corr_col("r3_liquidity"))
    vol_sens = max(_corr_col("r6_macd"), _corr_col("r7_div"))

    return {
        "smc_structure_dependency": smc_dep,
        "liquidity_sensitivity":    liq_sens,
        "volatility_sensitivity":   vol_sens,
    }


# ═══════════════════════════════════════════════════════════════
# HTML REPORT
# ═══════════════════════════════════════════════════════════════

def _pt_color(pt):
    return ("#6aa84f"  if pt == "discount_zone_success" else
            "#cc4444"  if pt == "discount_zone_failure" else "#d6a740")

def _sc(v, lo=0.4, hi=0.55):
    return "#6aa84f" if v >= hi else ("#d6a740" if v >= lo else "#cc4444")

def _bar(pct, color="#6c8ebf"):
    return (f'<div style="background:#1e2533;border-radius:3px;height:5px;width:100%;">'
            f'<div style="background:{color};width:{min(100,max(0,pct)):.0f}%;height:5px;border-radius:3px;"></div></div>')

def build_html(disc_signals, all_baseline, clusters, correlations,
               refinements, evolution, smc_dep):

    n_disc    = len(disc_signals)
    n_all     = all_baseline.get("n", 0)
    disc_pct  = round(n_disc / max(1, n_all) * 100, 1)
    disc_stats = _cluster_stats(disc_signals)

    # ── Section 1: Discount Zone Overview ─────────────────────
    def _kpi(items):
        cells = "".join(
            f'<div style="background:#0d1420;border-radius:6px;padding:12px;text-align:center;flex:1;min-width:110px;">'
            f'<div style="color:{c};font-size:20px;font-weight:700;font-family:monospace;">{v}</div>'
            f'<div style="color:#888;font-size:10px;margin-top:3px;text-transform:uppercase;">{l}</div></div>'
            for l, v, c in items
        )
        return f'<div style="display:flex;gap:8px;flex-wrap:wrap;">{cells}</div>'

    overview = _kpi([
        ("Disc Zone Signals",  str(n_disc),                                  "#aab"),
        ("% of All Signals",   f"{disc_pct:.0f}%",                           "#aab"),
        ("Disc Zone WR",       f"{disc_stats.get('wr',0)*100:.0f}%",         _sc(disc_stats.get('wr',0))),
        ("Disc Zone PF",       f"{disc_stats.get('pf',0):.2f}",              _sc(disc_stats.get('pf',0), 1.0, 1.5)),
        ("Disc Zone E[r20d]",  f"{disc_stats.get('mean_r20d',0)*100:+.1f}%", _sc(disc_stats.get('mean_r20d',0), 0, WIN_THRESH)),
        ("Disc Zone MFE",      f"{disc_stats.get('mean_mfe',0)*100:.1f}%",   "#6c8ebf"),
        ("Clusters Found",     str(len(clusters)),                            "#aab"),
    ])

    base_r   = all_baseline.get("mean_r20d", 0)
    disc_r   = disc_stats.get("mean_r20d", 0)
    disc_lift = disc_r - base_r
    cmp_html = (
        f'<div style="margin-top:10px;color:#8899aa;font-size:12px;">'
        f'All signals baseline: WR={all_baseline.get("wr",0)*100:.0f}% · '
        f'E[r20d]={base_r*100:+.1f}% &nbsp;|&nbsp; '
        f'Discount zone lift: <strong style="color:{"#6aa84f" if disc_lift>0 else "#cc4444"};">'
        f'{disc_lift*100:+.1f}%</strong></div>'
    )

    # ── Section 2: Clusters ────────────────────────────────────
    cluster_rows = ""
    for c in clusters[:20]:
        pt  = c["pattern_type"]
        pc  = _pt_color(pt)
        st  = c["stats"]
        ctx = c["context_signature"]
        ev  = next((e for e in evolution if e["pattern_id"] == c["pattern_id"]), {})
        stab = ev.get("stability", "—")
        stab_c = ("#6aa84f" if stab == "strengthening" else
                  "#cc4444" if stab == "decaying" else "#d6a740")
        cluster_rows += (
            f"<tr>"
            f"<td style='color:#e8eaf0;font-size:11px;font-family:monospace;'>{c['pattern_id']}</td>"
            f"<td><span style='background:{pc}22;color:{pc};padding:2px 6px;"
            f"border-radius:8px;font-size:10px;'>{pt.replace('_',' ')}</span></td>"
            f"<td style='color:#aab;font-size:11px;'>"
            f"{ctx['market_regime']}/{ctx['volatility_state']}/{ctx['structure_state'][:3]}/{ctx['liquidity_state'][:3]}</td>"
            f"<td style='color:#aab;font-size:12px;text-align:center;'>{st['n']} ({st['n_resolved']})</td>"
            f"<td style='color:{_sc(st['wr'])};font-size:12px;text-align:right;'>{st['wr']*100:.0f}%</td>"
            f"<td style='color:#aab;font-size:12px;text-align:right;'>{st['pf']:.2f}</td>"
            f"<td style='color:{_sc(st['mean_r20d'], 0, WIN_THRESH)};font-size:12px;text-align:right;font-weight:600;'>"
            f"{st['mean_r20d']*100:+.1f}%</td>"
            f"<td style='color:{stab_c};font-size:11px;text-align:center;'>{stab}</td>"
            f"</tr>"
        )

    cluster_table = (
        f'<div style="overflow-x:auto;">'
        f'<table style="width:100%;border-collapse:collapse;font-size:12px;">'
        f'<thead><tr style="border-bottom:1px solid #1e2d40;">'
        f'<th style="color:#5b8dee;padding:7px 6px;text-align:left;">Pattern ID</th>'
        f'<th style="color:#5b8dee;padding:7px 6px;">Type</th>'
        f'<th style="color:#5b8dee;padding:7px 6px;">Context</th>'
        f'<th style="color:#5b8dee;padding:7px 6px;text-align:center;">N (res.)</th>'
        f'<th style="color:#5b8dee;padding:7px 6px;text-align:right;">WR</th>'
        f'<th style="color:#5b8dee;padding:7px 6px;text-align:right;">PF</th>'
        f'<th style="color:#5b8dee;padding:7px 6px;text-align:right;">E[r20d]</th>'
        f'<th style="color:#5b8dee;padding:7px 6px;text-align:center;">Stability</th>'
        f'</tr></thead><tbody>{cluster_rows}</tbody></table></div>'
    )

    # ── Section 3: Correlations ────────────────────────────────
    corr_rows = ""
    for co in correlations[:12]:
        c    = co["correlation"]
        sc   = "#6aa84f" if c > 0 else "#cc4444"
        bar  = _bar(abs(c) * 500, sc)   # scale 0.2 corr → 100%
        corr_rows += (
            f"<tr>"
            f"<td style='color:#aab;font-size:12px;'>{co['feature']}</td>"
            f"<td style='color:{sc};font-size:12px;text-align:right;font-weight:600;'>{c:+.4f}</td>"
            f"<td style='color:{sc};font-size:11px;'>{co['direction']}</td>"
            f"<td style='color:#888;font-size:11px;'>{co['strength']}</td>"
            f"<td style='min-width:100px;padding:0 8px;'>{bar}</td>"
            f"</tr>"
        )

    corr_html = (
        f'<div style="overflow-x:auto;">'
        f'<table style="width:100%;border-collapse:collapse;font-size:12px;">'
        f'<thead><tr style="border-bottom:1px solid #1e2d40;">'
        f'<th style="color:#5b8dee;padding:7px 6px;text-align:left;">Feature</th>'
        f'<th style="color:#5b8dee;padding:7px 6px;text-align:right;">Correlation</th>'
        f'<th style="color:#5b8dee;padding:7px 6px;">Direction</th>'
        f'<th style="color:#5b8dee;padding:7px 6px;">Strength</th>'
        f'<th style="color:#5b8dee;padding:7px 6px;">Magnitude</th>'
        f'</tr></thead><tbody>{corr_rows}</tbody></table></div>'
        f'<div style="color:#666;font-size:11px;margin-top:6px;">'
        f'Pearson correlation with r20d within discount zone signals only. '
        f'Bar scaled: full bar = 0.20+ correlation.</div>'
    )

    # ── Section 4: Edge Refinement ────────────────────────────
    ref_rows = ""
    for ref in refinements:
        st   = ref["stats"]
        diff = ref["vs_baseline"]
        vc   = ("#6aa84f" if "outperforms" in ref["verdict"] else
                "#cc4444" if "Underperforms" in ref["verdict"].upper() else "#d6a740")
        ref_rows += (
            f"<tr>"
            f"<td style='color:#aab;font-size:12px;'>{ref['condition']}</td>"
            f"<td style='color:#888;font-size:11px;'>{ref['type'].replace('_',' ')}</td>"
            f"<td style='color:#aab;font-size:12px;text-align:center;'>{st['n_resolved']}</td>"
            f"<td style='color:{_sc(st['wr'])};font-size:12px;text-align:right;'>{st['wr']*100:.0f}%</td>"
            f"<td style='color:{_sc(diff, -0.02, 0.02)};font-size:12px;text-align:right;font-weight:600;'>{diff*100:+.1f}%</td>"
            f"<td style='color:{vc};font-size:11px;'>{ref['verdict']}</td>"
            f"</tr>"
        )

    ref_html = (
        f'<div style="overflow-x:auto;">'
        f'<table style="width:100%;border-collapse:collapse;font-size:12px;">'
        f'<thead><tr style="border-bottom:1px solid #1e2d40;">'
        f'<th style="color:#5b8dee;padding:7px 6px;text-align:left;">Condition</th>'
        f'<th style="color:#5b8dee;padding:7px 6px;">Type</th>'
        f'<th style="color:#5b8dee;padding:7px 6px;text-align:center;">N</th>'
        f'<th style="color:#5b8dee;padding:7px 6px;text-align:right;">WR</th>'
        f'<th style="color:#5b8dee;padding:7px 6px;text-align:right;">vs Baseline</th>'
        f'<th style="color:#5b8dee;padding:7px 6px;">Verdict</th>'
        f'</tr></thead><tbody>{ref_rows}</tbody></table></div>'
        f'<div style="color:#666;font-size:11px;margin-top:6px;">'
        f'Baseline = discount zone overall mean r20d. '
        f'Does NOT change SMC discount zone definition — only refines confidence.</div>'
    )

    # ── Section 5: SMC Dependency ─────────────────────────────
    dep_html = (
        f'<div style="display:flex;gap:10px;flex-wrap:wrap;">'
        + "".join(
            f'<div style="background:#0d1420;border-radius:6px;padding:14px;flex:1;min-width:140px;">'
            f'<div style="color:#aab;font-size:13px;font-weight:700;margin-bottom:4px;">{round(v*100,1)}%</div>'
            f'<div style="color:#888;font-size:10px;text-transform:uppercase;">{l}</div>'
            f'{_bar(v*100, "#5b8dee")}</div>'
            for l, v in [
                ("SMC Structure Dep.",   smc_dep.get("smc_structure_dependency", 0)),
                ("Liquidity Sensitivity",smc_dep.get("liquidity_sensitivity", 0)),
                ("Volatility Sensitivity",smc_dep.get("volatility_sensitivity", 0)),
            ]
        )
        + f'</div>'
        f'<div style="color:#666;font-size:11px;margin-top:8px;">'
        f'Correlation (absolute) of structural signals with r20d within discount zone. '
        f'Higher = that dimension is more predictive of outcome inside the discount zone.</div>'
    )

    # ── Full HTML ─────────────────────────────────────────────
    def _card(title, body, accent="#6c8ebf"):
        return (f'<div style="background:#141b27;border:1px solid #1e2d40;'
                f'border-top:3px solid {accent};border-radius:8px;'
                f'padding:20px;margin-bottom:20px;">'
                f'<h3 style="color:{accent};margin:0 0 14px;font-size:13px;'
                f'letter-spacing:1px;text-transform:uppercase;">{title}</h3>'
                f'{body}</div>')

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Discount Zone Pattern Miner — {TODAY}</title>
  <style>
    * {{ box-sizing:border-box; margin:0; padding:0; }}
    body {{ background:#0a1020; color:#c8d0e0; font-family:'Segoe UI',sans-serif; padding:20px; }}
    table tr:hover td {{ background:#0a1628; }}
    table td, table th {{ padding:7px 8px; border-bottom:1px solid #1a2535; }}
    @media(max-width:600px) {{ body {{ padding:10px; }} }}
  </style>
</head>
<body>
<div style="max-width:1200px;margin:0 auto;">

  <div style="background:linear-gradient(135deg,#0a1628 0%,#0d1f3c 100%);
              border:1px solid #1e3050;border-radius:12px;padding:24px;margin-bottom:20px;">
    <div style="color:#5b8dee;font-size:11px;letter-spacing:2px;margin-bottom:4px;">
      DISCOUNT ZONE PATTERN MINER</div>
    <h1 style="color:#e8eaf0;font-size:24px;margin-bottom:6px;">
      Hidden Structure Discovery Inside Discount Zones</h1>
    <div style="color:#aab;font-size:13px;">
      Generated: {TODAY} &nbsp;|&nbsp;
      r1_price ≥ {DISC_MIN_R1}/30 threshold &nbsp;|&nbsp;
      {n_disc} discount zone signals &nbsp;|&nbsp;
      {len(clusters)} clusters discovered
    </div>
    <div style="margin-top:8px;font-size:12px;color:#666;">
      Does NOT modify SMC discount zone definition.
      Discovers WHEN the discount zone works vs fails.
    </div>
  </div>

  {_card("① Discount Zone Overview vs All-Signal Baseline", overview + cmp_html, "#5b8dee")}
  {_card("② Context Clusters (Sorted by E[r20d])", cluster_table, "#6c8ebf")}
  {_card("③ Hidden Correlations with r20d Inside Discount Zone", corr_html, "#82d46a")}
  {_card("④ Edge Refinement — When Discount Zone is Valid vs Not", ref_html, "#d6a740")}
  {_card("⑤ SMC Structural Dependency Analysis", dep_html, "#5b8dee")}

  <div style="text-align:center;color:#444;font-size:11px;margin-top:20px;padding:10px;">
    Discount Zone Pattern Miner · EGX30 · {TODAY}
    · SMC discount zone is a fixed prerequisite. This module refines confidence inside it.
  </div>
</div>
</body>
</html>"""


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def run():
    print(f"\n{'='*60}")
    print("  Discount Zone Pattern Miner")
    print(f"{'='*60}")

    disc_signals = load_discount_signals()
    all_signals  = load_all_signals()
    print(f"  Discount zone signals (r1≥{DISC_MIN_R1}): {len(disc_signals)}")
    print(f"  All signals: {len(all_signals)}")

    if not disc_signals:
        print("  No discount zone signals found — exiting.")
        return

    all_baseline = _cluster_stats(all_signals)

    # 1. Cluster by context signature
    clusters = build_clusters(disc_signals)
    print(f"  Clusters: {len(clusters)} (success={sum(1 for c in clusters if c['pattern_type']=='discount_zone_success')}, "
          f"failure={sum(1 for c in clusters if c['pattern_type']=='discount_zone_failure')}, "
          f"mixed={sum(1 for c in clusters if c['pattern_type']=='mixed')})")

    # 2. Hidden correlations
    correlations = compute_correlations(disc_signals)
    top_corr = [(c["feature"], c["correlation"]) for c in correlations[:3]]
    print(f"  Top correlations: {top_corr}")

    # 3. Edge refinement
    refinements = edge_refinement(disc_signals, all_baseline)
    print(f"  Edge refinement entries: {len(refinements)}")

    # 4. SMC structural dependency
    smc_dep = smc_dependency_analysis(disc_signals)
    print(f"  SMC dep: {smc_dep}")

    # 5. Pattern evolution
    prev_memory  = _jload(MEMORY_FILE) or {}
    evolution    = track_evolution(clusters, prev_memory)
    n_new        = sum(1 for e in evolution if e["stability"] == "new")
    n_strengthen = sum(1 for e in evolution if e["stability"] == "strengthening")
    n_decay      = sum(1 for e in evolution if e["stability"] == "decaying")
    print(f"  Evolution: {n_new} new · {n_strengthen} strengthening · {n_decay} decaying")

    # 6. Save JSON
    disc_stats = _cluster_stats(disc_signals)
    output = {
        "generated_at":   TODAY,
        "disc_min_r1":    DISC_MIN_R1,
        "n_disc_signals": len(disc_signals),
        "n_all_signals":  len(all_signals),
        "disc_stats":     disc_stats,
        "all_baseline":   all_baseline,
        "clusters":       clusters,
        "correlations":   correlations,
        "edge_refinement": refinements,
        "smc_dependency":  smc_dep,
        "evolution":       evolution,
    }
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"  JSON → {MEMORY_FILE}")

    # 7. HTML report
    os.makedirs("reports", exist_ok=True)
    html = build_html(disc_signals, all_baseline, clusters, correlations,
                      refinements, evolution, smc_dep)
    with open(REPORT_OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Report → {REPORT_OUT}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    run()
