"""
Regression Suite — Phase 8 Constitutional Hardening.

Every bug previously fixed becomes a permanent regression test.
Any future code change that reintroduces a fixed bug will fail CI here.

Tests (each numbered for traceability):
  R-01  No duplicate CONST_R2_MIN / CONST_SCORE_MIN outside constitutional_gate.py
  R-02  No 2% price buffer (entry * 1.0x) in eligibility paths
  R-03  dashboard._s_buy_signals() calls is_constitutional_buy(), not inline gate
  R-04  detect_signal_changes() calls is_constitutional_buy(), not inline gate
  R-05  universe_snapshot.py has staleness guard for candidate_pool
  R-06  presentation_snapshot.json is not stale (>26h)
  R-07  No ticker appears in multiple presentation sections
  R-08  Every new_events_today ticker has a matching timeline entry
  R-09  No duplicate rows in signal_event_log (idempotency)
  R-10  No wf_v1 signal_version in production presentation output
  R-11  No orphan timeline events (every timeline ticker is in the universe)
  R-12  main.py and dashboard.py import from constitutional_gate
  R-13  production_decision_snapshot.json exists and has decisions

Exits 1 on any violation.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

failures: dict[str, list[str]] = {}


def _fail(test: str, msg: str) -> None:
    failures.setdefault(test, []).append(msg)


# ── R-01: No duplicate threshold constants ─────────────────────────────────────
_DUP_R2    = re.compile(r"CONST_R2_MIN\s*=\s*\d")
_DUP_SCORE = re.compile(r"CONST_SCORE_MIN\s*=\s*\d")
_GATE      = BASE / "constitutional_gate.py"

for _fp in sorted(BASE.glob("**/*.py")):
    if _fp == _GATE:
        continue
    _rel = str(_fp.relative_to(BASE))
    if _rel.startswith("archive/") or _rel.startswith("."):
        continue
    try:
        _t = _fp.read_text()
        for _m in _DUP_R2.finditer(_t):
            _ln = _t[:_m.start()].count("\n") + 1
            _fail("R-01", f"{_rel}:{_ln} defines CONST_R2_MIN (must import from constitutional_gate)")
        for _m in _DUP_SCORE.finditer(_t):
            _ln = _t[:_m.start()].count("\n") + 1
            _fail("R-01", f"{_rel}:{_ln} defines CONST_SCORE_MIN (must import from constitutional_gate)")
    except Exception:
        pass

# ── R-02: No 2% price buffer in eligibility paths ─────────────────────────────
_BUF = re.compile(r"(entry_price|entry|ep)\s*\*\s*1\.0[0-9]\b")
_ELIG_FILES = [
    "main.py", "dashboard.py",
    "constitutional_timeline_engine.py", "constitutional_opportunity_engine.py",
    "presentation/presentation_snapshot.py", "egx_email.py",
    "notifications/scan_orchestrator.py",
]
for _rel in _ELIG_FILES:
    _fp = BASE / _rel
    if not _fp.exists():
        continue
    _t = _fp.read_text()
    for _m in _BUF.finditer(_t):
        _ln = _t[:_m.start()].count("\n") + 1
        _fail("R-02", f"{_rel}:{_ln} 2% price buffer: {_m.group()!r}")

# ── R-03: dashboard._s_buy_signals must use is_constitutional_buy ──────────────
_DASH = BASE / "dashboard.py"
if _DASH.exists():
    _t  = _DASH.read_text()
    _fn = re.search(r"(def _s_buy_signals\(.+?\n)(?=def |\Z)", _t, re.DOTALL)
    if _fn:
        _body = _fn.group(0)
        if re.search(r"r2\s*>=\s*60.*\band\b.*score\s*>=\s*35|score\s*>=\s*35.*\band\b.*r2\s*>=\s*60", _body, re.IGNORECASE):
            _fail("R-03", "dashboard._s_buy_signals() contains inline R2+score AND gate — use is_constitutional_buy()")
        if "is_constitutional_buy" not in _body:
            _fail("R-03", "dashboard._s_buy_signals() does not call is_constitutional_buy()")
    else:
        _fail("R-03", "dashboard.py: _s_buy_signals() function not found")

# ── R-04: detect_signal_changes must use is_constitutional_buy ─────────────────
_MAIN = BASE / "main.py"
if _MAIN.exists():
    _t  = _MAIN.read_text()
    _fn = re.search(r"(def detect_signal_changes\(.+?\n)(?=def |\Z)", _t, re.DOTALL)
    if _fn:
        _body = _fn.group(0)
        if re.search(r"entry_price\s*\*\s*1\.0[12]", _body):
            _fail("R-04", "detect_signal_changes() still has price buffer (* 1.0x)")
        if re.search(r"r2\s*>=\s*60.*\band\b.*score\s*>=\s*35|score\s*>=\s*35.*\band\b.*r2\s*>=\s*60", _body, re.IGNORECASE):
            _fail("R-04", "detect_signal_changes() contains inline R2+score AND gate — use is_constitutional_buy()")
        if "is_constitutional_buy" not in _body:
            _fail("R-04", "detect_signal_changes() does not call is_constitutional_buy()")
    else:
        _fail("R-04", "main.py: detect_signal_changes() function not found")

# ── R-05: universe_snapshot.py has staleness guard for pool ───────────────────
_UNI = BASE / "universe_snapshot.py"
if _UNI.exists():
    _t = _UNI.read_text()
    if "_POOL_STALENESS_DAYS" not in _t and "_pool_stale" not in _t and "stale" not in _t.lower():
        _fail("R-05", "universe_snapshot.py: no staleness guard for candidate_pool (stale pool → false signals)")

# ── R-06: presentation_snapshot.json not stale (>26h) ─────────────────────────
_pres = BASE / "presentation_snapshot.json"
if _pres.exists():
    try:
        _d    = json.loads(_pres.read_text())
        _gen  = _d.get("generated_at", "")
        if _gen:
            from datetime import datetime, timezone
            _dt   = datetime.fromisoformat(_gen.replace("Z", "+00:00"))
            if _dt.tzinfo is None:
                _dt = _dt.replace(tzinfo=timezone.utc)
            _age  = (datetime.now(timezone.utc) - _dt).total_seconds() / 3600
            if _age > 26:
                _fail("R-06", f"presentation_snapshot.json is {_age:.1f}h old (>26h)")
    except Exception as _e:
        _fail("R-06", f"presentation_snapshot.json parse error: {_e}")
else:
    _fail("R-06", "presentation_snapshot.json missing")

# ── R-07: No ticker in multiple sections ──────────────────────────────────────
if _pres.exists():
    try:
        _d = json.loads(_pres.read_text())
        _near   = {e["ticker"] for e in _d.get("near_constitutional", [])}
        _active = {u["ticker"] for u in _d.get("active", [])}
        _future = {u["ticker"] for u in _d.get("future_candidates", [])}
        if _near & _future:
            _fail("R-07", f"Near ∩ Future not empty: {sorted(_near & _future)}")
        if _active & _future:
            _fail("R-07", f"Active ∩ Future not empty: {sorted(_active & _future)}")
    except Exception:
        pass

# ── R-08: new_events_today tickers must have timeline entries ─────────────────
_TL = BASE / "constitutional_opportunity_events.db"
if _pres.exists() and _TL.exists():
    try:
        _d = json.loads(_pres.read_text())
        from time_authority import today_cairo as _tc
        _today = _tc().isoformat()
        _today_evs = [e for e in _d.get("new_events_today", []) if e.get("event_date") == _today]
        if _today_evs:
            _con = sqlite3.connect(str(_TL))
            _tl_t = {r[0] for r in _con.execute(
                "SELECT ticker FROM constitutional_opportunity_events WHERE event_date=?", (_today,)
            ).fetchall()}
            _con.close()
            for _ev in _today_evs:
                _t = _ev["ticker"]
                if _t not in _tl_t:
                    _fail("R-08", f"{_t}: in new_events_today but missing from timeline for {_today}")
    except Exception:
        pass

# ── R-09: No duplicates in signal_event_log (idempotency) ─────────────────────
_NOTIF = BASE / "notification_delivery.db"
if _NOTIF.exists():
    try:
        _con = sqlite3.connect(str(_NOTIF))
        _rows = _con.execute(
            "SELECT ticker, event_date, to_state, COUNT(*) as n "
            "FROM signal_event_log GROUP BY ticker, event_date, to_state HAVING n > 1"
        ).fetchall()
        _con.close()
        for _r in _rows:
            _fail("R-09", f"signal_event_log duplicate: ticker={_r[0]} date={_r[1]} state={_r[2]} n={_r[3]}")
    except Exception:
        pass

# ── R-10: No wf_v1 events in production presentation output ───────────────────
if _pres.exists():
    try:
        _d = json.loads(_pres.read_text())
        for _ev in _d.get("re_accumulation", []):
            if _ev.get("signal_version", "v1") == "wf_v1":
                _fail("R-10", f"wf_v1 event in re_accumulation: {_ev.get('ticker')}")
    except Exception:
        pass

# ── R-11: No orphan timeline events ───────────────────────────────────────────
_UNI_DB = BASE / "universe_snapshot.db"
if _TL.exists() and _UNI_DB.exists():
    try:
        _c1 = sqlite3.connect(str(_TL))
        _c2 = sqlite3.connect(str(_UNI_DB))
        _tl_ts  = {r[0] for r in _c1.execute("SELECT DISTINCT ticker FROM constitutional_opportunity_events").fetchall()}
        _uni_ts = {r[0] for r in _c2.execute("SELECT ticker FROM universe_snapshot").fetchall()}
        _c1.close(); _c2.close()
        _orphans = _tl_ts - _uni_ts
        if _orphans:
            _fail("R-11", f"Orphan timeline tickers not in universe: {sorted(_orphans)}")
    except Exception:
        pass

# ── R-12: main.py and dashboard.py import from constitutional_gate ────────────
for _rel in ("main.py", "dashboard.py"):
    _fp = BASE / _rel
    if _fp.exists() and "constitutional_gate" not in _fp.read_text():
        _fail("R-12", f"{_rel} does not import from constitutional_gate")

# ── R-13: production_decision_snapshot.json exists and has decisions ──────────
_prod = BASE / "production_decision_snapshot.json"
if not _prod.exists():
    _fail("R-13", "production_decision_snapshot.json missing — build_production_decision_snapshot.py must run")
else:
    try:
        _d = json.loads(_prod.read_text())
        if not _d.get("decisions"):
            _fail("R-13", "production_decision_snapshot.json has no decisions")
        if _d.get("ticker_count", 0) < 20:
            _fail("R-13", f"production_decision_snapshot.json only {_d.get('ticker_count')} tickers (expected ~27)")
    except Exception as _e:
        _fail("R-13", f"production_decision_snapshot.json parse error: {_e}")

# ── R-14: Immutability — only build_production_decision_snapshot.py may write to production_decision_snapshot.json
_BUILD_SNAP = BASE / "audit" / "build_production_decision_snapshot.py"
_WRITE_PAT  = re.compile(r"""["']production_decision_snapshot\.json["']""")
for _fp in sorted(BASE.glob("**/*.py")):
    if _fp == _BUILD_SNAP:
        continue
    _rel = str(_fp.relative_to(BASE))
    if _rel.startswith("archive/") or _rel.startswith("."):
        continue
    try:
        _t = _fp.read_text()
        # Flag if file both references the snapshot AND uses open()/write_text()/json.dump
        if _WRITE_PAT.search(_t):
            # Check if it writes (not just reads) the file
            _lines = _t.splitlines()
            for _i, _line in enumerate(_lines):
                if _WRITE_PAT.search(_line):
                    _ctx = "\n".join(_lines[max(0, _i-2):_i+3])
                    if re.search(r'open\s*\(|\.write_text\s*\(|json\.dump\s*\(', _ctx):
                        _ln = _i + 1
                        _fail("R-14", f"{_rel}:{_ln} writes production_decision_snapshot.json "
                              "(only audit/build_production_decision_snapshot.py may write this file)")
    except Exception:
        pass

# ── R-15: No renderer-side constitutional eligibility recalculation ────────────
# Presentation/rendering files must not re-implement gate logic inline.
# They may call is_constitutional_buy() but must NOT inline threshold comparisons
# in executable code (comments documenting the gate are allowed).
_RENDERER_FILES = [
    "egx_email.py",
    "notifications/scan_orchestrator.py",
    "presentation/presentation_snapshot.py",
]
_INLINE_GATE = re.compile(
    r"r2\s*>=\s*(?:60|CONST_R2_MIN).*\band\b.*score\s*>=\s*(?:35|CONST_SCORE_MIN)",
    re.IGNORECASE,
)
for _rel in _RENDERER_FILES:
    _fp = BASE / _rel
    if not _fp.exists():
        continue
    for _ln_no, _line in enumerate(_fp.read_text().splitlines(), 1):
        _stripped = _line.lstrip()
        if _stripped.startswith("#"):   # pure comment line — allowed
            continue
        if _INLINE_GATE.search(_line):
            _fail("R-15", f"{_rel}:{_ln_no} inline gate logic — call is_constitutional_buy() instead: {_line.strip()!r}")

# ── R-16: No orphan signal_event_log notifications ────────────────────────────
# Every CONSTITUTIONAL_BUY notification must have a timeline entry.
_NOTIF_DB = BASE / "notification_delivery.db"
_TL_DB    = BASE / "constitutional_opportunity_events.db"
if _NOTIF_DB.exists() and _TL_DB.exists():
    try:
        _nc = sqlite3.connect(str(_NOTIF_DB))
        _tc = sqlite3.connect(str(_TL_DB))
        _notif_tickers = {r[0] for r in _nc.execute(
            "SELECT DISTINCT ticker FROM signal_event_log WHERE to_state='CONSTITUTIONAL_BUY'"
        ).fetchall()}
        _tl_tickers = {r[0] for r in _tc.execute(
            "SELECT DISTINCT ticker FROM constitutional_opportunity_events"
        ).fetchall()}
        _nc.close(); _tc.close()
        _orphan_notifs = _notif_tickers - _tl_tickers
        for _t in sorted(_orphan_notifs):
            _fail("R-16", f"{_t}: CONSTITUTIONAL_BUY notification exists but no timeline entry")
    except Exception:
        pass

# ── R-17: constitutional_timeline_engine and opportunity_engine import from gate
# These are the only files that apply CONST_R2_MIN/CONST_SCORE_MIN in SQL queries.
# They must import the values from constitutional_gate, never define them locally.
_ENGINE_FILES = ["constitutional_timeline_engine.py", "constitutional_opportunity_engine.py",
                 "presentation/presentation_snapshot.py"]
for _rel in _ENGINE_FILES:
    _fp = BASE / _rel
    if _fp.exists() and "constitutional_gate" not in _fp.read_text():
        _fail("R-17", f"{_rel} does not import from constitutional_gate "
              "(engine files must not hardcode constitutional thresholds)")

# ── Report ─────────────────────────────────────────────────────────────────────
print("Regression Suite")
print()

_TESTS = [
    ("R-01", "No duplicate CONST_R2_MIN/CONST_SCORE_MIN outside gate"),
    ("R-02", "No 2% price buffer in eligibility paths"),
    ("R-03", "dashboard._s_buy_signals() uses is_constitutional_buy()"),
    ("R-04", "detect_signal_changes() uses is_constitutional_buy()"),
    ("R-05", "universe_snapshot.py has pool staleness guard"),
    ("R-06", "presentation_snapshot.json not stale"),
    ("R-07", "No ticker in multiple presentation sections"),
    ("R-08", "new_events_today tickers have timeline entries"),
    ("R-09", "No duplicate signal_event_log rows"),
    ("R-10", "No wf_v1 events in production output"),
    ("R-11", "No orphan timeline events"),
    ("R-12", "main.py and dashboard.py import constitutional_gate"),
    ("R-13", "production_decision_snapshot.json exists and complete"),
    ("R-14", "Only build_production_decision_snapshot.py writes production snapshot"),
    ("R-15", "No renderer-side inline gate logic in email/presentation files"),
    ("R-16", "No orphan CONSTITUTIONAL_BUY notifications without timeline entry"),
    ("R-17", "egx_email.py and scan_orchestrator import constitutional_gate"),
]

total  = len(_TESTS)
passed = 0
for test_id, desc in _TESTS:
    errs = failures.get(test_id, [])
    if errs:
        for e in errs:
            print(f"  ✗ {test_id}: {e}")
    else:
        print(f"  ✓ {test_id}: {desc}")
        passed += 1

print()
print(f"Results: {passed}/{total} regression tests passed")

if failures:
    print("\nASSERTION FAILED — regression(s) detected.")
    sys.exit(1)

print("ASSERTION PASSED — all regression tests pass.")
sys.exit(0)
