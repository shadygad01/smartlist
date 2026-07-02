# RESEARCH_ROI_REPORT
*Generated: 2026-06-17 | Authority Mode Production Audit*

---

## Config Files Status

| File | Last Modified | Notes |
|---|---|---|
| config/weights.json | 2026-06-15 | 8 promotions total (deployment_log) |
| learned_weights.json | 2026-06-16 | Pattern engine internal; not in SMC path |
| smc_rl_weights.json | 2026-06-16 | RL-optimized; NOT connected to production |

**config/weights.json note**: Comment inside states "Do not edit manually — use production_promoter.py to update." The current weights diverge significantly from both original and RL-optimized weights (see WEIGHT_IMPACT_REPORT).

---

## File-by-File ROI Assessment

### ranking_engine.py
| Attribute | Value |
|---|---|
| Writes to | Nothing (pure read from egx_research.db → signals + bottom_quality) |
| Imported in main.py | YES — lazy import inside analyze() at `main.py:764` |
| Affects adj_score | YES — directly sets stock_mult via `_expectancy_to_mult(expectancy)` |
| Affects signal count | YES — stock_mult < 1.0 can push adj_score below entry gate |
| Operational 2026 | Only June 2026 (2 signals with non-default stock_mult in evaluated period) |
| **ROI Classification** | **HIGH (design), LOW (current utilization)** |

Evidence: In June 2026, HRHO.CA (stock_mult=0.88) has raw_score=50 but adj_score=44 — the ranking penalty demoted it from Strong Buy to Wait. OIH.CA (stock_mult=1.15) has raw_score=43, adj_score=49 — slight boost. For Jan–May 2026 (218 signals), ranking_engine was silent (all stock_mult=NULL). The ranking engine has the right architecture but was not feeding data for 95% of the evaluation period.

---

### production_promoter.py
| Attribute | Value |
|---|---|
| Writes to | config/weights.json (ONLY module that does this) |
| Imported in main.py | NO — called by continuous_learning.py only |
| Affects adj_score | YES — when new weights take effect on process restart |
| Total promotions | 8 (deployment_log table) |
| **ROI Classification** | **HIGH (critical path)** |

config/weights.json represents the output of 8 learning cycles. The current weights (last updated 2026-06-15) reflect the optimization history. Key issue: there is no hot-reload — promoted weights require process restart to activate.

---

### continuous_learning.py
| Attribute | Value |
|---|---|
| Writes to | gx_learning_memory.json; orchestrates production_promoter |
| Imported in main.py | YES — lazy import at `main.py:2146` post-scan |
| Affects adj_score | INDIRECTLY (via promotion chain on process restart) |
| Trigger conditions | >= 10 new outcomes AND > 24h since last cycle |
| **ROI Classification** | **MEDIUM** |

The module is live in the production run path but its effect requires process restart. `gx_learning_memory.json` stores promotion history. The 8 deployment_log entries confirm the pipeline has executed successfully 8 times — the system has genuinely updated weights based on outcomes.

---

### optimization_engine.py
| Attribute | Value |
|---|---|
| Writes to | optimization_history table (5 rows) |
| Imported in main.py | NO |
| Affects adj_score | INDIRECTLY via CL chain |
| **ROI Classification** | **MEDIUM** |

Orchestrates weight optimization methods. Of the three modes it can run (expectancy_gradient, walk_forward, rl_gradient), only expectancy_gradient has a path to production (via weight_optimizer → production_promoter). Walk-forward and RL gradient results are computed but never promoted.

---

### validation_engine.py
| Attribute | Value |
|---|---|
| Writes to | validation_runs table (24 rows) |
| Imported in main.py | NO |
| Affects adj_score | NO (gates promotion only) |
| Gate thresholds | oos_wr >= 0.65, oos_expectancy >= 0.10 |
| **ROI Classification** | **MEDIUM (risk management)** |

24 validation runs in DB suggests meaningful use. The strict thresholds (65% WR required for promotion) explain why only 8 of 24 validations led to promotion — 16 were rejected. This is functioning as a risk gate.

---

### weight_optimizer.py
| Attribute | Value |
|---|---|
| Writes to | optimization_results.json, HTML reports |
| Imported in main.py | NO |
| Affects adj_score | INDIRECTLY via CL → optimization → promoter chain |
| **ROI Classification** | **MEDIUM** |

Produces the actual weight vectors that eventually reach config/weights.json. The current config weights are the output of this module's last approved optimization.

---

### pattern_engine.py
| Attribute | Value |
|---|---|
| Writes to | learned_weights.json (pattern-internal weights) |
| Imported in main.py | YES — `main.py:19,2054,2114,2171` |
| Affects adj_score | NO (pattern_score is display only) |
| Affects BUY gate | NO |
| **ROI Classification** | **LOW (for entry decisions)** |

