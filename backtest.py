"""
EGX SMC Scanner - 5-Year Backtesting System
No Stop Loss | Time-Independent | Z3-Optimized Parameters

استراتيجية SMC على 5 سنوات من البيانات التاريخية
"""

import pandas as pd
import numpy as np
import yfinance as yf
import requests
import json
import os
from datetime import datetime, timedelta
from tqdm import tqdm
import warnings
warnings.filterwarnings('ignore')

# =========================================
# Z3 CONSTRAINT SOLVER FOR OPTIMIZATION
# =========================================
try:
    from z3 import *
    HAS_Z3 = True
except ImportError:
    print("⚠️ Z3 not installed. Install with: pip install z3-solver")
    HAS_Z3 = False

# =========================================
# CONFIGURATION
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

WHITELIST = [
    "FWRY.CA", "EAST.CA", "ETEL.CA", "EMFD.CA",
    "PHDC.CA", "HRHO.CA", "MCQE.CA", "OIH.CA", "GBCO.CA",
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

# =========================================
# DATA DOWNLOAD (5 YEARS)
# =========================================

def download_historical_data(symbol, years=5):
    """تحميل بيانات 5 سنوات من yfinance"""
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365 * years)
        
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start_date, end=end_date, interval="1d", auto_adjust=False)
        
        if df.empty:
            print(f"  ⚠️ {symbol}: لا توجد بيانات")
            return pd.DataFrame()
        
        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.index = df.index.tz_localize(None)
        return df
    
    except Exception as e:
        print(f"  ❌ {symbol}: خطأ في التحميل - {e}")
        return pd.DataFrame()


# =========================================
# SMC INDICATORS (من main.py)
# =========================================

def swings(close, lb=80):
    """الدعم والمقاومة - إطار 80 يوم"""
    hi = float(close.tail(lb).max())
    lo = float(close.tail(lb).min())
    rng = hi - lo
    eq = lo + rng * 0.50
    buy_hi = lo + rng * 0.15
    sell_lo = lo + rng * 0.85
    return hi, lo, eq, buy_hi, sell_lo

def calc_avwap(df):
    """Anchored VWAP مع Lower Band"""
    d = pd.DataFrame({
        "H": df["High"], "L": df["Low"],
        "C": df["Close"], "V": df["Volume"],
    }).dropna()
    
    if len(d) < 5:
        v = float(d["C"].iloc[-1]) if len(d) else 0.0
        return v, v
    
    lookback = min(60, len(d))
    tail_low = d["L"].tail(lookback)
    anchor_idx = int(tail_low.values.argmin())
    anchor_pos = len(d) - lookback + anchor_idx
    
    if anchor_pos >= len(d) - 3:
        anchor_pos = max(0, len(d) - 20)
    
    d_anc = d.iloc[anchor_pos:].copy()
    if len(d_anc) < 3:
        d_anc = d.copy()
    
    tp = (d_anc["H"] + d_anc["L"] + d_anc["C"]) / 3
    av = (tp * d_anc["V"]).cumsum() / d_anc["V"].cumsum()
    std = tp.expanding().std().fillna(0)
    lo = av - std
    
    return float(av.iloc[-1]), float(lo.iloc[-1])

def calc_macd(close):
    """MACD مع Signal Line"""
    m = close.ewm(span=12).mean() - close.ewm(span=26).mean()
    s = m.ewm(span=9).mean()
    return m, s, m - s

