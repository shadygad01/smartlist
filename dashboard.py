"""
EGX Scanner — Executive Operations Center Dashboard
====================================================
Sections:
  1. Alpha Engine Status
  2. Bottom Discovery Pipeline  [NEW]
  3. Today's Learning           [IMPROVED]
  4. Current Research           [IMPROVED]
  5. Production Alpha Snapshot  [NEW]
  6. Top Knowledge Findings     [NEW]
  7. Alpha Performance
  8. Changes Since Yesterday    [NEW]
  9. Deployment History
 10. System Health
"""

import json
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

DASHBOARD_FILE = "dashboard.html"
DB_PATH        = "egx_research.db"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}


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


# ── CSS constants ─────────────────────────────────────────────────────────────
G   = "#4caf50"   # green
R   = "#f44336"   # red
A   = "#f0b840"   # amber
B   = "#50d8d0"   # blue accent
DIM = "#8b8fa8"   # dim text
FG  = "#d0d4e8"   # foreground
BG0 = "#0b0c1a"   # page background
BG1 = "#10112a"   # card background
BG2 = "#181930"   # inner box
BOR = "#252645"   # border


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
    return (f'<div style="color:{B};font-size:1em;font-weight:700;letter-spacing:0.05em;'
            f'margin:0 0 12px;padding-bottom:8px;border-bottom:1px solid {BOR}">'
            f'{icon} {title}</div>')


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
# SECTION 1 — ALPHA ENGINE STATUS
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
              f"built {_ts(datetime.now().isoformat())} | 11 sections | all data from live state"),
    ])

    weights_row = " | ".join(
        f"{k}={v:.2f}" for k, v in sorted(weights.items()) if isinstance(v, (int, float))
    ) if weights else "—"

    return f"""
<div style="background:{BG1};border:2px solid {B};border-radius:10px;padding:20px 24px;margin-bottom:18px">
  {_section_header("ALPHA ENGINE STATUS", "⚡")}
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
# SECTION 3 — TODAY'S LEARNING  [IMPROVED]
# ══════════════════════════════════════════════════════════════════════════════

def _section_todays_learning() -> str:
    mem    = _load("gx_learning_memory.json")
    cycles = mem.get("cycles", [])

    kb_data        = _load("knowledge_base.json")
    factor_findings = _ff_list(kb_data)

    deployments = _db_query("SELECT * FROM deployment_log ORDER BY id DESC LIMIT 10")
    val_rows    = _db_query(
        "SELECT id, run_at, verdict, oos_wr, oos_sharpe, val_wr FROM validation_runs ORDER BY id DESC LIMIT 5"
    )
    exp_rows    = _db_query(
        "SELECT lab, run_at, n_signals FROM experiment_log ORDER BY id DESC LIMIT 5"
    )

    today_str    = datetime.now().strftime("%Y-%m-%d")
    yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    today_cycles = [c for c in reversed(cycles) if str(c.get("recorded_at", "")).startswith(today_str)]
    all_recent   = list(reversed(cycles))[:8]
    shown_cycles = today_cycles if today_cycles else all_recent

    # ── Summary card: TODAY THE SYSTEM LEARNED ───────────────────────────────
    # Counts since yesterday
    n_new_outcomes  = _db_scalar(
        "SELECT COUNT(*) FROM bottom_quality WHERE computed_at >= ?", (yesterday_str,)
    )
    n_new_signals   = _db_scalar(
        "SELECT COUNT(*) FROM signals WHERE created_at >= ?", (yesterday_str,)
    )
    n_new_findings  = sum(
        1 for f in factor_findings
        if isinstance(f, dict) and str(f.get("recorded_at", "")) >= yesterday_str
    )
    n_new_promos    = _db_scalar(
        "SELECT COUNT(*) FROM deployment_log WHERE action='PROMOTE' AND deployed_at >= ?",
        (yesterday_str,)
    )
    n_new_rollbacks = _db_scalar(
        "SELECT COUNT(*) FROM deployment_log WHERE action='ROLLBACK' AND deployed_at >= ?",
        (yesterday_str,)
    )
    n_new_val       = _db_scalar(
        "SELECT COUNT(*) FROM validation_runs WHERE run_at >= ?", (yesterday_str,)
    )
    n_new_exp       = _db_scalar(
        "SELECT COUNT(*) FROM experiment_log WHERE run_at >= ?", (yesterday_str,)
    )
    # Signals waiting for maturation (no mfe_40d yet)
    cutoff_40d = (datetime.now() - timedelta(days=40)).strftime("%Y-%m-%d")
    n_maturing = _db_scalar(
        "SELECT COUNT(*) FROM signals s LEFT JOIN bottom_quality bq ON s.id=bq.signal_id "
        "WHERE s.signal_date >= ? AND s.signal_date <= ? AND bq.mfe_40d IS NULL",
        (cutoff_40d, today_str)
    )

    # Recent learning cycle info
    last_cycle = shown_cycles[0] if shown_cycles else {}
    outcomes_today = last_cycle.get("outcomes_processed", 0) or 0
    promoted_today = any(c.get("promoted") for c in shown_cycles)

    def _delta_item(icon, label, val, col=FG, show_zero=True):
        if not show_zero and val == 0:
            return ""
        sign = "+" if val > 0 else ""
        return (f'<div style="display:flex;align-items:center;gap:8px;padding:6px 0;'
                f'border-bottom:1px solid {BOR}">'
                f'<span style="font-size:1em">{icon}</span>'
                f'<span style="color:{DIM};font-size:0.83em;flex:1">{label}</span>'
                f'<span style="font-size:1.0em;font-weight:700;color:{col}">{sign}{val}</span>'
                f'</div>')

    summary_items = (
        _delta_item("📈", "Outcomes matured (mfe_40d computed)", n_new_outcomes, G if n_new_outcomes else FG, True)
        + _delta_item("🧬", "New factors classified in knowledge base", n_new_findings, G if n_new_findings else FG, True)
        + _delta_item("🔬", "Validation runs completed", n_new_val, B if n_new_val else FG, True)
        + _delta_item("🧪", "Experiments executed (labs)", n_new_exp, B if n_new_exp else FG, True)
        + _delta_item("⬆", "Promotions to production", n_new_promos, G if n_new_promos else A, True)
        + _delta_item("⬇", "Rollbacks triggered", n_new_rollbacks, R if n_new_rollbacks else FG, True)
        + _delta_item("🆕", "New signals stored", n_new_signals, G if n_new_signals else FG, True)
        + _delta_item("⏳", "Signals waiting for maturation", n_maturing, A, True)
    )

    summary_html = _box(
        "TODAY THE SYSTEM LEARNED",
        f'<div style="font-size:0.85em">{summary_items}</div>',
        color=B
    )

    # ── Learning cycles ───────────────────────────────────────────────────────
    def _cycle_badge(c):
        v  = c.get("verdict", "?")
        ok = v == "APPROVED"
        rb = c.get("auto_rolled_back", False)
        cb = c.get("circuit_breaker_reason", "")
        if rb: return _badge(False, "APPROVED", "AUTO-ROLLBACK")
        if cb: return _badge(False, "APPROVED", "CIRCUIT-BREAKER", warn=True)
        return _badge(ok, "APPROVED", v)

    cycle_rows = "".join(
        f'<tr>'
        f'<td style="padding:5px 10px;color:{DIM};font-size:0.8em;white-space:nowrap">{_ts(c.get("finished_at", c.get("recorded_at")))}</td>'
        f'<td style="padding:5px 10px">{_cycle_badge(c)}</td>'
        f'<td style="padding:5px 10px;font-size:0.8em;color:#aab">outcomes={c.get("outcomes_processed","?")}</td>'
        f'<td style="padding:5px 10px;font-size:0.8em;color:#aab">{"✅ Promoted" if c.get("promoted") else "Not promoted"}</td>'
        f'<td style="padding:5px 10px;font-size:0.79em;color:{DIM}">{c.get("rollback_reason", c.get("circuit_breaker_reason", ""))[:50]}</td>'
        f'</tr>'
        for c in shown_cycles
    ) or f'<tr><td colspan=5 style="color:{DIM};padding:5px 10px;font-size:0.8em">No cycles recorded yet</td></tr>'

    dep_rows = "".join(
        f'<tr>'
        f'<td style="padding:4px 10px;color:{DIM};font-size:0.79em;white-space:nowrap">{_ts(d.get("deployed_at"))}</td>'
        f'<td style="padding:4px 10px">{_badge(d.get("action")=="PROMOTE","PROMOTE","ROLLBACK",d.get("action")=="ROLLBACK")}</td>'
        f'<td style="padding:4px 10px;font-size:0.79em;color:#aab">{d.get("triggered_by","—")}</td>'
        f'<td style="padding:4px 10px;font-size:0.79em;color:{DIM}">{str(d.get("note",""))[:60]}</td>'
        f'</tr>'
        for d in deployments
    ) or f'<tr><td colspan=4 style="color:{DIM};padding:4px 10px;font-size:0.8em">—</td></tr>'

    # KB findings - newest first
    recent_findings = sorted(factor_findings, key=lambda x: x.get("recorded_at", ""), reverse=True)[:8]
    finding_rows = "".join(
        f'<tr>'
        f'<td style="padding:4px 10px;color:{DIM};font-size:0.79em">{_ts(f.get("recorded_at"))}</td>'
        f'<td style="padding:4px 10px;font-size:0.8em;'
        f'color:{G if f.get("verdict")=="POSITIVE" else R if f.get("verdict")=="NEGATIVE" else A}">'
        f'{f.get("verdict","?")}</td>'
        f'<td style="padding:4px 10px;font-size:0.8em;color:{FG}">{f.get("factor","?")}</td>'
        f'<td style="padding:4px 10px;font-size:0.79em;color:{DIM}">{f.get("source","—")}</td>'
        f'</tr>'
        for f in recent_findings
    ) or f'<tr><td colspan=4 style="color:{DIM};padding:4px 10px;font-size:0.8em">No findings yet</td></tr>'

    matured = _db_query("""
        SELECT s.symbol, s.signal_date, bq.mfe_40d, bq.computed_at
        FROM bottom_quality bq JOIN signals s ON s.id = bq.signal_id
        WHERE bq.mfe_40d IS NOT NULL AND bq.computed_at >= ?
        ORDER BY bq.computed_at DESC LIMIT 5
    """, ((datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d"),))

    mat_rows = "".join(
        f'<tr>'
        f'<td style="padding:4px 10px;font-size:0.8em;color:{FG};font-weight:600">{m.get("symbol","?")}</td>'
        f'<td style="padding:4px 10px;font-size:0.79em;color:{DIM}">{m.get("signal_date","?")}</td>'
        f'<td style="padding:4px 10px;font-size:0.8em;'
        f'color:{G if (m.get("mfe_40d") or 0) >= 0.07 else R}">{_pct(m.get("mfe_40d"))}</td>'
        f'<td style="padding:4px 10px;font-size:0.79em;color:{DIM}">{_ts(m.get("computed_at"))}</td>'
        f'</tr>'
        for m in matured
    ) or f'<tr><td colspan=4 style="color:{DIM};padding:4px 10px;font-size:0.8em">No new outcomes in last 3 days</td></tr>'

    return f"""
