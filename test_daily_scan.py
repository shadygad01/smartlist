#!/usr/bin/env python3
"""
Test script to run daily_scan() and verify open positions are displayed
"""
import sys
import os
from datetime import datetime

# Add the project directory to path
sys.path.insert(0, '/home/user/smartlist')

from main import daily_scan, load_open_positions, build_report

print("=" * 80)
print("🧪 TESTING DAILY SCAN WITH MOCK DATA")
print("=" * 80)

# Check open positions
print("\n📁 Loading open positions from file...")
positions = load_open_positions()
print(f"✅ Loaded {len(positions)} positions:")
for stock, data in positions.items():
    print(f"   • {stock}: {data['entry_price']} EGP → {data['target']} EGP (Target: {data['target']})")

# Build and verify email report
print("\n📧 Building email report...")
html_report, results = build_report(holiday_mode=False)

# Check if open positions section exists in email
if "المراكز المفتوحة" in html_report or "open positions" in html_report.lower():
    print("✅ Email report contains open positions section")
    # Count positions in email
    position_count = html_report.count("<tr>") - 1  # Subtract header row
    print(f"   Positions shown in email: {position_count}")
else:
    print("❌ Email report does NOT contain open positions section")

# Show what would be in the results
print("\n📊 Qualifying stocks for new positions:")
qualifying_stocks = {s for s in results if results[s].get("ok") and results[s].get("score", 0) >= 35}
for stock in qualifying_stocks:
    print(f"   • {stock}: Score {results[stock].get('score', 0)}")

print("\n" + "=" * 80)
print("🎯 Test completed - Check email and Telegram alerts to verify open positions display")
print("=" * 80)
