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

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))
from time_authority import now_cairo, now_iso, today_cairo, is_trading_day as _is_trading_day, _EET as _CAIRO_TZ

_ADVISOR_DB = BASE / "portfolio_advisor.db"
_KB_DB      = BASE / "research" / "knowledge" / "knowledge_base.db"
_POOL_DB    = BASE / "candidate_pool.db"

# EGX: Sun-Thu 10:00-15:30, UTC+2 (no DST in Egypt)
_CAIRO_OPEN  = (10, 0)
_CAIRO_CLOSE = (15, 30)
_TRADING_DAYS = {0, 1, 2, 3, 6}  # Mon=0 Sun=6; EGX: Sun-Thu


def _db(path: Path) -> sqlite3.Connection | None:
    if not path.exists():
        return None
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _clean_reason(text: str) -> str:
    if not text:
        return text
    text = re.sub(r'\(\s*R\d+=[\d.]+\s*\)', '', text)
    text = re.sub(r'\bR\d+=[\d.]+\s*(?:\([^)]*\))?[.,]?\s*', '', text)
    text = re.sub(r'\s+([,.])', r'\1', text)
    text = re.sub(r'  +', ' ', text)
    return text.strip()


def _market_status() -> str:
    now_cairo_dt = now_cairo()
    dow = now_cairo_dt.weekday()  # Mon=0, Sun=6
    h, m = now_cairo_dt.hour, now_cairo_dt.minute
    mins = h * 60 + m
    if dow not in _TRADING_DAYS:
        return "CLOSED (Weekend)"
    open_mins  = _CAIRO_OPEN[0]  * 60 + _CAIRO_OPEN[1]
    close_mins = _CAIRO_CLOSE[0] * 60 + _CAIRO_CLOSE[1]
    if mins < open_mins:
        return f"PRE-MARKET (opens {_CAIRO_OPEN[0]:02d}:{_CAIRO_OPEN[1]:02d})"
    if mins > close_mins:
        return "CLOSED (After Hours)"
    return "OPEN"


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

    # Constitutional Opportunity Timeline — PRIMARY (all N events, immutable)
    timeline:          list[dict] = field(default_factory=list)
    total_events:      int = 0
    total_tickers:     int = 0
    new_events_today:  list[dict] = field(default_factory=list)
    first_buys:        list[dict] = field(default_factory=list)
    re_accumulations:  list[dict] = field(default_factory=list)

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
    generated_at: str = ""

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
    snap = PresentationSnapshot(
        generated_at=now_iso(),
        market_status=_market_status(),
    )

    # ── 0. Constitutional Opportunity Timeline ────────────────────────────────
    try:
        import sys
        sys.path.insert(0, str(BASE))
        from constitutional_timeline_engine import (
            get_timeline, get_new_events_today, get_analytics, get_leaderboards
        )
        tl = get_timeline()
        an = get_analytics()
        lb = get_leaderboards(timeline=tl, analytics=an)

        snap.timeline         = tl
        snap.total_events     = len(tl)
        snap.total_tickers    = len(set(e["ticker"] for e in tl))
        snap.new_events_today = get_new_events_today()
        snap.first_buys       = [e for e in tl if e["event_type"] == "FIRST_BUY"]
        snap.re_accumulations = [e for e in tl if e["event_type"] == "RE_ACCUMULATION"]
        snap.analytics        = an
        snap.leaderboards     = lb

        # Build constitutional leaders from analytics + timeline
        leaders = []
        for ticker, a in an.items():
            ticker_events = [e for e in tl if e["ticker"] == ticker]
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
            universe_cnt = pool.execute(
                "SELECT COUNT(DISTINCT ticker) FROM candidate_pool WHERE snapshot_ts=?",
                (latest_ts,)
            ).fetchone()[0]
            snap.universe_size = universe_cnt or 0

            # Best R2 per ticker in latest snapshot, approaching range
            # Only include tickers where price is AT or BELOW the entry zone
            # (i.e., the discount condition is met — only R2 gate remains)
            rows = pool.execute("""
                SELECT ticker, MAX(r2_score) as r2_score, MAX(final_score) as max_score,
                       entry_price, current_price, sector
                FROM candidate_pool
                WHERE snapshot_ts=?
                  AND r2_score BETWEEN 50.0 AND 59.9
                  AND current_price <= entry_price
                GROUP BY ticker
                HAVING max_score >= 35
                ORDER BY r2_score DESC
                LIMIT 15
            """, (latest_ts,)).fetchall()
            snap.approaching_entries = [
                dict(
                    ticker=r["ticker"],
                    r2_score=r["r2_score"],
                    final_score=r["max_score"],
                    entry_price=r["entry_price"],
                    current_price=r["current_price"],
                    sector=r["sector"] or "",
                    distance_to_constitutional=round(60.0 - r["r2_score"], 1),
                    need_move_pct=round(
                        (r["entry_price"] - r["current_price"]) / r["entry_price"] * 100, 1
                    ) if r["entry_price"] else 0.0,
                )
                for r in rows
            ]
        except Exception:
            pass
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

    data = {
        "generated_at":        snap.generated_at,
        "market_date":         snap.generated_at[:10],
        "market_status":       snap.market_status,
        "build_hash":          build_hash,
        "commit":              commit,
        "near_constitutional": snap.approaching_entries,
        "active":              active,
        "re_accumulation":     snap.re_accumulations,
        "future_candidates":   future_candidates,
        "watchlist":           watchlist,
        "universe_snapshot":   snap.universe_snapshot,
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
