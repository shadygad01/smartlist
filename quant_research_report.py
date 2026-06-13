"""
Quant Research Report
=====================
تقرير بحثي كمي شامل — 7 مراحل — يُولَّد تلقائياً يومياً.

لا يُعدّل أي منطق في النظام — بحث وإبلاغ فقط.

═══════════════════════════════════════════════════════
فلسفة التقييم — الترتيب الإلزامي للمقاييس:
  1. CAGR            ← العائد السنوي المركب
  2. Profit Factor   ← مجموع الأرباح ÷ مجموع الخسائر
  3. Average MFE     ← متوسط أقصى ربح غير محقق
  4. Calmar Ratio    ← CAGR ÷ متوسط الـ MAE
  5. Max Drawdown    ← أسوأ تراجع منفرد
  --- Win Rate مقياس مكمّل، الترتيب يبدأ من CAGR ---
  النظام يحقق عوائده من عدد قليل من الرابحين الكبار.
  رفع Win Rate يقتل العائد الكلي بتفضيل إشارات آمنة ضعيفة.
═══════════════════════════════════════════════════════
"""

import os
import sys
from datetime import date
from itertools import combinations

import warnings
warnings.filterwarnings("ignore", category=RuntimeWarning)

try:
    import numpy as np
    import pandas as pd
except ImportError:
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

WIN_MFE_THRESH  = 0.08   # 8% MFE = فائز — للمرجعية فقط، ليس للترتيب
MIN_N_EDGE      = 8
MIN_N_CLUSTER   = 5
TRAIN_SPLIT     = 0.70
TODAY           = date.today().isoformat()
ANNUALIZE_DAYS  = 252
HOLD_DAYS       = 20     # افتراض فترة الاحتفاظ 20 يوم تداول

PRICE_GATE_NORMAL    = 16
PRICE_GATE_WHITELIST = 15
ENTRY_SCORE_GATE     = 40
TOTAL_EGX_STOCKS     = 27   # إجمالي أسهم الكون

# ── Retention Thresholds (Phase 0 Constraints) ────────────────────────────────
RETENTION_TARGET  = 0.95   # الهدف
RETENTION_WARN    = 0.80   # تحذير — اتشال 20%+ من الإشارات
RETENTION_PENALTY = 0.60   # غرامة — اتشال 40%+ من الإشارات
RETENTION_REJECT  = 0.40   # رفض — اتشال أكثر من 60% من الإشارات

# ── Optimization Score Weights ─────────────────────────────────────────────────
OPT_WEIGHTS = {
    "cagr":      0.30,
    "pf":        0.20,
    "calmar":    0.15,
    "avg_mfe":   0.15,
    "retention": 0.10,
    "coverage":  0.05,
    "stocks":    0.05,
}

PHILOSOPHY_NOTE = """
<div style="background:#1a3c5e;color:#fff;border-radius:6px;padding:10px 16px;
            margin:10px 0;font-size:.85em;line-height:1.7">
  <strong>⚖ ترتيب التقييم:</strong>
  CAGR → Profit Factor → Avg MFE → Calmar → Max DD → Win Rate
  <span style="opacity:.7;margin-right:12px">|</span>
  Win Rate مقياس مهم لكنه ليس الأول — النظام يحقق عوائده من رابحين قلائل كبار،
  لذا CAGR وProfit Factor يُقيّمان حجم العائد الكلي بدقة أكبر.
</div>"""

# ── CSS ────────────────────────────────────────────────────────────────────────
_CSS = """
<style>
  body{font-family:'Segoe UI',Arial,sans-serif;background:#f0f2f5;color:#222;direction:rtl;margin:0}
  .container{max-width:980px;margin:20px auto;background:#fff;border-radius:10px;
             box-shadow:0 2px 12px #0002;overflow:hidden}
  .header{background:linear-gradient(135deg,#1a3c5e,#2a6496);color:#fff;padding:28px 30px}
  .header h1{margin:0;font-size:1.6em}
  .header p{margin:6px 0 0;opacity:.8;font-size:.9em}
  .section{padding:20px 30px;border-bottom:1px solid #eee}
  .section h2{color:#1a3c5e;margin-top:0;font-size:1.15em;
              border-right:4px solid #2a6496;padding-right:10px}
  .kpi-row{display:flex;flex-wrap:wrap;gap:12px;margin:10px 0}
  .kpi{flex:1;min-width:110px;background:#f7f9fb;border-radius:8px;
       padding:14px 16px;text-align:center}
  .kpi .val{font-size:1.7em;font-weight:700;color:#1a3c5e}
  .kpi .lbl{font-size:.76em;color:#666;margin-top:4px}
  .tbl-wrap{overflow-x:auto;-webkit-overflow-scrolling:touch}
  table{width:100%;border-collapse:collapse;font-size:.85em}
  th{background:#1a3c5e;color:#fff;padding:8px 10px;text-align:right;white-space:nowrap}
  th.wr-col{background:#4a5568;opacity:.8}
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
  .wr-dim{color:#999;font-size:.85em}
</style>"""


# ── DB Query ───────────────────────────────────────────────────────────────────

def _load_data() -> pd.DataFrame:
    conn = get_conn()
    try:
        view_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='view' AND name='v_all_signals'"
        ).fetchone()
        if view_exists:
            rows = conn.execute("SELECT * FROM v_all_signals ORDER BY signal_date").fetchall()
        else:
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
        for c in ["mae_20d", "mae_40d"]:
            if c in df.columns:
                df[c] = df[c].abs()
        return df
    finally:
        conn.close()


def _load_all_signals() -> pd.DataFrame:
    conn = get_conn()
    try:
        view_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='view' AND name='v_all_signals'"
        ).fetchone()
        if view_exists:
            rows = conn.execute("SELECT * FROM v_all_signals ORDER BY signal_date").fetchall()
        else:
            rows = conn.execute("SELECT * FROM signals ORDER BY signal_date").fetchall()
        return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()
    finally:
        conn.close()


# ── Metrics Engine ─────────────────────────────────────────────────────────────

