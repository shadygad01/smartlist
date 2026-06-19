"""
Research Features — Alpha Discovery Layer
==========================================
Computes three research scores per signal. Research-only: scores are stored
and studied but never affect rankings, filters, or production decisions.

Scores:
  res_compression_score   — Sustained ATR compression trajectory (0-1)
  res_vol_dryup_score     — Sustained volume contraction sequence (0-1)
  res_support_failure_score — Structural breakdown risk (0-1)

Status lifecycle: Tracking → Improving → Stable → Failing → Promoted/Rejected/Retired
"""

import sqlite3
import json
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd

DB_PATH = "egx_research.db"

# ── Initial hypothesis registry ───────────────────────────────────────────────

_HYPOTHESES = [
    {
        "id":          "compression_score",
        "name":        "Compression Score",
        "description": (
            "Measures whether ATR is monotonically decreasing over the last 10 bars "
            "— sustained energy coiling before a potential breakout. "
            "Distinct from feat_atr_compression (point-in-time ratio): this scores "
            "the directional trajectory of compression, not a single snapshot."
        ),
        "promotion_target": "RankingFactor",
    },
    {
        "id":          "vol_dryup_score",
        "name":        "Volume Dry-Up Score",
        "description": (
            "Scores how many of the last 8 bars have volume below 60% of the 20-bar "
            "mean, weighted by recency. Sustained low-volume sideways action signals "
            "that sellers have exhausted. Distinct from feat_vol_contraction "
            "(single-bar ratio snapshot)."
        ),
        "promotion_target": "RankingFactor",
    },
    {
        "id":          "support_failure_score",
        "name":        "Support Failure Score",
        "description": (
            "Structural breakdown risk: scores the probability that the current "
            "support zone will fail based on (1) distribution volume pattern — "
            "down-move bars carrying more volume than up-move bars in recent 20 bars, "
            "(2) lower-high formation — each rally peak is lower than the prior, "
            "(3) failed sweep recovery — price swept a low but recovered weakly "
            "(< 50% reclaim within 3 bars). Exit research only; never affects "
            "production decisions."
        ),
        "promotion_target": "ScannerFilter",
    },
]


# ── Score computation ─────────────────────────────────────────────────────────

def compute_compression_score(df: pd.DataFrame) -> float:
    """
    ATR compression trajectory score.
    Measures the degree to which ATR(14) has been monotonically decreasing
    over the last 10 bars. Score 0-1.
    """
    if df is None or len(df) < 20:
        return 0.0
    try:
        high = df["High"].values
        low  = df["Low"].values
        close = df["Close"].values

        # True Range
        tr = np.maximum(high[1:] - low[1:],
             np.maximum(np.abs(high[1:] - close[:-1]),
                        np.abs(low[1:]  - close[:-1])))

        # Rolling ATR(14) — only need last 10+14 bars
        lookback = min(len(tr), 30)
        tr_tail = tr[-lookback:]
        atrs = []
        for i in range(13, len(tr_tail)):
            atrs.append(np.mean(tr_tail[i-13:i+1]))

        if len(atrs) < 10:
            return 0.0

        window = np.array(atrs[-10:])
        # Normalise to relative values (% of mean) so absolute size doesn't matter
        mean_atr = np.mean(window)
        if mean_atr == 0:
            return 0.0
        rel = window / mean_atr

        # Score = fraction of consecutive down-steps in the 9 transitions
        steps = rel[1:] - rel[:-1]        # positive = expansion, negative = compression
        n_compress = np.sum(steps < 0)
        raw = n_compress / len(steps)

        # Amplify if the overall slope is clearly negative
        slope = np.polyfit(np.arange(len(window)), window, 1)[0]
        slope_bonus = min(max(-slope / mean_atr, 0.0), 0.2)   # up to +0.2 bonus

        return float(min(raw + slope_bonus, 1.0))
    except Exception:
        return 0.0


