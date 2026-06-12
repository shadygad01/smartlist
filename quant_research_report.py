"""
Quant Research Report
=====================
تقرير بحثي كمي شامل — 7 مراحل — يُولَّد تلقائياً يومياً.

لا يُعدّل أي منطق في النظام — بحث وإبلاغ فقط.

المراحل:
  1. Data Audit       — جودة البيانات، معدلات NULL، توزيع العوائد
  2. Feature Analysis — اتساق r1-r8: ارتباط، رتب، قيمة المعلومات
  3. Weight Validation— مقارنة الأوزان الحالية بأهمية ML
  4. Gate Analysis    — اختبار عتبات PRICE_GATE / LIQ / SCORE
  5. Edge Discovery   — مجموعات المكونات ذات الـ MFE الأعلى
  6. Cluster Profiles — تجميع الإشارات وتحديد ملامح الفائزين
  7. Final Summary    — الدرجات والتوصيات

التشغيل:
    python quant_research_report.py
"""

import os
import sys
import sqlite3
from datetime import date, datetime
from itertools import combinations

# ── اختياري: numpy / pandas / sklearn ─────────────────────────────────────────
import warnings
warnings.filterwarnings("ignore", category=RuntimeWarning)

try:
    import numpy as np
    import pandas as pd
    NUMPY_OK = True
except ImportError:
    NUMPY_OK = False
    sys.exit("Run: pip install numpy pandas")

try:
    from scipy import stats as sp_stats
    SCIPY_OK = True
except ImportError:
    SCIPY_OK = False

try:
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.metrics import r2_score
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler
    SKLEARN_OK = True
except ImportError:
    SKLEARN_OK = False

from signal_db import DB_PATH, get_conn, CURRENT_WEIGHTS, WEIGHT_LABELS

# ── Config ─────────────────────────────────────────────────────────────────────
R_COLS = ["r1_price", "r2_ob", "r3_liquidity", "r4_htf",
          "r5_avwap", "r6_macd", "r7_div", "r8_demand"]

R_LABELS = {
    "r1_price":    "r1 السعر",
    "r2_ob":       "r2 Order Block",
    "r3_liquidity":"r3 السيولة",
    "r4_htf":      "r4 HTF",
    "r5_avwap":    "r5 AVWAP",
    "r6_macd":     "r6 MACD",
    "r7_div":      "r7 Divergence",
    "r8_demand":   "r8 منطقة الطلب",
}

WIN_MFE_THRESH  = 0.08   # 8% MFE = فائز
MIN_N_EDGE      = 8      # حد أدنى للإشارات في Edge group
MIN_N_CLUSTER   = 5      # حد أدنى لـ cluster
TRAIN_SPLIT     = 0.70
TODAY           = date.today().isoformat()

PRICE_GATE_NORMAL    = 16
PRICE_GATE_WHITELIST = 15
ENTRY_SCORE_GATE     = 40

# ── CSS ────────────────────────────────────────────────────────────────────────
_CSS = """
<style>
  body{font-family:'Segoe UI',Arial,sans-serif;background:#f0f2f5;color:#222;direction:rtl;margin:0}
  .container{max-width:960px;margin:20px auto;background:#fff;border-radius:10px;
             box-shadow:0 2px 12px #0002;overflow:hidden}
  .header{background:linear-gradient(135deg,#1a3c5e,#2a6496);color:#fff;padding:28px 30px}
  .header h1{margin:0;font-size:1.6em}
  .header p{margin:6px 0 0;opacity:.8;font-size:.9em}
  .section{padding:20px 30px;border-bottom:1px solid #eee}
  .section h2{color:#1a3c5e;margin-top:0;font-size:1.15em;
              border-right:4px solid #2a6496;padding-right:10px}
  .kpi-row{display:flex;flex-wrap:wrap;gap:12px;margin:10px 0}
  .kpi{flex:1;min-width:120px;background:#f7f9fb;border-radius:8px;
       padding:14px 16px;text-align:center}
  .kpi .val{font-size:1.9em;font-weight:700;color:#1a3c5e}
  .kpi .lbl{font-size:.78em;color:#666;margin-top:4px}
  .tbl-wrap{overflow-x:auto;-webkit-overflow-scrolling:touch}
  table{width:100%;border-collapse:collapse;font-size:.87em}
  th{background:#1a3c5e;color:#fff;padding:8px 10px;text-align:right;white-space:nowrap}
  td{padding:7px 10px;border-bottom:1px solid #eee}
  tr:nth-child(even) td{background:#f9f9f9}
  .badge{display:inline-block;padding:2px 8px;border-radius:12px;font-size:.78em;font-weight:600}
  .b-high{background:#d4edda;color:#155724}
  .b-med{background:#fff3cd;color:#856404}
  .b-low{background:#f8d7da;color:#721c24}
  .warn{background:#fff3cd;border:1px solid #ffc107;border-radius:6px;
        padding:10px 14px;margin:8px 0;font-size:.88em;color:#856404}
  .rec-box{background:#e8f4f8;border:1px solid #bee5eb;border-radius:8px;
           padding:14px 18px;margin:10px 0}
  .rec-box h3{margin:0 0 8px;color:#1a3c5e;font-size:1em}
  .phase-badge{display:inline-block;background:#2a6496;color:#fff;border-radius:4px;
               padding:1px 8px;font-size:.75em;margin-left:8px;vertical-align:middle}
  .score-bar{display:inline-block;background:#e0e0e0;border-radius:4px;
             height:12px;vertical-align:middle;margin-right:6px}
  .score-fill{height:100%;border-radius:4px;background:#2a6496}
  .frozen-note{background:#e8f0fe;border:1px solid #c5cae9;border-radius:6px;
               padding:8px 14px;margin:8px 0;font-size:.82em;color:#3949ab}
</style>"""


