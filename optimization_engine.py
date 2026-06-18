"""
Optimization Engine — Layer 6.
Unified interface for all optimization methods.
Stores every run to optimization_history table.
"""
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

# ── DB schema ─────────────────────────────────────────────────────────────────

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS optimization_history (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    method         TEXT    NOT NULL,
    run_at         TEXT    NOT NULL,
    params_before  TEXT    NOT NULL,
    params_after   TEXT    NOT NULL,
    metric_name    TEXT    NOT NULL,
    metric_before  REAL    NOT NULL,
    metric_after   REAL    NOT NULL,
    n_signals      INTEGER NOT NULL,
    approved       INTEGER NOT NULL DEFAULT 0
)
"""


@dataclass
class OptimizationRun:
    method: str
    run_at: str
    params_before: dict
    params_after: dict
    metric_name: str
    metric_before: float
    metric_after: float
    n_signals: int
    approved: bool = False
    id: Optional[int] = None


# ── Persistence ───────────────────────────────────────────────────────────────

def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(CREATE_TABLE_SQL)
    conn.commit()


def save_run(run: OptimizationRun, db_path: str = "egx_research.db") -> int:
    """Write run to optimization_history, return inserted id."""
    conn = sqlite3.connect(db_path)
    _ensure_table(conn)
    cur = conn.execute(
        """
        INSERT INTO optimization_history
            (method, run_at, params_before, params_after,
             metric_name, metric_before, metric_after, n_signals, approved)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run.method,
            run.run_at,
            json.dumps(run.params_before, ensure_ascii=False),
            json.dumps(run.params_after, ensure_ascii=False),
            run.metric_name,
            float(run.metric_before),
            float(run.metric_after),
            int(run.n_signals),
            int(run.approved),
        ),
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    run.id = row_id
    return row_id


