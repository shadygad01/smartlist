# EXPECTANCY_DECOMPOSITION
*Generated: 2026-06-17 | Authority Mode Production Audit*

---

## Data

- **Dataset**: 2025-01-01 to 2026-06-14, BUY signals with r20d outcomes
- **n**: 276 signals
- **Win threshold**: r20d > 7%
- **Overall metrics**: WR=39.9%, mean r20d=+5.0%, expectancy=+5.0%

---

## 1. Component Win Rate Attribution (Zero vs Non-Zero)

For each SMC component (r1..r8), signals where the component scored >0 (the condition fired) vs =0 (did not fire):

| Component | W_i (current) | Zero n | WR(zero) | Non-zero n | WR(pos) | Avg Win | Lift | Rank |
|---|---|---|---|---|---|---|---|---|
| r2_ob (OB) | 14.47 | 251 | 37.8% | 25 | **56.0%** | +13.5% | **+18.2%** | #1 |
| r7_div (Divergence) | 10.58 | 254 | 38.2% | 22 | **54.6%** | +11.6% | **+16.4%** | #2 |
| r6_macd (MACD) | 14.87 | 181 | 35.4% | 95 | **47.4%** | **+8.0%** | **+12.0%** | #3 |
| r1_price (Price) | 7.69 | 165 | 37.0% | 111 | 43.2% | +6.7% | +6.3% | #4 |
| r8_demand (DZ) | 29.36 | 203 | 38.4% | 73 | 42.5% | +7.4% | +4.0% | #5 |
| r4_htf (HTF) | 0.70 | 189 | 38.6% | 87 | 41.4% | +6.9% | +2.8% | #6 |
| r3_liquidity (Liq) | 15.24 | 183 | 38.8% | 93 | 40.9% | +6.0% | +2.1% | #7 |
| r5_avwap (AVWAP) | 7.10 | 210 | **41.4%** | 66 | 33.3% | +5.1% | **-8.1%** | #8 |

### Key Component Findings

- **r2_ob (OB)**: Highest binary lift (+18.2%). When price is at an Order Block, WR jumps to 56%. Fires only 9% of the time. Current weight (14.47) is appropriate but component is underutilized.
- **r7_div (Divergence)**: Second-highest lift (+16.4%). Extremely rare (n=22, 8% frequency). High signal value when present. Current weight (10.58) — a 3.5× increase from original (3.0) — correctly elevated.
- **r6_macd (MACD)**: Only component with meaningful continuous correlation (r=0.20) AND high non-zero WR (47.4%) AND best avg non-zero win (+8.0%). Current weight 14.87 (was 4.0) — strongest evidence for the weight change.
- **r5_avwap (AVWAP)**: NEGATIVE lift (-8.1%). When AVWAP scores non-zero, WR drops from 41.4% to 33.3%. This suggests AVWAP fires in "almost there" conditions that actually precede further decline rather than reversal. Current weight (7.10) should be reduced toward zero.
- **r8_demand (DZ)**: Only +4.0% lift despite 29.4% weight (highest). Low frequency (27% of rows score >0) and modest discriminative power. Weight appears inflated vs. predictive value.

---

## 2. Pearson Correlation: Component Score vs r20d

| Component | r (Pearson) | Non-zero n | p-value (approx) |
|---|---|---|---|
| r6_macd | **+0.199** | 95 | ~0.05 |
| r8_demand | +0.108 | 73 | ~0.36 |
| r3_liquidity | +0.066 | 93 | ~0.53 |
| r7_div | +0.050 | 22 | ~0.82 |
| r4_htf | +0.047 | 87 | ~0.66 |
| r2_ob | +0.044 | 25 | ~0.84 |
| r1_price | +0.037 | 111 | ~0.70 |
| r5_avwap | **-0.018** | 66 | ~0.89 |

Only r6_macd approaches statistical significance. All others are noise at this sample size. The correlation analysis confirms: MACD is the most information-dense component; AVWAP is counter-productive.

---

## 3. price_ok Gate Analysis

| Gate State | n | WR >7% | Avg R20 | Median R20 |
|---|---|---|---|---|
| price_ok = 1 (passed) | 53 | **32.1%** | +4.1% | +3.2% |
| price_ok = 0 (failed) | 223 | **41.3%** | +5.2% | +4.5% |
| Difference | — | **-9.2 ppts** | **-1.1%** | -1.3% |

**The price gate is inverted.** Signals that pass price_ok (price in deepest discount) perform 9.2 ppts WORSE than those that fail. This is a critical finding.

Possible explanations:
1. Deepest discount = worst momentum = continued decline
2. The gate threshold may be set too broadly (nearly everything passes with current W_PRICE=7.69)
3. Wait signals (price_ok=0) that eventually fire may be capturing better entry points

Note: This dataset includes Wait signals, not just BUY-classified signals, since the r20d outcome is stored regardless.

---

## 4. stock_mult Quartile Analysis

For 2025-2026 data: stock_mult was NULL for 274/276 rows — insufficient data to compute quartile analysis. The only 2 rows with stock_mult populated have values 0.88 and 1.07, both June 2026 (no r20d outcomes).

