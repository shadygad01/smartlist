"""
Research Knowledge Layer
========================
Organizational memory for alpha discovery research.

What this stores (in research.db — separate from production):
  - Hypotheses: what we studied, how, and why
  - Validation records: statistical conclusions from each formal analysis
  - Research log: decisions, status changes, lessons learned
  - Lessons: standalone insights, searchable by category and hypothesis

What this never does:
  - Write to egx_research.db (production database)
  - Store per-signal research scores
  - Modify rankings, filters, or scoring logic
  - Automatically deploy anything to production

Statistics are computed dynamically from production data at query time.
Only conclusions and decisions are persisted.

CLI:
  python research_features.py validate [hypothesis_id]   — run formal validation + save
  python research_features.py promote <id> <target> "<rationale>"
  python research_features.py reject <id> "<rationale>"
  python research_features.py retire <id> "<rationale>"
  python research_features.py lesson "<text>" [category] [hypothesis_id ...]
  python research_features.py show [hypothesis_id]
"""

import json
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Optional

import numpy as np
import pandas as pd

# ── Paths ─────────────────────────────────────────────────────────────────────
RESEARCH_DB = "research.db"       # research knowledge only — never production
PROD_DB     = "egx_research.db"   # production — read-only

# ── Status definitions ────────────────────────────────────────────────────────
# Tracking  → observed, gathering data
# Validated → formal analysis run, results recorded
# Improving → consistent positive signal across validations
# Stable    → moderate positive signal, not yet promotion-ready
# Failing   → repeated weak/negative results
# Promoted  → ready for human review / integration into production
# Rejected  → tested, no alpha found; permanently searchable
# Retired   → was valid, no longer relevant; permanently searchable
TERMINAL_STATUSES = {"Promoted", "Rejected", "Retired"}
VALID_STATUSES    = {
    "Tracking", "Validated", "Improving", "Stable",
    "Failing", "Promoted", "Rejected", "Retired",
}

# ── Hypothesis registry ───────────────────────────────────────────────────────
# Score formulas use only existing columns from signals + hist_signals.
# Fields:
#   formula_cols  — production columns required
#   formula_notes — human description of computation
_HYPOTHESES = [
    {
        "id": "compression_score",
        "name": "Compression Score",
        "description": (
            "Tests whether sustained ATR compression before a signal improves "
            "subsequent returns. Hypothesis: stocks in tighter ranges at signal "
            "time have more potential energy and deliver higher MFE_40D."
        ),
        "formula_notes": (
            "Score = 0.6 × (1 − clamp(feat_atr_compression/1.5, 0, 1)) "
            "+ 0.4 × (snap_consol_len/19). "
            "feat_atr_compression < 1 = ATR contracting vs average. "
            "snap_consol_len = bars in consolidation (0–19)."
        ),
        "formula_cols": ["feat_atr_compression", "snap_consol_len"],
        "promotion_target": "RankingFactor",
        "overlap_analysis": (
            "feat_atr_compression exists as a point-in-time snapshot. "
            "This hypothesis tests the trajectory and duration of compression, "
            "not the instantaneous ratio — classified as Alpha Amplifier (B)."
        ),
    },
    {
        "id": "vol_dryup_score",
        "name": "Volume Dry-Up Score",
        "description": (
            "Tests whether sustained volume contraction before a signal improves "
            "returns. Hypothesis: low-volume quiet periods precede larger moves."
        ),
        "formula_notes": (
            "Score = 0.5 × clamp(−feat_vol_contraction/0.35, 0, 1) "
            "+ 0.5 × clamp((1.5 − snap_vol_exp)/1.5, 0, 1). "
            "feat_vol_contraction < 0 = volume declining vs baseline. "
            "snap_vol_exp < 1 = volume not expanding."
        ),
        "formula_cols": ["feat_vol_contraction", "snap_vol_exp"],
        "promotion_target": "RankingFactor",
        "overlap_analysis": (
            "feat_vol_contraction is a single-bar ratio. This hypothesis tests "
            "the combined sustained volume environment — Alpha Amplifier (B)."
        ),
    },
    {
        "id": "support_failure_score",
        "name": "Support Failure Score",
        "description": (
            "EXIT RESEARCH ONLY. Tests structural breakdown risk at the time "
            "of a signal: whether the support being tested shows signs of "
            "failing rather than holding. Three components: distribution volume "
            "pattern (snap_reclaim_spd), structural deterioration (snap_choch), "
            "and trend weakness (r4_htf)."
        ),
        "formula_notes": (
            "Score = 0.4 × clamp(−snap_reclaim_spd/0.65, 0, 1) "
            "+ 0.35 × snap_choch "
            "+ 0.25 × clamp(1 − r4_htf/10, 0, 1). "
            "snap_reclaim_spd < 0 = price failed to recover after sweep. "
            "snap_choch = 1 = change of character detected. "
            "Low r4_htf = weak higher-timeframe structure."
        ),
        "formula_cols": ["snap_reclaim_spd", "snap_choch", "r4_htf"],
        "promotion_target": "ScannerFilter",
        "overlap_analysis": (
            "No equivalent in r1-r8. Structural breakdown risk from existing "
            "snapshot columns — New Alpha (A). Exit research only: must never "
            "suppress signals, modify rankings, or affect production decisions."
        ),
    },
]

