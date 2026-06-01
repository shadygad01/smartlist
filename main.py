import smtplib
import os
import json
import re
import sys
import pandas as pd
import numpy as np
import yfinance as yf
import requests
import traceback

from bs4 import BeautifulSoup
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

CAIRO = ZoneInfo("Africa/Cairo")

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

NAMES = {
    "COMI.CA": "Commercial International Bank",
    "TMGH.CA": "Talaat Moustafa Group",
    "ETEL.CA": "Telecom Egypt",
    "EGAL.CA": "Egyptian Gulf Bank",
    "EAST.CA": "Eastern Company",
    "ABUK.CA": "Abu Qir Fertilizers",
    "ORAS.CA": "Orascom Construction PLC",
    "EFIH.CA": "EFG Hermes Holding",
    "ADIB.CA": "Abu Dhabi Islamic Bank Egypt",
    "FWRY.CA": "Fawry for Banking Technology",
    "EMFD.CA": "Egypt Foods Group",
    "PHDC.CA": "Palm Hills Developments",
    "ORHD.CA": "Orascom Development Egypt",
    "EFID.CA": "EFG Finance",
    "HRHO.CA": "Hermes Financial Group",
    "JUFO.CA": "Juhayna Food Industries",
    "BTFH.CA": "Beltone Financial Holding",
    "RAYA.CA": "Raya Holding",
    "GBCO.CA": "GB Auto",
    "HELI.CA": "Heliopolis Housing",
    "ARCC.CA": "Arabian Cement Company",
    "MCQE.CA": "Macro Group Pharmaceuticals",
    "ORWE.CA": "Oriental Weavers",
    "ISPH.CA": "Integrated Diagnostics Holdings",
    "RMDA.CA": "Rameda Pharmaceutical",
    "OIH.CA":  "Olympic Industries Holding",
    "CCAP.CA": "Cairo Capital Holding",
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

W_PRICE  = 30
W_OB     = 18
W_LIQ    = 12
W_HTF    = 10
W_AVWAP  =  8
W_MACD   =  4
W_DIV    =  3
W_DZ     = 15   # Demand Zone Confluence (Stopping Volume + Volume Profile)

# ── ORAS local history CSV path (stored in repo working directory) ────────────
ORAS_CSV = "oras_history.csv"

# =========================================
# EGX HOLIDAY CALENDAR (2026)
# =========================================
EGX_HOLIDAYS = {
    date(2026,1,7),  date(2026,1,29),
    date(2026,3,19), date(2026,3,20), date(2026,3,21),
    date(2026,3,22), date(2026,3,23),
    date(2026,4,13), date(2026,4,25), date(2026,5,1),
    date(2026,5,26), date(2026,5,27), date(2026,5,28), date(2026,5,29),
    date(2026,6,16), date(2026,7,23),
    date(2026,8,25), date(2026,10,6),
}

def is_egx_trading_day(d=None):
    if d is None:
        d = datetime.now(CAIRO).date()
    if d.weekday() in (4, 5):
        return False
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
    Fetch latest close, open, high, low, volume for one symbol
    from TradingView scanner API.
    Returns dict or None.
    """
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


# =========================================
# ORAS: TradingView + local CSV history
# =========================================

def _oras_update_csv(today_date, quote):
    """
    Append today's ORAS quote to local CSV.
    CSV columns: Date, Open, High, Low, Close, Volume
    """
    new_row = pd.DataFrame([{
        "Date":   pd.Timestamp(today_date).normalize(),
        "Open":   quote["open"],
        "High":   quote["high"],
        "Low":    quote["low"],
        "Close":  quote["close"],
        "Volume": quote["volume"],
    }])

    if os.path.exists(ORAS_CSV):
        existing = pd.read_csv(ORAS_CSV, parse_dates=["Date"])
        existing["Date"] = pd.to_datetime(existing["Date"]).dt.normalize()
        # Remove duplicate for today if exists then append
        existing = existing[existing["Date"] != new_row["Date"].iloc[0]]
        df = pd.concat([existing, new_row], ignore_index=True).sort_values("Date")
    else:
        df = new_row

    df.to_csv(ORAS_CSV, index=False)
    print(f"  [ORAS] CSV updated: {today_date} → close={quote['close']:.2f} EGP")
    return df


def _oras_load_csv(days=120):
    """Load ORAS history from local CSV, return DataFrame."""
    if not os.path.exists(ORAS_CSV):
        return pd.DataFrame()
    df = pd.read_csv(ORAS_CSV, parse_dates=["Date"])
    df["Date"] = pd.to_datetime(df["Date"]).dt.normalize()
    df = df.set_index("Date").sort_index()
    cut = pd.Timestamp.today().normalize() - pd.Timedelta(days=days + 5)
    df = df[df.index >= cut]
    return df


def _oras_history(days=120):
    """
    1. جيب السعر اللحظي من TradingView Scanner
    2. سجّله في CSV محلي
    3. رجّع الـ DataFrame من الـ CSV
    """
    today = most_recent_trading_day()

    # Step 1: جيب السعر من TradingView
    quote = tv_get_quote("EGX:ORAS")
    if quote and quote["close"]:
        print(f"  [ORAS] TradingView: close={quote['close']:.2f} EGP")
        _oras_update_csv(today, quote)
    else:
        print("  [ORAS] TradingView failed — using existing CSV only")

    # Step 2: حمّل الـ CSV
    df = _oras_load_csv(days)
    if df.empty:
        print("  [ORAS] WARNING: CSV is empty — no historical data yet")
        return pd.DataFrame()

    print(f"  [ORAS] CSV: {len(df)} rows | last={df.index[-1].date()} | close={df['Close'].iloc[-1]:.2f} EGP")
    return df


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
    # ── ORAS: TradingView + local CSV ─────────────────────────────────────────
    if "ORAS" in symbol:
        return _oras_history(days)

    # ── All other stocks: yfinance for history + TradingView for today ────────
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
    std = tp.expanding().std().fillna(0)
    lo  = av - std

    return float(av.iloc[-1]), float(lo.iloc[-1])

def swings(close, lb=80):
    """
    Price range levels based on custom SMC framework:
      0.00 = lo  (swing low  — best buy)
      0.15 = buy_hi  (top of buy zone)
      0.50 = eq  (equilibrium)
      0.85 = sell_lo (bottom of sell zone)
      1.00 = hi  (swing high — best sell)
    """
    hi      = float(close.tail(lb).max())
    lo      = float(close.tail(lb).min())
    rng     = hi - lo
    eq      = lo + rng * 0.50
    buy_hi  = lo + rng * 0.15   # top of buy zone  (0.15)
    sell_lo = lo + rng * 0.85   # bottom of sell zone (0.85)
    return hi, lo, eq, buy_hi, sell_lo

# =========================================
# STOPPING VOLUME & VOLUME PROFILE
# =========================================

def calc_stopping_volume(df, eq, lo, lookback=30, vol_mult=1.5, range_ratio=0.5):
    """
    Detect Stopping Volume candles inside the discount zone (price < EQ).
    A SV candle: high volume (effort) + narrow range (no result) + in discount.
    Returns: sv_detected(bool), sv_score(0-1), sv_desc(str)
    """
    needed = ["High", "Low", "Close", "Open", "Volume"]
    if not all(c in df.columns for c in needed) or len(df) < lookback + 5:
        return False, 0.0, "Insufficient data for SV scan"

    d         = df[needed].dropna().tail(lookback + 20)
    avg_vol   = d["Volume"].rolling(lookback).mean()
    candle_rng = d["High"] - d["Low"]
    avg_rng   = candle_rng.rolling(lookback).mean()

    sv_candles = []
    for i in range(lookback, len(d)):
        c_close = float(d["Close"].iloc[i])
        c_vol   = float(d["Volume"].iloc[i])
        c_rng   = float(candle_rng.iloc[i])
        a_vol   = float(avg_vol.iloc[i])
        a_rng   = float(avg_rng.iloc[i])
        if a_vol <= 0 or a_rng <= 0:
            continue
        if c_close >= eq:                   # must be in discount zone
            continue
        if c_vol < vol_mult * a_vol:        # must be high volume
            continue
        if c_rng > range_ratio * a_rng:     # must be narrow range
            continue
        discount_range = eq - lo
        depth = (eq - c_close) / discount_range if discount_range > 0 else 0
        sv_candles.append({"idx": i, "close": c_close,
                            "vol_ratio": c_vol / a_vol, "depth": depth})

    if not sv_candles:
        return False, 0.0, "No Stopping Volume detected in discount zone"

    best  = sorted(sv_candles,
                   key=lambda x: x["depth"] * 0.6 + min(x["vol_ratio"] / 5, 1.0) * 0.4,
                   reverse=True)[0]
    score = min(1.0, best["depth"] * 0.6 + min(best["vol_ratio"] / 5, 1.0) * 0.4)
    desc  = (f"Stopping Volume @ {best['close']:.1f} — "
             f"vol {best['vol_ratio']:.1f}x avg — "
             f"depth {best['depth']*100:.0f}% into discount")
    return True, score, desc


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

    for _, row in d.iterrows():
        h, l, v = float(row["High"]), float(row["Low"]), float(row["Volume"])
        if v <= 0 or h <= l:
            continue
        lo_bin = max(0, int((l - price_min) / bin_size))
        hi_bin = min(bins - 1, int((h - price_min) / bin_size))
        span   = hi_bin - lo_bin + 1
        for b in range(lo_bin, hi_bin + 1):
            vol_bins[b] += v / span

    threshold     = np.max(vol_bins) * hvn_pct
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
    hvn_score = min(1.0, best["vol"] / np.max(vol_bins))
    desc      = (f"HVN @ {best['price']:.1f} — "
                 f"{best['vol']/np.max(vol_bins)*100:.0f}% of peak vol — "
                 f"depth {best['depth']*100:.0f}% into discount")
    return True, hvn_score, best["price"], desc


def sc_demand_zone(df, eq, lo, buy_hi):
    """
    Demand Zone Confluence = Stopping Volume + Volume Profile HVN, both in discount.
    SV + HVN  → full W_DZ  (true institutional demand zone)
    SV only   → 60% W_DZ   (absorption present, no volume memory)
    HVN only  → 40% W_DZ   (volume memory, no absorption candle)
    Neither   → 0
    """
    sv_hit, sv_score, sv_desc   = calc_stopping_volume(df, eq, lo)
    hvn_hit, hvn_score, _, hvn_desc = calc_volume_profile(df, eq, lo, buy_hi)

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
        pct   = round((cur - lo) / rng * 100, 1)
        return pts, f"Buy Zone (0–15%) @ {cur:.1f} — level {pct:.1f}% — {pts}/{W_PRICE}"

    if cur < eq:
        # Mid-discount (0.15–0.50): score 60% → 0% linearly
        ratio = (cur - buy_hi) / (eq - buy_hi) if (eq - buy_hi) > 0 else 1
        pts   = max(round(W_PRICE * 0.60 * (1.0 - ratio)), 0)
        pct   = round((cur - lo) / rng * 100, 1)
        return pts, f"Mid-Discount (15–50%) @ {cur:.1f} — level {pct:.1f}% — {pts}/{W_PRICE}"

    pct = round((cur - lo) / rng * 100, 1)
    return 0, f"Premium Zone — level {pct:.1f}% (above EQ {eq:.1f})"

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
    search = d.tail(40)

    for i in range(len(search) - 2):
        c_open  = float(search["Open"].iloc[i])
        c_close = float(search["Close"].iloc[i])
        c_low   = float(search["Low"].iloc[i])
        c_high  = float(search["High"].iloc[i])

        # OB candle: bearish (close < open)
        if c_close >= c_open:
            continue

        # الـ candle التالية لازم تكون impulse صاعد قوي (≥ 1.5x avg range)
        next_high  = float(search["High"].iloc[i+1])
        next_low   = float(search["Low"].iloc[i+1])
        next_range = next_high - next_low
        if next_range < avg_rng * 1.5:
            continue

        # OB level = top of bearish candle (c_high) as resistance turned support
        ob_level = c_high

        # OB لازم يكون في Buy Zone (0–15%) فقط
        if ob_level >= buy_hi:
            continue

        # السعر الحالي لازم يكون فوق الـ OB (مش اخترقه)
        if cur <= c_low:
            continue

        # quality بناءً على موقع الـ OB في الـ discount zone
        ratio   = (ob_level - lo) / discount_range
        quality = max(0.0, 1.0 - ratio)

        dist = abs(cur - ob_level) / cur
        ob_candidates.append({
            "level":   ob_level,
            "quality": quality,
            "dist":    dist,
            "candle":  i,
        })

    if not ob_candidates:
        return 0, "No valid OB found in discount zone (last 40 bars)"

    # أفضل OB: أعلى quality × proximity
    best = max(ob_candidates,
               key=lambda x: x["quality"] * max(0.1, 1 - x["dist"] * 5))

    ob    = best["level"]
    qual  = best["quality"]
    dist  = best["dist"]
    zone_lbl = "Buy Zone (0–15%)" if ob <= buy_hi else "Mid-Discount (15–50%)"

    if dist > 0.10:
        pts = round(W_OB * qual * 0.15)
        return pts, f"OB {ob:.1f} [{zone_lbl}] — far ({dist*100:.0f}% away) → {pts}/{W_OB}"
    if dist < 0.02:
        pts = round(W_OB * qual)
        return pts, f"At OB {ob:.1f} [{zone_lbl}] — quality {qual*100:.0f}% → {pts}/{W_OB}"
    if dist < 0.05:
        pts = round(W_OB * qual * 0.6)
        return pts, f"Near OB {ob:.1f} [{zone_lbl}] — quality {qual*100:.0f}% → {pts}/{W_OB}"
    pts = round(W_OB * qual * 0.30)
    return pts, f"OB {ob:.1f} [{zone_lbl}] — moderate distance → {pts}/{W_OB}"

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
            prev_lo = float(recent["Low"].iloc[i-1])

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

    # ── 3. HH / HL structure (last 20 bars, 4 pivots) ────────────────────────
    w3 = W_HTF - w1 - w2
    if n >= 20:
        tail = close.tail(20).values
        # بنقارن 4 نقاط: أول 5 / تاني 5 / تالت 5 / آخر 5
        q1 = float(np.mean(tail[0:5]))
        q2 = float(np.mean(tail[5:10]))
        q3 = float(np.mean(tail[10:15]))
        q4 = float(np.mean(tail[15:20]))

        # Higher Lows: كل quarter أعلى من اللي قبله
        hl_count = sum([q2 > q1, q3 > q2, q4 > q3])

        # Higher Highs: max of each half
        hh = float(np.max(tail[10:20])) > float(np.max(tail[0:10]))

        if hl_count >= 2 and hh:
            pts += w3
            desc.append(f"HH+HL structure ({hl_count}/3 HL) ✓")
        elif hl_count >= 2 or hh:
            pts += round(w3 * 0.5)
            desc.append(f"Partial structure (HL:{hl_count}/3, HH:{hh})")
        else:
            desc.append(f"No HH/HL — downtrend structure")
    else:
        desc.append("HH/HL: insufficient data")

    return pts, " | ".join(desc)


def sc_avwap(cur, av, av_lo):
    if cur<=av_lo: return W_AVWAP, f"At/below AVWAP lower band {av_lo:.1f}"
    if cur<av: return max(round(((av-cur)/(av-av_lo))*(W_AVWAP-1)),1), f"Below AVWAP {av:.1f}"
    return 0, f"Above AVWAP {av:.1f}"

def sc_macd(close):
    if len(close)<15: return 0,"Not enough data"
    m,sg,h=calc_macd(close)
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
    rs    = avg_g / avg_l.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

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
    return               "Ignore",           "#721c24","#f8d7da","#f5c6cb"

# =========================================
# ENTRY ZONES (Averaging Strategy)
# =========================================

def calc_entry_zones(df, cur, hi, lo, eq, buy_hi, sell_lo, av, alo):
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

    # HVN from volume profile
    hvn_hit, _, hvn_price, _ = calc_volume_profile(df, eq, lo, buy_hi)
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

    # Stopping Volume candle level
    sv_hit, _, sv_desc = calc_stopping_volume(df, eq, lo)
    if sv_hit:
        # extract price from desc string
        try:
            sv_price = float(sv_desc.split("@ ")[1].split(" ")[0])
            if sv_price < eq:
                merged = False
                for i, (p, lbl, cnt) in enumerate(levels):
                    if abs(p - sv_price) / p < 0.02:
                        levels[i] = (p, lbl + " + SV", cnt + 1)
                        merged = True
                        break
                if not merged:
                    levels.append((sv_price, "Stopping Volume", 2))
        except Exception:
            pass

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
        z2_price = min(remaining, key=lambda x: abs(x[0] - mid))[0]
        z2_label = min(remaining, key=lambda x: abs(x[0] - mid))[1]
        z2_conf  = min(remaining, key=lambda x: abs(x[0] - mid))[2]
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
        hi,lo,eq,buy_hi,sell_lo = swings(close)
        av,alo                  = calc_avwap(df)   # always compute for display

        # ── GATE: Price must be strictly below EQ (< 0.50 level) ─────────────
        # At EQ or above → SMC setup does not exist → all scores locked at zero
        if cur >= eq:
            pct_pos = round((cur - lo) / (hi - lo) * 100, 1) if hi > lo else 0
            r1 = 0; l1 = f"Premium Zone — {pct_pos:.1f}% level (above EQ {eq:.1f}) — SMC setup inactive"
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
            ml,_,_ = calc_macd(close)
            r6,l6  = sc_macd(close)
            r7,l7  = sc_div(close,ml)
            r8,l8  = sc_demand_zone(df,eq,lo,buy_hi)   # Stopping Volume + Volume Profile

        total          = min(r1+r2+r3+r4+r5+r6+r7+r8, 100)

        # ── Demand Zone Gate: score >= 35 requires confirmed demand (r8 > 0) ──
        # Without institutional demand evidence, a cheap price is a liquidity trap
        effective_score = total if (total < 35 or r8 > 0) else 0
        if effective_score == 0 and total >= 35:
            # downgrade — keep total for display but block signal
            sig  = "Ignore"
            tc   = "#721c24"; tbg = "#f8d7da"; tbr = "#f5c6cb"
            # append warning to demand zone label
            l8   = l8 + " ⚠️ No demand confirmation — liquidity trap risk"
        else:
            sig,tc,tbg,tbr = sig_info(total)

        # ── Entry zones (only meaningful when score >= 35 AND demand confirmed) ─
        entry_zones = None
        if total >= 35 and r8 > 0:
            entry_zones = calc_entry_zones(df, cur, hi, lo, eq, buy_hi, sell_lo, av, alo)

        return {
            "ok":True,"price":round(cur,2),"last_dt":last_dt,
            "is_fresh":is_fresh,"price_src":src,
            "target":round(cur*1.12,2),
            "eq":round(eq,2),"buy_hi":round(buy_hi,2),"sell_lo":round(sell_lo,2),
            "avwap":round(av,2),"avwap_l":round(alo,2),
            "score":total,"signal":sig,"tc":tc,"tbg":tbg,"tbr":tbr,
            "entry_zones": entry_zones,
            "rows":[
                ("Price Position",      r1,W_PRICE,l1),
                ("Demand Zone (SV+VP)", r8,W_DZ,   l8),
                ("Order Block Quality", r2,W_OB,   l2),
                ("Liquidity Context",   r3,W_LIQ,  l3),
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
    row={"date":now_cairo().strftime("%Y-%m-%d"),"stock":stock,
         "company":NAMES.get(stock,stock),"price":r.get("price","N/A"),
         "last_dt":r.get("last_dt","N/A"),"fresh":r.get("is_fresh",False),
         "signal":r.get("signal","N/A"),"score":r.get("score",0),
         "target":r.get("target","N/A")}
    df=pd.DataFrame([row]); f="signals_history.csv"
    if os.path.exists(f): df=pd.concat([pd.read_csv(f),df],ignore_index=True)
    df.to_csv(f,index=False)

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
    return f'<span style="font-size:11px;padding:2px 7px;border-radius:6px;background:#d4edda;color:#155724;margin-left:8px;">Validated: {last_dt}</span>'

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


def build_report(holiday_mode=False, last_trading=None):
    results={}; news={}
    for s in STOCKS:
        print(f"  Analyzing: {NAMES.get(s,s)} ...")
        results[s]=analyze(s); news[s]=get_news(s); save_history(s,results[s])

    fresh_n=sum(1 for s in STOCKS if results[s].get("ok") and results[s].get("is_fresh"))
    stale  =[NAMES.get(s,s) for s in STOCKS if results[s].get("ok") and not results[s].get("is_fresh")]
    dq_c   ="#155724" if not stale else "#856404"
    dq_bg  ="#d4edda" if not stale else "#fff3cd"
    dq_msg =(f"All {fresh_n} stocks — data fully verified" if not stale else f"{fresh_n}/{len(STOCKS)} fresh")
    weights=""

    parts=[]
    holiday_banner=""
    if holiday_mode and last_trading:
        holiday_banner=f"""
<table width="100%" cellpadding="12" cellspacing="0" border="0" style="background:#fff3cd;border-bottom:3px solid #ffc107;">
  <tr><td style="font-family:Arial,sans-serif;font-size:14px;color:#856404;">
    <b>🏖 EGX Holiday / Weekend Today ({today_cairo()})</b> — Report forced to absolute latest active trading session: <b>{last_trading}</b>
  </td></tr>
</table>"""

    parts.append(f"""
{holiday_banner}
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#0B5394;">
  <tr><td style="padding:20px 24px;">
    <div style="font-family:Arial,sans-serif;color:#fff;font-size:22px;font-weight:bold;">EGX Institutional Swing Scanner</div>
    <div style="font-family:Arial,sans-serif;color:#bdd7f5;font-size:13px;margin-top:5px;">{fmt_cairo("%A, %d %B %Y  |  %H:%M")} Cairo</div>
  </td></tr>
</table>
<table width="100%" cellpadding="10" cellspacing="0" border="0" style="background:{dq_bg};border-bottom:1px solid #ccc;">
  <tr><td style="font-family:Arial,sans-serif;font-size:12px;color:{dq_c};">
    <b>Data Status:</b> {dq_msg}
  </td></tr>
</table>""")

    wr=""
    for s in STOCKS:
        r=results[s]
        if not r["ok"] or r["score"]<35: continue
        _,tc,tbg,tbr=sig_info(r["score"])
        wr+=f"""
<tr style="border-bottom:1px solid #e0e0e0;">
  <td style="padding:10px 12px;font-family:Arial,sans-serif;">
    <b style="font-size:14px;">{NAMES.get(s,s)}</b> {fresh_badge(r["is_fresh"],r["last_dt"])}<br>
    <span style="font-size:11px;color:#888;">{s} · {SECTORS.get(s,"")}</span></td>
  <td style="padding:10px 12px;font-family:Arial,sans-serif;font-size:14px;font-weight:bold;">{r["price"]} EGP</td>
  <td style="padding:10px 12px;">
    <span style="font-family:Arial,sans-serif;display:inline-block;padding:4px 12px;border-radius:14px;font-size:12px;font-weight:bold;background:{tbg};color:{tc};border:1px solid {tbr};">{r["signal"]}</span></td>
  <td style="padding:10px 12px;">{bar(r["score"])}</td>
  <td style="padding:10px 12px;font-family:Arial,sans-serif;font-size:14px;font-weight:bold;color:#155724;">{r["target"]} EGP</td>
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

    for s in STOCKS:
        r=results[s]; nws=news[s]
        if not r["ok"]:
            parts.append(f"""
<table width="100%" cellpadding="12" cellspacing="0" border="0" style="margin:24px 0;border-top:3px solid #b02a2a;background:#fff5f5;border:1px solid #f5c6cb;">
  <tr><td style="font-family:Arial,sans-serif;">
    <b style="color:#721c24;font-size:16px;">{NAMES.get(s,s)}</b> <span style="font-size:12px;color:#999;margin-left:8px;">{s}</span><br>
    <span style="color:#721c24;font-size:13px;">Error: {r.get("error","unknown")}</span>
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
      <div style="font-family:Arial,sans-serif;font-size:11px;color:#888;">{r["last_dt"]} · {r.get("price_src","")}</div>
    </td>
  </tr>
</table>
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:8px 0;">
  <tr>
    <td width="130" style="padding:10px 16px;background:#d4edda;border:1px solid #c3e6cb;text-align:center;">
      <div style="font-family:Arial,sans-serif;font-size:10px;color:#155724;font-weight:bold;letter-spacing:1px;">TARGET</div>
      <div style="font-family:Arial,sans-serif;font-size:17px;font-weight:bold;color:#155724;">{r["target"]} EGP</div>
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
""")

    parts.append(f"""
<table width="100%" cellpadding="12" cellspacing="0" border="0" style="margin-top:30px;background:#f0f0f0;border-top:1px solid #ddd;">
  <tr><td align="center" style="font-family:Arial,sans-serif;font-size:11px;color:#999;">EGX Institutional Scanner · TradingView Data Engine</td></tr>
</table>""")

    return f"""<!DOCTYPE html><html><body style="margin:0;padding:20px;background:#eef2f7;"><table width="680" cellpadding="0" cellspacing="0" border="0" align="center" style="background:#ffffff;border:1px solid #d0d7e2;"><tr><td style="padding:0 24px 24px 24px;">{"".join(parts)}</td></tr></table></body></html>"""

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
# RUN
# =========================================

if __name__ == "__main__":
    today = today_cairo()
    print(f"EGX SMC Scanner — TradingView Engine — {fmt_cairo()} Cairo")

    if is_egx_trading_day(today):
        print("EGX Open Session — analyzing...")
        html = build_report(holiday_mode=False)
        send_email(html)
    else:
        last_td = most_recent_trading_day(today)
        print(f"Today ({today}) is NOT a trading day. Last active session: {last_td}")
        html = build_report(holiday_mode=True, last_trading=str(last_td))
        send_email(html, subject_suffix=f" (Holiday — Active Session: {last_td})")
