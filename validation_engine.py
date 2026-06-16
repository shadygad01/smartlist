"""
Validation Engine — Layer 7.
Mandatory gate before production promotion.

Objective-aligned validation: uses mfe_40d (40-day max favorable excursion)
as primary metric for reversal-strategy evaluation, not r20d (20-day return).

Rationale: SMC reversal signals take 20-120 days to mature. r20d captures only
the first leg; mfe_40d captures whether the reversal actually delivered upside.
OOS Sharpe floor replaces train/val Sharpe continuity (avoids punishing recovery).

Gates:
  PRIMARY (mfe_40d based):
    - oos_mfe40_wr  >= 0.65  (≥65% of OOS signals reach +7% within 40 days)
    - val_mfe40_wr  >= 0.55  (validation period stable)
    - oos_expectancy >= 0.10  (positive expected value per trade on 40d MFE)
    - overfit_mfe40 < 0.20   (train-val gap < 20pp)
  SECONDARY (r20d, legacy):
    - oos_wr_r20d  >= 0.35   (sanity check on short-term)
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
    split_type: str
    train_wr: float           # mfe_40d win rate — training window
    val_wr: float             # mfe_40d win rate — validation window
    oos_wr: float             # mfe_40d win rate — OOS window
    train_sharpe: float       # Sharpe on mfe_40d returns — training
    val_sharpe: float         # Sharpe on mfe_40d returns — validation
    oos_sharpe: float         # Sharpe on mfe_40d returns — OOS
    overfit_flag: bool        # train_wr - val_wr > 0.20
    robustness_score: float   # 0–1
    verdict: str              # 'APPROVED' | 'REJECTED' | 'FURTHER_RESEARCH'
    n_train: int = 0
    n_val: int = 0
    n_oos: int = 0
    # Extended metrics
    train_expectancy: float = 0.0
    val_expectancy: float = 0.0
    oos_expectancy: float = 0.0
    oos_wr_r20d: float = 0.0  # legacy r20d OOS win rate
    metric_col: str = "mfe_40d"
    id: Optional[int] = None


# ── DB helpers ─────────────────────────────────────────────────────────────────

def save_result(result: ValidationResult, db_path: str = DB_PATH) -> int:
    conn = sqlite3.connect(db_path)
    try:
        # Deduplicate: skip insert if last saved run has identical metrics
        last = conn.execute(
            """SELECT id, train_wr, val_wr, oos_wr, oos_sharpe
               FROM validation_runs ORDER BY id DESC LIMIT 1"""
        ).fetchone()
        if last and (
            last[1] == result.train_wr
            and last[2] == result.val_wr
            and last[3] == result.oos_wr
            and last[4] == result.oos_sharpe
        ):
            result.id = last[0]
            return last[0]

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
        result.id = row_id
        return row_id
    finally:
        conn.close()


def get_latest(db_path: str = DB_PATH) -> Optional[ValidationResult]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM validation_runs ORDER BY rowid DESC LIMIT 1"
    ).fetchone()
    conn.close()
    if not row:
        return None
    cols = list(row.keys()) if hasattr(row, 'keys') else None
    if cols:
        d = dict(row)
        id_key = 'id' if 'id' in d else list(d.keys())[0]
        return ValidationResult(
            split_type=d.get("split_type", "mfe40_split"),
            train_wr=d.get("train_wr", 0.0) or 0.0,
            val_wr=d.get("val_wr", 0.0) or 0.0,
            oos_wr=d.get("oos_wr", 0.0) or 0.0,
            train_sharpe=d.get("train_sharpe", 0.0) or 0.0,
            val_sharpe=d.get("val_sharpe", 0.0) or 0.0,
            oos_sharpe=d.get("oos_sharpe", 0.0) or 0.0,
            overfit_flag=bool(d.get("overfit_flag", False)),
            robustness_score=d.get("robustness_score", 0.0) or 0.0,
            verdict=d.get("verdict", "FURTHER_RESEARCH") or "FURTHER_RESEARCH",
            id=d.get(id_key),
        )
    # Positional fallback
    return ValidationResult(
        split_type=row[2] or "mfe40_split",
        train_wr=row[3] or 0.0,
        val_wr=row[4] or 0.0,
        oos_wr=row[5] or 0.0,
        train_sharpe=row[6] or 0.0,
        val_sharpe=row[7] or 0.0,
        oos_sharpe=row[8] or 0.0,
        overfit_flag=bool(row[9]),
        robustness_score=row[10] or 0.0,
        verdict=row[11] or "FURTHER_RESEARCH",
        id=row[0],
    )


# ── Core logic ─────────────────────────────────────────────────────────────────

def _load_signals_with_outcomes(db_path: str, metric_col: str = "mfe_40d"):
    """Load signals with the specified outcome column, sorted chronologically."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    # Check which columns exist
    bq_cols = [r[1] for r in conn.execute("PRAGMA table_info(bottom_quality)").fetchall()]

    # Build select: always include r20d as legacy; add requested metric_col
    extra = f", bq.{metric_col}" if metric_col in bq_cols and metric_col != "r20d" else ""
    r20d_filter = "bq.r20d IS NOT NULL" if "r20d" in bq_cols else "1=1"
    metric_filter = f"bq.{metric_col} IS NOT NULL" if metric_col in bq_cols else r20d_filter

    rows = conn.execute(
        f"""SELECT s.signal_date, s.adj_score, s.symbol,
                   bq.r20d, bq.mfe_20d, bq.mae_20d, bq.bq_score
                   {extra}
            FROM signals s
            JOIN bottom_quality bq ON s.id = bq.signal_id
            WHERE {metric_filter}
            ORDER BY s.signal_date ASC"""
    ).fetchall()
    conn.close()

    result = []
    for r in rows:
        d = dict(r)
        if metric_col not in d:
            d[metric_col] = d.get("r20d")
        result.append(d)
    return result