def calc_stopping_volume(df, eq, lo, lookback=30, vol_mult=1.5, range_ratio=0.5):
    """كشف Stopping Volume في منطقة الخصم"""
    needed = ["High", "Low", "Close", "Open", "Volume"]
    if not all(c in df.columns for c in needed) or len(df) < lookback + 5:
        return False, 0.0
    
    d = df[needed].dropna().tail(lookback + 20)
    avg_vol = d["Volume"].rolling(lookback).mean()
    candle_rng = d["High"] - d["Low"]
    avg_rng = candle_rng.rolling(lookback).mean()
    
    sv_candles = []
    for i in range(lookback, len(d)):
        c_close = float(d["Close"].iloc[i])
        c_vol = float(d["Volume"].iloc[i])
        c_rng = float(candle_rng.iloc[i])
        a_vol = float(avg_vol.iloc[i])
        a_rng = float(avg_rng.iloc[i])
        if a_vol <= 0 or a_rng <= 0:
            continue
        if c_close >= eq:
            continue
        if c_vol < vol_mult * a_vol:
            continue
        if c_rng > range_ratio * a_rng:
            continue
        discount_range = eq - lo
        depth = (eq - c_close) / discount_range if discount_range > 0 else 0
        sv_candles.append({"idx": i, "close": c_close, "vol_ratio": c_vol / a_vol, "depth": depth})
    
    if not sv_candles:
        return False, 0.0
    
    best = sorted(sv_candles, key=lambda x: x["depth"] * 0.6 + min(x["vol_ratio"] / 5, 1.0) * 0.4, reverse=True)[0]
    score = min(1.0, best["depth"] * 0.6 + min(best["vol_ratio"] / 5, 1.0) * 0.4)
    return True, score

def _calc_rsi(close, period=14):
    """RSI بـ Wilder Smoothing"""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_g = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_l = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    rs = avg_g / avg_l.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

# =========================================
# BACKTESTING ENGINE
# =========================================

