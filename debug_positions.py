#!/usr/bin/env python3
import sys
import json
sys.path.insert(0, '/home/user/smartlist')

from main import load_open_positions, POSITIONS_FILE
import os

print("=" * 80)
print("🔍 تشخيص تحميل المراكز المفتوحة")
print("=" * 80)

# التحقق من وجود الملف
print(f"\n1. البحث عن الملف:")
print(f"   المسار المتوقع: {POSITIONS_FILE}")
print(f"   الملف موجود؟ {os.path.exists(POSITIONS_FILE)}")

if os.path.exists(POSITIONS_FILE):
    print(f"   حجم الملف: {os.path.getsize(POSITIONS_FILE)} بايت")

# قراءة الملف مباشرة
print(f"\n2. قراءة الملف مباشرة:")
try:
    with open(POSITIONS_FILE, 'r') as f:
        raw_data = json.load(f)
    print(f"   عدد الصفقات المفتوحة: {len(raw_data)}")
    for symbol in raw_data:
        print(f"   ✓ {symbol}")
except Exception as e:
    print(f"   ❌ خطأ: {e}")

# تحميل عبر الدالة
print(f"\n3. تحميل عبر الدالة load_open_positions():")
positions = load_open_positions()
print(f"   عدد الصفقات: {len(positions)}")

# التحقق من البنية
print(f"\n4. التحقق من بنية البيانات:")
if positions:
    first_symbol = list(positions.keys())[0]
    first_pos = positions[first_symbol]
    print(f"   أول صفقة: {first_symbol}")
    print(f"   المفاتيح الموجودة: {list(first_pos.keys())}")
    print(f"   القيم:")
    for key, val in first_pos.items():
        if key != 'progression':
            print(f"      {key}: {val}")

# التحقق من status
print(f"\n5. التحقق من حقل 'status':")
for symbol, pos in positions.items():
    status = pos.get("status", "NOT SET")
    print(f"   {symbol}: status = '{status}'")

print("\n" + "=" * 80)
