"""
Constitutional Gate — Single Source of Truth for constitutional BUY eligibility.

ONE function. ONE decision. Zero tolerance for duplicate gate logic.

Architecture contract:
  - is_constitutional_buy() is the ONLY place where BUY eligibility is evaluated.
  - All presentation layers (Dashboard, Morning Email, Alert Email, Telegram,
    Timeline, Universe Snapshot) MUST import and call this function.
  - No layer may define its own thresholds, tolerances, or price buffers.
  - No layer may re-evaluate eligibility from raw R2/score/price values.

Violations of this contract cause Dashboard ≠ Email ≠ Telegram inconsistency.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone

# ── Constitutional thresholds ─────────────────────────────────────────────────
# DO NOT COPY THESE VALUES INTO OTHER FILES.
# Import from here: from constitutional_gate import CONST_R2_MIN, CONST_SCORE_MIN

CONST_R2_MIN    = 60.0   # minimum discount-quality R2 score
CONST_SCORE_MIN = 35.0   # minimum expected reward score

# ── Price gate ────────────────────────────────────────────────────────────────
# Strict: no tolerance buffer.
# Alert path and display path must use the SAME gate.
# History: a 2% buffer (entry * 1.02) was previously used in detect_signal_changes()
# but NOT in dashboard._s_buy_signals(). This caused email to show signals the
# dashboard did not show — a Constitutional Single Source of Truth violation.
# Fixed: strict gate everywhere.
PRICE_TOLERANCE = 0.0


# ── Decision object ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ConstitutionalDecision:
    """
    Immutable result of one constitutional eligibility evaluation for one ticker.

    Produced by evaluate(). Consumed by presentation layers.
    No consumer may re-evaluate eligibility; they must render this object as-is.
    """
    ticker:                    str
    event_type:                str    # FIRST_BUY | RE_ACCUMULATION | NONE
    eligible:                  bool
    constitutional_entry_price: float
    current_price:             float
    constitutional_r2:         float
    constitutional_score:      float
    reason:                    str    # human-readable gate outcome
    sector:                    str
    event_date:                str
    return_pct:                float
    status:                    str
    generated_at:              str

    def as_dict(self) -> dict:
        """Return plain dict for downstream consumers that expect dict (e.g. register_alert_events)."""
        return asdict(self)


# ── Single gate function ──────────────────────────────────────────────────────

def is_constitutional_buy(
    r2: float,
    score: float,
    current_price: float,
    entry_price: float,
) -> bool:
    """
    Single constitutional BUY gate.

    Returns True when ALL conditions are simultaneously met:
      1. R2 >= CONST_R2_MIN (60) — discount quality threshold
      2. score >= CONST_SCORE_MIN (35) — expected reward threshold
      3. current_price <= entry_price — price at or below entry zone
         (entry_price <= 0 means the price gate passes — entry not yet established)

    This is the ONLY authoritative eligibility function.
    Do not inline these conditions elsewhere.
    """
    if r2 < CONST_R2_MIN or score < CONST_SCORE_MIN:
        return False
    if entry_price <= 0:
        return True
    return current_price <= entry_price


def evaluate(
    ticker: str,
    r2: float,
    score: float,
    current_price: float,
    entry_price: float,
    *,
    event_type: str = "FIRST_BUY",
    sector: str = "",
    event_date: str = "",
    return_pct: float = 0.0,
    status: str = "",
    generated_at: str = "",
) -> ConstitutionalDecision:
    """
    Evaluate constitutional BUY eligibility and return an immutable ConstitutionalDecision.

    Called by detect_signal_changes() (alert pipeline) and dashboard._s_buy_signals()
    (display pipeline). All callers receive the same decision object — no divergence possible.
    """
    if not generated_at:
        generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    eligible = is_constitutional_buy(r2, score, current_price, entry_price)

    if not eligible:
        if r2 < CONST_R2_MIN:
            reason = f"R2={r2:.1f} < {CONST_R2_MIN} (threshold not met)"
        elif score < CONST_SCORE_MIN:
            reason = f"Score={score:.1f} < {CONST_SCORE_MIN} (threshold not met)"
        else:
            pct_above = round((current_price - entry_price) / entry_price * 100, 2) if entry_price > 0 else 0.0
            reason = f"Price={current_price:.4f} > Entry={entry_price:.4f} (+{pct_above:.2f}% above)"
    else:
        dist = round((current_price - entry_price) / entry_price * 100, 2) if entry_price > 0 else 0.0
        reason = (
            f"R2={r2:.1f} Score={score:.1f} "
            f"Price={current_price:.4f} Entry={entry_price:.4f} ({dist:+.2f}%)"
        )

    return ConstitutionalDecision(
        ticker=ticker,
        event_type=event_type,
        eligible=eligible,
        constitutional_entry_price=entry_price if entry_price > 0 else current_price,
        current_price=current_price,
        constitutional_r2=r2,
        constitutional_score=score,
        reason=reason,
        sector=sector,
        event_date=event_date,
        return_pct=return_pct,
        status=status,
        generated_at=generated_at,
    )
