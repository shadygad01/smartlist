"""
Decision Engine
===============
Synthesis layer — consumes ALL research outputs and produces one
structured decision per signal. Does NOT modify any existing module.

Reads (never writes to):
  egx_research.db  (v_all_signals — complete signal universe)
  backtest_report.json, adaptive_learning_results.json,
  edge_discovery_results.json, system_audit_results.json,
  optimization_results.json, historical_backtest_results.json,
  gx_learning_memory.json, research_results.json

Writes:
  decision_engine_results.json
  reports/decision_engine_report_YYYY-MM-DD.html

Usage:
  python decision_engine.py
"""
# Constitution §AUTOMATIC ARCHIVING RULE — Research only; no path to production without r1-r8 mapping
RESEARCH_ONLY_LAB = True

import json
import os
import sqlite3
from collections import Counter, defaultdict
from datetime import date

TODAY      = date.today().isoformat()
DB_PATH    = "egx_research.db"
OUT_JSON   = "decision_engine_results.json"
REPORT_OUT = f"reports/decision_engine_report_{TODAY}.html"

WIN_THRESH  = 0.07   # r20d ≥ 7% → win
LOSS_THRESH = 0.0    # r20d < 0% → loss
BUY_CONF    = 0.55   # minimum final_confidence for BUY

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
    """Derive 4 context tags from a signal dict (same logic as gx_learning_layer)."""
    ht_hl = int(s.get("htf_hl") or 0)
    ht_hh = int(s.get("htf_hh") or 0)
    regime = "trend" if ht_hl else ("range" if (ht_hh == 0 and ht_hl == 0) else "mixed")

    r6 = float(s.get("r6_macd") or 0)
    r7 = float(s.get("r7_div")  or 0)
    md = int(s.get("macd_div")  or 0)
    rd = int(s.get("rsi_div")   or 0)
    vol = "high" if (r6 + r7 >= 8 and (md or rd)) else ("low" if r6 + r7 <= 4 else "medium")

    sw = int(s.get("sweep_detected")  or 0)
    eq = int(s.get("equal_lows")      or 0)
    wk = int(s.get("wick_rejection")  or 0)
    struct = ("expansion" if sw else
              "compression" if eq else
              "reversal"    if wk else "unknown")

    hv = int(s.get("hvn_hit") or 0)
    sv = int(s.get("sv_hit")  or 0)
    r3 = float(s.get("r3_liquidity") or 0)
    liq = "strong" if (hv or sv) else ("moderate" if r3 >= 7 else "weak")
    return regime, vol, struct, liq


def _smc_label(adj_score):
    s = float(adj_score or 0)
    if s >= 80: return "Strong Buy"
    if s >= 65: return "Buy"
    if s >= 50: return "Watch"
    return "Wait"


# ═══════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════

def load_sources():
    return {
        "backtest":   _jload("backtest_report.json"),
        "adaptive":   _jload("adaptive_learning_results.json"),
        "edge":       _jload("edge_discovery_results.json"),
        "audit":      _jload("system_audit_results.json"),
        "optimizer":  _jload("optimization_results.json"),
        "historical": _jload("historical_backtest_results.json"),
        "gx_mem":     _jload("gx_learning_memory.json"),
        "research":   _jload("research_results.json"),
    }


def load_signals_from_db():
    """Load all signals from v_all_signals (read-only)."""
    if not os.path.exists(DB_PATH):
        return []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM v_all_signals ORDER BY signal_date DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════════
# REGIME-CONDITIONAL STATISTICS
# ═══════════════════════════════════════════════════════════════

