#!/usr/bin/env python3
"""
اختبار يدوي للـ daily_scan - نفس ما يحدث في الساعة 8:30 صباحاً
"""
import sys
sys.path.insert(0, '/home/user/smartlist')

from main import daily_scan

print("\n" + "="*100)
print("🧪 اختبار يدوي: تشغيل daily_scan (نفس ما يحدث في 8:30 صباحاً)")
print("="*100 + "\n")

try:
    daily_scan()
    print("\n" + "="*100)
    print("✅ daily_scan تم تنفيذها بنجاح!")
    print("="*100 + "\n")
except Exception as e:
    print(f"\n❌ خطأ أثناء التنفيذ:")
    print(f"   {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
