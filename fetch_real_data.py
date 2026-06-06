#!/usr/bin/env python3
"""
جلب البيانات الحقيقية من TradingView للأسهم المصرية
"""
import sys
sys.path.insert(0, '/home/user/smartlist')

from main import STOCKS, NAMES, TV_SYMBOLS
from datetime import datetime, timedelta
import json

print("=" * 80)
print("📊 جلب البيانات الحقيقية للأسهم المصرية من يناير إلى يونيو 2026")
print("=" * 80)

# الأسهم التي نريد بيانات عنها
target_stocks = [
    ("ORAS", "أوراسكوم"),
    ("EBANK", "البنك الأهلي"),
    ("ETEL", "اتصالات مصر"),
    ("EGAL", "الألومنيوم المصرية"),
    ("COMI", "البنك التجاري الدولي"),
    ("TMGH", "مجموعة طلعت مصطفى"),
    ("EAST", "الشركة الشرقية"),
    ("ABUK", "أبو قير الأسمدة"),
    ("EFIH", "إيجيفايننس"),
    ("EFID", "عديتا للصناعات الغذائية"),
    ("HRHO", "EFG Holding"),
]

print("\n📍 الأسهم المطلوب جلب بيانات عنها:")
for symbol, name in target_stocks:
    print(f"   • {symbol}: {name}")

print("\n" + "=" * 80)
print("🔍 البحث عن الأسعار من خلال المتغيرات المعرفة في النظام:")
print("=" * 80)

# عرض الرموز المعروفة
for stock in target_stocks:
    symbol = stock[0]
    if symbol in STOCKS:
        tv_symbol = TV_SYMBOLS.get(symbol, f"{symbol}.CA")
        name = NAMES.get(symbol, stock[1])
        print(f"✅ {symbol}: {name}")
        print(f"   TradingView Symbol: {tv_symbol}")

print("\n" + "=" * 80)
print("📈 ملاحظة مهمة:")
print("=" * 80)
print("""
نحن في بيئة اختبار تحتوي على تحديدات شبكة (HTTP 403).
للحصول على بيانات حقيقية، نحتاج إلى:

1️⃣  استخدام بيانات من قاعدة بيانات مخزنة مسبقاً
2️⃣  استخدام API غير مقيد (إذا أمكن)
3️⃣  تنزيل البيانات يدويًا من TradingView

🌐 الحل الموصى به:
  - الانتظار حتى بيئة الإنتاج
  - استخدام واجهة برمجة تطبيقات TradingView الخاصة بنا
  - أو تحديث البيانات يدويًا من الموقع الرسمي
""")

print("=" * 80)
print("📝 للحصول على البيانات الحقيقية، الرجاء:")
print("=" * 80)
print("""
1. اذهب إلى https://tradingview.com
2. ابحث عن كل سهم (مثل EBANK.CA)
3. تحقق من أسعار الإغلاق اليومية من 1/1/2026 إلى 6/6/2026
4. انسخ البيانات في open_positions.json و positions_history.json

الأسهم المصرية على TradingView:
""")

for symbol, name in target_stocks:
    tv_symbol = TV_SYMBOLS.get(symbol, f"{symbol}.CA")
    print(f"   • {tv_symbol}: {name}")
