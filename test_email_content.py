#!/usr/bin/env python3
"""اختبار محتوى الإيميل الفعلي"""
import sys
sys.path.insert(0, '/home/user/smartlist')

from main import build_report, load_open_positions, NAMES

print("=" * 90)
print("🔍 اختبار محتوى الإيميل")
print("=" * 90)

# تحميل البيانات
positions = load_open_positions()
print(f"\n✅ تم تحميل {len(positions)} صفقة من open_positions.json")

# بناء التقرير
print("\n⏳ جاري بناء التقرير...")
html_content, results = build_report(holiday_mode=False)

# البحث عن قسم المراكز المفتوحة
print("\n" + "=" * 90)
print("📊 البحث عن قسم 'المراكز المفتوحة'")
print("=" * 90)

if "المراكز المفتوحة" in html_content:
    print("\n✅ وجدنا النص 'المراكز المفتوحة' في الإيميل")

    # البحث عن جدول
    if "<table" in html_content and "المراكز المفتوحة" in html_content:
        print("✅ وجدنا جدول بعد عنوان المراكز المفتوحة")

    # البحث عن الأسهم
    print("\n📌 البحث عن أسهم معينة:")
    found_stocks = []
    for symbol in positions.keys():
        if symbol in html_content:
            found_stocks.append(symbol)
            print(f"   ✅ {symbol} - {NAMES.get(symbol, symbol)}")
        else:
            print(f"   ❌ {symbol} - لم يتم العثور عليه")

    print(f"\nالإجمالي: {len(found_stocks)}/{len(positions)} سهم معروض")
else:
    print("\n❌ لم نجد النص 'المراكز المفتوحة' في الإيميل")

# استخراج جزء من الإيميل
print("\n" + "=" * 90)
print("📋 مقتطف من الإيميل (أول 2000 حرف)")
print("=" * 90)
print(html_content[:2000])

# البحث عن الكلمات المفتاحية
print("\n" + "=" * 90)
print("🔎 البحث عن الكلمات المفتاحية")
print("=" * 90)

keywords = [
    "المراكز المفتوحة",
    "سعر الدخول",
    "السعر الحالي",
    "التارجت الديناميكي",
    "مستوى",
    "Fib",
]

for keyword in keywords:
    count = html_content.count(keyword)
    status = "✅" if count > 0 else "❌"
    print(f"{status} '{keyword}': {count} مرة")

# بحث دقيق عن الجدول
print("\n" + "=" * 90)
print("📐 بحث دقيق عن جدول المراكز")
print("=" * 90)

start_idx = html_content.find("المراكز المفتوحة")
if start_idx > 0:
    # استخراج جزء يحتوي على الجدول
    section = html_content[start_idx:start_idx+3000]

    # البحث عن الصفوف
    table_rows = section.count("<tr")
    print(f"✅ عدد صفوف الجدول: {table_rows}")

    # طباعة الجزء
    print("\n📄 محتوى قسم المراكز المفتوحة (أول 1500 حرف):")
    print(section[:1500])
else:
    print("❌ لم يتم العثور على قسم المراكز المفتوحة")

print("\n" + "=" * 90)
