"""
Backtest Comparison: Static 12% Target vs Dynamic Fibonacci Target
5-Year analysis on all EGX stocks — optimised (precomputed signals)
"""

import pandas as pd
import numpy as np
from datetime import datetime
from backtest import (BacktestEngine, generate_synthetic_egx_data,
                      STOCKS, NAMES, swings, calc_macd, calc_stopping_volume, WHITELIST)

BASE_PARAMS = {
    "price_gate_whitelist": 12,
    "price_gate_normal":    18,
    "score_threshold":      20,   # adjusted: stopping_volume excluded from bulk compute
    "target_multiplier":    1.12,
    "min_data_points":      80,
}

FIB_LEVELS = [0.236, 0.382, 0.50, 0.618, 1.0, 1.5, 2.0]


# ── fast vectorised signal pre-compute ──────────────────────────────────────

def precompute_signals(df, symbol, params):
    """Pre-compute score and price_ok for every bar in O(n) passes."""
    min_dp = params["min_data_points"]
    close  = df["Close"].values
    n      = len(close)

    price_gate = (params["price_gate_whitelist"]
                  if symbol in WHITELIST else params["price_gate_normal"])

    # Swing levels — rolling 80-bar window
    lb = 80
    hi_arr     = np.full(n, np.nan)
    lo_arr     = np.full(n, np.nan)
    eq_arr     = np.full(n, np.nan)
    buy_hi_arr = np.full(n, np.nan)

    for i in range(lb - 1, n):
        window = close[max(0, i-lb+1): i+1]
        hi = window.max(); lo = window.min()
        rng = hi - lo
        hi_arr[i]     = hi
        lo_arr[i]     = lo
        eq_arr[i]     = lo + rng * 0.50
        buy_hi_arr[i] = lo + rng * 0.15

    # Price score
    r1_arr = np.zeros(n)
    for i in range(lb - 1, n):
        cur    = close[i]
        lo     = lo_arr[i]; hi = hi_arr[i]
        eq     = eq_arr[i]; buy_hi = buy_hi_arr[i]
        rng    = hi - lo
        if rng <= 0:
            continue
        if cur <= buy_hi:
            ratio  = (cur - lo) / (buy_hi - lo) if (buy_hi - lo) > 0 else 0
            r1_arr[i] = max(round(30 * (1.0 - ratio * 0.40)), 0)
        elif cur < eq:
            ratio     = (cur - buy_hi) / (eq - buy_hi) if (eq - buy_hi) > 0 else 1
            r1_arr[i] = max(round(30 * 0.60 * (1.0 - ratio)), 0)

    # MACD (full series once)
    close_s = df["Close"]
    try:
        m, sg, h = calc_macd(close_s)
        macd_vals = m.values
        sig_vals  = sg.values
    except Exception:
        macd_vals = np.zeros(n)
        sig_vals  = np.zeros(n)

    r6_arr = np.zeros(n)
    for i in range(1, n):
        if macd_vals[i] >= 0:
            continue
        crossed_up = (macd_vals[i-1] <= sig_vals[i-1]) and (macd_vals[i] > sig_vals[i])
        r6_arr[i]  = 4 if crossed_up else 2

    # Total score (r1 + r6 only — stopping volume too slow for bulk backtest)
    scores   = np.minimum((r1_arr + r6_arr).astype(int), 100)
    price_ok = r1_arr >= price_gate

    return scores, price_ok, close, lo_arr


