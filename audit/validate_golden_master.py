"""
Golden Master Validator — Constitutional Cleanup Phase 1
Compares current DB state against golden master snapshots.
Exits 0 if all checks pass, 1 on any failure.
"""
from __future__ import annotations
import hashlib, json, sqlite3, sys
from pathlib import Path

BASE   = Path(__file__).parent.parent
GOLDEN = Path(__file__).parent / "golden_master"

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"

failures = []

def sha256(path: Path) -> str:
    if not path.exists():
        return "FILE_NOT_FOUND"
    return hashlib.sha256(path.read_bytes()).hexdigest()

def check(label: str, ok: bool, detail: str = ""):
    status = PASS if ok else FAIL
    print(f"  [{status}] {label}" + (f" — {detail}" if detail else ""))
    if not ok:
        failures.append(f"{label}: {detail}")

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

golden_hashes = json.loads((GOLDEN / "hashes.json").read_text())
timeline_sem  = json.loads((GOLDEN / "timeline_semantic.json").read_text())

print("\n=== CONSTITUTIONAL GOLDEN MASTER VALIDATION ===\n")

# ── Hash checks (static DBs only — not append-only event stores) ──────────────
print("DB HASH CHECKS:")
hash_dbs = [
    "candidate_pool.db",
    "constitutional_buy_registry.db",
]
for db in hash_dbs:
    current = sha256(BASE / db)
    expected = golden_hashes.get(db, "MISSING")
    check(db, current == expected, f"current={current[:16]}… expected={expected[:16]}…")

# ── Universe check ───────────────────────────────────────────────────────────
print("\nUNIVERSE CHECK:")
golden_universe = json.loads((GOLDEN / "universe_27.json").read_text())
current_universe = qdb(BASE / "universe_snapshot.db",
    "SELECT ticker,status,current_price,entry_zone,reason,r2_score,final_score,return_pct FROM universe_snapshot ORDER BY ticker")

check("Universe size", len(current_universe) == len(golden_universe),
      f"{len(current_universe)} vs {len(golden_universe)}")

golden_by_ticker = {r["ticker"]: r for r in golden_universe}
current_by_ticker = {r["ticker"]: r for r in current_universe}
for ticker in sorted(golden_by_ticker):
    if ticker not in current_by_ticker:
        check(f"  {ticker} present", False, "MISSING from current")
        continue
    g = golden_by_ticker[ticker]
    c = current_by_ticker[ticker]
    check(f"  {ticker} status", g["status"] == c["status"],
          f"'{g['status']}' vs '{c['status']}'")

# ── FIRST BUY registry ───────────────────────────────────────────────────────
print("\nFIRST BUY REGISTRY CHECK:")
golden_fb = json.loads((GOLDEN / "first_buy_registry.json").read_text())
current_fb = qdb(BASE / "constitutional_buy_registry.db",
    "SELECT ticker,buy_date,buy_price,buy_r2,buy_score FROM constitutional_buy_registry ORDER BY ticker,buy_date")
check("FIRST BUY count", len(current_fb) == len(golden_fb),
      f"{len(current_fb)} vs {len(golden_fb)}")

# ── Candidate pool ───────────────────────────────────────────────────────────
print("\nCANDIDATE POOL CHECK:")
golden_pool = json.loads((GOLDEN / "candidate_pool_full.json").read_text())
current_pool = qdb(BASE / "candidate_pool.db",
    "SELECT ticker,signal_date,r2_score,final_score,entry_price,current_price,snapshot_ts FROM candidate_pool ORDER BY ticker,signal_date")
check("Candidate pool row count", len(current_pool) == len(golden_pool),
      f"{len(current_pool)} vs {len(golden_pool)}")

golden_pass = [r for r in golden_pool if (r["r2_score"] or 0) >= 60 and (r["final_score"] or 0) >= 35]
current_pass = [r for r in current_pool if (r["r2_score"] or 0) >= 60 and (r["final_score"] or 0) >= 35]
check("Constitutional pass rows", len(current_pass) == len(golden_pass),
      f"{len(current_pass)} vs {len(golden_pass)}")

# ── DNA ───────────────────────────────────────────────────────────────────────
print("\nDNA CHECK:")
golden_dna = json.loads((GOLDEN / "stock_dna.json").read_text())
current_dna = qdb(BASE / "stock_dna.db", "SELECT * FROM stock_dna ORDER BY ticker")
check("DNA row count", len(current_dna) == len(golden_dna),
      f"{len(current_dna)} vs {len(golden_dna)}")

# ── Timeline: semantic validation ─────────────────────────────────────────────
# Binary hash validation removed. Semantic invariants are resilient to VACUUM,
# index rebuilds, data normalization, append-only inserts, historical imports,
# and migrations. Violations indicate data corruption or logic errors.
print("\nTIMELINE CHECK (SEMANTIC):")

COE_DB = BASE / "constitutional_opportunity_events.db"

