R1-R8 EVOLUTION ROADMAP
=======================
Date: 2026-06-19
Source of truth: docs/LEARNING_LABS_CONSTITUTION.md

The purpose of this roadmap is to make each of r1-r8 measurably better
over time. Every item maps to a specific backbone factor, an allowed
outcome type, and the expected production improvement.

=======================================================================
CURRENT STATE (knowledge_base.json — factor_findings)
=======================================================================

  r1_price   verdict=NEGATIVE  suggested_weight=5.4   n=1051
  r2_ob      verdict=NEGATIVE  suggested_weight=10.1  n=1051
  r3_liquidity verdict=NEGATIVE suggested_weight=10.7 n=1051
  r4_htf     verdict=POSITIVE  suggested_weight=0.84  win_rate=0.47  exp=0.055
  r5_avwap   verdict=POSITIVE  suggested_weight=8.5   n=1051
  r6_macd    verdict=POSITIVE  suggested_weight=17.8  n=1051
  r7_div     verdict=TAIL_DRIVER suggested_weight=12.7 tail_contribution=0.31
  r8_demand  verdict=NEGATIVE  suggested_weight=20.6  n=1051

Key observation: r1, r2, r3, r8 show NEGATIVE verdicts yet carry the
highest production weights (30, 10, 20, 15). These are the priority
improvement targets.

=======================================================================
FACTOR AUDIT — ALLOWED OUTCOMES PER CONSTITUTION
=======================================================================

Every item below is classified as ONE of:
  1. Factor Refinement      — improve the scoring formula / thresholds
  2. Factor Replacement     — swap the underlying indicator
  3. Measurement Improvement — better detection of the same signal
  4. Weight Optimization    — adjust contribution to raw_score
  5. Interaction Enhancement — improve how this factor works with others

=======================================================================
R1 — PRICE ZONE (current weight: 30, suggested: 5.4)
=======================================================================
Verdict: NEGATIVE (n=1051)
Production role: Gate + primary score (30/100 max)

Evidence from archived sub-signals:
  (none routed from archived_findings yet)

ROADMAP:

[R1-A] Measurement Improvement — Discount Zone Depth Calibration
  Question: Does the 0-15% Buy Zone / 15-50% Mid-Discount split
            correctly differentiate entry quality?
  Lab: factor_lab → r1_price with zone_depth bins
  Expected: +5-10pp win rate for tightest zone entries
  Evidence needed: 100+ signals per zone bin
  Priority: HIGH (NEGATIVE verdict, largest weight)

[R1-B] Weight Optimization — Reduce from 30 to ~20
  Evidence: suggested_weight=5.4 is extreme; apply blend
            (current × 0.5 + suggested × 0.5) → ~17.7
  Outcome: Rebalances scoring so r3, r7, r8 have more influence
  Constraint: r1 remains mandatory gate (non-negotiable)
  Lab: weight_optimizer → run with Spearman + OOS validation
  Priority: HIGH

[R1-C] Interaction Enhancement — r1 × r3 (zone + liquidity sweep)
  Hypothesis: Signals where price enters Buy Zone via liquidity sweep
              outperform plain Buy Zone entries
  Evidence: sweep_detected win_rate=0.476, avg_return=5.28%
            routes_to=r3_liquidity but also conditions r1 entry
  Lab: interaction_lab → r1_zone_bin × sweep_detected
  Priority: MEDIUM

=======================================================================
R2 — ORDER BLOCK (current weight: 10, suggested: 10.1)
=======================================================================
Verdict: NEGATIVE (n=1051)
Evidence: order_block_present verdict=NEGATIVE (n=175, avg_return=3.4%)

ROADMAP:

[R2-A] Measurement Improvement — OB Detection Threshold
  Problem: Current OB requires bearish candle + 1.5× impulse in Buy Zone
  Hypothesis: Looser impulse (1.2×) or stronger (2.0×) may improve
  Lab: parameter_lab → r2_impulse_multiplier sensitivity
  Expected: +3-8% expectancy improvement
  Priority: HIGH (NEGATIVE verdict from 175 signals)

