import smtplib
import os
import json
import re
import sys
import html as _html
import csv
import pandas as pd
import numpy as np
import yfinance as yf
import requests
import traceback
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pattern_engine import analyze_entry_patterns
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

CAIRO = ZoneInfo("Africa/Cairo")

_tv_quote_cache: dict = {}   # populated by tv_prefetch_all_quotes() at the top of each scan

# =========================================
# GLOBAL STATE FOR MONITORING
# =========================================

open_positions = {}  # تتبع المراكز المفتوحة: {symbol: {entry_price, fib_targets, current_level, ...}}
POSITIONS_FILE = "open_positions.json"

# =========================================
# CONFIG
# =========================================

STOCKS = [
    "COMI.CA", "TMGH.CA", "ETEL.CA", "EGAL.CA",
    "EAST.CA", "ABUK.CA", "ORAS.CA", "EFIH.CA",
    "ADIB.CA", "FWRY.CA", "EMFD.CA", "PHDC.CA",
    "ORHD.CA", "EFID.CA", "HRHO.CA", "JUFO.CA",
    "BTFH.CA", "RAYA.CA", "GBCO.CA", "HELI.CA",
    "ARCC.CA", "MCQE.CA", "ORWE.CA", "ISPH.CA",
    "RMDA.CA", "OIH.CA",  "CCAP.CA",
]

# =========================================
# WHITELIST - Price Gate Threshold >= 12
# =========================================
WHITELIST = [
    "FWRY.CA",  # Fawry for Banking Technology
    "EAST.CA",  # Eastern Company
    "ETEL.CA",  # Telecom Egypt
    "EMFD.CA",  # Emaar Misr for Development
    "PHDC.CA",  # Palm Hills Developments
    "HRHO.CA",  # EFG Holding
    "MCQE.CA",  # Misr Cement (Qena)
    "OIH.CA",   # Orascom Investment Holding
    "GBCO.CA",  # GB Auto
]

PRICE_GATE_NORMAL = 18      # For stocks NOT in whitelist
PRICE_GATE_WHITELIST = 12   # For stocks IN whitelist ONLY

NAMES = {
    "COMI.CA": "Commercial International Bank",
    "TMGH.CA": "Talaat Moustafa Group",
    "ETEL.CA": "Telecom Egypt",
    "EGAL.CA": "Egypt Aluminum",
    "EAST.CA": "Eastern Company",
    "ABUK.CA": "Abu Qir Fertilizers",
    "ORAS.CA": "Orascom Construction PLC",
    "EFIH.CA": "e-Finance for Digital and Financial Investments",
    "ADIB.CA": "Abu Dhabi Islamic Bank Egypt",
    "FWRY.CA": "Fawry for Banking Technology",
    "EMFD.CA": "Emaar Misr for Development",
    "PHDC.CA": "Palm Hills Developments",
    "ORHD.CA": "Orascom Development Egypt",
    "EFID.CA": "Edita Food Industries",
    "HRHO.CA": "EFG Holding",
    "JUFO.CA": "Juhayna Food Industries",
    "BTFH.CA": "Beltone Financial Holding",
    "RAYA.CA": "Raya Holding",
    "GBCO.CA": "GB Auto",
    "HELI.CA": "Heliopolis Housing",
    "ARCC.CA": "Arabian Cement Company",
    "MCQE.CA": "Misr Cement (Qena)",
    "ORWE.CA": "Oriental Weavers",
    "ISPH.CA": "Ibnsina Pharma",
    "RMDA.CA": "Rameda Pharmaceutical",
    "OIH.CA":  "Orascom Investment Holding",
    "CCAP.CA": "Qalaa Holdings",
}

SECTORS = {
    "COMI.CA": "Banking",
    "TMGH.CA": "Real Estate",
    "ETEL.CA": "Telecommunications",
    "EGAL.CA": "Banking",
    "EAST.CA": "Consumer Goods",
    "ABUK.CA": "Chemicals & Fertilizers",
    "ORAS.CA": "Engineering & Construction",
    "EFIH.CA": "Financial Services",
    "ADIB.CA": "Banking",
    "FWRY.CA": "Financial Technology",
    "EMFD.CA": "Food & Beverages",
    "PHDC.CA": "Real Estate",
    "ORHD.CA": "Real Estate",
    "EFID.CA": "Financial Services",
    "HRHO.CA": "Financial Services",
    "JUFO.CA": "Food & Beverages",
    "BTFH.CA": "Financial Services",
    "RAYA.CA": "Technology",
    "GBCO.CA": "Automotive",
    "HELI.CA": "Real Estate",
    "ARCC.CA": "Construction Materials",
    "MCQE.CA": "Healthcare",
    "ORWE.CA": "Manufacturing",
    "ISPH.CA": "Healthcare",
    "RMDA.CA": "Healthcare",
    "OIH.CA":  "Industrial",
    "CCAP.CA": "Financial Services",
}

EMAIL = "shady.gad@live.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

TV_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.tradingview.com",
    "Referer": "https://www.tradingview.com/",
}

# =========================================
# DOW JONES PRE-MARKET SNAPSHOT
# =========================================

def get_dow_jones_status():
    try:
        ticker = yf.Ticker("^DJI")
        hist   = ticker.history(period="5d", interval="1d", auto_adjust=False)
        if hist.empty or len(hist) < 2:
            return None
        hist = hist.dropna(subset=["Close"])
        prev_close  = float(hist["Close"].iloc[-2])
        last_close  = float(hist["Close"].iloc[-1])
        last_date   = hist.index[-1].strftime("%d %b %Y")
        change      = last_close - prev_close
        change_pct  = (change / prev_close) * 100
        direction   = "up" if change >= 0 else "down"
        return {
            "price":      f"{last_close:,.2f}",
            "change":     f"{change:+,.2f}",
            "change_pct": f"{change_pct:+.2f}%",
            "direction":  direction,
            "date":       last_date,
            "emoji":      "🟢" if direction == "up" else "🔴",
            "arrow":      "▲" if direction == "up" else "▼",
            "color":      "#155724" if direction == "up" else "#721c24",
            "bg":         "#d4edda" if direction == "up" else "#f8d7da",
            "border":     "#c3e6cb" if direction == "up" else "#f5c6cb",
        }
    except Exception as e:
        print(f"  [DOW] Error fetching Dow Jones: {e}")
        return None


def build_dow_banner(dj):
    if not dj:
        return ""
    return f"""
<table width="100%" cellpadding="0" cellspacing="0" border="0"
       style="background:{dj['bg']};border-bottom:2px solid {dj['border']};">
  <tr>
    <td style="padding:12px 20px;">
      <table width="100%" cellpadding="0" cellspacing="0" border="0">
        <tr>
          <td style="font-family:Arial,sans-serif;">
            <span style="font-size:11px;font-weight:bold;letter-spacing:1px;
                         color:{dj['color']};text-transform:uppercase;">
              🇺🇸 Dow Jones Industrial Average — Last Close ({dj['date']})
            </span><br>
            <span style="font-size:20px;font-weight:bold;color:{dj['color']};">
              {dj['emoji']} {dj['price']}
            </span>
            &nbsp;
            <span style="font-size:14px;font-weight:bold;color:{dj['color']};">
              {dj['arrow']} {dj['change']} &nbsp;({dj['change_pct']})
            </span>
          </td>
          <td align="right" style="font-family:Arial,sans-serif;font-size:11px;
                                   color:{dj['color']};padding-right:4px;">
            US market closed<br>before EGX open
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>"""


W_PRICE  = 30
W_OB     = 10
W_LIQ    = 20
W_HTF    = 10
W_AVWAP  =  8
W_MACD   =  4
W_DIV    =  3
W_DZ     = 15   # Demand Zone Confluence (Stopping Volume + Volume Profile)

# =========================================
# EGX HOLIDAY CALENDAR (2026+)
# =========================================
EGX_HOLIDAYS = {
    # 2026
    date(2026,1,7),  date(2026,1,29),
    date(2026,3,19), date(2026,3,20), date(2026,3,21),
    date(2026,3,22), date(2026,3,23),
    date(2026,4,13), date(2026,4,25), date(2026,5,1),
    date(2026,5,26), date(2026,5,27), date(2026,5,28), date(2026,5,29),
    date(2026,6,16), date(2026,7,23),
    date(2026,8,25), date(2026,10,6),
    # 2027 — fixed national holidays (Islamic holidays TBD by moon sighting)
    date(2027,1,7),   # Coptic Christmas
    date(2027,4,25),  # Sinai Liberation Day
    date(2027,5,1),   # Labour Day
    date(2027,7,23),  # Revolution Day
    date(2027,10,6),  # Armed Forces Day
}

_HOLIDAY_CAL_WARN_AFTER = date(2027, 10, 6)  # update calendar when approaching this date

def is_egx_trading_day(d=None):
    if d is None:
        d = datetime.now(CAIRO).date()
    if d.weekday() in (4, 5):
        return False
    if d > _HOLIDAY_CAL_WARN_AFTER:
        print(f"  ⚠️  WARNING: EGX holiday calendar may be incomplete for {d} — update EGX_HOLIDAYS")
    return d not in EGX_HOLIDAYS

def most_recent_trading_day(from_date=None):
    d = from_date or datetime.now(CAIRO).date()
    for _ in range(14):
        if is_egx_trading_day(d):
            return d
        d -= timedelta(days=1)
    return d

def now_cairo():  return datetime.now(CAIRO)
def today_cairo(): return now_cairo().date()
def fmt_cairo(fmt="%A, %d %B %Y  |  %H:%M"): return now_cairo().strftime(fmt)

# =========================================
# TRADINGVIEW SCANNER — single stock quote
# =========================================

def tv_get_quote(tv_symbol):
    """
    Fetch latest quote for one symbol from TradingView scanner API.
    Checks _tv_quote_cache first (populated by tv_prefetch_all_quotes).
    Falls back to a single HTTP call if the cache is cold.
    """
    if tv_symbol in _tv_quote_cache:
        return _tv_quote_cache[tv_symbol]
    try:
        url = "https://scanner.tradingview.com/egypt/scan"
        payload = {
            "symbols": {"tickers": [tv_symbol]},
            "columns": ["close", "volume", "change_abs", "high", "low", "open",
                        "price_52_week_high", "price_52_week_low"]
        }
        r = requests.post(url, json=payload, headers=TV_HEADERS, timeout=15)
        if r.status_code != 200:
            print(f"  [TV] {tv_symbol}: HTTP {r.status_code}")
            return None
        data = r.json()
        rows = data.get("data", [])
        if not rows:
            return None
        d = rows[0]["d"]
        return {
            "close":  float(d[0]) if d[0] is not None else None,
            "volume": float(d[1]) if d[1] is not None else 0,
            "high":   float(d[3]) if len(d) > 3 and d[3] is not None else float(d[0]),
            "low":    float(d[4]) if len(d) > 4 and d[4] is not None else float(d[0]),
            "open":   float(d[5]) if len(d) > 5 and d[5] is not None else float(d[0]),
        }
    except Exception as e:
        print(f"  [TV] {tv_symbol} error: {e}")
        return None


def tv_prefetch_all_quotes(symbols):
    """
    Fetch all stock quotes in ONE TradingView API call and store in _tv_quote_cache.
    Reduces 26 serial HTTP requests to a single round-trip.
    Falls back gracefully — individual calls via tv_get_quote() will still work.
    """
    global _tv_quote_cache
    _tv_quote_cache = {}
    tv_symbols = [f"EGX:{s.replace('.CA', '')}" for s in symbols]
    try:
        url = "https://scanner.tradingview.com/egypt/scan"
        payload = {
            "symbols": {"tickers": tv_symbols},
            "columns": ["close", "volume", "change_abs", "high", "low", "open",
                        "price_52_week_high", "price_52_week_low"]
        }
        r = requests.post(url, json=payload, headers=TV_HEADERS, timeout=30)
        if r.status_code != 200:
            print(f"  [TV Batch] HTTP {r.status_code} — falling back to per-stock calls")
            return
        for row in r.json().get("data", []):
            sym = row.get("s", "")
            d   = row.get("d", [])
            if not d or d[0] is None:
                continue
            _tv_quote_cache[sym] = {
                "close":  float(d[0]),
                "volume": float(d[1]) if d[1] is not None else 0,
                "high":   float(d[3]) if len(d) > 3 and d[3] is not None else float(d[0]),
                "low":    float(d[4]) if len(d) > 4 and d[4] is not None else float(d[0]),
                "open":   float(d[5]) if len(d) > 5 and d[5] is not None else float(d[0]),
            }
        print(f"  [TV Batch] {len(_tv_quote_cache)}/{len(tv_symbols)} quotes in one call")
    except Exception as e:
        print(f"  [TV Batch] Error: {e} — falling back to per-stock calls")


# =========================================
# DATA DOWNLOADER
# =========================================

def _patch_today_from_tv(df, symbol):
    """
    Patch the latest row in df with today's price from TradingView Scanner.
    This ensures we always show today's closing price, not yesterday's.
    """
    ticker_code = symbol.replace(".CA", "")
    tv_symbol   = f"EGX:{ticker_code}"
    quote       = tv_get_quote(tv_symbol)

    if not quote or not quote["close"]:
        print(f"  [{symbol}] TradingView patch failed — using Yahoo price")
        return df

    today_ts = pd.Timestamp(most_recent_trading_day()).normalize()

    new_row = pd.DataFrame([{
        "Open":   quote["open"],
        "High":   quote["high"],
        "Low":    quote["low"],
        "Close":  quote["close"],
        "Volume": quote["volume"],
    }], index=[today_ts])

    df = df[df.index.normalize() != today_ts]
    df = pd.concat([df, new_row]).sort_index()
    print(f"  [{symbol}] TradingView patch: close={quote['close']:.2f} EGP")
    return df


def download_data(symbol, days=110):
    # ── All stocks: yfinance for history + TradingView patch for today ────────
    # ORAS.CA is listed on Yahoo Finance and works identically to other EGX stocks.
    # TradingView patch (applied at the end) ensures today's price is always current.
    yf_symbol = symbol if symbol.endswith(".CA") else f"{symbol}.CA"
    df = pd.DataFrame()

    try:
        ticker = yf.Ticker(yf_symbol)
        df = ticker.history(period="6mo", interval="1d", auto_adjust=False, repair=True)
        if not df.empty and len(df) > 5:
            df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
            df.index = df.index.tz_localize(None)
    except Exception as e:
        print(f"  [{symbol}] yfinance error: {e}")

    if df.empty:
        # Fallback: direct Yahoo Finance chart API
        try:
            url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{yf_symbol}"
                   f"?range=6mo&interval=1d&includeAdjustedClose=false")
            r    = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code != 200:
                print(f"  [{symbol}] Yahoo direct API: HTTP {r.status_code}")
                raise ValueError(f"HTTP {r.status_code}")
            data = r.json()
            res  = data["chart"]["result"][0]
            ind  = res["indicators"]["quote"][0]
            df   = pd.DataFrame({
                "Open":   ind["open"],
                "High":   ind["high"],
                "Low":    ind["low"],
                "Close":  ind["close"],
                "Volume": ind["volume"],
            }, index=pd.to_datetime(res["timestamp"], unit="s"))
            df = df.dropna(subset=["Close"])
            if not df.empty:
                df.index = df.index.tz_localize(None)
        except Exception as ex:
            print(f"  [{symbol}] direct API error: {ex}")

    if df.empty:
        return pd.DataFrame()

    # ── Patch today's price from TradingView (always up-to-date) ─────────────
    df = _patch_today_from_tv(df, symbol)
    return df


