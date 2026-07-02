# Constitutional Signal Engine — Version 1.0

**Status:** FROZEN — Production Baseline  
**Frozen:** 2026-06-21  
**Branch:** `claude/amazing-shannon-7b0je3`  
**Commit:** `eb15b1b1a6dc930ed238bd9efa018af95b5d4f3f`  
**Engine SHA-256:** `34de8666dd4afda777f03e8b542b42efa82c61056e9a982fa4438215789167d9`  
**Universe SHA-256:** `609c46c998f8c32acf0db519b93af8a9a6abe8598003e0db8c272e2866003dc6`

---

## UNIVERSE

**Source:** `config/scanner_config.py` — `get_constitutional_universe()`  
**Count:** 27 symbols (exact)  
**Symbols:**

```
ABUK.CA  ADIB.CA  ARCC.CA  BTFH.CA  CCAP.CA  COMI.CA  EAST.CA
EFID.CA  EFIH.CA  EGAL.CA  EMFD.CA  ETEL.CA  FWRY.CA  GBCO.CA
HELI.CA  HRHO.CA  ISPH.CA  JUFO.CA  MCQE.CA  OIH.CA   ORAS.CA
ORHD.CA  ORWE.CA  PHDC.CA  RAYA.CA  RMDA.CA  TMGH.CA
```

**Rule:** Any module requiring a symbol universe MUST import and call
`get_constitutional_universe()`. Hardcoded `.CA` lists in any file other
than `config/scanner_config.py` are unconstitutional.

---

## ARCHITECTURE

### Execution Order

```
price_data (OHLCV DataFrame, point-in-time)
    │
    ▼
swings(hist, lb=80)
    → hi, lo, eq, buy_hi, sell_lo
    │
    ▼
R1  Constitutional Hard Gate
    close >= eq  → REJECT (no score, no ranking)
    close <  eq  → PASS
    │
    ▼
R2  Discount Quality         [weight: 0.15]
R3  Discount Residency       [weight: 0.10]
R4  Base Formation           [weight: 0.30]  ← highest weight
R5  Low Protection           [weight: 0.20]
R6  Recovery                 [weight: 0.15]
R7  MACD Phase               [multiplier]
R8  Volume Behaviour         [weight: 0.10]
    │
    ▼
compute_final_score(r1..r8, r1_state)
    │
    ▼
signal dict → discount_signals table
```

### Discount Zone Geometry (LuxAlgo / swings)

```
lb = 80 bars
hi      = max(High, lb bars)
lo      = min(Low,  lb bars)
rng     = hi - lo
eq      = lo + rng * 0.50   ← 50th percentile — EQ gate
buy_hi  = lo + rng * 0.15   ← top of buy zone
sell_lo = lo + rng * 0.85   ← bottom of sell zone
```

---

## STATION DEFINITIONS

### R1 — Discount Context (Hard Gate)

- **Input:** `close, eq, discount_bottom (lo), premium_top (hi)`
- **Source:** All computed from OHLCV via `swings()`
- **Rule:** `close >= eq` → reject immediately, return `None`
- **Score range:** 60–100 (inside discount), 30–60 (emerging), 0 (premium/extended)
- **Ranking contribution:** ZERO — gate only
- **Lookahead:** None

### R2 — Discount Quality

- **Input:** `close, eq, true_lo (lo), true_hi (hi)`
- **Measures:** proximity to bottom (50 pts), discount depth (30 pts), upside to EQ (20 pts)
- **Score range:** 0–100
- **Spearman vs MAE:** +0.286*** (strongest entry-quality predictor)

### R3 — Discount Residency

- **Input:** `closes[], eq`
- **Measures:** consecutive bars below EQ (sweet spot: 5–30 bars → 100 pts)
- **Score range:** 0–100
- **Unique values:** 49 (day-count based)
- **Spearman vs MAE:** +0.243***

### R4 — Base Formation (highest weight)

- **Input:** `highs[], lows[], closes[], volumes[]`
- **Measures:** adaptive 20/40/60-bar range compression + ATR compression + base duration
- **Lookback:** Selects window with strongest compression from {20, 40, 60}
- **Duration:** anchored to detected base mid-price band (±7%), not current close
- **Score range:** 0–100
- **Spearman vs MAE:** +0.157***

### R5 — Low Protection

- **Input:** `lows[], closes[]`
- **Measures:** no_new_low (20-bar split) + failed_breakdown (vs 20-bar ATL)
- **Score range:** {0, 60, 70, 100} — 7 discrete values (known binary limitation)
- **Known defects:** D1–D5 documented; repair worsened Spearman — deferred
- **Spearman vs MFE:** -0.174*** (anti-predictive — known)
- **Status:** NO REDESIGN until mandate permits

### R6 — Recovery

- **Input:** `highs[], lows[], closes[]` (choch/bos computed internally)
- **Measures:** pivot-based higher_low (0/25/45 pts) + adaptive recovery_pct + CHOCH/BOS bonus
- **Helpers:** `_find_pivot_lows(context=3)`, `_detect_choch()` (with guard), `_detect_bos()` (with guard)
- **Score range:** 0–100
- **Known issue:** Anti-predictive for MFE (-0.202***) and MAE (-0.136***)
  Early recovery detection correlates with premature entry
- **Status:** NO REDESIGN until mandate permits

### R7 — MACD Phase

