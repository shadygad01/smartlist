"""
Incremental Processing + Smart Invalidation + Learning Cache
Wraps all intelligence/report modules with hash-based skip logic.

Usage:
    python cache_orchestrator.py --mode intelligence   # job C modules
    python cache_orchestrator.py --mode research       # job B modules
    python cache_orchestrator.py --symbols             # emit changed_symbols.json

Env:
    FULL_REBUILD=true   — ignore cache, recompute everything
"""

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

# ── Constants ─────────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent
CACHE_DIR = ROOT / "cache_metadata"
CACHE_DIR.mkdir(exist_ok=True)

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
NOW_ISO = datetime.now(timezone.utc).isoformat()
FULL_REBUILD = os.environ.get("FULL_REBUILD", "false").lower() == "true"

# ── Module registry ───────────────────────────────────────────────────────────
# category A: always run (handled by workflow directly — not in this registry)
# category B: conditional — run only if tracked inputs changed
# category C: learning cache — additional min_interval_hours guard

MODULES = {
    # ── Category C: Learning Cache ────────────────────────────────────────────
    "rule_discovery": {
        "category": "C",
        "cmd": ["python", "rule_discovery.py"],
        "inputs": ["egx_research.db"],
        "outputs": ["edge_discovery_results.json"],
        "min_interval_hours": 6,
    },
    "edge_report": {
        "category": "C",
        "cmd": ["python", "edge_report.py"],
        "inputs": ["edge_discovery_results.json"],
        "outputs": [],
        "min_interval_hours": 6,
        "depends_on": ["rule_discovery"],
    },
    "behavior_report": {
        "category": "C",
        "cmd": ["python", "behavior_report.py"],
        "inputs": ["egx_research.db"],
        "outputs": ["behavior_report.html"],
        "min_interval_hours": 6,
    },
    "logic_analyzer": {
        "category": "C",
        "cmd": ["python", "logic_analyzer.py"],
        "inputs": ["egx_research.db"],
        "outputs": ["logic_analysis_results.json"],
        "min_interval_hours": 6,
    },
    "weight_optimizer": {
        "category": "C",
        "cmd": ["python", "weight_optimizer.py"],
        "inputs": ["egx_research.db"],
        "outputs": ["optimization_results.json"],
        "min_interval_hours": 6,
    },
    "system_audit": {
        "category": "C",
        "cmd": ["python", "system_audit.py"],
        "inputs": ["egx_research.db"],
        "outputs": ["system_audit_results.json"],
        "min_interval_hours": 6,
    },
    "adaptive_learning": {
        "category": "C",
        "cmd": ["python", "adaptive_learning.py"],
        "inputs": ["egx_research.db"],
        "outputs": ["adaptive_learning_results.json"],
        "min_interval_hours": 6,
    },
    "backtest_analysis": {
        "category": "C",
        "cmd": ["python", "backtest_analysis.py"],
        "inputs": ["egx_research.db"],
        "outputs": ["backtest_report.json"],
        "min_interval_hours": 6,
    },
    "gx_learning_layer": {
        "category": "C",
        "cmd": ["python", "gx_learning_layer.py"],
        "inputs": [
            "backtest_report.json",
            "research_results.json",
            "logic_analysis_results.json",
            "optimization_results.json",
            "edge_discovery_results.json",
            "system_audit_results.json",
            "adaptive_learning_results.json",
            "historical_backtest_results.json",
            "gx_learning_memory.json",
        ],
        "outputs": ["gx_learning_memory.json"],
        "min_interval_hours": 6,
        "depends_on": [
            "rule_discovery", "logic_analyzer", "weight_optimizer",
            "system_audit", "adaptive_learning", "backtest_analysis",
        ],
    },
    "decision_engine": {
        "category": "C",
        "cmd": ["python", "decision_engine.py"],
        "inputs": [
            "egx_research.db",
            "logic_analysis_results.json",
            "optimization_results.json",
            "adaptive_learning_results.json",
        ],
        "outputs": ["decision_engine_results.json"],
        "min_interval_hours": 4,
        "depends_on": ["logic_analyzer", "weight_optimizer", "adaptive_learning"],
    },
    "discount_zone_miner": {
        "category": "C",
        "cmd": ["python", "discount_zone_miner.py"],
        "inputs": ["egx_research.db", "discount_zone_patterns.json"],
        "outputs": ["discount_zone_patterns.json"],
        "min_interval_hours": 4,
    },

    # ── Category B: Conditional ───────────────────────────────────────────────
    "heatmap": {
        "category": "B",
        "cmd": ["python", "heatmap.py"],
        "inputs": ["signal_history.json"],
        "outputs": [],
    },
    "research_report": {
        "category": "B",
        "cmd": ["python", "research_report.py", "--no-email", "--force"],
        "inputs": ["egx_research.db", "scan_results.json"],
        "outputs": ["research_results.json"],
    },
    "quant_research_report": {
        "category": "B",
        "cmd": ["python", "quant_research_report.py"],
        "inputs": ["egx_research.db", "research_results.json"],
        "outputs": [],
        "depends_on": ["research_report"],
    },
}

