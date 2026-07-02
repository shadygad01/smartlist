"""
Exponential backoff retry helper.
attempt 1 → immediate
attempt 2 → 2 s delay
attempt 3 → 4 s delay
"""
from __future__ import annotations

import time
from typing import Callable, TypeVar

T = TypeVar("T")


def with_retry(fn: Callable[[], T], attempts: int = 3, base_delay: float = 2.0) -> T:
    """
    Call fn() up to `attempts` times with exponential backoff.
    Raises the last exception if all attempts fail.
    """
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if attempt < attempts:
                delay = base_delay ** (attempt - 1)  # 1→0s, 2→2s, 3→4s
                time.sleep(delay)
    raise last_exc  # type: ignore[misc]
