"""
Feature Registry — Layer 2 of the architecture.
Centralizes feature metadata without changing extraction logic.
"""

from __future__ import annotations
from typing import Optional
import pandas as pd

# ── Feature Catalog ────────────────────────────────────────────────────────────
# Maps every feature name to metadata.
# Groups: structure, momentum, volume, volatility, context, market

FEATURE_CATALOG: dict[str, dict] = {

    # ── feat_* — Structure ──────────────────────────────────────────────────
    "feat_dist_swing_low": {
        "group": "structure",
        "description": "Distance from entry price to recent swing low (%)",
        "source": "feature_extractor",
        "dtype": "float",
        "range": [0.0, 1.0],
        "missing_strategy": "drop",
    },
    "feat_dealing_range_pos": {
        "group": "structure",
        "description": "Position within 20-bar dealing range (0=low, 1=high)",
        "source": "feature_extractor",
        "dtype": "float",
        "range": [0.0, 1.0],
        "missing_strategy": "drop",
    },
    "feat_candles_since_bos": {
        "group": "structure",
        "description": "Candles elapsed since last bullish Break of Structure",
        "source": "feature_extractor",
        "dtype": "int",
        "range": [0, 60],
        "missing_strategy": "drop",
    },
    "feat_dist_last_bos": {
        "group": "structure",
        "description": "Distance from entry price to last BOS level (%)",
        "source": "feature_extractor",
        "dtype": "float",
        "range": [-0.5, 0.5],
        "missing_strategy": "drop",
    },

    # ── feat_* — Volume / Liquidity ─────────────────────────────────────────
    "feat_sweep_depth_pct": {
        "group": "volume",
        "description": "Depth of liquidity sweep below prior 10-day low (%)",
        "source": "feature_extractor",
        "dtype": "float",
        "range": [-0.1, 0.2],
        "missing_strategy": "fill_zero",
    },
    "feat_equal_lows_count": {
        "group": "structure",
        "description": "Count of lows within +-0.8% of entry price (last 30 bars)",
        "source": "feature_extractor",
        "dtype": "int",
        "range": [0, 30],
        "missing_strategy": "fill_zero",
    },
    "feat_vol_spike_ratio": {
        "group": "volume",
        "description": "Max volume in last 5 bars divided by 20-bar average volume",
        "source": "feature_extractor",
        "dtype": "float",
        "range": [0.0, 20.0],
        "missing_strategy": "drop",
    },
    "feat_candles_since_sweep": {
        "group": "structure",
        "description": "Candles since last liquidity sweep event",
        "source": "feature_extractor",
        "dtype": "int",
        "range": [0, 30],
        "missing_strategy": "drop",
    },
    "feat_accumulation_score": {
        "group": "volume",
        "description": "Composite accumulation score (0-10): volume decline + inside bars + range compression",
        "source": "feature_extractor",
        "dtype": "float",
        "range": [0.0, 10.0],
        "missing_strategy": "fill_zero",
    },

    # ── feat_* — Momentum / Exhaustion ─────────────────────────────────────
    "feat_consec_red": {
        "group": "momentum",
        "description": "Consecutive red candles immediately before entry",
        "source": "feature_extractor",
        "dtype": "int",
        "range": [0, 15],
        "missing_strategy": "fill_zero",
    },
    "feat_down_days_pct": {
        "group": "momentum",
        "description": "Fraction of down days in last 20 trading sessions",
        "source": "feature_extractor",
        "dtype": "float",
        "range": [0.0, 1.0],
        "missing_strategy": "drop",
    },
    "feat_atr_compression": {
        "group": "volatility",
        "description": "Current 14-day ATR divided by ATR 40 bars prior (compression ratio)",
        "source": "feature_extractor",
        "dtype": "float",
        "range": [0.0, 5.0],
        "missing_strategy": "drop",
    },
    "feat_vol_contraction": {
        "group": "volume",
        "description": "Normalised slope of last 10-bar volume (negative = contraction)",
        "source": "feature_extractor",
        "dtype": "float",
        "range": [-1.0, 1.0],
        "missing_strategy": "drop",
    },
    "feat_dist_20d_low": {
        "group": "structure",
        "description": "Distance from entry price to 20-day low (%)",
        "source": "feature_extractor",
        "dtype": "float",
        "range": [0.0, 1.0],
        "missing_strategy": "drop",
    },
    "feat_dist_50d_low": {
        "group": "structure",
        "description": "Distance from entry price to 50-day low (%)",
        "source": "feature_extractor",
        "dtype": "float",
        "range": [0.0, 1.0],
        "missing_strategy": "drop",
    },
    "feat_dist_52w_low": {
        "group": "structure",
        "description": "Distance from entry price to 52-week low (%)",
        "source": "feature_extractor",
        "dtype": "float",
        "range": [0.0, 1.0],
        "missing_strategy": "drop",
    },

    # ── feat_* — Institutional ──────────────────────────────────────────────
    "feat_vwap_dist": {
        "group": "context",
        "description": "Distance of entry price from 20-day VWAP (%)",
        "source": "feature_extractor",
        "dtype": "float",
        "range": [-0.5, 0.5],
        "missing_strategy": "drop",
    },

    # ── feat_* — Market Context ─────────────────────────────────────────────
    "feat_rs_vs_egx30": {
        "group": "market",
        "description": "21-day return of stock relative to EGX30 return (ratio)",
        "source": "feature_extractor",
        "dtype": "float",
        "range": [-10.0, 10.0],
        "missing_strategy": "drop",
    },
    "feat_egx30_trend_val": {
        "group": "market",
        "description": "EGX30 distance above/below its 20-day MA (%)",
        "source": "feature_extractor",
        "dtype": "float",
        "range": [-0.2, 0.2],
        "missing_strategy": "drop",
    },

    # ── snap_* — Volatility / ATR ───────────────────────────────────────────
    "snap_atr": {
        "group": "volatility",
        "description": "14-period Average True Range (raw price value)",
        "source": "snapshot_engine",
        "dtype": "float",
        "range": [0.0, None],
        "missing_strategy": "drop",
    },
    "snap_wick_ratio": {
        "group": "structure",
        "description": "Lower wick fraction of total candle range on signal bar",
        "source": "snapshot_engine",
        "dtype": "float",
        "range": [0.0, 1.0],
        "missing_strategy": "fill_zero",
    },
    "snap_compression": {
        "group": "volatility",
        "description": "Recent 10-bar range divided by (ATR x lookback) — <1 means compressed",
        "source": "snapshot_engine",
        "dtype": "float",
        "range": [0.0, 5.0],
        "missing_strategy": "drop",
    },
    "snap_consol_len": {
        "group": "structure",
        "description": "Number of consecutive consolidation bars before signal",
        "source": "snapshot_engine",
        "dtype": "int",
        "range": [0, 40],
        "missing_strategy": "fill_zero",
    },

    # ── snap_* — Structure / BOS ────────────────────────────────────────────
    "snap_bos": {
        "group": "structure",
        "description": "Bullish Break of Structure detected (0/1)",
        "source": "snapshot_engine",
        "dtype": "int",
        "range": [0, 1],
        "missing_strategy": "fill_zero",
    },
    "snap_bos_dist": {
        "group": "structure",
        "description": "Distance from current close to BOS level (%)",
        "source": "snapshot_engine",
        "dtype": "float",
        "range": [0.0, 50.0],
        "missing_strategy": "fill_zero",
    },
    "snap_choch": {
        "group": "structure",
        "description": "Change of Character (higher low pattern) detected (0/1)",
        "source": "snapshot_engine",
        "dtype": "int",
        "range": [0, 1],
        "missing_strategy": "fill_zero",
    },
    "snap_pivot_str": {
        "group": "structure",
        "description": "Pivot support strength score (touches/5 capped at 1.0 via snapshot_engine; raw 0-20 via feature_extractor)",
        "source": "snapshot_engine",
        "dtype": "float",
        "range": [0.0, 20.0],
        "missing_strategy": "fill_zero",
    },
    "snap_num_touches": {
        "group": "structure",
        "description": "Number of touches at swing low level",
        "source": "snapshot_engine",
        "dtype": "int",
        "range": [0, 30],
        "missing_strategy": "fill_zero",
    },

    # ── snap_* — Volume ─────────────────────────────────────────────────────
    "snap_sweep_size": {
        "group": "volume",
        "description": "Liquidity sweep size — depth below prior swing low (%)",
        "source": "snapshot_engine",
        "dtype": "float",
        "range": [0.0, 0.2],
        "missing_strategy": "fill_zero",
    },
    "snap_vol_exp": {
        "group": "volume",
        "description": "Volume expansion ratio: last bar volume / 20-bar average",
        "source": "snapshot_engine",
        "dtype": "float",
        "range": [0.0, 20.0],
        "missing_strategy": "drop",
    },

    # ── snap_* — Momentum / Context ─────────────────────────────────────────
    "snap_reclaim_spd": {
        "group": "momentum",
        "description": "Speed of EQ reclaim: 1 / bars_since_below_eq",
        "source": "snapshot_engine",
        "dtype": "float",
        "range": [0.0, 1.0],
        "missing_strategy": "drop",
    },
    "snap_dist_lo": {
        "group": "structure",
        "description": "Distance from current price to swing low (%)",
        "source": "snapshot_engine",
        "dtype": "float",
        "range": [0.0, 1.0],
        "missing_strategy": "drop",
    },
    "snap_prem_disc": {
        "group": "context",
        "description": "Position within discount zone (0=swing low, 1=equilibrium)",
        "source": "snapshot_engine",
        "dtype": "float",
        "range": [0.0, 1.0],
        "missing_strategy": "drop",
    },
}


