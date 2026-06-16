"""
EGX Context Layer
=================
تصنيف السياق المحيط بكل إشارة تداول في البورصة المصرية:
  - تقويم أيام التداول الصحيح (الأحد-الخميس + الإجازات الرسمية)
  - موسم رمضان  →  نظام تداول مختلف (حجم ضعيف + تقلب غير عادي)
  - نافذة قرارات البنك المركزي (CBE)  →  تأثير سوقي عام
  - الموسم السنوي (صيف/شتاء/عادي)
  - نسبة الحجم للمتوسط (volume_vs_adv)  →  موثوقية الإشارة
"""

from datetime import date, timedelta


# ── تقويم إجازات EGX (2024-2027) ─────────────────────────────────────────────
EGX_HOLIDAYS = {
    # 2024
    date(2024, 1, 7),                                           # عيد الميلاد القبطي
    date(2024, 1, 25),                                          # ثورة 25 يناير
    date(2024, 2, 8),                                           # الإسراء والمعراج
    date(2024, 4, 8),  date(2024, 4, 9),  date(2024, 4, 10),
    date(2024, 4, 11),                                          # عيد الفطر
    date(2024, 4, 25),                                          # تحرير سيناء
    date(2024, 5, 1),                                           # عيد العمال
    date(2024, 6, 16), date(2024, 6, 17), date(2024, 6, 18),   # عيد الأضحى
    date(2024, 7, 7),                                           # رأس السنة الهجرية
    date(2024, 7, 23),                                          # ثورة 23 يوليو
    date(2024, 9, 15),                                          # المولد النبوي
    date(2024, 10, 6),                                          # أكتوبر
    # 2025
    date(2025, 1, 7),
    date(2025, 1, 27),                                          # الإسراء والمعراج
    date(2025, 3, 29), date(2025, 3, 30), date(2025, 3, 31),
    date(2025, 4, 1),  date(2025, 4, 2),                       # عيد الفطر
    date(2025, 4, 25),
    date(2025, 5, 1),
    date(2025, 6, 5),  date(2025, 6, 6),  date(2025, 6, 7),   # عيد الأضحى
    date(2025, 6, 26),                                          # رأس السنة الهجرية
    date(2025, 7, 23),
    date(2025, 9, 4),                                           # المولد النبوي
    date(2025, 10, 6),
    # 2026 — من main.py
    date(2026, 1, 7),  date(2026, 1, 29),
    date(2026, 3, 19), date(2026, 3, 20), date(2026, 3, 21),
    date(2026, 3, 22), date(2026, 3, 23),
    date(2026, 4, 13), date(2026, 4, 25), date(2026, 5, 1),
    date(2026, 5, 26), date(2026, 5, 27), date(2026, 5, 28), date(2026, 5, 29),
    date(2026, 6, 16), date(2026, 7, 23),
    date(2026, 8, 25), date(2026, 10, 6),
    # 2027 — أيام وطنية ثابتة (الإسلامية تعتمد على رؤية الهلال)
    date(2027, 1, 7),
    date(2027, 4, 25),
    date(2027, 5, 1),
    date(2027, 7, 23),
    date(2027, 10, 6),
}

# ── قرارات البنك المركزي المصري (CBE) ────────────────────────────────────────
# كل تاريخ يُغلق نافذة ±3 أيام تأثير على إشارات التداول
CBE_MEETING_DATES = {
    # 2024
    date(2024, 2, 1),  date(2024, 3, 7),  date(2024, 4, 4),
    date(2024, 5, 23), date(2024, 7, 18), date(2024, 9, 19),
    date(2024, 10, 17), date(2024, 12, 26),
    # 2025
    date(2025, 2, 6),  date(2025, 3, 20), date(2025, 5, 1),
    date(2025, 6, 19), date(2025, 7, 31), date(2025, 9, 11),
    date(2025, 10, 23), date(2025, 12, 4),
    # 2026
    date(2026, 2, 5),  date(2026, 3, 19), date(2026, 4, 30),
    date(2026, 6, 18), date(2026, 7, 30), date(2026, 9, 10),
    date(2026, 10, 22), date(2026, 12, 3),
}

CBE_WINDOW_DAYS = 3  # أيام قبل وبعد اجتماع CBE

# ── فترات رمضان ───────────────────────────────────────────────────────────────
RAMADAN_PERIODS = [
    (date(2023, 3, 22), date(2023, 4, 20)),
    (date(2024, 3, 11), date(2024, 4, 9)),
    (date(2025, 3, 1),  date(2025, 3, 30)),
    (date(2026, 2, 18), date(2026, 3, 19)),
    (date(2027, 2, 7),  date(2027, 3, 8)),
]


# ── دوال التقويم ──────────────────────────────────────────────────────────────

def is_egx_trading_day(d=None):
    """هل التاريخ يوم تداول فعلي في EGX؟ (الأحد-الخميس ما عدا الإجازات الرسمية)"""
    if d is None:
        d = date.today()
    # Python weekday: 0=Mon 1=Tue 2=Wed 3=Thu 4=Fri 5=Sat 6=Sun
    # EGX يتداول: الأحد(6) الاثنين(0) الثلاثاء(1) الأربعاء(2) الخميس(3)
    if d.weekday() in (4, 5):  # الجمعة والسبت
        return False
    return d not in EGX_HOLIDAYS


def trading_days_between(start_date_str, end_date=None):
    """
    عدد أيام التداول الفعلية في EGX من تاريخ البداية حتى اليوم.
    يحسب الأحد-الخميس مع استثناء الإجازات الرسمية.
    """
    try:
        start = date.fromisoformat(start_date_str)
        end   = end_date or date.today()
        count = 0
        d = start + timedelta(days=1)
        while d <= end:
            if is_egx_trading_day(d):
                count += 1
            d += timedelta(days=1)
        return count
    except Exception:
        return 0


# ── دوال السياق ───────────────────────────────────────────────────────────────

def is_ramadan(d=None):
    """هل التاريخ يقع في شهر رمضان؟"""
    if d is None:
        d = date.today()
    return any(start <= d <= end for start, end in RAMADAN_PERIODS)


def is_cbe_window(d=None):
    """هل التاريخ ضمن نافذة ±3 أيام من اجتماع CBE؟"""
    if d is None:
        d = date.today()
    return any(abs((d - cbe).days) <= CBE_WINDOW_DAYS for cbe in CBE_MEETING_DATES)


def get_season(d=None):
    """الموسم السنوي: summer (يون-أغس) | winter (ديس-فبر) | normal"""
    if d is None:
        d = date.today()
    m = d.month
    if m in (6, 7, 8):
        return "summer"
    if m in (12, 1, 2):
        return "winter"
    return "normal"


def get_signal_context(signal_date_str, today_volume=None, avg_volume=None):
    """
    يُرجع dict يصف السياق الكامل المحيط بإشارة تداول.

    signal_date_str : تاريخ الإشارة بصيغة ISO  "2026-06-10"
    today_volume    : حجم التداول في يوم الإشارة (عدد الأسهم)
    avg_volume      : متوسط الحجم اليومي لآخر 20 يوم تداول
    """
    try:
        d = date.fromisoformat(signal_date_str)
    except Exception:
        d = date.today()

    volume_vs_adv = None
    if today_volume is not None and avg_volume and avg_volume > 0:
        volume_vs_adv = round(float(today_volume) / float(avg_volume), 3)

    return {
        "is_ramadan":    is_ramadan(d),
        "cbe_window":    is_cbe_window(d),
        "season":        get_season(d),
        "volume_vs_adv": volume_vs_adv,
    }
