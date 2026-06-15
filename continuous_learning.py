"""
Continuous Learning Loop — Layer 10.
Orchestrates: scan → store → measure → research → optimize → validate → decide → deploy → monitor.
Merges gx_learning_layer, gx_research_memory, adaptive_learning.
"""
import json
import sqlite3
import os
from datetime import datetime
from typing import Optional

# Optional imports — may not be present in all environments
try:
    import gx_learning_layer as _gx_learning
except ImportError:
    _gx_learning = None

try:
    import gx_research_memory as _gx_memory
except ImportError:
    _gx_memory = None

try:
    import adaptive_learning as _adaptive
except ImportError:
    _adaptive = None

try:
    import validation_engine as _validation
except ImportError:
    _validation = None

try:
    import production_promoter as _promoter
except ImportError:
    _promoter = None

try:
    import optimization_engine as _optimizer
except ImportError:
    _optimizer = None

try:
    from labs import drift_lab as _drift_lab
except ImportError:
    try:
        import drift_lab as _drift_lab
    except ImportError:
        _drift_lab = None

try:
    from labs import factor_lab as _factor_lab
except ImportError:
    try:
        import factor_lab as _factor_lab
    except ImportError:
        _factor_lab = None

try:
    from labs import regime_lab as _regime_lab
except ImportError:
    try:
        import regime_lab as _regime_lab
    except ImportError:
        _regime_lab = None

MEMORY_FILE = "gx_learning_memory.json"
MIN_OUTCOMES_PER_CYCLE = 10
MIN_HOURS_BETWEEN_CYCLES = 24


# ── LearningMemory ─────────────────────────────────────────────────────────────

class LearningMemory:
    """Persistent learning memory wrapping gx_learning_memory.json."""

    def __init__(self, path: str = MEMORY_FILE):
        self.path = path
        self._data = self._load()

    def _load(self) -> dict:
        default = {
            "schema_version": 1,
            "created_at": datetime.now().isoformat(),
            "total_cycles": 0,
            "last_cycle_at": None,
            "cycles": [],
        }
        if os.path.exists(self.path):
            try:
                with open(self.path) as f:
                    data = json.load(f)
                # ensure required keys exist (migrate old format)
                for k, v in default.items():
                    data.setdefault(k, v)
                return data
            except Exception:
                pass
        return default

    def _save(self) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self.path)

    def record_cycle(self, cycle_result: dict) -> None:
        cycle_result.setdefault("recorded_at", datetime.now().isoformat())
        self._data["cycles"].append(cycle_result)
        self._data["total_cycles"] = self._data.get("total_cycles", 0) + 1
        self._data["last_cycle_at"] = cycle_result["recorded_at"]
        self._save()

    def get_recent(self, n: int = 10) -> list[dict]:
        return self._data.get("cycles", [])[-n:]

    def get_summary(self) -> dict:
        cycles = self._data.get("cycles", [])
        promoted = sum(1 for c in cycles if c.get("promoted"))
        return {
            "total_cycles": self._data.get("total_cycles", 0),
            "last_cycle_at": self._data.get("last_cycle_at"),
            "total_promoted": promoted,
            "recent_cycles": self.get_recent(5),
        }

    @property
    def last_cycle_at(self) -> Optional[str]:
        return self._data.get("last_cycle_at")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _count_new_outcomes(db_path: str, since: Optional[str]) -> int:
    """Count bottom_quality rows with r20d filled after `since` timestamp."""
    try:
        conn = sqlite3.connect(db_path)
        try:
            if since:
                row = conn.execute(
                    """SELECT COUNT(*) FROM bottom_quality
                       WHERE r20d IS NOT NULL
                         AND updated_at > ?""",
                    (since,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) FROM bottom_quality WHERE r20d IS NOT NULL"
                ).fetchone()
            return row[0] if row else 0
        except Exception:
            # Fallback: count all completed signals
            try:
                row = conn.execute(
                    "SELECT COUNT(*) FROM bottom_quality WHERE r20d IS NOT NULL"
                ).fetchone()
                return row[0] if row else 0
            except Exception:
                return 0
        finally:
            conn.close()
    except Exception:
        return 0


def _run_drift_lab(db_path: str) -> bool:
    """Return True if drift is detected."""
    if _drift_lab and hasattr(_drift_lab, "run"):
        try:
            result = _drift_lab.run(db_path=db_path)
            return bool(result.get("drift_detected", False))
        except Exception:
            pass
    # Numpy fallback: compare win rate of last 60 vs prior 60 signals
    try:
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            """SELECT bq.r20d FROM bottom_quality bq
               JOIN signals s ON s.id = bq.signal_id
               WHERE bq.r20d IS NOT NULL
               ORDER BY s.signal_date DESC LIMIT 120"""
        ).fetchall()
        conn.close()
        vals = [r[0] for r in rows]
        if len(vals) < 60:
            return False
        recent, prior = vals[:60], vals[60:]
        wr_recent = sum(1 for v in recent if v > 0.07) / 60
        wr_prior  = sum(1 for v in prior  if v > 0.07) / len(prior)
        return abs(wr_recent - wr_prior) > 0.10
    except Exception:
        return False


def _run_labs(db_path: str) -> dict:
    """Run factor_lab and regime_lab; return combined improvement dict."""
    improvements = {}
    if _factor_lab and hasattr(_factor_lab, "run"):
        try:
            improvements["factor"] = _factor_lab.run(db_path=db_path)
        except Exception:
            pass
    if _regime_lab and hasattr(_regime_lab, "run"):
        try:
            improvements["regime"] = _regime_lab.run(db_path=db_path)
        except Exception:
            pass
    return improvements


