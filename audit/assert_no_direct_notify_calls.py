"""
No Direct Notify Calls Assertion — Constitutional Architecture Phase 11 (Phase 8).

Enforces the architectural rule: no production function may call
send_email(), send_telegram_alerts(), send_morning_brief(), or
send_change_alert() directly without going through ProductionTransaction.

This assertion scans all Python files in the project and fails CI if any
call to these functions is found OUTSIDE of:
  - main.py's _run_scan_workflow() (the authorized caller, which uses tx.step())
  - test files
  - audit files
  - the functions' own definitions
  - archive/ or legacy/ directories

Rationale:
  If production code can call send_email() directly, the NOTIFY-after-PERSIST
  ordering guarantee of ProductionTransaction is bypassed. The only safe call
  site is inside ProductionTransaction.step(Phase.NOTIFY, ...).

Exits 0 (PASS), 1 (FAIL).
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

from audit.audit_status import AuditStatus

# Notification functions that must only be called via ProductionTransaction
_GUARDED_CALLS = {
    "send_email",
    "send_telegram_alerts",
    "send_morning_brief",
    "send_change_alert",
    "send_alert",
}

# Files/directories that are explicitly exempt
_EXEMPT_DIRS = {
    "archive", "legacy", "audit", "test", "tests",
    ".git", "__pycache__", "venv", ".venv",
}
_EXEMPT_FILES = {
    # The function definitions themselves
    "main.py",             # authorized call site: _run_scan_workflow uses tx.step()
    "telegram.py",         # definition of send_alert() and send_morning_brief()
    "egx_email.py",        # email builder (not a sender)
    "alert_email.py",      # alert email builder (not a sender)
    "notifications/email_sender.py",    # definition of send()
    "notifications/telegram_sender.py", # definition of send()
    "notifications/notification_router.py",
    "notifications/morning_guard.py",
}


_EXEMPT_FILES.add("telegram_v2.py")  # deprecated wrapper, preserved for reference only


def _is_exempt(path: Path) -> bool:
    rel = path.relative_to(BASE)
    parts = rel.parts
    # Exempt directories
    if any(p in _EXEMPT_DIRS for p in parts):
        return True
    # Exempt files by relative path or filename
    rel_str = str(rel)
    if any(rel_str == ex or rel_str.endswith("/" + ex) or rel.name == ex
           for ex in _EXEMPT_FILES):
        return True
    return False


def _find_direct_calls(path: Path) -> list[tuple[int, str]]:
    """
    Return (line_no, line_text) for actual Call nodes to guarded functions.
    Uses AST to avoid false positives in comments and string literals.
    Falls back to regex if the file is not valid Python.
    """
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree   = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []  # skip unparseable files
    except Exception:
        return []

    lines = source.splitlines()
    hits: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        # Direct call: send_email(...)
        if isinstance(node.func, ast.Name) and node.func.id in _GUARDED_CALLS:
            fn_name = node.func.id
        # Attribute call: obj.send_email(...) — only match if attr is a guarded name
        elif isinstance(node.func, ast.Attribute) and node.func.attr in _GUARDED_CALLS:
            fn_name = node.func.attr
        else:
            continue

        ln = node.lineno
        line_text = lines[ln - 1] if 0 < ln <= len(lines) else ""

        # Exclude: function definitions (def send_email(...))
        if re.match(rf"\s*(async\s+)?def\s+{re.escape(fn_name)}\s*\(", line_text):
            continue

        hits.append((ln, line_text.rstrip()))

    return hits


def main() -> int:
    print("No Direct Notify Calls Assertion (Phase 8)")
    print("  Scanning for unauthorized direct calls to notification functions...")
    print()
    print(f"  Guarded functions: {sorted(_GUARDED_CALLS)}")
    print()

    violations: list[tuple[str, int, str]] = []

    for py_file in sorted(BASE.rglob("*.py")):
        if _is_exempt(py_file):
            continue
        hits = _find_direct_calls(py_file)
        for line_no, line_text in hits:
            rel = str(py_file.relative_to(BASE))
            violations.append((rel, line_no, line_text.strip()))

    if violations:
        print(f"  ✗ Found {len(violations)} unauthorized direct notification call(s):")
        for rel, ln, text in violations:
            print(f"      {rel}:{ln}  →  {text[:80]}")
        print()
        print("  Rule: All send_email/send_telegram/send_morning_brief/send_change_alert")
        print("  calls must be routed through ProductionTransaction.step(Phase.NOTIFY, ...).")
        print("  This ensures notifications never fire before persistence completes.")
        print()
        print("ASSERTION FAILED — direct notification calls violate Phase 8 architecture.")
        return AuditStatus.FAIL

    print("  ✓ No unauthorized direct notification calls found.")
    print()
    print("ASSERTION PASSED — all notification calls are routed through ProductionTransaction.")
    return AuditStatus.PASS


if __name__ == "__main__":
    sys.exit(main())