def _metrics(sub: pd.DataFrame) -> dict:
    """
    يحسب المقاييس الخمسة بالترتيب الإلزامي.
    يُستخدم r20d للعائد الفعلي — mfe_20d للإمكانية — mae_20d للمخاطرة.
    """
    n = len(sub)
    n_stocks = sub["symbol"].nunique() if "symbol" in sub.columns else 0
    result = {"n": n, "n_stocks": n_stocks, "cagr": None, "pf": None,
              "avg_mfe": None, "calmar": None, "max_dd": None, "win_rate": None}
    if n < 3:
        return result

    # 1. CAGR — من r20d (العائد الفعلي لكل إشارة)
    if "r20d" in sub.columns:
        r20 = sub["r20d"].dropna()
        if len(r20) >= 3:
            mean_r = r20.mean()
            cagr   = (1 + mean_r) ** (ANNUALIZE_DAYS / HOLD_DAYS) - 1
            result["cagr"] = cagr
            # 2. Profit Factor
            gains  = r20[r20 > 0].sum()
            losses = r20[r20 < 0].abs().sum()
            result["pf"] = gains / losses if losses > 0 else float("inf")

    # 3. Average MFE
    if "mfe_20d" in sub.columns:
        mfe = sub["mfe_20d"].dropna()
        if len(mfe) >= 3:
            result["avg_mfe"] = mfe.mean()
            # Win Rate — مقياس كامل في التقرير
            result["win_rate"] = (mfe >= WIN_MFE_THRESH).mean()

    # 4. Calmar = CAGR / avg_MAE
    if "mae_20d" in sub.columns and result["cagr"] is not None:
        mae = sub["mae_20d"].dropna()
        if len(mae) >= 3 and mae.mean() > 0:
            result["calmar"] = result["cagr"] / mae.mean()

    # 5. Max Drawdown (أسوأ تراجع منفرد)
    if "mae_20d" in sub.columns:
        mae = sub["mae_20d"].dropna()
        if len(mae) >= 1:
            result["max_dd"] = mae.max()

    return result


def _fmt_metrics(m: dict, base: dict | None = None,
                 base_n: int = 0, show_retention: bool = False) -> list:
    """
    يُرجع قائمة خلايا HTML:
    N | Retention | CAGR | PF | Avg MFE | Calmar | Max DD | Win Rate | OPT Score
    """
    def _delta_badge(val, bval, hi, lo, fmt):
        if val is None:
            return "—"
        s = f"{val:{fmt}}"
        cls = "b-high" if val >= hi else ("b-low" if val < lo else "b-med")
        if base and bval is not None:
            d = val - bval
            sign = "+" if d > 0 else ""
            s += f' <span style="font-size:.73em;color:#aaa">({sign}{d:{fmt}})</span>'
        return f'<span class="badge {cls}">{s}</span>'

    bm   = base or {}
    n    = m["n"]
    ret  = _retention_badge(n, base_n) if (show_retention and base_n > 0) else ""
    cagr_s = _delta_badge(m["cagr"],    bm.get("cagr"),    0.20, 0.05, ".0%")
    pf_s   = _delta_badge(m["pf"],      bm.get("pf"),      1.5,  1.0,  ".2f")
    mfe_s  = _delta_badge(m["avg_mfe"], bm.get("avg_mfe"), 0.12, 0.05, ".1%")
    cal_s  = _delta_badge(m["calmar"],  bm.get("calmar"),  2.0,  0.5,  ".2f")
    dd_s   = f"{m['max_dd']:.1%}"  if m["max_dd"]  is not None else "—"
    wr_s   = f"{m['win_rate']:.0%}"if m["win_rate"] is not None else "—"

    cells = [str(n)]
    if show_retention and base_n > 0:
        cells.append(ret)
        opt = _opt_score(m, bm, n, base_n, m.get("n_stocks", 0))
        cells += [cagr_s, pf_s, mfe_s, cal_s, dd_s, wr_s,
                  f'<span class="badge {"b-high" if opt>=60 else "b-low" if opt<35 else "b-med"}">{opt:.0f}</span>']
    else:
        cells += [cagr_s, pf_s, mfe_s, cal_s, dd_s, wr_s]
    return cells


def _metrics_headers(with_retention: bool = False) -> list:
    base = ["N"]
    if with_retention:
        base += ["Retention %", "CAGR", "Profit Factor", "Avg MFE",
                 "Calmar", "Max DD", "Win Rate", "OPT Score"]
    else:
        base += ["CAGR", "Profit Factor", "Avg MFE", "Calmar", "Max DD", "Win Rate"]
    return base


METRICS_HEADERS = _metrics_headers(with_retention=False)


# ── HTML helpers ───────────────────────────────────────────────────────────────

def _retention_badge(n: int, base_n: int) -> str:
    """يُظهر نسبة الاحتفاظ مع badge ملون + تحذير إن كانت أقل من العتبة."""
    if base_n == 0:
        return "—"
    r = n / base_n
    if r >= RETENTION_TARGET:
        cls, note = "b-high", ""
    elif r >= RETENTION_WARN:
        cls, note = "b-med", " ⚠"
    elif r >= RETENTION_PENALTY:
        cls, note = "b-low", " ⛔"
    else:
        cls, note = "b-low", " ❌ رفض"
    return f'<span class="badge {cls}">{r:.0%}{note}</span>'


def _opt_score(m: dict, base_m: dict, n: int, base_n: int,
               n_stocks: int = 0) -> float:
    """
    درجة التحسين المركّبة 0-100.
    تُعاقَب العوامل ذات الاحتفاظ المنخفض تلقائياً.
    """
    def _norm(val, base, cap):
        if val is None or base is None or base == 0:
            return 0.0
        return min(1.0, max(0.0, val / cap))

    ret = (n / base_n) if base_n > 0 else 0
    cov = (n_stocks / TOTAL_EGX_STOCKS) if n_stocks else (ret * 0.9)

    score  = OPT_WEIGHTS["cagr"]     * _norm(m.get("cagr"),    None, 0.5) * 100
    score += OPT_WEIGHTS["pf"]       * _norm(m.get("pf"),      None, 3.0) * 100
    score += OPT_WEIGHTS["calmar"]   * _norm(m.get("calmar"),  None, 5.0) * 100
    score += OPT_WEIGHTS["avg_mfe"]  * _norm(m.get("avg_mfe"), None, 0.3) * 100
    score += OPT_WEIGHTS["retention"]* ret * 100
    score += OPT_WEIGHTS["coverage"] * cov * 100
    score += OPT_WEIGHTS["stocks"]   * cov * 100

    # عقوبة الاحتفاظ المنخفض
    if ret < RETENTION_REJECT:
        score *= 0.3
    elif ret < RETENTION_PENALTY:
        score *= 0.65
    elif ret < RETENTION_WARN:
        score *= 0.88

    return round(min(100, score), 1)


