#!/usr/bin/env python3
"""V6.2 Universe Integrity Validator — run after every build."""
import sys, sqlite3, re

EXPECTED = 27

def check(name, actual, expected=EXPECTED):
    status = "PASS" if actual == expected else "FAIL"
    print(f"  [{status}] {name}: {actual}/{expected}")
    return actual == expected

results = []

# 1. universe_snapshot.db
try:
    conn = sqlite3.connect('universe_snapshot.db')
    count = conn.execute('SELECT COUNT(*) FROM universe_snapshot').fetchone()[0]
    bad = conn.execute("SELECT COUNT(*) FROM universe_snapshot WHERE status IN ('NO_DATA','NO POOL DATA','UNKNOWN')").fetchone()[0]
    conn.close()
    results.append(check("universe_snapshot.db rows", count))
    results.append(check("universe_snapshot bad statuses", bad, 0))
except Exception as e:
    print(f"  [FAIL] universe_snapshot.db: {e}")
    results.append(False)

# 2. stock_dna.db
try:
    conn2 = sqlite3.connect('stock_dna.db')
    dna = conn2.execute('SELECT COUNT(*) FROM stock_dna').fetchone()[0]
    conn2.close()
    results.append(check("stock_dna.db rows", dna))
except Exception as e:
    print(f"  [FAIL] stock_dna.db: {e}")
    results.append(False)

# 3. dashboard.html
try:
    html = open('dashboard.html').read()
    bad_labels = html.count('NO POOL DATA') + html.count('NO_DATA') + html.count('UNKNOWN')
    tickers = set(re.findall(r'(ABUK|ADIB|ARCC|BTFH|CCAP|COMI|EAST|EFID|EFIH|EGAL|EMFD|ETEL|FWRY|GBCO|HELI|HRHO|ISPH|JUFO|MCQE|OIH|ORAS|ORHD|ORWE|PHDC|RAYA|RMDA|TMGH)\.CA', html))
    results.append(check("dashboard.html tickers", len(tickers)))
    results.append(check("dashboard.html bad labels", bad_labels, 0))
except Exception as e:
    print(f"  [FAIL] dashboard.html: {e}")
    results.append(False)

# 4. email.html
try:
    email = open('email.html').read()
    active_start = email.find('All Active Opportunities')
    active_end = email.find('Re-Accumulation', active_start+100) if 'Re-Accumulation' in email[active_start+100:] else len(email)
    active_sec = email[active_start:active_end]
    re_in_active = active_sec.count('RE-ACCUM')
    results.append(check("email All Active RE-ACCUM rows", re_in_active, 0))
except Exception as e:
    print(f"  [FAIL] email.html: {e}")
    results.append(False)

all_pass = all(results)
print()
print("UNIVERSE INTEGRITY:", "PASS" if all_pass else "FAIL")
sys.exit(0 if all_pass else 1)
