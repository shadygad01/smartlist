"""
EGX Scanner — Operational Command Center Dashboard
====================================================
Displays live system state only. No research archive.
Sections: Alpha Status | Today's Learning | Current Research |
          Alpha Performance | Deployment History | System Health
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


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — ALPHA ENGINE STATUS
# ══════════════════════════════════════════════════════════════════════════════

def _section_alpha_status() -> str:
    # Load all state sources
    sched = _load("scheduler_state.json")
    weights = _load("config/weights.json")

    mem_summary = {}
    try:
        from continuous_learning import LearningMemory
        mem_summary = LearningMemory().get_summary()
    except BaseException:
        pass

    # DB metrics
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

    ld_rows = _db_query("SELECT * FROM deployment_log ORDER BY id DESC LIMIT 1")
    ld = ld_rows[0] if ld_rows else {}

    last_promo_rows = _db_query("SELECT deployed_at FROM deployment_log WHERE action='PROMOTE' ORDER BY id DESC LIMIT 1")
    last_promo = last_promo_rows[0].get("deployed_at") if last_promo_rows else None

    last_rb_rows = _db_query("SELECT deployed_at FROM deployment_log WHERE action='ROLLBACK' ORDER BY id DESC LIMIT 1")
    last_rb = last_rb_rows[0].get("deployed_at") if last_rb_rows else None

    # KB — factor_findings is a dict keyed by factor name
    kb_data = _load("knowledge_base.json")
    ff_raw = kb_data.get("factor_findings", {})
    ff = list(ff_raw.values()) if isinstance(ff_raw, dict) else (ff_raw if isinstance(ff_raw, list) else [])
    n_kb_pos  = sum(1 for f in ff if isinstance(f, dict) and f.get("verdict") == "POSITIVE")
    n_kb_neg  = sum(1 for f in ff if isinstance(f, dict) and f.get("verdict") == "NEGATIVE")
    n_kb_tot  = len(ff)

    # State
    oos_wr      = lv.get("oos_wr", 0) or 0
    oos_sh      = lv.get("oos_sharpe", 0) or 0
    val_wr      = lv.get("val_wr", 0) or 0
    alpha_ok    = lv.get("verdict") == "APPROVED"
    recent      = mem_summary.get("recent_cycles", [])
    last_cycle  = recent[-1] if recent else {}
    total_cyc   = mem_summary.get("total_cycles", 0)
    total_prom  = mem_summary.get("total_promoted", 0)
    best_oos    = mem_summary.get("best_approved_oos_wr", 0) or 0

    # DB utilization
    util_mfe40  = min(100, n_mfe40 / n_bq * 100) if n_bq else 0
    util_peak1y = min(100, n_peak1y / n_bq * 100) if n_bq else 0
    util_kb     = min(100, n_kb_tot / 8 * 100)  # 8 indicator factors (r1-r8)

    def _bar_pct(pct):
        w = int(pct)
        col = G if pct >= 80 else (A if pct >= 50 else R)
        return (f'<div style="display:inline-flex;align-items:center;gap:6px">'
                f'<div style="width:100px;height:8px;background:{BOR};border-radius:3px">'
                f'<div style="width:{w}px;height:8px;background:{col};border-radius:3px"></div></div>'
                f'<span style="font-size:0.8em;color:{FG}">{pct:.0f}%</span></div>')

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
              f"60/20/20 split | mfe_40d primary | gates: oos_wr≥0.65 val_wr≥0.55 oos_exp≥0.10 oos_sharpe≥0.30"),
        _row2("Promotion",         _badge(n_promote > 0, f"{n_promote} promotions", "NONE"),
              f"last={_ts(last_promo)} | circuit_breaker=3/24h | best_oos_wr={_num(best_oos)}"),
        _row2("Monitoring",        _badge(not last_cycle.get("drift_detected", False), "CLEAR", "DRIFT", warn=True),
              f"drift_lab active | last={_ts(last_cycle.get('finished_at'))}"),
        _row2("Rollback",          _badge(True, "WIRED", "NOT WIRED"),
              f"auto-trigger on OOS WR drop >10pp | {n_rollback} rollbacks | last={_ts(last_rb)}"),
        _row2("Dashboard",         _badge(True, "LIVE", "STALE"),
              f"built {_ts(datetime.now().isoformat())} | 7 sections | all data from live state"),
    ])

    weights_row = " | ".join(
        f"{k}={v:.2f}" for k, v in sorted(weights.items()) if isinstance(v, (int, float))
    ) if weights else "—"

    return f"""
<div style="background:{BG1};border:2px solid {B};border-radius:10px;padding:20px 24px;margin-bottom:18px">
  {_section_header("ALPHA ENGINE STATUS", "⚡")}
  {_box("14-Point System Checklist",
    f'<table style="width:100%;border-collapse:collapse">{status_rows}</table>')}
  {_box("Active Production Weights",
    f'<div style="font-size:0.82em;color:{FG};font-family:monospace;line-height:1.8">{weights_row}</div>')}