def _badge(val: float, hi: float, lo: float, fmt: str = ".1%") -> str:
    cls = "b-high" if val >= hi else ("b-low" if val < lo else "b-med")
    return f'<span class="badge {cls}">{val:{fmt}}</span>'


def _kpi(val: str, lbl: str) -> str:
    return f'<div class="kpi"><div class="val">{val}</div><div class="lbl">{lbl}</div></div>'


def _bar(score: float, maxv: float = 100) -> str:
    pct = max(0, min(100, score / maxv * 100))
    return (f'<span class="score-bar" style="width:60px">'
            f'<span class="score-fill" style="width:{pct:.0f}%"></span></span>'
            f'{score:.0f}')


def _tbl(headers: list, rows: list) -> str:
    ths = "".join(f"<th>{h}</th>" for h in headers)
    trs = "".join(
        "<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>"
        for row in rows
    )
    return (f'<div class="tbl-wrap"><table>'
            f'<thead><tr>{ths}</tr></thead>'
            f'<tbody>{trs}</tbody></table></div>')


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 0 — Operational Constraints
# ══════════════════════════════════════════════════════════════════════════════

def phase0_constraints(df: pd.DataFrame, df_all: pd.DataFrame) -> str:
    n_mat   = len(df)
    n_all   = len(df_all)
    n_stk   = df_all["symbol"].nunique() if "symbol" in df_all.columns else 0

    # Signals per year / month
    if "signal_date" in df_all.columns and len(df_all) > 1:
        dates = pd.to_datetime(df_all["signal_date"])
        span_days = (dates.max() - dates.min()).days or 1
        sig_yr  = round(n_all / span_days * 365, 1)
        sig_mo  = round(n_all / span_days * 30,  1)
    else:
        sig_yr = sig_mo = 0

    coverage = f"{n_stk}/{TOTAL_EGX_STOCKS}"

    html = f"""
<div class="section" style="border-right:6px solid #c0392b;">
  <h2 style="color:#c0392b;">المرحلة 0: القيود التشغيلية
    <span class="phase-badge" style="background:#c0392b;">Operational Constraints</span>
  </h2>

  <div style="background:#fff3f3;border:1px solid #f5c6cb;border-radius:8px;
              padding:14px 18px;margin:10px 0;font-size:.88em;line-height:1.9">
    <strong>الهدف الأساسي:</strong> ماسح فرص قيعان — <em>ليس</em> تعظيم الدقة أو Win Rate<br>
    <strong>الأولوية القصوى:</strong> الحفاظ على تدفق الإشارات<br>
    <strong>قاعدة الرفض:</strong> أي توصية تُخفّض الإشارات > 5% تُرفَض إلا بأداء استثنائي<br>
    <strong>الحل المفضّل:</strong> <em>حافة أعلى مع عدد إشارات مشابه</em> — ليس إشارات أقل بإحصاءات أجمل
  </div>

  <div class="kpi-row">
    {_kpi(str(n_all),      "إجمالي الإشارات")}
    {_kpi(str(n_mat),      "إشارات ناضجة")}
    {_kpi(str(int(sig_yr)),"إشارة / سنة")}
    {_kpi(str(int(sig_mo)),"إشارة / شهر")}
    {_kpi(coverage,        "تغطية السوق")}
    {_kpi(str(n_stk),      "أسهم مُغطّاة")}
  </div>

  <div class="tbl-wrap">
  <table>
    <thead><tr>
      <th>العتبة</th><th>Retention %</th><th>حالة التوصية</th><th>الإجراء</th>
    </tr></thead>
    <tbody>
      <tr><td>≥ 95%</td>
          <td><span class="badge b-high">هدف مثالي</span></td>
          <td>✅ مقبول بالكامل</td><td>تطبيق مباشر</td></tr>
      <tr><td>80–95%</td>
          <td><span class="badge b-med">⚠ تحذير</span></td>
          <td>مقبول مع تحفظ — اتشال 20-5% من الإشارات</td><td>دراسة إضافية</td></tr>
      <tr><td>40–80%</td>
          <td><span class="badge b-low">⛔ غرامة</span></td>
          <td>غرامة في OPT Score — اتشال 20-60%</td><td>رفض إلا لأداء استثنائي</td></tr>
      <tr><td>< 40%</td>
          <td><span class="badge b-low">❌ رفض</span></td>
          <td>مرفوض — اتشال أكثر من 60% من الإشارات</td><td>رفض</td></tr>
    </tbody>
  </table>
  </div>

  <div style="background:#1a3c5e;color:#fff;border-radius:6px;padding:10px 16px;
              margin:10px 0;font-size:.83em;line-height:1.8">
    <strong>صيغة OPT Score:</strong>
    CAGR×30% + Profit Factor×20% + Calmar×15% + Avg MFE×15%
    + Signal Retention×10% + Market Coverage×5% + Unique Stocks×5%<br>
    <span style="opacity:.75">الاحتفاظ المنخفض يُطبَّق عليه ضارب تخفيض تلقائي: &lt;90%→×0.85 | &lt;80%→×0.60 | &lt;70%→×0.30</span>
  </div>
</div>"""
    return html, n_mat   # returns base_n for use in subsequent phases


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 1 — Data Audit
# ══════════════════════════════════════════════════════════════════════════════