[R2-B] Refinement — OB Mitigation Level Logic
  Sub-signal: order_block_present verdict=NEGATIVE
  routes_to: r2_ob
  The detection seems to fire on weak OBs. Add minimum zone quality
  score (OB depth below 10% of range = disqualify)
  Lab: factor_lab → r2_ob with quality_threshold variants
  Priority: HIGH

[R2-C] Weight Optimization — Hold at 10 pending R2-A/B
  Current weight=10 matches suggested_weight=10.1.
  Do not change weight until measurement is improved.
  Priority: LOW (wait for R2-A/B)

=======================================================================
R3 — LIQUIDITY (current weight: 20, suggested: 10.7)
=======================================================================
Verdict: NEGATIVE (n=1051)
Evidence from archived sub-signals:
  sweep_detected:   verdict=POSITIVE  n=477  avg=5.28%  mfe20d=13.27%
  wick_rejection:   verdict=NEGATIVE  n=111  avg=3.81%  mfe20d=12.04%
  equal_lows:       verdict=NEGATIVE  n=44   avg=2.82%  mfe20d=11.2%

Key insight: sweep_detected is POSITIVE (routes to r3) but the
overall r3_liquidity factor scores NEGATIVE. The scoring formula
may weight sub-signals wrong or the gate is too loose.

ROADMAP:

[R3-A] Measurement Improvement — Sweep Gets Full Score; Others Partial
  Current: sweep OR wick OR equal_lows all produce similar r3 scores
  Change: sweep → 100% r3 weight; wick → 60%; equal_lows → 30%
  Evidence: sweep mfe20d=13.27% vs equal_lows mfe20d=11.2% (16% better)
  Lab: parameter_lab → r3_sweep_weight, r3_wick_weight, r3_eq_weight
  Priority: HIGH (largest evidence base, clear ranking exists)

[R3-B] Weight Optimization — Reduce from 20 to ~15
  suggested_weight=10.7 but sweep evidence is strong.
  Blend: (20 × 0.7 + 10.7 × 0.3) = 17.2
  Keep higher than suggested because sweep sub-signal is POSITIVE
  Lab: weight_optimizer → r3_liquidity
  Priority: MEDIUM (after R3-A)

[R3-C] Interaction Enhancement — r3 × r8 (liquidity + demand zone)
  Hypothesis: Sweep into HVN area (demand zone) is highest-quality entry
  Evidence: hvn_hit routes_to r8 (avg_return=5.11%, mfe20d=13.92%)
            sweep_detected routes_to r3 (avg_return=5.28%)
  Lab: interaction_lab → sweep_detected × hvn_hit
  Priority: MEDIUM

=======================================================================
R4 — HTF STRUCTURE (current weight: 10, suggested: 0.84)
=======================================================================
Verdict: POSITIVE  win_rate=0.47  expectancy=0.055  avg_return=8.5%
Evidence from archived sub-signals:
  htf_higher_high: verdict=POSITIVE  n=216  avg=5.48%  mfe20d=13.93%
  htf_hh_and_hl:   verdict=NEUTRAL   n=148  avg=5.38%  mfe20d=13.12%

ROADMAP:

[R4-A] Weight Optimization — Increase from 10 (suggested: 0.84 is outlier)
  The suggested_weight of 0.84 is from a single linear optimization run
  and is likely an overfit. r4_htf shows POSITIVE verdict.
  Hold at 10, or test small increase to 12.
  Lab: walk_forward_backtester → r4_htf weight variants
  Priority: LOW (already POSITIVE, don't over-optimize)

[R4-B] Measurement Improvement — Separate MA200 from HH/HL Structure
  Evidence: htf_higher_high POSITIVE (n=216), htf_hh_and_hl NEUTRAL (n=148)
  Higher highs alone predict better than combined HH+HL
  Current: r4 scores all three sub-components equally (40%+30%+30%)
  Change: MA200 40% + higher_high 40% + higher_low 20%
  Lab: factor_lab → r4_htf with restructured component weights
  Priority: MEDIUM

=======================================================================
R5 — AVWAP (current weight: 8, suggested: 8.5)
=======================================================================
Verdict: POSITIVE  n=1051  suggested_weight≈8.5

ROADMAP:

[R5-A] Refinement — Anchor Window Sensitivity
  Current anchor: last 60-bar swing low
  Question: Is 60 bars optimal? Test 40, 80, 120 bars
  Lab: parameter_lab → r5_avwap_anchor_window
  Priority: LOW (POSITIVE verdict, weight near-optimal)

[R5-B] Weight Optimization — Minor adjustment 8→8.5
  suggested_weight=8.5 vs current 8.
  Small improvement available; validate OOS before promoting.
  Lab: weight_optimizer → r5_avwap isolated
  Priority: LOW

=======================================================================
R6 — MACD MOMENTUM (current weight: 4, suggested: 17.8)
=======================================================================
Verdict: POSITIVE  n=1051  suggested_weight=17.8 (extreme outlier)

ROADMAP:

[R6-A] Weight Optimization — suggested_weight=17.8 is SUSPECT
  Current weight=4; suggested is 4.45× higher.
  This is likely in-sample overfitting. MACD has maximum information
  content of 4 points in the scoring formula.
  Action: Run walk-forward backtester with weight in [4, 6, 8].
  Do NOT accept 17.8 without OOS validation.
  Lab: walk_forward_backtester → r6_macd weight variants
  Priority: HIGH (large suggested deviation, needs OOS validation)

[R6-B] Replacement Investigation — MACD vs Rate-of-Change
  r6 measures momentum reversal; MACD is one way.
  Hypothesis: 10-bar ROC < -5% may be a better reversal signal
  Lab: parameter_lab → r6 alternative indicators
  Priority: LOW (only after R6-A is resolved)

=======================================================================
R7 — DIVERGENCE (current weight: 3, suggested: 12.7)
=======================================================================
Verdict: TAIL_DRIVER  win_rate=0.40  expectancy=0.048  tail_contribution=0.31

Key insight: r7 is a TAIL_DRIVER — it identifies multi-bagger candidates
even though average win rate is only 40%. The 31% tail contribution means
it adds disproportionate value in the right tail.

Evidence from archived sub-signals:
  rsi_divergence: routes_to r7_div
  macd_divergence: routes_to r7_div

ROADMAP:

[R7-A] Measurement Improvement — Separate RSI vs MACD Divergence
  Evidence: rsi_div and macd_div archived separately
  Hypothesis: RSI divergence may be more reliable than MACD divergence
  Lab: factor_lab → r7_div with rsi_div_only vs macd_div_only split
  Priority: MEDIUM (TAIL_DRIVER — don't break what works)

[R7-B] Weight Optimization — Small increase from 3 to 5-6
  suggested_weight=12.7 is extreme for a 3-point factor.
  TAIL_DRIVER nature suggests increasing weight, but cautiously.
  Test: weight 4 → OOS validation → if no degradation → try 5.
  Lab: weight_optimizer → r7_div isolated
  Priority: MEDIUM

[R7-C] Interaction Enhancement — r7 × r3 (divergence + liquidity sweep)
  Hypothesis: Divergence that coincides with a liquidity sweep has
              the highest tail-risk reward (multi-bagger setup)
  Lab: interaction_lab → r7_div × sweep_detected
  Priority: LOW

=======================================================================
R8 — DEMAND ZONE (current weight: 15, suggested: 20.6)
=======================================================================
Verdict: NEGATIVE  n=1051  suggested_weight=20.6

Evidence from archived sub-signals:
  stopping_volume: verdict=NEGATIVE n=19  avg=3.3%  (very small n)
  hvn_hit:         verdict=POSITIVE  n=~  avg=5.11% mfe20d=13.92%

Key insight: hvn_hit (routes_to r8) is POSITIVE but stopping_volume
is NEGATIVE. The combined r8_demand score is dragged down by SV-only
signals which get 60% of r8 weight even without HVN confirmation.

ROADMAP:

[R8-A] Measurement Improvement — SV-only Weight Reduction
  Current: SV + HVN → 100% r8; SV only → 60%; HVN only → 0%
  Evidence: HVN alone is POSITIVE; SV alone is NEGATIVE (n=19, weak)
  Change: SV + HVN → 100%; SV only → 30%; HVN only → 50%
  Lab: parameter_lab → r8_sv_only_fraction, r8_hvn_only_fraction
  Priority: HIGH (NEGATIVE overall verdict; hvn_hit is POSITIVE)

[R8-B] Weight Optimization — Increase from 15 to ~17-18
  suggested_weight=20.6; current=15. If R8-A improves verdict,
  a weight increase is justified. Blend: (15 × 0.7 + 20.6 × 0.3) = 16.7
  Lab: weight_optimizer → r8_demand after R8-A
  Priority: MEDIUM (after R8-A)

[R8-C] Interaction Enhancement — r8 × r1 (demand zone inside Buy Zone)
  Current: HVN must already be in Buy Zone (0-15%).
  Enhancement: Score r8 higher when HVN center is in 0-8% (deepest)
  Lab: interaction_lab → hvn_depth_pct binned vs r20d
  Priority: LOW

=======================================================================
PRIORITIZED EXECUTION ORDER
=======================================================================

PHASE 1 — High Priority (address NEGATIVE verdicts)
  R8-A: SV-only fraction reduction   (r8_demand measurement)
  R1-A: Buy Zone depth calibration   (r1_price measurement)
  R2-A/B: OB detection improvement   (r2_ob measurement + refinement)
  R3-A: Sweep vs wick vs equal scoring (r3_liquidity measurement)
  R6-A: MACD weight OOS validation   (r6_macd weight)

PHASE 2 — Medium Priority (optimize positive factors)
  R1-B: Weight reduction 30→~18      (r1_price weight)
  R3-B: Weight adjustment 20→~17     (r3_liquidity weight)
  R4-B: MA200+HH reweighting         (r4_htf measurement)
  R7-A: RSI vs MACD divergence split (r7_div measurement)
  R7-B: Weight increase 3→5          (r7_div weight)
  R8-B: Weight increase 15→17        (r8_demand weight)

PHASE 3 — Low Priority (interactions and edge refinements)
  R1-C: r1 × r3 interaction          (price zone × liquidity)
  R3-C: r3 × r8 interaction          (liquidity × demand)
  R4-A: r4 weight OOS re-test        (hold unless evidence changes)
  R5-A/B: AVWAP anchor + weight      (r5_avwap refinement)
  R6-B: MACD replacement research    (r6_macd replacement candidate)
  R7-C: r7 × r3 tail interaction     (divergence × sweep)
  R8-C: HVN depth scoring            (r8_demand refinement)

=======================================================================
PROMOTION GATE (per Constitution)
=======================================================================

Before any item above reaches production, it MUST provide:
  1. target_factor: one of r1-r8
  2. expected_improvement: quantified (e.g. "+3% expectancy")
  3. supporting_evidence: OOS validated, walk-forward consistent
  4. improvement_type: one of the 5 allowed outcomes

Items that cannot answer all four: NOT PROMOTED.

=======================================================================
SUCCESS METRIC
=======================================================================

Success is NOT:
  x more discoveries
  x more reports
  x higher GX Score

Success IS:
  ✓ r1_price verdict changes from NEGATIVE → POSITIVE or NEUTRAL
  ✓ r2_ob verdict changes from NEGATIVE → POSITIVE
  ✓ r3_liquidity overall verdict improves (sub-scoring fixed)
  ✓ r8_demand verdict changes from NEGATIVE → POSITIVE
  ✓ r6_macd weight validated OOS (17.8 accepted or rejected)
  ✓ r7_div tail_contribution maintained or increased
  ✓ Total raw_score expectancy improves on walk-forward test