# Modules that belong to the intelligence job (C)
# Tier 1: fully independent — run in parallel
INTELLIGENCE_TIER1 = [
    "rule_discovery", "behavior_report", "logic_analyzer",
    "weight_optimizer", "system_audit", "adaptive_learning",
    "backtest_analysis",
]
# Tier 2: depend on tier-1 outputs — run sequentially
# edge_report must follow rule_discovery; gx_learning/decision/discount follow tier-1 results
INTELLIGENCE_TIER2 = [
    "edge_report",
    "gx_learning_layer",
    "decision_engine",
    "discount_zone_miner",
]

# Modules that belong to the research job (B)
RESEARCH_MODULES = ["heatmap", "research_report", "quant_research_report"]

# ── Hash helpers ──────────────────────────────────────────────────────────────

def _hash_file(path: Path) -> str:
    """SHA256 of file content; for .db files use row-count + mtime combo."""
    if not path.exists():
        return "missing"
    if path.suffix == ".db":
        try:
            mtime = int(path.stat().st_mtime)
            conn = sqlite3.connect(str(path))
            counts = []
            for (tbl,) in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall():
                (n,) = conn.execute(f"SELECT COUNT(*) FROM [{tbl}]").fetchone()
                counts.append(f"{tbl}:{n}")
            conn.close()
            payload = f"{mtime}|{'|'.join(sorted(counts))}"
            return hashlib.sha256(payload.encode()).hexdigest()[:16]
        except Exception:
            return hashlib.sha256(str(path.stat().st_mtime).encode()).hexdigest()[:16]
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
    except OSError:
        return "unreadable"
    return h.hexdigest()[:16]


def compute_input_hash(module_name: str) -> str:
    """Combined hash of all declared input files for a module."""
    defn = MODULES[module_name]
    parts = []
    for fname in defn.get("inputs", []):
        h = _hash_file(ROOT / fname)
        parts.append(f"{fname}={h}")
    combined = "|".join(parts)
    return hashlib.sha256(combined.encode()).hexdigest()[:20]


# ── Metadata store ────────────────────────────────────────────────────────────

def meta_path(module_name: str) -> Path:
    return CACHE_DIR / f"{module_name}.json"


def load_meta(module_name: str) -> dict:
    p = meta_path(module_name)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return {}


def save_meta(module_name: str, meta: dict) -> None:
    meta_path(module_name).write_text(json.dumps(meta, indent=2))


def _detect_symbols() -> list[str]:
    p = ROOT / "scan_results.json"
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text())
        return sorted(data.keys())
    except Exception:
        return []


# ── Cache decision ────────────────────────────────────────────────────────────