_HYP_INDEX = {h["id"]: h for h in _HYPOTHESES}


# ── Research DB ────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_research_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(RESEARCH_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_research_db() -> None:
    """Create research.db schema and seed hypotheses. Idempotent."""
    conn = get_research_conn()
    with conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS hypotheses (
            id               TEXT PRIMARY KEY,
            name             TEXT NOT NULL,
            description      TEXT,
            formula_notes    TEXT,
            formula_cols     TEXT,
            promotion_target TEXT,
            overlap_analysis TEXT,
            status           TEXT NOT NULL DEFAULT 'Tracking',
            created_at       TEXT NOT NULL,
            updated_at       TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS validation_runs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            hypothesis_id   TEXT NOT NULL,
            run_at          TEXT NOT NULL,
            n_signals       INTEGER,
            corr_mfe_40d    REAL,
            corr_r20d       REAL,
            q1_mfe_40d      REAL,
            q2_mfe_40d      REAL,
            q3_mfe_40d      REAL,
            q4_mfe_40d      REAL,
            q1_r20d         REAL,
            q2_r20d         REAL,
            q3_r20d         REAL,
            q4_r20d         REAL,
            incremental_r2  REAL,
            win_rate_lift   REAL,
            auto_status     TEXT,
            conclusion      TEXT,
            FOREIGN KEY(hypothesis_id) REFERENCES hypotheses(id)
        );
        CREATE INDEX IF NOT EXISTS idx_vr_hyp ON validation_runs(hypothesis_id);

        CREATE TABLE IF NOT EXISTS research_log (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            hypothesis_id  TEXT,
            logged_at      TEXT NOT NULL,
            event_type     TEXT NOT NULL,
            summary        TEXT NOT NULL,
            details_json   TEXT,
            recorded_by    TEXT DEFAULT 'system'
        );
        CREATE INDEX IF NOT EXISTS idx_rl_hyp ON research_log(hypothesis_id);

        CREATE TABLE IF NOT EXISTS lessons (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            logged_at       TEXT NOT NULL,
            hypothesis_ids  TEXT,
            lesson          TEXT NOT NULL,
            category        TEXT,
            actionable      INTEGER DEFAULT 1
        );
        """)

    # Seed hypotheses
    with conn:
        for h in _HYPOTHESES:
            exists = conn.execute(
                "SELECT 1 FROM hypotheses WHERE id = ?", (h["id"],)
            ).fetchone()
            if not exists:
                now = _now()
                conn.execute(
                    """INSERT INTO hypotheses
                       (id, name, description, formula_notes, formula_cols,
                        promotion_target, overlap_analysis, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (h["id"], h["name"], h["description"], h["formula_notes"],
                     json.dumps(h["formula_cols"]), h["promotion_target"],
                     h["overlap_analysis"], now, now),
                )
                conn.execute(
                    """INSERT INTO research_log
                       (hypothesis_id, logged_at, event_type, summary)
                       VALUES (?, ?, 'Discovered', ?)""",
                    (h["id"], now,
                     f"Hypothesis '{h['name']}' registered for tracking."),
                )
    conn.close()


