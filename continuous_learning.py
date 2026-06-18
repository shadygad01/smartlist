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
except (ImportError, BaseException):
    try:
        import drift_lab as _drift_lab
    except (ImportError, BaseException):
        _drift_lab = None

try:
    from labs import factor_lab as _factor_lab
except (ImportError, BaseException):
    try:
        import factor_lab as _factor_lab
    except (ImportError, BaseException):
        _factor_lab = None

try:
    from labs import regime_lab as _regime_lab
except (ImportError, BaseException):
    try:
        import regime_lab as _regime_lab
    except (ImportError, BaseException):
        _regime_lab = None

MEMORY_FILE = "gx_learning_memory.json"
MIN_OUTCOMES_PER_CYCLE = 10
MIN_HOURS_BETWEEN_CYCLES = 24
MAX_PROMOTIONS_PER_DAY = 3          # circuit breaker
AUTO_ROLLBACK_DEGRADATION = 0.10    # rollback if OOS WR drops > 10pp


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
            "best_approved_oos_wr": 0.0,
        }
        if os.path.exists(self.path):
            try:
                with open(self.path) as f:
                    data = json.load(f)
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
            "best_approved_oos_wr": self._data.get("best_approved_oos_wr", 0.0),
            "recent_cycles": self.get_recent(5),
        }

    def get_best_oos_wr(self) -> float:
        return float(self._data.get("best_approved_oos_wr", 0.0))

    def update_best_oos_wr(self, oos_wr: float) -> None:
        if oos_wr > self.get_best_oos_wr():
            self._data["best_approved_oos_wr"] = round(oos_wr, 6)
            self._save()

    def get_recent_promotions_count(self, hours: float = 24.0) -> int:
        """Count promotions recorded within the last N hours."""
        from datetime import timedelta
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        return sum(
            1 for c in self._data.get("cycles", [])
            if c.get("promoted") and (c.get("recorded_at") or "0") >= cutoff
        )

    @property
    def last_cycle_at(self) -> Optional[str]:
        return self._data.get("last_cycle_at")


# ── Helpers ────────────────────────────────────────────────────────────────────

def reconcile_from_deployment_log(
    db_path: str = "egx_research.db",
    memory: Optional["LearningMemory"] = None,
) -> int:
    """
    Sync gx_learning_memory.json from deployment_log (authoritative promotion record).
    Adds synthetic cycle entries for PROMOTE actions not already tracked in memory.
    Returns the number of entries reconciled.
    """
    if memory is None:
        memory = LearningMemory()

    tracked_ids: set = set()
    for cycle in memory._data.get("cycles", []):
        dlid = cycle.get("deployment_log_id")
        if dlid is not None:
            tracked_ids.add(int(dlid))

    try:
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            """SELECT id, deployed_at, triggered_by, note
               FROM deployment_log
               WHERE action = 'PROMOTE'
               ORDER BY id ASC"""
        ).fetchall()
        conn.close()
    except Exception:
        return 0

    reconciled = 0
    for row_id, ts, triggered_by, note in rows:
        if int(row_id) in tracked_ids:
            continue
        synthetic = {
            "started_at": ts,
            "finished_at": ts,
            "recorded_at": ts,
            "outcomes_processed": 0,
            "labs_run": [],
            "drift_detected": False,
            "optimized": True,
            "promoted": True,
            "verdict": "APPROVED",
            "deployment_log_id": row_id,
            "triggered_by": triggered_by or "unknown",
            "note": note or "",
            "reconciled": True,
            "dry_run": False,
        }
        memory._data["cycles"].append(synthetic)
        memory._data["total_cycles"] = memory._data.get("total_cycles", 0) + 1
        reconciled += 1

    if reconciled > 0:
        # Set last_cycle_at to most recent promotion timestamp
        all_promo_times = [
            c.get("recorded_at", c.get("finished_at", ""))
            for c in memory._data["cycles"]
            if c.get("promoted")
        ]
        if all_promo_times:
            memory._data["last_cycle_at"] = max(t for t in all_promo_times if t)
        memory._save()

    return reconciled


