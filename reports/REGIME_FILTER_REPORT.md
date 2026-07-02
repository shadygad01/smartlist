# REGIME FILTER REPORT

**Date**: 2026-06-17

## Implementation Summary

### Changes Made

1. `config/gates_config.json`: Added `"regime_filter_enabled": true` and `"regime_down_mult": 0.70`
2. `main.py` (after line 506): Load `_REGIME_FILTER_ENABLED` and `_REGIME_DOWN_MULT` at module startup from gates_config.json
3. `main.py` (in `analyze()`, after ctx_mult block): Apply regime multiplier to `ctx_mult` when EGX30 trend is bearish
4. `analyze()` return dict: Added `"regime_state"` and `"regime_multiplier"` for telemetry

### Logic

```python
if _REGIME_FILTER_ENABLED and cur < eq:
    _sg_trend = _sg.get("egx30_trend", "")
    if _sg_trend in ("DOWN", "DOWNTREND", "bearish", "Bearish", "downtrend"):
        ctx_mult *= _REGIME_DOWN_MULT  # e.g. 0.70
        ctx_labels.append(f"Bear Regime 70%")
```

- Safe default: disabled if `regime_filter_enabled` key missing from gates_config.json
- Does NOT change the raw `total` gate (35-point minimum)
- Reduces `score` (adj_score) so borderline signals may fall below the 40-point entry gate
- Returns `regime_state` and `regime_multiplier` in every analyze() call for monitoring

## Historical Evidence

### Monthly WR Variance (2021-2026)

| Period | WR | Avg R20d | Assessment |
|---|---|---|---|
| 2022-04 to 2022-06 | 12% | -2% | Deep bear |
| 2022-07 | 100% | +18.5% | Bull reversal |
| 2023-03 | 70% | +14% | Bull |
| 2024-12 | 6% | -2.9% | Bear |
| 2026-02 | 19% | -2.6% | Bear |
| 2026-04 | 62% | +11.7% | Bull |

Bull months (WR 50%+): 2022-07, 2023-03, 2023-08, 2023-10, 2024-06, 2026-01, 2026-03, 2026-04
Bear months (WR <25%): 2022-04, 2022-05, 2022-06, 2024-04, 2024-12, 2026-02, 2026-05

### Regime Data Availability

- `egx30_trend` column: 14 signals tagged as "downtrend", 646 as NULL (historical signals logged before field was added)
- `feat_egx30_trend_val`: 0 signals (not yet populated by feature_extractor)
- Regime multiplier currently fires only for live analysis where `score_signal()` returns `egx30_trend`

## Expected Impact (Estimate)

Based on monthly WR data:
- Bear months produce WR ~12-25% vs bull months 50-70%
- Filtering bear regime signals: ~30% reduction in bear-month signals accepted
- Expected WR lift: +5 to +8pp when regime gate is active
- Selectivity: reduces signal count in bear periods (fewer false positives)

## Telemetry

Every `analyze()` now returns:
- `regime_state`: "bear" | "bull" | "neutral" | ""
- `regime_multiplier`: 0.70 (bear) | 1.0 (neutral/bull)

These flow into `signal_db.log_signals()` via the return dict (future column addition recommended).