# ── Score computation (read-only from production) ─────────────────────────────

def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _compute_scores(df: pd.DataFrame) -> pd.DataFrame:
    """
    Derive research scores from existing production columns.
    Returns df with added columns: score_compression, score_vol_dryup,
    score_support_failure. No writes to production DB.
    """
    out = df.copy()

    # ── Compression Score ─────────────────────────────────────────────────────
    def _compression(row):
        atr = row.get("feat_atr_compression")
        con = row.get("snap_consol_len")
        if atr is None and con is None:
            return None
        atr_s = _clamp(1.0 - (atr or 1.0) / 1.5, 0.0, 1.0)
        con_s = _clamp((con or 0) / 19.0, 0.0, 1.0)
        return round(0.6 * atr_s + 0.4 * con_s, 4)

    # ── Volume Dry-Up Score ───────────────────────────────────────────────────
    def _vol_dryup(row):
        vc = row.get("feat_vol_contraction")
        ve = row.get("snap_vol_exp")
        if vc is None and ve is None:
            return None
        vc_s = _clamp(-(vc or 0) / 0.35, 0.0, 1.0)
        ve_s = _clamp((1.5 - (ve or 1.0)) / 1.5, 0.0, 1.0)
        return round(0.5 * vc_s + 0.5 * ve_s, 4)

    # ── Support Failure Score ─────────────────────────────────────────────────
    def _support_failure(row):
        spd   = row.get("snap_reclaim_spd")
        choch = row.get("snap_choch")
        htf   = row.get("r4_htf")
        if spd is None and choch is None and htf is None:
            return None
        spd_s   = _clamp(-(spd or 0) / 0.65, 0.0, 1.0)
        choch_s = float(bool(choch))
        htf_s   = _clamp(1.0 - (htf or 0) / 10.0, 0.0, 1.0)
        return round(0.40 * spd_s + 0.35 * choch_s + 0.25 * htf_s, 4)

    out["score_compression"]     = [_compression(r)     for r in out.to_dict("records")]
    out["score_vol_dryup"]       = [_vol_dryup(r)       for r in out.to_dict("records")]
    out["score_support_failure"] = [_support_failure(r) for r in out.to_dict("records")]
    return out


def _score_col(hypothesis_id: str) -> str:
    return {
        "compression_score":     "score_compression",
        "vol_dryup_score":       "score_vol_dryup",
        "support_failure_score": "score_support_failure",
    }[hypothesis_id]