def should_run(module_name: str, forced_modules: set[str] | None = None) -> tuple[bool, str]:
    """
    Returns (run_it, reason).
    Checks: FULL_REBUILD → forced set → output existence → hash → interval.
    """
    if FULL_REBUILD:
        return True, "FULL_REBUILD"

    if forced_modules and module_name in forced_modules:
        return True, "forced-dependency-changed"

    defn = MODULES[module_name]
    meta = load_meta(module_name)

    # Always run if declared output files are missing
    for out in defn.get("outputs", []):
        if not (ROOT / out).exists():
            return True, f"output-missing:{out}"

    # Hash comparison
    current_hash = compute_input_hash(module_name)
    if meta.get("input_hash") != current_hash:
        return True, "input-changed"

    # Minimum interval guard (category C only)
    if defn.get("category") == "C":
        min_h = defn.get("min_interval_hours", 0)
        last_run = meta.get("completed_at")
        if last_run and min_h > 0:
            elapsed = (
                datetime.now(timezone.utc)
                - datetime.fromisoformat(last_run)
            ).total_seconds() / 3600
            if elapsed < min_h:
                return False, f"interval-guard:{elapsed:.1f}h<{min_h}h"

    if meta.get("input_hash") == current_hash:
        return False, "cache-hit"

    return True, "unknown"


# ── Execution ─────────────────────────────────────────────────────────────────

def run_module(module_name: str) -> dict:
    """Run one module, time it, write metadata, return result dict."""
    defn = MODULES[module_name]
    t0 = time.time()
    print(f"[CACHE] RUN  {module_name}", flush=True)
    try:
        result = subprocess.run(
            defn["cmd"],
            cwd=ROOT,
            capture_output=False,
            text=True,
        )
        ok = result.returncode == 0
    except Exception as exc:
        print(f"[CACHE] ERROR {module_name}: {exc}", flush=True)
        ok = False

    elapsed = time.time() - t0
    current_hash = compute_input_hash(module_name)

    meta = {
        "report_name": module_name,
        "generated_at": NOW_ISO,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "input_hash": current_hash,
        "source_files": defn.get("inputs", []),
        "data_timestamp": TODAY,
        "ok": ok,
        "elapsed_seconds": round(elapsed, 1),
    }
    save_meta(module_name, meta)

    status = "ok" if ok else "error"
    print(f"[CACHE] {status.upper()} {module_name} ({elapsed:.0f}s)", flush=True)
    return {"module": module_name, "ran": True, "ok": ok, "elapsed": elapsed}


def skip_module(module_name: str, reason: str) -> dict:
    print(f"[CACHE] SKIP {module_name} ({reason})", flush=True)
    return {"module": module_name, "ran": False, "ok": True, "reason": reason}


# ── Symbol-level change detection ────────────────────────────────────────────

def emit_changed_symbols() -> None:
    prev_path = CACHE_DIR / "previous_symbols.json"
    current = set(_detect_symbols())
    previous = set(json.loads(prev_path.read_text()) if prev_path.exists() else [])

    result = {
        "generated_at": NOW_ISO,
        "added": sorted(current - previous),
        "removed": sorted(previous - current),
        "modified": [],  # populated below via scan_results hash changes
        "unchanged": sorted(current & previous),
    }

    # Detect modified symbols by comparing per-symbol hash in scan_results
    sr_path = ROOT / "scan_results.json"
    prev_hash_path = CACHE_DIR / "scan_results_per_symbol.json"
    if sr_path.exists():
        try:
            current_data = json.loads(sr_path.read_text())
            prev_hashes = json.loads(prev_hash_path.read_text()) if prev_hash_path.exists() else {}
            new_hashes = {}
            for sym, val in current_data.items():
                h = hashlib.sha256(json.dumps(val, sort_keys=True).encode()).hexdigest()[:12]
                new_hashes[sym] = h
                if sym in prev_hashes and prev_hashes[sym] != h:
                    result["modified"].append(sym)
            prev_hash_path.write_text(json.dumps(new_hashes, indent=2))
        except Exception:
            pass

    (ROOT / "changed_symbols.json").write_text(json.dumps(result, indent=2))
    prev_path.write_text(json.dumps(sorted(current), indent=2))

    added = len(result["added"])
    removed = len(result["removed"])
    modified = len(result["modified"])
    print(
        f"[CACHE] symbols: +{added} -{removed} ~{modified} "
        f"unchanged={len(result['unchanged'])}",
        flush=True,
    )


