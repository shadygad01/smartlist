import yfinance as yf
import pandas as pd
import json
import os
from datetime import datetime, timedelta
from tqdm import tqdm
import time
import sqlite3

# ==================== EGX30 Symbols ====================
from config.scanner_config import get_constitutional_universe
EGX30_SYMBOLS = get_constitutional_universe()

def download_and_backfill():
    print("🚀 بدء تحميل بيانات EGX30 لآخر 5 سنين...")

    end_date = datetime.now()
    start_date = end_date - timedelta(days=5*365 + 200)

    all_data = {}
    
    for symbol in tqdm(EGX30_SYMBOLS, desc="تحميل البيانات"):
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(start=start_date, end=end_date, interval="1d")
            
            if df.empty:
                print(f"⚠️ {symbol} فارغ")
                continue
                
            df = df[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
            df.index = pd.to_datetime(df.index).tz_localize(None)
            
            # حفظ dividends للتعامل مع التوزيعات
            dividends = ticker.dividends
            if not dividends.empty:
                print(f"   → {symbol}: {len(dividends)} توزيعات")
            
            all_data[symbol] = df
            print(f"✓ {symbol}: {len(df)} يوم")
            time.sleep(1.2)
            
        except Exception as e:
            print(f"❌ {symbol}: {e}")

    # حفظ البيانات — must match the path used by extend_metrics.py and backfill_research_db.py
    os.makedirs("historical_data/historical_data", exist_ok=True)
    for symbol, df in all_data.items():
        df.index.name = "Date"
        df.to_csv(f"historical_data/historical_data/{symbol}.csv")
    
    print(f"\n✅ تم تحميل {len(all_data)} سهم بنجاح")
    return all_data

def run_system_backfill():
    print("\n🔄 جاري تشغيل Backfill Scripts الموجودة في الريبو...")
    
    # تشغيل السكريبتات الأصلية في الريبو (الأفضل)
    os.system("python build_history.py")
    os.system("python backfill_signal_log.py")
    os.system("python backfill_research_db.py")
    os.system("python backfill_positions.py")
    
    print("\n🔬 جاري تشغيل Self-Learning Reports...")
    os.system("python research_report.py")
    os.system("python edge_report.py")

if __name__ == "__main__":
    import sys
    download_only = "--download-only" in sys.argv

    print("="*60)
    print("          EGX30 Full Backfill + Forward Simulation")
    print("="*60)

    data = download_and_backfill()

    if not download_only:
        print("\n⚡ بدء توليد إشارات Early Buy / Buy (Forward Style)...")
        run_system_backfill()

        print("\n🎉 اكتمل العملية!")
        print("   - البيانات التاريخية محفوظة")
        print("   - الإشارات مسجلة في signal_log + research DB")
        print("   - التقارير الجديدة جاهزة (research_report + edge_report)")

        print("\nشغل دلوقتي:")
        print("python research_report.py")
