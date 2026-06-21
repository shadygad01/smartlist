"""
Constitutional Portfolio Allocator Research — read-only research harness.
Does NOT modify the frozen engine. Imports engine functions directly.
"""
import os, warnings
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
warnings.filterwarnings("ignore")

from config.scanner_config import get_constitutional_universe
from signal_engine import swings
import discount_reversal_engine as E

DATA_DIR = "historical_data/historical_data"
START = pd.Timestamp("2021-01-01")
END   = pd.Timestamp("2026-06-21")
LB_SWINGS = 80
HIST_BARS = 80

UNIVERSE = get_constitutional_universe()
SECTORS = {
    'TMGH.CA':'Real Estate','EMFD.CA':'Real Estate','PHDC.CA':'Real Estate',
    'ORHD.CA':'Real Estate','HELI.CA':'Real Estate',
    'EAST.CA':'Industrial','ABUK.CA':'Industrial','ORAS.CA':'Industrial',
    'EFID.CA':'Industrial','HRHO.CA':'Industrial','JUFO.CA':'Industrial',
    'ARCC.CA':'Industrial','ORWE.CA':'Industrial','CCAP.CA':'Industrial',
    'MCQE.CA':'Healthcare','ISPH.CA':'Healthcare','RMDA.CA':'Healthcare',
    'FWRY.CA':'FinTech','EFIH.CA':'FinTech','RAYA.CA':'FinTech','BTFH.CA':'FinTech',
    'COMI.CA':'Banking','EGAL.CA':'Banking','ADIB.CA':'Banking',
    'ETEL.CA':'Telecom','GBCO.CA':'Telecom','OIH.CA':'Telecom',
}

data = {}
for sym in UNIVERSE:
    p = os.path.join(DATA_DIR, f"{sym}.csv")
    if not os.path.exists(p):
        continue
    df = pd.read_csv(p, parse_dates=["Date"]).sort_values("Date").reset_index(drop=True)
    df = df.dropna(subset=["Open","High","Low","Close","Volume"])
    data[sym] = df
print(f"Loaded {len(data)}/{len(UNIVERSE)} symbols")

ENGINE = E.DiscountReversalEngine(db_path=":memory:")

# ── MISSION 1: full historical replay ────────────────────────────────────────
rows = []
for sym, df in data.items():
    n = len(df)
    H = df["High"].values; L = df["Low"].values; C = df["Close"].values
    dates = df["Date"].values
    for i in range(HIST_BARS, n):
        d = pd.Timestamp(dates[i])
        if d < START or d > END:
            continue
        win = df.iloc[i-HIST_BARS+1:i+1]
        hi, lo, eq, buy_hi, sell_lo = swings(win, lb=LB_SWINGS)
        close = float(C[i])
        if not (close < eq):   # R1 buy-zone gate
            continue
        pdata = pd.DataFrame({
            "date": win["Date"].values, "open": win["Open"].values,
            "high": win["High"].values, "low": win["Low"].values,
            "close": win["Close"].values, "volume": win["Volume"].values,
        })
        res = ENGINE.scan_symbol(sym, pdata, eq=eq, discount_bottom=lo, premium_top=hi)
        if res is None:
            continue
        entry = close
        def fslice(k): return slice(i+1, min(i+1+k, n))
        out = {}
        for k in (20,40,60):
            sl = fslice(k); fl=L[sl]; fh=H[sl]
            out[f"mae_{k}"] = (fl.min()-entry)/entry if len(fl) else np.nan
            out[f"mfe_{k}"] = (fh.max()-entry)/entry if len(fh) else np.nan
        fc60=C[fslice(60)]; fc120=C[fslice(120)]; fc40=C[fslice(40)]
        peak60 = (fc60.max()-entry)/entry if len(fc60) else np.nan
        peak120 = (fc120.max()-entry)/entry if len(fc120) else np.nan
        low_break_40 = int(np.any(fc40 < entry)) if len(fc40) else np.nan
        target=entry*1.20; h20=np.nan
        fcfull=C[i+1:min(i+1+120,n)]
        hit=np.where(fcfull>=target)[0]
        if len(hit): h20=int(hit[0]+1)
        def fret(k):
            j=i+k; return (C[j]-entry)/entry if j<n else np.nan
        rows.append(dict(
            symbol=sym, sector=SECTORS.get(sym,"Other"), date=d,
            month=d.to_period("M").strftime("%Y-%m"), entry=entry,
            R2=res["r2_discount_quality"], R3=res["r3_discount_residency_score"],
            R4=res["r4_base_score"], R5=res["r5_protection_score"],
            R6=res["r6_recovery_score"], R7=res["r7_macd_score"],
            R8=res["r8_volume_score"], final_score=res["final_score"],
            ret_20=fret(20), ret_40=fret(40), ret_60=fret(60),
            peak_return_60=peak60, peak_return_120=peak120,
            low_break_40=low_break_40, holding_to_20pct=h20, bar_idx=i, **out))

