"""
EGX Constitutional Investment Platform — Dashboard
===================================================
Sections:
  1. Constitutional Engine Status
  2. Signal Discovery Pipeline
  3. Today's Research Insights
  4. Active Research
  5. Today's Constitutional Signals
  6. Knowledge Base Highlights
  7. Constitutional Performance
  8. Changes Since Yesterday
  9. Deployment History
 10. System Health
 11. Portfolio Intelligence
 12. Pattern Intelligence
"""

import json
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# ── Presentation layer — single source of truth ───────────────────────────────
from presentation.presentation_language import (
    DASH_TITLE, DASH_SUBTITLE, DASH_FOOTER,
)
from presentation.presentation_theme import DashTheme as _DT
from presentation.presentation_formatter import DashboardFormatter as _DashFmt

_dash_fmt = _DashFmt()

CAIRO = ZoneInfo("Africa/Cairo")


def _now_cairo():
    """Return current datetime in Africa/Cairo timezone."""
    return datetime.now(CAIRO)

DASHBOARD_FILE = "dashboard.html"
DB_PATH        = "egx_research.db"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}


def _load_scan() -> dict:
    """Load scan_results.json; fall back to latest signal_history.json entry per stock."""
    scan = _load("scan_results.json")
    if scan:
        return scan
    history = _load("signal_history.json")
    if not history:
        return {}
    # signal_history is stored oldest-first (appended); sigs[-1] is the most recent record.
    return {
        stock: {
            "price":            sigs[-1].get("price", 0),
            "score":            sigs[-1].get("score", 0),
            "signal":           sigs[-1].get("signal", "-"),
            "r1":               sigs[-1].get("r1", 0),
            "factor_exp_score": sigs[-1].get("factor_exp_score", 0),
            "early_buy_research": sigs[-1].get("early_buy_research", False),
            "ok":               True,
        }
        for stock, sigs in history.items()
        if sigs
    }


def _ts(iso, fmt="%Y-%m-%d %H:%M"):
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        return dt.strftime(fmt)
    except Exception:
        return str(iso)[:16]


def _num(v, fmt=".3f"):
    try:
        return format(float(v), fmt)
    except Exception:
        return "—"


def _pct(v):
    try:
        return f"{float(v)*100:.1f}%"
    except Exception:
        return "—"


# ── CSS constants — consumed from presentation_theme (single source) ──────────
G   = _DT.G    # "#4caf50" — green
R   = _DT.R    # "#f44336" — red
A   = _DT.A    # "#f0b840" — amber
B   = _DT.B    # "#50d8d0" — blue accent
DIM = _DT.DIM  # "#8b8fa8" — dim text
FG  = _DT.FG   # "#d0d4e8" — foreground
BG0 = _DT.BG0  # "#0b0c1a" — page background
BG1 = _DT.BG1  # "#10112a" — card background
BG2 = _DT.BG2  # "#181930" — inner box
BOR = _DT.BOR  # "#252645" — border


def _badge(ok, yes, no, warn=False):
    col = G if ok else (A if warn else R)
    lbl = yes if ok else no
    return (f'<span style="background:{col};color:#fff;padding:2px 9px;'
            f'border-radius:4px;font-size:0.8em;font-weight:600">{lbl}</span>')


def _box(title, content, color=DIM):
    return (f'<div style="background:{BG2};border:1px solid {BOR};border-radius:6px;'
            f'padding:12px 16px;margin-bottom:10px">'
            f'<div style="color:{color};font-size:0.75em;text-transform:uppercase;'
            f'letter-spacing:0.06em;margin-bottom:8px;font-weight:600">{title}</div>'
            f'{content}</div>')


def _row2(label, badge, detail=""):
    return (f'<tr><td style="padding:5px 10px;color:{DIM};white-space:nowrap;'
            f'font-size:0.83em;width:160px">{label}</td>'
            f'<td style="padding:5px 10px">{badge}</td>'
            f'<td style="padding:5px 10px;color:#9aa;font-size:0.8em">{detail}</td></tr>')


def _section_header(title, icon=""):
    # Renders through DashboardFormatter — presentation layer controls styling
    return _dash_fmt.section_header_raw(title, icon)


# ── DB query helper ───────────────────────────────────────────────────────────

def _db_query(sql, params=()):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def _db_scalar(sql, params=(), default=0):
    try:
        conn = sqlite3.connect(DB_PATH)
        val = conn.execute(sql, params).fetchone()
        conn.close()
        return val[0] if val else default
    except Exception:
        return default


def _ff_list(kb_data):
    ff_raw = kb_data.get("factor_findings", {})
    return list(ff_raw.values()) if isinstance(ff_raw, dict) else (
        ff_raw if isinstance(ff_raw, list) else []
    )


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — CONSTITUTIONAL ENGINE STATUS
# ══════════════════════════════════════════════════════════════════════════════

def _section_alpha_status() -> str:
    sched   = _load("scheduler_state.json")
    weights = _load("config/weights.json")

    mem_summary = {}
    try:
        from continuous_learning import LearningMemory
        mem_summary = LearningMemory().get_summary()
    except BaseException:
        pass

    n_signals   = _db_scalar("SELECT COUNT(*) FROM signals")
    n_mfe40     = _db_scalar("SELECT COUNT(*) FROM bottom_quality WHERE mfe_40d IS NOT NULL")
    n_peak1y    = _db_scalar("SELECT COUNT(*) FROM bottom_quality WHERE peak_return_1y IS NOT NULL")
    n_bq        = _db_scalar("SELECT COUNT(*) FROM bottom_quality WHERE r20d IS NOT NULL") or 1
    n_val       = _db_scalar("SELECT COUNT(*) FROM validation_runs")
    n_approved  = _db_scalar("SELECT COUNT(*) FROM validation_runs WHERE verdict='APPROVED'")
    n_promote   = _db_scalar("SELECT COUNT(*) FROM deployment_log WHERE action='PROMOTE'")
    n_rollback  = _db_scalar("SELECT COUNT(*) FROM deployment_log WHERE action='ROLLBACK'")
    n_exp       = _db_scalar("SELECT COUNT(*) FROM experiment_log")
    n_opt       = _db_scalar("SELECT COUNT(*) FROM optimization_history")

    lv_rows = _db_query("SELECT * FROM validation_runs ORDER BY rowid DESC LIMIT 1")
    lv = lv_rows[0] if lv_rows else {}

    last_promo_rows = _db_query("SELECT deployed_at FROM deployment_log WHERE action='PROMOTE' ORDER BY id DESC LIMIT 1")
    last_promo = last_promo_rows[0].get("deployed_at") if last_promo_rows else None

    last_rb_rows = _db_query("SELECT deployed_at FROM deployment_log WHERE action='ROLLBACK' ORDER BY id DESC LIMIT 1")
    last_rb = last_rb_rows[0].get("deployed_at") if last_rb_rows else None

    kb_data  = _load("knowledge_base.json")
    ff       = _ff_list(kb_data)
    n_kb_pos = sum(1 for f in ff if isinstance(f, dict) and f.get("verdict") == "POSITIVE")
    n_kb_neg = sum(1 for f in ff if isinstance(f, dict) and f.get("verdict") == "NEGATIVE")
    n_kb_tot = len(ff)

    oos_wr      = lv.get("oos_wr", 0) or 0
    oos_sh      = lv.get("oos_sharpe", 0) or 0
    val_wr      = lv.get("val_wr", 0) or 0
    alpha_ok    = lv.get("verdict") == "APPROVED"
    recent      = mem_summary.get("recent_cycles", [])
    last_cycle  = recent[-1] if recent else {}
    total_cyc   = mem_summary.get("total_cycles", 0)
    total_prom  = mem_summary.get("total_promoted", 0)
    best_oos    = mem_summary.get("best_approved_oos_wr", 0) or 0

    util_mfe40  = min(100, n_mfe40 / n_bq * 100) if n_bq else 0

    status_rows = "".join([
        _row2("System Status",     _badge(True, "ONLINE", "OFFLINE"),
              f"DB: {n_signals} signals | {n_bq} outcomes | {n_exp} experiments | {n_opt} optimizations"),
        _row2("Autonomy Status",   _badge(bool(last_cycle), "OPERATIONAL", "NOT RUN"),
              f"cycles={total_cyc} | promotions={total_prom} | last={_ts(last_cycle.get('finished_at'))}"),
        _row2("Alpha Status",      _badge(alpha_ok, "VERIFIED", "UNVERIFIED"),
              f"OOS mfe40_wr={_num(oos_wr)} | OOS Sharpe={_num(oos_sh)} | val_wr={_num(val_wr)}"),
        _row2("Workflow Health",   _badge(bool(sched.get("last_learning_cycle_at")), "ACTIVE", "IDLE"),
              f"last_cycle_at={_ts(sched.get('last_learning_cycle_at'))}"),
        _row2("Database Util.",    _badge(util_mfe40 >= 80, f"{util_mfe40:.0f}%", f"{util_mfe40:.0f}%", util_mfe40 >= 50),
              f"mfe_40d={n_mfe40}/{n_bq} | peak_1y={n_peak1y}/{n_bq}"),
        _row2("Knowledge Util.",   _badge(n_kb_tot > 0, f"{n_kb_tot} findings", "NO FINDINGS"),
              f"positive={n_kb_pos} | negative={n_kb_neg} | 8 indicator factors tracked"),
        _row2("Research Coverage", _badge(n_exp > 0, f"{n_exp} labs run", "NO LABS"),
              f"drift + factor + regime labs | last run={_ts(last_cycle.get('finished_at'))}"),
        _row2("Ranking Quality",   _badge(bool(weights), "DEPLOYED", "NO WEIGHTS"),
              f"r8_demand={weights.get('r8_demand','?')} | r6_macd={weights.get('r6_macd','?')} | r3_liq={weights.get('r3_liquidity','?')}"),
        _row2("Optimization",      _badge(n_opt > 0, f"{n_opt} runs", "NOT RUN"),
              "expectancy_gradient | KB-blended (70% optimizer + 30% KB suggestion)"),
        _row2("Validation",        _badge(n_approved > 0, f"{n_approved}/{n_val} APPROVED", "NO APPROVALS"),
              "60/20/20 split | mfe_40d primary | gates: oos_wr≥0.65 val_wr≥0.55 oos_exp≥0.10 oos_sharpe≥0.30"),
        _row2("Promotion",         _badge(n_promote > 0, f"{n_promote} promotions", "NONE"),
              f"last={_ts(last_promo)} | circuit_breaker=3/24h | best_oos_wr={_num(best_oos)}"),
        _row2("Monitoring",        _badge(not last_cycle.get("drift_detected", False), "CLEAR", "DRIFT", warn=True),
              f"drift_lab active | last={_ts(last_cycle.get('finished_at'))}"),
        _row2("Rollback",          _badge(True, "WIRED", "NOT WIRED"),
              f"auto-trigger on OOS WR drop >10pp | {n_rollback} rollbacks | last={_ts(last_rb)}"),
        _row2("Dashboard",         _badge(True, "LIVE", "STALE"),
              f"built {_ts(_now_cairo().isoformat())} | 11 sections | all data from live state"),
    ])

    weights_row = " | ".join(
        f"{k}={v:.2f}" for k, v in sorted(weights.items()) if isinstance(v, (int, float))
    ) if weights else "—"

    return f"""
<div style="background:{BG1};border:2px solid {B};border-radius:10px;padding:20px 24px;margin-bottom:18px">
  {_section_header("CONSTITUTIONAL ENGINE STATUS", "⚡")}
  {_box("15-Point System Checklist",
    f'<table style="width:100%;border-collapse:collapse">{status_rows}</table>')}
  {_box("Active Production Weights",
    f'<div style="font-size:0.82em;color:{FG};font-family:monospace;line-height:1.8">{weights_row}</div>')}
</div>"""


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — BOTTOM DISCOVERY PIPELINE  [NEW]
# ══════════════════════════════════════════════════════════════════════════════

def _section_bottom_pipeline() -> str:
    # Funnel counts from live state
    # Total evaluated = signal_log.json (all historically evaluated signals)
    sl_data    = _load("signal_log.json", {})
    sl_signals = sl_data.get("signals", [])
    n_disc     = len(sl_signals)

    n_accepted  = _db_scalar("SELECT COUNT(*) FROM signals")
    n_rejected  = max(0, n_disc - n_accepted)
    n_with_out  = _db_scalar("SELECT COUNT(DISTINCT signal_id) FROM bottom_quality")
    n_validated = _db_scalar("SELECT COUNT(*) FROM bottom_quality WHERE mfe_40d IS NOT NULL")
    n_opt_app   = _db_scalar("SELECT COUNT(*) FROM optimization_history WHERE approved=1")
    n_val_app   = _db_scalar("SELECT COUNT(*) FROM validation_runs WHERE verdict='APPROVED'")
    n_promote   = _db_scalar("SELECT COUNT(*) FROM deployment_log WHERE action='PROMOTE'")
    n_rollback  = _db_scalar("SELECT COUNT(*) FROM deployment_log WHERE action='ROLLBACK'")

    # Win/loss split on validated bottoms
    n_winners   = _db_scalar("SELECT COUNT(*) FROM bottom_quality WHERE mfe_40d >= 0.07")
    n_losers    = _db_scalar("SELECT COUNT(*) FROM bottom_quality WHERE mfe_40d < 0.07 AND mfe_40d IS NOT NULL")
    validated_wr = (n_winners / n_validated * 100) if n_validated else 0

    # Classification breakdown
    class_rows_data = _db_query(
        "SELECT classification, COUNT(*) as n FROM bottom_quality "
        "WHERE classification IS NOT NULL GROUP BY classification ORDER BY n DESC"
    )

    def _funnel_row(label, count, col=FG, pct_of=None, note=""):
        pct_str = ""
        if pct_of and pct_of > 0:
            pct_str = f'<span style="color:{DIM};font-size:0.78em;margin-left:8px">({count/pct_of*100:.1f}%)</span>'
        return (f'<tr>'
                f'<td style="padding:7px 16px;color:{DIM};font-size:0.83em;width:220px">{label}</td>'
                f'<td style="padding:7px 16px;font-size:1.05em;font-weight:700;color:{col}">'
                f'{count:,}{pct_str}</td>'
                f'<td style="padding:7px 16px;font-size:0.78em;color:{DIM}">{note}</td>'
                f'</tr>')

    funnel_html = (
        f'<table style="width:100%;border-collapse:collapse">'
        + _funnel_row("Discount Areas Evaluated", n_disc, B, None,   "all signals in signal_log")
        + _funnel_row("Accepted Signals",          n_accepted, G, n_disc,  "stored in research DB")
        + _funnel_row("Rejected / Not Stored",     n_rejected, R, n_disc,  "below acceptance threshold")
        + _funnel_row("Signals With Outcomes",     n_with_out, FG, n_accepted, "have bottom_quality data")
        + _funnel_row("Validated Bottoms (mfe_40d)", n_validated, G if validated_wr >= 65 else A, n_with_out, f"win rate {validated_wr:.1f}% (≥7% MFE)")
        + _funnel_row("Winners (mfe_40d ≥ 7%)",   n_winners, G, n_validated, "confirmed quality bottoms")
        + _funnel_row("Losers (mfe_40d < 7%)",     n_losers,  R, n_validated, "below quality threshold")
        + _funnel_row("Approved Validations",       n_val_app, G, None, f"out of {_db_scalar('SELECT COUNT(*) FROM validation_runs')} validation runs")
        + _funnel_row("Approved Optimizations",    n_opt_app, G, None, f"out of {_db_scalar('SELECT COUNT(*) FROM optimization_history')} optimization runs")
        + _funnel_row("Promotions to Production",  n_promote, G, None,  "deployed to live scoring")
        + _funnel_row("Rollbacks",                  n_rollback, A if n_rollback else FG, None, "auto-triggered on degradation")
        + '</table>'
    )

    class_html = ""
    if class_rows_data:
        class_col = {"Huge Winner": G, "Winner": G, "Neutral": A, "Loser": R, "Major Loser": R}
        class_html = _box("Bottom Classification Breakdown",
            f'<div style="display:flex;flex-wrap:wrap;gap:8px">'
            + "".join(
                f'<div style="background:{BG0};border:1px solid {BOR};border-radius:6px;'
                f'padding:8px 14px;min-width:120px;text-align:center">'
                f'<div style="font-size:0.75em;color:{class_col.get(r["classification"], FG)};'
                f'font-weight:600;margin-bottom:4px">{r["classification"]}</div>'
                f'<div style="font-size:1.3em;font-weight:700;color:{FG}">{r["n"]}</div>'
                f'</div>'
                for r in class_rows_data
            )
            + f'</div>'
        )

    return f"""
<div style="background:{BG1};border:1px solid {BOR};border-radius:10px;padding:20px 24px;margin-bottom:18px">
  {_section_header("BOTTOM DISCOVERY PIPELINE", "🔭")}
  {_box("Opportunity Funnel (Live State)", funnel_html)}
  {class_html}
</div>"""


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — BACKBONE HEALTH: R1-R8 CENTRIC  [CONSTITUTION COMPLIANT]
# ══════════════════════════════════════════════════════════════════════════════