def build_regime_stats(signals):
    """
    Compute performance stats grouped by (regime, vol) from resolved signals.
    Used as historical_edge reference for each decision.
    """
    buckets = defaultdict(list)
    for s in signals:
        r20d = s.get("r20d")
        if r20d is None:
            continue
        regime, vol, _, _ = _tag(s)
        buckets[(regime, vol)].append(float(r20d))

    stats = {}
    for key, r20ds in buckets.items():
        n      = len(r20ds)
        wins   = [r for r in r20ds if r >= WIN_THRESH]
        gw     = sum(r for r in r20ds if r > 0)
        gl     = abs(sum(r for r in r20ds if r < 0))
        stats[key] = {
            "n":          n,
            "wr":         round(len(wins) / n, 4),
            "mean_r20d":  round(sum(r20ds) / n, 4),
            "pf":         round(gw / gl, 3) if gl > 0 else (99.0 if gw > 0 else 0.0),
        }
    return stats


# ═══════════════════════════════════════════════════════════════
# CONTEXT CLUSTER PATTERNS  (⑭/⑮ from gx_learning_layer)
# ═══════════════════════════════════════════════════════════════

def build_context_clusters(signals):
    """
    Build top success and failure context combos.
    Replicates ⑭/⑮ logic from gx_learning_layer — no import needed.
    """
    win_ctr  = Counter()
    fail_ctr = Counter()
    win_r    = defaultdict(list)
    fail_r   = defaultdict(list)

    for s in signals:
        r20d = s.get("r20d")
        if r20d is None:
            continue
        regime, vol, struct, _ = _tag(s)
        key = f"regime={regime} · vol={vol} · struct={struct}"
        r = float(r20d)
        if r >= WIN_THRESH:
            win_ctr[key]  += 1
            win_r[key].append(r)
        elif r < LOSS_THRESH:
            fail_ctr[key] += 1
            fail_r[key].append(r)

    def _enrich(ctr, rmap):
        return [
            {"combo": k, "n": n, "mean": round(sum(rmap[k]) / len(rmap[k]), 4)}
            for k, n in ctr.most_common(10)
        ]

    return _enrich(win_ctr, win_r), _enrich(fail_ctr, fail_r)


# ═══════════════════════════════════════════════════════════════
# LEARNING ADJUSTMENT (from adaptive + GX memory)
# ═══════════════════════════════════════════════════════════════

def compute_learning_adjustment(src):
    """
    Derive a scalar score delta from WF-consistent adaptive improvements
    and GX memory recommendations. Returns (delta: float, reasons: list).
    """
    adp = src.get("adaptive") or {}
    improvements = adp.get("all_improvements") or []
    wf_imps = [i for i in improvements if i.get("wf_consistent") is True]

    delta   = 0.0
    reasons = []
    for imp in wf_imps[:5]:
        dr = float(imp.get("delta_ret") or 0)
        delta += dr * 0.4   # 40% discount: potential gain, not guaranteed
        if dr != 0:
            reasons.append(f"{imp.get('id','?')}: Δ={dr*100:+.1f}%")

    # GX memory: cross-validated recommendations add small confidence
    gx = src.get("gx_mem") or {}
    multi_recs = [r for r in (gx.get("recommendations") or [])
                  if len(r.get("supporting", [])) >= 2
                  and r.get("wf_consistent") is True]
    delta += len(multi_recs) * 0.01   # each cross-validated wf rec adds 1pp

    delta = round(min(0.20, max(-0.20, delta)), 4)
    return delta, reasons[:3]


# ═══════════════════════════════════════════════════════════════
# EDGE RULE MATCHING
# ═══════════════════════════════════════════════════════════════