def col(df, name):
    if name not in df.columns: return pd.Series(dtype=float)
    return df[name].dropna()

# =========================================
# INDICATORS
# =========================================

def calc_macd(close):
    m = close.ewm(span=12).mean() - close.ewm(span=26).mean()
    s = m.ewm(span=9).mean()
    return m, s, m - s

def calc_avwap(df):
    """
    Anchored VWAP — anchor على آخر swing low حقيقي (أدنى نقطة في آخر 60 bar).
    بدل anchor ثابت على 1 يناير اللي بيعطي نتائج عشوائية.
    Returns: (avwap, avwap_lower_band)
    """
    d = pd.DataFrame({
        "H": col(df,"High"), "L": col(df,"Low"),
        "C": col(df,"Close"),"V": col(df,"Volume"),
    }).dropna()

    if len(d) < 5:
        v = float(d["C"].iloc[-1]) if len(d) else 0.0
        return v, v

    # anchor = آخر swing low في 60 bar
    lookback   = min(60, len(d))
    tail_low   = d["L"].tail(lookback)
    anchor_idx = int(tail_low.values.argmin())
    anchor_pos = len(d) - lookback + anchor_idx

    # لو الـ anchor هو آخر 3 bars → fallback لـ 20 bar قبله
    if anchor_pos >= len(d) - 3:
        anchor_pos = max(0, len(d) - 20)

    d_anc = d.iloc[anchor_pos:].copy()
    if len(d_anc) < 3:
        d_anc = d.copy()

    tp  = (d_anc["H"] + d_anc["L"] + d_anc["C"]) / 3
    av  = (tp * d_anc["V"]).cumsum() / d_anc["V"].cumsum()
    cum_v  = d_anc["V"].cumsum()
    var_vw = ((tp - av) ** 2 * d_anc["V"]).cumsum() / cum_v.where(cum_v > 0, 1)
    std_vw = np.sqrt(var_vw.clip(lower=0)).fillna(0)
    lo     = av - std_vw

    return float(av.iloc[-1]), float(lo.iloc[-1])

def swings(df, lb=80):
    """
    Price range levels based on custom SMC framework:
      0.00 = lo  (swing low  — best buy)
      0.15 = buy_hi  (top of buy zone)
      0.50 = eq  (equilibrium)
      0.85 = sell_lo (bottom of sell zone)
      1.00 = hi  (swing high — best sell)
    Uses actual High/Low prices for accurate range measurement.
    """
    hi      = float(df["High"].tail(lb).max())
    lo      = float(df["Low"].tail(lb).min())
    rng     = hi - lo
    eq      = lo + rng * 0.50
    buy_hi  = lo + rng * 0.15   # top of buy zone  (0.15)
    sell_lo = lo + rng * 0.85   # bottom of sell zone (0.85)
    return hi, lo, eq, buy_hi, sell_lo




# =========================================
# STOPPING VOLUME & VOLUME PROFILE
# =========================================

def calc_stopping_volume(df, eq, lo, lookback=30, vol_mult=2.5, range_ratio=0.5):
    """
    Detect Stopping Volume candles inside the discount zone (price < EQ).
    A SV candle: high volume (effort) + narrow range (no result) + in discount.
    Returns: sv_detected(bool), sv_score(0-1), sv_desc(str)
    """
    needed = ["High", "Low", "Close", "Open", "Volume"]
    if not all(c in df.columns for c in needed) or len(df) < lookback + 5:
        return False, 0.0, "Insufficient data for SV scan", 0.0

    d          = df[needed].dropna().tail(lookback + 20)
    avg_vol    = d["Volume"].rolling(lookback).mean()
    candle_rng = d["High"] - d["Low"]
    avg_rng    = candle_rng.rolling(lookback).mean()

    # extract scan-window arrays (after rolling warmup) — avoids repeated .iloc[i] overhead
    c_close = d["Close"].values[lookback:]
    c_vol   = d["Volume"].values[lookback:]
    c_low   = d["Low"].values[lookback:]
    c_rng   = candle_rng.values[lookback:]
    a_vol   = avg_vol.values[lookback:]
    a_rng   = avg_rng.values[lookback:]

    discount_range = eq - lo
    with np.errstate(invalid="ignore", divide="ignore"):
        close_pos = np.where(c_rng > 0, (c_close - c_low) / c_rng, 0.0)

    mask = (
        (a_vol > 0) & (a_rng > 0) &
        (c_close < eq) &
        (c_vol >= vol_mult * a_vol) &
        (c_rng <= range_ratio * a_rng) &
        (c_rng > 0) &
        (close_pos >= 0.40)
    )

    idx = np.where(mask)[0]
    if len(idx) == 0:
        return False, 0.0, "No Stopping Volume detected in discount zone", 0.0

    vol_ratio = c_vol[idx] / a_vol[idx]
    depth     = (eq - c_close[idx]) / discount_range if discount_range > 0 else np.zeros(len(idx))
    scores    = depth * 0.6 + np.minimum(vol_ratio / 5, 1.0) * 0.4
    best_i    = int(np.argmax(scores))

    best_close     = float(c_close[idx[best_i]])
    best_vol_ratio = float(vol_ratio[best_i])
    best_depth     = float(depth[best_i])
    score          = float(min(1.0, scores[best_i]))
    desc = (f"Stopping Volume @ {best_close:.1f} — "
            f"vol {best_vol_ratio:.1f}x avg — "
            f"depth {best_depth*100:.0f}% into discount")
    return True, score, desc, best_close


def calc_volume_profile(df, eq, lo, buy_hi, bins=20, hvn_pct=0.70):
    """
    Build volume profile over full history; find HVN inside discount zone.
    Each bar's volume is distributed proportionally across its H-L price range.
    Returns: hvn_detected(bool), hvn_score(0-1), hvn_price(float), hvn_desc(str)
    """
    needed = ["High", "Low", "Close", "Volume"]
    if not all(c in df.columns for c in needed) or len(df) < 10:
        return False, 0.0, 0.0, "Insufficient data for VP scan"

    d         = df[needed].dropna()
    price_min = float(d["Low"].min())
    price_max = float(d["High"].max())
    if price_max <= price_min:
        return False, 0.0, 0.0, "Invalid price range for VP"

    bin_size  = (price_max - price_min) / bins
    vol_bins  = np.zeros(bins)
    bin_edges = np.linspace(price_min, price_max, bins + 1)

    h_arr = d["High"].values
    l_arr = d["Low"].values
    v_arr = d["Volume"].values.astype(float)
    valid = (v_arr > 0) & (h_arr > l_arr)
    h_arr, l_arr, v_arr = h_arr[valid], l_arr[valid], v_arr[valid]
    lo_bins = np.clip(((l_arr - price_min) / bin_size).astype(int), 0, bins - 1)
    hi_bins = np.clip(((h_arr - price_min) / bin_size).astype(int), 0, bins - 1)
    for i in range(len(h_arr)):
        span = hi_bins[i] - lo_bins[i] + 1
        vol_bins[lo_bins[i]: hi_bins[i] + 1] += v_arr[i] / span

    max_vol       = np.max(vol_bins)
    threshold     = max_vol * hvn_pct
    discount_hvns = []
    for b in range(bins):
        bin_price = (bin_edges[b] + bin_edges[b + 1]) / 2
        # HVN لازم يكون في Buy Zone (0–15%) فقط
        if bin_price >= buy_hi:
            continue
        if vol_bins[b] >= threshold:
            depth = (eq - bin_price) / (eq - lo) if (eq - lo) > 0 else 0
            discount_hvns.append({"price": bin_price,
                                   "vol": vol_bins[b], "depth": depth})

    if not discount_hvns:
        return False, 0.0, 0.0, "No HVN in discount zone"

    best      = max(discount_hvns, key=lambda x: x["vol"])
    hvn_score = min(1.0, best["vol"] / max_vol)
    desc      = (f"HVN @ {best['price']:.1f} — "
                 f"{best['vol']/max_vol*100:.0f}% of peak vol — "
                 f"depth {best['depth']*100:.0f}% into discount")
    return True, hvn_score, best["price"], desc


def sc_demand_zone(df, eq, lo, buy_hi, _sv=None, _hvn=None):
    """
    Demand Zone Confluence = Stopping Volume + Volume Profile HVN, both in discount.
    SV + HVN  → full W_DZ  (true institutional demand zone)
    SV only   → 60% W_DZ   (absorption present, no volume memory)
    HVN only  → 40% W_DZ   (volume memory, no absorption candle)
    Neither   → 0
    _sv/_hvn: pre-computed tuples from calc_stopping_volume / calc_volume_profile
              to avoid recomputing when called from analyze().
    """
    sv_hit, sv_score, sv_desc, _sv_price = _sv  if _sv  is not None else calc_stopping_volume(df, eq, lo)
    hvn_hit, hvn_score, _, hvn_desc      = _hvn if _hvn is not None else calc_volume_profile(df, eq, lo, buy_hi)

    if sv_hit and hvn_hit:
        pts  = W_DZ
        desc = f"DEMAND ZONE CONFIRMED — {sv_desc} | {hvn_desc}"
    elif sv_hit:
        pts  = round(W_DZ * 0.60)
        desc = f"Stopping Volume only — {sv_desc} | No HVN: {hvn_desc}"
    elif hvn_hit:
        pts  = round(W_DZ * 0.40)
        desc = f"HVN only — {hvn_desc} | No SV: {sv_desc}"
    else:
        pts  = 0
        desc = f"No demand confluence — SV: {sv_desc} | VP: {hvn_desc}"

    return pts, desc


# =========================================
# SMC SCORING
# =========================================

def sc_price(cur, lo, hi, eq, buy_hi, sell_lo):
    """
    Score price position using custom SMC zones:
      Buy Zone   : lo  → buy_hi  (0.00–0.15) — max score, degrades toward buy_hi
      Mid Disc.  : buy_hi → eq   (0.15–0.50) — partial score, degrades toward EQ
      EQ or above: eq → hi       (0.50–1.00) — 0, gate already blocks these
    """
    rng = hi - lo
    if rng <= 0: return 0, "Invalid range"

    if cur <= buy_hi:
        # Inside buy zone (0.00–0.15): score 100% → 60% linearly
        ratio = (cur - lo) / (buy_hi - lo) if (buy_hi - lo) > 0 else 0
        pts   = max(round(W_PRICE * (1.0 - ratio * 0.40)), 0)
        dist_pct = round((cur - lo) / lo * 100, 1) if lo > 0 else 0
        return pts, f"Buy Zone @ {cur:.1f} — {dist_pct}% above Deep Discount floor — {pts}/{W_PRICE}"

    if cur < eq:
        # Mid-discount (0.15–0.50): score 60% → 0% linearly
        ratio = (cur - buy_hi) / (eq - buy_hi) if (eq - buy_hi) > 0 else 1
        pts   = max(round(W_PRICE * 0.60 * (1.0 - ratio)), 0)
        dist_to_dd = round((cur - buy_hi) / rng * 100, 1)
        return pts, f"Mid-Discount @ {cur:.1f} — {dist_to_dd}% away from Deep Discount — {pts}/{W_PRICE}"

    pct_above_eq = round((cur - eq) / rng * 100, 1)
    return 0, f"Premium Zone @ {cur:.1f} — {pct_above_eq}% above EQ — SMC setup inactive"

def sc_ob(df, cur, eq, lo, buy_hi):
    """
    Order Block Quality — OB حقيقي بناءً على:
    1. آخر bearish candle قبل move صاعد قوي (impulse ≥ 1.5x avg range)
    2. OB لازم يكون في discount zone (تحت EQ)
    3. السعر الحالي لازم يكون فوق الـ OB (مش اخترقه لتحت)

    لو مفيش OB حقيقي → يرجع 0 بدل ما يبعت رقم مضلل.
    """
    needed = ["Open", "High", "Low", "Close"]
    if not all(c in df.columns for c in needed) or len(df) < 10:
        return 0, "Insufficient data for OB detection"

    d   = df[needed].dropna()
    rng = d["High"] - d["Low"]
    avg_rng = float(rng.rolling(20).mean().iloc[-1]) if len(d) >= 20 else float(rng.mean())

    if avg_rng <= 0:
        return 0, "Invalid range data"

    discount_range = eq - lo
    if discount_range <= 0:
        return 0, "Invalid discount range"

    # ── بحث عن OB حقيقي في آخر 40 bar ───────────────────────────────────────
    ob_candidates = []
    search   = d.tail(40)
    s_open   = search["Open"].values
    s_close  = search["Close"].values
    s_low    = search["Low"].values
    s_high   = search["High"].values
    n_search = len(search)

    for i in range(n_search - 2):
        c_open  = s_open[i]
        c_close = s_close[i]
        c_low   = s_low[i]
        c_high  = s_high[i]

        # OB candle: bearish (close < open)
        if c_close >= c_open:
            continue

        # الـ 1-2 candles التالية لازم يكون فيها impulse صاعد قوي (≥ 1.5x avg range)
        has_impulse = False
        for j in range(i + 1, min(i + 3, n_search)):
            if s_high[j] - s_low[j] >= avg_rng * 1.5:
                has_impulse = True
                break
        if not has_impulse:
            continue

        # OB zone = body of the bearish candle (open → close)
        ob_top = max(c_open, c_close)   # top of bearish body
        ob_bot = min(c_open, c_close)   # bottom of bearish body (mitigation level)

        # OB zone must be in Buy Zone (0–15%)
        if ob_top >= buy_hi:
            continue

        # OB is mitigated if price closed below the body bottom
        if cur <= ob_bot:
            continue

        # quality based on zone midpoint depth in discount zone
        ob_mid  = (ob_top + ob_bot) / 2
        ratio   = (ob_mid - lo) / discount_range
        quality = max(0.0, 1.0 - ratio)

        dist = abs(cur - ob_top) / cur   # distance to OB top (natural entry point)
        ob_candidates.append({
            "top":     ob_top,
            "bot":     ob_bot,
            "quality": quality,
            "dist":    dist,
            "candle":  i,
        })

    if not ob_candidates:
        return 0, "No valid OB found in discount zone (last 40 bars)"

    # أفضل OB: أعلى quality × proximity
    best = max(ob_candidates,
               key=lambda x: x["quality"] * max(0.1, 1 - x["dist"] * 5))

    ob_top = best["top"]
    ob_bot = best["bot"]
    qual   = best["quality"]
    dist   = best["dist"]
    zone_lbl = "Buy Zone" if ob_top <= buy_hi else "Mid-Discount"

    if dist > 0.10:
        pts = round(W_OB * qual * 0.15)
        return pts, f"OB zone {ob_bot:.1f}–{ob_top:.1f} [{zone_lbl}] — far ({dist*100:.0f}% away) → {pts}/{W_OB}"
    if dist < 0.02:
        pts = round(W_OB * qual)
        return pts, f"At OB zone {ob_bot:.1f}–{ob_top:.1f} [{zone_lbl}] — quality {qual*100:.0f}% → {pts}/{W_OB}"
    if dist < 0.05:
        pts = round(W_OB * qual * 0.6)
        return pts, f"Near OB zone {ob_bot:.1f}–{ob_top:.1f} [{zone_lbl}] — quality {qual*100:.0f}% → {pts}/{W_OB}"
    pts = round(W_OB * qual * 0.30)
    return pts, f"OB zone {ob_bot:.1f}–{ob_top:.1f} [{zone_lbl}] — moderate distance → {pts}/{W_OB}"