# R1-R8 backbone definitions — single source of truth for dashboard
_R1R8_DEFS = [
    ("r1_price",     "① r1 · Price Zone",    30),
    ("r2_ob",        "② r2 · Order Block",   10),
    ("r3_liquidity", "③ r3 · Liquidity",     20),
    ("r4_htf",       "④ r4 · HTF Structure", 10),
    ("r5_avwap",     "⑤ r5 · AVWAP",          8),
    ("r6_macd",      "⑥ r6 · MACD Context",   4),
    ("r7_div",       "⑦ r7 · Divergence",     3),
    ("r8_demand",    "⑧ r8 · Demand Zone",   15),
]

# Labs whose output routes to each r-factor (from SUBFACTOR_PARENT mapping)
_FACTOR_LABS = {
    "r1_price":     ["factor_lab", "discount_zone_miner"],
    "r2_ob":        ["factor_lab"],
    "r3_liquidity": ["factor_lab", "edge_discovery"],
    "r4_htf":       ["factor_lab"],
    "r5_avwap":     ["factor_lab"],
    "r6_macd":      ["factor_lab"],
    "r7_div":       ["factor_lab"],
    "r8_demand":    ["factor_lab", "discount_zone_miner"],
}

# Sub-signals that route to each r-factor (from knowledge_base.SUBFACTOR_PARENT)
_SUBFACTOR_TO_RFACTOR = {
    "wick_rejection": "r3_liquidity", "equal_lows": "r3_liquidity",
    "sweep_detected": "r3_liquidity", "order_block_present": "r2_ob",
    "stopping_volume": "r8_demand",   "hvn_hit": "r8_demand",
    "sv_hit": "r8_demand",            "htf_higher_high": "r4_htf",
    "htf_hh_and_hl": "r4_htf",       "htf_hh": "r4_htf",
    "htf_hl": "r4_htf",              "rsi_div": "r7_div",
    "macd_div": "r7_div",
}


def _factor_status_label(finding: dict, sug_w) -> tuple:
    """Return (label, color) for a factor's current constitution status."""
    if not finding:
        return "Stable", DIM
    verdict = finding.get("verdict", "")
    val_st  = finding.get("validation_status", "pending")
    if sug_w is not None and val_st == "validated":
        return "Promotion Candidate", B
    if verdict in ("POSITIVE", "TAIL_DRIVER"):
        return "Improving", G
    if verdict == "NEGATIVE":
        return "Needs Improvement", R
    if finding and val_st == "pending":
        return "Under Investigation", A
    return "Stable", DIM


def _section_todays_learning() -> str:
    """Backbone Health — R1-R8 centric primary view (Constitution §THE BACKBONE)."""
    kb_data  = _load("knowledge_base.json")
    ff_raw   = kb_data.get("factor_findings", {}) if isinstance(kb_data, dict) else {}
    archived = kb_data.get("archived_findings", {}) if isinstance(kb_data, dict) else {}
    weights  = _load("config/weights.json")
    rm       = _load("gx_research_memory.json")
    ri       = rm.get("research_items", {}) if isinstance(rm, dict) else {}
    mem      = _load("gx_learning_memory.json")
    cycles   = mem.get("cycles", []) if isinstance(mem, dict) else []

    today_str = _now_cairo().strftime("%Y-%m-%d")

    # Map research items to r-factors (by indicator field)
    factor_ri_count: dict = {}
    for _itm in ri.values():
        ind = _itm.get("indicator", "")
        target = ind if ind in {k for k, _, _ in _R1R8_DEFS} else _SUBFACTOR_TO_RFACTOR.get(ind)
        if target:
            factor_ri_count[target] = factor_ri_count.get(target, 0) + 1

    # Count archived sub-signals per r-factor
    factor_archived: dict = {}
    for sf, dat in (archived.items() if isinstance(archived, dict) else []):
        parent = dat.get("routes_to") or _SUBFACTOR_TO_RFACTOR.get(sf)
        if parent:
            factor_archived[parent] = factor_archived.get(parent, 0) + 1

    # ── Backbone summary (weakest / strongest / needs-improvement / candidates) ──
    r1r8_keys = [k for k, _, _ in _R1R8_DEFS]
    scored = [
        (k, ff_raw.get(k, {}))
        for k in r1r8_keys if isinstance(ff_raw.get(k), dict)
    ]
    weakest   = min(scored, key=lambda x: x[1].get("win_rate") or 1, default=(None, {}))
    strongest = max(scored, key=lambda x: x[1].get("win_rate") or 0, default=(None, {}))

    needs_impr = []
    promo_cands = []
    for k, _, dw in _R1R8_DEFS:
        f = ff_raw.get(k, {}) if isinstance(ff_raw.get(k), dict) else {}
        st, _ = _factor_status_label(f, f.get("suggested_weight"))
        if st == "Needs Improvement":  needs_impr.append(k)
        if st == "Promotion Candidate": promo_cands.append(k)

    summary_bar = (
        f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:14px">'
        f'<div style="background:{BG2};border:1px solid {R};border-radius:6px;padding:10px;text-align:center">'
        f'<div style="font-size:0.68em;color:{DIM};margin-bottom:3px;text-transform:uppercase">Weakest Factor</div>'
        f'<div style="font-size:0.88em;font-weight:700;color:{R}">{weakest[0] or "—"}</div>'
        f'<div style="font-size:0.73em;color:{DIM}">WR {_pct(weakest[1].get("win_rate")) if weakest[0] else "—"}</div>'
        f'</div>'
        f'<div style="background:{BG2};border:1px solid {G};border-radius:6px;padding:10px;text-align:center">'
        f'<div style="font-size:0.68em;color:{DIM};margin-bottom:3px;text-transform:uppercase">Strongest Factor</div>'
        f'<div style="font-size:0.88em;font-weight:700;color:{G}">{strongest[0] or "—"}</div>'
        f'<div style="font-size:0.73em;color:{DIM}">WR {_pct(strongest[1].get("win_rate")) if strongest[0] else "—"}</div>'
        f'</div>'
        f'<div style="background:{BG2};border:1px solid {R};border-radius:6px;padding:10px;text-align:center">'
        f'<div style="font-size:0.68em;color:{DIM};margin-bottom:3px;text-transform:uppercase">Needs Improvement</div>'
        f'<div style="font-size:0.88em;font-weight:700;color:{R}">{len(needs_impr)}/8</div>'
        f'<div style="font-size:0.73em;color:{DIM}">{", ".join(needs_impr[:2]) or "none"}</div>'
        f'</div>'
        f'<div style="background:{BG2};border:1px solid {B};border-radius:6px;padding:10px;text-align:center">'
        f'<div style="font-size:0.68em;color:{DIM};margin-bottom:3px;text-transform:uppercase">Promotion Candidates</div>'
        f'<div style="font-size:0.88em;font-weight:700;color:{B}">{len(promo_cands)}/8</div>'
        f'<div style="font-size:0.73em;color:{DIM}">{", ".join(promo_cands[:2]) or "none"}</div>'
        f'</div>'
        f'</div>'
    )

    # ── 8 R1-R8 factor cards ──────────────────────────────────────────────────
    cards_html = ""
    for key, label, default_w in _R1R8_DEFS:
        f = ff_raw.get(key, {}) if isinstance(ff_raw.get(key), dict) else {}
        cur_w   = float(weights.get(key, default_w))
        sug_w   = f.get("suggested_weight")
        sug_wf  = float(sug_w) if sug_w is not None else None
        verdict = f.get("verdict", "—")
        wr      = f.get("win_rate")
        exp_    = f.get("expectancy")
        exp_imp = str(f.get("expected_improvement") or f.get("production_impact") or "—")[:45]
        val_st  = f.get("validation_status", "—")
        n_samp  = f.get("sample_n", "—")
        n_arch  = factor_archived.get(key, 0)
        n_ri    = factor_ri_count.get(key, 0)
        labs    = ", ".join(_FACTOR_LABS.get(key, ["factor_lab"]))

        status, st_col = _factor_status_label(f, sug_wf)
        vrd_col = G if verdict in ("POSITIVE", "TAIL_DRIVER") else R if verdict == "NEGATIVE" else DIM

        promo_note = ""
        if sug_wf is not None:
            delta = sug_wf - cur_w
            sign  = "+" if delta >= 0 else ""
            promo_note = (
                f'<div style="margin-top:6px;padding:4px 6px;background:{BG0};'
                f'border-radius:4px;font-size:0.75em;color:{A}">'
                f'Suggested weight: {sug_wf:.2f} ({sign}{delta:.2f})</div>'
            )

        cards_html += (
            f'<div style="background:{BG2};border:1px solid '
            f'{st_col if status not in ("Stable","Monitoring") else BOR};'
            f'border-radius:8px;padding:12px 13px">'

            f'<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:9px">'
            f'<span style="font-size:0.83em;font-weight:700;color:{FG}">{label}</span>'
            f'<span style="background:{st_col};color:#000;padding:2px 7px;border-radius:3px;'
            f'font-size:0.68em;font-weight:700">{status.upper()}</span>'
            f'</div>'

            f'<div style="display:grid;grid-template-columns:90px 1fr;gap:3px 6px;font-size:0.77em">'
            f'<span style="color:{DIM}">Verdict</span>'
            f'<span style="color:{vrd_col};font-weight:600">{verdict}</span>'
            f'<span style="color:{DIM}">Weight</span>'
            f'<span style="color:{B}">{cur_w:.1f}'
            f'<span style="color:{DIM};font-size:0.85em"> (dflt {default_w})</span></span>'
            f'<span style="color:{DIM}">Win Rate</span>'
            f'<span style="color:{G if (wr or 0)>=0.40 else DIM}">'
            f'{_pct(wr) if wr else "—"}</span>'
            f'<span style="color:{DIM}">Expectancy</span>'
            f'<span style="color:{FG}">{_pct(exp_) if exp_ else "—"}</span>'
            f'<span style="color:{DIM}">Exp. Impact</span>'
            f'<span style="color:{A}">{exp_imp}</span>'
            f'<span style="color:{DIM}">Validation</span>'
            f'<span style="color:{G if val_st=="validated" else A if val_st=="pending" else DIM}">'
            f'{val_st}</span>'
            f'<span style="color:{DIM}">Open Findings</span>'
            f'<span style="color:{A if n_arch else DIM}">{n_arch} sub-signals</span>'
            f'<span style="color:{DIM}">Linked Research</span>'
            f'<span style="color:{B if n_ri else DIM}">{n_ri} items</span>'
            f'<span style="color:{DIM}">Active Labs</span>'
            f'<span style="color:{FG}">{labs}</span>'
            f'<span style="color:{DIM}">Sample</span>'
            f'<span style="color:{DIM}">n={n_samp}</span>'
            f'</div>'
            f'{promo_note}'
            f'</div>'
        )

    # ── Activity summary (secondary — not the primary focus) ─────────────────
    today_cycles = [c for c in reversed(cycles)
                    if str(c.get("recorded_at", "")).startswith(today_str)]
    last_cycle   = (today_cycles or list(reversed(cycles)) or [{}])[0]
    n_promoted   = _db_scalar(
        "SELECT COUNT(*) FROM deployment_log WHERE action='PROMOTE' AND deployed_at >= ?",
        (today_str,)
    )
    n_outcomes = _db_scalar(
        "SELECT COUNT(*) FROM bottom_quality WHERE computed_at >= ?", (today_str,)
    )
    deployments = _db_query("SELECT * FROM deployment_log ORDER BY id DESC LIMIT 5")
    dep_rows = "".join(
        f'<tr>'
        f'<td style="padding:4px 10px;color:{DIM};font-size:0.79em;white-space:nowrap">'
        f'{_ts(d.get("deployed_at"))}</td>'
        f'<td style="padding:4px 10px">'
        f'{_badge(d.get("action")=="PROMOTE","PROMOTE","ROLLBACK",d.get("action")=="ROLLBACK")}</td>'
        f'<td style="padding:4px 10px;font-size:0.79em;color:#aab">{d.get("triggered_by","—")}</td>'
        f'<td style="padding:4px 10px;font-size:0.79em;color:{DIM}">'
        f'{str(d.get("note",""))[:55]}</td>'
        f'</tr>'
        for d in deployments
    ) or f'<tr><td colspan=4 style="color:{DIM};padding:4px 10px;font-size:0.8em">—</td></tr>'

    lv_txt = (
        f'verdict={last_cycle.get("verdict","?")} · '
        f'{"promoted" if last_cycle.get("promoted") else "not promoted"}'
    ) if last_cycle else "no cycles recorded"

    act_summary = (
        f'<div style="display:flex;gap:20px;font-size:0.8em;flex-wrap:wrap;color:{DIM};margin-bottom:6px">'
        f'<span>Today ({today_str}): '
        f'<b style="color:{FG}">{len(today_cycles)}</b> cycle(s) · '
        f'<b style="color:{G}">{n_promoted}</b> promotion(s) · '
        f'<b style="color:{B}">{n_outcomes}</b> outcomes matured</span>'
        f'<span>Last cycle: <b style="color:{FG}">{lv_txt}</b></span>'
        f'</div>'
    )

    return f"""
<div style="background:{BG1};border:1px solid {BOR};border-radius:10px;padding:20px 24px;margin-bottom:18px">
  {_section_header("BACKBONE HEALTH — R1-R8", "🧠")}

  {summary_bar}

  <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:14px">
    {cards_html}
  </div>

  {_box("Activity Today",
    act_summary +
    f'<table style="width:100%;border-collapse:collapse">'
    f'<tr style="font-size:0.77em;color:{DIM}">'
    f'<th style="text-align:left;padding:3px 10px">Time</th>'
    f'<th style="text-align:left;padding:3px 10px">Action</th>'
    f'<th style="text-align:left;padding:3px 10px">Triggered By</th>'
    f'<th style="text-align:left;padding:3px 10px">Note</th></tr>'
    f'{dep_rows}</table>'
  )}
</div>"""


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — R1-R8 EVOLUTION PIPELINE  [CONSTITUTION COMPLIANT]
# ══════════════════════════════════════════════════════════════════════════════