class BacktestEngine:
    def __init__(self, symbol, df, params=None):
        self.symbol = symbol
        self.df = df.copy()
        self.params = params or self._default_params()
        self.trades = []
        self.equity_curve = []
        self.buy_signals = []
        self.results = {}
    
    def _default_params(self):
        """المعاملات الافتراضية للاستراتيجية"""
        return {
            "price_gate_whitelist": 12,
            "price_gate_normal": 18,
            "liq_gate": 12,
            "demand_zone_weight": 0.20,
            "score_threshold": 35,
            "target_multiplier": 1.12,  # الهدف = السعر × 1.12
            "min_data_points": 80,
        }
    
    def _analyze_bar(self, idx):
        """تحليل شمعة واحدة (point-in-time analysis)"""
        if idx < self.params["min_data_points"]:
            return None
        
        # الحصول على البيانات حتى هذه النقطة
        hist_df = self.df.iloc[:idx+1]
        close = hist_df["Close"]
        
        cur = float(close.iloc[-1])
        
        # الحسابات الأساسية
        hi, lo, eq, buy_hi, sell_lo = swings(close)
        av, alo = calc_avwap(hist_df)
        
        # الدرجات
        r1 = self._score_price(cur, lo, hi, eq, buy_hi)
        
        close_tail = close.tail(30)
        if len(close_tail) >= 10:
            ml, _, _ = calc_macd(close)
            r6 = self._score_macd(close)
        else:
            r6 = 0
        
        sv_hit, sv_score = calc_stopping_volume(hist_df, eq, lo)
        r8 = int(sv_hit) * 15
        
        total_score = min(r1 + r6 + r8, 100)
        
        # البوابات
        PRICE_GATE = self.params["price_gate_whitelist"] if self.symbol in WHITELIST else self.params["price_gate_normal"]
        price_ok = (r1 >= PRICE_GATE)
        
        return {
            "date": hist_df.index[-1],
            "price": cur,
            "score": total_score,
            "price_ok": price_ok,
            "hi": hi, "lo": lo, "eq": eq, "buy_hi": buy_hi,
            "r1": r1, "r6": r6, "r8": r8,
        }
    
    def _score_price(self, cur, lo, hi, eq, buy_hi):
        """تسجيل موضع السعر"""
        rng = hi - lo
        if rng <= 0:
            return 0
        
        if cur <= buy_hi:
            ratio = (cur - lo) / (buy_hi - lo) if (buy_hi - lo) > 0 else 0
            pts = max(round(30 * (1.0 - ratio * 0.40)), 0)
            return pts
        
        if cur < eq:
            ratio = (cur - buy_hi) / (eq - buy_hi) if (eq - buy_hi) > 0 else 1
            pts = max(round(30 * 0.60 * (1.0 - ratio)), 0)
            return pts
        
        return 0
    
    def _score_macd(self, close):
        """تسجيل MACD"""
        if len(close) < 15:
            return 0
        m, sg, h = calc_macd(close)
        macd_now = m.iloc[-1]
        macd_prev = m.iloc[-2]
        sig_now = sg.iloc[-1]
        sig_prev = sg.iloc[-2]
        
        if macd_now >= 0:
            return 0
        
        crossed_up = macd_prev <= sig_prev and macd_now > sig_now
        if crossed_up:
            return 4
        
        return 2
    
    def run(self):
        """تشغيل الاختبار الخلفي"""
        print(f"\n🔄 Backtesting {self.symbol}...")
        
        position = None  # {"entry_date": date, "entry_price": float, "qty": int}
        
        for idx in tqdm(range(self.params["min_data_points"], len(self.df)), desc=f"  {self.symbol}"):
            bar_analysis = self._analyze_bar(idx)
            
            if bar_analysis is None:
                continue
            
            date = bar_analysis["date"]
            price = bar_analysis["price"]
            score = bar_analysis["score"]
            price_ok = bar_analysis["price_ok"]
            
            # BUY SIGNAL
            if not position and price_ok and score >= self.params["score_threshold"]:
                # فتح مركز شراء
                entry_date = date
                entry_price = price
                target_price = price * self.params["target_multiplier"]
                
                position = {
                    "entry_date": entry_date,
                    "entry_price": entry_price,
                    "target": target_price,
                    "qty": 1,
                    "score": score,
                }
                
                self.buy_signals.append({
                    "date": date,
                    "price": price,
                    "score": score,
                })
            
            # SELL SIGNAL (when target hit OR max holding period)
            if position:
                # الهدف موجود → البيع عند تحقيقه
                if price >= position["target"]:
                    exit_date = date
                    exit_price = position["target"]
                    pnl = (exit_price - position["entry_price"]) * position["qty"]
                    pnl_pct = ((exit_price - position["entry_price"]) / position["entry_price"]) * 100
                    
                    self.trades.append({
                        "symbol": self.symbol,
                        "entry_date": position["entry_date"],
                        "entry_price": position["entry_price"],
                        "exit_date": exit_date,
                        "exit_price": exit_price,
                        "pnl": pnl,
                        "pnl_pct": pnl_pct,
                        "days_held": (exit_date - position["entry_date"]).days,
                        "reason": "target_hit",
                        "score": position["score"],
                    })
                    
                    position = None
                
                # Hold indefinitely (لا يوجد وقت محدد للخروج)
        
        # إغلاق أي مركز مفتوح في النهاية
        if position:
            exit_date = self.df.index[-1]
            exit_price = float(self.df["Close"].iloc[-1])
            pnl = (exit_price - position["entry_price"]) * position["qty"]
            pnl_pct = ((exit_price - position["entry_price"]) / position["entry_price"]) * 100
            
            self.trades.append({
                "symbol": self.symbol,
                "entry_date": position["entry_date"],
                "entry_price": position["entry_price"],
                "exit_date": exit_date,
                "exit_price": exit_price,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "days_held": (exit_date - position["entry_date"]).days,
                "reason": "end_of_period",
                "score": position["score"],
            })
        
        return self._calculate_metrics()
    
    def _calculate_metrics(self):
        """حساب مقاييس الأداء"""
        if not self.trades:
            return {
                "symbol": self.symbol,
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0,
                "avg_win": 0,
                "avg_loss": 0,
                "total_pnl": 0,
                "total_pnl_pct": 0,
                "profit_factor": 0,
                "buy_signals": len(self.buy_signals),
            }
        
        trades_df = pd.DataFrame(self.trades)
        
        total_trades = len(trades_df)
        winning_trades = len(trades_df[trades_df["pnl"] > 0])
        losing_trades = len(trades_df[trades_df["pnl"] < 0])
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        gross_profit = trades_df[trades_df["pnl"] > 0]["pnl"].sum()
        gross_loss = abs(trades_df[trades_df["pnl"] < 0]["pnl"].sum())
        
        avg_win = (gross_profit / winning_trades) if winning_trades > 0 else 0
        avg_loss = (gross_loss / losing_trades) if losing_trades > 0 else 0
        
        total_pnl = trades_df["pnl"].sum()
        total_pnl_pct = trades_df["pnl_pct"].mean()
        
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (1.0 if gross_profit > 0 else 0)
        
        return {
            "symbol": self.symbol,
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "total_pnl": total_pnl,
            "total_pnl_pct": total_pnl_pct,
            "profit_factor": profit_factor,
            "buy_signals": len(self.buy_signals),
        }


