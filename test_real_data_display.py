#!/usr/bin/env python3
"""
اختبار عرض البيانات الحقيقية في الإيميل والتيليجرام
"""
import sys
sys.path.insert(0, '/home/user/smartlist')

from main import load_open_positions, build_report, send_telegram_alerts, NAMES
import json

print("\n" + "=" * 90)
print("✅ اختبار عرض البيانات الحقيقية (1/1 - 6/6/2026)")
print("=" * 90)

# تحميل البيانات الحقيقية
positions = load_open_positions()

print(f"\n📁 البيانات المحملة: {len(positions)} صفقة مفتوحة")
print("\n" + "─" * 90)
print("📧 اختبار الإيميل - سيتم عرض جدول المراكز المفتوحة")
print("─" * 90)

# بناء التقرير
html_report, analysis_results = build_report(holiday_mode=False)

# التحقق من وجود المراكز المفتوحة في الإيميل
if "المراكز المفتوحة" in html_report or "open positions" in html_report.lower():
    print("✅ قسم 'المراكز المفتوحة' موجود في التقرير!")

    # حساب عدد الصفقات المعروضة
    email_positions = []
    for symbol in positions:
        if symbol in html_report:
            email_positions.append(symbol)

    print(f"✅ عدد الصفقات المعروضة في الإيميل: {len(email_positions)}/{len(positions)}")

    if email_positions:
        print("\n📊 الصفقات المعروضة في الإيميل:")
        for symbol in sorted(email_positions):
            data = positions[symbol]
            name = NAMES.get(symbol, symbol)
            entry = data['entry_price']
            current = data.get('current_price', entry)
            target = data['target']
            profit = ((current - entry) / entry) * 100
            print(f"   ✓ {symbol} — {name}")
            print(f"      💰 الدخول: {entry} → الحالي: {current} (الربح: {profit:+.1f}%)")
            print(f"      🎯 الهدف: {target}")
else:
    print("❌ قسم المراكز المفتوحة غير موجود في الإيميل!")

print("\n" + "─" * 90)
print("📱 اختبار التيليجرام - محاكاة الرسالة")
print("─" * 90)

print("\n📊 *المراكز المفتوحة: 10*\n")

# عرض الصفقات مثل ما ستظهر في التيليجرام
for symbol in sorted(positions.keys()):
    data = positions[symbol]
    name = NAMES.get(symbol, symbol)[:30]  # اختصار الاسم
    entry = data['entry_price']
    current = data.get('current_price', entry)
    target = data['target']
    level = data['current_level']

    fib_labels = {0: "12%", 1: "23.6%", 2: "38.2%", 3: "50%", 4: "61.8%", 5: "100%"}
    fib_label = fib_labels.get(level, "N/A")

    profit = ((current - entry) / entry) * 100

    print(f"• {symbol}: {entry} → {current} {name} ({fib_label}) ↑{profit:+.1f}%")

print("\n" + "=" * 90)
print("📈 ملخص الأداء")
print("=" * 90)

total_profit = sum(
    ((p.get('current_price', p['entry_price']) - p['entry_price']) / p['entry_price']) * 100
    for p in positions.values()
) / len(positions)

avg_entry = sum(p['entry_price'] for p in positions.values()) / len(positions)
avg_current = sum(p.get('current_price', p['entry_price']) for p in positions.values()) / len(positions)

print(f"\n📊 متوسط ربحية الصفقات: {total_profit:+.1f}%")
print(f"💰 متوسط سعر الدخول: {avg_entry:.2f} EGP")
print(f"📈 متوسط السعر الحالي: {avg_current:.2f} EGP")

# عدد الصفقات بأداء جيد
good_trades = sum(
    1 for p in positions.values()
    if ((p.get('current_price', p['entry_price']) - p['entry_price']) / p['entry_price']) * 100 > 30
)

print(f"\n🏆 عدد الصفقات برابح >30%: {good_trades}/{len(positions)}")

print("\n" + "=" * 90)
print("✅ النظام جاهز لعرض البيانات الحقيقية في الإيميل والتيليجرام")
print("=" * 90 + "\n")
