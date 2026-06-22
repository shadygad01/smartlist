import os
import json
import re
import sys
import html as _html
import csv
import socket
import pandas as pd
import numpy as np
import yfinance as yf
import requests
import traceback
import time

# yfinance لا يدعم timeout مباشرة — نضع حداً لكل socket operations
socket.setdefaulttimeout(60)
from concurrent.futures import ThreadPoolExecutor, as_completed
from signal_logger import log_signal, check_outcomes
try:
    from snapshot_engine import compute_snapshot_features as _snap_features
except ImportError:
    _snap_features = None
from backfill_signal_log import run_backfill
from egx_context import is_ramadan, is_cbe_window
from signal_db import log_signals as db_log_signals
from daily_tracker import run_all as tracker_run_all
from research_report import maybe_run_weekly_report
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from notifications.email_sender import send as _send_email_raw
from notifications.notification_router import (
    route as _tg_route,
    MORNING_BRIEF, SIGNAL_CHANGE, FIRST_BUY, TARGET_UPDATE,
    ZONE3_REINFORCEMENT, HIGH_SCORE, PRODUCTION_PROMOTION,
    NEAR_CONSTITUTIONAL, TIMELINE_EVENT,
)

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

# Constitutional universe — single source of truth is config/scanner_config.py.
from config.scanner_config import get_constitutional_universe
STOCKS = get_constitutional_universe()

# ── Presentation layer — single source of truth ───────────────────────────────
from presentation.presentation_language import (
    STOCK_NAMES, SIGNAL_EMOJI as _SIGNAL_EMOJI,
    NO_SETUPS_MESSAGE,
    TG_HEADER, TG_POSITIONS_HEADER, TG_SECTION_SEP,
    TG_REALTIME_HEADER, TG_CHANGE_HEADER, TG_RESEARCH_HEADER,
    EMAIL_HEADER_TITLE, EMAIL_HEADER_BG, EMAIL_HEADER_FG, EMAIL_HEADER_SUBTITLE,
    EMAIL_FOOTER_TEXT,
    COL_SIGNAL_QUALITY, COL_RANK_SCORE, COL_FACTOR_CONTRIB,
    COL_ENTRY_STRATEGY, COL_PATTERN_INTEL,
    TIER_PREMIER, TIER_MONITOR,
)

# =========================================
# WHITELIST - Price Gate Threshold >= 15
# =========================================
# ⚠️ تنبيه منهجي (مراجعة مستقلة 2026-06):
# الأرقام السابقة هنا (MDD=0%, CAGR=1001%) كانت من تحليل دائري في
# backtest_analysis.py: عتبات r1 كانت تُحاكى بالفلترة على "العائد المحقق"
# نفسه (outcome percentiles)، أي اختيار الصفقات بنتيجتها المستقبلية.
# سجل signal_log التاريخي لا يحتوي r1 أصلاً (smc_score=0 لكل الأحداث).
# القيم الحالية (15/16) أبقيناها كما هي، لكن لا يوجد دليل صالح يفضّلها
# على 14 أو 18 — التحقق الحقيقي الوحيد هو سجل الإشارات الحية الآجل.
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

# PRICE_GATE_NORMAL and PRICE_GATE_WHITELIST are computed as fractions of W_PRICE
# after signal_engine is imported below (search for "PRICE_GATE_NORMAL =").
# Fractions stored in config/gates_config.json — auto-track weight optimization.

# Stock names — consumed from presentation layer (single source of truth)
NAMES = STOCK_NAMES

SECTORS = {
    "COMI.CA": "Banking",
    "TMGH.CA": "Real Estate",
    "ETEL.CA": "Telecommunications",
    "EGAL.CA": "Basic Resources",
    "EAST.CA": "Consumer Goods",
    "ABUK.CA": "Chemicals & Fertilizers",
    "ORAS.CA": "Engineering & Construction",
    "EFIH.CA": "Financial Services",
    "ADIB.CA": "Banking",
    "FWRY.CA": "Financial Technology",
    "EMFD.CA": "Real Estate",
    "PHDC.CA": "Real Estate",
    "ORHD.CA": "Real Estate",
    "EFID.CA": "Food & Beverages",
    "HRHO.CA": "Financial Services",
    "JUFO.CA": "Food & Beverages",
    "BTFH.CA": "Financial Services",
    "RAYA.CA": "Technology",
    "GBCO.CA": "Automotive",
    "HELI.CA": "Real Estate",
    "ARCC.CA": "Construction Materials",
    "MCQE.CA": "Construction Materials",
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


# W_PRICE, W_OB, W_LIQ, W_HTF, W_AVWAP, W_MACD, W_DIV, W_DZ
# imported from signal_engine (loaded from config/weights.json)


# =========================================
# POSITION SIZING (Conservative Fund Mode)
# =========================================
# ⚠️ الأرقام السابقة هنا (CAGR=958%, MDD=-0.20%) كانت من محاكاة غير قابلة
# للتنفيذ: خروج عند قمة المستقبل + تعرض متزامن يصل 378% من رأس المال.
# محاكاة واقعية (قيد تعرض ≤100%، عوائد close-to-close، تكاليف 0.6%) تعطي
# ترتيب CAGR ≈ 35-50% و MDD ≈ 5-7% لنفس الأحداث — وهذا لسلة "كل قاع محلي"
# وليس لإشارات الماسح. الأحجام 2%/5% معقولة كإدارة مخاطر متحفظة بذاتها.
MAX_RISK_PER_TRADE_PCT = 2.0    # % of portfolio to risk on a single new signal
FULL_POSITION_PCT      = 5.0    # % of portfolio for high-conviction (score >= 70) signals

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
    # ── All stocks: CSV → yfinance → Yahoo API → TradingView patch for today ──
    # Priority 1: local committed CSVs (always available, no network, no hang)
    # Priority 2: yfinance (blocked in GitHub Actions — wrapped with 30s timeout)
    # Priority 3: Yahoo direct API (also blocked but has explicit timeout=15)
    # TradingView patch (applied at end) ensures today's price is always current.
    yf_symbol = symbol if symbol.endswith(".CA") else f"{symbol}.CA"

    # Convert days to yfinance period string
    if days <= 130:
        period = "6mo"
    elif days <= 260:
        period = "1y"
    elif days <= 520:
        period = "2y"
    else:
        period = "5y"

    range_param = period   # used by fallback Yahoo API too

    df = pd.DataFrame()

    # ── Priority 1: local CSV (committed to repo — zero network, zero hang) ───
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    _csv_path = os.path.join(_BASE_DIR, "historical_data", "historical_data", f"{yf_symbol}.csv")
    if not os.path.exists(_csv_path):
        _csv_path = os.path.join(_BASE_DIR, "historical_data", "historical_data",
                                 f"{symbol}.csv")
    if os.path.exists(_csv_path):
        try:
            _csv_df = pd.read_csv(_csv_path, parse_dates=["Date"])
            _csv_df = _csv_df.set_index("Date")
            _csv_df.index = pd.to_datetime(_csv_df.index).tz_localize(None)
            _csv_df = _csv_df[["Open", "High", "Low", "Close", "Volume"]].copy()
            # Trim to requested window
            _cutoff = pd.Timestamp.now() - pd.Timedelta(days=days + 30)
            _csv_df = _csv_df[_csv_df.index >= _cutoff]
            if not _csv_df.empty and len(_csv_df) > 5:
                df = _csv_df
                print(f"  [{symbol}] CSV loaded: {len(df)} rows from {_csv_path[-40:]}")
        except Exception as _csv_err:
            print(f"  [{symbol}] CSV load error: {_csv_err}")

    # ── Priority 2: yfinance (with hard 30s thread timeout to prevent hangs) ──
    if df.empty:
        import threading
        _yf_result = [pd.DataFrame()]
        def _yf_fetch():
            try:
                ticker = yf.Ticker(yf_symbol)
                _df = ticker.history(period=period, interval="1d", auto_adjust=False, repair=True)
                if not _df.empty and len(_df) > 5:
                    _df = _df[["Open", "High", "Low", "Close", "Volume"]].copy()
                    _df.index = _df.index.tz_localize(None)
                    _yf_result[0] = _df
            except Exception as e:
                print(f"  [{symbol}] yfinance error: {e}")
        _t = threading.Thread(target=_yf_fetch, daemon=True)
        _t.start()
        _t.join(timeout=30)
        if _t.is_alive():
            print(f"  [{symbol}] yfinance timeout (30s) — skipping")
        elif not _yf_result[0].empty:
            df = _yf_result[0]

    if df.empty:
        # Fallback: direct Yahoo Finance chart API
        try:
            url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{yf_symbol}"
                   f"?range={range_param}&interval=1d&includeAdjustedClose=false")
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


