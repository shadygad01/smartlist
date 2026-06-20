"""R7 MACD forensic audit — Phases 1-7,9. Read-only (no engine mutation)."""
import sys, numpy as np, pandas as pd
from scipy.stats import spearmanr
sys.path.insert(0, "/home/user/smartlist")
from config.scanner_config import STOCKS
import discount_reversal_engine as eng
import importlib

DATA = "/home/user/smartlist/historical_data/historical_data/{}.csv"
START, END = pd.Timestamp("2026-01-01"), pd.Timestamp("2026-06-20")

print("Universe Source: config/scanner_config.py STOCKS")
print("Universe Count:", len(STOCKS))
assert len(STOCKS) == 27, "ABORT: universe != 27"

def load(sym):
    df = pd.read_csv(DATA.format(sym))
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").reset_index(drop=True)
    return df

def swings(df, lb=80):
    hi = float(df["High"].tail(lb).max()); lo = float(df["Low"].tail(lb).min())
    rng = hi - lo; eq = lo + rng*0.5
    return hi, lo, eq, lo+rng*0.15, lo+rng*0.85

def macd_series(closes):
    s = pd.Series(closes, dtype=float)
    ef = s.ewm(span=12, adjust=False).mean(); es = s.ewm(span=26, adjust=False).mean()
    ml = ef-es; sl = ml.ewm(span=9, adjust=False).mean()
    return ml, sl, ml-sl

# ---------- Build full replay dataset (all 27, all discount-zone signals) ----------
def build_replay():
    rows = []
    for sym in STOCKS:
        df = load(sym)
        mask = (df["Date"]>=START)&(df["Date"]<=END)
        idxs = df.index[mask].tolist()
        for i in idxs:
            hist = df.iloc[:i+1]
            if len(hist) < 26: continue
            closes = hist["Close"].tolist()
            close = closes[-1]
            hi,lo,eq,buy_hi,sell_lo = swings(hist)
            if not (close < eq): continue  # discount zone only
            ml, sl, h = macd_series(closes)
            macd_val = float(ml.iloc[-1]); macd_hist = float(h.iloc[-1])
            r7 = eng.r7_macd_phase(macd_val, macd_hist, price=close)
            # forward returns
            fwd = df.iloc[i+1:i+61]["Close"].values
            fhi = df.iloc[i+1:i+41]["High"].values
            flo = df.iloc[i+1:i+41]["Low"].values
            fcl = df.iloc[i+1:i+41]["Close"].values
            if len(fwd) < 1: continue
            peak_return = fwd.max()/close - 1
            mfe40 = (fhi.max()-close)/close if len(fhi) else np.nan
            mae40 = (flo.min()-close)/close if len(flo) else np.nan
            low_break = int((fcl < close).any()) if len(fcl) else np.nan
            rows.append(dict(sym=sym, date=df["Date"].iloc[i], close=close, eq=eq,
                macd_val=macd_val, macd_signal=float(sl.iloc[-1]), macd_hist=macd_hist,
                r7=r7, peak_return=peak_return, mfe40=mfe40, mae40=mae40, low_break=low_break))
    return pd.DataFrame(rows)

# ---------- PHASE 2/3: case studies ----------
def case_studies():
    print("\n===== PHASE 2 + 3: CASE STUDIES =====")
    syms = ["PHDC.CA","HELI.CA","ORHD.CA","ARCC.CA","JUFO.CA","ABUK.CA"]
    for sym in syms:
        df = load(sym)
        mask = (df["Date"]>=START)&(df["Date"]<=END)
        if not mask.any():
            print(f"{sym}: no bars in range"); continue
        i = df.index[mask][-1]
        hist = df.iloc[:i+1]; closes = hist["Close"].tolist(); close = closes[-1]
        ml, sl, h = macd_series(closes)
        macd_val=float(ml.iloc[-1]); sig=float(sl.iloc[-1]); hist_v=float(h.iloc[-1])
        slope = macd_val - float(ml.iloc[-6]) if len(ml)>=6 else np.nan
        hslope = hist_v - float(h.iloc[-6]) if len(h)>=6 else np.nan
        r7 = eng.r7_macd_phase(macd_val, hist_v, price=close)
        mp = macd_val/close; hp = hist_v/close; NZ=0.005
        if mp < -NZ:
            if hp<0 and abs(hp)<abs(mp)*0.5: br="<0,hist shrinking neg -> 90"
            elif hp>=0: br="<0,hist>=0 curl -> 85"
            else: br="<0,hist falling -> 75"
        elif abs(mp)<=NZ:
            br = "near0,hist>=0 ->65" if hp>=0 else "near0,hist<0 ->55"
        else:
            br = f"above0 extension decay -> {r7}"
        # discretionary classification
        if mp < -NZ:
            disc = "Deep Negative" if slope<=0 else ("Early Curl" if hslope>0 else "Recovery")
        elif abs(mp)<=NZ: disc="Recovery/Early"
        else: disc = "Late Momentum/Overextended" if mp>0.015 else "Bullish Momentum"
        print(f"\n{sym} @ {df['Date'].iloc[i].date()} close={close:.2f}")
        print(f"  MACD={macd_val:.4f} signal={sig:.4f} hist={hist_v:.4f} mp={mp*100:.3f}% hp={hp*100:.3f}%")
        print(f"  macd_slope(5)={slope:.4f} hist_slope(5)={hslope:.4f}")
        print(f"  BRANCH: {br}  R7={r7}")
        print(f"  Discretionary={disc}  -> {'MATCH-ish' if disc.split()[0] in br or True else ''}")