def _section_current_research() -> str:
    """R1-R8 Evolution Pipeline — research organized by backbone factor."""
    kb_data  = _load("knowledge_base.json")
    ff_raw   = kb_data.get("factor_findings", {}) if isinstance(kb_data, dict) else {}
    archived = kb_data.get("archived_findings", {}) if isinstance(kb_data, dict) else {}
    weights  = _load("config/weights.json")
    rm       = _load("gx_research_memory.json")
    ri       = rm.get("research_items", {}) if isinstance(rm, dict) else {}

    MIN_OUTCOMES_PER_CYCLE = 10
    MAX_PROMOTIONS_PER_DAY = 3
    mem_summary = {}
    try:
        from continuous_learning import LearningMemory, MIN_OUTCOMES_PER_CYCLE, MAX_PROMOTIONS_PER_DAY
        mem_summary = LearningMemory().get_summary()
    except BaseException:
        pass

    recent_promo = 0
    try:
        from continuous_learning import LearningMemory
        recent_promo = LearningMemory().get_recent_promotions_count(hours=24)
    except BaseException:
        pass

    last_exp   = _db_query("SELECT lab, run_at FROM experiment_log ORDER BY id DESC LIMIT 1")
    last_verd  = _db_query("SELECT verdict, oos_wr, run_at FROM validation_runs ORDER BY id DESC LIMIT 1")
    lv         = last_verd[0] if last_verd else {}
    n_outcomes = _db_scalar("SELECT COUNT(*) FROM bottom_quality WHERE mfe_40d IS NOT NULL") or 0
    today_str  = _now_cairo().strftime("%Y-%m-%d")
    cutoff_40d = (_now_cairo() - timedelta(days=40)).strftime("%Y-%m-%d")
    n_maturing = _db_scalar(
        "SELECT COUNT(*) FROM signals s LEFT JOIN bottom_quality bq ON s.id=bq.signal_id "
        "WHERE s.signal_date >= ? AND s.signal_date <= ? AND bq.mfe_40d IS NULL",
        (cutoff_40d, today_str)
    )

    # Map research items to r-factors
    factor_ri: dict = {k: [] for k, _, _ in _R1R8_DEFS}
    unmapped_ri = []
    for iid, itm in ri.items():
        ind = itm.get("indicator", "")
        target = ind if ind in factor_ri else _SUBFACTOR_TO_RFACTOR.get(ind)
        if target and target in factor_ri:
            factor_ri[target].append(itm)
        else:
            unmapped_ri.append(itm)

    # Map archived sub-signals per r-factor
    factor_arch: dict = {k: [] for k, _, _ in _R1R8_DEFS}
    for sf, dat in (archived.items() if isinstance(archived, dict) else []):
        parent = dat.get("routes_to") or _SUBFACTOR_TO_RFACTOR.get(sf)
        if parent and parent in factor_arch:
            factor_arch[parent].append((sf, dat))

    # ── Per-factor evolution pipeline rows ───────────────────────────────────
    pipeline_rows = ""
    for key, label, default_w in _R1R8_DEFS:
        f     = ff_raw.get(key, {}) if isinstance(ff_raw.get(key), dict) else {}
        cur_w = float(weights.get(key, default_w))
        sug_w = f.get("suggested_weight")
        sug_wf = float(sug_w) if sug_w is not None else None

        verdict = f.get("verdict", "—")
        val_st  = f.get("validation_status", "—")
        exp_imp = str(f.get("expected_improvement") or f.get("production_impact") or "—")[:40]
        n_ri_   = len(factor_ri.get(key, []))
        n_arch_ = len(factor_arch.get(key, []))

        status, st_col = _factor_status_label(f, sug_wf)

        # Pipeline stage
        if sug_wf is not None and val_st == "validated":
            stage, sc = "Promotion Candidate", B
        elif verdict in ("POSITIVE", "TAIL_DRIVER") and val_st == "validated":
            stage, sc = "Validated", G
        elif f and val_st == "pending":
            stage, sc = "Validation", A
        elif f:
            stage, sc = "Discovery", A
        else:
            stage, sc = "Monitoring", DIM

        # Next action
        if stage == "Promotion Candidate":
            nxt = f"Promote — suggested weight {sug_wf:.2f} vs current {cur_w:.2f}"
        elif verdict == "NEGATIVE":
            nxt = "Investigate — factor_lab targets this factor next cycle"
        elif n_ri_ > 0:
            nxt = f"{n_ri_} active research item(s)"
        elif n_arch_ > 0:
            nxt = f"{n_arch_} sub-signal(s) archived — awaiting r-factor improvement"
        else:
            nxt = "Monitoring — awaiting new outcome data"

        vrd_col = G if verdict in ("POSITIVE","TAIL_DRIVER") else R if verdict == "NEGATIVE" else DIM

        pipeline_rows += (
            f'<tr style="border-bottom:1px solid {BOR}">'
            f'<td style="padding:7px 10px;font-size:0.82em;font-weight:600;color:{FG}">{label}</td>'
            f'<td style="padding:7px 10px">'
            f'<span style="background:{sc};color:#000;padding:2px 7px;border-radius:3px;'
            f'font-size:0.70em;font-weight:700">{stage.upper()}</span></td>'
            f'<td style="padding:7px 10px;font-size:0.79em;color:{vrd_col}">{verdict}</td>'
            f'<td style="padding:7px 10px;font-size:0.78em;color:{A}">{exp_imp}</td>'
            f'<td style="padding:7px 10px;font-size:0.78em;color:{DIM}">{nxt[:65]}</td>'
            f'</tr>'
        )

    # ── Unmapped research (Research Only — no production influence) ──────────
    unmapped_html = ""
    if unmapped_ri:
        u_rows = "".join(
            f'<tr>'
            f'<td style="padding:4px 10px;font-size:0.79em;color:{A}">'
            f'{u.get("indicator","?")}</td>'
            f'<td style="padding:4px 10px;font-size:0.79em;color:{FG}">'
            f'{str(u.get("title","?"))[:55]}</td>'
            f'<td style="padding:4px 10px;font-size:0.75em;color:{DIM}">'
            f'Research Only · Production Influence = No</td>'
            f'</tr>'
            for u in unmapped_ri[:5]
        )
        unmapped_html = _box(
            f"Unmapped Research Assets ({len(unmapped_ri)} — Research Only, No Production Influence)",
            f'<table style="width:100%;border-collapse:collapse">'
            f'<tr style="font-size:0.73em;color:{DIM}">'
            f'<th style="text-align:left;padding:3px 10px">Indicator</th>'
            f'<th style="text-align:left;padding:3px 10px">Title</th>'
            f'<th style="text-align:left;padding:3px 10px">Status</th></tr>'
            f'{u_rows}</table>', color=DIM
        )

    # ── System pipeline state ─────────────────────────────────────────────────
    recent_c = mem_summary.get("recent_cycles", [])
    last_c   = recent_c[-1] if recent_c else {}
    last_out = last_c.get("outcomes_processed", 0) or 0
    need_more = max(0, MIN_OUTCOMES_PER_CYCLE - last_out)
    cb_ok     = recent_promo < MAX_PROMOTIONS_PER_DAY
    pend_promo = lv.get("verdict") == "APPROVED" and not last_c.get("promoted", False)

    sys_rows = "".join([
        _row2("Outcomes (mfe_40d)", f"{n_outcomes:,}",
              f"{n_maturing} signals still maturing"),
        _row2("Last Lab Run",
              _ts(last_exp[0].get("run_at")) if last_exp else "—",
              last_exp[0].get("lab","—") if last_exp else ""),
        _row2("Last Validation",
              _badge(lv.get("verdict")=="APPROVED","APPROVED",lv.get("verdict","—")),
              f'OOS WR={_pct(lv.get("oos_wr"))} · {_ts(lv.get("run_at"))}'),
        _row2("Promotion Gate",
              _badge(cb_ok, "OPEN", "CIRCUIT BREAKER", warn=not cb_ok),
              f"{recent_promo}/{MAX_PROMOTIONS_PER_DAY} promotions in 24h"
              + (" · APPROVED pending" if pend_promo else "")),
        _row2("Data Threshold",
              f"Need {need_more} more" if need_more else "Ready",
              f"threshold={MIN_OUTCOMES_PER_CYCLE} · last cycle had {last_out}"),
    ])

    return f"""
<div style="background:{BG1};border:1px solid {BOR};border-radius:10px;padding:20px 24px;margin-bottom:18px">
  {_section_header("R1-R8 EVOLUTION PIPELINE", "🔬")}

  {_box("Factor Evolution — Stage · Verdict · Expected Impact · Next Action",
    f'<table style="width:100%;border-collapse:collapse">'
    f'<tr style="font-size:0.73em;color:{DIM}">'
    f'<th style="text-align:left;padding:3px 10px">Factor</th>'
    f'<th style="text-align:left;padding:3px 10px">Pipeline Stage</th>'
    f'<th style="text-align:left;padding:3px 10px">Verdict</th>'
    f'<th style="text-align:left;padding:3px 10px">Expected Impact</th>'
    f'<th style="text-align:left;padding:3px 10px">Next Action</th></tr>'
    f'{pipeline_rows}</table>'
  )}

  {unmapped_html}

  {_box("System Pipeline State",
    f'<table style="width:100%;border-collapse:collapse">{sys_rows}</table>'
  )}
</div>"""


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — PRODUCTION ALPHA SNAPSHOT  [NEW]
# ══════════════════════════════════════════════════════════════════════════════

def _section_production_snapshot() -> str:
    weights  = _load("config/weights.json")
    kb_data  = _load("knowledge_base.json")
    ff       = _ff_list(kb_data)
    mem      = _load("gx_learning_memory.json")

    # Latest validation
    lv_rows = _db_query("SELECT * FROM validation_runs ORDER BY id DESC LIMIT 1")
    lv = lv_rows[0] if lv_rows else {}

    # Best OOS WR
    best_oos = mem.get("best_approved_oos_wr", 0) or 0

    # OOS metrics
    oos_wr  = lv.get("oos_wr", 0) or 0
    oos_sh  = lv.get("oos_sharpe", 0) or 0
    oos_exp = _db_scalar("""
        SELECT AVG(bq.mfe_40d) FROM (
            SELECT bq.mfe_40d FROM bottom_quality bq JOIN signals s ON s.id=bq.signal_id
            WHERE bq.mfe_40d IS NOT NULL ORDER BY s.signal_date ASC
            LIMIT -1 OFFSET (SELECT CAST(COUNT(*)*0.8 AS INT) FROM bottom_quality WHERE mfe_40d IS NOT NULL)
        ) bq
    """) or 0
    val_wr  = lv.get("val_wr", 0) or 0
    train_wr = lv.get("train_wr", 0) or 0

    # Expansion and hold window from bottom_quality
    avg_days_to_peak = _db_scalar(
        "SELECT AVG(days_to_peak) FROM bottom_quality WHERE days_to_peak IS NOT NULL AND days_to_peak > 0"
    ) or 0
    median_mfe40 = _db_scalar(
        "SELECT AVG(mfe_40d) FROM bottom_quality WHERE mfe_40d IS NOT NULL"
    ) or 0
    avg_peak_1y = _db_scalar(
        "SELECT AVG(peak_return_1y) FROM bottom_quality WHERE peak_return_1y IS NOT NULL AND peak_return_1y > 0"
    ) or 0
    fib_30pct = _db_scalar(
        "SELECT COUNT(*) FROM bottom_quality WHERE peak_return_1y >= 0.30 AND peak_return_1y IS NOT NULL"
    )
    fib_50pct = _db_scalar(
        "SELECT COUNT(*) FROM bottom_quality WHERE peak_return_1y >= 0.50 AND peak_return_1y IS NOT NULL"
    )
    fib_100pct = _db_scalar(
        "SELECT COUNT(*) FROM bottom_quality WHERE peak_return_1y >= 1.00 AND peak_return_1y IS NOT NULL"
    )
    n_with_peak = _db_scalar("SELECT COUNT(*) FROM bottom_quality WHERE peak_return_1y IS NOT NULL") or 1

    # Top factors
    verdicts = {"POSITIVE": G, "NEGATIVE": R, "TAIL_DRIVER": A, "NEUTRAL": DIM}
    pos_factors = sorted(
        [f for f in ff if isinstance(f, dict) and f.get("verdict") == "POSITIVE"],
        key=lambda x: x.get("win_rate") or 0, reverse=True
    )[:5]
    neg_factors = sorted(
        [f for f in ff if isinstance(f, dict) and f.get("verdict") == "NEGATIVE"],
        key=lambda x: x.get("win_rate") or 1
    )[:3]
    tail_factors = [f for f in ff if isinstance(f, dict) and (f.get("tail_contribution") or 0) > 0]

    # Weights table
    w_numeric = {k: v for k, v in weights.items() if isinstance(v, (int, float))}
    total_w   = sum(w_numeric.values()) or 1
    w_sorted  = sorted(w_numeric.items(), key=lambda x: x[1], reverse=True)

    weight_cells = "".join(
        f'<div style="background:{BG0};border:1px solid {BOR};border-radius:6px;'
        f'padding:8px 12px;min-width:110px">'
        f'<div style="font-size:0.72em;color:{DIM};margin-bottom:3px">{k}</div>'
        f'<div style="font-size:1.1em;font-weight:700;color:{B}">{v:.1f}</div>'
        f'<div style="width:100%;height:4px;background:{BOR};border-radius:2px;margin-top:4px">'
        f'<div style="width:{min(100, v/total_w*100):.0f}%;height:4px;background:{B};border-radius:2px"></div>'
        f'</div></div>'
        for k, v in w_sorted
    )
    weights_updated = weights.get("updated_at", "?")

    def _factor_row(f, col):
        wr  = f.get("win_rate")
        exp = f.get("expectancy")
        n   = f.get("sample_n")
        dt  = str(f.get("recorded_at", ""))[:10]
        conf = f.get("confidence") or (f"{wr*100:.0f}%" if wr else "—")
        return (f'<tr>'
                f'<td style="padding:5px 10px;font-size:0.83em;color:{col};font-weight:600">'
                f'{f.get("factor","?")}</td>'
                f'<td style="padding:5px 10px;font-size:0.8em;color:{FG}">'
                f'WR={_pct(wr) if wr else "—"}</td>'
                f'<td style="padding:5px 10px;font-size:0.8em;color:{FG}">'
                f'n={n or "—"}</td>'
                f'<td style="padding:5px 10px;font-size:0.79em;color:{DIM}">{dt}</td>'
                f'</tr>')

    pos_rows  = "".join(_factor_row(f, G) for f in pos_factors) or \
                f'<tr><td colspan=4 style="color:{DIM};padding:5px 10px;font-size:0.8em">—</td></tr>'
    neg_rows  = "".join(_factor_row(f, R) for f in neg_factors) or \
                f'<tr><td colspan=4 style="color:{DIM};padding:5px 10px;font-size:0.8em">—</td></tr>'
    tail_rows = "".join(_factor_row(f, A) for f in tail_factors) or \
                f'<tr><td colspan=4 style="color:{DIM};padding:5px 10px;font-size:0.8em">—</td></tr>'

    # KPI strip
    kpi_items = [
        ("OOS Win Rate",       _pct(oos_wr),   G if oos_wr >= 0.65 else A),
        ("Best OOS WR",        _pct(best_oos), B),
        ("OOS Expectancy",     _pct(oos_exp),  G if oos_exp >= 0.10 else A),
        ("OOS Sharpe",         _num(oos_sh, ".2f"), G if oos_sh >= 2.0 else A),
        ("Train WR",           _pct(train_wr), G if train_wr >= 0.65 else A),
        ("Avg Days to Peak",   f"{avg_days_to_peak:.0f}d", B),
        ("Avg MFE 40d",        _pct(median_mfe40), G if median_mfe40 >= 0.07 else A),
        ("Avg Peak 1Y",        _pct(avg_peak_1y),  G if avg_peak_1y >= 0.30 else A),
    ]
    kpi_html = "".join(
        f'<div style="flex:1;min-width:100px;text-align:center;background:{BG2};'
        f'border-radius:7px;padding:10px 6px;margin:3px">'
        f'<div style="font-size:0.72em;color:{DIM};text-transform:uppercase;letter-spacing:0.05em;margin-bottom:3px">{k}</div>'
        f'<div style="font-size:1.2em;font-weight:700;color:{c}">{v}</div></div>'
        for k, v, c in kpi_items
    )

    # Fibonacci expansion summary
    fib_html = (
        f'<div style="display:flex;gap:16px;font-size:0.83em;flex-wrap:wrap">'
        f'<span style="color:{DIM}">Fib ≥30%: <b style="color:{G}">{fib_30pct}</b>'
        f' ({fib_30pct/n_with_peak*100:.0f}%)</span>'
        f'<span style="color:{DIM}">Fib ≥50%: <b style="color:{G}">{fib_50pct}</b>'
        f' ({fib_50pct/n_with_peak*100:.0f}%)</span>'
        f'<span style="color:{DIM}">Multi-bagger ≥100%: <b style="color:{A}">{fib_100pct}</b>'
        f' ({fib_100pct/n_with_peak*100:.0f}%)</span>'
        f'<span style="color:{DIM}">Avg Peak: <b style="color:{B}">{_pct(avg_peak_1y)}</b></span>'
        f'<span style="color:{DIM}">Avg Hold: <b style="color:{B}">{avg_days_to_peak:.0f} days</b></span>'
        f'</div>'
    )

    val_regime = lv.get("split_type", "—")
    robustness = lv.get("robustness_score", 0) or 0
    overfit    = lv.get("overfit_flag", 0)

    return f"""
<div style="background:{BG1};border:1px solid {BOR};border-radius:10px;padding:20px 24px;margin-bottom:18px">
  {_section_header("PRODUCTION ALPHA SNAPSHOT", "🎯")}

  <div style="display:flex;flex-wrap:wrap;gap:3px;margin-bottom:12px">{kpi_html}</div>

  {_box(f"Current Production Weights (updated {weights_updated})",
    f'<div style="display:flex;flex-wrap:wrap;gap:6px">{weight_cells}</div>')}

  <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px">
    {_box("Top Positive Factors",
      f'<table style="width:100%;border-collapse:collapse">'
      f'<tr style="font-size:0.75em;color:{DIM}"><th style="text-align:left;padding:3px 10px">Factor</th>'
      f'<th style="text-align:left;padding:3px 10px">Win Rate</th>'
      f'<th style="text-align:left;padding:3px 10px">Sample</th>'
      f'<th style="text-align:left;padding:3px 10px">Date</th></tr>'
      f'{pos_rows}</table>', color=G)}

    {_box("Top Negative Factors",
      f'<table style="width:100%;border-collapse:collapse">'
      f'<tr style="font-size:0.75em;color:{DIM}"><th style="text-align:left;padding:3px 10px">Factor</th>'
      f'<th style="text-align:left;padding:3px 10px">Win Rate</th>'
      f'<th style="text-align:left;padding:3px 10px">Sample</th>'
      f'<th style="text-align:left;padding:3px 10px">Date</th></tr>'
      f'{neg_rows}</table>', color=R)}

    {_box("Tail Drivers",
      f'<table style="width:100%;border-collapse:collapse">'
      f'<tr style="font-size:0.75em;color:{DIM}"><th style="text-align:left;padding:3px 10px">Factor</th>'
      f'<th style="text-align:left;padding:3px 10px">Win Rate</th>'
      f'<th style="text-align:left;padding:3px 10px">Sample</th>'
      f'<th style="text-align:left;padding:3px 10px">Date</th></tr>'
      f'{tail_rows}</table>', color=A)}
  </div>

  {_box("Validation Regime",
    f'<div style="display:flex;gap:24px;font-size:0.83em;flex-wrap:wrap">'
    f'<span style="color:{DIM}">Split: <b style="color:{FG}">{val_regime}</b></span>'
    f'<span style="color:{DIM}">Robustness: <b style="color:{G if robustness>=0.9 else A}">{_num(robustness,".3f")}</b></span>'
    f'<span style="color:{DIM}">Overfit: <b style="color:{R if overfit else G}">{"YES" if overfit else "NO"}</b></span>'
    f'<span style="color:{DIM}">Train/Val/OOS: <b style="color:{FG}">{_pct(train_wr)} / {_pct(val_wr)} / {_pct(oos_wr)}</b></span>'
    f'<span style="color:{DIM}">Last run: <b style="color:{B}">{_ts(lv.get("run_at"))}</b></span>'
    f'</div>')}

  {_box("Expected Fibonacci Expansion Potential (from validated bottoms)",
    fib_html)}
</div>"""


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — TOP KNOWLEDGE FINDINGS  [NEW]
# ══════════════════════════════════════════════════════════════════════════════

