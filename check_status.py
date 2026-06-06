#!/usr/bin/env python3
"""اختبار لمعرفة السبب بالضبط"""
import json
import os

print("\n" + "="*90)
print("🔧 فحص دقيق للمشكلة - ما يحدث بالضبط")
print("="*90)

# الخطوة 1: هل الملف موجود؟
print("\n1️⃣ هل الملف موجود؟")
print("-"*90)

if not os.path.exists("open_positions.json"):
    print("❌ الملف غير موجود!")
    print("   المسار المتوقع: open_positions.json")
    print("\n   الحل: أنشئ الملف ببيانات:")
    print("""
    {
      "SYMBOL.CA": {
        "entry_date": "2026-01-01T10:00:00+03:00",
        "entry_price": 100.0,
        "current_price": 110.0,
        "fib_targets": [112, 120, 130],
        "current_level": 1,
        "target": 120.0,
        "status": "open"
      }
    }
    """)
    exit(1)

print("✅ الملف موجود")

# الخطوة 2: حجم الملف
print("\n2️⃣ حجم الملف")
print("-"*90)

size = os.path.getsize("open_positions.json")
print(f"   الحجم: {size} بايت")

if size < 10:
    print("❌ الملف فارغ تقريباً!")
    print("   هذه هي المشكلة!")
    exit(1)

print("✅ الملف يحتوي على محتوى")

# الخطوة 3: قراءة الملف
print("\n3️⃣ قراءة محتوى الملف")
print("-"*90)

try:
    with open("open_positions.json", "r") as f:
        data = json.load(f)
    print("✅ الملف صحيح من ناحية JSON")
except json.JSONDecodeError as e:
    print(f"❌ خطأ في JSON: {e}")
    exit(1)

# الخطوة 4: عدد الصفقات
print("\n4️⃣ عدد الصفقات")
print("-"*90)

print(f"   إجمالي الصفقات في الملف: {len(data)}")

if not data:
    print("❌ الملف فارغ تماماً!")
    print("   هذه هي المشكلة!")
    exit(1)

# الخطوة 5: التحقق من كل صفقة
print("\n5️⃣ تحليل كل صفقة")
print("-"*90)

open_positions = []
closed_positions = []
bad_positions = []

for sym, pos in data.items():
    status = pos.get("status")

    if status == "open":
        open_positions.append(sym)
        print(f"   ✅ {sym}: status='open'")
    elif status == "closed":
        closed_positions.append(sym)
        print(f"   ❌ {sym}: status='closed' (لن تُعرض!)")
    else:
        bad_positions.append(sym)
        print(f"   ⚠️  {sym}: status='{status}' (غير معروف!)")

print(f"\n   ملخص:")
print(f"     • صفقات مفتوحة (ستُعرض): {len(open_positions)}")
print(f"     • صفقات مغلقة (لن تُعرض): {len(closed_positions)}")
print(f"     • صفقات غير صحيحة: {len(bad_positions)}")

# الخطوة 6: التحقق من البيانات الأساسية
print("\n6️⃣ التحقق من البيانات الأساسية")
print("-"*90)

if open_positions:
    first = open_positions[0]
    pos_data = data[first]

    required_fields = ["entry_date", "entry_price", "target", "status"]
    missing = []

    for field in required_fields:
        if field not in pos_data:
            missing.append(field)
            print(f"   ❌ حقل '{field}' غير موجود في {first}")
        else:
            print(f"   ✅ حقل '{field}' موجود")

    if missing:
        print(f"\n❌ الصفقة {first} تحتوي على حقول ناقصة!")
        exit(1)
else:
    print("⚠️  لا توجد صفقات مفتوحة!")

# الخلاصة
print("\n" + "="*90)
print("📋 الخلاصة")
print("="*90)

if not open_positions:
    print("""
❌ المشكلة الحقيقية:
   لا توجد صفقات بـ status='open' في الملف!

الحل:
   1. تأكد من أن الملف يحتوي على صفقات
   2. تأكد من أن status = "open"
   3. أضف صفقة واحدة على الأقل للاختبار
   4. جرّب مرة أخرى
""")
else:
    print(f"""
✅ يبدو أن كل شيء صحيح:
   • عدد الصفقات المفتوحة: {len(open_positions)}
   • جميع الحقول المطلوبة موجودة

   إذا لم تره في الإيميل:
   1. تأكد من أن build_report() تُستدعى
   2. تأكد من أن الإيميل يُرسل بنجاح
   3. افحص سجل الأخطاء
""")

print("="*90 + "\n")