# ── DB Query ───────────────────────────────────────────────────────────────────

def _load_data() -> pd.DataFrame:
    conn = get_conn()
    try:
        # all mature signals (with BQ computed)
        rows = conn.execute("""
            SELECT s.*, b.bq_score, b.mfe_20d, b.mfe_40d,
                   b.mae_20d, b.mae_40d, b.days_to_peak,
                   b.classification, b.r5d, b.r10d, b.r20d
            FROM signals s
            JOIN bottom_quality b ON b.signal_id = s.id
        """).fetchall()
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame([dict(r) for r in rows])
        df = df.sort_values("signal_date").reset_index(drop=True)
        # mae → absolute
        for c in ["mae_20d", "mae_40d"]:
            if c in df.columns:
                df[c] = df[c].abs()
        return df
    finally:
        conn.close()


def _load_all_signals() -> pd.DataFrame:
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM signals ORDER BY signal_date").fetchall()
        return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()
    finally:
        conn.close()


# ── HTML helpers ───────────────────────────────────────────────────────────────

def _badge(val: float, hi: float, lo: float, fmt: str = ".1%") -> str:
    cls = "b-high" if val >= hi else ("b-low" if val < lo else "b-med")
    return f'<span class="badge {cls}">{val:{fmt}}</span>'


def _pct(n: int, tot: int) -> str:
    return f"{n/tot:.1%}" if tot else "—"


def _kpi(val: str, lbl: str) -> str:
    return f'<div class="kpi"><div class="val">{val}</div><div class="lbl">{lbl}</div></div>'


def _bar(score: float, maxv: float = 100) -> str:
    pct = max(0, min(100, score / maxv * 100))
    return (f'<span class="score-bar" style="width:60px">'
            f'<span class="score-fill" style="width:{pct:.0f}%"></span></span>'
            f'{score:.0f}')


def _tbl(headers: list, rows: list) -> str:
    ths = "".join(f"<th>{h}</th>" for h in headers)
    trs = ""
    for row in rows:
        tds = "".join(f"<td>{c}</td>" for c in row)
        trs += f"<tr>{tds}</tr>"
    return f'<div class="tbl-wrap"><table><thead><tr>{ths}</tr></thead><tbody>{trs}</tbody></table></div>'


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 1 — Data Audit
# ══════════════════════════════════════════════════════════════════════════════

