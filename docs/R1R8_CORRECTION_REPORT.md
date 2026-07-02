R1-R8 CORRECTION REPORT
=======================
Date: 2026-06-19
Branch: claude/learning-labs-audit-igq1q2

=======================================================================
CORRECTION 1 — SCORE_MAX BUG FIX
=======================================================================
File: gx_learning_layer.py:742-743
Status: FIXED

Before:
  SCORE_MAX = {"r1_price": 30, "r2_ob": 10, "r3_liquidity": 10, "r4_htf": 20,
               "r5_avwap": 10, "r6_macd": 10, "r7_div": 5, "r8_demand": 5}

After:
  SCORE_MAX = {"r1_price": 30, "r2_ob": 10, "r3_liquidity": 20, "r4_htf": 10,
               "r5_avwap": 8,  "r6_macd": 4,  "r7_div": 3,  "r8_demand": 15}

Impact: Section ⑪ "Score Contribution Decomposition" now uses correct
weights. r3 (Liquidity) and r8 (Demand Zone) were the most distorted;
both are now correctly represented at 20pts and 15pts respectively.

=======================================================================
CORRECTION 2 — R1-R8 EVOLUTION ENGINE ADDED
=======================================================================
File: gx_learning_layer.py
Status: IMPLEMENTED

Added constants and functions:

  R1_R8_MAP          — Definition of all 8 backbone factors with their
                        sub-signals and allowed improvement types.

  SUBFACTOR_TO_RFACTOR — Keyword routing table: maps any sub-signal
                        name to its parent r-factor.

  _map_rec_to_rfactor(rec) — Assigns target_factor (r1-r8) to every
                        recommendation using column key matching,
                        sub-signal routing, and keyword patterns.

  _classify_improvement_type(rec) — Labels each rec as one of:
                        weight_optimization / replacement /
                        measurement / interaction / refinement.

  compute_rfactor_evolution(all_recs, src) — Per-factor state dict:
                        evolution_score (0-100), current weight,
                        suggested weight, KB verdict, win rate,
                        expectancy, n_recs, n_validated, priority.

  compute_evolution_score(rfactor_state) — Replaces abstract GX Score
                        as the primary backbone metric:
                        R1-R8 Evolution Score (avg of 8 factor scores),
                        factors_evidenced, factors_validated, needs_work.

  _rfactor_evolution_card(rfactor_state, evo) — HTML dashboard card
                        showing per-factor status table, evolution
                        scores, priority flags, and work items.

=======================================================================
CORRECTION 3 — EVERY RECOMMENDATION NOW TAGGED WITH TARGET FACTOR
=======================================================================
File: gx_learning_layer.py → _extract_recommendations()
Status: IMPLEMENTED

All four recommendation sources now produce recs with:
  target_factor    — which r-factor (r1-r8) this rec targets
  improvement_type — weight_optimization / refinement / measurement /
                     interaction / replacement

If a rec cannot be mapped to any r-factor, target_factor = "unknown"
(visible in dashboard — allows manual triage, not silent loss).

The Recommendation Tracker table (Section ④) now shows:
  Target Factor column (colored badge: r1-r8 in blue, unknown in grey)
  Improvement Type column

=======================================================================
CORRECTION 4 — DASHBOARD HERO NOW SHOWS R1-R8 EVOLUTION SCORE
=======================================================================
File: gx_learning_layer.py → build_html()
Status: IMPLEMENTED

Hero circle now displays: "R1-R8 EVOLUTION SCORE"
Hero title changed to: "R1-R8 Evolution Report"
Hero subtitle: "R1-R8 EVOLUTION ENGINE — SMARTLIST BACKBONE"
Hero badges: Factors Measured (N/8), Factors Improved (N/8)

GX Score (ecosystem health) preserved in badge and Section ①.
Section ① retitled: "GX Score Breakdown (Research Ecosystem Health)"

New primary section:
  ⓪ R1-R8 Evolution Engine — Backbone Status
     (inserted before all other sections)

=======================================================================
CORRECTION 5 — knowledge_base.json MIGRATED
=======================================================================
File: knowledge_base.json
Status: DONE

schema_version bumped: 1 → 2

All 12 non-r1-r8 factor_findings moved to archived_findings:
  wick_rejection    → routes_to: r3_liquidity
  equal_lows        → routes_to: r3_liquidity
  sweep_detected    → routes_to: r3_liquidity
  order_block_present → routes_to: r2_ob
  stopping_volume   → routes_to: r8_demand
  hvn_hit           → routes_to: r8_demand
  htf_higher_high   → routes_to: r4_htf
  htf_hh_and_hl     → routes_to: r4_htf
  rsi_divergence    → routes_to: r7_div
  macd_divergence   → routes_to: r7_div
  system_mfe40_gate → routes_to: null (promotion gate, not r-factor)
  test_factor_T4    → routes_to: null (test entry)

Each archived entry carries:
  routes_to      — the parent r-factor (if applicable)
  archive_reason — human-readable explanation
  archived_at    — timestamp

factor_findings now contains ONLY the 8 r1-r8 factors:
  r1_price, r2_ob, r3_liquidity, r4_htf,
  r5_avwap, r6_macd, r7_div, r8_demand

=======================================================================
CORRECTION 6 — knowledge_base.py ENFORCES R1-R8
=======================================================================
File: knowledge_base.py
Status: IMPLEMENTED

Added constants:
  R1_R8_FACTORS     — set of 8 valid backbone factor column names
  SUBFACTOR_PARENT  — maps sub-signal names to parent r-factor

Updated record_factor():
  - r1-r8 factors → stored in factor_findings (unchanged)
  - known sub-signals → auto-archived in archived_findings with
    routes_to pointing to parent r-factor + warning log
  - unknown factors → auto-archived with archive_reason explaining
    Constitution constraint + warning log

Added record_subfactor_for_parent():
  - Labs that discover a sub-signal improvement call this instead
  - Routes the finding to the parent r-factor's finding record
  - Only updates parent if metrics actually improve

=======================================================================
SUMMARY
=======================================================================
Files changed:
  gx_learning_layer.py  — +280 lines (R1-R8 engine, bug fix, UI)
  knowledge_base.py     — +55 lines (R1-R8 enforcement)
  knowledge_base.json   — schema v2, 12 findings archived

Syntax check: PASS (python3 -m py_compile)

Constitution compliance after corrections:
  ✓ Every recommendation tagged with target_factor
  ✓ Hero metric is R1-R8 Evolution Score
  ✓ Factor findings contain only r1-r8
  ✓ Sub-signals archived with parent routing
  ✓ SCORE_MAX matches signal_engine.py weights
  ✓ New record_subfactor_for_parent() method available
