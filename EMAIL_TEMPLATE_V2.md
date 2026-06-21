# Email Template V2 — EGX Constitutional Morning Brief

**Created:** 2026-06-21  
**Channel:** HTML Email  
**Subject format:** `EGX Constitutional Morning Brief · {date} — {N} Entr{y/ies}`

---

## Structure

```
┌─────────────────────────────────────────────────────┐
│  HEADER                                              │
│  EGX Constitutional Morning Brief                    │
│  {Weekday, DD Month YYYY · HH:MM} Cairo              │
│  {N constitutional entries · portfolio management}   │
├─────────────────────────────────────────────────────┤
│  DATA STATUS BAR                                     │
│  {N fresh · N prior session}                        │
├─────────────────────────────────────────────────────┤
│  RANKED OPPORTUNITIES                                │
│  Premier Opportunities (#1–#5)                       │
│  Monitored Opportunities (#6–#10)                    │
│  Columns: Rank / Stock / Signal / Rank Score /       │
│           Expectancy / Signal Quality / Δ            │
├─────────────────────────────────────────────────────┤
│  PORTFOLIO POSITIONS — CONSTITUTIONAL TARGETS        │
│  Stock / Entry / Current (P&L) / Target / Date       │
│  Pattern Intelligence badge per position             │
├─────────────────────────────────────────────────────┤
│  SIGNAL CARDS (one per qualifying stock)             │
│  {Company Name} · {ticker} · {sector}                │
│  {Signal label badge}                                │
│  Rank Score | Factor Expectancy | Signal Quality     │
│  Decision Driver (narrative sentence)                │
│  EQ | Buy Zone Top | Sell Zone Floor | AVWAP         │
│  Factor Contribution (table)                         │
│  Entry Strategy — Averaging Plan (zones)             │
│  Pattern Intelligence — Historical Context           │
├─────────────────────────────────────────────────────┤
│  FOOTER                                              │
│  EGX Constitutional Investment Platform              │
│  Research-Driven · Constitutionally Governed         │
└─────────────────────────────────────────────────────┘
```

---

## Signal Badge Colors

| Signal | Badge Text | Background |
|--------|-----------|-----------|
| Constitutional BUY (≥85) | Constitutional BUY | Green #d4edda |
| High Conviction BUY (≥70) | High Conviction BUY | Bright Green #c3e6cb |
| Constitutional BUY (≥55) | Constitutional BUY | Teal #d1e7dd |
| Constitutional BUY (≥35) | Constitutional BUY | Blue #cfe2ff |
| Watch — Monitoring | Watch — Monitoring | Red-tinted #f8d7da |

---

## Column Header Vocabulary

| Column | Display |
|--------|---------|
| Rank | Rank |
| Stock | Stock |
| Signal | Signal |
| Rank Score (blended) | Rank Score |
| Expectancy | Expectancy |
| SMC Score | Signal Quality |
| Δ (rank change) | Δ |

---

## Decision Driver Template

| Context | Text |
|---------|------|
| BUY signal | "Discount zone confirmed. Constitutional entry criteria met." |
| WAIT signal | "Discount zone active. Monitoring for full entry confirmation." |
| SKIP signal | "Above equilibrium — premium zone. Constitutional setup not active." |

---

## What Unchanged

- Score computation (R1-R8 math, weights) — FROZEN
- Entry zone calculations — FROZEN
- Pattern matching algorithm — FROZEN
- Target / Fibonacci calculations — FROZEN
- Portfolio positions logic — FROZEN
- All thresholds (35/55/70/85) — FROZEN