def phase1_data_audit(df: pd.DataFrame, df_all: pd.DataFrame) -> tuple:
    """Returns (html_section, dq_score)"""

    total_all  = len(df_all)
    total_mat  = len(df)
    n_symbols  = df_all["symbol"].nunique() if "symbol" in df_all.columns else 0

    # NULL rates for r1-r8
    null_rows = []
    dq_penalties = 0.0
    for col in R_COLS:
        n_null = df[col].isna().sum() if col in df.columns else total_mat
        pct_ok = (total_mat - n_null) / total_mat if total_mat else 0
        lbl    = R_LABELS.get(col, col)
        badge  = _badge(pct_ok, 0.90, 0.50, ".1%")
        null_rows.append([lbl, str(total_mat - n_null), str(n_null), badge])
        if pct_ok < 0.90:
            dq_penalties += (0.90 - pct_ok) * 20

    # Target columns
    tgt_null_rows = []
    for col in ["mfe_20d", "mfe_40d", "mae_20d", "bq_score"]:
        if col not in df.columns:
            continue
        n_null = df[col].isna().sum()
        pct_ok = (total_mat - n_null) / total_mat if total_mat else 0
        badge  = _badge(pct_ok, 0.90, 0.50, ".1%")
        tgt_null_rows.append([col, str(total_mat - n_null), str(n_null), badge])
        if pct_ok < 0.90:
            dq_penalties += (0.90 - pct_ok) * 10

    # Return distribution
    dist_html = ""
    if "mfe_20d" in df.columns:
        mfe = df["mfe_20d"].dropna()
        n_high = (mfe >= 0.15).sum()
        n_med  = ((mfe >= 0.05) & (mfe < 0.15)).sum()
        n_low  = (mfe < 0.05).sum()
        n_tot  = len(mfe)
        dist_html = f"""
<div class="kpi-row">
  {_kpi(f"{n_high/n_tot:.0%}" if n_tot else "—", "MFE ≥ 15%")}
  {_kpi(f"{n_med/n_tot:.0%}"  if n_tot else "—", "MFE 5–15%")}
  {_kpi(f"{n_low/n_tot:.0%}"  if n_tot else "—", "MFE < 5%")}
  {_kpi(f"{mfe.median():.1%}" if n_tot else "—", "Median MFE")}
  {_kpi(f"{mfe.mean():.1%}"   if n_tot else "—", "Mean MFE")}
</div>"""

    # DQ Score
    dq_score = max(0.0, 100.0 - dq_penalties)
    # Penalise small sample
    if total_mat < 30:
        dq_score = min(dq_score, 40.0)
    elif total_mat < 60:
        dq_score = min(dq_score, 70.0)

    dq_badge = ("b-high" if dq_score >= 70 else ("b-low" if dq_score < 40 else "b-med"))

    html = f"""
<div class="section">
  <h2>المرحلة 1: تدقيق البيانات <span class="phase-badge">Data Audit</span></h2>
  <div class="kpi-row">
    {_kpi(str(total_all),  "إجمالي الإشارات")}
    {_kpi(str(total_mat),  "إشارات ناضجة")}
    {_kpi(str(n_symbols),  "رمز سهم")}
    {_kpi(f'<span class="badge {dq_badge}">{dq_score:.0f}/100</span>', "درجة جودة البيانات")}
  </div>
  {dist_html}
  <h3 style="color:#1a3c5e;margin:14px 0 6px">معدلات البيانات — مكونات التسجيل (r1-r8)</h3>
  {_tbl(["المكوّن","متوفر","Null","اكتمال"],null_rows)}
  <h3 style="color:#1a3c5e;margin:14px 0 6px">معدلات البيانات — متغيرات الهدف</h3>
  {_tbl(["المتغير","متوفر","Null","اكتمال"],tgt_null_rows)}
  <div class="frozen-note">⚙ منطق الإدخال مجمّد — هذا التقرير للبحث والإبلاغ فقط</div>
</div>"""

    return html, dq_score


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 2 — Feature Consistency
# ══════════════════════════════════════════════════════════════════════════════

