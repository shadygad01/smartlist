"""
challenger_eligibility_engine.py — Layer 1 of the Challenger Architecture.

DISCOUNT-FIRST RULE (NON-NEGOTIABLE):
  A stock CANNOT be a buy candidate unless it is inside a valid discount zone.
  This engine enforces that rule as a BINARY gate — no score, no weight, no bypass.

Output:
  ELIGIBLE   → pass to Layer 2 (Expectancy Engine)
  REJECTED   → no buy, no score, no ranking

Eligibility criteria (all must pass):
  1. Price strictly below EQ (< 0.50 Fibonacci level) — discount zone required
  2. r1_price >= price_gate threshold — must be in meaningful discount depth
  3. raw_score (r1–r8) >= 35 — minimum structural validity
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


# Default gate fractions — mirror signal_engine defaults
_PRICE_GATE_FRAC_NORMAL    = 0.55   # 55% of W_PRICE
_PRICE_GATE_FRAC_WHITELIST = 0.50   # 50% of W_PRICE for whitelisted symbols
_RAW_SCORE_MIN             = 35     # structural validity floor


@dataclass(frozen=True)
class EligibilityResult:
    eligible: bool
    reason: str                  # human-readable decision explanation
    discount_depth: float        # 0.0 (at EQ) → 1.0 (at swing low)
    r1_score: int                # raw price gate score
    price_gate: float            # threshold r1 must meet


def check_eligibility(
    *,
    cur: float,
    eq: float,
    lo: float,
    hi: float,
    r1_price: int,
    raw_score: int,
    w_price: int = 30,
    is_whitelist: bool = False,
) -> EligibilityResult:
    """
    Binary discount eligibility check.

    Parameters
    ----------
    cur         : current price
    eq          : equilibrium level (50% of swing range = swing discount boundary)
    lo          : swing low (80-bar)
    hi          : swing high (80-bar)
    r1_price    : score from sc_price() — represents discount depth (0–W_PRICE)
    raw_score   : total SMC raw score (r1+…+r8, capped at 100)
    w_price     : weight for price gate (default 30, mirrors signal_engine)
    is_whitelist: apply looser price gate fraction for whitelisted symbols
    """
    # ── Gate 1: Price must be strictly below EQ (discount zone) ──────────────
    if cur >= eq:
        pct_above = round((cur - eq) / max(hi - lo, 1) * 100, 1)
        return EligibilityResult(
            eligible=False,
            reason=f"REJECTED — price @ {cur:.2f} is {pct_above}% above EQ ({eq:.2f}): premium zone",
            discount_depth=0.0,
            r1_score=r1_price,
            price_gate=0.0,
        )

    # ── Gate 2: Price must be in meaningful discount depth (price gate) ───────
    frac = _PRICE_GATE_FRAC_WHITELIST if is_whitelist else _PRICE_GATE_FRAC_NORMAL
    gate = frac * w_price
    if r1_price < gate:
        depth = round((eq - cur) / max(eq - lo, 1), 3)
        return EligibilityResult(
            eligible=False,
            reason=(f"REJECTED — r1={r1_price} < price_gate={gate:.1f} "
                    f"({frac*100:.0f}% of W_PRICE={w_price}): not in deep discount"),
            discount_depth=depth,
            r1_score=r1_price,
            price_gate=gate,
        )

    # ── Gate 3: Minimum structural validity ──────────────────────────────────
    if raw_score < _RAW_SCORE_MIN:
        depth = round((eq - cur) / max(eq - lo, 1), 3)
        return EligibilityResult(
            eligible=False,
            reason=f"REJECTED — raw_score={raw_score} < minimum {_RAW_SCORE_MIN}: insufficient structure",
            discount_depth=depth,
            r1_score=r1_price,
            price_gate=gate,
        )

    # ── ELIGIBLE ──────────────────────────────────────────────────────────────
    depth = round((eq - cur) / max(eq - lo, 1), 3)
    return EligibilityResult(
        eligible=True,
        reason=(f"ELIGIBLE — price @ {cur:.2f} is {depth*100:.1f}% into discount zone "
                f"(r1={r1_price}/{w_price}, raw={raw_score})"),
        discount_depth=depth,
        r1_score=r1_price,
        price_gate=gate,
    )


def check_from_signal_dict(signal: dict, whitelist: set = None) -> EligibilityResult:
    """
    Convenience wrapper — accepts a signal dict as returned by analyze() or score_signal().
    """
    if whitelist is None:
        whitelist = set()
    sym = signal.get("symbol", "")
    return check_eligibility(
        cur=signal.get("price", signal.get("cur", 0.0)),
        eq=signal.get("eq", 0.0),
        lo=signal.get("lo", 0.0),
        hi=signal.get("hi", 0.0),
        r1_price=signal.get("r1", signal.get("r1_price", 0)),
        raw_score=signal.get("raw_score", 0),
        is_whitelist=(sym in whitelist),
    )
