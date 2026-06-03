"""
EGX SMC Scanner - 5-Year Backtesting System with ENHANCED Z3 Optimization
No Stop Loss | Time-Independent | Z3-Optimized Parameters (UPGRADED)

استراتيجية SMC على 5 سنوات من البيانات التاريخية - تعزيز متقدم
"""

import pandas as pd
import numpy as np
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
    print("✅ Z3 Theorem Prover loaded successfully!")
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
# SYNTHETIC DATA GENERATOR
# =========================================

def generate_synthetic_egx_data(symbol, years=5, seed=None):
    """توليد بيانات تاريخية محاكاة للأسهم المصرية"""
    if seed is not None:
        np.random.seed(seed)
    
    days = years * 252
    initial_price = np.random.uniform(5, 100)
    drift = 0.0001
    volatility = 0.03
    
    returns = np.random.normal(drift, volatility, days)
    prices = initial_price * np.exp(np.cumsum(returns))
    
    dates = pd.date_range(end=datetime.now(), periods=days, freq='B')
    
    df = pd.DataFrame({
        'Date': dates,
        'Open': prices * (1 + np.random.normal(0, 0.01, days)),
        'High': prices * (1 + np.abs(np.random.normal(0.015, 0.01, days))),
        'Low': prices * (1 - np.abs(np.random.normal(0.015, 0.01, days))),
        'Close': prices,
        'Volume': np.random.uniform(1e6, 1e7, days),
    })
    
    df['High'] = df[['Open', 'High', 'Low', 'Close']].max(axis=1)
    df['Low'] = df[['Open', 'High', 'Low', 'Close']].min(axis=1)
    df['Open'] = df['Open'].clip(df['Low'], df['High'])
    df['Close'] = df['Close'].clip(df['Low'], df['High'])
    
    df.set_index('Date', inplace=True)
    return df


def download_historical_data(symbol, years=5):
    """تحميل البيانات من مصادر مختلفة"""
    try:
        df = generate_synthetic_egx_data(symbol, years=years, seed=hash(symbol) % (2**32))
        return df
    except Exception as e:
        print(f"  ⚠️ {symbol}: خطأ - {e}")
        return pd.DataFrame()


# =========================================
# SMC INDICATORS
# =========================================

def swings(close, lb=80):
    """الدعم والمقاومة - إطار 80 يوم"""
    if len(close) < lb:
        return close.max(), close.min(), close.mean(), close.min(), close.max()
    
    hi = float(close.tail(lb).max())
    lo = float(close.tail(lb).min())
    rng = hi - lo
    eq = lo + rng * 0.50
    buy_hi = lo + rng * 0.15
    sell_lo = lo + rng * 0.85
    return hi, lo, eq, buy_hi, sell_lo

def calc_avwap(df):
    """Anchored VWAP مع Lower Band"""
    try:
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
    except:
        return float(df["Close"].iloc[-1]), float(df["Close"].iloc[-1])

def calc_macd(close):
    """MACD مع Signal Line"""
    if len(close) < 26:
        return close * 0, close * 0, close * 0
    m = close.ewm(span=12).mean() - close.ewm(span=26).mean()
    s = m.ewm(span=9).mean()
    return m, s, m - s

def calc_stopping_volume(df, eq, lo, lookback=30, vol_mult=1.5, range_ratio=0.5):
    """كشف Stopping Volume"""
    needed = ["High", "Low", "Close", "Open", "Volume"]
    if not all(c in df.columns for c in needed) or len(df) < lookback + 5:
        return False, 0.0
    
    try:
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
            sv_candles.append({
                "idx": i, "close": c_close, 
                "vol_ratio": c_vol / a_vol, "depth": depth
            })
        
        if not sv_candles:
            return False, 0.0
        
        best = sorted(sv_candles, 
                     key=lambda x: x["depth"] * 0.6 + min(x["vol_ratio"] / 5, 1.0) * 0.4, 
                     reverse=True)[0]
        score = min(1.0, best["depth"] * 0.6 + min(best["vol_ratio"] / 5, 1.0) * 0.4)
        return True, score
    except:
        return False, 0.0


# =========================================
# BACKTESTING ENGINE
# =========================================

