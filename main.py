import smtplib
import os
import json
import pandas as pd
import numpy as np
import yfinance as yf
import requests
import traceback
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

CAIRO = ZoneInfo("Africa/Cairo")

# =========================================
# CONFIG
# =========================================

STOCKS = [
    "COMI.CA", "TMGH.CA", "ETEL.CA", "EGAL.CA",
    "EAST.CA", "ABUK.CA", "ORAS.CA", "EFIH.CA",
    "ADIB.CA", "FWRY.CA", "EMFD.CA", "PHDC.CA",
    "ORHD.CA", "EFID.CA", "HRHO.CA", "JUFO.CA",
    "BTFH.CA", "RAYA.CA", "GBCO.CA", "HELI.CA",
    "ARCC.CA", "MCQE.CA", "ORWE.CA", "ISPH.CA",
    "RMDA.CA", "OIH.CA", "CCAP.CA",
]

WHITELIST = [
    "FWRY.CA", "EAST.CA", "ETEL.CA", "EMFD.CA",
    "PHDC.CA", "HRHO.CA", "MCQE.CA", "OIH.CA", "GBCO.CA",
]

NAMES = {
    "COMI.CA": "Commercial International Bank",
    "TMGH.CA": "Talaat Moustafa Group",
    "ETEL.CA": "Telecom Egypt",
    "EGAL.CA": "Egyptian Gulf Bank",
    "EAST.CA": "Eastern Company",
    "ABUK.CA": "Abu Qir Fertilizers",
    "ORAS.CA": "Orascom Construction PLC",
    "EFIH.CA": "EFG Hermes Holding",
    "ADIB.CA": "Abu Dhabi Islamic Bank Egypt",
    "FWRY.CA": "Fawry for Banking Technology",
    "EMFD.CA": "Egypt Foods Group",
    "PHDC.CA": "Palm Hills Developments",
    "ORHD.CA": "Orascom Development Egypt",
    "EFID.CA": "EFG Finance",
    "HRHO.CA": "Hermes Financial Group",
    "JUFO.CA": "Juhayna Food Industries",
    "BTFH.CA": "Beltone Financial Holding",
    "RAYA.CA": "Raya Holding",
    "GBCO.CA": "GB Auto",
    "HELI.CA": "Heliopolis Housing",
    "ARCC.CA": "Arabian Cement Company",
    "MCQE.CA": "Macro Group Pharmaceuticals",
    "ORWE.CA": "Oriental Weavers",
    "ISPH.CA": "Integrated Diagnostics Holdings",
    "RMDA.CA": "Rameda Pharmaceutical",
    "OIH.CA": "Olympic Industries Holding",
    "CCAP.CA": "Cairo Capital Holding",
}

EMAIL = "shady.gad@live.com"

# =========================================
# UTILITY FUNCTIONS
# =========================================

def now_cairo():
    """الوقت الحالي بتوقيت القاهرة"""
    return datetime.now(CAIRO)

def fmt_cairo():
    """تنسيق الوقت الحالي"""
    return now_cairo().strftime("%Y-%m-%d %H:%M:%S %Z")

def get_hour_minute():
    """الساعة والدقيقة الحالية"""
    now = now_cairo()
    return now.hour, now.minute

# =========================================
# PARALLEL DATA FETCHING
# =========================================

def fetch_stock_data(ticker, period="60d"):
    """جلب بيانات سهم واحد (بدون sequential delays)"""
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period=period, interval="1d", auto_adjust=False)
        
        if hist.empty or len(hist) < 20:
            return None
        
        hist = hist.dropna(subset=["Close"])
        return {
            "ticker": ticker,
            "data": hist,
            "error": None
        }
    except Exception as e:
        print(f"  ⚠️  {ticker}: {str(e)[:50]}")
        return None

def fetch_all_stocks_parallel(max_workers=6):
    """جلب كل الأسهم بشكل متوازي (سريع جداً)"""
    print(f"📊 جلب {len(STOCKS)} سهم (متوازي)...")
    start = time.time()
    
    stock_data = {}
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(fetch_stock_data, ticker): ticker 
            for ticker in STOCKS
        }
        
        completed = 0
        for future in as_completed(futures):
            try:
                result = future.result(timeout=30)
                if result:
                    stock_data[result["ticker"]] = result["data"]
                    completed += 1
            except Exception as e:
                pass
        
        elapsed = time.time() - start
        print(f"✅ تم جلب {completed}/{len(STOCKS)} سهم في {elapsed:.1f}ث\n")
    
    return stock_data

# =========================================
# DUMMY SCANNING LOGIC
# (استبدل بـ logic الـ SMC الأصلي بتاعك)
# =========================================