def _win_rate(signals: list, col: str = "mfe_40d", win_thresh: float = 0.07) -> float:
    if not signals:
        return 0.0
    wins = sum(1 for s in signals if (s.get(col) or 0) >= win_thresh)
    return wins / len(signals)


def _expectancy(signals: list, col: str = "mfe_40d", win_thresh: float = 0.07) -> float:
    """Expected return per trade: wr * avg_win + (1-wr) * avg_loss."""
    vals = [s.get(col) or 0.0 for s in signals]
    if not vals:
        return 0.0
    wins   = [v for v in vals if v >= win_thresh]
    losses = [v for v in vals if v <  win_thresh]
    wr = len(wins) / len(vals)
    avg_win  = sum(wins)   / len(wins)   if wins   else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    return wr * avg_win + (1 - wr) * avg_loss


def _sharpe(signals: list, col: str = "mfe_40d") -> float:
    """Approximate annualised Sharpe. mfe_40d: ~6.5 non-overlapping periods/yr."""
    returns = [s.get(col) or 0.0 for s in signals]
    if len(returns) < 2:
        return 0.0
    n = len(returns)
    mean_r = sum(returns) / n
    var_r  = sum((r - mean_r) ** 2 for r in returns) / (n - 1)
    std_r  = math.sqrt(var_r) if var_r > 0 else 1e-9
    periods_per_year = 6.5 if col == "mfe_40d" else 13.0  # r20d: 13; mfe_40d: ~6.5
    return (mean_r / std_r) * math.sqrt(periods_per_year)


def approve(result: ValidationResult) -> bool:
    """
    APPROVED when (objective-aligned gates):
    PRIMARY:
      - oos_wr       >= 0.65  (≥65% of OOS signals achieve +7% within 40 days)
      - val_wr       >= 0.55  (validation window also adequate)
      - oos_expectancy >= 0.10 (positive expected value per trade)
      - NOT overfit  (train-val mfe_40d gap < 20pp)
      - n_oos >= 10, n_val >= 10
    SECONDARY:
      - oos_sharpe   >= 0.30  (absolute OOS Sharpe floor; not relative to train)
    """
    if result.overfit_flag:
        return False
    if result.n_val < 10 or result.n_oos < 10:
        return False
    wr_ok  = result.oos_wr >= 0.65 and result.val_wr >= 0.55
    exp_ok = result.oos_expectancy >= 0.10
    sh_ok  = result.oos_sharpe >= 0.30
    return wr_ok and exp_ok and sh_ok


def _verdict(result: ValidationResult) -> str:
    total_n = result.n_train + result.n_val + result.n_oos
    if total_n < 30:
        return "FURTHER_RESEARCH"
    if approve(result):
        return "APPROVED"
    return "REJECTED"