def run_engine_fast(symbol, df, params, dynamic):
    """Streamlined backtest loop using precomputed signals."""
    scores, price_ok_arr, close, lo_arr = precompute_signals(df, symbol, params)

    threshold   = params["score_threshold"]
    min_dp      = params["min_data_points"]
    fib_levels  = params.get("fib_levels", FIB_LEVELS)
    n           = len(df)
    dates       = df.index

    position  = None
    trades    = []

    def fib_targets(entry):
        tgts = [entry * 1.12]
        for lv in fib_levels:
            p = entry * (1 + lv)
            if p >= tgts[0]:
                tgts.append(p)
        return tgts

    def nearest_lower(entry, price, tgts):
        best = entry * 1.12
        for t in tgts:
            if t < price and t >= best:
                best = t
        return best

    def macd_crossdown(idx):
        if idx < 1:
            return False
        try:
            sl  = df["Close"].iloc[max(0, idx-30):idx+1]
            m, sg, _ = calc_macd(sl)
            return (m.iloc[-2] >= sg.iloc[-2]) and (m.iloc[-1] < sg.iloc[-1])
        except Exception:
            return False

    def make_position(entry_date, entry_price, score, is_reinforcement=False):
        tgts = fib_targets(entry_price) if dynamic else [entry_price * 1.12]
        return dict(entry_date=entry_date, entry_price=entry_price,
                    fib_targets=tgts, current_level=0, target=tgts[0],
                    score=score, is_reinforcement=is_reinforcement)

    def exit_position(pos, exit_p, reason, date):
        ep  = pos["entry_price"]
        pnl = exit_p - ep
        trades.append(dict(symbol=symbol,
                           entry_date=pos["entry_date"], entry_price=ep,
                           exit_date=date, exit_price=exit_p,
                           pnl=pnl, pnl_pct=pnl / ep * 100,
                           days_held=(date - pos["entry_date"]).days,
                           reason=reason, score=pos["score"],
                           reinforced=pos["is_reinforcement"]))

    def update_and_check_exit(pos, price, date, i):
        """Update ratchet and check exit conditions. Returns True if position closed."""
        tgts = pos["fib_targets"]
        for j, t in enumerate(tgts):
            if price >= t:
                pos["current_level"] = max(pos["current_level"], j)
        pos["target"] = tgts[pos["current_level"]]
        lvl = pos["current_level"]

        if price >= pos["target"]:
            if dynamic and macd_crossdown(i):
                exit_position(pos, tgts[lvl], "weakness_at_target", date)
                return True
            elif dynamic and lvl < len(tgts) - 1:
                pos["current_level"] = lvl + 1
                pos["target"] = tgts[pos["current_level"]]
            else:
                exit_position(pos, price, "target_hit", date)
                return True
        elif lvl > 0 and dynamic and macd_crossdown(i):
            exit_position(pos, tgts[lvl], "downtrend_protection", date)
            return True
        return False

    position    = None   # الصفقة الأولى
    reinforcement = None  # صفقة التعزيز Z3

    for i in range(min_dp, n):
        price = float(close[i])
        date  = dates[i]
        zone3 = float(lo_arr[i]) if not np.isnan(lo_arr[i]) else None

        # ── BUY: الدخول الأول ────────────────────────────────────────────────
        if position is None and reinforcement is None:
            if price_ok_arr[i] and scores[i] >= threshold:
                position = make_position(date, price, scores[i])

        if position is None and reinforcement is None:
            continue

        # ── Zone 3 Reinforcement (مرة واحدة، مستقلة) ────────────────────────
        if dynamic and position is not None and reinforcement is None and zone3 is not None:
            if price <= zone3 * 1.015:
                reinforcement = make_position(date, price, scores[i], is_reinforcement=True)

        # ── Update & Exit: الصفقة الأولى ─────────────────────────────────────
        if position is not None:
            if update_and_check_exit(position, price, date, i):
                position = None

        # ── Update & Exit: صفقة التعزيز ──────────────────────────────────────
        if reinforcement is not None:
            if update_and_check_exit(reinforcement, price, date, i):
                reinforcement = None

    # ── إغلاق أي صفقة مفتوحة في نهاية الفترة ────────────────────────────────
    for pos in [position, reinforcement]:
        if pos is not None:
            exit_p = float(close[-1])
            exit_position(pos, exit_p, "end_of_period", dates[-1])

    return trades


