#!/usr/bin/env python3
"""اختبار رسالة Telegram"""
import sys
sys.path.insert(0, '/home/user/smartlist')

from main import build_report, load_open_positions, STOCKS, NAMES, FIB_LABELS, now_cairo
import os

print("=" * 100)
print("📱 اختبار رسالة Telegram")
print("=" * 100)

# تحميل البيانات والنتائج
positions = load_open_positions()
html_content, results = build_report(holiday_mode=False)

print(f"\n✅ تم تحميل {len(positions)} صفقة")

# تجميع الأسهم المؤهلة (مثل الدالة الحقيقية)
alerts = [
    (s, results[s])
    for s in STOCKS
    if results[s].get("ok") and results[s].get("score", 0) >= 35
]

print(f"✅ عدد الأسهم المؤهلة (score >= 35): {len(alerts)}")

# إذا لم توجد أسهم مؤهلة، نعرض رسالة بدون أسهم
if not alerts:
    print("\n📊 لا توجد أسهم مؤهلة اليوم - سيتم عرض المراكز المفتوحة فقط")

    msg = f"📊 *EGX Daily Scan — {now_cairo().strftime('%d %b %Y')}*\n"
    msg += "No stocks reached the Watch threshold (≥35) today."

    if positions:
        open_positions_list = [(sym, pos) for sym, pos in positions.items() if pos.get("status") == "open"]
        if open_positions_list:
            msg += f"\n\n📊 *المراكز المفتوحة: {len(open_positions_list)}*"

            print(f"\n📌 المراكز المفتوحة ({len(open_positions_list)}):")
            print("-" * 100)

            for sym, pos in open_positions_list:
                entry = pos["entry_price"]
                tgt = pos["target"]

                # حاول الحصول على السعر
                if sym in results and results[sym].get("ok"):
                    cur_price = results[sym].get("price", "—")
                elif "current_price" in pos:
                    cur_price = pos["current_price"]
                else:
                    cur_price = "—"

                pnl = "—"
                if cur_price != "—":
                    try:
                        pnl_pct = ((float(cur_price) - entry) / entry * 100)
                        pnl = f"+{pnl_pct:.1f}%" if pnl_pct >= 0 else f"{pnl_pct:.1f}%"
                    except:
                        pass

                line = f"   • {NAMES.get(sym, sym)}: {entry:.2f} → {tgt:.2f} EGP ({pnl})"
                print(line)
                msg += f"\n{line}"

    print("\n" + "=" * 100)
    print("📨 الرسالة كاملة:")
    print("=" * 100)
    print(msg)

else:
    print(f"\n✅ توجد {len(alerts)} أسهم مؤهلة")

    # بناء الرسالة مثل الدالة الحقيقية
    date_str = now_cairo().strftime("%d %b %Y")
    lines = [f"📊 *EGX Daily Scan — {date_str}*\n_{len(alerts)} stock(s) above threshold_"]

    # إضافة قسم المراكز المفتوحة
    open_positions_list = [(s, p) for s, p in positions.items() if p.get("status") == "open"]
    if open_positions_list:
        lines.append("\n━━━━━━━━━━━━━━━━━━━━━")
        lines.append("📊 *المراكز المفتوحة*")

        print(f"\n📌 المراكز المفتوحة ({len(open_positions_list)}):")
        print("-" * 100)

        for sym, pos in open_positions_list:
            entry = pos["entry_price"]
            tgt = pos["target"]
            lvl = FIB_LABELS.get(pos.get("current_level", 0), "")

            # حاول الحصول على السعر
            if sym in results and results[sym].get("ok"):
                cur_price = results[sym].get("price", "—")
            elif "current_price" in pos:
                cur_price = pos["current_price"]
            else:
                cur_price = "—"

            if cur_price != "—":
                try:
                    pnl_pct = ((float(cur_price) - entry) / entry * 100)
                    pnl = f"+{pnl_pct:.1f}%" if pnl_pct >= 0 else f"{pnl_pct:.1f}%"
                except:
                    pnl = "—"
            else:
                pnl = "—"

            line = f"   {NAMES.get(sym, sym)}: {entry:.2f} → *{tgt:.2f}* EGP ({pnl}) {lvl}"
            print(line)
            lines.append(line)

        lines.append("━━━━━━━━━━━━━━━━━━━━━\n")

    full_msg = "\n".join(lines)

    print("\n" + "=" * 100)
    print("📨 الرسالة كاملة (أول 1500 حرف):")
    print("=" * 100)
    print(full_msg[:1500])

print("\n" + "=" * 100)
print("✅ الرسالة جاهزة للإرسال عبر Telegram")
print("=" * 100)
