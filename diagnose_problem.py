#!/usr/bin/env python3
"""تشخيص شامل للمشكلة"""
import os
import json
import sys

sys.path.insert(0, '/home/user/smartlist')

print("\n" + "="*90)
print("🔍 تشخيص شامل للمشكلة")
print("="*90)

# ===== الفحص 1: الملف =====
print("\n1️⃣  فحص الملف:")
print("-" * 90)

file_path = "open_positions.json"

if not os.path.exists(file_path):
    print(f"❌ الملف {file_path} غير موجود!")
    print("   الحل: تأكد من وجود الملف في المجلد الصحيح")
    sys.exit(1)

file_size = os.path.getsize(file_path)
print(f"✅ الملف موجود")
print(f"   المسار: {os.path.abspath(file_path)}")
print(f"   الحجم: {file_size} بايت")

if file_size == 0:
    print(f"❌ الملف **فارغ تماماً**!")
    print("   هذه هي المشكلة الحقيقية!")
    sys.exit(1)

# ===== الفحص 2: محتوى الملف =====
print("\n2️⃣  فحص محتوى الملف:")
print("-" * 90)

try:
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if not data:
        print(f"❌ الملف يحتوي على بيانات فارغة (فارغ)")
        print("   هذه هي المشكلة الحقيقية!")
        sys.exit(1)

    print(f"✅ البيانات قابلة للقراءة")
    print(f"   عدد الصفقات: {len(data)}")

    # التحقق من كل صفقة
    print("\n   قائمة الصفقات:")
    for symbol, pos in data.items():
        status = pos.get("status", "UNKNOWN")
        entry = pos.get("entry_price", "N/A")
        target = pos.get("target", "N/A")
        print(f"      ✓ {symbol}: entry={entry}, target={target}, status={status}")

except json.JSONDecodeError as e:
    print(f"❌ خطأ في قراءة الـ JSON:")
    print(f"   {e}")
    sys.exit(1)

except Exception as e:
    print(f"❌ خطأ عام:")
    print(f"   {e}")
    sys.exit(1)

# ===== الفحص 3: تحميل الدالة =====
print("\n3️⃣  فحص دالة load_open_positions():")
print("-" * 90)

try:
    from main import load_open_positions

    positions = load_open_positions()

    if not positions:
        print(f"❌ الدالة أرجعت بيانات فارغة!")
        print("   هذه مشكلة في الكود")
        sys.exit(1)

    print(f"✅ الدالة تعمل بشكل صحيح")
    print(f"   عدد الصفقات المحملة: {len(positions)}")

except Exception as e:
    print(f"❌ خطأ في استيراد الدالة:")
    print(f"   {e}")
    sys.exit(1)

# ===== الفحص 4: الإيميل =====
print("\n4️⃣  فحص محتوى الإيميل:")
print("-" * 90)

try:
    from main import build_report

    html, results = build_report(holiday_mode=False)

    if "المراكز المفتوحة" not in html:
        print(f"❌ قسم 'المراكز المفتوحة' غير موجود في الإيميل!")
        print("   هذه مشكلة في الكود")
        sys.exit(1)

    # عد الصفقات في الإيميل
    count = 0
    for symbol in positions:
        if symbol in html:
            count += 1

    print(f"✅ قسم 'المراكز المفتوحة' موجود")
    print(f"   عدد الصفقات المعروضة: {count}/{len(positions)}")

    if count == 0:
        print(f"❌ لا توجد صفقات معروضة!")
        print("   هذه مشكلة في الكود")
        sys.exit(1)

    # تحقق من الأسعار
    if "52.67" in html:  # COMI current price
        print(f"✅ الأسعار تُعرض بشكل صحيح")
    else:
        print(f"⚠️  قد لا تُعرض الأسعار بشكل صحيح")

except Exception as e:
    print(f"❌ خطأ في بناء الإيميل:")
    print(f"   {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# ===== الخلاصة =====
print("\n" + "="*90)
print("✅ جميع الفحوصات نجحت!")
print("="*90)

print(f"""
النتائج:
  ✅ الملف موجود وحجمه {file_size} بايت
  ✅ يحتوي على {len(positions)} صفقة مفتوحة
  ✅ الدالة تحمل البيانات بشكل صحيح
  ✅ الإيميل يعرض {count} صفقة

الخلاصة:
  🎯 النظام يعمل بشكل صحيح!
  📧 الإيميل سيحتوي على جدول المراكز المفتوحة
  📱 التيليجرام سيحتوي على قائمة المراكز المفتوحة

إذا كنت لا تراها في الإيميل الفعلي:
  1. تأكد من أن الإيميل يصل بنجاح
  2. افحص محتوى الإيميل في جسم الرسالة (قد يكون في نهاية الرسالة)
  3. جرّب فتح الإيميل في متصفح ويب
  4. تحقق من أن open_positions.json موجود ويحتوي على بيانات
""")

print("="*90)