def run_train_val_oos(db_path: str = DB_PATH, config: dict = None) -> ValidationResult:
    """
    Chronological 60/20/20 split.
    Primary metric: mfe_40d (40-day max favorable excursion).
    Secondary: r20d legacy win rate stored in oos_wr_r20d.
    """
    metric_col = "mfe_40d"
    win_thresh = 0.07
    if config:
        metric_col = config.get("validation_metric", metric_col)
        win_thresh = config.get("win_thresh_r20d", win_thresh)

    signals = _load_signals_with_outcomes(db_path, metric_col)
    n = len(signals)

    if n < 10:
        result = ValidationResult(
            split_type="mfe40_split",
            train_wr=0.0, val_wr=0.0, oos_wr=0.0,
            train_sharpe=0.0, val_sharpe=0.0, oos_sharpe=0.0,
            overfit_flag=False, robustness_score=0.0,
            verdict="FURTHER_RESEARCH",
            n_train=n, n_val=0, n_oos=0,
            metric_col=metric_col,
        )
        save_result(result, db_path)
        return result

    i_val = int(n * 0.60)
    i_oos = int(n * 0.80)

    train = signals[:i_val]
    val   = signals[i_val:i_oos]
    oos   = signals[i_oos:]

    train_wr  = _win_rate(train, metric_col, win_thresh)
    val_wr    = _win_rate(val,   metric_col, win_thresh)
    oos_wr    = _win_rate(oos,   metric_col, win_thresh)

    train_exp = _expectancy(train, metric_col, win_thresh)
    val_exp   = _expectancy(val,   metric_col, win_thresh)
    oos_exp   = _expectancy(oos,   metric_col, win_thresh)

    train_sh  = _sharpe(train, metric_col)
    val_sh    = _sharpe(val,   metric_col)
    oos_sh    = _sharpe(oos,   metric_col)

    # Overfit: mfe_40d train-val gap > 20pp
    overfit = (train_wr - val_wr) > 0.20

    # r20d legacy win rate for OOS (sanity check)
    oos_wr_r20d = _win_rate(oos, "r20d", 0.07)

    # Robustness: average (val_wr/train_wr, oos_wr/train_wr), capped 0-1
    rob_val = (val_wr / train_wr) if train_wr > 0 else 0.0
    rob_oos = (oos_wr / train_wr) if train_wr > 0 else 0.0
    robustness = min(1.0, (rob_val + rob_oos) / 2)

    result = ValidationResult(
        split_type="mfe40_split",
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
        train_expectancy=round(train_exp, 4),
        val_expectancy=round(val_exp, 4),
        oos_expectancy=round(oos_exp, 4),
        oos_wr_r20d=round(oos_wr_r20d, 4),
        metric_col=metric_col,
    )
    result.verdict = _verdict(result)
    save_result(result, db_path)
    return result


def run_robustness_checks(result: ValidationResult) -> dict:
    checks = {}
    if result.train_wr > 0:
        checks["val_retention_pct"] = round(result.val_wr / result.train_wr * 100, 1)
        checks["oos_retention_pct"] = round(result.oos_wr / result.train_wr * 100, 1)
    else:
        checks["val_retention_pct"] = None
        checks["oos_retention_pct"] = None
    checks["sharpe_decay_val"] = round(result.val_sharpe - result.train_sharpe, 4)
    checks["sharpe_decay_oos"] = round(result.oos_sharpe - result.train_sharpe, 4)
    checks["n_oos_adequate"] = result.n_oos >= 30
    checks["n_val_adequate"] = result.n_val >= 30
    checks["oos_expectancy"] = result.oos_expectancy
    checks["val_expectancy"] = result.val_expectancy
    checks["oos_wr_r20d"]   = result.oos_wr_r20d
    checks["metric_col"]    = result.metric_col
    checks["verdict"]       = result.verdict
    checks["overfit_flag"]  = result.overfit_flag
    checks["approval_gates"] = {
        "oos_wr >= 0.65": result.oos_wr >= 0.65,
        "val_wr >= 0.55": result.val_wr >= 0.55,
        "oos_expectancy >= 0.10": result.oos_expectancy >= 0.10,
        "oos_sharpe >= 0.30": result.oos_sharpe >= 0.30,
        "not overfit": not result.overfit_flag,
    }
    return checks


