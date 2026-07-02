"""
Constitutional Operations Director — central coordinator.
Runs full decision-tree cycle: observe → diagnose → recover → validate → close.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))
from time_authority import now_cairo, today_cairo, now_iso, today_iso, age_hours



def _now() -> str:
    return now_iso()


def _log(msg: str) -> None:
    ts = now_cairo().strftime("%H:%M:%S")
    print(f"[Director {ts}] {msg}")


class OperationsDirector:
    """
    Full-cycle constitutional operations coordinator.
    Usage:
        director = OperationsDirector()
        report   = director.run_full_cycle()
    """

    def run_full_cycle(self, market_date: str | None = None) -> dict:
        from .heartbeat   import update_heartbeat, record_validation, set_status, compute_next_scan
        from .incident    import open_incident, close_by_type, list_open_incidents, incident_summary
        from .health      import system_health
        from .sla         import compute_metrics, record_event
        from .recovery    import (
            rebuild_universe_snapshot, rebuild_stock_dna,
            rebuild_presentation_snapshot, rebuild_dashboard,
            validate_presentation_consistency, validate_price_freshness,
        )
        from .scheduler   import is_trading_day, sla_violated

        market_date = market_date or today_iso()
        _log(f"Starting full cycle for {market_date}")

        report = {
            "cycle_at":     _now(),
            "market_date":  market_date,
            "jobs":         {},
            "incidents":    [],
            "health":       {},
            "recovered":    [],
        }

        # ── 1. Observe: load heartbeat + open incidents ────────────────────────
        from .heartbeat import read_heartbeat
        hb           = read_heartbeat()
        open_inc     = list_open_incidents()
        health       = system_health(hb, open_inc)
        report["health"] = health

        _log(f"System status: {health['status']} — {len(open_inc)} open incidents")

        # ── 2. Price Freshness ─────────────────────────────────────────────────
        if is_trading_day():
            fresh = validate_price_freshness()
            record_event("scan", fresh, "price_freshness_check")
            if not fresh:
                inc = open_incident("PRICE_STALE", "price freshness assertion failed")
                report["incidents"].append(inc["id"])
                _log("DIAG: prices stale — rebuilding universe snapshot")
                ok = rebuild_universe_snapshot() and rebuild_stock_dna()
                if ok and validate_price_freshness():
                    close_by_type("PRICE_STALE", "recovered via rebuild_universe_snapshot")
                    report["recovered"].append("PRICE_STALE")
                    record_event("recovery", True, "PRICE_STALE")
                else:
                    record_event("recovery", False, "PRICE_STALE")
            else:
                close_by_type("PRICE_STALE", "prices fresh")

        # ── 3. Presentation Snapshot ───────────────────────────────────────────
        snap_ok = rebuild_presentation_snapshot()
        if snap_ok:
            from .heartbeat import record_snapshot
            record_snapshot(market_date)
        consistent = validate_presentation_consistency()
        if not consistent:
            inc = open_incident("PRESENTATION_DRIFT", "consistency assertion failed")
            report["incidents"].append(inc["id"])
            ok = rebuild_universe_snapshot() and rebuild_presentation_snapshot() and validate_presentation_consistency()
            if ok:
                close_by_type("PRESENTATION_DRIFT", "recovered")
                report["recovered"].append("PRESENTATION_DRIFT")
                record_event("recovery", True, "PRESENTATION_DRIFT")
            else:
                record_event("recovery", False, "PRESENTATION_DRIFT")
        else:
            close_by_type("PRESENTATION_DRIFT", "consistency ok")

        # ── 4. Dashboard ──────────────────────────────────────────────────────
        dash_ok = rebuild_dashboard()
        if dash_ok:
            from .heartbeat import record_dashboard
            record_dashboard()
            record_event("dashboard", True)
        else:
            inc = open_incident("DASHBOARD_DRIFT", "dashboard build failed")
            report["incidents"].append(inc["id"])
            record_event("dashboard", False)

        # ── 5. Validation ─────────────────────────────────────────────────────
        try:
            import subprocess
            result = subprocess.run(
                [sys.executable, "audit/assert_presentation_consistency.py"],
                cwd=str(BASE), capture_output=True, text=True, timeout=30
            )
            val_ok = result.returncode == 0
        except Exception:
            val_ok = False
        record_validation(val_ok)
        record_event("validation", val_ok)
        if not val_ok:
            open_incident("VALIDATION_FAILURE", "presentation consistency validation failed")
        else:
            close_by_type("VALIDATION_FAILURE", "validation passed")

        # ── 6. Heartbeat + Final Health ────────────────────────────────────────
        open_inc  = list_open_incidents()
        health    = system_health(hb, open_inc)
        set_status(health["status"])
        update_heartbeat(
            last_scan=_now(),
            market_date=market_date,
            next_scan=compute_next_scan(),
        )
        record_event("scan", val_ok, market_date)

        report["health"]         = health
        report["incident_summary"] = incident_summary()
        report["sla_30d"]        = compute_metrics(30)

        _log(
            f"Cycle complete — status={health['status']}, "
            f"recovered={report['recovered']}, "
            f"open_incidents={len(open_inc)}"
        )
        return report

    def run_morning_report(self, market_date: str | None = None) -> bool:
        """Build + send morning email + Telegram."""
        from .heartbeat import record_email
        from .incident  import open_incident, close_by_type
        from .sla       import record_event
        from .recovery  import rebuild_presentation_snapshot, send_morning_email

        market_date = market_date or today_iso()
        _log(f"Running morning report for {market_date}")

        ok = rebuild_presentation_snapshot() and send_morning_email()
        if ok:
            record_email(market_date)
            close_by_type("MISSED_MORNING_REPORT", "morning report sent")
            record_event("morning_report", True, market_date)
        else:
            open_incident("MISSED_MORNING_REPORT", f"morning report failed for {market_date}")
            record_event("morning_report", False, market_date)
        return ok

    def status_summary(self) -> dict:
        from .heartbeat import read_heartbeat
        from .incident  import list_open_incidents, incident_summary
        from .health    import system_health
        from .sla       import compute_metrics

        hb      = read_heartbeat()
        open_i  = list_open_incidents()
        health  = system_health(hb, open_i)
        sla30   = compute_metrics(30)

        return {
            "status":           health["status"],
            "reasons":          health["reasons"],
            "checks":           health["checks"],
            "heartbeat":        hb,
            "open_incidents":   open_i,
            "incident_summary": incident_summary(),
            "sla_30d":          sla30,
        }


if __name__ == "__main__":
    director = OperationsDirector()
    report   = director.run_full_cycle()
    import json
    print(json.dumps(report, indent=2, default=str))
