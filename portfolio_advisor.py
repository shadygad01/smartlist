"""
Constitutional Portfolio Intelligence + Advisor V2

PHILOSOPHY
- Every constitutional BUY remains a BUY. No BUY is ever rejected.
- Two independent evaluations: Signal Quality + Portfolio Fit.
- Language of an experienced portfolio manager, never an optimizer.
- Portfolio Health expressed as stars + narrative, never A/B/C grade.
- Append-only history. Reads ONLY from candidate_pool.db and portfolio_manager.db.
- NEVER modifies any upstream layer.
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
SECTOR_PREFERRED_MAX = 25.0   # preferred ceiling — breach is noted, never blocks
CORR_CAP = 0.80
RETURN_EVOLUTION_THRESHOLD = 75.0   # positions with >75% gain noted in evolution section

# ---------------------------------------------------------------------------
# STAR SCALES
# ---------------------------------------------------------------------------

# Signal Quality — based on R2 score (entry discount quality)
def _signal_quality_stars(r2: float) -> tuple[str, str]:
    """Map R2 score to (star string, quality label) for signal quality display."""
    if r2 >= 75:   return "★★★★★", "Exceptional"
    if r2 >= 65:   return "★★★★☆", "Strong"
    if r2 >= 55:   return "★★★☆☆", "Good"
    if r2 >= 45:   return "★★☆☆☆", "Acceptable"
    return              "★☆☆☆☆", "Weak"


# Portfolio Fit — based on sector concentration + correlation + capacity
def _portfolio_fit_stars(
    sector: str,
    sector_pct: float,
    max_corr: float,
    held_count: int,
) -> tuple[str, str]:
    """Map sector concentration, correlation, and capacity to (star string, fit label)."""
    penalty = 0
    if sector_pct >= SECTOR_PREFERRED_MAX * 1.5:  penalty += 2   # seriously elevated
    elif sector_pct > SECTOR_PREFERRED_MAX:        penalty += 1   # mildly elevated
    if max_corr >= CORR_CAP:                       penalty += 2
    elif max_corr >= 0.65:                         penalty += 1
    if held_count >= MAX_POSITIONS:                penalty += 1

    fit_score = max(0, 5 - penalty)
    labels = {5: "★★★★★", 4: "★★★★☆", 3: "★★★☆☆", 2: "★★☆☆☆", 1: "★☆☆☆☆", 0: "★☆☆☆☆"}
    descs  = {5: "Excellent Fit", 4: "Good Fit", 3: "Neutral Fit",
              2: "Cautious Fit", 1: "Low Fit", 0: "Low Fit"}
    return labels[fit_score], descs[fit_score]


# Portfolio Health — based on sector concentration + correlation + fill rate
def _portfolio_health(health: dict, sector_alloc: dict) -> tuple[str, str, list[str]]:
    """Evaluate portfolio health and return (stars, label, observation narratives)."""
    observations = []
    penalty = 0

    held = health.get("held_positions", 0)
    max_corr = health.get("max_held_correlation", 0.0)
    max_sector = max(sector_alloc.values(), default=0)
    max_sector_name = max(sector_alloc, key=sector_alloc.get, default="")

    if max_sector > SECTOR_PREFERRED_MAX * 1.5:
        penalty += 2
        observations.append(
            f"{max_sector_name} exposure is significantly above the preferred level "
            f"({max_sector:.1f}%). Future additions should naturally reduce concentration."
        )
    elif max_sector > SECTOR_PREFERRED_MAX:
        penalty += 1
        observations.append(
            f"{max_sector_name} exposure is above the preferred level ({max_sector:.1f}%). "
            "No immediate action required."
        )

    if max_corr >= CORR_CAP:
        penalty += 2
        observations.append(
            f"Maximum pairwise correlation is elevated ({max_corr:.3f}). "
            "Review closely correlated pairs before adding further positions in the same theme."
        )
    elif max_corr >= 0.65:
        penalty += 1
        observations.append(
            f"Maximum pairwise correlation is moderate ({max_corr:.3f}). Within acceptable range."
        )

    if held > MAX_POSITIONS:
        penalty += 1
        observations.append(f"Portfolio is at capacity ({held} positions). Additions require an exit first.")
    elif held < MIN_POSITIONS:
        penalty += 1
        observations.append(f"Portfolio is under-deployed ({held}/{MIN_POSITIONS} target). Opportunity to add.")

    health_score = max(1, 5 - penalty)
    stars = {5: "★★★★★", 4: "★★★★☆", 3: "★★★☆☆", 2: "★★☆☆☆", 1: "★☆☆☆☆"}
    labels = {5: "Stable", 4: "Healthy", 3: "Balanced", 2: "Needs Attention", 1: "Review Recommended"}

    if not observations:
        observations.append(
            "Portfolio is well-positioned. Sector exposures and correlations are within preferred ranges."
        )

    return stars[health_score], labels[health_score], observations


# ---------------------------------------------------------------------------
# DB INIT
# ---------------------------------------------------------------------------

def _init_advisor_db(conn: sqlite3.Connection):
    """Create advisor_recommendations and advisor_reports tables if not present."""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS advisor_recommendations (
        rec_id              TEXT PRIMARY KEY,
        report_date         TEXT NOT NULL,
        ticker              TEXT NOT NULL,
        category            TEXT NOT NULL,
        decision            TEXT NOT NULL,
        signal_quality_stars TEXT,
        signal_quality_label TEXT,
        portfolio_fit_stars  TEXT,
        portfolio_fit_label  TEXT,
        confidence          TEXT NOT NULL,
        reason              TEXT NOT NULL,
        portfolio_impact    TEXT NOT NULL,
        suggested_action    TEXT NOT NULL,
        expected_benefit    TEXT NOT NULL,
        candidate_r2        REAL,
        current_return_pct  REAL,
        sector              TEXT,
        created_at          TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS advisor_reports (
        report_id           TEXT PRIMARY KEY,
        report_date         TEXT NOT NULL,
        health_stars        TEXT NOT NULL,
        health_label        TEXT NOT NULL,
        health_narrative    TEXT NOT NULL,
        summary_json        TEXT NOT NULL,
        full_report_text    TEXT NOT NULL,
        created_at          TEXT NOT NULL
    );
    """)
    conn.commit()