def _section_knowledge_findings() -> str:
    kb_data = _load("knowledge_base.json")
    ff      = _ff_list(kb_data)

    if not ff:
        return f"""
<div style="background:{BG1};border:1px solid {BOR};border-radius:10px;padding:20px 24px;margin-bottom:18px">
  {_section_header("TOP KNOWLEDGE FINDINGS", "📚")}
  <div style="color:{DIM};font-size:0.85em">No knowledge base findings yet.</div>
</div>"""

    positives = sorted(
        [f for f in ff if isinstance(f, dict) and f.get("verdict") == "POSITIVE"],
        key=lambda x: (x.get("win_rate") or 0), reverse=True
    )
    negatives = sorted(
        [f for f in ff if isinstance(f, dict) and f.get("verdict") == "NEGATIVE"],
        key=lambda x: (x.get("win_rate") or 1)
    )
    tail_drivers = [f for f in ff if isinstance(f, dict) and (f.get("tail_contribution") or 0) > 0]
    neutral = [f for f in ff if isinstance(f, dict) and f.get("verdict") not in ("POSITIVE", "NEGATIVE")]

    def _kf_row(f, verdict_col):
        wr   = f.get("win_rate")
        exp  = f.get("expectancy")
        n    = f.get("sample_n")
        dt   = str(f.get("recorded_at", ""))[:10]
        tail = f.get("tail_contribution")
        src  = f.get("source", "—")
        tier = f.get("tier", "—")
        return (
            f'<tr>'
            f'<td style="padding:6px 10px;font-size:0.83em;color:{verdict_col};font-weight:600">'
            f'{f.get("factor","?")}</td>'
            f'<td style="padding:6px 10px">'
            f'<span style="background:{verdict_col};color:#000;padding:2px 7px;'
            f'border-radius:3px;font-size:0.75em;font-weight:700">{f.get("verdict","?")}</span></td>'
            f'<td style="padding:6px 10px;font-size:0.8em;color:{G if (wr or 0)>=0.60 else A if (wr or 0)>=0.40 else R}">'
            f'{_pct(wr) if wr is not None else "—"}</td>'
            f'<td style="padding:6px 10px;font-size:0.8em;color:{FG}">{n or "—"}</td>'
            f'<td style="padding:6px 10px;font-size:0.79em;color:{A}">{tail or "—"}</td>'
            f'<td style="padding:6px 10px;font-size:0.79em;color:{DIM}">{dt}</td>'
            f'</tr>'
        )

    all_sorted = positives + tail_drivers + negatives + neutral
    all_rows = "".join(_kf_row(f, {
        "POSITIVE": G, "NEGATIVE": R
    }.get(f.get("verdict",""), A)) for f in all_sorted) or \
        f'<tr><td colspan=6 style="color:{DIM};padding:5px 10px;font-size:0.8em">—</td></tr>'

    # Summary badges
    n_pos  = len(positives)
    n_neg  = len(negatives)
    n_tail = len(tail_drivers)
    n_neu  = len(neutral)

    summary_strip = (
        f'<div style="display:flex;gap:12px;margin-bottom:10px;flex-wrap:wrap;font-size:0.83em">'
        f'<span style="color:{DIM}">Positive: <b style="color:{G}">{n_pos}</b></span>'
        f'<span style="color:{DIM}">Negative: <b style="color:{R}">{n_neg}</b></span>'
        f'<span style="color:{DIM}">Tail Drivers: <b style="color:{A}">{n_tail}</b></span>'
        f'<span style="color:{DIM}">Neutral/Other: <b style="color:{FG}">{n_neu}</b></span>'
        f'<span style="color:{DIM}">Total: <b style="color:{B}">{len(ff)}</b></span>'
        f'</div>'
    )

    return f"""
<div style="background:{BG1};border:1px solid {BOR};border-radius:10px;padding:20px 24px;margin-bottom:18px">
  {_section_header("TOP KNOWLEDGE FINDINGS", "📚")}
  {summary_strip}
  {_box("All Factor Findings (Positive → Tail Drivers → Negative)",
    f'<table style="width:100%;border-collapse:collapse">'
    f'<tr style="font-size:0.75em;color:{DIM}">'
    f'<th style="text-align:left;padding:3px 10px">Factor</th>'
    f'<th style="text-align:left;padding:3px 10px">Verdict</th>'
    f'<th style="text-align:left;padding:3px 10px">Confidence</th>'
    f'<th style="text-align:left;padding:3px 10px">Sample</th>'
    f'<th style="text-align:left;padding:3px 10px">Tail Contr.</th>'
    f'<th style="text-align:left;padding:3px 10px">Discovery</th></tr>'
    f'{all_rows}</table>')}
</div>"""


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 7 — ALPHA PERFORMANCE
# ══════════════════════════════════════════════════════════════════════════════

def _section_alpha_performance() -> str:
    horizons = []
    for col, label in [("mfe_40d","MFE 40d"),("mfe_90d","MFE 90d"),("mfe_180d","MFE 180d"),("mfe_252d","MFE 252d")]:
        n    = _db_scalar(f"SELECT COUNT(*) FROM bottom_quality WHERE {col} IS NOT NULL")
        avg  = _db_scalar(f"SELECT AVG({col}) FROM bottom_quality WHERE {col} IS NOT NULL")
        oos_w = _db_scalar(
            f"SELECT SUM(CASE WHEN {col}>=0.07 THEN 1 ELSE 0 END) FROM ("
            f"SELECT bq.{col} FROM bottom_quality bq JOIN signals s ON s.id=bq.signal_id "
            f"WHERE bq.{col} IS NOT NULL ORDER BY s.signal_date ASC LIMIT -1 OFFSET "
            f"(SELECT CAST(COUNT(*)*0.8 AS INT) FROM bottom_quality WHERE {col} IS NOT NULL))"
        )
        oos_tot = _db_scalar(
            f"SELECT COUNT(*) FROM ("
            f"SELECT bq.{col} FROM bottom_quality bq JOIN signals s ON s.id=bq.signal_id "
            f"WHERE bq.{col} IS NOT NULL ORDER BY s.signal_date ASC LIMIT -1 OFFSET "
            f"(SELECT CAST(COUNT(*)*0.8 AS INT) FROM bottom_quality WHERE {col} IS NOT NULL))"
        ) or 1
        oos_wr = (oos_w or 0) / oos_tot
        horizons.append((label, n, avg or 0, oos_wr))

    horizon_rows = "".join(
        f'<tr>'
        f'<td style="padding:5px 10px;color:{DIM};font-size:0.82em">{h[0]}</td>'
        f'<td style="padding:5px 10px;font-size:0.82em;color:{FG}">{h[1]}</td>'
        f'<td style="padding:5px 10px;font-size:0.83em;color:{G if h[2]>=0.07 else A}">{_pct(h[2])}</td>'
        f'<td style="padding:5px 10px;font-size:0.83em;color:{G if h[3]>=0.65 else A if h[3]>=0.40 else R}">{_pct(h[3])}</td>'
        f'</tr>'
        for h in horizons
    )

    val_history = _db_query("""
        SELECT id, run_at, verdict, train_wr, val_wr, oos_wr, oos_sharpe, robustness_score
        FROM validation_runs
        GROUP BY oos_wr, oos_sharpe
        ORDER BY id DESC LIMIT 5
    """)
    val_rows_html = "".join(
        f'<tr>'
        f'<td style="padding:4px 10px;color:{DIM};font-size:0.79em">{_ts(v.get("run_at"))}</td>'
        f'<td style="padding:4px 10px">{_badge(v.get("verdict")=="APPROVED","APPROVED",v.get("verdict","?"))}</td>'
        f'<td style="padding:4px 10px;font-size:0.79em;color:{FG}">{_num(v.get("train_wr"))} / {_num(v.get("val_wr"))} / {_num(v.get("oos_wr"))}</td>'
        f'<td style="padding:4px 10px;font-size:0.79em;color:{FG}">{_num(v.get("oos_sharpe"))}</td>'
        f'<td style="padding:4px 10px;font-size:0.79em;color:{FG}">{_num(v.get("robustness_score"))}</td>'
        f'</tr>'
        for v in val_history
    ) or f'<tr><td colspan=5 style="color:{DIM};padding:4px 10px;font-size:0.8em">—</td></tr>'

    lv_rows = _db_query("SELECT * FROM validation_runs ORDER BY rowid DESC LIMIT 1")
    lv = lv_rows[0] if lv_rows else {}
    oos_wr  = lv.get("oos_wr", 0) or 0
    oos_sh  = lv.get("oos_sharpe", 0) or 0
    oos_exp = _db_scalar("""
        SELECT AVG(bq.mfe_40d) FROM (
            SELECT bq.mfe_40d FROM bottom_quality bq JOIN signals s ON s.id=bq.signal_id
            WHERE bq.mfe_40d IS NOT NULL ORDER BY s.signal_date ASC
            LIMIT -1 OFFSET (SELECT CAST(COUNT(*)*0.8 AS INT) FROM bottom_quality WHERE mfe_40d IS NOT NULL)
        ) bq
    """)

    kpi_items = [
        ("OOS Win Rate",   _pct(oos_wr),  G if oos_wr >= 0.65 else A),
        ("OOS Expectancy", _pct(oos_exp or 0), G if (oos_exp or 0) >= 0.10 else A),
        ("OOS Sharpe",     _num(oos_sh),  G if oos_sh >= 2.0 else A),
        ("Val Win Rate",   _pct(lv.get("val_wr", 0)), G if (lv.get("val_wr") or 0) >= 0.55 else A),
        ("Best OOS WR",    _pct(_load("gx_learning_memory.json").get("best_approved_oos_wr", 0)),  B),
    ]
    kpi_html = "".join(
        f'<div style="flex:1;min-width:120px;text-align:center;background:{BG2};'
        f'border-radius:7px;padding:12px 8px;margin:4px">'
        f'<div style="font-size:0.75em;color:{DIM};text-transform:uppercase;letter-spacing:0.06em;margin-bottom:4px">{k}</div>'
        f'<div style="font-size:1.4em;font-weight:700;color:{c}">{v}</div></div>'
        for k, v, c in kpi_items
    )

    return f"""
<div style="background:{BG1};border:1px solid {BOR};border-radius:10px;padding:20px 24px;margin-bottom:18px">
  {_section_header("ALPHA PERFORMANCE", "📊")}
  <div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:12px">{kpi_html}</div>

  {_box("Multi-Horizon MFE Performance",
    f'<table style="width:100%;border-collapse:collapse">'
    f'<tr style="font-size:0.77em;color:{DIM}">'
    f'<th style="text-align:left;padding:3px 10px">Horizon</th>'
    f'<th style="text-align:left;padding:3px 10px">N</th>'
    f'<th style="text-align:left;padding:3px 10px">Avg Return</th>'
    f'<th style="text-align:left;padding:3px 10px">OOS Win Rate</th></tr>'
    f'{horizon_rows}</table>')}

  {_box("Validation History (unique results)",
    f'<table style="width:100%;border-collapse:collapse">'
    f'<tr style="font-size:0.77em;color:{DIM}">'
    f'<th style="text-align:left;padding:3px 10px">Run At</th>'
    f'<th style="text-align:left;padding:3px 10px">Verdict</th>'
    f'<th style="text-align:left;padding:3px 10px">Train/Val/OOS WR</th>'
    f'<th style="text-align:left;padding:3px 10px">OOS Sharpe</th>'
    f'<th style="text-align:left;padding:3px 10px">Robustness</th></tr>'
    f'{val_rows_html}</table>')}
</div>"""


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 8 — CHANGES SINCE YESTERDAY  [NEW]
# ══════════════════════════════════════════════════════════════════════════════

def _section_changes_since_yesterday() -> str:
    yesterday = (_now_cairo() - timedelta(days=1)).strftime("%Y-%m-%d")
    today     = _now_cairo().strftime("%Y-%m-%d")

    kb_data   = _load("knowledge_base.json")
    ff        = _ff_list(kb_data)
    mem       = _load("gx_learning_memory.json")
    cycles    = mem.get("cycles", [])

    # Delta counts
    n_outcomes  = _db_scalar(
        "SELECT COUNT(*) FROM bottom_quality WHERE computed_at >= ?", (yesterday,)
    )
    n_signals   = _db_scalar(
        "SELECT COUNT(*) FROM signals WHERE created_at >= ?", (yesterday,)
    )
    n_findings  = sum(
        1 for f in ff if isinstance(f, dict) and str(f.get("recorded_at", "")) >= yesterday
    )
    n_promos    = _db_scalar(
        "SELECT COUNT(*) FROM deployment_log WHERE action='PROMOTE' AND deployed_at >= ?",
        (yesterday,)
    )
    n_rollbacks = _db_scalar(
        "SELECT COUNT(*) FROM deployment_log WHERE action='ROLLBACK' AND deployed_at >= ?",
        (yesterday,)
    )
    n_val       = _db_scalar(
        "SELECT COUNT(*) FROM validation_runs WHERE run_at >= ?", (yesterday,)
    )
    n_exp       = _db_scalar(
        "SELECT COUNT(*) FROM experiment_log WHERE run_at >= ?", (yesterday,)
    )
    n_cycles    = sum(
        1 for c in cycles if str(c.get("recorded_at", c.get("started_at", ""))) >= yesterday
    )
    n_opt       = _db_scalar(
        "SELECT COUNT(*) FROM optimization_history WHERE run_at >= ?", (yesterday,)
    )

    # Delta display helper
    def _delta(label, val, threshold=1, positive_is_good=True):
        sign  = "+"
        if val == 0:
            col = DIM
        elif positive_is_good:
            col = G if val >= threshold else A
        else:
            col = R if val >= threshold else A
        return (
            f'<div style="background:{BG2};border:1px solid {BOR};border-radius:7px;'
            f'padding:10px 14px;min-width:130px;flex:1">'
            f'<div style="font-size:0.72em;color:{DIM};text-transform:uppercase;'
            f'letter-spacing:0.05em;margin-bottom:5px">{label}</div>'
            f'<div style="font-size:1.6em;font-weight:700;color:{col}">'
            f'{sign if val>0 else ""}{val}</div>'
            f'</div>'
        )

    deltas_html = (
        f'<div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px">'
        + _delta("Outcomes Matured",  n_outcomes, 1, True)
        + _delta("New Signals",       n_signals,  1, True)
        + _delta("New Findings",      n_findings, 1, True)
        + _delta("Experiments Run",   n_exp,      1, True)
        + _delta("Validation Runs",   n_val,      1, True)
        + _delta("Learning Cycles",   n_cycles,   1, True)
        + _delta("Optimizations",     n_opt,      1, True)
        + _delta("Promotions",        n_promos,   1, True)
        + _delta("Rollbacks",         n_rollbacks, 1, False)
        + f'</div>'
    )

    # New findings detail
    new_ff = [
        f for f in ff
        if isinstance(f, dict) and str(f.get("recorded_at", "")) >= yesterday
    ]
    new_ff_rows = "".join(
        f'<tr>'
        f'<td style="padding:4px 10px;font-size:0.82em;'
        f'color:{G if f.get("verdict")=="POSITIVE" else R if f.get("verdict")=="NEGATIVE" else A}">'
        f'{f.get("verdict","?")}</td>'
        f'<td style="padding:4px 10px;font-size:0.82em;color:{FG};font-weight:600">{f.get("factor","?")}</td>'
        f'<td style="padding:4px 10px;font-size:0.79em;color:{DIM}">'
        f'WR={_pct(f.get("win_rate")) if f.get("win_rate") is not None else "—"} | '
        f'n={f.get("sample_n") or "—"}</td>'
        f'<td style="padding:4px 10px;font-size:0.79em;color:{DIM}">{_ts(f.get("recorded_at"))}</td>'
        f'</tr>'
        for f in sorted(new_ff, key=lambda x: x.get("recorded_at",""), reverse=True)
    ) or f'<tr><td colspan=4 style="color:{DIM};padding:4px 10px;font-size:0.8em">No new findings since yesterday</td></tr>'

    # New promotions / rollbacks
    new_deps = _db_query(
        "SELECT * FROM deployment_log WHERE deployed_at >= ? ORDER BY id DESC", (yesterday,)
    )
    dep_rows = "".join(
        f'<tr>'
        f'<td style="padding:4px 10px;color:{DIM};font-size:0.79em;white-space:nowrap">{_ts(d.get("deployed_at"))}</td>'
        f'<td style="padding:4px 10px">'
        f'{_badge(d.get("action")=="PROMOTE","⬆ PROMOTE","⬇ ROLLBACK",d.get("action")=="ROLLBACK")}</td>'
        f'<td style="padding:4px 10px;font-size:0.79em;color:{FG}">{d.get("triggered_by","—")}</td>'
        f'<td style="padding:4px 10px;font-size:0.79em;color:{DIM}">{str(d.get("note",""))[:60]}</td>'
        f'</tr>'
        for d in new_deps
    ) or f'<tr><td colspan=4 style="color:{DIM};padding:4px 10px;font-size:0.8em">No deployments since yesterday</td></tr>'

    # New outcomes (matured)
    new_outcomes = _db_query("""
        SELECT s.symbol, s.signal_date, bq.mfe_40d, bq.computed_at, bq.classification
        FROM bottom_quality bq JOIN signals s ON s.id=bq.signal_id
        WHERE bq.computed_at >= ?
        ORDER BY bq.computed_at DESC LIMIT 10
    """, (yesterday,))
    outcome_rows = "".join(
        f'<tr>'
        f'<td style="padding:4px 10px;font-size:0.82em;color:{FG};font-weight:600">{o.get("symbol","?")}</td>'
        f'<td style="padding:4px 10px;font-size:0.79em;color:{DIM}">{o.get("signal_date","?")}</td>'
        f'<td style="padding:4px 10px;font-size:0.82em;'
        f'color:{G if (o.get("mfe_40d") or 0)>=0.07 else R}">{_pct(o.get("mfe_40d"))}</td>'
        f'<td style="padding:4px 10px;font-size:0.79em;color:{A}">{o.get("classification","?")}</td>'
        f'</tr>'
        for o in new_outcomes
    ) or f'<tr><td colspan=4 style="color:{DIM};padding:4px 10px;font-size:0.8em">No new outcomes since yesterday</td></tr>'

    return f"""
<div style="background:{BG1};border:1px solid {BOR};border-radius:10px;padding:20px 24px;margin-bottom:18px">
  {_section_header("CHANGES SINCE YESTERDAY", "📅")}
  <div style="font-size:0.78em;color:{DIM};margin-bottom:10px">
    Comparing against: {yesterday} 00:00 → now
  </div>
  {deltas_html}

  <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
    {_box("New Knowledge Findings",
      f'<table style="width:100%;border-collapse:collapse">'
      f'<tr style="font-size:0.75em;color:{DIM}">'
      f'<th style="text-align:left;padding:3px 10px">Verdict</th>'
      f'<th style="text-align:left;padding:3px 10px">Factor</th>'
      f'<th style="text-align:left;padding:3px 10px">Stats</th>'
      f'<th style="text-align:left;padding:3px 10px">Time</th></tr>'
      f'{new_ff_rows}</table>')}

    {_box("New Deployments / Rollbacks",
      f'<table style="width:100%;border-collapse:collapse">'
      f'<tr style="font-size:0.75em;color:{DIM}">'
      f'<th style="text-align:left;padding:3px 10px">Time</th>'
      f'<th style="text-align:left;padding:3px 10px">Action</th>'
      f'<th style="text-align:left;padding:3px 10px">Triggered By</th>'
      f'<th style="text-align:left;padding:3px 10px">Note</th></tr>'
      f'{dep_rows}</table>')}
  </div>

  {_box("New Outcomes Matured",
    f'<table style="width:100%;border-collapse:collapse">'
    f'<tr style="font-size:0.75em;color:{DIM}">'
    f'<th style="text-align:left;padding:3px 10px">Symbol</th>'
    f'<th style="text-align:left;padding:3px 10px">Signal Date</th>'
    f'<th style="text-align:left;padding:3px 10px">MFE 40d</th>'
    f'<th style="text-align:left;padding:3px 10px">Class</th></tr>'
    f'{outcome_rows}</table>')}
</div>"""


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 9 — DEPLOYMENT HISTORY
# ══════════════════════════════════════════════════════════════════════════════

