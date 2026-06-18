# ENTRY_ENGINE_MAP
*Generated: 2026-06-17 | Authority Mode Production Audit*

---

## 1. BUY Signal Classification Thresholds

Source: `main.py:508-513` (`sig_info()`), `main.py:787-803` (classification in `analyze()`)

| Signal Class | adj_score Range | Entry Gate (WHITELIST) | Entry Gate (Normal) |
|---|---|---|---|
| Institutional Buy | >= 85 | >= 35 | >= 40 |
| Very Strong Buy | 70–84 | >= 35 | >= 40 |
| Strong Buy | 55–69 | >= 35 | >= 40 |
| Buy | 40–54 | >= 35 | >= 40 |
| Wait | adj < gate, price_ok=False, OR raw < 35 | — | — |
| Skip | raw_score < 35 | — | — |

Note from DB: In practice, 2026 production output is 217/220 (98.6%) "Strong Buy" (adj 55-84) and 3/220 "Buy". Zero IB or VSB signals triggered in Jan-Jun 2026.

---

## 2. Pre-Gate: Discount Zone Check

**`main.py:693-700`**: If `cur >= eq` (price at or above the 50% equilibrium of SMC range), all r1..r8 are forced to zero and signal is hard-skipped. The full `score_signal()` path is only entered when `cur < eq`. This gate runs before any scoring.

---

## 3. raw_score Computation

**`signal_engine.py:848`** (inside `score_signal()`):
```
raw_score = r1 + r2 + r3 + r4 + r5 + r6 + r7 + r8
```

Component maximums (current config weights from `config/weights.json` last updated 2026-06-15):
- r1_price: max 7.69 pts (continuous, position in SMC range)
- r2_ob: max 14.47 pts (Order Block proximity × quality)
- r3_liquidity: max 15.24 pts (Sweep & Reverse detection)
- r4_htf: max 0.70 pts (Higher Timeframe structure)
- r5_avwap: max 7.10 pts (AVWAP position)
- r6_macd: max 14.87 pts (MACD confluence)
- r7_div: max 10.58 pts (RSI/MACD divergence)
- r8_demand: max 29.36 pts (Demand Zone: SV+HVN)

Total max = 100.00

**Original weights** (pre-optimization, still in `smc_rl_weights.json` learned result): W_PRICE=30, W_OB=10, W_LIQ=20, W_HTF=10, W_AVWAP=8, W_MACD=4, W_DIV=3, W_DZ=15

The current config represents a major rebalancing: W_DZ jumped from 15→29.4, W_MACD from 4→14.9, W_DIV from 3→10.6, while W_PRICE dropped from 30→7.7 and W_HTF from 10→0.7.

---

## 4. adj_score Computation

**`main.py:777`**:
```python
score = min(int(round(total * stock_mult * ctx_mult)), 100)
```

- `total` = raw_score (capped at 100 but sum already bounded)
- `stock_mult` = from `ranking_engine.compute_expectancy()` if sample_n >= 30, else from `STOCK_QUALITY` dict
  - Range: 0.80–1.20 (expectancy-based) or 0.88–1.15 (tier-based fallback)
- `ctx_mult` = context multiplier
  - Ramadan: 0.70
  - CBE window: 1.30
  - Neutral: 1.00
  - Both: product

**Critical finding**: For 208/220 (94.5%) of 2026 BUY signals (Jan–May), `stock_mult` and `ctx_mult` were NULL in the DB, meaning `adj_score = raw_score` for those signals. The multiplier system became operational only in June 2026 (13 signals with multipliers set).

---

## 5. PRICE_GATE Logic

**`main.py:505-506`**:
```python
PRICE_GATE_NORMAL    = PRICE_GATE_FRAC_NORMAL    * W_PRICE  # 0.55 × 7.69 ≈ 4.2
PRICE_GATE_WHITELIST = PRICE_GATE_FRAC_WHITELIST * W_PRICE  # 0.50 × 7.69 ≈ 3.8
```

Fractions from `config/gates_config.json` (0.55 normal, 0.50 whitelist). With current W_PRICE=7.69, the gates are much lower than with original W_PRICE=30 (which gave 16.5 / 15.0).

