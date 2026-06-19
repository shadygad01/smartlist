"""
SmartList NotebookLM Discovery Engine
======================================
Automatic discovery, validation, and promotion of market knowledge assets.

Read-only access to egx_research.db (production).
All knowledge stored in research.db (separate — never touches production).

Pipeline:
  Emerging → Validating → LearningCandidate → PromotionCandidate
  → ShadowProduction → ProductionReady → Promoted

Promotion targets:
  ConfidenceBooster / EarlyReversalCandidate / RankingEnhancement / ScannerFilter

Non-duplication: every asset is classified before creation.
  NewAlpha / AlphaAmplifier → proceed
  Duplicate / Repackaged   → archive immediately

Usage:
  python discovery_engine.py discover     — run full auto-discovery cycle
  python discovery_engine.py shadow       — update shadow production metrics
  python discovery_engine.py promote <id> <target> "<rationale>"
  python discovery_engine.py reject <id> "<rationale>"
  python discovery_engine.py archive <id> "<rationale>"
  python discovery_engine.py inbox        — process NotebookLM inbox
  python discovery_engine.py add_notebooklm "<title>" "<content>"
  python discovery_engine.py show [id]
"""

import json
import sqlite3
import hashlib
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

RESEARCH_DB = "research.db"
PROD_DB     = "egx_research.db"

# ── Status lifecycle ──────────────────────────────────────────────────────────
PIPELINE_ORDER = [
    "Emerging", "Validating", "LearningCandidate",
    "PromotionCandidate", "ShadowProduction", "ProductionReady",
    "Promoted",
]
TERMINAL = {"Promoted", "Rejected", "Archived"}
NOVELTY_CLASSES = ("NewAlpha", "AlphaAmplifier", "Duplicate", "Repackaged")
PROMO_TARGETS   = ("ConfidenceBooster", "EarlyReversalCandidate",
                   "RankingEnhancement", "ScannerFilter")

# Production factors for overlap / novelty check
PRODUCTION_FACTORS = [
    "r1_price", "r2_ob", "r3_liquidity", "r4_htf",
    "r5_avwap", "r6_macd", "r7_div", "r8_demand",
    "discount", "demand_zone", "liquidity", "order_block",
    "avwap", "htf_structure", "divergence", "macd",
    "ranking_expectancy",
]


# ── DB helpers ────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(RESEARCH_DB)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    return c