df_candidates = pd.DataFrame(rows)
print(f"Candidate signals: {len(df_candidates)}")

# primary outcome metric = ret_40 (forward 40-bar close return)
OUT = "ret_40"
dfc = df_candidates.dropna(subset=[OUT]).copy()
print(f"Candidates with {OUT} outcome: {len(dfc)}")

# ── correlation matrix helper (last 60d returns at signal date) ──────────────
ret_idx = {s: data[s].set_index("Date")["Close"].pct_change() for s in data}
def corr_at(symbols, date):
    cols={}
    for s in symbols:
        sr=ret_idx[s]
        sr=sr[sr.index<=date].tail(60)
        cols[s]=sr.reset_index(drop=True)
    if len(cols)<2: return pd.DataFrame()
    M=pd.DataFrame(cols).corr()
    return M
def vol20(sym,date):
    sr=ret_idx[sym]; sr=sr[sr.index<=date].tail(20)
    v=sr.std(); return v if v and v>0 else np.nan

# ── Portfolio outcome evaluator ──────────────────────────────────────────────
def eval_portfolio(sel, weights=None):
    """sel: DataFrame of selected positions. weights: array or None(equal)."""
    if len(sel)==0: return None
    r=sel[OUT].values
    if weights is None:
        w=np.ones(len(sel))
    else:
        w=np.array(weights,dtype=float)
    w=w/w.sum()
    port_ret=float(np.sum(w*r))
    return dict(
        port_ret=port_ret, median_ret=float(np.median(r)),
        worst_mae=float(sel["mae_40"].min()),
        mfe=float(sel["mfe_40"].mean()),
        win_rate=float(np.mean(r>0)), npos=len(sel),
        sectors=sel["sector"].values, symbols=sel["symbol"].values,
        avg_score=float(sel["final_score"].mean()),
        avg_R2=float(sel["R2"].mean()), avg_R4=float(sel["R4"].mean()),
        avg_R6=float(sel["R6"].mean()),
    )

months = sorted(dfc["month"].unique())
print(f"Cohort months: {len(months)} ({months[0]}..{months[-1]})")

# ── MISSION 2: portfolio characteristics ─────────────────────────────────────
def topN(g,N): return g.sort_values("final_score",ascending=False).head(N)
def maxk_sector(g,k):
    g=g.sort_values("final_score",ascending=False); cnt={}; keep=[]
    for _,r in g.iterrows():
        s=r["sector"]
        if cnt.get(s,0)>=k: continue
        cnt[s]=cnt.get(s,0)+1; keep.append(r)
    return pd.DataFrame(keep)

def cohort_stat(selector):
    res=[]
    for m in months:
        g=dfc[dfc["month"]==m]
        sel=selector(g)
        e=eval_portfolio(sel)
        if e: res.append(e)
    return res
def agg(res,key):
    v=[r[key] for r in res]; return np.mean(v),np.median(v)

m2={}
for N in (10,15,20):
    r=cohort_stat(lambda g,N=N: topN(g,N))
    m2[f"top{N}"]=(agg(r,"port_ret"),agg(r,"median_ret"),len(r))
# sector diversification max2 vs concentration(top10 no limit)
r_div=cohort_stat(lambda g: maxk_sector(g,2).head(15))
r_con=cohort_stat(lambda g: topN(g,15))
# score top-N vs random
np.random.seed(7)
r_score=cohort_stat(lambda g: topN(g,12))
def rnd(g):
    g=g.copy()
    return g.sample(min(12,len(g)),random_state=np.random.randint(1e6))
r_rand=cohort_stat(rnd)
# equal vs score-weighted (median)
def ew(g):
    s=topN(g,12); return eval_portfolio(s)
def sw(g):
    s=topN(g,12); return eval_portfolio(s,weights=s["final_score"].values)