def sc_liquidity(df, cur):
    """
    Liquidity Context — 3 أنواع من الـ liquidity events:
    1. Sweep & Reverse   : السعر اخترق swing low ثم رجع فوقه (stop hunt)
    2. Equal Lows (EQL)  : مستويات متقاربة تشير لـ liquidity pool تحت
    3. Rejection Wick    : شمعة بـ lower wick طويل (≥ 2x body) في discount

    الأعلى قيمة = Sweep & Reverse (إثبات أن السوق امتص البيع وعكس)
    """
    needed = ["High", "Low", "Close", "Open"]
    close  = df["Close"].dropna() if "Close" in df.columns else pd.Series(dtype=float)

    if not all(c in df.columns for c in needed) or len(df) < 10:
        return 0, "Insufficient data for liquidity scan"

    d     = df[needed].dropna()
    score = 0
    desc  = []

    # ── 1. Sweep & Reverse (أقوى إشارة) ──────────────────────────────────────
    if len(d) >= 10:
        recent   = d.tail(10)
        swing_lo = float(d["Low"].tail(20).quantile(0.10))  # أدنى 10% من الـ 20 bar

        for i in range(1, len(recent) - 1):
            c_low   = float(recent["Low"].iloc[i])
            c_close = float(recent["Close"].iloc[i])

            # اخترق الـ swing low ثم أقفل فوقه
            if c_low < swing_lo and c_close > swing_lo:
                score += W_LIQ
                desc.append(f"Sweep & Reverse @ {c_low:.1f} — stop hunt confirmed ✓")
                break

    # ── 2. Rejection Wick في discount ─────────────────────────────────────────
    if score == 0 and len(d) >= 5:
        last5 = d.tail(5)
        for i in range(len(last5)):
            o = float(last5["Open"].iloc[i])
            c = float(last5["Close"].iloc[i])
            l = float(last5["Low"].iloc[i])
            h = float(last5["High"].iloc[i])
            body      = abs(c - o)
            lower_wick = min(o, c) - l
            candle_rng = h - l

            if candle_rng <= 0:
                continue
            # lower wick ≥ 60% of candle range و close في upper 40%
            if lower_wick >= candle_rng * 0.60 and c >= l + candle_rng * 0.40:
                pts = round(W_LIQ * 0.6)
                score = max(score, pts)
                desc.append(f"Rejection wick @ {l:.1f} — lower wick {lower_wick/candle_rng*100:.0f}% of range")

    # ── 3. Equal Lows (liquidity pool below) ──────────────────────────────────
    if score == 0 and len(d) >= 15:
        lows = d["Low"].tail(15).values
        eql_count = 0
        base_lo   = float(d["Low"].tail(15).min())
        for lv in lows:
            if abs(lv - base_lo) / base_lo < 0.005:   # within 0.5%
                eql_count += 1
        if eql_count >= 3:
            pts = round(W_LIQ * 0.4)
            score = pts
            desc.append(f"Equal Lows x{eql_count} @ {base_lo:.1f} — liquidity pool below")

    if not desc:
        desc.append("No liquidity event detected")

    return min(score, W_LIQ), " · ".join(desc)

def _find_pivots(high_series, low_series, left=3, right=3):
    """Identify swing highs/lows using left/right bar confirmation."""
    h = high_series.values
    l = low_series.values
    n = min(len(h), len(l))
    swing_highs, swing_lows = [], []
    for i in range(left, n - right):
        if all(h[i] >= h[i - j] for j in range(1, left + 1)) and \
           all(h[i] >= h[i + j] for j in range(1, right + 1)):
            swing_highs.append(float(h[i]))
        if all(l[i] <= l[i - j] for j in range(1, left + 1)) and \
           all(l[i] <= l[i + j] for j in range(1, right + 1)):
            swing_lows.append(float(l[i]))
    return swing_highs, swing_lows


def sc_htf(df):
    """
    Higher Timeframe Trend Quality — 3 components (total W_HTF pts):
      1. MA200 position  : price vs 200-day MA         (40% of W_HTF)
      2. MA50 slope      : is 50-day MA rising?         (30% of W_HTF)
      3. HH/HL structure : Higher Highs & Higher Lows   (30% of W_HTF)
    Scoring:
      - Full score  → clear recovery signals present
      - Partial     → mixed signals
      - Zero        → deep downtrend, no structure yet
    """
    close = df["Close"].dropna()
    n = len(close)

    pts  = 0
    desc = []

    # ── 1. MA200 position ────────────────────────────────────────────────────
    w1 = round(W_HTF * 0.40)
    if n >= 200:
        ma200 = float(close.rolling(200).mean().iloc[-1])
        cur   = float(close.iloc[-1])
        if cur >= ma200:
            pts += w1
            desc.append(f"Above MA200 ({ma200:.1f}) ✓")
        else:
            gap = round((ma200 - cur) / ma200 * 100, 1)
            if gap < 5:
                pts += round(w1 * 0.5)
                desc.append(f"Near MA200 ({ma200:.1f}, -{gap}%)")
            else:
                desc.append(f"Below MA200 ({ma200:.1f}, -{gap}%)")
    elif n >= 50:
        # حساب MA50 كبديل لو مفيش 200 يوم
        ma50 = float(close.rolling(50).mean().iloc[-1])
        cur  = float(close.iloc[-1])
        if cur >= ma50:
            pts += round(w1 * 0.6)
            desc.append(f"Above MA50 ({ma50:.1f}) [no MA200] ✓")
        else:
            desc.append(f"Below MA50 ({ma50:.1f}) [no MA200]")
    else:
        desc.append("Insufficient data for MA")

    # ── 2. MA50 slope (last 10 bars) ─────────────────────────────────────────
    w2 = round(W_HTF * 0.30)
    if n >= 60:
        ma50_series = close.rolling(50).mean().dropna()
        if len(ma50_series) >= 10:
            slope = float(ma50_series.iloc[-1]) - float(ma50_series.iloc[-10])
            if slope > 0:
                pts += w2
                desc.append(f"MA50 rising (+{slope:.2f}) ✓")
            elif slope > -float(close.iloc[-1]) * 0.01:
                pts += round(w2 * 0.4)
                desc.append(f"MA50 flattening ({slope:.2f})")
            else:
                desc.append(f"MA50 falling ({slope:.2f})")
    else:
        desc.append("MA50 slope: insufficient data")

    # ── 3. HH / HL structure (last 40 bars, pivot confirmation) ─────────────
    w3 = W_HTF - w1 - w2
    if n >= 20:
        lb_tail = min(40, n)
        h_ser = df["High"].dropna().tail(lb_tail) if "High" in df.columns else close.tail(lb_tail)
        l_ser = df["Low"].dropna().tail(lb_tail)  if "Low"  in df.columns else close.tail(lb_tail)
        s_highs, s_lows = _find_pivots(h_ser, l_ser, left=3, right=3)

        if len(s_highs) >= 2 and len(s_lows) >= 2:
            hh = s_highs[-1] > s_highs[-2]
            hl = s_lows[-1]  > s_lows[-2]
            if hh and hl:
                pts += w3
                desc.append("HH+HL structure confirmed ✓")
            elif hh or hl:
                pts += round(w3 * 0.5)
                desc.append(f"Partial structure (HH:{hh}, HL:{hl})")
            else:
                desc.append("No HH/HL — downtrend structure")
        else:
            desc.append(f"Insufficient pivots ({len(s_highs)} highs, {len(s_lows)} lows) — no structure")
    else:
        desc.append("HH/HL: insufficient data")

    return pts, " | ".join(desc)


def sc_avwap(cur, av, av_lo):
    if cur<=av_lo: return W_AVWAP, f"At/below AVWAP lower band {av_lo:.1f}"
    if cur<av: return max(round(((av-cur)/(av-av_lo))*(W_AVWAP-1)),1), f"Below AVWAP {av:.1f}"
    return 0, f"Above AVWAP {av:.1f}"

def sc_macd(close, _macd=None):
    if len(close)<15: return 0,"Not enough data"
    m,sg,h = _macd if _macd is not None else calc_macd(close)
    macd_now  = m.iloc[-1]
    macd_prev = m.iloc[-2]
    sig_now   = sg.iloc[-1]
    sig_prev  = sg.iloc[-2]
    # فوق الصفر → صفر دايماً
    if macd_now >= 0:
        return 0, f"MACD above zero ({macd_now:.4f}) — no score"
    # تحت الصفر + تقاطع صاعد (crossover) → 4/4
    crossed_up = macd_prev <= sig_prev and macd_now > sig_now
    if crossed_up:
        return W_MACD, f"Bullish crossover BELOW zero ({macd_now:.4f}) — 4/4"
    # تحت الصفر بدون تقاطع → 2/4
    half = round(W_MACD / 2)
    return half, f"MACD below zero ({macd_now:.4f}), no cross yet — 2/4"

def _calc_rsi(close, period=14):
    """RSI حقيقي بـ Wilder smoothing."""
    delta = close.diff()
    gain  = delta.clip(lower=0)
    loss  = (-delta).clip(lower=0)
    avg_g = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_l = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    # avg_l == 0 means no losses → RSI = 100; use where() to avoid NaN propagation
    rsi = avg_l.copy()
    rsi[:] = 100.0
    has_loss = avg_l > 0
    rs = avg_g[has_loss] / avg_l[has_loss]
    rsi[has_loss] = 100 - (100 / (1 + rs))
    rsi[avg_g == 0] = 0.0   # no gains either → RSI = 0 (flat price after warmup)
    return rsi

def sc_div(close, ml):
    """
    Bullish Divergence Detection — RSI + MACD:
      - Price makes Lower Low (LL)  while RSI  makes Higher Low → RSI  divergence
      - Price makes Lower Low (LL)  while MACD makes Higher Low → MACD divergence
    Lookback: last 30 bars, comparing last 2 swing lows (simple: min of halves).
    Scoring:
      Both divergences  → W_DIV      (3/3)
      RSI  only         → W_DIV * 0.7 (2/3 rounded)
      MACD only         → W_DIV * 0.5 (1-2/3)
      None              → 0
    """
    if len(close) < 30:
        return 0, "Insufficient data for divergence"

    # تقسيم آخر 30 bar لنصين — نقارن الـ swing low في كل نص
    half = 15
    tail = close.tail(30)

    price_lo1 = float(tail.iloc[:half].min())   # أول نص (قديم)
    price_lo2 = float(tail.iloc[half:].min())   # تاني نص (حديث)

    # لازم يكون في lower low في السعر عشان يبقى divergence حقيقي
    if price_lo2 >= price_lo1 * 0.998:
        return 0, f"No price LL (lo1={price_lo1:.1f}, lo2={price_lo2:.1f}) — no divergence"

    signals = []

    # ── RSI divergence ────────────────────────────────────────────────────────
    if len(close) >= 44:   # 14 period warmup + 30 tail
        rsi    = _calc_rsi(close).dropna()
        if len(rsi) >= 30:
            rsi_tail = rsi.tail(30)
            rsi_lo1  = float(rsi_tail.iloc[:half].min())
            rsi_lo2  = float(rsi_tail.iloc[half:].min())
            if rsi_lo2 > rsi_lo1 * 1.01:   # RSI higher low (+1% tolerance)
                signals.append(f"RSI div (RSI {rsi_lo1:.1f}→{rsi_lo2:.1f} ↑, price ↓)")

    # ── MACD divergence ───────────────────────────────────────────────────────
    if len(ml) >= 30:
        ml_tail = ml.tail(30)
        ml_lo1  = float(ml_tail.iloc[:half].min())
        ml_lo2  = float(ml_tail.iloc[half:].min())
        if ml_lo2 > ml_lo1 * 1.01:
            signals.append(f"MACD div (MACD {ml_lo1:.4f}→{ml_lo2:.4f} ↑, price ↓)")

    if len(signals) == 2:
        return W_DIV, "STRONG: " + " | ".join(signals)
    elif len(signals) == 1:
        if "RSI" in signals[0]:
            pts = round(W_DIV * 0.7)
        else:
            pts = round(W_DIV * 0.5)
        return pts, signals[0]
    else:
        return 0, f"No divergence (price LL confirmed: {price_lo1:.1f}→{price_lo2:.1f}, but indicators confirmed trend)"

def sig_info(score):
    if score>=85: return "Institutional Buy","#155724","#d4edda","#c3e6cb"
    if score>=70: return "Very Strong Buy",  "#155724","#c3e6cb","#b1dfbb"
    if score>=55: return "Strong Buy",       "#0a3622","#d1e7dd","#a3cfbb"
    if score>=35: return "Buy",              "#084298","#cfe2ff","#b6d4fe"
    return               "Skip",             "#721c24","#f8d7da","#f5c6cb"

# =========================================
# ENTRY ZONES (Averaging Strategy)
# =========================================

