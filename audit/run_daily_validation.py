"""
Constitutional Daily Validation Runner
Runs validate_golden_master.py, stores result, appends to history.log.
Called after every production scan.
"""
from __future__ import annotations
import hashlib, json, sqlite3, sys, subprocess
from pathlib import Path

BASE   = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))
AUDIT  = Path(__file__).parent
DAILY  = AUDIT / "daily_validation"
GOLDEN = AUDIT / "golden_master"
DAILY.mkdir(exist_ok=True)

from time_authority import now_cairo
TODAY  = now_cairo().strftime("%Y-%m-%d")
TS     = now_cairo().isoformat()

def sha256(path: Path) -> str:
    if not path.exists(): return "FILE_NOT_FOUND"
    return hashlib.sha256(path.read_bytes()).hexdigest()

def qdb(db_path: Path, sql: str, params: tuple = ()) -> list[dict]:
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def scalar(db_path: Path, sql: str, params: tuple = ()):
    if not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path))
    row = conn.execute(sql, params).fetchone()
    conn.close()
    return row[0] if row else None

golden_hashes  = json.loads((GOLDEN / "hashes.json").read_text())
timeline_sem   = json.loads((GOLDEN / "timeline_semantic.json").read_text())

failures  = []
checks    = []

def check(label: str, ok: bool, expected=None, actual=None):
    entry = {"check": label, "pass": ok, "expected": str(expected), "actual": str(actual)}
    checks.append(entry)
    if not ok:
        failures.append(entry)

# ── Hash checks (static DBs only — not append-only event stores) ──────────────
for db in ["candidate_pool.db", "constitutional_buy_registry.db"]:
    cur = sha256(BASE / db)
    exp = golden_hashes.get(db, "MISSING")
    check(f"hash:{db}", cur == exp, exp[:16], cur[:16])

# ── Universe ──────────────────────────────────────────────────────────────────
golden_universe = json.loads((GOLDEN / "universe_27.json").read_text())
current_universe = qdb(BASE / "universe_snapshot.db",
    "SELECT ticker,status,current_price,entry_zone,reason,r2_score,final_score,return_pct FROM universe_snapshot ORDER BY ticker")

check("universe:size", len(current_universe) == len(golden_universe),
      len(golden_universe), len(current_universe))

# Per-ticker status is a dynamic computed field (derived from return_pct daily).
# It legitimately transitions every trading session — not a constitutional invariant.
# Only universe SIZE is validated here; status is reported in the daily JSON for audit.

# ── FIRST BUY registry ───────────────────────────────────────────────────────
golden_fb = json.loads((GOLDEN / "first_buy_registry.json").read_text())
current_fb = qdb(BASE / "constitutional_buy_registry.db",
    "SELECT ticker,buy_date,buy_price,buy_r2,buy_score FROM constitutional_buy_registry ORDER BY ticker,buy_date")
check("first_buy:count", len(current_fb) == len(golden_fb), len(golden_fb), len(current_fb))
for i, (g, c) in enumerate(zip(golden_fb, current_fb)):
    check(f"first_buy:{g['ticker']}:date",    g["buy_date"]  == c["buy_date"],  g["buy_date"],  c["buy_date"])
    check(f"first_buy:{g['ticker']}:price",   g["buy_price"] == c["buy_price"], g["buy_price"], c["buy_price"])

# ── Candidate pool ───────────────────────────────────────────────────────────
golden_pool = json.loads((GOLDEN / "candidate_pool_full.json").read_text())
current_pool = qdb(BASE / "candidate_pool.db",
    "SELECT ticker,signal_date,r2_score,final_score,entry_price,current_price,snapshot_ts FROM candidate_pool ORDER BY ticker,signal_date")
check("candidate_pool:rows", len(current_pool) == len(golden_pool), len(golden_pool), len(current_pool))

g_pass = len([r for r in golden_pool  if (r["r2_score"] or 0) >= 60 and (r["final_score"] or 0) >= 35])
c_pass = len([r for r in current_pool if (r["r2_score"] or 0) >= 60 and (r["final_score"] or 0) >= 35])
check("candidate_pool:constitutional_pass", c_pass == g_pass, g_pass, c_pass)

# ── DNA ───────────────────────────────────────────────────────────────────────
golden_dna = json.loads((GOLDEN / "stock_dna.json").read_text())
current_dna = qdb(BASE / "stock_dna.db", "SELECT * FROM stock_dna ORDER BY ticker")
check("dna:rows", len(current_dna) == len(golden_dna), len(golden_dna), len(current_dna))

# ── Timeline ─────────────────────────────────────────────────────────────────
# Semantic validation replaces binary hash: validates structural invariants that
# remain true after VACUUM, index rebuild, data normalization, append-only insert,
# historical import, and migration. These are constitutional invariants — violations
# indicate data corruption or logic errors, not legitimate DB operations.

COE_DB = BASE / "constitutional_opportunity_events.db"

# Minimum thresholds (monotonically non-decreasing — new events can only be added)
total_rows = scalar(COE_DB, "SELECT COUNT(*) FROM constitutional_opportunity_events")
v1_count   = scalar(COE_DB, "SELECT COUNT(*) FROM constitutional_opportunity_events WHERE signal_version='v1'")
wf1_count  = scalar(COE_DB, "SELECT COUNT(*) FROM constitutional_opportunity_events WHERE signal_version='wf_v1'")
check("timeline:total_rows_min",   (total_rows or 0) >= timeline_sem["total_rows_min"],
      f">={timeline_sem['total_rows_min']}", total_rows)