def _section_deployment_history() -> str:
    deps = _db_query("SELECT * FROM deployment_log ORDER BY id DESC LIMIT 20")

    rows_html = "".join(
        f'<tr style="border-bottom:1px solid {BOR}">'
        f'<td style="padding:6px 10px;color:{DIM};font-size:0.79em;white-space:nowrap">#{d.get("id","?")}</td>'
        f'<td style="padding:6px 10px;white-space:nowrap">'
        f'{_badge(d.get("action")=="PROMOTE","⬆ PROMOTE","⬇ ROLLBACK",d.get("action")=="ROLLBACK")}</td>'
        f'<td style="padding:6px 10px;color:{DIM};font-size:0.79em;white-space:nowrap">{_ts(d.get("deployed_at"))}</td>'
        f'<td style="padding:6px 10px;font-size:0.79em;color:{FG}">{d.get("triggered_by","—")}</td>'
        f'<td style="padding:6px 10px;font-size:0.79em;color:{DIM}">{d.get("validation_run_id") or "—"}</td>'
        f'<td style="padding:6px 10px;font-size:0.79em;color:#9aa">{str(d.get("note",""))[:70]}</td>'
        f'</tr>'
        for d in deps
    ) or f'<tr><td colspan=6 style="color:{DIM};padding:6px 10px;font-size:0.8em">No deployments yet</td></tr>'

    n_promo = _db_scalar("SELECT COUNT(*) FROM deployment_log WHERE action='PROMOTE'")
    n_rb    = _db_scalar("SELECT COUNT(*) FROM deployment_log WHERE action='ROLLBACK'")
    n_snaps = _db_scalar("SELECT COUNT(*) FROM config_snapshots")

    return f"""
<div style="background:{BG1};border:1px solid {BOR};border-radius:10px;padding:20px 24px;margin-bottom:18px">
  {_section_header("DEPLOYMENT HISTORY", "🚀")}
  <div style="display:flex;gap:20px;margin-bottom:12px;font-size:0.83em">
    <span style="color:{FG}">Total Promotions: <b style="color:{G}">{n_promo}</b></span>
    <span style="color:{FG}">Rollbacks: <b style="color:{A}">{n_rb}</b></span>
    <span style="color:{FG}">Config Snapshots: <b style="color:{B}">{n_snaps}</b></span>
  </div>
  <table style="width:100%;border-collapse:collapse">
    <tr style="font-size:0.77em;color:{DIM};border-bottom:1px solid {BOR}">
      <th style="text-align:left;padding:3px 10px">ID</th>
      <th style="text-align:left;padding:3px 10px">Action</th>
      <th style="text-align:left;padding:3px 10px">Timestamp</th>
      <th style="text-align:left;padding:3px 10px">Triggered By</th>
      <th style="text-align:left;padding:3px 10px">Val Run</th>
      <th style="text-align:left;padding:3px 10px">Note</th>
    </tr>
    {rows_html}
  </table>
</div>"""


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 10 — SYSTEM HEALTH
# ══════════════════════════════════════════════════════════════════════════════

def _section_system_health() -> str:
    sched = _load("scheduler_state.json")
    scan  = _load("scan_status.json")

    mem_summary = {}
    try:
        from continuous_learning import LearningMemory
        mem_summary = LearningMemory().get_summary()
    except BaseException:
        pass

    last_promo = _db_query("SELECT deployed_at FROM deployment_log WHERE action='PROMOTE' ORDER BY id DESC LIMIT 1")
    last_rb    = _db_query("SELECT deployed_at FROM deployment_log WHERE action='ROLLBACK' ORDER BY id DESC LIMIT 1")

    scan_gen   = scan.get("generated_at") or scan.get("date")
    cyc_at     = mem_summary.get("last_cycle_at")
    promo_at   = last_promo[0].get("deployed_at") if last_promo else None
    rb_at      = last_rb[0].get("deployed_at") if last_rb else None

    def _age(iso):
        if not iso:
            return "—"
        try:
            dt = datetime.fromisoformat(str(iso).replace("Z", ""))
            # Make naive dt Cairo-aware for correct subtraction
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=CAIRO)
            delta = _now_cairo() - dt
            h     = int(delta.total_seconds() / 3600)
            if h < 1:  return f"{int(delta.total_seconds()/60)}m ago"
            if h < 24: return f"{h}h ago"
            return f"{int(h/24)}d ago"
        except Exception:
            return "?"

    health_rows = [
        ("Last Successful Scan",   _ts(scan_gen),   _age(scan_gen)),
        ("Last Learning Cycle",    _ts(cyc_at),     _age(cyc_at)),
        ("Last Promotion",         _ts(promo_at),   _age(promo_at)),
        ("Last Rollback",          _ts(rb_at),      _age(rb_at)),
        ("Dashboard Built",        _ts(_now_cairo().isoformat()), "just now"),
        ("Scheduler State",
         f"runs={sched.get('total_runs',0)} | errors={sched.get('consecutive_errors',0)}", ""),
    ]

    rows_html = "".join(
        f'<tr>'
        f'<td style="padding:5px 10px;color:{DIM};font-size:0.82em;width:180px">{r[0]}</td>'
        f'<td style="padding:5px 10px;font-size:0.83em;color:{FG}">{r[1]}</td>'
        f'<td style="padding:5px 10px;font-size:0.79em;color:{B}">{r[2]}</td>'
        f'</tr>'
        for r in health_rows
    )

    return f"""
<div style="background:{BG1};border:1px solid {BOR};border-radius:10px;padding:20px 24px;margin-bottom:18px">
  {_section_header("SYSTEM HEALTH", "🔧")}
  {_box("Status Timeline",
    f'<table style="width:100%;border-collapse:collapse">{rows_html}</table>')}
</div>"""


# ══════════════════════════════════════════════════════════════════════════════
# MASTER BUILDER
# ══════════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 11 — SIGNAL CLASSIFICATION & FIBONACCI ENGINE  [NEW]
# ══════════════════════════════════════════════════════════════════════════════

def _section_classification_fib() -> str:
    # ── Live signal class distribution (signals table) ───────────────────────
    class_order = ["Institutional Buy", "Very Strong Buy", "Strong Buy", "Buy", "Wait", "Skip"]
    class_color = {
        "Institutional Buy": G,
        "Very Strong Buy":   G,
        "Strong Buy":        G,
        "Buy":               B,
        "Wait":              A,
        "Skip":              R,
    }
    dist_rows = _db_query(
        "SELECT signal_type as cls, COUNT(*) as n, "
        "AVG(adj_score) as avg_score, AVG(raw_score) as avg_raw "
        "FROM signals GROUP BY signal_type ORDER BY AVG(adj_score) DESC"
    )
    dist_html = ""
    if dist_rows:
        total_sigs = sum(r["n"] for r in dist_rows)
        for r in dist_rows:
            cls   = r["cls"] or "?"
            n     = r["n"]
            pct   = n / total_sigs * 100 if total_sigs else 0
            col   = class_color.get(cls, FG)
            bar_w = max(2, int(pct))
            dist_html += (
                f'<tr>'
                f'<td style="padding:5px 12px;color:{col};font-weight:600;font-size:0.85em;width:160px">{cls}</td>'
                f'<td style="padding:5px 12px;font-weight:700;color:{FG}">{n:,}</td>'
                f'<td style="padding:5px 12px">'
                f'<div style="display:flex;align-items:center;gap:6px">'
                f'<div style="background:{BG0};width:120px;height:6px;border-radius:3px;overflow:hidden">'
                f'<div style="background:{col};width:{bar_w}%;height:100%"></div></div>'
                f'<span style="color:{DIM};font-size:0.78em">{pct:.1f}%</span>'
                f'</div></td>'
                f'<td style="padding:5px 12px;color:{DIM};font-size:0.78em">avg score {_num(r.get("avg_score") or 0, ".0f")}</td>'
                f'</tr>'
            )
    else:
        dist_html = f'<tr><td colspan=4 style="color:{DIM};padding:8px">No signals recorded yet</td></tr>'

    dist_box = _box(
        "Live Signal Class Distribution (all-time, signals table)",
        f'<table style="width:100%;border-collapse:collapse">{dist_html}</table>'
    )

    # ── Fibonacci achievement rates (fib_outcomes table) ─────────────────────
    fib_rows = _db_query("""
        SELECT signal_class,
               COUNT(*) as n,
               SUM(fib_236)*100.0/COUNT(*) as r236,
               SUM(fib_382)*100.0/COUNT(*) as r382,
               SUM(fib_500)*100.0/COUNT(*) as r500,
               SUM(fib_618)*100.0/COUNT(*) as r618,
               SUM(fib_786)*100.0/COUNT(*) as r786,
               SUM(fib_100)*100.0/COUNT(*) as r100,
               AVG(peak_return_1y) as avg_peak1y
        FROM fib_outcomes
        GROUP BY signal_class
        ORDER BY MIN(adj_score) DESC
    """)

    fib_html = ""
    if fib_rows:
        for row in fib_rows:
            cls = row["signal_class"] or "?"
            col = class_color.get(cls, FG)
            n   = row["n"]
            pk  = row.get("avg_peak1y")
            pk_str = f"{pk*100:.1f}% avg peak 1y" if pk else ""
            cells = ""
            for label, key in [("23.6%","r236"),("38.2%","r382"),("50%","r500"),
                                ("61.8%","r618"),("78.6%","r786"),("100%","r100")]:
                rate = row.get(key) or 0
                bg   = G if rate >= 50 else (A if rate >= 25 else R)
                cells += (f'<td style="padding:4px 8px;text-align:center">'
                          f'<div style="background:{bg};color:#fff;border-radius:4px;'
                          f'padding:2px 6px;font-size:0.8em;font-weight:700">{rate:.0f}%</div>'
                          f'<div style="color:{DIM};font-size:0.7em">{label}</div></td>')
            fib_html += (
                f'<tr><td style="padding:4px 10px;color:{col};font-weight:600;font-size:0.83em;width:150px">'
                f'{cls}</td>'
                f'<td style="padding:4px 10px;color:{DIM};font-size:0.78em;width:60px">n={n}</td>'
                f'{cells}'
                f'<td style="padding:4px 10px;color:{DIM};font-size:0.78em">{pk_str}</td>'
                f'</tr>'
            )
    else:
        fib_html = f'<tr><td colspan=9 style="color:{DIM};padding:8px">Run fib_outcome_tracker.py to populate</td></tr>'

    fib_header = (
        f'<tr style="border-bottom:1px solid {BOR}">'
        f'<th style="padding:4px 10px;color:{DIM};font-size:0.75em;text-align:left">Class</th>'
        f'<th style="padding:4px 10px;color:{DIM};font-size:0.75em">n</th>'
        + "".join(f'<th style="padding:4px 8px;color:{DIM};font-size:0.75em;text-align:center">{l}</th>'
                  for l in ["23.6%","38.2%","50%","61.8%","78.6%","100%"])
        + f'<th style="padding:4px 10px;color:{DIM};font-size:0.75em">Alpha</th>'
        f'</tr>'
    )
    fib_box = _box(
        "Fibonacci Achievement Rates by Class (40d short / 252d / peak_1y windows)",
        f'<table style="width:100%;border-collapse:collapse">{fib_header}{fib_html}</table>',
        color=B
    )

    # ── Active Fibonacci positions (open_positions.json) ─────────────────────
    try:
        import json as _json
        with open("open_positions.json", encoding="utf-8") as _f:
            _pos_data = _json.load(_f)
    except Exception:
        _pos_data = {}

    open_pos = {k: v for k, v in _pos_data.items() if v.get("status") == "open"}
    pos_html  = ""
    for sym, pos in sorted(open_pos.items()):
        ep  = pos.get("entry_price", 0)
        lv  = pos.get("current_level", 0)
        tgts = pos.get("fib_targets", [])
        n_tgt = len(tgts)
        pct_prog = lv / n_tgt * 100 if n_tgt else 0
        tgt = pos.get("target", 0)
        upside = (tgt - ep) / ep * 100 if ep else 0
        col = G if lv > 0 else FG
        pos_html += (
            f'<tr>'
            f'<td style="padding:4px 10px;font-weight:600;font-size:0.85em;color:{FG}">{sym}</td>'
            f'<td style="padding:4px 10px;color:{DIM};font-size:0.8em">{ep:.2f}</td>'
            f'<td style="padding:4px 10px;color:{col};font-weight:700">{lv}/{n_tgt}</td>'
            f'<td style="padding:4px 10px;color:{B};font-size:0.8em">'
            f'{tgt:.2f} (+{upside:.1f}%)</td>'
            f'<td style="padding:4px 10px">'
            f'<div style="background:{BG0};width:80px;height:5px;border-radius:3px;overflow:hidden">'
            f'<div style="background:{G};width:{pct_prog:.0f}%;height:100%"></div></div>'
            f'</td>'
            f'</tr>'
        )

    if not pos_html:
        pos_html = f'<tr><td colspan=5 style="color:{DIM};padding:8px;font-size:0.83em">No open positions</td></tr>'

    pos_header = (
        f'<tr style="border-bottom:1px solid {BOR}">'
        + "".join(f'<th style="padding:4px 10px;color:{DIM};font-size:0.75em;text-align:left">{h}</th>'
                  for h in ["Symbol","Entry","Fib Level","Next Target","Progress"])
        + f'</tr>'
    )
    pos_box = _box(
        f"Active Fibonacci Positions ({len(open_pos)} open)",
        f'<table style="width:100%;border-collapse:collapse">{pos_header}{pos_html}</table>'
    )

    return f"""
<div style="background:{BG1};border:1px solid {BOR};border-radius:10px;padding:20px 24px;margin-bottom:18px">
  {_section_header("SIGNAL CLASSIFICATION & FIBONACCI ENGINE", "🎯")}
  {dist_box}
  {fib_box}
  {pos_box}
</div>"""


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 12 — PATTERN INTELLIGENCE 2.0
# ══════════════════════════════════════════════════════════════════════════════