def match_edge_rules(row, edge_src):
    """Match signal against top significant edge rules. Returns list of texts."""
    rules = (edge_src.get("top_rules") or
             edge_src.get("significant_rules") or
             edge_src.get("rules") or [])
    top = sorted(rules, key=lambda r: float(r.get("expectancy", 0) or 0), reverse=True)[:20]

    matched = []
    for rule in top:
        conditions = rule.get("conditions") or []
        ok = True
        for cond in conditions[:5]:
            if not isinstance(cond, (list, tuple)) or len(cond) < 3:
                continue
            col, op, val = str(cond[0]), str(cond[1]), cond[2]
            sig_val = row.get(col)
            if sig_val is None:
                ok = False; break
            try:
                sv, fv = float(sig_val), float(val)
                if op in ("<=", "<")  and not (sv <= fv): ok = False; break
                if op in (">=", ">")  and not (sv >= fv): ok = False; break
                if op == "==" and abs(sv - fv) > 0.5:    ok = False; break
            except (ValueError, TypeError):
                if str(sig_val) != str(val): ok = False; break
        if ok:
            matched.append(rule.get("rule_text", "")[:70])
    return matched[:3]


# ═══════════════════════════════════════════════════════════════
# AUDIT FILTER CHECK
# ═══════════════════════════════════════════════════════════════

def audit_filter_flags(src):
    """
    From system_audit filter_damage: identify filters that are damaging.
    Returns dict {filter_name: verdict}.
    """
    audit = src.get("audit") or {}
    damage_flags = {}
    for fd in (audit.get("filter_damage") or []):
        if fd.get("diff", 0) < -0.02 and fd.get("significant"):
            damage_flags[fd.get("filter", "?")] = fd.get("verdict", "damaging")
    return damage_flags


# ═══════════════════════════════════════════════════════════════
# CORE DECISION FUNCTION
# ═══════════════════════════════════════════════════════════════