# =========================================
# Z3 PARAMETER OPTIMIZATION (ONE TIME)
# =========================================

def optimize_parameters_with_z3(sample_results, max_iterations=100):
    """تحسين المعاملات باستخدام Z3 (مرة واحدة فقط)"""
    
    if not HAS_Z3:
        print("⚠️ Z3 غير متاح. استخدام المعاملات الافتراضية...")
        return {
            "price_gate_whitelist": 12,
            "price_gate_normal": 18,
            "liq_gate": 12,
            "score_threshold": 35,
            "target_multiplier": 1.12,
        }
    
    print("\n🧮 تحسين المعاملات باستخدام Z3...")
    
    # إنشاء متغيرات Z3
    solver = Solver()
    
    price_gate_wl = Int('price_gate_wl')
    price_gate_normal = Int('price_gate_normal')
    score_threshold = Int('score_threshold')
    target_mult_int = Int('target_mult_int')  # 100 = 1.00, 115 = 1.15
    
    # القيود
    solver.add(price_gate_wl >= 10, price_gate_wl <= 15)
    solver.add(price_gate_normal >= 15, price_gate_normal <= 25)
    solver.add(score_threshold >= 30, score_threshold <= 50)
    solver.add(target_mult_int >= 105, target_mult_int <= 120)
    solver.add(price_gate_wl < price_gate_normal)
    
    # نسبة الربح المرغوبة من العينة
    if sample_results and len(sample_results) > 0:
        avg_win_rate = np.mean([r.get("win_rate", 0) for r in sample_results])
        
        # نريد معاملات تزيد نسبة الفوز
        solver.add(score_threshold < 40)  # عتبة منخفضة = إشارات أكثر
    
    # حل المسألة
    if solver.check() == sat:
        model = solver.model()
        
        optimized = {
            "price_gate_whitelist": model[price_gate_wl].as_long(),
            "price_gate_normal": model[price_gate_normal].as_long(),
            "score_threshold": model[score_threshold].as_long(),
            "target_multiplier": model[target_mult_int].as_long() / 100.0,
            "liq_gate": 12,
        }
        
        print(f"✅ Z3 وجد معاملات مثلى:")
        print(f"   - Price Gate (Whitelist): {optimized['price_gate_whitelist']}")
        print(f"   - Price Gate (Normal): {optimized['price_gate_normal']}")
        print(f"   - Score Threshold: {optimized['score_threshold']}")
        print(f"   - Target Multiplier: {optimized['target_multiplier']:.2f}x")
        
        return optimized
    else:
        print("⚠️ Z3 لم يجد حل. استخدام المعاملات الافتراضية...")
        return {
            "price_gate_whitelist": 12,
            "price_gate_normal": 18,
            "score_threshold": 35,
            "target_multiplier": 1.12,
            "liq_gate": 12,
        }


# =========================================
# MAIN BACKTESTING WORKFLOW
# =========================================

