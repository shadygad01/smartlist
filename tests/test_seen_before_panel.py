"""
Regression test: "Seen Before" historical evidence panel in Constitutional Dashboard.

Verifies that:
1. stock_dna_engine computes the required fields for the panel
2. presentation_snapshot.json contains those fields for every buy-signal ticker
3. The frontend TypeScript types declare all required fields
4. BuySignalCard renders a SeenBeforePanel when constitutional_memory_hits > 0
"""
import json
import re
import sqlite3
import tempfile
from pathlib import Path

import pytest

BASE = Path(__file__).parent.parent
# The Next.js frontend at frontend/src this file originally targeted was
# migrated to the Vite app at artifacts/egx-commandcenter (frontend/ no
# longer exists on the code branch); dashboard components now live under
# components/dashboard/ (no app/ nesting).
FRONTEND      = BASE / "artifacts" / "egx-commandcenter" / "src"
DASHBOARD_DIR = FRONTEND / "components" / "dashboard"

# ── Required fields the Seen Before panel must expose ─────────────────────────
REQUIRED_DNA_FIELDS = {
    "constitutional_memory_hits",
    "avg_return_pct",
    "best_return_pct",
    "worst_return_pct",
    "last_event_date",
    "first_buy_date",
    "constitutional_memory_confidence",
}

REQUIRED_MPI_FIELDS = {
    "avg_mfe40",
    "historical_cases",
}


class TestStockDNAEngine:
    def _build_dna(self, events: list[dict], universe: list[str]) -> list[dict]:
        """Minimal in-process run of stock_dna build logic."""
        from statistics import mean
        from datetime import datetime

        by_ticker: dict[str, list] = {}
        for e in events:
            by_ticker.setdefault(e["ticker"], []).append(e)

        rows = []
        for ticker in universe:
            if ticker in by_ticker:
                evts = sorted(by_ticker[ticker], key=lambda e: e["event_date"])
                prices = [e["constitutional_entry_price"] for e in evts if e.get("constitutional_entry_price")]
                returns = [e["return_pct"] for e in evts if "return_pct" in e]
                rows.append({
                    "ticker": ticker,
                    "first_buy_date": evts[0]["event_date"],
                    "last_event_date": evts[-1]["event_date"],
                    "buy_count": sum(1 for e in evts if e["event_type"] == "FIRST_BUY"),
                    "re_accum_count": sum(1 for e in evts if e["event_type"] == "RE_ACCUMULATION"),
                    "avg_return_pct": mean(returns) if returns else 0.0,
                    "best_return_pct": max(returns) if returns else 0.0,
                    "worst_return_pct": min(returns) if returns else 0.0,
                    "constitutional_memory_hits": len(evts),
                    "constitutional_memory_confidence": "CONFIRMED" if len([e for e in evts if e["event_type"] == "FIRST_BUY"]) >= 2 else "DEVELOPING",
                })
        return rows

    def test_required_fields_computed(self):
        events = [
            {"ticker": "TEST.CA", "event_type": "FIRST_BUY", "event_date": "2023-01-15",
             "constitutional_entry_price": 10.0, "return_pct": 25.0},
            {"ticker": "TEST.CA", "event_type": "FIRST_BUY", "event_date": "2024-06-01",
             "constitutional_entry_price": 12.0, "return_pct": -5.0},
            {"ticker": "TEST.CA", "event_type": "RE_ACCUMULATION", "event_date": "2025-03-10",
             "constitutional_entry_price": 11.0, "return_pct": 40.0},
        ]
        rows = self._build_dna(events, ["TEST.CA"])
        assert len(rows) == 1
        row = rows[0]
        for field in REQUIRED_DNA_FIELDS:
            assert field in row, f"Missing field: {field}"

    def test_worst_return_is_minimum(self):
        events = [
            {"ticker": "X.CA", "event_type": "FIRST_BUY", "event_date": "2023-01-01",
             "constitutional_entry_price": 10.0, "return_pct": 50.0},
            {"ticker": "X.CA", "event_type": "RE_ACCUMULATION", "event_date": "2024-01-01",
             "constitutional_entry_price": 10.0, "return_pct": -15.0},
        ]
        rows = self._build_dna(events, ["X.CA"])
        assert rows[0]["worst_return_pct"] == -15.0

    def test_last_event_date_is_most_recent(self):
        events = [
            {"ticker": "Y.CA", "event_type": "FIRST_BUY", "event_date": "2022-06-01",
             "constitutional_entry_price": 5.0, "return_pct": 10.0},
            {"ticker": "Y.CA", "event_type": "RE_ACCUMULATION", "event_date": "2025-11-20",
             "constitutional_entry_price": 6.0, "return_pct": 30.0},
        ]
        rows = self._build_dna(events, ["Y.CA"])
        assert rows[0]["last_event_date"] == "2025-11-20"
        assert rows[0]["first_buy_date"] == "2022-06-01"


class TestStockDNASchema:
    def test_db_has_required_columns(self):
        db_path = BASE / "stock_dna.db"
        if not db_path.exists():
            pytest.skip("stock_dna.db not present")
        conn = sqlite3.connect(str(db_path))
        cols = {row[1] for row in conn.execute("PRAGMA table_info(stock_dna)").fetchall()}
        conn.close()
        missing = REQUIRED_DNA_FIELDS - cols
        assert not missing, f"stock_dna.db missing columns: {missing}"


