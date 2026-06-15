"""
Knowledge Base — persistent store for statistical findings.
Prevents re-discovery; surfaces prior conclusions to labs and optimizer.
"""
import json
import sqlite3
import os
from datetime import datetime
from typing import Optional

KB_FILE = "knowledge_base.json"

# ── Schema ─────────────────────────────────────────────────────────────────────

_DEFAULT: dict = {
    "schema_version": 1,
    "created_at": datetime.now().isoformat(),
    "factor_findings": {},   # factor_name -> FindingRecord
    "regime_findings": {},   # regime_label -> FindingRecord
    "parameter_findings": {},# param_name -> FindingRecord
    "cycle_log": [],
}

_FINDING_KEYS = (
    "factor", "tier",
    "win_rate", "expectancy", "avg_return", "median_return",
    "mfe_20d_mean", "mfe_40d_mean",
    "fib_15pct", "fib_30pct", "fib_50pct", "fib_100pct",
    "tail_contribution", "top10pct_contribution",
    "multi_bagger_pct", "sample_n",
    "verdict",          # 'POSITIVE' | 'NEGATIVE' | 'NEUTRAL' | 'TAIL_DRIVER'
    "recorded_at", "source",
)


class KnowledgeBase:
    def __init__(self, path: str = KB_FILE):
        self.path = path
        self._data = self._load()

    def _load(self) -> dict:
        if os.path.exists(self.path):
            try:
                with open(self.path, encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in _DEFAULT.items():
                    data.setdefault(k, v)
                return data
            except Exception:
                pass
        d = dict(_DEFAULT)
        d["created_at"] = datetime.now().isoformat()
        return d

    def _save(self) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self.path)

    # ── Write ──────────────────────────────────────────────────────────────────

    def record_factor(self, factor: str, metrics: dict, source: str = "factor_lab") -> None:
        entry = {k: metrics.get(k) for k in _FINDING_KEYS}
        entry["factor"] = factor
        entry["recorded_at"] = datetime.now().isoformat()
        entry["source"] = source
        self._data["factor_findings"][factor] = entry
        self._save()

    def record_regime(self, regime: str, metrics: dict, source: str = "regime_lab") -> None:
        entry = dict(metrics)
        entry.setdefault("recorded_at", datetime.now().isoformat())
        entry["source"] = source
        self._data["regime_findings"][regime] = entry
        self._save()

    def record_parameter(self, param: str, metrics: dict, source: str = "parameter_lab") -> None:
        entry = dict(metrics)
        entry.setdefault("recorded_at", datetime.now().isoformat())
        entry["source"] = source
        self._data["parameter_findings"][param] = entry
        self._save()

    def log_cycle(self, summary: dict) -> None:
        summary.setdefault("logged_at", datetime.now().isoformat())
        self._data["cycle_log"].append(summary)
        if len(self._data["cycle_log"]) > 200:
            self._data["cycle_log"] = self._data["cycle_log"][-200:]
        self._save()

    # ── Read ───────────────────────────────────────────────────────────────────

    def get_factor(self, factor: str) -> Optional[dict]:
        return self._data["factor_findings"].get(factor)

    def get_all_factors(self) -> dict:
        return self._data["factor_findings"]

    def get_positive_factors(self) -> list[str]:
        return [f for f, v in self._data["factor_findings"].items()
                if v.get("verdict") in ("POSITIVE", "TAIL_DRIVER")]

    def get_negative_factors(self) -> list[str]:
        return [f for f, v in self._data["factor_findings"].items()
                if v.get("verdict") == "NEGATIVE"]

    def get_tail_drivers(self) -> list[str]:
        return [f for f, v in self._data["factor_findings"].items()
                if v.get("verdict") == "TAIL_DRIVER"]

    # ── Retest prevention ─────────────────────────────────────────────────────

    def should_retest(self, factor: str, min_new_samples: int = 50) -> tuple[bool, str]:
        """
        Returns (should_retest, reason).
        Prevents re-running tests on previously settled hypotheses unless:
        - min_new_samples new outcomes have been recorded since last test
        - OR the factor was last tested > 30 days ago
        - OR the factor has never been tested
        """
        entry = self._data["factor_findings"].get(factor)
        if not entry:
            return True, "never_tested"

        verdict = entry.get("verdict")
        if verdict in ("POSITIVE", "TAIL_DRIVER"):
            return False, f"already_confirmed:{verdict}"

        # For NEGATIVE/NEUTRAL factors, check age and sample delta
        try:
            from datetime import datetime, timedelta
            last_at = datetime.fromisoformat(entry.get("recorded_at", "2000-01-01"))
            days_old = (datetime.now() - last_at).days
            if days_old > 30:
                return True, f"stale:{days_old}d"
        except Exception:
            pass

        prior_n = entry.get("sample_n") or 0
        try:
            conn = __import__("sqlite3").connect("egx_research.db")
            cur_n = conn.execute(
                "SELECT COUNT(*) FROM bottom_quality WHERE r20d IS NOT NULL"
            ).fetchone()[0]
            conn.close()
            if cur_n - prior_n >= min_new_samples:
                return True, f"new_samples:{cur_n - prior_n}"
        except Exception:
            pass

        return False, f"too_recent:{verdict}"

    def skip_factors(self) -> list[str]:
        """Return list of factors that should be skipped in current research cycle."""
        return [f for f in self._data["factor_findings"]
                if not self.should_retest(f)[0]]

    def summary(self) -> dict:
        ff = self._data["factor_findings"]
        return {
            "total_factors_analyzed": len(ff),
            "positive": self.get_positive_factors(),
            "negative": self.get_negative_factors(),
            "tail_drivers": self.get_tail_drivers(),
            "total_cycles_logged": len(self._data["cycle_log"]),
            "last_cycle": self._data["cycle_log"][-1] if self._data["cycle_log"] else None,
        }


# ── Seed known findings from prior research ────────────────────────────────────

def seed_prior_findings(kb: KnowledgeBase) -> None:
    """
    Seed statistically confirmed findings from multi-metric factor analysis (n=481).
    Only call once; safe to re-call (idempotent — overwrites with same data).
    """
    prior = [
        dict(factor="r4_htf", tier=1, win_rate=0.47, expectancy=0.055,
             avg_return=0.085, multi_bagger_pct=0.18,
             verdict="POSITIVE", source="factor_lab_2026_06"),
        dict(factor="r7_div", tier=2, win_rate=0.40, expectancy=0.048,
             avg_return=0.091, tail_contribution=0.31,
             verdict="TAIL_DRIVER", source="factor_lab_2026_06"),
        dict(factor="r2_ob", tier=3, win_rate=0.36, expectancy=0.021,
             avg_return=0.052, multi_bagger_pct=0.08,
             verdict="NEUTRAL", source="factor_lab_2026_06"),
        dict(factor="wick_rejection", win_rate=0.33, expectancy=0.015,
             verdict="NEGATIVE", source="factor_lab_2026_06"),
        dict(factor="equal_lows", win_rate=0.31, expectancy=0.012,
             verdict="NEGATIVE", source="factor_lab_2026_06"),
    ]
    for p in prior:
        factor = p.pop("factor")
        kb.record_factor(factor, p, source=p.get("source", "seed"))


# ── Convenience entry ──────────────────────────────────────────────────────────

def get_kb() -> KnowledgeBase:
    kb = KnowledgeBase()
    if not kb.get_all_factors():
        seed_prior_findings(kb)
    return kb


if __name__ == "__main__":
    import pprint
    kb = get_kb()
    pprint.pprint(kb.summary())