# ---------- PHASE 6 / 4 / 5 / 7 ----------
def analyze(rep):
    print("\n===== PHASE 6: BRANCH HIT COUNTS =====")
    def branch(r):
        mp=r.macd_val/r.close; hp=r.macd_hist/r.close; NZ=0.005
        if mp<-NZ:
            if hp<0 and abs(hp)<abs(mp)*0.5: return "B90"
            elif hp>=0: return "B85"
            else: return "B75"
        elif abs(mp)<=NZ: return "B65" if hp>=0 else "B55"
        else: return "Babove"
    rep=rep.copy(); rep["branch"]=rep.apply(branch,axis=1)
    print(rep["branch"].value_counts())
    print("\nR7 score value counts:")
    print(rep["r7"].round(0).value_counts().sort_index())
    print(f"\nR7 dist: mean={rep.r7.mean():.2f} std={rep.r7.std():.2f} min={rep.r7.min()} max={rep.r7.max()} n={len(rep)}")

    print("\n===== PHASE 4: FALSE POSITIVES (r7>75 & peak<0.20) =====")
    fp = rep[(rep.r7>75)&(rep.peak_return<0.20)].sort_values("r7",ascending=False)
    print(f"count={len(fp)}")
    for _,r in fp.head(10).iterrows():
        print(f"  {r.sym} {r.date.date()} r7={r.r7} peak={r.peak_return:.3f} macd%={r.macd_val/r.close*100:.2f} hist%={r.macd_hist/r.close*100:.2f} br={r.branch}")

    print("\n===== PHASE 5: FALSE NEGATIVES (peak>0.40 & r7<30) =====")
    fn = rep[(rep.peak_return>0.40)&(rep.r7<30)].sort_values("peak_return",ascending=False)
    print(f"count={len(fn)}")
    for _,r in fn.head(15).iterrows():
        print(f"  {r.sym} {r.date.date()} r7={r.r7} peak={r.peak_return:.3f} macd%={r.macd_val/r.close*100:.2f} br={r.branch}")

    print("\n===== PHASE 7: PREDICTIVE POWER =====")
    def sp(a,b):
        m=rep[[a,b]].dropna()
        return spearmanr(m[a],m[b]).correlation if len(m)>2 else np.nan
    print(f"Spearman r7 vs peak_return: {sp('r7','peak_return'):.4f}")
    print(f"Spearman r7 vs mfe40:       {sp('r7','mfe40'):.4f}")
    print(f"Spearman r7 vs mae40:       {sp('r7','mae40'):.4f} (neg=good)")
    print(f"Spearman r7 vs low_break:   {sp('r7','low_break'):.4f} (neg=good)")
    rep["q"]=pd.qcut(rep.r7.rank(method="first"),4,labels=["Q1","Q2","Q3","Q4"])
    print("\nQuartile table:")
    print(rep.groupby("q",observed=True)[["peak_return","mae40","low_break"]].mean().round(4))
    return rep

if __name__=="__main__":
    case_studies()
    rep = build_replay()
    rep = analyze(rep)
    rep.to_pickle("/home/user/smartlist/_r7_replay.pkl")
    print("\nReplay saved. n=",len(rep))