Pattern scores are computed and stored in DB but do not gate entry. learned_weights.json affects only the pattern_score calculation, not any SMC weight. The module is active but its output is informational only.

---

### research_report.py
| Attribute | Value |
|---|---|
| Writes to | research_results.json, HTML email, report_log table |
| Imported in main.py | YES — `main.py:29` |
| Affects adj_score | NO |
| **ROI Classification** | **LOW (for trading alpha)** |

Value is informational/communication only. Generates weekly HTML email with BQ metrics. Does not feed back into scoring.

---

### walk_forward_backtester.py
| Attribute | Value |
|---|---|
| Writes to | walk_forward_state.json, HTML reports |
| Imported in main.py | NO |
| Affects adj_score | NO |
| walk_forward_state.json readers | gx_research_memory.py, cache_orchestrator.py only |
| **ROI Classification** | **LOW (disconnected)** |

Walk-forward weights are computed but never promoted to config/weights.json. The pipeline stops at optimization_engine and does not route walk-forward results through production_promoter.

---

### smc_rl_optimizer.py
| Attribute | Value |
|---|---|
| Writes to | smc_rl_weights.json |
| Imported in main.py | NO |
| Affects adj_score | NO |
| smc_rl_weights.json readers | gx_research_memory.py, cache_orchestrator.py only |
| RL weights vs config | W_PRICE: 30.6 vs 7.7 (current), W_DZ: 15.1 vs 29.4 |
| **ROI Classification** | **LOW (disconnected)** |

The RL optimizer produced weights that are significantly more conservative and closer to the original than what's in production. These findings are being silently discarded.

---

### historical_backtest.py
| Attribute | Value |
|---|---|
| Writes to | hist_signals table, historical_backtest_results.json |
| Imported in main.py | NO |
| Affects adj_score | INDIRECTLY via hist_signals → ranking_engine.compute_expectancy() |
| **ROI Classification** | **LOW-MEDIUM (data bootstrapping only)** |

If ranking_engine needs sample_n >= 30 to use expectancy-based stock_mult (rather than tier-based fallback), then historical_backtest is needed to bootstrap the DB with enough historical signals. Once the DB is populated, this module's work is done.

---

### decision_engine.py
| Attribute | Value |
|---|---|
| Writes to | decision_engine_results.json |
| Imported in main.py | NO |
| Affects adj_score | NO |
| **ROI Classification** | **ZERO (dead)** |

Never in production path. Output not consumed by anything in main.py chain.

---

### adaptive_learning.py
| Attribute | Value |
|---|---|
| Writes to | adaptive_learning_results.json, HTML |
| Imported in main.py | NO |
| Affects adj_score | NO |
| **ROI Classification** | **ZERO (dead)** |

---

## ROI Summary Table

| Module | ROI Class | Lives in main.py | Affects Score | Priority |
|---|---|---|---|---|
| ranking_engine.py | HIGH (design) | YES | YES (stock_mult) | Fix utilization |
| production_promoter.py | HIGH | NO (via CL) | YES (deferred) | Fix hot-reload |
| continuous_learning.py | MEDIUM | YES | YES (deferred) | Keep, fix reload |
| optimization_engine.py | MEDIUM | NO | YES (deferred) | Keep |
| validation_engine.py | MEDIUM | NO | Gate | Keep |
| weight_optimizer.py | MEDIUM | NO | YES (deferred) | Keep |
| pattern_engine.py | LOW | YES | NO | Display-only |
| research_report.py | LOW | YES | NO | Communication |
| walk_forward_backtester.py | LOW | NO | NO | Wire to promoter |
| smc_rl_optimizer.py | LOW | NO | NO | Wire to promoter |
| historical_backtest.py | LOW | NO | Indirect | One-time bootstrap |
| decision_engine.py | ZERO | NO | NO | Dead code |
| adaptive_learning.py | ZERO | NO | NO | Dead code |

---

## Three Critical ROI Gaps

1. **Hot-reload gap**: `production_promoter.promote()` writes `config/weights.json` but `main.py` never calls `signal_engine.reload_weights()`. 8 successful promotions had zero immediate effect.

2. **RL/walk-forward disconnection**: `smc_rl_optimizer` recommends reverting to near-original weights (W_PRICE=30.6) but these are silently discarded. Current production weights diverge significantly from RL-optimized.

3. **ranking_engine non-operational**: 208/220 2026 BUY signals had NULL stock_mult — the ranking system that should differentiate signal quality by stock history was not running for 94.5% of the year.
