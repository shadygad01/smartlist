import csv
import json
from pathlib import Path

import numpy as np
import pandas as pd

import event_timeline_engine as timeline
from main import calculate_volume_spike_ratio


def _write_volume_csv(path: Path, previous_volume: float, current_volume: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for index in range(22):
        rows.append({
            "Date": f"2026-08-{index + 1:02d}",
            "Open": "1",
            "High": "1",
            "Low": "1",
            "Close": "1",
            "Volume": str(current_volume if index == 21 else previous_volume),
        })
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def test_volume_ratio_returns_none_when_baseline_is_zero():
    volumes = pd.Series([0.0] * 21 + [438592.0])
    assert calculate_volume_spike_ratio(volumes) is None


def test_volume_ratio_uses_previous_21_rows_and_rounds():
    volumes = pd.Series([100.0] * 21 + [296.0])
    assert calculate_volume_spike_ratio(volumes) == 2.96


def test_volume_ratio_returns_none_for_short_or_nonfinite_data():
    assert calculate_volume_spike_ratio(pd.Series([100.0] * 21)) is None
    assert calculate_volume_spike_ratio(pd.Series([100.0] * 21 + [np.nan])) is None


def test_log_vol_spike_rejects_nonpositive_ratio(tmp_path, monkeypatch):
    monkeypatch.setattr(timeline, "_DB_PATH", tmp_path / "events.db")
    assert timeline.log_vol_spike("ORAS.CA", vol_ratio=0.0) == 0
    assert timeline.get_recent_events() == []


def test_purge_invalid_zero_baseline_spike_preserves_valid_spike(tmp_path, monkeypatch):
    monkeypatch.setattr(timeline, "BASE", tmp_path)
    monkeypatch.setattr(timeline, "_DB_PATH", tmp_path / "events.db")
    _write_volume_csv(
        tmp_path / "historical_data" / "historical_data" / "ORAS.CA.csv",
        previous_volume=0,
        current_volume=438592,
    )
    _write_volume_csv(
        tmp_path / "historical_data" / "historical_data" / "MCQE.CA.csv",
        previous_volume=100,
        current_volume=296,
    )

    timeline.log_vol_spike(
        "ORAS.CA", vol_ratio=438592.0, timestamp="2026-08-22T14:30:00+03:00"
    )
    timeline.log_vol_spike(
        "MCQE.CA", vol_ratio=2.96, timestamp="2026-08-22T14:30:00+03:00"
    )

    assert timeline.purge_invalid_volume_spikes() == 1
    remaining = timeline.get_recent_events(limit=10)
    assert [row["ticker"] for row in remaining] == ["MCQE.CA"]
    assert json.loads(remaining[0]["metadata"])["vol_ratio"] == 2.96
