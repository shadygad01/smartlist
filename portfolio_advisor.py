"""
Constitutional Portfolio Advisor V1

Reads ONLY from candidate_pool.db and portfolio_manager.db.
NEVER modifies any upstream layer (engine, pool builder, portfolio manager).
NEVER rebuilds the portfolio — only helps evolve it.

Output categories: KEEP, ADD, BUY_RESERVE, WATCH, CONSIDER_REDUCING, EXIT_CANDIDATE
Portfolio Health Grade: A / B / C
"""

import sqlite3
import json
import hashlib
from datetime import datetime, date
from typing import Optional

POOL_DB = "candidate_pool.db"
MGR_DB = "portfolio_manager.db"
ADVISOR_DB = "portfolio_advisor.db"

MAX_POSITIONS = 15
MIN_POSITIONS = 12
SECTOR_CAP = 0.25
CORR_CAP = 0.80
R2_KEEP_MIN = 45.0       # below this → CONSIDER_REDUCING candidate
R2_ADD_MIN = 60.0        # threshold for ADD recommendation
R2_RESERVE_MIN = 50.0    # threshold for BUY_RESERVE
R2_WATCH_MIN = 40.0      # threshold for WATCH
RETURN_EXIT_THRESHOLD = 75.0   # positions with >75% gain = potential EXIT candidate
RETURN_REDUCE_THRESHOLD = 50.0 # positions with >50% gain and low R2 = CONSIDER_REDUCING

# ---------------------------------------------------------------------------
# DB INIT
# ---------------------------------------------------------------------------

