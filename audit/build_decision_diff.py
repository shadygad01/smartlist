"""
Decision Diff Builder — Constitutional Architecture.

Compares the current production_decision_snapshot.json against the previous
committed version (git HEAD:production_decision_snapshot.json) and produces
decision_diff.json explaining every BUY/RE-ACCUM addition, removal, or change.

Constitutional rule: NO silent disappearance.
Every transition must carry a reason derived from the gate rule evaluation.

Called by: full_production_scan.yml and morning_email.yml after
           build_production_decision_snapshot.py runs.

Writes: decision_diff.json
Exit 0: diff built (including no-change runs)
Exit 1: unrecoverable error
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

from constitutional_gate import CONST_R2_MIN, CONST_SCORE_MIN

OUTPUT_PATH = BASE / "decision_diff.json"
SNAP_PATH   = BASE / "production_decision_snapshot.json"


def _load_previous_snapshot() -> dict | None:
    """Load the previous committed production_decision_snapshot.json via git show."""
    try:
        result = subprocess.run(
            ["git", "show", "HEAD:production_decision_snapshot.json"],
            capture_output=True, text=True, cwd=str(BASE), timeout=15,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except Exception:
        pass
    return None


def _decisions_by_ticker(snapshot: dict) -> dict[str, dict]:
    return {d["ticker"]: d for d in snapshot.get("decisions", [])}


def _gate_reason(curr: dict, prev: dict | None) -> str:
    """Explain why a ticker was added or removed from the eligible set."""
    cr2    = float(curr.get("constitutional_r2")    or 0)
    cscore = float(curr.get("constitutional_score") or 0)
    cprice = float(curr.get("current_price")        or 0)
    centry = float(curr.get("constitutional_entry_price") or 0)

    if prev is None:
        return (
            f"First scan record — "
            f"R2={cr2:.1f} (≥{CONST_R2_MIN}={cr2>=CONST_R2_MIN}), "
            f"score={cscore:.1f} (≥{CONST_SCORE_MIN}={cscore>=CONST_SCORE_MIN}), "
            f"price={cprice:.2f} vs entry={centry:.2f} "
            f"({'OK' if centry<=0 or cprice<=centry else 'ABOVE'})"
        )

    pr2    = float(prev.get("constitutional_r2")    or 0)
    pscore = float(prev.get("constitutional_score") or 0)
    pprice = float(prev.get("current_price")        or 0)
    pentry = float(prev.get("constitutional_entry_price") or 0)

    parts = []
    if abs(cr2 - pr2) >= 0.01:
        direction = "↑" if cr2 > pr2 else "↓"
        parts.append(f"R2 {direction} {pr2:.1f}→{cr2:.1f} (threshold {CONST_R2_MIN})")
    if abs(cscore - pscore) >= 0.01:
        direction = "↑" if cscore > pscore else "↓"
        parts.append(f"score {direction} {pscore:.1f}→{cscore:.1f} (threshold {CONST_SCORE_MIN})")
    if abs(cprice - pprice) >= 0.001:
        direction = "↓" if cprice < pprice else "↑"
        parts.append(f"price {direction} {pprice:.2f}→{cprice:.2f} (entry={centry:.2f})")

    if not parts:
        parts.append("values unchanged — eligibility flipped due to gate boundary")

    return "; ".join(parts)


def _removal_reason(curr: dict, prev: dict | None) -> str:
    """Explain why a ticker lost eligibility."""
    cr2    = float(curr.get("constitutional_r2")    or 0)
    cscore = float(curr.get("constitutional_score") or 0)
    cprice = float(curr.get("current_price")        or 0)
    centry = float(curr.get("constitutional_entry_price") or 0)

    failures = []
    if cr2 < CONST_R2_MIN:
        failures.append(f"R2={cr2:.1f} < {CONST_R2_MIN} (gate FAIL)")
    if cscore < CONST_SCORE_MIN:
        failures.append(f"score={cscore:.1f} < {CONST_SCORE_MIN} (gate FAIL)")
    if centry > 0 and cprice > centry:
        pct = (cprice - centry) / centry * 100
        failures.append(f"price={cprice:.2f} > entry={centry:.2f} (+{pct:.1f}%, gate FAIL)")

    if not failures:
        # This shouldn't happen if is_constitutional_buy is correct, but be defensive
        failures.append("gate evaluation returned False — check rules_evaluated in snapshot")

    prev_reason = ""
    if prev:
        pr2    = float(prev.get("constitutional_r2")    or 0)
        pscore = float(prev.get("constitutional_score") or 0)
        pprice = float(prev.get("current_price")        or 0)
        prev_reason = f" (was R2={pr2:.1f}, score={pscore:.1f}, price={pprice:.2f})"

    return "; ".join(failures) + prev_reason


def build_decision_diff() -> dict:
    if not SNAP_PATH.exists():
        print("SKIP: production_decision_snapshot.json not found")
        return {}

    curr_snap = json.loads(SNAP_PATH.read_text())
    prev_snap = _load_previous_snapshot()

    curr_by_ticker = _decisions_by_ticker(curr_snap)
    prev_by_ticker = _decisions_by_ticker(prev_snap) if prev_snap else {}

    curr_eligible = {t for t, d in curr_by_ticker.items() if d.get("eligible")}
    prev_eligible = {t for t, d in prev_by_ticker.items() if d.get("eligible")}

    added_tickers   = curr_eligible - prev_eligible
    removed_tickers = prev_eligible - curr_eligible
    changed_tickers = {
        t for t in (curr_eligible & prev_eligible)
        if curr_by_ticker[t].get("event_type") != prev_by_ticker[t].get("event_type")
    }

    def _entry(ticker: str, curr: dict, prev: dict | None, reason: str) -> dict:
        return {
            "ticker":      ticker,
            "event_type":  curr.get("event_type", "UNKNOWN"),
            "reason":      reason,
            "curr_r2":     float(curr.get("constitutional_r2")    or 0),
            "curr_score":  float(curr.get("constitutional_score") or 0),
            "curr_price":  float(curr.get("current_price")        or 0),
            "entry_price": float(curr.get("constitutional_entry_price") or 0),
            "prev_r2":     float(prev.get("constitutional_r2")    or 0) if prev else None,
            "prev_score":  float(prev.get("constitutional_score") or 0) if prev else None,
            "prev_price":  float(prev.get("current_price")        or 0) if prev else None,
        }

    added = sorted(
        [_entry(t, curr_by_ticker[t], prev_by_ticker.get(t),
                _gate_reason(curr_by_ticker[t], prev_by_ticker.get(t)))
         for t in added_tickers],
        key=lambda x: x["ticker"],
    )
    removed = sorted(
        [_entry(t, curr_by_ticker[t], prev_by_ticker.get(t),
                _removal_reason(curr_by_ticker[t], prev_by_ticker.get(t)))
         for t in removed_tickers],
        key=lambda x: x["ticker"],
    )
    changed = sorted(
        [{
            "ticker":          t,
            "prev_event_type": prev_by_ticker[t].get("event_type"),
            "curr_event_type": curr_by_ticker[t].get("event_type"),
            "reason":          (
                f"Event type changed: "
                f"{prev_by_ticker[t].get('event_type')} → {curr_by_ticker[t].get('event_type')}"
            ),
        }
         for t in changed_tickers],
        key=lambda x: x["ticker"],
    )
    unchanged = sorted(curr_eligible & prev_eligible - changed_tickers)

    diff = {
        "generated_at":       datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "prev_scan_id":       prev_snap.get("scan_id", "none") if prev_snap else "none",
        "curr_scan_id":       curr_snap.get("scan_id", "unknown"),
        "prev_eligible_count": len(prev_eligible),
        "curr_eligible_count": len(curr_eligible),
        "added_count":        len(added),
        "removed_count":      len(removed),
        "changed_count":      len(changed),
        "unchanged_count":    len(unchanged),
        "added":              added,
        "removed":            removed,
        "changed":            changed,
        "unchanged":          unchanged,
    }

    OUTPUT_PATH.write_text(json.dumps(diff, indent=2))

    print(f"decision_diff.json  added={len(added)}  removed={len(removed)}  "
          f"changed={len(changed)}  unchanged={len(unchanged)}")
    for a in added:
        print(f"  + ADDED   {a['ticker']} ({a['event_type']}): {a['reason']}")
    for r in removed:
        print(f"  - REMOVED {r['ticker']}: {r['reason']}")
    for c in changed:
        print(f"  ~ CHANGED {c['ticker']}: {c['reason']}")

    return diff


if __name__ == "__main__":
    result = build_decision_diff()
    sys.exit(0 if result is not None else 1)
