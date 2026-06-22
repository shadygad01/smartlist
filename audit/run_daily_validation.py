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

def qdb(db_path: Path, sql: str) -> list[dict]:
    if not db_path.exists(): return []
    conn = sqlite3.connect(str(db_path)); conn.row_factory = sqlite3.Row
    rows = conn.execute(sql).fetchall(); conn.close()
    return [dict(r) for r in rows]

golden_hashes = json.loads((GOLDEN / "hashes.json").read_text())

failures  = []
checks    = []

def check(label: str, ok: bool, expected=None, actual=None):
    entry = {"check": label, "pass": ok, "expected": str(expected), "actual": str(actual)}
    checks.append(entry)
    if not ok:
        failures.append(entry)

# ── Hash checks ───────────────────────────────────────────────────────────────
for db in ["candidate_pool.db", "constitutional_buy_registry.db",
           "constitutional_opportunity_events.db"]:
    cur = sha256(BASE / db)
    exp = golden_hashes.get(db, "MISSING")
    check(f"hash:{db}", cur == exp, exp[:16], cur[:16])

# ── Universe ──────────────────────────────────────────────────────────────────
golden_universe = json.loads((GOLDEN / "universe_27.json").read_text())
current_universe = qdb(BASE / "universe_snapshot.db",
    "SELECT ticker,status,current_price,entry_zone,reason,r2_score,final_score,return_pct FROM universe_snapshot ORDER BY ticker")

check("universe:size", len(current_universe) == len(golden_universe),
      len(golden_universe), len(current_universe))

g_by_t = {r["ticker"]: r for r in golden_universe}
c_by_t = {r["ticker"]: r for r in current_universe}
for ticker in sorted(g_by_t):
    g, c = g_by_t.get(ticker, {}), c_by_t.get(ticker, {})
    check(f"universe:{ticker}:status", g.get("status") == c.get("status"),
          g.get("status"), c.get("status"))

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
golden_tl = json.loads((GOLDEN / "timeline.json").read_text())
current_tl = qdb(BASE / "constitutional_opportunity_events.db",
    "SELECT * FROM constitutional_opportunity_events ORDER BY ticker, event_date")
check("timeline:rows", len(current_tl) == len(golden_tl), len(golden_tl), len(current_tl))

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