def load_signals_with_outcomes() -> pd.DataFrame:
    """
    Read-only query of production DB.
    Returns unified DataFrame from signals+bottom_quality and hist_signals,
    maximising sample size for research analysis.
    """
    conn = sqlite3.connect(PROD_DB)
    conn.row_factory = sqlite3.Row

    # Live signals with bottom_quality outcomes
    live = pd.DataFrame([
        dict(r) for r in conn.execute("""
            SELECT s.symbol, s.signal_date,
                   s.r1_price, s.r2_ob, s.r3_liquidity, s.r4_htf,
                   s.r5_avwap, s.r6_macd, s.r7_div, s.r8_demand,
                   s.feat_atr_compression, s.feat_vol_contraction,
                   s.snap_compression, s.snap_consol_len,
                   s.snap_vol_exp, s.snap_reclaim_spd, s.snap_choch,
                   s.sweep_detected, s.htf_hl,
                   bq.mfe_40d, bq.r20d, bq.mfe_20d, bq.mae_40d,
                   bq.classification,
                   'live' AS source
            FROM signals s
            JOIN bottom_quality bq ON s.id = bq.signal_id
            WHERE bq.mfe_40d IS NOT NULL AND bq.r20d IS NOT NULL
        """).fetchall()
    ])

    # Historical signals (hist_signals has outcomes inline)
    hist = pd.DataFrame([
        dict(r) for r in conn.execute("""
            SELECT symbol, signal_date,
                   r1_price, r2_ob, r3_liquidity, r4_htf,
                   r5_avwap, r6_macd, r7_div, r8_demand,
                   feat_atr_compression, feat_vol_contraction,
                   snap_compression, snap_consol_len,
                   snap_vol_exp, snap_reclaim_spd, snap_choch,
                   sweep_detected, htf_hl,
                   mfe_40d, r20d, mfe_20d, mae_40d,
                   classification,
                   'historical' AS source
            FROM hist_signals
            WHERE mfe_40d IS NOT NULL AND r20d IS NOT NULL
        """).fetchall()
    ])

    conn.close()

    frames = [f for f in [live, hist] if not f.empty]
    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)

    # Deduplicate by symbol+date (live takes priority)
    combined = combined.sort_values("source").drop_duplicates(
        subset=["symbol", "signal_date"], keep="first"
    ).reset_index(drop=True)

    return _compute_scores(combined)


# ── Statistical analysis ───────────────────────────────────────────────────────

def _pearson_r(x, y) -> Optional[float]:
    if len(x) < 10:
        return None
    try:
        r = float(np.corrcoef(x.astype(float), y.astype(float))[0, 1])
        return r if np.isfinite(r) else None
    except Exception:
        return None


def _quartile_means(scores, outcomes) -> tuple:
    """Q1 (lowest scores) → Q4 (highest scores)."""
    if len(scores) < 20:
        return None, None, None, None
    try:
        p = np.percentile(scores, [25, 50, 75])
        masks = [
            scores <= p[0],
            (scores > p[0]) & (scores <= p[1]),
            (scores > p[1]) & (scores <= p[2]),
            scores > p[2],
        ]
        def _m(mask):
            sub = outcomes[mask]
            return float(np.mean(sub)) if len(sub) >= 3 else None
        return _m(masks[0]), _m(masks[1]), _m(masks[2]), _m(masks[3])
    except Exception:
        return None, None, None, None


def _incremental_r2(scores, outcomes, existing_features) -> Optional[float]:
    if len(scores) < 15:
        return None
    try:
        from numpy.linalg import lstsq
        y = outcomes.reshape(-1, 1)
        def _r2(X):
            X_ = np.hstack([np.ones((len(X), 1)), X])
            coef, _, _, _ = lstsq(X_, y, rcond=None)
            ss_res = float(np.sum((y - X_ @ coef) ** 2))
            ss_tot = float(np.sum((y - np.mean(y)) ** 2))
            return 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
        r2_base = _r2(existing_features)
        r2_full = _r2(np.hstack([existing_features, scores.reshape(-1, 1)]))
        return round(r2_full - r2_base, 5)
    except Exception:
        return None


def _auto_status(corr_mfe: Optional[float], incr_r2: Optional[float], n: int) -> str:
    if n < 30:
        return "Tracking"
    if corr_mfe is None:
        return "Tracking"
    if corr_mfe < 0.05:
        return "Failing"
    if corr_mfe >= 0.15 and incr_r2 is not None and incr_r2 >= 0.01:
        return "Improving"
    if 0.05 <= corr_mfe < 0.15:
        return "Stable"
    return "Validated"