def run_full_backtest(stocks=None):
    """تشغيل الاختبار الخلفي الشامل"""
    
    stocks = stocks or STOCKS
    all_results = []
    all_trades = []
    
    print("\n" + "="*70)
    print("🚀 EGX SMC SCANNER - 5-YEAR BACKTEST")
    print("="*70)
    print(f"📊 تحميل البيانات لمدة 5 سنوات من {len(stocks)} سهم...")
    print()
    
    # تحميل البيانات
    data_cache = {}
    for symbol in stocks:
        df = download_historical_data(symbol)
        if not df.empty:
            data_cache[symbol] = df
            print(f"  ✅ {symbol} ({NAMES.get(symbol, symbol)}): {len(df)} يوم")
    
    print(f"\n✅ تم تحميل {len(data_cache)} سهم بنجاح\n")
    
    # العينة الأولية للتحسين
    print("📈 تشغيل عينة أولية (3 أسهم) للتحسين...")
    sample_params = BacktestEngine.init_default_params()
    sample_results = []
    
    for symbol in list(data_cache.keys())[:3]:
        engine = BacktestEngine(symbol, data_cache[symbol], sample_params)
        result = engine.run()
        sample_results.append(result)
    
    # تحسين المعاملات باستخدام Z3 (مرة واحدة)
    optimized_params = optimize_parameters_with_z3(sample_results)
    
    print("\n" + "="*70)
    print("🔄 تشغيل الاختبار الخلفي الكامل بالمعاملات المحسّنة...")
    print("="*70 + "\n")
    
    # تشغيل الاختبار على جميع الأسهم
    for symbol in data_cache.keys():
        engine = BacktestEngine(symbol, data_cache[symbol], optimized_params)
        result = engine.run()
        all_results.append(result)
        all_trades.extend(engine.trades)
    
    return all_results, all_trades, optimized_params


# =========================================
# REPORTING
# =========================================

def generate_report(all_results, all_trades, optimized_params):
    """توليد تقرير شامل"""
    
    print("\n" + "="*70)
    print("📊 BACKTEST RESULTS - 5 YEARS")
    print("="*70 + "\n")
    
    # ملخص المعاملات
    print("⚙️ OPTIMIZED PARAMETERS (Z3):")
    print(f"   • Price Gate (Whitelist): {optimized_params.get('price_gate_whitelist', 12)}")
    print(f"   • Price Gate (Normal): {optimized_params.get('price_gate_normal', 18)}")
    print(f"   • Score Threshold: {optimized_params.get('score_threshold', 35)}")
    print(f"   • Target Multiplier: {optimized_params.get('target_multiplier', 1.12):.2f}x")
    print()
    
    # نتائج الأسهم
    results_df = pd.DataFrame(all_results)
    results_df = results_df.sort_values("profit_factor", ascending=False)
    
    print("📈 PERFORMANCE BY STOCK:\n")
    print(f"{'Stock':<12} {'Trades':<8} {'Win%':<8} {'Profit Factor':<15} {'Total P&L':<12} {'Avg P&L%':<10}")
    print("-" * 75)
    
    for _, row in results_df.iterrows():
        print(f"{row['symbol']:<12} {row['total_trades']:<8} "
              f"{row['win_rate']:.1f}%{'':<4} {row['profit_factor']:.2f}{'':<12} "
              f"{row['total_pnl']:>10.2f} {row['total_pnl_pct']:>9.2f}%")
    
    print()
    
    # إجمالي النتائج
    total_trades = len(all_trades)
    winning_trades = len([t for t in all_trades if t["pnl"] > 0])
    losing_trades = len([t for t in all_trades if t["pnl"] < 0])
    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
    
    gross_profit = sum(t["pnl"] for t in all_trades if t["pnl"] > 0)
    gross_loss = abs(sum(t["pnl"] for t in all_trades if t["pnl"] < 0))
    
    total_pnl = sum(t["pnl"] for t in all_trades)
    avg_pnl_pct = np.mean([t["pnl_pct"] for t in all_trades]) if all_trades else 0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (1.0 if gross_profit > 0 else 0)
    
    print("🎯 OVERALL SUMMARY:\n")
    print(f"Total Trades:        {total_trades}")
    print(f"Winning Trades:      {winning_trades}")
    print(f"Losing Trades:       {losing_trades}")
    print(f"Win Rate:            {win_rate:.2f}%")
    print(f"Gross Profit:        {gross_profit:>12.2f} EGP")
    print(f"Gross Loss:          {gross_loss:>12.2f} EGP")
    print(f"Total P&L:           {total_pnl:>12.2f} EGP")
    print(f"Avg P&L per Trade:   {total_pnl/total_trades:>12.2f} EGP" if total_trades > 0 else "N/A")
    print(f"Profit Factor:       {profit_factor:.2f}x")
    print(f"Avg Return per Trade: {avg_pnl_pct:.2f}%")
    print()
    
    # أفضل الصفقات
    print("🏆 TOP 5 WINNING TRADES:\n")
    trades_df = pd.DataFrame(all_trades)
    trades_df = trades_df.sort_values("pnl_pct", ascending=False)
    
    for i, (_, trade) in enumerate(trades_df.head(5).iterrows(), 1):
        print(f"{i}. {trade['symbol']}: {trade['entry_date'].date()} → {trade['exit_date'].date()} | "
              f"+{trade['pnl']:.2f} EGP (+{trade['pnl_pct']:.2f}%)")
    
    print()
    
    # أسوأ الصفقات
    print("💔 TOP 5 LOSING TRADES:\n")
    for i, (_, trade) in enumerate(trades_df.tail(5).iterrows(), 1):
        print(f"{i}. {trade['symbol']}: {trade['entry_date'].date()} → {trade['exit_date'].date()} | "
              f"{trade['pnl']:.2f} EGP ({trade['pnl_pct']:.2f}%)")
    
    print()
    print("="*70)
    
    # حفظ النتائج
    save_results(all_results, all_trades, optimized_params)


