"""
Research Report
===============
يُولّد تقرير HTML مُفصَّل ويُرسله بالبريد الإلكتروني.

التشغيل الأسبوعي التلقائي: يُستدعى من main.py.
التشغيل اليدوي:
    python research_report.py                  # يُولّد ويُرسل
    python research_report.py --no-email       # يُولّد فقط
    python research_report.py --force          # يتجاهل الـ 7 أيام cooldown

التقرير يقيس جودة الـ bottom بـ:
  - MFE (أقصى ربح غير محقق) — المقياس الأول
  - BQ Score (0-100) — التقييم الشامل
  - MAE (أقصى تراجع) — التقييم الثاني
ولا يستخدم مفاهيم win/loss أو عائدات قصيرة الأجل.
"""

import json
import os
import smtplib
import sys
from datetime import date, datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from signal_db import (
    DB_PATH, get_stats, get_mature_signals, get_active_signals,
    get_last_report_date, log_report_sent, init_db,
)
from research_engine import run_research, MIN_SAMPLES, MIN_PER_STOCK_ML, TRAIN_SPLIT_PCT

# ── Email Config ───────────────────────────────────────────────────────────────
EMAIL_FROM    = os.getenv("REPORT_EMAIL_FROM", "")
EMAIL_TO      = os.getenv("REPORT_EMAIL_TO",   "shady.gad.mb@gmail.com")
EMAIL_PASS    = os.getenv("REPORT_EMAIL_PASS",  "")
SMTP_HOST     = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))

WEEKLY_COOLDOWN_DAYS = 7
REPORT_JSON_PATH     = "research_results.json"


# ── CSS & Layout ───────────────────────────────────────────────────────────────

_CSS = """
<style>
  body { font-family: 'Segoe UI', Arial, sans-serif; background:#f0f2f5;
         color:#222; direction:rtl; margin:0; }
  .container { max-width:900px; margin:20px auto; background:#fff;
               border-radius:10px; box-shadow:0 2px 12px #0002;
               overflow:hidden; }
  .header { background:linear-gradient(135deg,#1a3c5e,#2a6496);
            color:#fff; padding:28px 30px; }
  .header h1 { margin:0; font-size:1.6em; }
  .header p  { margin:6px 0 0; opacity:.8; font-size:.9em; }
  .section  { padding:20px 30px; border-bottom:1px solid #eee; }
  .section h2 { color:#1a3c5e; margin-top:0; font-size:1.15em;
                border-right:4px solid #2a6496; padding-right:10px; }
  .kpi-row  { display:flex; flex-wrap:wrap; gap:12px; margin:10px 0; }
  .kpi      { flex:1; min-width:130px; background:#f7f9fb;
              border-radius:8px; padding:14px 16px; text-align:center; }
  .kpi .val { font-size:1.9em; font-weight:700; color:#1a3c5e; }
  .kpi .lbl { font-size:.78em; color:#666; margin-top:4px; }
  .tbl-wrap { overflow-x:auto; -webkit-overflow-scrolling:touch; }
  table     { width:100%; border-collapse:collapse; font-size:.88em; }
  th        { background:#1a3c5e; color:#fff; padding:8px 10px;
              text-align:right; white-space:nowrap; }
  td        { padding:7px 10px; border-bottom:1px solid #eee; }
  tr:nth-child(even) td { background:#f9f9f9; }
  .badge    { display:inline-block; padding:2px 8px; border-radius:12px;
              font-size:.78em; font-weight:600; }
  .b-high   { background:#d4edda; color:#155724; }
  .b-med    { background:#fff3cd; color:#856404; }
  .b-low    { background:#f8d7da; color:#721c24; }
  .warn     { background:#fff3cd; border:1px solid #ffc107;
              border-radius:6px; padding:10px 14px; margin:8px 0;
              font-size:.88em; color:#856404; }
  .rec-box  { background:#e8f4f8; border:1px solid #bee5eb;
              border-radius:8px; padding:14px 18px; margin:10px 0; }
  .rec-box h3 { margin:0 0 8px; color:#0c5460; font-size:1em; }
  .footer   { background:#f7f9fb; padding:14px 30px;
              font-size:.8em; color:#888; text-align:center; }
  @media(max-width:640px){
    .container { margin:0; border-radius:0; }
    .header { padding:18px 16px; }
    .header h1 { font-size:1.25em; }
    .section { padding:14px 12px; }
    .kpi { min-width:90px; padding:10px 8px; }
    .kpi .val { font-size:1.4em; }
    table { font-size:.78em; }
    th, td { padding:6px 7px; }
  }
</style>
"""


# ── Formatting Helpers ─────────────────────────────────────────────────────────

def _pct(v, decimals=1):
    if v is None: return "—"
    return f"{v*100:+.{decimals}f}%"

def _f(v, decimals=2):
    if v is None: return "—"
    return f"{v:.{decimals}f}"

def _bq_badge(score):
    if score is None: return "—"
    cls  = "b-high" if score >= 65 else ("b-med" if score >= 40 else "b-low")
    return f'<span class="badge {cls}">{score:.1f}</span>'

def _mfe_badge(mfe):
    if mfe is None: return "—"
    cls = "b-high" if mfe >= 0.15 else ("b-med" if mfe >= 0.07 else "b-low")
    return f'<span class="badge {cls}">{mfe*100:.1f}%</span>'


# ── Section Builders ───────────────────────────────────────────────────────────

def _build_kpi_section(stats: dict, res: dict) -> str:
    meta   = res.get("meta", {})
    n_ml   = meta.get("n_signals",  0)   # إشارات الدخول الفعلي (للـ ML)
    n_wait = meta.get("n_wait",     0)   # Wait (مراقبة فقط)
    mfe_m  = meta.get("mfe_mean")
    bq_m   = meta.get("bq_mean")
    mae_m  = meta.get("mae_mean")

    def kpi(val, lbl):
        return f'<div class="kpi"><div class="val">{val}</div><div class="lbl">{lbl}</div></div>'

    cards = [
        kpi(stats.get("total_signals", 0),    "إجمالي الإشارات"),
        kpi(n_ml,                              "إشارات ML (دخول فعلي)"),
        kpi(n_wait,                            "إشارات Wait (مراقبة)"),
        kpi(stats.get("tracking_records", 0), "سجلات المتابعة"),
        kpi(f"{mfe_m*100:.1f}%" if mfe_m else "—", "متوسط MFE"),
        kpi(f"{bq_m:.1f}" if bq_m else "—",   "متوسط BQ Score"),
        kpi(f"{mae_m*100:.1f}%" if mae_m else "—", "متوسط MAE"),
    ]
    return (
        '<div class="section">'
        '<h2>ملخص المنظومة</h2>'
        f'<div class="kpi-row">{"".join(cards)}</div>'
        '</div>'
    )


def _build_correlation_section(res: dict) -> str:
    corr = res.get("correlation", {})
    if not corr:
        return ""

    rows_html = ""
    # نُرتّب حسب ارتباط MFE
    mfe_corr = corr.get("mfe_20d", {})
    bq_corr  = corr.get("bq_score", {})

    all_features = list(dict.fromkeys(list(mfe_corr.keys()) + list(bq_corr.keys())))
    for feat in all_features[:20]:
        mfe_v = mfe_corr.get(feat)
        bq_v  = bq_corr.get(feat)
        rows_html += (
            f"<tr><td><code>{feat}</code></td>"
            f"<td>{_f(mfe_v, 3)}</td>"
            f"<td>{_f(bq_v,  3)}</td></tr>"
        )

    return (
        '<div class="section">'
        '<h2>ارتباط المتغيرات مع جودة الـ Bottom</h2>'
        '<p style="font-size:.85em;color:#666">Spearman — موجب = كلما زاد المتغير زادت جودة الـ bottom</p>'
        '<table><thead><tr>'
        '<th>المتغير</th><th>↔ MFE</th><th>↔ BQ Score</th>'
        '</tr></thead><tbody>'
        f'{rows_html}'
        '</tbody></table>'
        '</div>'
    )