**`main.py:746,749`**:
```python
PRICE_GATE = PRICE_GATE_WHITELIST if symbol in WHITELIST else PRICE_GATE_NORMAL
price_ok = (r1 >= PRICE_GATE)
```

DB evidence: In June 2026 signals, r1 values range 1–15 with price_gate stored as 15 or 16 — this suggests these were computed with OLD weights (W_PRICE=30). The stored `price_gate` values in the DB reflect the live weights at time of scoring.

**LIQ_GATE**: `liq_ok = (r3 >= W_LIQ)` — used for display only, never blocks entry (`main.py:747,750,801-803`).

---

## 6. Skip / Wait Classification Path

**`main.py:787-803`** (simplified):
```python
if total < 35:
    signal = "Skip"
elif not price_ok:
    signal = "Wait"  # raw >= 35 but price not in deep discount
elif score < _entry_score_gate:
    signal = "Wait"  # adj_score too low after multipliers
else:
    label = sig_info(score)  # Buy / Strong Buy / VSB / IB
    _register_new_positions(symbol, label, ...)
```

Note: `_entry_score_gate` = 35 for WHITELIST symbols, 40 for others (`main.py:807`).

---

## 7. Entry Price Source

**`main.py:426-485`** (`download_data()`):
- Historical OHLCV: `yfinance.Ticker.history(period="6mo")`
- Fallback: Yahoo Finance chart API (`query1.finance.yahoo.com/v8/finance/chart`)
- **Live patch**: `_patch_today_from_tv()` at `main.py:397-423` replaces the final bar with real-time data from `https://scanner.tradingview.com/egypt/scan` (TradingView EGX scanner)

Entry price recorded in `add_position()` (`main.py:2033`): `round(cur, 2)` where `cur = float(df["Close"].iloc[-1])` after the TradingView patch.

Source tag: `"yfinance + TradingView patch"` (`main.py:678`).

---

## 8. stock_mult Path

**`main.py:762-774`**:
```python
try:
    import ranking_engine as _re
    _exp = _re.compute_expectancy(symbol)
    if _exp.sample_n >= 30:
        stock_mult = _re._expectancy_to_mult(_exp.expectancy)   # 0.80–1.20
    else:
        stock_mult = STOCK_QUALITY.get(symbol, 1.0)             # 0.88–1.15
except Exception:
    stock_mult = STOCK_QUALITY.get(symbol, 1.0)
```

`ranking_engine._expectancy_to_mult()` (`ranking_engine.py:50-54`): maps historical r20d expectancy from `egx_research.db → bottom_quality.r20d` to [0.80, 1.20].

`STOCK_QUALITY` dict fallback:
- Tier A (COMI, ETEL, TMGH, etc.): 1.15
- Tier B (EAST, OIH, etc.): 1.07
- Tier D (HRHO, EAST, etc.): 0.88
- Default: 1.00

**Range impact on adj_score**: A Tier A stock (1.15) vs Tier D (0.88) on the same raw_score of 50: 57 vs 44. This can shift a "Wait" to "Strong Buy" or demote "Strong Buy" to "Wait".

---

## 9. Research Effect on Live Path

| Component | Called From | Effect on BUY/Skip Decision |
|---|---|---|
| `ranking_engine.py` | `main.py:764` (inside `analyze()`) | DIRECT — sets stock_mult → adj_score |
| `pattern_engine.py` | `main.py:19,824` (inside `analyze()`) | NONE — pattern_data is display/email only |
| `continuous_learning.py` | `main.py:2146` (post-scan) | DEFERRED — updates `config/weights.json` but needs process restart to take effect; `main.py` never calls `signal_engine.reload_weights()` |
| `research_report.py` | `main.py:2142` (post-scan) | NONE — HTML email only |

---

## 10. _register_new_positions Path

**`main.py:2018-2040`**: Called only when `signal in BUY_SIGNALS`. Reads `open_positions.json`, deduplicates by symbol, sets `entry_price = cur` (TradingView-patched close), `target = fib_levels[1]` (first Fibonacci extension). Writes `open_positions.json`.

Current open positions: 10 symbols (TMGH.CA, EAST.CA, EMFD.CA, PHDC.CA, ORHD.CA, EFID.CA, HRHO.CA, JUFO.CA, BTFH.CA, GBCO.CA).