def compute_vol_dryup_score(df: pd.DataFrame) -> float:
    """
    Sustained volume dry-up score.
    Scores how many of the last 8 bars have volume < 60% of the 20-bar mean,
    weighted by recency (more recent bars count more). Score 0-1.
    """
    if df is None or len(df) < 22:
        return 0.0
    try:
        vol = df["Volume"].values.astype(float)
        mean_20 = np.mean(vol[-22:-2])   # 20-bar mean, excluding the last 2 bars
        if mean_20 == 0:
            return 0.0

        window = vol[-8:]
        threshold = 0.60 * mean_20

        # Recency weights: [1,1,1,1,1.5,1.5,2,2] (more weight to recent bars)
        weights = np.array([1.0, 1.0, 1.0, 1.0, 1.5, 1.5, 2.0, 2.0])
        flags = (window < threshold).astype(float)
        score = float(np.dot(flags, weights) / np.sum(weights))

        return min(score, 1.0)
    except Exception:
        return 0.0


def compute_support_failure_score(df: pd.DataFrame) -> float:
    """
    Structural breakdown risk score (research only).

    Three components (each 0-1, equally weighted):
    1. Distribution volume: down-bar volume > up-bar volume in last 20 bars
       (sellers in control of volume).
    2. Lower-high formation: each of the last 3 swing highs is lower than
       the prior (weakening rally structure).
    3. Failed sweep recovery: a recent sweep of a swing low was followed by
       a recovery that reclaimed < 50% of the sweep range within 3 bars.

    Score = mean of the three components.
    """
    if df is None or len(df) < 25:
        return 0.0
    try:
        close = df["Close"].values
        high  = df["High"].values
        low   = df["Low"].values
        vol   = df["Volume"].values.astype(float)

        # ── Component 1: Distribution volume ─────────────────────────────────
        tail = slice(-20, None)
        c  = close[tail]
        v  = vol[tail]
        h  = high[tail]
        l  = low[tail]
        bar_returns = np.diff(c)
        down_mask = bar_returns < 0
        up_mask   = bar_returns >= 0
        down_vol  = np.sum(v[1:][down_mask])
        up_vol    = np.sum(v[1:][up_mask])
        total_vol = down_vol + up_vol
        dist_component = float(down_vol / total_vol) if total_vol > 0 else 0.5
        # Normalise: 0.5 = neutral, 1.0 = all volume on down bars
        dist_score = max(0.0, (dist_component - 0.5) * 2.0)   # 0-1

        # ── Component 2: Lower-high formation ────────────────────────────────
        # Find swing highs (local maxima) in last 30 bars
        h30 = high[-30:] if len(high) >= 30 else high
        swing_highs = []
        for i in range(2, len(h30) - 2):
            if h30[i] >= h30[i-1] and h30[i] >= h30[i+1] and \
               h30[i] >= h30[i-2] and h30[i] >= h30[i+2]:
                swing_highs.append(h30[i])

        if len(swing_highs) >= 3:
            last3 = swing_highs[-3:]
            lh_score = 1.0 if (last3[0] > last3[1] > last3[2]) else 0.0
        elif len(swing_highs) == 2:
            lh_score = 0.5 if swing_highs[0] > swing_highs[1] else 0.0
        else:
            lh_score = 0.0

        # ── Component 3: Failed sweep recovery ───────────────────────────────
        # Look for a sweep: price dips below a recent swing low then closes above
        sweep_score = 0.0
        h15 = high[-15:] if len(high) >= 15 else high
        l15 = low[-15:]  if len(low)  >= 15 else low
        c15 = close[-15:] if len(close) >= 15 else close

        if len(l15) >= 6:
            swing_lo = np.percentile(l15[:-3], 15)   # base support level
            for i in range(2, len(l15) - 2):
                if l15[i] < swing_lo and c15[i] > swing_lo:
                    # Sweep candle found — measure recovery over next 3 bars
                    sweep_range = swing_lo - l15[i]
                    recovery_bars = c15[i+1 : i+4] if i + 4 <= len(c15) else c15[i+1:]
                    if len(recovery_bars) > 0:
                        best_close = np.max(recovery_bars)
                        reclaim = (best_close - swing_lo) / sweep_range if sweep_range > 0 else 1.0
                        if reclaim < 0.5:
                            sweep_score = 1.0 - reclaim   # weak recovery = higher risk
                        else:
                            sweep_score = 0.0   # strong recovery = structure held
                    break

        return float(round((dist_score + lh_score + sweep_score) / 3.0, 4))
    except Exception:
        return 0.0


