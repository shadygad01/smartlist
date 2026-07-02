# AVWAP FORENSIC AUDIT

**Date**: 2026-06-17  
**Dataset**: 2025+ signals with r20d outcomes (n=321)

## Summary Finding

**AVWAP scoring has significant NEGATIVE lift (-4.8pp WR).**

When `r5_avwap > 0` (price is below AVWAP), win rate drops 4.8 percentage points vs when `r5_avwap = 0` (price is above AVWAP or equal to it).

## Formula Analysis

**`sc_avwap(cur, av, av_lo)` in signal_engine.py (line 684-687):**

```python
def sc_avwap(cur, av, av_lo):
    if cur <= av_lo: return W_AVWAP, f"At/below AVWAP lower band {av_lo:.1f}"
    if cur < av: return max(round(((av - cur) / (av - av_lo)) * (W_AVWAP - 1)), 1), f"Below AVWAP {av:.1f}"
    return 0, f"Above AVWAP {av:.1f}"
```

**Interpretation:**
- `r5=0`: Price is above AVWAP (positive momentum relative to AVWAP anchor)
- `r5=W_AVWAP`: Price is at/below AVWAP lower band (maximum "discount" vs AVWAP)
- Mid-band: Proportional between AVWAP and lower band

## Data Results

| r5 Score | n | WR | Expectancy |
|---|---|---|---|
| 0 (above AVWAP) | 219 | **41.1%** | +4.8% |
| 1-2 (slightly below) | 14 | 35.7% | +6.1% |
| 3-5 (mid-band) | 6 | 50.0% | +5.0% |
| 6-7 (near lower band) | 10 | **10.0%** | +1.5% |
| 8 (at/below lower band) | 72 | 38.9% | +5.1% |

**Aggregate:**
- r5=0 (above AVWAP): n=219, WR=41.1%
- r5>0 (below AVWAP): n=102, WR=36.3%
- **Negative lift: -4.8pp WR**

## Root Cause Analysis

### AVWAP Anchor Selection Issue

`calc_avwap()` anchors to the **most recent swing low in 60 bars**. In a discount zone setup:

1. EGX scanner only evaluates stocks already in the discount zone (below EQ = below 50th percentile)
2. The most recent swing low is often the **current or very recent price level**
3. This means AVWAP is anchored near current price → AVWAP ≈ current price
4. Result: most signals have `cur ≈ av` → mid-range r5 scores that are meaningless noise

### Why r5=6-7 is the Worst (WR=10%)

The r5=6-7 band scores signals where `cur` is "slightly above the lower band" — these are
stocks in a narrow range between AVWAP and lower band, suggesting:
- Tight consolidation with uncertain direction
- Price has been oscillating without a clear reversal
- Not confirmed as either "deeply discounted relative to AVWAP" or "recovering above AVWAP"

### Why r5=8 (Max) Recovers (WR=38.9%)

When price is at/below the AVWAP lower band, there's a minimum signal:
- Price has pushed significantly below the volume-weighted anchor
- This often coincides with extreme discount conditions (SV, demand zone)
- So the WR partially recovers but still below r5=0

### Why r5=0 Has Best WR (41.1%)

Stocks where price is ABOVE AVWAP in the discount zone signal:
- Price has bounced above the AVWAP anchor (recovering momentum)
- The stock is in discount zone structurally (below EQ) but above AVWAP (local recovery)
- This "double discount" with AVWAP support is a stronger setup

## Diagnosis

The AVWAP gate is **inverted relative to its intent**. The formula rewards being below AVWAP
(more "discount"), but empirically, being above AVWAP in the discount zone is a better signal.

**The AVWAP scoring is adding noise and dragging down WR.**

## Recommendation

**Option 1 (Quick Fix): Set W_AVWAP=0 in config/weights.json**
- Zero out AVWAP weight — eliminates -4.8pp drag
- Expected WR lift: +1 to +2pp (less weight on a negative gate)
- Risk: LOW (confirmed negative alpha)

**Option 2 (Correct Fix): Invert the formula**
```python
def sc_avwap(cur, av, av_lo):
    if cur >= av: return W_AVWAP, f"Above AVWAP {av:.1f} — positive momentum"
    if cur > av_lo: return round(((cur - av_lo) / (av - av_lo)) * (W_AVWAP - 1)), f"Between bands"
    return 0, f"At/below lower band {av_lo:.1f}"
```
- Rewards being ABOVE AVWAP (empirically better)
- Expected WR lift: +3 to +5pp
- Risk: MEDIUM (requires revalidation)

**Option 3 (Alternative): Use EGX30 AVWAP instead of per-stock AVWAP**
- Anchor AVWAP on market index rather than individual stock
- Would capture regime better
- Risk: HIGH (significant restructuring)

**Decision**: Implement Option 1 immediately, validate, then consider Option 2.
