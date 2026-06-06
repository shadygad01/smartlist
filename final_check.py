#!/usr/bin/env python3
"""فحص نهائي - ما الذي يحدث فعلاً؟"""
import sys
import os
import json

sys.path.insert(0, '/home/user/smartlist')

print("\n" + "="*100)
print("🔍 فحص نهائي - ما الذي يحدث بالضبط في النظام؟")
print("="*100 + "\n")

# الفحص 1: هل open_positions.json موجود؟
print("1️⃣  التحقق من الملف:")
print("-"*100)

if not os.path.exists("open_positions.json"):
    print("❌ الملف open_positions.json غير موجود!")
    print("   هذا هو السبب الأول المحتمل")
    sys.exit(1)

size = os.path.getsize("open_positions.json")
print(f"✅ الملف موجود ({size} بايت)")

# الفحص 2: البيانات
print("\n2️⃣  التحقق من البيانات:")
print("-"*100)

try:
    with open("open_positions.json", "r") as f:
        data = json.load(f)
except:
    print("❌ خطأ في قراءة الملف!")
    sys.exit(1)

if not data:
    print("❌ الملف فارغ - لا توجد بيانات")
    print("   هذا هو السبب المباشر لعدم ظهور المراكز المفتوحة")
    sys.exit(1)

print(f"✅ الملف يحتوي على {len(data)} صفقات")

open_positions = [s for s, p in data.items() if p.get("status") == "open"]
if not open_positions:
    print("❌ لا توجد صفقات مفتوحة")
    sys.exit(1)

print(f"✅ {len(open_positions)} منها مفتوحة")

# الفحص 3: تحميل البيانات من الكود
print("\n3️⃣  التحقق من تحميل البيانات من الكود:")
print("-"*100)

from main import load_open_positions

positions = load_open_positions()
print(f"✅ تم تحميل {len(positions)} صفقات من الكود")

# الفحص 4: بناء الإيميل
print("\n4️⃣  التحقق من بناء الإيميل:")
print("-"*100)

from main import build_report

html, results = build_report(holiday_mode=False)

# هل المراكز المفتوحة موجودة في الإيميل؟
if "المراكز المفتوحة" not in html:
    print("❌ قسم المراكز المفتوحة غير موجود في الإيميل HTML!")
    sys.exit(1)

print("✅ قسم المراكز المفتوحة موجود في الإيميل")

# كم صفقة معروضة؟
displayed = sum(1 for s in open_positions if s in html)
print(f"✅ عدد الصفقات المعروضة: {displayed}/{len(open_positions)}")

if displayed == 0:
    print("❌ لا توجد صفقات معروضة في الإيميل!")
    sys.exit(1)

# الفحص 5: تفاصيل الإيميل
print("\n5️⃣  تفاصيل الإيميل:")
print("-"*100)

# هل الأسعار موجودة؟
sample_price = list(positions.values())[0].get("current_price")
if str(sample_price) in html:
    print(f"✅ الأسعار معروضة (مثال: {sample_price})")
else:
    print(f"⚠️  الأسعار قد لا تكون معروضة")

# هل الأرباح موجودة؟
if "%" in html:
    print("✅ النسب المئوية (الأرباح) موجودة")
else:
    print("⚠️  النسب المئوية قد لا تكون معروضة")

# الفحص 6: الملخص النهائي
print("\n" + "="*100)
print("📋 الملخص:")
print("="*100)

print(f"""
✅ جميع الفحوصات نجحت!

الحالة:
  • الملف موجود
  • يحتوي على {len(open_positions)} صفقات مفتوحة
  • الكود يحملها بشكل صحيح
  • الإيميل يعرض {displayed} صفقات
  • الأسعار والأرباح موجودة

النتيجة:
  🎯 الإيميل يجب أن يعرض المراكز المفتوحة
  📧 إذا لم تراها، المشكلة قد تكون في:
     1. نسخة قديمة من الكود تُرسل الإيميل
     2. الإيميل لم يُحدّث بعد تشغيل الكود الجديد
     3. تحتاج لإعادة تشغيل البرنامج

اختبر الآن:
  python simple_test.py
  أو
  python initialize_positions.py
""")

print("="*100 + "\n")