def run_research_scoring(
    df: pd.DataFrame,
) -> dict:
    """
    Compute all three research scores for a signal's price DataFrame.
    Returns dict with res_* keys ready to merge into the signal record.
    """
    return {
        "res_compression_score":    round(compute_compression_score(df), 4),
        "res_vol_dryup_score":      round(compute_vol_dryup_score(df), 4),
        "res_support_failure_score": round(compute_support_failure_score(df), 4),
    }


# ── DB helpers ────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def init_research_schema(conn: sqlite3.Connection) -> None:
    """
    Create research tables and add res_* columns to signals.
    Safe to call on every startup — all operations are idempotent.
    """
    # New columns on signals table
    existing = {r[1] for r in conn.execute("PRAGMA table_info(signals)").fetchall()}
    res_cols = {
        "res_compression_score":     "REAL",
        "res_vol_dryup_score":       "REAL",
        "res_support_failure_score": "REAL",
    }
    for col, defn in res_cols.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE signals ADD COLUMN {col} {defn}")

    # research_hypotheses table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS research_hypotheses (
            id               TEXT PRIMARY KEY,
            name             TEXT NOT NULL,
            description      TEXT,
            status           TEXT NOT NULL DEFAULT 'Tracking',
            promotion_target TEXT,
            corr_mfe_40d     REAL,
            corr_r20d        REAL,
            q1_mfe_40d       REAL,
            q2_mfe_40d       REAL,
            q3_mfe_40d       REAL,
            q4_mfe_40d       REAL,
            q1_r20d          REAL,
            q2_r20d          REAL,
            q3_r20d          REAL,
            q4_r20d          REAL,
            incremental_r2   REAL,
            n_signals        INTEGER DEFAULT 0,
            win_rate_lift    REAL,
            last_validated   TEXT,
            created_at       TEXT NOT NULL,
            updated_at       TEXT NOT NULL
        )
    """)

    # research_log table (append-only)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS research_log (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            hypothesis_id  TEXT NOT NULL,
            logged_at      TEXT NOT NULL,
            event_type     TEXT NOT NULL,
            details_json   TEXT,
            FOREIGN KEY(hypothesis_id) REFERENCES research_hypotheses(id)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_rlog_hyp ON research_log(hypothesis_id)"
    )

    # Seed hypotheses if missing
    for h in _HYPOTHESES:
        exists = conn.execute(
            "SELECT 1 FROM research_hypotheses WHERE id = ?", (h["id"],)
        ).fetchone()
        if not exists:
            now = _now_iso()
            conn.execute(
                """INSERT INTO research_hypotheses
                   (id, name, description, status, promotion_target, created_at, updated_at)
                   VALUES (?, ?, ?, 'Tracking', ?, ?, ?)""",
                (h["id"], h["name"], h["description"], h["promotion_target"], now, now),
            )
            conn.execute(
                """INSERT INTO research_log (hypothesis_id, logged_at, event_type, details_json)
                   VALUES (?, ?, 'Created', ?)""",
                (h["id"], now, json.dumps({"note": "Hypothesis seeded"})),
            )
    conn.commit()


# ── Validation statistics ─────────────────────────────────────────────────────

def _pearson_r(x: np.ndarray, y: np.ndarray) -> Optional[float]:
    """Pearson r with minimum sample guard."""
    if len(x) < 10:
        return None
    try:
        r = float(np.corrcoef(x, y)[0, 1])
        return r if np.isfinite(r) else None
    except Exception:
        return None


def _quartile_means(score_col: np.ndarray, outcome_col: np.ndarray) -> tuple:
    """
    Split score_col into Q1-Q4 quartiles, return mean outcome per quartile.
    Q1 = lowest scores, Q4 = highest scores.
    Returns (q1_mean, q2_mean, q3_mean, q4_mean) or (None,)*4 if insufficient data.
    """
    if len(score_col) < 20:
        return None, None, None, None
    try:
        p25, p50, p75 = np.percentile(score_col, [25, 50, 75])
        q1 = outcome_col[score_col <= p25]
        q2 = outcome_col[(score_col > p25) & (score_col <= p50)]
        q3 = outcome_col[(score_col > p50) & (score_col <= p75)]
        q4 = outcome_col[score_col > p75]
        def _safe_mean(arr):
            return float(np.mean(arr)) if len(arr) >= 3 else None
        return _safe_mean(q1), _safe_mean(q2), _safe_mean(q3), _safe_mean(q4)
    except Exception:
        return None, None, None, None


def _incremental_r2(
    score_col: np.ndarray,
    outcome_col: np.ndarray,
    existing_features: np.ndarray,
) -> Optional[float]:
    """
    Compute incremental R² that score_col adds beyond existing_features.
    Returns R²_full - R²_baseline, or None if insufficient data.
    """
    if len(score_col) < 15:
        return None
    try:
        from numpy.linalg import lstsq
        y = outcome_col.reshape(-1, 1)

        def _r2(X):
            ones = np.ones((len(X), 1))
            Xb = np.hstack([ones, X])
            coef, _, _, _ = lstsq(Xb, y, rcond=None)
            pred = Xb @ coef
            ss_res = np.sum((y - pred) ** 2)
            ss_tot = np.sum((y - np.mean(y)) ** 2)
            return 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

        r2_base = _r2(existing_features)
        X_full  = np.hstack([existing_features, score_col.reshape(-1, 1)])
        r2_full = _r2(X_full)
        return float(round(r2_full - r2_base, 5))
    except Exception:
        return None


def _auto_status(
    current_status: str,
    corr_mfe: Optional[float],
    incr_r2: Optional[float],
    n: int,
    days_since_validated: Optional[int],
) -> str:
    """
    Determine hypothesis status from current evidence.
    Promoted, Rejected, and Retired are sticky — never auto-changed.
    """
    if current_status in ("Promoted", "Rejected", "Retired"):
        return current_status

    if n < 30:
        return "Tracking"

    if corr_mfe is None:
        return "Tracking"

    # Failing: weak or negative correlation for sustained period
    if corr_mfe < 0.05 and (days_since_validated is None or days_since_validated >= 14):
        return "Failing"

    # Improving: meaningful correlation + incremental alpha
    if corr_mfe >= 0.15 and incr_r2 is not None and incr_r2 >= 0.01:
        return "Improving"

    # Stable: moderate correlation, no strong incremental alpha
    if 0.05 <= corr_mfe < 0.15:
        return "Stable"

    return "Tracking"


def update_hypothesis_stats(conn: Optional[sqlite3.Connection] = None) -> None:
    """
    Recompute validation statistics for all non-terminal hypotheses.
    Called daily by the scheduler after outcome measurement.
    """
    _own_conn = conn is None
    if _own_conn:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

    try:
        init_research_schema(conn)

        rows = conn.execute(
            """
            SELECT s.res_compression_score,
                   s.res_vol_dryup_score,
                   s.res_support_failure_score,
                   bq.mfe_40d,
                   bq.r20d,
                   s.r1_price, s.r2_ob, s.r3_liquidity, s.r4_htf,
                   s.r5_avwap, s.r6_macd, s.r7_div, s.r8_demand
            FROM signals s
            JOIN bottom_quality bq ON s.id = bq.signal_id
            WHERE bq.mfe_40d IS NOT NULL
              AND bq.r20d IS NOT NULL
            """
        ).fetchall()

        if not rows:
            return

        df = pd.DataFrame([dict(r) for r in rows])

        # Existing factor features for incremental R² baseline
        factor_cols = ["r1_price", "r2_ob", "r3_liquidity", "r4_htf",
                       "r5_avwap", "r6_macd", "r7_div", "r8_demand"]
        existing = df[factor_cols].fillna(0).values

        score_map = {
            "compression_score":     "res_compression_score",
            "vol_dryup_score":       "res_vol_dryup_score",
            "support_failure_score": "res_support_failure_score",
        }

        now = _now_iso()

        for hyp_id, col_name in score_map.items():
            if col_name not in df.columns:
                continue
            sub = df[df[col_name].notna()].copy()
            if sub.empty:
                continue

            scores  = sub[col_name].values.astype(float)
            mfe_40d = sub["mfe_40d"].values.astype(float)
            r20d    = sub["r20d"].values.astype(float)
            feat_existing = sub[factor_cols].fillna(0).values
            n = len(scores)

            corr_mfe = _pearson_r(scores, mfe_40d)
            corr_r20 = _pearson_r(scores, r20d)
            incr_r2  = _incremental_r2(scores, mfe_40d, feat_existing)

            q1m, q2m, q3m, q4m = _quartile_means(scores, mfe_40d)
            q1r, q2r, q3r, q4r = _quartile_means(scores, r20d)

            # Win rate lift: Q4 vs Q1 on r20d >= 0.07
            wr_lift = None
            if q4m is not None and q1m is not None and n >= 20:
                try:
                    p25 = np.percentile(scores, 25)
                    p75 = np.percentile(scores, 75)
                    wr_q4 = np.mean(r20d[scores > p75] >= 0.07)
                    wr_q1 = np.mean(r20d[scores <= p25] >= 0.07)
                    wr_lift = float(round(wr_q4 - wr_q1, 4))
                except Exception:
                    pass

            # Current status
            hyp_row = conn.execute(
                "SELECT status, last_validated FROM research_hypotheses WHERE id = ?",
                (hyp_id,)
            ).fetchone()
            if not hyp_row:
                continue

            current_status = hyp_row["status"]
            last_val = hyp_row["last_validated"]
            days_since = None
            if last_val:
                try:
                    lv_dt = datetime.fromisoformat(last_val.replace("Z", "+00:00"))
                    days_since = (datetime.now(timezone.utc) - lv_dt).days
                except Exception:
                    pass

            new_status = _auto_status(current_status, corr_mfe, incr_r2, n, days_since)
            status_changed = new_status != current_status

            conn.execute(
                """UPDATE research_hypotheses SET
                   corr_mfe_40d   = ?,
                   corr_r20d      = ?,
                   q1_mfe_40d     = ?, q2_mfe_40d = ?, q3_mfe_40d = ?, q4_mfe_40d = ?,
                   q1_r20d        = ?, q2_r20d    = ?, q3_r20d    = ?, q4_r20d    = ?,
                   incremental_r2 = ?,
                   n_signals      = ?,
                   win_rate_lift  = ?,
                   status         = ?,
                   last_validated = ?,
                   updated_at     = ?
                   WHERE id = ?""",
                (
                    corr_mfe, corr_r20,
                    q1m, q2m, q3m, q4m,
                    q1r, q2r, q3r, q4r,
                    incr_r2, n, wr_lift,
                    new_status, now, now,
                    hyp_id,
                ),
            )

            details = {
                "corr_mfe_40d": corr_mfe,
                "corr_r20d": corr_r20,
                "incremental_r2": incr_r2,
                "n_signals": n,
                "win_rate_lift": wr_lift,
                "quartiles_mfe_40d": [q1m, q2m, q3m, q4m],
                "quartiles_r20d": [q1r, q2r, q3r, q4r],
            }
            if status_changed:
                details["status_change"] = f"{current_status} → {new_status}"

            conn.execute(
                """INSERT INTO research_log (hypothesis_id, logged_at, event_type, details_json)
                   VALUES (?, ?, ?, ?)""",
                (hyp_id, now,
                 "StatusChange" if status_changed else "Validated",
                 json.dumps(details, default=str)),
            )

        conn.commit()
    finally:
        if _own_conn:
            conn.close()


# ── Manual promotion / rejection / retirement ─────────────────────────────────

def _change_status(
    hypothesis_id: str,
    new_status: str,
    target: Optional[str] = None,
    note: str = "",
) -> None:
    """Internal helper for promote / reject / retire."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM research_hypotheses WHERE id = ?", (hypothesis_id,)
        ).fetchone()
        if not row:
            raise ValueError(f"Hypothesis '{hypothesis_id}' not found")

        now = _now_iso()
        params: dict = {"status": new_status, "updated_at": now}
        if target:
            params["promotion_target"] = target

        set_clause = ", ".join(f"{k} = ?" for k in params)
        vals = list(params.values()) + [hypothesis_id]
        conn.execute(
            f"UPDATE research_hypotheses SET {set_clause} WHERE id = ?", vals
        )
        conn.execute(
            """INSERT INTO research_log (hypothesis_id, logged_at, event_type, details_json)
               VALUES (?, ?, ?, ?)""",
            (hypothesis_id, now, new_status,
             json.dumps({"note": note, "target": target,
                         "previous_status": row["status"]},
                        default=str)),
        )
        conn.commit()
        print(f"[Research] {hypothesis_id}: {row['status']} → {new_status}")
    finally:
        conn.close()


