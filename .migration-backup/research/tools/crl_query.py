"""
CRL Query Tool — Constitutional Research Lab

Query the knowledge base, experiment registry, and backtest library.
Read-only. Never modifies production.
"""

import sqlite3
import json
from typing import Optional

KB_PATH = "research/knowledge/knowledge_base.db"


def query_findings(station: Optional[str] = None, confidence: Optional[str] = None) -> list[dict]:
    conn = sqlite3.connect(KB_PATH)
    sql = "SELECT * FROM findings WHERE 1=1"
    params = []
    if station:
        sql += " AND (research_id LIKE ? OR question LIKE ?)"
        params += [f"%{station}%", f"%{station}%"]
    if confidence:
        sql += " AND confidence = ?"
        params.append(confidence)
    rows = conn.execute(sql, params).fetchall()
    cols = [d[1] for d in conn.execute("PRAGMA table_info(findings)")]
    conn.close()
    return [dict(zip(cols, r)) for r in rows]


def query_station_knowledge(station: Optional[str] = None) -> list[dict]:
    conn = sqlite3.connect(KB_PATH)
    sql = "SELECT * FROM station_knowledge"
    params = []
    if station:
        sql += " WHERE station = ?"
        params.append(station)
    sql += " ORDER BY ABS(spearman_rho) DESC"
    rows = conn.execute(sql, params).fetchall()
    cols = [d[1] for d in conn.execute("PRAGMA table_info(station_knowledge)")]
    conn.close()
    return [dict(zip(cols, r)) for r in rows]


def query_experiments(status: Optional[str] = None) -> list[dict]:
    conn = sqlite3.connect(KB_PATH)
    sql = "SELECT * FROM experiment_registry"
    params = []
    if status:
        sql += " WHERE status = ?"
        params.append(status)
    sql += " ORDER BY created_at DESC"
    rows = conn.execute(sql, params).fetchall()
    cols = [d[1] for d in conn.execute("PRAGMA table_info(experiment_registry)")]
    conn.close()
    return [dict(zip(cols, r)) for r in rows]


def query_backtests() -> list[dict]:
    conn = sqlite3.connect(KB_PATH)
    rows = conn.execute("SELECT * FROM backtest_library ORDER BY recorded_at DESC").fetchall()
    cols = [d[1] for d in conn.execute("PRAGMA table_info(backtest_library)")]
    conn.close()
    return [dict(zip(cols, r)) for r in rows]


def add_finding(
    research_id: str,
    question: str,
    conclusion: str,
    confidence: str,
    dataset: str = "",
    method: str = "",
    evidence: dict = None,
    future_rec: str = "",
    related_files: str = "",
    status: str = "VERIFIED",
) -> None:
    from datetime import datetime
    conn = sqlite3.connect(KB_PATH)
    conn.execute(
        """INSERT OR IGNORE INTO findings
           (research_id, question, dataset, method, evidence, conclusion,
            confidence, future_rec, related_files, status, recorded_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (research_id, question, dataset, method,
         json.dumps(evidence or {}), conclusion, confidence,
         future_rec, related_files, status, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    print(f"Finding {research_id} recorded.")


def add_experiment(
    exp_id: str,
    title: str,
    question: str,
    status: str = "OPEN",
    **kwargs,
) -> None:
    from datetime import datetime
    conn = sqlite3.connect(KB_PATH)
    conn.execute(
        """INSERT OR IGNORE INTO experiment_registry
           (exp_id, title, question, dataset, method, evidence, result,
            confidence, recommendation, status, source_file, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (exp_id, title, question,
         kwargs.get("dataset", ""), kwargs.get("method", ""),
         kwargs.get("evidence", ""), kwargs.get("result", ""),
         kwargs.get("confidence", "LOW"), kwargs.get("recommendation", ""),
         status, kwargs.get("source_file", ""), datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    print(f"Experiment {exp_id} registered.")


def print_summary():
    conn = sqlite3.connect(KB_PATH)
    print("=== CRL Knowledge Base Summary ===")
    for table in ("findings", "station_knowledge", "experiment_registry", "backtest_library"):
        n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {n} rows")
    print()
    print("=== Station Knowledge (by |rho|) ===")
    rows = conn.execute(
        "SELECT station, metric, spearman_rho, verdict FROM station_knowledge "
        "ORDER BY ABS(spearman_rho) DESC"
    ).fetchall()
    for r in rows:
        print(f"  {r[0]:<8} {r[1]:<25} rho={r[2]:+.3f}  {r[3]}")
    print()
    print("=== Experiments by Status ===")
    rows = conn.execute(
        "SELECT status, COUNT(*) FROM experiment_registry GROUP BY status"
    ).fetchall()
    for r in rows:
        print(f"  {r[0]:<15} {r[1]}")
    conn.close()


if __name__ == "__main__":
    print_summary()
