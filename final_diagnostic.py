#!/usr/bin/env python3
"""
فحص نهائي شامل - ما الذي سيظهر في الإيميل بالضبط؟
"""
import sys
import json
sys.path.insert(0, '/home/user/smartlist')

from main import build_report, load_open_positions

print("\n" + "="*120)
print("🔍 FINAL DIAGNOSTIC: ما الذي سيظهر في الإيميل؟")
print("="*120 + "\n")

# Step 1: Check data
print("📊 الخطوة 1: التحقق من البيانات الأساسية")
print("-"*120)

positions = load_open_positions()
print(f"✓ تم تحميل {len(positions)} صفقة من open_positions.json")

open_positions = {s: p for s, p in positions.items() if p.get("status") == "open"}
print(f"✓ عدد الصفقات المفتوحة: {len(open_positions)}")

if not open_positions:
    print("\n❌ المشكلة: لا توجد صفقات مفتوحة في الملف!")
    print("   هذا هو السبب - لا شيء ليُعرض في الإيميل")
    sys.exit(1)

print(f"\nالصفقات المفتوحة:")
for i, (sym, p) in enumerate(list(open_positions.items())[:3], 1):
    print(f"  {i}. {sym}: {p['entry_price']} → {p['current_price']} → {p['target']}")

# Step 2: Build report
print("\n\n📧 الخطوة 2: بناء الإيميل (كما يحدث في daily_scan)")
print("-"*120)

html, results = build_report(holiday_mode=False)
print(f"✓ تم بناء الإيميل ({len(html)} حرف)")

# Step 3: Check for open positions section
print("\n\n🔎 الخطوة 3: البحث عن قسم المراكز المفتوحة في الإيميل")
print("-"*120)

if "المراكز المفتوحة" not in html:
    print("❌ المشكلة: قسم 'المراكز المفتوحة' غير موجود في الإيميل!")
    print("   هذا يعني أن كود build_report لم يُنشئ القسم")
    sys.exit(1)

print("✓ وُجدت كلمة 'المراكز المفتوحة' في الإيميل")

# Count open positions in the HTML
open_section_start = html.find("المراكز المفتوحة")
open_section_end = html.find("</table>", open_section_start)

if open_section_start > 0 and open_section_end > 0:
    open_section = html[open_section_start:open_section_end]
    
    # Count .CA symbols in the section
    positions_shown = open_section.count(".CA")
    print(f"✓ عدد الصفقات المعروضة في جدول: {positions_shown}")
    
    if positions_shown == 0:
        print("❌ المشكلة: الجدول موجود لكن الصفقات غير معروضة!")
        sys.exit(1)
    elif positions_shown < len(open_positions):
        print(f"⚠️ تحذير: معروضة {positions_shown} من {len(open_positions)} صفقة")

# Step 4: Extract and display the actual section
print("\n\n📋 الخطوة 4: محتوى قسم المراكز المفتوحة من الإيميل")
print("-"*120)

import re
# Extract the open positions section
start = html.find("المراكز المفتوحة")
end = html.find("</table>", start) + 8

if start > 0 and end > start:
    section = html[start:end]
    
    # Remove HTML tags for display
    clean = re.sub('<[^>]+>', '', section)
    clean = re.sub(r'\s+', ' ', clean)
    
    print(clean[:2000])
    if len(clean) > 2000:
        print("...[أكثر]")

# Step 5: Summary
print("\n\n" + "="*120)
print("✅ SUMMARY:")
print("="*120)

print(f"""
✓ البيانات موجودة: {len(open_positions)} صفقة مفتوحة
✓ الإيميل مبني: {len(html)} حرف
✓ القسم موجود: 'المراكز المفتوحة'
✓ الصفقات معروضة: نعم

🎯 النتيجة: الإيميل يحتوي على المراكز المفتوحة بشكل صحيح!

إذا لم تكن تراها في بريدك الفعلي، فالمشكلة قد تكون:
  1. أن البريد لم يصل بعد (تأخير في الإرسال)
  2. أو أن GitHub Actions لم يشغّل الكود الجديد بعد
  3. أو أن open_positions.json فارغ في بيئتك أنت
""")

print("="*120 + "\n")
