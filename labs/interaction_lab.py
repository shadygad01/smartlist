"""
interaction_lab.py — Signal Interaction & Edge Discovery Lab
Delegates to edge_discovery, rule_discovery, discount_zone_miner, pattern_discovery.
"""

import json
import sqlite3
from datetime import datetime

try:
    import edge_discovery
    _HAS_EDGE_DISCOVERY = True
except Exception as e:
    _HAS_EDGE_DISCOVERY = False
    print(f"[warn] edge_discovery import failed: {e}")

try:
    import rule_discovery
    _HAS_RULE_DISCOVERY = True
except Exception as e:
    _HAS_RULE_DISCOVERY = False
    print(f"[warn] rule_discovery import failed: {e}")

try:
    import discount_zone_miner
    _HAS_DISCOUNT_MINER = True
except Exception as e:
    _HAS_DISCOUNT_MINER = False
    print(f"[warn] discount_zone_miner import failed: {e}")

try:
    import pattern_discovery
    _HAS_PATTERN_DISCOVERY = True
except Exception as e:
    _HAS_PATTERN_DISCOVERY = False
    print(f"[warn] pattern_discovery import failed: {e}")


def _log_experiment(db_path, lab, n_signals, result_dict, report_path=None):
    try:
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT OR IGNORE INTO experiment_log (lab, run_at, n_signals, result_json, report_path) VALUES (?,?,?,?,?)",
            (lab, datetime.now().isoformat(), n_signals, json.dumps(result_dict, default=str)[:10000], report_path)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[warn] experiment_log write failed: {e}")


def run(db_path="egx_research.db") -> dict:
    """Run interaction/edge discovery analysis by delegating to discovery modules."""
    result = {
        "edges": [],
        "rules": [],
        "discount_zone": {},
        "pattern_clusters": {},
        "n_signals": 0,
        "run_at": datetime.now().isoformat(),
    }

    n_signals = 0

    # Edge discovery
    if _HAS_EDGE_DISCOVERY:
        try:
            edges = edge_discovery.run_edge_discovery(db_path=db_path)
            result["edges"] = edges.get("edges", edges) if isinstance(edges, dict) else edges
            if isinstance(edges, dict):
                n_signals = max(n_signals, edges.get("n_signals", 0))
        except Exception as e:
            result["edges_error"] = str(e)
            print(f"[warn] edge_discovery failed: {e}")

    # Rule discovery
    if _HAS_RULE_DISCOVERY:
        try:
            rules = rule_discovery.run_rule_discovery(db_path=db_path, dry_run=True)
            result["rules"] = rules.get("rules", []) if isinstance(rules, dict) else []
            result["bottom_dna"] = rules.get("bottom_dna", {}) if isinstance(rules, dict) else {}
            if isinstance(rules, dict):
                n_signals = max(n_signals, rules.get("n_signals", 0))
        except Exception as e:
            result["rules_error"] = str(e)
            print(f"[warn] rule_discovery failed: {e}")

    # Discount zone miner
    if _HAS_DISCOUNT_MINER:
        try:
            disc = discount_zone_miner.run()
            result["discount_zone"] = disc if isinstance(disc, dict) else {"raw": str(disc)}
            if isinstance(disc, dict):
                n_signals = max(n_signals, disc.get("n_signals", disc.get("n_discount", 0)))
        except Exception as e:
            result["discount_zone_error"] = str(e)
            print(f"[warn] discount_zone_miner failed: {e}")

    # Pattern discovery
    if _HAS_PATTERN_DISCOVERY:
        try:
            patterns = pattern_discovery.run_pattern_discovery(db_path=db_path)
            result["pattern_clusters"] = patterns if isinstance(patterns, dict) else {"raw": str(patterns)}
            if isinstance(patterns, dict):
                n_signals = max(n_signals, patterns.get("n_signals", 0))
        except Exception as e:
            result["pattern_clusters_error"] = str(e)
            print(f"[warn] pattern_discovery failed: {e}")

    result["n_signals"] = n_signals
    _log_experiment(db_path, "interaction", n_signals, result)
    return result


if __name__ == "__main__":
    import sys
    print(run(sys.argv[1] if len(sys.argv) > 1 else "egx_research.db"))
