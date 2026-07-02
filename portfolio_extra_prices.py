"""Daily prices for portfolio-only tickers outside the scanner's trading
universe (config/scanner_config.py's STOCKS — the 27-symbol constitutional
universe used for signals/gates/backtests).

A user's real portfolio can hold EGX70 names the scanner never trades as
candidates (e.g. PHAR, CSAG). The Portfolio Tracker still needs today's price
for those. Rather than adding them to STOCKS (which would pull them into
signal generation, gating, and backtests — a much bigger change than "show me
a price"), this fetches just their current price from the exact same sources
main.py already uses for every tracked stock: the TradingView scanner API
first, yfinance as fallback. Output feeds presentation_snapshot.json's
"portfolio_extra_prices" and never touches the trading universe.
"""
import requests

TV_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.tradingview.com",
    "Referer": "https://www.tradingview.com/",
}

# Add more here if a user's portfolio holds other tickers outside STOCKS.
PORTFOLIO_EXTRA_TICKERS = ["PHAR.CA", "CSAG.CA"]

NAMES = {
    "PHAR.CA": "Egyptian International Pharmaceuticals (EIPICO)",
    "CSAG.CA": "Canal Shipping Agencies",
}


def _tv_batch_quote(tickers: list) -> dict:
    """One TradingView scanner API call for all tickers. Returns {ticker: close}."""
    tv_symbols = [f"EGX:{t.replace('.CA', '')}" for t in tickers]
    try:
        r = requests.post(
            "https://scanner.tradingview.com/egypt/scan",
            json={"symbols": {"tickers": tv_symbols}, "columns": ["close"]},
            headers=TV_HEADERS,
            timeout=15,
        )
        if r.status_code != 200:
            print(f"[PortfolioExtraPrices] TradingView batch HTTP {r.status_code}")
            return {}
        out = {}
        for row in r.json().get("data", []):
            sym = row.get("s", "")  # e.g. "EGX:PHAR"
            d = row.get("d", [])
            if d and d[0] is not None:
                out[sym.replace("EGX:", "") + ".CA"] = float(d[0])
        return out
    except Exception as e:
        print(f"[PortfolioExtraPrices] TradingView batch error: {e}")
        return {}


def _yfinance_quote(ticker: str):
    """Single-ticker yfinance fallback when TradingView has no quote for it."""
    try:
        import yfinance as yf
        hist = yf.Ticker(ticker).history(period="5d")
        if hist.empty:
            return None
        return float(hist["Close"].iloc[-1])
    except Exception as e:
        print(f"[PortfolioExtraPrices] yfinance error for {ticker}: {e}")
        return None


def fetch_portfolio_extra_prices() -> list:
    """Returns [{"ticker", "name", "current_price"}, ...] for PORTFOLIO_EXTRA_TICKERS.

    Shaped like a subset of universe_snapshot items (ticker + current_price)
    so the frontend can just concatenate the two arrays before building its
    ticker -> price lookup map, with no separate merge logic needed.
    """
    quotes = _tv_batch_quote(PORTFOLIO_EXTRA_TICKERS)
    result = []
    for ticker in PORTFOLIO_EXTRA_TICKERS:
        price = quotes.get(ticker) or _yfinance_quote(ticker)
        if not price:
            print(f"[PortfolioExtraPrices] No price found for {ticker}")
            continue
        result.append({
            "ticker": ticker,
            "name": NAMES.get(ticker, ticker),
            "current_price": round(price, 4),
        })
    return result