r_ew=[ew(dfc[dfc["month"]==m]) for m in months]; r_ew=[x for x in r_ew if x]
r_sw=[sw(dfc[dfc["month"]==m]) for m in months]; r_sw=[x for x in r_sw if x]

# ── MISSION 3 / 4: policies ──────────────────────────────────────────────────
def pol_A(g): return topN(g,15)
def pol_B(g):
    g=g.sort_values("final_score",ascending=False); cnt={}; keep=[]
    for _,r in g.iterrows():
        s=r["sector"]
        if cnt.get(s,0)>=2: continue
        cnt[s]=cnt.get(s,0)+1; keep.append(r)
    return pd.DataFrame(keep)
def pol_C(g):
    g=g.sort_values("final_score",ascending=False); keep=[]; sec={}
    for _,r in g.iterrows():
        tot=len(keep)+1
        s=r["sector"]
        newcnt=sec.get(s,0)+1
        if tot>0 and newcnt/tot>0.25 and tot>=4:
            continue
        sec[s]=sec.get(s,0)+1; keep.append(r)
    return pd.DataFrame(keep)
def pol_D(g):
    g=g.sort_values("final_score",ascending=False)
    keep=[]; ksyms=[]
    if len(g): d=g.iloc[0]["date"]
    M=corr_at(list(g["symbol"].unique()), d) if len(g) else pd.DataFrame()
    for _,r in g.iterrows():
        s=r["symbol"]; ok=True
        for ps in ksyms:
            if s in M.index and ps in M.index:
                c=M.loc[s,ps]
                if pd.notna(c) and c>0.80: ok=False; break
        if ok: keep.append(r); ksyms.append(s)
    return pd.DataFrame(keep)
def pol_E(g):
    g=g.sort_values("final_score",ascending=False); keep=[]; re=0
    for _,r in g.iterrows():
        if r["sector"]=="Real Estate":
            if re>=3: continue
            re+=1
        keep.append(r)
        if len(keep)>=15: break
    return pd.DataFrame(keep)
def pol_F(g): return g.sort_values("mae_40",ascending=False).head(15)  # lowest adverse = highest(closest to 0) mae
def pol_G(g): return g.sort_values("R2",ascending=False).head(15)
def pol_H(g): return topN(g,12)
def pol_I(g):
    s=topN(g,12); d=s.iloc[0]["date"] if len(s) else None
    w=[1.0/(vol20(sym,d) or 0.02) for sym in s["symbol"]]
    return s,np.array(w)
def pol_J(g):
    s=topN(g,12); return s,s["final_score"].values

POLICIES={
 "A":("Top15 by score",pol_A,None),
 "B":("Top2 per sector",pol_B,None),
 "C":("Max25% sector",pol_C,None),
 "D":("Max corr 0.80",pol_D,None),
 "E":("Max3 RealEstate",pol_E,None),
 "F":("Lowest MAE40",pol_F,None),
 "G":("Highest R2",pol_G,None),
 "H":("EW top12",pol_H,"ew"),
 "I":("Vol-adj top12",pol_I,"volw"),
 "J":("Score-weighted top12",pol_J,"scorew"),
}

def run_policy(code):
    name,fn,mode=POLICIES[code]
    coh=[]
    prev=set()
    turns=[]
    for m in months:
        g=dfc[dfc["month"]==m]
        if len(g)==0: continue
        if mode in ("volw","scorew"):
            sel,w=fn(g); e=eval_portfolio(sel,weights=w)
        else:
            sel=fn(g); e=eval_portfolio(sel)
        if e is None: continue
        cur=set(e["symbols"])
        if prev:
            turn=len(cur.symmetric_difference(prev))/max(len(cur|prev),1)
            turns.append(turn)
        prev=cur
        coh.append(e)
    rr=np.array([c["port_ret"] for c in coh])
    mae=np.array([c["worst_mae"] for c in coh])
    mfe=np.array([c["mfe"] for c in coh])
    wr=np.array([c["win_rate"] for c in coh])
    return dict(
        name=name, n=len(coh),
        avg_ret=rr.mean(), med_ret=np.median(rr),
        avg_mae=mae.mean(), avg_mfe=mfe.mean(),
        best=rr.max(), worst=rr.min(),
        win_rate=wr.mean(), max_dd=mae.min(),
        vol=rr.std(), turnover=(np.mean(turns) if turns else 0.0),
        consistency=np.mean(rr>0), coh=coh)

