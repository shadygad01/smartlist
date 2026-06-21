"""
Constitutional Presentation Snapshot V3
Single data contract consumed by dashboard_v2, email_v2, telegram_v2.
Sources: constitutional_buy_registry.db, portfolio_advisor.db, knowledge_base.db.
Historical BUY status NEVER depends on today's R2 — always uses buy_date snapshot.
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).parent.parent

_ADVISOR_DB  = BASE / "portfolio_advisor.db"
_MANAGER_DB  = BASE / "portfolio_manager.db"
_KB_DB       = BASE / "research" / "knowledge" / "knowledge_base.db"


def _db(path: Path) -> sqlite3.Connection | None:
    if not path.exists():
        return None
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _clean_reason(text: str) -> str:
    """Remove internal factor score references (R2=75.1, R5=42.0, etc.) from advisor text."""
    if not text:
        return text
    # Remove standalone "(R2=75.1)" references first
    text = re.sub(r'\(\s*R\d+=[\d.]+\s*\)', '', text)
    # Remove "R2=75.1 (Label)." or "R2=75.1." or "R2=75.1," or "R2=75.1"
    text = re.sub(r'\bR\d+=[\d.]+\s*(?:\([^)]*\))?[.,]?\s*', '', text)
    # Fix floating punctuation like "quality . Blocked" → "quality. Blocked"
    text = re.sub(r'\s+([,.])', r'\1', text)
    # Collapse multiple spaces
    text = re.sub(r'  +', ' ', text)
    return text.strip()


@dataclass
class PresentationSnapshot:
    # Portfolio health (from advisor)
    health_stars:     str = "★☆☆☆☆"
    health_label:     str = "Unknown"
    health_narrative: str = ""

    # Constitutional BUY Registry — PRIMARY display (all N, never filtered by today's R2)
    constitutional_buys:  list[dict] = field(default_factory=list)
    total_buys:           int = 0
    new_buys_today:       list[dict] = field(default_factory=list)

    # Legacy fields — kept for backward compatibility with advisor sections
    held_positions:   list[dict] = field(default_factory=list)
    held_count:       int = 0
    opportunities:    list[dict] = field(default_factory=list)
    future_priorities: list[dict] = field(default_factory=list)
    watch_list:       list[str] = field(default_factory=list)

    # Portfolio metrics (informational only — not used for BUY gating)
    sector_allocation:    dict[str, float] = field(default_factory=dict)
    max_correlation:      float = 0.0
    capacity_used_pct:    float = 0.0
    position_weight_pct:  float = 0.0
    sector_cap_ok:        bool = True

    # Research & knowledge
    research_insights:    list[dict] = field(default_factory=list)
    knowledge_count:      int = 0
    experiments_running:  int = 0

    # Meta
    generated_at: str = ""


def build_presentation_snapshot() -> PresentationSnapshot:
    snap = PresentationSnapshot(generated_at=datetime.now().isoformat())

    # ── 0. Constitutional BUY Registry (V3) ──────────────────────────────────
    try:
        import sys
        sys.path.insert(0, str(BASE))
        from constitutional_opportunity_engine import get_registry, get_new_buys_today
        snap.constitutional_buys = get_registry()
        snap.total_buys          = len(snap.constitutional_buys)
        snap.new_buys_today      = get_new_buys_today()
    except Exception:
        pass

    # ── 1. Portfolio Advisor ──────────────────────────────────────────────────
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

        try:
            recs = advisor.execute(
                "SELECT * FROM advisor_recommendations ORDER BY confidence DESC"
            ).fetchall()
            for r in recs:
                cat     = (r["category"] or "").upper()
                ticker  = r["ticker"] or ""
                reason  = _clean_reason(r["reason"] or "")
                sector  = r["sector"] or ""
                decision = r["decision"] or ""
                confidence = r["confidence"] or "MEDIUM"

                rec = dict(
                    ticker=ticker,
                    sector=sector,
                    decision=decision,
                    reason=reason,
                    confidence=confidence,
                    category=cat,
                )

                if cat == "ADD":
                    snap.opportunities.append(rec)
                elif cat == "FUTURE_PRIORITY":
                    snap.future_priorities.append(rec)
                elif cat in ("WATCH",):
                    snap.watch_list.append(ticker)

        except Exception:
            pass

        advisor.close()

    # ── 2. Portfolio Manager ──────────────────────────────────────────────────
    manager = _db(_MANAGER_DB)
    if manager:
        try:
            cols = [d[0] for d in manager.execute(
                "SELECT * FROM portfolio_snapshots LIMIT 1"
            ).description]
            row = manager.execute(
                "SELECT * FROM portfolio_snapshots ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
            if row:
                d = dict(zip(cols, row))

                # Holdings — column is holdings_json
                holdings_raw = d.get("holdings_json") or d.get("positions_json") or "[]"
                health_raw   = d.get("portfolio_health_json") or d.get("health_json") or "{}"
                sector_raw   = d.get("sector_alloc_json") or "{}"

                positions = json.loads(holdings_raw)
                health    = json.loads(health_raw)

                held = []
                for p in positions:
                    entry   = float(p.get("entry_price") or 0)
                    current = float(p.get("current_price") or entry)
                    ret_pct = ((current - entry) / entry * 100) if entry else 0.0
                    held.append(dict(
                        ticker=p.get("ticker") or "",
                        sector=p.get("sector") or "Other",
                        entry_price=entry,
                        current_price=current,
                        return_pct=ret_pct,
                    ))

                held.sort(key=lambda x: x["return_pct"], reverse=True)
                snap.held_positions = held
                snap.held_count     = len(held)

                # Sector allocation — prefer pre-computed field
                sector_alloc = json.loads(sector_raw)
                if not sector_alloc:
                    counts: dict[str, int] = {}
                    for p in held:
                        counts[p["sector"]] = counts.get(p["sector"], 0) + 1
                    total = len(held) or 1
                    sector_alloc = {s: round(n / total * 100, 1) for s, n in counts.items()}
                snap.sector_allocation = sector_alloc

                snap.max_correlation   = float(health.get("max_held_correlation") or health.get("max_correlation") or 0)
                snap.capacity_used_pct = float(health.get("capacity_used_pct") or 0)
                snap.position_weight_pct = float(health.get("position_weight_pct") or 0)
                snap.sector_cap_ok = bool(health.get("sector_cap_ok", True))

        except Exception:
            pass

        manager.close()

    # ── 3. Knowledge Base ─────────────────────────────────────────────────────
    kb = _db(_KB_DB)
    if kb:
        try:
            rows = kb.execute(
                "SELECT question, conclusion, confidence, status "
                "FROM findings WHERE status='VERIFIED' ORDER BY rowid DESC LIMIT 5"
            ).fetchall()
            snap.research_insights = [
                dict(
                    question=r["question"] or "",
                    conclusion=r["conclusion"] or "",
                    confidence=r["confidence"] or "MEDIUM",
                )
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