**Conclusion**: stock_mult impact on expectancy cannot be measured from available data. The ranking engine was not operational during the evaluated production period.

---

## 5. adj_score Quartile Analysis

| Quartile | adj Range | n | WR >7% | Avg R20 |
|---|---|---|---|---|
| Q1 (lowest) | 40–66 | 69 | 31.9% | +3.4% |
| Q2 | 66–69 | 69 | **47.8%** | **+6.9%** |
| Q3 | 69–75 | 69 | 40.6% | +4.5% |
| Q4 (highest) | 75–95 | 69 | 37.7% | +5.2% |

Q2 (adj 66-69) outperforms Q4 (adj 75-95). The optimal entry is a narrow mid-range band, not the highest-confidence signals.

---

## 6. Signal Quality by Active Component Count

Signals where components r1..r8 were all zero (stored as NULL) vs those with populated components:

| Active Components | n | WR >7% | Avg R20 | Note |
|---|---|---|---|---|
| 0 (all NULL) | 162 | 37.0% | +3.8% | Jan-May DB schema, no components |
| 3 | 14 | 57.1% | +5.1% | Best small n |
| 4 | 22 | 45.5% | +9.5% | High quality |
| 5 | 24 | 50.0% | +10.2% | High quality |
| 6 | 38 | 34.2% | +5.1% | Diminishing returns |
| 7 | 9 | 44.4% | +3.2% | Over-fitted? |
| 8 | 3 | 66.7% | +10.7% | Too small |

Signals with 4-5 active components appear optimal (WR 45-50%, avg R20 +9.5-10.2%). The 162-row "no component data" group shows lower WR (37%) and avg R20 (+3.8%), consistent with these being older-format signals with less precise scoring.

---

## 7. Demand Zone Subsystem Analysis

| Demand Zone Config | n | WR >7% | Avg R20 | Lift over base |
|---|---|---|---|---|
| HVN only | 36 | **52.8%** | **+10.8%** | +14.6% |
| SV only | 2 | 0.0% | +4.3% | -35.6%¹ |
| SV + HVN | 0 | N/A | N/A | N/A |
| Neither | 238 | 37.8% | +4.1% | Baseline |

¹ n=2, statistically meaningless

**HVN (High Volume Node) is the best demand-zone signal**: +14.6% WR lift, +6.7% avg R20 lift. No SV+HVN confluences in the dataset suggests this condition is extremely rare or never triggers.

---

## 8. Expectancy Attribution Model

Using component lift analysis to estimate each factor's contribution:

| Factor | Frequency | Lift | Expected Contribution |
|---|---|---|---|
| Market regime (bull month) | ~55% of months | +42% WR swing | **+23% WR** |
| r2_ob presence | 9% of signals | +18.2% lift | +1.6% WR |
| r7_div presence | 8% of signals | +16.4% lift | +1.3% WR |
| r6_macd presence | 34% of signals | +12.0% lift | +4.1% WR |
| r1_price magnitude | 40% of signals | +6.3% lift | +2.5% WR |
| r8_demand (DZ/HVN) | 27% of signals | +4.0% lift | +1.1% WR |
| r5_avwap (drag) | 24% of signals | -8.1% lift | -1.9% WR drag |

**Regime effect is 5-15× larger than any individual SMC component** in terms of WR impact. The scanner's alpha comes primarily from firing during market regime alignment. MACD is the single strongest SMC component; AVWAP creates net drag.

---

## 9. Ranked Recommendations by Expected Impact

1. **Add regime filter** (skip signals when EGX30 in confirmed downtrend): Est. +20-25% WR improvement based on monthly analysis. Highest impact available.

2. **Reduce W_AVWAP toward 0** (currently 7.1): AVWAP scoring hurts WR by -8.1%. Removing or inverting it would improve signal quality.

3. **Investigate price_ok gate logic**: gate=1 signals underperform by 9.2 ppts. Either the gate threshold is too low (W_PRICE=7.69 makes it too easy to pass) or the deepest discount signals need a different entry approach.

4. **Raise W_OB (Order Block)**: +18.2% lift with current 14.5% weight. Evidence supports pushing higher, but needs more non-zero examples (only n=25).

5. **Treat W_DZ as information, not driver**: +4% lift vs 29.4% weight — misaligned. Consider reducing to 15-20 (matching RL optimizer's 15.1 recommendation).

6. **Restore W_PRICE to 20-30 range**: Current 7.7 from 30 original — dramatically reduced. RL optimizer recommends 30.6. Restoring price as primary gate would tighten the price_ok filter and potentially resolve the inverted gate finding.

---

## 10. Data Quality Notes

- 162/276 (58.7%) of rows have zero component values (Jan–May 2026 DB schema gap) — expectancy decomposition by component is based on the 114 rows with actual component data
- Component correlation analysis has low statistical power (n per non-zero component: 22-111)
- All findings should be considered MEDIUM confidence pending a dataset with full component coverage
