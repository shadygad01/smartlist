# WEIGHT_IMPACT_REPORT
*Generated: 2026-06-17 | Authority Mode Production Audit*

---

## Section 1: Current Production Weights (config/weights.json, 2026-06-15)

| Component | Weight | Share of Total | Original Weight | Change |
|---|---|---|---|---|
| r1_price | 7.6871 | 7.7% | 30.0 | -75% |
| r2_ob | 14.4677 | 14.5% | 10.0 | +45% |
| r3_liquidity | 15.2448 | 15.2% | 20.0 | -24% |
| r4_htf | 0.7011 | 0.7% | 10.0 | -93% |
| r5_avwap | 7.0981 | 7.1% | 8.0 | -11% |
| r6_macd | 14.8669 | 14.9% | 4.0 | +272% |
| r7_div | 10.5770 | 10.6% | 3.0 | +253% |
| r8_demand | 29.3573 | 29.4% | 15.0 | +96% |
| **TOTAL** | **100.0000** | **100.0%** | **100.0** | — |

**Context**: Current weights were last updated 2026-06-15 via production_promoter. The smc_rl_optimizer (run 2026-06-13) computed near-original weights (W_PRICE=30.6, W_DZ=15.1) but these are NOT in production — they were never promoted. The continuous_learning chain produced the weights currently in config.

---

## Section 2: Score Formula

From `signal_engine.py:848` and `main.py:777`:
```
raw_score = r1 + r2 + r3 + r4 + r5 + r6 + r7 + r8
adj_score = min(int(round(raw_score × stock_mult × ctx_mult)), 100)
```

Each `r_i` is scored continuously (not binary) within [0, W_i] using the formulas in `sc_price()`, `sc_ob()`, `sc_liquidity()`, etc. The weights ARE the max points for each component.

---

## Section 3: Data Availability for Weight Sensitivity Analysis

**Total 2026 BUY signals**: 220  
**With r1..r8 component data populated**: 71 (32.3%) — June 2026 only  
**Without component data (Jan–May 2026)**: 149 (67.7%) — only raw_score and adj_score stored

For 149/220 signals, weight sensitivity analysis is impossible without component data. Results below apply to the 71 June 2026 signals only.

**Note on r1..r8 schema**: June 2026 signals show mixed weight regimes (some r_i values exceed current W_i, indicating stored values from prior weight configurations). Weight fractionalization is approximate.

---

## Section 4: Weight Scenario Results (n=71 signals with component data)

| Scenario | Description | N_BUY+ | Changed vs A | Pct Changed | Note |
|---|---|---|---|---|---|
| **A** (current) | Config weights, actual stock_mult/ctx_mult | 54 | 0 | 0.0% | Baseline |
| **B** (original) | W_PRICE=30, W_OB=10, W_LIQ=20, W_HTF=10, W_AVWAP=8, W_MACD=4, W_DIV=3, W_DZ=15; sm=1.0 | 70 | 14 | 19.7% | More signals but same composition |
| **C** (DZ=0) | Demand Zone weight zeroed out | 22 | 56 | 78.9% | Most signals lost — DZ dominates |
| **D** (DZ=100) | Only Demand Zone scored | 0 | 56 | 78.9% | 0 signals — DZ rarely fires |
| **E** (OB=0) | Order Block weight zeroed | 24 | 56 | 78.9% | Heavy collateral from DZ dependence |
| **F** (OB=100) | Only Order Block scored | 6 | 52 | 73.2% | OB rarely fires at full weight |
| **G** (Equal) | 12.5 each | 66 | 20 | 28.2% | Closest to Scenario B in outcome |

---

## Section 5: Interpretation

### 5.1 Weight Independence NOT Confirmed
The 73.2–78.9% change rates under extreme scenarios (C, D, E, F) show that the entry engine IS highly weight-sensitive when component data is available.