def phase1_data_audit(df: pd.DataFrame, df_all: pd.DataFrame) -> tuple:
    total_all = len(df_all)
    total_mat = len(df)
    n_symbols = df_all["symbol"].nunique() if "symbol" in df_all.columns else 0

    null_rows     = []
    dq_penalties  = 0.0
    for col in R_COLS:
        n_null = df[col].isna().sum() if col in df.columns else total_mat
        pct_ok = (total_mat - n_null) / total_mat if total_mat else 0
        lbl    = R_LABELS.get(col, col)
        badge  = _badge(pct_ok, 0.90, 0.50, ".1%")
        null_rows.append([lbl, str(total_mat - n_null), str(n_null), badge])
        if pct_ok < 0.90:
            dq_penalties += (0.90 - pct_ok) * 20

    tgt_null_rows = []
    for col in ["mfe_20d", "mfe_40d", "mae_20d", "r20d", "bq_score"]:
        if col not in df.columns:
            continue
        n_null = df[col].isna().sum()
        pct_ok = (total_mat - n_null) / total_mat if total_mat else 0
        badge  = _badge(pct_ok, 0.90, 0.50, ".1%")
        tgt_null_rows.append([col, str(total_mat - n_null), str(n_null), badge])
        if pct_ok < 0.90:
            dq_penalties += (0.90 - pct_ok) * 10

    # توزيع MFE
    dist_html = ""
    if "mfe_20d" in df.columns:
        mfe   = df["mfe_20d"].dropna()
        n_tot = len(mfe)
        dist_html = f"""
<div class="kpi-row">
  {_kpi(f"{(mfe>=0.20).sum()/n_tot:.0%}" if n_tot else "—", "MFE ≥ 20% (كبار)")}
  {_kpi(f"{((mfe>=0.10)&(mfe<0.20)).sum()/n_tot:.0%}" if n_tot else "—", "MFE 10–20%")}
  {_kpi(f"{((mfe>=0.05)&(mfe<0.10)).sum()/n_tot:.0%}" if n_tot else "—", "MFE 5–10%")}
  {_kpi(f"{(mfe<0.05).sum()/n_tot:.0%}" if n_tot else "—", "MFE < 5%")}
  {_kpi(f"{mfe.median():.1%}" if n_tot else "—", "Median MFE")}
</div>"""

    # مقاييس كاملة للمجموعة كلها
    bm = _metrics(df)
    dq_score = max(0.0, 100.0 - dq_penalties)
    if total_mat < 30:
        dq_score = min(dq_score, 40.0)
    elif total_mat < 60:
        dq_score = min(dq_score, 70.0)

    dq_cls = "b-high" if dq_score >= 70 else ("b-low" if dq_score < 40 else "b-med")

    cagr_s  = f"{bm['cagr']:.0%}"   if bm["cagr"]    is not None else "—"
    pf_s    = f"{bm['pf']:.2f}"     if bm["pf"]      is not None else "—"
    mfe_s   = f"{bm['avg_mfe']:.1%}"if bm["avg_mfe"] is not None else "—"
    cal_s   = f"{bm['calmar']:.2f}" if bm["calmar"]  is not None else "—"
    dd_s    = f"{bm['max_dd']:.1%}" if bm["max_dd"]  is not None else "—"

    html = f"""
<div class="section">
  <h2>المرحلة 1: تدقيق البيانات <span class="phase-badge">Data Audit</span></h2>
  <div class="kpi-row">
    {_kpi(str(total_all),  "إجمالي الإشارات")}
    {_kpi(str(total_mat),  "إشارات ناضجة")}
    {_kpi(str(n_symbols),  "رمز سهم")}
    {_kpi(f'<span class="badge {dq_cls}">{dq_score:.0f}/100</span>', "درجة جودة البيانات")}
  </div>
  <div class="kpi-row">
    {_kpi(cagr_s,  "CAGR الكلي")}
    {_kpi(pf_s,    "Profit Factor")}
    {_kpi(mfe_s,   "Avg MFE")}
    {_kpi(cal_s,   "Calmar Ratio")}
    {_kpi(dd_s,    "Max DD")}
  </div>
  {dist_html}
  <h3 style="color:#1a3c5e;margin:14px 0 6px">اكتمال بيانات المكوّنات r1-r8</h3>
  {_tbl(["المكوّن","متوفر","Null","اكتمال"],null_rows)}
  <h3 style="color:#1a3c5e;margin:14px 0 6px">اكتمال متغيرات الهدف</h3>
  {_tbl(["المتغير","متوفر","Null","اكتمال"],tgt_null_rows)}
  <div class="frozen-note">⚙ منطق الإدخال مجمّد — هذا التقرير للبحث والإبلاغ فقط</div>
</div>"""
    return html, dq_score


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 2 — Feature Consistency
# ══════════════════════════════════════════════════════════════════════════════

