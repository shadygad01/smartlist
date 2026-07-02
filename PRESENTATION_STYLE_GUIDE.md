# Presentation Style Guide

**Created:** 2026-06-21  
**Authority:** FULL  
**Governs:** All user-facing language across Email, Telegram, and Dashboard

---

## Voice

Write like a senior portfolio manager briefing a principal.

- Observe. Don't instruct.
- Inform. Don't alarm.
- Present evidence. Don't make decisions for the reader.
- Use complete phrases, not scanner codes.

**Never use:**
- BLOCKED, REJECTED, FAILED, INVALID, DENIED
- "score too low", "position blocked", "entry failed"
- Raw technical codes as user-visible labels (SMC, BUY raw signal string)

---

## Signal Language

The system produces one of four constitutional outcomes:

| Outcome | Display |
|---------|---------|
| Full constitutional entry | Constitutional BUY |
| Highest-conviction entry | High Conviction BUY |
| Monitoring, discount zone active | Watch — Monitoring |
| Above equilibrium, no setup | Not In Scope |

Never say a BUY was blocked. Never add a warning to a BUY.
If concentration is a consideration, note it as context — not a gate.

---

## Portfolio Language

| Situation | Language |
|-----------|----------|
| Position being held in portfolio | Portfolio Core |
| Position up ≥ 75% return | Materially Appreciated |
| Candidate not yet entered, full conviction | High Conviction BUY |
| Candidate, sector concentration context | Buy With Diversification Awareness |
| Candidate, sector at cap | Future Priority |
| Non-constitutional candidate | Watch |

---

## Stars

Stars rate Signal Quality and Portfolio Fit independently. They are NEVER combined.

### Signal Quality

| Stars | Score Range | Label |
|-------|-------------|-------|
| ★★★★★ | R2 ≥ 75 | Exceptional |
| ★★★★☆ | R2 ≥ 65 | Strong |
| ★★★☆☆ | R2 ≥ 55 | Good |
| ★★☆☆☆ | R2 ≥ 45 | Acceptable |
| ★☆☆☆☆ | R2 < 45 | Developing |

### Portfolio Fit

| Stars | Meaning |
|-------|---------|
| ★★★★★ | No concentration concerns |
| ★★★★☆ | Minimal concentration context |
| ★★★☆☆ | Sector moderately elevated |
| ★★☆☆☆ | Sector concentration noted |
| ★☆☆☆☆ | Maximum diversification context |

### Portfolio Health

| Stars | Label |
|-------|-------|
| ★★★★★ | Stable |
| ★★★★☆ | Well Positioned |
| ★★★☆☆ | Attention Advised |
| ★★☆☆☆ | Needs Attention |
| ★☆☆☆☆ | Review Recommended |

---

## Tone by Channel

### Email (EGX Constitutional Morning Brief)
- Full sentences where possible
- Narrative context for opportunities
- Portfolio health as a story, not a grade
- Decision Driver explains WHY, not just what

### Telegram
- Concise. One line per data point.
- Stars over raw scores where stars are defined
- Emoji used purposefully (category identifier, not decoration)
- No jargon codes

### Dashboard
- Technical language is acceptable (this is an operations view)
- Section titles use constitutional vocabulary
- Metrics use standard units
- Platform identity uses constitutional branding

---

## Numbers

| Value | Format |
|-------|--------|
| Price | {value:.2f} EGP |
| Return | +{pct:.1f}% / -{pct:.1f}% |
| Score | {n}/100 |
| Win rate | {n:.0f}% |
| Spearman rho | rho={value:+.3f} |
| P-value | p<0.01 / p<0.05 |
| Position size | {n:.1f}% of portfolio |

---

## Capitalization

- Platform name: always "EGX Constitutional Morning Brief" or "EGX Constitutional Investment Platform"
- Signal labels: title case — "Constitutional BUY", "High Conviction BUY", "Watch — Monitoring"
- Section headers: sentence case in Telegram, title case in HTML
- Stars: always ★ (Unicode U+2605) and ☆ (U+2606)

---

## What Never Changes

The style guide governs words. It does not govern:
- Which signals are generated
- When a BUY becomes a BUY
- Portfolio entry/exit criteria
- Research evidence thresholds
- Score computation
