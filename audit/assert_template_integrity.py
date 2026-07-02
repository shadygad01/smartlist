"""
CI Template Integrity Assertion — Constitutional Rule: ONE builder per email type.

Verifies:
1. morning brief  → ONLY egx_email.py:build_email()
2. alert email    → ONLY alert_email.py:build_alert_email()
3. main.py has NO inline HTML builder (no DOCTYPE, no Signal Alert subject pattern)
4. email_v2.py does NOT exist at repo root (was deprecated and deleted)
5. send_change_email() in main.py delegates to alert_email.build_alert_email()

Exits 1 if ANY violation is found.
"""
from __future__ import annotations

import sys
from pathlib import Path

BASE      = Path(__file__).parent.parent
THIS_FILE = Path(__file__).name
failures: list[str] = []
import re

_SKIP_PARTS = {"archive", "__pycache__", "audit"}


def _production_py_files():
    for p in BASE.rglob("*.py"):
        if any(part in _SKIP_PARTS for part in p.parts):
            continue
        yield p


# ── 1. email_v2.py must NOT exist at root ────────────────────────────────────
if (BASE / "email_v2.py").exists():
    failures.append("FAIL: email_v2.py exists at repo root — deprecated file was not deleted")

# ── 2. egx_email.py must be the only file with build_email() in production ───
builders = []
for p in _production_py_files():
    if "def build_email(" in p.read_text(errors="replace"):
        builders.append(str(p.relative_to(BASE)))

if sorted(builders) != ["egx_email.py"]:
    failures.append(
        f"FAIL: build_email() found in unexpected files: {sorted(builders)} "
        f"(expected only ['egx_email.py'])"
    )

# ── 3. alert_email.py must be the only file with build_alert_email() ─────────
alert_builders = []
for p in _production_py_files():
    if "def build_alert_email(" in p.read_text(errors="replace"):
        alert_builders.append(str(p.relative_to(BASE)))

if sorted(alert_builders) != ["alert_email.py"]:
    failures.append(
        f"FAIL: build_alert_email() found in unexpected files: {sorted(alert_builders)} "
        f"(expected only ['alert_email.py'])"
    )

# ── 4. send_change_email in main.py must delegate to alert_email, not inline ─
main_py   = BASE / "main.py"
main_text = main_py.read_text(errors="replace") if main_py.exists() else ""

if main_py.exists():
    # Extract only the send_change_email function body
    m = re.search(r"^def send_change_email\((.+?)(?=^def |\Z)", main_text,
                  re.MULTILINE | re.DOTALL)
    fn_body = m.group(0) if m else ""

    if "build_alert_email" not in fn_body:
        failures.append(
            "FAIL: send_change_email() in main.py does not call build_alert_email — "
            "inline builder may still be present"
        )
    if re.search(r"<!DOCTYPE|Signal Alert.*moved to BUY|Buy Signal Alert", fn_body):
        failures.append(
            "FAIL: send_change_email() in main.py contains inline HTML — should delegate to alert_email"
        )

# ── 5. build_report() must use egx_email.build_email, not inline HTML ────────
if main_py.exists():
    m2 = re.search(r"^def build_report\((.+?)(?=^def |\Z)", main_text,
                   re.MULTILINE | re.DOTALL)
    br_body = m2.group(0) if m2 else ""
    if "from egx_email import build_email" not in br_body and "build_email(snap)" not in br_body:
        failures.append(
            "FAIL: build_report() in main.py does not call egx_email.build_email — "
            "morning email may not use canonical builder"
        )

# ── Report ────────────────────────────────────────────────────────────────────
print("Template Integrity Assertion")
print(f"  email_v2.py at root    : {'ABSENT (OK)' if not (BASE/'email_v2.py').exists() else 'PRESENT (BAD)'}")
print(f"  build_email() in       : {builders}")
print(f"  build_alert_email() in : {alert_builders}")
print(f"  send_change_email uses : {'alert_email.build_alert_email (OK)' if not failures else 'CHECK BELOW'}")

if failures:
    print("\nTEMPLATE INTEGRITY VIOLATIONS:")
    for f in failures:
        print(f"  ✗ {f}")
    print("\nASSERTION FAILED — duplicate email builders exist.")
    sys.exit(1)

print("\nASSERTION PASSED — single template per email type confirmed.")
sys.exit(0)