def phase2_feature_consistency(df: pd.DataFrame) -> tuple:
    if df.empty or "mfe_20d" not in df.columns:
        return ('<div class="section"><h2>المرحلة 2</h2>'
                '<p class="warn">بيانات غير كافية</p></div>'), {}

    base_m = _metrics(df)
    rows   = []
    scores = {}

    for col in R_COLS:
        if col not in df.columns:
            continue
        vals = df[col].fillna(0)
        n    = int(vals.notna().sum())
        if n < 10:
            rows.append([R_LABELS[col], str(n)] + ["—"]*8)
            scores[col] = 0
            continue

        med    = vals.median()
        top_df = df.loc[vals >= med].copy()
        bot_df = df.loc[vals <  med].copy()
        top_m  = _metrics(top_df)
        bot_m  = _metrics(bot_df)

        # Spearman(component, MFE)
        if SCIPY_OK:
            spear, _ = sp_stats.spearmanr(vals, df["mfe_20d"].fillna(0))
        else:
            spear = vals.corr(df["mfe_20d"].fillna(0), method="spearman")

        # رتابة عبر الأرباع
        try:
            q      = pd.qcut(vals, 4, labels=False, duplicates="drop")
            mono_c = df.groupby(q)["mfe_20d"].mean().dropna()
            mono_ok = mono_c.corr(
                pd.Series(range(len(mono_c)), index=mono_c.index)
            ) > 0.5 if len(mono_c) >= 3 else None
        except Exception:
            mono_ok = None

        # درجة المكوّن — مرتّبة حسب CAGR/PF/MFE وليس Win Rate
        score = 0.0
        if top_m["cagr"] is not None and base_m["cagr"] is not None and base_m["cagr"] != 0:
            score += min(40, max(0, (top_m["cagr"] - base_m["cagr"]) / abs(base_m["cagr"]) * 40))
        if top_m["pf"] is not None and bot_m["pf"] is not None and bot_m["pf"] > 0:
            pf_lift = top_m["pf"] / bot_m["pf"]
            score  += min(30, max(0, (pf_lift - 1) * 30))
        if top_m["avg_mfe"] is not None and base_m["avg_mfe"] is not None and base_m["avg_mfe"] > 0:
            mfe_lift = top_m["avg_mfe"] / base_m["avg_mfe"]
            score   += min(20, max(0, (mfe_lift - 1) * 20))
        score += 10 if mono_ok else 0
        scores[col] = round(min(100, score), 1)

        # أعمدة الجدول
        cagr_top = f"{top_m['cagr']:.0%}"  if top_m["cagr"]    is not None else "—"
        pf_top   = f"{top_m['pf']:.2f}"    if top_m["pf"]       is not None else "—"
        mfe_top  = f"{top_m['avg_mfe']:.1%}"if top_m["avg_mfe"] is not None else "—"
        wr_top   = f'{top_m["win_rate"]:.0%}' \
                   if top_m["win_rate"] is not None else '—'
        mono_s   = "✓" if mono_ok else ("✗" if mono_ok is False else "—")
        sp_s     = f"{spear:+.3f}"

        rows.append([
            R_LABELS[col], str(n), sp_s,
            cagr_top, pf_top, mfe_top, mono_s, wr_top, _bar(scores[col]),
        ])

    html = f"""
<div class="section">
  <h2>المرحلة 2: اتساق المكونات <span class="phase-badge">Feature Analysis</span></h2>
  {PHILOSOPHY_NOTE}
  <p style="font-size:.85em;color:#555">
    CAGR/PF/MFE للنصف العلوي من كل مكوّن — Spearman مع MFE — Mono = رتابة عبر الأرباع
  </p>
  {_tbl(
    ["المكوّن","N","Spearman","CAGR(top)","PF(top)","MFE(top)","Mono",
     "Win Rate","درجة"],
    rows
  )}
</div>"""
    return html, scores


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 3 — Weight Validation
# ══════════════════════════════════════════════════════════════════════════════

def phase3_weight_validation(df: pd.DataFrame) -> str:
    if not SKLEARN_OK or df.empty or "mfe_20d" not in df.columns:
        return ('<div class="section"><h2>المرحلة 3: التحقق من الأوزان</h2>'
                '<p class="warn">sklearn غير متوفر أو بيانات غير كافية</p></div>')

    valid = df[R_COLS + ["mfe_20d"]].dropna()
    if len(valid) < 20:
        return (f'<div class="section"><h2>المرحلة 3: التحقق من الأوزان</h2>'
                f'<p class="warn">عدد الإشارات ({len(valid)}) أقل من الحد الأدنى</p></div>')

    X  = valid[R_COLS].values
    y  = valid["mfe_20d"].values
    n  = len(X)
    sp = int(n * TRAIN_SPLIT)
    Xtr, Xte = X[:sp], X[sp:]
    ytr, yte = y[:sp], y[sp:]

    if len(ytr) < 10 or len(yte) < 5:
        return ('<div class="section"><h2>المرحلة 3: التحقق من الأوزان</h2>'
                '<p class="warn">تدريب/اختبار غير كافيَين</p></div>')

    # RF مدرَّب على MFE (وليس Win Rate)
    model = RandomForestRegressor(
        n_estimators=200, max_depth=5,
        min_samples_leaf=3, random_state=42, n_jobs=-1,
    )
    model.fit(Xtr, ytr)
    r2  = r2_score(yte, model.predict(Xte))
    imp = model.feature_importances_
    imp_pct   = imp / imp.sum() if imp.sum() > 0 else imp
    total_w   = sum(CURRENT_WEIGHTS.values())

    rows = []
    for i, col in enumerate(R_COLS):
        cur_w   = CURRENT_WEIGHTS.get(col, 0)
        cur_pct = cur_w / total_w
        ml_pct  = imp_pct[i]
        sugg_w  = round(ml_pct * total_w)
        delta   = sugg_w - cur_w
        d_s     = f"+{delta}" if delta > 0 else str(delta)
        d_cls   = "b-high" if delta > 2 else ("b-low" if delta < -2 else "b-med")
        rows.append([
            R_LABELS[col], str(cur_w), f"{cur_pct:.1%}",
            f"{ml_pct:.1%}", str(sugg_w),
            f'<span class="badge {d_cls}">{d_s}</span>',
        ])

    html = f"""
<div class="section">
  <h2>المرحلة 3: التحقق من الأوزان <span class="phase-badge">Weight Validation</span></h2>
  {PHILOSOPHY_NOTE}
  <div class="kpi-row">
    {_kpi(str(len(valid)), "إشارات")}
    {_kpi(f"{r2:.3f}", "RF R² على MFE")}
    {_kpi(str(sp), "تدريب")}
    {_kpi(str(n-sp), "اختبار")}
  </div>
  <p style="font-size:.85em;color:#555">
    الأهمية مُحسَّبة على هدف <strong>MFE_20d</strong> — ليس Win Rate.
    النموذج يُقيّم مساهمة كل مكوّن في تعظيم العائد الكامن.
  </p>
  {_tbl(["المكوّن","وزن حالي","%حالي","أهمية↔MFE","وزن مقترح","فارق"],rows)}
  <div class="frozen-note">⚠ الأوزان الحالية مجمّدة — هذا اقتراح بحثي فقط</div>
</div>"""
    return html


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 4 — Gate Analysis
# ══════════════════════════════════════════════════════════════════════════════

