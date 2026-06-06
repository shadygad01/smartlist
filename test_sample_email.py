#!/usr/bin/env python3
import sys
sys.path.insert(0, '/home/user/smartlist')

from main import build_report

# Generate the email with test data
html, results = build_report(holiday_mode=False)

# Extract just the open positions section
start_idx = html.find("المراكز المفتوحة")
if start_idx > 0:
    # Find the section end (next section or end of table)
    end_idx = html.find("</table>", start_idx)
    if end_idx > 0:
        section = html[start_idx:end_idx+8]
        
        # Extract text content for display
        import re
        # Remove HTML tags but keep structure
        text = re.sub('<[^>]+>', '', section)
        text = re.sub(r'\s+', ' ', text)
        
        print("\n" + "="*100)
        print("📊 المراكز المفتوحة - جزء من الإيميل")
        print("="*100)
        print(text[:1500])
        
        # Count positions in HTML
        positions = section.count(".CA")
        print(f"\n✅ عدد الصفقات المعروضة: {positions}")
        print("="*100 + "\n")

# Also save the full HTML for inspection
with open("sample_email.html", "w", encoding="utf-8") as f:
    f.write(html)
    
print("📧 تم حفظ الإيميل كاملاً في: sample_email.html")