pol_results={c:run_policy(c) for c in POLICIES}

# ── MISSION 5: variable importance (portfolio-level) ─────────────────────────
# Build portfolio-level feature table using policy A cohorts (broadest)
feat=[]
for m in months:
    g=dfc[dfc["month"]==m]
    if len(g)==0: continue
    sel=topN(g,15)
    e=eval_portfolio(sel)
    if e is None: continue
    secs=pd.Series(e["sectors"]).value_counts(normalize=True)
    entropy=-np.sum(secs*np.log(secs))
    cnts=pd.Series(e["sectors"]).value_counts()
    d=sel.iloc[0]["date"]
    M=corr_at(list(sel["symbol"].unique()),d)
    maxc=np.nan
    if not M.empty:
        vals=M.where(~np.eye(len(M),dtype=bool)).stack()
        maxc=vals.max() if len(vals) else np.nan
    feat.append(dict(
        port_ret=e["port_ret"], sector_entropy=entropy,
        max_sector_w=secs.max(), max_corr=maxc,
        n_realestate=cnts.get("Real Estate",0),
        avg_score=e["avg_score"], npos=e["npos"],
        avg_R4=e["avg_R4"], avg_R2=e["avg_R2"], avg_R6=e["avg_R6"]))
fdf=pd.DataFrame(feat)
vi={}
for c in ["sector_entropy","max_sector_w","max_corr","n_realestate","avg_score","npos","avg_R4","avg_R2","avg_R6"]:
    sub=fdf.dropna(subset=[c,"port_ret"])
    if len(sub)>3 and sub[c].nunique()>1:
        rho,p=spearmanr(sub[c],sub["port_ret"])
    else:
        rho,p=np.nan,np.nan
    vi[c]=(rho,p,len(sub))

# signal-level R-score importance (for context)
sig_vi={}
for c in ["R2","R3","R4","R5","R6","R7","R8","final_score"]:
    rho,p=spearmanr(dfc[c],dfc[OUT])
    sig_vi[c]=(rho,p)

# ════════════════════════ OUTPUT ════════════════════════════════════════════
L=print
def line(): L("="*78)

L("\n"); line(); L("SECTION 1: CANDIDATE DATASET SUMMARY"); line()
L(f"Window               : {START.date()} .. {END.date()}")
L(f"Symbols with data    : {len(data)}/{len(UNIVERSE)}")
L(f"Total candidate signals (R1 buy-zone pass) : {len(df_candidates)}")
L(f"With ret_40 outcome (used for eval)        : {len(dfc)}")
L(f"Cohort months                              : {len(months)}")
L(f"Signals per symbol (mean)                  : {len(df_candidates)/max(len(data),1):.1f}")
L("")
L("Per-sector signal counts:")
for s,c in df_candidates["sector"].value_counts().items():
    L(f"  {s:<14} {c:>6}")
L("")
L(f"final_score  mean={df_candidates['final_score'].mean():.2f}  median={df_candidates['final_score'].median():.2f}  max={df_candidates['final_score'].max():.2f}")
L(f"ret_40       mean={dfc['ret_40'].mean()*100:.2f}%  median={dfc['ret_40'].median()*100:.2f}%  win={np.mean(dfc['ret_40']>0)*100:.1f}%")
L(f"ret_20       mean={dfc['ret_20'].mean()*100:.2f}%   ret_60 mean={dfc['ret_60'].dropna().mean()*100:.2f}%")
L(f"mae_40       mean={dfc['mae_40'].mean()*100:.2f}%   mfe_40 mean={dfc['mfe_40'].mean()*100:.2f}%")
L(f"peak_return_60 mean={dfc['peak_return_60'].dropna().mean()*100:.2f}%  peak_120 mean={dfc['peak_return_120'].dropna().mean()*100:.2f}%")
L(f"low_break_40 rate={dfc['low_break_40'].dropna().mean()*100:.1f}%   reached +20%: {dfc['holding_to_20pct'].notna().mean()*100:.1f}% (median days={dfc['holding_to_20pct'].dropna().median()})")