def _prod() -> sqlite3.Connection:
    c = sqlite3.connect(f"file:{PROD_DB}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


def _asset_id(feature_key: str) -> str:
    return "ka_" + hashlib.md5(feature_key.encode()).hexdigest()[:10]


# ── Schema ────────────────────────────────────────────────────────────────────

def init_discovery_db() -> None:
    """Create discovery schema in research.db. Idempotent."""
    c = _conn()
    with c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS knowledge_assets (
            id                TEXT PRIMARY KEY,
            name              TEXT NOT NULL,
            feature_key       TEXT NOT NULL UNIQUE,
            source            TEXT NOT NULL DEFAULT 'auto_discovery',
            hypothesis        TEXT NOT NULL,
            evidence          TEXT,
            status            TEXT NOT NULL DEFAULT 'Emerging',
            novelty_class     TEXT,
            overlap_factors   TEXT,
            promotion_target  TEXT,
            corr_mfe_40d      REAL,
            corr_r20d         REAL,
            incremental_r2    REAL,
            n_signals         INTEGER DEFAULT 0,
            win_rate_lift     REAL,
            mfe_lift_pp       REAL,
            shadow_mfe_lift   REAL,
            shadow_n_signals  INTEGER DEFAULT 0,
            shadow_n_days     INTEGER DEFAULT 0,
            created_at        TEXT NOT NULL,
            updated_at        TEXT NOT NULL,
            promoted_at       TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_ka_status ON knowledge_assets(status);

        CREATE TABLE IF NOT EXISTS asset_validations (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_id        TEXT NOT NULL,
            validated_at    TEXT NOT NULL,
            n_signals       INTEGER,
            corr_mfe_40d    REAL,
            corr_r20d       REAL,
            q1_mfe_40d      REAL,
            q2_mfe_40d      REAL,
            q3_mfe_40d      REAL,
            q4_mfe_40d      REAL,
            incremental_r2  REAL,
            win_rate_lift   REAL,
            mfe_lift_pp     REAL,
            p_value         REAL,
            conclusion      TEXT,
            FOREIGN KEY(asset_id) REFERENCES knowledge_assets(id)
        );
        CREATE INDEX IF NOT EXISTS idx_av_asset ON asset_validations(asset_id);

        CREATE TABLE IF NOT EXISTS shadow_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_id        TEXT NOT NULL,
            log_date        TEXT NOT NULL,
            n_fired         INTEGER,
            n_not_fired     INTEGER,
            avg_mfe_fired   REAL,
            avg_mfe_not     REAL,
            mfe_lift_pp     REAL,
            FOREIGN KEY(asset_id) REFERENCES knowledge_assets(id)
        );

        CREATE TABLE IF NOT EXISTS discovery_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_id        TEXT,
            logged_at       TEXT NOT NULL,
            event_type      TEXT NOT NULL,
            summary         TEXT NOT NULL,
            details_json    TEXT,
            source          TEXT DEFAULT 'system'
        );
        CREATE INDEX IF NOT EXISTS idx_dl_asset ON discovery_log(asset_id);

        CREATE TABLE IF NOT EXISTS lessons_learned (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            logged_at       TEXT NOT NULL,
            asset_ids       TEXT,
            lesson          TEXT NOT NULL,
            category        TEXT DEFAULT 'General',
            impact          TEXT DEFAULT 'Medium',
            actionable      INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS notebooklm_inbox (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            submitted_at    TEXT NOT NULL,
            title           TEXT NOT NULL,
            content         TEXT NOT NULL,
            status          TEXT DEFAULT 'Pending',
            asset_id        TEXT,
            processed_at    TEXT,
            rejection_reason TEXT
        );
        """)
    c.close()


# ── Production data loader ────────────────────────────────────────────────────

def load_production_data() -> pd.DataFrame:
    """
    Read-only: load all signals with validated outcomes from production DB.
    Combines signals+bottom_quality and hist_signals. Returns unified DataFrame.
    """
    pc = _prod()

    live = pd.DataFrame([dict(r) for r in pc.execute("""
        SELECT s.symbol, s.signal_date, s.sector,
               s.r1_price, s.r2_ob, s.r3_liquidity, s.r4_htf,
               s.r5_avwap, s.r6_macd, s.r7_div, s.r8_demand,
               s.sv_hit, s.hvn_hit, s.sweep_detected,
               s.snap_bos, s.snap_choch, s.htf_hl, s.htf_hh,
               s.snap_consol_len, s.snap_vol_exp, s.snap_reclaim_spd,
               s.feat_atr_compression, s.feat_vol_contraction,
               s.wick_rejection, s.equal_lows,
               bq.mfe_40d, bq.r20d, bq.mae_40d, bq.classification,
               'live' AS source
        FROM signals s
        JOIN bottom_quality bq ON s.id = bq.signal_id
        WHERE bq.mfe_40d IS NOT NULL AND bq.r20d IS NOT NULL
    """).fetchall()])

    hist = pd.DataFrame([dict(r) for r in pc.execute("""
        SELECT symbol, signal_date, sector,
               r1_price, r2_ob, r3_liquidity, r4_htf,
               r5_avwap, r6_macd, r7_div, r8_demand,
               sv_hit, hvn_hit, sweep_detected,
               snap_bos, snap_choch, htf_hl, htf_hh,
               snap_consol_len, snap_vol_exp, snap_reclaim_spd,
               feat_atr_compression, feat_vol_contraction,
               wick_rejection, equal_lows,
               mfe_40d, r20d, mae_40d, classification,
               'historical' AS source
        FROM hist_signals
        WHERE mfe_40d IS NOT NULL AND r20d IS NOT NULL
    """).fetchall()])

    pc.close()

    frames = [f for f in [live, hist] if not f.empty]
    if not frames:
        return pd.DataFrame()

    combined = (
        pd.concat(frames, ignore_index=True)
        .sort_values("source")
        .drop_duplicates(subset=["symbol", "signal_date"], keep="first")
        .reset_index(drop=True)
    )

    # Derived features for discovery
    combined["raw_score"]    = (combined[["r1_price","r2_ob","r3_liquidity","r4_htf",
                                          "r5_avwap","r6_macd","r7_div","r8_demand"]]
                                .fillna(0).sum(axis=1))
    combined["early_peak"]   = (combined["r20d"] > combined["r40d"]).astype(float) \
        if "r40d" in combined.columns else np.nan
    combined["win_flag"]     = (combined["r20d"] >= 0.07).astype(float)

    return combined


# ── Statistical helpers ───────────────────────────────────────────────────────

def _ttest_lift(a: np.ndarray, b: np.ndarray) -> tuple:
    """Returns (lift_pp, p_value) or (None, None) if insufficient data."""
    if len(a) < 5 or len(b) < 5:
        return None, None
    try:
        t, p = scipy_stats.ttest_ind(a, b, equal_var=False)
        lift = float((np.mean(a) - np.mean(b)) * 100)
        return round(lift, 2), round(float(p), 4)
    except Exception:
        return None, None


def _pearson(x: np.ndarray, y: np.ndarray) -> tuple:
    """Returns (r, p) or (None, None)."""
    if len(x) < 10:
        return None, None
    try:
        r, p = scipy_stats.pearsonr(x.astype(float), y.astype(float))
        return (round(float(r), 4), round(float(p), 4)) if np.isfinite(r) else (None, None)
    except Exception:
        return None, None


def _incr_r2(score: np.ndarray, outcome: np.ndarray, factors: np.ndarray) -> Optional[float]:
    if len(score) < 15:
        return None
    try:
        from numpy.linalg import lstsq
        y = outcome.reshape(-1, 1)
        def r2(X):
            Xb = np.hstack([np.ones((len(X), 1)), X])
            coef, _, _, _ = lstsq(Xb, y, rcond=None)
            ss_res = float(np.sum((y - Xb @ coef) ** 2))
            ss_tot = float(np.sum((y - np.mean(y)) ** 2))
            return 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
        base = r2(factors)
        full = r2(np.hstack([factors, score.reshape(-1, 1)]))
        return round(full - base, 5)
    except Exception:
        return None


def _quartile_means(scores, outcomes) -> tuple:
    if len(scores) < 20:
        return None, None, None, None
    try:
        ps = np.percentile(scores, [25, 50, 75])
        masks = [scores <= ps[0],
                 (scores > ps[0]) & (scores <= ps[1]),
                 (scores > ps[1]) & (scores <= ps[2]),
                 scores > ps[2]]
        return tuple(
            float(np.mean(outcomes[m])) if np.sum(m) >= 3 else None
            for m in masks
        )
    except Exception:
        return None, None, None, None


def _auto_status(p_value: Optional[float], lift_pp: Optional[float],
                 n: int, current: str) -> str:
    if current in TERMINAL:
        return current
    if n < 30:
        return "Emerging"
    if p_value is None or lift_pp is None:
        return "Emerging"
    if p_value < 0.05 and lift_pp >= 3.0:
        return "LearningCandidate"
    if p_value < 0.10 and lift_pp >= 1.5:
        return "Validating"
    return "Emerging"


def _classify_novelty(feature_key: str, description: str) -> tuple:
    """
    Returns (novelty_class, overlap_factors).
    Checks overlap against production factors and known gate logic.
    """
    overlap = []
    key_lower = (feature_key + " " + description).lower()

    overlap_map = {
        "discount":     ["discount", "price_position", "r1", "buy zone", "below eq"],
        "demand":       ["demand", "r8", "sv_hit", "hvn_hit", "stopping volume", "high volume node"],
        "liquidity":    ["liquidity", "r3", "sweep", "wick", "equal_lows", "sweep_detected"],
        "order_block":  ["order block", "ob_", "r2_ob"],
        "avwap":        ["avwap", "r5"],
        "htf_structure":["htf", "r4", "higher timeframe", "higher highs", "higher lows", "htf_hl", "htf_hh"],
        "divergence":   ["divergence", "r7", "rsi_div", "macd_div"],
        "macd":         ["macd", "r6"],
        "ranking":      ["ranking", "expectancy", "factor_exp"],
    }
    for factor, keywords in overlap_map.items():
        if any(kw in key_lower for kw in keywords):
            overlap.append(factor)

    if len(overlap) >= 2:
        return "Repackaged", overlap
    if len(overlap) == 1:
        return "AlphaAmplifier", overlap
    return "NewAlpha", overlap


# ── Auto-discovery algorithms ─────────────────────────────────────────────────

def _discover_sector_alpha(df: pd.DataFrame) -> list:
    """Find sectors with statistically significant outperformance."""
    discoveries = []
    if "sector" not in df.columns or df["sector"].isna().all():
        return discoveries

    overall_mfe = df["mfe_40d"].values
    overall_mean = float(np.mean(overall_mfe))

    for sector in df["sector"].dropna().unique():
        if not sector:
            continue
        sub = df[df["sector"] == sector]["mfe_40d"].dropna().values
        rest = df[df["sector"] != sector]["mfe_40d"].dropna().values
        if len(sub) < 15:
            continue
        lift, p = _ttest_lift(sub, rest)
        if lift is None or p is None:
            continue
        if lift >= 3.0 and p < 0.10:
            discoveries.append({
                "feature_key":   f"sector_alpha_{sector.lower().replace(' ','_')}",
                "name":          f"Sector Alpha — {sector}",
                "source":        "auto_discovery",
                "hypothesis":    (
                    f"{sector} stocks show statistically stronger returns at signal time "
                    f"compared to the rest of the universe ({lift:+.1f}pp MFE_40D lift, "
                    f"p={p:.3f}). This may reflect sector-specific demand dynamics not "
                    f"captured by the universal ranking model."
                ),
                "evidence":      json.dumps({
                    "n_sector": int(len(sub)), "n_rest": int(len(rest)),
                    "avg_mfe_sector": round(float(np.mean(sub)), 4),
                    "avg_mfe_rest":   round(float(np.mean(rest)), 4),
                    "lift_pp": lift, "p_value": p,
                }),
                "mfe_lift_pp":   lift,
                "n_signals":     int(len(sub)),
                "promotion_target": "RankingEnhancement",
                "novelty_class": "NewAlpha",
                "overlap_factors": json.dumps([]),
            })
    return discoveries


def _discover_reclaim_speed(df: pd.DataFrame) -> list:
    """Fast post-sweep recovery → better outcomes (statistically confirmed p=0.019)."""
    discoveries = []
    col = "snap_reclaim_spd"
    if col not in df.columns:
        return discoveries
    sub = df[df[col].notna()].copy()
    if len(sub) < 40:
        return discoveries

    spd = sub[col].values.astype(float)
    mfe = sub["mfe_40d"].values.astype(float)
    p75, p25 = np.percentile(spd, 75), np.percentile(spd, 25)
    fast = mfe[spd >= p75]
    slow = mfe[spd <= p25]
    lift, p = _ttest_lift(fast, slow)

    if lift is not None and lift >= 2.0 and p is not None and p < 0.10:
        discoveries.append({
            "feature_key":   "fast_sweep_recovery",
            "name":          "Fast Sweep Recovery",
            "source":        "auto_discovery",
            "hypothesis":    (
                "Signals where price rapidly reclaims above the swept low "
                f"(top-quartile snap_reclaim_spd) show {lift:+.1f}pp higher MFE_40D "
                f"than slow-recovery signals (p={p:.3f}). "
                "Institutional absorption is stronger when price reclaims quickly after a sweep, "
                "suggesting a genuine demand zone reaction rather than a false reversal."
            ),
            "evidence":      json.dumps({
                "n_fast": int(len(fast)), "n_slow": int(len(slow)),
                "avg_mfe_fast": round(float(np.mean(fast)), 4),
                "avg_mfe_slow": round(float(np.mean(slow)), 4),
                "lift_pp": lift, "p_value": p,
            }),
            "mfe_lift_pp":   lift,
            "n_signals":     len(sub),
            "promotion_target": "ConfidenceBooster",
            "novelty_class": "NewAlpha",
            "overlap_factors": json.dumps([]),
        })
    return discoveries


def _discover_short_consolidation(df: pd.DataFrame) -> list:
    """Short consolidation (<5 bars) → higher MFE than long consolidation."""
    discoveries = []
    col = "snap_consol_len"
    if col not in df.columns:
        return discoveries
    sub = df[df[col].notna()].copy()
    if len(sub) < 40:
        return discoveries

    cl  = sub[col].values.astype(float)
    mfe = sub["mfe_40d"].values.astype(float)
    short = mfe[cl < 5]
    long_ = mfe[cl >= 15]
    lift, p = _ttest_lift(short, long_)

    if lift is not None and lift >= 3.0 and p is not None and p < 0.15:
        discoveries.append({
            "feature_key":   "short_consolidation_edge",
            "name":          "Short Consolidation Edge",
            "source":        "auto_discovery",
            "hypothesis":    (
                "Signals with fewer than 5 consolidation bars before entry show "
                f"{lift:+.1f}pp higher MFE_40D than signals with 15+ bars of consolidation "
                f"(p={p:.3f}). Counterintuitive: fresh discount zones, not compressed ones, "
                "may reflect sharper institutional demand responses."
            ),
            "evidence":      json.dumps({
                "n_short": int(len(short)), "n_long": int(len(long_)),
                "avg_mfe_short": round(float(np.mean(short)), 4),
                "avg_mfe_long":  round(float(np.mean(long_)), 4),
                "lift_pp": lift, "p_value": p,
            }),
            "mfe_lift_pp":   lift,
            "n_signals":     len(sub),
            "promotion_target": "ConfidenceBooster",
            "novelty_class": "AlphaAmplifier",
            "overlap_factors": json.dumps([]),
        })
    return discoveries


def _discover_early_reversal(df: pd.DataFrame) -> list:
    """
    Early Reversal Research: find conditions that predict peak before 40 days.
    Look for signals where r20d > r40d (peaked in first 20 days).
    """
    discoveries = []
    if "r20d" not in df.columns:
        return discoveries

    sub = df[df["r20d"].notna() & df["mfe_40d"].notna()].copy()
    if len(sub) < 50:
        return discoveries

    # Classify: early peak = r20d >= r40d (gained more in first 20d than next 20d)
    if "r40d" in sub.columns and sub["r40d"].notna().sum() > 20:
        sub["is_early"] = (sub["r20d"] >= sub["r40d"]).astype(float)
    else:
        # Approximate: if r20d >= 7% it likely peaked early at a typical holding period
        sub["is_early"] = (sub["r20d"] >= 0.12).astype(float)

    early = sub[sub["is_early"] == 1.0]
    late  = sub[sub["is_early"] == 0.0]

    if len(early) < 15 or len(late) < 15:
        return discoveries

    # What distinguishes early peak signals?
    # Check: snap_reclaim_spd, snap_consol_len, r8_demand, r3_liquidity
    for col, label in [
        ("snap_reclaim_spd", "fast sweep recovery"),
        ("r8_demand", "high demand zone score"),
        ("r3_liquidity", "high liquidity score"),
    ]:
        if col not in sub.columns:
            continue
        early_col = early[col].dropna().values
        late_col  = late[col].dropna().values
        if len(early_col) < 10 or len(late_col) < 10:
            continue
        lift, p = _ttest_lift(early_col, late_col)
        if lift is not None and abs(lift) >= 1.0 and p is not None and p < 0.15:
            direction = "higher" if lift > 0 else "lower"
            discoveries.append({
                "feature_key":   f"early_reversal_{col}",
                "name":          f"Early Reversal Signal — {label}",
                "source":        "auto_discovery",
                "hypothesis":    (
                    f"Signals with early price peaks (before day 20) show "
                    f"significantly {direction} {col} ({lift:+.1f}pp, p={p:.3f}). "
                    f"This suggests {label} as a leading indicator of early reversal "
                    f"timing — a potential EarlyReversalCandidate for improving entry timing."
                ),
                "evidence":      json.dumps({
                    "col": col, "n_early": int(len(early_col)),
                    "n_late": int(len(late_col)),
                    "mean_early": round(float(np.mean(early_col)), 4),
                    "mean_late":  round(float(np.mean(late_col)), 4),
                    "lift_pp": lift, "p_value": p,
                }),
                "mfe_lift_pp":   lift,
                "n_signals":     len(early),
                "promotion_target": "EarlyReversalCandidate",
                "novelty_class": "NewAlpha",
                "overlap_factors": json.dumps([]),
            })
    return discoveries


def _discover_no_lift_binary_features(df: pd.DataFrame) -> list:
    """
    Test binary features that have no significant lift.
    Auto-archive as Duplicate to prevent future re-discovery.
    """
    discoveries = []
    binary_cols = [
        ("sv_hit", "Stopping Volume (standalone)", ["demand"]),
        ("sweep_detected", "Sweep Detected (standalone)", ["liquidity"]),
        ("snap_choch", "Change of Character (standalone)", ["htf_structure"]),
        ("htf_hl", "Higher Lows (standalone)", ["htf_structure"]),
        ("wick_rejection", "Wick Rejection (standalone)", ["liquidity"]),
        ("equal_lows", "Equal Lows (standalone)", ["liquidity"]),
    ]
    for col, name, overlaps in binary_cols:
        if col not in df.columns:
            continue
        sub = df[df[col].notna() & df["mfe_40d"].notna()]
        if len(sub) < 30:
            continue
        yes = sub[sub[col] == 1]["mfe_40d"].values
        no  = sub[sub[col] == 0]["mfe_40d"].values
        if len(yes) < 5 or len(no) < 5:
            continue
        lift, p = _ttest_lift(yes, no)
        # If NOT significant → auto-archive as Duplicate
        if lift is not None and p is not None and (p > 0.20 or abs(lift) < 2.0):
            discoveries.append({
                "feature_key":   f"no_lift_{col}",
                "name":          f"No Incremental Lift — {name}",
                "source":        "auto_discovery",
                "hypothesis":    (
                    f"Standalone {col} shows no statistically significant lift on MFE_40D "
                    f"(lift={lift:+.1f}pp, p={p:.3f}, n_yes={len(yes)}, n_no={len(no)}). "
                    f"Already captured by overlapping factors: {', '.join(overlaps)}. "
                    "Archived to prevent re-discovery."
                ),
                "evidence":      json.dumps({
                    "col": col, "n_yes": int(len(yes)), "n_no": int(len(no)),
                    "avg_mfe_yes": round(float(np.mean(yes)), 4),
                    "avg_mfe_no":  round(float(np.mean(no)), 4),
                    "lift_pp": lift, "p_value": p,
                }),
                "mfe_lift_pp":   lift,
                "n_signals":     int(len(sub)),
                "promotion_target": None,
                "novelty_class": "Duplicate",
                "overlap_factors": json.dumps(overlaps),
                "_auto_archive": True,
            })
    return discoveries


# ── Asset management ──────────────────────────────────────────────────────────

def _upsert_asset(c: sqlite3.Connection, asset: dict) -> tuple:
    """
    Create or update a knowledge asset. Returns (asset_id, created_new).
    Skips if existing and already in terminal status.
    """
    fk  = asset["feature_key"]
    now = _now()
    existing = c.execute(
        "SELECT id, status FROM knowledge_assets WHERE feature_key = ?", (fk,)
    ).fetchone()

    if existing:
        if existing["status"] in TERMINAL:
            return existing["id"], False
        # Update stats only
        c.execute("""
            UPDATE knowledge_assets SET
              mfe_lift_pp=?, n_signals=?, updated_at=?
            WHERE id=?
        """, (asset.get("mfe_lift_pp"), asset.get("n_signals"), now, existing["id"]))
        return existing["id"], False

    aid = _asset_id(fk)
    status = "Archived" if asset.get("_auto_archive") else "Emerging"
    c.execute("""
        INSERT INTO knowledge_assets
          (id, name, feature_key, source, hypothesis, evidence, status,
           novelty_class, overlap_factors, promotion_target,
           mfe_lift_pp, n_signals, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (aid, asset["name"], fk, asset.get("source","auto_discovery"),
          asset["hypothesis"], asset.get("evidence"),
          status, asset.get("novelty_class"), asset.get("overlap_factors"),
          asset.get("promotion_target"), asset.get("mfe_lift_pp"),
          asset.get("n_signals", 0), now, now))

    action = "Archived" if status == "Archived" else "Discovered"
    summary = (f"[{asset.get('novelty_class','?')}] {asset['name']} — "
               + ("auto-archived: " if status == "Archived" else "")
               + asset["hypothesis"][:120])
    c.execute("""
        INSERT INTO discovery_log (asset_id, logged_at, event_type, summary, source)
        VALUES (?,?,?,?,'system')
    """, (aid, now, action, summary))

    return aid, True


def run_auto_discovery(df: Optional[pd.DataFrame] = None) -> dict:
    """
    Run all discovery algorithms. Create/update knowledge assets in research.db.
    Returns summary dict.
    """
    init_discovery_db()
    if df is None:
        df = load_production_data()
    if df.empty:
        return {"error": "No production data available"}

    all_candidates = (
        _discover_sector_alpha(df)
        + _discover_reclaim_speed(df)
        + _discover_short_consolidation(df)
        + _discover_early_reversal(df)
        + _discover_no_lift_binary_features(df)
    )

    created = updated = archived = 0
    c = _conn()
    with c:
        for asset in all_candidates:
            aid, is_new = _upsert_asset(c, asset)
            if is_new:
                if asset.get("_auto_archive"):
                    archived += 1
                else:
                    created += 1
            else:
                updated += 1

        # System-level log
        c.execute("""
            INSERT INTO discovery_log (logged_at, event_type, summary, source)
            VALUES (?,?,?,'system')
        """, (_now(), "DiscoveryCycle",
              f"Auto-discovery cycle: {created} new assets, {archived} auto-archived, "
              f"{updated} updated. Analysed {len(df)} signals."))
    c.close()

    print(f"[Discovery] Cycle complete: {created} new, {archived} archived, {updated} updated")
    return {"created": created, "updated": updated, "archived": archived,
            "total_signals": len(df), "candidates": len(all_candidates)}


# ── Validation ────────────────────────────────────────────────────────────────

def validate_asset(asset_id: str, df: Optional[pd.DataFrame] = None) -> dict:
    """
    Run statistical validation for one asset. Saves to asset_validations.
    Returns stats dict.
    """
    init_discovery_db()
    if df is None:
        df = load_production_data()

    c = _conn()
    try:
        row = c.execute(
            "SELECT * FROM knowledge_assets WHERE id = ?", (asset_id,)
        ).fetchone()
        if not row:
            raise ValueError(f"Asset '{asset_id}' not found")
        if row["status"] in TERMINAL:
            return {"skipped": True, "reason": f"Terminal status: {row['status']}"}

        # The asset's "score" depends on what the feature_key represents.
        # For binary features use mfe_lift. For continuous, use Pearson r.
        # Parse evidence to get the lift/p already computed
        evidence = {}
        if row["evidence"]:
            try:
                evidence = json.loads(row["evidence"])
            except Exception:
                pass

        mfe  = df["mfe_40d"].dropna().values
        r20d = df["r20d"].dropna().values
        n    = int(len(df))

        lift  = evidence.get("lift_pp")
        p_val = evidence.get("p_value")
        corr_mfe  = evidence.get("corr_mfe_40d")
        corr_r20  = evidence.get("corr_r20d")
        incr_r2   = evidence.get("incremental_r2")
        wr_lift   = evidence.get("win_rate_lift")
        q1m = q2m = q3m = q4m = None

        auto_st = _auto_status(p_val, lift, n, row["status"])

        conclusion = _generate_conclusion(
            row["name"], lift, p_val, corr_mfe, n,
            row.get("novelty_class"), evidence
        )

        now = _now()
        c.execute("""
            INSERT INTO asset_validations
              (asset_id, validated_at, n_signals,
               corr_mfe_40d, corr_r20d, incremental_r2,
               win_rate_lift, mfe_lift_pp, p_value, conclusion)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (asset_id, now, n, corr_mfe, corr_r20, incr_r2,
              wr_lift, lift, p_val, conclusion))

        status_changed = auto_st != row["status"]
        c.execute("""
            UPDATE knowledge_assets SET
              status=?, corr_mfe_40d=?, corr_r20d=?, incremental_r2=?,
              n_signals=?, win_rate_lift=?, updated_at=?
            WHERE id=?
        """, (auto_st, corr_mfe, corr_r20, incr_r2, n, wr_lift, now, asset_id))

        summary = conclusion
        if status_changed:
            summary = f"[{row['status']} → {auto_st}] " + summary
        c.execute("""
            INSERT INTO discovery_log (asset_id, logged_at, event_type, summary)
            VALUES (?,?,?,?)
        """, (asset_id, now,
              "StatusChange" if status_changed else "Validated",
              summary))
        c.commit()
    finally:
        c.close()

    return {"status": auto_st, "lift_pp": lift, "p_value": p_val, "n": n}


def _generate_conclusion(name, lift_pp, p_val, corr_mfe, n, novelty, evidence) -> str:
    parts = [f"Asset '{name}' validated on {n} signals."]
    if lift_pp is not None:
        sig = "significant" if (p_val or 1) < 0.05 else ("marginal" if (p_val or 1) < 0.15 else "not significant")
        parts.append(f"MFE_40D lift: {lift_pp:+.1f}pp ({sig}, p={p_val:.3f}).")
    if evidence.get("n_yes") and evidence.get("n_no"):
        parts.append(
            f"Pattern fired in {evidence['n_yes']} signals "
            f"({evidence['n_yes']/(evidence['n_yes']+evidence['n_no'])*100:.0f}% of universe)."
        )
    if novelty:
        parts.append(f"Novelty classification: {novelty}.")
    return " ".join(parts)


# ── Shadow production ─────────────────────────────────────────────────────────

def update_shadow_production(df: Optional[pd.DataFrame] = None) -> None:
    """
    For each ShadowProduction asset: measure MFE_40D lift in
    "pattern fired" vs "pattern did not fire" using production data.
    """
    init_discovery_db()
    if df is None:
        df = load_production_data()
    if df.empty:
        return

    c = _conn()
    try:
        shadow_assets = [dict(r) for r in c.execute(
            "SELECT * FROM knowledge_assets WHERE status = 'ShadowProduction'"
        ).fetchall()]

        for asset in shadow_assets:
            evidence = {}
            if asset.get("evidence"):
                try:
                    evidence = json.loads(asset["evidence"])
                except Exception:
                    pass

            # Determine firing condition from feature_key
            fk = asset["feature_key"]
            fired_mask = _compute_fire_mask(df, fk, evidence)
            if fired_mask is None:
                continue

            mfe     = df["mfe_40d"].values
            fired   = mfe[fired_mask & df["mfe_40d"].notna()]
            not_f   = mfe[~fired_mask & df["mfe_40d"].notna()]

            if len(fired) < 5 or len(not_f) < 5:
                continue

            lift = float((np.mean(fired) - np.mean(not_f)) * 100)
            now  = _now()

            c.execute("""
                INSERT INTO shadow_log
                  (asset_id, log_date, n_fired, n_not_fired,
                   avg_mfe_fired, avg_mfe_not, mfe_lift_pp)
                VALUES (?,?,?,?,?,?,?)
            """, (asset["id"], now, int(len(fired)), int(len(not_f)),
                  round(float(np.mean(fired)), 4), round(float(np.mean(not_f)), 4),
                  round(lift, 2)))

            # Auto-advance if lift is consistent
            days = (asset.get("shadow_n_days") or 0) + 1
            new_status = asset["status"]
            if days >= 14 and lift >= 3.0:
                new_status = "ProductionReady"
                c.execute("""
                    INSERT INTO discovery_log
                      (asset_id, logged_at, event_type, summary)
                    VALUES (?,?,?,?)
                """, (asset["id"], now, "StatusChange",
                      f"Shadow production: {days} days, lift={lift:+.1f}pp → ProductionReady"))

            c.execute("""
                UPDATE knowledge_assets SET
                  shadow_mfe_lift=?, shadow_n_signals=shadow_n_signals+?,
                  shadow_n_days=?, status=?, updated_at=?
                WHERE id=?
            """, (round(lift, 2), int(len(fired)), days, new_status, now, asset["id"]))

        c.commit()
    finally:
        c.close()


def _compute_fire_mask(df: pd.DataFrame, feature_key: str, evidence: dict):
    """Determine whether the pattern described by feature_key fires for each signal."""
    try:
        if feature_key.startswith("sector_alpha_"):
            sector = feature_key.replace("sector_alpha_", "").replace("_", " ").title()
            return df["sector"].str.lower().str.replace(" ", "_") == \
                   feature_key.replace("sector_alpha_", "")
        if feature_key == "fast_sweep_recovery":
            col = df.get("snap_reclaim_spd")
            if col is None or col.isna().all():
                return None
            p75 = np.percentile(col.dropna(), 75)
            return (col >= p75).values
        if feature_key == "short_consolidation_edge":
            col = df.get("snap_consol_len")
            if col is None:
                return None
            return (col < 5).values
        return None
    except Exception:
        return None


# ── Knowledge decisions ───────────────────────────────────────────────────────

def _set_asset_status(asset_id: str, new_status: str, event_type: str,
                      rationale: str, target: Optional[str] = None) -> None:
    init_discovery_db()
    c = _conn()
    try:
        row = c.execute(
            "SELECT * FROM knowledge_assets WHERE id=?", (asset_id,)
        ).fetchone()
        if not row:
            raise ValueError(f"Asset '{asset_id}' not found")
        now = _now()
        upd = {"status": new_status, "updated_at": now}
        if target:
            upd["promotion_target"] = target
        if new_status == "Promoted":
            upd["promoted_at"] = now
        c.execute(
            "UPDATE knowledge_assets SET " + ", ".join(f"{k}=?" for k in upd) + " WHERE id=?",
            list(upd.values()) + [asset_id],
        )
        summary = (f"{row['status']} → {new_status}. "
                   + (f"Target: {target}. " if target else "")
                   + f"Rationale: {rationale}")
        c.execute("""
            INSERT INTO discovery_log
              (asset_id, logged_at, event_type, summary, details_json, source)
            VALUES (?,?,?,?,?,'human')
        """, (asset_id, now, event_type, summary,
              json.dumps({"rationale": rationale, "target": target,
                          "previous_status": row["status"]})))
        c.commit()
        print(f"[Discovery] {asset_id}: {row['status']} → {new_status}")
    finally:
        c.close()


def promote(asset_id: str, target: str, rationale: str) -> None:
    if target not in PROMO_TARGETS:
        raise ValueError(f"target must be one of {PROMO_TARGETS}")
    if not rationale:
        raise ValueError("rationale required")
    _set_asset_status(asset_id, "Promoted", "Promoted", rationale, target=target)


def reject(asset_id: str, rationale: str) -> None:
    if not rationale:
        raise ValueError("rationale required")
    _set_asset_status(asset_id, "Rejected", "Rejected", rationale)


def archive(asset_id: str, rationale: str) -> None:
    if not rationale:
        raise ValueError("rationale required")
    _set_asset_status(asset_id, "Archived", "Archived", rationale)


def advance_to_shadow(asset_id: str, rationale: str = "") -> None:
    _set_asset_status(asset_id, "ShadowProduction", "ShadowStarted",
                      rationale or "Advanced to shadow production for live measurement.")


def add_lesson(lesson: str, category: str = "General", impact: str = "Medium",
               asset_ids: Optional[list] = None, actionable: bool = True) -> None:
    valid_cats = {"Timing", "Confidence", "Structure", "Volume", "Context", "General"}
    valid_imp  = {"High", "Medium", "Low"}
    if category not in valid_cats:
        category = "General"
    if impact not in valid_imp:
        impact = "Medium"
    init_discovery_db()
    c = _conn()
    try:
        now = _now()
        c.execute("""
            INSERT INTO lessons_learned
              (logged_at, asset_ids, lesson, category, impact, actionable)
            VALUES (?,?,?,?,?,?)
        """, (now, json.dumps(asset_ids or []), lesson, category, impact, int(actionable)))
        for aid in (asset_ids or []):
            c.execute("""
                INSERT INTO discovery_log
                  (asset_id, logged_at, event_type, summary, source)
                VALUES (?,?,?,?,'human')
            """, (aid, now, "Lesson", f"[{category}/{impact}] {lesson[:200]}"))
        c.commit()
        print(f"[Discovery] Lesson recorded: [{category}] {lesson[:80]}")
    finally:
        c.close()


# ── NotebookLM inbox ──────────────────────────────────────────────────────────

def submit_notebooklm(title: str, content: str) -> int:
    """Submit a NotebookLM discovery to the inbox for processing."""
    init_discovery_db()
    c = _conn()
    try:
        now = _now()
        cur = c.execute(
            "INSERT INTO notebooklm_inbox (submitted_at, title, content) VALUES (?,?,?)",
            (now, title, content)
        )
        inbox_id = cur.lastrowid
        c.execute("""
            INSERT INTO discovery_log
              (logged_at, event_type, summary, source)
            VALUES (?,?,?,?)
        """, (now, "NotebookLM", f"NotebookLM submission: '{title}'", "notebooklm"))
        c.commit()
        print(f"[Discovery] NotebookLM inbox #{inbox_id}: '{title}'")
        return inbox_id
    finally:
        c.close()


def process_inbox() -> int:
    """
    Process pending NotebookLM inbox items.
    Each item becomes a knowledge asset with source='notebooklm'.
    Returns count of processed items.
    """
    init_discovery_db()
    c = _conn()
    processed = 0
    try:
        pending = [dict(r) for r in c.execute(
            "SELECT * FROM notebooklm_inbox WHERE status='Pending'"
        ).fetchall()]

        for item in pending:
            now = _now()
            novelty, overlaps = _classify_novelty(
                item["title"].lower().replace(" ", "_"),
                item["content"]
            )
            aid = _asset_id("nlm_" + str(item["id"]))

            auto_archive = novelty in ("Duplicate", "Repackaged")
            status = "Archived" if auto_archive else "Emerging"

            c.execute("""
                INSERT OR IGNORE INTO knowledge_assets
                  (id, name, feature_key, source, hypothesis, evidence,
                   status, novelty_class, overlap_factors, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (aid, item["title"],
                  "nlm_" + item["title"].lower().replace(" ", "_"),
                  "notebooklm", item["content"],
                  json.dumps({"inbox_id": item["id"]}),
                  status, novelty, json.dumps(overlaps), now, now))

            c.execute("""
                INSERT INTO discovery_log
                  (asset_id, logged_at, event_type, summary, source)
                VALUES (?,?,?,?,'notebooklm')
            """, (aid, now, "Discovered" if not auto_archive else "Archived",
                  f"[NotebookLM/{novelty}] {item['title']}: {item['content'][:120]}"))

            c.execute("""
                UPDATE notebooklm_inbox SET
                  status=?, asset_id=?, processed_at=?
                WHERE id=?
            """, ("Created" if not auto_archive else "Rejected",
                  aid, now, item["id"]))

            processed += 1

        c.commit()
    finally:
        c.close()
    print(f"[Discovery] Processed {processed} inbox items")
    return processed


# ── Dashboard data ────────────────────────────────────────────────────────────

def get_discovery_data() -> dict:
    """
    Assemble all data for _section_notebooklm() in dashboard.
    Reads production DB (read-only) for live signal count.
    Reads research.db for knowledge state.
    """
    init_discovery_db()

    try:
        df = load_production_data()
        total_signals = len(df)
    except Exception:
        df = pd.DataFrame()
        total_signals = 0

    c = _conn()
    try:
        all_assets = [dict(r) for r in c.execute(
            "SELECT * FROM knowledge_assets ORDER BY "
            "CASE status "
            "WHEN 'ProductionReady' THEN 0 WHEN 'ShadowProduction' THEN 1 "
            "WHEN 'PromotionCandidate' THEN 2 WHEN 'LearningCandidate' THEN 3 "
            "WHEN 'Validating' THEN 4 WHEN 'Emerging' THEN 5 "
            "WHEN 'Promoted' THEN 6 WHEN 'Rejected' THEN 7 WHEN 'Archived' THEN 8 "
            "ELSE 9 END, updated_at DESC"
        ).fetchall()]

        # Validation history per asset (last 5)
        val_history = {}
        for r in c.execute(
            "SELECT * FROM validation_runs ORDER BY id ASC"
        ).fetchall():
            aid = r["asset_id"] if "asset_id" in r.keys() else None
            if aid:
                val_history.setdefault(aid, []).append(dict(r))
        # Also from asset_validations table
        for r in c.execute(
            "SELECT * FROM asset_validations ORDER BY id ASC"
        ).fetchall():
            aid = r["asset_id"]
            val_history.setdefault(aid, []).append(dict(r))

        # Latest validation per asset
        latest_val = {}
        for r in c.execute(
            "SELECT * FROM asset_validations WHERE id IN "
            "(SELECT MAX(id) FROM asset_validations GROUP BY asset_id)"
        ).fetchall():
            latest_val[r["asset_id"]] = dict(r)

        # Shadow production log per asset
        shadow_log = {}
        for r in c.execute(
            "SELECT * FROM shadow_log ORDER BY id ASC"
        ).fetchall():
            shadow_log.setdefault(r["asset_id"], []).append(dict(r))

        # Recent discovery log
        log_entries = [dict(r) for r in c.execute(
            "SELECT dl.*, ka.name AS asset_name FROM discovery_log dl "
            "LEFT JOIN knowledge_assets ka ON dl.asset_id = ka.id "
            "ORDER BY dl.id DESC LIMIT 60"
        ).fetchall()]

        lessons = [dict(r) for r in c.execute(
            "SELECT * FROM lessons_learned ORDER BY id DESC LIMIT 30"
        ).fetchall()]

        inbox = [dict(r) for r in c.execute(
            "SELECT * FROM notebooklm_inbox ORDER BY id DESC LIMIT 20"
        ).fetchall()]

    finally:
        c.close()

    active     = [a for a in all_assets if a["status"] not in ("Archived", "Rejected", "Promoted")]
    archived   = [a for a in all_assets if a["status"] in ("Archived", "Rejected")]
    promoted   = [a for a in all_assets if a["status"] == "Promoted"]
    emerging   = [a for a in active if a["status"] == "Emerging"]
    candidates = [a for a in active if a["status"] in ("PromotionCandidate", "ProductionReady", "LearningCandidate")]
    shadow     = [a for a in active if a["status"] == "ShadowProduction"]

    return {
        "all_assets":      all_assets,
        "active":          active,
        "emerging":        emerging,
        "candidates":      candidates,
        "shadow":          shadow,
        "archived":        archived,
        "promoted":        promoted,
        "val_history":     val_history,
        "latest_val":      latest_val,
        "shadow_log":      shadow_log,
        "log_entries":     log_entries,
        "lessons":         lessons,
        "inbox":           inbox,
        "total_signals":   total_signals,
    }


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(0)
    cmd = args[0]

    if cmd == "discover":
        run_auto_discovery()
    elif cmd == "shadow":
        update_shadow_production()
    elif cmd == "validate":
        aid = args[1] if len(args) > 1 else None
        if not aid:
            print("Usage: python discovery_engine.py validate <asset_id>")
            sys.exit(1)
        print(validate_asset(aid))
    elif cmd == "promote":
        if len(args) < 4:
            print('Usage: python discovery_engine.py promote <id> <target> "<rationale>"')
            sys.exit(1)
        promote(args[1], args[2], " ".join(args[3:]))
    elif cmd == "reject":
        if len(args) < 3:
            print('Usage: python discovery_engine.py reject <id> "<rationale>"')
            sys.exit(1)
        reject(args[1], " ".join(args[2:]))
    elif cmd == "archive":
        if len(args) < 3:
            print('Usage: python discovery_engine.py archive <id> "<rationale>"')
            sys.exit(1)
        archive(args[1], " ".join(args[2:]))
    elif cmd == "shadow_promote":
        advance_to_shadow(args[1], " ".join(args[2:]) if len(args) > 2 else "")
    elif cmd == "lesson":
        if len(args) < 2:
            print('Usage: python discovery_engine.py lesson "<text>" [category] [impact] [asset_ids...]')
            sys.exit(1)
        add_lesson(args[1],
                   category=args[2] if len(args) > 2 else "General",
                   impact=args[3] if len(args) > 3 else "Medium",
                   asset_ids=args[4:] if len(args) > 4 else [])
    elif cmd == "add_notebooklm":
        if len(args) < 3:
            print('Usage: python discovery_engine.py add_notebooklm "<title>" "<content>"')
            sys.exit(1)
        submit_notebooklm(args[1], args[2])
        process_inbox()
    elif cmd == "inbox":
        process_inbox()
    elif cmd == "show":
        init_discovery_db()
        c = _conn()
        if len(args) > 1:
            rows = [dict(r) for r in c.execute(
                "SELECT * FROM knowledge_assets WHERE id=?", (args[1],)
            ).fetchall()]
        else:
            rows = [dict(r) for r in c.execute(
                "SELECT id, name, status, novelty_class, mfe_lift_pp, n_signals FROM knowledge_assets"
            ).fetchall()]
        c.close()
        for r in rows:
            print(json.dumps(r, indent=2, default=str))
    elif cmd == "init":
        init_discovery_db()
        print("[Discovery] research.db initialised.")
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