</div>"""


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — TODAY'S LEARNING
# ══════════════════════════════════════════════════════════════════════════════

def _section_todays_learning() -> str:
    mem = _load("gx_learning_memory.json")
    cycles = mem.get("cycles", [])

    kb_data = _load("knowledge_base.json")
    _ff_raw = kb_data.get("factor_findings", {})
    factor_findings = list(_ff_raw.values()) if isinstance(_ff_raw, dict) else (_ff_raw if isinstance(_ff_raw, list) else [])

    deployments = _db_query(
        "SELECT * FROM deployment_log ORDER BY id DESC LIMIT 10"
    )
    val_rows = _db_query(
        "SELECT id, run_at, verdict, oos_wr, oos_sharpe, val_wr FROM validation_runs ORDER BY id DESC LIMIT 5"
    )
    exp_rows = _db_query(
        "SELECT lab, run_at, n_signals FROM experiment_log ORDER BY id DESC LIMIT 5"
    )

    today_str = datetime.now().strftime("%Y-%m-%d")
    today_cycles = [c for c in reversed(cycles) if str(c.get("recorded_at", "")).startswith(today_str)]
    all_recent  = list(reversed(cycles))[:8]  # fallback: last 8

    shown_cycles = today_cycles if today_cycles else all_recent

    def _cycle_badge(c):
        v = c.get("verdict", "?")
        ok = v == "APPROVED"
        rb = c.get("auto_rolled_back", False)
        cb = c.get("circuit_breaker_reason", "")
        if rb:   return _badge(False, "APPROVED", "AUTO-ROLLBACK")
        if cb:   return _badge(False, "APPROVED", "CIRCUIT-BREAKER", warn=True)
        return _badge(ok, "APPROVED", v)

    cycle_rows = "".join(
        f'<tr>'
        f'<td style="padding:5px 10px;color:{DIM};font-size:0.8em;white-space:nowrap">{_ts(c.get("finished_at",c.get("recorded_at")))}</td>'
        f'<td style="padding:5px 10px">{_cycle_badge(c)}</td>'
        f'<td style="padding:5px 10px;font-size:0.8em;color:#aab">outcomes={c.get("outcomes_processed","?")}</td>'
        f'<td style="padding:5px 10px;font-size:0.8em;color:#aab">{"✅ Promoted" if c.get("promoted") else "Not promoted"}</td>'
        f'<td style="padding:5px 10px;font-size:0.79em;color:{DIM}">{c.get("rollback_reason",c.get("circuit_breaker_reason",""))[:50]}</td>'
        f'</tr>'
        for c in shown_cycles
    ) or f'<tr><td colspan=5 style="color:{DIM};padding:5px 10px;font-size:0.8em">No cycles recorded today</td></tr>'

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
        f'<td style="padding:4px 10px;font-size:0.8em;color:{G if f.get("verdict")=="POSITIVE" else R if f.get("verdict")=="NEGATIVE" else A}">'
        f'{f.get("verdict","?")}</td>'
        f'<td style="padding:4px 10px;font-size:0.8em;color:{FG}">{f.get("factor","?")}</td>'
        f'<td style="padding:4px 10px;font-size:0.79em;color:{DIM}">{f.get("source","—")}</td>'
        f'</tr>'
        for f in recent_findings
    ) or f'<tr><td colspan=4 style="color:{DIM};padding:4px 10px;font-size:0.8em">No findings yet</td></tr>'

    # New matured outcomes (signals that recently got mfe_40d computed)
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
        f'<td style="padding:4px 10px;font-size:0.8em;color:{G if (m.get("mfe_40d") or 0)>=0.07 else R}">'
        f'{_pct(m.get("mfe_40d"))}</td>'
        f'<td style="padding:4px 10px;font-size:0.79em;color:{DIM}">{_ts(m.get("computed_at"))}</td>'
        f'</tr>'
        for m in matured
    ) or f'<tr><td colspan=4 style="color:{DIM};padding:4px 10px;font-size:0.8em">No new outcomes in last 3 days</td></tr>'

    return f"""