line(); L("SECTION 2: PORTFOLIO CHARACTERISTICS RESEARCH"); line()
L("Q1 Position count (Top-N by score) -> (avg_ret%, med_ret%) across cohorts")
for N in (10,15,20):
    (a,_),(mm,_),nn=m2[f"top{N}"]
    L(f"   Top{N:<3} n={nn:<3}  avg={a*100:6.2f}%  median={mm*100:6.2f}%")
L("")
L("Q2 Sector diversification (max2/sector,15) vs concentration (top15):")
L(f"   Diversified  avg={np.mean([r['port_ret'] for r in r_div])*100:6.2f}%  median={np.median([r['median_ret'] for r in r_div])*100:6.2f}%")
L(f"   Concentrated avg={np.mean([r['port_ret'] for r in r_con])*100:6.2f}%  median={np.median([r['median_ret'] for r in r_con])*100:6.2f}%")
L("")
L("Q3 Score top-12 vs random-12:")
L(f"   Score  avg={np.mean([r['port_ret'] for r in r_score])*100:6.2f}%  win={np.mean([r['win_rate'] for r in r_score])*100:.1f}%")
L(f"   Random avg={np.mean([r['port_ret'] for r in r_rand])*100:6.2f}%  win={np.mean([r['win_rate'] for r in r_rand])*100:.1f}%")
L("")
L("Q4 Equal-weight vs score-weighted (top12):")
L(f"   Equal  median_ret={np.median([r['median_ret'] for r in r_ew])*100:6.2f}%  avg_port={np.mean([r['port_ret'] for r in r_ew])*100:6.2f}%")
L(f"   ScoreW median_ret={np.median([r['median_ret'] for r in r_sw])*100:6.2f}%  avg_port={np.mean([r['port_ret'] for r in r_sw])*100:6.2f}%")

line(); L("SECTION 3: POLICY TEST RESULTS TABLE"); line()
hdr=f"{'P':<2} {'Policy':<22} {'N':>3} {'AvgRet':>8} {'MedRet':>8} {'AvgMAE':>8} {'AvgMFE':>8} {'Win%':>6} {'Vol':>6} {'Cons%':>6}"
L(hdr); L("-"*len(hdr))
for c in POLICIES:
    r=pol_results[c]
    L(f"{c:<2} {r['name']:<22} {r['n']:>3} {r['avg_ret']*100:>7.2f}% {r['med_ret']*100:>7.2f}% {r['avg_mae']*100:>7.2f}% {r['avg_mfe']*100:>7.2f}% {r['win_rate']*100:>5.1f}% {r['vol']*100:>5.2f} {r['consistency']*100:>5.1f}%")
L("")
L("Extended metrics (Best/Worst cohort, MaxDD, Turnover):")
hdr2=f"{'P':<2} {'Best':>8} {'Worst':>8} {'MaxDD':>8} {'Turn%':>7}"
L(hdr2); L("-"*len(hdr2))
for c in POLICIES:
    r=pol_results[c]
    L(f"{c:<2} {r['best']*100:>7.2f}% {r['worst']*100:>7.2f}% {r['max_dd']*100:>7.2f}% {r['turnover']*100:>6.1f}%")

line(); L("SECTION 4: VARIABLE IMPORTANCE TABLE"); line()
L("Portfolio-level Spearman rho vs port_ret (Policy-A cohorts, n="+str(len(fdf))+"):")
hdr3=f"{'Variable':<20} {'rho':>8} {'p':>8} {'n':>5}"
L(hdr3); L("-"*len(hdr3))
order=sorted(vi.items(), key=lambda kv:-(abs(kv[1][0]) if not np.isnan(kv[1][0]) else -1))
for k,(rho,p,nn) in order:
    rs=f"{rho:>8.3f}" if not np.isnan(rho) else "     nan"
    ps=f"{p:>8.3f}" if not np.isnan(p) else "     nan"
    L(f"{k:<20} {rs} {ps} {nn:>5}")
L("")
L("Signal-level Spearman rho vs ret_40 (context, n="+str(len(dfc))+"):")
for k,(rho,p) in sorted(sig_vi.items(), key=lambda kv:-abs(kv[1][0])):
    L(f"  {k:<12} rho={rho:>7.3f}  p={p:.4f}")

import pickle
with open("_research_out.pkl","wb") as f:
    pickle.dump(dict(pol_results={c:{k:v for k,v in pol_results[c].items() if k!='coh'} for c in POLICIES},
                     vi=vi, sig_vi=sig_vi, m2=m2), f)
L("\nDONE")