def phase2_feature_consistency(df: pd.DataFrame) -> tuple:
    """Returns (html_section, feature_scores: dict r→score)"""
    if df.empty or "mfe_20d" not in df.columns:
        return '<div class="section"><h2>المرحلة 2: اتساق المكونات</h2><p class="warn">بيانات غير كافية</p></div>', {}

    mfe = df["mfe_20d"].fillna(0)
    bq  = df["bq_score"].fillna(0) if "bq_score" in df.columns else pd.Series([0]*len(df))
    rows   = []
    scores = {}

    for col in R_COLS:
        if col not in df.columns:
            continue
        vals = df[col].fillna(0)
        n    = vals.notna().sum()
        if n < 10:
            rows.append([R_LABELS[col], str(n), "—","—","—","—","—"])
            scores[col] = 0
            continue

        # correlation with MFE (Spearman)
        if SCIPY_OK:
            spear, p_spear = sp_stats.spearmanr(vals, mfe)
        else:
            corr_df = pd.DataFrame({"v": vals, "m": mfe}).dropna()
            spear   = corr_df["v"].corr(corr_df["m"], method="spearman") if len(corr_df) > 5 else 0.0
            p_spear = 0.5

        # win rate in top half vs bottom half
        med = vals.median()
        top = df.loc[vals >= med, "mfe_20d"].dropna()
        bot = df.loc[vals < med,  "mfe_20d"].dropna()
        wr_top = (top >= WIN_MFE_THRESH).mean() if len(top) else 0
        wr_bot = (bot >= WIN_MFE_THRESH).mean() if len(bot) else 0
        lift   = wr_top / wr_bot if wr_bot > 0 else float("nan")

        # avg MFE top half
        avg_mfe_top = top.mean() if len(top) else 0

        # monotonicity: split into quartiles, check if avg MFE is increasing
        try:
            q_labels  = pd.qcut(vals, 4, labels=False, duplicates="drop")
            mono_mfe  = df.groupby(q_labels)["mfe_20d"].mean().dropna()
            mono_corr = mono_mfe.corr(pd.Series(range(len(mono_mfe)), index=mono_mfe.index))
            mono_ok   = mono_corr > 0.5 if len(mono_mfe) >= 3 else None
        except Exception:
            mono_ok = None

        # information value proxy (abs spearman × sign)
        iv = abs(spear)

        # component score 0-100
        comp_score  = min(100, max(0, iv * 60 + (lift - 1) * 20 + (1 if mono_ok else 0) * 20))
        scores[col] = round(comp_score, 1)

        spear_fmt = f"{spear:+.3f}"
        lift_fmt  = f"{lift:.2f}" if not (isinstance(lift, float) and (lift != lift)) else "—"
        mono_fmt  = "✓" if mono_ok else ("✗" if mono_ok is False else "—")
        p_fmt     = f"{p_spear:.3f}" if SCIPY_OK else "—"
        mfe_fmt   = f"{avg_mfe_top:.1%}"

        rows.append([
            R_LABELS[col], str(int(n)), spear_fmt, p_fmt, lift_fmt, mfe_fmt,
            mono_fmt, _bar(comp_score),
        ])

    html = f"""
<div class="section">
  <h2>المرحلة 2: اتساق المكونات <span class="phase-badge">Feature Analysis</span></h2>
  <p style="font-size:.88em;color:#555">Spearman مع MFE_20d — Lift = win-rate النصف العلوي ÷ السفلي — Mono = رتابة عبر الأرباع</p>
  {_tbl(
    ["المكوّن","N","Spearman","p-val","Lift","Avg-MFE(top)","Mono","درجة"],
    rows
  )}
</div>"""
    return html, scores


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 3 — Weight Validation
# ══════════════════════════════════════════════════════════════════════════════

def phase3_weight_validation(df: pd.DataFrame) -> str:
    if not SKLEARN_OK or df.empty or "mfe_20d" not in df.columns:
        return '<div class="section"><h2>المرحلة 3: التحقق من الأوزان</h2><p class="warn">sklearn غير متوفر أو بيانات غير كافية</p></div>'

    valid = df[R_COLS + ["mfe_20d"]].dropna()
    if len(valid) < 20:
        return f'<div class="section"><h2>المرحلة 3: التحقق من الأوزان</h2><p class="warn">عدد الإشارات ({len(valid)}) أقل من الحد الأدنى</p></div>'

    X = valid[R_COLS].values
    y = valid["mfe_20d"].values

    n      = len(X)
    split  = int(n * TRAIN_SPLIT)
    X_tr, X_te = X[:split], X[split:]
    y_tr, y_te = y[:split], y[split:]

    if len(y_tr) < 10 or len(y_te) < 5:
        return '<div class="section"><h2>المرحلة 3: التحقق من الأوزان</h2><p class="warn">تدريب/اختبار غير كافيَين</p></div>'

    model = RandomForestRegressor(
        n_estimators=200, max_depth=5,
        min_samples_leaf=3, random_state=42, n_jobs=-1,
    )
    model.fit(X_tr, y_tr)
    y_pred = model.predict(X_te)
    r2 = r2_score(y_te, y_pred)

    importances = model.feature_importances_
    imp_sum     = importances.sum()
    imp_pct     = importances / imp_sum if imp_sum > 0 else importances

    total_w     = sum(CURRENT_WEIGHTS.values())
    rows        = []
    suggestions = {}

    for i, col in enumerate(R_COLS):
        cur_w   = CURRENT_WEIGHTS.get(col, 0)
        cur_pct = cur_w / total_w
        ml_pct  = imp_pct[i]
        sugg_w  = round(ml_pct * total_w)
        delta   = sugg_w - cur_w
        delta_s = f"+{delta}" if delta > 0 else str(delta)
        delta_c = "b-high" if delta > 2 else ("b-low" if delta < -2 else "b-med")
        suggestions[col] = sugg_w
        rows.append([
            R_LABELS[col],
            str(cur_w),
            f"{cur_pct:.1%}",
            f"{ml_pct:.1%}",
            str(sugg_w),
            f'<span class="badge {delta_c}">{delta_s}</span>',
        ])

    html = f"""
<div class="section">
  <h2>المرحلة 3: التحقق من الأوزان <span class="phase-badge">Weight Validation</span></h2>
  <div class="kpi-row">
    {_kpi(str(len(valid)), "إشارات مُستخدَمة")}
    {_kpi(f"{r2:.3f}", "RF R² (اختبار)")}
    {_kpi(str(int(split)), "تدريب")}
    {_kpi(str(n - split), "اختبار")}
  </div>
  <p style="font-size:.85em;color:#555">
    الأهمية: Random Forest permutation importance على مجموعة الاختبار.
    الاقتراح = إعادة توزيع نسبي فقط — الأوزان مجمّدة في النظام الفعلي.
  </p>
  {_tbl(
    ["المكوّن","وزن حالي","%حالي","أهمية ML","وزن مقترح","فارق"],
    rows
  )}
  <div class="frozen-note">⚠ الأوزان الحالية مجمّدة — هذا اقتراح بحثي فقط</div>
</div>"""
    return html


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 4 — Gate Analysis
# ══════════════════════════════════════════════════════════════════════════════

