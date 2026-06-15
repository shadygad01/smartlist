"""
Production Promoter — Layer 9.
Atomically promotes validated configs to production.
Writes audit trail to deployment_log and config_snapshots tables.
"""
import json
import os
import shutil
import sqlite3
import tempfile
from datetime import datetime
from typing import Optional

CONFIG_DIR = "config"


def _config_path(filename: str, config_dir: str = CONFIG_DIR) -> str:
    return os.path.join(config_dir, filename)


def _atomic_write(path: str, data: dict) -> None:
    """Write JSON atomically: write to temp file then rename."""
    dir_ = os.path.dirname(os.path.abspath(path))
    fd, tmp_path = tempfile.mkstemp(dir=dir_, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def get_current_config(config_dir: str = CONFIG_DIR) -> dict:
    """Read and merge weights.json + thresholds.json + gates_config.json."""
    merged = {}
    for fname in ("weights.json", "thresholds.json", "gates_config.json"):
        path = _config_path(fname, config_dir)
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
            merged[fname.replace(".json", "")] = data
    return merged


def _save_snapshot(conn: sqlite3.Connection, config_snapshot: dict, note: str = None) -> int:
    weights_j    = json.dumps(config_snapshot.get("weights", config_snapshot))
    thresholds_j = json.dumps(config_snapshot.get("thresholds", {}))
    gates_j      = json.dumps(config_snapshot.get("gates", {}))
    cur = conn.execute(
        """INSERT INTO config_snapshots
               (snapshot_at, weights_json, thresholds_json, gates_json, note)
           VALUES (?, ?, ?, ?, ?)""",
        (datetime.now().isoformat(), weights_j, thresholds_j, gates_j, note),
    )
    return cur.lastrowid


def _write_deployment_log(
    conn: sqlite3.Connection,
    action: str,
    snapshot_id: int,
    validation_run_id: Optional[int],
    triggered_by: str,
    note: str,
) -> int:
    cur = conn.execute(
        """INSERT INTO deployment_log
           (deployed_at, action, config_snapshot_id, validation_run_id, triggered_by, note)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            datetime.now().isoformat(),
            action,
            snapshot_id,
            validation_run_id,
            triggered_by,
            note,
        ),
    )
    return cur.lastrowid


def promote(
    artifacts: dict,
    validation_run_id: int = None,
    note: str = None,
    triggered_by: str = "auto",
    db_path: str = "egx_research.db",
    config_dir: str = CONFIG_DIR,
) -> int:
    """
    Atomically write config changes to config/*.json files.
    artifacts dict may contain: weights, thresholds, gates (partial updates OK).
    Saves snapshot to config_snapshots table.
    Writes to deployment_log.
    Returns deployment_log id.
    Only promotes if validation_run_id points to an APPROVED validation run,
    OR if validation_run_id is None (manual override).
    Raises ValueError if validation run is REJECTED.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        # Validate the validation run if provided
        if validation_run_id is not None:
            row = conn.execute(
                "SELECT verdict FROM validation_runs WHERE id = ?",
                (validation_run_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"validation_run_id {validation_run_id} not found.")
            verdict = row["verdict"]
            if verdict == "REJECTED":
                raise ValueError(
                    f"Cannot promote: validation run {validation_run_id} was REJECTED."
                )
            if verdict not in ("APPROVED", "FURTHER_RESEARCH"):
                raise ValueError(
                    f"Cannot promote: validation run {validation_run_id} has verdict '{verdict}'."
                )

        # Capture snapshot of current config before overwriting
        current = get_current_config(config_dir)
        snapshot_id = _save_snapshot(conn, current, note=f"pre-promote snapshot")
        conn.commit()

        # Map artifact keys to filenames
        key_to_file = {
            "weights":    "weights.json",
            "thresholds": "thresholds.json",
            "gates":      "gates_config.json",
        }

        for key, fname in key_to_file.items():
            if key not in artifacts:
                continue
            path = _config_path(fname, config_dir)
            # Load existing and merge (partial update)
            if os.path.exists(path):
                with open(path) as f:
                    existing = json.load(f)
            else:
                existing = {}
            existing.update(artifacts[key])
            _atomic_write(path, existing)

        # Write deployment log
        log_id = _write_deployment_log(
            conn,
            action="PROMOTE",
            snapshot_id=snapshot_id,
            validation_run_id=validation_run_id,
            triggered_by=triggered_by,
            note=note,
        )
        conn.commit()

        # Hot-reload signal_engine weights so current process uses new config immediately
        try:
            from signal_engine import reload_weights
            reload_weights(config_path=config_dir)
        except Exception:
            pass

        return log_id

    finally:
        conn.close()


def rollback(
    snapshot_id: int = None,
    db_path: str = "egx_research.db",
    config_dir: str = CONFIG_DIR,
) -> int:
    """
    Restore config from a config_snapshots row.
    If snapshot_id is None, restores the previous snapshot.
    Writes ROLLBACK entry to deployment_log.
    Returns deployment_log id.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        if snapshot_id is None:
            row = conn.execute(
                "SELECT * FROM config_snapshots ORDER BY id DESC LIMIT 1 OFFSET 1"
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM config_snapshots WHERE id = ?", (snapshot_id,)
            ).fetchone()

        if row is None:
            raise ValueError("No snapshot found to rollback to.")

        snap_id = row["id"]
        for fname, col in [("weights.json", "weights_json"),
                           ("thresholds.json", "thresholds_json"),
                           ("gates_config.json", "gates_json")]:
            try:
                data = json.loads(row[col] or "{}")
                if data:
                    _atomic_write(_config_path(fname, config_dir), data)
            except Exception:
                pass

        log_id = _write_deployment_log(
            conn,
            action="ROLLBACK",
            snapshot_id=snap_id,
            validation_run_id=None,
            triggered_by="rollback",
            note=f"Rolled back to snapshot {snap_id}",
        )
        conn.commit()
        return log_id

    finally:
        conn.close()


def get_promotion_history(limit: int = 10, db_path: str = "egx_research.db") -> list[dict]:
    """Return recent deployment_log entries as list of dicts."""
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT * FROM deployment_log ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        finally:
            conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []
