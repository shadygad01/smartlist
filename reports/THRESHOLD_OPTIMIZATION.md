# THRESHOLD OPTIMIZATION REPORT
Generated: 2026-06-17

## Dataset Note
ALL signals in the database already have raw_score >= 40 (the system pre-filters).
The minimum observed raw_score is 40. Gates below 40 cannot be tested on stored data.

## In-Sample Performance by Gate
| Gate | n   | WR    | Exp20  | Exp40  | AvgWin | AvgLoss |
|------|-----|-------|--------|--------|--------|---------|
|   25 | 321 | 0.396 | 0.0481 | 0.1880 | 0.1691 | -0.0311 |
|   30 | 321 | 0.396 | 0.0481 | 0.1880 | 0.1691 | -0.0311 |
|   35 | 321 | 0.396 | 0.0481 | 0.1880 | 0.1691 | -0.0311 |
|   40 | 321 | 0.396 | 0.0481 | 0.1880 | 0.1691 | -0.0311 |
|   45 | 294 | 0.395 | 0.0474 | 0.1871 | 0.1683 | -0.0313 |
|   50 | 266 | 0.398 | 0.0507 | 0.1944 | 0.1717 | -0.0294 |
|   55 | 249 | 0.398 | 0.0508 | 0.1982 | 0.1750 | -0.0312 |
|   60 | 237 | 0.401 | 0.0516 | 0.2039 | 0.1766 | -0.0319 |

## Walk-Forward Validation Results
All 4 splits tested with optimal threshold selected on train, applied to test.

| Split | Test Period   | Best_T | Test_n | Test_WR | Base_WR | Test_Exp | Base_Exp | Delta  |
|-------|---------------|--------|--------|---------|---------|----------|----------|--------|
|     1 | 2025-07 to 09 |     55 |      6 |   0.000 |   0.294 |   0.0291 |   0.0652 | -0.036 |
|     2 | 2025-10 to 12 |     55 |      7 |   0.429 |   0.333 |   0.0091 |   0.0228 | -0.014 |
|     3 | 2026-01 to 03 |     60 |    101 |   0.327 |   0.346 |   0.0175 |   0.0225 | -0.005 |
|     4 | 2026-04 to 05 |     25 |    115 |   0.478 |   0.478 |   0.0826 |   0.0826 | +0.000 |

## Conclusion
**THRESHOLD CHANGE REJECTED — Insufficient Evidence**

- Walk-forward shows threshold optimization DEGRADES out-of-sample performance in 3 of 4 periods
- The optimal threshold varies wildly by period (55 in splits 1-2, 60 in split 3, 25 in split 4)
- This is classic overfitting: train-optimized gate does not generalize
- Score is essentially uncorrelated with r20d (point-biserial r=0.0213, p=0.7042)
- Higher gates reduce sample size without improving quality

## Current Gate Assessment
- System gate: 35 (whitelist) or 40 (normal stocks)
- This is already conservative — scores range 40-95 in practice
- No evidence that a higher gate improves expected returns out-of-sample
- **Keep current gate unchanged**
