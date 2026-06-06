#!/usr/bin/env python3
"""اختبار بسيط جداً - خطوة بخطوة"""
import sys
import json
sys.path.insert(0, '/home/user/smartlist')

print("\n" + "="*80)
print("اختبار 1: قراءة الملف مباشرة")
print("="*80)

with open('open_positions.json', 'r') as f:
    data = json.load(f)

print(f"✅ عدد الصفقات في الملف: {len(data)}")
print(f"✅ أول صفقة: {list(data.keys())[0]}")

print("\n" + "="*80)
print("اختبار 2: استيراد الدالة من main.py")
print("="*80)

from main import load_open_positions

positions = load_open_positions()
print(f"✅ عدد الصفقات المحملة: {len(positions)}")

print("\n" + "="*80)
print("اختبار 3: التحقق من البيانات المحملة")
print("="*80)

if positions:
    first_key = list(positions.keys())[0]
    first_pos = positions[first_key]
    print(f"\n✅ أول صفقة: {first_key}")
    print(f"   entry_price: {first_pos.get('entry_price')}")
    print(f"   current_price: {first_pos.get('current_price')}")
    print(f"   target: {first_pos.get('target')}")
    print(f"   status: {first_pos.get('status')}")

print("\n" + "="*80)
print("اختبار 4: استدعاء build_report()")
print("="*80)

from main import build_report

html, results = build_report(holiday_mode=False)

# البحث عن القسم
if "المراكز المفتوحة" in html:
    print("✅ وجدنا قسم 'المراكز المفتوحة' في الإيميل")

    # البحث عن أول صفقة
    if "COMI" in html:
        print("✅ وجدنا COMI في الإيميل")
    else:
        print("❌ لم نجد COMI في الإيميل")

    # عد الصفوف
    rows = html.count("<tr")
    print(f"✅ عدد صفوف HTML: {rows}")
else:
    print("❌ لم نجد قسم المراكز المفتوحة")

print("\n" + "="*80)
print("اختبار 5: حفظ الإيميل في ملف لفحصه")
print("="*80)

with open('/tmp/test_email.html', 'w', encoding='utf-8') as f:
    f.write(html)

print("✅ تم حفظ الإيميل في /tmp/test_email.html")

print("\n" + "="*80)