def calc_entry_zones(df, cur, hi, lo, eq, buy_hi, sell_lo, av, alo, _sv=None, _hvn=None):
    """
    Calculate 3 entry zones for averaging-down strategy.
    No stop loss — zones are designed for scaled entries with renewable liquidity.

    Zone 1 (Aggressive) : first confluence area just inside discount
    Zone 2 (Add / Avg)  : deeper discount, OB + HVN level
    Zone 3 (Deep Value) : near swing low, maximum value area

    Returns dict with zone levels, confluence count, avg_entry, return_from_avg.
    """
    levels = []  # list of (price, label, confluence_count)

    # ── collect all meaningful support levels inside discount ─────────────────
    # Top of buy zone (0.15 level)
    if buy_hi < eq:
        levels.append((buy_hi, "Buy Zone Top (0.15)", 2))

    # Midpoint of buy zone (0.075 level) — best entry area
    buy_mid = lo + (hi - lo) * 0.075
    levels.append((buy_mid, "Buy Zone Mid (0.075)", 3))

    # AVWAP lower band
    if alo < eq:
        levels.append((alo, "AVWAP Lower Band", 1))

    # HVN from volume profile (use pre-computed result when available)
    hvn_hit, _, hvn_price, _ = _hvn if _hvn is not None else calc_volume_profile(df, eq, lo, buy_hi)
    if hvn_hit and hvn_price < eq:
        # check if it's close to an existing level (within 2%) — if so, add confluence
        merged = False
        for i, (p, lbl, cnt) in enumerate(levels):
            if abs(p - hvn_price) / p < 0.02:
                levels[i] = (p, lbl + " + HVN", cnt + 1)
                merged = True
                break
        if not merged:
            levels.append((hvn_price, "Volume Profile HVN", 2))

    # Stopping Volume candle level (use pre-computed result when available)
    sv_hit, _, _sv_desc, sv_price = _sv if _sv is not None else calc_stopping_volume(df, eq, lo)
    if sv_hit and sv_price > 0 and sv_price < eq:
        merged = False
        for i, (p, lbl, cnt) in enumerate(levels):
            if abs(p - sv_price) / p < 0.02:
                levels[i] = (p, lbl + " + SV", cnt + 1)
                merged = True
                break
        if not merged:
            levels.append((sv_price, "Stopping Volume", 2))

    # Recent swing low (20-bar)
    if len(df) >= 20:
        recent_low = float(df["Low"].tail(20).min())
        if recent_low < eq:
            merged = False
            for i, (p, lbl, cnt) in enumerate(levels):
                if abs(p - recent_low) / p < 0.015:
                    levels[i] = (p, lbl + " + SwingLow", cnt + 1)
                    merged = True
                    break
            if not merged:
                levels.append((recent_low, "Recent Swing Low", 1))

    # Absolute swing low (80-bar)
    if lo < eq:
        merged = False
        for i, (p, lbl, cnt) in enumerate(levels):
            if abs(p - lo) / p < 0.015:
                levels[i] = (p, lbl + " + Range Low", cnt + 1)
                merged = True
                break
        if not merged:
            levels.append((lo, "Range Low (80-bar)", 1))

    if not levels:
        return None

    # ── sort by price descending (highest first = closest to current price) ──
    levels.sort(key=lambda x: x[0], reverse=True)

    # ── filter: only levels BELOW current price ───────────────────────────────
    levels = [(p, lbl, cnt) for p, lbl, cnt in levels if p < cur * 0.999]

    if not levels:
        return None

    # ── assign to 3 zones ─────────────────────────────────────────────────────
    # Zone 1: highest confluence level (or highest price level if tie)
    # Zone 2: middle area
    # Zone 3: deepest / lowest level

    # sort by confluence desc, then price desc for tie-breaking
    by_conf = sorted(levels, key=lambda x: (x[2], x[0]), reverse=True)

    z1_price = by_conf[0][0]
    z1_label = by_conf[0][1]
    z1_conf  = by_conf[0][2]

    # zone 3 = lowest price level
    z3_price = levels[-1][0]
    z3_label = levels[-1][1]
    z3_conf  = levels[-1][2]

    # zone 2 = middle — closest to midpoint between z1 and z3
    mid = (z1_price + z3_price) / 2
    remaining = [(p, lbl, cnt) for p, lbl, cnt in levels
                 if abs(p - z1_price) / z1_price > 0.005
                 and abs(p - z3_price) / z3_price > 0.005]
    if remaining:
        z2_item  = min(remaining, key=lambda x: abs(x[0] - mid))
        z2_price, z2_label, z2_conf = z2_item
    else:
        z2_price = (z1_price + z3_price) / 2
        z2_label = "Midpoint Estimate"
        z2_conf  = 1

    # ── entry range ±1.5% around each zone center ─────────────────────────────
    def zone_range(p):
        return round(p * 0.985, 2), round(p * 1.015, 2)

    z1_lo, z1_hi = zone_range(z1_price)
    z2_lo, z2_hi = zone_range(z2_price)
    z3_lo, z3_hi = zone_range(z3_price)

    # ── weighted average entry (Zone1 × 0.5, Zone2 × 0.3, Zone3 × 0.2) ──────
    avg_entry = round(z1_price * 0.5 + z2_price * 0.3 + z3_price * 0.2, 2)

    # ── target already set as cur*1.12 — recompute from hi for accuracy ───────
    target = round(hi * 0.88, 2)   # conservative: 88% of swing high
    ret_from_avg = round(((target - avg_entry) / avg_entry) * 100, 1) if avg_entry > 0 else 0

    return {
        "z1": {"lo": z1_lo, "hi": z1_hi, "center": round(z1_price,2),
               "label": z1_label, "conf": z1_conf},
        "z2": {"lo": z2_lo, "hi": z2_hi, "center": round(z2_price,2),
               "label": z2_label, "conf": z2_conf},
        "z3": {"lo": z3_lo, "hi": z3_hi, "center": round(z3_price,2),
               "label": z3_label, "conf": z3_conf},
        "avg_entry":     avg_entry,
        "target":        target,
        "ret_from_avg":  ret_from_avg,
    }


# =========================================
# MAIN ANALYSIS
# =========================================

def analyze(symbol):
    try:
        df = download_data(symbol, 110)
        if df.empty or len(df) < 5:
            raise Exception("API Data stream isolated or empty")

        hist_price = float(df["Close"].iloc[-1])
        hist_date  = df.index[-1].strftime("%Y-%m-%d")
        cur        = hist_price
        last_dt    = hist_date
        src        = "TradingView Scanner" if "ORAS" in symbol else "EGX yfinance"
        is_fresh   = True

        close            = df["Close"]
        hi,lo,eq,buy_hi,sell_lo = swings(df)
        av,alo                  = calc_avwap(df)   # always compute for display
        sv_result  = None   # populated in discount-zone branch, reused by entry zones
        hvn_result = None

        # ── GATE: Price must be strictly below EQ (< 0.50 level) ─────────────
        # At EQ or above → SMC setup does not exist → all scores locked at zero
        if cur >= eq:
            pct_above_eq = round((cur - eq) / (hi - lo) * 100, 1) if hi > lo else 0
            r1 = 0; l1 = f"Premium Zone @ {cur:.1f} — {pct_above_eq}% above EQ — SMC setup inactive"
            locked     = "Locked — price not in discount zone (0–50%)"
            r2,l2 = 0,locked; r3,l3 = 0,locked; r4,l4 = 0,locked
            r5,l5 = 0,locked; r6,l6 = 0,locked; r7,l7 = 0,locked
            r8,l8 = 0,locked
        else:
            # ── Full SMC scoring — price confirmed in discount zone ────────────
            r1,l1  = sc_price(cur,lo,hi,eq,buy_hi,sell_lo)
            r2,l2  = sc_ob(df,cur,eq,lo,buy_hi)
            r3,l3  = sc_liquidity(df,cur)
            r4,l4  = sc_htf(df)
            r5,l5  = sc_avwap(cur,av,alo)
            macd_result = calc_macd(close)              # compute once, share with sc_macd + sc_div
            ml          = macd_result[0]
            r6,l6  = sc_macd(close, _macd=macd_result)
            r7,l7  = sc_div(close,ml)
            sv_result  = calc_stopping_volume(df,eq,lo) # compute once, share with sc_demand_zone + calc_entry_zones
            hvn_result = calc_volume_profile(df,eq,lo,buy_hi)
            r8,l8  = sc_demand_zone(df,eq,lo,buy_hi, _sv=sv_result, _hvn=hvn_result)

        total = min(r1+r2+r3+r4+r5+r6+r7+r8, 100)

        # ══════════════════════════════════════════════════════════════════
        # DUAL GATE
        #   GATE 1 — Price in Deep Discount:  r1 >= 15  (out of W_PRICE=30)
        #   GATE 2 — Sweep & Reverse confirmed: r3 == W_LIQ (20/20)
        #
        #   r1 >= 15 AND r3 == 20  →  BUY eligible (normal sig_info)
        #   r1 >= 15 AND r3 <  20  →  WATCH (price ok, waiting for sweep)
        #   r1 <  15               →  IGNORE (hard block)
        # ══════════════════════════════════════════════════════════════════
        # ✅ DYNAMIC PRICE GATE - استخدم 12 للـ whitelist، 18 للأسهم العادية
        PRICE_GATE = PRICE_GATE_WHITELIST if symbol in WHITELIST else PRICE_GATE_NORMAL
        LIQ_GATE   = W_LIQ   # only Sweep & Reverse (20/20) passes to BUY

        price_ok = (r1 >= PRICE_GATE)
        liq_ok   = (r3 >= LIQ_GATE)

        if total < 35:
            sig = "Skip"
            tc  = "#721c24"; tbg = "#f8d7da"; tbr = "#f5c6cb"
        elif not price_ok:
            sig = "Wait"
            tc  = "#721c24"; tbg = "#f8d7da"; tbr = "#f5c6cb"
            if cur < eq:
                l1  = l1 + f" ⛔ Price gate failed — not in Deep Discount (need >= {PRICE_GATE}/{W_PRICE})"
        elif not liq_ok:
            sig = "Wait"
            tc  = "#721c24"; tbg = "#f8d7da"; tbr = "#f5c6cb"
            l3  = l3 + " ⏳ Liquidity gate pending — waiting for Sweep & Reverse (need 20/20)"
        else:
            sig,tc,tbg,tbr = sig_info(total)

        entry_zones = None
        if price_ok and liq_ok and r8 > 0 and total >= 35:
            entry_zones = calc_entry_zones(df, cur, hi, lo, eq, buy_hi, sell_lo, av, alo,
                                           _sv=sv_result, _hvn=hvn_result)

        # ── Pattern Recognition + Historical Backtesting ──────────────────────
        pattern_data = analyze_entry_patterns(df)

        return {
            "ok":True,"price":round(cur,2),"last_dt":last_dt,
            "is_fresh":is_fresh,"price_src":src,
            "target":round(cur*1.12,2),
            "eq":round(eq,2),"buy_hi":round(buy_hi,2),"sell_lo":round(sell_lo,2),
            "avwap":round(av,2),"avwap_l":round(alo,2),
            "score":total,"signal":sig,"tc":tc,"tbg":tbg,"tbr":tbr,"r1":r1,
            "entry_zones": entry_zones,
            "pattern": pattern_data,
            "rows":[
                ("Price Position",      r1,W_PRICE,l1),
                ("Liquidity Context",   r3,W_LIQ,  l3),
                ("Demand Zone (SV+VP)", r8,W_DZ,   l8),
                ("Order Block Quality", r2,W_OB,   l2),
                ("Higher Timeframe",    r4,W_HTF,  l4),
                ("Anchored VWAP",       r5,W_AVWAP,l5),
                ("MACD vs Zero",        r6,W_MACD, l6),
                ("Divergence",          r7,W_DIV,  l7),
            ],
        }
    except Exception as e:
        return {"ok":False,"error":str(e)}

# =========================================
# NEWS
# =========================================

def get_news(symbol):
    return [{"headline":"News aggregator synchronized","date_str":"","days_ago":0}]

# =========================================
# SAVE HISTORY
# =========================================

