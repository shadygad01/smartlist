"""
اختبار نظام الأهداف الديناميكية بفرض وجود صفقة شراء
Test Dynamic Target System with Forced Buy Position
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from backtest import BacktestEngine

def create_test_scenarios():
    """Create various price scenarios to test dynamic targets"""

    scenarios = [
        {
            'name': '📈 سيناريو 1: ارتفاع مستمر (60% صعود)',
            'description': 'السعر يصعد تدريجياً وبقوة',
            'prices': [100, 105, 110, 115, 120, 125, 130, 138, 142, 145, 150, 155, 160],
            'entry_day': 0,
            'entry_price': 100,
        },
        {
            'name': '📈 سيناريو 2: ارتفاع سريع ثم انهيار (60% صعود + 20% انهيار)',
            'description': 'السعر يرتفع بسرعة ثم ينهار',
            'prices': [100, 110, 125, 138, 150, 155, 160, 140, 120, 110, 105, 102],
            'entry_day': 0,
            'entry_price': 100,
        },
        {
            'name': '⚡ سيناريو 3: ارتفاع متقطع وقوي (40% صعود)',
            'description': 'السعر يصعد بشكل متقطع وآمن',
            'prices': [100, 102, 104, 108, 112, 115, 118, 125, 130, 135, 140],
            'entry_day': 0,
            'entry_price': 100,
        },
        {
            'name': '⬆️ سيناريو 4: ارتفاع بطيء ثم تسارع (50% صعود)',
            'description': 'ارتفاع بطيء في البداية ثم تسارع',
            'prices': [100, 101, 101.5, 102, 103, 105, 110, 115, 120, 130, 140, 150],
            'entry_day': 0,
            'entry_price': 100,
        },
        {
            'name': '⚠️ سيناريو 5: وصول لـ Fibonacci ثم انهيار (38.2% صعود)',
            'description': 'السعر يصل للـ 38.2% Fibonacci ثم ينهار',
            'prices': [100, 105, 110, 115, 120, 125, 130, 138.2, 135, 125, 115, 105],
            'entry_day': 0,
            'entry_price': 100,
        },
    ]

    return scenarios


def test_scenario(scenario):
    """Test a single scenario with forced buy position"""

    print(f"\n{'='*100}")
    print(f"{scenario['name']}")
    print(f"{'='*100}")
    print(f"📝 الوصف: {scenario['description']}")
    print(f"📊 البيانات: {scenario['prices']}\n")

    entry_price = scenario['entry_price']
    prices = scenario['prices']

    # Calculate Fibonacci targets
    targets = [
        entry_price * 1.12,      # 12%
        entry_price * 1.236,     # 23.6%
        entry_price * 1.382,     # 38.2%
        entry_price * 1.50,      # 50%
        entry_price * 1.618,     # 61.8%
    ]

    target_labels = ['12%', '23.6%', '38.2%', '50%', '61.8%']

    print(f"🎯 الأهداف المحسوبة:")
    for i, (target, label) in enumerate(zip(targets, target_labels)):
        print(f"   [{i}] {label:6} → {target:7.2f}")

    # Simulate dynamic target system
    print(f"\n📈 محاكاة حركة السعر:")
    print(f"{'اليوم':>6} | {'السعر':>7} | {'التارجت':>10} | {'المستوى':>8} | {'% الربح':>8} | {'الحالة':>30}")
    print(f"{'-'*100}")

    current_level = 0
    exit_price = None
    exit_day = None
    exit_reason = None

    for day, price in enumerate(prices):
        # Update to highest level reached
        for i, target in enumerate(targets):
            if price >= target:
                current_level = max(current_level, i)

        current_target = targets[current_level]
        profit_pct = ((current_target - entry_price) / entry_price) * 100

        status = ''

        # Check for exit
        if exit_price is None:
            if price >= current_target:
                exit_price = current_target
                exit_day = day
                exit_reason = 'target_hit'
                status = f'✅ خروج على التارجت'
            elif current_level > 0 and day > 0:
                # Check for weakness (simplified: if price moves down significantly)
                price_change = (price - prices[day-1]) / prices[day-1] * 100
                if price_change < -1.5:  # Strong downward movement
                    status = '⚠️ انهيار - احذر'

        if exit_price is None:
            print(f'{day:6d} | {price:7.2f} | {current_target:10.2f} | L{current_level} | {profit_pct:7.2f}% | {status:>30}')
        else:
            break

    # Summary
    print(f"\n{'📊 النتيجة النهائية:':>50}")
    print(f"{'-'*100}")

    if exit_price:
        exit_profit = ((exit_price - entry_price) / entry_price) * 100
        print(f"✅ الخروج:")
        print(f"   • السبب: {exit_reason}")
        print(f"   • اليوم: {exit_day}")
        print(f"   • سعر الخروج: {exit_price:.2f}")
        print(f"   • الأرباح: {exit_profit:.2f}%")
        if current_level < len(target_labels):
            print(f"   • المستوى: {target_labels[current_level]}")
        else:
            print(f"   • المستوى: {((targets[current_level] - entry_price) / entry_price) * 100:.1f}% (مستوى عالي)")
    else:
        print(f"❌ لم يتم الخروج من الصفقة")
        print(f"   • التارجت الحالي: {current_target:.2f}")
        print(f"   • السعر النهائي: {prices[-1]:.2f}")
        print(f"   • الأرباح المحتملة: {((prices[-1] - entry_price) / entry_price) * 100:.2f}%")

    return {
        'scenario': scenario['name'],
        'entry_price': entry_price,
        'exit_price': exit_price,
        'exit_day': exit_day,
        'max_price': max(prices),
        'final_price': prices[-1],
        'profit': ((exit_price - entry_price) / entry_price) * 100 if exit_price else None,
        'level': current_level,
    }


def main():
    """Run all scenarios"""

    print("\n" + "="*100)
    print("🧪 اختبار نظام الأهداف الديناميكية مع صفقات شراء مفروضة")
    print("="*100)

    scenarios = create_test_scenarios()
    results = []

    for scenario in scenarios:
        result = test_scenario(scenario)
        results.append(result)

    # Final summary
    print("\n\n" + "="*100)
    print("📊 ملخص جميع السيناريوهات")
    print("="*100)
    print(f"{'السيناريو':>40} | {'نتيجة':>10} | {'الأرباح':>8} | {'اليوم':>6}")
    print(f"{'-'*100}")

    for result in results:
        if result['exit_price']:
            status = '✅'
            profit_str = f"{result['profit']:.2f}%"
            day_str = f"{result['exit_day']}"
        else:
            status = '❌'
            profit_str = 'لم يخرج'
            day_str = '-'

        scenario_short = result['scenario'].split(':')[0][:35]
        print(f"{scenario_short:>40} | {status:>10} | {profit_str:>8} | {day_str:>6}")

    print("="*100)

    # Analysis
    successful = sum(1 for r in results if r['exit_price'])
    total_profit = sum(r['profit'] for r in results if r['profit'] is not None)
    avg_profit = total_profit / successful if successful > 0 else 0

    print(f"\n📈 التحليل:")
    print(f"   • عدد السيناريوهات: {len(results)}")
    print(f"   • الناجحة (خروج): {successful}/{len(results)}")
    print(f"   • إجمالي الأرباح: {total_profit:.2f}%")
    print(f"   • متوسط الربح للصفقة: {avg_profit:.2f}%")
    print("="*100 + "\n")


if __name__ == "__main__":
    main()