# ── FeatureRegistry ────────────────────────────────────────────────────────────

class FeatureRegistry:
    """
    Centralises feature metadata and provides a single compute() entry point
    for all feat_* and snap_* features.  Does not alter extraction logic.
    """

    def __init__(self):
        self.catalog: dict[str, dict] = FEATURE_CATALOG

    # ── Metadata helpers ───────────────────────────────────────────────────

    def list_features(self) -> list[str]:
        """Return all registered feature names."""
        return list(self.catalog.keys())

    def feature_metadata(self, name: str) -> dict:
        """Return metadata dict for a feature. Raises KeyError if not found."""
        return self.catalog[name]

    def get_ml_feature_set(self) -> list[str]:
        """
        Canonical list of features for ML models.
        Includes all feat_* and snap_* features (excludes raw r1-r8 scores).
        """
        return [k for k in self.catalog if k.startswith("feat_") or k.startswith("snap_")]

    def get_feature_groups(self) -> dict[str, list[str]]:
        """Return features grouped by their 'group' key."""
        groups: dict[str, list[str]] = {}
        for name, meta in self.catalog.items():
            g = meta.get("group", "other")
            groups.setdefault(g, []).append(name)
        return groups

    # ── Compute ────────────────────────────────────────────────────────────

    def compute(
        self,
        sig: dict,
        df: "pd.DataFrame",
        egx30_df: "Optional[pd.DataFrame]" = None,
    ) -> dict:
        """
        Compute all features for a signal using existing extraction modules.

        For feat_* features uses feature_extractor.compute_entry_features().
        For snap_* features when sig already contains eq/lo/hi keys (live signal
        path) uses snapshot_engine.compute_snapshot_features(); otherwise relies
        on the snap_* values already embedded in the feat_* output produced by
        compute_entry_features() (backfill path).

        Returns merged feat_* + snap_* dict.
        """
        from feature_extractor import compute_entry_features
        from snapshot_engine import compute_snapshot_features

        # Primary extraction (feat_* and snap_* recompute for backfill)
        result = compute_entry_features(sig, df, egx30_df=egx30_df)

        # If live-signal keys are present, overlay with snapshot_engine values
        eq = sig.get("eq") or sig.get("equilibrium")
        lo = sig.get("lo") or sig.get("swing_low")
        hi = sig.get("hi") or sig.get("swing_high")
        cur = float(sig.get("price", 0) or 0)

        if cur and eq and lo and hi and df is not None and not df.empty:
            snap = compute_snapshot_features(df, cur=cur, eq=float(eq),
                                             lo=float(lo), hi=float(hi))
            result.update(snap)

        return result