def _init_advisor_db(conn: sqlite3.Connection):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS advisor_recommendations (
        rec_id          TEXT PRIMARY KEY,
        report_date     TEXT NOT NULL,
        ticker          TEXT NOT NULL,
        category        TEXT NOT NULL,
        decision        TEXT NOT NULL,
        reason          TEXT NOT NULL,
        confidence      TEXT NOT NULL,
        portfolio_impact TEXT NOT NULL,
        suggested_action TEXT NOT NULL,
        expected_benefit TEXT NOT NULL,
        r2_score        REAL,
        current_return_pct REAL,
        sector          TEXT,
        created_at      TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS advisor_reports (
        report_id       TEXT PRIMARY KEY,
        report_date     TEXT NOT NULL,
        health_grade    TEXT NOT NULL,
        health_detail   TEXT NOT NULL,
        summary_json    TEXT NOT NULL,
        full_report_text TEXT NOT NULL,
        created_at      TEXT NOT NULL
    );
    """)
    conn.commit()


def _rec_id(report_date: str, ticker: str, category: str) -> str:
    raw = f"{report_date}|{ticker}|{category}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# DATA LOADING
# ---------------------------------------------------------------------------

def _load_latest_snapshot(mgr_conn: sqlite3.Connection) -> dict:
    row = mgr_conn.execute(
        "SELECT * FROM portfolio_snapshots ORDER BY rowid DESC LIMIT 1"
    ).fetchone()
    if not row:
        return {}
    cols = [d[1] for d in mgr_conn.execute("PRAGMA table_info(portfolio_snapshots)")]
    snap = dict(zip(cols, row))
    for key in ("holdings_json", "reserve_json", "watch_json",
                "sector_alloc_json", "replacement_queue_json",
                "portfolio_health_json", "corr_matrix_json"):
        if snap.get(key):
            snap[key] = json.loads(snap[key])
    return snap


def _load_candidate_states(mgr_conn: sqlite3.Connection) -> list[dict]:
    rows = mgr_conn.execute(
        "SELECT ticker, state, r2_score, sector, decision_reason, "
        "portfolio_impact, suggested_action, entry_price "
        "FROM candidate_states"
    ).fetchall()
    cols = ["ticker", "state", "r2_score", "sector", "decision_reason",
            "portfolio_impact", "suggested_action", "entry_price"]
    return [dict(zip(cols, r)) for r in rows]


def _load_best_pool_entry(pool_conn: sqlite3.Connection, ticker: str) -> Optional[dict]:
    """Return the most recent / highest R2 pool entry for a ticker."""
    row = pool_conn.execute(
        "SELECT ticker, signal_date, entry_price, r2_score, r3_score, r4_score, "
        "r5_score, r6_score, r7_score, r8_score, final_score, sector, "
        "discount_depth, distance_from_eq, atr20, volatility20 "
        "FROM candidate_pool "
        "WHERE ticker = ? "
        "ORDER BY r2_score DESC, signal_date DESC LIMIT 1",
        (ticker,)
    ).fetchone()
    if not row:
        return None
    cols = ["ticker", "signal_date", "entry_price", "r2_score", "r3_score",
            "r4_score", "r5_score", "r6_score", "r7_score", "r8_score",
            "final_score", "sector", "discount_depth", "distance_from_eq",
            "atr20", "volatility20"]
    return dict(zip(cols, row))


# ---------------------------------------------------------------------------
# ADVISOR LOGIC
# ---------------------------------------------------------------------------

def _grade_health(health: dict, sector_alloc: dict) -> tuple[str, list[str]]:
    """
    Returns (grade, issues_list).
    A = healthy, B = minor issues, C = significant concerns.
    """
    issues = []
    held = health.get("held_positions", 0)
    max_sector = max(sector_alloc.values(), default=0)

    if max_sector > SECTOR_CAP * 100:
        issues.append(f"Sector concentration {max_sector:.1f}% (cap {int(SECTOR_CAP*100)}%)")
    if held > MAX_POSITIONS:
        issues.append(f"Over capacity: {held}/{MAX_POSITIONS} positions")
    if held < MIN_POSITIONS:
        issues.append(f"Under-deployed: {held}/{MIN_POSITIONS} min positions")
    if not health.get("corr_cap_ok", True):
        issues.append("Correlation breach in held positions")

    corr_max = health.get("max_held_correlation", 0)
    if corr_max >= 0.75:
        issues.append(f"Correlation elevated: max={corr_max:.3f}")

    if len(issues) == 0:
        return "A", []
    elif len(issues) <= 2:
        return "B", issues
    else:
        return "C", issues


def _classify_held(holding: dict, sector_alloc: dict, corr_matrix: dict,
                   all_held_tickers: list[str]) -> tuple[str, str, str, str, str, str]:
    """
    Returns (category, decision, reason, confidence, portfolio_impact, suggested_action, expected_benefit)
    for a single held position.
    """
    ticker = holding["ticker"]
    ret = holding.get("return_pct", 0.0)
    r2 = holding.get("r2_score", 0.0)
    sector = holding.get("sector", "Unknown")
    sector_pct = sector_alloc.get(sector, 0.0)

    # Compute max correlation with other held positions
    corr_row = corr_matrix.get(ticker, {})
    peers = [t for t in all_held_tickers if t != ticker]
    max_corr = max((corr_row.get(t, 0.0) for t in peers), default=0.0)

    # Decision logic
    if ret >= RETURN_EXIT_THRESHOLD and r2 < R2_KEEP_MIN:
        category = "EXIT_CANDIDATE"
        decision = "Consider exiting"
        reason = (f"Position up {ret:.1f}% with weak current setup (R2={r2:.1f}). "
                  "Discount zone geometry likely no longer favourable.")
        confidence = "HIGH" if ret >= 90 else "MEDIUM"
        portfolio_impact = (f"Frees 1 slot ({100/max(len(all_held_tickers),1):.1f}% weight). "
                            f"Sector {sector} drops to {max(0, sector_pct - 100/max(len(all_held_tickers),1)):.1f}%.")
        suggested_action = "Exit position at market open. Review ABUK.CA (BUY_RESERVE) as replacement."
        expected_benefit = "Capture realised gain, redeploy into higher-R2 setup."

    elif ret >= RETURN_REDUCE_THRESHOLD and r2 < R2_KEEP_MIN and sector_pct > SECTOR_CAP * 100:
        category = "CONSIDER_REDUCING"
        decision = "Consider reducing"
        reason = (f"Significant gain ({ret:.1f}%) with weak setup (R2={r2:.1f}) "
                  f"in overweight sector ({sector} {sector_pct:.1f}%).")
        confidence = "MEDIUM"
        portfolio_impact = f"Partial exit reduces {sector} concentration."
        suggested_action = "Reduce to half-position or exit if better R2 candidate available."
        expected_benefit = "Reduce sector risk, preserve partial gain, create room for new signal."

    elif max_corr > CORR_CAP and r2 < R2_KEEP_MIN:
        category = "CONSIDER_REDUCING"
        decision = "Review for correlation"
        reason = (f"Highest held correlation={max_corr:.3f} (cap {CORR_CAP}). "
                  f"R2={r2:.1f} — weakest of correlated pair.")
        confidence = "MEDIUM"
        portfolio_impact = "Reduces portfolio correlation. Frees 1 slot."
        suggested_action = "Exit weakest R2 of correlated pair if new signal available."
        expected_benefit = "Lower drawdown correlation in stress scenario."

    else:
        category = "KEEP"
        decision = "Hold"
        reason = (f"R2={r2:.1f}, return={ret:+.1f}%. "
                  "No exit trigger reached. Sector and correlation within policy.")
        confidence = "HIGH" if r2 >= 50 else "MEDIUM"
        portfolio_impact = f"Maintains {sector} sector exposure at {sector_pct:.1f}%."
        suggested_action = "No action required. Monitor weekly."
        expected_benefit = "Continue capturing upside while holding discount-zone position."

    return category, decision, reason, confidence, portfolio_impact, suggested_action, expected_benefit


def _classify_reserve(cand: dict) -> tuple[str, str, str, str, str, str]:
    r2 = cand.get("r2_score", 0.0)
    sector = cand.get("sector", "Unknown")
    reason_src = cand.get("decision_reason", "")

    if r2 >= R2_ADD_MIN:
        category = "ADD"
        decision = "Add when capacity opens"
        confidence = "HIGH"
    else:
        category = "BUY_RESERVE"
        decision = "Reserve — add on sector/corr clearance"
        confidence = "MEDIUM"

    ticker = cand.get("ticker", "?")
    reason = f"R2={r2:.1f}. {reason_src}"
    portfolio_impact = f"Adding {ticker} increases {sector} exposure."
    suggested_action = cand.get("suggested_action", "Buy if portfolio has room.")
    expected_benefit = "Adds high-quality discount entry to portfolio."
    return category, decision, reason, confidence, portfolio_impact, suggested_action, expected_benefit


def _classify_watch(cand: dict) -> tuple[str, str, str, str, str, str]:
    r2 = cand.get("r2_score", 0.0)
    sector = cand.get("sector", "Unknown")
    reason_src = cand.get("decision_reason", "")

    category = "WATCH"
    decision = "Monitor — not ready for entry"
    reason = f"R2={r2:.1f}. {reason_src}"
    confidence = "LOW" if r2 < 45 else "MEDIUM"
    portfolio_impact = "No current impact."
    suggested_action = "Track R2 trend. Move to ADD if R2 >= 60 and capacity exists."
    expected_benefit = "Maintains awareness of developing setups."
    return category, decision, reason, confidence, portfolio_impact, suggested_action, expected_benefit


# ---------------------------------------------------------------------------
# REPORT BUILDER
# ---------------------------------------------------------------------------

def _build_report(
    report_date: str,
    grade: str,
    grade_issues: list[str],
    recs: list[dict],
    snapshot: dict,
) -> str:
    health = snapshot.get("portfolio_health_json", {})
    sector_alloc = snapshot.get("sector_alloc_json", {})

    lines = []
    lines.append("=" * 68)
    lines.append(f"  CONSTITUTIONAL PORTFOLIO ADVISOR — {report_date}")
    lines.append(f"  Portfolio Health Grade: {grade}")
    lines.append("=" * 68)

    if grade_issues:
        lines.append("")
        lines.append("HEALTH ISSUES:")
        for iss in grade_issues:
            lines.append(f"  ! {iss}")

    def section(title, cats):
        filtered = [r for r in recs if r["category"] in cats]
        if not filtered:
            return
        lines.append("")
        lines.append(f"--- {title} ({len(filtered)}) ---")
        for r in filtered:
            lines.append(f"  {r['ticker']:<10}  [{r['confidence']}]  {r['decision']}")
            lines.append(f"             Reason: {r['reason']}")
            lines.append(f"             Action: {r['suggested_action']}")
            lines.append(f"             Benefit: {r['expected_benefit']}")
            if r.get("current_return_pct") is not None:
                lines.append(f"             Return: {r['current_return_pct']:+.1f}%  R2={r.get('r2_score',0):.1f}")
            lines.append("")

    section("KEEP", ["KEEP"])
    section("ADD — BUY IMMEDIATELY WHEN SLOT OPENS", ["ADD"])
    section("BUY_RESERVE — WAITING FOR CLEARANCE", ["BUY_RESERVE"])
    section("WATCH — MONITOR", ["WATCH"])
    section("CONSIDER_REDUCING", ["CONSIDER_REDUCING"])
    section("EXIT_CANDIDATES", ["EXIT_CANDIDATE"])

    lines.append("--- SECTOR ALLOCATION ---")
    for sec, pct in sorted(sector_alloc.items(), key=lambda x: -x[1]):
        flag = " !" if pct > SECTOR_CAP * 100 else "  "
        lines.append(f"  {flag}{sec:<18} {pct:.1f}%")

    lines.append("")
    lines.append("--- PORTFOLIO STATS ---")
    lines.append(f"  Held:          {health.get('held_positions','?')}/{MAX_POSITIONS}")
    lines.append(f"  Max corr:      {health.get('max_held_correlation','?'):.3f}  (cap {CORR_CAP})")
    lines.append(f"  Position size: {health.get('position_weight_pct','?'):.1f}%  (equal weight)")

    lines.append("")
    lines.append("--- TODAY SUMMARY ---")
    counts = {}
    for r in recs:
        counts[r["category"]] = counts.get(r["category"], 0) + 1
    for cat in ["KEEP", "ADD", "BUY_RESERVE", "WATCH", "CONSIDER_REDUCING", "EXIT_CANDIDATE"]:
        if counts.get(cat, 0):
            lines.append(f"  {cat:<22} {counts[cat]}")

    lines.append("")
    lines.append(f"  Grade {grade} — {', '.join(grade_issues) if grade_issues else 'All checks passed.'}")
    lines.append("=" * 68)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# MAIN ADVISOR
# ---------------------------------------------------------------------------

def run_portfolio_advisor(
    report_date: Optional[str] = None,
    mgr_db: str = MGR_DB,
    pool_db: str = POOL_DB,
    advisor_db: str = ADVISOR_DB,
) -> dict:
    if report_date is None:
        report_date = date.today().isoformat()

    pool_conn = sqlite3.connect(pool_db)
    mgr_conn = sqlite3.connect(mgr_db)
    adv_conn = sqlite3.connect(advisor_db)
    _init_advisor_db(adv_conn)

    try:
        snapshot = _load_latest_snapshot(mgr_conn)
        states = _load_candidate_states(mgr_conn)

        holdings = snapshot.get("holdings_json", [])
        sector_alloc = snapshot.get("sector_alloc_json", {})
        health = snapshot.get("portfolio_health_json", {})
        corr_matrix = snapshot.get("corr_matrix_json", {})
        all_held_tickers = [h["ticker"] for h in holdings]

        grade, grade_issues = _grade_health(health, sector_alloc)

        recs = []

        # Classify HELD positions
        for h in holdings:
            ticker = h["ticker"]
            cat, decision, reason, conf, impact, action, benefit = _classify_held(
                h, sector_alloc, corr_matrix, all_held_tickers
            )
            # Enrich with latest pool data if available
            pool_entry = _load_best_pool_entry(pool_conn, ticker)
            r2 = pool_entry["r2_score"] if pool_entry else h.get("r2_score", 0.0)

            rec = {
                "rec_id": _rec_id(report_date, ticker, cat),
                "report_date": report_date,
                "ticker": ticker,
                "category": cat,
                "decision": decision,
                "reason": reason,
                "confidence": conf,
                "portfolio_impact": impact,
                "suggested_action": action,
                "expected_benefit": benefit,
                "r2_score": r2,
                "current_return_pct": h.get("return_pct"),
                "sector": h.get("sector"),
            }
            recs.append(rec)

        # Classify BUY_RESERVE from candidate_states
        for s in states:
            if s["state"] not in ("BUY_RESERVE", "PRIMARY_BUY"):
                continue
            cat, decision, reason, conf, impact, action, benefit = _classify_reserve(s)
            rec = {
                "rec_id": _rec_id(report_date, s["ticker"], cat),
                "report_date": report_date,
                "ticker": s["ticker"],
                "category": cat,
                "decision": decision,
                "reason": reason,
                "confidence": conf,
                "portfolio_impact": impact,
                "suggested_action": action,
                "expected_benefit": benefit,
                "r2_score": s.get("r2_score"),
                "current_return_pct": None,
                "sector": s.get("sector"),
            }
            recs.append(rec)

        # Classify WATCH
        for s in states:
            if s["state"] != "WATCH":
                continue
            cat, decision, reason, conf, impact, action, benefit = _classify_watch(s)
            rec = {
                "rec_id": _rec_id(report_date, s["ticker"], cat),
                "report_date": report_date,
                "ticker": s["ticker"],
                "category": cat,
                "decision": decision,
                "reason": reason,
                "confidence": conf,
                "portfolio_impact": impact,
                "suggested_action": action,
                "expected_benefit": benefit,
                "r2_score": s.get("r2_score"),
                "current_return_pct": None,
                "sector": s.get("sector"),
            }
            recs.append(rec)

        # Persist recommendations (append-only: INSERT OR IGNORE)
        now = datetime.now().isoformat()
        for rec in recs:
            adv_conn.execute(
                """INSERT OR IGNORE INTO advisor_recommendations
                   (rec_id, report_date, ticker, category, decision, reason,
                    confidence, portfolio_impact, suggested_action, expected_benefit,
                    r2_score, current_return_pct, sector, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (rec["rec_id"], rec["report_date"], rec["ticker"], rec["category"],
                 rec["decision"], rec["reason"], rec["confidence"],
                 rec["portfolio_impact"], rec["suggested_action"],
                 rec["expected_benefit"], rec["r2_score"],
                 rec["current_return_pct"], rec["sector"], now)
            )

        # Build and persist full report
        report_text = _build_report(report_date, grade, grade_issues, recs, snapshot)
        summary = {
            cat: [r["ticker"] for r in recs if r["category"] == cat]
            for cat in ["KEEP", "ADD", "BUY_RESERVE", "WATCH", "CONSIDER_REDUCING", "EXIT_CANDIDATE"]
        }
        report_id = _rec_id(report_date, "REPORT", grade)
        adv_conn.execute(
            """INSERT OR IGNORE INTO advisor_reports
               (report_id, report_date, health_grade, health_detail,
                summary_json, full_report_text, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (report_id, report_date, grade, json.dumps(grade_issues),
             json.dumps(summary), report_text, now)
        )
        adv_conn.commit()

        return {
            "report_date": report_date,
            "health_grade": grade,
            "health_issues": grade_issues,
            "recommendations": recs,
            "summary": summary,
            "report_text": report_text,
        }

    finally:
        pool_conn.close()
        mgr_conn.close()
        adv_conn.close()


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    rd = sys.argv[1] if len(sys.argv) > 1 else None
    result = run_portfolio_advisor(report_date=rd)
    print(result["report_text"])