def scan_stocks(stock_data):
    """
    فحص الأسهم وحساب الـ scores والإشارات
    
    ⚠️ استبدل الـ placeholder بـ logic الـ SMC الأصلي بتاعك:
    - calculate_price_position()
    - calculate_order_block()
    - calculate_liquidity()
    - calculate_htf_structure()
    - calculate_anchored_vwap()
    - calculate_macd()
    - calculate_divergence()
    """
    results = {}
    
    for ticker in STOCKS:
        if ticker not in stock_data:
            continue
        
        hist = stock_data[ticker]
        
        # 🔴 PLACEHOLDER - استبدل بـ logic الأصلي:
        # ─────────────────────────────────────────────────────────
        # price_pos = calculate_price_position(hist)
        # ob_quality = calculate_order_block(hist)
        # liquidity = calculate_liquidity(hist)
        # htf_struct = calculate_htf_structure(hist)
        # avwap_val = calculate_anchored_vwap(hist)
        # macd_val = calculate_macd(hist)
        # divergence = calculate_divergence(hist)
        #
        # score = (price_pos * 0.35 + ob_quality * 0.20 + 
        #          liquidity * 0.15 + htf_struct * 0.12 +
        #          avwap_val * 0.10 + macd_val * 0.05 +
        #          divergence * 0.03)
        #
        # signal = ("INSTITUTIONAL BUY" if score >= 85 else
        #           "STRONG BUY" if score >= 70 else
        #           "BUY" if score >= 55 else
        #           "IGNORE" if score < 35 else "BUY")
        # ─────────────────────────────────────────────────────────
        
        # مؤقتاً (test purposes):
        score = np.random.randint(20, 95)
        signal = np.random.choice(["IGNORE", "BUY", "STRONG BUY", "INSTITUTIONAL BUY"])
        
        price = hist["Close"].iloc[-1]
        target = price * np.random.uniform(1.1, 1.5)
        
        results[ticker] = {
            "ticker": ticker,
            "name": NAMES.get(ticker, ticker),
            "score": score,
            "signal": signal,
            "price": price,
            "target": target,
            "is_whitelist": ticker in WHITELIST,
        }
    
    return results

def get_changed_stocks(current_results):
    """
    مقارنة النتائج الحالية مع السابقة
    ترجع الأسهم اللي تغيرت **إلى** BUY من IGNORE أو signals أخرى
    
    المنطق:
    - أول الأسهم اللي signal بتاعتها = BUY أو أعلى
    - مقارنة مع last_scores.json
    - إذا كانت last_signal ليست BUY → إذن تغيرت!
    """
    
    # جرب قراءة النتائج السابقة
    try:
        with open("last_scores.json", "r") as f:
            last_results = json.load(f)
    except:
        last_results = {}
    
    # احفظ النتائج الحالية للمرة القادمة
    try:
        with open("last_scores.json", "w") as f:
            # احفظ فقط البيانات المطلوبة
            to_save = {
                ticker: {
                    "signal": data["signal"],
                    "score": data["score"]
                }
                for ticker, data in current_results.items()
            }
            json.dump(to_save, f)
    except Exception as e:
        print(f"⚠️ خطأ حفظ last_scores.json: {e}")
    
    # ابحث عن التغييرات إلى BUY
    changed = []
    buy_signals = ["BUY", "STRONG BUY", "INSTITUTIONAL BUY"]
    
    for ticker, current in current_results.items():
        # هل الإشارة الحالية BUY أو أعلى؟
        if current["signal"] in buy_signals:
            # ما الإشارة السابقة؟
            last_signal = last_results.get(ticker, {}).get("signal", "IGNORE")
            
            # إذا كانت السابقة ليست BUY → تغيير جديد!
            if last_signal not in buy_signals:
                changed.append(current)
    
    return changed

# =========================================
# EMAIL FUNCTIONS
# =========================================

