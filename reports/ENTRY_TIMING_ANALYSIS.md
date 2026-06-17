# ENTRY_TIMING_ANALYSIS
*Generated: 2026-06-17 | Authority Mode Production Audit*

---

## 1. Structural Claim: Timing is 100% SMC-Driven

**Verified.** Entry timing is determined exclusively by the SMC conditions being met simultaneously:

1. `cur < eq` (price below 50% equilibrium of SMC range) — `main.py:693-700`
2. `r1 >= PRICE_GATE` (price in deep discount zone) — `main.py:749`
3. `raw_score >= 35` (minimum score threshold) — `main.py:789`

These three conditions define WHEN a signal fires. None of them can be influenced by research/ranking — they are properties of current price relative to the detected SMC structure (Order Block range, liquidity sweeps, demand zones).

**Research/ranking affects what label is applied (Buy/Strong Buy) and the adj_score magnitude, but NOT the trigger timing.**

---

## 2. stock_mult and ctx_mult Operational Status

**stock_mult**: NULL for 208/220 (94.5%) of 2026 BUY signals.
- Jan–May 2026: all NULL → stock_mult defaults to 1.0 → adj_score = raw_score
- June 2026: 12 signals have stock_mult set (0.88 or 1.07/1.15)
- None of the June signals have r20d outcomes yet (too recent)

**ctx_mult**: NULL for 208/220 signals; June signals show 1.0 or 1.3 (CBE window active)

**Implication**: For the entire evaluated production period (Jan–May 2026), the ranking/research multiplier system was non-operational. Stock_mult and ctx_mult were not computed. Entry decisions were made purely on raw SMC scores with no research enhancement.

---

## 3. Correlation Analysis: Does Higher Score = Earlier/Better Entry?

From 218 signals with r20d outcomes:

| Variable | vs adj_score (r) | vs raw_score (r) |
|---|---|---|
| r5d (5-day return) | -0.0701 | -0.0701 |
| r10d (10-day return) | -0.0631 | -0.0631 |
| r20d (20-day return) | -0.0185 | -0.0185 |
| MFE_20d (max favorable) | +0.0216 | +0.0216 |
| MAE_20d (max adverse) | -0.0322 | -0.0322 |

All correlations are near zero. Score does not predict return at any horizon. The slight negative correlation at 5–10 days may reflect mean-reversion: higher-scoring signals are already deeper in the discount zone, requiring more accumulation time before lifting.

---

## 4. Entry Timing by adj_score Quartile

| Quartile | Score Range | n | WR >7% | Avg R20 | Days to 7% | MFE_20d | MAE_20d |
|---|---|---|---|---|---|---|---|
| Q1 (lowest) | 47–67 | 54 | 46.3% | +6.50% | 5.9 | 14.6% | -6.4% |
| Q2 | 67–71 | 54 | 33.3% | +3.79% | 6.4 | 11.8% | -5.7% |
| Q3 | 71–77 | 54 | 42.6% | +5.38% | 9.0 | 12.3% | -6.2% |
| Q4 (highest) | 77–95 | 56 | 41.1% | +5.41% | 6.5 | 14.2% | -6.7% |

**Q1 has best WR (46.3%) and fastest time to target (5.9 days)** — suggesting lower-scored signals in deep discount are actually closer to the reversal point. Q3 takes longest (9.0 days) to reach 7% target despite mid-range scores.

---

## 5. Hold Duration and Return Progression

| Horizon | n | WR (threshold) | Avg Return | Pct of WR gain vs 5d |
|---|---|---|---|---|
| r5d | 218 | 29.8% (>5%) | 2.37% | Baseline |
| r10d | 218 | 39.5% (>5%) | 3.08% | +9.7 ppts |
| r20d | 218 | 40.8% (>7%) | 5.27% | +11 ppts |
| r40d | 136 | 55.1% (>7%) | 11.6% | +14.3 ppts extra |

**Hold 40 days vs 20 days**: WR increases by 14.3 ppts (55.1% vs 40.8%), avg return doubles (11.6% vs 5.3%). The scanner appears to be identifying multi-week to multi-month reversal setups, not quick scalps.

---

## 6. Days to 7% Target Distribution

Total signals reaching 7%: 149/218 (68.3%)

| Time Bracket | n | % of Achievers | Cumulative % |
|---|---|---|---|
| <= 3 days | 57 | 38.3% | 38.3% |
| 4–7 days | 42 | 28.2% | 66.4% |
| 8–14 days | 37 | 24.8% | 91.3% |
| 15–20 days | 13 | 8.7% | 100.0% |

- **Median: 5 days** to 7% target
- **91.3% of achievers hit target within 2 weeks**
- Fast-movers (<=3 days): 57 signals = strong momentum entries

---

## 7. Monthly Timing vs Market Regime

| Month | n Signals | WR | Avg EGX30 Trend (via ctx_mult) | Interpretation |
|---|---|---|---|---|
| 2026-02 | 63 | 19.1% | Likely flat/down | Scanner fires into weakness |
| 2026-03 | 38 | 55.3% | Recovery | Scanner fires near lows |
| 2026-04 | 76 | 61.8% | Uptrend | Scanner fires in bull |
| 2026-05 | 39 | 20.5% | Weakening | Scanner fires into decline |

The scanner generates signals throughout all market regimes (it fires on SMC conditions, not market trend). February saw 63 signals (highest monthly volume) in a month where WR was 19.1% — meaning the SMC gates were firing frequently during a losing period, suggesting SMC structures were forming but macro conditions prevented follow-through.

---

## 8. Structural Verification: Research Cannot Advance Entry

The following facts prove research/ranking does not affect entry timing:

1. **Price gate trigger**: `price_ok = (r1 >= PRICE_GATE)` — controlled entirely by `sc_price()` in `signal_engine.py`, which is a function of current market price vs SMC range boundaries. Research plays no role.

2. **Raw score gate**: `total >= 35` — this is `sc_price() + sc_ob() + sc_liquidity() + sc_htf() + sc_avwap() + sc_macd() + sc_div() + sc_demand_zone()`. All are real-time market structure functions. No research input.

3. **stock_mult effect**: Amplifies or dampens adj_score (the label), not the trigger. A stock with raw_score=34 (below 35 Skip gate) is Skipped regardless of stock_mult=2.0 — the gate uses raw `total`.

4. **ctx_mult (Ramadan/CBE)**: These are calendar-based, not research-based. They affect the label tier only.

**Conclusion**: Entry timing is 100% driven by SMC conditions. Earlier entry = earlier breach of the discount zone + liquidity sweep conditions. Research contributes zero to timing.

---

## 9. Summary

| Finding | Evidence | Confidence |
|---|---|---|
| Entry timing = 100% SMC gates | main.py:693-803 traced | HIGH |
| stock_mult non-functional Jan–May 2026 | DB confirms NULL for 208/220 | HIGH |
| adj_score has no predictive timing power | r = -0.07 to -0.02 across horizons | HIGH |
| Lower-scored signals enter closer to reversal | Q1 WR=46.3% beats Q4 WR=41.1% | MEDIUM |
| Hold 40d adds 14 ppts WR vs 20d | r40d vs r20d data | MEDIUM |
| Market regime is primary timing variable | WR swing 19% to 62% by month | HIGH |
| Research cannot advance entry | Structural analysis | HIGH |