def save_results(all_results, all_trades, optimized_params):
    """حفظ النتائج إلى ملفات JSON و CSV"""
    
    # حفظ ملخص النتائج
    results_df = pd.DataFrame(all_results)
    results_df.to_csv("backtest_results.csv", index=False)
    
    # حفظ كل الصفقات
    trades_df = pd.DataFrame(all_trades)
    if not trades_df.empty:
        trades_df.to_csv("backtest_trades.csv", index=False)
    
    # حفظ المعاملات المحسّنة
    with open("optimized_params.json", "w") as f:
        json.dump(optimized_params, f, indent=2)
    
    print("✅ تم حفظ النتائج:")
    print("   - backtest_results.csv (ملخص الأسهم)")
    print("   - backtest_trades.csv (جميع الصفقات)")
    print("   - optimized_params.json (المعاملات المحسّنة)")


# =========================================
# ADD MISSING METHOD
# =========================================

def BacktestEngine.init_default_params(cls):
    """المعاملات الافتراضية"""
    return {
        "price_gate_whitelist": 12,
        "price_gate_normal": 18,
        "liq_gate": 12,
        "score_threshold": 35,
        "target_multiplier": 1.12,
        "min_data_points": 80,
    }

# إصلاح الطريقة
BacktestEngine.init_default_params = staticmethod(lambda: {
    "price_gate_whitelist": 12,
    "price_gate_normal": 18,
    "liq_gate": 12,
    "score_threshold": 35,
    "target_multiplier": 1.12,
    "min_data_points": 80,
})

# =========================================
# MAIN
# =========================================

if __name__ == "__main__":
    try:
        all_results, all_trades, optimized_params = run_full_backtest()
        generate_report(all_results, all_trades, optimized_params)
        
        print("\n✅ تم الانتهاء من الاختبار الخلفي بنجاح!")
    
    except Exception as e:
        print(f"\n❌ خطأ: {e}")
        import traceback
        traceback.print_exc()