def _build_model_section(res: dict) -> str:
    models = []
    for key, label in [("rf_mfe", "RF→MFE"), ("rf_bq", "RF→BQ"),
                        ("gbm_mfe", "GBM→MFE"), ("gbm_bq", "GBM→BQ")]:
        m = res.get(key)
        if not m:
            continue
        imp = m.get("importance", {})
        top5 = sorted(imp.items(), key=lambda x: x[1], reverse=True)[:5]
        top5_str = ", ".join(f"{k}({v:.3f})" for k, v in top5)
        models.append(
            f"<tr><td>{label}</td><td>{m['r2']}</td>"
            f"<td>{m['n_train']}</td><td>{m['n_test']}</td>"
            f"<td style='font-size:.82em'>{top5_str}</td></tr>"
        )

    if not models:
        return ""

    return (
        '<div class="section">'
        '<h2>نماذج ML — أهم المتغيرات (Target: MFE و BQ Score)</h2>'
        '<table><thead><tr>'
        '<th>النموذج</th><th>R²</th><th>تدريب</th><th>اختبار</th><th>أهم 5 متغيرات</th>'
        '</tr></thead><tbody>'
        f'{"".join(models)}'
        '</tbody></table>'
        '</div>'
    )


def _build_weight_suggestions_section(res: dict) -> str:
    ws = res.get("weight_suggestions", {})
    if not ws:
        return ""

    rows = ""
    has_change = False
    for comp, v in ws.items():
        cur  = v["current"]
        sug  = v["suggested"]
        chg  = v["change"]
        if chg != 0:
            has_change = True
        chg_str = f'<span style="color:{"green" if chg>0 else "red"}">{chg:+d}</span>'
        rows += (
            f"<tr><td><code>{comp}</code></td>"
            f"<td>{cur}</td><td>{sug}</td><td>{chg_str}</td>"
            f"<td style='font-size:.82em'>{v['reason']}</td></tr>"
        )

    if not has_change:
        intro = '<p style="color:#155724;font-weight:600">النماذج لا تقترح تغييرات في الأوزان الحالية.</p>'
    else:
        intro = (
            '<div class="warn">⚠ هذه توصيات بحثية فقط — يجب مراجعتها يدوياً قبل أي تغيير. '
            'النظام الحالي لن يتغير تلقائياً.</div>'
        )

    return (
        '<div class="section">'
        '<h2>توصيات تعديل الأوزان</h2>'
        f'{intro}'
        '<table><thead><tr>'
        '<th>المكوّن</th><th>الحالي</th><th>المقترح</th><th>التغيير</th><th>السبب</th>'
        '</tr></thead><tbody>'
        f'{rows}'
        '</tbody></table>'
        '</div>'
    )


def _build_segment_section(res: dict) -> str:
    seg = res.get("segment_analysis", {})
    if not seg:
        return ""

    html = '<div class="section"><h2>تحليل قطاعي وبيئي</h2>'

    # ── Score Buckets ──────────────────────────────────────────────────
    buckets = seg.get("by_score_bucket", {})
    if buckets:
        html += "<h3 style='color:#2a6496'>أداء حسب نطاق الـ Score</h3>"
        html += ("<table><thead><tr><th>نطاق Score</th><th>عدد</th>"
                 "<th>MFE (متوسط)</th><th>BQ (متوسط)</th><th>MAE (متوسط)</th></tr>"
                 "</thead><tbody>")
        for bucket, v in sorted(buckets.items()):
            n = v.get("n", 0)
            html += (
                f"<tr><td>{bucket}</td><td>{n}</td>"
                f"<td>{_mfe_badge(v.get('mfe_20d_mean'))}</td>"
                f"<td>{_bq_badge(v.get('bq_score_mean'))}</td>"
                f"<td>{_pct(v.get('mae_20d_mean'))}</td></tr>"
            )
        html += "</tbody></table>"

    # ── Market Regime ──────────────────────────────────────────────────
    mr = seg.get("by_market_regime", {})
    if mr:
        html += "<h3 style='color:#2a6496'>أداء حسب ظروف السوق</h3>"
        html += ("<table><thead><tr><th>حالة السوق</th><th>عدد</th>"
                 "<th>MFE (متوسط)</th><th>BQ (متوسط)</th></tr>"
                 "</thead><tbody>")
        for regime, v in mr.items():
            html += (
                f"<tr><td>{regime}</td><td>{v.get('n')}</td>"
                f"<td>{_mfe_badge(v.get('mfe_20d_mean'))}</td>"
                f"<td>{_bq_badge(v.get('bq_score_mean'))}</td></tr>"
            )
        html += "</tbody></table>"

    # ── Context ────────────────────────────────────────────────────────
    ctx = seg.get("by_context", {})
    if ctx:
        html += "<h3 style='color:#2a6496'>السياق الماكرو</h3>"
        html += ("<table><thead><tr><th>الظرف</th><th>عدد</th>"
                 "<th>MFE (متوسط)</th><th>BQ (متوسط)</th></tr>"
                 "</thead><tbody>")
        for ctx_key, v in ctx.items():
            html += (
                f"<tr><td>{ctx_key}</td><td>{v.get('n')}</td>"
                f"<td>{_mfe_badge(v.get('mfe_20d_mean'))}</td>"
                f"<td>{_bq_badge(v.get('bq_score_mean'))}</td></tr>"
            )
        html += "</tbody></table>"

    html += "</div>"
    return html


def _build_active_signals_section(db_path: str) -> str:
    signals = get_active_signals(max_days=90, db_path=db_path)
    if not signals:
        return ""

    rows = ""
    for s in sorted(signals, key=lambda x: x["signal_date"], reverse=True)[:30]:
        rows += (
            f"<tr><td>{s['symbol']}</td>"
            f"<td>{s['signal_date']}</td>"
            f"<td>{s.get('signal_type','')}</td>"
            f"<td>{s.get('raw_score','')}</td>"
            f"<td>{_f(s.get('price'))}</td>"
            f"<td>{s.get('sector','')}</td></tr>"
        )

    return (
        '<div class="section">'
        '<h2>الإشارات النشطة (آخر 90 يوم)</h2>'
        '<table><thead><tr>'
        '<th>السهم</th><th>التاريخ</th><th>الإشارة</th>'
        '<th>Score</th><th>سعر الدخول</th><th>القطاع</th>'
        '</tr></thead><tbody>'
        f'{rows}'
        '</tbody></table>'
        '</div>'
    )


def _build_mature_signals_section(db_path: str) -> str:
    signals = get_mature_signals(db_path=db_path)
    if not signals:
        return ""

    rows = ""
    for s in sorted(signals, key=lambda x: x["signal_date"], reverse=True)[:50]:
        rows += (
            f"<tr><td>{s['symbol']}</td>"
            f"<td>{s['signal_date']}</td>"
            f"<td>{_mfe_badge(s.get('mfe_20d'))}</td>"
            f"<td>{_bq_badge(s.get('bq_score'))}</td>"
            f"<td>{_pct(s.get('mae_20d'))}</td>"
            f"<td>{_pct(s.get('r20d'))}</td>"
            f"<td>{s.get('raw_score','')}</td></tr>"
        )

    return (
        '<div class="section">'
        '<h2>الإشارات الناضجة — قاعدة التعلم</h2>'
        '<table><thead><tr>'
        '<th>السهم</th><th>التاريخ</th><th>MFE</th><th>BQ Score</th>'
        '<th>MAE</th><th>R20d</th><th>Score</th>'
        '</tr></thead><tbody>'
        f'{rows}'
        '</tbody></table>'
        '</div>'
    )


