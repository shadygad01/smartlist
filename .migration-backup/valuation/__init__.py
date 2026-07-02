"""
Institutional Valuation Engine (IVE)
Information-only service for institutional-quality valuation data.

ARCHITECTURE CONTRACT:
- This module is NEVER imported by scanner, signal_engine, constitutional_gate,
  ranking_engine, or any decision-making module.
- During scan execution, only valuation.db is read (via valuation.db.get_valuation_card).
- All computations run offline via valuation_scheduler.py.
- This module has ZERO influence on BUY/RE-BUY decisions.
"""

from valuation.db import get_valuation_card

__all__ = ["get_valuation_card"]