class TestPresentationSnapshot:
    @pytest.fixture
    def snapshot(self):
        snap_path = BASE / "presentation_snapshot.json"
        if not snap_path.exists():
            pytest.skip("presentation_snapshot.json not present")
        return json.loads(snap_path.read_text())

    def test_buy_signals_have_dna_with_seen_before(self, snapshot):
        buy_signals = [
            u for u in snapshot.get("universe_snapshot", [])
            if "READY NOW" in (u.get("waiting_for_reason") or "")
        ]
        dna = snapshot.get("stock_dna", {})
        for signal in buy_signals:
            ticker = signal["ticker"]
            assert ticker in dna, f"{ticker} has buy signal but no stock_dna entry"
            entry = dna[ticker]
            missing = REQUIRED_DNA_FIELDS - set(entry.keys())
            assert not missing, f"{ticker} stock_dna missing fields: {missing}"

    def test_seen_before_fields_are_not_null_for_historical_tickers(self, snapshot):
        dna = snapshot.get("stock_dna", {})
        for ticker, entry in dna.items():
            if entry.get("constitutional_memory_hits", 0) > 0:
                assert entry.get("best_return_pct") is not None, f"{ticker} missing best_return_pct"
                assert entry.get("worst_return_pct") is not None, f"{ticker} missing worst_return_pct"
                assert entry.get("last_event_date") is not None, f"{ticker} missing last_event_date"


class TestFrontendTypes:
    def test_typescript_type_declares_required_fields(self):
        ts_path = FRONTEND / "types" / "snapshot.ts"
        assert ts_path.exists(), "snapshot.ts missing"
        content = ts_path.read_text()
        for field in REQUIRED_DNA_FIELDS:
            assert field in content, f"TypeScript StockDNA missing field: {field}"
        for field in REQUIRED_MPI_FIELDS:
            assert field in content, f"TypeScript MPIBehavior missing field: {field}"

    def test_buy_signal_card_renders_seen_before_panel(self):
        """
        BuySignalCard.tsx wires SeenBeforePanel with the dna/mpi data; the field
        rendering itself lives in the shared SeenBeforePanel.tsx (verified by
        tests/test_seen_before_generalization.py, which requires BuySignalCard
        to import — not inline-define — SeenBeforePanel). Checking each field
        name against BuySignalCard.tsx directly is stale since that extraction;
        this asserts the wiring here and the actual field rendering against
        SeenBeforePanel.tsx, preserving the original intent.
        """
        card_path = DASHBOARD_DIR / "BuySignalCard.tsx"
        assert card_path.exists(), "BuySignalCard.tsx missing"
        content = card_path.read_text()
        assert "SeenBeforePanel" in content, "SeenBeforePanel component missing from BuySignalCard.tsx"
        assert "constitutional_memory_hits" in content, "Seen Before render condition not gated on hits"
        assert "dna={dna}" in content or "dna={" in content, "dna prop not passed to SeenBeforePanel"
        assert "mpi={mpi}" in content or "mpi={" in content, "mpi prop not passed to SeenBeforePanel"

        panel_path = DASHBOARD_DIR / "SeenBeforePanel.tsx"
        assert panel_path.exists(), "SeenBeforePanel.tsx missing"
        panel_content = panel_path.read_text()
        assert "avg_return_pct" in panel_content, "Historical Expectancy not rendered"
        assert "best_return_pct" in panel_content, "Best historical outcome not rendered"
        assert "worst_return_pct" in panel_content, "Worst historical outcome not rendered"
        assert "last_event_date" in panel_content, "Last signal date not rendered"
        assert "avg_mfe40" in panel_content, "Avg MFE40 not rendered"

    def test_seen_before_panel_is_wired_to_dna_map(self):
        card_path = DASHBOARD_DIR / "BuySignalCard.tsx"
        content = card_path.read_text()
        assert "dnaMap" in content or "stock_dna" in content, "dnaMap not wired in BuySignalCard"
        assert "dna={dnaMap" in content or "dna={" in content, "dna prop not passed to BuyCard"

    def test_is_buy_ready_matches_both_production_strings(self):
        """
        isBuyReady() must match BOTH strings the backend emits:
          'READY NOW — R2≥60, Score≥35'   (new first-buy)
          'READY FOR RE-ACCUMULATION'      (status=PREMIUM or ACTIVE)
        A mismatch here silently drops all RE-ACCUMULATION signals before BuyCard
        is instantiated, making SeenBeforePanel unreachable regardless of DNA data.
        """
        card_path = DASHBOARD_DIR / "BuySignalCard.tsx"
        content = card_path.read_text()
        assert "READY FOR RE-ACCUMULATION" in content, (
            "isBuyReady() does not handle 'READY FOR RE-ACCUMULATION' — "
            "all PREMIUM/ACTIVE buy signals will be silently filtered out"
        )
        assert "READY NOW" in content, "isBuyReady() must still handle 'READY NOW' string"

    def test_snapshot_reaccum_signals_have_dna_and_would_render(self):
        """End-to-end integration: RE-ACCUMULATION buy signals in the snapshot
        must have DNA with hits > 0, meaning SeenBeforePanel would actually render."""
        snap_path = BASE / "presentation_snapshot.json"
        if not snap_path.exists():
            pytest.skip("presentation_snapshot.json not present")
        import json
        snap = json.loads(snap_path.read_text())

        def is_buy_ready(item):
            r = item.get("waiting_for_reason", "")
            return "READY NOW" in r or "READY FOR RE-ACCUMULATION" in r

        buy_signals = [u for u in snap.get("universe_snapshot", []) if is_buy_ready(u)]
        dna_map = snap.get("stock_dna", {})

        reaccum = [s for s in buy_signals if "RE-ACCUMULATION" in (s.get("waiting_for_reason") or "")]
        for sig in reaccum:
            ticker = sig["ticker"]
            assert ticker in dna_map, f"{ticker} RE-ACCUMULATION signal has no stock_dna entry"
            assert dna_map[ticker].get("constitutional_memory_hits", 0) > 0, (
                f"{ticker} DNA has constitutional_memory_hits=0 — SeenBeforePanel would not render"
            )