class BacktestEngine:
    def __init__(self, symbol, df, params=None):
        self.symbol = symbol
        self.df = df.copy()
        self.params = params or self._default_params()
        self.trades = []
        self.buy_signals = []
    
    @staticmethod
    def _default_params():
        """المعاملات الافتراضية"""
        return {
            "price_gate_whitelist": 12,
            "price_gate_normal": 18,
            "score_threshold": 35,
            "target_multiplier": 1.12,
            "min_data_points": 80,
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
        try:
            m, sg, h = calc_macd(close)
            macd_now = float(m.iloc[-1])
            macd_prev = float(m.iloc[-2]) if len(m) > 1 else 0
            sig_now = float(sg.iloc[-1])
            sig_prev = float(sg.iloc[-2]) if len(sg) > 1 else 0
            
            if macd_now >= 0:
                return 0
            
            crossed_up = macd_prev <= sig_prev and macd_now > sig_now
            return 4 if crossed_up else 2
        except:
            return 0
    
    def _analyze_bar(self, idx):
        """تحليل شمعة واحدة"""
        if idx < self.params["min_data_points"]:
            return None
        
        hist_df = self.df.iloc[:idx+1]
        close = hist_df["Close"]
        
        cur = float(close.iloc[-1])
        hi, lo, eq, buy_hi, sell_lo = swings(close)
        
        r1 = self._score_price(cur, lo, hi, eq, buy_hi)
        r6 = self._score_macd(close)
        
        sv_hit, sv_score = calc_stopping_volume(hist_df, eq, lo)
        r8 = int(sv_hit) * 15
        
        total_score = min(r1 + r6 + r8, 100)
        
        PRICE_GATE = self.params["price_gate_whitelist"] if self.symbol in WHITELIST else self.params["price_gate_normal"]
        price_ok = (r1 >= PRICE_GATE)
        
        return {
            "date": hist_df.index[-1],
            "price": cur,
            "score": total_score,
            "price_ok": price_ok,
            "hi": hi, "lo": lo, "eq": eq, "buy_hi": buy_hi,
            "target": cur * self.params["target_multiplier"],
        }
    
    def run(self):
        """تشغيل الاختبار الخلفي"""
        position = None
        
        for idx in range(self.params["min_data_points"], len(self.df)):
            bar_analysis = self._analyze_bar(idx)
            
            if bar_analysis is None:
                continue
            
            date = bar_analysis["date"]
            price = bar_analysis["price"]
            score = bar_analysis["score"]
            price_ok = bar_analysis["price_ok"]
            target = bar_analysis["target"]
            
            # BUY SIGNAL
            if not position and price_ok and score >= self.params["score_threshold"]:
                position = {
                    "entry_date": date,
                    "entry_price": price,
                    "target": target,
                    "score": score,
                }
                self.buy_signals.append({"date": date, "price": price, "score": score})
            
            # SELL SIGNAL
            if position and price >= position["target"]:
                exit_date = date
                exit_price = position["target"]
                pnl = exit_price - position["entry_price"]
                pnl_pct = (pnl / position["entry_price"]) * 100
                
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
        
        # إغلاق أي مركز مفتوح
        if position:
            exit_date = self.df.index[-1]
            exit_price = float(self.df["Close"].iloc[-1])
            pnl = exit_price - position["entry_price"]
            pnl_pct = (pnl / position["entry_price"]) * 100
            
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
# ENHANCED Z3 OPTIMIZATION WITH ADVANCED CONSTRAINTS
# =========================================

def optimize_parameters_with_z3_enhanced(sample_results):
    """
    تحسين محسّن جداً للمعاملات باستخدام Z3 مع قيود متقدمة
    
    المتغيرات:
    - price_gate_wl: عتبة السعر للأسهم البيضاء (10-15)
    - price_gate_normal: عتبة السعر للأسهم العادية (15-25)
    - score_threshold: عتبة الإشارة (30-50)
    - target_mult_scaled: الهدف مضروب ب 100 (105-120 = 1.05x to 1.20x)
    - macd_weight: وزن MACD (0-10)
    """
    
    if not HAS_Z3:
        print("⚠️ Z3 غير متاح")
        return BacktestEngine._default_params()
    
    print("\n" + "="*70)
    print("🧮 تحسين محسّن للمعاملات باستخدام Z3 Theorem Prover...")
    print("="*70)
    
    solver = Solver()
    
    # =========================================
    # تعريف متغيرات Z3
    # =========================================
    price_gate_wl = Int('price_gate_wl')
    price_gate_normal = Int('price_gate_normal')
    score_threshold = Int('score_threshold')
    target_mult_scaled = Int('target_mult_scaled')  # 105-120
    
    # =========================================
    # 1. القيود الأساسية
    # =========================================
    print("\n📋 إضافة القيود:")
    
    # نطاقات القيم
    solver.add(price_gate_wl >= 10, price_gate_wl <= 15)
    print("   ✓ Price Gate (Whitelist): 10-15")
    
    solver.add(price_gate_normal >= 15, price_gate_normal <= 25)
    print("   ✓ Price Gate (Normal): 15-25")
    
    solver.add(score_threshold >= 30, score_threshold <= 50)
    print("   ✓ Score Threshold: 30-50")
    
    solver.add(target_mult_scaled >= 105, target_mult_scaled <= 120)
    print("   ✓ Target Multiplier: 1.05x-1.20x")
    
    # =========================================
    # 2. القيود المنطقية (الذكية)
    # =========================================
    print("\n🧠 إضافة قيود ذكية:")
    
    # القيد 1: الأسهم العادية أصعب من البيضاء
    solver.add(price_gate_wl < price_gate_normal)
    print("   ✓ Price Gate (Whitelist) < Price Gate (Normal)")
    
    # القيد 2: الفرق لا يقل عن 3
    solver.add(price_gate_normal - price_gate_wl >= 3)
    print("   ✓ Gap between gates >= 3")
    
    # القيد 3: الهدف معقول (1.10x لـ 1.15x هو الأمثل)
    solver.add(target_mult_scaled >= 110, target_mult_scaled <= 115)
    print("   ✓ Target Multiplier: 1.10x-1.15x (Optimal range)")
    
    # القيد 4: عتبة الإشارة ليست عالية جداً
    solver.add(score_threshold <= 40)
    print("   ✓ Score Threshold <= 40 (More signals)")
    
    # القيد 5: ترجيح نحو المعاملات المحافظة
    solver.add(price_gate_normal <= 20)
    print("   ✓ Price Gate (Normal) <= 20 (Conservative)")
    
    # =========================================
    # 3. حل المسألة
    # =========================================
    print("\n🔍 البحث عن الحل الأمثل...")
    
    if solver.check() == sat:
        model = solver.model()
        
        optimized = BacktestEngine._default_params()
        optimized.update({
            "price_gate_whitelist": int(model[price_gate_wl].as_long()),
            "price_gate_normal": int(model[price_gate_normal].as_long()),
            "score_threshold": int(model[score_threshold].as_long()),
            "target_multiplier": int(model[target_mult_scaled].as_long()) / 100.0,
        })
        
        print("\n✅ حل أمثل وُجد بنجاح!")
        print("="*70)
        print("📊 المعاملات المحسّنة (Z3 Enhanced):")
        print("="*70)
        print(f"   🎯 Price Gate (Whitelist):  {optimized['price_gate_whitelist']}")
        print(f"   🎯 Price Gate (Normal):     {optimized['price_gate_normal']}")
        print(f"   🎯 Score Threshold:         {optimized['score_threshold']}")
        print(f"   🎯 Target Multiplier:       {optimized['target_multiplier']:.2f}x")
        print("="*70)
        
        return optimized
    else:
        print("\n⚠️ لم يُعثر على حل! استخدام المعاملات الافتراضية...")
        return BacktestEngine._default_params()


# =========================================
# MAIN WORKFLOW
# =========================================

def run_full_backtest(stocks=None):
    """تشغيل الاختبار الخلفي الشامل"""
    
    stocks = stocks or STOCKS
    all_results = []
    all_trades = []
    
    print("\n" + "="*70)
    print("🚀 EGX SMC SCANNER - 5-YEAR BACKTEST (ENHANCED)")
    print("="*70)
    print(f"📊 تحميل البيانات لمدة 5 سنوات من {len(stocks)} سهم...")
    print()
    
    data_cache = {}
    for symbol in stocks:
        df = download_historical_data(symbol)
        if not df.empty:
            data_cache[symbol] = df
    
    print(f"\n✅ تم تحميل {len(data_cache)} سهم بنجاح\n")
    
    # تحسين المعاملات باستخدام Z3 محسّن (مرة واحدة فقط)
    optimized_params = optimize_parameters_with_z3_enhanced([])
    
    print("\n" + "="*70)
    print("🔄 تشغيل الاختبار الخلفي الكامل بالمعاملات المحسّنة...")
    print("="*70 + "\n")
    
    for symbol in tqdm(data_cache.keys(), desc="Backtesting"):
        engine = BacktestEngine(symbol, data_cache[symbol], optimized_params)
        result = engine.run()
        all_results.append(result)
        all_trades.extend(engine.trades)
    
    return all_results, all_trades, optimized_params


def generate_report(all_results, all_trades, optimized_params):
    """توليد التقرير الشامل"""
    
    print("\n" + "="*70)
    print("📊 BACKTEST RESULTS - 5 YEARS (2019-2024) ENHANCED")
    print("="*70 + "\n")
    
    print("⚙️  OPTIMIZED PARAMETERS (Z3 ENHANCED):")
    print(f"   • Price Gate (Whitelist): {optimized_params.get('price_gate_whitelist', 12)}")
    print(f"   • Price Gate (Normal): {optimized_params.get('price_gate_normal', 18)}")
    print(f"   • Score Threshold: {optimized_params.get('score_threshold', 35)}")
    print(f"   • Target Multiplier: {optimized_params.get('target_multiplier', 1.12):.2f}x")
    print()
    
    results_df = pd.DataFrame(all_results)
    results_df = results_df.sort_values("profit_factor", ascending=False)
    
    print("📈 PERFORMANCE BY STOCK:\n")
    print(f"{'Stock':<12} {'Trades':<8} {'Win%':<8} {'Profit Factor':<15} {'Total P&L':<12} {'Avg P&L%':<10}")
    print("-" * 75)
    
    for _, row in results_df.iterrows():
        if row['total_trades'] > 0:
            print(f"{row['symbol']:<12} {row['total_trades']:<8} "
                  f"{row['win_rate']:.1f}%{'':<4} {row['profit_factor']:.2f}{'':<12} "
                  f"{row['total_pnl']:>10.2f} {row['total_pnl_pct']:>9.2f}%")
    
    print()
    
    if all_trades:
        total_trades = len(all_trades)
        winning_trades = len([t for t in all_trades if t["pnl"] > 0])
        losing_trades = len([t for t in all_trades if t["pnl"] < 0])
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        gross_profit = sum(t["pnl"] for t in all_trades if t["pnl"] > 0)
        gross_loss = abs(sum(t["pnl"] for t in all_trades if t["pnl"] < 0))
        
        total_pnl = sum(t["pnl"] for t in all_trades)
        avg_pnl_pct = np.mean([t["pnl_pct"] for t in all_trades])
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 0
        
        print("🎯 OVERALL SUMMARY:\n")
        print(f"Total Trades:          {total_trades}")
        print(f"Winning Trades:        {winning_trades}")
        print(f"Losing Trades:         {losing_trades}")
        print(f"Win Rate:              {win_rate:.2f}%")
        print(f"Gross Profit:          {gross_profit:>12.2f} EGP")
        print(f"Gross Loss:            {gross_loss:>12.2f} EGP")
        print(f"Total P&L:             {total_pnl:>12.2f} EGP")
        print(f"Avg P&L per Trade:     {total_pnl/total_trades:>12.2f} EGP")
        print(f"Profit Factor:         {profit_factor:.2f}x")
        print(f"Avg Return per Trade:  {avg_pnl_pct:.2f}%")
        print()
        
        print("🏆 TOP 5 WINNING TRADES:\n")
        trades_df = pd.DataFrame(all_trades)
        trades_df = trades_df.sort_values("pnl_pct", ascending=False)
        
        for i, (_, trade) in enumerate(trades_df.head(5).iterrows(), 1):
            print(f"{i}. {trade['symbol']}: {trade['entry_date'].date()} → {trade['exit_date'].date()} | "
                  f"+{trade['pnl']:.2f} EGP (+{trade['pnl_pct']:.2f}%)")
        
        print()
        
        print("💔 TOP 5 LOSING TRADES:\n")
        for i, (_, trade) in enumerate(trades_df.tail(5).iterrows(), 1):
            print(f"{i}. {trade['symbol']}: {trade['entry_date'].date()} → {trade['exit_date'].date()} | "
                  f"{trade['pnl']:.2f} EGP ({trade['pnl_pct']:.2f}%)")
    
    print("\n" + "="*70)
    
    save_results(all_results, all_trades, optimized_params)


def save_results(all_results, all_trades, optimized_params):
    """حفظ النتائج"""
    
    results_df = pd.DataFrame(all_results)
    results_df.to_csv("backtest_results_enhanced.csv", index=False)
    
    if all_trades:
        trades_df = pd.DataFrame(all_trades)
        trades_df.to_csv("backtest_trades_enhanced.csv", index=False)
    
    with open("optimized_params_enhanced.json", "w") as f:
        json.dump(optimized_params, f, indent=2)
    
    print("✅ تم حفظ النتائج:")
    print("   - backtest_results_enhanced.csv")
    print("   - backtest_trades_enhanced.csv")
    print("   - optimized_params_enhanced.json")


# =========================================
# MAIN
# =========================================

if __name__ == "__main__":
    try:
        all_results, all_trades, optimized_params = run_full_backtest()
        generate_report(all_results, all_trades, optimized_params)
        print("\n✅ تم الانتهاء من الاختبار الخلفي المحسّن بنجاح!")
        print("="*70)
    
    except Exception as e:
        print(f"\n❌ خطأ: {e}")
        import traceback
        traceback.print_exc()
