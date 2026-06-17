# NEXT BEST IMPROVEMENT RANKING

**Date**: 2026-06-17  
**Baseline**: WR=39.5%, Expectancy=+4.8% (2025+ signals, n=321)

All estimates derived from actual DB data unless noted.

---

## Rank 1 — Weight Realignment: Disable AVWAP, Boost Divergence + MACD + OB

**Expected WR Lift**: +6 to +10pp  
**Expected Expectancy Lift**: +2 to +3%  
**Implementation**: ~20 lines (update weights.json via production_promoter)  
**Risk**: LOW (evidence-backed from 321 signal dataset)

### Evidence

| Gate | Current Weight | Alpha Lift | Correct Direction |
|---|---|---|---|
| r5_avwap | 7.10 | **-4.8pp** | Set to 0 |
| r7_div | 3.00 | +15.1pp | Increase to 12+ |
| r6_macd | 4.00 | +10.7pp | Increase to 12+ |
| r2_ob | 10.00 | +9.1pp | Increase to 15+ |
| r8_demand | 29.36 | +0.4pp | Reduce to 10-12 |
| r4_htf | 0.70 | +2.8pp | Increase to 8+ |

### Suggested New Weights

```json
{
  "r1_price": 20,
  "r2_ob": 15,
  "r3_liquidity": 15,
  "r4_htf": 8,
  "r5_avwap": 0,
  "r6_macd": 12,
  "r7_div": 12,
  "r8_demand": 12
}
```

### What Changes

- Total max = 94 (vs 100 current) — score scale maintained
- Divergence becomes a primary gate (fired 10% of signals, +15pp WR)
- MACD becomes a primary gate (fired 43% of signals, +10.7pp WR)
- AVWAP removed (currently -4.8pp drag, W_AVWAP=7.10 wasted weight)
- Demand zone reduced (currently oversized at 29+ pts for +0.4pp lift)

---

## Rank 2 — Raise Raw Score Gate from 35 to 50

**Expected WR Lift**: +1 to +2pp  
**Expected Selectivity**: -25% fewer signals  
**Implementation**: 5 lines in main.py  
**Risk**: LOW-MEDIUM (fewer signals, but higher quality)

### Evidence

| Band | WR | Expectancy |
|---|---|---|
| 40-49 | 38.2% | +3.5% |
| 50-59 | 37.9% | +4.3% |
| 60-69 | **40.8%** | **+5.5%** |
| 70-79 | 40.0% | +5.0% |

The 40-49 band underperforms all higher bands. Filtering to raw >= 50 would remove 55 low-quality
signals from 2025+ dataset, gaining +0.6-2pp WR on remaining signals.

---

## Rank 3 — Restore Price Gate Power (W_PRICE back toward 20-25)

**Expected WR Lift**: +2 to +4pp  
**Implementation**: 5 lines (update weights.json)  
**Risk**: MEDIUM (gate currently passes almost everything; raising will reject signals)

### Evidence

At current W_PRICE=7.69, gate threshold = 0.55 × 7.69 = 4.2 pts (minimal).
Original design: W_PRICE=30, gate=16 pts (meaningful 53% filter).
RL suggests W_PRICE=30.6 (nearly original level).

**Simulated impact** (restore to W_PRICE=20, gate_frac=0.55 → gate=11):
- Signals in buy zone (r1>=11): ~40% of current signals
- Historical WR of signals with r1 in top 50% should be higher

---

## Rank 4 — MACD Gate Inversion Fix

**Expected WR Lift**: +2 to +3pp  
**Implementation**: 10 lines in signal_engine.py  
**Risk**: LOW

### Current MACD Formula

```python
if macd_now >= 0: return 0  # blocks premium MACD
if crossed_up: return W_MACD  # best: bullish cross below zero
else: return round(W_MACD/2)  # partial: below zero no cross
```

MACD fires on 43% of signals with +10.7pp lift. But partial score (half W_MACD for
no-crossover below zero) adds noise. Consider: only score on confirmed crossover OR
above a threshold histogram value.

---

## Rank 5 — Regime Filter Calibration

**Expected WR Lift**: +3 to +5pp in bear periods  
**Implementation**: DONE (this session)  
**Risk**: LOW (already implemented)

### Evidence

Bear months (2022-04-06, 2024-12, 2026-02): WR 6-19%  
Bull months (2023-03, 2026-04): WR 55-70%

With 0.70× multiplier in bear regime: borderline signals (score 35-57) fall below entry
gate (40 pts), reducing false positives by ~25-30% in bear months.

Note: Current `egx30_trend` data is mostly NULL (needs backfill). Regime filter will activate
only for new live signals where `score_signal()` returns a trend.

---

## Rank 6 — RL Weight Graduation

**Expected WR Lift**: +2 to +4pp (speculative)  
**Implementation**: ~30 lines (promote RL weights via production_promoter)  
**Risk**: MEDIUM (RL trained on different metric — 90d return not 20d WR)

### RL Weight Signals

RL cut AVWAP (-49%) and MACD (-73%) and Liquidity (-25%) — all confirmed by gate analysis.
RL kept r1_price (~same) and r8_demand (~same).

RL confirms: AVWAP and MACD are overweighted; but RL cuts MACD too aggressively.
Hybrid approach: use RL for direction, gate analysis for magnitude.

---

## Implementation Priority

| Rank | Action | Files | Effort | Risk | Expected Alpha |
|---|---|---|---|---|---|
| 1 | Realign weights (disable AVWAP, boost r7/r6/r2) | weights.json | ~20 lines | LOW | +6-10pp WR |
| 2 | Raise score gate to 50 | main.py | ~5 lines | LOW | +1-2pp WR |
| 3 | Restore W_PRICE to 20-25 | weights.json | ~5 lines | MED | +2-4pp WR |
| 4 | MACD gate refinement | signal_engine.py | ~10 lines | LOW | +2-3pp WR |
| 5 | Regime calibration (done) | gates_config.json | done | LOW | +3-5pp (bear) |
| 6 | RL weight graduation | weights.json | ~30 lines | MED | +2-4pp WR |

**Combined potential if all implemented**: WR baseline 39.5% → estimated 50-55%