def phase4_gate_analysis(df: pd.DataFrame, base_n: int = 0) -> str:
    if df.empty or "mfe_20d" not in df.columns:
        return ('<div class="section"><h2>المرحلة 4: تحليل العتبات</h2>'
                '<p class="warn">بيانات غير كافية</p></div>')

    _base_n = base_n or len(df)
    base_m  = _metrics(df)
    gate_headers = ["العتبة"] + _metrics_headers(with_retention=True) + ["ملاحظة"]

    def _gate_rows(col: str, thresholds: list, cur_thresh=None) -> list:
        rows = []
        for t in thresholds:
            mask = df[col] >= t
            sub  = df.loc[mask].copy()
            m    = _metrics(sub)
            ret  = m["n"] / _base_n if _base_n > 0 else 0
            # highlight current threshold
            note = " ◀ حالي" if t == cur_thresh else ""
            # reject flag
            if ret < RETENTION_REJECT and t != cur_thresh:
                note = " ❌ رفض (Retention<70%)"
            cells = _fmt_metrics(m, base_m, base_n=_base_n, show_retention=True)
            rows.append([str(t)] + cells + [note])
        return rows

    pg_rows = _gate_rows("r1_price",    list(range(10, 25)), PRICE_GATE_NORMAL) \
              if "r1_price"    in df.columns else []
    lq_rows = _gate_rows("r3_liquidity",[0,5,8,10,12,14,16,18,20], 20) \
              if "r3_liquidity" in df.columns else []
    sc_rows = _gate_rows("raw_score",   list(range(25, 75, 5)), ENTRY_SCORE_GATE) \
              if "raw_score"   in df.columns else []

    html = f"""
<div class="section">
  <h2>المرحلة 4: تحليل العتبات <span class="phase-badge">Gate Analysis</span></h2>
  {PHILOSOPHY_NOTE}
  <div class="frozen-note">⚠ العتبات مجمّدة في النظام — النتائج للبحث فقط</div>
  <p style="font-size:.84em;color:#555">
    <strong>Retention %</strong>: نسبة الإشارات المحتفَظ بها بعد تطبيق العتبة من القاعدة ({_base_n} إشارة).
    <strong>OPT Score</strong>: الدرجة المركّبة (CAGR×30 + PF×20 + Calmar×15 + MFE×15 + Retention×10 + Coverage×10) مع عقوبة الاحتفاظ المنخفض.
  </p>

  <h3 style="color:#1a3c5e;margin:14px 0 6px">PRICE_GATE — r1_price ≥ x</h3>
  {_tbl(gate_headers, pg_rows) if pg_rows else '<p class="warn">r1_price غير متوفر</p>'}

  <h3 style="color:#1a3c5e;margin:14px 0 6px">LIQ_GATE — r3_liquidity ≥ x</h3>
  {_tbl(gate_headers, lq_rows) if lq_rows else '<p class="warn">r3_liquidity غير متوفر</p>'}

  <h3 style="color:#1a3c5e;margin:14px 0 6px">ENTRY_SCORE_GATE — raw_score ≥ x</h3>
  {_tbl(gate_headers, sc_rows) if sc_rows else '<p class="warn">raw_score غير متوفر</p>'}
</div>"""
    return html


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 5 — Edge Discovery
# ══════════════════════════════════════════════════════════════════════════════

def _edge_test(df: pd.DataFrame, mask: pd.Series) -> tuple:
    """Returns (metrics_dict, p_value)"""
    sub  = df.loc[mask].copy()
    rest = df.loc[~mask, "mfe_20d"].dropna()
    m    = _metrics(sub)
    if m["n"] < MIN_N_EDGE or m["avg_mfe"] is None:
        return m, None
    if SCIPY_OK and len(rest) >= 5:
        _, p = sp_stats.ttest_ind(
            sub["mfe_20d"].dropna(), rest, equal_var=False
        )
    else:
        p = 1.0
    return m, p