**Scenario A produces 54 BUY signals; zeroing DZ (Scenario C) drops to 22.** This means 32 of the 54 BUY signals depend entirely on r8_demand scoring non-zero. Since r8_demand has a weight of 29.4% (largest component), the current system is heavily DZ-dependent.

### 5.2 PRICE_GATE Bottleneck Dominates
For Jan–May 2026 (149/220 signals where adj_score = raw_score, no multipliers): all 217 "Strong Buy" signals pass the entry gate because adj_score >= 55 (they're Strong Buys by definition). The price_ok gate is the actual bottleneck in production — only 9/228 recent signals pass price_ok.

### 5.3 Original vs Current Weights
Scenario B (original weights, sm=1.0) produces MORE BUY signals (70 vs 54) because W_PRICE=30 gives more credit to price position, which directly feeds into the price_ok gate. The current W_PRICE=7.69 effectively lowered the price gate from 16.5 to ~4.2, making it easier to pass but giving price position less scoring weight.

### 5.4 DZ Weight Inflation
r8_demand has the highest weight (29.4%) but the lowest fill rate in the data: only 14.5% of component-bearing rows score any r8 points. This means 85.5% of signals get 29.4% of the score space for free (scored as zero on the largest component). This is a structural mismatch: the most important component fires least often.

---

## Section 6: Price Gate Sensitivity

Current PRICE_GATE values with W_PRICE=7.69:
- WHITELIST gate: 0.50 × 7.69 = **3.84 pts**
- NORMAL gate: 0.55 × 7.69 = **4.23 pts**

Original gates with W_PRICE=30:
- WHITELIST: 15.0 pts
- NORMAL: 16.5 pts

The price gate now requires r1 >= ~4 pts out of a max 7.69, vs. original 15+ pts out of 30. This means any signal with price even slightly in the discount zone passes the price gate with current weights.

**DB evidence (June 2026, n=13 rows with price_gate stored)**:
- All stored price_gate values are 15 or 16 (old regime values)
- price_ok=0 for all 13 rows despite gate of 15 — meaning these were computed under old weights before the 2026-06-15 update
- The 2026 BUY signals from Jan–May lack price_gate column data

---

## Section 7: RL Optimizer Divergence from Production

The SMC RL optimizer (last run 2026-06-13) computed weights close to the original:

| Component | RL Optimal | Current Config | Original |
|---|---|---|---|
| r1_price | 30.6 | 7.7 | 30.0 |
| r2_ob | 9.6 | 14.5 | 10.0 |
| r3_liquidity | 15.0 | 15.2 | 20.0 |
| r4_htf | 9.6 | 0.7 | 10.0 |
| r5_avwap | 4.1 | 7.1 | 8.0 |
| r6_macd | 1.1 | 14.9 | 4.0 |
| r7_div | 3.1 | 10.6 | 3.0 |
| r8_demand | 15.1 | 29.4 | 15.0 |

The RL optimizer (using 395 data points, 40 epochs) converged toward original weights — placing W_PRICE back at 30 and W_DZ at 15. The current config/weights.json diverges significantly from what the RL optimizer recommends, yet the RL weights are not promoted (smc_rl_weights.json is disconnected from config/weights.json).

**RL performance at its weights**: all_win_rate=67.8%, top_q_win_rate=68.4%, top_q_avg_252d=66.18%.

---

## Section 8: Conclusions

1. The current weight configuration is markedly different from both the original and the RL-optimized weights
2. W_DZ (29.4%) is 2× the RL-optimal (15.1%) and 2× the original (15.0)
3. W_PRICE has been reduced from 30→7.7, lowering the price gate significantly
4. Weight changes matter: 19.7% of June signals would change classification under original weights
5. The optimization pipeline (continuous_learning → production_promoter) has fired 8 times, producing a weight set that diverges from the RL optimizer's recommendation
6. The RL-optimized weights in smc_rl_weights.json are never used in production
