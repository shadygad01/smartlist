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
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).parent.parent

_ADVISOR_DB = BASE / "portfolio_advisor.db"
_KB_DB      = BASE / "research" / "knowledge" / "knowledge_base.db"


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


@dataclass
class PresentationSnapshot:
    # Health (from advisor — informational only)
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

    # Research & knowledge
    research_insights:   list[dict] = field(default_factory=list)
    knowledge_count:     int = 0
    experiments_running: int = 0

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
    snap = PresentationSnapshot(generated_at=datetime.now().isoformat())

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

        # Legacy aliases
        snap.constitutional_buys = snap.first_buys
        snap.total_buys          = len(snap.first_buys)
        snap.new_buys_today      = [e for e in snap.new_events_today
                                    if e["event_type"] == "FIRST_BUY"]
    except Exception:
        pass

    # ── 1. Portfolio Advisor (health narrative only) ──────────────────────────
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

    # ── 2. Knowledge Base ─────────────────────────────────────────────────────
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