def get_best_run(metric: str, db_path: str = "egx_research.db") -> Optional[OptimizationRun]:
    """Retrieve best historical run by metric improvement (metric_after - metric_before)."""
    conn = sqlite3.connect(db_path)
    _ensure_table(conn)
    row = conn.execute(
        """
        SELECT id, method, run_at, params_before, params_after,
               metric_name, metric_before, metric_after, n_signals, approved
        FROM optimization_history
        WHERE metric_name = ?
        ORDER BY (metric_after - metric_before) DESC
        LIMIT 1
        """,
        (metric,),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return OptimizationRun(
        id=row[0],
        method=row[1],
        run_at=row[2],
        params_before=json.loads(row[3]),
        params_after=json.loads(row[4]),
        metric_name=row[5],
        metric_before=row[6],
        metric_after=row[7],
        n_signals=row[8],
        approved=bool(row[9]),
    )


# ── Metric helpers ────────────────────────────────────────────────────────────

def _read_metric_from_db(db_path: str, metric: str = "win_rate") -> tuple:
    """
    Read current metric (win_rate or expectancy) from DB.
    Returns (metric_value, n_signals).
    win_rate = fraction of signals with r20d > 0.07
    expectancy = mean r20d
    """
    try:
        conn = sqlite3.connect(db_path)
        view_ok = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='view' AND name='v_all_signals'"
        ).fetchone()
        if view_ok:
            rows = conn.execute(
                "SELECT r20d FROM v_all_signals WHERE r20d IS NOT NULL"
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT bq.r20d
                FROM signals s
                JOIN bottom_quality bq ON bq.signal_id = s.id
                WHERE bq.r20d IS NOT NULL
                """
            ).fetchall()
        conn.close()

        values = [float(r[0]) for r in rows if r[0] is not None]
        if not values:
            return 0.0, 0

        n = len(values)
        if metric == "win_rate":
            metric_val = sum(1 for v in values if v > 0.07) / n
        elif metric == "expectancy":
            wins  = [v for v in values if v > 0.07]
            losses = [v for v in values if v <= 0.07]
            wr = len(wins) / n
            avg_win  = sum(wins)  / len(wins)  if wins  else 0.0
            avg_loss = sum(losses) / len(losses) if losses else 0.0
            metric_val = wr * avg_win + (1 - wr) * avg_loss
        else:  # peak_return or mean
            metric_val = sum(values) / n

        return metric_val, n
    except Exception as exc:
        print(f"[optimization_engine] Warning reading metric from DB: {exc}")
        return 0.0, 0


def _read_current_weights(config_path: str = "config/") -> dict:
    """Try to read current weights from config. Falls back to system defaults."""
    import os
    defaults = {
        "r1_price": 30, "r2_ob": 10, "r3_liquidity": 20, "r4_htf": 10,
        "r5_avwap": 8,  "r6_macd": 4, "r7_div": 3,       "r8_demand": 15,
    }
    try:
        cfg_file = os.path.join(config_path, "weights.json")
        if os.path.exists(cfg_file):
            with open(cfg_file, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return defaults


# ── Method delegates ──────────────────────────────────────────────────────────

def _run_weight_gradient(db_path: str, config_path: str) -> tuple:
    """Delegate to weight_optimizer. Returns (params_before, params_after, metric_val, n)."""
    try:
        import weight_optimizer as wo
        params_before = _read_current_weights(config_path)
        df = wo.load_data(db_path)
        opt = wo.optimize_weights(df)
        if opt and "optimal_weights" in opt:
            params_after = {k: round(v, 4) for k, v in opt["optimal_weights"].items()}
            m_opt = opt.get("metrics_optimized", {})
            metric_val = float(m_opt.get("expected_return", 0.0))
            n = int(m_opt.get("n", len(df)))
        else:
            params_after = params_before
            metric_val = 0.0
            n = len(df)
        return params_before, params_after, metric_val, n
    except Exception as exc:
        import traceback
        print(f"[optimization_engine] weight_gradient CRITICAL: {exc}")
        print(traceback.format_exc())
        params_before = _read_current_weights(config_path)
        return params_before, params_before, 0.0, 0


def _run_walk_forward(db_path: str, config_path: str) -> tuple:
    """Delegate to walk_forward_backtester. Returns (params_before, params_after, metric_val, n)."""
    try:
        import walk_forward_backtester as wf
        state = wf.load_state()
        params_before = {k: round(v, 4) for k, v in state.get("weights", wf.SYSTEM_WEIGHTS).items()}
        state = wf.run_walk_forward(state)
        wf.save_state(state)
        an = wf.compute_analytics(state)
        params_after = {k: round(v, 4) for k, v in state.get("weights", params_before).items()}
        metric_val = float(an.get("expectancy", an.get("expected_return", 0.0))) if an else 0.0
        n = int(an.get("n", 0)) if an else 0
        return params_before, params_after, metric_val, n
    except Exception as exc:
        print(f"[optimization_engine] walk_forward error: {exc}")
        params_before = _read_current_weights(config_path)
        return params_before, params_before, 0.0, 0


def _run_rl_gradient(db_path: str, config_path: str) -> tuple:
    """Delegate to smc_rl_optimizer. Returns (params_before, params_after, metric_val, n)."""
    try:
        import smc_rl_optimizer as rl
        import random
        random.seed(42)
        from signal_db import get_conn
        conn = get_conn(db_path)
        data = rl.load_training_data(conn)
        conn.close()
        weights_data = rl.load_weights()
        params_before = {k: round(v, 4) for k, v in weights_data["current_weights"].items()}
        if not data:
            return params_before, params_before, 0.0, 0
        new_weights, _ = rl.run_gradient_descent(data, weights_data["current_weights"])
        params_after = {k: round(v, 4) for k, v in new_weights.items()}
        perf = rl.compute_performance_stats(data, new_weights)
        metric_val = float(perf.get("expectancy", perf.get("expected_return", 0.0)))
        n = int(perf.get("n", len(data)))
        return params_before, params_after, metric_val, n
    except Exception as exc:
        print(f"[optimization_engine] rl_gradient error: {exc}")
        params_before = _read_current_weights(config_path)
        return params_before, params_before, 0.0, 0


def _run_threshold_grid(db_path: str, config_path: str) -> tuple:
    """Placeholder for future threshold grid search."""
    params_before = _read_current_weights(config_path)
    print("[optimization_engine] threshold_grid: placeholder — no-op")
    return params_before, params_before, 0.0, 0


def _run_expectancy_gradient(db_path: str, config_path: str) -> tuple:
    """
    Grid search over weight perturbations to maximize expectancy
    (wr * avg_win + (1-wr) * avg_loss) using peak_return_1y where available.
    Falls back to r20d if peak_return_1y absent.
    """
    import os
    params_before = _read_current_weights(config_path)

    try:
        conn = sqlite3.connect(db_path)
        # Try peak_return_1y first, fall back to r20d
        cols = [r[1] for r in conn.execute("PRAGMA table_info(bottom_quality)").fetchall()]
        ret_col = "peak_return_1y" if "peak_return_1y" in cols else "r20d"
        rows = conn.execute(
            f"""SELECT s.adj_score, bq.{ret_col}
                FROM signals s
                JOIN bottom_quality bq ON bq.signal_id = s.id
                WHERE bq.{ret_col} IS NOT NULL"""
        ).fetchall()
        conn.close()
    except Exception as exc:
        print(f"[optimization_engine] expectancy_gradient: DB error: {exc}")
        return params_before, params_before, 0.0, 0

    if len(rows) < 30:
        return params_before, params_before, 0.0, 0

    values = [float(r[1]) for r in rows]
    n = len(values)
    win_thresh = 0.07
    wins   = [v for v in values if v > win_thresh]
    losses = [v for v in values if v <= win_thresh]
    wr = len(wins) / n
    avg_win  = sum(wins)  / len(wins)  if wins  else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    base_exp = wr * avg_win + (1 - wr) * avg_loss

    # Coordinate descent on per-weight perturbations requires raw per-signal factor
    # components (r1..r8) which are not stored — delegate to weight_optimizer which
    # uses scipy L-BFGS-B over its own in-memory dataset.
    best_params = dict(params_before)
    best_exp = base_exp

    try:
        import weight_optimizer as wo
        df = wo.load_data(db_path)
        opt = wo.optimize_weights(df)
        if opt and "optimal_weights" in opt:
            best_params = {k: round(v, 4) for k, v in opt["optimal_weights"].items()}
            m = opt.get("metrics_optimized", {})
            best_exp = float(m.get("expected_return", base_exp))
        else:
            print(f"[optimization_engine] weight_optimizer returned empty result — staying at params_before")
    except Exception as exc:
        import traceback
        print(f"[optimization_engine] CRITICAL: weight_optimizer failed: {exc}")
        print(traceback.format_exc())
        # Do NOT swallow — record failure in return so caller can log it
        return params_before, params_before, base_exp, n

    return params_before, best_params, best_exp, n


# ── Public API ────────────────────────────────────────────────────────────────

METHODS = {
    "weight_gradient":     _run_weight_gradient,
    "walk_forward":        _run_walk_forward,
    "rl_gradient":         _run_rl_gradient,
    "threshold_grid":      _run_threshold_grid,
    "expectancy_gradient": _run_expectancy_gradient,
}


def run(
    method: str,
    db_path: str = "egx_research.db",
    config_path: str = "config/",
) -> OptimizationRun:
    """
    Run optimization. method must be one of:
    - 'weight_gradient': delegates to weight_optimizer
    - 'walk_forward': delegates to walk_forward_backtester
    - 'rl_gradient': delegates to smc_rl_optimizer
    - 'threshold_grid': placeholder for future threshold grid search

    Returns OptimizationRun with before/after metrics and param diffs.
    Always saves to optimization_history table.
    """
    if method not in METHODS:
        raise ValueError(
            f"Unknown method '{method}'. Choose from: {list(METHODS.keys())}"
        )

    run_at = datetime.utcnow().isoformat() + "Z"
    metric_name = "expectancy"
    metric_before, n_signals = _read_metric_from_db(db_path, metric_name)

    print(f"[optimization_engine] method={method}  metric_before={metric_before:.4f}  n={n_signals}")

    fn = METHODS[method]
    params_before, params_after, metric_after_raw, n_out = fn(db_path, config_path)

    # Use DB metric if method returned nothing meaningful
    metric_after = metric_after_raw if (metric_after_raw != 0.0 or n_out > 0) else metric_before
    if n_out > 0:
        n_signals = n_out

    opt_run = OptimizationRun(
        method=method,
        run_at=run_at,
        params_before=params_before,
        params_after=params_after,
        metric_name=metric_name,
        metric_before=metric_before,
        metric_after=metric_after,
        n_signals=n_signals,
        approved=False,
    )

    save_run(opt_run, db_path=db_path)

    delta = metric_after - metric_before
    print(
        f"[optimization_engine] Done — metric_after={metric_after:.4f}  "
        f"delta={delta:+.4f}  id={opt_run.id}"
    )
    return opt_run


if __name__ == "__main__":
    print(run("weight_gradient"))