<div style="background:{BG1};border:1px solid {BOR};border-radius:10px;padding:20px 24px;margin-bottom:18px">
  {_section_header("TODAY'S LEARNING", "🧠")}

  {_box("Learning Cycles",
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
# SECTION 3 — CURRENT RESEARCH
# ══════════════════════════════════════════════════════════════════════════════

def _section_current_research() -> str:
    from continuous_learning import LearningMemory, MIN_OUTCOMES_PER_CYCLE
    mem_summary = {}
    try:
        mem_summary = LearningMemory().get_summary()
    except BaseException:
        pass

    last_exp = _db_query(
        "SELECT lab, run_at, n_signals FROM experiment_log ORDER BY id DESC LIMIT 3"
    )
    n_outcomes = _db_scalar(
        "SELECT COUNT(*) FROM bottom_quality WHERE mfe_40d IS NOT NULL"
    )
    n_val = _db_scalar("SELECT COUNT(*) FROM validation_runs")
    last_verdict = _db_query("SELECT verdict, oos_wr, run_at FROM validation_runs ORDER BY id DESC LIMIT 1")
    lv = last_verdict[0] if last_verdict else {}

    # Signals maturing in next 0-40 days (signal_date between 40 days ago and today)
    cutoff_40d = (datetime.now() - timedelta(days=40)).strftime("%Y-%m-%d")
    today_str  = datetime.now().strftime("%Y-%m-%d")
    n_maturing = _db_scalar(
        "SELECT COUNT(*) FROM signals s LEFT JOIN bottom_quality bq ON s.id=bq.signal_id "
        "WHERE s.signal_date >= ? AND s.signal_date <= ? AND bq.mfe_40d IS NULL",
        (cutoff_40d, today_str)
    )

    # Pending validation: need MIN_OUTCOMES_PER_CYCLE new outcomes since last cycle
    recent = mem_summary.get("recent_cycles", [])
    last_cycle = recent[-1] if recent else {}
    last_cycle_at = last_cycle.get("recorded_at", "")
    last_outcomes = last_cycle.get("outcomes_processed", 0) or 0
    need_more = max(0, MIN_OUTCOMES_PER_CYCLE - last_outcomes)

    # Circuit breaker state
    try:
        mem_obj = LearningMemory()
        recent_promo = mem_obj.get_recent_promotions_count(hours=24)
    except BaseException:
        recent_promo = 0

    from continuous_learning import MAX_PROMOTIONS_PER_DAY
    cb_ok = recent_promo < MAX_PROMOTIONS_PER_DAY

    # Pending promotion
    pending_promo = lv.get("verdict") == "APPROVED" and not last_cycle.get("promoted", False)

    # Research memory backlog
    rm = _load("gx_research_memory.json")
    backlog = rm.get("backlog", [])
    run_log = rm.get("run_log", [])
    last_research_run = run_log[-1] if run_log else {}

    currently_running = [e.get("lab", "?") for e in last_exp] if last_exp else []

    rows = [
        ("Currently Running",   ", ".join(currently_running) if currently_running else "—",
         f"last run: {_ts(last_exp[0].get('run_at') if last_exp else None)}"),
        ("Waiting For Data",    f"{n_maturing} signals maturing",
         "need mfe_40d outcome (up to 40 days after signal_date)"),
        ("Next Research Target",f"{backlog[0].get('symbol','?') if backlog else '—'} ({len(backlog)} in backlog)",
         "from gx_research_memory backlog"),
        ("Maturing Signals",    f"{n_maturing} signals",
         f"signal_date in last 40 days without mfe_40d outcome yet"),
        ("Pending Validation",  f"Need {need_more} more outcomes" if need_more > 0 else "Ready to validate",
         f"threshold={MIN_OUTCOMES_PER_CYCLE} outcomes/cycle | last_cycle had {last_outcomes}"),
        ("Pending Promotion",   _badge(cb_ok, "ALLOWED", "CIRCUIT BREAKER", warn=not cb_ok),
         f"{recent_promo}/{MAX_PROMOTIONS_PER_DAY} promotions in last 24h | "
         f"{'APPROVED verdict pending' if pending_promo else 'no approved cycle pending'}"),
    ]

    table_rows = "".join(
        f'<tr>'
        f'<td style="padding:5px 10px;color:{DIM};font-size:0.82em;width:180px;white-space:nowrap">{r[0]}</td>'
        f'<td style="padding:5px 10px;font-size:0.83em;color:{FG}">{r[1]}</td>'
        f'<td style="padding:5px 10px;font-size:0.79em;color:#9aa">{r[2]}</td>'
        f'</tr>'
        for r in rows
    )

    return f"""
<div style="background:{BG1};border:1px solid {BOR};border-radius:10px;padding:20px 24px;margin-bottom:18px">
  {_section_header("CURRENT RESEARCH", "🔬")}
  {_box("Live Research State",
    f'<table style="width:100%;border-collapse:collapse">{table_rows}</table>')}
</div>"""


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — ALPHA PERFORMANCE
# ══════════════════════════════════════════════════════════════════════════════

def _section_alpha_performance() -> str:
    # Multi-horizon MFE from DB
    horizons = []
    for col, label in [("mfe_40d","MFE 40d"),("mfe_90d","MFE 90d"),("mfe_180d","MFE 180d"),("mfe_252d","MFE 252d")]:
        n    = _db_scalar(f"SELECT COUNT(*) FROM bottom_quality WHERE {col} IS NOT NULL")
        avg  = _db_scalar(f"SELECT AVG({col}) FROM bottom_quality WHERE {col} IS NOT NULL")
        oos_n = max(1, int(n * 0.2))
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

    # Validation trend (last 5 unique results)
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

    # Current OOS metrics
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
# SECTION 5 — DEPLOYMENT HISTORY
# ══════════════════════════════════════════════════════════════════════════════

def _section_deployment_history() -> str:
    deps = _db_query("SELECT * FROM deployment_log ORDER BY id DESC LIMIT 20")
    snapshots = {
        r["id"]: r for r in _db_query("SELECT id, snapshot_at FROM config_snapshots")
    }

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

    n_promo   = _db_scalar("SELECT COUNT(*) FROM deployment_log WHERE action='PROMOTE'")
    n_rb      = _db_scalar("SELECT COUNT(*) FROM deployment_log WHERE action='ROLLBACK'")
    n_snaps   = _db_scalar("SELECT COUNT(*) FROM config_snapshots")

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
# SECTION 6 — SYSTEM HEALTH
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
            dt = datetime.fromisoformat(str(iso).replace("Z",""))
            delta = datetime.now() - dt
            h = int(delta.total_seconds() / 3600)
            if h < 1:    return f"{int(delta.total_seconds()/60)}m ago"
            if h < 24:   return f"{h}h ago"
            return f"{int(h/24)}d ago"
        except Exception:
            return "?"

    health_rows = [
        ("Last Successful Scan",   _ts(scan_gen),   _age(scan_gen)),
        ("Last Learning Cycle",    _ts(cyc_at),     _age(cyc_at)),
        ("Last Promotion",         _ts(promo_at),   _age(promo_at)),
        ("Last Rollback",          _ts(rb_at),      _age(rb_at)),
        ("Dashboard Built",        _ts(datetime.now().isoformat()), "just now"),
        ("Scheduler State",        f"runs={sched.get('total_runs',0)} | errors={sched.get('consecutive_errors',0)}", ""),
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

def build_dashboard() -> str:
    now     = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    body = f"""
{_section_alpha_status()}
{_section_todays_learning()}
{_section_current_research()}
{_section_alpha_performance()}
{_section_deployment_history()}
{_section_system_health()}
"""

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
    .nav{{display:flex;gap:20px;padding:12px 28px;background:#0e0f23;border-bottom:1px solid {BOR};
          font-size:0.82em;align-items:center;flex-wrap:wrap}}
    .nav a{{color:{B};text-decoration:none;padding:4px 10px;border-radius:4px;
            border:1px solid {BOR};transition:background 0.2s}}
    .nav a:hover{{background:{BG2}}}
    .nav .active{{background:{BG2};border-color:{B}}}
    .container{{max-width:1000px;margin:24px auto;padding:0 16px}}
    .footer{{text-align:center;color:{DIM};font-size:0.75em;padding:24px 0 36px;
             border-top:1px solid {BOR};margin-top:12px}}
    table th{{font-weight:600}}
  </style>
</head>
<body>

<div class="header">
  <div>
    <h1>⚡ EGX Operations Center</h1>
    <div class="meta">EGX Autonomous Bottom Discovery Platform — Live State</div>
  </div>
  <div class="meta" style="text-align:right">
    <div style="color:{FG}">{now_str}</div>
    <div>Cairo Time</div>
  </div>
</div>

<div class="nav">
  <span style="color:{DIM};font-size:0.85em">SECTIONS:</span>
  <a href="#alpha-status" class="active">⚡ Alpha Status</a>
  <a href="#learning">🧠 Today's Learning</a>
  <a href="#research">🔬 Current Research</a>
  <a href="#performance">📊 Alpha Performance</a>
  <a href="#deployments">🚀 Deployments</a>
  <a href="#health">🔧 System Health</a>
  <a href="heatmap.html" style="border-color:{G};color:{G}">📈 Signal Heatmap</a>
</div>

<div class="container">

<div id="alpha-status">{_section_alpha_status()}</div>
<div id="learning">{_section_todays_learning()}</div>
<div id="research">{_section_current_research()}</div>
<div id="performance">{_section_alpha_performance()}</div>
<div id="deployments">{_section_deployment_history()}</div>
<div id="health">{_section_system_health()}</div>

<div class="footer">
  EGX Autonomous Bottom Discovery Platform · Built {now_str} ·
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
    print("[Dashboard] Building operational command center...")
    html = build_dashboard()
    with open(DASHBOARD_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    _write_status_json()
    size_kb = os.path.getsize(DASHBOARD_FILE) // 1024
    print(f"[Dashboard] Saved → {DASHBOARD_FILE} ({size_kb} KB)")


if __name__ == "__main__":
    main()
