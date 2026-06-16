#!/usr/bin/env python3
"""
GX Research Memory
==================
Persistent knowledge base for the GX learning ecosystem.

Every finding becomes a ResearchItem that progresses through:
  Open → Investigating → Awaiting Validation → Validated | Rejected → Promoted

Run:
    python gx_research_memory.py
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

ROOT   = Path(__file__).parent
STATE  = ROOT / "gx_research_memory.json"
TODAY  = date.today().isoformat()
NOW    = datetime.now(timezone.utc).isoformat()

INDICATOR_LABELS = {
    "r1_price":     "Price Position",
    "r2_ob":        "Order Block",
    "r3_liquidity": "Liquidity",
    "r4_htf":       "HTF Structure",
    "r5_avwap":     "Anchored VWAP",
    "r6_macd":      "MACD Context",
    "r7_div":       "Divergence",
    "r8_demand":    "Demand Zone",
    "arch":         "Architecture",
    "gate":         "Gate / Filter",
    "micro":        "Microstructure",
    "rl":           "RL Engine",
    "multi":        "Multi-indicator",
}

STATUS_ORDER   = ["Open", "Investigating", "Awaiting Validation", "Validated", "Rejected", "Promoted"]
PRIORITY_RANK  = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
EVIDENCE_RANK  = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}

SYS_WEIGHTS = {
    "r1_price": 30, "r2_ob": 10, "r3_liquidity": 20,
    "r4_htf": 10, "r5_avwap": 8, "r6_macd": 4, "r7_div": 3, "r8_demand": 15,
}


# ── data structures ───────────────────────────────────────────────────────────

@dataclass
class ResearchItem:
    id: str
    title: str
    category: str          # weight_change | scoring_fix | gate | architecture | overfitting | new_feature
    indicator: str
    finding: str
    source_report: str
    date_discovered: str
    date_updated: str
    priority: str          # CRITICAL | HIGH | MEDIUM | LOW
    evidence_strength: str # HIGH | MEDIUM | LOW
    current_status: str    # Open | Investigating | Awaiting Validation | Validated | Rejected | Promoted
    next_required_action: str
    estimated_impact: float
    supporting_modules: list = field(default_factory=list)
    conflicting_modules: list = field(default_factory=list)
    evidence_data: dict    = field(default_factory=dict)
    history: list          = field(default_factory=list)


@dataclass
class IndicatorMaturity:
    indicator: str
    label: str
    current_weight: float
    evidence_score: int
    validation_score: int
    promotion_readiness: int
    research_priority: str
    open_items: int
    validated_items: int
    promoted_items: int
    recommended_direction: str  # INCREASE | DECREASE | FIX_LOGIC | STABLE
    recommended_weight: Optional[float]
    last_finding: str


# ── state I/O ─────────────────────────────────────────────────────────────────

def _load_state() -> dict:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text())
        except Exception:
            pass
    return {
        "schema_version": 2,
        "created_at": NOW,
        "last_updated": NOW,
        "research_items": {},
        "indicator_maturity": {},
        "backlog": [],
        "run_log": [],
    }


def _save_state(state: dict) -> None:
    state["last_updated"] = NOW
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def _load_json(name: str) -> dict:
    p = ROOT / name
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return {}
    return {}


# ── research item management ──────────────────────────────────────────────────

def upsert(state: dict, item: ResearchItem) -> None:
    """Insert or update. Never downgrades a status already further in the pipeline."""
    items = state["research_items"]
    existing = items.get(item.id)

    if existing is None:
        d = asdict(item)
        d["history"] = [{"date": TODAY, "event": "created", "status": item.current_status}]
        items[item.id] = d
        return

    # Preserve status if already further along
    old_idx = STATUS_ORDER.index(existing.get("current_status", "Open"))
    new_idx = STATUS_ORDER.index(item.current_status)
    final_status = existing["current_status"] if old_idx > new_idx else item.current_status

    changed = []
    for f in ["evidence_strength", "next_required_action", "estimated_impact",
              "supporting_modules", "conflicting_modules", "evidence_data"]:
        nv = getattr(item, f)
        if existing.get(f) != nv:
            existing[f] = nv
            changed.append(f)

    existing["date_updated"]   = TODAY
    existing["current_status"] = final_status
    if changed:
        existing["history"].append({"date": TODAY, "event": "updated", "fields": changed})


# ── ingest from each module ───────────────────────────────────────────────────

def ingest_logic_analyzer(state: dict) -> None:
    d = _load_json("logic_analysis_results.json")
    if not d:
        return
    n = d.get("n_signals", 0)
    fi = d.get("function_impact", {})

    specs = [
        ("RI-PRICE-INV",  "r1_price",     "scoring_fix",  "MEDIUM", "MEDIUM",
         "Open",
         "Price scoring inversion: near-EQ (r1=1-10) outperforms deep-discount (r1=21-30)",
         "Current linear scoring rewards the wrong range. delta_r20d when r1>0: +0.59%.",
         "Test modified buy-zone scoring in shadow mode; cross-check WF fold consistency.",
         fi.get("sc_price", {}).get("delta_r20d", 0)),

        ("RI-OB-HARM",    "r2_ob",        "scoring_fix",  "MEDIUM", "MEDIUM",
         "Investigating",
         "Order Block presence REDUCES expected return by -1.4%",
         "r2_ob>0 signals underperform (delta_r20d=-1.4%). 3 modules agree, but WF folds inconsistent — System Audit verdict: OVERFITTED.",
         "Extend OOS window to 6+ months. Do not remove OB until WF folds converge.",
         abs(fi.get("sc_ob", {}).get("delta_r20d", -0.014))),

        ("RI-HTF-INV",    "r4_htf",       "scoring_fix",  "MEDIUM", "MEDIUM",
         "Awaiting Validation",
         "HTF Scoring Inversion: HH+HL = -0.8%, HL-only = +11.6%",
         "Full HH+HL confirmation currently scores highest but returns -0.8%. HL-only returns +11.6%. System Audit WF-consistent.",
         "Implement HTF scoring inversion fix in shadow mode for 20 sessions.",
         0.011),

        ("RI-DEM-PAR",    "r8_demand",    "scoring_fix",  "MEDIUM", "MEDIUM",
         "Investigating",
         "Demand Zone Paradox: SV+HVN (max score=15) = lowest return",
         "SV+HVN together is the worst demand outcome. HVN-only is the best. The scoring function is rewarding the wrong combination.",
         "Validate HVN-only vs SV+HVN split across WF folds. Fix internal scoring multipliers in sc_demand().",
         0.005),

        ("RI-LIQ-WICK",   "r3_liquidity", "weight_change","MEDIUM", "LOW",
         "Open",
         "Rejection Wick (r3=8 pts) has near-zero edge — sub-component overweighted",
         "Wick rejection is the weakest liquidity sub-signal. Reducing its multiplier from 0.6 to 0.15 frees weight for equal-lows.",
         "Cross-validate wick reduction in Weight Optimizer and Walk-Forward before changing.",
         0.004),

        ("RI-DIV-RSI",    "r7_div",       "scoring_fix",  "MEDIUM", "MEDIUM",
         "Open",
         "RSI Divergence: NEGATIVE edge (mean=3.8% vs baseline 4.7%)",
         "rsi_div=1 signals underperform. r7_div combines RSI+MACD div — RSI drag cancels MACD edge. Need to separate them.",
         "Separate RSI and MACD divergence sub-scores in sc_div(). RSI div should be zeroed or penalized.",
         0.009),
    ]

    for rid, ind, cat, pri, ev, stat, title, finding, action, impact in specs:
        upsert(state, ResearchItem(
            id=rid, title=title, category=cat, indicator=ind,
            finding=finding, source_report="logic_analyzer",
            date_discovered=d.get("generated_at", TODAY)[:10],
            date_updated=TODAY, priority=pri, evidence_strength=ev,
            current_status=stat, next_required_action=action,
            estimated_impact=impact,
            supporting_modules=["logic_analyzer"],
            evidence_data={"n_signals": n, "function_impact": fi.get(f"sc_{ind.split('_')[1]}", {})},
        ))


def ingest_weight_optimizer(state: dict) -> None:
    d = _load_json("optimization_results.json")
    if not d:
        return
    oos  = d.get("oos_improvement", 0)
    opt  = d.get("optimal_weights", {})

    # r6_macd — only HIGH-evidence weight change (3-method convergence)
    upsert(state, ResearchItem(
        id="RI-MACD-REDUCE",
        title="r6_macd: reduce 4 → 2  (Optimizer=1.2, RL=1.1, WF=2.9 — 3-method convergence)",
        category="weight_change", indicator="r6_macd",
        finding="Three independent methods converge on reducing r6_macd. Only weight change currently with HIGH evidence.",
        source_report="weight_optimizer",
        date_discovered=d.get("generated_at", TODAY)[:10],
        date_updated=TODAY, priority="HIGH", evidence_strength="HIGH",
        current_status="Awaiting Validation",
        next_required_action="Stage shadow scoring with r6_macd=2 for 20 trading sessions. This is the only weight change currently safe to promote.",
        estimated_impact=0.003,
        supporting_modules=["weight_optimizer", "smc_rl", "walk_forward"],
        evidence_data={"optimizer_w": opt.get("r6_macd", 1.2), "current_w": 4, "oos": oos},
    ))

    # r5_avwap — MEDIUM (3-method, smaller drift)
    upsert(state, ResearchItem(
        id="RI-AVWAP-REDUCE",
        title="r5_avwap: reduce 8 → 4-6  (Optimizer=4.3, RL=4.1, WF=6.3 — 3-method convergence)",
        category="weight_change", indicator="r5_avwap",
        finding="Three methods agree: reduce AVWAP weight. Positive delta when present but modest. Consensus around 4-6.",
        source_report="weight_optimizer",
        date_discovered=TODAY, date_updated=TODAY,
        priority="MEDIUM", evidence_strength="MEDIUM",
        current_status="Awaiting Validation",
        next_required_action="Shadow test r5_avwap=5 for 20 sessions. Validate after r6_macd reduction is complete (one change at a time).",
        estimated_impact=0.002,
        supporting_modules=["weight_optimizer", "smc_rl", "walk_forward"],
        evidence_data={"optimizer_w": opt.get("r5_avwap", 4.3), "current_w": 8},
    ))

    # Liquidity gate — highest-confidence gate candidate
    upsert(state, ResearchItem(
        id="RI-GATE-LIQ20",
        title="Liquidity gate: r3_liquidity >= 20  (optimizer confidence=0.88 — highest of all gates)",
        category="gate", indicator="r3_liquidity",
        finding="Retains 43% of signals, win_rate=68.4%, expected return +0.9% vs baseline. Highest optimizer confidence.",
        source_report="weight_optimizer",
        date_discovered=TODAY, date_updated=TODAY,
        priority="MEDIUM", evidence_strength="MEDIUM",
        current_status="Awaiting Validation",
        next_required_action="Validate across WF fold periods. If consistent, stage for shadow scoring.",
        estimated_impact=0.009,
        supporting_modules=["weight_optimizer"],
        evidence_data={"confidence": 0.88, "n_retained": 275, "win_rate": 0.684},
    ))

    # Score gate — REJECTED (overfitted)
    upsert(state, ResearchItem(
        id="RI-GATE-SCORE",
        title="Score gates (>=55, >=60) — REJECTED: OVERFITTED in System Audit OOS",
        category="gate", indicator="multi",
        finding="Score gate >=55: IS +1.75% but OOS -4.52%. Gate >=60: IS +1.06%, OOS OVERFITTED. Both confirmed overfitted.",
        source_report="system_audit",
        date_discovered=TODAY, date_updated=TODAY,
        priority="LOW", evidence_strength="HIGH",
        current_status="Rejected",
        next_required_action="Rejected. Score-based gates on raw_score are overfitted. Do not reopen without new architecture.",
        estimated_impact=-0.045,
        supporting_modules=["system_audit"],
        conflicting_modules=["weight_optimizer"],
        evidence_data={"oos_diff_55": -0.0452, "oos_diff_60": -0.0452},
    ))

    # Full weight rebalance — LOW (OOS near zero)
    upsert(state, ResearchItem(
        id="RI-OPT-REBAL",
        title="Full weight rebalance (Optimizer) — OOS improvement ≈ 0, high overfit risk",
        category="weight_change", indicator="multi",
        finding=f"ML rebalance to Liq=28, Div=26, Demand=21, Price=12. OOS improvement={oos:.6f} ≈ zero. Conflicts with RL and WF.",
        source_report="weight_optimizer",
        date_discovered=TODAY, date_updated=TODAY,
        priority="LOW", evidence_strength="LOW",
        current_status="Investigating",
        next_required_action="Do not promote as a batch. Decompose into per-indicator items. Validate each independently.",
        estimated_impact=oos,
        supporting_modules=["weight_optimizer"],
        conflicting_modules=["smc_rl", "walk_forward"],
        evidence_data={"optimal_weights": opt, "oos": oos},
    ))


def ingest_system_audit(state: dict) -> None:
    d = _load_json("system_audit_results.json")
    if not d:
        return
    oa   = d.get("overfitting_audit", [])
    conc = d.get("conclusions", {})

    for finding in oa:
        text    = finding.get("finding", "")
        verdict = finding.get("verdict", "")
        oos     = finding.get("oos_diff", 0)
        wf_cons = finding.get("wf_consistent", False)
        folds   = finding.get("wf_fold_diffs", [])

        if "sweep" in text:
            upsert(state, ResearchItem(
                id="RI-SWEEP-GATE",
                title=f"Sweep detected mandatory gate — System Audit: {verdict}",
                category="gate", indicator="gate",
                finding=f"sweep=1 signals: IS diff=+{finding.get('is_diff',0):.3f}, OOS=+{oos:.3f}, WF consistent={wf_cons}. Folds={folds}.",
                source_report="system_audit",
                date_discovered=TODAY, date_updated=TODAY,
                priority="MEDIUM", evidence_strength="MEDIUM" if wf_cons else "LOW",
                current_status="Awaiting Validation",
                next_required_action="Reduces signals by 54.6%. Shadow test 20 sessions to measure opportunity cost before promoting.",
                estimated_impact=0.007,
                supporting_modules=["system_audit", "adaptive_learning"],
                evidence_data={"verdict": verdict, "oos_diff": oos, "wf_folds": folds},
            ))

        elif "hvn" in text.lower():
            upsert(state, ResearchItem(
                id="RI-HVN-CONF",
                title=f"HVN-only = strongest demand signal — System Audit: {verdict}",
                category="scoring_fix", indicator="r8_demand",
                finding=f"HVN hit outperforms. WF consistent={wf_cons}, OOS diff=+{oos:.3f}. Folds={folds}.",
                source_report="system_audit",
                date_discovered=TODAY, date_updated=TODAY,
                priority="HIGH", evidence_strength="HIGH" if verdict == "CONFIRMED" else "MEDIUM",
                current_status="Awaiting Validation",
                next_required_action="Promote HVN-only scoring fix: increase HVN-only sub-score, decrease SV+HVN sub-score in sc_demand().",
                estimated_impact=0.009,
                supporting_modules=["system_audit", "logic_analyzer", "historical_backtest"],
                evidence_data={"verdict": verdict, "oos_diff": oos, "wf_folds": folds},
            ))

    # Architecture finding
    arch = conc.get("q7_architecture", "")
    if arch:
        upsert(state, ResearchItem(
            id="RI-ARCH-ADDITIVE",
            title="Additive scoring: OOS R² = -0.15 — architecture cannot be fixed by weight tuning",
            category="architecture", indicator="arch",
            finding=arch,
            source_report="system_audit",
            date_discovered=TODAY, date_updated=TODAY,
            priority="CRITICAL", evidence_strength="HIGH",
            current_status="Investigating",
            next_required_action="Design non-linear scoring: mandatory gates × quality bonus. Test vs current additive sum. This is the root cause of the learning plateau.",
            estimated_impact=0.02,
            supporting_modules=["system_audit", "research_quant"],
            evidence_data={"oos_r2": -0.15},
        ))

    # HTF highest-impact fix from conclusions
    htf_note = conc.get("q8_highest_impact", "")
    if htf_note:
        upsert(state, ResearchItem(
            id="RI-HTF-FIX-IMPACT",
            title="HTF inversion fix = highest single-change impact per System Audit",
            category="scoring_fix", indicator="r4_htf",
            finding=htf_note,
            source_report="system_audit",
            date_discovered=TODAY, date_updated=TODAY,
            priority="HIGH", evidence_strength="MEDIUM",
            current_status="Awaiting Validation",
            next_required_action="Swap HH+HL → 0 pts, HL-only → full pts in sc_htf(). Shadow mode 20 sessions.",
            estimated_impact=0.012,
            supporting_modules=["system_audit", "logic_analyzer"],
            evidence_data={"note": htf_note},
        ))


def ingest_adaptive_learning(state: dict) -> None:
    d = _load_json("adaptive_learning_results.json")
    if not d:
        return

    for imp in d.get("all_improvements", []):
        imp_id = imp.get("id", "")
        if imp_id != "IMP-5":
            continue
        upsert(state, ResearchItem(
            id="RI-HVN-HTF-BONUS",
            title="IMP-5: HVN + HTF_HH super-bonus tier — model_score=100, n=8.5% of signals",
            category="scoring_fix", indicator="multi",
            finding=f"delta_ret=+{imp.get('delta_ret',0):.3f} when hvn_hit=1 AND htf_hh=1. WF-consistent={imp.get('wf_consistent')}. Only 8.5% of signals qualify. GX memory flags as overfitted.",
            source_report="adaptive_learning",
            date_discovered=TODAY, date_updated=TODAY,
            priority="MEDIUM", evidence_strength="MEDIUM",
            current_status="Awaiting Validation",
            next_required_action="Need 6+ months forward data (n≥150) before promoting. Do not apply to main scanner.",
            estimated_impact=imp.get("delta_ret", 0),
            supporting_modules=["adaptive_learning"],
            conflicting_modules=["gx_learning"],
            evidence_data={"model_score": imp.get("model_score"), "retention": 0.085},
        ))


def ingest_smc_rl(state: dict) -> None:
    d = _load_json("smc_rl_weights.json")
    if not d:
        return
    hist = d.get("history", [])
    if not hist:
        return
    last = hist[-1]
    perf = last.get("perf", {})
    disc = perf.get("discrimination")
    top_q = perf.get("top_q_avg_90d")
    bot_q = perf.get("bot_q_avg_90d")
    loss  = last.get("loss_final")
    n     = last.get("n_data", 0)
    epochs = last.get("epochs", 0)

    upsert(state, ResearchItem(
        id="RI-RL-NEG-DISC",
        title=f"SMC RL discrimination = {disc} (NEGATIVE — top-quartile underperforms bottom)",
        category="overfitting", indicator="rl",
        finding=f"After {epochs} epochs on {n} signals: top-Q avg={top_q}% vs bot-Q avg={bot_q}%. Loss={loss:.4f} converging but model is inversely predictive.",
        source_report="smc_rl",
        date_discovered=TODAY, date_updated=TODAY,
        priority="CRITICAL", evidence_strength="HIGH",
        current_status="Investigating",
        next_required_action="Diagnose RL objective function. Likely the target variable is inverted or the loss is minimizing the wrong direction. Do not use RL weights for any promotion until fixed.",
        estimated_impact=-0.04,
        supporting_modules=["smc_rl"],
        evidence_data={"discrimination": disc, "top_q": top_q, "bot_q": bot_q, "loss": loss},
    ))


def ingest_walk_forward(state: dict) -> None:
    d = _load_json("walk_forward_state.json")
    if not d:
        return
    weights  = d.get("weights", {})
    equity   = d.get("equity", 100)
    n_trades = len(d.get("trades", []))
    n_updates = len(d.get("weight_log", []))

    max_drift = max(
        abs(weights.get(k, v) - v) / v
        for k, v in SYS_WEIGHTS.items() if v > 0
    ) if weights else 0

    upsert(state, ResearchItem(
        id="RI-WF-DRIFT",
        title=f"Walk-Forward: {n_updates} weight updates but max drift {max_drift:.0%} — micro-corrections only",
        category="architecture", indicator="arch",
        finding=f"{n_trades} trades, equity grew to {equity:.0f}x. But weights barely moved from original (max drift {max_drift:.1%}). WF is not encoding structural fixes (HTF inversion, OB removal).",
        source_report="walk_forward",
        date_discovered=TODAY, date_updated=TODAY,
        priority="MEDIUM", evidence_strength="MEDIUM",
        current_status="Investigating",
        next_required_action="Evaluate whether WF's trade-by-trade micro-learning can coexist with structural overrides. May need a 'structural anchor' layer above WF.",
        estimated_impact=0.005,
        supporting_modules=["walk_forward"],
        evidence_data={"max_drift_pct": round(max_drift, 3), "n_trades": n_trades, "equity": equity},
    ))


def ingest_edge_discovery(state: dict) -> None:
    d = _load_json("edge_discovery_results.json")
    if not d:
        return
    n_sig    = d.get("total_rules_significant", 0)
    feat_cols = d.get("feat_cols", [])
    scanner_features = {
        "r1_price","r2_ob","r3_liquidity","r4_htf","r5_avwap",
        "r6_macd","r7_div","r8_demand","raw_score","adj_score",
    }
    n_external = len(set(feat_cols) - scanner_features)
    sig_rules  = d.get("significant_rules", [])
    top_rule   = max(sig_rules, key=lambda r: r.get("win_rate", 0), default={})

    upsert(state, ResearchItem(
        id="RI-MICRO-FEATURES",
        title=f"Edge Discovery: {n_external} microstructure features predict returns but are absent from scanner",
        category="new_feature", indicator="micro",
        finding=f"{n_sig} significant rules found. Top features: snap_reclaim_spd, feat_dist_52w_low, feat_dist_last_bos, snap_atr. Best rule achieves WR={top_rule.get('win_rate',0):.0%} on n={top_rule.get('n',0)}.",
        source_report="edge_discovery",
        date_discovered=TODAY, date_updated=TODAY,
        priority="MEDIUM", evidence_strength="MEDIUM",
        current_status="Open",
        next_required_action="Start with snap_reclaim_spd (reclaim speed appears in multiple top rules). Research whether it can be computed daily and added as r9 without major architecture change.",
        estimated_impact=0.025,
        supporting_modules=["edge_discovery", "research_quant"],
        evidence_data={"n_sig_rules": n_sig, "n_external_features": n_external,
                       "top_rule_wr": top_rule.get("win_rate"), "top_rule_n": top_rule.get("n")},
    ))


def ingest_research_quant(state: dict) -> None:
    d = _load_json("research_results.json")
    if not d:
        return
    mc   = d.get("model_comparison_mfe", {})
    prob = d.get("probability_analysis", {})
    best_r2 = mc.get("best_r2")

    upsert(state, ResearchItem(
        id="RI-QUANT-R2",
        title=f"All ML models R² ≤ -0.012 — scoring has zero predictive power for returns",
        category="architecture", indicator="arch",
        finding=f"RF R²=-1.225, GBM R²=-0.021, XGBoost R²={best_r2}. AUC=0.506 (near random). High-confidence prob model hits {prob.get('high_conf_precision',0):.0%} precision but only on tiny subset.",
        source_report="research_quant",
        date_discovered=TODAY, date_updated=TODAY,
        priority="CRITICAL", evidence_strength="HIGH",
        current_status="Investigating",
        next_required_action="Confirms RI-ARCH-ADDITIVE. Weight tuning cannot fix R²<0. Structural redesign needed — not weight changes.",
        estimated_impact=0.03,
        supporting_modules=["research_quant", "system_audit"],
        evidence_data={"best_r2": best_r2, "rf_r2": -1.225, "gbm_r2": -0.021, "auc": prob.get("auc")},
    ))

    # MACD divergence from historical backtest
    hist = _load_json("historical_backtest_results.json")
    if hist:
        for flag in hist.get("flag_analysis", []):
            if flag.get("flag") == "macd_div":
                yes = flag.get("yes", {})
                no  = flag.get("no",  {})
                upsert(state, ResearchItem(
                    id="RI-DIV-MACD",
                    title=f"MACD Divergence: PF={yes.get('pf',0):.2f} vs baseline {no.get('pf',0):.2f} — strongest edge of any flag",
                    category="weight_change", indicator="r7_div",
                    finding=f"macd_div=1: n={yes.get('n')}, PF={yes.get('pf'):.2f}, WR={yes.get('wr'):.1%}, mean={yes.get('mean'):.3f}. RSI div is negative — must be separated before increasing r7_div.",
                    source_report="historical_backtest",
                    date_discovered=TODAY, date_updated=TODAY,
                    priority="MEDIUM", evidence_strength="MEDIUM",
                    current_status="Investigating",
                    next_required_action="Separate RSI and MACD div sub-scores in sc_div() first (RI-DIV-RSI). Then test r7_div increase from 3 → 5.",
                    estimated_impact=0.016,
                    supporting_modules=["historical_backtest"],
                    conflicting_modules=["smc_rl", "walk_forward"],
                    evidence_data={"macd_pf": yes.get("pf"), "baseline_pf": no.get("pf"), "n": yes.get("n")},
                ))


def ingest_structural_gaps(state: dict) -> None:
    """Gaps in the promotion pipeline itself."""
    upsert(state, ResearchItem(
        id="RI-SYS-PROMOTE",
        title="Structural gap: no promotion pipeline — all 33 findings stuck at Proposed, actual_delta=None",
        category="architecture", indicator="arch",
        finding="The learning ecosystem has no mechanism to move findings from Proposed → Staged → Promoted. actual_delta_ret=None for every recommendation. The system discovers but does not learn.",
        source_report="gx_research_memory",
        date_discovered=TODAY, date_updated=TODAY,
        priority="CRITICAL", evidence_strength="HIGH",
        current_status="Open",
        next_required_action="Implement shadow scoring: run scanner in parallel with proposed change, log results without alerting, compare after 20 sessions. This is the single highest-ROI engineering task.",
        estimated_impact=0.05,
        supporting_modules=["gx_learning"],
        evidence_data={"n_proposed": 33, "n_promoted": 0},
    ))

    upsert(state, ResearchItem(
        id="RI-SYS-WFSCOPE",
        title="Walk-Forward micro-learning cannot encode structural fixes — two incompatible learning speeds",
        category="architecture", indicator="arch",
        finding="WF adjusts weights ±0.05 per trade. Structural fixes (HTF inversion, OB removal) require ±5-10 point changes. These cannot coexist in the same update loop.",
        source_report="gx_research_memory",
        date_discovered=TODAY, date_updated=TODAY,
        priority="MEDIUM", evidence_strength="MEDIUM",
        current_status="Investigating",
        next_required_action="Design two-layer weight system: structural base (updated quarterly via promotion) + WF micro-delta (updated per trade).",
        estimated_impact=0.01,
        supporting_modules=["walk_forward", "system_audit"],
        evidence_data={},
    ))


# ── indicator maturity ────────────────────────────────────────────────────────

def compute_maturity(state: dict) -> dict:
    items = state["research_items"]

    # Best-guess weight references from each method
    opt_w = {"r1_price":12, "r2_ob":0, "r3_liquidity":28, "r4_htf":1.5,
             "r5_avwap":4.3, "r6_macd":1.2, "r7_div":26, "r8_demand":21}
    rl_w  = {"r1_price":30.6, "r2_ob":9.6, "r3_liquidity":15, "r4_htf":9.6,
             "r5_avwap":4.1, "r6_macd":1.1, "r7_div":3.1, "r8_demand":15.1}
    wf_w  = {"r1_price":31.4, "r2_ob":10.7, "r3_liquidity":19.9, "r4_htf":10.2,
             "r5_avwap":6.3, "r6_macd":2.9, "r7_div":2.7, "r8_demand":15.9}

    result = {}
    for ind, cur in SYS_WEIGHTS.items():
        ind_items  = [v for v in items.values() if v.get("indicator") == ind]
        active     = [i for i in ind_items if i["current_status"] in ("Open","Investigating","Awaiting Validation")]
        validated  = [i for i in ind_items if i["current_status"] == "Validated"]
        promoted   = [i for i in ind_items if i["current_status"] == "Promoted"]

        # Evidence score: methods that recommend a change + number of findings
        n_change = sum([
            1 if abs(opt_w[ind] - cur) / cur > 0.15 else 0,
            1 if abs(rl_w[ind]  - cur) / cur > 0.15 else 0,
            1 if abs(wf_w[ind]  - cur) / cur > 0.15 else 0,
        ])
        evidence_score     = min(100, n_change * 28 + len(ind_items) * 7 + len(validated) * 10)
        validation_score   = min(100, len(validated) * 30 + len(promoted) * 50)
        promotion_readiness = min(100, int(evidence_score * 0.4 + validation_score * 0.6))

        n_dec = sum(1 for w in [opt_w[ind], rl_w[ind], wf_w[ind]] if w < cur * 0.85)
        n_inc = sum(1 for w in [opt_w[ind], rl_w[ind], wf_w[ind]] if w > cur * 1.15)
        direction = "DECREASE" if n_dec >= 2 else "INCREASE" if n_inc >= 2 else \
                    "FIX_LOGIC" if ind in ("r4_htf","r8_demand","r1_price") else "STABLE"
        rec_weight = round((opt_w[ind] + rl_w[ind] + wf_w[ind]) / 3, 1) if direction in ("DECREASE","INCREASE") else cur

        rp = "HIGH" if evidence_score >= 55 and validation_score < 40 else \
             "MEDIUM" if evidence_score >= 25 else "LOW"

        last = max(ind_items, key=lambda x: x.get("date_updated",""), default=None)
        result[ind] = {
            "indicator": ind, "label": INDICATOR_LABELS[ind], "current_weight": cur,
            "evidence_score": evidence_score, "validation_score": validation_score,
            "promotion_readiness": promotion_readiness, "research_priority": rp,
            "open_items": len(active), "validated_items": len(validated), "promoted_items": len(promoted),
            "recommended_direction": direction, "recommended_weight": rec_weight,
            "last_finding": (last.get("title","")[:80] if last else "none"),
        }
    return result


# ── build ranked backlog ──────────────────────────────────────────────────────

def build_backlog(state: dict) -> list:
    active = {"Open", "Investigating", "Awaiting Validation"}
    rows = []
    for item in state["research_items"].values():
        if item.get("current_status") not in active:
            continue
        p      = PRIORITY_RANK.get(item.get("priority","LOW"), 3)
        e      = EVIDENCE_RANK.get(item.get("evidence_strength","LOW"), 1)
        impact = abs(item.get("estimated_impact", 0))
        score  = p * 100 - e * 20 - impact * 500
        rows.append({
            "id": item["id"], "title": item["title"][:80],
            "priority": item.get("priority"), "evidence": item.get("evidence_strength"),
            "status": item.get("current_status"), "impact": impact,
            "indicator": item.get("indicator"),
            "next_action": item.get("next_required_action","")[:120],
            "rank_score": score,
        })
    rows.sort(key=lambda x: x["rank_score"])
    return rows


# ── HTML report ───────────────────────────────────────────────────────────────

def _pc(p: str) -> str:
    return {"CRITICAL":"#dc3545","HIGH":"#fd7e14","MEDIUM":"#ffc107","LOW":"#6c757d"}.get(p,"#6c757d")

def _sc(s: str) -> str:
    return {"Open":"#8b949e","Investigating":"#58a6ff","Awaiting Validation":"#f0883e",
            "Validated":"#3fb950","Rejected":"#da3633","Promoted":"#a371f7"}.get(s,"#8b949e")

def _ec(e: str) -> str:
    return {"HIGH":"#3fb950","MEDIUM":"#f0883e","LOW":"#da3633"}.get(e,"#8b949e")

def _bar(v: int, c: str) -> str:
    return (f'<div style="display:inline-flex;align-items:center;gap:6px">'
            f'<div style="background:#21262d;border-radius:4px;height:6px;width:80px">'
            f'<div style="background:{c};width:{v}%;height:6px;border-radius:4px"></div></div>'
            f'<span style="font-size:0.8em;color:#8b949e">{v}</span></div>')


def generate_html(state: dict, backlog: list, maturity: dict) -> str:
    items  = list(state["research_items"].values())
    now    = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    by_st  = {s: sum(1 for i in items if i.get("current_status") == s) for s in STATUS_ORDER}
    crits  = [i for i in items if i.get("priority") == "CRITICAL" and
              i.get("current_status") in {"Open","Investigating"}]
    top3   = backlog[:3]
    rejected = [i for i in items if i.get("current_status") == "Rejected"]
    safe_ignore = [i for i in items if i.get("priority") in ("LOW",) and
                   i.get("evidence_strength") == "LOW" and
                   i.get("current_status") not in ("Validated","Promoted")]

    # Maturity rows
    mat_rows = ""
    for ind, m in maturity.items():
        dc = {"DECREASE":"#da3633","INCREASE":"#3fb950","FIX_LOGIC":"#f0883e","STABLE":"#8b949e"}.get(m["recommended_direction"],"#8b949e")
        rpc = {"HIGH":"#da3633","MEDIUM":"#f0883e","LOW":"#8b949e"}.get(m["research_priority"],"#8b949e")
        mat_rows += f"""<tr>
          <td><strong style="color:#e6edf3">{m['label']}</strong><br>
              <small style="color:#8b949e">{m['indicator']} · w={m['current_weight']}</small></td>
          <td>{_bar(m['evidence_score'], '#58a6ff')}</td>
          <td>{_bar(m['validation_score'], '#3fb950')}</td>
          <td>{_bar(m['promotion_readiness'], '#a371f7')}</td>
          <td><span style="color:{dc};font-weight:600">{m['recommended_direction']}</span>
              {"<br><small style='color:#8b949e'>→ "+str(m['recommended_weight'])+"</small>" if m['recommended_weight'] != m['current_weight'] else ""}</td>
          <td><span style="color:{rpc}">{m['research_priority']}</span>
              <br><small style="color:#8b949e">{m['open_items']} open</small></td>
        </tr>"""

    # Backlog rows
    bl_rows = ""
    for i, row in enumerate(backlog[:25], 1):
        bl_rows += f"""<tr>
          <td style="color:#6c757d;font-size:0.8em;white-space:nowrap">#{i}</td>
          <td><span style="background:{_pc(row['priority'])};color:#fff;padding:1px 7px;border-radius:10px;font-size:0.72em;white-space:nowrap">{row['priority']}</span></td>
          <td style="min-width:120px"><code style="color:#58a6ff;font-size:0.8em">{row['id']}</code><br>
              <small>{row['title']}</small></td>
          <td><span style="color:{_sc(row['status'])};font-size:0.82em">{row['status']}</span></td>
          <td><span style="color:{_ec(row['evidence'])};font-size:0.82em">{row['evidence']}</span></td>
          <td style="font-size:0.8em;color:#8b949e">{row['next_action']}</td>
        </tr>"""

    # What next
    next_html = ""
    for i, row in enumerate(top3, 1):
        next_html += f"""<div style="border-left:4px solid {_pc(row['priority'])};padding:12px 16px;margin:8px 0;background:#1c2128;border-radius:0 8px 8px 0">
          <div style="font-weight:600;color:#e6edf3">{i}. <code style="color:#58a6ff">[{row['id']}]</code> {row['title']}</div>
          <div style="color:#8b949e;margin-top:6px;font-size:0.88em">→ {row['next_action']}</div>
          <div style="margin-top:8px">
            <span style="background:{_pc(row['priority'])};color:#fff;padding:1px 8px;border-radius:10px;font-size:0.72em">{row['priority']}</span>
            <span style="background:#21262d;color:#8b949e;padding:1px 8px;border-radius:10px;font-size:0.72em;margin-left:4px">{row['status']}</span>
          </div></div>"""

    # Critical alerts
    crit_html = ""
    for c in crits:
        crit_html += f"""<div style="background:#1f1b18;border:1px solid #f0883e;border-radius:8px;padding:12px;margin:8px 0">
          <div style="color:#f0883e;font-weight:700">⚠ <code>{c['id']}</code> — {c['title']}</div>
          <div style="color:#8b949e;font-size:0.85em;margin-top:4px">{c.get('next_required_action','')[:180]}</div>
        </div>"""

    # Ignore list
    ignore_items = rejected + safe_ignore
    ign_html = "".join(
        f"<li><code style='color:#8b949e'>{i['id']}</code> — {i['title'][:70]}… "
        f"<span style='color:#da3633;font-size:0.8em'>({i['current_status']})</span></li>"
        for i in ignore_items[:8]
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>GX Research Memory — {TODAY}</title>
<style>
  *{{box-sizing:border-box}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;margin:0;background:#0d1117;color:#e6edf3;font-size:14px}}
  .wrap{{max-width:1400px;margin:0 auto;padding:24px}}
  h1{{font-size:1.5em;color:#58a6ff;border-bottom:1px solid #30363d;padding-bottom:12px;margin-bottom:8px}}
  h2{{font-size:0.85em;color:#8b949e;margin:28px 0 12px;text-transform:uppercase;letter-spacing:1.2px}}
  .card{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:18px;margin:10px 0}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;margin:14px 0}}
  .stat{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:14px;text-align:center}}
  .sv{{font-size:1.9em;font-weight:700}}
  .sl{{font-size:0.72em;color:#8b949e;margin-top:4px}}
  table{{width:100%;border-collapse:collapse}}
  th{{background:#161b22;color:#8b949e;padding:9px 12px;text-align:left;border-bottom:2px solid #30363d;font-size:0.78em;text-transform:uppercase;letter-spacing:0.8px;font-weight:500;white-space:nowrap}}
  td{{padding:9px 12px;border-bottom:1px solid #21262d;vertical-align:top;line-height:1.5}}
  tr:hover td{{background:#1c2128}}
  .ts{{font-size:0.75em;color:#6c757d}}
  ul{{margin:0;padding-left:18px;line-height:2.2}}
</style>
</head>
<body>
<div class="wrap">
<h1>🔬 GX Research Memory</h1>
<div class="ts">Generated: {now} &nbsp;·&nbsp; {len(items)} total items &nbsp;·&nbsp; Schema v2</div>

<div class="grid">
  <div class="stat"><div class="sv" style="color:#58a6ff">{by_st['Open']+by_st['Investigating']}</div><div class="sl">Open / Investigating</div></div>
  <div class="stat"><div class="sv" style="color:#f0883e">{by_st['Awaiting Validation']}</div><div class="sl">Awaiting Validation</div></div>
  <div class="stat"><div class="sv" style="color:#3fb950">{by_st['Validated']}</div><div class="sl">Validated</div></div>
  <div class="stat"><div class="sv" style="color:#a371f7">{by_st['Promoted']}</div><div class="sl">Promoted</div></div>
  <div class="stat"><div class="sv" style="color:#da3633">{by_st['Rejected']}</div><div class="sl">Rejected</div></div>
  <div class="stat"><div class="sv" style="color:#da3633">{len(crits)}</div><div class="sl">Critical Open</div></div>
</div>

{"<h2>⚠ Critical Items</h2><div class='card'>" + crit_html + "</div>" if crits else ""}

<h2>📋 What Should Be Investigated Next?</h2>
<div class="card">{next_html}</div>

<h2>🎯 Indicator Maturity</h2>
<div class="card"><table>
  <tr><th>Indicator</th><th>Evidence</th><th>Validation</th><th>Promotion Readiness</th><th>Direction</th><th>Research Priority</th></tr>
  {mat_rows}
</table></div>

<h2>🗂 Research Backlog — Ranked</h2>
<div class="card"><table>
  <tr><th>#</th><th>Priority</th><th>Item</th><th>Status</th><th>Evidence</th><th>Next Required Action</th></tr>
  {bl_rows}
</table></div>

<h2>🚫 What Can Be Safely Ignored Now</h2>
<div class="card"><ul>{ign_html}</ul></div>

</div></body></html>"""


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("[Research Memory] Loading state …", flush=True)
    state = _load_state()

    print("[Research Memory] Ingesting module outputs …", flush=True)
    ingest_logic_analyzer(state)
    ingest_weight_optimizer(state)
    ingest_system_audit(state)
    ingest_adaptive_learning(state)
    ingest_smc_rl(state)
    ingest_walk_forward(state)
    ingest_edge_discovery(state)
    ingest_research_quant(state)
    ingest_structural_gaps(state)

    print("[Research Memory] Computing indicator maturity …", flush=True)
    state["indicator_maturity"] = compute_maturity(state)

    print("[Research Memory] Building backlog …", flush=True)
    backlog = build_backlog(state)
    state["backlog"] = backlog

    state["run_log"].append({
        "date": TODAY,
        "n_items": len(state["research_items"]),
        "n_active": sum(1 for i in state["research_items"].values()
                        if i.get("current_status") in {"Open","Investigating","Awaiting Validation"}),
        "n_validated": sum(1 for i in state["research_items"].values() if i["current_status"] == "Validated"),
        "n_promoted":  sum(1 for i in state["research_items"].values() if i["current_status"] == "Promoted"),
    })

    _save_state(state)
    print("[Research Memory] State saved.", flush=True)

    html = generate_html(state, backlog, state["indicator_maturity"])
    report = ROOT / "reports" / f"research_memory_report_{TODAY}.html"
    report.parent.mkdir(exist_ok=True)
    report.write_text(html, encoding="utf-8")
    print(f"[Research Memory] Report → {report}  ({len(html)//1024} KB)", flush=True)

    n_active = state["run_log"][-1]["n_active"]
    n_total  = len(state["research_items"])
    top_item = backlog[0] if backlog else {}
    print(f"[Research Memory] {n_total} items | {n_active} active | top: [{top_item.get('id','')}] {top_item.get('title','')[:60]}", flush=True)


if __name__ == "__main__":
    main()
