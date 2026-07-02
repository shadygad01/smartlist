"""
tests/test_dashboard_architecture.py

Regression tests enforcing the V8 constitutional architectural rules:
  1. ValuationSection is NOT rendered on the dashboard (fair value lives inside signal cards only).
  2. Behavior Phase is NOT rendered on the dashboard outside Buy/ReAccum cards.
  3. NearEntrySection has no hardcoded tickers and no behavior phase block.
  4. All collapsible sections default to collapsed=true.
  5. ValuationPanel, SeenBeforePanel, BehaviorPhaseBlock all default to collapsed.

Run with: pytest tests/test_dashboard_architecture.py -v
"""
from __future__ import annotations

from pathlib import Path

ROOT         = Path(__file__).parent.parent
FRONTEND_SRC = ROOT / "frontend" / "src"
PAGE         = FRONTEND_SRC / "app" / "page.tsx"
COMPONENTS   = FRONTEND_SRC / "app" / "components"


class TestDashboardPageLayout:

    def test_valuation_section_not_imported_in_page(self):
        text = PAGE.read_text()
        assert "ValuationSection" not in text, (
            "ValuationSection must NOT be imported or rendered on the dashboard page. "
            "Fair value belongs inside signal cards only."
        )

    def test_valuation_section_tier_divider_removed(self):
        text = PAGE.read_text()
        assert "INSTITUTIONAL VALUATION ENGINE" not in text, (
            "Standalone 'INSTITUTIONAL VALUATION ENGINE' divider must be removed from page.tsx"
        )

    def test_valuation_panel_still_imported_in_buy_card(self):
        text = (COMPONENTS / "BuySignalCard.tsx").read_text()
        assert "import ValuationPanel from './ValuationPanel'" in text

    def test_valuation_panel_still_imported_in_re_accum(self):
        text = (COMPONENTS / "ReAccumulationSection.tsx").read_text()
        assert "import ValuationPanel from './ValuationPanel'" in text


class TestBehaviorPhaseScope:

    def test_behavior_phase_not_in_near_entry_section(self):
        text = (COMPONENTS / "NearEntrySection.tsx").read_text()
        assert "BehaviorPhaseBlock" not in text, (
            "BehaviorPhaseBlock must not appear in NearEntrySection"
        )
        assert "mpi.explanation" not in text, (
            "Behavior Phase explanation must not appear in NearEntrySection"
        )
        assert "BEHAVIOR PHASE" not in text, (
            "Behavior Phase label must not appear in NearEntrySection"
        )

    def test_behavior_phase_exists_in_buy_card(self):
        text = (COMPONENTS / "BuySignalCard.tsx").read_text()
        assert "BehaviorPhaseBlock" in text, (
            "BehaviorPhaseBlock must remain inside BuySignalCard"
        )
        assert "BEHAVIOR PHASE" in text

    def test_near_entry_section_has_no_hardcoded_tickers(self):
        text = (COMPONENTS / "NearEntrySection.tsx").read_text()
        for symbol in ["ABUK", "MCQE", "COMI", "TMGH", "SWDY", "ORWE"]:
            assert symbol not in text, f"NearEntrySection hardcodes ticker '{symbol}'"


class TestCollapsibleDefaults:

    def _check_collapsed_true(self, filename: str):
        path = COMPONENTS / filename
        text = path.read_text()
        assert "useState(true)" in text, (
            f"{filename}: collapsed state must default to true (collapsed by default)"
        )
        assert "useState(false)" not in text or "setCopied" in text, (
            f"{filename}: found useState(false) — all collapsible sections must default to collapsed. "
            "Only CopyButton's 'copied' state is exempt."
        )

    def test_re_accumulation_section_default_collapsed(self):
        self._check_collapsed_true("ReAccumulationSection.tsx")

    def test_universe_section_default_collapsed(self):
        self._check_collapsed_true("UniverseSection.tsx")

    def test_timeline_section_default_collapsed(self):
        self._check_collapsed_true("TimelineSection.tsx")

    def test_diagnostics_section_default_collapsed(self):
        self._check_collapsed_true("DiagnosticsSection.tsx")

    def test_near_entry_section_default_collapsed(self):
        self._check_collapsed_true("NearEntrySection.tsx")

    def test_valuation_panel_default_collapsed(self):
        self._check_collapsed_true("ValuationPanel.tsx")

    def test_seen_before_panel_default_collapsed(self):
        self._check_collapsed_true("SeenBeforePanel.tsx")

    def test_behavior_phase_block_default_collapsed(self):
        text = (COMPONENTS / "BuySignalCard.tsx").read_text()
        assert "useState(true)" in text, (
            "BehaviorPhaseBlock must default to collapsed (useState(true))"
        )


class TestSingleSourceOfTruth:

    def test_valuation_section_price_field_fixed(self):
        """ValuationSection.tsx must not reference the non-existent 'u.price' field."""
        text = (COMPONENTS / "ValuationSection.tsx").read_text()
        assert "u.price" not in text, (
            "ValuationSection.tsx still references u.price which doesn't exist on UniverseItem. "
            "Must use u.current_price."
        )

    def test_no_component_fetches_data_independently(self):
        """No component should use fetch() or axios — dashboard is read-only from snapshot."""
        for tsx in COMPONENTS.glob("*.tsx"):
            text = tsx.read_text()
            assert "fetch(" not in text or "useSnapshot" in text or tsx.name == "DashboardHeader.tsx", (
                f"{tsx.name}: component must not fetch data independently. "
                "All data flows from SnapshotProvider."
            )
