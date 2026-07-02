"""
challenger_expectancy_engine.py — Layer 2 of the Challenger Architecture.

PURPOSE:
  Estimate FUTURE OPPORTUNITY QUALITY for an eligible signal.
  Inputs:  r2_ob, r3_liquidity, r4_htf, r5_avwap, r6_macd, r7_div, r8_demand
  Output:  Expected outcome score (0–100)

NOTE ON r1_price:
  r1 is NOT a feature here. It is a binary eligibility check (Layer 1).
  Including r1 in scoring confounds discount-depth with reversal quality.
  Evidence: raw_score (r1+…+r8) has −0.115 correlation with mfe_40d,
  whereas r2–r8 subscore shows better monotonic alignment with quality outcomes.

TRAINING METHOD:
  Ridge regression trained on historical outcomes (r20d, mfe_40d) from egx_research.db.
  Features are normalised to their respective W_* maximums so coefficients are comparable.
  Walk-forward safe: only data BEFORE the signal date is used for training at inference time.

FALLBACK:
  When fewer than 30 historical signals are available, falls back to a
  evidence-prior: weights proportional to mfe_40d correlations measured at build time.
"""

from __future__ import annotations
import sqlite3
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


# ── Evidence-Prior Weights ────────────────────────────────────────────────────
# Derived from peak_return_1y Pearson correlations (N=560 signals, current optimized weights):
#   r5_avwap +0.258  r6_macd  +0.205  r4_htf   +0.163
#   r3_liq   +0.139  r7_div   +0.118  r8_demand+0.100  r2_ob  −0.051
# Normalised to sum=1.0; negative → floored at 0.
_PRIOR_WEIGHTS = {
    "r2_ob":        0.000,  # negative correlation → floor at 0
    "r3_liquidity": 0.141,
    "r4_htf":       0.166,
    "r5_avwap":     0.262,
    "r6_macd":      0.208,
    "r7_div":       0.120,
    "r8_demand":    0.103,
}

# Max possible values for each factor (from signal_engine defaults)
_W_MAX = {
    "r2_ob":        10,
    "r3_liquidity": 20,
    "r4_htf":       10,
    "r5_avwap":      8,
    "r6_macd":       4,
    "r7_div":        3,
    "r8_demand":    15,
}

# Demand zone gets a bonus when BOTH SV and HVN are confirmed (best case)
_DEMAND_BONUS_WEIGHT = 0.12   # additive bonus, normalised within 0–100 output


@dataclass
class ExpectancyResult:
    score: int                      # 0–100
    expected_outcome: float         # model's predicted r20d (or mfe_40d-based proxy)
    confidence: float               # 0–1, based on training sample size
    feature_contributions: dict     # factor → contribution points
    model_source: str               # "learned" | "prior" | "hybrid"
    n_train: int                    # training sample count


# ── Internal: Ridge Regression (pure stdlib — no numpy/sklearn required) ──────

def _ridge_fit(X: list[list[float]], y: list[float], alpha: float = 1.0) -> list[float]:
    """
    Fit Ridge regression analytically: w = (X'X + αI)^{-1} X'y.
    Returns coefficient vector (excluding intercept — we centre data).
    Falls back to prior weights on numerical failure.
    """
    n = len(y)
    k = len(X[0]) if X else 0
    if n < k + 5:
        return []

    # Centre y
    y_mean = sum(y) / n
    yc = [v - y_mean for v in y]

    # Centre X column-wise
    x_means = [sum(X[i][j] for i in range(n)) / n for j in range(k)]
    Xc = [[X[i][j] - x_means[j] for j in range(k)] for i in range(n)]

    # XtX
    XtX = [[sum(Xc[i][a] * Xc[i][b] for i in range(n)) for b in range(k)] for a in range(k)]
    # Add ridge penalty to diagonal
    for d in range(k):
        XtX[d][d] += alpha

    # Xty
    Xty = [sum(Xc[i][j] * yc[i] for i in range(n)) for j in range(k)]

    # Solve XtX @ w = Xty via Gaussian elimination
    try:
        m = [row[:] + [Xty[r]] for r, row in enumerate(XtX)]
        for col in range(k):
            pivot = max(range(col, k), key=lambda r: abs(m[r][col]))
            m[col], m[pivot] = m[pivot], m[col]
            if abs(m[col][col]) < 1e-12:
                return []
            div = m[col][col]
            m[col] = [v / div for v in m[col]]
            for row in range(k):
                if row != col:
                    factor = m[row][col]
                    m[row] = [m[row][c] - factor * m[col][c] for c in range(k + 1)]
        return [m[j][k] for j in range(k)]
    except Exception:
        return []


def _build_features(signal_factors: dict) -> list[float]:
    """
    Convert factor dict → normalised feature vector [0,1] for each of r2–r8.
    Order matches _FEATURE_NAMES.
    """
    features = []
    for name in _FEATURE_NAMES:
        raw = signal_factors.get(name, 0) or 0
        wmax = _W_MAX.get(name, 1)
        features.append(min(1.0, max(0.0, raw / wmax)))
    return features

_FEATURE_NAMES = ["r2_ob", "r3_liquidity", "r4_htf", "r5_avwap", "r6_macd", "r7_div", "r8_demand"]