def _build_pattern_section(res: dict) -> str:
    pat = res.get("pattern_analysis", {})
    if not pat or not pat.get("n_used"):
        return ""

    n = pat["n_used"]
    html = (
        '<div class="section">'
        '<h2>تحليل Pattern Recognition Engine</h2>'
        f'<p style="font-size:.85em;color:#666">مبني على {n} إشارة ناضجة — '
        'Target: MFE و BQ Score (لا win/loss)</p>'
    )

    # ── ارتباط المؤشرات ──────────────────────────────────────────────────
    ind_corr = pat.get("indicator_correlations", {})
    dir_val  = pat.get("direction_validation",   {})
    if ind_corr:
        html += (
            '<h3 style="color:#2a6496">ارتباط كل مؤشر مع MFE و BQ Score</h3>'
            '<table><thead><tr>'
            '<th>المؤشر</th><th>↔ MFE</th><th>↔ BQ</th>'
            '<th>الاتجاه المتوقع</th><th>حالة التحقق</th>'
            '</tr></thead><tbody>'
        )
        for col, v in ind_corr.items():
            dv = dir_val.get(col, {})
            verdict = dv.get("verdict", "—")
            color = ("green" if verdict == "مؤكَّد"
                     else "orange" if "جزئياً" in verdict
                     else "red" if "تعارض" in verdict
                     else "#888")
            html += (
                f"<tr><td><code>{col}</code></td>"
                f"<td>{_f(v['corr_mfe'], 3)}</td>"
                f"<td>{_f(v['corr_bq'],  3)}</td>"
                f"<td>{dv.get('expected','—')}</td>"
                f"<td style='color:{color};font-weight:600'>{verdict}</td></tr>"
            )
        html += "</tbody></table>"

    # ── Pattern Score Buckets ─────────────────────────────────────────────
    ps_buckets = pat.get("pattern_score_buckets", {})
    if ps_buckets:
        html += '<h3 style="color:#2a6496">أداء حسب نطاق Pattern Score</h3>'
        html += (
            '<table><thead><tr>'
            '<th>Pattern Score</th><th>عدد</th>'
            '<th>MFE (متوسط)</th><th>BQ (متوسط)</th><th>MAE (متوسط)</th>'
            '</tr></thead><tbody>'
        )
        for bucket, v in sorted(ps_buckets.items()):
            html += (
                f"<tr><td>{bucket}</td><td>{v.get('n',0)}</td>"
                f"<td>{_mfe_badge(v.get('mfe_20d_mean'))}</td>"
                f"<td>{_bq_badge(v.get('bq_score_mean'))}</td>"
                f"<td>{_pct(v.get('mae_20d_mean'))}</td></tr>"
            )
        html += "</tbody></table>"

    # ── Effective Score Buckets ───────────────────────────────────────────
    eff_buckets = pat.get("effective_score_buckets", {})
    if eff_buckets:
        html += '<h3 style="color:#2a6496">أداء حسب نطاق Effective Score</h3>'
        html += (
            '<table><thead><tr>'
            '<th>Effective Score</th><th>عدد</th>'
            '<th>MFE (متوسط)</th><th>BQ (متوسط)</th>'
            '</tr></thead><tbody>'
        )
        for bucket, v in sorted(eff_buckets.items()):
            html += (
                f"<tr><td>{bucket}</td><td>{v.get('n',0)}</td>"
                f"<td>{_mfe_badge(v.get('mfe_20d_mean'))}</td>"
                f"<td>{_bq_badge(v.get('bq_score_mean'))}</td></tr>"
            )
        html += "</tbody></table>"

    # ── Combined SMC + Pattern ─────────────────────────────────────────────
    combined = pat.get("combined_smc_pattern", {})
    if combined:
        labels_ar = {
            "high_smc_high_pattern": "SMC ≥60 + Pattern ≥50",
            "high_smc_low_pattern":  "SMC ≥60 + Pattern <50",
            "low_smc_high_pattern":  "SMC <60  + Pattern ≥50",
            "low_smc_low_pattern":   "كلاهما منخفض",
        }
        html += (
            '<h3 style="color:#2a6496">SMC Score + Pattern Score مجتمعَين</h3>'
            '<p style="font-size:.83em;color:#666">هل Pattern يضيف قيمة فوق SMC وحده؟</p>'
            '<table><thead><tr>'
            '<th>الحالة</th><th>عدد</th>'
            '<th>MFE (متوسط)</th><th>BQ (متوسط)</th><th>MAE (متوسط)</th>'
            '</tr></thead><tbody>'
        )
        for key, v in combined.items():
            html += (
                f"<tr><td>{labels_ar.get(key, key)}</td><td>{v.get('n',0)}</td>"
                f"<td>{_mfe_badge(v.get('mfe_20d_mean'))}</td>"
                f"<td>{_bq_badge(v.get('bq_score_mean'))}</td>"
                f"<td>{_pct(v.get('mae_20d_mean'))}</td></tr>"
            )
        html += "</tbody></table>"

    # ── Entry Zone Analysis ───────────────────────────────────────────────
    zone_res = pat.get("entry_zone_analysis", {})
    if zone_res:
        zone_labels = {
            "z1": "Z1 — المنطقة الأولى (أقرب للسعر)",
            "z2": "Z2 — المنطقة الثانية",
            "z3": "Z3 — الأعمق (أكثر خصماً)",
        }
        html += (
            '<h3 style="color:#2a6496">أداء حسب منطقة الدخول</h3>'
            '<table><thead><tr>'
            '<th>المنطقة</th><th>عدد</th>'
            '<th>MFE (متوسط)</th><th>BQ (متوسط)</th><th>MAE (متوسط)</th>'
            '</tr></thead><tbody>'
        )
        for zone, v in zone_res.items():
            html += (
                f"<tr><td>{zone_labels.get(zone,zone)}</td><td>{v.get('n',0)}</td>"
                f"<td>{_mfe_badge(v.get('mfe_20d_mean'))}</td>"
                f"<td>{_bq_badge(v.get('bq_score_mean'))}</td>"
                f"<td>{_pct(v.get('mae_20d_mean'))}</td></tr>"
            )
        html += "</tbody></table>"

    # ── Weight Suggestions ────────────────────────────────────────────────
    ws = pat.get("indicator_weight_suggestions", {})
    if ws:
        has_change = any(abs(v.get("change", 0)) > 0.005 for v in ws.values())
        html += '<h3 style="color:#2a6496">اقتراح أوزان Pattern Engine (مبنية على MFE)</h3>'
        if has_change:
            html += (
                '<div class="warn">⚠ الأوزان الحالية محسوبة من AUC(win/loss). '
                'الأوزان المقترحة مبنية على MFE و BQ Score — أنسب لاستراتيجية الـ bottom fishing. '
                'تحتاج مراجعة يدوية قبل التطبيق في <code>pattern_engine.py</code></div>'
                '<table><thead><tr>'
                '<th>المؤشر</th><th>الوزن الحالي</th><th>الوزن المقترح</th><th>التغيير</th><th>قوة الارتباط</th>'
                '</tr></thead><tbody>'
            )
            for key, v in sorted(ws.items(), key=lambda x: -abs(x[1]["change"])):
                chg   = v["change"]
                color = "green" if chg > 0 else "red"
                html += (
                    f"<tr><td><code>{key}</code></td>"
                    f"<td>{v['current']:.4f}</td>"
                    f"<td>{v['suggested']:.4f}</td>"
                    f"<td style='color:{color};font-weight:600'>{chg:+.4f}</td>"
                    f"<td>{v['combined_corr']:.4f}</td></tr>"
                )
            html += "</tbody></table>"
        else:
            html += '<p style="color:#155724;font-weight:600">أوزان Pattern Engine تبدو مناسبة — لا تغييرات ذات أهمية مقترحة.</p>'

    html += "</div>"
    return html