- **Input:** `closes[]` → `_compute_macd(with_context=True)` internally
- **Measures:** Continuous surface: location (45%) + curl/slope (35%) + recovery magnitude (20%)
  with overextension gate
- **MACD params:** EMA(12) / EMA(26), signal EMA(9), slope over 5 bars
- **Score range:** 0–100 (continuous, 747 unique values)
- **Lookahead:** None — all computed from closes up to signal date
- **Spearman vs MAE:** +0.106** | vs MFE: +0.081* | vs low_break: -0.089*

### R8 — Volume Behaviour

- **Input:** `volumes[]`
- **Measures:** baseline excludes recent 5 bars; dry-up via recent_5/baseline; expansion via last_3/baseline
- **Score range:** 46–90 (continuous)
- **Spearman:** near-zero on all metrics (low discrimination)

---

## FINAL SCORE FORMULA

```python
def compute_final_score(r1, r2, r3, r4, r5, r6, r7, r8, r1_state):
    if r1_state in ('premium', 'extended', 'unknown'):
        return 0.0
    weighted = (
        r4 * 0.30 +
        r5 * 0.20 +
        r2 * 0.15 +
        r6 * 0.15 +
        r3 * 0.10 +
        r8 * 0.10
    )
    # R7 acts as multiplier, not additive weight
    if r7 < 20:   weighted *= 0.50
    elif r7 < 40: weighted *= 0.75
    r1_mult = 1.0 + (r1 - 60) / 400
    return round(min(100, weighted * r1_mult), 2)
```

**R7 acts as a multiplier (gate), not an additive weight.**  
Weights: R4=30%, R5=20%, R2=15%, R6=15%, R3=10%, R8=10%

---

## VALIDATED PERFORMANCE (Walk-Forward 2026-01-01 to 2026-06-21)

```
Signals               : 782 (23 of 27 symbols triggered)
Manual positions found : 15 / 15
Additional discoveries : 9
Engine avg return      : +26.7%
Manual avg return      : +30.8%
Engine >20% signals    : 11
Manual >20% signals    : 8
Engine >50% signals    : 5
Manual >50% signals    : 4
Engine peak avg        : +36.8%

Ranking quality (Spearman, final_score):
  vs MAE_40     : +0.137***  GOOD (higher score → less adverse excursion)
  vs MFE_40     : -0.049     neutral
  vs low_break  : -0.042     neutral
```

---

## FORBIDDEN MODIFICATIONS

The following changes are forbidden without a new constitutional mandate:

1. **Weight changes** — `compute_final_score()` weights are frozen
2. **Universe changes** — no symbols added or removed without updating `config/scanner_config.py`
3. **R1 gate changes** — the EQ-based hard reject is structural
4. **Station redesign** — R1–R8 logic is frozen; only proven implementation defects may be patched
5. **Lookahead introduction** — no future OHLCV data may be used as station input
6. **ML/optimization** — no weight tuning, no parameter fitting to returns
7. **Hindsight scoring** — outcome metrics (MAE, MFE, peak_return) are measurements only, never inputs
8. **Symbol substitution** — no replacing a universe symbol with a similar one

---

## FUTURE CHANGES POLICY

A change to the Constitutional Engine requires:

1. **Mandate** — explicit authority level (e.g., AUTHORITY: FULL)
2. **Evidence** — Spearman / quartile data proving defect exists
3. **Scope** — defect must be an *implementation* defect, not a *conceptual* preference
4. **Validation** — walk-forward replay before and after, same universe, same date range
5. **No simultaneous weight change** — fixing a station and reweighting in the same mandate is forbidden

Known deferred issues awaiting future mandate:

| Issue | Evidence | Required Action |
|-------|----------|-----------------|
| R5 binary (7 values) | Spearman worsened on all repairs | Larger dataset needed |
| R6 anti-predictive | rho=-0.202*** vs MFE | Redesign or weight change mandate |
| R8 range 46–86 | Low discrimination | Review baseline window |
| Dead functions in engine | No callers | Safe removal (low priority) |

---

## FILE INTEGRITY

```
Engine file       : discount_reversal_engine.py
Engine SHA-256    : 34de8666dd4afda777f03e8b542b42efa82c61056e9a982fa4438215789167d9

Universe source   : config/scanner_config.py
Universe SHA-256  : 609c46c998f8c32acf0db519b93af8a9a6abe8598003e0db8c272e2866003dc6

Git commit        : eb15b1b1a6dc930ed238bd9efa018af95b5d4f3f
Constitution date : 2026-06-21
```

---

## EXECUTION PATH AUDIT (at freeze date)

| File | Universe Source | Verdict |
|------|----------------|---------|
| `discount_reversal_engine.py` | `get_constitutional_universe()` | PASS |
| `backfill_discount_signals.py` | `get_constitutional_universe()` | PASS |
| `main.py` | imports `EGX30_SYMBOLS` from engine (derives from config) | PASS |
| `backtest.py` | `get_constitutional_universe()` | PASS |
| `backtest_regime_aware.py` | `get_constitutional_universe()` | PASS |
| `backfill_signal_log.py` | `get_constitutional_universe()` | PASS |
| `build_history.py` | `get_constitutional_universe()` | PASS |
| `standalone_backtest_script.py` | `get_constitutional_universe()` | PASS |
| `backfill_egx30.py` | `get_constitutional_universe()` | PASS |
| `heatmap.py` | Sector display taxonomy (not execution gate) | NOTE |

All execution paths: **CONSTITUTIONAL**