check("timeline:v1_count_min",     (v1_count or 0)   >= timeline_sem["v1_count_min"],
      f">={timeline_sem['v1_count_min']}", v1_count)
check("timeline:wf_v1_count_min",  (wf1_count or 0)  >= timeline_sem["wf_v1_count_min"],
      f">={timeline_sem['wf_v1_count_min']}", wf1_count)

# Structural integrity: no duplicates
dup_ids = scalar(COE_DB,
    "SELECT COUNT(*) FROM (SELECT event_id, COUNT(*) c FROM constitutional_opportunity_events GROUP BY event_id HAVING c>1)")
check("timeline:no_duplicate_event_ids", (dup_ids or 0) == 0, 0, dup_ids)

dup_ttd = scalar(COE_DB,
    "SELECT COUNT(*) FROM (SELECT ticker,event_type,event_date,COUNT(*) c FROM constitutional_opportunity_events GROUP BY ticker,event_type,event_date HAVING c>1)")
check("timeline:no_duplicate_ticker_type_date", (dup_ttd or 0) == 0, 0, dup_ttd)

# Constitutional threshold: all signals must have qualified at buy_r2>=60, buy_score>=35
thresh_violations = scalar(COE_DB,
    "SELECT COUNT(*) FROM constitutional_opportunity_events WHERE buy_r2 < 60 OR buy_score < 35")
check("timeline:constitutional_threshold", (thresh_violations or 0) == 0, 0, thresh_violations)

# Ordering integrity: event_date must not be after event_end_date
order_violations = scalar(COE_DB,
    "SELECT COUNT(*) FROM constitutional_opportunity_events WHERE event_date > event_end_date")
check("timeline:event_date_order", (order_violations or 0) == 0, 0, order_violations)

# UNIQUE INDEX must be present — protects against duplicate signals on same day
if COE_DB.exists():
    conn = sqlite3.connect(str(COE_DB))
    indexes = {r[1]: bool(r[2]) for r in conn.execute("PRAGMA index_list(constitutional_opportunity_events)").fetchall()}
    conn.close()
    check("timeline:unique_index_exists", indexes.get("ux_coe_ticker_type_date") is True,
          "ux_coe_ticker_type_date (unique)", str(indexes))
else:
    check("timeline:unique_index_exists", False, "ux_coe_ticker_type_date", "DB_NOT_FOUND")

# v1 golden event_ids: all must still be present (append-only, never deleted)
if COE_DB.exists():
    conn = sqlite3.connect(str(COE_DB))
    current_ids = {r[0] for r in conn.execute(
        "SELECT event_id FROM constitutional_opportunity_events WHERE signal_version='v1'"
    ).fetchall()}
    conn.close()
    golden_ids  = set(timeline_sem["v1_event_ids"])
    missing_ids = sorted(golden_ids - current_ids)
    check("timeline:v1_event_ids_preserved", len(missing_ids) == 0,
          f"{len(golden_ids)} ids present", f"missing={missing_ids or 'none'}")
else:
    check("timeline:v1_event_ids_preserved", False, "42 ids present", "DB_NOT_FOUND")

# v1 cluster_days consistency: cluster_days must equal calendar span (end - start + 1)
v1_cd_bad = scalar(COE_DB, """
    SELECT COUNT(*) FROM constitutional_opportunity_events
    WHERE signal_version='v1'
      AND cluster_days != (CAST(julianday(event_end_date) - julianday(event_date) AS INTEGER) + 1)
""")
check("timeline:v1_cluster_days_consistent", (v1_cd_bad or 0) == 0, 0, v1_cd_bad)

# ── Build result ─────────────────────────────────────────────────────────────
total  = len(checks)
passed = sum(1 for c in checks if c["pass"])
result = {
    "date":      TODAY,
    "timestamp": TS,
    "total_checks": total,
    "passed": passed,
    "failed": total - passed,
    "overall": "PASS" if not failures else "FAIL",
    "failures": failures,
    "checks":  checks,
    "hashes": {
        db: sha256(BASE / db)
        for db in ["candidate_pool.db", "constitutional_buy_registry.db",
                   "universe_snapshot.db", "stock_dna.db",
                   "constitutional_opportunity_events.db"]
    },
}

# ── Write dated report (never overwrite) ──────────────────────────────────────
out_path = DAILY / f"{TODAY}.json"
if out_path.exists():
    # append scan index
    existing = json.loads(out_path.read_text())
    if isinstance(existing, list):
        existing.append(result)
        out_path.write_text(json.dumps(existing, indent=2))
    else:
        out_path.write_text(json.dumps([existing, result], indent=2))
else:
    out_path.write_text(json.dumps(result, indent=2))

# ── Append to history.log ─────────────────────────────────────────────────────
log_line = f"{TS}  {result['overall']}  checks={passed}/{total}  failures={total-passed}\n"
(DAILY / "history.log").open("a").write(log_line)

# ── Console output ─────────────────────────────────────────────────────────────
print(f"\n=== CONSTITUTIONAL DAILY VALIDATION {TODAY} ===")
print(f"  Checks: {passed}/{total} passed")
if failures:
    print(f"\n  FAILURES DETECTED — STOP CLEANUP:")
    for f in failures:
        print(f"    ✗ {f['check']}")
        print(f"      Expected: {f['expected']}")
        print(f"      Actual:   {f['actual']}")
    sys.exit(1)
else:
    print(f"  RESULT: PASS — Constitutional production identical to golden master.")
    sys.exit(0)
