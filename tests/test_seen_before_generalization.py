"""
tests/test_seen_before_generalization.py

Regression tests proving:
  1. SeenBeforePanel is completely generic — no hardcoded ticker symbols.
  2. Every Buy/Re-Accum card in today's snapshot renders (or correctly suppresses)
     SeenBeforePanel based solely on constitutional_memory_hits.
  3. All prices within presentation_snapshot.json are internally consistent.
  4. CI fails if any snapshot section shows a different current_price for the same ticker.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SNAPSHOT_PATH = ROOT / "presentation_snapshot.json"
# The Next.js frontend at frontend/src this file originally targeted was
# migrated to the Vite app at artifacts/egx-commandcenter (frontend/ no
# longer exists on the code branch). Dashboard components now live directly
# under components/dashboard/ (no app/ nesting).
FRONTEND_SRC  = ROOT / "artifacts" / "egx-commandcenter" / "src"
COMPONENTS    = FRONTEND_SRC / "components" / "dashboard"


# ── Helper ────────────────────────────────────────────────────────────────────

def _load_snapshot() -> dict:
    assert SNAPSHOT_PATH.exists(), f"Snapshot not found: {SNAPSHOT_PATH}"
    return json.loads(SNAPSHOT_PATH.read_text())


# ── Part 1: SeenBeforePanel Generalization ────────────────────────────────────

class TestSeenBeforePanelGeneralization:
    """SeenBeforePanel must be a generic component with zero ticker-specific logic."""

    HARDCODED_SYMBOLS = ["ABUK", "MCQE"]

    def _all_source_files(self):
        """
        Scoped to components/dashboard/ (not the whole frontend tree): the
        app has since grown lib/portfolioParser.ts, a brokerage-statement
        parser with a legitimate full-company-name -> ticker lookup table
        covering the entire EGX universe (including ABUK). That's unrelated
        to SeenBeforePanel's rendering logic, which is what this test class
        actually guards — matching the scope every other test in this class
        already uses.
        """
        exts = {".tsx", ".ts", ".js", ".jsx"}
        return [p for p in COMPONENTS.rglob("*") if p.suffix in exts]

    def test_no_hardcoded_tickers_in_frontend(self):
        """No ticker symbol may be hardcoded in any dashboard component file."""
        violations = []
        for path in self._all_source_files():
            text = path.read_text(encoding="utf-8")
            for symbol in self.HARDCODED_SYMBOLS:
                # Allow symbol in comments/strings only if it's in test data.
                # A real violation is `=== "ABUK"`, `ticker: "ABUK"`, etc.
                # We check for the symbol as a standalone quoted string literal.
                pattern = rf'["\']{{0,1}}\b{re.escape(symbol)}\b["\']{{0,1}}'
                if re.search(rf'["\']{re.escape(symbol)}["\']', text):
                    violations.append(f"{path.relative_to(ROOT)}: contains '{symbol}'")
        assert not violations, (
            "Ticker-specific logic found in frontend:\n" + "\n".join(violations)
        )

    def test_seen_before_panel_is_standalone_component(self):
        """SeenBeforePanel must live in its own shared component file."""
        panel_file = COMPONENTS / "SeenBeforePanel.tsx"
        assert panel_file.exists(), "SeenBeforePanel.tsx must exist as a shared component"

    def test_buy_signal_card_imports_shared_seen_before_panel(self):
        """BuySignalCard must import SeenBeforePanel from the shared component."""
        buy_card = COMPONENTS / "BuySignalCard.tsx"
        assert buy_card.exists()
        text = buy_card.read_text()
        assert "import SeenBeforePanel from './SeenBeforePanel'" in text, (
            "BuySignalCard.tsx must import SeenBeforePanel from './SeenBeforePanel'"
        )

    def test_buy_signal_card_has_no_inline_seen_before_definition(self):
        """BuySignalCard must NOT define SeenBeforePanel inline — it must use the shared one."""
        buy_card = COMPONENTS / "BuySignalCard.tsx"
        text = buy_card.read_text()
        assert "function SeenBeforePanel" not in text, (
            "BuySignalCard.tsx still contains an inline SeenBeforePanel definition. "
            "Remove it — only the shared component in SeenBeforePanel.tsx is allowed."
        )

    def test_re_accumulation_section_imports_shared_seen_before_panel(self):
        """ReAccumulationSection must import SeenBeforePanel from the shared component."""
        reaccum = COMPONENTS / "ReAccumulationSection.tsx"
        assert reaccum.exists()
        text = reaccum.read_text()
        assert "import SeenBeforePanel from './SeenBeforePanel'" in text, (
            "ReAccumulationSection.tsx must import SeenBeforePanel from './SeenBeforePanel'"
        )

    def test_seen_before_rendering_condition_is_generic(self):
        """The SeenBeforePanel render condition must be based on data fields, not ticker names."""
        panel_file = COMPONENTS / "SeenBeforePanel.tsx"
        text = panel_file.read_text()
        for symbol in self.HARDCODED_SYMBOLS:
            assert symbol not in text, (
                f"SeenBeforePanel.tsx contains hardcoded ticker '{symbol}'"
            )
        # Must receive dna as a prop — it's generic over any ticker
        assert "dna: StockDNA" in text or "dna:" in text, (
            "SeenBeforePanel must accept a generic `dna` prop"
        )


# ── Part 2: Seen Before Data Coverage from Snapshot ──────────────────────────

class TestSeenBeforeDataCoverage:
    """Every buy/re-accum ticker must be evaluated against stock_dna generically."""

    BUY_SIGNALS = ["READY NOW", "READY FOR RE-ACCUMULATION"]

    def _buy_universe_items(self, snap: dict) -> list[dict]:
        return [
            u for u in snap.get("universe_snapshot", [])
            if any(sig in (u.get("waiting_for_reason") or "") for sig in self.BUY_SIGNALS)
        ]

    def test_all_buy_cards_evaluated_for_seen_before(self):
        """
        For every buy-ready ticker, print its DNA status.
        Verify: either DNA with hits > 0 (should render) or hits == 0 (correctly hidden).
        There must be no ticker where DNA is missing entirely from stock_dna.
        """
        snap    = _load_snapshot()
        dna_map = snap.get("stock_dna", {})
        buys    = self._buy_universe_items(snap)

        assert len(buys) > 0, "No buy-ready tickers in snapshot — cannot validate coverage"

        missing_dna = []
        results = []
        for item in buys:
            ticker  = item["ticker"]
            dna     = dna_map.get(ticker)
            hits    = dna["constitutional_memory_hits"] if dna else None
            renders = (hits is not None and hits > 0)
            results.append({
                "ticker":     ticker,
                "buy_state":  item.get("waiting_for_reason", ""),
                "hits":       hits,
                "renders":    "YES" if renders else ("NO (hits=0)" if hits == 0 else "NO (no DNA)"),
            })
            if dna is None:
                missing_dna.append(ticker)

        # Print table for CI log visibility
        print(f"\n{'Ticker':12s} {'Buy State':40s} {'Hits':8s} {'Seen Before':12s}")
        print("-" * 76)
        for r in results:
            print(f"{r['ticker']:12s} {r['buy_state']:40s} {str(r['hits'] or '—'):8s} {r['renders']}")

        assert not missing_dna, (
            f"These buy-ready tickers have NO stock_dna entry at all: {missing_dna}. "
            f"stock_dna must cover every ticker in the constitutional universe."
        )

    def test_re_accumulation_events_have_dna(self):
        """Every RE_ACCUMULATION event ticker must exist in stock_dna."""
        snap    = _load_snapshot()
        dna_map = snap.get("stock_dna", {})
        reaccum = snap.get("re_accumulation", [])

        if not reaccum:
            pytest.skip("No re-accumulation events in snapshot")

        missing = [e["ticker"] for e in reaccum if e["ticker"] not in dna_map]
        assert not missing, (
            f"Re-accumulation tickers with no stock_dna: {missing}"
        )


# ── Part 3: Intra-Snapshot Price Consistency ──────────────────────────────────

PRICE_TOLERANCE_PCT = 0.01  # same as audit/assert_price_consistency.py


def _pct_diff(a: float, b: float) -> float:
    return abs(a - b) / max(a, b, 0.001) * 100


class TestSnapshotPriceConsistency:
    """
    All current_price values within ONE snapshot must be identical for the same ticker.
    Sections compared: universe_snapshot[], active[], near_constitutional[].
    """

    def _build_price_map(self, snap: dict) -> dict[str, dict[str, float]]:
        """Returns {ticker: {section: price}} for all snapshot sections."""
        result: dict[str, dict[str, float]] = {}

        def _add(section: str, items: list[dict]):
            for item in items:
                t = item.get("ticker")
                p = item.get("current_price")
                if t and p:
                    result.setdefault(t, {})[section] = float(p)

        _add("universe_snapshot", snap.get("universe_snapshot", []))
        _add("active",            snap.get("active", []))
        _add("near_constitutional", snap.get("near_constitutional", []))
        return result

    def test_no_intra_snapshot_price_mismatch(self):
        """
        Every ticker appearing in multiple snapshot sections must have the same
        current_price in each. Fails if divergence exceeds PRICE_TOLERANCE_PCT.
        """
        snap      = _load_snapshot()
        price_map = self._build_price_map(snap)
        failures  = []

        for ticker, sections in price_map.items():
            if len(sections) < 2:
                continue
            vals = list(sections.values())
            ref  = vals[0]
            if any(_pct_diff(ref, v) > PRICE_TOLERANCE_PCT for v in vals[1:]):
                failures.append(
                    f"{ticker}: " + ", ".join(f"{k}={v:.4f}" for k, v in sections.items())
                )

        assert not failures, (
            f"Intra-snapshot price mismatch for {len(failures)} ticker(s):\n"
            + "\n".join(f"  ✗ {f}" for f in failures)
        )

    def test_active_prices_subset_of_universe_snapshot(self):
        """
        active[] is derived from universe_snapshot[], so every active[] price
        must exactly match the universe_snapshot[] price for the same ticker.
        """
        snap      = _load_snapshot()
        universe  = {e["ticker"]: float(e["current_price"])
                     for e in snap.get("universe_snapshot", []) if e.get("current_price")}
        active    = {e["ticker"]: float(e["current_price"])
                     for e in snap.get("active", []) if e.get("current_price")}
        failures  = []

        for ticker, a_price in active.items():
            u_price = universe.get(ticker)
            if u_price is None:
                failures.append(f"{ticker}: in active[] but not in universe_snapshot[]")
            elif _pct_diff(u_price, a_price) > PRICE_TOLERANCE_PCT:
                failures.append(f"{ticker}: universe={u_price:.4f} vs active={a_price:.4f}")

        assert not failures, (
            "active[] prices must match universe_snapshot[] prices:\n"
            + "\n".join(f"  ✗ {f}" for f in failures)
        )

    def test_ci_fails_on_price_mismatch(self):
        """
        Simulate a mismatch: if we inject a wrong price, the consistency check
        must detect it and produce a failure.
        """
        import copy
        snap = _load_snapshot()
        # Inject a deliberate mismatch into a copy
        patched = copy.deepcopy(snap)
        if patched.get("active"):
            patched["active"][0]["current_price"] = 0.01  # obviously wrong
        price_map = self._build_price_map(patched)
        found_mismatch = False
        for ticker, sections in price_map.items():
            if len(sections) >= 2:
                vals = list(sections.values())
                ref  = vals[0]
                if any(_pct_diff(ref, v) > PRICE_TOLERANCE_PCT for v in vals[1:]):
                    found_mismatch = True
                    break
        assert found_mismatch, (
            "The price consistency check failed to detect an injected mismatch. "
            "The test logic itself is broken."
        )
