"""
اختبار مفصّل لسيناريو واحد مع عرض كل خطوة
Detailed test for single scenario showing every step
"""

def test_detailed():
    """Test one scenario step by step"""

    entry_price = 100
    prices = [100, 105, 110, 115, 120, 125, 130, 138, 142, 145, 150, 155, 160]

    # Calculate targets
    targets = [
        entry_price * 1.12,      # 12%
        entry_price * 1.236,     # 23.6%
        entry_price * 1.382,     # 38.2%
        entry_price * 1.50,      # 50%
        entry_price * 1.618,     # 61.8%
    ]

    print("\n" + "="*120)
    print("🔬 اختبار تفصيلي: محاكاة خطوة بخطوة")
    print("="*120)
    print(f"\n📌 سعر الدخول: {entry_price}")
    print(f"📊 البيانات: {prices}")
    print(f"\n🎯 الأهداف:")
    for i, t in enumerate(targets):
        pct = ((t - entry_price) / entry_price) * 100
        print(f"   [{i}] {pct:5.1f}% → {t:7.2f}")

    print(f"\n{'='*120}")
    print(f"{'اليوم':>6} | {'السعر':>8} | {'التارجت القديم':>15} | {'المستوى':>10} | {'التارجت الجديد':>15} | {'الحدث':>40}")
    print(f"{'='*120}")

    # Simulation
    current_target = targets[0]
    current_level = 0
    exit_done = False

    for day, price in enumerate(prices):
        old_target = current_target
        old_level = current_level

        # Step 1: Update target to highest level reached using max()
        print(f"   Day {day}: Price = {price}")

        # Check each Fibonacci level and track highest one reached
        best_level = current_level
        for i, fib_target in enumerate(targets):
            if price >= fib_target:
                best_level = max(best_level, i)
                if best_level != current_level:
                    print(f"      → Price {price} >= Target {fib_target:.2f} (Level {i})")

        current_level = best_level
        current_target = targets[current_level]

        # Show the line
        event = ''
        if current_level > old_level:
            event = f"⬆️ رفع التارجت من مستوى {old_level} إلى {current_level}"

        if price >= current_target and not exit_done:
            exit_done = True
            event += f" | ✅ خروج على التارجت"

        pct_profit = ((current_target - entry_price) / entry_price) * 100
        print(f'{day:6d} | {price:8.2f} | {old_target:15.2f} | L{current_level:8d} | {current_target:15.2f} | {event:>40}')

        if exit_done:
            break

    # Summary
    if exit_done:
        exit_profit = ((current_target - entry_price) / entry_price) * 100
        print(f"\n{'✅ نتيجة الاختبار:':>50}")
        print(f"  • السعر الذي وصل إليه: {price:.2f}")
        print(f"  • المستوى النهائي: {current_level} ({['12%', '23.6%', '38.2%', '50%', '61.8%'][current_level]})")
        print(f"  • التارجت النهائي: {current_target:.2f}")
        print(f"  • الأرباح: {exit_profit:.2f}%")
        print(f"  • اليوم: {day}")

    print("="*120 + "\n")


if __name__ == "__main__":
    test_detailed()