def _count_new_outcomes(db_path: str, since: Optional[str]) -> int:
    """
    Count bottom_quality rows with r20d filled.
    When `since` is provided, counts signals whose signal_date falls after
    (since minus 40 days) — capturing outcomes that matured since the last cycle.
    Uses signal_date from joined signals table since bottom_quality has no updated_at.
    """
    try:
        conn = sqlite3.connect(db_path)
        try:
            if since:
                # Approximate: signals dated >= (last_cycle - 40d) whose 20d outcome is now filled
                from datetime import datetime, timedelta
                try:
                    last_dt = datetime.fromisoformat(since)
                    cutoff = (last_dt - timedelta(days=40)).strftime("%Y-%m-%d")
                except Exception:
                    cutoff = "2000-01-01"
                row = conn.execute(
                    """SELECT COUNT(*) FROM bottom_quality bq
                       JOIN signals s ON s.id = bq.signal_id
                       WHERE bq.r20d IS NOT NULL
                         AND s.signal_date >= ?""",
                    (cutoff,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) FROM bottom_quality WHERE r20d IS NOT NULL"
                ).fetchone()
            return row[0] if row else 0
        except Exception:
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
    """Run factor_lab and regime_lab; persist findings to KB; return combined dict."""
    improvements = {}

    # Check KB for factors to skip (already confirmed/recently tested)
    skip = set()
    try:
        from knowledge_base import get_kb
        kb = get_kb()
        skip = set(kb.skip_factors())
        if skip:
            print(f"  [KB] Skipping previously settled factors: {skip}")
    except Exception:
        kb = None

    if _factor_lab and hasattr(_factor_lab, "run"):
        try:
            result = _factor_lab.run(db_path=db_path)
            improvements["factor"] = result
            # Persist weight suggestions as factor findings
            if kb and result.get("weight_suggestions") and not result.get("error"):
                ws = result["weight_suggestions"]
                if isinstance(ws, dict):
                    items = ws.items()
                elif hasattr(ws, "__iter__"):
                    items = [(k, v) for k, v in ws] if ws else []
                else:
                    items = []
                for factor, data in items:
                    if factor in skip:
                        continue
                    if isinstance(data, dict):
                        change = data.get("change", 0)
                        verdict = "POSITIVE" if change > 0 else ("NEGATIVE" if change < 0 else "NEUTRAL")
                        kb.record_factor(factor, {
                            "sample_n": result.get("n_signals", 0),
                            "verdict": verdict,
                            "avg_importance": data.get("reason", ""),
                            "suggested_weight": data.get("suggested"),
                            "current_weight": data.get("current"),
                        }, source="factor_lab")
        except Exception as e:
            improvements["factor"] = {"error": str(e), "n_signals": 0}

    if _regime_lab and hasattr(_regime_lab, "run"):
        try:
            result = _regime_lab.run(db_path=db_path)
            improvements["regime"] = result
            # Persist regime findings
            if kb and result.get("n_signals", 0) > 0 and not result.get("error"):
                kb.record_regime("latest", {
                    "n_signals": result.get("n_signals"),
                    "behavior": result.get("behavior", {}),
                }, source="regime_lab")
        except Exception as e:
            improvements["regime"] = {"error": str(e), "n_signals": 0}

    # Backfill any KB entries that have verdicts but no suggested_weight yet
    if kb:
        try:
            cfg_file = os.path.join("config", "weights.json")
            if os.path.exists(cfg_file):
                with open(cfg_file, encoding="utf-8") as _f:
                    _cfg_w = json.load(_f)
                kb.backfill_suggested_weights(_cfg_w)
        except Exception:
            pass

    return improvements


def _run_optimization(db_path: str, config_dir: str,
                      lab_improvements: Optional[dict] = None) -> Optional[dict]:
    """Run optimization engine; blend KB weight suggestions; return proposed artifacts."""
    if not _optimizer or not hasattr(_optimizer, "run"):
        return None
    try:
        opt_run = _optimizer.run(
            method="expectancy_gradient",
            db_path=db_path,
            config_path=config_dir,
        )
        weights = dict(opt_run.params_after)

        # Blend KB-confirmed factor suggestions into proposed weights
        try:
            from knowledge_base import get_kb
            kb = get_kb()
            ff = kb.get_all_factors()
            for factor, finding in ff.items():
                sw = finding.get("suggested_weight")
                if sw is not None and factor in weights:
                    # Blend: 70% optimizer + 30% KB suggestion
                    weights[factor] = round(weights[factor] * 0.70 + float(sw) * 0.30, 2)
        except Exception:
            pass

        return {
            "weights": weights,
            "optimization_run_id": opt_run.id,
            "metric_before": opt_run.metric_before,
            "metric_after": opt_run.metric_after,
        }
    except Exception:
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
        # Circuit breaker: stop if too many promotions happened in last 24h
        recent_promo_count = memory.get_recent_promotions_count(hours=24)
        if recent_promo_count >= MAX_PROMOTIONS_PER_DAY:
            cycle_result["verdict"] = "CIRCUIT_BREAKER"
            cycle_result["circuit_breaker_reason"] = (
                f"{recent_promo_count} promotions in last 24h (max={MAX_PROMOTIONS_PER_DAY})"
            )
            return cycle_result

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
        if not lab_improvements:
            cycle_result["verdict"] = "LABS_UNAVAILABLE"

        # Step 4: optimization
        proposed = _run_optimization(db_path, config_dir, lab_improvements)
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

        # Capture metrics for cycle record and auto-rollback logic
        current_oos_wr = getattr(val_result, "oos_wr", 0.0) or 0.0
        cycle_result["val_oos_wr"] = current_oos_wr
        cycle_result["val_oos_sharpe"] = getattr(val_result, "oos_sharpe", 0.0) or 0.0
        cycle_result["val_n_oos"] = getattr(val_result, "n_oos", 0) or 0

        # Auto-rollback: if metrics degraded > threshold vs best known baseline
        best_oos_wr = memory.get_best_oos_wr()
        if (
            verdict == "REJECTED"
            and not dry_run
            and _promoter
            and best_oos_wr > 0
            and (best_oos_wr - current_oos_wr) > AUTO_ROLLBACK_DEGRADATION
        ):
            try:
                rb_id = _promoter.rollback(db_path=db_path, config_dir=config_dir)
                cycle_result["auto_rolled_back"] = True
                cycle_result["rollback_log_id"] = rb_id
                cycle_result["rollback_reason"] = (
                    f"OOS WR degraded {best_oos_wr:.4f}→{current_oos_wr:.4f} "
                    f"(threshold={AUTO_ROLLBACK_DEGRADATION})"
                )
            except Exception as e:
                cycle_result["rollback_error"] = str(e)

        # Step 6: promote if approved and circuit breaker allows
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
                memory.update_best_oos_wr(current_oos_wr)
            except Exception as e:
                cycle_result["promotion_error"] = str(e)
        elif verdict == "APPROVED":
            # Update best baseline even in dry_run (metrics are real)
            memory.update_best_oos_wr(current_oos_wr)
            if dry_run:
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
    reconcile_from_deployment_log(db_path=db_path, memory=memory)
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
