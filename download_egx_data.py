"""
EGX Historical Data Downloader
================================
شغّل هذا الـ script مرة واحدة على جهازك لتحميل البيانات الحقيقية.
البيانات تُحفظ في مجلد data/ وتُرفع على GitHub للاستخدام في الباكتيست.

التشغيل:
    python download_egx_data.py
    git add data/
    git commit -m "Add real EGX historical data"
    git push
"""

import os
import pandas as pd
import yfinance as yf
from datetime import datetime

STOCKS = [
    "COMI.CA", "TMGH.CA", "ETEL.CA", "EGAL.CA",
    "EAST.CA", "ABUK.CA", "ORAS.CA", "EFIH.CA",
    "ADIB.CA", "FWRY.CA", "EMFD.CA", "PHDC.CA",
    "ORHD.CA", "EFID.CA", "HRHO.CA", "JUFO.CA",
    "BTFH.CA", "RAYA.CA", "GBCO.CA", "HELI.CA",
    "ARCC.CA", "MCQE.CA", "ORWE.CA", "ISPH.CA",
    "RMDA.CA", "OIH.CA",  "CCAP.CA",
]

DATA_DIR = "data"
YEARS = 5


def download_stock(symbol, years=YEARS):
    """تحميل بيانات سهم واحد"""
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=f"{years}y", interval="1d",
                           auto_adjust=False, repair=True)
        if df.empty or len(df) < 80:
            print(f"  ⚠️  {symbol}: بيانات غير كافية ({len(df)} يوم)")
            return None

        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.index = df.index.tz_localize(None)
        df = df.dropna(subset=["Close"])
        return df

    except Exception as e:
        print(f"  ❌ {symbol}: {e}")
        return None


def main():
    os.makedirs(DATA_DIR, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"EGX Historical Data Downloader")
    print(f"تاريخ التحميل: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}\n")

    success, failed = [], []

    for symbol in STOCKS:
        print(f"  ⬇️  {symbol}...", end=" ", flush=True)
        df = download_stock(symbol)

        if df is not None:
            path = os.path.join(DATA_DIR, f"{symbol}.csv")
            df.to_csv(path)
            print(f"✅ {len(df)} يوم → {path}")
            success.append(symbol)
        else:
            failed.append(symbol)

    print(f"\n{'='*60}")
    print(f"✅ تم تحميل: {len(success)}/{len(STOCKS)} سهم")
    if failed:
        print(f"❌ فشل: {', '.join(failed)}")

    print(f"\nالخطوة التالية:")
    print(f"  git add data/")
    print(f"  git commit -m 'Add real EGX historical data'")
    print(f"  git push")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