def save_history(stock, r):
    row = {"date": now_cairo().strftime("%Y-%m-%d"), "stock": stock,
           "company": NAMES.get(stock, stock), "price": r.get("price", "N/A"),
           "last_dt": r.get("last_dt", "N/A"), "fresh": r.get("is_fresh", False),
           "signal": r.get("signal", "N/A"), "score": r.get("score", 0),
           "target": r.get("target", "N/A")}
    f = "signals_history.csv"
    file_exists = os.path.exists(f)
    with open(f, "a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=row.keys())
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

# =========================================
# HTML HELPERS
# =========================================

def pill(sc,mx):
    pct=int(sc/mx*100) if mx else 0
    bg,fg=(("#d4edda","#155724") if pct>=70 else (("#fff3cd","#856404") if pct>=40 else ("#f8d7da","#721c24")))
    return f'<span style="display:inline-block;padding:2px 9px;border-radius:10px;font-size:12px;font-weight:bold;background:{bg};color:{fg};">{sc}/{mx}</span>'

def bar(score):
    fg="#1e7e34" if score>=70 else ("#856404" if score>=45 else "#b02a2a")
    f=max(2,score); e=100-f
    return (f'<table cellpadding="0" cellspacing="0" border="0" style="display:inline-table;vertical-align:middle;margin-right:6px;">'
            f'<tr><td width="{f}" height="10" bgcolor="{fg}"></td><td width="{e}" height="10" bgcolor="#e0e0e0"></td></tr></table>'
            f'<span style="font-weight:bold;color:{fg};font-size:14px;">{score}/100</span>')

def fresh_badge(is_fresh, last_dt):
    if is_fresh:
        return f'<span style="font-size:11px;padding:2px 7px;border-radius:6px;background:#d4edda;color:#155724;margin-left:8px;">✓ {last_dt}</span>'
    return f'<span style="font-size:11px;padding:2px 7px;border-radius:6px;background:#fff3cd;color:#856404;margin-left:8px;">⚠ Stale: {last_dt}</span>'

# =========================================
# BUILD REPORT
# =========================================

def build_ez_html(r):
    ez = r.get("entry_zones")
    if not ez:
        return ""

    def conf_badge(n):
        if n >= 3:   bg,fg,txt = "#155724","#fff",f"★★★ {n} confluences"
        elif n == 2: bg,fg,txt = "#856404","#fff",f"★★ {n} confluences"
        else:        bg,fg,txt = "#6c757d","#fff",f"★ {n} confluence"
        return (f'<span style="display:inline-block;padding:2px 8px;border-radius:8px;'
                f'font-size:11px;font-weight:bold;background:{bg};color:{fg};">{txt}</span>')

    def zone_row(num, color, z, cur_price):
        dist     = round(((z["center"] - cur_price) / cur_price) * 100, 1)
        dist_str = f"{dist:+.1f}%" if dist != 0 else "At current"
        label    = "Aggressive" if num==1 else ("Add / Average" if num==2 else "Deep Value")
        return (f'<tr style="border-bottom:1px solid #e8e8e8;">'
                f'<td style="padding:10px 12px;font-family:Arial,sans-serif;">'
                f'<span style="display:inline-block;width:10px;height:10px;border-radius:50%;'
                f'background:{color};margin-right:6px;"></span>'
                f'<b style="font-size:12px;color:#333;">Zone {num}</b>'
                f'<span style="font-size:11px;color:#777;margin-left:6px;">{label}</span></td>'
                f'<td style="padding:10px 12px;font-family:Arial,sans-serif;font-size:13px;'
                f'font-weight:bold;color:#1C4587;">{z["lo"]} – {z["hi"]} EGP</td>'
                f'<td style="padding:10px 12px;font-family:Arial,sans-serif;font-size:12px;'
                f'color:#555;">{z["label"]}</td>'
                f'<td style="padding:10px 12px;text-align:center;">{conf_badge(z["conf"])}</td>'
                f'<td style="padding:10px 12px;font-family:Arial,sans-serif;font-size:12px;'
                f'color:#888;">{dist_str}</td></tr>')

    cur = r["price"]
    z1,z2,z3 = ez["z1"],ez["z2"],ez["z3"]
    rc = "#155724" if ez["ret_from_avg"]>=10 else ("#856404" if ez["ret_from_avg"]>=5 else "#721c24")
    return (f'<div style="font-family:Arial,sans-serif;font-size:12px;font-weight:bold;'
            f'color:#1C4587;margin:16px 0 5px 0;letter-spacing:0.5px;'
            f'border-left:4px solid #1C4587;padding-left:8px;">ENTRY ZONES — AVERAGING STRATEGY</div>'
            f'<table width="100%" cellpadding="0" cellspacing="0" border="0" '
            f'style="border:1px solid #d0e4f7;border-collapse:collapse;background:#f4f8ff;">'
            f'<tr style="background:#1C4587;">'
            f'<th align="left" style="padding:7px 12px;font-family:Arial,sans-serif;font-size:11px;color:#fff;">Zone</th>'
            f'<th align="left" style="padding:7px 12px;font-family:Arial,sans-serif;font-size:11px;color:#fff;">Price Range</th>'
            f'<th align="left" style="padding:7px 12px;font-family:Arial,sans-serif;font-size:11px;color:#fff;">Basis</th>'
            f'<th align="center" style="padding:7px 12px;font-family:Arial,sans-serif;font-size:11px;color:#fff;">Confluence</th>'
            f'<th align="left" style="padding:7px 12px;font-family:Arial,sans-serif;font-size:11px;color:#fff;">vs Current</th></tr>'
            f'{zone_row(1,"#1e7e34",z1,cur)}'
            f'{zone_row(2,"#856404",z2,cur)}'
            f'{zone_row(3,"#b02a2a",z3,cur)}'
            f'</table>'
            f'<table width="100%" cellpadding="0" cellspacing="0" border="0" '
            f'style="margin:6px 0;background:#eef6ff;border:1px solid #d0e4f7;">'
            f'<tr><td style="padding:10px 14px;font-family:Arial,sans-serif;font-size:12px;color:#444;">'
            f'<b>Weighted Avg Entry:</b> <span style="color:#1C4587;font-weight:bold;font-size:14px;">{ez["avg_entry"]} EGP</span>'
            f'&nbsp;&nbsp;|&nbsp;&nbsp;<b>Conservative Target:</b> <span style="color:#155724;font-weight:bold;font-size:14px;">{ez["target"]} EGP</span>'
            f'&nbsp;&nbsp;|&nbsp;&nbsp;<b>Return from Avg:</b> <span style="color:{rc};font-weight:bold;font-size:14px;">+{ez["ret_from_avg"]}%</span>'
            f'</td></tr></table>')


def build_pattern_html(r):
    """Renders the Pattern Recognition + Backtesting block for a stock card."""
    p = r.get("pattern")
    if not p or not p.get("ok"):
        return ""

    ps   = p["pattern_score"]
    wr   = p["win_rate"] * 100
    gain = p["avg_gain"]
    days = p["avg_days"]
    cnt  = p["similar_count"]
    lbl  = p["label"]

    # Color based on pattern score
    if ps >= 70:
        bar_color = "#155724"; bg = "#d4edda"; border = "#c3e6cb"
        badge_txt = "Strong Historical Match"
    elif ps >= 45:
        bar_color = "#856404"; bg = "#fff3cd"; border = "#ffeeba"
        badge_txt = "Moderate Historical Match"
    else:
        bar_color = "#6c757d"; bg = "#f8f9fa"; border = "#dee2e6"
        badge_txt = "Weak Historical Match"

    bar_w = max(4, min(100, int(ps)))

    return (
        f'<div style="margin:10px 0 4px 0;font-family:Arial,sans-serif;font-size:12px;'
        f'font-weight:bold;color:#1C4587;letter-spacing:0.5px;border-left:4px solid #1C4587;'
        f'padding-left:8px;">PATTERN INTELLIGENCE — HISTORICAL ANALYSIS</div>'
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="border:1px solid {border};border-collapse:collapse;background:{bg};">'
        f'<tr><td style="padding:10px 14px;">'
        f'<table width="100%" cellpadding="0" cellspacing="0"><tr>'
        # Pattern Score
        f'<td width="28%" style="font-family:Arial,sans-serif;">'
        f'<div style="font-size:10px;color:#555;font-weight:bold;margin-bottom:4px;">PATTERN SCORE</div>'
        f'<div style="font-size:22px;font-weight:bold;color:{bar_color};">{ps:.0f}<span style="font-size:13px;">/100</span></div>'
        f'<div style="background:#e0e0e0;border-radius:4px;height:6px;margin-top:4px;">'
        f'<div style="width:{bar_w}%;background:{bar_color};height:6px;border-radius:4px;"></div></div>'
        f'</td>'
        # Win Rate
        f'<td width="18%" style="font-family:Arial,sans-serif;padding-left:12px;">'
        f'<div style="font-size:10px;color:#555;font-weight:bold;margin-bottom:4px;">WIN RATE</div>'
        f'<div style="font-size:22px;font-weight:bold;color:{bar_color};">{wr:.0f}<span style="font-size:13px;">%</span></div>'
        f'<div style="font-size:10px;color:#777;">{cnt} similar cases</div>'
        f'</td>'
        # Avg Gain
        f'<td width="18%" style="font-family:Arial,sans-serif;padding-left:12px;">'
        f'<div style="font-size:10px;color:#555;font-weight:bold;margin-bottom:4px;">AVG GAIN</div>'
        f'<div style="font-size:22px;font-weight:bold;color:#155724;">+{gain:.1f}<span style="font-size:13px;">%</span></div>'
        f'<div style="font-size:10px;color:#777;">in ~{days} days</div>'
        f'</td>'
        # Badge + label
        f'<td style="font-family:Arial,sans-serif;padding-left:12px;vertical-align:middle;">'
        f'<span style="display:inline-block;padding:3px 10px;border-radius:10px;font-size:11px;'
        f'font-weight:bold;background:{bar_color};color:#fff;">{badge_txt}</span>'
        f'<div style="font-size:11px;color:#555;margin-top:6px;">{lbl}</div>'
        f'</td>'
        f'</tr></table>'
        f'</td></tr></table>'
    )


FIB_LABELS = {0: "12% Min", 1: "23.6%", 2: "38.2%", 3: "50%", 4: "61.8%", 5: "100%", 6: "150%", 7: "200%"}

def _target_box_html(symbol, r, positions):
    pos = positions.get(symbol)
    if pos and pos.get("status") == "open":
        dyn_tgt = pos["target"]
        fib_lbl = FIB_LABELS.get(pos.get("current_level", 0), "—")
        return (
            '<div style="font-family:Arial,sans-serif;font-size:10px;color:#155724;font-weight:bold;letter-spacing:1px;">🎯 DYNAMIC TARGET</div>'
            f'<div style="font-family:Arial,sans-serif;font-size:17px;font-weight:bold;color:#155724;">{dyn_tgt:.2f} EGP</div>'
            f'<div style="font-family:Arial,sans-serif;font-size:10px;color:#0B5394;margin-top:2px;">Fib {fib_lbl}</div>'
        )
    return (
        '<div style="font-family:Arial,sans-serif;font-size:10px;color:#155724;font-weight:bold;letter-spacing:1px;">TARGET</div>'
        f'<div style="font-family:Arial,sans-serif;font-size:17px;font-weight:bold;color:#155724;">{r["target"]} EGP</div>'
        '<div style="font-family:Arial,sans-serif;font-size:11px;color:#888;margin-top:2px;">Initial</div>'
    )

def build_report(holiday_mode=False, last_trading=None, _cached_results=None):
    print("  Fetching Dow Jones status...")
    dj = get_dow_jones_status()
    dow_banner = build_dow_banner(dj)
    positions = load_open_positions()

    if _cached_results is not None:
        results = _cached_results
    else:
        tv_prefetch_all_quotes(STOCKS)   # one batch TV call instead of 26 serial calls
        results = {}
        workers = min(8, len(STOCKS))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_sym = {executor.submit(analyze, s): s for s in STOCKS}
            for future in as_completed(future_to_sym):
                s = future_to_sym[future]
                results[s] = future.result()
                print(f"  Done: {NAMES.get(s, s)}")
        for s in STOCKS:               # save_history writes CSV — keep it sequential
            save_history(s, results[s])

    # ── Sort stocks by score descending for the entire report ────────────────
    sorted_stocks = sorted(STOCKS, key=lambda s: results[s].get("score", 0), reverse=True)

    fresh_n=sum(1 for s in STOCKS if results[s].get("ok") and results[s].get("is_fresh"))
    stale  =[NAMES.get(s,s) for s in STOCKS if results[s].get("ok") and not results[s].get("is_fresh")]
    dq_c   ="#155724" if not stale else "#856404"
    dq_bg  ="#d4edda" if not stale else "#fff3cd"
    dq_msg =(f"All {fresh_n} stocks — data fully verified" if not stale else f"{fresh_n}/{len(STOCKS)} fresh")

    parts=[]
    holiday_banner=""
    if holiday_mode and last_trading:
        holiday_banner=f"""
<table width="100%" cellpadding="12" cellspacing="0" border="0" style="background:#fff3cd;border-bottom:3px solid #ffc107;">
  <tr><td style="font-family:Arial,sans-serif;font-size:14px;color:#856404;">
    <b>🏖 EGX Holiday / Weekend Today ({today_cairo()})</b> — Report forced to absolute latest active trading session: <b>{last_trading}</b>
  </td></tr>
</table>"""

    # ── Open Positions section ────────────────────────────────────────────────
    open_pos_rows = ""
    open_pos_list = [(sym, p) for sym, p in positions.items() if p.get("status") == "open"]
    open_pos_list.sort(key=lambda x: (
        ((results[x[0]]["price"] - x[1]["entry_price"]) / x[1]["entry_price"])
        if x[0] in results and results[x[0]].get("ok") else
        ((x[1].get("current_price", x[1]["entry_price"]) - x[1]["entry_price"]) / x[1]["entry_price"])
    ), reverse=True)
    if open_pos_list:
        for sym, p in open_pos_list:
            entry   = p["entry_price"]
            dyn_tgt = p["target"]
            if sym in results and results[sym].get("ok"):
                cur_price = results[sym]["price"]
            elif "current_price" in p:
                cur_price = p["current_price"]
            else:
                cur_price = "—"
            pnl_pct = ((float(cur_price) - entry) / entry * 100) if cur_price != "—" else None
            pnl_str = (f'+{pnl_pct:.1f}%' if pnl_pct and pnl_pct >= 0 else f'{pnl_pct:.1f}%') if pnl_pct is not None else "—"
            pnl_col = "#155724" if (pnl_pct or 0) >= 0 else "#721c24"
            entry_date = p.get("entry_date", "")[:10]
            entry_score = p.get("entry_score", 0)
            reinforced = p.get("reinforced", False)
            reinf_price = p.get("reinforcement_price")
            avg_price   = p.get("avg_price")
            if reinforced and reinf_price:
                entry_cell = (
                    f"{entry:.2f} EGP<br>"
                    f"<span style='font-size:11px;color:#c0392b;'>🔄 إعادة شراء: {reinf_price:.2f} EGP</span><br>"
                    f"<span style='font-size:11px;color:#7d3c98;font-weight:bold;'>متوسط: {avg_price:.2f} EGP</span>"
                )
            else:
                entry_cell = f"{entry:.2f} EGP"
            open_pos_rows += f"""
<tr style="border-bottom:1px solid #e8f0f8;">
  <td style="padding:9px 12px;font-family:Arial,sans-serif;font-size:13px;font-weight:bold;color:#1C4587;">{NAMES.get(sym, sym)}<br><span style="font-size:10px;color:#999;">{sym}</span></td>
  <td style="padding:9px 12px;font-family:Arial,sans-serif;font-size:13px;">{entry_cell}</td>
  <td style="padding:9px 12px;font-family:Arial,sans-serif;font-size:13px;color:{pnl_col};font-weight:bold;">{cur_price} EGP &nbsp;<span style="font-size:11px;">({pnl_str})</span></td>
  <td style="padding:9px 12px;font-family:Arial,sans-serif;font-size:13px;font-weight:bold;color:#0B5394;">{dyn_tgt:.2f} EGP</td>
  <td style="padding:9px 12px;font-family:Arial,sans-serif;font-size:11px;color:#666;">{entry_date}</td>
  <td style="padding:9px 12px;font-family:Arial,sans-serif;font-size:13px;font-weight:bold;color:#4a4a4a;text-align:center;">{entry_score}</td>
</tr>"""
        open_positions_block = f"""
<div style="font-family:Arial,sans-serif;font-size:13px;font-weight:bold;color:#0B5394;margin:20px 0 6px 0;letter-spacing:0.5px;">📊 Open Positions — Dynamic Target</div>
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="border:1px solid #c8daf5;border-collapse:collapse;margin-bottom:20px;">
  <tr style="background:#0B5394;">
    <th align="left" style="padding:8px 12px;font-family:Arial,sans-serif;font-size:11px;color:#fff;">Stock</th>
    <th align="left" style="padding:8px 12px;font-family:Arial,sans-serif;font-size:11px;color:#fff;">Entry Price</th>
    <th align="left" style="padding:8px 12px;font-family:Arial,sans-serif;font-size:11px;color:#fff;">Current Price</th>
    <th align="left" style="padding:8px 12px;font-family:Arial,sans-serif;font-size:11px;color:#fff;">Dynamic Target</th>
    <th align="left" style="padding:8px 12px;font-family:Arial,sans-serif;font-size:11px;color:#fff;">Entry Date</th>
    <th align="center" style="padding:8px 12px;font-family:Arial,sans-serif;font-size:11px;color:#fff;">Confidence</th>
  </tr>
  {open_pos_rows}
</table>"""
    else:
        open_positions_block = ""

    parts.append(f"""
{holiday_banner}
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#0B5394;">
  <tr><td style="padding:20px 24px;">
    <div style="font-family:Arial,sans-serif;color:#fff;font-size:22px;font-weight:bold;">EGX Institutional Swing Scanner</div>
    <div style="font-family:Arial,sans-serif;color:#bdd7f5;font-size:13px;margin-top:5px;">{fmt_cairo("%A, %d %B %Y  |  %H:%M")} Cairo</div>
  </td></tr>
</table>
{dow_banner}
<table width="100%" cellpadding="10" cellspacing="0" border="0" style="background:{dq_bg};border-bottom:1px solid #ccc;">
  <tr><td style="font-family:Arial,sans-serif;font-size:12px;color:{dq_c};">
    <b>Data Status:</b> {dq_msg}
  </td></tr>
</table>
{open_positions_block}""")

    wr=""
    for s in sorted_stocks:
        r=results[s]
        if not r["ok"] or r["score"]<35: continue
        _pg = PRICE_GATE_WHITELIST if s in WHITELIST else PRICE_GATE_NORMAL
        if r.get("r1", 0) < _pg: continue
        _,tc,tbg,tbr=sig_info(r["score"])
        in_portfolio = s in positions and positions[s].get("status") == "open"
        portfolio_badge = ' <span style="display:inline-block;padding:2px 7px;border-radius:10px;font-size:10px;font-weight:bold;background:#dbeafe;color:#1e40af;border:1px solid #93c5fd;">🔵 In Portfolio</span>' if in_portfolio else ""
        wr+=f"""
<tr style="border-bottom:1px solid #e0e0e0;">
  <td style="padding:10px 12px;font-family:Arial,sans-serif;">
    <b style="font-size:14px;">{NAMES.get(s,s)}</b> {fresh_badge(r["is_fresh"],r["last_dt"])}{portfolio_badge}<br>
    <span style="font-size:11px;color:#888;">{s} · {SECTORS.get(s,"")}</span></td>
  <td style="padding:10px 12px;font-family:Arial,sans-serif;font-size:14px;font-weight:bold;">{r["price"]} EGP</td>
  <td style="padding:10px 12px;">
    <span style="font-family:Arial,sans-serif;display:inline-block;padding:4px 12px;border-radius:14px;font-size:12px;font-weight:bold;background:{tbg};color:{tc};border:1px solid {tbr};">{r["signal"]}</span></td>
  <td style="padding:10px 12px;">{bar(r["score"])}</td>
  <td style="padding:10px 12px;font-family:Arial,sans-serif;font-size:14px;font-weight:bold;color:#155724;">
    {f'{positions[s]["target"]:.2f} EGP <span style="font-size:10px;color:#0B5394;">🎯 {FIB_LABELS.get(positions[s].get("current_level",0),"")}</span>' if s in positions and positions[s].get("status")=="open" else f'{r["target"]} EGP'}
  </td>
</tr>"""

    parts.append(f"""
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:20px 0;border:1px solid #c3e6cb;background:#f8fff8;">
  <tr style="background:#2e6b20;">
    <th align="left" style="padding:9px 12px;font-family:Arial,sans-serif;color:#fff;font-size:12px;">Company</th>
    <th align="left" style="padding:9px 12px;font-family:Arial,sans-serif;color:#fff;font-size:12px;">Price</th>
    <th align="left" style="padding:9px 12px;font-family:Arial,sans-serif;color:#fff;font-size:12px;">Signal</th>
    <th align="left" style="padding:9px 12px;font-family:Arial,sans-serif;color:#fff;font-size:12px;">SMC Score</th>
    <th align="left" style="padding:9px 12px;font-family:Arial,sans-serif;color:#fff;font-size:12px;">Target</th>
  </tr>
  {wr or '<tr><td colspan="5" style="padding:14px;font-family:Arial,sans-serif;color:#856404;">No stocks reached Watch threshold today.</td></tr>'}
</table>""")

    for s in sorted_stocks:
        r = results[s]
        if not r["ok"]:
            parts.append(f"""
<table width="100%" cellpadding="12" cellspacing="0" border="0" style="margin:24px 0;border-top:3px solid #b02a2a;background:#fff5f5;border:1px solid #f5c6cb;">
  <tr><td style="font-family:Arial,sans-serif;">
    <b style="color:#721c24;font-size:16px;">{NAMES.get(s,s)}</b> <span style="font-size:12px;color:#999;margin-left:8px;">{s}</span><br>
    <span style="color:#721c24;font-size:13px;">Error: {_html.escape(r.get("error","unknown"))}</span>
  </td></tr></table>"""); continue

        _,tc,tbg,tbr=sig_info(r["score"])
        ind_rows=""
        for nm,sc,mx,lb in r["rows"]:
            bg="#f0fff4" if sc==mx else ("#fff8f8" if sc==0 else "#fffdf0")
            ind_rows+=f"""
<tr style="background:{bg};border-bottom:1px solid #eee;">
  <td width="175" style="padding:9px 12px;font-family:Arial,sans-serif;font-size:12px;font-weight:bold;color:#444;border-right:1px solid #eee;">{nm}</td>
  <td width="65" style="padding:9px 12px;text-align:center;">{pill(sc,mx)}</td>
  <td style="padding:9px 12px;font-family:Arial,sans-serif;font-size:13px;color:#333;">{lb}</td>
</tr>"""

        ez_html = build_ez_html(r)
        parts.append(f"""
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:32px;border-top:3px solid #0B5394;">
  <tr><td style="padding:12px 0 2px 0;">
    <span style="font-family:Arial,sans-serif;font-size:18px;font-weight:bold;color:#1C4587;">{NAMES.get(s,s)}</span>
    <span style="font-family:Arial,sans-serif;font-size:12px;color:#aaa;margin-left:8px;">{s} · {SECTORS.get(s,"")}</span>
    {fresh_badge(r["is_fresh"],r["last_dt"])}
  </td></tr>
</table>
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{tbg};border:1px solid {tbr};margin:8px 0;">
  <tr>
    <td style="padding:14px 16px;">
      <div style="font-family:Arial,sans-serif;font-size:17px;font-weight:bold;color:{tc};">{r["signal"]}</div>
      <div style="font-family:Arial,sans-serif;font-size:13px;color:#444;margin-top:6px;">SMC Score: &nbsp;{bar(r["score"])}</div>
    </td>
    <td align="right" style="padding:14px 16px;">
      <div style="font-family:Arial,sans-serif;font-size:24px;font-weight:bold;color:#222;">{r["price"]} EGP</div>
    </td>
  </tr>
</table>
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:8px 0;">
  <tr>
    <td width="130" style="padding:10px 16px;background:#d4edda;border:1px solid #c3e6cb;text-align:center;">
      {_target_box_html(s, r, positions)}
    </td>
    <td width="12"></td>
    <td style="padding:10px 14px;background:#f4f8ff;border:1px solid #d0e4f7;font-family:Arial,sans-serif;font-size:12px;color:#444;">
      <b>EQ (0.50):</b> {r["eq"]} &nbsp;|&nbsp; <b>Buy Zone Top (0.15):</b> {r["buy_hi"]} &nbsp;|&nbsp; <b>Sell Zone Floor (0.85):</b> {r["sell_lo"]} &nbsp;|&nbsp; <b>AVWAP:</b> {r["avwap"]} &nbsp;|&nbsp; <b>AVWAP Lower:</b> {r["avwap_l"]}
    </td>
  </tr>
</table>
<div style="font-family:Arial,sans-serif;font-size:12px;font-weight:bold;color:#555;margin:12px 0 5px 0;letter-spacing:0.5px;">SMC INDICATOR BREAKDOWN</div>
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="border:1px solid #e0e0e0;border-collapse:collapse;">
  <tr style="background:#f5f5f5;border-bottom:1px solid #ddd;">
    <th width="175" align="left" style="padding:7px 12px;font-family:Arial,sans-serif;font-size:11px;color:#666;border-right:1px solid #eee;">Indicator</th>
    <th width="65" align="center" style="padding:7px 12px;font-family:Arial,sans-serif;font-size:11px;color:#666;">Score</th>
    <th align="left" style="padding:7px 12px;font-family:Arial,sans-serif;font-size:11px;color:#666;">Reading</th>
  </tr>
  {ind_rows}
</table>
{ez_html}
{build_pattern_html(r)}
""")

    parts.append(f"""
<table width="100%" cellpadding="12" cellspacing="0" border="0" style="margin-top:30px;background:#f0f0f0;border-top:1px solid #ddd;">
  <tr><td align="center" style="font-family:Arial,sans-serif;font-size:11px;color:#999;">EGX Institutional Scanner · TradingView Data Engine</td></tr>
</table>""")

    html = f"""<!DOCTYPE html><html><body style="margin:0;padding:20px;background:#eef2f7;"><table width="680" cellpadding="0" cellspacing="0" border="0" align="center" style="background:#ffffff;border:1px solid #d0d7e2;"><tr><td style="padding:0 24px 24px 24px;">{"".join(parts)}</td></tr></table></body></html>"""
    return html, results

# =========================================
# EMAIL
# =========================================

def send_email(html, subject_suffix=""):
    sender  = os.getenv("EMAIL_USER")
    password= os.getenv("EMAIL_PASS")
    if not sender or not password:
        print("ERROR: EMAIL_USER or EMAIL_PASS not set."); return False
    msg=MIMEMultipart("alternative")
    date_str=now_cairo().strftime("%Y-%m-%d")
    msg["Subject"]=f"EGX Scanner — {date_str}{subject_suffix}"
    msg["From"]=sender; msg["To"]=EMAIL
    msg.attach(MIMEText(html,"html","utf-8"))
    try:
        with smtplib.SMTP("smtp.gmail.com",587,timeout=30) as srv:
            srv.ehlo(); srv.starttls(); srv.ehlo()
            srv.login(sender,password)
            srv.sendmail(sender,EMAIL,msg.as_string())
            print("Email sent successfully."); return True
    except Exception as e:
        print(f"Email error: {e}"); traceback.print_exc()
    return False

# =========================================
# TELEGRAM ALERTS
# =========================================

def send_telegram_zone3_reinforcement(symbol, entry_price, reinforcement_price, avg_price):
    """Send alert when Zone 3 reinforcement is triggered"""
    token   = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False

    name = NAMES.get(symbol, symbol)
    drop_pct = ((reinforcement_price - entry_price) / entry_price) * 100

    def fib_levels_str(ep):
        levels = [
            (12.0,  ep * 1.120),
            (23.6,  ep * 1.236),
            (38.2,  ep * 1.382),
            (50.0,  ep * 1.500),
        ]
        return "\n".join(
            f"   {'حد أدنى 12%' if pct == 12.0 else f'🎯 {pct}%':14}: {price:.2f} EGP"
            for pct, price in levels
        )

    message = (
        f"🔄 *تعزيز Zone 3 — إضافة للمركز*\n\n"
        f"📊 السهم: *{name}* `{symbol}`\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🟢 *الشراء الأول*\n"
        f"   سعر الدخول  : {entry_price:.2f} EGP\n"
        f"{fib_levels_str(entry_price)}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔵 *التعزيز (Zone 3)*\n"
        f"   سعر التعزيز : {reinforcement_price:.2f} EGP\n"
        f"   ⚠️ إعادة شراء\n"
        f"{fib_levels_str(reinforcement_price)}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📐 *متوسط السعر الجديد: {avg_price:.2f} EGP*\n\n"
        f"⚠️ الخروج عند أول ضعف بعد 12%\n"
        f"   الهدف يرتفع تلقائياً بلا حد أقصى\n\n"
        f"📉 الهبوط من الدخول: *{drop_pct:.1f}%*\n"
        f"⏰ {now_cairo().strftime('%H:%M | %d-%m-%Y')}"
    )

    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"},
            timeout=10,
        )
        return True
    except Exception as e:
        print(f"❌ Telegram error: {e}")
        return False