def phase5_edge_discovery(df: pd.DataFrame, base_n: int = 0) -> str:
    if df.empty or "mfe_20d" not in df.columns:
        return ('<div class="section"><h2>المرحلة 5: اكتشاف الحافة</h2>'
                '<p class="warn">بيانات غير كافية</p></div>')

    _base_n  = base_n or len(df)
    base_m   = _metrics(df)
    available= [c for c in R_COLS
                if c in df.columns and df[c].notna().sum() >= MIN_N_EDGE]
    medians  = {c: df[c].median() for c in available}

    edges = []

    # فردية
    for col in available:
        mask = df[col] >= medians[col]
        m, p = _edge_test(df, mask)
        if p is not None:
            edges.append({"combo": R_LABELS.get(col, col),
                          "m": m, "p": p, "deg": 1})

    # زوجية
    for c1, c2 in combinations(available, 2):
        mask = (df[c1] >= medians[c1]) & (df[c2] >= medians[c2])
        m, p = _edge_test(df, mask)
        if p is not None:
            edges.append({"combo": f"{R_LABELS.get(c1,c1)} + {R_LABELS.get(c2,c2)}",
                          "m": m, "p": p, "deg": 2})

    # ثلاثية (أفضل 4 زوجية × كل مكوّن متبقٍّ)
    top_pairs = sorted([e for e in edges if e["deg"] == 2],
                       key=lambda x: -(x["m"]["avg_mfe"] or 0))[:4]
    for pe in top_pairs:
        for c3 in available:
            if R_LABELS.get(c3, c3) in pe["combo"]:
                continue
            matched = [c for c in available if R_LABELS.get(c, c) in pe["combo"]]
            if len(matched) < 2:
                continue
            mask = ((df[matched[0]] >= medians[matched[0]]) &
                    (df[matched[1]] >= medians[matched[1]]) &
                    (df[c3]         >= medians[c3]))
            m, p = _edge_test(df, mask)
            if p is not None:
                edges.append({
                    "combo": pe["combo"] + f" + {R_LABELS.get(c3,c3)}",
                    "m": m, "p": p, "deg": 3,
                })

    # فلترة p ≤ 0.25 — ترتيب: CAGR أولاً ثم MFE
    def _sort_key(e):
        m = e["m"]
        cagr = m["cagr"]  if m["cagr"]    is not None else -999
        mfe  = m["avg_mfe"] if m["avg_mfe"] is not None else 0
        return (-cagr, -mfe)

    sig = sorted([e for e in edges if e["p"] is not None and e["p"] <= 0.25],
                 key=_sort_key)[:20]

    base_cagr = base_m["cagr"]  if base_m["cagr"]    is not None else 0
    base_mfe  = base_m["avg_mfe"] if base_m["avg_mfe"] is not None else 0

    rows = []
    for e in sig:
        m     = e["m"]
        deg_s = ["—","فردي","زوجي","ثلاثي"][min(e["deg"],3)]
        p_s   = f"{e['p']:.3f}"
        cagr_lift = f"{m['cagr']/base_cagr:.2f}×"  if (m["cagr"]  and base_cagr) else "—"
        mfe_s     = f"{m['avg_mfe']:.1%}"           if m["avg_mfe"]  is not None else "—"
        pf_s      = f"{m['pf']:.2f}"                if m["pf"]       is not None else "—"
        cal_s     = f"{m['calmar']:.2f}"             if m["calmar"]   is not None else "—"
        wr_s      = f'{m["win_rate"]:.0%}' \
                    if m["win_rate"] is not None else '—'
        ret_s     = _retention_badge(m["n"], _base_n)
        opt       = _opt_score(m, base_m, m["n"], _base_n, m.get("n_stocks", 0))
        opt_cls   = "b-high" if opt >= 60 else ("b-low" if opt < 35 else "b-med")
        rows.append([e["combo"], deg_s, str(m["n"]), ret_s,
                     cagr_lift, pf_s, mfe_s, cal_s, p_s, wr_s,
                     f'<span class="badge {opt_cls}">{opt:.0f}</span>'])

    cagr_s = f"{base_m['cagr']:.0%}" if base_m["cagr"] is not None else "—"
    mfe_bs = f"{base_mfe:.1%}"

    html = f"""
<div class="section">
  <h2>المرحلة 5: اكتشاف الحافة <span class="phase-badge">Edge Discovery</span></h2>
  {PHILOSOPHY_NOTE}
  <div class="kpi-row">
    {_kpi(cagr_s,        "CAGR قاعدي")}
    {_kpi(mfe_bs,        "Avg MFE قاعدي")}
    {_kpi(str(_base_n),  "إجمالي الإشارات")}
    {_kpi(str(len(sig)), "حافة ذات دلالة")}
  </div>
  <p style="font-size:.84em;color:#555">
    مرتَّب: CAGR Lift ← ثم Avg MFE. فلترة: p ≤ 0.25 و N ≥ {MIN_N_EDGE}.
    <strong>Retention</strong>: نسبة الإشارات التي تُحقق هذا الشرط — الحافات ذات الاحتفاظ العالي أكثر عملية.
    <strong>OPT Score</strong>: درجة مركّبة تُعاقِب الاحتفاظ المنخفض.
  </p>
  {_tbl(
    ["التركيبة","نوع","N","Retention","CAGR Lift","PF","Avg MFE","Calmar","p-val","Win Rate","OPT"],
    rows
  ) if rows else '<p class="warn">لا حوافّ ذات دلالة</p>'}
</div>"""
    return html


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 6 — Cluster Profiles
# ══════════════════════════════════════════════════════════════════════════════

