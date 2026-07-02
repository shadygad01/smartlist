R1-R8 VIOLATION REPORT
======================
Date: 2026-06-19
Authority: docs/LEARNING_LABS_CONSTITUTION.md + CLAUDE_PROJECT_RULES.md

=======================================================================
VIOLATION 1 — CRITICAL: SCORE_MAX MISMATCH IN CONTEXT INTELLIGENCE
=======================================================================
File: gx_learning_layer.py:742-743
Type: Data corruption — wrong max weights used in win/loss decomposition

Hardcoded wrong values:
  r3_liquidity: 10  (actual: 20)  ← half the real weight
  r4_htf:       20  (actual: 10)  ← double the real weight
  r5_avwap:     10  (actual: 8)
  r6_macd:      10  (actual: 4)   ← 2.5× the real weight
  r7_div:       5   (actual: 3)
  r8_demand:    5   (actual: 15)  ← one-third the real weight

Impact: Section ⑪ "Score Contribution Decomposition" displayed wrong
percentages for r3, r4, r5, r6, r7, r8 in every run. Decisions based
on this decomposition were systematically biased.

=======================================================================
VIOLATION 2 — CRITICAL: LEARNING ENGINE NOT MEASURING R1-R8 EVOLUTION
=======================================================================
File: gx_learning_layer.py
Constitution Rule: "The Learning Labs are an Evolution Engine.
Their sole purpose is: Making r1-r8 better over time."

Actual behavior: The GX Learning Score measured 5 abstract dimensions:
  - Research Coherence (25%) — cross-module agreement count
  - Performance Quality (25%) — backtest win rate / profit factor / CAGR
  - OOS Robustness (20%) — walk-forward survival rate
  - System Health (15%) — adaptive health score
  - Knowledge Retention (15%) — run count × 8 + history depth × 3

None of these dimensions answer: "Is r1 better today than yesterday?"
None tracked: which r-factor each recommendation targets.
None tracked: how many validated improvements exist per r-factor.
None tracked: which r-factors lack evidence.

The "GX Score" measured the health of the research ecosystem,
NOT the evolution of the backbone.

=======================================================================
VIOLATION 3 — CRITICAL: RECOMMENDATIONS HAVE NO TARGET FACTOR
=======================================================================
File: gx_learning_layer.py (_extract_recommendations)
Constitution Rule: "Every promoted discovery must clearly identify:
  * target factor
  * expected improvement
  * supporting evidence
If no target factor exists: promotion forbidden."

Actual behavior: All extracted recommendations contained:
  id, source, name, description, expected_delta_ret, confidence,
  wf_consistent, overfitted, supporting

Missing field: target_factor
Missing field: improvement_type (refinement / replacement /
  measurement / weight_optimization / interaction)

This means the system could never answer the mandatory Constitution
question: "Which existing factor does this improve?"

=======================================================================
VIOLATION 4 — CRITICAL: knowledge_base.json STORES NON-R1-R8 FACTORS
=======================================================================
File: knowledge_base.json → factor_findings
Constitution Rule: "Every active asset must target r1-r8."
Rule 12: "If no factor is improved: archive the asset."

Active factor_findings that are NOT r1-r8 backbone factors:

  wick_rejection       → sub-signal of r3_liquidity (ARCHIVED)
  equal_lows           → sub-signal of r3_liquidity (ARCHIVED)
  sweep_detected       → sub-signal of r3_liquidity (ARCHIVED)
  order_block_present  → sub-signal of r2_ob        (ARCHIVED)
  stopping_volume      → sub-signal of r8_demand     (ARCHIVED)
  hvn_hit              → sub-signal of r8_demand     (ARCHIVED)
  htf_higher_high      → sub-signal of r4_htf        (ARCHIVED)
  htf_hh_and_hl        → sub-signal of r4_htf        (ARCHIVED)
  rsi_divergence       → sub-signal of r7_div        (ARCHIVED)
  macd_divergence      → sub-signal of r7_div        (ARCHIVED)
  system_mfe40_gate    → promotion gate, not r1-r8   (ARCHIVED)
  test_factor_T4       → test entry                  (ARCHIVED)

These sub-signals were tracked as independent factors. Each finding
should have been routed to improve the parent r-factor's measurement,
weight, or definition — not stored as a competing standalone asset.

=======================================================================
VIOLATION 5 — MAJOR: knowledge_base.py ACCEPTS ANY FACTOR NAME
=======================================================================
File: knowledge_base.py → record_factor()
Rule 6: "Every active asset must target r1-r8."

record_factor() accepted any string as a factor name with no validation.
This enabled the proliferation of sub-factors as independent assets.

=======================================================================
VIOLATION 6 — MODERATE: DASHBOARD HERO METRIC WAS NOT R1-R8
=======================================================================
File: gx_learning_layer.py → build_html()

The primary hero circle displayed "GX LEARNING SCORE" — the abstract
ecosystem health metric. The R1-R8 Evolution Score was not computed
at all. A user reading the dashboard could not determine the status
of any individual r-factor.

=======================================================================
VIOLATION 7 — MODERATE: EDGE DISCOVERY RESULTS NOT R1-R8 MAPPED
=======================================================================
File: edge_discovery_results.json (45MB)

Edges stored as raw flag combinations (e.g. "r1>=15 AND sv_hit AND sweep")
without mapping each rule to which r-factor it could improve. Per
Constitution: "Can this improve r1? ... r8?" must be asked for every
discovery. The edge engine asked "is this statistically significant?"
but not "which r-factor does this improve?"

=======================================================================
SUMMARY COUNTS
=======================================================================
Critical violations:  4  (SCORE_MAX, GX Score, no target_factor, KB non-r1-r8)
Major violations:     1  (KB accepts any factor name)
Moderate violations:  2  (hero metric, edge discovery)
Total:                7