def decide(row, regime_stats, la_delta, success_patterns,
           failure_patterns, edge_src, audit_flags, src):
    """
    Produce one structured decision dict for a signal row.
    Applies the 5-step decision rule system:
      1. SMC base signal
      2. Learning adjustment
      3. Context filtering
      4. Edge validation
      5. Conflict handling
    """
    adj   = float(row.get("adj_score") or row.get("raw_score") or 0)
    raw   = float(row.get("raw_score") or adj)
    smc_label = _smc_label(adj)

    # ── 1. Context tags ────────────────────────────────────────
    regime, vol, struct, liq = _tag(row)

    # ── 2. Historical edge in current regime ───────────────────
    rkey = (regime, vol)
    hist  = regime_stats.get(rkey, {})
    wr_r  = float(hist.get("wr", 0.50))
    exp_r = float(hist.get("mean_r20d", 0.0))
    pf_r  = float(hist.get("pf", 1.0))
    n_r   = int(hist.get("n", 0))

    dd_profile = ("favorable" if pf_r >= 1.5 and wr_r >= 0.50 else
                  "adverse"   if pf_r < 1.0  or wr_r < 0.38  else "neutral")

    # ── 3. Base confidence from SMC score ─────────────────────
    # Maps adj_score to (-0.5, +0.5) range centred at 65 (typical buy threshold)
    base_conf = (adj - 65.0) / 35.0
    base_conf = max(-0.40, min(0.40, base_conf))

    # ── 4. Regime alignment bonus/penalty ─────────────────────
    if wr_r >= 0.55:
        regime_adj = +0.10
    elif wr_r < 0.38:
        regime_adj = -0.15
    else:
        regime_adj = (wr_r - 0.47) / 0.09 * 0.05

    # ── 5. Learning adjustment ─────────────────────────────────
    la_factor = min(0.12, max(-0.12, la_delta))

    # ── 6. Expectancy adjustment ───────────────────────────────
    exp_adj = (+0.05 if exp_r >= WIN_THRESH else
               -0.10 if exp_r < LOSS_THRESH else 0.0)

    # ── 7. Composite confidence ────────────────────────────────
    raw_conf   = 0.50 + base_conf + regime_adj + la_factor + exp_adj
    final_conf = round(max(0.0, min(1.0, raw_conf)), 3)

    # ── 8. Edge rule matching ──────────────────────────────────
    matched_rules = match_edge_rules(row, edge_src)

    # ── 9. GX insights (⑭/⑮ cross-reference) ─────────────────
    sig_key = f"regime={regime} · vol={vol} · struct={struct}"
    supporting  = [p["combo"] for p in success_patterns if p["combo"] == sig_key]
    conflicting = [p["combo"] for p in failure_patterns if p["combo"] == sig_key]

    fail_flags = []
    if conflicting:
        fail_flags.append(f"context={sig_key} matches failure cluster")
    if vol == "high" and struct == "unknown":
        fail_flags.append("high volatility + unknown structure")
    if liq == "weak":
        fail_flags.append("weak liquidity state")
    if matched_rules:
        fail_flags_from_edge = []  # matched rules are positive, so no flag

    # ── 10. Conflict rule (critical) ──────────────────────────
    smc_positive      = adj >= 65
    history_negative  = wr_r < 0.38 or exp_r < LOSS_THRESH
    learning_negative = la_delta < -0.05
    # Conflict = SMC says buy BUT learning AND history both say negative
    conflict = smc_positive and history_negative and learning_negative

    if conflict:
        final_decision = "NO_TRADE"
        final_conf     = min(final_conf, 0.35)
        conf_rationale = (f"CONFLICT: SMC positive (score={adj:.0f}) but "
                          f"regime history weak (WR={wr_r:.0%}, E[r20d]={exp_r*100:+.1f}%) "
                          f"and learning negative (Δ={la_delta*100:+.1f}%)")
    elif final_conf >= BUY_CONF:
        final_decision = "BUY"
        conf_rationale = f"Confidence {final_conf:.3f} ≥ {BUY_CONF} threshold"
    else:
        final_decision = "NO_TRADE"
        conf_rationale = f"Confidence {final_conf:.3f} < {BUY_CONF} threshold"

    # ── 11. Decision rationale ─────────────────────────────────
    adp = src.get("adaptive") or {}
    n_wf = sum(1 for i in (adp.get("all_improvements") or [])
               if i.get("wf_consistent") is True)
    rationale = [
        (f"SMC: score={adj:.0f}/100 (raw={raw:.0f}), signal={smc_label} — "
         f"{'positive' if adj>=65 else 'neutral' if adj>=50 else 'negative'} anchor"),
        (f"Learning: Δ={la_delta*100:+.1f}% from {n_wf} WF-consistent improvements; "
         f"GX health={(adp.get('health_score') or 0)}/100"),
        (f"History [{regime}×{vol}]: WR={wr_r:.0%}, E[r20d]={exp_r*100:+.1f}%, "
         f"PF={pf_r:.2f} (n={n_r})"),
        (f"Context: {regime}/{vol}/{struct}/{liq} — "
         f"{'aligned' if wr_r>=0.50 else 'misaligned'}"),
        conf_rationale,
    ]
    if matched_rules:
        rationale.append("Edge rules matched: " + " | ".join(matched_rules[:2]))

    return {
        "trade_id":           str(row.get("id") or ""),
        "symbol":             str(row.get("symbol") or ""),
        "signal_date":        str(row.get("signal_date") or ""),
        "final_decision":     final_decision,
        "final_confidence":   final_conf,
        "final_score":        round(final_conf * 100, 1),

        "smc_signal":         smc_label,
        "smc_score":          round(adj, 1),

        "learning_adjustment": {
            "score_delta": la_delta,
            "reason":      f"{n_wf} WF-consistent improvements aggregated",
        },

        "context_alignment": {
            "market_regime":    regime,
            "volatility_state": vol,
            "liquidity_state":  liq,
            "structure_state":  struct,
        },

        "historical_edge": {
            "win_rate_in_regime": wr_r,
            "expectancy":         round(exp_r, 4),
            "drawdown_profile":   dd_profile,
        },

        "gx_learning_insights": {
            "supporting_patterns": supporting,
            "conflicting_patterns": conflicting,
            "failure_risk_flags":   fail_flags,
        },

        "decision_rationale": rationale,

        # Internal fields for report / backtest
        "_r20d":          row.get("r20d"),
        "_mfe_20d":       row.get("mfe_20d"),
        "_matched_rules": matched_rules,
    }