def _build_best_conditions_section(res: dict) -> str:
    bc = res.get("best_conditions", {})
    if not bc:
        return ""

    html = (
        '<div class="section">'
        '<h2>بصمة الـ Bottom المثالي — لكل سهم بشكل منفصل</h2>'
        '<p style="font-size:.85em;color:#666">'
        'مقارنة أفضل 25% إشارة بـ MFE (Top Quartile) مع باقي الإشارات — '
        'الهدف: اكتشاف الأنماط المشتركة اللي تسبق أفضل النتائج لكل سهم'
        '</p>'
    )

    for sym, data in sorted(bc.items()):
        n         = data["n"]
        n_top     = data["n_top"]
        mfe_t     = data["mfe_threshold"]
        conditions= data["conditions"]
        summary   = data.get("top5_summary", [])

        html += (
            f'<div class="rec-box">'
            f'<h3>{sym} — أفضل {n_top} من {n} إشارة (MFE ≥ {mfe_t*100:.1f}%)</h3>'
        )

        if summary:
            items = "".join(f"<li>{s}</li>" for s in summary)
            html += f'<p style="font-size:.85em;margin:4px 0 8px"><strong>أهم 5 شروط للـ top signals:</strong><ul style="margin:4px 0">{items}</ul></p>'

        if conditions:
            html += (
                '<table style="font-size:.82em"><thead><tr>'
                '<th>المتغير</th>'
                '<th>Top 25% (متوسط)</th>'
                '<th>باقي الإشارات</th>'
                '<th>الفرق</th>'
                '<th>Effect Size</th>'
                '</tr></thead><tbody>'
            )
            for feat, v in list(conditions.items())[:12]:
                diff     = v["diff"]
                eff      = v["effect_size"]
                d_color  = "green" if diff > 0 else "red"
                eff_label= "قوي" if abs(eff) >= 0.5 else ("متوسط" if abs(eff) >= 0.2 else "ضعيف")
                eff_color= "green" if abs(eff) >= 0.5 else ("orange" if abs(eff) >= 0.2 else "#888")
                html += (
                    f"<tr><td><code>{feat}</code></td>"
                    f"<td>{v['top_mean']:.4f}</td>"
                    f"<td>{v['bottom_mean']:.4f}</td>"
                    f"<td style='color:{d_color};font-weight:600'>{diff:+.4f}</td>"
                    f"<td style='color:{eff_color}'>{eff:+.3f} ({eff_label})</td></tr>"
                )
            html += "</tbody></table>"

        html += "</div>"

    html += "</div>"
    return html


def _build_per_stock_ml_section(res: dict) -> str:
    ps_ml = res.get("per_stock_ml", {})
    if not ps_ml:
        return ""

    html = (
        '<div class="section">'
        '<h2>نماذج ML مستقلة — لكل سهم بشكل منفصل</h2>'
        '<p style="font-size:.85em;color:#666">'
        f'الحد الأدنى: {MIN_PER_STOCK_ML} إشارة ناضجة لكل سهم — '
        'Target: MFE (أولاً) و BQ Score (ثانياً) — تقسيم زمني 70/30%'
        '</p>'
    )

    for sym, data in sorted(ps_ml.items()):
        n        = data["n"]
        mfe_m    = data.get("mfe_model")
        bq_m     = data.get("bq_model")

        html += f'<div class="rec-box"><h3>{sym} — {n} إشارة ناضجة</h3>'

        for model_data, label, target_label in [
            (mfe_m, "MFE Model", "Target: MFE"),
            (bq_m,  "BQ Model",  "Target: BQ Score"),
        ]:
            if not model_data:
                continue
            if "error" in model_data:
                html += f'<p style="color:red">{label}: {model_data["error"]}</p>'
                continue

            r2       = model_data.get("r2", 0)
            n_train  = model_data.get("n_train", 0)
            n_test   = model_data.get("n_test",  0)
            top5     = model_data.get("top5", [])
            r2_color = "green" if r2 >= 0.10 else ("orange" if r2 >= 0.05 else "red")

            html += (
                f'<p style="margin:8px 0 4px"><strong>{label}</strong> ({target_label}) — '
                f'R²=<span style="color:{r2_color};font-weight:700">{r2}</span> '
                f'| train={n_train} | test={n_test}</p>'
            )
            if top5:
                top5_str = " | ".join(f"<code>{k}</code> ({v:.4f})" for k, v in top5)
                html += f'<p style="font-size:.83em;color:#555">أهم المتغيرات: {top5_str}</p>'

        html += "</div>"

    html += (
        '<div class="warn" style="margin-top:8px">'
        'R² منخفض (< 0.05) يعني البيانات مش كافية بعد للتنبؤ — '
        'النماذج ستتحسن تلقائياً مع تراكم الإشارات.'
        '</div>'
        '</div>'
    )
    return html


def _build_per_stock_pattern_section(res: dict) -> str:
    pat      = res.get("pattern_analysis", {})
    ps_data  = pat.get("per_stock_analysis", {})
    if not ps_data:
        return ""

    summary      = ps_data.get("mode_summary", {})
    global_list  = summary.get("global_mode",    [])
    ps_list      = summary.get("per_stock_mode",  [])
    per_stock    = ps_data.get("per_stock", {})
    min_req      = ps_data.get("min_required", 20)

    html = (
        '<div class="section">'
        '<h2>Pattern Engine — السلوك الهجين (Global vs Per-Stock)</h2>'
        f'<p style="font-size:.85em;color:#666">'
        f'الحد الأدنى لتفعيل التحليل per-stock: <strong>{min_req} إشارة ناضجة</strong> لكل سهم</p>'
    )

    # ── ملخص الأوضاع ─────────────────────────────────────────────────────
    n_global = len(global_list)
    n_ps     = len(ps_list)
    html += (
        '<div class="kpi-row">'
        f'<div class="kpi"><div class="val">{n_ps}</div>'
        f'<div class="lbl">أسهم في Per-Stock Mode</div></div>'
        f'<div class="kpi"><div class="val">{n_global}</div>'
        f'<div class="lbl">أسهم في Global Mode</div></div>'
        '</div>'
    )

    # ── أسهم في Global Mode (تحتاج مزيداً من البيانات) ──────────────────
    if global_list:
        html += '<h3 style="color:#856404">أسهم في Global Mode — بيانات غير كافية بعد</h3>'
        html += (
            '<table><thead><tr>'
            '<th>السهم</th><th>إشارات ناضجة</th><th>المطلوب إضافة</th>'
            '</tr></thead><tbody>'
        )
        for s in sorted(global_list, key=lambda x: -x["n"]):
            html += (
                f"<tr><td>{s['symbol']}</td><td>{s['n']}</td>"
                f"<td>{s['needed']} إشارة</td></tr>"
            )
        html += "</tbody></table>"

    # ── أسهم في Per-Stock Mode ────────────────────────────────────────────
    if per_stock:
        html += '<h3 style="color:#155724">أسهم في Per-Stock Mode — تحليل مستقل</h3>'

        for sym, sym_data in per_stock.items():
            n        = sym_data["n"]
            sym_corr = sym_data.get("indicator_correlations", {})
            sym_ws   = sym_data.get("weight_suggestions",     {})
            vs_glob  = sym_data.get("vs_global",              {})

            # هل يختلف سلوك هذا السهم بشكل ملحوظ عن الـ global؟
            diverging = [col for col, v in vs_glob.items() if v.get("diverges")]

            html += (
                f'<div class="rec-box">'
                f'<h3>{sym} — {n} إشارة ناضجة'
            )
            if diverging:
                html += f' | <span style="color:orange">⚠ سلوك مختلف عن Global في: {", ".join(diverging)}</span>'
            html += '</h3>'

            if sym_corr:
                html += (
                    '<table><thead><tr>'
                    '<th>المؤشر</th>'
                    '<th>Corr(MFE) — هذا السهم</th>'
                    '<th>Corr(MFE) — Global</th>'
                    '<th>الفرق</th>'
                    '</tr></thead><tbody>'
                )
                for col, sv in sym_corr.items():
                    gv      = vs_glob.get(col, {})
                    diff    = gv.get("difference", 0)
                    d_color = "orange" if abs(diff) > 0.15 else "#444"
                    html += (
                        f"<tr><td><code>{col}</code></td>"
                        f"<td>{_f(sv['corr_mfe'], 3)}</td>"
                        f"<td>{_f(gv.get('global_corr'), 3)}</td>"
                        f"<td style='color:{d_color};font-weight:600'>{diff:+.3f}</td></tr>"
                    )
                html += "</tbody></table>"

            # أوزان مقترحة خاصة بهذا السهم
            if sym_ws:
                has_chg = any(abs(v["change"]) > 0.005 for v in sym_ws.values())
                if has_chg:
                    html += '<p style="margin:8px 0 4px;font-size:.85em"><strong>أوزان مقترحة لهذا السهم:</strong></p>'
                    html += (
                        '<table style="font-size:.83em"><thead><tr>'
                        '<th>المؤشر</th><th>الحالي</th><th>المقترح</th><th>التغيير</th>'
                        '</tr></thead><tbody>'
                    )
                    for key, v in sorted(sym_ws.items(), key=lambda x: -abs(x[1]["change"])):
                        chg   = v["change"]
                        color = "green" if chg > 0 else "red"
                        html += (
                            f"<tr><td><code>{key}</code></td>"
                            f"<td>{v['current']:.4f}</td>"
                            f"<td>{v['suggested']:.4f}</td>"
                            f"<td style='color:{color};font-weight:600'>{chg:+.4f}</td></tr>"
                        )
                    html += "</tbody></table>"

            html += "</div>"  # rec-box

        html += (
            '<div class="warn" style="margin-top:12px">'
            '⚠ لتفعيل الأوزان per-stock في الماسح: '
            '<code>python research_engine.py --export-weights</code> '
            'ثم اضبط <code>FREEZE_WEIGHTS = False</code> في <code>pattern_engine.py</code>'
            '</div>'
        )

    html += "</div>"
    return html