def promote(hypothesis_id: str, target: str, note: str = "") -> None:
    """Mark a hypothesis as Promoted. Run manually after review."""
    valid = ("RankingFactor", "ConfidenceFactor", "ScannerFilter")
    if target not in valid:
        raise ValueError(f"target must be one of {valid}")
    _change_status(hypothesis_id, "Promoted", target=target, note=note)


def reject(hypothesis_id: str, note: str = "") -> None:
    """Mark a hypothesis as Rejected (tested, no alpha)."""
    _change_status(hypothesis_id, "Rejected", note=note)


def retire(hypothesis_id: str, note: str = "") -> None:
    """Mark a hypothesis as Retired (was valid, no longer relevant)."""
    _change_status(hypothesis_id, "Retired", note=note)


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    cmd = sys.argv[1] if len(sys.argv) > 1 else "update"

    if cmd == "update":
        print("[Research] Updating hypothesis stats …")
        update_hypothesis_stats()
        print("[Research] Done.")

    elif cmd == "promote":
        if len(sys.argv) < 4:
            print("Usage: python research_features.py promote <id> <target> [note]")
            sys.exit(1)
        promote(sys.argv[2], sys.argv[3], note=" ".join(sys.argv[4:]))

    elif cmd == "reject":
        if len(sys.argv) < 3:
            print("Usage: python research_features.py reject <id> [note]")
            sys.exit(1)
        reject(sys.argv[2], note=" ".join(sys.argv[3:]))

    elif cmd == "retire":
        if len(sys.argv) < 3:
            print("Usage: python research_features.py retire <id> [note]")
            sys.exit(1)
        retire(sys.argv[2], note=" ".join(sys.argv[3:]))

    elif cmd == "init":
        conn = sqlite3.connect(DB_PATH)
        init_research_schema(conn)
        conn.close()
        print("[Research] Schema initialised.")

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
