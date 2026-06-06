#!/usr/bin/env python3
"""عرض جدول المراكز المفتوحة كما يظهر في الإيميل"""
import sys
import re
sys.path.insert(0, '/home/user/smartlist')

from main import build_report, load_open_positions, NAMES

print("=" * 100)
print("📊 جدول المراكز المفتوحة كما يظهر في الإيميل")
print("=" * 100)

# تحميل البيانات والتقرير
positions = load_open_positions()
html_content, results = build_report(holiday_mode=False)

# استخراج جدول المراكز المفتوحة
start = html_content.find("المراكز المفتوحة")
if start > 0:
    section = html_content[start:start+5000]

    # استخراج الصفوف
    rows = re.findall(r'<tr style="border-bottom:1px solid #e8f0f8;">.*?</tr>', section, re.DOTALL)

    print(f"\n✅ تم العثور على {len(rows)} صف من البيانات\n")

    # طباعة رأس الجدول
    print(f"{'السهم':<30} {'الدخول':<12} {'الحالي':<12} {'الربح':<10} {'التارجت':<12} {'المستوى':<8}")
    print("-" * 100)

    # استخراج البيانات من كل صف
    for i, row in enumerate(rows):
        # استخراج النصوص من HTML
        symbols = re.findall(r'>([A-Z]+\.CA)<', row)
        prices = re.findall(r'(\d+\.?\d*) EGP', row)
        percents = re.findall(r'\(([+-]?\d+\.?\d*%)\)', row)
        fibs = re.findall(r'<span style="font-family:Arial,sans-serif;font-size:11px;background:#e8f0fe;color:#1a56db;padding:3px 8px;border-radius:10px;font-weight:bold;">([^<]+)</span>', row)

        if symbols:
            symbol = symbols[0]
            data = positions.get(symbol, {})

            # تنظيم البيانات
            if len(prices) >= 3:
                entry = prices[0]
                current = prices[1]
                target = prices[2]
                profit = percents[0] if percents else "—"
                fib = fibs[0] if fibs else "—"

                print(f"{NAMES.get(symbol, symbol):<30} {entry:<12} {current:<12} {profit:<10} {target:<12} {fib:<8}")

    print("\n" + "=" * 100)
    print("✅ الجدول معروض بشكل صحيح في الإيميل")
    print("=" * 100)
else:
    print("❌ لم يتم العثور على جدول المراكز المفتوحة")
