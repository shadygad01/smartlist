"""
Shared audit status module — Phase 1 Constitutional Architecture Certification.

Single source of truth for all audit exit codes.
All audit scripts must import AuditStatus from this module.
No script may define its own status enum or exit code constants.

Exit code contract:
  0 = PASS     — assertion ran, all checks passed
  1 = FAIL     — real production inconsistency detected; CI must fail
  2 = SKIPPED  — prerequisite missing or manual execution skipped
  3 = EXPECTED — known limitation in dev/non-CI mode; same condition is FAIL in CI
"""
from __future__ import annotations

import os
import sys
from enum import IntEnum


class AuditStatus(IntEnum):
    PASS     = 0
    FAIL     = 1
    SKIPPED  = 2
    EXPECTED = 3


def is_ci() -> bool:
    """Return True when running inside GitHub Actions or any CI environment."""
    return bool(os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"))


def exit_pass(msg: str = "ASSERTION PASSED.") -> None:
    print(msg)
    sys.exit(int(AuditStatus.PASS))


def exit_fail(msg: str = "ASSERTION FAILED.") -> None:
    print(msg)
    sys.exit(int(AuditStatus.FAIL))


def exit_skipped(msg: str = "SKIPPED.") -> None:
    print(msg)
    sys.exit(int(AuditStatus.SKIPPED))


def exit_expected(msg: str = "ASSERTION EXPECTED.") -> None:
    print(msg)
    sys.exit(int(AuditStatus.EXPECTED))
