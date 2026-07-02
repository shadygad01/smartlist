"""
challenger_allocation_engine.py — Layer 3 of the Challenger Architecture.

PURPOSE:
  Rank eligible opportunities and assign capital allocation grades.
  Input:  expectancy score (0–100) from Layer 2
  Output: allocation grade + priority label

GRADES:
  A+  (90–100) → Top priority — maximum allocation
  A   (80–89)  → High priority — full allocation
  B   (70–79)  → Standard allocation
  C   (60–69)  → Reduced allocation (monitor)
  D   (<60)    → Ignore — insufficient expectancy edge

NOTE:
  This layer controls PRIORITY and ALLOCATION — not eligibility.
  A stock that passes Layer 1 (Eligible) is NEVER blocked by this layer;
  it simply receives lower priority / smaller allocation size.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class AllocationResult:
    grade: str              # "A+", "A", "B", "C", "D"
    priority: int           # 1=highest, 5=lowest
    allocation_pct: float   # recommended capital allocation (% of available capital per slot)
    label: str              # human-readable label
    deploy: bool            # True = deploy capital; False = ignore


_GRADE_TABLE = [
    # (min_score, grade, priority, alloc_pct, label, deploy)
    (90, "A+",  1, 1.00, "Institutional Grade — Maximum Allocation",   True),
    (80, "A",   2, 0.80, "High Confidence — Full Allocation",           True),
    (70, "B",   3, 0.60, "Standard Setup — Regular Allocation",         True),
    (60, "C",   4, 0.40, "Marginal Edge — Reduced Allocation",          True),
    ( 0, "D",   5, 0.00, "Insufficient Expectancy — No Deployment",     False),
]


def grade(expectancy_score: int) -> AllocationResult:
    """Map expectancy score 0–100 to allocation grade."""
    for min_s, g, prio, alloc, label, deploy in _GRADE_TABLE:
        if expectancy_score >= min_s:
            return AllocationResult(
                grade=g,
                priority=prio,
                allocation_pct=alloc,
                label=label,
                deploy=deploy,
            )
    return AllocationResult(grade="D", priority=5, allocation_pct=0.0,
                            label="Insufficient Expectancy — No Deployment", deploy=False)


def rank_opportunities(
    opportunities: list[dict],
    expectancy_key: str = "challenger_score",
) -> list[dict]:
    """
    Sort a list of opportunity dicts by expectancy score (descending).
    Adds 'allocation_grade', 'allocation_priority', 'allocation_pct' to each dict.
    """
    result = []
    for opp in opportunities:
        exp_score = opp.get(expectancy_key, 0) or 0
        alloc = grade(exp_score)
        enriched = dict(opp)
        enriched["allocation_grade"]    = alloc.grade
        enriched["allocation_priority"] = alloc.priority
        enriched["allocation_pct"]      = alloc.allocation_pct
        enriched["allocation_label"]    = alloc.label
        enriched["deploy"]              = alloc.deploy
        result.append(enriched)

    result.sort(key=lambda x: x.get(expectancy_key, 0), reverse=True)
    return result


def summarise(opportunities: list[dict], expectancy_key: str = "challenger_score") -> dict:
    """Return grade distribution summary."""
    from collections import Counter
    graded = rank_opportunities(opportunities, expectancy_key)
    counts = Counter(o["allocation_grade"] for o in graded)
    deployable = [o for o in graded if o.get("deploy")]
    return {
        "total":       len(graded),
        "deployable":  len(deployable),
        "grade_dist":  dict(counts),
        "top3":        [o.get("symbol", "?") for o in graded[:3]],
    }