def phase4_gate_analysis(df: pd.DataFrame) -> str:
    if df.empty or "mfe_20d" not in df.columns:
        return '<div class="section"><h2>المرحلة 4: تحليل العتبات</h2><p class="warn">بيانات غير كافية</p></div>'

    def _gate_stats(mask) -> tuple:
        sub = df.loc[mask, "mfe_20d"].dropna()
        n   = len(sub)
        if n < 3:
            return n, "—", "—"
        avg_mfe = sub.mean()
        wr      = (sub >= WIN_MFE_THRESH).mean()
        return n, f"{avg_mfe:.1%}", f"{wr:.0%}"

    # ── PRICE_GATE (r1_price) ──────────────────────────────────────────────
    pg_rows = []
    if "r1_price" in df.columns:
        for thresh in range(10, 25):
            n, am, wr = _gate_stats(df["r1_price"] >= thresh)
            cur = " ◀ حالي" if thresh == PRICE_GATE_NORMAL else ""
            pg_rows.append([str(thresh), str(n), am, wr, cur])

    # ── LIQ_GATE (r3_liquidity) ────────────────────────────────────────────
    lq_rows = []
    if "r3_liquidity" in df.columns:
        for thresh in [0, 5, 8, 10, 12, 14, 16, 18, 20]:
            n, am, wr = _gate_stats(df["r3_liquidity"] >= thresh)
            cur = " ◀ حالي (W=20)" if thresh == 20 else ""
            lq_rows.append([str(thresh), str(n), am, wr, cur])

    # ── ENTRY_SCORE_GATE (raw_score) ───────────────────────────────────────
    sc_rows = []
    if "raw_score" in df.columns:
        for thresh in range(25, 75, 5):
            n, am, wr = _gate_stats(df["raw_score"] >= thresh)
            cur = " ◀ حالي" if thresh == ENTRY_SCORE_GATE else ""
            sc_rows.append([str(thresh), str(n), am, wr, cur])

    html = f"""
<div class="section">
  <h2>المرحلة 4: تحليل العتبات <span class="phase-badge">Gate Analysis</span></h2>
  <div class="frozen-note">⚠ العتبات مجمّدة في النظام — النتائج أدناه للبحث فقط</div>

  <h3 style="color:#1a3c5e;margin:14px 0 6px">PRICE_GATE (r1_price ≥ x)</h3>
  {_tbl(["العتبة","N","Avg MFE","Win Rate","ملاحظة"],pg_rows) if pg_rows else '<p class="warn">r1_price غير متوفر</p>'}

  <h3 style="color:#1a3c5e;margin:14px 0 6px">LIQ_GATE (r3_liquidity ≥ x)</h3>
  {_tbl(["العتبة","N","Avg MFE","Win Rate","ملاحظة"],lq_rows) if lq_rows else '<p class="warn">r3_liquidity غير متوفر</p>'}

  <h3 style="color:#1a3c5e;margin:14px 0 6px">ENTRY_SCORE_GATE (raw_score ≥ x)</h3>
  {_tbl(["العتبة","N","Avg MFE","Win Rate","ملاحظة"],sc_rows) if sc_rows else '<p class="warn">raw_score غير متوفر</p>'}
</div>"""
    return html


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 5 — Edge Discovery
# ══════════════════════════════════════════════════════════════════════════════

def _edge_test(df: pd.DataFrame, mask: pd.Series) -> tuple:
    """Returns (n, avg_mfe, win_rate, p_value)"""
    sub  = df.loc[mask, "mfe_20d"].dropna()
    rest = df.loc[~mask, "mfe_20d"].dropna()
    n    = len(sub)
    if n < MIN_N_EDGE:
        return n, None, None, None
    avg_mfe = sub.mean()
    wr      = (sub >= WIN_MFE_THRESH).mean()
    # t-test vs rest
    if SCIPY_OK and len(rest) >= 5:
        _, p = sp_stats.ttest_ind(sub, rest, equal_var=False)
    else:
        p = 1.0
    return n, avg_mfe, wr, p


