"""
PortfolioSnapshot — single data object consumed by Dashboard, Email, Telegram.

Sources: portfolio_advisor.db, portfolio_manager.db, research/knowledge/knowledge_base.db
NOT sourced from: egx_research.db, scan_results.json, signal_engine, pattern engine.
"""
from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from time_authority import now_iso as _now_iso
from typing import Any


# ── DB helpers ────────────────────────────────────────────────────────────────

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _scalar(db_path: str, sql: str, params=()):
    try:
        with _db(db_path) as c:
            row = c.execute(sql, params).fetchone()
            return row[0] if row else None
    except Exception:
        return None


def _rows(db_path: str, sql: str, params=()):
    try:
        with _db(db_path) as c:
            return [dict(r) for r in c.execute(sql, params).fetchall()]
    except Exception:
        return []


def _one(db_path: str, sql: str, params=()):
    rows = _rows(db_path, sql, params)
    return rows[0] if rows else {}


# ── Snapshot dataclass ────────────────────────────────────────────────────────

@dataclass
class PortfolioSnapshot:
    # Portfolio health
    health_stars: str                   # e.g. "★★☆☆☆"
    health_label: str                   # e.g. "Needs Attention"
    health_narrative: str

    # Holdings
    held_positions: list[dict]          # [{ticker, sector, entry_price, current_price, return_pct, r2_score}]
    held_count: int

    # Opportunities from advisor
    high_conviction_buys: list[dict]    # [{ticker, decision, reason, confidence, sector, signal_quality_stars}]
    buy_with_awareness: list[dict]
    future_priorities: list[str]        # [ABUK.CA, ...]
    watch_list: list[str]               # [ETEL.CA, ...]

    # Portfolio health metrics
    sector_allocation: dict[str, float] # {Real Estate: 33.3, Industrial: 40.0, ...}
    max_correlation: float
    capacity_used_pct: float
    position_weight_pct: float
    sector_cap_ok: bool

    # Research
    research_insights: list[dict]       # [{question, conclusion, confidence, status}]
    knowledge_count: int
    experiments_running: int

    # Advisor recommendations (full, for detail views)
    recommendations: list[dict]

    # Meta
    generated_at: str


# ── Assembler ─────────────────────────────────────────────────────────────────

def build_portfolio_snapshot() -> PortfolioSnapshot:
    advisor_db  = os.path.join(_BASE, "portfolio_advisor.db")
    manager_db  = os.path.join(_BASE, "portfolio_manager.db")
    kb_db       = os.path.join(_BASE, "research", "knowledge", "knowledge_base.db")

    # ── advisor_reports ────────────────────────────────────────────────────────
    report = _one(advisor_db, "SELECT * FROM advisor_reports ORDER BY rowid DESC LIMIT 1")
    health_stars     = report.get("health_stars", "★☆☆☆☆")
    health_label     = report.get("health_label", "Unknown")
    health_narrative = report.get("health_narrative", "")

    summary = {}
    try:
        summary = json.loads(report.get("summary_json") or "{}")
    except Exception:
        pass

    future_priorities = summary.get("FUTURE_PRIORITY", [])
    watch_list        = summary.get("WATCH", [])

    # ── advisor_recommendations ────────────────────────────────────────────────
    recs = _rows(advisor_db, "SELECT * FROM advisor_recommendations ORDER BY confidence DESC")
    high_conviction_buys = [r for r in recs if r.get("category") in ("HIGH_CONVICTION_BUY", "ADD")]
    buy_with_awareness   = [r for r in recs if r.get("category") in ("BUY_WITH_AWARENESS", "FUTURE_PRIORITY")]
    recommendations      = recs

    # ── portfolio_snapshots ────────────────────────────────────────────────────
    snap = _one(manager_db, "SELECT * FROM portfolio_snapshots ORDER BY rowid DESC LIMIT 1")

    held_positions: list[dict] = []
    try:
        held_positions = json.loads(snap.get("holdings_json") or "[]")
    except Exception:
        pass

    health_json: dict[str, Any] = {}
    try:
        health_json = json.loads(snap.get("portfolio_health_json") or "{}")
    except Exception:
        pass

    sector_allocation   = health_json.get("sector_weights", {})
    max_correlation     = float(health_json.get("max_held_correlation", 0.0))
    capacity_used_pct   = float(health_json.get("capacity_used_pct", 0.0))
    position_weight_pct = float(health_json.get("position_weight_pct", 0.0))
    sector_cap_ok       = bool(health_json.get("sector_cap_ok", True))
    held_count          = int(health_json.get("held_positions", len(held_positions)))

    # ── knowledge_base ─────────────────────────────────────────────────────────
    insights: list[dict] = []
    knowledge_count = 0
    experiments_running = 0
    try:
        insights        = _rows(kb_db, "SELECT question, conclusion, confidence, status FROM findings WHERE status='VERIFIED' ORDER BY rowid DESC LIMIT 5")
        knowledge_count = _scalar(kb_db, "SELECT COUNT(*) FROM findings") or 0
        try:
            experiments_running = _scalar(kb_db, "SELECT COUNT(*) FROM experiment_registry WHERE status='RUNNING'") or 0
        except Exception:
            experiments_running = 0
    except Exception:
        pass

    return PortfolioSnapshot(
        health_stars=health_stars,
        health_label=health_label,
        health_narrative=health_narrative,
        held_positions=held_positions,
        held_count=held_count,
        high_conviction_buys=high_conviction_buys,
        buy_with_awareness=buy_with_awareness,
        future_priorities=future_priorities,
        watch_list=watch_list,
        sector_allocation=sector_allocation,
        max_correlation=max_correlation,
        capacity_used_pct=capacity_used_pct,
        position_weight_pct=position_weight_pct,
        sector_cap_ok=sector_cap_ok,
        research_insights=insights,
        knowledge_count=knowledge_count,
        experiments_running=experiments_running,
        recommendations=recommendations,
        generated_at=_now_iso(),
    )