# =========================================
# SIGNAL ENGINE — single source of truth for all gate scoring
# =========================================
from signal_engine import (
    col, calc_macd, calc_avwap, swings,
    calc_stopping_volume, calc_volume_profile,
    sc_demand_zone, sc_price, sc_ob, sc_liquidity,
    sc_htf, sc_avwap, sc_macd, sc_div,
    _calc_rsi, _find_pivots, score_signal,
    W_PRICE, W_OB, W_LIQ, W_HTF, W_AVWAP, W_MACD, W_DIV, W_DZ,
    PRICE_GATE_FRAC_NORMAL, PRICE_GATE_FRAC_WHITELIST,
)
# Effective price gate = fraction × W_PRICE.
# Proportional design: auto-recalibrates when weight optimization changes W_PRICE.
# Normal: ~55% of W_PRICE (original design intent: 16/30 ≈ 53%).
# Whitelist: 50% of W_PRICE (original design intent: 15/30 = 50%).
# Evidence: alpha audit 2026-06 — gate at 50-55% of W_PRICE → Sharpe=1.265-1.272.
PRICE_GATE_NORMAL    = PRICE_GATE_FRAC_NORMAL    * W_PRICE
PRICE_GATE_WHITELIST = PRICE_GATE_FRAC_WHITELIST * W_PRICE

# ── Regime Filter — loaded from gates_config.json ────────────────────────────
_GATES_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "gates_config.json")
try:
    with open(_GATES_CONFIG_PATH) as _f:
        _gc = json.load(_f)
    _REGIME_FILTER_ENABLED = bool(_gc.get("regime_filter_enabled", False))
    _REGIME_DOWN_MULT      = float(_gc.get("regime_down_mult",      0.70))
except Exception:
    _REGIME_FILTER_ENABLED = False
    _REGIME_DOWN_MULT      = 0.70

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
        src        = "yfinance + TradingView patch"   # نفس المصدر لكل الأسهم
        # حديثة = آخر شمعة بتاريخ آخر يوم تداول فعلي (كانت سابقاً True دائماً)
        is_fresh   = (hist_date == str(most_recent_trading_day()))

        close            = df["Close"]
        hi,lo,eq,buy_hi,sell_lo = swings(df)
        av,alo                  = calc_avwap(df)   # always compute for display
        sv_result   = None   # populated in discount-zone branch, reused by entry zones
        hvn_result  = None
        macd_result = None   # populated in discount-zone branch
        # Research variable placeholders — filled in discount-zone branch only
        _rsi_val = None; _macd_hist = None; _macd_signal = None
        _avwap_gap = 0.0; _sv_depth = 0.0

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
            # ── Full SMC scoring — signal_engine is the single source of truth ──
            _sg = score_signal(symbol, df, hi, lo, eq, buy_hi, sell_lo)
            r1, l1 = _sg["r1_price"],     _sg["desc_price"]
            r2, l2 = _sg["r2_ob"],        _sg["desc_ob"]
            r3, l3 = _sg["r3_liquidity"], _sg["desc_liquidity"]
            r4, l4 = _sg["r4_htf"],       _sg["desc_htf"]
            r5, l5 = _sg["r5_avwap"],     _sg["desc_avwap"]
            r6, l6 = _sg["r6_macd"],      _sg["desc_macd"]
            r7, l7 = _sg["r7_div"],       _sg["desc_div"]
            r8, l8 = _sg["r8_demand"],    _sg["desc_demand"]
            av, alo = _sg["avwap"], _sg["avwap_lower"]

            # shared intermediates needed downstream (calc_entry_zones, DB logging)
            macd_result = calc_macd(close)
            ml          = macd_result[0]
            sv_result   = calc_stopping_volume(df, eq, lo)
            hvn_result  = calc_volume_profile(df, eq, lo, buy_hi)

            # ── Research detail variables ─────────────────────────────────────
            _rsi_val     = _sg["rsi_val"]
            _mh          = macd_result[2].dropna()
            _ms          = macd_result[1].dropna()
            _macd_hist   = round(float(_mh.iloc[-1]), 4) if len(_mh) > 0 else None
            _macd_signal = round(float(_ms.iloc[-1]), 4) if len(_ms) > 0 else None
            _raw_gap     = (av - cur) / max(av - alo, 0.001) if av > cur else 0.0
            _avwap_gap   = round(min(_raw_gap, 2.0), 4)
            _sv_depth    = round((eq - sv_result[3]) / max(eq - lo, 0.001), 4) \
                           if sv_result and sv_result[0] else 0.0

        total = min(r1+r2+r3+r4+r5+r6+r7+r8, 100)

        # ══════════════════════════════════════════════════════════════════
        # DUAL GATE
        #   GATE 1 — Price in Deep Discount:
        #     r1 >= FRAC × W_PRICE  (proportional — tracks weight optimization)
        #     Normal:    55% × W_PRICE  |  Whitelist: 50% × W_PRICE
        #     Fractions in config/gates_config.json → signal_engine exports.
        #   GATE 2 — Sweep & Reverse: r3 >= W_LIQ  [METADATA — not classification]
        #
        #   price_ok   →  BUY eligible; sig_info(adj_score) → Buy/Strong/VSB/IB
        #   !price_ok  →  WAIT (price not in Deep Discount)
        #   total < 35 →  SKIP
        #   liq_ok     →  metadata tag shown in alert; never overrides class
        # ══════════════════════════════════════════════════════════════════
        PRICE_GATE = PRICE_GATE_WHITELIST if symbol in WHITELIST else PRICE_GATE_NORMAL
        LIQ_GATE   = W_LIQ   # only Sweep & Reverse (20/20) passes to BUY

        price_ok = (r1 >= PRICE_GATE)
        liq_ok   = (r3 >= LIQ_GATE)

        ctx_label = ""
        score = min(int(round(total)), 100)

        # ══ سلم الإشارات الصارم (مصدر حقيقة واحد) ══════════════════════════
        #   Skip      : الجودة الخام < 35           → لا يُشترى أبداً
        #   Wait      : السعر غير عميق (r1 < البوابة) أو الـ score المعدّل
        #               تحت بوابة الدخول (35/40)     → لا شراء بعد
        #   Buy…      : كل البوابات + Sweep & Reverse → يُشترى فوراً
        # التسجيل في _register_new_positions يقرأ هذا التصنيف فقط —
        # فلا يمكن أن يُشترى سهم معروض Skip/Wait أو يُعرض Buy دون شراء.
        _entry_score_gate = 35 if symbol in WHITELIST else 40
        if total < 35:
            sig = "Skip"
            tc  = "#721c24"; tbg = "#f8d7da"; tbr = "#f5c6cb"
        elif not price_ok:
            sig = "Wait"
            tc  = "#721c24"; tbg = "#f8d7da"; tbr = "#f5c6cb"
            if cur < eq:
                l1  = l1 + f" ⛔ Price gate failed — not in Deep Discount (need >= {PRICE_GATE}/{W_PRICE})"
        elif score < _entry_score_gate:
            sig = "Wait"
            tc  = "#721c24"; tbg = "#f8d7da"; tbr = "#f5c6cb"
            l3  = l3 + f" ⏳ Adjusted score {score} below entry gate ({_entry_score_gate}) — quality pending"
        else:
            # liq_confirmed = metadata (Sweep & Reverse confirmed); never overrides class
            if not liq_ok:
                l3 = l3 + " 🟦 Sweep & Reverse pending — early entry"
            sig,tc,tbg,tbr = sig_info(score)
        liq_confirmed = liq_ok

        # ── EARLY BUY (Research Shadow) ──────────────────────────────────────
        # Research-only classification. Does NOT affect production entry decisions,
        # open_positions, portfolio, or performance metrics.
        # Rule: WAIT signal (price_ok=False) + partial discount (r1>0) + raw_score>=65
        # Historical validation: full-data WR=0.829, OOS WR=0.853 (2025+, N=34)
        # Promotion policy: requires N>=100, WR>=BUY WR, Exp>=BUY Exp, Sharpe>=BUY Sharpe,
        #                   OOS + walk-forward validation.
        _is_early_buy_research = (
            sig == "Wait"
            and r1 > 0          # partial discount only — not premium zone
            and total >= 65     # high raw score despite failed price gate
        )

        entry_zones = None
        _score_gate = 35 if symbol in WHITELIST else 40
        # entry_zones computed for all buy-eligible signals (price_ok + score gate)
        if price_ok and r8 > 0 and total >= _score_gate:
            entry_zones = calc_entry_zones(df, cur, hi, lo, eq, buy_hi, sell_lo, av, alo,
                                           _sv=sv_result, _hvn=hvn_result)

        pattern_data = {"ok": False, "reason": "removed", "label": ""}

        try:
            _vol = df["Volume"]
            _vol_spike = round(float(_vol.iloc[-1]) / max(float(_vol.iloc[-21:-1].mean()), 1), 2) if len(_vol) > 21 else None
        except Exception:
            _vol_spike = None

        # ── Parse OB label → ob_quality / ob_dist ────────────────────────────
        _ob_qm      = re.search(r'quality\s+(\d+)%', l2)
        if _ob_qm:
            _ob_quality = round(int(_ob_qm.group(1)) / 100, 2)
        elif l2.startswith("OB zone") and "far" in l2 and r2 > 0:
            # "far" label omits quality — back-calculate: pts = round(W_OB * qual * 0.15)
            _ob_quality = round(min(r2 / max(W_OB * 0.15, 0.1), 1.0), 2)
        elif "moderate distance" in l2 and r2 > 0:
            # moderate: pts = round(W_OB * qual * 0.30)
            _ob_quality = round(min(r2 / max(W_OB * 0.30, 0.1), 1.0), 2)
        else:
            _ob_quality = None
        _ob_dm      = re.search(r'far\s*\((\d+(?:\.\d+)?)%\s*away\)', l2, re.IGNORECASE)
        if _ob_dm:
            _ob_dist = round(float(_ob_dm.group(1)) / 100, 4)
        elif l2.startswith("At OB"):
            _ob_dist = 0.01
        elif l2.startswith("Near OB"):
            _ob_dist = 0.035
        elif "moderate distance" in l2:
            _ob_dist = 0.075
        else:
            _ob_dist = None

        # ── Snapshot Features — لا يُغيّر منطق الدخول ───────────────────────
        _snap = _snap_features(df, cur, eq, lo, hi) if (_snap_features and cur < eq) else {}

        return {
            "ok":True,"price":round(cur,2),"last_dt":last_dt,
            "is_fresh":is_fresh,"price_src":src,
            "target":round(cur*1.12,2),
            "eq":round(eq,2),"buy_hi":round(buy_hi,2),"sell_lo":round(sell_lo,2),
            "avwap":round(av,2),"avwap_l":round(alo,2),
            "score":score,"raw_score":total,"ctx_label":ctx_label,
            "signal":sig,"tc":tc,"tbg":tbg,"tbr":tbr,"r1":r1,
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
            "sv_hit":    bool(sv_result[0])         if sv_result   else False,
            "sv_score":  round(float(sv_result[1]),3) if sv_result else 0.0,
            "sv_price":  round(float(sv_result[3]),2) if sv_result and sv_result[0] else None,
            "hvn_hit":   bool(hvn_result[0])          if hvn_result else False,
            "hvn_score": round(float(hvn_result[1]),3) if hvn_result else 0.0,
            "hvn_price": round(float(hvn_result[2]),2) if hvn_result and hvn_result[0] else None,
            "macd_val":  round(float(macd_result[0].iloc[-1]),4) if macd_result is not None and len(macd_result[0]) > 0 else None,
            "vol_spike": _vol_spike,
            # 18 extended research variables
            "rsi_val":        _rsi_val,
            "macd_hist":      _macd_hist,
            "macd_signal":    _macd_signal,
            "rsi_div":        bool("RSI div" in l7),
            "macd_div":       bool("MACD div" in l7),
            "ob_quality":     _ob_quality,
            "ob_dist":        _ob_dist,
            "htf_hh":         bool("HH+HL" in l4 or "HH:True" in l4),
            "htf_hl":         bool("HH+HL" in l4 or "HL:True" in l4),
            "avwap_gap":      _avwap_gap,
            "sweep_detected": bool("Sweep" in l3),
            "wick_rejection": bool("wick" in l3.lower()),
            "equal_lows":     bool("Equal Lows" in l3),
            "price_gate":       PRICE_GATE,
            "price_ok":         bool(price_ok),
            "liq_confirmed":    bool(liq_confirmed),
            "early_buy_research": bool(_is_early_buy_research),
            "sv_depth":         _sv_depth,
            **_snap,
        }


        return result
    except Exception as e:
        return {"ok":False,"error":str(e)}

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