<div style="background:{BG1};border:1px solid {BOR};border-radius:10px;padding:20px 24px;margin-bottom:18px">
  {_section_header("TODAY'S LEARNING", "🧠")}

  {summary_html}

  {_box("Learning Cycles (today / most recent)",
    f'<table style="width:100%;border-collapse:collapse">'
    f'<tr style="font-size:0.77em;color:{DIM}">'
    f'<th style="text-align:left;padding:3px 10px">Time</th>'
    f'<th style="text-align:left;padding:3px 10px">Verdict</th>'
    f'<th style="text-align:left;padding:3px 10px">Outcomes</th>'
    f'<th style="text-align:left;padding:3px 10px">Production</th>'
    f'<th style="text-align:left;padding:3px 10px">Note</th></tr>'
    f'{cycle_rows}</table>')}

  {_box("Deployments",
    f'<table style="width:100%;border-collapse:collapse">'
    f'<tr style="font-size:0.77em;color:{DIM}">'
    f'<th style="text-align:left;padding:3px 10px">Time</th>'
    f'<th style="text-align:left;padding:3px 10px">Action</th>'
    f'<th style="text-align:left;padding:3px 10px">Triggered By</th>'
    f'<th style="text-align:left;padding:3px 10px">Note</th></tr>'
    f'{dep_rows}</table>')}

  <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
    {_box("Knowledge Base Findings (newest first)",
      f'<table style="width:100%;border-collapse:collapse">'
      f'<tr style="font-size:0.77em;color:{DIM}">'
      f'<th style="text-align:left;padding:3px 10px">Time</th>'
      f'<th style="text-align:left;padding:3px 10px">Verdict</th>'
      f'<th style="text-align:left;padding:3px 10px">Factor</th>'
      f'<th style="text-align:left;padding:3px 10px">Source</th></tr>'
      f'{finding_rows}</table>')}

    {_box("Newly Matured Outcomes (last 3 days)",
      f'<table style="width:100%;border-collapse:collapse">'
      f'<tr style="font-size:0.77em;color:{DIM}">'
      f'<th style="text-align:left;padding:3px 10px">Symbol</th>'
      f'<th style="text-align:left;padding:3px 10px">Signal Date</th>'
      f'<th style="text-align:left;padding:3px 10px">MFE 40d</th>'
      f'<th style="text-align:left;padding:3px 10px">Computed</th></tr>'
      f'{mat_rows}</table>')}
  </div>