class ExpectancyEngine:
    """
    Stateless expectancy engine with optional learned weights.
    Call compute() for each eligible signal.
    """

    def __init__(
        self,
        db_path: str = "egx_research.db",
        target: str = "mfe_40d",    # primary outcome target
        alpha: float = 2.0,         # Ridge regularisation strength
        min_train: int = 30,        # minimum samples to use learned model
    ):
        self.db_path  = db_path
        self.target   = target
        self.alpha    = alpha
        self.min_train = min_train
        self._cache: dict[str, tuple[list[float], float, int]] = {}  # date → (coefs, y_mean, n)

    def _load_training_data(
        self, before_date: str
    ) -> tuple[list[list[float]], list[float]]:
        """
        Load all buy signals BEFORE before_date with non-null outcome.
        Returns (X, y) where X is normalised r2–r8 features, y is the target.
        """
        col = self.target
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"""
                SELECT s.r2_ob, s.r3_liquidity, s.r4_htf, s.r5_avwap,
                       s.r6_macd, s.r7_div, s.r8_demand,
                       bq.{col} AS outcome
                FROM signals s
                JOIN bottom_quality bq ON s.id = bq.signal_id
                WHERE s.signal_date < ?
                  AND bq.{col} IS NOT NULL
                  AND s.signal_type NOT IN ('Skip', 'Wait')
                ORDER BY s.signal_date
                """,
                (before_date,),
            ).fetchall()
            conn.close()
        except Exception:
            return [], []

        X, y = [], []
        for r in rows:
            feat = [min(1.0, max(0.0, (r[name] or 0) / _W_MAX[name]))
                    for name in _FEATURE_NAMES]
            X.append(feat)
            y.append(float(r["outcome"]))
        return X, y

    def _get_coefs(self, before_date: str) -> tuple[list[float], float, int]:
        """Return (coefs, y_mean, n_train) for signals before given date."""
        # Cache by date (day granularity is sufficient)
        cache_key = before_date[:10]
        if cache_key not in self._cache:
            X, y = self._load_training_data(before_date)
            n = len(y)
            if n < self.min_train:
                self._cache[cache_key] = ([], 0.0, n)
            else:
                y_mean = sum(y) / n
                coefs  = _ridge_fit(X, y, alpha=self.alpha)
                self._cache[cache_key] = (coefs, y_mean, n)
        return self._cache[cache_key]

    def compute(
        self,
        signal_factors: dict,
        signal_date: Optional[str] = None,
        sv_hit: bool = False,
        hvn_hit: bool = False,
    ) -> ExpectancyResult:
        """
        Compute expectancy score for an eligible signal.

        Parameters
        ----------
        signal_factors : dict with keys r2_ob, r3_liquidity, …, r8_demand
        signal_date    : YYYY-MM-DD — only data BEFORE this date used for training
        sv_hit         : Stopping Volume detected (demand bonus trigger)
        hvn_hit        : High Volume Node in Buy Zone (demand bonus trigger)
        """
        if signal_date is None:
            signal_date = datetime.now().strftime("%Y-%m-%d")

        feats = _build_features(signal_factors)
        coefs, y_mean, n_train = self._get_coefs(signal_date)

        # ── Demand Zone Bonus ─────────────────────────────────────────────────
        # Both SV + HVN = best institutional demand context; partial scores keep base
        demand_bonus = 0.0
        if sv_hit and hvn_hit:
            demand_bonus = _DEMAND_BONUS_WEIGHT

        if len(coefs) == len(feats):
            # Learned model available ─────────────────────────────────────────
            # Predict raw outcome (centred model: y = y_mean + X_centred @ coefs)
            # features are already normalised [0,1], training was centred around x_mean
            # We apply the sign of coefs to weight the features
            raw_pred = y_mean + sum(c * f for c, f in zip(coefs, feats))

            # Map predicted outcome to 0–100 score
            # Expected range of mfe_40d: [-0.20, +0.60]; map to [0, 100]
            lo_bound = -0.20
            hi_bound =  0.60
            norm = (raw_pred - lo_bound) / (hi_bound - lo_bound)
            base_score = min(100.0, max(0.0, norm * 100))
            score_float = min(100.0, base_score + demand_bonus * 100)

            # Contribution breakdown (proportional to |coef| × feature × sign)
            contribs = {}
            total_mag = sum(abs(c) for c in coefs) or 1.0
            for name, c, f in zip(_FEATURE_NAMES, coefs, feats):
                share = (abs(c) / total_mag) * score_float
                contribs[name] = round(share, 2)

            confidence = min(1.0, math.sqrt(n_train / 200))
            model_source = "learned"

        else:
            # Prior weights fallback ──────────────────────────────────────────
            weighted = sum(_PRIOR_WEIGHTS[n] * f for n, f in zip(_FEATURE_NAMES, feats))
            score_float = min(100.0, weighted * 100 + demand_bonus * 100)
            contribs = {n: round(_PRIOR_WEIGHTS[n] * f * 100, 2)
                        for n, f in zip(_FEATURE_NAMES, feats)}
            raw_pred = 0.05 * weighted   # rough proxy
            confidence = min(0.5, n_train / self.min_train * 0.5)
            model_source = "prior" if n_train == 0 else "hybrid"

        return ExpectancyResult(
            score=int(round(score_float)),
            expected_outcome=round(raw_pred, 4),
            confidence=round(confidence, 3),
            feature_contributions=contribs,
            model_source=model_source,
            n_train=n_train,
        )


# Module-level singleton (constructed lazily)
_engine: Optional[ExpectancyEngine] = None


def get_engine(db_path: str = "egx_research.db", **kwargs) -> ExpectancyEngine:
    global _engine
    if _engine is None or _engine.db_path != db_path:
        _engine = ExpectancyEngine(db_path=db_path, **kwargs)
    return _engine


def score(signal_factors: dict, signal_date: str = None,
          sv_hit: bool = False, hvn_hit: bool = False,
          db_path: str = "egx_research.db") -> ExpectancyResult:
    """Convenience function — uses module-level engine singleton."""
    return get_engine(db_path).compute(signal_factors, signal_date, sv_hit, hvn_hit)
