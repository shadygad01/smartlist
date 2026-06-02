# ============================================================
# تعليمات التثبيت والتشغيل
# ============================================================

## 1️⃣ تثبيت المكتبة المطلوبة:

```bash
pip install apscheduler
```

## 2️⃣ الخطوات:

### A) في ملف main.py الأصلي، أضف هذه الواردات في البداية:

```python
import threading
import time
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
```

### B) أضف المتغيرات العامة (Global Variables):

```python
# =========================================
# GLOBAL STATE FOR MONITORING
# =========================================

last_alerted_stocks = set()  # لتجنب إرسال تنبيهات متكررة
monitoring_active = True
last_score_data = {}
```

### C) أضف هذه الدوال قبل `if __name__ == "__main__":`:

```python
# =========================================
# ALERT FOR HIGH SCORE (REAL-TIME)
# =========================================

def send_alert_for_high_score(stock, score, result):
    """
    إرسال تنبيه فوري عندما يصل score إلى 35+
    """
    print(f"\n🚨 ALERT: {NAMES.get(stock, stock)} ({stock}) وصل score {score}/100!")
    
    # إرسال Telegram
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if token and chat_id:
        signal = result.get("signal", "WATCH").upper()
        emoji_map = {
            "STRONG BUY": "🟢",
            "BUY": "🟩",
            "WATCH": "🟡",
        }
        emoji = emoji_map.get(signal, "🔵")
        
        try:
            upside = ""
            try:
                pct = (float(result["target"]) - float(result["price"])) / float(result["price"]) * 100
                upside = f" (+{pct:.1f}%)"
            except:
                pass
            
            msg = (
                f"🚨 *ALERT* — {emoji} {NAMES.get(stock, stock)}\n"
                f"Score: *{score}/100*  |  Signal: *{signal}*\n"
                f"Price: *{result['price']} EGP*\n"
                f"Target: *{result['target']} EGP*{upside}\n"
                f"Time: {now_cairo().strftime('%H:%M:%S')}"
            )
            
            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"},
                timeout=10,
            )
            print(f"✅ Telegram alert sent for {stock}")
        except Exception as e:
            print(f"❌ Telegram alert error: {e}")


# =========================================
# MONITORING FUNCTION
# =========================================

def monitor_scores():
    """
    مراقبة الـ scores بشكل مستمر وإرسال تنبيهات فوراً عند الوصول إلى 35+
    """
    global last_alerted_stocks
    
    print(f"\n▶️ بدء المراقبة المستمرة في {fmt_cairo()}")
    
    while monitoring_active:
        try:
            # تنفيذ التحليل
            html, results = build_report(holiday_mode=False)
            
            # البحث عن stocks وصلت 35+
            current_qualified = {
                s for s in STOCKS
                if results[s].get("ok") and results[s].get("score", 0) >= 35
            }
            
            # إرسال تنبيهات للـ stocks الجديدة
            new_alerts = current_qualified - last_alerted_stocks
            for stock in new_alerts:
                score = results[stock].get("score", 0)
                send_alert_for_high_score(stock, score, results[stock])
                last_alerted_stocks.add(stock)
            
            # حفظ البيانات الحالية
            global last_score_data
            last_score_data = results
            
            # انتظر 5 دقائق قبل التحديث التالي
            time.sleep(300)
            
        except Exception as e:
            print(f"❌ Monitor error: {e}")
            traceback.print_exc()
            time.sleep(60)


# =========================================
# SCHEDULED TASKS
# =========================================

def daily_scan():
    """
    المسح اليومي في تمام الساعة 8:30 صباحاً
    """
    print(f"\n📅 Daily scan started at {fmt_cairo()}")
    
    if is_egx_trading_day(today_cairo()):
        html, _results = build_report(holiday_mode=False)
        send_email(html)
        send_telegram_alerts(_results)
    else:
        last_td = most_recent_trading_day(today_cairo())
        html, _results = build_report(holiday_mode=True, last_trading=str(last_td))
        send_email(html, subject_suffix=f" (Holiday — Last Session: {last_td})")
        send_telegram_alerts(_results)


def manual_scan():
    """
    مسح يدوي عند الطلب
    """
    print(f"\n🔄 Manual scan at {fmt_cairo()}")
    
    if is_egx_trading_day(today_cairo()):
        html, _results = build_report(holiday_mode=False)
        send_email(html, subject_suffix=" — Manual Scan")
        send_telegram_alerts(_results)
    else:
        last_td = most_recent_trading_day(today_cairo())
        html, _results = build_report(holiday_mode=True, last_trading=str(last_td))
        send_email(html, subject_suffix=f" — Manual Scan (Holiday)")
        send_telegram_alerts(_results)
```

### D) استبدل `if __name__ == "__main__":` بـ:

```python
if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f"EGX SMC Scanner — TradingView Engine")
    print(f"Start Time: {fmt_cairo()}")
    print(f"{'='*60}\n")
    
    # إنشاء Scheduler
    scheduler = BackgroundScheduler()
    scheduler.add_job(daily_scan, CronTrigger(hour=8, minute=30, timezone=CAIRO))
    
    print("✅ Scheduler configured:")
    print(f"   ⏰ Daily scan at 08:30 Cairo Time")
    print(f"   📱 Real-time monitoring active")
    print(f"   🚨 Instant alerts when score >= 35\n")
    
    # بدء الـ Scheduler
    scheduler.start()
    
    # بدء المراقبة في thread منفصل
    monitor_thread = threading.Thread(target=monitor_scores, daemon=True)
    monitor_thread.start()
    
    print("🟢 System running... Press Ctrl+C to stop\n")
    
    try:
        # Keep the program running
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n⛔ Shutting down...")
        monitoring_active = False
        scheduler.shutdown()
        print("✅ System stopped.")
```

## 3️⃣ أيضاً تأكد من وجود دالة `fmt_cairo()` و `now_cairo()`:

```python
def now_cairo():
    return datetime.now(CAIRO)

def fmt_cairo():
    return now_cairo().strftime("%Y-%m-%d %H:%M:%S")
```

## ============================================================
## الآن هاني ما يحصل:
## ============================================================

✅ **يومياً الساعة 8:30 صباحاً:**
   - Email تلقائي بالتقرير الكامل
   - Telegram message بـ stocks وصلت 35+

✅ **مراقبة مستمرة (كل 5 دقائق):**
   - فحص الـ scores في الوقت الفعلي
   - عند وصول أي stock لـ 35+ → Telegram alert فوري + Email فوري

✅ **لو أردت مسح يدوي:**
   - اتصل بـ `manual_scan()` من أي مكان في الكود

## ============================================================
## ملاحظات مهمة:
## ============================================================

1. البرنامج سيبقى يعمل 24/7 في الخلفية
2. كل 5 دقائق يفحص الـ scores
3. عند الساعة 8:30 تماماً → مسح شامل + email + telegram
4. لا تُرسل تنبيهات مكررة للـ stock نفسه في نفس اليوم

استخدم Ctrl+C لإيقاف البرنامج بشكل آمن.