</div>"""


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — CURRENT RESEARCH  [IMPROVED]
# ══════════════════════════════════════════════════════════════════════════════

def _section_current_research() -> str:
    mem_summary = {}
    MIN_OUTCOMES_PER_CYCLE = 5
    MAX_PROMOTIONS_PER_DAY = 3
    try:
        from continuous_learning import LearningMemory, MIN_OUTCOMES_PER_CYCLE, MAX_PROMOTIONS_PER_DAY
        mem_summary = LearningMemory().get_summary()
    except BaseException:
        pass

    last_exp       = _db_query("SELECT lab, run_at, n_signals FROM experiment_log ORDER BY id DESC LIMIT 3")
    n_outcomes     = _db_scalar("SELECT COUNT(*) FROM bottom_quality WHERE mfe_40d IS NOT NULL")
    n_val          = _db_scalar("SELECT COUNT(*) FROM validation_runs")
    last_verdict   = _db_query("SELECT verdict, oos_wr, run_at FROM validation_runs ORDER BY id DESC LIMIT 1")
    lv             = last_verdict[0] if last_verdict else {}

    cutoff_40d  = (datetime.now() - timedelta(days=40)).strftime("%Y-%m-%d")
    today_str   = datetime.now().strftime("%Y-%m-%d")
    n_maturing  = _db_scalar(
        "SELECT COUNT(*) FROM signals s LEFT JOIN bottom_quality bq ON s.id=bq.signal_id "
        "WHERE s.signal_date >= ? AND s.signal_date <= ? AND bq.mfe_40d IS NULL",
        (cutoff_40d, today_str)
    )

    recent     = mem_summary.get("recent_cycles", [])
    last_cycle = recent[-1] if recent else {}
    last_outcomes  = last_cycle.get("outcomes_processed", 0) or 0
    need_more      = max(0, MIN_OUTCOMES_PER_CYCLE - last_outcomes)

    try:
        from continuous_learning import LearningMemory
        recent_promo = LearningMemory().get_recent_promotions_count(hours=24)
    except BaseException:
        recent_promo = 0

    cb_ok          = recent_promo < MAX_PROMOTIONS_PER_DAY
    pending_promo  = lv.get("verdict") == "APPROVED" and not last_cycle.get("promoted", False)

    # Research memory — show WHY / EXPECTED IMPACT for active items
    rm             = _load("gx_research_memory.json")
    backlog        = rm.get("backlog", [])
    research_items = rm.get("research_items", {})
    run_log        = rm.get("run_log", [])
    last_research  = run_log[-1] if run_log else {}

    # Impact label helper
    def _impact_label(impact_val):
        v = float(impact_val) if impact_val else 0
        if v > 0.05:   return f'<span style="color:{G};font-weight:600">HIGH</span>'
        if v > 0.02:   return f'<span style="color:{A};font-weight:600">MEDIUM</span>'
        return f'<span style="color:{DIM}">LOW</span>'

    def _priority_col(p):
        return {
            "CRITICAL": R, "HIGH": A, "MEDIUM": B, "LOW": DIM
        }.get(str(p).upper(), DIM)

    # Top research items from backlog (highest priority first)
    priority_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    sorted_backlog = sorted(backlog,
        key=lambda x: (priority_order.get(str(x.get("priority","")).upper(), 9),
                       -(float(x.get("impact", 0)) or 0)))[:6]

    research_cards = ""
    for item in sorted_backlog:
        title   = item.get("title", "?")[:80]
        why     = item.get("next_action", item.get("evidence", "Insufficient evidence"))
        why     = str(why)[:120] if why else "—"
        impact  = item.get("impact", 0)
        prio    = str(item.get("priority", "?"))
        status  = str(item.get("status", "?"))
        ind     = item.get("indicator", "?")
        p_col   = _priority_col(prio)
        research_cards += (
            f'<div style="background:{BG0};border:1px solid {BOR};border-radius:7px;'
            f'padding:10px 14px;margin-bottom:8px">'
            f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">'
            f'<span style="font-size:0.75em;font-weight:700;color:{p_col};'
            f'background:{BG2};padding:2px 7px;border-radius:4px">{prio}</span>'
            f'<span style="font-size:0.83em;color:{FG};font-weight:600">{title}</span>'
            f'</div>'
            f'<div style="display:grid;grid-template-columns:80px 1fr;gap:4px 12px;font-size:0.8em">'
            f'<span style="color:{DIM}">WHAT</span>'
            f'<span style="color:{FG}">{ind} — {status}</span>'
            f'<span style="color:{DIM}">WHY</span>'
            f'<span style="color:#aab">{why}</span>'
            f'<span style="color:{DIM}">IMPACT</span>'
            f'<span>{_impact_label(impact)} ({_pct(impact) if impact else "—"})</span>'
            f'</div></div>'
        )

    if not research_cards:
        research_cards = f'<div style="color:{DIM};font-size:0.83em">No active research items</div>'

    # Pipeline state summary
    pipe_rows = "".join([
        _row2("Currently Running",   ", ".join(e.get("lab","?") for e in last_exp) if last_exp else "—",
              f'last run: {_ts(last_exp[0].get("run_at") if last_exp else None)}'),
        _row2("Waiting For Data",    f"{n_maturing} signals maturing",
              "need mfe_40d outcome (up to 40 days after signal_date)"),
        _row2("Research Backlog",    f"{len(backlog)} items",
              f'last_research={_ts(last_research.get("date"))} | {last_research.get("n_active",0)} active'),
        _row2("Pending Validation",  f"Need {need_more} more" if need_more > 0 else "Ready to validate",
              f"threshold={MIN_OUTCOMES_PER_CYCLE} outcomes/cycle | last had {last_outcomes}"),
        _row2("Promotion Gate",      _badge(cb_ok, "OPEN", "CIRCUIT BREAKER", warn=not cb_ok),
              f"{recent_promo}/{MAX_PROMOTIONS_PER_DAY} promotions in 24h | "
              f'{"APPROVED verdict pending" if pending_promo else "no cycle pending"}'),
    ])

    return f"""
