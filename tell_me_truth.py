#!/usr/bin/env python3
"""قل لي الحقيقة بدون تفاصيل معقدة"""
import os
import json

print("\n🔍 الحقيقة بدون تعقيد:\n")

# 1. هل الملف موجود؟
if os.path.exists("open_positions.json"):
    size = os.path.getsize("open_positions.json")
    print(f"✅ الملف موجود - الحجم: {size} بايت")

    if size == 0:
        print("❌ لكنه **فارغ تماماً**!")
        print("\nهذا هو السبب - الملف لا يحتوي على أي بيانات!")
        exit(1)
    elif size < 50:
        print("⚠️  الملف صغير جداً - قد يكون فارغاً")

    # حاول قراءته
    try:
        with open("open_positions.json", "r") as f:
            data = json.load(f)

        if not data:
            print("❌ الملف فارغ ({})")
            print("\nهذا هو السبب - لا توجد بيانات!")
            exit(1)
        else:
            print(f"✅ الملف يحتوي على {len(data)} صفقات")

            # هل كلها مفتوحة؟
            open_count = sum(1 for p in data.values() if p.get("status") == "open")
            print(f"   منها {open_count} صفقات مفتوحة")

            if open_count == 0:
                print("\n❌ لا توجد صفقات مفتوحة!")
                print("لذلك لن تُعرض في الإيميل")
                exit(1)

            print(f"\n✅ يجب أن تظهر {open_count} صفقات في الإيميل")

    except json.JSONDecodeError:
        print("❌ الملف معطوب (JSON غير صحيح)")
        print("\nهذا هو السبب - البيانات غير صحيحة")
        exit(1)
else:
    print("❌ الملف غير موجود")
    print("\nهذا هو السبب - لا يوجد ملف!")
    exit(1)
