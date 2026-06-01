# EGX SMC Scanner — smartlist

Automated EGX institutional swing scanner using Smart Money Concepts (SMC).  
Watchlist is **fetched live** from TradingView EGX30 components on every run.

## How it works

1. On startup, `fetch_egx30_components()` pulls the full EGX30 constituent list from TradingView Scanner API
2. Each stock is scored across 8 SMC indicators (Price Position, Demand Zone, Order Block, Liquidity, HTF Trend, AVWAP, MACD, Divergence)
3. Results are emailed to the configured address as a formatted HTML report
4. ORAS history is persisted in `oras_history.csv` and committed back to the repo automatically

## Scoring

| Indicator | Max pts |
|---|---|
| Price Position | 30 |
| Demand Zone (SV + VP) | 15 |
| Order Block Quality | 18 |
| Liquidity Context | 12 |
| Higher Timeframe Trend | 10 |
| Anchored VWAP | 8 |
| MACD vs Zero | 4 |
| Divergence | 3 |

Signals: **Institutional Buy** ≥85 · **Strong Watchlist** ≥70 · **Watch** ≥55 · **Watch List** ≥35

## Setup

### 1. Secrets (Settings → Secrets → Actions)

| Secret | Value |
|---|---|
| `EMAIL_USER` | Gmail address you send from |
| `EMAIL_PASS` | Gmail App Password |

### 2. Schedule

Runs automatically at **3:30 PM Cairo time** Sunday–Thursday via GitHub Actions.  
Can also be triggered manually via **Actions → Run workflow**.

## Local run

```bash
pip install -r requirements.txt
EMAIL_USER=you@gmail.com EMAIL_PASS=yourapppassword python main.py
```
