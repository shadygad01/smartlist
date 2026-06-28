"""
valuation.source_manager — Multi-source data acquisition for IVE V2.

Source priority hierarchy (IVE spec):
  Priority 1: Official company financial statements (IR, exchange disclosures)
  Priority 2: Structured financial providers (yfinance, Alpha Vantage, FMP, Polygon)
  Priority 3: Market data (price, cap, volume, shares)
  Priority 4: Analyst consensus (target prices, recommendations)
  Priority 5: Economic inputs (risk-free rate, ERP, beta, tax rate, terminal growth, WACC)

Every fetch returns a SourceResult with full provenance metadata.
Retries with exponential backoff. Falls back to next-priority source on failure.
Results are cached in-memory for the lifetime of the SourceManager instance.
Never called during scanner execution.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

_MAX_RETRIES   = 3
_BASE_DELAY_S  = 2.0


@dataclass
class SourceResult:
    """Encapsulates a successful data fetch with full provenance metadata."""
    data:             Any
    source_name:      str
    source_priority:  int    # 1=official, 2=structured, 3=market, 4=analyst, 5=economic
    data_version:     str    # e.g. "yfinance-2025-06-28-v1"
    collection_time:  str    # ISO 8601 UTC


@dataclass
class _Reg:
    """Internal source registration."""
    name:         str
    priority:     int
    fetcher:      Callable[[str], Any]
    max_retries:  int   = _MAX_RETRIES
    base_delay_s: float = _BASE_DELAY_S


class SourceManager:
    """
    Multi-source data acquisition manager for a single ticker.

    Register sources per data_type (e.g. "financials", "market_data").
    fetch() tries registered sources in priority order, retrying each with
    exponential backoff, falling back to the next source on failure.
    """

    def __init__(self, ticker: str) -> None:
        self.ticker = ticker
        self._registry: dict[str, list[_Reg]] = {}
        self._cache:    dict[str, SourceResult] = {}

    def register(
        self,
        data_type:   str,
        name:        str,
        priority:    int,
        fetcher:     Callable[[str], Any],
        max_retries: int = _MAX_RETRIES,
    ) -> None:
        """Register a fetcher for data_type. Lower priority number = tried first."""
        bucket = self._registry.setdefault(data_type, [])
        bucket.append(_Reg(name=name, priority=priority, fetcher=fetcher,
                           max_retries=max_retries))
        bucket.sort(key=lambda r: r.priority)

    def fetch(self, data_type: str) -> SourceResult | None:
        """
        Fetch data_type using the highest-priority available source.
        Returns cached result if already fetched this session.
        Returns None when all sources fail.
        """
        if data_type in self._cache:
            return self._cache[data_type]

        for reg in self._registry.get(data_type, []):
            result = self._attempt(reg, data_type)
            if result is not None:
                self._cache[data_type] = result
                return result

        print(f"[SourceManager] {self.ticker}: all sources exhausted for '{data_type}'")
        return None

    def _attempt(self, reg: _Reg, data_type: str) -> SourceResult | None:
        delay = reg.base_delay_s
        for attempt in range(1, reg.max_retries + 1):
            try:
                data = reg.fetcher(self.ticker)
                if _nonempty(data):
                    now     = datetime.now(timezone.utc).isoformat()
                    version = f"{reg.name}-{now[:10]}-v{attempt}"
                    print(
                        f"[SourceManager] {self.ticker}/{data_type}: "
                        f"{reg.name} OK (attempt {attempt})"
                    )
                    return SourceResult(
                        data=data,
                        source_name=reg.name,
                        source_priority=reg.priority,
                        data_version=version,
                        collection_time=now,
                    )
                print(
                    f"[SourceManager] {self.ticker}/{data_type}: "
                    f"{reg.name} returned empty (attempt {attempt})"
                )
            except Exception as exc:
                print(
                    f"[SourceManager] {self.ticker}/{data_type}: "
                    f"{reg.name} error attempt {attempt}: {exc}"
                )
                if attempt < reg.max_retries:
                    time.sleep(delay)
                    delay *= 2
        return None


def _nonempty(data: Any) -> bool:
    if data is None:
        return False
    if isinstance(data, (list, dict)) and len(data) == 0:
        return False
    try:
        if hasattr(data, "empty") and data.empty:
            return False
    except Exception:
        pass
    return True