def _build_mutual_info_section(res: dict) -> str:
    mi = res.get("mutual_information", {})
    if not mi:
        return ""

    html = (
        '<div class="section">'
        '<h2>Mutual Information — ارتباط غير خطي مع MFE و BQ</h2>'
        '<p style="font-size:.85em;color:#666">'
        'يقيس قوة الارتباط بأي شكل (خطي أو غير خطي) — '
        '1.0 = أقوى متغير، 0 = لا ارتباط. يُكمّل Spearman.</p>'
    )

    mfe_mi = mi.get("mfe_20d", {})
    bq_mi  = mi.get("bq_score", {})
    all_feats = list(dict.fromkeys(list(mfe_mi.keys()) + list(bq_mi.keys())))

    if all_feats:
        html += (
            '<table><thead><tr>'
            '<th>المتغير</th><th>MI ↔ MFE</th><th>MI ↔ BQ</th>'
            '</tr></thead><tbody>'
        )
        for feat in all_feats[:20]:
            mfe_v = mfe_mi.get(feat)
            bq_v  = bq_mi.get(feat)

            def _bar(v):
                if v is None: return "—"
                pct = min(int(v * 100), 100)
                color = "#1a6e3c" if v >= 0.5 else ("#2a6496" if v >= 0.25 else "#888")
                return (f'<div style="background:{color};height:10px;'
                        f'width:{pct}%;border-radius:3px;display:inline-block"></div> '
                        f'{v:.3f}')

            html += (
                f"<tr><td><code>{feat}</code></td>"
                f"<td>{_bar(mfe_v)}</td>"
                f"<td>{_bar(bq_v)}</td></tr>"
            )
        html += "</tbody></table>"

    html += "</div>"
    return html


def _build_probability_section(res: dict) -> str:
    pa = res.get("probability_analysis", {})
    if not pa or "error" in pa:
        err = pa.get("error", "") if pa else ""
        if err:
            return (
                '<div class="section">'
                f'<h2>Probability Score</h2>'
                f'<div class="warn">⚠ {err}</div>'
                '</div>'
            )
        return ""

    auc       = pa.get("auc", 0)
    n_train   = pa.get("n_train", 0)
    n_test    = pa.get("n_test", 0)
    base_wr   = pa.get("base_win_rate", 0)
    hc_n      = pa.get("high_conf_n", 0)
    hc_wins   = pa.get("high_conf_wins", 0)
    hc_prec   = pa.get("high_conf_precision", 0)
    win_thr   = pa.get("win_threshold_pct", 8)
    top5      = pa.get("top5_features", [])

    auc_color = "green" if auc >= 0.60 else ("orange" if auc >= 0.55 else "red")
    hc_color  = "green" if hc_prec >= 0.70 else ("orange" if hc_prec >= 0.55 else "red")

    def kpi(val, lbl):
        return f'<div class="kpi"><div class="val">{val}</div><div class="lbl">{lbl}</div></div>'

    html = (
        '<div class="section">'
        '<h2>Probability Score — احتمالية النجاح (MFE ≥ ' + f'{win_thr:.0f}%)</h2>'
        f'<p style="font-size:.85em;color:#666">'
        f'RandomForest Classifier — تقسيم زمني {int(TRAIN_SPLIT_PCT*100)}/{100-int(TRAIN_SPLIT_PCT*100)}% '
        f'| target: MFE ≥ {win_thr:.0f}%</p>'
        '<div class="kpi-row">'
        + kpi(f'<span style="color:{auc_color}">{auc}</span>', "AUC Score")
        + kpi(n_train,  "إشارات تدريب")
        + kpi(n_test,   "إشارات اختبار")
        + kpi(f"{base_wr:.1%}", "معدل الفوز الأساسي")
        + kpi(hc_n,     "إشارات عالية الثقة (≥65%)")
        + kpi(f'<span style="color:{hc_color}">{hc_prec:.1%}</span>',
              "دقة التنبؤات عالية الثقة")
        + '</div>'
    )

    if top5:
        top5_str = " | ".join(f"<code>{k}</code> ({v:.4f})" for k, v in top5)
        html += f'<p style="font-size:.85em;color:#555">أهم المتغيرات: {top5_str}</p>'

    auc_note = ""
    if auc < 0.55:
        auc_note = "AUC قريب من 0.5 يعني النموذج لا يتجاوز التخمين العشوائي — بيانات أكثر مطلوبة."
    elif auc >= 0.60:
        auc_note = "AUC ≥ 0.60 — النموذج يمتلك قدرة تنبؤية حقيقية. الإشارات عالية الثقة تستحق اهتماماً."

    if auc_note:
        html += f'<div class="warn">{auc_note}</div>'

    html += (
        '<div class="warn" style="background:#e8f4f8;border-color:#bee5eb">'
        'Probability Score هو مقياس بحثي فقط — لا يُعدّل الإشارات تلقائياً. '
        'استخدمه لترتيب الإشارات المتزامنة بناءً على احتمالية التحقق.'
        '</div>'
        '</div>'
    )
    return html


def _build_edge_discovery_section(res: dict) -> str:
    edges = res.get("edge_discovery", [])
    if not edges:
        return ""

    from edge_discovery import WIN_MFE_THRESHOLD

    html = (
        '<div class="section">'
        '<h2>Hidden Edge Discovery — أفضل مجموعات الشروط</h2>'
        f'<p style="font-size:.85em;color:#666">'
        f'اختبار إحصائي (binomtest) لمجموعات 1-3 شروط — '
        f'target: MFE ≥ {WIN_MFE_THRESHOLD*100:.0f}% | '
        f'مرتّبة بـ lift × log₂(n+1) / (1 + p×5)</p>'
        '<table><thead><tr>'
        '<th>القاعدة</th><th>N</th><th>فائزون</th>'
        '<th>Win Rate</th><th>Avg MFE</th><th>Avg BQ</th>'
        '<th>Lift</th><th>P-Value</th><th>Score</th>'
        '</tr></thead><tbody>'
    )

    for i, e in enumerate(edges):
        wr_pct   = f"{e['win_rate']*100:.1f}%"
        mfe_pct  = f"{e['avg_mfe']*100:.1f}%"
        bq_str   = f"{e['avg_bq']:.1f}" if e.get("avg_bq") is not None else "—"
        p_color  = "green" if e["p_value"] <= 0.05 else ("orange" if e["p_value"] <= 0.10 else "#888")
        lift_color = "green" if e["lift"] >= 1.5 else ("orange" if e["lift"] >= 1.2 else "#888")
        n_conds  = e.get("n_conditions", 1)
        cond_badge = f'<span class="badge b-high">{n_conds} شرط</span>' if n_conds > 1 else ""

        html += (
            f"<tr>"
            f"<td style='font-size:.82em'>{e['rule']} {cond_badge}</td>"
            f"<td>{e['n']}</td>"
            f"<td>{e['wins']}</td>"
            f"<td>{wr_pct}</td>"
            f"<td>{_mfe_badge(e['avg_mfe'])}</td>"
            f"<td>{bq_str}</td>"
            f"<td style='color:{lift_color};font-weight:600'>{e['lift']:.2f}x</td>"
            f"<td style='color:{p_color};font-weight:600'>{e['p_value']:.3f}</td>"
            f"<td>{e['score']:.2f}</td>"
            f"</tr>"
        )

    html += (
        '</tbody></table>'
        '<div class="warn" style="margin-top:8px">'
        '⚠ هذه قواعد بحثية مستخرجة من البيانات التاريخية — '
        'تحتاج تحقق forward-looking قبل الاعتماد عليها. '
        'p≤0.05 = دلالة إحصائية قوية، p≤0.10 = مشجّع، p>0.10 = استكشافي فقط.'
        '</div>'
        '</div>'
    )
    return html