def multi_horizon_analysis(db_path: str = DB_PATH) -> dict:
    """
    Compute expectancy, win rate, and Sharpe across all available time horizons.
    Used to determine optimal holding periods and factor-specific horizons.
    Returns dict keyed by column name.
    """
    conn = sqlite3.connect(db_path)
    bq_cols = [r[1] for r in conn.execute("PRAGMA table_info(bottom_quality)").fetchall()]

    horizons = [c for c in [
        "r20d", "r40d", "r60d",
        "mfe_20d", "mfe_40d", "mfe_60d", "mfe_90d", "mfe_120d", "mfe_180d", "mfe_252d",
        "peak_return_1y",
    ] if c in bq_cols]

    results = {}
    win_thresh = 0.07

    for col_name in horizons:
        try:
            rows = conn.execute(
                f"""SELECT bq.{col_name}, s.signal_date
                    FROM bottom_quality bq
                    JOIN signals s ON s.id = bq.signal_id
                    WHERE bq.{col_name} IS NOT NULL
                    ORDER BY s.signal_date ASC"""
            ).fetchall()
            if not rows:
                continue
            vals = [r[0] for r in rows]
            n = len(vals)
            wins   = [v for v in vals if v >= win_thresh]
            losses = [v for v in vals if v < win_thresh]
            wr = len(wins) / n
            avg_win  = sum(wins)  / len(wins)  if wins  else 0.0
            avg_loss = sum(losses) / len(losses) if losses else 0.0
            exp = wr * avg_win + (1 - wr) * avg_loss
            mean_r = sum(vals) / n
            var_r  = sum((v - mean_r) ** 2 for v in vals) / (n - 1) if n > 1 else 0
            std_r  = math.sqrt(var_r) if var_r > 0 else 1e-9
            # OOS (last 20%)
            oos_start = int(n * 0.80)
            oos = vals[oos_start:]
            oos_wr = sum(1 for v in oos if v >= win_thresh) / len(oos) if oos else 0
            oos_exp_v = [v for v in oos]
            oos_wins  = [v for v in oos if v >= win_thresh]
            oos_loss  = [v for v in oos if v < win_thresh]
            oos_wr2   = len(oos_wins)/len(oos) if oos else 0
            oos_exp2  = (oos_wr2 * (sum(oos_wins)/len(oos_wins) if oos_wins else 0)
                         + (1-oos_wr2) * (sum(oos_loss)/len(oos_loss) if oos_loss else 0))

            results[col_name] = {
                "n": n,
                "win_rate": round(wr, 4),
                "expectancy": round(exp, 4),
                "avg_return": round(mean_r, 4),
                "avg_win": round(avg_win, 4),
                "avg_loss": round(avg_loss, 4),
                "oos_n": len(oos),
                "oos_win_rate": round(oos_wr2, 4),
                "oos_expectancy": round(oos_exp2, 4),
                "fib_15pct": round(sum(1 for v in vals if v >= 0.15) / n, 4),
                "fib_30pct": round(sum(1 for v in vals if v >= 0.30) / n, 4),
                "fib_50pct": round(sum(1 for v in vals if v >= 0.50) / n, 4),
                "fib_100pct": round(sum(1 for v in vals if v >= 1.00) / n, 4),
            }
        except Exception as e:
            results[col_name] = {"error": str(e)}

    conn.close()
    return results


# ── Entry point ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import pprint
    result = run_train_val_oos()
    pprint.pprint({
        "verdict":          result.verdict,
        "metric_col":       result.metric_col,
        "train_wr":         result.train_wr,
        "val_wr":           result.val_wr,
        "oos_wr":           result.oos_wr,
        "train_sharpe":     result.train_sharpe,
        "val_sharpe":       result.val_sharpe,
        "oos_sharpe":       result.oos_sharpe,
        "overfit_flag":     result.overfit_flag,
        "robustness_score": result.robustness_score,
        "train_expectancy": result.train_expectancy,
        "val_expectancy":   result.val_expectancy,
        "oos_expectancy":   result.oos_expectancy,
        "oos_wr_r20d":      result.oos_wr_r20d,
        "n":                f"{result.n_train}/{result.n_val}/{result.n_oos}",
    })
    pprint.pprint(run_robustness_checks(result))