def send_telegram_target_update(symbol, entry_price, old_target, new_target, current_price, fib_level):
    """Send alert when dynamic target is updated"""
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        return False

    old_pct = ((old_target - entry_price) / entry_price) * 100
    new_pct = ((new_target - entry_price) / entry_price) * 100

    message = (
        f"🚀 *تحديث التارجت الديناميكي*\n\n"
        f"📊 السهم: *{NAMES.get(symbol, symbol)}* `{symbol}`\n"
        f"💰 سعر الدخول: {entry_price:.2f} EGP\n"
        f"📈 السعر الحالي: {current_price:.2f} EGP\n\n"
        f"🎯 التارجت القديم: {old_target:.2f} (*{old_pct:.2f}%*)\n"
        f"⬆️ التارجت الجديد: {new_target:.2f} (*{new_pct:.2f}%*)\n"
        f"📍 مستوى Fibonacci: *{fib_level:.1f}%*\n\n"
        f"⏰ الوقت: {now_cairo().strftime('%H:%M:%S')}"
    )

    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"},
            timeout=10,
        )
        return True
    except Exception as e:
        print(f"❌ Telegram error: {e}")
        return False

# =========================================
# POSITION TRACKING & MANAGEMENT
# =========================================

def load_open_positions():
    """Load open positions from JSON file"""
    global open_positions
    if os.path.exists(POSITIONS_FILE):
        try:
            with open(POSITIONS_FILE, 'r') as f:
                open_positions = json.load(f)
        except Exception as e:
            print(f"⚠️ Error loading positions: {e}")
            open_positions = {}
    return open_positions

def save_open_positions():
    """Save open positions to JSON file"""
    try:
        with open(POSITIONS_FILE, 'w') as f:
            json.dump(open_positions, f, indent=2)
    except Exception as e:
        print(f"❌ Error saving positions: {e}")

def add_position(symbol, entry_price, entry_date, volatility_min_target=0.12, entry_score=0):
    """Add new position when entry signal is triggered"""
    global open_positions

    # حساب أهداف Fibonacci
    fib_levels = [0.236, 0.382, 0.50, 0.618, 1.0, 1.5, 2.0]
    min_tgt = entry_price * (1 + volatility_min_target)
    fib_targets = [min_tgt]
    for lv in fib_levels:
        p = entry_price * (1 + lv)
        if p >= min_tgt:
            fib_targets.append(p)

    open_positions[symbol] = {
        "entry_date": entry_date,
        "entry_price": entry_price,
        "fib_targets": fib_targets,
        "current_level": 0,
        "target": fib_targets[0],
        "status": "open",
        "entry_score": entry_score,
    }
    save_open_positions()
    print(f"✅ Position added: {symbol} @ {entry_price:.2f} EGP")

def update_position_target(symbol, new_level, current_price):
    """Update position target and send notification"""
    global open_positions

    if symbol not in open_positions:
        return False

    pos = open_positions[symbol]
    old_target = pos["target"]
    old_level = pos["current_level"]

    if new_level >= len(pos["fib_targets"]):
        return False

    pos["current_level"] = new_level
    pos["target"] = pos["fib_targets"][new_level]   # new_level = التارجت التالي غير المتجاوز
    save_open_positions()

    # إرسال تنبيه
    fib_pct = ((pos["target"] - pos["entry_price"]) / pos["entry_price"]) * 100
    send_telegram_target_update(
        symbol,
        pos["entry_price"],
        old_target,
        pos["target"],
        current_price,
        fib_pct
    )

    print(f"🚀 {symbol}: Target raised from {old_target:.2f} to {pos['target']:.2f}")
    return True

def close_position(symbol, exit_price, reason="manual"):
    """Close position and record the trade"""
    global open_positions

    if symbol not in open_positions:
        return False

    pos = open_positions[symbol]
    pnl = exit_price - pos["entry_price"]
    pnl_pct = (pnl / pos["entry_price"]) * 100

    pos["status"] = "closed"
    pos["exit_price"] = exit_price
    pos["exit_reason"] = reason
    pos["pnl"] = pnl
    pos["pnl_pct"] = pnl_pct
    save_open_positions()

    print(f"❌ Position closed: {symbol} | PnL: {pnl_pct:.2f}%")
    return True

def monitor_positions(current_prices):
    """Monitor open positions and update targets"""
    global open_positions

    for symbol in list(open_positions.keys()):
        if open_positions[symbol]["status"] != "open":
            continue

        if symbol not in current_prices:
            continue

        price = current_prices[symbol]
        pos = open_positions[symbol]
        fib_targets = pos["fib_targets"]

        # إيجاد أول تارجت لم يُتجاوز بعد (next_level = index التارجت التالي المطلوب)
        next_level = pos["current_level"]
        for i in range(pos["current_level"], len(fib_targets)):
            if price >= fib_targets[i]:
                next_level = i + 1
            else:
                break
        next_level = min(next_level, len(fib_targets) - 1)

        if next_level > pos["current_level"]:
            update_position_target(symbol, next_level, price)

def monitor_reinforcement(current_prices, results):
    """Check if any open position has hit Zone 3 — trigger re-buy reinforcement once."""
    global open_positions

    for symbol in list(open_positions.keys()):
        pos = open_positions[symbol]
        if pos["status"] != "open" or pos.get("reinforced"):
            continue
        if symbol not in current_prices or symbol not in results:
            continue
        ez = results[symbol].get("entry_zones")
        if not ez or "z3" not in ez:
            continue
        z3 = ez["z3"]
        cur = current_prices[symbol]
        if z3["lo"] <= cur <= z3["hi"]:
            entry_price = pos["entry_price"]
            avg_price = round((entry_price + cur) / 2, 2)
            open_positions[symbol]["reinforced"] = True
            open_positions[symbol]["reinforcement_price"] = round(cur, 2)
            open_positions[symbol]["avg_price"] = avg_price
            save_open_positions()
            print(f"🔄 Z3 Reinforcement triggered: {symbol} @ {cur:.2f} (avg {avg_price:.2f})")
            send_telegram_zone3_reinforcement(symbol, entry_price, round(cur, 2), avg_price)


