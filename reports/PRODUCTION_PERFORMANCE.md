# PRODUCTION_PERFORMANCE
*Generated: 2026-06-17 | Authority Mode Production Audit*

---

## Section 1: Signal Volume (2026-01-01 to 2026-06-17)

| Signal Type | Count | % of Total |
|---|---|---|
| Strong Buy | 217 | 92.3% |
| Wait | 11 | 4.7% |
| Early Buy | 4 | 1.7% |
| Buy | 3 | 1.3% |
| **Total** | **235** | **100%** |

Buy-family signals (Strong Buy + Buy + Early Buy): 224 (95.3%)

---

## Section 2: Outcome Coverage

- Total BUY signals: 224
- With r20d outcome: 222 (99.1%)
- Pending (r20d=NULL): 2 (both HRHO.CA, recent entries)

---

## Section 3: Core Return Metrics (r20d basis, threshold 7%)

| Metric | Value |
|---|---|
| Win Rate (r20d > 7%) | **40.8%** (89/218 with outcomes) |
| Loss Rate (r20d <= 0%) | 36.5% (80/218) |
| Breakeven (0-7%) | 22.6% (49/218) |
| Avg Win (r20d) | **+18.1%** |
| Avg Non-Win (r20d) | **-3.6%** |
| Expectancy (r20d) | **+5.27%** |
| Median r20d | +4.3% |
| Mean r20d | +5.3% |
| Std r20d | 13.6% |
| Min r20d | -19.9% |
| Max r20d | +66.3% |
| Sharpe-proxy (mean/std) | 0.39 |

---

## Section 4: Extended Horizon Returns

| Horizon | n | WR (>7%) | Mean Return | Median | Max MFE |
|---|---|---|---|---|---|
| r10d | 218 | 31.5% | +3.1% | +2.2% | — |
| r20d | 218 | 40.8% | +5.3% | +4.3% | — |
| r40d | 136 | 55.1% | +11.6% | +10.5% | +20.8% (MFE) |
| r90d | 5 | 80.0% | +20.1% | +11.5% | — |
| Peak 1Y | 218 | — | +22.2% | +15.2% | +91.7% |

**Hold-duration improvement**: WR jumps from 31.5% at 10 days to 55.1% at 40 days. The scanner identifies entries that need time to develop — the 20-day window captures only partial moves.

---

## Section 5: Performance by Signal Type (r20d)

| Signal Type | n | WR >7% | Mean r20d | Median r20d |
|---|---|---|---|---|
| Strong Buy | 217 | 41.0% | +5.3% | +4.5% |
| Buy | 1 | 0.0% | +2.8% | +2.8% |
| Early Buy | 4 | 75.0% | +10.6% | +11.7% |

Note: "Early Buy" (n=4) shows highest WR but tiny sample. "Buy" (n=1) insufficient.

---

## Section 6: Performance by adj_score Band (r20d)

| adj_score | n | WR >7% | Mean r20d | Note |
|---|---|---|---|---|
| 35-54 | 7 | 14.3% | -2.4% | Below Strong Buy threshold |
| 55-69 | 89 | 44.9% | +6.4% | Best performing band |
| 70-84 | 101 | 38.6% | +4.4% | Largest group, underperforms lower scores |
| 85-100 | 20 | 45.0% | +7.6% | Best absolute return, good WR |

**Non-monotonic adj_score relationship**: adj 55-69 outperforms adj 70-84 by +6.3% WR. Higher scores do not predict better outcomes. Pearson r(adj_score, r20d) = -0.02.

---

## Section 7: Monthly Performance (Market Regime Effect)

| Month | n | WR >7% | Mean r20d | Regime |
|---|---|---|---|---|
| 2026-01 | 2 | 50.0% | +10.9% | — |
| 2026-02 | 63 | 19.1% | -2.6% | Losing month |
| 2026-03 | 38 | 55.3% | +9.0% | Winning month |
| 2026-04 | 76 | 61.8% | +11.7% | Best month |
| 2026-05 | 39 | 20.5% | +1.6% | Losing month |
| 2026-06 | 2 | 0.0% | N/A | Pending |

**Key insight**: WR swings from 19% (February) to 62% (April) — a 43-point range driven entirely by market regime. The scanner fires 63 signals in February (a losing month) and 76 in April (best month). No regime filtering is applied.

---

## Section 8: BQ Classification Distribution

| Classification | Count | % |
|---|---|---|
| Huge Winner (r20d >= 20%) | 46 | 20.7% |
| Winner (r20d 7-20%) | 43 | 19.4% |
| Neutral (r20d 0-7%) | 49 | 22.1% |
| Loser (r20d -10 to 0%) | 57 | 25.7% |
| Major Loser (r20d < -10%) | 25 | 11.3% |

- Combined winners: 89/222 (40.1%)
- Combined losers: 82/222 (36.9%)

---

## Section 9: Days to 7% Target

- Signals reaching 7%: 149/220 (67.7%)
- Mean days to 7%: 7.0 days
- Median days to 7%: 5.0 days
- < 5 days: 76 signals (51.0% of achievers)
- < 10 days: 127 signals (85.2% of achievers)
- < 20 days: 148 signals (99.3% of achievers)

---

## Section 10: Open Positions Status (as of 2026-06-17)

10 open positions in `open_positions.json`, 15 in DB-backed position tracking:

| Symbol | Entry Date | Entry Px | Score | Fib Level |
|---|---|---|---|---|
| TMGH.CA | 2026-03-16 | 73.81 | 54 | L2 → L4 hit (61.8% fib) |
| EAST.CA | 2026-01-01 | 37.10 | 67 | L0 → L2 hit (38.2% fib) |
| EMFD.CA | 2026-01-28 | 9.05 | 39 | L2 target 12.51 |
| PHDC.CA | 2026-03-16 | 8.20 | 36 | L5 target 16.40 |
| ORHD.CA | 2026-03-04 | 23.60 | 50 | L5 target 47.20 |
| EFID.CA | 2026-04-02 | 25.05 | 50 | L1 hit → L2 pending |
| HRHO.CA | 2026-01-01 | 24.92 | 64 | L0 target 27.91 |
| JUFO.CA | 2026-03-31 | 24.27 | 41 | L2 target 33.54 |
| BTFH.CA | 2026-03-03 | 2.92 | 60 | L0 target 3.27 |
| GBCO.CA | 2026-03-04 | 26.84 | 51 | L0 target 30.06 |

Positions history tracks 14 position updates through 2026-06-05; highlights:
- ORAS: reached L4 (61.8% fib), still open
- EBANK: reached L3 (50% fib) at 62.88
- COMI: reached L3 (50% fib) at 52.67
- EGAL: reached L3 (50% fib) at 8.03
- ETEL: reached L3 (50% fib) at 3.38
- ABUK: reached L2 (38.2%) at 40.17

---

## Section 11: Top and Bottom Performers

**Top 5 (r20d)**:
1. PHDC.CA (2026-04-08): adj=79 → r20d=+66.3%
2. PHDC.CA (2026-04-15): adj=86 → r20d=+56.5%
3. PHDC.CA (2026-04-30): adj=66 → r20d=+40.5%
4. ABUK.CA (2026-02-22): adj=66 → r20d=+40.3%
5. CCAP.CA (2026-04-21): adj=66 → r20d=+36.5%

**Bottom 5 (r20d)**:
1. EFIH.CA (2026-02-18): adj=73 → r20d=-19.9%
2. GBCO.CA (2026-02-15): adj=68 → r20d=-19.9%
3. GBCO.CA (2026-02-18): adj=75 → r20d=-19.7%
4. ETEL.CA (2026-02-16): adj=95 → r20d=-18.2%
5. ABUK.CA (2026-05-17): adj=0 → r20d=-17.5%

Note: ETEL.CA with adj=95 (highest possible Strong Buy) returned -18.2% — reinforcing that score does not predict outcomes.

---

## Section 12: Summary Statistics

| Metric | Value | Quality |
|---|---|---|
| Win Rate (20d) | 40.8% | Moderate |
| Expectancy (20d) | +5.27% per signal | Positive |
| Avg Win / Avg Loss | 18.1% / -3.6% | 5.0:1 ratio |
| Signals per month (2026) | ~38 | High volume |
| Regime sensitivity | 43 ppt WR swing | HIGH risk |
| Score predictive power | r = -0.02 | NONE |
| Hold-to-40d WR | 55.1% | Strong |
| % signals with outcomes | 99.1% | Complete coverage |