# ── Parallel tier runner ──────────────────────────────────────────────────────

def run_tier(module_names: list[str], forced: set[str]) -> list[dict]:
    """Run a list of modules in parallel (ThreadPoolExecutor). Returns results."""
    results = []
    tasks = {}

    with ThreadPoolExecutor(max_workers=len(module_names) or 1) as pool:
        for name in module_names:
            run_it, reason = should_run(name, forced)
            if run_it:
                tasks[pool.submit(run_module, name)] = name
            else:
                results.append(skip_module(name, reason))

        for future in as_completed(tasks):
            results.append(future.result())

    return results


# ── Report generation ─────────────────────────────────────────────────────────

def write_execution_report(results: list[dict], t_start: float) -> None:
    ran = [r for r in results if r["ran"]]
    skipped = [r for r in results if not r["ran"]]
    ok = [r for r in ran if r.get("ok")]
    total_ran_time = sum(r.get("elapsed", 0) for r in ran)
    # Rough estimate: assume skipped modules would each take 60s on average
    time_saved = len(skipped) * 60
    cache_hit_rate = len(skipped) / len(results) if results else 0

    report = {
        "generated_at": NOW_ISO,
        "wall_clock_seconds": round(time.time() - t_start, 1),
        "modules_executed": [r["module"] for r in ran],
        "modules_skipped": [r["module"] for r in skipped],
        "modules_failed": [r["module"] for r in ran if not r.get("ok")],
        "execution_time_saved_seconds": time_saved,
        "cache_hit_rate": round(cache_hit_rate, 3),
        "total_ran_time_seconds": round(total_ran_time, 1),
        "full_rebuild": FULL_REBUILD,
    }
    out = ROOT / "incremental_execution_report.json"
    out.write_text(json.dumps(report, indent=2))
    print(
        f"\n[CACHE] Execution report: "
        f"{len(ran)} ran / {len(skipped)} skipped / "
        f"cache_hit={cache_hit_rate:.0%} / "
        f"time_saved≈{time_saved//60}min",
        flush=True,
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["intelligence", "research", "all"],
        default="all",
    )
    parser.add_argument(
        "--symbols",
        action="store_true",
        help="Emit changed_symbols.json and exit",
    )
    args = parser.parse_args()

    if args.symbols:
        emit_changed_symbols()
        return

    t_start = time.time()
    all_results: list[dict] = []

    if args.mode in ("intelligence", "all"):
        print("\n[CACHE] === Tier 1 (parallel) ===", flush=True)
        forced: set[str] = set()
        tier1_results = run_tier(INTELLIGENCE_TIER1, forced)
        all_results.extend(tier1_results)

        # Propagate: if a dependency ran, force its dependents
        ran_names = {r["module"] for r in tier1_results if r["ran"]}
        forced_t2: set[str] = set()
        for name in INTELLIGENCE_TIER2:
            deps = set(MODULES[name].get("depends_on", []))
            if deps & ran_names:
                forced_t2.add(name)

        print("\n[CACHE] === Tier 2 (sequential) ===", flush=True)
        for name in INTELLIGENCE_TIER2:
            run_it, reason = should_run(name, forced_t2)
            if run_it:
                all_results.append(run_module(name))
            else:
                all_results.append(skip_module(name, reason))

    if args.mode in ("research", "all"):
        print("\n[CACHE] === Research (parallel) ===", flush=True)
        all_results.extend(run_tier(RESEARCH_MODULES, set()))

    write_execution_report(all_results, t_start)


if __name__ == "__main__":
    main()
