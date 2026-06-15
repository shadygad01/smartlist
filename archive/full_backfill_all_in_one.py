import yfinance as yf
import pandas as pd
import os
import json
import time
from datetime import datetime, timedelta
from tqdm import tqdm

print("="*70)
print("🚀 EGX30 Full Backfill + Forward Simulation + Self-Learning")
print("="*70)

# ==================== 1. تحميل البيانات التاريخية ====================
EGX30_SYMBOLS = [
    "COMI.CA", "TMGH.CA", "ETEL.CA", "EGAL.CA", "EAST.CA", "HRHO.CA",
    "FWRY.CA", "ORAS.CA", "EFIH.CA", "ADIB.CA", "ABUK.CA", "PHDC.CA",
    "RMDA.CA", "ORHD.CA", "EMFD.CA", "EFID.CA", "ISPH.CA", "BTFH.CA",
    "ARCC.CA", "GBCO.CA", "JUFO.CA", "CCAP.CA", "RAYA.CA", "OIH.CA",
    "ORWE.CA", "HELI.CA", "MCQE.CA", "VLMR.CA", "AMOC.CA", "EGCH.CA"
]

def download_historical_data():
    print("\n📥 بدء تحميل بيانات EGX30 لآخر 5 سنين...")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=5*365 + 200)
    
    os.makedirs("historical_data", exist_ok=True)
    
    for symbol in tqdm(EGX30_SYMBOLS):
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(start=start_date, end=end_date, interval="1d")
            if not df.empty:
                df = df[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
                df.index = pd.to_datetime(df.index).tz_localize(None)
                df.to_csv(f"historical_data/{symbol}.csv")
                print(f"✓ {symbol}: {len(df)} يوم")
            time.sleep(1.1)
        except Exception as e:
            print(f"❌ {symbol}: {e}")
    
    print("✅ تم تحميل البيانات التاريخية بنجاح!")

# ==================== 2. تشغيل كل Backfill Scripts الأصلية ====================
def run_all_backfills():
    print("\n🔄 تشغيل جميع Backfill Scripts الأصلية...")
    
    scripts = [
        "build_history.py",
        "backfill_signal_log.py",
        "backfill_research_db.py",
        "backfill_positions.py"
    ]
    
    for script in scripts:
        if os.path.exists(script):
            print(f"▶️ تشغيل {script} ...")
            os.system(f"python {script}")
        else:
            print(f"⚠️ {script} غير موجود")

# ==================== 3. تشغيل التقارير ====================
def generate_reports():
    print("\n📊 تشغيل Self-Learning Reports...")
    reports = ["research_report.py", "edge_report.py", "research_engine.py"]
    
    for report in reports:
        if os.path.exists(report):
            print(f"▶️ تشغيل {report} ...")
            os.system(f"python {report}")
        else:
            print(f"⚠️ {report} غير موجود")

# ==================== التشغيل الرئيسي ====================
if __name__ == "__main__":
    download_historical_data()
    run_all_backfills()
    generate_reports()
    
    print("\n🎉 اكتمل كل شيء بنجاح!")
    print("الآن تقدر تشغل:")
    print("python main.py")
    print("أو تشوف التقارير الجديدة (research_report.html أو edge_report.html)")