def run_comparison(years=5):
    print("\n" + "=" * 110)
    print("  SMARTLIST EGX — BACKTEST COMPARISON REPORT")
    print(f"  Static 12% Target  vs  Dynamic Fibonacci Target  |  {years} سنوات  |  {len(STOCKS)} سهم")
    print("=" * 110)
    print(f"\n  Loading {len(STOCKS)} stocks × {years} years ...\n")

    s_trades, d_trades = [], []
    s_results, d_results = [], []

    for symbol in STOCKS:
        df = generate_synthetic_egx_data(symbol, years=years, seed=hash(symbol) % (2**32))
        if df.empty:
            continue

        st = run_engine_fast(symbol, df, BASE_PARAMS, dynamic=False)
        dt = run_engine_fast(symbol, df, BASE_PARAMS, dynamic=True)
        s_trades.extend(st); d_trades.extend(dt)

        def sym_metrics(tlist):
            if not tlist:
                return dict(symbol=symbol, total_trades=0, winning_trades=0,
                            losing_trades=0, win_rate=0, avg_win=0, avg_loss=0,
                            total_pnl=0, total_pnl_pct=0, profit_factor=0)
            tdf = pd.DataFrame(tlist)
            wins  = tdf[tdf["pnl"] > 0]
            loss  = tdf[tdf["pnl"] <= 0]
            gp    = wins["pnl"].sum()
            gl    = abs(loss["pnl"].sum())
            return dict(symbol=symbol,
                        total_trades=len(tdf),
                        winning_trades=len(wins), losing_trades=len(loss),
                        win_rate=len(wins)/len(tdf)*100,
                        avg_win=wins["pnl_pct"].mean() if len(wins) else 0,
                        avg_loss=loss["pnl_pct"].mean() if len(loss) else 0,
                        total_pnl=tdf["pnl"].sum(),
                        total_pnl_pct=tdf["pnl_pct"].mean(),
                        profit_factor=gp/gl if gl else 0)

        s_results.append(sym_metrics(st))
        d_results.append(sym_metrics(dt))
        print(f"  ✓ {symbol:12}  static={len(st):3} trades   dynamic={len(dt):3} trades")

    return s_results, s_trades, d_results, d_trades


def aggregate(results, trades):
    if not trades:
        return {}
    df_t = pd.DataFrame(trades)
    df_r = pd.DataFrame(results)
    winners = df_t[df_t["pnl"] > 0]
    losers  = df_t[df_t["pnl"] <= 0]
    gp = winners["pnl"].sum()
    gl = abs(losers["pnl"].sum())
    reasons = df_t["reason"].value_counts().to_dict()
    return dict(
        total_trades   = len(df_t),
        winners        = len(winners),
        losers         = len(losers),
        win_rate       = len(winners) / len(df_t) * 100,
        gross_profit   = gp,
        gross_loss     = gl,
        profit_factor  = gp / gl if gl else 0,
        avg_win_pct    = winners["pnl_pct"].mean() if len(winners) else 0,
        avg_loss_pct   = losers["pnl_pct"].mean()  if len(losers)  else 0,
        avg_pnl_pct    = df_t["pnl_pct"].mean(),
        median_pnl_pct = df_t["pnl_pct"].median(),
        best_trade     = df_t["pnl_pct"].max(),
        worst_trade    = df_t["pnl_pct"].min(),
        avg_days       = df_t["days_held"].mean(),
        total_pnl_sum  = df_t["pnl_pct"].sum(),
        reasons        = reasons,
        trades_df      = df_t,
        results_df     = df_r,
    )