def send_telegram_alerts(results):
    """
    Send a Telegram message for every stock with score >= 35.
    Requires TELEGRAM_TOKEN and TELEGRAM_CHAT_ID env vars.
    """
    token   = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("Telegram: TELEGRAM_TOKEN or TELEGRAM_CHAT_ID not set — skipping.")
        return

    # Load open positions
    positions = load_open_positions()

    # Collect qualifying stocks sorted by score descending
    alerts = [
        (s, results[s])
        for s in STOCKS
        if results[s].get("ok") and results[s].get("score", 0) >= 35
    ]
    alerts.sort(key=lambda x: x[1].get("score", 0), reverse=True)

    if not alerts:
        # Send a "nothing today" summary so you know the scan ran
        msg = (
            f"📊 *EGX Daily Scan — {now_cairo().strftime('%d %b %Y')}*\n"
            f"No stocks reached the Watch threshold (≥35) today."
        )
        open_pos = [(s, p) for s, p in positions.items() if p.get("status") == "open"]
        open_pos.sort(key=lambda x: (
            ((results[x[0]]["price"] - x[1]["entry_price"]) / x[1]["entry_price"])
            if x[0] in results and results[x[0]].get("ok") else
            ((x[1].get("current_price", x[1]["entry_price"]) - x[1]["entry_price"]) / x[1]["entry_price"])
        ), reverse=True)
        if open_pos:
            msg += f"\n\n━━━━━━━━━━━━━━━━━━━━━"
            msg += f"\n📂 *Open Positions ({len(open_pos)})*\n"
            for sym, pos in open_pos:
                entry = pos["entry_price"]
                tgt   = pos["target"]
                if sym in results and results[sym].get("ok"):
                    cur_price = results[sym].get("price", "—")
                elif "current_price" in pos:
                    cur_price = pos["current_price"]
                else:
                    cur_price = "—"
                if cur_price != "—":
                    pnl_pct = ((float(cur_price) - entry) / entry * 100)
                    pnl = f"+{pnl_pct:.1f}%" if pnl_pct >= 0 else f"{pnl_pct:.1f}%"
                    cur_str = f"{cur_price} EGP ({pnl})"
                else:
                    cur_str = "—"
                score_str = f" | Score {pos.get('entry_score', 0)}" if pos.get('entry_score') else ""
                msg += f"\n📌 *{sym}* — {NAMES.get(sym, sym)}"
                msg += f"\n   Entry {entry:.2f} | Now {cur_str} | Target *{tgt:.2f} EGP*{score_str}"
                if pos.get("reinforced") and pos.get("reinforcement_price"):
                    msg += f"\n   🔄 إعادة شراء: {pos['reinforcement_price']:.2f} EGP"
                    msg += f"\n   📐 متوسط السعر: *{pos['avg_price']:.2f} EGP*"
                msg += "\n"
            msg += "━━━━━━━━━━━━━━━━━━━━━"
        try:
            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"},
                timeout=10,
            )
        except Exception as e:
            print(f"Telegram error: {e}")
        return

    # Build one summary message with all qualifying stocks
    date_str = now_cairo().strftime("%d %b %Y")
    lines = [f"📊 *EGX Daily Scan — {date_str}*\n_{len(alerts)} stock(s) above threshold_"]

    # Add open positions section if any exist
    open_positions_list = [(s, p) for s, p in positions.items() if p.get("status") == "open"]
    open_positions_list.sort(key=lambda x: (
        ((results[x[0]]["price"] - x[1]["entry_price"]) / x[1]["entry_price"])
        if x[0] in results and results[x[0]].get("ok") else
        ((x[1].get("current_price", x[1]["entry_price"]) - x[1]["entry_price"]) / x[1]["entry_price"])
    ), reverse=True)
    if open_positions_list:
        lines.append("\n━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"📂 *Open Positions ({len(open_positions_list)})*\n")
        for sym, pos in open_positions_list:
            entry = pos["entry_price"]
            tgt   = pos["target"]
            if sym in results and results[sym].get("ok"):
                cur_price = results[sym].get("price", "—")
            elif "current_price" in pos:
                cur_price = pos["current_price"]
            else:
                cur_price = "—"
            if cur_price != "—":
                pnl_pct = ((float(cur_price) - entry) / entry * 100)
                pnl = f"+{pnl_pct:.1f}%" if pnl_pct >= 0 else f"{pnl_pct:.1f}%"
                cur_str = f"{cur_price} EGP ({pnl})"
            else:
                cur_str = "—"
            score_str = f" | Score {pos.get('entry_score', 0)}" if pos.get('entry_score') else ""
            lines.append(f"📌 *{sym}* — {NAMES.get(sym, sym)}")
            pos_line = f"   Entry {entry:.2f} | Now {cur_str} | Target *{tgt:.2f} EGP*{score_str}"
            lines.append(pos_line)
            if pos.get("reinforced") and pos.get("reinforcement_price"):
                lines.append(f"   🔄 إعادة شراء: {pos['reinforcement_price']:.2f} EGP")
                lines.append(f"   📐 متوسط السعر: *{pos['avg_price']:.2f} EGP*")
            lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━\n")

    SIGNAL_EMOJI = {
        "STRONG BUY":  "🟢",
        "BUY":         "🟩",
        "WATCH":       "🟡",
        "NEUTRAL":     "⚪",
        "SELL":        "🔴",
        "STRONG SELL": "🔴",
    }

    for s, r in alerts:
        signal_upper = r.get("signal", "").upper()
        emoji        = SIGNAL_EMOJI.get(signal_upper, "🔵")
        fresh_flag   = "✅" if r.get("is_fresh") else "⚠️"
        is_buy       = signal_upper in ("BUY", "STRONG BUY")

        in_portfolio = s in positions and positions[s].get("status") == "open"
        portfolio_tag = "  🔵 _In Portfolio_" if in_portfolio else ""

        if is_buy:
            # Full details for BUY / STRONG BUY
            # Use dynamic target if position is open, otherwise use static target
            target_to_display = r["target"]
            if in_portfolio:
                target_to_display = positions[s]["target"]

            upside = ""
            try:
                pct    = (float(target_to_display) - float(r["price"])) / float(r["price"]) * 100
                upside = f" (+{pct:.1f}%)"
            except Exception:
                pass
            lines.append(
                f"{emoji} *{NAMES.get(s, s)}* `{s}`{portfolio_tag}\n"
                f"   Signal: *{r['signal']}*  |  Score: *{r['score']}/100*\n"
                f"   Price: *{r['price']} EGP*  →  Target: *{target_to_display} EGP*{upside}\n"
                f"   Data: {fresh_flag} {'Fresh' if r.get('is_fresh') else 'Stale'}\n"
            )
        else:
            # WATCH only — no target, no buy mention
            lines.append(
                f"{emoji} *{NAMES.get(s, s)}* `{s}`{portfolio_tag}\n"
                f"   👀 Watch  |  Score: *{r['score']}/100*\n"
                f"   Price: *{r['price']} EGP*\n"
                f"   Data: {fresh_flag} {'Fresh' if r.get('is_fresh') else 'Stale'}\n"
            )

    full_msg = "\n".join(lines)

    # Telegram limit: 4096 chars per message — split if needed
    MAX = 4000
    chunks = []
    current = ""
    for line in full_msg.split("\n"):
        if len(current) + len(line) + 1 > MAX:
            chunks.append(current)
            current = line + "\n"
        else:
            current += line + "\n"
    if current:
        chunks.append(current)

    for chunk in chunks:
        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": chunk, "parse_mode": "Markdown"},
                timeout=10,
            )
            if resp.status_code == 200:
                print(f"Telegram: chunk sent ({len(chunk)} chars)")
            else:
                print(f"Telegram: HTTP {resp.status_code} — {resp.text[:200]}")
        except Exception as e:
            print(f"Telegram error: {e}")


# =========================================
# ALERT FOR HIGH SCORE (REAL-TIME)
# =========================================

def send_alert_for_high_score(stock, score, result):
    """
    إرسال تنبيه فوري عندما يصل score إلى 35+
    """
    print(f"\n🚨 ALERT: {NAMES.get(stock, stock)} ({stock}) وصل score {score}/100!")
    
    # إرسال Telegram
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if token and chat_id:
        signal = result.get("signal", "WATCH").upper()
        emoji_map = {
            "STRONG BUY": "🟢",
            "BUY": "🟩",
            "WATCH": "🟡",
        }
        emoji = emoji_map.get(signal, "🔵")
        
        try:
            upside = ""
            try:
                pct = (float(result["target"]) - float(result["price"])) / float(result["price"]) * 100
                upside = f" (+{pct:.1f}%)"
            except:
                pass
            
            msg = (
                f"🚨 *ALERT* — {emoji} {NAMES.get(stock, stock)}\n"
                f"Score: *{score}/100*  |  Signal: *{signal}*\n"
                f"Price: *{result['price']} EGP*\n"
                f"Target: *{result['target']} EGP*{upside}\n"
                f"Time: {now_cairo().strftime('%H:%M:%S')}"
            )
            
            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"},
                timeout=10,
            )
            print(f"✅ Telegram alert sent for {stock}")
        except Exception as e:
            print(f"❌ Telegram alert error: {e}")




# =========================================
# UTILITY HELPERS
# =========================================

def is_market_hours():
    """True if current Cairo time is between 10:00 and 14:30."""
    now = now_cairo()
    t = now.hour * 60 + now.minute
    return 600 <= t <= 870   # 10:00–14:30

def is_trading_day_today():
    """Alias for is_egx_trading_day() using today's date."""
    return is_egx_trading_day(today_cairo())

# =========================================
# SCHEDULED TASKS
# =========================================

def _collect_current_prices(results):
    return {
        s: results[s]["price"] for s in STOCKS
        if results[s].get("ok")
        and isinstance(results[s].get("price"), (int, float))
        and results[s]["price"] > 0
    }

def _register_new_positions(results):
    """Register positions for all qualifying stocks not already tracked."""
    qualifying = {
        s for s in STOCKS
        if results[s].get("ok")
        and results[s].get("score", 0) >= 35
        and results[s].get("r1", 0) >= 18
    }
    for stock in qualifying:
        positions = load_open_positions()
        if stock not in positions:
            price = results[stock].get("price", 0)
            if price > 0:
                add_position(stock, price, datetime.now(CAIRO).isoformat(),
                             entry_score=results[stock].get("score", 0))
                print(f"📌 تسجيل مركز جديد: {NAMES.get(stock, stock)} @ {price}")

def _run_scan_workflow(holiday_mode, last_trading, email_suffix):
    """
    Shared workflow for daily and manual scans:
    1. Fetch data once
    2. Register new positions + update targets
    3. Rebuild HTML from cached data (no re-fetch)
    4. Send email + Telegram
    5. Save results + detect changes
    """
    previous_results = load_previous_results()

    # Step 1: fetch data
    html, results = build_report(holiday_mode=holiday_mode, last_trading=last_trading)

    # Step 2: register positions, update targets
    _register_new_positions(results)
    cur_prices = _collect_current_prices(results)
    monitor_positions(cur_prices)
    monitor_reinforcement(cur_prices, results)

    # Step 3: rebuild HTML using cached prices (no extra HTTP calls)
    html, _ = build_report(holiday_mode=holiday_mode, last_trading=last_trading,
                           _cached_results=results)

    # Step 4: send
    send_email(html, subject_suffix=email_suffix)
    send_telegram_alerts(results)

    # Step 5: persist + change alerts
    save_scan_results(results)
    save_signal_history(results)
    changes = detect_signal_changes(results, previous_results)
    if changes:
        send_change_alert(changes)


def daily_scan():
    print(f"\n📅 Daily scan started at {fmt_cairo()}")
    if is_egx_trading_day(today_cairo()):
        _run_scan_workflow(holiday_mode=False, last_trading=None, email_suffix="")
    else:
        last_td = most_recent_trading_day(today_cairo())
        _run_scan_workflow(
            holiday_mode=True,
            last_trading=str(last_td),
            email_suffix=f" (Holiday — Last Session: {last_td})",
        )
    print("\n✅ Daily scan completed!")


def continuous_scan():
    print(f"\n🔄 Continuous scan at {fmt_cairo()}")
    previous_results = load_previous_results()
    html, current_results = build_report(holiday_mode=False)
    save_scan_results(current_results)
    save_signal_history(current_results)
    changes = detect_signal_changes(current_results, previous_results)
    if changes:
        print(f"🚨 Found {len(changes)} signal change(s)!")
        send_change_alert(changes)
    else:
        print("ℹ️ No signal changes detected")


def manual_scan():
    print(f"\n🔄 Manual scan at {fmt_cairo()}")
    holiday = not is_egx_trading_day(today_cairo())
    last_td = most_recent_trading_day(today_cairo()) if holiday else None
    suffix = f" — Manual Scan{' (Holiday)' if holiday else ''}"
    _run_scan_workflow(
        holiday_mode=holiday,
        last_trading=str(last_td) if last_td else None,
        email_suffix=suffix,
    )
    print("\n✅ Manual scan completed!")

# =========================================
# PERSISTENT STATE MANAGEMENT
# =========================================