def phase5_edge_discovery(df: pd.DataFrame) -> str:
    if df.empty or "mfe_20d" not in df.columns:
        return '<div class="section"><h2>المرحلة 5: اكتشاف الحافة</h2><p class="warn">بيانات غير كافية</p></div>'

    base_wr  = (df["mfe_20d"].dropna() >= WIN_MFE_THRESH).mean()
    base_mfe = df["mfe_20d"].dropna().mean()

    available = [c for c in R_COLS if c in df.columns and df[c].notna().sum() >= MIN_N_EDGE]
    medians   = {c: df[c].median() for c in available}

    edges = []

    # Singles
    for col in available:
        mask = df[col] >= medians[col]
        n, am, wr, p = _edge_test(df, mask)
        if n and am is not None:
            lift = am / base_mfe if base_mfe > 0 else 0
            edges.append({
                "combo": R_LABELS.get(col, col),
                "n": n, "avg_mfe": am, "wr": wr,
                "lift": lift, "p": p, "degree": 1,
            })

    # Pairs
    for c1, c2 in combinations(available, 2):
        mask = (df[c1] >= medians[c1]) & (df[c2] >= medians[c2])
        n, am, wr, p = _edge_test(df, mask)
        if n and am is not None:
            lift  = am / base_mfe if base_mfe > 0 else 0
            label = f"{R_LABELS.get(c1,c1)} + {R_LABELS.get(c2,c2)}"
            edges.append({
                "combo": label,
                "n": n, "avg_mfe": am, "wr": wr,
                "lift": lift, "p": p, "degree": 2,
            })

    # Triples (top pairs by lift)
    if edges:
        pair_edges = sorted([e for e in edges if e["degree"] == 2],
                            key=lambda x: -x["lift"])[:5]
        used_cols  = set()
        for e in pair_edges:
            for c in available:
                if R_LABELS.get(c, c) in e["combo"]:
                    used_cols.add(c)
        for base_e in pair_edges[:3]:
            for c3 in available:
                if R_LABELS.get(c3, c3) in base_e["combo"]:
                    continue
                # reconstruct mask from label
                matched = [c for c in available if R_LABELS.get(c, c) in base_e["combo"]]
                if len(matched) < 2:
                    continue
                mask = (df[matched[0]] >= medians[matched[0]]) & \
                       (df[matched[1]] >= medians[matched[1]]) & \
                       (df[c3]         >= medians[c3])
                n, am, wr, p = _edge_test(df, mask)
                if n and am is not None:
                    lift  = am / base_mfe if base_mfe > 0 else 0
                    label = base_e["combo"] + f" + {R_LABELS.get(c3,c3)}"
                    edges.append({
                        "combo": label,
                        "n": n, "avg_mfe": am, "wr": wr,
                        "lift": lift, "p": p, "degree": 3,
                    })

    # filter p ≤ 0.25 and sort by avg_mfe descending, take top 20
    sig  = sorted([e for e in edges if e["p"] is not None and e["p"] <= 0.25],
                  key=lambda x: -x["avg_mfe"])[:20]
    rows = []
    for e in sig:
        deg_s = ["—","فردي","زوجي","ثلاثي"][min(e["degree"],3)]
        p_s   = f"{e['p']:.3f}" if e["p"] is not None else "—"
        rows.append([
            e["combo"], deg_s, str(e["n"]),
            f"{e['avg_mfe']:.1%}",
            f"{e['wr']:.0%}",
            f"{e['lift']:.2f}×",
            p_s,
        ])

    html = f"""
<div class="section">
  <h2>المرحلة 5: اكتشاف الحافة <span class="phase-badge">Edge Discovery</span></h2>
  <div class="kpi-row">
    {_kpi(f"{base_wr:.0%}", "Win Rate قاعدي")}
    {_kpi(f"{base_mfe:.1%}", "Avg MFE قاعدي")}
    {_kpi(str(len(sig)), "حافة ذات دلالة")}
  </div>
  <p style="font-size:.85em;color:#555">فلترة: p ≤ 0.25 و N ≥ {MIN_N_EDGE} — ترتيب تنازلي حسب Avg MFE</p>
  {_tbl(["التركيبة","نوع","N","Avg MFE","Win Rate","Lift","p-value"],rows) if rows else '<p class="warn">لا حوافّ ذات دلالة</p>'}
</div>"""
    return html


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 6 — Cluster Profiles
# ══════════════════════════════════════════════════════════════════════════════