def print_report(s, d, sr, dr):
    L = "─" * 110
    D = "═" * 110

    def sec(title):
        print(f"\n{D}")
        print(f"  {title}")
        print(D)

    # ── 1. HEADLINE ─────────────────────────────────────────────────────────
    sec("SECTION 1 — إجمالي النتائج عبر كامل 5 سنوات")

    rows = [
        ("إجمالي الصفقات",           "total_trades",   "",  ""),
        ("الصفقات الرابحة",           "winners",        "",  ""),
        ("الصفقات الخاسرة",           "losers",         "",  ""),
        ("نسبة الفوز %",              "win_rate",       "%", "+"),
        ("Profit Factor",             "profit_factor",  "x", "+"),
        ("إجمالي الأرباح (Σ PnL %)",  "total_pnl_sum",  "%", "+"),
        ("متوسط ربح الصفقة %",        "avg_pnl_pct",    "%", "+"),
        ("Median الصفقة %",           "median_pnl_pct", "%", "+"),
        ("متوسط الصفقة الرابحة %",    "avg_win_pct",    "%", "+"),
        ("متوسط الصفقة الخاسرة %",    "avg_loss_pct",   "%", "-"),
        ("أفضل صفقة %",               "best_trade",     "%", "+"),
        ("أسوأ صفقة %",               "worst_trade",    "%", "-"),
        ("متوسط مدة الصفقة (أيام)",   "avg_days",       "d", ""),
    ]

    print(f"\n  {'المقياس':35} {'ثابت 12%':>16} {'ديناميكي':>16} {'الفرق':>14}  الجدوى")
    print(f"  {L}")
    for lbl, key, unit, sign in rows:
        sv = s.get(key, 0) or 0
        dv = d.get(key, 0) or 0
        diff = dv - sv
        fs = f"{sv:.2f}{unit}" if isinstance(sv, float) else f"{sv}{unit}"
        fd = f"{dv:.2f}{unit}" if isinstance(dv, float) else f"{dv}{unit}"
        fd2 = f"{diff:+.2f}{unit}" if isinstance(diff, float) else f"{diff:+}{unit}"
        verdict = ("✅ أفضل"  if ((diff > 0 and sign=="+") or (diff < 0 and sign=="-")) else
                   "⚠  أسوأ" if diff != 0 and sign else "➡")
        print(f"  {lbl:35} {fs:>16} {fd:>16} {fd2:>14}  {verdict}")

    # ── 2. EXIT REASONS ──────────────────────────────────────────────────────
    sec("SECTION 2 — أسباب الخروج")
    labels = {
        "target_hit":             "✅ وصل للتارجت",
        "downtrend_exit":         "📉 هبوط (أقرب Fibonacci)",
        "weakness_at_min_target": "⚠  ضعف عند 12%",
        "end_of_period":          "⏱  نهاية الفترة",
    }
    print(f"\n  {'سبب الخروج':32} {'ثابت 12%':>22} {'ديناميكي':>22}")
    print(f"  {L}")
    for r, lbl in labels.items():
        sv = s["reasons"].get(r, 0)
        dv = d["reasons"].get(r, 0)
        ps = sv / s["total_trades"] * 100 if s["total_trades"] else 0
        pd_ = dv / d["total_trades"] * 100 if d["total_trades"] else 0
        print(f"  {lbl:32} {sv:>8} ({ps:5.1f}%)       {dv:>8} ({pd_:5.1f}%)")

    # ── 2b. REINFORCEMENT STATS ──────────────────────────────────────────────
    if "reinforced" in d["trades_df"].columns:
        dr_df_all = d["trades_df"]
        reinforced   = dr_df_all[dr_df_all["reinforced"] == True]
        unreinforced = dr_df_all[dr_df_all["reinforced"] == False]
        sec("SECTION 2b — إحصائيات التعزيز (Zone 3)")
        print(f"\n  إجمالي الصفقات الديناميكية : {len(dr_df_all)}")
        print(f"  صفقات بتعزيز (Zone 3)       : {len(reinforced)} ({len(reinforced)/len(dr_df_all)*100:.1f}%)")
        print(f"  صفقات بدون تعزيز            : {len(unreinforced)} ({len(unreinforced)/len(dr_df_all)*100:.1f}%)")
        if len(reinforced):
            rw = reinforced[reinforced["pnl"] > 0]
            rl = reinforced[reinforced["pnl"] <= 0]
            print(f"\n  أداء الصفقات المعززة:")
            print(f"    نسبة الفوز   : {len(rw)/len(reinforced)*100:.1f}%")
            print(f"    متوسط الربح  : {reinforced['pnl_pct'].mean():.2f}%")
            print(f"    أفضل صفقة    : {reinforced['pnl_pct'].max():.2f}%")
            print(f"    أسوأ صفقة    : {reinforced['pnl_pct'].min():.2f}%")
        if len(unreinforced):
            print(f"\n  أداء الصفقات غير المعززة:")
            print(f"    نسبة الفوز   : {len(unreinforced[unreinforced['pnl']>0])/len(unreinforced)*100:.1f}%")
            print(f"    متوسط الربح  : {unreinforced['pnl_pct'].mean():.2f}%")

    # ── 3. PER-STOCK ─────────────────────────────────────────────────────────
    sec("SECTION 3 — مقارنة الأسهم سهم × سهم")
    sr_df = pd.DataFrame(sr).set_index("symbol")
    dr_df = pd.DataFrame(dr).set_index("symbol")

    print(f"\n  {'السهم':14} {'اسم السهم':30} {'صفقات(ث)':>9} {'صفقات(د)':>9} {'Avg%(ث)':>9} {'Avg%(د)':>9} {'الفرق':>9}  الجدوى")
    print(f"  {L}")
    imp = reg = unch = 0
    for sym in STOCKS:
        if sym not in sr_df.index or sym not in dr_df.index:
            continue
        rs = sr_df.loc[sym]; rd = dr_df.loc[sym]
        if rs["total_trades"] == 0 and rd["total_trades"] == 0:
            continue
        ts = int(rs["total_trades"]); td = int(rd["total_trades"])
        avgs = rs["total_pnl_pct"] if ts else 0
        avgd = rd["total_pnl_pct"] if td else 0
        diff = avgd - avgs
        flag = "✅" if diff > 0.5 else ("⚠" if diff < -0.5 else "➡")
        if diff > 0.5: imp += 1
        elif diff < -0.5: reg += 1
        else: unch += 1
        nm = NAMES.get(sym, sym)[:28]
        print(f"  {sym:14} {nm:30} {ts:>9} {td:>9} {avgs:>8.2f}% {avgd:>8.2f}% {diff:>+8.2f}%  {flag}")

    print(f"\n  تحسّن: {imp} أسهم   تراجع: {reg} أسهم   بدون تغيير: {unch} أسهم")

    # ── 4. PROFIT BUCKETS ────────────────────────────────────────────────────
    sec("SECTION 4 — توزيع الصفقات بالفئات")
    def bkt(df):
        return {
            "خسارة < 0%":        len(df[df["pnl_pct"] < 0]),
            "0% – 12%":          len(df[(df["pnl_pct"] >= 0)   & (df["pnl_pct"] < 12)]),
            "12% – 23.6%":       len(df[(df["pnl_pct"] >= 12)  & (df["pnl_pct"] < 23.6)]),
            "23.6% – 38.2%":     len(df[(df["pnl_pct"] >= 23.6)& (df["pnl_pct"] < 38.2)]),
            "38.2% – 61.8%":     len(df[(df["pnl_pct"] >= 38.2)& (df["pnl_pct"] < 61.8)]),
            "61.8% – 100%":      len(df[(df["pnl_pct"] >= 61.8)& (df["pnl_pct"] < 100)]),
            "أعلى من 100%":      len(df[df["pnl_pct"] >= 100]),
        }
    sb = bkt(s["trades_df"]); db = bkt(d["trades_df"])
    print(f"\n  {'الفئة':22} {'ثابت 12%':>18} {'ديناميكي':>18} {'الفرق':>10}  الجدوى")
    print(f"  {L}")
    for k in sb:
        sv = sb[k]; dv = db[k]; diff = dv - sv
        ps = sv/s["total_trades"]*100; pd_ = dv/d["total_trades"]*100
        is_bad = "خسارة" in k or "0%" in k
        flag = ("⚠" if (diff > 0 and is_bad) else
                "✅" if (diff > 0 and not is_bad) else
                "⬇" if (diff < 0 and not is_bad) else "")
        print(f"  {k:22} {sv:>7} ({ps:4.1f}%)    {dv:>7} ({pd_:4.1f}%)  {diff:>+7}  {flag}")

    # ── 5. RISK METRICS ──────────────────────────────────────────────────────
    sec("SECTION 5 — مقاييس معدّلة بالمخاطر")
    std_s = s["trades_df"]["pnl_pct"].std()
    std_d = d["trades_df"]["pnl_pct"].std()
    exp_s = (s["win_rate"]/100*s["avg_win_pct"]) - ((1-s["win_rate"]/100)*abs(s["avg_loss_pct"]))
    exp_d = (d["win_rate"]/100*d["avg_win_pct"]) - ((1-d["win_rate"]/100)*abs(d["avg_loss_pct"]))
    sharpe_s = s["avg_pnl_pct"] / std_s if std_s else 0
    sharpe_d = d["avg_pnl_pct"] / std_d if std_d else 0
    wl_s = abs(s["avg_win_pct"]/s["avg_loss_pct"]) if s["avg_loss_pct"] else 0
    wl_d = abs(d["avg_win_pct"]/d["avg_loss_pct"]) if d["avg_loss_pct"] else 0

    risk = [
        ("Expectancy / Trade %",   exp_s,    exp_d,    "+"),
        ("Std Dev of Returns %",   std_s,    std_d,    "-"),
        ("Sharpe-like Ratio",      sharpe_s, sharpe_d, "+"),
        ("Win / Loss Ratio",       wl_s,     wl_d,     "+"),
        ("Max Drawdown (Worst %)", s["worst_trade"], d["worst_trade"], "+"),
    ]
    print(f"\n  {'المقياس':30} {'ثابت 12%':>16} {'ديناميكي':>16} {'الفرق':>14}  الجدوى")
    print(f"  {L}")
    better = 0
    for lbl, sv, dv, sign in risk:
        diff = dv - sv
        v = ("✅ أفضل" if ((diff > 0 and sign=="+") or (diff < 0 and sign=="-")) else
             "⚠  أسوأ" if diff != 0 else "➡")
        if "أفضل" in v: better += 1
        print(f"  {lbl:30} {sv:>16.4f} {dv:>16.4f} {diff:>+14.4f}  {v}")

    # ── 6. VERDICT ───────────────────────────────────────────────────────────
    sec("SECTION 6 — الحكم النهائي والتوصية")
    pnl_diff = d["total_pnl_sum"] - s["total_pnl_sum"]
    pf_diff  = d["profit_factor"]  - s["profit_factor"]
    wr_diff  = d["win_rate"]       - s["win_rate"]
    bt_diff  = d["best_trade"]     - s["best_trade"]

    print(f"""
  ┌──────────────────────────────────────────────────────────────────────────────────────┐
  │  الملخص التنفيذي                                                                     │
  │  ──────────────────────────────────────────────────────────────────────────────────  │
  │                                                                                       │
  │  إجمالي الأرباح (Σ PnL %)                                                           │
  │    ثابت     {s["total_pnl_sum"]:>9.2f}%     ديناميكي {d["total_pnl_sum"]:>9.2f}%     الفرق {pnl_diff:>+9.2f}%      │
  │                                                                                       │
  │  Profit Factor                                                                        │
  │    ثابت     {s["profit_factor"]:>9.4f}x     ديناميكي {d["profit_factor"]:>9.4f}x     الفرق {pf_diff:>+9.4f}x      │
  │                                                                                       │
  │  نسبة الفوز                                                                          │
  │    ثابت     {s["win_rate"]:>9.2f}%     ديناميكي {d["win_rate"]:>9.2f}%     الفرق {wr_diff:>+9.2f}%      │
  │                                                                                       │
  │  أفضل صفقة                                                                           │
  │    ثابت     {s["best_trade"]:>9.2f}%     ديناميكي {d["best_trade"]:>9.2f}%     الفرق {bt_diff:>+9.2f}%      │
  │                                                                                       │
  │  أسهم تحسّنت: {imp:>3}   تراجعت: {reg:>3}   بدون تغيير: {unch:>3}                          │
  │  مقاييس مخاطر محسّنة: {better}/5                                                      │
  │                                                                                       │
  └──────────────────────────────────────────────────────────────────────────────────────┘
""")

    if pnl_diff > 0 and pf_diff >= 0:
        print("  الحكم النهائي: ✅ النظام الديناميكي أفضل — يُنصح بالتبني الكامل")
    elif pnl_diff > 0 and pf_diff < 0:
        print("  الحكم النهائي: ✅ الديناميكي أرباح أعلى مع تقلب أكبر قليلاً — يُنصح مع مراقبة")
    elif pnl_diff < 0:
        print("  الحكم النهائي: ⚠  الثابت أداء أفضل — مراجعة مستويات Fibonacci مطلوبة")
    else:
        print("  الحكم النهائي: ➡  أداء متقارب")

    print(f"\n{'='*110}\n")


if __name__ == "__main__":
    import time
    t0 = time.time()
    sr, st, dr, dt = run_comparison(years=5)
    s_agg = aggregate(sr, st)
    d_agg = aggregate(dr, dt)
    print_report(s_agg, d_agg, sr, dr)
    print(f"  Completed in {time.time()-t0:.1f}s")
