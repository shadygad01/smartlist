"""
Constitutional Presentation Snapshot V4 — Timeline Edition
Single data contract consumed by dashboard_v2, email_v2, telegram_v2.
Primary source: constitutional_opportunity_events.db (append-only timeline).
Historical BUY status NEVER depends on today's R2.
No portfolio dependency. No capacity. No sector filter. No correlation.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
import csv as _csv

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))
from time_authority import now_cairo, now_iso, today_cairo, is_trading_day as _is_trading_day, _EET as _CAIRO_TZ, market_state as _market_state_ta, _MARKET_OPEN_H, _MARKET_OPEN_M
from constitutional_gate import is_constitutional_buy as _is_constitutional_buy

_ADVISOR_DB  = BASE / "portfolio_advisor.db"
_KB_DB       = BASE / "research" / "knowledge" / "knowledge_base.db"
_POOL_DB     = BASE / "candidate_pool.db"
_HIST_DIR    = BASE / "historical_data" / "historical_data"


def _latest_csv_price(ticker: str) -> tuple[float | None, str]:
    """Return (latest_close, date_str) from CSV file, or (None, '') if unavailable."""
    csv_path = _HIST_DIR / f"{ticker}.csv"
    if not csv_path.exists():
        return None, ""
    try:
        with open(csv_path, newline="") as f:
            rows = list(_csv.DictReader(f))
        if not rows:
            return None, ""
        last = rows[-1]
        close = float(last.get("Close", 0) or 0)
        date  = last.get("Date", "")
        if close > 0:
            return close, date
    except Exception:
        pass
    return None, ""


def _csv_data_as_of() -> str:
    """Return the most recent price date — PriceAuthority first, then CSV fallback."""
    # Primary: universe_snapshot.db last_price_update (reflects actual scan date)
    try:
        from price_authority import get_data_as_of
        auth_date = get_data_as_of()
        if auth_date:
            return auth_date
    except Exception:
        pass

    # Fallback: scan CSV files
    best_date = ""
    if not _HIST_DIR.exists():
        return best_date
    try:
        for csv_path in _HIST_DIR.glob("*.CA.csv"):
            with open(csv_path, newline="") as f:
                for row in _csv.DictReader(f):
                    d = row.get("Date", "")
                    if d > best_date:
                        best_date = d
    except Exception:
        pass
    return best_date


def _db(path: Path) -> sqlite3.Connection | None:
    """Open SQLite connection with Row factory, or return None if path does not exist."""
    if not path.exists():
        return None
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _clean_reason(text: str) -> str:
    """Strip raw R-score annotations from reason strings for clean display."""
    if not text:
        return text
    text = re.sub(r'\(\s*R\d+=[\d.]+\s*\)', '', text)
    text = re.sub(r'\bR\d+=[\d.]+\s*(?:\([^)]*\))?[.,]?\s*', '', text)
    text = re.sub(r'\s+([,.])', r'\1', text)
    text = re.sub(r'  +', ' ', text)
    return text.strip()


def _market_status() -> str:
    """Delegates to time_authority.market_state() — single source of truth."""
    state = _market_state_ta()
    if state == "OPEN":
        return "OPEN"
    if state == "PRE_OPEN":
        return f"PRE-MARKET (opens {_MARKET_OPEN_H:02d}:{_MARKET_OPEN_M:02d})"
    if state == "WEEKEND":
        return "CLOSED (Weekend)"
    return "CLOSED (After Hours)"


def _confidence_stars(total_events: int, avg_return: float, win_rate: float) -> str:
    """DEVELOPING / CONFIRMED / STRONG / ELITE based on track record."""
    score = 0
    score += min(total_events, 4)
    if avg_return >= 30:  score += 3
    elif avg_return >= 10: score += 2
    elif avg_return >= 0:  score += 1
    if win_rate >= 0.8:  score += 2
    elif win_rate >= 0.6: score += 1
    if score >= 8:   return "ELITE"
    if score >= 5:   return "STRONG"
    if score >= 3:   return "CONFIRMED"
    return "DEVELOPING"


@dataclass
class PresentationSnapshot:
    # Health (from advisor — informational only, shown in System Diagnostics)
    health_stars:     str = "★☆☆☆☆"
    health_label:     str = "Unknown"
    health_narrative: str = ""

    # Constitutional Opportunity Timeline — OPERATIONAL (v1 production events only)
    timeline:          list[dict] = field(default_factory=list)
    total_events:      int = 0
    total_tickers:     int = 0
    new_events_today:  list[dict] = field(default_factory=list)
    first_buys:        list[dict] = field(default_factory=list)
    re_accumulations:  list[dict] = field(default_factory=list)

    # Historical Knowledge Base — ALL events (v1 + wf_v1 walk-forward history)
    knowledge_timeline: list[dict] = field(default_factory=list)

    # Analytics & leaderboards
    analytics:    dict = field(default_factory=dict)
    leaderboards: dict = field(default_factory=dict)

    # Constitutional leaders (enriched per-ticker analytics)
    constitutional_leaders: list[dict] = field(default_factory=list)

    # Approaching constitutional entry (R2 50-59.9, score >= 35)
    approaching_entries: list[dict] = field(default_factory=list)

    # Runtime metadata
    universe_size:  int = 0
    market_status:  str = ""
    last_scan_ts:   str = ""

    # Research & knowledge
    research_insights:   list[dict] = field(default_factory=list)
    knowledge_count:     int = 0
    experiments_running: int = 0

    # Universe Snapshot (all 27 tickers)
    universe_snapshot: list[dict] = field(default_factory=list)

    # Meta
    generated_at:      str = ""
    price_data_as_of:  str = ""   # date of latest CSV close — authoritative price date

    # Legacy compatibility
    constitutional_buys: list[dict] = field(default_factory=list)
    total_buys:          int = 0
    new_buys_today:      list[dict] = field(default_factory=list)
    held_positions:      list[dict] = field(default_factory=list)
    held_count:          int = 0
    opportunities:       list[dict] = field(default_factory=list)
    future_priorities:   list[dict] = field(default_factory=list)
    watch_list:          list[str]  = field(default_factory=list)
    sector_allocation:   dict       = field(default_factory=dict)
    max_correlation:     float = 0.0
    capacity_used_pct:   float = 0.0
    position_weight_pct: float = 0.0
    sector_cap_ok:       bool  = True


def build_presentation_snapshot() -> PresentationSnapshot:
    """Build PresentationSnapshot from constitutional timeline, pool, advisor, and universe sources."""
    snap = PresentationSnapshot(
        generated_at=now_iso(),
        market_status=_market_status(),
        price_data_as_of=_csv_data_as_of(),
    )

    # ── 0. Constitutional Opportunity Timeline ────────────────────────────────
    try:
        import sys
        sys.path.insert(0, str(BASE))
        from constitutional_timeline_engine import (
            get_timeline, get_analytics, get_leaderboards
        )
        from datetime import date as _date
        _today = _date.today().isoformat()

        # OPERATIONAL: production events only (signal_version='v1')
        tl_ops = get_timeline(production_only=True)
        # KNOWLEDGE BASE: all events including walk-forward history (wf_v1)
        tl_all = get_timeline()

        # Analytics and leaderboards use full history — they power knowledge base
        # enrichment (Similar Setups count, historical win rate, avg return, etc.)
        an = get_analytics(timeline=tl_all)
        lb = get_leaderboards(timeline=tl_all, analytics=an)

        # Operational fields — production events only
        snap.timeline         = tl_ops
        snap.total_events     = len(tl_ops)
        snap.total_tickers    = len(set(e["ticker"] for e in tl_ops))
        snap.new_events_today = [e for e in tl_ops if e["event_date"] == _today]
        snap.first_buys       = [e for e in tl_ops if e["event_type"] == "FIRST_BUY"]
        snap.re_accumulations = [e for e in tl_ops if e["event_type"] == "RE_ACCUMULATION"]

        # Knowledge base fields — full history
        snap.knowledge_timeline = tl_all
        snap.analytics          = an
        snap.leaderboards       = lb

        # Build constitutional leaders from full history analytics (knowledge base enrichment)
        leaders = []
        for ticker, a in an.items():
            ticker_events = [e for e in tl_all if e["ticker"] == ticker]
            wins = sum(1 for e in ticker_events if e["return_pct"] > 0)
            win_rate = wins / len(ticker_events) if ticker_events else 0.0
            current_price = ticker_events[-1]["current_price"] if ticker_events else 0.0
            peak_ret = max((e["peak_return_pct"] for e in ticker_events), default=0.0)
            current_ret = ticker_events[-1]["return_pct"] if ticker_events else 0.0
            sector = ticker_events[0]["sector"] if ticker_events else ""
            confidence = _confidence_stars(a["total_events"], a["avg_return_pct"], win_rate)
            leaders.append(dict(
                ticker=ticker,
                sector=sector,
                total_events=a["total_events"],
                avg_return_pct=a["avg_return_pct"],
                best_return_pct=a["best_return_pct"],
                current_price=current_price,
                current_ret=current_ret,
                peak_ret=peak_ret,
                win_rate=win_rate,
                confidence=confidence,
            ))
        snap.constitutional_leaders = sorted(
            leaders, key=lambda x: (-x["total_events"], -x["avg_return_pct"])
        )

        # Legacy aliases
        snap.constitutional_buys = snap.first_buys
        snap.total_buys          = len(snap.first_buys)
        snap.new_buys_today      = [e for e in snap.new_events_today
                                    if e["event_type"] == "FIRST_BUY"]
    except Exception:
        pass

    # ── Filter new_events_today by current eligibility ────────────────────────
    # production_decision_snapshot is the authoritative eligibility source.
    # new_events_today must be a subset of currently eligible tickers so that
    # all consumers (dashboard, email, Telegram, audit assertions) see a
    # consistent signal set. The dashboard already applies this filter at render
    # time; applying it here ensures the snapshot itself agrees with the gate.
    # When the production snapshot does not yet exist (first run in a pipeline)
    # this block is skipped and the reconciliation step rebuilds the snapshot
    # after the production snapshot is written.
    _prod_snap_path = BASE / "production_decision_snapshot.json"
    if _prod_snap_path.exists() and snap.new_events_today:
        try:
            import json as _json_prod_filter
            _prod_filter_data = _json_prod_filter.loads(_prod_snap_path.read_text())
            _prod_eligible_set = {
                d["ticker"]
                for d in _prod_filter_data.get("decisions", [])
                if d.get("eligible")
            }
            _before = len(snap.new_events_today)
            snap.new_events_today = [
                e for e in snap.new_events_today
                if e["ticker"] in _prod_eligible_set
            ]
            snap.new_buys_today = [
                e for e in snap.new_events_today
                if e["event_type"] == "FIRST_BUY"
            ]
            _filtered = _before - len(snap.new_events_today)
            if _filtered:
                print(
                    f"[PresentationSnapshot] new_events_today: excluded {_filtered} "
                    f"ineligible ticker(s) via production_decision_snapshot"
                )
        except Exception as _prod_filt_err:
            print(
                f"[PresentationSnapshot] new_events_today eligibility filter "
                f"non-fatal: {_prod_filt_err}"
            )

    # ── 1. Approaching Constitutional Entry (candidate_pool) ──────────────────
    pool = _db(_POOL_DB)
    if pool:
        try:
            latest_ts = pool.execute(
                "SELECT MAX(snapshot_ts) FROM candidate_pool"
            ).fetchone()[0]
            # Use heartbeat.last_scan as the authoritative last scan timestamp
            # (candidate_pool is only updated by standalone builder, not market scans)
            try:
                import json as _json
                _hb = _json.loads((BASE / "heartbeat.json").read_text())
                snap.last_scan_ts = _hb.get("last_scan") or latest_ts or ""
            except Exception:
                snap.last_scan_ts = latest_ts or ""

            # Staleness guard: pool > 5 days old must not drive approaching-entry display.
            _pool_stale = False
            _latest_sig = pool.execute(
                "SELECT MAX(signal_date) FROM candidate_pool WHERE snapshot_ts=?", (latest_ts,)
            ).fetchone()[0]
            if _latest_sig:
                from datetime import date as _dt_date
                _days_stale = (_dt_date.today() - _dt_date.fromisoformat(_latest_sig)).days
                if _days_stale > 5:
                    print(f"[PresentationSnapshot] Pool stale ({_days_stale}d) — "
                          f"skipping approaching entries from stale pool.")
                    _pool_stale = True

            universe_cnt = pool.execute(
                "SELECT COUNT(DISTINCT ticker) FROM candidate_pool WHERE snapshot_ts=?",
                (latest_ts,)
            ).fetchone()[0]
            snap.universe_size = universe_cnt or 0

            # Best R2 per ticker in latest snapshot, approaching range
            # Only include tickers where price is AT or BELOW the entry zone
            # (i.e., the discount condition is met — only R2 gate remains)
            rows = [] if _pool_stale else pool.execute("""
                SELECT ticker, candidate_r2, expected_reward_score,
                       candidate_entry_zone, current_price, sector
                FROM (
                    SELECT ticker, candidate_r2, expected_reward_score,
                           candidate_entry_zone, current_price, sector,
                           ROW_NUMBER() OVER (
                               PARTITION BY ticker
                               ORDER BY candidate_r2 DESC, expected_reward_score DESC
                           ) AS rn
                    FROM candidate_pool
                    WHERE snapshot_ts=?
                      AND candidate_r2 BETWEEN 50.0 AND 59.9
                      AND expected_reward_score >= 35
                      AND current_price <= candidate_entry_zone
                )
                WHERE rn = 1
                ORDER BY candidate_r2 DESC
                LIMIT 15
            """, (latest_ts,)).fetchall()
            # Load PriceAuthority prices once for all tickers
            try:
                from price_authority import get_all_prices as _get_all_prices
                _auth_prices = _get_all_prices()
            except Exception:
                _auth_prices = {}

            entries = []
            for r in rows:
                candidate_entry_zone = r["candidate_entry_zone"]
                # PriceAuthority is the single source of truth for current price.
                # Fallback: CSV price, then candidate_pool price.
                ticker = r["ticker"]
                if ticker in _auth_prices and _auth_prices[ticker] > 0:
                    current_price = _auth_prices[ticker]
                else:
                    csv_price, _ = _latest_csv_price(ticker)
                    current_price = csv_price if csv_price is not None else r["current_price"]
                # Re-apply constitutional gate with authoritative price
                if current_price > candidate_entry_zone:
                    continue
                entries.append(dict(
                    ticker=ticker,
                    candidate_r2=r["candidate_r2"],
                    expected_reward_score=r["expected_reward_score"],
                    candidate_entry_zone=candidate_entry_zone,
                    current_price=current_price,
                    sector=r["sector"] or "",
                    distance_to_constitutional=round(60.0 - r["candidate_r2"], 1),
                    need_move_pct=round(
                        (candidate_entry_zone - current_price) / current_price * 100, 1
                    ) if candidate_entry_zone and current_price else 0.0,
                ))
            snap.approaching_entries = entries
        except Exception as exc:
            print(f"[PresentationSnapshot] candidate pool query failed: {exc}")
        pool.close()

    # ── 2. Portfolio Advisor (health narrative only — shown in System Diagnostics)
    advisor = _db(_ADVISOR_DB)
    if advisor:
        try:
            row = advisor.execute(
                "SELECT * FROM advisor_reports ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
            if row:
                snap.health_stars     = row["health_stars"] or "★☆☆☆☆"
                snap.health_label     = row["health_label"] or "Unknown"
                snap.health_narrative = row["health_narrative"] or ""
        except Exception:
            pass
        advisor.close()

    # ── Universe Snapshot (all 27 tickers) ──────────────────────────────────────
    try:
        from universe_snapshot import load_universe_snapshot
        snap.universe_snapshot = load_universe_snapshot()
        snap.universe_size = len(snap.universe_snapshot)
    except Exception:
        snap.universe_snapshot = []

    # ── Approaching Entry exclusivity (must run after universe_snapshot is loaded) ─
    # Exclude tickers that are CURRENTLY live constitutional buy/re-accum signals.
    # "Live" means: R2>=60 AND score>=35 AND price<=constitutional_entry_price right now.
    # Historical RE_ACCUMULATION events must NOT suppress current Near Entry
    # candidates — a ticker that previously had a re-accum event may be
    # approaching the constitutional gate again and must be visible.
    try:
        _prod_snap_path = BASE / "production_decision_snapshot.json"
        live_constitutional_tickers: set[str] = set()
        if _prod_snap_path.exists():
            import json as _json_ps
            _prod = _json_ps.loads(_prod_snap_path.read_text())
            live_constitutional_tickers = {
                d["ticker"] for d in _prod.get("decisions", []) if d.get("eligible")
            }
        signal_tickers = {
            e["ticker"] for e in (snap.new_events_today or [])
        } | live_constitutional_tickers
        if signal_tickers:
            snap.approaching_entries = [
                e for e in snap.approaching_entries
                if e["ticker"] not in signal_tickers
            ]
    except Exception as exc:
        print(f"[PresentationSnapshot] approaching-entry exclusivity failed: {exc}")

    # ── 3. Knowledge Base ─────────────────────────────────────────────────────
    kb = _db(_KB_DB)
    if kb:
        try:
            rows = kb.execute(
                "SELECT question, conclusion, confidence FROM findings "
                "WHERE status='VERIFIED' ORDER BY rowid DESC LIMIT 5"
            ).fetchall()
            snap.research_insights = [
                dict(question=r["question"] or "",
                     conclusion=r["conclusion"] or "",
                     confidence=r["confidence"] or "MEDIUM")
                for r in rows
            ]
        except Exception:
            pass
        try:
            snap.knowledge_count = kb.execute(
                "SELECT COUNT(*) FROM findings"
            ).fetchone()[0]
        except Exception:
            pass
        try:
            snap.experiments_running = kb.execute(
                "SELECT COUNT(*) FROM experiment_registry WHERE status='RUNNING'"
            ).fetchone()[0]
        except Exception:
            pass
        kb.close()

    return snap


def write_presentation_snapshot_json(snap: "PresentationSnapshot", build_hash: str = "") -> "Path":
    """Write canonical presentation_snapshot.json — single source of truth for all layers."""
    import json
    import subprocess

    near_tickers = {e["ticker"] for e in snap.approaching_entries}
    active = [u for u in snap.universe_snapshot if u["status"] in ("ACTIVE", "PREMIUM", "UNDER_REVIEW")]
    active_tickers = {u["ticker"] for u in active}
    future_candidates = [
        u for u in snap.universe_snapshot
        if u["ticker"] not in near_tickers and u["ticker"] not in active_tickers
    ]
    watchlist = [e["ticker"] for e in snap.approaching_entries] + [
        u["ticker"] for u in future_candidates
        if u["ticker"] not in near_tickers
    ]

    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=str(BASE), text=True
        ).strip()
    except Exception:
        commit = ""

    try:
        from scan_context import get_scan_id, build_lineage as _build_lineage
        _scan_id = get_scan_id()
        _lineage = _build_lineage(
            producer=__file__,
            parents=[BASE / "constitutional_opportunity_events.db",
                     BASE / "universe_snapshot.db",
                     BASE / "candidate_pool.db"],
        )
    except Exception:
        _scan_id = ""
        _lineage = {}

    data = {
        "scan_id":             _scan_id,
        "generated_at":        snap.generated_at,
        "price_data_as_of":    snap.price_data_as_of,
        "market_date":         snap.generated_at[:10],
        "market_status":       snap.market_status,
        "build_hash":          build_hash,
        "commit":              commit,
        "_lineage":            _lineage,
        "near_constitutional": snap.approaching_entries,
        "active":              active,
        "re_accumulation":     snap.re_accumulations,
        "future_candidates":   future_candidates,
        "watchlist":           watchlist,
        "universe_snapshot":   snap.universe_snapshot,
        "new_events_today":    list(snap.new_events_today),
        "statistics": {
            "total_timeline_events":    snap.total_events,
            "total_tickers_in_timeline": snap.total_tickers,
            "near_constitutional_count": len(snap.approaching_entries),
            "active_count":             len(active),
            "re_accumulation_count":    len(snap.re_accumulations),
            "future_candidates_count":  len(future_candidates),
            "universe_size":            len(snap.universe_snapshot),
            "new_events_today":         len(snap.new_events_today),
        },
        "health_stars":      snap.health_stars,
        "health_label":      snap.health_label,
        "health_narrative":  snap.health_narrative,
        "research_insights": snap.research_insights,
        "knowledge_count":   snap.knowledge_count,
    }

    out = BASE / "presentation_snapshot.json"
    out.write_text(json.dumps(data, indent=2, default=str))
    print(
        f"[PresentationSnapshot] Wrote presentation_snapshot.json — "
        f"{len(snap.universe_snapshot)} universe, "
        f"{len(snap.approaching_entries)} near, "
        f"{len(active)} active, "
        f"{len(snap.re_accumulations)} re-acc"
    )
    return out