def _rec_id(report_date: str, ticker: str, category: str) -> str:
    """Return deterministic 16-char hex ID for a recommendation record."""
    return hashlib.sha256(f"{report_date}|{ticker}|{category}".encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# DATA LOADING
# ---------------------------------------------------------------------------

def _load_latest_snapshot(mgr_conn: sqlite3.Connection) -> dict:
    """Return the most recent portfolio_snapshots row as a dict with JSON fields parsed."""
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
    """Return all candidate_states rows as a list of dicts with canonical field names."""
    rows = mgr_conn.execute(
        "SELECT ticker, state, candidate_r2, sector, decision_reason, "
        "portfolio_impact, suggested_action, candidate_entry_zone "
        "FROM candidate_states"
    ).fetchall()
    cols = ["ticker", "state", "candidate_r2", "sector", "decision_reason",
            "portfolio_impact", "suggested_action", "candidate_entry_zone"]
    return [dict(zip(cols, r)) for r in rows]


def _load_best_pool_entry(pool_conn: sqlite3.Connection, ticker: str) -> Optional[dict]:
    """Return highest-R2 candidate_pool row for ticker, or None if absent."""
    row = pool_conn.execute(
        "SELECT ticker, signal_date, candidate_entry_zone, candidate_r2, r3_score, r4_score, "
        "r5_score, r6_score, r7_score, r8_score, expected_reward_score, sector, "
        "discount_depth, distance_from_eq, atr20, volatility20 "
        "FROM candidate_pool "
        "WHERE ticker = ? "
        "ORDER BY candidate_r2 DESC, signal_date DESC LIMIT 1",
        (ticker,)
    ).fetchone()
    if not row:
        return None
    cols = ["ticker", "signal_date", "candidate_entry_zone", "candidate_r2", "r3_score",
            "r4_score", "r5_score", "r6_score", "r7_score", "r8_score",
            "expected_reward_score", "sector", "discount_depth", "distance_from_eq",
            "atr20", "volatility20"]
    return dict(zip(cols, row))


# ---------------------------------------------------------------------------
# CLASSIFICATION — HELD POSITIONS
# ---------------------------------------------------------------------------

def _classify_held(
    holding: dict,
    sector_alloc: dict,
    corr_matrix: dict,
    all_held_tickers: list[str],
    pool_conn: sqlite3.Connection,
) -> dict:
    """Classify a held position and return its advisory recommendation dict."""
    ticker = holding["ticker"]
    ret = holding.get("return_pct", 0.0)
    sector = holding.get("sector", "Unknown")
    sector_pct = sector_alloc.get(sector, 0.0)

    pool_entry = _load_best_pool_entry(pool_conn, ticker)
    r2 = pool_entry["candidate_r2"] if pool_entry else holding.get("candidate_r2", 0.0)

    corr_row = corr_matrix.get(ticker, {})
    peers = [t for t in all_held_tickers if t != ticker]
    max_corr = max((corr_row.get(t, 0.0) for t in peers), default=0.0)

    sq_stars, sq_label = _signal_quality_stars(r2)
    pf_stars, pf_label = _portfolio_fit_stars(
        sector, sector_pct, max_corr, len(all_held_tickers)
    )

    reason = (
        f"Held position. Return: {ret:+.1f}%. "
        f"R2={r2:.1f} ({sq_label}). "
        f"Max peer correlation: {max_corr:.3f}. "
        f"{sector} sector at {sector_pct:.1f}% of portfolio."
    )
    impact = (
        f"Contributes {100/max(len(all_held_tickers), 1):.1f}% weight. "
        f"{sector} exposure: {sector_pct:.1f}%."
    )

    if ret >= RETURN_EVOLUTION_THRESHOLD:
        action = (
            "Position has materially appreciated. Hold unless a higher-conviction "
            "entry in a diversifying sector becomes available."
        )
        benefit = "Preserving unrealised gain while maintaining portfolio continuity."
        category = "KEEP_EVOLVED"
    else:
        action = "No action required. Monitor weekly."
        benefit = "Continue holding constitutional discount-zone position."
        category = "KEEP"

    conf = "HIGH" if r2 >= 50 else "MEDIUM"

    return {
        "ticker": ticker,
        "category": category,
        "decision": "Hold — continue position",
        "signal_quality_stars": sq_stars,
        "signal_quality_label": sq_label,
        "portfolio_fit_stars": pf_stars,
        "portfolio_fit_label": pf_label,
        "confidence": conf,
        "reason": reason,
        "portfolio_impact": impact,
        "suggested_action": action,
        "expected_benefit": benefit,
        "candidate_r2": r2,
        "current_return_pct": ret,
        "sector": sector,
    }


# ---------------------------------------------------------------------------
# CLASSIFICATION — CANDIDATES (BUY_RESERVE / PRIMARY_BUY / WATCH)
# ---------------------------------------------------------------------------

def _candidate_fit_context(
    cand: dict,
    sector_alloc: dict,
    corr_matrix: dict,
    all_held_tickers: list[str],
    held_count: int,
) -> tuple[str, str, str]:
    """Returns (portfolio_fit_stars, portfolio_fit_label, fit_explanation)."""
    sector = cand.get("sector", "Unknown")
    sector_pct = sector_alloc.get(sector, 0.0)

    # Estimate max correlation vs held positions using cached values
    ticker = cand.get("ticker", "")
    corr_row = corr_matrix.get(ticker, {})
    max_corr = max((corr_row.get(t, 0.0) for t in all_held_tickers), default=0.0)

    pf_stars, pf_label = _portfolio_fit_stars(sector, sector_pct, max_corr, held_count)

    # Build narrative explanation (never negative, always advisory)
    parts = []
    if sector_pct > SECTOR_PREFERRED_MAX * 1.5:
        parts.append(
            f"{sector} exposure is already significantly elevated ({sector_pct:.1f}%). "
            "This is an excellent constitutional BUY. "
            "Adding it is a portfolio manager's decision — "
            "diversification opportunities in other sectors may deserve priority."
        )
    elif sector_pct > SECTOR_PREFERRED_MAX:
        parts.append(
            f"{sector} exposure is above the preferred level ({sector_pct:.1f}%). "
            "Adding with awareness of concentration."
        )
    else:
        parts.append(f"Adds {sector} exposure ({sector_pct:.1f}% current, well within range).")

    if max_corr >= CORR_CAP:
        parts.append(
            f"Highest correlation with held positions: {max_corr:.3f}. "
            "Consider timing with respect to correlated holdings."
        )
    elif max_corr >= 0.65:
        parts.append(f"Moderate correlation with existing positions ({max_corr:.3f}).")
    else:
        parts.append(f"Low correlation with existing positions ({max_corr:.3f}). Good diversifier.")

    if held_count >= MAX_POSITIONS:
        parts.append(
            "Portfolio is at capacity. This is a Future Priority — "
            "buy when a position exits naturally."
        )

    return pf_stars, pf_label, " ".join(parts)


def _classify_candidate(
    cand: dict,
    state: str,
    sector_alloc: dict,
    corr_matrix: dict,
    all_held_tickers: list[str],
    held_count: int,
) -> dict:
    """Classify a BUY_RESERVE/PRIMARY_BUY/WATCH candidate and return its advisory recommendation dict."""
    ticker = cand.get("ticker", "?")
    r2 = cand.get("candidate_r2", 0.0)
    sector = cand.get("sector", "Unknown")
    sector_pct = sector_alloc.get(sector, 0.0)

    sq_stars, sq_label = _signal_quality_stars(r2)
    pf_stars, pf_label, fit_explanation = _candidate_fit_context(
        cand, sector_alloc, corr_matrix, all_held_tickers, held_count
    )

    # Determine human-readable category and decision language
    if held_count < MAX_POSITIONS and sector_pct <= SECTOR_PREFERRED_MAX and r2 >= 60:
        category = "HIGH_CONVICTION_BUY"
        decision = "Buy — strong signal, good portfolio fit"
        conf = "HIGH"
    elif held_count >= MAX_POSITIONS:
        category = "FUTURE_PRIORITY"
        decision = "Future Priority — buy when capacity opens"
        conf = "HIGH" if r2 >= 65 else "MEDIUM"
    elif sector_pct > SECTOR_PREFERRED_MAX or r2 < 60:
        category = "BUY_WITH_AWARENESS"
        decision = "Buy with diversification awareness"
        conf = "MEDIUM"
    else:
        category = "BUY_WITH_AWARENESS"
        decision = "Buy with diversification awareness"
        conf = "MEDIUM"

    if state == "WATCH":
        category = "WATCH"
        decision = "Monitor — developing setup"
        conf = "LOW" if r2 < 50 else "MEDIUM"

    reason = f"R2={r2:.1f} ({sq_label}). {fit_explanation}"
    portfolio_impact = (
        f"Adds {sector} exposure. "
        f"Position weight: {100/max(held_count + 1, 1):.1f}% (equal weight after addition)."
    )
    action = cand.get("suggested_action", "Buy when portfolio has capacity.")
    if state == "WATCH":
        action = "Monitor. Re-evaluate when R2 approaches 60 or sector concentration eases."
    benefit = (
        "Adds constitutional discount-zone exposure with strong entry quality." if r2 >= 55
        else "Adds developing discount-zone setup to tracking list."
    )

    return {
        "ticker": ticker,
        "category": category,
        "decision": decision,
        "signal_quality_stars": sq_stars,
        "signal_quality_label": sq_label,
        "portfolio_fit_stars": pf_stars,
        "portfolio_fit_label": pf_label,
        "confidence": conf,
        "reason": reason,
        "portfolio_impact": portfolio_impact,
        "suggested_action": action,
        "expected_benefit": benefit,
        "candidate_r2": r2,
        "current_return_pct": None,
        "sector": sector,
    }


# ---------------------------------------------------------------------------
# REPORT BUILDER
# ---------------------------------------------------------------------------

def _build_report(
    report_date: str,
    health_stars: str,
    health_label: str,
    health_observations: list[str],
    recs: list[dict],
    snapshot: dict,
) -> str:
    """Render the full plain-text portfolio intelligence report from classified recommendations."""
    health = snapshot.get("portfolio_health_json", {})
    sector_alloc = snapshot.get("sector_alloc_json", {})
    held_count = health.get("held_positions", 0)
    max_corr = health.get("max_held_correlation", 0.0)
    pos_weight = health.get("position_weight_pct", 0.0)

    L = []
    sep = "=" * 68

    L.append(sep)
    L.append("  PORTFOLIO INTELLIGENCE REPORT")
    L.append(f"  {report_date}")
    L.append(sep)
    L.append("")

    # Portfolio Health
    L.append(f"Portfolio Health    {health_stars}  {health_label}")
    L.append("")
    L.append("Narrative Summary")
    for obs in health_observations:
        L.append(f"  {obs}")
    L.append("")

    # CURRENT HOLDINGS — KEEP
    keep_recs = [r for r in recs if r["category"] in ("KEEP", "KEEP_EVOLVED")]
    if keep_recs:
        L.append("-" * 68)
        L.append(f"  CURRENT HOLDINGS — KEEP  ({len(keep_recs)})")
        L.append("-" * 68)
        for r in sorted(keep_recs, key=lambda x: -(x.get("current_return_pct") or 0)):
            ret_str = f"{r['current_return_pct']:+.1f}%" if r.get("current_return_pct") is not None else "—"
            evolved_tag = "  [Materially Appreciated]" if r["category"] == "KEEP_EVOLVED" else ""
            L.append(
                f"  {r['ticker']:<10}  Return: {ret_str:<8}  "
                f"Signal: {r['signal_quality_stars']} {r['signal_quality_label']:<12}  "
                f"Fit: {r['portfolio_fit_stars']} {r['portfolio_fit_label']}{evolved_tag}"
            )
            if r.get("suggested_action") and "Monitor weekly" not in r["suggested_action"]:
                L.append(f"             → {r['suggested_action']}")
        L.append("")

    # HIGH CONVICTION BUY
    hcb = [r for r in recs if r["category"] == "HIGH_CONVICTION_BUY"]
    if hcb:
        L.append("-" * 68)
        L.append(f"  HIGH CONVICTION BUY  ({len(hcb)})")
        L.append("-" * 68)
        for r in sorted(hcb, key=lambda x: -(x.get("candidate_r2") or 0)):
            L.append(f"  {r['ticker']}")
            L.append(f"    Signal Quality   {r['signal_quality_stars']}  {r['signal_quality_label']}")
            L.append(f"    Portfolio Fit    {r['portfolio_fit_stars']}  {r['portfolio_fit_label']}")
            L.append(f"    Confidence       {r['confidence']}")
            L.append(f"    Reason           {r['reason']}")
            L.append(f"    Portfolio Impact {r['portfolio_impact']}")
            L.append(f"    Suggested Action {r['suggested_action']}")
            L.append(f"    Expected Benefit {r['expected_benefit']}")
            L.append("")

    # BUY WITH DIVERSIFICATION AWARENESS
    bwa = [r for r in recs if r["category"] == "BUY_WITH_AWARENESS"]
    if bwa:
        L.append("-" * 68)
        L.append(f"  BUY WITH DIVERSIFICATION AWARENESS  ({len(bwa)})")
        L.append("-" * 68)
        for r in sorted(bwa, key=lambda x: -(x.get("candidate_r2") or 0)):
            L.append(f"  {r['ticker']}")
            L.append(f"    Signal Quality   {r['signal_quality_stars']}  {r['signal_quality_label']}")
            L.append(f"    Portfolio Fit    {r['portfolio_fit_stars']}  {r['portfolio_fit_label']}")
            L.append(f"    Confidence       {r['confidence']}")
            L.append(f"    Explanation      {r['reason']}")
            L.append(f"    Suggested Action {r['suggested_action']}")
            L.append("")

    # WATCH
    watch = [r for r in recs if r["category"] == "WATCH"]
    if watch:
        L.append("-" * 68)
        L.append(f"  WATCH — DEVELOPING SETUPS  ({len(watch)})")
        L.append("-" * 68)
        for r in sorted(watch, key=lambda x: -(x.get("candidate_r2") or 0)):
            L.append(
                f"  {r['ticker']:<10}  Signal: {r['signal_quality_stars']} {r['signal_quality_label']:<12}  "
                f"R2={r.get('candidate_r2', 0):.1f}"
            )
        L.append("")

    # OBSERVATIONS
    L.append("-" * 68)
    L.append("  OBSERVATIONS")
    L.append("-" * 68)
    L.append("")
    L.append("  Sector Concentration")
    for sec, pct in sorted(sector_alloc.items(), key=lambda x: -x[1]):
        arrow = "  ↑" if pct > SECTOR_PREFERRED_MAX else "   "
        L.append(f"  {arrow}{sec:<18} {pct:.1f}%")
    L.append("")
    L.append(f"  Correlation Notes")
    L.append(f"    Maximum pairwise correlation: {max_corr:.3f}")
    if max_corr < 0.65:
        L.append("    Correlation within comfortable range across all held pairs.")
    elif max_corr < CORR_CAP:
        L.append("    Moderate concentration in correlated pairs — acceptable.")
    else:
        L.append("    Elevated correlation — review closely correlated pairs before next addition.")
    L.append("")
    L.append(f"  Cash Utilization")
    L.append(f"    {held_count} positions × {pos_weight:.1f}% = {held_count * pos_weight:.1f}% deployed")
    cash_remaining = max(0, 100 - held_count * pos_weight)
    L.append(f"    Cash available: {cash_remaining:.1f}%")
    L.append("")

    # FUTURE OPPORTUNITIES
    future = [r for r in recs if r["category"] == "FUTURE_PRIORITY"]
    if future:
        L.append("-" * 68)
        L.append("  FUTURE OPPORTUNITIES")
        L.append("  If capacity becomes available, priority order by Signal Quality:")
        L.append("-" * 68)
        for i, r in enumerate(sorted(future, key=lambda x: -(x.get("candidate_r2") or 0)), 1):
            L.append(f"  Priority {i}   {r['ticker']}")
            L.append(f"    Signal Quality   {r['signal_quality_stars']}  {r['signal_quality_label']}")
            L.append(f"    Portfolio Fit    {r['portfolio_fit_stars']}  {r['portfolio_fit_label']}")
            L.append(f"    Explanation      {r['reason']}")
            L.append("")

    # PORTFOLIO EVOLUTION
    L.append("-" * 68)
    L.append("  PORTFOLIO EVOLUTION")
    L.append("  Natural improvements without unnecessary turnover")
    L.append("-" * 68)
    L.append("")
    evolved = [r for r in recs if r["category"] == "KEEP_EVOLVED"]
    if evolved:
        L.append(
            f"  {len(evolved)} position(s) have materially appreciated. "
            "These are not sell signals. They are opportunities to consider "
            "whether a higher-conviction new entry in a diversifying sector "
            "would improve the portfolio's forward positioning."
        )
        for r in evolved:
            L.append(
                f"    {r['ticker']:<10}  Return: {r.get('current_return_pct', 0):+.1f}%  "
                f"→ {r['suggested_action']}"
            )
        L.append("")

    # Sector evolution advice
    overweight = [(s, p) for s, p in sector_alloc.items() if p > SECTOR_PREFERRED_MAX]
    underweight_sectors = set(sector_alloc.keys()) - {s for s, _ in overweight}
    if overweight:
        over_names = ", ".join(f"{s} ({p:.1f}%)" for s, p in overweight)
        under_names = ", ".join(underweight_sectors) if underweight_sectors else "other sectors"
        L.append(
            f"  Over time, natural exits from {over_names} and additions "
            f"in {under_names} will improve diversification organically."
        )
        L.append("")

    # TODAY'S SUMMARY — max 8 bullets
    L.append("-" * 68)
    L.append("  TODAY'S SUMMARY")
    L.append("-" * 68)
    counts = {}
    for r in recs:
        counts[r["category"]] = counts.get(r["category"], 0) + 1

    bullets = []
    bullets.append(
        f"Portfolio Health: {health_stars} {health_label}."
    )
    bullets.append(
        f"{held_count} positions held. "
        f"Equal weight {pos_weight:.1f}% per position."
    )
    if counts.get("HIGH_CONVICTION_BUY", 0):
        bullets.append(
            f"{counts['HIGH_CONVICTION_BUY']} High Conviction BUY signal(s) available."
        )
    if counts.get("BUY_WITH_AWARENESS", 0):
        bullets.append(
            f"{counts['BUY_WITH_AWARENESS']} BUY With Diversification Awareness candidate(s)."
        )
    if counts.get("FUTURE_PRIORITY", 0):
        bullets.append(
            f"{counts['FUTURE_PRIORITY']} Future Priority candidate(s) queued for when capacity opens."
        )
    if counts.get("WATCH", 0):
        bullets.append(
            f"{counts['WATCH']} developing setup(s) on the watchlist."
        )
    if overweight:
        bullets.append(
            f"Sector attention: {', '.join(s for s,_ in overweight)}. "
            "No immediate action required — natural turnover will improve balance."
        )
    if counts.get("KEEP_EVOLVED", 0):
        bullets.append(
            f"{counts['KEEP_EVOLVED']} position(s) have materially appreciated — review for evolution opportunity."
        )

    for b in bullets[:8]:
        L.append(f"  • {b}")

    L.append("")
    L.append(sep)

    return "\n".join(L)


# ---------------------------------------------------------------------------
# MAIN ADVISOR
# ---------------------------------------------------------------------------

def run_portfolio_advisor(
    report_date: Optional[str] = None,
    mgr_db: str = MGR_DB,
    pool_db: str = POOL_DB,
    advisor_db: str = ADVISOR_DB,
) -> dict:
    """Run the full portfolio advisor pipeline and return report dict with recommendations."""
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
        held_count = len(all_held_tickers)

        health_stars, health_label, health_obs = _portfolio_health(health, sector_alloc)

        recs = []

        # Classify HELD positions
        for h in holdings:
            rec = _classify_held(h, sector_alloc, corr_matrix, all_held_tickers, pool_conn)
            rec["rec_id"] = _rec_id(report_date, rec["ticker"], rec["category"])
            rec["report_date"] = report_date
            recs.append(rec)

        # Classify candidates from candidate_states
        for s in states:
            if s["state"] in ("HELD",):
                continue  # already handled above
            rec = _classify_candidate(
                s, s["state"], sector_alloc, corr_matrix, all_held_tickers, held_count
            )
            rec["rec_id"] = _rec_id(report_date, rec["ticker"], rec["category"])
            rec["report_date"] = report_date
            recs.append(rec)

        # Persist (append-only)
        now = datetime.now().isoformat()
        for rec in recs:
            adv_conn.execute(
                """INSERT OR IGNORE INTO advisor_recommendations
                   (rec_id, report_date, ticker, category, decision,
                    signal_quality_stars, signal_quality_label,
                    portfolio_fit_stars, portfolio_fit_label,
                    confidence, reason, portfolio_impact, suggested_action,
                    expected_benefit, candidate_r2, current_return_pct, sector, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (rec["rec_id"], rec["report_date"], rec["ticker"], rec["category"],
                 rec["decision"], rec.get("signal_quality_stars"), rec.get("signal_quality_label"),
                 rec.get("portfolio_fit_stars"), rec.get("portfolio_fit_label"),
                 rec["confidence"], rec["reason"], rec["portfolio_impact"],
                 rec["suggested_action"], rec["expected_benefit"],
                 rec.get("candidate_r2"), rec.get("current_return_pct"), rec.get("sector"), now)
            )

        report_text = _build_report(
            report_date, health_stars, health_label, health_obs, recs, snapshot
        )

        summary = {
            cat: [r["ticker"] for r in recs if r["category"] == cat]
            for cat in ["KEEP", "KEEP_EVOLVED", "HIGH_CONVICTION_BUY",
                        "BUY_WITH_AWARENESS", "FUTURE_PRIORITY", "WATCH"]
        }
        report_id = _rec_id(report_date, "REPORT", health_label)
        adv_conn.execute(
            """INSERT OR IGNORE INTO advisor_reports
               (report_id, report_date, health_stars, health_label, health_narrative,
                summary_json, full_report_text, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (report_id, report_date, health_stars, health_label,
             "\n".join(health_obs), json.dumps(summary), report_text, now)
        )
        adv_conn.commit()

        return {
            "report_date": report_date,
            "health_stars": health_stars,
            "health_label": health_label,
            "health_observations": health_obs,
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