def _build_distribution_section(res: dict) -> str:
    pd = res.get("pattern_discovery", {})
    if not pd:
        return ""
    mfe_dist_raw = pd.get("mfe_distribution", {})
    mae_dist_raw = pd.get("mae_distribution", {})
    if not mfe_dist_raw and not mae_dist_raw:
        return ""

    # mfe_distribution / mae_distribution have nested structure:
    # {"buckets": {bucket: count, ...}, "mean": float, "median": float, ...}
    def _extract(dist_raw):
        if isinstance(dist_raw.get("buckets"), dict):
            return dist_raw["buckets"], {k: v for k, v in dist_raw.items() if k != "buckets"}
        return dist_raw, {}

    mfe_dist, mfe_stats = _extract(mfe_dist_raw)
    mae_dist, mae_stats = _extract(mae_dist_raw)

    def _bar_row(label, count, total, color):
        pct = (count / total * 100) if total else 0
        bar = (f'<div style="background:{color};height:14px;width:{min(pct,100):.0f}%;'
               f'border-radius:3px;display:inline-block;vertical-align:middle"></div>')
        return (f"<tr><td style='white-space:nowrap'>{label}</td>"
                f"<td style='width:60%'>{bar}</td>"
                f"<td style='text-align:center'>{count}</td>"
                f"<td style='text-align:center'>{pct:.1f}%</td></tr>")

    def _stats_line(stats):
        if not stats:
            return ""
        parts = []
        if "mean"   in stats: parts.append(f"متوسط: {stats['mean']:.1f}%")
        if "median" in stats: parts.append(f"وسيط: {stats['median']:.1f}%")
        if "p75"    in stats: parts.append(f"P75: {stats['p75']:.1f}%")
        if "p90"    in stats: parts.append(f"P90: {stats['p90']:.1f}%")
        if "worst"  in stats: parts.append(f"أسوأ: {stats['worst']:.1f}%")
        return (f'<p style="font-size:.85em;color:#555;margin:4px 0 12px">'
                f'{" &nbsp;|&nbsp; ".join(parts)}</p>') if parts else ""

    html = '<div class="section"><h2>توزيع MFE و MAE — بصمة الجودة الكلية</h2>'

    if mfe_dist:
        total = sum(int(v) for v in mfe_dist.values())
        html += '<h3 style="color:#2a6496">توزيع MFE (الحركة القصوى لصالحنا)</h3>'
        html += _stats_line(mfe_stats)
        html += '<table><thead><tr><th>الفئة</th><th>التوزيع</th><th>عدد</th><th>%</th></tr></thead><tbody>'
        colors = {"<0%": "#dc3545", "0–3%": "#fd7e14", "3–8%": "#ffc107",
                  "8–15%": "#20c997", "15–25%": "#0d6efd", ">25%": "#198754"}
        for bucket in list(mfe_dist.keys()):
            count = int(mfe_dist.get(bucket, 0))
            html += _bar_row(bucket, count, total, colors.get(bucket, "#888"))
        html += "</tbody></table>"

    if mae_dist:
        total = sum(int(v) for v in mae_dist.values())
        html += '<h3 style="color:#2a6496">توزيع MAE (الحركة القصوى ضدنا — قيمة مطلقة)</h3>'
        html += _stats_line(mae_stats)
        html += '<table><thead><tr><th>الفئة</th><th>التوزيع</th><th>عدد</th><th>%</th></tr></thead><tbody>'
        colors = {"0–2%": "#198754", "2–5%": "#20c997", "5–10%": "#ffc107",
                  "10–15%": "#fd7e14", ">15%": "#dc3545"}
        for bucket in list(mae_dist.keys()):
            count = int(mae_dist.get(bucket, 0))
            html += _bar_row(bucket, count, total, colors.get(bucket, "#888"))
        html += "</tbody></table>"

    html += "</div>"
    return html


def _build_pattern_clusters_section(res: dict) -> str:
    pd = res.get("pattern_discovery", {})
    if not pd:
        return ""
    clusters_raw = pd.get("clusters", [])
    top_feats = pd.get("top_discriminating_features", [])
    n_total = pd.get("n_used", pd.get("n_signals", 0))
    algo    = pd.get("algorithm", "")
    sil     = pd.get("silhouette_score")

    # clusters is a list of dicts (one per cluster)
    if isinstance(clusters_raw, dict):
        clusters = list(clusters_raw.values())
    else:
        clusters = list(clusters_raw)

    if not clusters:
        return ""

    algo_tag = f" — {algo}" if algo else ""
    sil_tag  = f" (silhouette: {sil:.3f})" if sil else ""
    html = (
        '<div class="section">'
        f'<h2>Pattern Clusters{algo_tag} — اكتشاف أنماط تلقائي</h2>'
        f'<p style="font-size:.85em;color:#666">'
        f'مبني على {n_total} إشارة{sil_tag} — مُرتَّبة بـ MFE تنازلياً</p>'
    )

    if top_feats:
        feats_str = " | ".join(f"<code>{f}</code>" for f in top_feats[:8])
        html += f'<p style="font-size:.83em;color:#555">أكثر المتغيرات تمييزاً: {feats_str}</p>'

    html += (
        '<table><thead><tr>'
        '<th>Cluster</th><th>عدد</th><th>MFE (متوسط)</th>'
        '<th>MAE (متوسط)</th><th>BQ (متوسط)</th>'
        '<th>أبرز خصائص الـ Cluster</th>'
        '</tr></thead><tbody>'
    )

    sorted_clusters = sorted(clusters, key=lambda c: c.get("mfe_mean") or 0, reverse=True)
    for cv in sorted_clusters:
        cid  = cv.get("cluster_id", "?")
        n    = cv.get("n", 0)
        mfe_m = cv.get("mfe_mean")
        mae_m = cv.get("mae_mean")
        bq_m  = cv.get("bq_mean")
        label = cv.get("cluster_label", "")

        # signatures: {feat: {cluster_mean, diff_from_global}}
        sigs = cv.get("signatures", {})
        top_sigs = sorted(sigs.items(), key=lambda x: abs(x[1].get("diff_from_global", 0)), reverse=True)[:4]
        profile_str = " | ".join(
            f"<code>{k}</code>: {v.get('diff_from_global', 0):+.2f}" for k, v in top_sigs
        )
        if not profile_str:
            profile_str = " | ".join(f"<code>{f}</code>" for f in cv.get("top_features", [])[:4])

        html += (
            f"<tr><td><strong>C{cid}</strong><br><small style='color:#888'>{label}</small></td>"
            f"<td>{n}</td>"
            f"<td>{_mfe_badge(mfe_m)}</td>"
            f"<td>{_pct(mae_m)}</td>"
            f"<td>{_bq_badge(bq_m)}</td>"
            f"<td style='font-size:.80em'>{profile_str}</td></tr>"
        )

    html += (
        '</tbody></table>'
        '<div class="warn" style="margin-top:8px">'
        'الـ Clusters مُحسَّنة تلقائياً عند كل تشغيل للبحث — '
        'الـ Cluster الأعلى MFE يمثّل "بصمة القاع المثالية" التي يبحث عنها النظام.'
        '</div>'
        '</div>'
    )
    return html