def phase6_clusters(df: pd.DataFrame) -> str:
    if not SKLEARN_OK or df.empty or "mfe_20d" not in df.columns:
        return ('<div class="section"><h2>المرحلة 6: ملامح التجميع</h2>'
                '<p class="warn">sklearn غير متوفر أو بيانات غير كافية</p></div>')

    feat_cols = [c for c in R_COLS
                 if c in df.columns and df[c].notna().sum() >= MIN_N_CLUSTER]
    if not feat_cols:
        return ('<div class="section"><h2>المرحلة 6: ملامح التجميع</h2>'
                '<p class="warn">مكونات غير كافية</p></div>')

    sub = df[feat_cols + ["mfe_20d","mae_20d","bq_score","r20d"]].dropna(subset=feat_cols)
    if len(sub) < 9:
        return (f'<div class="section"><h2>المرحلة 6: ملامح التجميع</h2>'
                f'<p class="warn">إشارات ({len(sub)}) أقل من الحد الأدنى</p></div>')

    scaler = StandardScaler()
    X_s    = scaler.fit_transform(sub[feat_cols])
    k      = min(3, len(sub) // MIN_N_CLUSTER)
    if k < 2:
        return ('<div class="section"><h2>المرحلة 6: ملامح التجميع</h2>'
                '<p class="warn">إشارات غير كافية للتجميع</p></div>')

    km     = KMeans(n_clusters=k, random_state=42, n_init=10)
    sub    = sub.copy()
    sub["cl"] = km.fit_predict(X_s)

    # ترتيب المجموعات حسب CAGR (وليس Win Rate)
    cl_cagr = {}
    for ci in range(k):
        m = _metrics(sub[sub["cl"] == ci])
        cl_cagr[ci] = m["cagr"] if m["cagr"] is not None else -999

    ranked   = sorted(cl_cagr.keys(), key=lambda x: -cl_cagr[x])
    tag_map  = {0: "قاع قوي 🟢", 1: "متوسط 🟡", 2: "ضعيف 🔴"}
    cl_label = {ci: tag_map.get(rank, f"مجموعة {rank}") for rank, ci in enumerate(ranked)}

    rows = []
    for ci in ranked:
        grp = sub[sub["cl"] == ci]
        m   = _metrics(grp)
        cells = _fmt_metrics(m)
        top_r = max(feat_cols, key=lambda c: grp[c].mean())
        rows.append([cl_label[ci]] + cells + [R_LABELS.get(top_r, top_r)])

    detail_rows = []
    for ci in ranked:
        grp  = sub[sub["cl"] == ci]
        vals = [cl_label[ci]] + [
            f"{grp[c].mean():.1f}" if c in grp.columns else "—"
            for c in feat_cols
        ]
        detail_rows.append(vals)

    html = f"""
<div class="section">
  <h2>المرحلة 6: ملامح التجميع <span class="phase-badge">Cluster Profiles</span></h2>
  {PHILOSOPHY_NOTE}
  <p style="font-size:.85em;color:#555">
    KMeans (k={k}) — مرتَّب حسب CAGR تنازلياً.
    Win Rate مُدرَج كمقياس كامل — الترتيب يبدأ من CAGR.
  </p>
  {_tbl(
    ["المجموعة"] + METRICS_HEADERS + ["أقوى مكوّن"],
    rows
  )}
  <h3 style="color:#1a3c5e;margin:14px 0 6px">متوسط المكونات لكل مجموعة</h3>
  {_tbl(["المجموعة"] + [R_LABELS.get(c,c) for c in feat_cols], detail_rows)}
</div>"""
    return html


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 7 — Final Summary
# ══════════════════════════════════════════════════════════════════════════════

def phase7_summary(dq_score: float, feat_scores: dict, df: pd.DataFrame) -> str:
    n  = len(df) if df is not None else 0
    bm = _metrics(df) if df is not None and not df.empty else {}

    dq_cls = ("b-high" if dq_score >= 70 else ("b-low" if dq_score < 40 else "b-med"))
    dq_lbl = ("جيدة" if dq_score >= 70 else ("ضعيفة" if dq_score < 40 else "متوسطة"))

    cagr_s  = f"{bm['cagr']:.0%}"    if bm.get("cagr")    is not None else "—"
    pf_s    = f"{bm['pf']:.2f}"      if bm.get("pf")      is not None else "—"
    mfe_s   = f"{bm['avg_mfe']:.1%}" if bm.get("avg_mfe") is not None else "—"
    cal_s   = f"{bm['calmar']:.2f}"  if bm.get("calmar")  is not None else "—"
    dd_s    = f"{bm['max_dd']:.1%}"  if bm.get("max_dd")  is not None else "—"
    wr_s    = f"{bm['win_rate']:.0%}" if bm.get("win_rate") is not None else "—"

    if feat_scores:
        ranked  = sorted(feat_scores.items(), key=lambda x: -x[1])
        top3    = ranked[:3]
        bottom3 = ranked[-3:][::-1]
    else:
        top3 = bottom3 = []

    top_html = "".join(
        f"<li><strong>{R_LABELS.get(c,c)}</strong> — درجة {s:.0f}/100</li>"
        for c, s in top3
    )
    bot_html = "".join(
        f"<li><strong>{R_LABELS.get(c,c)}</strong> — درجة {s:.0f}/100</li>"
        for c, s in bottom3
    )

    recs = []
    if n < 60:
        recs.append("جمع إشارات إضافية لتحسين دقة التحليل الإحصائي")
    if feat_scores:
        low_feats  = [R_LABELS.get(c,c) for c, s in feat_scores.items() if s < 30]
        high_feats = [R_LABELS.get(c,c) for c, s in feat_scores.items() if s > 70]
        if low_feats:
            recs.append(f"مكونات ذات ارتباط ضعيف بـ CAGR/MFE: {', '.join(low_feats[:3])}")
        if high_feats:
            recs.append(f"مكونات ذات قيمة تنبؤية عالية للعائد: {', '.join(high_feats[:3])}")

    if bm.get("pf") is not None and bm["pf"] < 1.0:
        recs.append("⚠ Profit Factor < 1 — الخسائر تتجاوز الأرباح في العينة الحالية")
    if bm.get("calmar") is not None and bm["calmar"] < 1.0:
        recs.append("⚠ Calmar < 1 — مخاطرة عالية نسبياً مقارنة بالعائد")

    rec_html = "".join(f"<li>{r}</li>" for r in recs) if recs else "<li>لا توصيات استثنائية</li>"
    sample_note = (
        "✓ حجم العينة كافٍ للتحليل الموثوق" if n >= 60 else
        f"⚠ حجم العينة ({n}) صغير — زِد الإشارات لمزيد من الدقة"
    )

    html = f"""
<div class="section">
  <h2>المرحلة 7: الملخص النهائي <span class="phase-badge">Final Summary</span></h2>
  {PHILOSOPHY_NOTE}
  <div class="kpi-row">
    {_kpi(f'<span class="badge {dq_cls}">{dq_lbl}</span>', "جودة البيانات")}
    {_kpi(str(n),    "إشارات ناضجة")}
    {_kpi(cagr_s,   "CAGR الكلي")}
    {_kpi(pf_s,     "Profit Factor")}
    {_kpi(mfe_s,    "Avg MFE")}
    {_kpi(cal_s,    "Calmar Ratio")}
  </div>
  <div class="kpi-row">
    {_kpi(dd_s,  "Max DD")}
    {_kpi(f'{wr_s}', "Win Rate")}
  </div>
  <div class="rec-box">
    <h3>أقوى المكونات (CAGR/PF/MFE)</h3>
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
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def build_report() -> str:
    print("[QuantReport] Loading data…")
    df     = _load_data()
    df_all = _load_all_signals()
    n_mat  = len(df)
    print(f"[QuantReport] {len(df_all)} total signals, {n_mat} mature")

    sections = []

    print("[QuantReport] Phase 0: Operational Constraints…")
    s0, base_n = phase0_constraints(df, df_all)
    sections.append(s0)

    print("[QuantReport] Phase 1: Data Audit…")
    s1, dq_score = phase1_data_audit(df, df_all)
    sections.append(s1)

    print("[QuantReport] Phase 2: Feature Consistency…")
    s2, feat_scores = phase2_feature_consistency(df)
    sections.append(s2)

    print("[QuantReport] Phase 3: Weight Validation…")
    sections.append(phase3_weight_validation(df))

    print("[QuantReport] Phase 4: Gate Analysis…")
    sections.append(phase4_gate_analysis(df, base_n=base_n))

    print("[QuantReport] Phase 5: Edge Discovery…")
    sections.append(phase5_edge_discovery(df, base_n=base_n))

    print("[QuantReport] Phase 6: Cluster Profiles…")
    sections.append(phase6_clusters(df))

    print("[QuantReport] Phase 7: Final Summary…")
    sections.append(phase7_summary(dq_score, feat_scores, df))

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
  {"".join(sections)}
</div>
</body>
</html>"""
    return html


def main():
    html     = build_report()
    out_path = f"reports/quant_research_report_{TODAY}.html"
    os.makedirs("reports", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[QuantReport] Written → {out_path}")


if __name__ == "__main__":
    main()
