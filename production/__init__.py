"""
Production Transaction Engine — Constitutional Architecture Phase 11.

Enforces explicit commit phases so partial execution is architecturally impossible.

Public API:
    from production.transaction import ProductionTransaction, Phase
    from production.journal import ExecutionJournal
    from production.invariants import assert_production_invariants
"""