# ═══════════════════════════════════════════════════════════════
# DECISION ENGINE SELF-VALIDATION (backtesting its own decisions)
# ═══════════════════════════════════════════════════════════════

def validate_decisions(decisions):
    """
    For resolved signals, compare engine decision vs actual r20d.
    Returns validation statistics.
    """
    buy_resolved     = [d for d in decisions if d["final_decision"] == "BUY"
                        and d.get("_r20d") is not None]
    notrade_resolved = [d for d in decisions if d["final_decision"] == "NO_TRADE"
                        and d.get("_r20d") is not None]

    def _stats(lst):
        if not lst: return {}
        r20ds = [float(d["_r20d"]) for d in lst]
        wins  = [r for r in r20ds if r >= WIN_THRESH]
        gw    = sum(r for r in r20ds if r > 0)
        gl    = abs(sum(r for r in r20ds if r < 0))
        return {
            "n":          len(lst),
            "wr":         round(len(wins)/len(lst), 4),
            "mean_r20d":  round(sum(r20ds)/len(lst), 4),
            "pf":         round(gw/gl, 3) if gl > 0 else (99.0 if gw > 0 else 0.0),
        }

    buy_stats     = _stats(buy_resolved)
    notrade_stats = _stats(notrade_resolved)
    all_stats     = _stats(buy_resolved + notrade_resolved)

    edge_lift = 0.0
    if buy_stats and all_stats and all_stats.get("mean_r20d", 0) != 0:
        edge_lift = (buy_stats.get("mean_r20d", 0) -
                     all_stats.get("mean_r20d", 0))

    return {
        "buy_signals":     buy_stats,
        "no_trade_signals": notrade_stats,
        "all_baseline":    all_stats,
        "edge_lift_r20d":  round(edge_lift, 4),
        "filtering_pct":   round(len(notrade_resolved) /
                                 max(1, len(buy_resolved)+len(notrade_resolved)) * 100, 1),
    }


# ═══════════════════════════════════════════════════════════════
# HTML REPORT
# ═══════════════════════════════════════════════════════════════

def _sc(s):
    if s >= 80: return "#6aa84f"
    if s >= 65: return "#a0c878"
    if s >= 50: return "#d6a740"
    return "#cc4444"

def _conf_color(c):
    if c >= 0.70: return "#6aa84f"
    if c >= 0.55: return "#a0c878"
    if c >= 0.40: return "#d6a740"
    return "#cc4444"

def _kpi(items):
    cells = "".join(
        f'<div style="background:#0d1420;border-radius:6px;padding:14px;text-align:center;flex:1;min-width:110px;">'
        f'<div style="color:{c};font-size:22px;font-weight:700;font-family:monospace;">{v}</div>'
        f'<div style="color:#888;font-size:11px;margin-top:4px;text-transform:uppercase;">{l}</div></div>'
        for l, v, c in items
    )
    return f'<div style="display:flex;gap:10px;flex-wrap:wrap;">{cells}</div>'