def _build_fingerprints_section(res: dict) -> str:
    """Top 5 Bottom Fingerprints from pattern_discovery."""
    pd_res = res.get("pattern_discovery", {})
    fps    = pd_res.get("top_fingerprints", [])
    algo   = pd_res.get("algorithm", "KMeans")
    sil    = pd_res.get("silhouette_score")
    if not fps:
        return ""

    sil_str = f"  |  Silhouette: {sil:.3f}" if sil is not None else ""
    html = (
        '<div class="section">'
        f'<h2>Top 5 Bottom Fingerprints — أفضل أنماط القاع المكتشفة تلقائياً</h2>'
        f'<p style="font-size:.85em;color:#666">خوارزمية: <strong>{algo}</strong>{sil_str}</p>'
    )

    for fp in fps:
        rank  = fp.get("rank", "?")
        label = fp.get("label", "")
        n     = fp.get("n", 0)
        mfe_m = fp.get("mfe_mean")
        mae_m = fp.get("mae_mean")
        bq_m  = fp.get("bq_mean")
        ttr_m = fp.get("time_to_recovery_mean")
        ddr_m = fp.get("drawdown_duration_mean")

        rank_color = "#198754" if rank == 1 else ("#2a6496" if rank <= 3 else "#555")
        html += (
            f'<div class="rec-box" style="margin-bottom:10px">'
            f'<h3 style="color:{rank_color}">'
            f'#{rank} — {label}  <small style="font-weight:400;color:#888">(n={n})</small>'
            f'</h3>'
        )

        # KPIs row
        html += '<div class="kpi-row">'
        if mfe_m is not None:
            html += f'<div class="kpi"><div class="val">{_mfe_badge(mfe_m)}</div><div class="lbl">MFE متوسط</div></div>'
        if mae_m is not None:
            html += f'<div class="kpi"><div class="val">{_pct(abs(mae_m))}</div><div class="lbl">MAE متوسط</div></div>'
        if bq_m is not None:
            html += f'<div class="kpi"><div class="val">{_bq_badge(bq_m)}</div><div class="lbl">BQ متوسط</div></div>'
        if ttr_m is not None:
            html += f'<div class="kpi"><div class="val">{ttr_m:.0f}d</div><div class="lbl">وقت الانتعاش</div></div>'
        if ddr_m is not None:
            html += f'<div class="kpi"><div class="val">{ddr_m:.0f}d</div><div class="lbl">مدة التراجع</div></div>'
        html += '</div>'

        # Feature values
        fv = fp.get("feature_values", {})
        if fv:
            parts = []
            for feat, vals in fv.items():
                mean_v = vals.get("mean", 0)
                diff_v = vals.get("vs_global", 0)
                arrow  = "↑" if diff_v > 0 else ("↓" if diff_v < 0 else "→")
                color  = "#198754" if diff_v > 0 else ("#dc3545" if diff_v < 0 else "#888")
                parts.append(
                    f'<code>{feat}</code>: {mean_v:.3f} '
                    f'<span style="color:{color}">{arrow}{abs(diff_v):.3f}</span>'
                )
            html += '<p style="font-size:.82em;line-height:1.8">' + "  |  ".join(parts) + '</p>'

        html += '</div>'

    html += '</div>'
    return html


def _build_feature_health_section(res: dict) -> str:
    """Phase 6: Feature Health Report table."""
    fh = res.get("feature_health", {})
    if not fh or not fh.get("features"):
        return ""

    features   = fh["features"]
    auto_excl  = fh.get("auto_excluded", [])
    n_ok       = fh.get("n_ok", 0)
    n_sparse   = fh.get("n_sparse", 0)
    n_low_info = fh.get("n_low_info", 0)
    n_zero_var = fh.get("n_zero_var", 0)
    n_mostly_z = fh.get("n_mostly_zero", 0)

    html = (
        '<div class="section">'
        '<h2>Feature Health Report — جودة المتغيرات البحثية (Phase 6)</h2>'
        '<div class="kpi-row">'
        f'<div class="kpi"><div class="val" style="color:#198754">{n_ok}</div><div class="lbl">✓ سليم</div></div>'
        f'<div class="kpi"><div class="val" style="color:#ffc107">{n_low_info}</div><div class="lbl">معلومات ضعيفة</div></div>'
        f'<div class="kpi"><div class="val" style="color:#dc3545">{n_sparse + n_zero_var + n_mostly_z}</div><div class="lbl">مستبعد تلقائياً</div></div>'
        '</div>'
    )

    if auto_excl:
        excl_str = ", ".join(f"<code>{c}</code>" for c in auto_excl[:15])
        html += (
            f'<div class="warn">المتغيرات المستبعدة تلقائياً ({len(auto_excl)}): {excl_str}'
            + (' ...' if len(auto_excl) > 15 else '') + '</div>'
        )

    # Show top 20 by info gain, then any excluded ones
    sorted_feats = sorted(features.items(), key=lambda x: -x[1]["info_gain_mfe"])
    shown = sorted_feats[:25]

    health_colors = {
        "ok":            "#198754",
        "low_info":      "#856404",
        "too_sparse":    "#721c24",
        "zero_variance": "#721c24",
        "mostly_zero":   "#721c24",
    }
    health_labels = {
        "ok":            "سليم",
        "low_info":      "معلومات ضعيفة",
        "too_sparse":    "بيانات شحيحة",
        "zero_variance": "تباين صفري",
        "mostly_zero":   "أغلبه أصفار",
    }

    html += (
        '<table><thead><tr>'
        '<th>المتغير</th><th>حالة</th><th>غائب%</th>'
        '<th>أصفار%</th><th>قيم فريدة</th><th>Info Gain (MFE)</th>'
        '</tr></thead><tbody>'
    )

    for col, v in shown:
        hc    = v.get("health", "ok")
        color = health_colors.get(hc, "#333")
        label = health_labels.get(hc, hc)
        ig    = v.get("info_gain_mfe", 0)
        ig_bar_w = int(min(ig * 100, 100))
        ig_bar = (f'<div style="display:inline-block;background:#2a6496;height:10px;'
                  f'width:{ig_bar_w}px;border-radius:2px;vertical-align:middle"></div> {ig:.3f}')

        html += (
            f"<tr>"
            f"<td><code style='font-size:.82em'>{col}</code></td>"
            f"<td><span style='color:{color};font-weight:600'>{label}</span></td>"
            f"<td>{v.get('missing_ratio',0)*100:.0f}%</td>"
            f"<td>{v.get('zero_ratio',0)*100:.0f}%</td>"
            f"<td>{v.get('n_unique',0)}</td>"
            f"<td>{ig_bar}</td>"
            f"</tr>"
        )

    html += '</tbody></table></div>'
    return html