golden_tl = json.loads((GOLDEN / "timeline.json").read_text())
current_tl = qdb(COE_DB,
    "SELECT * FROM constitutional_opportunity_events ORDER BY ticker, event_date")

# Row count: total must match golden snapshot exactly
check("Timeline row count", len(current_tl) == len(golden_tl),
      f"{len(current_tl)} vs {len(golden_tl)}")

# Minimum floor counts (append-only: can only grow)
total_rows = scalar(COE_DB, "SELECT COUNT(*) FROM constitutional_opportunity_events")
v1_count   = scalar(COE_DB, "SELECT COUNT(*) FROM constitutional_opportunity_events WHERE signal_version='v1'")
wf1_count  = scalar(COE_DB, "SELECT COUNT(*) FROM constitutional_opportunity_events WHERE signal_version='wf_v1'")
check("timeline:total_rows_min",
      (total_rows or 0) >= timeline_sem["total_rows_min"],
      f"{total_rows} >= {timeline_sem['total_rows_min']}")
check("timeline:v1_count_min",
      (v1_count or 0) >= timeline_sem["v1_count_min"],
      f"{v1_count} >= {timeline_sem['v1_count_min']}")
check("timeline:wf_v1_count_min",
      (wf1_count or 0) >= timeline_sem["wf_v1_count_min"],
      f"{wf1_count} >= {timeline_sem['wf_v1_count_min']}")

# Structural integrity: no duplicates
dup_ids = scalar(COE_DB,
    "SELECT COUNT(*) FROM (SELECT event_id, COUNT(*) c FROM constitutional_opportunity_events GROUP BY event_id HAVING c>1)")
check("timeline:no_duplicate_event_ids", (dup_ids or 0) == 0,
      f"duplicate event_ids={dup_ids}")

dup_ttd = scalar(COE_DB,
    "SELECT COUNT(*) FROM (SELECT ticker,event_type,event_date,COUNT(*) c FROM constitutional_opportunity_events GROUP BY ticker,event_type,event_date HAVING c>1)")
check("timeline:no_duplicate_ticker_type_date", (dup_ttd or 0) == 0,
      f"duplicate (ticker,type,date)={dup_ttd}")

# Constitutional threshold: all signals qualified at R2>=60, score>=35
thresh_violations = scalar(COE_DB,
    "SELECT COUNT(*) FROM constitutional_opportunity_events WHERE buy_r2 < 60 OR buy_score < 35")
check("timeline:constitutional_threshold", (thresh_violations or 0) == 0,
      f"threshold violations={thresh_violations}")

# Ordering integrity: event_date must not be after event_end_date
order_violations = scalar(COE_DB,
    "SELECT COUNT(*) FROM constitutional_opportunity_events WHERE event_date > event_end_date")
check("timeline:event_date_order", (order_violations or 0) == 0,
      f"ordering violations={order_violations}")

# UNIQUE INDEX must be present
if COE_DB.exists():
    conn = sqlite3.connect(str(COE_DB))
    idx_names = [r[1] for r in conn.execute("PRAGMA index_list(constitutional_opportunity_events)").fetchall()]
    conn.close()
    check("timeline:unique_index_exists", "ux_coe_ticker_type_date" in idx_names,
          f"indexes={idx_names}")
else:
    check("timeline:unique_index_exists", False, "DB_NOT_FOUND")

# v1 golden event_ids: all must be present (append-only, never deleted)
if COE_DB.exists():
    conn = sqlite3.connect(str(COE_DB))
    current_ids = {r[0] for r in conn.execute(
        "SELECT event_id FROM constitutional_opportunity_events WHERE signal_version='v1'"
    ).fetchall()}
    conn.close()
    golden_ids  = set(timeline_sem["v1_event_ids"])
    missing_ids = sorted(golden_ids - current_ids)
    check("timeline:v1_event_ids_preserved", len(missing_ids) == 0,
          f"missing={missing_ids or 'none'}")
else:
    check("timeline:v1_event_ids_preserved", False, "DB_NOT_FOUND")

# v1 cluster_days consistency: must equal calendar span (end - start + 1)
v1_cd_bad = scalar(COE_DB, """
    SELECT COUNT(*) FROM constitutional_opportunity_events
    WHERE signal_version='v1'
      AND cluster_days != (CAST(julianday(event_end_date) - julianday(event_date) AS INTEGER) + 1)
""")
check("timeline:v1_cluster_days_consistent", (v1_cd_bad or 0) == 0,
      f"mismatched cluster_days={v1_cd_bad}")

# ── Summary ───────────────────────────────────────────────────────────────────
print(f"\n{'='*50}")
if failures:
    print(f"RESULT: FAIL — {len(failures)} check(s) failed:")
    for f in failures:
        print(f"  ✗ {f}")
    sys.exit(1)
else:
    print("RESULT: ALL CHECKS PASS — Golden master validated.")
    sys.exit(0)