def phase6_clusters(df: pd.DataFrame) -> str:
    if not SKLEARN_OK or df.empty or "mfe_20d" not in df.columns:
        return '<div class="section"><h2>المرحلة 6: ملامح التجميع</h2><p class="warn">sklearn غير متوفر أو بيانات غير كافية</p></div>'

    feat_cols = [c for c in R_COLS if c in df.columns and df[c].notna().sum() >= MIN_N_CLUSTER]
    if not feat_cols:
        return '<div class="section"><h2>المرحلة 6: ملامح التجميع</h2><p class="warn">مكونات غير كافية</p></div>'

    sub = df[feat_cols + ["mfe_20d", "bq_score"]].dropna(subset=feat_cols)
    if len(sub) < 9:
        return f'<div class="section"><h2>المرحلة 6: ملامح التجميع</h2><p class="warn">إشارات ({len(sub)}) أقل من الحد الأدنى</p></div>'

    # scale and cluster
    scaler  = StandardScaler()
    X_s     = scaler.fit_transform(sub[feat_cols])
    k       = min(3, len(sub) // MIN_N_CLUSTER)
    if k < 2:
        return '<div class="section"><h2>المرحلة 6: ملامح التجميع</h2><p class="warn">إشارات غير كافية للتجميع</p></div>'

    km        = KMeans(n_clusters=k, random_state=42, n_init=10)
    labels    = km.fit_predict(X_s)
    sub       = sub.copy()
    sub["cl"] = labels

    # label each cluster by MFE
    cl_mfe   = sub.groupby("cl")["mfe_20d"].mean().sort_values(ascending=False)
    cl_label = {}
    tag_map  = {0: "قاع قوي 🟢", 1: "متوسط 🟡", 2: "ضعيف 🔴"}
    for rank, cl_idx in enumerate(cl_mfe.index):
        cl_label[cl_idx] = tag_map.get(rank, f"مجموعة {rank}")

    rows = []
    for cl_idx in cl_mfe.index:
        grp   = sub[sub["cl"] == cl_idx]
        n     = len(grp)
        am    = grp["mfe_20d"].mean()
        bqs   = grp["bq_score"].mean() if "bq_score" in grp else float("nan")
        wr    = (grp["mfe_20d"] >= WIN_MFE_THRESH).mean()
        # mean of each r component (raw scale after inverse transform)
        r_means = {c: grp[c].mean() for c in feat_cols}
        top_r   = max(r_means, key=r_means.get)
        rows.append([
            cl_label[cl_idx], str(n),
            f"{am:.1%}", f"{bqs:.1f}" if not (isinstance(bqs, float) and bqs != bqs) else "—",
            f"{wr:.0%}",
            R_LABELS.get(top_r, top_r),
        ])

    # per-cluster r-component means table
    detail_rows = []
    for cl_idx in cl_mfe.index:
        grp  = sub[sub["cl"] == cl_idx]
        vals = [cl_label[cl_idx]] + [f"{grp[c].mean():.1f}" if c in grp.columns else "—" for c in feat_cols]
        detail_rows.append(vals)

    html = f"""
<div class="section">
  <h2>المرحلة 6: ملامح التجميع <span class="phase-badge">Cluster Profiles</span></h2>
  <p style="font-size:.85em;color:#555">KMeans (k={k}) على مكونات r1–r8 — ترتيب حسب Avg MFE تنازلياً</p>
  {_tbl(["المجموعة","N","Avg MFE","BQ Avg","Win Rate","أقوى مكوّن"],rows)}
  <h3 style="color:#1a3c5e;margin:14px 0 6px">متوسط المكونات لكل مجموعة</h3>
  {_tbl(["المجموعة"]+[R_LABELS.get(c,c) for c in feat_cols], detail_rows)}
</div>"""
    return html


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 7 — Final Summary
# ══════════════════════════════════════════════════════════════════════════════

def phase7_summary(
    dq_score:       float,
    feat_scores:    dict,
    df:             pd.DataFrame,
) -> str:
    # Overall grade
    if dq_score >= 70 and df is not None and len(df) >= 50:
        data_grade = ("b-high", "جيدة")
    elif dq_score >= 40:
        data_grade = ("b-med",  "متوسطة")
    else:
        data_grade = ("b-low",  "ضعيفة")

    # Strongest / weakest components (by feature score)
    if feat_scores:
        ranked  = sorted(feat_scores.items(), key=lambda x: -x[1])
        top3    = ranked[:3]
        bottom3 = ranked[-3:][::-1]
    else:
        top3 = bottom3 = []

    top_html = "".join(
        f'<li><strong>{R_LABELS.get(c,c)}</strong> — درجة {s:.0f}/100</li>'
        for c, s in top3
    )
    bot_html = "".join(
        f'<li><strong>{R_LABELS.get(c,c)}</strong> — درجة {s:.0f}/100</li>'
        for c, s in bottom3
    )

    # Sample size note
    n = len(df) if df is not None else 0
    sample_note = (
        "✓ حجم العينة كافٍ للتحليل الموثوق" if n >= 60 else
        f"⚠ حجم العينة ({n}) صغير — زِد الإشارات لمزيد من الدقة"
    )

    recs = []
    if n < 60:
        recs.append("جمع إشارات إضافية لتحسين دقة التحليل الإحصائي")
    if feat_scores:
        low_feats = [R_LABELS.get(c,c) for c,s in feat_scores.items() if s < 30]
        if low_feats:
            recs.append(f"مكونات تستحق مراجعة الحساب (ارتباط منخفض): {', '.join(low_feats[:3])}")
        high_feats = [R_LABELS.get(c,c) for c,s in feat_scores.items() if s > 70]
        if high_feats:
            recs.append(f"مكونات ذات قيمة تنبؤية عالية: {', '.join(high_feats[:3])}")

    rec_html = "".join(f"<li>{r}</li>" for r in recs) if recs else "<li>لا توصيات استثنائية</li>"

    html = f"""
<div class="section">
  <h2>المرحلة 7: الملخص النهائي <span class="phase-badge">Final Summary</span></h2>
  <div class="kpi-row">
    {_kpi(f'<span class="badge {data_grade[0]}">{data_grade[1]}</span>', "جودة البيانات")}
    {_kpi(str(n), "إشارات ناضجة")}
    {_kpi(f"{dq_score:.0f}/100", "درجة DQ")}
  </div>
  <div class="rec-box">
    <h3>أقوى المكونات</h3>
    <ul style="margin:4px 0;padding-right:18px">{top_html or "<li>—</li>"}</ul>
  </div>
  <div class="rec-box">
    <h3>المكونات الأضعف تنبؤياً</h3>
    <ul style="margin:4px 0;padding-right:18px">{bot_html or "<li>—</li>"}</ul>
  </div>
  <div class="rec-box">
    <h3>توصيات البحث</h3>
    <ul style="margin:4px 0;padding-right:18px">{rec_html}</ul>
  </div>
  <div class="warn">{sample_note}</div>
  <div class="frozen-note">
    ⚙ جميع التوصيات بحثية — منطق الدخول والأوزان والعتبات مجمّدة في النظام الفعلي
  </div>
</div>"""
    return html


# ══════════════════════════════════════════════════════════════════════════════
# MAIN — build report
# ══════════════════════════════════════════════════════════════════════════════

def build_report() -> str:
    print("[QuantReport] Loading data…")
    df     = _load_data()
    df_all = _load_all_signals()
    n_mat  = len(df)
    print(f"[QuantReport] {len(df_all)} total signals, {n_mat} mature")

    sections = []

    # Phase 1
    print("[QuantReport] Phase 1: Data Audit…")
    s1, dq_score = phase1_data_audit(df, df_all)
    sections.append(s1)

    # Phase 2
    print("[QuantReport] Phase 2: Feature Consistency…")
    s2, feat_scores = phase2_feature_consistency(df)
    sections.append(s2)

    # Phase 3
    print("[QuantReport] Phase 3: Weight Validation…")
    sections.append(phase3_weight_validation(df))

    # Phase 4
    print("[QuantReport] Phase 4: Gate Analysis…")
    sections.append(phase4_gate_analysis(df))

    # Phase 5
    print("[QuantReport] Phase 5: Edge Discovery…")
    sections.append(phase5_edge_discovery(df))

    # Phase 6
    print("[QuantReport] Phase 6: Cluster Profiles…")
    sections.append(phase6_clusters(df))

    # Phase 7
    print("[QuantReport] Phase 7: Final Summary…")
    sections.append(phase7_summary(dq_score, feat_scores, df))

    body    = "\n".join(sections)
    weights_fmt = " | ".join(
        f"{WEIGHT_LABELS.get(k,k)}={v}" for k, v in CURRENT_WEIGHTS.items()
    )

    html = f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>تقرير البحث الكمي — {TODAY}</title>
  {_CSS}
</head>
<body>
<div class="container">
  <div class="header">
    <h1>📊 تقرير البحث الكمي — EGX30</h1>
    <p>تاريخ: {TODAY} | إشارات ناضجة: {n_mat} | {weights_fmt}</p>
  </div>
  {body}
</div>
</body>
</html>"""
    return html


def main():
    html      = build_report()
    out_path  = f"quant_research_report_{TODAY}.html"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[QuantReport] Written → {out_path}")


if __name__ == "__main__":
    main()