def pill(sc, mx):
    pct = int(sc / mx * 100) if mx else 0
    if pct >= 70:
        bg, fg = "#d1f0dd", "#1a7340"
    elif pct >= 40:
        bg, fg = "#fef3c7", "#7a5c00"
    else:
        bg, fg = "#fde8e8", "#a02020"
    return (
        f'<span style="display:inline-block;padding:3px 10px;border-radius:10px;'
        f'font-family:Arial,sans-serif;font-size:11px;font-weight:700;'
        f'background:{bg};color:{fg};">{sc}/{mx}</span>'
    )

def bar(score):
    if score >= 70:
        fg, bg_track = "#1a7340", "#c8ecd8"
    elif score >= 45:
        fg, bg_track = "#7a5c00", "#fdefc3"
    else:
        fg, bg_track = "#a02020", "#f9d5d5"
    fill = max(2, score)
    return (
        f'<span style="display:inline-flex;align-items:center;gap:8px;vertical-align:middle;">'
        f'<span style="display:inline-block;width:100px;height:8px;border-radius:4px;background:{bg_track};overflow:hidden;">'
        f'<span style="display:block;width:{fill}%;height:100%;background:{fg};border-radius:4px;"></span>'
        f'</span>'
        f'<span style="font-family:Arial,sans-serif;font-weight:700;font-size:14px;color:{fg};">{score}<span style="font-size:11px;font-weight:400;color:#888;">/100</span></span>'
        f'</span>'
    )

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
            f'border-left:4px solid #1C4587;padding-left:8px;">{COL_ENTRY_STRATEGY}</div>'
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
    header = (
        '<div style="margin:10px 0 4px 0;font-family:Arial,sans-serif;font-size:12px;'
        'font-weight:bold;color:#1C4587;letter-spacing:0.5px;border-left:4px solid #1C4587;'
        f'padding-left:8px;">{COL_PATTERN_INTEL}</div>'
    )
    if not p or not p.get("ok"):
        reason = p.get("reason", "") if p else ""
        if reason == "premium":
            msg = "⛔ Price in Premium Zone — pattern analysis inactive (only runs in Discount Zone)"
            bg, border = "#fff3cd", "#ffeeba"
        else:
            msg = f"⚠️ {p.get('label', 'Insufficient historical data for pattern analysis') if p else 'Insufficient historical data for pattern analysis'}"
            bg, border = "#f8f9fa", "#dee2e6"
        return (
            header +
            f'<table width="100%" cellpadding="0" cellspacing="0" border="0" '
            f'style="border:1px solid {border};background:{bg};margin-bottom:8px;">'
            f'<tr><td style="padding:10px 14px;font-family:Arial,sans-serif;font-size:12px;color:#555;">'
            f'{msg}</td></tr></table>'
        )

    ps      = p["pattern_score"]
    gain    = p["avg_gain"]
    cnt     = p["similar_count"]
    lbl     = p["label"]
    detail  = p.get("detail", {})
    eff_raw = p.get("effective_score", 0)
    eff_v   = eff_raw / 20
    eff_lbl = "Excellent" if eff_v >= 3 else "Strong" if eff_v >= 2 else "Moderate" if eff_v >= 1 else "Weak"
    wr      = p.get("win_rate", 0)

    if ps >= 70:
        bar_color = "#155724"; bg = "#d4edda"; border = "#c3e6cb"
        badge_txt = "Strong Setup"
    elif ps >= 50:
        bar_color = "#856404"; bg = "#fff3cd"; border = "#ffeeba"
        badge_txt = "Moderate Setup"
    elif ps >= 35:
        bar_color = "#5a6268"; bg = "#f8f9fa"; border = "#dee2e6"
        badge_txt = "Weak Setup"
    else:
        bar_color = "#721c24"; bg = "#fff5f5"; border = "#f5c6cb"
        badge_txt = "Poor Setup"

    bar_w = max(4, min(100, int(ps)))

    return (
        header +
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
        # Effective Score
        f'<td width="22%" style="font-family:Arial,sans-serif;padding-left:12px;">'
        f'<div style="font-size:10px;color:#555;font-weight:bold;margin-bottom:4px;">EFFECTIVE SCORE</div>'
        f'<div style="font-size:22px;font-weight:bold;color:{bar_color};">{eff_v:.1f}<span style="font-size:13px;">/5</span></div>'
        f'<div style="font-size:10px;color:#777;margin-top:2px;">{eff_lbl} — {wr*100:.0f}% win rate</div>'
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
    # V2 runtime — email rendered by egx_email.py from PresentationSnapshot only
    from egx_email import build_email
    from presentation.presentation_snapshot import build_presentation_snapshot

    # Still run analyze() to keep results for change detection / real-time alerts
    if _cached_results is not None:
        results = _cached_results
    else:
        tv_prefetch_all_quotes(STOCKS)
        results = {}
        workers = min(8, len(STOCKS))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_sym = {executor.submit(analyze, s): s for s in STOCKS}
            for future in as_completed(future_to_sym):
                sym = future_to_sym[future]
                try:
                    results[sym] = future.result()
                except Exception as e:
                    results[sym] = {"ok": False, "error": str(e)}
        for sym, res in results.items():
            if res.get("ok"):
                print(f"  Done: {res.get('name', sym)}")

    snap = build_presentation_snapshot()
    html = build_email(snap)
    return html, results, snap


def _build_report_v1(holiday_mode=False, last_trading=None, _cached_results=None):
    """Preserved V1 — NOT called in production."""
    from presentation.portfolio_snapshot import build_portfolio_snapshot
    print("  Fetching Dow Jones status...")
    dj = get_dow_jones_status()
    dow_banner = build_dow_banner(dj)

    if _cached_results is not None:
        results = _cached_results
    else:
        tv_prefetch_all_quotes(STOCKS)
        results = {}
        workers = min(8, len(STOCKS))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_sym = {executor.submit(analyze, s): s for s in STOCKS}
            for future in as_completed(future_to_sym):
                s = future_to_sym[future]
                results[s] = future.result()
                print(f"  Done: {NAMES.get(s, s)}")
        for s in STOCKS:
            save_history(s, results[s])

    snap = build_portfolio_snapshot()
    date_str = fmt_cairo("%A, %d %B %Y  ·  %H:%M")

    # ── Email header ──────────────────────────────────────────────────────────
    holiday_banner = ""
    if holiday_mode and last_trading:
        holiday_banner = f"""
<table width="100%" cellpadding="12" cellspacing="0" border="0" style="background:#fff3cd;border-bottom:3px solid #ffc107;">
  <tr><td style="font-family:Arial,sans-serif;font-size:14px;color:#856404;">
    <b>🏖 EGX Holiday / Weekend Today ({today_cairo()})</b> — Report forced to latest trading session: <b>{last_trading}</b>
  </td></tr>
</table>"""

    header = f"""
{holiday_banner}
{dow_banner}
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{EMAIL_HEADER_BG};">
  <tr><td style="padding:22px 28px;">
    <div style="font-family:Arial,sans-serif;color:{EMAIL_HEADER_FG};font-size:20px;font-weight:700;letter-spacing:0.3px;">{EMAIL_HEADER_TITLE}</div>
    <div style="font-family:Arial,sans-serif;color:{EMAIL_HEADER_SUBTITLE};font-size:12px;margin-top:6px;letter-spacing:0.3px;">{date_str} Cairo</div>
  </td></tr>
</table>"""

    def _sec_title(title):
        return (f'<div style="font-family:Arial,sans-serif;font-size:13px;font-weight:700;'
                f'color:#1a3a5c;margin:20px 0 8px 0;letter-spacing:0.4px;'
                f'border-left:4px solid #1a3a5c;padding-left:8px;">{title}</div>')

    # ── Executive Summary ─────────────────────────────────────────────────────
    h_col = "#1a7340" if "★★★★" in snap.health_stars else ("#856404" if "★★★" in snap.health_stars else "#721c24")
    exec_summary = f"""
{_sec_title("📋 Executive Summary")}
<table width="100%" cellpadding="12" cellspacing="0" border="0" style="background:#f8f9fb;border:1px solid #e0e6ef;border-radius:6px;">
  <tr><td style="font-family:Arial,sans-serif;">
    <div style="font-size:18px;font-weight:700;color:{h_col};">{snap.health_stars} {snap.health_label}</div>
    <div style="font-size:13px;color:#444;margin-top:6px;">{snap.health_narrative}</div>
    <div style="margin-top:10px;font-size:12px;color:#666;">
      <b>{snap.held_count}</b> positions held &nbsp;·&nbsp;
      Capacity <b>{snap.capacity_used_pct:.0f}%</b> &nbsp;·&nbsp;
      Max Correlation <b>{snap.max_correlation:.2f}</b> &nbsp;·&nbsp;
      Sector Cap <b>{"OK" if snap.sector_cap_ok else "⚠ Exceeded"}</b>
    </div>
  </td></tr>
</table>"""

    # ── Today's Opportunities ─────────────────────────────────────────────────
    opp_rows = ""
    for r in snap.high_conviction_buys + snap.buy_with_awareness:
        conf_col = "#155724" if r.get("confidence") == "HIGH" else "#856404"
        opp_rows += f"""
<tr style="border-bottom:1px solid #e8f0f8;">
  <td style="padding:9px 12px;font-family:Arial,sans-serif;font-size:13px;font-weight:700;color:#1a3a5c;">{r["ticker"]}</td>
  <td style="padding:9px 12px;font-family:Arial,sans-serif;font-size:12px;color:#666;">{r.get("sector","")}</td>
  <td style="padding:9px 12px;font-family:Arial,sans-serif;font-size:12px;color:{conf_col};font-weight:600;">{r.get("decision","")}</td>
  <td style="padding:9px 12px;font-family:Arial,sans-serif;font-size:11px;color:#555;">{r.get("reason","")[:100]}</td>
</tr>"""
    if not opp_rows:
        opp_rows = '<tr><td colspan=4 style="padding:12px;font-family:Arial,sans-serif;color:#888;font-size:13px;">No high conviction opportunities today.</td></tr>'

    opp_block = f"""
{_sec_title("🎯 Today's Opportunities")}
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="border:1px solid #c8daf5;border-collapse:collapse;">
  <tr style="background:#1a3a5c;">
    <th align="left" style="padding:8px 12px;font-family:Arial,sans-serif;font-size:11px;color:#fff;">Ticker</th>
    <th align="left" style="padding:8px 12px;font-family:Arial,sans-serif;font-size:11px;color:#fff;">Sector</th>
    <th align="left" style="padding:8px 12px;font-family:Arial,sans-serif;font-size:11px;color:#fff;">Decision</th>
    <th align="left" style="padding:8px 12px;font-family:Arial,sans-serif;font-size:11px;color:#fff;">Reason</th>
  </tr>
  {opp_rows}
</table>"""

    # ── Future Priorities ─────────────────────────────────────────────────────
    fp_items = " &nbsp;·&nbsp; ".join(f'<b>{t}</b>' for t in snap.future_priorities) or "None pending"
    future_block = f"""
{_sec_title("⏳ Future Priorities")}
<table width="100%" cellpadding="10" cellspacing="0" border="0" style="background:#f0f7ff;border:1px solid #d0e4f7;border-radius:4px;">
  <tr><td style="font-family:Arial,sans-serif;font-size:13px;color:#0B5394;">{fp_items}</td></tr>
</table>"""

    # ── Current Portfolio ─────────────────────────────────────────────────────
    pos_rows = ""
    for p in sorted(snap.held_positions, key=lambda x: x.get("return_pct", 0), reverse=True):
        ret = p.get("return_pct", 0) or 0
        ret_col = "#155724" if ret >= 0 else "#721c24"
        ret_str = f'+{ret:.1f}%' if ret >= 0 else f'{ret:.1f}%'
        entry_quality = p.get("r2_score", 0) or 0
        quality_str = f"{entry_quality:.0f}" if entry_quality else "—"
        pos_rows += f"""
<tr style="border-bottom:1px solid #e8f0f8;">
  <td style="padding:8px 12px;font-family:Arial,sans-serif;font-size:13px;font-weight:700;color:#1a3a5c;">{p.get("ticker","")}</td>
  <td style="padding:8px 12px;font-family:Arial,sans-serif;font-size:12px;color:#666;">{p.get("sector","")}</td>
  <td style="padding:8px 12px;font-family:Arial,sans-serif;font-size:12px;color:#444;">{p.get("entry_price",0):.2f} EGP</td>
  <td style="padding:8px 12px;font-family:Arial,sans-serif;font-size:12px;color:#444;">{p.get("current_price",0):.2f} EGP</td>
  <td style="padding:8px 12px;font-family:Arial,sans-serif;font-size:13px;font-weight:700;color:{ret_col};">{ret_str}</td>
  <td style="padding:8px 12px;font-family:Arial,sans-serif;font-size:12px;color:#666;">{quality_str}</td>
</tr>"""
    if not pos_rows:
        pos_rows = '<tr><td colspan=6 style="padding:12px;color:#888;">No positions held.</td></tr>'

    portfolio_block = f"""
{_sec_title("📂 Current Portfolio ({n} positions)".format(n=snap.held_count))}
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="border:1px solid #c8daf5;border-collapse:collapse;">
  <tr style="background:#0B5394;">
    <th align="left" style="padding:8px 12px;font-family:Arial,sans-serif;font-size:11px;color:#fff;">Ticker</th>
    <th align="left" style="padding:8px 12px;font-family:Arial,sans-serif;font-size:11px;color:#fff;">Sector</th>
    <th align="left" style="padding:8px 12px;font-family:Arial,sans-serif;font-size:11px;color:#fff;">Entry</th>
    <th align="left" style="padding:8px 12px;font-family:Arial,sans-serif;font-size:11px;color:#fff;">Current</th>
    <th align="left" style="padding:8px 12px;font-family:Arial,sans-serif;font-size:11px;color:#fff;">Return</th>
    <th align="left" style="padding:8px 12px;font-family:Arial,sans-serif;font-size:11px;color:#fff;">Entry Quality</th>
  </tr>
  {pos_rows}
</table>"""

    # ── Portfolio Health ──────────────────────────────────────────────────────
    sector_rows_html = ""
    for sector, pct in sorted(snap.sector_allocation.items(), key=lambda x: -x[1]):
        cap_warn = " ⚠" if pct > 25 else ""
        c = "#721c24" if pct > 25 else ("#856404" if pct > 20 else "#155724")
        sector_rows_html += f'<tr><td style="font-family:Arial,sans-serif;font-size:12px;padding:5px 12px;color:#444;width:140px;">{sector}</td><td style="padding:5px 12px;font-family:Arial,sans-serif;font-size:12px;font-weight:700;color:{c};">{pct:.1f}%{cap_warn}</td></tr>'

    health_block = f"""
{_sec_title("⚖️ Portfolio Health")}
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="border:1px solid #e0e6ef;border-collapse:collapse;">
  <tr style="background:#f8f9fb;"><td colspan=2 style="padding:8px 12px;font-family:Arial,sans-serif;font-size:11px;font-weight:700;color:#5b6c82;text-transform:uppercase;letter-spacing:0.5px;">Sector Allocation</td></tr>
  {sector_rows_html}
  <tr style="background:#f8f9fb;border-top:1px solid #e0e6ef;">
    <td style="padding:8px 12px;font-family:Arial,sans-serif;font-size:12px;color:#444;">Max Correlation</td>
    <td style="padding:8px 12px;font-family:Arial,sans-serif;font-size:12px;font-weight:700;">{snap.max_correlation:.3f}</td>
  </tr>
  <tr>
    <td style="padding:8px 12px;font-family:Arial,sans-serif;font-size:12px;color:#444;">Capacity Used</td>
    <td style="padding:8px 12px;font-family:Arial,sans-serif;font-size:12px;font-weight:700;">{snap.capacity_used_pct:.0f}%</td>
  </tr>
</table>"""

    # ── Watch List ────────────────────────────────────────────────────────────
    watch_str = " &nbsp;·&nbsp; ".join(f'<b>{t}</b>' for t in snap.watch_list) or "Empty"
    watch_block = f"""
{_sec_title("👁 Watch List")}
<table width="100%" cellpadding="10" cellspacing="0" border="0" style="background:#f8f9fb;border:1px solid #e0e6ef;border-radius:4px;">
  <tr><td style="font-family:Arial,sans-serif;font-size:13px;color:#333;">{watch_str}</td></tr>
</table>"""

    # ── Research Insight ──────────────────────────────────────────────────────
    insight_html = ""
    for ins in snap.research_insights[:3]:
        insight_html += f"""
<tr style="border-bottom:1px solid #e8f0f8;">
  <td style="padding:8px 12px;font-family:Arial,sans-serif;font-size:12px;color:#444;">{ins.get("question","")}</td>
  <td style="padding:8px 12px;font-family:Arial,sans-serif;font-size:12px;color:#333;">{ins.get("conclusion","")[:120]}</td>
  <td style="padding:8px 12px;font-family:Arial,sans-serif;font-size:11px;color:#888;">{ins.get("confidence","")}</td>
</tr>"""
    if not insight_html:
        insight_html = '<tr><td colspan=3 style="padding:12px;color:#888;">No verified findings yet.</td></tr>'

    research_block = f"""
{_sec_title("🔬 Research Insight ({n} verified findings)".format(n=snap.knowledge_count))}
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="border:1px solid #c8daf5;border-collapse:collapse;">
  <tr style="background:#1a3a5c;">
    <th align="left" style="padding:8px 12px;font-family:Arial,sans-serif;font-size:11px;color:#fff;">Question</th>
    <th align="left" style="padding:8px 12px;font-family:Arial,sans-serif;font-size:11px;color:#fff;">Conclusion</th>
    <th align="left" style="padding:8px 12px;font-family:Arial,sans-serif;font-size:11px;color:#fff;">Confidence</th>
  </tr>
  {insight_html}
</table>"""

    # ── Footer ────────────────────────────────────────────────────────────────
    footer = f"""
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:40px;border-top:1px solid #e8eaed;">
  <tr><td align="center" style="padding:16px;font-family:Arial,sans-serif;font-size:11px;color:#bbb;letter-spacing:0.4px;">
    {EMAIL_FOOTER_TEXT}
  </td></tr>
</table>"""

    parts = [header, exec_summary, opp_block, future_block, portfolio_block, health_block, watch_block, research_block, footer]
    html = f"""<!DOCTYPE html><html><body style="margin:0;padding:20px;background:#eef2f7;"><table width="680" cellpadding="0" cellspacing="0" border="0" align="center" style="background:#ffffff;border:1px solid #d0d7e2;"><tr><td style="padding:0 24px 24px 24px;">{"".join(parts)}</td></tr></table></body></html>"""
    return html, results


# ── Stub retained for import compatibility (no longer called by build_report) ─
def _build_ranking_block_legacy():
    pass

# =========================================
# EMAIL
# =========================================

def send_email(html, subject_suffix=""):
    date_str = now_cairo().strftime("%Y-%m-%d")
    subject  = f"{EMAIL_HEADER_TITLE} · {date_str}{subject_suffix}"
    return _send_email_raw(subject=subject, html=html, to=EMAIL)

# =========================================
# TELEGRAM ALERTS
# =========================================

def send_telegram_zone3_reinforcement(symbol, entry_price, reinforcement_price, avg_price):
    """Send alert when Zone 3 reinforcement is triggered"""
    name = NAMES.get(symbol, symbol)
    drop_pct = ((reinforcement_price - entry_price) / entry_price) * 100

    def fib_levels_str(ep):
        levels = [
            (12.0, ep * 1.120),
            (23.6, ep * 1.236),
            (38.2, ep * 1.382),
            (50.0, ep * 1.500),
        ]
        return "\n".join(
            f"   {'Min +12.0%':10}  {price:.2f} EGP" if pct == 12.0
            else f"   Fib {pct:.1f}%   {price:.2f} EGP"
            for pct, price in levels
        )

    message = (
        f"🔄 *Zone 3 Reinforcement — Adding to Position*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"*{name}*  `{symbol}`\n\n"
        f"🟢 *Initial Entry*\n"
        f"   Price       {entry_price:.2f} EGP\n"
        f"{fib_levels_str(entry_price)}\n\n"
        f"🔵 *Zone 3 Re-entry*\n"
        f"   Price       {reinforcement_price:.2f} EGP\n"
        f"   Drop        *{drop_pct:.1f}%* from initial entry\n"
        f"{fib_levels_str(reinforcement_price)}\n\n"
        f"📐 *New Avg Entry:  {avg_price:.2f} EGP*\n"
        f"⚠️  Exit on first weakness after +12%\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⏰ {now_cairo().strftime('%H:%M  |  %d %b %Y')}"
    )
    return _tg_route(ZONE3_REINFORCEMENT, message, symbol=symbol, check_duplicate=False)


def send_telegram_target_update(symbol, entry_price, old_target, new_target, current_price, fib_level):
    """Send alert when dynamic target is updated"""
    old_pct = ((old_target - entry_price) / entry_price) * 100
    new_pct = ((new_target - entry_price) / entry_price) * 100

    message = (
        f"🚀 *Dynamic Target Updated*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"*{NAMES.get(symbol, symbol)}*  `{symbol}`\n\n"
        f"   Entry         {entry_price:.2f} EGP\n"
        f"   Current       {current_price:.2f} EGP\n\n"
        f"   Old Target    {old_target:.2f} EGP  (*+{old_pct:.1f}%*)\n"
        f"   New Target    *{new_target:.2f} EGP*  (*+{new_pct:.1f}%*) ⬆️\n\n"
        f"   Fib Level     *{fib_level:.1f}%*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⏰ {now_cairo().strftime('%H:%M  |  %d %b %Y')}"
    )
    return _tg_route(TARGET_UPDATE, message, symbol=symbol, check_duplicate=False)

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

def suggested_position_size(portfolio_value: float, entry_score: int) -> dict:
    """
    Score-proportional sizing: allocates more capital to high-conviction signals.
    Tiered by score to improve risk-adjusted returns while keeping MDD minimal.
    """
    if entry_score >= 75:
        pct, tier = 5.0, "Excellent"
    elif entry_score >= 65:
        pct, tier = 3.5, "Very Good"
    elif entry_score >= 55:
        pct, tier = 2.5, "Good"
    elif entry_score >= 45:
        pct, tier = 1.5, "Moderate"
    else:
        pct, tier = 1.0, "Weak"
    amount = portfolio_value * pct / 100
    return {"pct": pct, "amount": round(amount, 2), "tier": tier}


def add_position(symbol, entry_price, entry_date, volatility_min_target=0.12, entry_score=0, entry_pattern_score=0, entry_effective_score=0):
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
        "entry_pattern_score": entry_pattern_score,
        "entry_effective_score": entry_effective_score,
        "suggested_risk_pct": FULL_POSITION_PCT if entry_score >= 70 else MAX_RISK_PER_TRADE_PCT,
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


def _get_position_bq(symbol: str, db_path: str = "egx_research.db") -> dict | None:
    """Return latest bq_score and action flag for an open position symbol."""
    try:
        import sqlite3 as _sqlite3
        conn = _sqlite3.connect(db_path)
        row = conn.execute(
            """SELECT bq.bq_score, bq.classification
               FROM signals s JOIN bottom_quality bq ON s.id = bq.signal_id
               WHERE s.symbol = ? AND bq.bq_score IS NOT NULL
               ORDER BY s.signal_date DESC LIMIT 1""",
            (symbol,),
        ).fetchone()
        conn.close()
        if row:
            bq = row[0]
            if bq < 40:
                action = "⚠️ REVIEW EXIT"
            elif bq < 60:
                action = "📊 MONITOR"
            else:
                action = "✅ QUALITY"
            return {"bq_score": bq, "action": action, "classification": row[1]}
    except Exception:
        pass
    return None


def send_telegram_alerts(results, snap=None):
    """Constitutional Morning Brief V2 — delegates to telegram.py. Accepts pre-built snap."""
    from telegram import send_morning_brief
    date_str = now_cairo().strftime("%d %b %Y")
    send_morning_brief(date_str, snap)  # snap=None → telegram.py builds it (fallback only)


def _send_telegram_alerts_v1(results):
    """Preserved V1 — NOT called in production."""
    from presentation.portfolio_snapshot import build_portfolio_snapshot

    snap = build_portfolio_snapshot()
    date_str = now_cairo().strftime("%d %b %Y")

    msg_lines = [
        TG_HEADER,
        f"*{date_str}*",
        TG_SECTION_SEP,
    ]

    # Portfolio Health
    h_icon = "🟢" if "★★★★" in snap.health_stars else ("🟡" if "★★★" in snap.health_stars else "🔴")
    msg_lines.append(f"{h_icon} Portfolio Health: *{snap.health_stars} {snap.health_label}*")
    msg_lines.append(f"   {snap.held_count} positions · Capacity {snap.capacity_used_pct:.0f}% · Corr {snap.max_correlation:.2f}")
    msg_lines.append("")

    # Today's Opportunities
    all_opps = snap.high_conviction_buys + snap.buy_with_awareness
    if all_opps:
        msg_lines.append(TG_SECTION_SEP)
        msg_lines.append("🎯 *Today's Opportunities*\n")
        for r in all_opps:
            conf_icon = "🟢" if r.get("confidence") == "HIGH" else "🟡"
            reason = (r.get("reason") or "")[:80]
            msg_lines.append(f"{conf_icon} *{r['ticker']}*  {r.get('sector', '')}")
            msg_lines.append(f"   {r.get('decision', '')}")
            msg_lines.append(f"   _{reason}_")
            msg_lines.append("")

    # Future Priorities
    if snap.future_priorities:
        fp_str = "  ·  ".join(f"*{t}*" for t in snap.future_priorities)
        msg_lines.append(f"⏳ *Future Priority:* {fp_str}")
        msg_lines.append("")

    # Watch List
    if snap.watch_list:
        msg_lines.append(TG_SECTION_SEP)
        watch_str = "  ·  ".join(snap.watch_list)
        msg_lines.append(f"👁 *Watch List:* {watch_str}")
        msg_lines.append("")

    # Research Insight
    if snap.research_insights:
        ins = snap.research_insights[0]
        msg_lines.append(TG_SECTION_SEP)
        conclusion = (ins.get("conclusion") or "")[:120]
        question = (ins.get("question") or "")[:80]
        msg_lines.append(f"🔬 *Research:* {conclusion}")
        msg_lines.append(f"   _{question}_")
        msg_lines.append("")

    msg_lines.append(TG_SECTION_SEP)
    msg_lines.append(f"⏰ {now_cairo().strftime('%H:%M  |  %d %b %Y')}")

    full_msg = "\n".join(msg_lines)
    _tg_route(MORNING_BRIEF, full_msg, symbol="")

# =========================================
# ALERT FOR HIGH SCORE (REAL-TIME)
# =========================================

def send_alert_for_high_score(stock, score, result):
    """
    إرسال تنبيه فوري عندما يصل score إلى 35+
    """
    print(f"\n🚨 ALERT: {NAMES.get(stock, stock)} ({stock}) score {score}/100!")
    
    signal = result.get("signal", "WAIT").upper()
    emoji  = _SIGNAL_EMOJI.get(signal, "🔵")

    try:
        upside = ""
        try:
            pct = (float(result["target"]) - float(result["price"])) / float(result["price"]) * 100
            upside = f" (+{pct:.1f}%)"
        except Exception:
            pass

        msg = (
            f"{TG_REALTIME_HEADER}\n"
            f"{emoji} *{NAMES.get(stock, stock)}*  `{stock}`\n\n"
            f"   Decision   *Constitutional BUY*\n"
            f"   Price      *{result['price']} EGP*\n"
            f"   Target     *{round(float(result['target']), 2)} EGP*{upside}\n"
            f"{TG_SECTION_SEP}━━\n"
            f"⏰ {now_cairo().strftime('%H:%M  |  %d %b %Y')}"
        )
        _tg_route(HIGH_SCORE, msg, symbol=stock)
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

_BUY_SIGNALS = {"Buy", "Strong Buy", "Very Strong Buy", "Institutional Buy"}

def _register_new_positions(results):
    """
    Registers new positions for all buy-eligible signals.
    Eligibility: total >= 35 AND r1 >= PRICE_GATE AND adj_score >= entry_gate.
    liq_ok (Sweep & Reverse) is metadata only — does not block position entry.
    Signal class (Buy/Strong Buy/Very Strong Buy/Institutional Buy) reflects adj_score tier.
    """
    # Single source of truth: signal field — classify() ensures all buy classes
    # passed both the price gate and the adj_score entry gate.
    qualifying = {
        s for s in STOCKS
        if results[s].get("ok") and results[s].get("signal") in _BUY_SIGNALS
    }
    for stock in qualifying:
        positions = load_open_positions()
        if stock not in positions:
            price = results[stock].get("price", 0)
            if price > 0:
                pat = results[stock].get("pattern") or {}
                add_position(stock, price, datetime.now(CAIRO).isoformat(),
                             entry_score=results[stock].get("score", 0),
                             entry_pattern_score=round(pat.get("pattern_score", 0)),
                             entry_effective_score=round(pat.get("effective_score", 0)))
                print(f"📌 تسجيل مركز جديد ({results[stock].get('signal')}): {NAMES.get(stock, stock)} @ {price}")

def backfill_pattern_scores():
    pass  # pattern_engine removed 2026-06-21


def _run_scan_workflow(holiday_mode, last_trading, email_suffix, morning_mid=None):
    """
    Shared workflow for daily and manual scans:
    1. Fetch data once
    2. Register new positions + update targets
    3. Rebuild HTML + snapshot from cached data (one snapshot, no re-fetch)
    4. Send email + Telegram from the SAME snapshot
    5. Save results + detect changes
    """
    from notifications.morning_guard import html_hash, snap_hash, record_morning_done

    previous_results = load_previous_results()

    # Step 0: backfill missing pattern scores for existing positions
    backfill_pattern_scores()

    # Step 1: fetch data
    html, results, _ = build_report(holiday_mode=holiday_mode, last_trading=last_trading)

    # Step 2: register positions, update targets
    _register_new_positions(results)
    cur_prices = _collect_current_prices(results)
    monitor_positions(cur_prices)
    monitor_reinforcement(cur_prices, results)
    resolved = check_outcomes(cur_prices)

    # Step 3: rebuild HTML using cached prices — ONE snapshot build, shared with Telegram
    html, _, snap = build_report(holiday_mode=holiday_mode, last_trading=last_trading,
                                 _cached_results=results)

    # Step 4: send email + Telegram from the same snapshot
    send_email(html, subject_suffix=email_suffix)
    send_telegram_alerts(results, snap=snap)

    # Log morning delivery hashes
    if morning_mid:
        try:
            record_morning_done(morning_mid, "sent",
                                build_hash=html_hash(html),
                                snapshot_hash=snap_hash(snap))
        except Exception:
            pass

    # Step 5: persist + change alerts
    save_scan_results(results)
    save_signal_history(results)
    save_rank_history(results)

    # Step 6: log signals for outcome tracking
    for s in STOCKS:
        if results.get(s, {}).get("ok"):
            log_signal(s, results[s])

    # Step 7: research platform — تسجيل + متابعة + تقرير أسبوعي
    db_log_signals(results, SECTORS, {}, is_ramadan(), is_cbe_window())
    tracker_run_all(verbose=False)
    maybe_run_weekly_report()

    # Layer 10: continuous learning — runs if >= 10 new outcomes and > 24h since last cycle
    try:
        from continuous_learning import schedule_daily
        schedule_daily()
    except Exception as _cl_err:
        print(f"  [ContinuousLearning] skipped: {_cl_err}")

    # EARLY BUY Research Shadow — log, enrich outcomes, snapshot performance
    try:
        import early_buy_tracker as _ebt
        _today = now_cairo().strftime("%Y-%m-%d")
        _ebt.daily_run(results=results, signal_date=_today)
    except Exception as _eb_err:
        print(f"  [EarlyBuy] skipped: {_eb_err}")

    # Pattern Intelligence 2.0 — daily incremental learning (research only)
    try:
        import pattern_kb as _pkb
        _pkb_result = _pkb.daily_run()
        print(f"  [PatternKB] daily_run: {_pkb_result.get('n_signals',0)} signals "
              f"{_pkb_result.get('n_patterns',0)} patterns "
              f"dir_corrected={_pkb_result.get('directions_corrected',False)}")
    except Exception as _pkb_err:
        print(f"  [PatternKB] skipped: {_pkb_err}")
    changes = detect_signal_changes(results, previous_results)
    if changes:
        send_change_alert(changes)

    # Discount Reversal Engine — daily scan
    try:
        _dre_result = run_discount_scan(results=results)
        if _dre_result:
            print(f"  [DiscountReversal] {len(_dre_result)} signals persisted "
                  f"(top: {_dre_result[0]['symbol']} score={_dre_result[0]['final_score']:.1f})")
    except Exception as _dre_err:
        print(f"  [DiscountReversal] skipped: {_dre_err}")


def run_discount_scan(results: dict = None) -> list:
    """
    Run the Discount Reversal Engine against today's signals.
    Reads live signal data from `results` (output of analyze()) or falls back
    to the signals table.  For each EGX30 symbol with price data available,
    calls engine.scan_symbol() and persists to discount_signals.
    Returns list of signal dicts sorted by final_score DESC.
    """
    from discount_reversal_engine import DiscountReversalEngine, EGX30_SYMBOLS

    engine = DiscountReversalEngine(db_path="egx_research.db")
    today_str = today_cairo().strftime("%Y-%m-%d")
    persisted = []

    # Build candidate list from live results dict (keyed by symbol)
    candidates = {}
    if results:
        for sym, r in results.items():
            if not r.get("ok") or sym not in EGX30_SYMBOLS:
                continue
            candidates[sym] = r

    # Fallback: read today's rows from signals table
    if not candidates:
        import sqlite3 as _sq
        conn = _sq.connect("egx_research.db")
        rows = conn.execute(
            "SELECT symbol, price, eq, buy_hi, sell_lo, macd_val, macd_hist, snap_consol_len "
            "FROM signals WHERE signal_date=? AND eq IS NOT NULL",
            (today_str,)
        ).fetchall()
        conn.close()
        for row in rows:
            sym = row[0]
            if sym in EGX30_SYMBOLS:
                candidates[sym] = {
                    "price": row[1], "eq": row[2], "buy_hi": row[3],
                    "sell_lo": row[4], "macd_val": row[5], "macd_hist": row[6],
                    "snap_consol_len": row[7],
                }

    for sym, r in candidates.items():
        try:
            # Download OHLCV price history
            df_raw = download_data(sym, 60)
            if df_raw.empty or len(df_raw) < 10:
                continue

            # Normalise columns to lowercase
            df_price = df_raw.rename(columns={
                "Open": "open", "High": "high", "Low": "low",
                "Close": "close", "Volume": "volume"
            }).reset_index()
            df_price = df_price.rename(columns={df_price.columns[0]: "date"})

            # Resolve price zone boundaries
            eq_val      = r.get("eq") or 0.0
            buy_hi_val  = r.get("buy_hi") or 0.0
            sell_lo_val = r.get("sell_lo") or 0.0
            if eq_val <= 0:
                # derive from swings if not in results
                try:
                    hi_v, lo_v, eq_v, bhi, slo = swings(df_raw)
                    eq_val = eq_v; buy_hi_val = bhi; sell_lo_val = slo
                except Exception:
                    continue

            discount_bottom = buy_hi_val if buy_hi_val > 0 else eq_val * 0.90
            premium_top     = sell_lo_val if sell_lo_val > 0 else eq_val * 1.10
            macd_v  = r.get("macd_val") or 0.0
            macd_h  = r.get("macd_hist") or r.get("macd_signal") or 0.0
            days_disc = int(r.get("snap_consol_len") or 0)

            sig = engine.scan_symbol(
                symbol=sym,
                price_data=df_price,
                eq=eq_val,
                discount_bottom=discount_bottom,
                premium_top=premium_top,
                macd_val=macd_v,
                macd_hist=macd_h,
                days_in_discount=days_disc,
            )
            if sig:
                engine.persist_signal(sig)
                persisted.append(sig)
        except Exception as _e:
            logger.debug(f"[DiscountReversal] {sym}: {_e}")

    persisted.sort(key=lambda x: x.get("final_score", 0), reverse=True)
    return persisted


def integrate_with_existing_signal(signal_row: dict, price_history, engine) -> dict:
    """
    Wire a single signal row (from signals table) into the DiscountReversalEngine.
    signal_row: dict with keys matching signals table columns.
    price_history: pd.DataFrame [date, open, high, low, close, volume]
    engine: DiscountReversalEngine instance
    Returns persisted signal dict or None.
    """
    from discount_reversal_engine import EGX30_SYMBOLS
    sym = signal_row.get("symbol", "")
    if sym not in EGX30_SYMBOLS:
        return None

    eq_val  = signal_row.get("eq") or 0.0
    bhi     = signal_row.get("buy_hi") or eq_val * 0.90
    slo     = signal_row.get("sell_lo") or eq_val * 1.10
    sig = engine.scan_symbol(
        symbol=sym,
        price_data=price_history,
        eq=eq_val,
        discount_bottom=bhi,
        premium_top=slo,
        macd_val=signal_row.get("macd_val") or 0.0,
        macd_hist=signal_row.get("macd_hist") or 0.0,
        days_in_discount=int(signal_row.get("snap_consol_len") or 0),
    )
    if sig:
        engine.persist_signal(sig)
    return sig


def _ensure_backfill():
    """يشغّل الباكتست التاريخي مرة واحدة فقط لو السجل فاضي أو صغير."""
    import os, json
    log_file = "signal_log.json"
    try:
        if os.path.exists(log_file):
            with open(log_file) as f:
                data = json.load(f)
            hist_count = sum(1 for s in data.get("signals", [])
                             if s.get("source") == "backfill")
            if hist_count >= 50:
                return  # عنده بيانات كافية
        print("  🔄 Running historical backfill (first time setup)...")
        run_backfill(period="2y")
    except Exception as e:
        print(f"  ⚠️ Backfill skipped: {e}")


def daily_scan():
    from notifications.morning_guard import is_morning_sent, record_morning_start
    date_str = today_cairo().isoformat()

    if is_morning_sent(date_str):
        print(f"⚠️  Morning report for {date_str} already sent — EXIT (idempotency guard)")
        return

    morning_mid = record_morning_start(date_str)
    print(f"\n📅 Daily scan started at {fmt_cairo()} [id={morning_mid[:8]}]")
    _ensure_backfill()
    if is_egx_trading_day(today_cairo()):
        _run_scan_workflow(holiday_mode=False, last_trading=None, email_suffix="",
                          morning_mid=morning_mid)
    else:
        last_td = most_recent_trading_day(today_cairo())
        _run_scan_workflow(
            holiday_mode=True,
            last_trading=str(last_td),
            email_suffix=f" (Holiday — Last Session: {last_td})",
            morning_mid=morning_mid,
        )
    print("\n✅ Daily scan completed!")


def continuous_scan():
    print(f"\n🔄 Continuous scan at {fmt_cairo()}")
    previous_results = load_previous_results()
    html, current_results, _ = build_report(holiday_mode=False)
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
    _ensure_backfill()
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


_SIGNAL_HISTORY_DAYS = 1825  # keep 5 years — protects historical backtest data for ML

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
                "date":            today,
                "score":           d.get("score", 0),
                "price":           d.get("price", 0),
                "r1":              d.get("r1", 0),
                "signal":          d.get("signal", ""),
                "factor_exp_score": d.get("factor_exp_score", 0),
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


_RANK_HISTORY_DAYS = 90  # rolling window for rank movement tracking


def save_rank_history(results):
    """
    Persist daily blended rank snapshot to rank_history.json.
    Enables rank-change indicators (▲/▼) across sessions.
    Keeps a rolling 90-day window.
    """
    try:
        today = date.today().isoformat()
        cutoff = (date.today() - timedelta(days=_RANK_HISTORY_DAYS)).isoformat()
        hist = {}
        if os.path.exists("rank_history.json"):
            with open("rank_history.json", "r", encoding="utf-8") as f:
                hist = json.load(f)
        # Compute blended rank for every valid stock
        ranked = []
        for sym, r in results.items():
            if not isinstance(r, dict) or not r.get("ok"):
                continue
            fexp  = r.get("factor_exp_score", 0) or 0
            score = r.get("score", 0) or 0
            sig   = r.get("signal", "")
            blended = 0.60 * fexp + 0.40 * score
            ranked.append((sym, blended, fexp, score, sig))
        ranked.sort(key=lambda x: x[1], reverse=True)
        snapshot = {}
        for rank_pos, (sym, blended, fexp, score, sig) in enumerate(ranked, 1):
            snapshot[sym] = {
                "rank":    rank_pos,
                "blended": round(blended, 2),
                "fexp":    round(fexp, 2),
                "score":   score,
                "signal":  sig,
            }
        hist[today] = snapshot
        # Prune old entries
        hist = {d: v for d, v in hist.items() if d >= cutoff}
        with open("rank_history.json", "w", encoding="utf-8") as f:
            json.dump(hist, f, ensure_ascii=False, separators=(",", ":"))
        print(f"✅ rank_history.json updated ({today}, {len(snapshot)} stocks)")
    except Exception as e:
        print(f"❌ Error saving rank history: {e}")


def load_rank_changes():
    """
    Return dict mapping symbol → previous_rank (most recent prior session).
    Returns empty dict if no history available.
    """
    try:
        if not os.path.exists("rank_history.json"):
            return {}
        with open("rank_history.json", "r", encoding="utf-8") as f:
            hist = json.load(f)
        today = date.today().isoformat()
        past_dates = sorted([d for d in hist if d < today], reverse=True)
        if not past_dates:
            return {}
        prev = hist[past_dates[0]]
        return {sym: v["rank"] for sym, v in prev.items()}
    except Exception:
        return {}


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
        current_raw_score = current.get("raw_score", current_score)
        current_price = current.get("price", "N/A")
        current_target = current.get("target", "N/A")

        # Signal upgraded from Skip/Wait into a buy class
        BUY_SIGNALS = {"Buy", "Strong Buy", "Very Strong Buy", "Institutional Buy"}
        if previous_sig in ("Skip", "Wait") and current_sig in BUY_SIGNALS:
            changed_stocks.append({
                "stock": stock,
                "from": previous_sig,
                "to": current_sig,
                "score": current_score,
                "raw_score": current_raw_score,
                "factor_exp_score": current.get("factor_exp_score", 0),
                "ctx_label": current.get("ctx_label", ""),
                "price": current_price,
                "target": current_target,
                "entry_zones": current.get("entry_zones", None),
                "pattern": current.get("pattern", {}),
            })
    
    return changed_stocks


def send_change_email(changed_stocks):
    """
    إرسال Email فوري عند تغيير أي سهم (whitelist أو عادي) إلى BUY
    """
    if not changed_stocks:
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
        fexp   = float(item.get("factor_exp_score", 0) or 0)
        blended = round(0.60 * fexp + 0.40 * score, 1)
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

        pat_row = ""  # Pattern analysis removed — constitutional portfolio presentation only

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

            # ── buy alert context ──
            f'<tr><td style="padding:12px 16px 0;">'
            f'<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#0d1117;border-radius:10px;">'
            f'<tr><td style="padding:12px 15px;">'
            f'<div style="color:#22c55e;font-size:14px;font-weight:700;margin-bottom:6px;">⚡ Constitutional Buy Alert</div>'
            f'<div style="color:#94a3b8;font-size:11px;">Stock entered constitutional buy zone — portfolio management action required.</div>'
            f'</td></tr></table>'
            f'</td></tr>'

            # ── pattern intelligence ──
            + pat_row +

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
        'EGX Constitutional Investment Platform &copy; 2026</p>'
        '</td></tr>'

        '</table>'
        '</td></tr></table>'
        '</body></html>'
    )

    date_str = now_cairo().strftime("%Y-%m-%d %H:%M")
    subject  = f"🚨 Signal Alert: {total_count} stock(s) moved to BUY — {date_str}"
    ok = _send_email_raw(subject=subject, html=html_body, to=EMAIL)
    if ok:
        print(f"📧 Email alert sent for {total_count} stock(s) "
              f"({len(whitelist_stocks)} whitelist, {len(normal_stocks)} normal)")
    return ok