def _run_optimization(db_path: str, config_dir: str) -> Optional[dict]:
    """Run optimization engine; return proposed artifacts dict or None."""
    if _optimizer and hasattr(_optimizer, "run"):
        try:
            opt_run = _optimizer.run(
                method="expectancy_gradient",
                db_path=db_path,
                config_path=config_dir,
            )
            # Return artifacts dict with weights for validation/promotion
            return {
                "weights": opt_run.params_after,
                "optimization_run_id": opt_run.id,
                "metric_before": opt_run.metric_before,
                "metric_after": opt_run.metric_after,
            }
        except Exception:
            pass
    return None


def _run_validation(proposed_artifacts: dict, db_path: str) -> Optional[object]:
    """Run validation engine on proposed artifacts; return ValidationResult or None."""
    if _validation and hasattr(_validation, "run_train_val_oos"):
        try:
            config = proposed_artifacts.get("thresholds", {})
            return _validation.run_train_val_oos(db_path=db_path, config=config)
        except Exception:
            pass
    return None


# ── Core API ───────────────────────────────────────────────────────────────────

def run_learning_cycle(
    db_path: str = "egx_research.db",
    config_dir: str = "config/",
    dry_run: bool = False,
) -> dict:
    """
    Full learning cycle:
    1. Count new outcomes since last cycle
    2. If >= 10 new outcomes: run drift_lab
    3. If drift detected: run factor_lab, regime_lab
    4. If labs find improvement: run optimization_engine
    5. Run validation_engine on optimized config
    6. If APPROVED: run production_promoter.promote()
    7. Record cycle to LearningMemory
    Returns cycle_result dict with:
      outcomes_processed, labs_run, optimized, promoted, verdict
    """
    memory = LearningMemory()
    cycle_result: dict = {
        "started_at": datetime.now().isoformat(),
        "outcomes_processed": 0,
        "labs_run": [],
        "drift_detected": False,
        "optimized": False,
        "promoted": False,
        "verdict": None,
        "dry_run": dry_run,
        "error": None,
    }

    try:
        # Step 1: count new outcomes
        n_outcomes = _count_new_outcomes(db_path, memory.last_cycle_at)
        cycle_result["outcomes_processed"] = n_outcomes

        if n_outcomes < MIN_OUTCOMES_PER_CYCLE:
            cycle_result["verdict"] = "SKIPPED_INSUFFICIENT_OUTCOMES"
            return cycle_result

        # Step 2: drift detection (informational — does not gate research)
        drift = _run_drift_lab(db_path)
        cycle_result["labs_run"].append("drift_lab")
        cycle_result["drift_detected"] = drift

        # Step 3: factor + regime labs (always run; soft errors don't gate optimization)
        lab_improvements = _run_labs(db_path)
        cycle_result["labs_run"].extend(lab_improvements.keys())
        cycle_result["lab_results"] = {
            k: {"error": v.get("error"), "n_signals": v.get("n_signals")}
            for k, v in lab_improvements.items()
        }
        # Only skip optimization if ALL labs hard-failed (empty dict)
        if not lab_improvements:
            cycle_result["verdict"] = "LABS_UNAVAILABLE"
            # Still fall through to optimization — research state alone is sufficient

        # Step 4: optimization
        proposed = _run_optimization(db_path, config_dir)
        if proposed:
            cycle_result["optimized"] = True
        else:
            cycle_result["verdict"] = "OPTIMIZATION_FAILED"
            return cycle_result

        # Step 5: validation
        val_result = _run_validation(proposed, db_path)
        verdict = getattr(val_result, "verdict", None) if val_result else None
        cycle_result["verdict"] = verdict
        val_run_id = getattr(val_result, "id", None) if val_result else None

        # Step 6: promote if approved
        if verdict == "APPROVED" and not dry_run and _promoter:
            try:
                log_id = _promoter.promote(
                    artifacts=proposed,
                    validation_run_id=val_run_id,
                    note="auto-promoted by continuous_learning cycle",
                    triggered_by="continuous_learning",
                    db_path=db_path,
                    config_dir=config_dir,
                )
                cycle_result["promoted"] = True
                cycle_result["deployment_log_id"] = log_id
            except Exception as e:
                cycle_result["promotion_error"] = str(e)
        elif dry_run and verdict == "APPROVED":
            cycle_result["promoted"] = False
            cycle_result["dry_run_would_promote"] = True

    except Exception as e:
        cycle_result["error"] = str(e)
        cycle_result["verdict"] = "ERROR"

    finally:
        # Step 7: always record cycle (regardless of outcome)
        cycle_result["finished_at"] = datetime.now().isoformat()
        memory.record_cycle(cycle_result)
        try:
            from knowledge_base import get_kb
            get_kb().log_cycle(cycle_result)
        except Exception:
            pass

    return cycle_result


def schedule_daily(db_path: str = "egx_research.db") -> Optional[dict]:
    """
    Called from main.py daily_scan() after scan completes.
    Runs run_learning_cycle() only if conditions are met:
    - New outcomes available (>= 10)
    - Last cycle was > 24 hours ago
    Returns cycle_result dict if cycle ran, else None.
    """
    memory = LearningMemory()
    now = datetime.now()

    # Check time since last cycle
    if memory.last_cycle_at:
        try:
            last_dt = datetime.fromisoformat(memory.last_cycle_at)
            hours_elapsed = (now - last_dt).total_seconds() / 3600
            if hours_elapsed < MIN_HOURS_BETWEEN_CYCLES:
                return None
        except Exception:
            pass

    # Check if enough new outcomes exist
    n_outcomes = _count_new_outcomes(db_path, memory.last_cycle_at)
    if n_outcomes < MIN_OUTCOMES_PER_CYCLE:
        return None

    return run_learning_cycle(db_path=db_path)