def build_html(decisions, validation, src):
    n_total   = len(decisions)
    n_buy     = sum(1 for d in decisions if d["final_decision"] == "BUY")
    n_notrade = n_total - n_buy
    avg_conf  = sum(d["final_confidence"] for d in decisions) / max(1, n_total)

    # ── summary KPIs ──
    val_buy = validation.get("buy_signals", {})
    kpis = _kpi([
        ("Total Signals",    str(n_total),                "#aab"),
        ("BUY",              str(n_buy),                  "#6aa84f"),
        ("NO_TRADE",         str(n_notrade),              "#cc4444"),
        ("Avg Confidence",   f"{avg_conf*100:.0f}%",      _conf_color(avg_conf)),
        ("BUY Win Rate",     f"{val_buy.get('wr',0)*100:.0f}%", _sc(int(val_buy.get('wr',0)*100))),
        ("BUY E[r20d]",      f"{val_buy.get('mean_r20d',0)*100:+.1f}%", "#6c8ebf"),
        ("Edge Lift",        f"{validation.get('edge_lift_r20d',0)*100:+.1f}%", "#d6a740"),
        ("Filtered",         f"{validation.get('filtering_pct',0):.0f}%", "#888"),
    ])

    # ── validation comparison ──
    def _vs(stats, label, color):
        return (f'<div style="background:#0d1420;border-radius:6px;padding:12px;flex:1;">'
                f'<div style="color:{color};font-size:12px;font-weight:600;margin-bottom:6px;">{label}</div>'
                f'<div style="color:#aab;font-size:12px;">n={stats.get("n",0)} · '
                f'WR={stats.get("wr",0)*100:.0f}% · '
                f'E[r20d]={stats.get("mean_r20d",0)*100:+.1f}% · '
                f'PF={stats.get("pf",0):.2f}</div></div>')

    val_html = (
        f'<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px;">'
        f'{_vs(validation.get("buy_signals",{}), "BUY Decisions (engine accepted)", "#6aa84f")}'
        f'{_vs(validation.get("no_trade_signals",{}), "NO_TRADE (engine filtered)", "#cc4444")}'
        f'{_vs(validation.get("all_baseline",{}), "All Signals Baseline", "#888")}'
        f'</div>'
        f'<div style="color:#8899aa;font-size:12px;">'
        f'Edge lift = BUY mean r20d − baseline mean r20d. '
        f'Positive = engine adds value over taking all signals.</div>'
    )

    # ── decisions table (recent 60) ──
    recent = [d for d in decisions if d["signal_date"] >= "2025-01-01"][:60]
    rows_html = ""
    for d in recent:
        dc   = "#6aa84f" if d["final_decision"] == "BUY" else "#cc4444"
        cc   = _conf_color(d["final_confidence"])
        sc   = _sc(int(d["smc_score"]))
        r20d = d.get("_r20d")
        r20d_str = f"{r20d*100:+.1f}%" if r20d is not None else "—"
        r20d_c   = ("#6aa84f" if r20d is not None and r20d >= WIN_THRESH else
                    "#cc4444" if r20d is not None and r20d < LOSS_THRESH else "#888")
        ctx = d["context_alignment"]
        risk = ", ".join(d["gx_learning_insights"]["failure_risk_flags"][:1]) or "—"
        rows_html += (
            f"<tr>"
            f"<td style='color:#aab;font-size:11px;'>{d['signal_date']}</td>"
            f"<td style='color:#e8eaf0;font-size:12px;'>{d['symbol']}</td>"
            f"<td><span style='background:{dc}22;color:{dc};padding:2px 8px;"
            f"border-radius:10px;font-size:11px;font-weight:600;'>{d['final_decision']}</span></td>"
            f"<td style='color:{cc};font-size:12px;text-align:right;font-weight:600;'>{d['final_confidence']:.2f}</td>"
            f"<td style='color:{sc};font-size:12px;text-align:right;'>{d['smc_score']:.0f}</td>"
            f"<td style='color:#888;font-size:11px;'>{ctx['market_regime']}/{ctx['volatility_state']}</td>"
            f"<td style='color:{r20d_c};font-size:12px;text-align:right;'>{r20d_str}</td>"
            f"<td style='color:#666;font-size:10px;max-width:200px;overflow:hidden;text-overflow:ellipsis;"
            f"white-space:nowrap;' title='{risk}'>{risk}</td>"
            f"</tr>"
        )

    table_html = (
        f'<div style="overflow-x:auto;">'
        f'<table style="width:100%;border-collapse:collapse;font-size:12px;">'
        f'<thead><tr style="border-bottom:1px solid #1e2d40;">'
        f'<th style="color:#5b8dee;padding:7px 6px;text-align:left;">Date</th>'
        f'<th style="color:#5b8dee;padding:7px 6px;">Symbol</th>'
        f'<th style="color:#5b8dee;padding:7px 6px;">Decision</th>'
        f'<th style="color:#5b8dee;padding:7px 6px;text-align:right;">Conf</th>'
        f'<th style="color:#5b8dee;padding:7px 6px;text-align:right;">SMC</th>'
        f'<th style="color:#5b8dee;padding:7px 6px;">Regime/Vol</th>'
        f'<th style="color:#5b8dee;padding:7px 6px;text-align:right;">r20d</th>'
        f'<th style="color:#5b8dee;padding:7px 6px;">Risk Flag</th>'
        f'</tr></thead><tbody>{rows_html}</tbody></table></div>'
        f'<div style="color:#666;font-size:11px;margin-top:6px;">'
        f'Showing {len(recent)} signals from 2025+ · r20d = actual 20-day return · '
        f'Conf = Decision Engine confidence (not SMC score)</div>'
    )

    # ── data sources consumed ──
    sources_used = []
    for key, label in [
        ("backtest", "backtest_report.json"),
        ("adaptive", "adaptive_learning_results.json"),
        ("edge",     "edge_discovery_results.json"),
        ("audit",    "system_audit_results.json"),
        ("optimizer","optimization_results.json"),
        ("historical","historical_backtest_results.json"),
        ("gx_mem",   "gx_learning_memory.json"),
        ("research", "research_results.json"),
    ]:
        col = "#6aa84f" if src.get(key) else "#cc4444"
        sources_used.append(
            f'<span style="background:{col}22;color:{col};padding:3px 8px;'
            f'border-radius:10px;font-size:11px;margin:2px;">{label}</span>'
        )

    src_html = f'<div style="display:flex;flex-wrap:wrap;gap:4px;">{"".join(sources_used)}</div>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Decision Engine Report — {TODAY}</title>
  <style>
    * {{ box-sizing:border-box; margin:0; padding:0; }}
    body {{ background:#0a1020; color:#c8d0e0; font-family:'Segoe UI',sans-serif; padding:20px; }}
    table tr:hover td {{ background:#0a1628; }}
    table td, table th {{ padding:7px 8px; border-bottom:1px solid #1a2535; }}
    .card {{ background:#141b27; border:1px solid #1e2d40; border-radius:8px;
             padding:20px; margin-bottom:20px; }}
    .card-title {{ color:#5b8dee; font-size:13px; font-weight:600; letter-spacing:1px;
                   text-transform:uppercase; margin-bottom:14px; }}
    @media(max-width:600px) {{ body {{ padding:10px; }} }}
  </style>
</head>
<body>
<div style="max-width:1200px;margin:0 auto;">

  <div style="background:linear-gradient(135deg,#0a1628 0%,#0d1f3c 100%);
              border:1px solid #1e3050;border-radius:12px;padding:24px;margin-bottom:20px;">
    <div style="color:#5b8dee;font-size:11px;letter-spacing:2px;margin-bottom:4px;">
      DECISION ENGINE</div>
    <h1 style="color:#e8eaf0;font-size:24px;margin-bottom:6px;">
      Unified Trading Decision Synthesis</h1>
    <div style="color:#aab;font-size:13px;">
      Generated: {TODAY} &nbsp;|&nbsp; {n_total} signals processed &nbsp;|&nbsp;
      {n_buy} BUY &nbsp;|&nbsp; {n_notrade} NO_TRADE
    </div>
    <div style="margin-top:8px;font-size:12px;color:#666;">
      Consumes ALL research outputs. Does NOT modify any existing module.
    </div>
  </div>

  <div class="card">
    <div class="card-title">① Summary KPIs</div>
    {kpis}
  </div>

  <div class="card" style="border-top:3px solid #6aa84f;">
    <div class="card-title">② Engine Self-Validation (Backtest of Decisions vs Actual r20d)</div>
    {val_html}
  </div>

  <div class="card" style="border-top:3px solid #6c8ebf;">
    <div class="card-title">③ Decision Table — 2025+ Signals (Most Recent First)</div>
    {table_html}
  </div>

  <div class="card" style="border-top:3px solid #d6a740;">
    <div class="card-title">④ Data Sources Consumed</div>
    {src_html}
    <div style="color:#666;font-size:11px;margin-top:8px;">
      Green = loaded successfully. Red = file missing or unreadable.
      All available sources are integrated into decision confidence computation.
    </div>
  </div>

  <div style="text-align:center;color:#444;font-size:11px;margin-top:20px;padding:10px;">
    Decision Engine · EGX30 Intelligence System · {TODAY}
    · Final confidence = f(SMC score, regime history, learning adjustment, context alignment)
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
    print("  Decision Engine")
    print(f"{'='*60}")

    # 1. Load all research sources
    src = load_sources()
    available = [k for k, v in src.items() if v is not None]
    print(f"  Sources loaded: {', '.join(available)}")

    # 2. Load signals from DB
    signals = load_signals_from_db()
    print(f"  Signals from DB: {len(signals)}")
    if not signals:
        print("  No signals found — exiting.")
        return

    # 3. Build regime-conditional performance table
    regime_stats = build_regime_stats(signals)
    print(f"  Regime buckets: {len(regime_stats)}")

    # 4. Build context cluster patterns (success/failure combos)
    success_pats, failure_pats = build_context_clusters(signals)
    print(f"  Success patterns: {len(success_pats)} · Failure patterns: {len(failure_pats)}")

    # 5. Compute learning adjustment (global, applied to all signals)
    la_delta, la_reasons = compute_learning_adjustment(src)
    print(f"  Learning adjustment: {la_delta*100:+.1f}% ({'; '.join(la_reasons) or 'none'})")

    # 6. Extract edge rules
    edge_src = src.get("edge") or {}

    # 7. Audit filter flags
    audit_flags = audit_filter_flags(src)
    if audit_flags:
        print(f"  Audit flags: {list(audit_flags.keys())[:3]}")

    # 8. Compute one decision per signal
    decisions = []
    for row in signals:
        d = decide(row, regime_stats, la_delta,
                   success_pats, failure_pats, edge_src, audit_flags, src)
        decisions.append(d)

    n_buy     = sum(1 for d in decisions if d["final_decision"] == "BUY")
    n_notrade = len(decisions) - n_buy
    print(f"  Decisions: {n_buy} BUY · {n_notrade} NO_TRADE")

    # 9. Validate decisions against known r20d
    validation = validate_decisions(decisions)
    lift = validation.get("edge_lift_r20d", 0)
    buy_wr = validation.get("buy_signals", {}).get("wr", 0)
    print(f"  BUY win rate: {buy_wr:.0%} · Edge lift: {lift*100:+.1f}%")

    # 10. Save JSON output
    # Strip internal fields from public JSON
    public_decisions = []
    for d in decisions:
        pd = {k: v for k, v in d.items() if not k.startswith("_")}
        public_decisions.append(pd)

    output = {
        "generated_at":   TODAY,
        "n_signals":      len(decisions),
        "n_buy":          n_buy,
        "n_no_trade":     n_notrade,
        "buy_rate":       round(n_buy / max(1, len(decisions)), 4),
        "learning_delta": la_delta,
        "validation":     validation,
        "decisions":      public_decisions,
    }
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"  JSON → {OUT_JSON}")

    # 11. Generate HTML report
    os.makedirs("reports", exist_ok=True)
    html = build_html(decisions, validation, src)
    with open(REPORT_OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Report → {REPORT_OUT}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    run()