def send_change_alert(changed_stocks):
    """Send instant Telegram alert when a signal flips to BUY."""
    if not changed_stocks:
        return

    date_str = now_cairo().strftime("%d %b %Y  %H:%M")
    lines = [
        TG_CHANGE_HEADER,
        f"_{date_str}_\n",
    ]

    for item in changed_stocks:
        stock  = item['stock']
        price  = item.get('price', 'N/A')
        target = item.get('target', 'N/A')
        raw_c  = item.get("raw_score", item["score"])
        adj_tag = f"  _(raw {raw_c:.0f})_" if raw_c != item["score"] else ""
        ctx_line = f"\n   {item['ctx_label']}" if item.get("ctx_label") else ""
        wl_tag  = "  ⭐ _Watchlist_" if stock in WHITELIST else ""

        try:
            upside = f"  (+{(float(target) - float(price)) / float(price) * 100:.1f}%)"
        except Exception:
            upside = ""

        lines.append(f"{'─'*25}")
        lines.append(f"📈 *{NAMES.get(stock, stock)}*  `{stock}`{wl_tag}")
        lines.append(f"   {item['from']}  →  *{item['to']}*")
        lines.append(f"   Constitutional BUY — entered buy zone{ctx_line}")
        lines.append(f"   Price      *{price} EGP*")
        lines.append(f"   Target     *{target} EGP*{upside}\n")

    message = "\n".join(lines)

    if _tg_route(SIGNAL_CHANGE, message, symbol="", check_duplicate=False):
        print("Signal change alert sent to Telegram")

    # إرسال Email للجميع مع التمييز
    send_change_email(changed_stocks)

# =========================================
# RUN
# =========================================

if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f"EGX Constitutional Investment Platform — GitHub Actions Mode")
    print(f"Start Time: {fmt_cairo()}")
    print(f"{'='*60}\n")

    # All mode-dispatch is now owned by ScanOrchestrator (Step 4).
    # main.py delegates immediately — no inline mode logic here.
    try:
        from notifications.scan_orchestrator import ScanOrchestrator
        ok = ScanOrchestrator().dispatch_from_env()
        sys.exit(0 if ok is not False else 1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        traceback.print_exc()
        sys.exit(1)