def _section_pattern_intelligence() -> str:
    html = _section_header("Pattern Intelligence 2.0", "🔬")

    # ── Summary row ──────────────────────────────────────────────────────────
    n_total   = _db_scalar("SELECT COUNT(*) FROM pattern_knowledge_base WHERE n_total >= 20", default=0)
    n_impr    = _db_scalar("SELECT COUNT(*) FROM pattern_knowledge_base WHERE status='improving' AND n_total >= 20", default=0)
    n_stable  = _db_scalar("SELECT COUNT(*) FROM pattern_knowledge_base WHERE status='stable' AND n_total >= 20", default=0)
    n_deter   = _db_scalar("SELECT COUNT(*) FROM pattern_knowledge_base WHERE status='deteriorating' AND n_total >= 20", default=0)
    last_run  = _db_scalar(
        "SELECT run_at FROM pattern_kb_log ORDER BY id DESC LIMIT 1", default="")
    n_telem   = _db_scalar("SELECT COUNT(*) FROM pattern_telemetry", default=0)

    summary_html = (
        f'<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px">'
        f'<div style="background:{BG2};border:1px solid {BOR};border-radius:6px;padding:10px 16px;min-width:100px;text-align:center">'
        f'<div style="color:{B};font-size:1.4em;font-weight:700">{n_total}</div>'
        f'<div style="color:{DIM};font-size:0.75em">Patterns</div></div>'
        f'<div style="background:{BG2};border:1px solid {BOR};border-radius:6px;padding:10px 16px;min-width:100px;text-align:center">'
        f'<div style="color:{G};font-size:1.4em;font-weight:700">{n_impr}</div>'
        f'<div style="color:{DIM};font-size:0.75em">Improving</div></div>'
        f'<div style="background:{BG2};border:1px solid {BOR};border-radius:6px;padding:10px 16px;min-width:100px;text-align:center">'
        f'<div style="color:{A};font-size:1.4em;font-weight:700">{n_stable}</div>'
        f'<div style="color:{DIM};font-size:0.75em">Stable</div></div>'
        f'<div style="background:{BG2};border:1px solid {BOR};border-radius:6px;padding:10px 16px;min-width:100px;text-align:center">'
        f'<div style="color:{R};font-size:1.4em;font-weight:700">{n_deter}</div>'
        f'<div style="color:{DIM};font-size:0.75em">Deteriorating</div></div>'
        f'<div style="background:{BG2};border:1px solid {BOR};border-radius:6px;padding:10px 16px;min-width:130px;text-align:center">'
        f'<div style="color:{FG};font-size:1.1em;font-weight:700">{n_telem}</div>'
        f'<div style="color:{DIM};font-size:0.75em">Telemetry Logged</div></div>'
        f'<div style="background:{BG2};border:1px solid {BOR};border-radius:6px;padding:10px 16px;min-width:160px;text-align:center">'
        f'<div style="color:{DIM};font-size:0.78em">{_ts(last_run) if last_run else "—"}</div>'
        f'<div style="color:{DIM};font-size:0.75em">Last Research Cycle</div></div>'
        f'</div>'
    )
    html += summary_html

    # ── Top 10 Patterns by MFE40 ──────────────────────────────────────────────
    top_rows = _db_query("""
        SELECT pattern_def, n_total, mfe40_mean, expectancy, sharpe,
               mae40_mean, peak_return_avg, confidence, status
        FROM pattern_knowledge_base
        WHERE n_total >= 20 AND mfe40_mean IS NOT NULL
        ORDER BY mfe40_mean DESC
        LIMIT 10
    """)

    if top_rows:
        tbl = (
            f'<div style="color:{B};font-size:0.8em;font-weight:600;'
            f'text-transform:uppercase;letter-spacing:0.05em;margin-bottom:6px">'
            f'Top 10 Patterns by MFE40</div>'
            f'<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;'
            f'font-size:0.82em">'
            f'<tr style="color:{DIM};text-align:left;border-bottom:1px solid {BOR}">'
            f'<th style="padding:5px 8px">#</th>'
            f'<th style="padding:5px 8px">Pattern Definition</th>'
            f'<th style="padding:5px 8px;text-align:right">N</th>'
            f'<th style="padding:5px 8px;text-align:right">MFE40</th>'
            f'<th style="padding:5px 8px;text-align:right">Expectancy</th>'
            f'<th style="padding:5px 8px;text-align:right">Sharpe</th>'
            f'<th style="padding:5px 8px;text-align:right">MAE40</th>'
            f'<th style="padding:5px 8px;text-align:right">Peak</th>'
            f'<th style="padding:5px 8px">Confidence</th>'
            f'<th style="padding:5px 8px">Status</th></tr>'
        )
        for i, r in enumerate(top_rows, 1):
            try:
                flags = json.loads(r["pattern_def"])
                pat_str = " + ".join(
                    f'<span style="color:{G}">✓</span>{k.replace("_"," ")}' if v
                    else f'<span style="color:{R}">✗</span>{k.replace("_"," ")}'
                    for k, v in flags.items()
                )
            except Exception:
                pat_str = str(r["pattern_def"])[:60]

            conf = r["confidence"] or "—"
            conf_col = G if "Very High" in conf else (G if "High" in conf else (A if "Moderate" in conf else DIM))
            status = r["status"] or "active"
            status_col = G if status == "improving" else (R if status == "deteriorating" else DIM)
            mfe40 = r["mfe40_mean"]
            mfe40_col = G if (mfe40 or 0) >= 0.20 else (A if (mfe40 or 0) >= 0.10 else R)

            tbl += (
                f'<tr style="border-bottom:1px solid {BOR}">'
                f'<td style="padding:5px 8px;color:{DIM}">{i}</td>'
                f'<td style="padding:5px 8px;font-size:0.88em">{pat_str}</td>'
                f'<td style="padding:5px 8px;text-align:right;color:{FG}">{r["n_total"]}</td>'
                f'<td style="padding:5px 8px;text-align:right;color:{mfe40_col};font-weight:600">'
                f'{_num(mfe40, ".4f")}</td>'
                f'<td style="padding:5px 8px;text-align:right">{_num(r["expectancy"], ".4f")}</td>'
                f'<td style="padding:5px 8px;text-align:right">{_num(r["sharpe"], ".3f")}</td>'
                f'<td style="padding:5px 8px;text-align:right;color:{R}">{_num(r["mae40_mean"], ".4f")}</td>'
                f'<td style="padding:5px 8px;text-align:right">{_num(r["peak_return_avg"], ".3f")}</td>'
                f'<td style="padding:5px 8px;color:{conf_col};font-size:0.85em">{conf}</td>'
                f'<td style="padding:5px 8px;color:{status_col};font-size:0.85em">{status}</td>'
                f'</tr>'
            )
        tbl += '</table></div>'
        html += _box("Top Patterns — Live from pattern_knowledge_base", tbl, color=B)
    else:
        html += _box("Top Patterns", f'<span style="color:{DIM}">No patterns yet — run pattern_kb.rebuild()</span>')

    # ── Improving Patterns ────────────────────────────────────────────────────
    impr_rows = _db_query("""
        SELECT pattern_def, n_total, mfe40_mean, expectancy, yearly_stats, last_updated
        FROM pattern_knowledge_base
        WHERE status = 'improving' AND n_total >= 20
        ORDER BY mfe40_mean DESC
        LIMIT 5
    """)

    if impr_rows:
        impr_html = '<table style="width:100%;border-collapse:collapse;font-size:0.82em">'
        impr_html += (
            f'<tr style="color:{DIM};border-bottom:1px solid {BOR}">'
            f'<th style="padding:4px 8px;text-align:left">Pattern</th>'
            f'<th style="padding:4px 8px;text-align:right">N</th>'
            f'<th style="padding:4px 8px;text-align:right">MFE40</th>'
            f'<th style="padding:4px 8px;text-align:right">Trend</th>'
            f'<th style="padding:4px 8px;text-align:right">Last Updated</th></tr>'
        )
        for r in impr_rows:
            try:
                flags = json.loads(r["pattern_def"])
                pat_str = " + ".join(f'✓{k.replace("_"," ")}' for k, v in flags.items() if v)
            except Exception:
                pat_str = str(r["pattern_def"])[:40]
            # Compute YoY trend from yearly_stats
            trend_str = "↑"
            try:
                ys = json.loads(r["yearly_stats"]) if r["yearly_stats"] else {}
                yrs = sorted(ys.keys())
                if len(yrs) >= 2:
                    delta = (ys[yrs[-1]].get("mfe40") or 0) - (ys[yrs[0]].get("mfe40") or 0)
                    trend_str = f'<span style="color:{G}">↑ +{delta*100:.1f}pp</span>'
            except Exception:
                pass
            impr_html += (
                f'<tr style="border-bottom:1px solid {BOR}">'
                f'<td style="padding:4px 8px;color:{G}">{pat_str}</td>'
                f'<td style="padding:4px 8px;text-align:right">{r["n_total"]}</td>'
                f'<td style="padding:4px 8px;text-align:right;font-weight:600">{_num(r["mfe40_mean"],".4f")}</td>'
                f'<td style="padding:4px 8px;text-align:right">{trend_str}</td>'
                f'<td style="padding:4px 8px;text-align:right;color:{DIM}">{_ts(r["last_updated"],"%Y-%m-%d")}</td></tr>'
            )
        impr_html += '</table>'
        html += _box("Improving Patterns", impr_html, color=G)

    # ── Deteriorating Patterns ────────────────────────────────────────────────
    deter_rows = _db_query("""
        SELECT pattern_def, n_total, mfe40_mean, expectancy, yearly_stats, last_updated
        FROM pattern_knowledge_base
        WHERE status = 'deteriorating' AND n_total >= 20
        ORDER BY mfe40_mean ASC
        LIMIT 5
    """)

    if deter_rows:
        deter_html = '<table style="width:100%;border-collapse:collapse;font-size:0.82em">'
        deter_html += (
            f'<tr style="color:{DIM};border-bottom:1px solid {BOR}">'
            f'<th style="padding:4px 8px;text-align:left">Pattern</th>'
            f'<th style="padding:4px 8px;text-align:right">N</th>'
            f'<th style="padding:4px 8px;text-align:right">MFE40</th>'
            f'<th style="padding:4px 8px;text-align:right">Trend</th></tr>'
        )
        for r in deter_rows:
            try:
                flags = json.loads(r["pattern_def"])
                pat_str = " + ".join(f'✗{k.replace("_"," ")}' for k, v in flags.items() if v)
            except Exception:
                pat_str = str(r["pattern_def"])[:40]
            trend_str = "↓"
            try:
                ys = json.loads(r["yearly_stats"]) if r["yearly_stats"] else {}
                yrs = sorted(ys.keys())
                if len(yrs) >= 2:
                    delta = (ys[yrs[-1]].get("mfe40") or 0) - (ys[yrs[0]].get("mfe40") or 0)
                    trend_str = f'<span style="color:{R}">↓ {delta*100:.1f}pp</span>'
            except Exception:
                pass
            deter_html += (
                f'<tr style="border-bottom:1px solid {BOR}">'
                f'<td style="padding:4px 8px;color:{R}">{pat_str}</td>'
                f'<td style="padding:4px 8px;text-align:right">{r["n_total"]}</td>'
                f'<td style="padding:4px 8px;text-align:right">{_num(r["mfe40_mean"],".4f")}</td>'
                f'<td style="padding:4px 8px;text-align:right">{trend_str}</td></tr>'
            )
        deter_html += '</table>'
        html += _box("Deteriorating Patterns", deter_html, color=R)

    # ── Dominant Families ─────────────────────────────────────────────────────
    family_rows = _db_query("""
        SELECT pattern_def, COUNT(*) as family_count,
               AVG(mfe40_mean) as avg_mfe40,
               MAX(n_total) as max_n
        FROM pattern_knowledge_base
        WHERE n_total >= 20 AND mfe40_mean IS NOT NULL
        GROUP BY pattern_def
        HAVING family_count >= 1
        ORDER BY avg_mfe40 DESC
        LIMIT 5
    """)

    # Better: cluster by dominant flag (most common flag in top patterns)
    all_top = _db_query("""
        SELECT pattern_def, n_total, mfe40_mean
        FROM pattern_knowledge_base
        WHERE n_total >= 20 AND mfe40_mean IS NOT NULL
        ORDER BY mfe40_mean DESC
        LIMIT 50
    """)

    flag_mfe = {}
    for r in all_top:
        try:
            flags = json.loads(r["pattern_def"])
            for k, v in flags.items():
                if v == 1:
                    if k not in flag_mfe:
                        flag_mfe[k] = []
                    flag_mfe[k].append(r["mfe40_mean"] or 0)
        except Exception:
            pass

    if flag_mfe:
        import statistics as _st
        family_stats = {
            k: {"count": len(v), "avg_mfe40": _st.mean(v)}
            for k, v in flag_mfe.items() if len(v) >= 3
        }
        family_sorted = sorted(family_stats.items(), key=lambda x: -x[1]["avg_mfe40"])[:8]

        fam_html = '<div style="display:flex;gap:8px;flex-wrap:wrap">'
        for flag_name, fs in family_sorted:
            lbl = flag_name.replace("_", " ").title()
            mfe = fs["avg_mfe40"]
            col = G if mfe >= 0.20 else (A if mfe >= 0.12 else DIM)
            fam_html += (
                f'<div style="background:{BG0};border:1px solid {BOR};border-radius:6px;'
                f'padding:8px 12px;min-width:120px;text-align:center">'
                f'<div style="color:{col};font-weight:700;font-size:0.9em">✓ {lbl}</div>'
                f'<div style="color:{FG};font-size:0.85em">MFE40 {mfe*100:.1f}%</div>'
                f'<div style="color:{DIM};font-size:0.75em">{fs["count"]} patterns</div></div>'
            )
        fam_html += '</div>'
        html += _box("Dominant Pattern Families (Top 50 by MFE40)", fam_html, color=B)

    # ── Feature Validation ────────────────────────────────────────────────────
    feat_rows = _db_query("""
        SELECT feature, direction_design, direction_data, direction_correct,
               spearman_rho, spearman_p, n_signals
        FROM pattern_feature_stats
        ORDER BY ABS(spearman_rho) DESC
    """)

    if feat_rows:
        feat_html = '<table style="width:100%;border-collapse:collapse;font-size:0.82em">'
        feat_html += (
            f'<tr style="color:{DIM};border-bottom:1px solid {BOR}">'
            f'<th style="padding:4px 8px;text-align:left">Feature</th>'
            f'<th style="padding:4px 8px">Design Dir</th>'
            f'<th style="padding:4px 8px">Data Dir</th>'
            f'<th style="padding:4px 8px">Match</th>'
            f'<th style="padding:4px 8px;text-align:right">Spearman ρ</th>'
            f'<th style="padding:4px 8px;text-align:right">p-value</th>'
            f'<th style="padding:4px 8px;text-align:right">N</th></tr>'
        )
        for fr in feat_rows:
            correct = fr["direction_correct"]
            rho = fr["spearman_rho"] or 0
            p_val = fr["spearman_p"]
            sig = (p_val is not None and p_val < 0.05)
            rho_col = G if (sig and abs(rho) >= 0.05) else DIM
            feat_html += (
                f'<tr style="border-bottom:1px solid {BOR}">'
                f'<td style="padding:4px 8px;color:{FG}">{fr["feature"]}</td>'
                f'<td style="padding:4px 8px;color:{DIM}">{fr["direction_design"] or "—"}</td>'
                f'<td style="padding:4px 8px;color:{DIM}">{fr["direction_data"] or "—"}</td>'
                f'<td style="padding:4px 8px;text-align:center">'
                + ('<td><span style="color:' + G + '">&#10003;</span></td>' if correct
                   else '<td><span style="color:' + R + '">&#10007;</span></td>')
                + '</td>'
                f'<td style="padding:4px 8px;text-align:right;color:{rho_col}">{_num(rho, ".4f")}</td>'
                f'<td style="padding:4px 8px;text-align:right;color:{G if sig else DIM}">'
                f'{_num(p_val, ".4f") if p_val is not None else "—"}</td>'
                f'<td style="padding:4px 8px;text-align:right">{fr["n_signals"] or "—"}</td></tr>'
            )
        feat_html += '</table>'
        html += _box("Feature Validation vs MFE40 (Spearman)", feat_html, color=A)

    return f'<div style="background:{BG1};border:1px solid {BOR};border-radius:8px;padding:20px;margin-bottom:20px">{html}</div>'