def send_daily_report(results):
    """
    إرسال التقرير اليومي الساعة 8:30 صباحاً
    (كل الأسهم بغض النظر عن الإشارة)
    """
    sender = os.getenv("EMAIL_USER")
    password = os.getenv("EMAIL_PASS")
    
    if not sender or not password:
        print("❌ بيانات البريد ناقصة")
        return False
    
    # بناء الـ HTML
    html_body = f"""
    <html>
    <body style="direction: rtl; font-family: Arial, sans-serif; background: #f5f5f5;">
    <div style="max-width: 800px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px;">
    
    <h2 style="color: #1976d2; text-align: center;">📊 التقرير اليومي - EGX SMC Scanner</h2>
    <p style="text-align: center; color: #666;">التاريخ: {now_cairo().strftime('%Y-%m-%d %H:%M')} — توقيت القاهرة</p>
    <hr>
    
    <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
    <thead>
    <tr style="background: #1976d2; color: white;">
        <th style="padding: 10px; text-align: right;">السهم</th>
        <th style="padding: 10px; text-align: center;">الإشارة</th>
        <th style="padding: 10px; text-align: center;">الـ Score</th>
        <th style="padding: 10px; text-align: center;">السعر الحالي</th>
        <th style="padding: 10px; text-align: center;">السعر المستهدف</th>
    </tr>
    </thead>
    <tbody>
    """
    
    for ticker, data in sorted(results.items(), key=lambda x: x[1]["score"], reverse=True):
        signal_color = {
            "INSTITUTIONAL BUY": "#2e7d32",
            "STRONG BUY": "#d32f2f",
            "BUY": "#f57c00",
            "IGNORE": "#999",
        }.get(data["signal"], "#999")
        
        is_whitelist = "⭐" if data["is_whitelist"] else ""
        
        html_body += f"""
        <tr style="border-bottom: 1px solid #ddd;">
            <td style="padding: 10px; text-align: right; font-weight: bold;">{is_whitelist} {data["name"]}</td>
            <td style="padding: 10px; text-align: center; color: {signal_color}; font-weight: bold;">{data["signal"]}</td>
            <td style="padding: 10px; text-align: center;">{data["score"]:.1f}</td>
            <td style="padding: 10px; text-align: center;">{data["price"]:.2f} EGP</td>
            <td style="padding: 10px; text-align: center;">{data["target"]:.2f} EGP</td>
        </tr>
        """
    
    html_body += """
    </tbody>
    </table>
    
    <hr style="margin-top: 20px;">
    <p style="color: #666; font-size: 12px; text-align: center;">
    EGX Smart Money Concepts Scanner © 2026<br>
    تنبيهات تلقائية يومياً الساعة 8:30 صباحاً
    </p>
    
    </div>
    </body>
    </html>
    """
    
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📊 التقرير اليومي — {now_cairo().strftime('%d/%m/%Y')}"
    msg["From"] = sender
    msg["To"] = EMAIL
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as srv:
            srv.ehlo()
            srv.starttls()
            srv.login(sender, password)
            srv.sendmail(sender, EMAIL, msg.as_string())
        print(f"✅ تم إرسال التقرير اليومي")
        return True
    except Exception as e:
        print(f"❌ خطأ في الإرسال: {e}")
        return False

def send_buy_alert(changed_stocks):
    """
    إرسال تنبيه فوري عند ظهور BUY
    (من 9 صباحاً إلى 2:30 مساءً فقط)
    """
    if not changed_stocks:
        print("⏭️  لا توجد إشارات BUY جديدة")
        return True
    
    sender = os.getenv("EMAIL_USER")
    password = os.getenv("EMAIL_PASS")
    
    if not sender or not password:
        print("❌ بيانات البريد ناقصة")
        return False
    
    # بناء الـ HTML للتنبيه الفوري
    html_body = f"""
    <html>
    <body style="direction: rtl; font-family: Arial, sans-serif; background: #fff3e0;">
    <div style="max-width: 600px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; border-left: 4px solid #d32f2f;">
    
    <h2 style="color: #d32f2f; text-align: center;">🚨 تنبيه BUY فوري!</h2>
    <p style="text-align: center; color: #666;">الوقت: {now_cairo().strftime('%H:%M:%S')} — {now_cairo().strftime('%Y-%m-%d')}</p>
    <hr>
    """
    
    for stock in changed_stocks:
        whitelist_badge = "⭐ WHITELIST ⭐" if stock["is_whitelist"] else ""
        html_body += f"""
        <div style="background: #f5f5f5; padding: 15px; margin: 10px 0; border-radius: 4px; border-right: 3px solid #d32f2f;">
            <h3 style="color: #d32f2f; margin: 0;">{stock["name"]} {whitelist_badge}</h3>
            <p style="margin: 5px 0;"><strong>الإشارة:</strong> {stock["signal"]}</p>
            <p style="margin: 5px 0;"><strong>الـ Score:</strong> {stock["score"]:.1f}</p>
            <p style="margin: 5px 0;"><strong>السعر الحالي:</strong> <span style="color: #d32f2f; font-weight: bold;">{stock["price"]:.2f} EGP</span></p>
            <p style="margin: 5px 0;"><strong>السعر المستهدف:</strong> <span style="color: #2e7d32; font-weight: bold;">{stock["target"]:.2f} EGP</span></p>
        </div>
        """
    
    html_body += """
    <hr style="margin-top: 20px;">
    <p style="color: #666; font-size: 11px; text-align: center;">
    هذا تنبيه تلقائي من EGX Smart Money Concepts Scanner<br>
    التنبيهات الفورية: من 9 صباحاً إلى 2:30 مساءً يومياً
    </p>
    
    </div>
    </body>
    </html>
    """
    
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🚨 تنبيه BUY فوري — {len(changed_stocks)} سهم — {now_cairo().strftime('%H:%M')}"
    msg["From"] = sender
    msg["To"] = EMAIL
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as srv:
            srv.ehlo()
            srv.starttls()
            srv.login(sender, password)
            srv.sendmail(sender, EMAIL, msg.as_string())
        print(f"✅ تم إرسال تنبيه BUY ({len(changed_stocks)} سهم)")
        return True
    except Exception as e:
        print(f"❌ خطأ في الإرسال: {e}")
        return False