def _generate_conclusion(
    hyp_name: str,
    corr_mfe: Optional[float],
    incr_r2: Optional[float],
    q4_mfe: Optional[float],
    q1_mfe: Optional[float],
    n: int,
    win_rate_lift: Optional[float],
) -> str:
    """Auto-generate a human-readable research conclusion."""
    if n < 30:
        return f"Insufficient data ({n} signals). Continue tracking."

    parts = [f"Analysed {n} signals with validated outcomes."]

    if corr_mfe is not None:
        direction = "positive" if corr_mfe >= 0 else "negative"
        strength  = ("strong" if abs(corr_mfe) >= 0.20 else
                     "moderate" if abs(corr_mfe) >= 0.10 else "weak")
        parts.append(
            f"Pearson r vs MFE_40D = {corr_mfe:+.3f} ({strength} {direction} correlation)."
        )

    if q4_mfe is not None and q1_mfe is not None:
        lift = (q4_mfe - q1_mfe) * 100
        parts.append(
            f"Top-quartile signals average {q4_mfe*100:.1f}% MFE_40D vs "
            f"{q1_mfe*100:.1f}% for bottom-quartile (lift: {lift:+.1f}pp)."
        )

    if incr_r2 is not None:
        if incr_r2 >= 0.01:
            parts.append(
                f"Incremental R² beyond r1-r8 = {incr_r2:+.4f} — "
                "adds information not captured by existing gates."
            )
        else:
            parts.append(
                f"Incremental R² beyond r1-r8 = {incr_r2:+.4f} — "
                "marginal new information beyond existing gates."
            )

    if win_rate_lift is not None:
        parts.append(
            f"Win-rate lift (Q4 vs Q1) = {win_rate_lift*100:+.1f}pp "
            f"(threshold: r20d ≥ 7%)."
        )

    return " ".join(parts)


def compute_live_stats(df: pd.DataFrame, hypothesis_id: str) -> dict:
    """
    Compute current statistics for one hypothesis from the full dataset.
    Pure computation — no writes anywhere.
    """
    col = _score_col(hypothesis_id)
    sub = df[df[col].notna()].copy()
    if sub.empty:
        return {"n": 0}

    scores  = sub[col].values.astype(float)
    mfe_40d = sub["mfe_40d"].values.astype(float)
    r20d    = sub["r20d"].values.astype(float)
    factor_cols = ["r1_price", "r2_ob", "r3_liquidity", "r4_htf",
                   "r5_avwap", "r6_macd", "r7_div", "r8_demand"]
    existing = sub[factor_cols].fillna(0).values
    n = len(scores)

    corr_mfe = _pearson_r(scores, mfe_40d)
    corr_r20 = _pearson_r(scores, r20d)
    incr_r2  = _incremental_r2(scores, mfe_40d, existing)

    q1m, q2m, q3m, q4m = _quartile_means(scores, mfe_40d)
    q1r, q2r, q3r, q4r = _quartile_means(scores, r20d)

    win_rate_lift = None
    if n >= 20:
        try:
            p25, p75 = np.percentile(scores, [25, 75])
            wr_q4 = float(np.mean(r20d[scores > p75] >= 0.07))
            wr_q1 = float(np.mean(r20d[scores <= p25] >= 0.07))
            win_rate_lift = round(wr_q4 - wr_q1, 4)
        except Exception:
            pass

    auto_st = _auto_status(corr_mfe, incr_r2, n)
    conclusion = _generate_conclusion(
        _HYP_INDEX.get(hypothesis_id, {}).get("name", hypothesis_id),
        corr_mfe, incr_r2, q4m, q1m, n, win_rate_lift,
    )

    return {
        "n":              n,
        "corr_mfe_40d":  corr_mfe,
        "corr_r20d":     corr_r20,
        "q1_mfe_40d":    q1m, "q2_mfe_40d": q2m,
        "q3_mfe_40d":    q3m, "q4_mfe_40d": q4m,
        "q1_r20d":       q1r, "q2_r20d": q2r,
        "q3_r20d":       q3r, "q4_r20d": q4r,
        "incremental_r2": incr_r2,
        "win_rate_lift":  win_rate_lift,
        "auto_status":    auto_st,
        "conclusion":     conclusion,
    }


# ── Formal validation (saves to research.db) ──────────────────────────────────

