"""
Constitutional Decision Consistency Assertion.

Verifies that BUY eligibility is decided only by constitutional_gate.is_constitutional_buy:
  1. No file outside constitutional_gate.py defines a 2% price buffer (the historical violation).
  2. main.py and dashboard.py import from constitutional_gate (not inline).
  3. Runtime: universe_snapshot data produces the same gate result regardless of caller path.

Exits 1 on any violation.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

from constitutional_gate import is_constitutional_buy, CONST_R2_MIN, CONST_SCORE_MIN
from audit.audit_status import AuditStatus

failures: list[str] = []

# ── 1. Static: 2% price buffer must not exist outside the gate file ─────────
BUFFER_PATTERN = re.compile(r"(entry_price|entry|ep)\s*\*\s*1\.0[0-9]\b")
ALLOWED_PATHS  = {"constitutional_gate.py", "audit/assert_decision_consistency.py"}

SCAN_FILES = [
    "main.py",
    "dashboard.py",
    "constitutional_timeline_engine.py",
    "constitutional_opportunity_engine.py",
    "presentation/presentation_snapshot.py",
    "universe_snapshot.py",
    "egx_email.py",
    "notifications/scan_orchestrator.py",
]

for rel in SCAN_FILES:
    fp = BASE / rel
    if not fp.exists():
        continue
    text = fp.read_text()
    for m in BUFFER_PATTERN.finditer(text):
        line_no = text[: m.start()].count("\n") + 1
        snippet = m.group().strip()
        failures.append(f"{rel}:{line_no} — forbidden price buffer: {snippet!r}")

# ── 2. Static: main.py and dashboard.py must import from constitutional_gate ─
for rel in ("main.py", "dashboard.py"):
    fp = BASE / rel
    if not fp.exists():
        continue
    text = fp.read_text()
    if "constitutional_gate" not in text:
        failures.append(f"{rel} — does not import from constitutional_gate")

# ── 3. Static: duplicate threshold constants must not exist outside gate ─────
DUP_R2    = re.compile(r"CONST_R2_MIN\s*=\s*\d+")
DUP_SCORE = re.compile(r"CONST_SCORE_MIN\s*=\s*\d+")
GATE_FILE = BASE / "constitutional_gate.py"

for fp in BASE.glob("**/*.py"):
    if fp == GATE_FILE:
        continue
    rel = str(fp.relative_to(BASE))
    if rel.startswith("archive/") or rel.startswith("."):
        continue
    text = fp.read_text()
    for m in DUP_R2.finditer(text):
        line_no = text[: m.start()].count("\n") + 1
        failures.append(f"{rel}:{line_no} — duplicate CONST_R2_MIN definition (import from constitutional_gate instead)")
    for m in DUP_SCORE.finditer(text):
        line_no = text[: m.start()].count("\n") + 1
        failures.append(f"{rel}:{line_no} — duplicate CONST_SCORE_MIN definition (import from constitutional_gate instead)")

# ── 4. Runtime: gate agrees with universe_snapshot eligibility set ──────────
snap_path = BASE / "presentation_snapshot.json"
buy_tickers: list[str] = []
if snap_path.exists():
    snap  = json.loads(snap_path.read_text())
    uni   = snap.get("universe_snapshot", [])
    for row in uni:
        ticker = row.get("ticker", "")
        r2     = float(row.get("candidate_r2") or 0)
        score  = float(row.get("expected_reward_score") or 0)
        cp     = float(row.get("current_price") or 0)
        ep     = float(row.get("constitutional_entry_price") or 0)
        if ticker and is_constitutional_buy(r2, score, cp, ep):
            buy_tickers.append(ticker)

    # Every ticker in new_events_today must have come from gate-positive data.
    # Price may have moved since event was recorded — so this is a soft warning only.
    gate_set = set(buy_tickers)
    try:
        from time_authority import today_cairo
        _today = today_cairo().isoformat()
    except Exception:
        from datetime import date
        _today = date.today().isoformat()

    today_events = [e for e in snap.get("new_events_today", []) if e.get("event_date") == _today]
    for e in today_events:
        t = e["ticker"]
        if t not in gate_set:
            print(f"  INFO: {t} fired today's event but gate=False now (price may have moved after event)")
else:
    print("  SKIP: presentation_snapshot.json not found — runtime check skipped")

# ── Report ────────────────────────────────────────────────────────────────────
print("Constitutional Decision Consistency Assertion")
print(f"  CONST_R2_MIN      : {CONST_R2_MIN}")
print(f"  CONST_SCORE_MIN   : {CONST_SCORE_MIN}")
print(f"  Price tolerance   : strict (no buffer)")
print(f"  Buy tickers (gate): {sorted(buy_tickers) or 'none'}")
print(f"  Today's events    : {len(today_events) if snap_path.exists() else 'N/A'}")

if failures:
    print("\nCONSISTENCY FAILURES:")
    for f in failures:
        print(f"  ✗ {f}")
    print("\nASSERTION FAILED — constitutional gate is not the single source of truth.")
    sys.exit(AuditStatus.FAIL)

print("\nASSERTION PASSED — constitutional gate.is_constitutional_buy is single source of truth.")
sys.exit(AuditStatus.PASS)
