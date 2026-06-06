#!/usr/bin/env python3
"""إنشاء بيانات تجريبية للاختبار"""
import json
import os

print("\n" + "="*80)
print("📝 إنشاء بيانات تجريبية لاختبار النظام")
print("="*80 + "\n")

# البيانات التجريبية
positions = {
    "COMI.CA": {
        "entry_date": "2026-02-20T14:15:00+03:00",
        "entry_price": 38.20,
        "current_price": 52.67,
        "fib_targets": [42.79, 47.10, 52.67, 57.30, 62.93, 76.40, 114.60, 152.80],
        "current_level": 3,
        "target": 57.30,
        "status": "open"
    },
    "TMGH.CA": {
        "entry_date": "2026-03-10T09:45:00+03:00",
        "entry_price": 12.80,
        "current_price": 21.07,
        "fib_targets": [14.34, 15.76, 17.63, 19.20, 21.07, 25.60, 38.40, 51.20],
        "current_level": 5,
        "target": 25.60,
        "status": "open"
    },
    "ETEL.CA": {
        "entry_date": "2026-01-28T08:15:00+03:00",
        "entry_price": 2.45,
        "current_price": 3.68,
        "fib_targets": [2.75, 3.02, 3.38, 3.68, 4.03, 4.90, 7.35, 9.80],
        "current_level": 4,
        "target": 4.03,
        "status": "open"
    },
    "EGAL.CA": {
        "entry_date": "2026-02-05T10:50:00+03:00",
        "entry_price": 5.80,
        "current_price": 8.70,
        "fib_targets": [6.51, 7.17, 8.03, 8.70, 9.56, 11.60, 17.40, 23.20],
        "current_level": 4,
        "target": 9.56,
        "status": "open"
    },
    "EAST.CA": {
        "entry_date": "2026-03-22T14:30:00+03:00",
        "entry_price": 4.20,
        "current_price": 5.81,
        "fib_targets": [4.72, 5.19, 5.81, 6.30, 6.91, 8.40, 12.60, 16.80],
        "current_level": 3,
        "target": 6.30,
        "status": "open"
    },
    "ABUK.CA": {
        "entry_date": "2026-04-05T11:20:00+03:00",
        "entry_price": 32.50,
        "current_price": 45.95,
        "fib_targets": [36.46, 40.17, 45.95, 50.88, 55.57, 65.00, 97.50, 130.00],
        "current_level": 3,
        "target": 50.88,
        "status": "open"
    },
    "ORAS.CA": {
        "entry_date": "2026-01-08T09:20:00+03:00",
        "entry_price": 3.15,
        "current_price": 5.18,
        "fib_targets": [3.54, 3.89, 4.35, 4.73, 5.18, 6.30, 9.45, 12.60],
        "current_level": 5,
        "target": 6.30,
        "status": "open"
    },
    "EFIH.CA": {
        "entry_date": "2026-04-18T12:45:00+03:00",
        "entry_price": 2.10,
        "current_price": 2.60,
        "fib_targets": [2.36, 2.60, 2.91, 3.15, 3.46, 4.20, 6.30, 8.40],
        "current_level": 2,
        "target": 2.91,
        "status": "open"
    },
    "EFID.CA": {
        "entry_date": "2026-05-12T13:30:00+03:00",
        "entry_price": 28.75,
        "current_price": 35.60,
        "fib_targets": [32.23, 35.60, 40.61, 43.13, 47.13, 57.50, 86.25, 115.00],
        "current_level": 2,
        "target": 40.61,
        "status": "open"
    },
    "HRHO.CA": {
        "entry_date": "2026-05-28T15:45:00+03:00",
        "entry_price": 18.90,
        "current_price": 18.90,
        "fib_targets": [21.18, 23.38, 26.75, 29.35, 32.26, 37.80, 56.70, 75.60],
        "current_level": 0,
        "target": 21.18,
        "status": "open"
    }
}

# حفظ البيانات
file_path = "open_positions.json"

print(f"📝 كتابة البيانات إلى {file_path}...")
print(f"   • عدد الصفقات: {len(positions)}")

try:
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(positions, f, indent=2, ensure_ascii=False)

    file_size = os.path.getsize(file_path)
    print(f"✅ تم الحفظ بنجاح")
    print(f"   • حجم الملف: {file_size} بايت")

    # التحقق
    with open(file_path, "r", encoding="utf-8") as f:
        verify = json.load(f)

    print(f"\n✅ تم التحقق:")
    print(f"   • عدد الصفقات المحفوظة: {len(verify)}")

    open_count = sum(1 for p in verify.values() if p.get("status") == "open")
    print(f"   • صفقات مفتوحة: {open_count}")

    print(f"\n✅ البيانات جاهزة للاختبار!")
    print(f"\n   الآن الإيميل يجب أن يعرض جدول يحتوي على {open_count} صفقات")

except Exception as e:
    print(f"❌ خطأ: {e}")
    exit(1)

print("\n" + "="*80 + "\n")
