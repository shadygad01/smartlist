"""
Validation Engine — Layer 7.
Mandatory gate before production promotion.
Runs train/validation/OOS split; stores every result to validation_runs table.
"""
import sqlite3
import json
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

DB_PATH = "egx_research.db"

# ── Data class ─────────────────────────────────────────────────────────────────

@dataclass
class ValidationResult:
    split_type: str           # 'time_split' | 'walk_forward' | 'oos'
    train_wr: float           # win rate on training window
    val_wr: float             # win rate on validation window
    oos_wr: float             # win rate on out-of-sample window
    train_sharpe: float
    val_sharpe: float
    oos_sharpe: float
    overfit_flag: bool
    robustness_score: float   # 0–1
    verdict: str              # 'APPROVED' | 'REJECTED' | 'FURTHER_RESEARCH'
    n_train: int = 0
    n_val: int = 0
    n_oos: int = 0
    id: Optional[int] = None


# ── DB helpers ─────────────────────────────────────────────────────────────────

def save_result(result: ValidationResult, db_path: str = DB_PATH) -> int:
    conn = sqlite3.connect(db_path)
    cur = conn.execute(
        """INSERT INTO validation_runs
           (run_at, split_type, train_wr, val_wr, oos_wr,
            train_sharpe, val_sharpe, oos_sharpe,
            overfit_flag, robustness_score, verdict)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            datetime.now().isoformat(), result.split_type,
            result.train_wr, result.val_wr, result.oos_wr,
            result.train_sharpe, result.val_sharpe, result.oos_sharpe,
            int(result.overfit_flag), result.robustness_score, result.verdict,
        ),
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    result.id = row_id
    return row_id


def get_latest(db_path: str = DB_PATH) -> Optional[ValidationResult]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM validation_runs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    if not row:
        return None
    return ValidationResult(
        split_type=row["split_type"] or "time_split",
        train_wr=row["train_wr"] or 0.0,
        val_wr=row["val_wr"] or 0.0,
        oos_wr=row["oos_wr"] or 0.0,
        train_sharpe=row["train_sharpe"] or 0.0,
        val_sharpe=row["val_sharpe"] or 0.0,
        oos_sharpe=row["oos_sharpe"] or 0.0,
        overfit_flag=bool(row["overfit_flag"]),
        robustness_score=row["robustness_score"] or 0.0,
        verdict=row["verdict"] or "FURTHER_RESEARCH",
        id=row["id"],
    )


# ── Core logic ─────────────────────────────────────────────────────────────────

def _load_signals_with_outcomes(db_path: str):
    """
    Load signals that have computed bottom_quality outcomes.
    Returns list of dicts sorted by signal_date ascending.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT s.signal_date, s.adj_score, s.symbol,
                  bq.r20d, bq.mfe_20d, bq.mae_20d, bq.bq_score
           FROM signals s
           JOIN bottom_quality bq ON s.id = bq.signal_id
           WHERE bq.r20d IS NOT NULL
           ORDER BY s.signal_date ASC"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _win_rate(signals: list, win_thresh: float = 0.07) -> float:
    if not signals:
        return 0.0
    wins = sum(1 for s in signals if (s.get("r20d") or 0) >= win_thresh)
    return wins / len(signals)


def _sharpe(signals: list) -> float:
    """Approximate annualised Sharpe using 20-day returns."""
    returns = [s.get("r20d") or 0.0 for s in signals]
    if len(returns) < 2:
        return 0.0
    n = len(returns)
    mean_r = sum(returns) / n
    var_r  = sum((r - mean_r) ** 2 for r in returns) / (n - 1)
    std_r  = math.sqrt(var_r) if var_r > 0 else 1e-9
    # annualise: ~13 non-overlapping 20-day periods per year
    return (mean_r / std_r) * math.sqrt(13)


def approve(result: ValidationResult) -> bool:
    """
    APPROVED when:
    - val_sharpe >= train_sharpe * 0.7  (not severely overfit)
    - oos_wr >= 0.40                     (minimum live win rate)
    - overfit_flag is False
    """
    if result.overfit_flag:
        return False
    if result.n_val < 10 or result.n_oos < 10:
        return False
    sharpe_ok = (result.val_sharpe >= result.train_sharpe * 0.70) or (result.train_sharpe <= 0)
    wr_ok     = result.oos_wr >= 0.40
    return sharpe_ok and wr_ok


def _verdict(result: ValidationResult) -> str:
    total_n = result.n_train + result.n_val + result.n_oos
    if total_n < 30:
        return "FURTHER_RESEARCH"
    if approve(result):
        return "APPROVED"
    return "REJECTED"


def run_train_val_oos(db_path: str = DB_PATH, config: dict = None) -> ValidationResult:
    """
    Chronological 60/20/20 split of all signals with measured outcomes.
    Computes win_rate and Sharpe per split; saves result to validation_runs.
    """
    win_thresh = 0.07
    if config and "win_thresh_r20d" in config:
        win_thresh = config["win_thresh_r20d"]

    signals = _load_signals_with_outcomes(db_path)
    n = len(signals)

    if n < 10:
        result = ValidationResult(
            split_type="time_split",
            train_wr=0.0, val_wr=0.0, oos_wr=0.0,
            train_sharpe=0.0, val_sharpe=0.0, oos_sharpe=0.0,
            overfit_flag=False, robustness_score=0.0,
            verdict="FURTHER_RESEARCH",
            n_train=n, n_val=0, n_oos=0,
        )
        save_result(result, db_path)
        return result

    i_val = int(n * 0.60)
    i_oos = int(n * 0.80)

    train = signals[:i_val]
    val   = signals[i_val:i_oos]
    oos   = signals[i_oos:]

    train_wr  = _win_rate(train, win_thresh)
    val_wr    = _win_rate(val,   win_thresh)
    oos_wr    = _win_rate(oos,   win_thresh)
    train_sh  = _sharpe(train)
    val_sh    = _sharpe(val)
    oos_sh    = _sharpe(oos)

    overfit = (train_wr - val_wr) > 0.15

    # robustness: average of (val_wr/train_wr) and (oos_wr/train_wr), capped 0–1
    rob_val = (val_wr / train_wr) if train_wr > 0 else 0.0
    rob_oos = (oos_wr / train_wr) if train_wr > 0 else 0.0
    robustness = min(1.0, (rob_val + rob_oos) / 2)

    result = ValidationResult(
        split_type="time_split",
        train_wr=round(train_wr, 4),
        val_wr=round(val_wr, 4),
        oos_wr=round(oos_wr, 4),
        train_sharpe=round(train_sh, 4),
        val_sharpe=round(val_sh, 4),
        oos_sharpe=round(oos_sh, 4),
        overfit_flag=overfit,
        robustness_score=round(robustness, 4),
        verdict="",
        n_train=len(train), n_val=len(val), n_oos=len(oos),
    )
    result.verdict = _verdict(result)
    save_result(result, db_path)
    return result


def run_robustness_checks(result: ValidationResult) -> dict:
    """
    Structural robustness checks on a ValidationResult.
    Does not re-run the backtest — evaluates the already-computed metrics.
    """
    checks = {}

    # Check 1: val performance relative to train
    if result.train_wr > 0:
        checks["val_retention_pct"] = round(result.val_wr / result.train_wr * 100, 1)
    else:
        checks["val_retention_pct"] = None

    # Check 2: OOS performance relative to train
    if result.train_wr > 0:
        checks["oos_retention_pct"] = round(result.oos_wr / result.train_wr * 100, 1)
    else:
        checks["oos_retention_pct"] = None

    # Check 3: Sharpe consistency
    checks["sharpe_decay_val"] = round(result.val_sharpe - result.train_sharpe, 4)
    checks["sharpe_decay_oos"] = round(result.oos_sharpe - result.train_sharpe, 4)

    # Check 4: Sample adequacy
    checks["n_oos_adequate"] = result.n_oos >= 30
    checks["n_val_adequate"] = result.n_val >= 30

    # Check 5: Pass/Fail per check
    checks["verdict"] = result.verdict
    checks["overfit_flag"] = result.overfit_flag

    return checks


# ── Entry point ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import pprint
    result = run_train_val_oos()
    pprint.pprint({
        "verdict":          result.verdict,
        "train_wr":         result.train_wr,
        "val_wr":           result.val_wr,
        "oos_wr":           result.oos_wr,
        "train_sharpe":     result.train_sharpe,
        "val_sharpe":       result.val_sharpe,
        "oos_sharpe":       result.oos_sharpe,
        "overfit_flag":     result.overfit_flag,
        "robustness_score": result.robustness_score,
        "n":                f"{result.n_train}/{result.n_val}/{result.n_oos}",
    })
    pprint.pprint(run_robustness_checks(result))