# =========================================
# MAIN MODES
# =========================================

def daily_scan():
    """
    🔔 الوضع اليومي - الساعة 8:30 صباحاً
    يرسل تقرير كامل لكل الأسهم بغض النظر عن الإشارة
    """
    print(f"\n{'='*60}")
    print(f"📊 الفحص اليومي (8:30 AM)")
    print(f"{'='*60}\n")
    
    # جلب البيانات
    stock_data = fetch_all_stocks_parallel(max_workers=6)
    if not stock_data:
        print("❌ فشل جلب البيانات!")
        return False
    
    # فحص الأسهم
    print("🔍 فحص الأسهم...")
    results = scan_stocks(stock_data)
    
    # إرسال التقرير اليومي
    print("\n📧 إرسال التقرير اليومي...")
    success = send_daily_report(results)
    
    print(f"\n{'='*60}")
    print(f"✅ انتهى الفحص اليومي")
    print(f"{'='*60}\n")
    
    return success

def intraday_alert():
    """
    📈 الوضع خلال التداول (9 AM - 2:30 PM)
    يفتش الأسهم وإذا ظهرت BUY جديدة → يرسل تنبيه فوري
    """
    hour, minute = get_hour_minute()
    
    # تحقق من الوقت (9 AM - 2:30 PM Cairo)
    if not (9 <= hour < 15):  # 9:00 - 14:59
        print(f"⏳ وقت خارج ساعات التنبيهات الفورية ({hour}:{minute:02d})")
        print("   التنبيهات الفورية: من 9:00 صباحاً إلى 2:30 مساءً")
        return True
    
    print(f"\n{'='*60}")
    print(f"📈 فحص التنبيهات الفورية ({hour}:{minute:02d} AM)")
    print(f"{'='*60}\n")
    
    # جلب البيانات
    stock_data = fetch_all_stocks_parallel(max_workers=6)
    if not stock_data:
        print("❌ فشل جلب البيانات!")
        return False
    
    # فحص الأسهم
    print("🔍 فحص الأسهم...")
    results = scan_stocks(stock_data)
    
    # البحث عن إشارات BUY جديدة
    changed = get_changed_stocks(results)
    
    # إرسال التنبيهات
    if changed:
        print(f"\n⚠️  وجدت {len(changed)} سهم جديد مع BUY!\n")
        success = send_buy_alert(changed)
    else:
        print("⏭️  لا توجد إشارات BUY جديدة")
        success = True
    
    print(f"\n{'='*60}")
    print(f"✅ انتهى الفحص الفوري")
    print(f"{'='*60}\n")
    
    return success

def manual_scan():
    """
    🔧 الوضع اليدوي - في أي وقت بدون شروط
    يفحص الأسهم ويرسل تقرير فوراً
    """
    print(f"\n{'='*60}")
    print(f"🔧 الفحص اليدوي (بدون شروط)")
    print(f"{'='*60}\n")
    
    # جلب البيانات
    stock_data = fetch_all_stocks_parallel(max_workers=6)
    if not stock_data:
        print("❌ فشل جلب البيانات!")
        return False
    
    # فحص الأسهم
    print("🔍 فحص الأسهم...")
    results = scan_stocks(stock_data)
    
    # إرسال التقرير اليومي
    print("\n📧 إرسال التقرير...")
    success = send_daily_report(results)
    
    print(f"\n{'='*60}")
    print(f"✅ انتهى الفحص اليدوي")
    print(f"{'='*60}\n")
    
    return success

# =========================================
# ENTRY POINT
# =========================================

if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f"EGX SMC Scanner")
    print(f"الوقت: {fmt_cairo()}")
    print(f"{'='*60}")
    
    try:
        # تحديد الوضع
        hour, minute = get_hour_minute()
        
        # الوضع اليومي: 8:30 AM بالضبط
        if hour == 8 and 25 <= minute <= 35:
            success = daily_scan()
        
        # الوضع الفوري: 9 AM - 2:30 PM
        elif 9 <= hour < 15:
            success = intraday_alert()
        
        # الوضع اليدوي
        else:
            success = manual_scan()
        
        sys.exit(0 if success else 1)
    
    except Exception as e:
        print(f"\n❌ خطأ: {e}")
        traceback.print_exc()
        sys.exit(1)