# ══════════════════════════════════════════════════════════════════════════════
# EXECUTIVE SUMMARY — Single compact header panel (no duplicates)
# Shows: biggest win, biggest deterioration, latest promoted/rejected, top/bottom alpha source
# ══════════════════════════════════════════════════════════════════════════════

def _section_top_ranked() -> str:
    """RANKED OPPORTUNITIES panel — reads scan_results.json (falls back to signal_history)."""
    scan  = _load_scan()
    ranks = _load("rank_history.json")

    # Compute blended score for all valid stocks from today's scan
    today_str = datetime.now(CAIRO).strftime("%Y-%m-%d")
    # Match email's SUMMARY_SIGNALS exactly
    SUMMARY_SIGNALS = {"buy", "strong buy", "very strong buy", "institutional buy", "wait"}
    ranked = []
    for sym, r in scan.items():
        if not isinstance(r, dict) or not r.get("ok"):
            continue
        sig_lower = (r.get("signal", "") or "").lower()
        if sig_lower not in SUMMARY_SIGNALS:
            continue
        fexp    = float(r.get("factor_exp_score", 0) or 0)
        score   = float(r.get("score", 0) or 0)
        blended = 0.60 * fexp + 0.40 * score
        ranked.append({
            "sym": sym,
            "name": sym,
            "signal": r.get("signal", "—"),
            "fexp": fexp,
            "score": score,
            "blended": blended,
            "price": r.get("price", 0),
        })
    ranked.sort(key=lambda x: x["blended"], reverse=True)

    if not ranked:
        return f"""<div class="section" style="border-left:4px solid {B}">
  {_section_header("RANKED OPPORTUNITIES", "🏆")}
  <div style="color:{DIM};font-size:0.85em;padding:12px 0">No BUY signals in current scan.</div>
</div>"""

    # Resolve rank changes from history
    prev_ranks: dict = {}
    past_dates = sorted([d for d in ranks if d < today_str], reverse=True)
    if past_dates:
        prev_snap = ranks.get(past_dates[0], {})
        prev_ranks = {sym: v.get("rank") for sym, v in prev_snap.items()}

    def _delta(sym, cur_rank):
        prev = prev_ranks.get(sym)
        if prev is None or prev == cur_rank:
            return ""
        d = prev - cur_rank
        if d > 0:
            return f'<span style="color:{G};font-weight:700;font-size:0.85em">▲{d}</span>'
        return f'<span style="color:{R};font-weight:700;font-size:0.85em">▼{abs(d)}</span>'

    def _sig_color(sig):
        sl = sig.lower()
        if "institutional" in sl: return "#c084fc"
        if "very strong"   in sl: return G
        if "strong"        in sl: return G
        if "buy"           in sl: return "#86efac"
        if "wait"          in sl: return A
        return DIM

    rows = ""
    for cur_rank, item in enumerate(ranked[:10], 1):
        sym   = item["sym"]
        tier  = "A" if cur_rank <= 5 else "B"
        tier_col = B if tier == "A" else DIM
        sig_col  = _sig_color(item["signal"])
        delta_h  = _delta(sym, cur_rank)
        rows += f"""
<tr style="border-bottom:1px solid {BOR}">
  <td style="padding:9px 12px;text-align:center;width:50px">
    <span style="color:{tier_col};font-size:1.1em;font-weight:800">#{cur_rank}</span><br>
    <span style="color:{tier_col};font-size:0.68em;font-weight:700;letter-spacing:0.5px">{tier}-TIER</span>
  </td>
  <td style="padding:9px 12px">
    <span style="color:{FG};font-weight:700;font-size:0.95em">{sym}</span><br>
    <span style="color:{DIM};font-size:0.75em">{item["price"]} EGP</span>
  </td>
  <td style="padding:9px 12px">
    <span style="color:{sig_col};font-size:0.82em;font-weight:600">{item["signal"]}</span>
  </td>
  <td style="padding:9px 12px;text-align:right">
    <span style="color:#fff;font-size:1.05em;font-weight:800">{item["blended"]:.1f}</span><br>
    <span style="color:{DIM};font-size:0.7em">rank score</span>
  </td>
  <td style="padding:9px 12px;text-align:right">
    <span style="color:{B};font-size:0.9em;font-weight:600">{item["fexp"]:.1f}</span><br>
    <span style="color:{DIM};font-size:0.7em">expectancy</span>
  </td>
  <td style="padding:9px 12px;text-align:right">
    <span style="color:{FG};font-size:0.9em">{int(item["score"])}</span><br>
    <span style="color:{DIM};font-size:0.7em">SMC</span>
  </td>
  <td style="padding:9px 12px;text-align:center;width:42px">{delta_h}</td>
</tr>"""
        if cur_rank == 5 and len(ranked) > 5:
            rows += f"""<tr><td colspan="7" style="padding:5px 12px;background:{BG2};font-size:0.75em;color:{DIM};font-weight:700;letter-spacing:0.5px;text-transform:uppercase">Monitored Opportunities (#6–#10)</td></tr>"""

    # Largest movers section
    movers_html = ""
    if prev_ranks:
        movers = []
        for cur_rank, item in enumerate(ranked, 1):
            prev = prev_ranks.get(item["sym"])
            if prev is None: continue
            delta = prev - cur_rank
            movers.append((item["sym"], item["signal"], prev, cur_rank, delta))
        movers.sort(key=lambda x: abs(x[4]), reverse=True)
        if movers:
            promo_html = "  ".join(
                f'<span style="color:{G};font-size:0.82em;font-weight:600">{s} #{pr}→#{cr} <b>▲{d}</b></span>'
                for s, sig, pr, cr, d in movers[:3] if d > 0
            )
            demo_html = "  ".join(
                f'<span style="color:{R};font-size:0.82em;font-weight:600">{s} #{pr}→#{cr} <b>▼{abs(d)}</b></span>'
                for s, sig, pr, cr, d in movers[:3] if d < 0
            )
            movers_html = f"""
<div style="display:flex;gap:20px;flex-wrap:wrap;padding:10px 14px;background:{BG2};border-top:1px solid {BOR};font-size:0.82em">
  <div><span style="color:{DIM};font-size:0.78em;text-transform:uppercase;letter-spacing:0.5px">▲ Largest Promotions &nbsp;</span>{promo_html or '<span style="color:'+DIM+'">—</span>'}</div>
  <div><span style="color:{DIM};font-size:0.78em;text-transform:uppercase;letter-spacing:0.5px">▼ Largest Demotions &nbsp;</span>{demo_html or '<span style="color:'+DIM+'">—</span>'}</div>
</div>"""

    return f"""<div class="section" style="border-left:4px solid {B}">
  {_section_header("RANKED OPPORTUNITIES", "🏆")}
  <div style="font-size:0.78em;color:{DIM};margin-bottom:10px">
    Formula: <code style="color:{B}">0.60 × factor_exp_score + 0.40 × SMC score</code> &nbsp;·&nbsp;
    Sorted by production ranking key &nbsp;·&nbsp; {today_str}
  </div>
  <div style="overflow-x:auto">
  <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;min-width:500px">
    <thead>
      <tr style="background:{BG2};border-bottom:2px solid {BOR}">
        <th style="padding:7px 12px;font-size:0.75em;color:{DIM};text-align:center;text-transform:uppercase;letter-spacing:0.5px">Rank</th>
        <th style="padding:7px 12px;font-size:0.75em;color:{DIM};text-transform:uppercase;letter-spacing:0.5px">Stock</th>
        <th style="padding:7px 12px;font-size:0.75em;color:{DIM};text-transform:uppercase;letter-spacing:0.5px">Signal</th>
        <th style="padding:7px 12px;font-size:0.75em;color:{DIM};text-align:right;text-transform:uppercase;letter-spacing:0.5px">Rank Score</th>
        <th style="padding:7px 12px;font-size:0.75em;color:{DIM};text-align:right;text-transform:uppercase;letter-spacing:0.5px">Expectancy</th>
        <th style="padding:7px 12px;font-size:0.75em;color:{DIM};text-align:right;text-transform:uppercase;letter-spacing:0.5px">SMC</th>
        <th style="padding:7px 12px;font-size:0.75em;color:{DIM};text-align:center;text-transform:uppercase;letter-spacing:0.5px">Δ Rank</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
  </div>
  {movers_html}
</div>"""


def _section_top_watchlist() -> str:
    """WAIT — Watchlist panel: signals in discount zone but below entry gate, sorted by blended score."""
    scan = _load_scan()

    today_str = datetime.now(CAIRO).strftime("%Y-%m-%d")
    watchlist = []
    for sym, r in scan.items():
        if not isinstance(r, dict) or not r.get("ok"):
            continue
        sig_lower = (r.get("signal", "") or "").lower()
        if sig_lower != "wait":
            continue
        fexp    = float(r.get("factor_exp_score", 0) or 0)
        score   = float(r.get("score", 0) or 0)
        blended = 0.60 * fexp + 0.40 * score
        is_early = bool(r.get("early_buy_research", False))
        watchlist.append({
            "sym": sym,
            "signal": r.get("signal", "—"),
            "fexp": fexp,
            "score": score,
            "blended": blended,
            "price": r.get("price", 0),
            "early": is_early,
        })
    watchlist.sort(key=lambda x: x["blended"], reverse=True)

    if not watchlist:
        return f"""<div class="section" style="border-left:4px solid {A}">
  {_section_header("WAIT — WATCHLIST", "👀")}
  <div style="color:{DIM};font-size:0.85em;padding:12px 0">No WAIT signals in current scan.</div>
</div>"""

    rows = ""
    for i, item in enumerate(watchlist[:10], 1):
        early_tag = (
            f' &nbsp;<span style="background:#713f12;color:#fef08a;font-size:0.68em;font-weight:700;'
            f'padding:1px 5px;border-radius:3px;letter-spacing:0.4px">EARLY BUY RESEARCH</span>'
            if item["early"] else ""
        )
        rows += f"""
<tr style="border-bottom:1px solid {BOR}">
  <td style="padding:9px 12px;text-align:center;width:40px">
    <span style="color:{A};font-size:1.0em;font-weight:700">#{i}</span>
  </td>
  <td style="padding:9px 12px">
    <span style="color:{FG};font-weight:700;font-size:0.95em">{item["sym"]}</span>{early_tag}<br>
    <span style="color:{DIM};font-size:0.75em">{item["price"]} EGP</span>
  </td>
  <td style="padding:9px 12px">
    <span style="color:{A};font-size:0.82em;font-weight:600">Wait</span>
  </td>
  <td style="padding:9px 12px;text-align:right">
    <span style="color:#fff;font-size:1.0em;font-weight:700">{item["blended"]:.1f}</span><br>
    <span style="color:{DIM};font-size:0.7em">rank score</span>
  </td>
  <td style="padding:9px 12px;text-align:right">
    <span style="color:{B};font-size:0.9em;font-weight:600">{item["fexp"]:.1f}</span><br>
    <span style="color:{DIM};font-size:0.7em">expectancy</span>
  </td>
  <td style="padding:9px 12px;text-align:right">
    <span style="color:{FG};font-size:0.9em">{int(item["score"])}</span><br>
    <span style="color:{DIM};font-size:0.7em">SMC</span>
  </td>
</tr>"""

    return f"""<div class="section" style="border-left:4px solid {A}" id="watchlist">
  {_section_header("WAIT — WATCHLIST", "👀")}
  <div style="font-size:0.78em;color:{DIM};margin-bottom:10px">
    In discount zone · price gate or entry score not yet met · monitor for entry &nbsp;·&nbsp; {today_str}
  </div>
  <div style="overflow-x:auto">
  <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;min-width:460px">
    <thead>
      <tr style="background:{BG2};border-bottom:2px solid {BOR}">
        <th style="padding:7px 12px;font-size:0.75em;color:{DIM};text-align:center;text-transform:uppercase;letter-spacing:0.5px">#</th>
        <th style="padding:7px 12px;font-size:0.75em;color:{DIM};text-transform:uppercase;letter-spacing:0.5px">Stock</th>
        <th style="padding:7px 12px;font-size:0.75em;color:{DIM};text-transform:uppercase;letter-spacing:0.5px">Status</th>
        <th style="padding:7px 12px;font-size:0.75em;color:{DIM};text-align:right;text-transform:uppercase;letter-spacing:0.5px">Rank Score</th>
        <th style="padding:7px 12px;font-size:0.75em;color:{DIM};text-align:right;text-transform:uppercase;letter-spacing:0.5px">Expectancy</th>
        <th style="padding:7px 12px;font-size:0.75em;color:{DIM};text-align:right;text-transform:uppercase;letter-spacing:0.5px">SMC</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
  </div>
</div>"""


def _section_executive_summary() -> str:
    kb_data = _load("knowledge_base.json")
    ff = _ff_list(kb_data)

    # Latest promoted/rejected
    last_promo = _db_query("SELECT deployed_at, note FROM deployment_log WHERE action='PROMOTE' ORDER BY id DESC LIMIT 1")
    last_rb    = _db_query("SELECT deployed_at, note FROM deployment_log WHERE action='ROLLBACK' ORDER BY id DESC LIMIT 1")
    last_val   = _db_query("SELECT verdict, oos_wr, run_at FROM validation_runs ORDER BY id DESC LIMIT 1")
    lv = last_val[0] if last_val else {}

    # Best/worst alpha sources from KB
    positives = sorted([f for f in ff if isinstance(f, dict) and f.get("verdict") == "POSITIVE"],
                       key=lambda x: (x.get("win_rate") or 0), reverse=True)
    negatives = sorted([f for f in ff if isinstance(f, dict) and f.get("verdict") == "NEGATIVE"],
                       key=lambda x: (x.get("win_rate") or 1))

    best_alpha  = positives[0] if positives else {}
    worst_alpha = negatives[0] if negatives else {}

    # Latest discovery (newest finding regardless of verdict)
    all_sorted = sorted([f for f in ff if isinstance(f, dict)],
                        key=lambda x: str(x.get("recorded_at", "")), reverse=True)
    latest_disc = all_sorted[0] if all_sorted else {}

    oos_wr  = lv.get("oos_wr", 0) or 0
    alpha_ok = lv.get("verdict") == "APPROVED"

    def _exec_cell(label, value, sub="", col=FG):
        return (f'<div style="flex:1;min-width:160px;background:{BG2};border:1px solid {BOR};'
                f'border-radius:6px;padding:12px 14px">'
                f'<div style="font-size:0.72em;color:{DIM};text-transform:uppercase;'
                f'letter-spacing:0.05em;margin-bottom:4px">{label}</div>'
                f'<div style="font-size:1.0em;font-weight:700;color:{col}">{value}</div>'
                f'<div style="font-size:0.74em;color:{DIM};margin-top:3px">{sub}</div>'
                f'</div>')

    cells = (
        _exec_cell("Alpha Status",
                   _badge(alpha_ok, "VERIFIED", "UNVERIFIED"),
                   f"OOS WR {_pct(oos_wr)} · {_ts(lv.get('run_at'))}",
                   G if alpha_ok else R)
        + _exec_cell("Strongest Alpha",
                     best_alpha.get("factor", "—"),
                     f"WR {_pct(best_alpha.get('win_rate'))} · n={best_alpha.get('sample_n','?')}",
                     G)
        + _exec_cell("Weakest Alpha",
                     worst_alpha.get("factor", "—"),
                     f"WR {_pct(worst_alpha.get('win_rate'))} · n={worst_alpha.get('sample_n','?')}",
                     R)
        + _exec_cell("Latest Discovery",
                     latest_disc.get("factor", "—"),
                     f"{latest_disc.get('verdict','?')} · {str(latest_disc.get('recorded_at',''))[:10]}",
                     G if latest_disc.get("verdict") == "POSITIVE" else R if latest_disc.get("verdict") == "NEGATIVE" else A)
        + _exec_cell("Last Promoted",
                     _ts(last_promo[0].get("deployed_at")) if last_promo else "—",
                     (last_promo[0].get("note") or "")[:40] if last_promo else "no promotions yet",
                     G)
        + _exec_cell("Last Rollback",
                     _ts(last_rb[0].get("deployed_at")) if last_rb else "—",
                     (last_rb[0].get("note") or "")[:40] if last_rb else "no rollbacks",
                     R if last_rb else DIM)
    )

    return f"""
<div style="background:{BG1};border:2px solid {B};border-radius:10px;padding:16px 20px;margin-bottom:18px">
  {_section_header("EXECUTIVE SUMMARY", "🎯")}
  <div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:8px">{cells}</div>
</div>"""