def save_scan_results(results):
    """
    حفظ نتائج المسح في ملف JSON
    """
    try:
        with open("scan_results.json", "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2, default=str)
        print(f"✅ Results saved to scan_results.json")
    except Exception as e:
        print(f"❌ Error saving results: {e}")


_SIGNAL_HISTORY_DAYS = 365  # keep rolling window of this many days

def save_signal_history(results):
    """
    Append today's per-stock scan data to signal_history.json for heatmap.
    Keeps a rolling window of _SIGNAL_HISTORY_DAYS to prevent unbounded growth.
    """
    try:
        today = date.today().isoformat()
        cutoff = (date.today() - timedelta(days=_SIGNAL_HISTORY_DAYS)).isoformat()
        hist = {}
        if os.path.exists("signal_history.json"):
            with open("signal_history.json", "r", encoding="utf-8") as f:
                hist = json.load(f)
        for ticker, d in results.items():
            if not isinstance(d, dict) or not d.get("ok"):
                continue
            entry = {
                "date":   today,
                "score":  d.get("score", 0),
                "price":  d.get("price", 0),
                "r1":     d.get("r1", 0),
                "signal": d.get("signal", ""),
            }
            stock_hist = hist.setdefault(ticker, [])
            # replace if same date already exists, otherwise append
            existing = [i for i, e in enumerate(stock_hist) if e.get("date") == today]
            if existing:
                stock_hist[existing[0]] = entry
            else:
                stock_hist.append(entry)
            # prune entries older than the rolling window
            hist[ticker] = [e for e in stock_hist if e.get("date", "") >= cutoff]
        with open("signal_history.json", "w", encoding="utf-8") as f:
            json.dump(hist, f, ensure_ascii=False, separators=(",", ":"))
        print(f"✅ signal_history.json updated ({today})")
    except Exception as e:
        print(f"❌ Error saving signal history: {e}")


def load_previous_results():
    """
    تحميل نتائج المسح السابق من JSON
    """
    try:
        if os.path.exists("scan_results.json"):
            with open("scan_results.json", "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"⚠️ Error loading previous results: {e}")
    return {}


def detect_signal_changes(current_results, previous_results):
    """
    كشف التغييرات في الإشارات (من Wait إلى BUY/STRONG BUY)
    """
    changed_stocks = []
    
    for stock in STOCKS:
        current = current_results.get(stock, {})
        previous = previous_results.get(stock, {})
        
        current_sig = current.get("signal", "Skip")
        previous_sig = previous.get("signal", "Skip")
        current_score = current.get("score", 0)
        current_price = current.get("price", "N/A")
        current_target = current.get("target", "N/A")

        # إذا تغيرت الإشارة من Skip/Wait إلى أي إشارة شراء
        BUY_SIGNALS = {"Buy", "Strong Buy", "Very Strong Buy", "Institutional Buy"}
        if previous_sig in ("Skip", "Wait") and current_sig in BUY_SIGNALS:
            changed_stocks.append({
                "stock": stock,
                "from": previous_sig,
                "to": current_sig,
                "score": current_score,
                "price": current_price,
                "target": current_target,
                "entry_zones": current.get("entry_zones", None),
            })
    
    return changed_stocks


def send_change_email(changed_stocks):
    """
    إرسال Email فوري عند تغيير أي سهم (whitelist أو عادي) إلى BUY
    """
    if not changed_stocks:
        return

    sender   = os.getenv("EMAIL_USER")
    password = os.getenv("EMAIL_PASS")
    if not sender or not password:
        print("⚠️ Email config missing for change alert")
        return

    time_str = fmt_cairo()

    def _gain_str(price, target):
        try:
            pct = round(((float(target) - float(price)) / float(price)) * 100, 1)
            return f"+{pct}%"
        except Exception:
            return ""

    def _stock_card(item, is_whitelist):
        stock  = item["stock"]
        price  = item.get("price", "N/A")
        target = item.get("target", "N/A")
        score  = item.get("score", 0)
        signal = item.get("to", "Buy")
        ez     = item.get("entry_zones")

        gain  = _gain_str(price, target)
        bar_w = min(int(score), 100)
        # gradient spans the filled portion — short bars stay amber, long bars reach deep green
        bar_gradient = "linear-gradient(90deg,#f59e0b 0%,#eab308 25%,#84cc16 50%,#22c55e 75%,#16a34a 100%)"

        # Zone 1 → سعر الدخول المقترح
        entry_price = price
        if ez and "z1" in ez:
            entry_price = ez["z1"]["center"]

        # Zone 3 → منطقة Deep Value
        z3_lo = z3_hi = None
        if ez and "z3" in ez:
            z3_lo = ez["z3"]["lo"]
            z3_hi = ez["z3"]["hi"]

        hdr_bg    = "#b45309" if is_whitelist else "#1d4ed8"
        hdr_label = f"⭐ {stock} — WHITELIST" if is_whitelist else f"📈 {stock}"

        if z3_lo is not None:
            dv_row = (
                f'<tr><td style="padding:0 16px 16px;">'
                f'<table width="100%" cellpadding="0" cellspacing="0" border="0"'
                f' style="background:#0d1117;border-radius:10px;border-left:4px solid #818cf8;">'
                f'<tr><td style="padding:12px 15px;">'
                f'<p style="color:#94a3b8;font-size:10px;text-transform:uppercase;'
                f'letter-spacing:1px;margin:0 0 8px 0;">🔷 منطقة Deep Value — Zone 3</p>'
                f'<table width="100%" cellpadding="0" cellspacing="0" border="0">'
                f'<tr>'
                f'<td style="color:#818cf8;font-size:14px;font-weight:bold;">{z3_lo} EGP</td>'
                f'<td align="center" style="color:#4b5563;font-size:13px;">↔</td>'
                f'<td align="right" style="color:#818cf8;font-size:14px;font-weight:bold;">{z3_hi} EGP</td>'
                f'</tr></table>'
                f'</td></tr></table>'
                f'</td></tr>'
            )
        else:
            dv_row = (
                f'<tr><td style="padding:0 16px 16px;">'
                f'<table width="100%" cellpadding="0" cellspacing="0" border="0"'
                f' style="background:#0d1117;border-radius:10px;border-left:4px solid #374151;">'
                f'<tr><td style="padding:10px 15px;">'
                f'<p style="color:#4b5563;font-size:11px;margin:0;">🔷 Deep Value Zone: غير متاح</p>'
                f'</td></tr></table>'
                f'</td></tr>'
            )

        return (
            f'<tr><td style="padding:3px 0 0;">'
            f'<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#1a1f36;">'

            # ── card header ──
            f'<tr><td style="background:{hdr_bg};padding:12px 18px;">'
            f'<table width="100%" cellpadding="0" cellspacing="0" border="0">'
            f'<tr>'
            f'<td style="color:#fff;font-size:15px;font-weight:bold;">{hdr_label}</td>'
            f'<td align="right">'
            f'<span style="background:rgba(0,0,0,0.28);color:#fff;padding:4px 12px;'
            f'border-radius:20px;font-size:12px;font-weight:bold;">{signal}</span>'
            f'</td>'
            f'</tr></table>'
            f'</td></tr>'

            # ── current price + target ──
            f'<tr><td style="padding:14px 16px 0;">'
            f'<table width="100%" cellpadding="0" cellspacing="0" border="0">'
            f'<tr>'
            f'<td width="48%" style="background:#0d1117;border-radius:10px;padding:14px;text-align:center;vertical-align:top;">'
            f'<p style="color:#64748b;font-size:10px;text-transform:uppercase;letter-spacing:1px;margin:0 0 5px 0;">السعر الحالي</p>'
            f'<p style="color:#f8fafc;font-size:22px;font-weight:bold;margin:0 0 2px 0;">{price}</p>'
            f'<p style="color:#64748b;font-size:11px;margin:0;">EGP</p>'
            f'</td>'
            f'<td width="4%">&nbsp;</td>'
            f'<td width="48%" style="background:#0d1117;border-radius:10px;padding:14px;text-align:center;vertical-align:top;">'
            f'<p style="color:#64748b;font-size:10px;text-transform:uppercase;letter-spacing:1px;margin:0 0 5px 0;">التارجت المستهدف</p>'
            f'<p style="color:#22c55e;font-size:22px;font-weight:bold;margin:0 0 2px 0;">{target}</p>'
            f'<p style="color:#22c55e;font-size:11px;margin:0;">{gain}</p>'
            f'</td>'
            f'</tr></table>'
            f'</td></tr>'

            # ── score bar ──
            f'<tr><td style="padding:12px 16px 0;">'
            f'<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#0d1117;border-radius:10px;">'
            f'<tr><td style="padding:12px 15px;">'
            f'<table width="100%" cellpadding="0" cellspacing="0" border="0">'
            f'<tr>'
            f'<td style="color:#94a3b8;font-size:11px;letter-spacing:0.5px;">Score</td>'
            f'<td align="right" style="color:#f8fafc;font-size:14px;font-weight:bold;">{score:.0f} / 100</td>'
            f'</tr></table>'
            f'<table width="100%" cellpadding="0" cellspacing="0" border="0"'
            f' style="margin-top:8px;background:#1e2641;border-radius:20px;overflow:hidden;">'
            f'<tr>'
            f'<td width="{bar_w}%" style="background:{bar_gradient};height:8px;border-radius:20px;font-size:1px;">&nbsp;</td>'
            f'<td style="height:8px;font-size:1px;">&nbsp;</td>'
            f'</tr></table>'
            f'</td></tr></table>'
            f'</td></tr>'

            # ── entry price (Zone 1) ──
            f'<tr><td style="padding:12px 16px 0;">'
            f'<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#0d1117;border-radius:10px;">'
            f'<tr><td style="padding:12px 15px;">'
            f'<table width="100%" cellpadding="0" cellspacing="0" border="0">'
            f'<tr>'
            f'<td style="color:#94a3b8;font-size:12px;">🎯 سعر الدخول</td>'
            f'<td align="right" style="color:#fbbf24;font-size:16px;font-weight:bold;">{entry_price} EGP</td>'
            f'</tr></table>'
            f'</td></tr></table>'
            f'</td></tr>'

            # ── deep value zone ──
            + dv_row +

            f'</table></td></tr>'
        )

    whitelist_stocks = [s for s in changed_stocks if s["stock"] in WHITELIST]
    normal_stocks    = [s for s in changed_stocks if s["stock"] not in WHITELIST]
    total_count      = len(changed_stocks)

    cards_html = ""

    if whitelist_stocks:
        cards_html += (
            f'<tr><td style="padding:18px 18px 8px;">'
            f'<p style="color:#f59e0b;font-size:12px;font-weight:bold;'
            f'letter-spacing:1.5px;margin:0;text-transform:uppercase;">'
            f'⭐ Whitelist Stocks ({len(whitelist_stocks)})</p>'
            f'<table width="100%" cellpadding="0" cellspacing="0" style="margin-top:6px;">'
            f'<tr><td style="background:#d97706;height:2px;border-radius:1px;"></td></tr>'
            f'</table></td></tr>'
        )
        for item in whitelist_stocks:
            cards_html += _stock_card(item, True)

    if normal_stocks:
        cards_html += (
            f'<tr><td style="padding:18px 18px 8px;">'
            f'<p style="color:#60a5fa;font-size:12px;font-weight:bold;'
            f'letter-spacing:1.5px;margin:0;text-transform:uppercase;">'
            f'📈 Stocks ({len(normal_stocks)})</p>'
            f'<table width="100%" cellpadding="0" cellspacing="0" style="margin-top:6px;">'
            f'<tr><td style="background:#3b82f6;height:2px;border-radius:1px;"></td></tr>'
            f'</table></td></tr>'
        )
        for item in normal_stocks:
            cards_html += _stock_card(item, False)

    html_body = (
        '<!DOCTYPE html><html><head>'
        '<meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '</head>'
        '<body style="margin:0;padding:0;background:#0d1117;font-family:Arial,Helvetica,sans-serif;">'
        '<table width="100%" cellpadding="0" cellspacing="0" border="0"'
        ' style="background:#0d1117;padding:24px 0;">'
        '<tr><td align="center">'
        '<table width="560" cellpadding="0" cellspacing="0" border="0"'
        ' style="max-width:560px;width:100%;">'

        # header
        '<tr><td style="background:#141928;border-radius:16px 16px 0 0;'
        'padding:28px 28px 20px;text-align:center;">'
        '<p style="color:#ef4444;font-size:32px;margin:0 0 10px;">🚨</p>'
        '<h1 style="color:#ffffff;font-size:22px;font-weight:bold;'
        'margin:0 0 8px;letter-spacing:2px;text-transform:uppercase;">Buy Signal Alert</h1>'
        f'<p style="color:#94a3b8;font-size:13px;margin:0 0 18px;">📅 {time_str}</p>'
        '<table width="100%" cellpadding="0" cellspacing="0">'
        '<tr><td style="background:#ef4444;height:3px;border-radius:2px;font-size:1px;">&nbsp;</td></tr>'
        '</table>'
        '</td></tr>'

        # cards wrapper
        '<tr><td style="background:#1a1f36;padding:0 18px;">'
        '<table width="100%" cellpadding="0" cellspacing="0" border="0">'
        + cards_html +
        '</table>'
        '</td></tr>'

        # footer
        '<tr><td style="background:#141928;border-radius:0 0 16px 16px;'
        'padding:14px;text-align:center;">'
        '<p style="color:#374151;font-size:11px;margin:0;letter-spacing:0.5px;">'
        'EGX SMC Scanner &copy; 2026</p>'
        '</td></tr>'

        '</table>'
        '</td></tr></table>'
        '</body></html>'
    )

    msg = MIMEMultipart("alternative")
    date_str = now_cairo().strftime("%Y-%m-%d %H:%M")
    msg["Subject"] = f"🚨 Signal Alert: {total_count} stock(s) moved to BUY — {date_str}"
    msg["From"]    = sender
    msg["To"]      = EMAIL
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as srv:
            srv.ehlo(); srv.starttls(); srv.ehlo()
            srv.login(sender, password)
            srv.sendmail(sender, EMAIL, msg.as_string())
        print(f"📧 Email alert sent for {total_count} stock(s) "
              f"({len(whitelist_stocks)} whitelist, {len(normal_stocks)} normal)")
        return True
    except Exception as e:
        print(f"❌ Email error: {e}")
        return False


def send_change_alert(changed_stocks):
    """
    إرسال تنبيه Telegram فوري عند تغيير الإشارة
    مع علامة مميزة ⭐ للأسهم من قائمة الـ whitelist
    + Email للجميع مع التمييز
    """
    if not changed_stocks:
        return
    
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        print("⚠️ Telegram config missing")
        return
    
    message = "🚨 **إشارة تغير إلى BUY!**\n\n"
    for item in changed_stocks:
        stock = item['stock']
        price = item.get('price', 'N/A')
        target = item.get('target', 'N/A')
        
        # ⭐ علامة مميزة للأسهم من الـ whitelist
        whitelist_badge = "⭐ **WHITELIST** ⭐" if stock in WHITELIST else ""
        
        message += f"📈 {stock}"
        if whitelist_badge:
            message += f" {whitelist_badge}\n"
        else:
            message += "\n"
        
        message += f"  └─ {item['from']} → {item['to']}\n"
        message += f"  └─ Score: {item['score']:.1f}\n"
        message += f"  └─ السعر الحالي: {price} EGP\n"
        message += f"  └─ السعر المستهدف: {target} EGP\n\n"
    
    # إرسال Telegram
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            print(f"✅ Signal change alert sent to Telegram")
        else:
            print(f"❌ Telegram error: {response.text}")
    except Exception as e:
        print(f"❌ Error sending Telegram alert: {e}")
    
    # إرسال Email للجميع مع التمييز
    send_change_email(changed_stocks)

# =========================================
# RUN
# =========================================

if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f"EGX SMC Scanner — GitHub Actions Mode")
    print(f"Start Time: {fmt_cairo()}")
    print(f"{'='*60}\n")
    
    # =========================================
    # DETERMINE RUN MODE BASED ON TIME
    # =========================================
    
    manual_run  = os.getenv("MANUAL_RUN",  "False") == "True"
    force_daily = os.getenv("FORCE_DAILY", "False") == "True"
    hour = now_cairo().hour
    minute = now_cairo().minute

    print(f"Current time: {hour:02d}:{minute:02d}")
    print(f"Manual run: {manual_run}")
    print(f"Force daily: {force_daily}\n")

    try:
        # =========================================
        # MODE 1: MANUAL RUN (Any time)
        # =========================================
        if manual_run:
            print("🔧 MANUAL RUN MODE")
            print("="*60 + "\n")
            print("🚀 Running manual scan now...\n")
            manual_scan()
            print("\n✅ Manual scan completed!")
            print("="*60 + "\n")
            sys.exit(0)

        # =========================================
        # MODE 2: DAILY SCAN (7:00 AM or force_daily)
        # =========================================
        elif force_daily or hour == 7:
            print("📅 DAILY SCAN MODE (7:00 AM)")
            print("="*60 + "\n")
            daily_scan()
            print("\n✅ Daily scan completed!")
            print("="*60 + "\n")
            sys.exit(0)
        
        # =========================================
        # MODE 3: CONTINUOUS SCAN (10:00 AM - 2:30 PM)
        # =========================================
        elif 10 <= hour <= 14:
            print("🔄 CONTINUOUS SCAN MODE (Market Hours)")
            print("="*60 + "\n")
            continuous_scan()
            print("\n✅ Continuous scan completed!")
            print("="*60 + "\n")
            sys.exit(0)
        
        # =========================================
        # NO ACTION (Outside configured times)
        # =========================================
        else:
            print(f"⏳ No action scheduled for {hour:02d}:{minute:02d}")
            print("   Configured times:")
            print("   - 09:00 (Daily Report)")
            print("   - 10:00-14:30 (Continuous Scan)")
            print("   - Any time (Manual Run)")
            print("="*60 + "\n")
            sys.exit(0)
    
    except Exception as e:
        print(f"\n❌ Error: {e}")
        traceback.print_exc()
        sys.exit(1)