def validate_hypothesis(hypothesis_id: str, note: str = "") -> dict:
    """
    Run formal validation for one hypothesis against current production data.
    Saves a validation_run record and logs the conclusion to research_log.
    This is the only function that writes to research.db from analysis.
    """
    init_research_db()

    df = load_signals_with_outcomes()
    if df.empty:
        raise RuntimeError("No signals with validated outcomes found in production DB.")

    stats = compute_live_stats(df, hypothesis_id)
    hyp   = _HYP_INDEX.get(hypothesis_id)
    if not hyp:
        raise ValueError(f"Unknown hypothesis: {hypothesis_id}")

    now     = _now()
    conn    = get_research_conn()
    try:
        conn.execute(
            """INSERT INTO validation_runs
               (hypothesis_id, run_at, n_signals,
                corr_mfe_40d, corr_r20d,
                q1_mfe_40d, q2_mfe_40d, q3_mfe_40d, q4_mfe_40d,
                q1_r20d, q2_r20d, q3_r20d, q4_r20d,
                incremental_r2, win_rate_lift, auto_status, conclusion)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (hypothesis_id, now, stats["n"],
             stats["corr_mfe_40d"], stats["corr_r20d"],
             stats["q1_mfe_40d"], stats["q2_mfe_40d"],
             stats["q3_mfe_40d"], stats["q4_mfe_40d"],
             stats["q1_r20d"], stats["q2_r20d"],
             stats["q3_r20d"], stats["q4_r20d"],
             stats["incremental_r2"], stats["win_rate_lift"],
             stats["auto_status"], stats["conclusion"]),
        )

        # Update hypothesis status if not terminal
        current = conn.execute(
            "SELECT status FROM hypotheses WHERE id = ?", (hypothesis_id,)
        ).fetchone()
        if current and current["status"] not in TERMINAL_STATUSES:
            conn.execute(
                "UPDATE hypotheses SET status = ?, updated_at = ? WHERE id = ?",
                (stats["auto_status"], now, hypothesis_id),
            )

        summary = stats["conclusion"]
        if note:
            summary += f" Note: {note}"
        conn.execute(
            """INSERT INTO research_log
               (hypothesis_id, logged_at, event_type, summary, details_json)
               VALUES (?, ?, 'Validated', ?, ?)""",
            (hypothesis_id, now, summary,
             json.dumps({k: v for k, v in stats.items()
                         if k not in ("conclusion",)}, default=str)),
        )
        conn.commit()
    finally:
        conn.close()

    print(f"[Research] Validated '{hyp['name']}': {stats['auto_status']} (n={stats['n']})")
    return stats


def validate_all(note: str = "") -> None:
    """Run formal validation for every non-terminal hypothesis."""
    init_research_db()
    conn = get_research_conn()
    active = [r["id"] for r in conn.execute(
        "SELECT id FROM hypotheses WHERE status NOT IN ('Promoted','Rejected','Retired')"
    ).fetchall()]
    conn.close()
    for hid in active:
        try:
            validate_hypothesis(hid, note=note)
        except Exception as e:
            print(f"[Research] {hid}: {e}")


# ── Knowledge management (human decisions) ────────────────────────────────────

def _set_status(
    hypothesis_id: str,
    new_status: str,
    event_type: str,
    rationale: str,
    promotion_target: Optional[str] = None,
) -> None:
    init_research_db()
    conn = get_research_conn()
    try:
        row = conn.execute(
            "SELECT * FROM hypotheses WHERE id = ?", (hypothesis_id,)
        ).fetchone()
        if not row:
            raise ValueError(f"Hypothesis '{hypothesis_id}' not found.")
        if row["status"] in TERMINAL_STATUSES and new_status not in TERMINAL_STATUSES:
            raise ValueError(
                f"Cannot change terminal status '{row['status']}' for '{hypothesis_id}'."
            )
        now = _now()
        upd = {"status": new_status, "updated_at": now}
        if promotion_target:
            upd["promotion_target"] = promotion_target
        conn.execute(
            "UPDATE hypotheses SET " + ", ".join(f"{k}=?" for k in upd) + " WHERE id = ?",
            list(upd.values()) + [hypothesis_id],
        )
        summary = (
            f"Status changed {row['status']} → {new_status}. "
            f"Rationale: {rationale}"
        )
        if promotion_target:
            summary += f" Target: {promotion_target}."
        conn.execute(
            """INSERT INTO research_log
               (hypothesis_id, logged_at, event_type, summary, details_json, recorded_by)
               VALUES (?, ?, ?, ?, ?, 'human')""",
            (hypothesis_id, now, event_type, summary,
             json.dumps({"rationale": rationale, "target": promotion_target,
                         "previous_status": row["status"]}, default=str)),
        )
        conn.commit()
        print(f"[Research] {hypothesis_id}: {row['status']} → {new_status}")
    finally:
        conn.close()


def promote(hypothesis_id: str, target: str, rationale: str) -> None:
    """
    Mark hypothesis as Promoted — ready for human review and possible production
    integration. Does NOT modify production code or logic.
    """
    valid = ("RankingFactor", "ConfidenceFactor", "ScannerFilter")
    if target not in valid:
        raise ValueError(f"target must be one of {valid}")
    if not rationale:
        raise ValueError("rationale is required for promotion decisions.")
    _set_status(hypothesis_id, "Promoted", "Promoted", rationale, promotion_target=target)


def reject(hypothesis_id: str, rationale: str) -> None:
    """
    Mark hypothesis as Rejected. Rationale is required.
    Record remains permanently searchable.
    """
    if not rationale:
        raise ValueError("rationale is required for rejection decisions.")
    _set_status(hypothesis_id, "Rejected", "Rejected", rationale)


def retire(hypothesis_id: str, rationale: str) -> None:
    """
    Mark hypothesis as Retired (was valid, no longer relevant).
    Record remains permanently searchable.
    """
    if not rationale:
        raise ValueError("rationale is required for retirement decisions.")
    _set_status(hypothesis_id, "Retired", "Retired", rationale)


def add_lesson(
    lesson: str,
    category: str = "General",
    hypothesis_ids: Optional[list] = None,
    actionable: bool = True,
) -> None:
    """
    Record a standalone lesson learned. Linked to zero or more hypotheses.
    Stored permanently in research.db.
    """
    valid_cats = {"Alpha", "DataQuality", "MarketRegime", "Methodology", "General"}
    if category not in valid_cats:
        category = "General"
    init_research_db()
    conn = get_research_conn()
    try:
        now = _now()
        conn.execute(
            """INSERT INTO lessons (logged_at, hypothesis_ids, lesson, category, actionable)
               VALUES (?, ?, ?, ?, ?)""",
            (now, json.dumps(hypothesis_ids or []), lesson, category, int(actionable)),
        )
        # Also log to research_log for each linked hypothesis
        for hid in (hypothesis_ids or []):
            conn.execute(
                """INSERT INTO research_log
                   (hypothesis_id, logged_at, event_type, summary, recorded_by)
                   VALUES (?, ?, 'Lesson', ?, 'human')""",
                (hid, now, f"[{category}] {lesson[:200]}"),
            )
        conn.commit()
        print(f"[Research] Lesson recorded: [{category}] {lesson[:80]}")
    finally:
        conn.close()


# ── Dashboard data assembly ───────────────────────────────────────────────────

def get_dashboard_data() -> dict:
    """
    Assemble all data needed by _section_research_lab() in dashboard.py.
    Reads production DB (read-only) for live statistics.
    Reads research.db for knowledge, decisions, lessons.
    Returns a single dict — dashboard renders it without further DB access.
    """
    init_research_db()

    # Load production data once
    df = load_signals_with_outcomes()

    conn = get_research_conn()
    try:
        hypotheses = [dict(r) for r in conn.execute(
            "SELECT * FROM hypotheses ORDER BY "
            "CASE status WHEN 'Improving' THEN 0 WHEN 'Validated' THEN 1 "
            "WHEN 'Stable' THEN 2 WHEN 'Tracking' THEN 3 "
            "WHEN 'Failing' THEN 4 WHEN 'Promoted' THEN 5 "
            "WHEN 'Rejected' THEN 6 WHEN 'Retired' THEN 7 ELSE 8 END, "
            "updated_at DESC"
        ).fetchall()]

        # Latest validation run per hypothesis
        latest_validation = {}
        for row in conn.execute(
            "SELECT * FROM validation_runs WHERE id IN "
            "(SELECT MAX(id) FROM validation_runs GROUP BY hypothesis_id)"
        ).fetchall():
            latest_validation[row["hypothesis_id"]] = dict(row)

        # Validation history per hypothesis (for trend display)
        validation_history = {}
        for row in conn.execute(
            "SELECT * FROM validation_runs ORDER BY id ASC"
        ).fetchall():
            hid = row["hypothesis_id"]
            validation_history.setdefault(hid, []).append(dict(row))

        # Recent research log (last 50 events)
        log_entries = [dict(r) for r in conn.execute(
            "SELECT rl.*, h.name AS hyp_name FROM research_log rl "
            "LEFT JOIN hypotheses h ON rl.hypothesis_id = h.id "
            "ORDER BY rl.id DESC LIMIT 50"
        ).fetchall()]

        # All lessons
        lessons = [dict(r) for r in conn.execute(
            "SELECT * FROM lessons ORDER BY id DESC"
        ).fetchall()]

    finally:
        conn.close()

    # Compute live statistics for each non-terminal hypothesis
    live_stats = {}
    if not df.empty:
        for h in hypotheses:
            if h["status"] not in TERMINAL_STATUSES:
                try:
                    live_stats[h["id"]] = compute_live_stats(df, h["id"])
                except Exception:
                    live_stats[h["id"]] = {"n": 0}

    return {
        "hypotheses":          hypotheses,
        "live_stats":          live_stats,
        "latest_validation":   latest_validation,
        "validation_history":  validation_history,
        "log_entries":         log_entries,
        "lessons":             lessons,
        "total_signals":       len(df) if not df.empty else 0,
    }


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    def _usage():
        print(__doc__)
        sys.exit(0)

    args = sys.argv[1:]
    if not args:
        _usage()

    cmd = args[0]

    if cmd == "validate":
        hid  = args[1] if len(args) > 1 else None
        note = " ".join(args[2:]) if len(args) > 2 else ""
        if hid:
            validate_hypothesis(hid, note=note)
        else:
            validate_all(note=note)

    elif cmd == "promote":
        if len(args) < 4:
            print("Usage: python research_features.py promote <id> <target> \"<rationale>\"")
            sys.exit(1)
        promote(args[1], args[2], " ".join(args[3:]))

    elif cmd == "reject":
        if len(args) < 3:
            print("Usage: python research_features.py reject <id> \"<rationale>\"")
            sys.exit(1)
        reject(args[1], " ".join(args[2:]))

    elif cmd == "retire":
        if len(args) < 3:
            print("Usage: python research_features.py retire <id> \"<rationale>\"")
            sys.exit(1)
        retire(args[1], " ".join(args[2:]))

    elif cmd == "lesson":
        if len(args) < 2:
            print("Usage: python research_features.py lesson \"<text>\" [category] [hyp_id ...]")
            sys.exit(1)
        text     = args[1]
        category = args[2] if len(args) > 2 else "General"
        hyp_ids  = args[3:] if len(args) > 3 else []
        add_lesson(text, category=category, hypothesis_ids=hyp_ids)

    elif cmd == "show":
        hid = args[1] if len(args) > 1 else None
        init_research_db()
        conn = get_research_conn()
        if hid:
            rows = [dict(r) for r in conn.execute(
                "SELECT * FROM hypotheses WHERE id = ?", (hid,)
            ).fetchall()]
        else:
            rows = [dict(r) for r in conn.execute(
                "SELECT id, name, status, updated_at FROM hypotheses"
            ).fetchall()]
        conn.close()
        for r in rows:
            print(json.dumps(r, indent=2, default=str))

    elif cmd == "init":
        init_research_db()
        print("[Research] research.db initialised.")

    else:
        print(f"Unknown command: {cmd}")
        _usage()