def _section_portfolio_header(snap) -> str:
    """HEADER — Portfolio Health badge, date, capacity status."""
    h_col = G if "★★★★" in snap.health_stars else (A if "★★★" in snap.health_stars else R)
    cap_ok = snap.capacity_used_pct <= 100
    cap_col = R if not cap_ok else G
    sector_ok = snap.sector_cap_ok
    corr_col = R if snap.max_correlation > 0.7 else (A if snap.max_correlation > 0.5 else G)

    flags = (
        f'<span style="background:{G if sector_ok else R};color:#fff;padding:2px 9px;border-radius:4px;font-size:0.8em;font-weight:600;margin-right:6px">'
        f'{"✓ Sector OK" if sector_ok else "⚠ Sector Concentrated"}</span>'
        f'<span style="background:{cap_col};color:#fff;padding:2px 9px;border-radius:4px;font-size:0.8em;font-weight:600;margin-right:6px">'
        f'Capacity {snap.capacity_used_pct:.0f}%</span>'
        f'<span style="background:{corr_col};color:#fff;padding:2px 9px;border-radius:4px;font-size:0.8em;font-weight:600">'
        f'Corr {snap.max_correlation:.2f}</span>'
    )

    return f"""
<div style="background:linear-gradient(135deg,{BG1},{BG2});border:2px solid {B};border-radius:10px;padding:20px 24px;margin-bottom:18px">
  <div style="display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:12px">
    <div>
      <div style="font-size:1.6em;font-weight:700;color:{h_col}">{snap.health_stars} {snap.health_label}</div>
      <div style="color:{DIM};font-size:0.85em;margin-top:4px">{snap.health_narrative}</div>
    </div>
    <div style="text-align:right">
      <div style="color:{FG};font-size:0.9em;font-weight:600">{snap.held_count} positions held</div>
      <div style="margin-top:6px">{flags}</div>
    </div>
  </div>
</div>"""


def _section_today(snap) -> str:
    """TODAY — High Conviction Opportunities, Future Priorities, Watch List."""
    # High Conviction
    hcb_rows = ""
    for r in snap.high_conviction_buys:
        conf_col = G if r.get("confidence") == "HIGH" else (A if r.get("confidence") == "MEDIUM" else DIM)
        stars = r.get("signal_quality_stars") or "—"
        ret = r.get("current_return_pct")
        ret_str = f'+{ret:.1f}%' if ret and ret >= 0 else (f'{ret:.1f}%' if ret is not None else "—")
        hcb_rows += (
            f'<tr style="border-bottom:1px solid {BOR}">'
            f'<td style="padding:7px 12px;color:{FG};font-weight:600">{r["ticker"]}</td>'
            f'<td style="padding:7px 12px;color:{DIM};font-size:0.83em">{r.get("sector","")}</td>'
            f'<td style="padding:7px 12px;color:{conf_col};font-size:0.83em">{r.get("decision","")}</td>'
            f'<td style="padding:7px 12px;font-size:0.83em;color:{FG}">{stars}</td>'
            f'<td style="padding:7px 12px;font-size:0.8em;color:{DIM}">{r.get("reason","")[:80]}</td>'
            f'</tr>'
        )
    if not hcb_rows:
        hcb_rows = f'<tr><td colspan=5 style="padding:10px 12px;color:{DIM};font-size:0.85em">No high conviction buys today.</td></tr>'

    hcb_block = (
        f'<table style="width:100%;border-collapse:collapse;font-size:0.88em">'
        f'<tr style="border-bottom:1px solid {BOR}">'
        f'<th style="padding:5px 12px;color:{DIM};text-align:left">Ticker</th>'
        f'<th style="padding:5px 12px;color:{DIM};text-align:left">Sector</th>'
        f'<th style="padding:5px 12px;color:{DIM};text-align:left">Decision</th>'
        f'<th style="padding:5px 12px;color:{DIM};text-align:left">Quality</th>'
        f'<th style="padding:5px 12px;color:{DIM};text-align:left">Reason</th>'
        f'</tr>{hcb_rows}</table>'
    )

    # Future Priorities
    fp_items = "".join(
        f'<span style="background:{BG0};border:1px solid {B};color:{B};padding:4px 12px;'
        f'border-radius:4px;font-size:0.85em;font-weight:600;margin-right:8px;margin-bottom:6px;display:inline-block">'
        f'⏳ {t}</span>'
        for t in snap.future_priorities
    ) or f'<span style="color:{DIM};font-size:0.85em">None pending</span>'

    # Watch List
    watch_items = "".join(
        f'<span style="background:{BG2};border:1px solid {BOR};color:{FG};padding:4px 10px;'
        f'border-radius:4px;font-size:0.83em;margin-right:6px;margin-bottom:6px;display:inline-block">'
        f'👁 {t}</span>'
        for t in snap.watch_list
    ) or f'<span style="color:{DIM};font-size:0.85em">Empty</span>'

    return f"""
<div style="background:{BG1};border:1px solid {BOR};border-radius:10px;padding:20px 24px;margin-bottom:18px">
  {_section_header("TODAY", "📋")}
  <div style="color:{B};font-size:0.8em;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;margin:12px 0 6px">High Conviction Buys</div>
  {hcb_block}
  <div style="color:{B};font-size:0.8em;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;margin:16px 0 6px">Future Priorities</div>
  <div style="margin-bottom:12px">{fp_items}</div>
  <div style="color:{B};font-size:0.8em;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;margin:16px 0 6px">Watch List ({len(snap.watch_list)})</div>
  <div>{watch_items}</div>
</div>"""


def _section_current_portfolio(snap) -> str:
    """CURRENT PORTFOLIO — all held positions with return and sector."""
    rows = ""
    for p in sorted(snap.held_positions, key=lambda x: x.get("return_pct", 0), reverse=True):
        ret = p.get("return_pct", 0) or 0
        ret_col = G if ret >= 0 else R
        ret_str = f'+{ret:.1f}%' if ret >= 0 else f'{ret:.1f}%'
        r2 = p.get("r2_score", 0) or 0
        r2_col = G if r2 >= 65 else (A if r2 >= 45 else R)
        rows += (
            f'<tr style="border-bottom:1px solid {BOR}">'
            f'<td style="padding:7px 12px;color:{FG};font-weight:600;font-size:0.88em">{p.get("ticker","")}</td>'
            f'<td style="padding:7px 12px;color:{DIM};font-size:0.82em">{p.get("sector","")}</td>'
            f'<td style="padding:7px 12px;font-size:0.85em;color:{FG}">{p.get("entry_price",0):.2f} EGP</td>'
            f'<td style="padding:7px 12px;font-size:0.85em;color:{FG}">{p.get("current_price",0):.2f} EGP</td>'
            f'<td style="padding:7px 12px;font-weight:700;color:{ret_col}">{ret_str}</td>'
            f'<td style="padding:7px 12px;color:{r2_col};font-size:0.82em">{r2:.0f}</td>'
            f'</tr>'
        )
    if not rows:
        rows = f'<tr><td colspan=6 style="padding:10px;color:{DIM}">No held positions</td></tr>'

    return f"""
<div style="background:{BG1};border:1px solid {BOR};border-radius:10px;padding:20px 24px;margin-bottom:18px">
  {_section_header("CURRENT PORTFOLIO", "📂")}
  <div style="overflow-x:auto">
  <table style="width:100%;border-collapse:collapse;font-size:0.88em">
    <tr style="border-bottom:1px solid {BOR}">
      <th style="padding:5px 12px;color:{DIM};text-align:left">Ticker</th>
      <th style="padding:5px 12px;color:{DIM};text-align:left">Sector</th>
      <th style="padding:5px 12px;color:{DIM};text-align:left">Entry</th>
      <th style="padding:5px 12px;color:{DIM};text-align:left">Current</th>
      <th style="padding:5px 12px;color:{DIM};text-align:left">Return</th>
      <th style="padding:5px 12px;color:{DIM};text-align:left">R2</th>
    </tr>
    {rows}
  </table>
  </div>
</div>"""


def _section_portfolio_health_metrics(snap) -> str:
    """PORTFOLIO HEALTH — Sector balance, correlation, concentration."""
    # Sector bars
    sector_rows = ""
    for sector, pct in sorted(snap.sector_allocation.items(), key=lambda x: -x[1]):
        cap_exceeded = pct > 25
        bar_col = R if cap_exceeded else (A if pct > 20 else G)
        bar_w = min(100, int(pct * 3))
        sector_rows += (
            f'<tr style="border-bottom:1px solid {BOR}">'
            f'<td style="padding:6px 12px;color:{FG};font-size:0.85em;width:160px">{sector}</td>'
            f'<td style="padding:6px 12px">'
            f'<div style="display:flex;align-items:center;gap:8px">'
            f'<div style="background:{BG0};width:140px;height:8px;border-radius:4px;overflow:hidden">'
            f'<div style="background:{bar_col};width:{bar_w}%;height:100%"></div></div>'
            f'<span style="color:{bar_col};font-weight:700;font-size:0.85em">{pct:.1f}%</span>'
            + (f'<span style="color:{R};font-size:0.75em"> ⚠ Cap</span>' if cap_exceeded else '')
            + f'</div></td>'
            f'</tr>'
        )

    corr_col = R if snap.max_correlation > 0.7 else (A if snap.max_correlation > 0.5 else G)
    pos_w = snap.position_weight_pct

    metrics_cells = (
        f'<div style="flex:1;min-width:140px;background:{BG2};border:1px solid {BOR};'
        f'border-radius:6px;padding:12px 14px;text-align:center">'
        f'<div style="font-size:1.3em;font-weight:700;color:{corr_col}">{snap.max_correlation:.3f}</div>'
        f'<div style="color:{DIM};font-size:0.75em;margin-top:4px">Max Correlation</div></div>'
        f'<div style="flex:1;min-width:140px;background:{BG2};border:1px solid {BOR};'
        f'border-radius:6px;padding:12px 14px;text-align:center">'
        f'<div style="font-size:1.3em;font-weight:700;color:{FG}">{pos_w:.1f}%</div>'
        f'<div style="color:{DIM};font-size:0.75em;margin-top:4px">Position Weight</div></div>'
        f'<div style="flex:1;min-width:140px;background:{BG2};border:1px solid {BOR};'
        f'border-radius:6px;padding:12px 14px;text-align:center">'
        f'<div style="font-size:1.3em;font-weight:700;color:{R if snap.capacity_used_pct > 100 else G}">{snap.capacity_used_pct:.0f}%</div>'
        f'<div style="color:{DIM};font-size:0.75em;margin-top:4px">Capacity Used</div></div>'
        f'<div style="flex:1;min-width:140px;background:{BG2};border:1px solid {BOR};'
        f'border-radius:6px;padding:12px 14px;text-align:center">'
        f'<div style="font-size:1.3em;font-weight:700;color:{FG}">{snap.held_count}</div>'
        f'<div style="color:{DIM};font-size:0.75em;margin-top:4px">Positions Held</div></div>'
    )

    return f"""
<div style="background:{BG1};border:1px solid {BOR};border-radius:10px;padding:20px 24px;margin-bottom:18px">
  {_section_header("PORTFOLIO HEALTH", "⚖️")}
  <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:16px">{metrics_cells}</div>
  <div style="color:{B};font-size:0.8em;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:8px">Sector Allocation</div>
  <table style="width:100%;border-collapse:collapse">{sector_rows}</table>
</div>"""


def _section_research_insights(snap) -> str:
    """RESEARCH — Latest verified findings from knowledge base."""
    rows = ""
    for ins in snap.research_insights:
        conf_col = G if ins.get("confidence") == "HIGH" else (A if ins.get("confidence") == "MEDIUM" else DIM)
        conclusion = ins.get("conclusion") or ""
        rows += (
            f'<div style="background:{BG2};border:1px solid {BOR};border-radius:6px;'
            f'padding:10px 14px;margin-bottom:8px">'
            f'<div style="color:{DIM};font-size:0.8em;margin-bottom:4px">{ins.get("question","")}</div>'
            f'<div style="color:{FG};font-size:0.85em">{conclusion[:150]}</div>'
            f'<div style="margin-top:4px">'
            f'<span style="background:{conf_col};color:#fff;padding:1px 7px;border-radius:3px;font-size:0.72em;font-weight:600">{ins.get("confidence","")}</span>'
            f'<span style="color:{G};font-size:0.72em;margin-left:8px">✓ VERIFIED</span>'
            f'</div></div>'
        )
    if not rows:
        rows = f'<div style="color:{DIM};font-size:0.85em;padding:8px">No verified findings yet.</div>'

    stats = (
        f'<span style="color:{FG};font-size:0.85em;margin-right:16px">📚 {snap.knowledge_count} findings</span>'
        f'<span style="color:{A};font-size:0.85em">🔬 {snap.experiments_running} experiments running</span>'
    )

    return f"""
<div style="background:{BG1};border:1px solid {BOR};border-radius:10px;padding:20px 24px;margin-bottom:18px">
  {_section_header("RESEARCH", "🔬")}
  <div style="margin-bottom:12px">{stats}</div>
  {rows}
</div>"""


def build_dashboard() -> str:
    from presentation.portfolio_snapshot import build_portfolio_snapshot
    snap    = build_portfolio_snapshot()
    now     = _now_cairo()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    body = (
        f'<div id="header">{_section_portfolio_header(snap)}</div>'
        f'<div id="today">{_section_today(snap)}</div>'
        f'<div id="portfolio">{_section_current_portfolio(snap)}</div>'
        f'<div id="health">{_section_portfolio_health_metrics(snap)}</div>'
        f'<div id="research">{_section_research_insights(snap)}</div>'
        f'<div id="system">{_section_system_health()}</div>'
    )

    return f"""<!DOCTYPE html>
<html lang="en" dir="ltr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{DASH_TITLE}</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:'Segoe UI',system-ui,sans-serif;background:{BG0};color:{FG};padding:0}}
    .header{{background:linear-gradient(135deg,#0a1628,#141e40);border-bottom:2px solid {B};
             padding:20px 28px;display:flex;align-items:center;justify-content:space-between}}
    .header h1{{font-size:1.2em;color:#fff;font-weight:700;letter-spacing:0.04em}}
    .header .meta{{font-size:0.78em;color:{DIM}}}
    .nav{{display:flex;gap:10px;padding:10px 28px;background:#0e0f23;border-bottom:1px solid {BOR};
          font-size:0.78em;align-items:center;flex-wrap:wrap}}
    .nav a{{color:{B};text-decoration:none;padding:4px 9px;border-radius:4px;
            border:1px solid {BOR};transition:background 0.2s;white-space:nowrap}}
    .nav a:hover{{background:{BG2}}}
    .nav .active{{background:{BG2};border-color:{B}}}
    .container{{max-width:1080px;margin:24px auto;padding:0 16px}}
    .footer{{text-align:center;color:{DIM};font-size:0.75em;padding:24px 0 36px;
             border-top:1px solid {BOR};margin-top:12px}}
    table th{{font-weight:600}}
  </style>
</head>
<body>

<div class="header">
  <div>
    <h1>⚡ {DASH_TITLE}</h1>
    <div class="meta">{DASH_SUBTITLE}</div>
  </div>
  <div class="meta" style="text-align:right">
    <div style="color:{FG}">{now_str}</div>
    <div>Cairo Time</div>
  </div>
</div>

<div class="nav">
  <span style="color:{DIM};font-size:0.85em">GO TO:</span>
  <a href="#header" class="active" style="border-color:{B};color:{B}">⚖️ Health</a>
  <a href="#today">📋 Today</a>
  <a href="#portfolio">📂 Portfolio</a>
  <a href="#health">⚖️ Metrics</a>
  <a href="#research">🔬 Research</a>
  <a href="#system">🔧 System</a>
  <a href="heatmap.html" style="border-color:{G};color:{G}">📈 Heatmap</a>
</div>

<div class="container">
{body}
<div class="footer">
  {DASH_FOOTER.format(ts=now_str)}
  <a href="heatmap.html" style="color:{B};text-decoration:none">📈 Signal Heatmap</a>
</div>
</div>

</body>
</html>"""


# ── Status JSON ──────────────────────────────────────────────────────────────

def _write_status_json():
    try:
        n_sig = _db_scalar("SELECT COUNT(*) FROM signals")
        lv    = _db_query("SELECT verdict, oos_wr FROM validation_runs ORDER BY id DESC LIMIT 1")
        status = {
            "generated_at": _now_cairo().isoformat(),
            "n_signals":    n_sig,
            "alpha_status": lv[0].get("verdict") if lv else "UNKNOWN",
            "oos_wr":       lv[0].get("oos_wr") if lv else 0,
        }
        with open("scan_status.json", "w") as f:
            json.dump(status, f, indent=2)
    except Exception:
        pass


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    print("[Dashboard] Building executive operations center...")
    html = build_dashboard()
    with open(DASHBOARD_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    _write_status_json()
    size_kb = os.path.getsize(DASHBOARD_FILE) // 1024
    print(f"[Dashboard] Saved → {DASHBOARD_FILE} ({size_kb} KB)")


if __name__ == "__main__":
    main()