<div style="background:{BG1};border:1px solid {BOR};border-radius:10px;padding:20px 24px;margin-bottom:18px">
  {_section_header("CURRENT RESEARCH", "🔬")}
  {_box("Live Pipeline State",
    f'<table style="width:100%;border-collapse:collapse">{pipe_rows}</table>')}
  {_box("Active Research Items — What · Why · Expected Impact", research_cards, color=B)}
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
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    today     = datetime.now().strftime("%Y-%m-%d")

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
            dt    = datetime.fromisoformat(str(iso).replace("Z", ""))
            delta = datetime.now() - dt
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
        ("Dashboard Built",        _ts(datetime.now().isoformat()), "just now"),
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


def build_dashboard() -> str:
    now     = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    body = (
        f'<div id="alpha-status">{_section_alpha_status()}</div>'
        f'<div id="pipeline">{_section_bottom_pipeline()}</div>'
        f'<div id="learning">{_section_todays_learning()}</div>'
        f'<div id="research">{_section_current_research()}</div>'
        f'<div id="snapshot">{_section_production_snapshot()}</div>'
        f'<div id="knowledge">{_section_knowledge_findings()}</div>'
        f'<div id="performance">{_section_alpha_performance()}</div>'
        f'<div id="classification">{_section_classification_fib()}</div>'
        f'<div id="changes">{_section_changes_since_yesterday()}</div>'
        f'<div id="deployments">{_section_deployment_history()}</div>'
        f'<div id="health">{_section_system_health()}</div>'
    )

    return f"""<!DOCTYPE html>
<html lang="en" dir="ltr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>EGX — Operations Center</title>
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
    <h1>⚡ EGX Executive Operations Center</h1>
    <div class="meta">EGX Autonomous Bottom Discovery Platform — Live State · 11 Sections</div>
  </div>
  <div class="meta" style="text-align:right">
    <div style="color:{FG}">{now_str}</div>
    <div>Cairo Time</div>
  </div>
</div>

<div class="nav">
  <span style="color:{DIM};font-size:0.85em">GO TO:</span>
  <a href="#alpha-status" class="active">⚡ Status</a>
  <a href="#pipeline">🔭 Pipeline</a>
  <a href="#learning">🧠 Learning</a>
  <a href="#research">🔬 Research</a>
  <a href="#snapshot">🎯 Alpha Snapshot</a>
  <a href="#knowledge">📚 Knowledge</a>
  <a href="#performance">📊 Performance</a>
  <a href="#classification">🎯 Classification</a>
  <a href="#changes">📅 Changes</a>
  <a href="#deployments">🚀 Deployments</a>
  <a href="#health">🔧 Health</a>
  <a href="heatmap.html" style="border-color:{G};color:{G}">📈 Heatmap</a>
</div>

<div class="container">
{body}
<div class="footer">
  EGX Autonomous Bottom Discovery Platform · Built {now_str} · 11 sections
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
            "generated_at": datetime.now().isoformat(),
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