def _build_model_comparison_section(res: dict) -> str:
    mc_mfe = res.get("model_comparison_mfe", {})
    mc_bq  = res.get("model_comparison_bq",  {})
    if not mc_mfe and not mc_bq:
        return ""

    html = (
        '<div class="section">'
        '<h2>مقارنة النماذج — RF vs GBM vs XGBoost + SHAP</h2>'
        '<p style="font-size:.85em;color:#666">'
        'مقارنة شاملة بين ثلاثة نماذج ML — الأفضل R² هو المُعتمَد للأوزان التلقائية</p>'
    )

    for mc, target_label in [(mc_mfe, "MFE"), (mc_bq, "BQ Score")]:
        if not mc:
            continue
        best_name  = mc.get("best_model", "—")
        best_r2    = mc.get("best_r2", 0)
        ensemble   = mc.get("ensemble_importance", {})
        shap_vals  = mc.get("shap_importance", {})
        top20      = mc.get("top20_features", [])
        all_models = mc.get("all_models", {})

        r2_color = "green" if best_r2 >= 0.10 else ("orange" if best_r2 >= 0.05 else "red")
        html += (
            f'<h3 style="color:#2a6496">Target: {target_label} — '
            f'أفضل نموذج: <strong>{best_name}</strong> '
            f'(R²=<span style="color:{r2_color}">{best_r2}</span>)</h3>'
        )

        if all_models:
            html += (
                '<table><thead><tr>'
                '<th>النموذج</th><th>R²</th><th>تدريب</th><th>اختبار</th>'
                '</tr></thead><tbody>'
            )
            for mname, mdata in all_models.items():
                mr2 = mdata.get("r2", 0)
                mc_color = "green" if mr2 >= 0.10 else ("orange" if mr2 >= 0.05 else "#888")
                is_best = "★ " if mname == best_name else ""
                html += (
                    f"<tr><td>{is_best}{mname}</td>"
                    f"<td style='color:{mc_color};font-weight:600'>{mr2}</td>"
                    f"<td>{mdata.get('n_train','—')}</td>"
                    f"<td>{mdata.get('n_test','—')}</td></tr>"
                )
            html += "</tbody></table>"

        if top20 or ensemble:
            html += (
                '<h4 style="color:#444;margin:12px 0 6px">'
                'أهمية المتغيرات (Ensemble + SHAP مدمجَين)</h4>'
                '<table><thead><tr>'
                '<th>#</th><th>المتغير</th><th>Ensemble</th><th>SHAP</th>'
                '</tr></thead><tbody>'
            )
            shown = top20 if top20 else list(ensemble.items())[:20]
            for rank, item in enumerate(shown[:20], 1):
                if isinstance(item, (list, tuple)):
                    feat, ens_v = item[0], item[1]
                else:
                    feat, ens_v = item, ensemble.get(item, 0)
                shap_v = shap_vals.get(feat)
                shap_str = f"{shap_v:.4f}" if shap_v is not None else "—"
                bar_w = min(int(ens_v * 300), 100)
                bar = (f'<div style="background:#2a6496;height:8px;width:{bar_w}%;'
                       f'border-radius:2px;display:inline-block;vertical-align:middle"></div>')
                html += (
                    f"<tr><td>{rank}</td>"
                    f"<td><code>{feat}</code></td>"
                    f"<td>{bar} {ens_v:.4f}</td>"
                    f"<td>{shap_str}</td></tr>"
                )
            html += "</tbody></table>"

    html += (
        '<div class="warn" style="margin-top:8px;background:#e8f4f8;border-color:#bee5eb">'
        'الأوزان التلقائية محسوبة من ensemble importance — '
        'محفوظة في <code>learned_weights.json</code> ومُطبَّقة على pattern_engine تلقائياً.'
        '</div>'
        '</div>'
    )
    return html


def _build_warnings_section(warnings: list) -> str:
    if not warnings:
        return ""
    items = "".join(f'<li>{w}</li>' for w in warnings)
    return (
        '<div class="section">'
        f'<div class="warn"><strong>تنبيهات:</strong><ul style="margin:6px 0 0">{items}</ul></div>'
        '</div>'
    )


# ── Main Report Builder ────────────────────────────────────────────────────────

def build_report(db_path: str = DB_PATH) -> str:
    init_db(db_path)
    stats = get_stats(db_path=db_path)

    if stats.get("with_bq", 0) >= 5:
        res = run_research(db_path=db_path, verbose=False)
        try:
            with open(REPORT_JSON_PATH, "w", encoding="utf-8") as f:
                json.dump(res, f, ensure_ascii=False, indent=2, default=str)
        except Exception:
            pass
    else:
        res = {"meta": {}, "correlation": {}, "weight_suggestions": {},
               "segment_analysis": {}, "warnings": [
                   f"فقط {stats.get('with_bq', 0)} إشارات ناضجة — نحتاج 5 على الأقل للتحليل."
               ]}

    today = date.today().strftime("%Y-%m-%d")
    html  = f"""<!DOCTYPE html>
<html lang="ar">
<head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>EGX Research Report — {today}</title>
{_CSS}
</head>
<body>
<div class="container">
  <div class="header">
    <h1>EGX30 — تقرير البحث الاستراتيجي</h1>
    <p>{today} | البيانات: {stats.get('first_date','?')} ← {stats.get('last_date','?')}</p>
  </div>

  {_build_warnings_section(res.get("warnings", []))}
  {_build_kpi_section(stats, res)}
  {_build_active_signals_section(db_path)}
  {_build_probability_section(res)}
  {_build_edge_discovery_section(res)}
  {_build_distribution_section(res)}
  {_build_fingerprints_section(res)}
  {_build_pattern_clusters_section(res)}
  {_build_feature_health_section(res)}
  {_build_model_comparison_section(res)}
  {_build_correlation_section(res)}
  {_build_mutual_info_section(res)}
  {_build_model_section(res)}
  {_build_weight_suggestions_section(res)}
  {_build_pattern_section(res)}
  {_build_per_stock_pattern_section(res)}
  {_build_best_conditions_section(res)}
  {_build_per_stock_ml_section(res)}
  {_build_segment_section(res)}
  {_build_mature_signals_section(db_path)}

  <div class="footer">
    النظام لا يُعدّل نفسه تلقائياً — جميع التوصيات تحتاج مراجعة يدوية.<br>
    EGX Research Platform · {today}
  </div>
</div>
</body>
</html>"""
    # wrap all tables for horizontal scroll on mobile
    html = html.replace('<table', '<div class="tbl-wrap"><table').replace('</table>', '</table></div>')
    return html


# ── Email ──────────────────────────────────────────────────────────────────────

def send_report_email(html: str, db_path: str = DB_PATH) -> bool:
    """يُرسل التقرير بالبريد الإلكتروني. يُرجع True عند النجاح."""
    if not EMAIL_FROM or not EMAIL_PASS:
        print("[Report] Email not configured (set REPORT_EMAIL_FROM / REPORT_EMAIL_PASS).")
        return False

    today   = date.today().strftime("%Y-%m-%d")
    subject = f"EGX30 Research Report — {today}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = EMAIL_FROM
    msg["To"]      = EMAIL_TO
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
            s.ehlo()
            s.starttls()
            s.login(EMAIL_FROM, EMAIL_PASS)
            s.sendmail(EMAIL_FROM, [EMAIL_TO], msg.as_string())

        n_mature = get_stats(db_path=db_path).get("with_bq", 0)
        log_report_sent("weekly", n_mature, db_path=db_path)
        print(f"[Report] Email sent to {EMAIL_TO}")
        return True

    except Exception as e:
        print(f"[Report] Email failed: {e}")
        return False


# ── Scheduling Helpers ─────────────────────────────────────────────────────────

def is_weekly_due(db_path: str = DB_PATH) -> bool:
    """هل مرّ 7 أيام منذ آخر تقرير؟"""
    last = get_last_report_date("weekly", db_path=db_path)
    if not last:
        return True
    try:
        last_date = datetime.fromisoformat(last).date()
        return (date.today() - last_date).days >= WEEKLY_COOLDOWN_DAYS
    except Exception:
        return True


def maybe_run_weekly_report(db_path: str = DB_PATH, send_email: bool = True) -> bool:
    """
    يُشغّل التقرير الأسبوعي إن حان وقته.
    يُستدعى من main.py بعد الـ scan.
    يُرجع True إن أُرسل التقرير.
    """
    if not is_weekly_due(db_path=db_path):
        return False

    print("[Report] Weekly report due — generating ...")
    html = build_report(db_path=db_path)

    # احفظ HTML محلياً دائماً
    today    = date.today().strftime("%Y-%m-%d")
    out_path = f"research_report_{today}.html"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[Report] Saved → {out_path}")

    if send_email:
        send_report_email(html, db_path=db_path)

    return True


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="EGX Research Report Generator")
    p.add_argument("--no-email", action="store_true", help="Generate only, don't send email")
    p.add_argument("--force",    action="store_true", help="Ignore 7-day cooldown")
    p.add_argument("--db", default=DB_PATH, help=f"DB path (default: {DB_PATH})")
    args = p.parse_args()

    if not args.force and not is_weekly_due(db_path=args.db):
        last = get_last_report_date("weekly", db_path=args.db)
        print(f"[Report] Last report sent: {last}. Use --force to override.")
        sys.exit(0)

    html     = build_report(db_path=args.db)
    today    = date.today().strftime("%Y-%m-%d")
    out_path = f"research_report_{today}.html"

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[Report] Saved → {out_path}")

    if not args.no_email:
        ok = send_report_email(html, db_path=args.db)
        if not ok:
            print("[Report] Set REPORT_EMAIL_FROM and REPORT_EMAIL_PASS env vars to enable email.")
