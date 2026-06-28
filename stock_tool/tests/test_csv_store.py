"""Tests for storage.csv_store."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from storage import csv_store
from storage.csv_store import CsvStoreError, OHLCV_COLUMNS


def _make_df(dates: list[str], close_offset: float = 0.0) -> pd.DataFrame:
    idx = pd.DatetimeIndex(pd.to_datetime(dates), name="Date")
    n = len(idx)
    return pd.DataFrame(
        {
            "Open": [100.0 + i for i in range(n)],
            "High": [101.0 + i for i in range(n)],
            "Low": [99.0 + i for i in range(n)],
            "Close": [100.5 + i + close_offset for i in range(n)],
            "Volume": [1_000 * (i + 1) for i in range(n)],
            "Adj_Close": [100.5 + i + close_offset for i in range(n)],
        },
        index=idx,
    )


def test_market_subfolder_routing():
    assert csv_store.market_subfolder("AAPL") == "US"
    assert csv_store.market_subfolder("MSFT") == "US"
    assert csv_store.market_subfolder("0700.HK") == "HK"
    assert csv_store.market_subfolder("BP.L") == "LSE"
    assert csv_store.market_subfolder("RY.TO") == "TSX"
    assert csv_store.market_subfolder("BHP.AX") == "ASX"


def test_csv_path_includes_market_subfolder(tmp_path):
    assert csv_store.csv_path("AAPL", tmp_path) == tmp_path / "US" / "AAPL.csv"
    assert csv_store.csv_path("0700.HK", tmp_path) == tmp_path / "HK" / "0700.HK.csv"


def test_write_creates_subdir_and_read_roundtrips(tmp_path):
    df = _make_df(["2024-01-02", "2024-01-03", "2024-01-04"])
    out_path = csv_store.write("AAPL", tmp_path, df)

    assert out_path == tmp_path / "US" / "AAPL.csv"
    assert out_path.is_file()

    loaded = csv_store.read("AAPL", tmp_path)
    pd.testing.assert_frame_equal(loaded, df, check_freq=False)


def test_write_normalises_unsorted_input(tmp_path):
    df = _make_df(["2024-01-04", "2024-01-02", "2024-01-03"])
    csv_store.write("AAPL", tmp_path, df)

    loaded = csv_store.read("AAPL", tmp_path)
    assert list(loaded.index.strftime("%Y-%m-%d")) == [
        "2024-01-02",
        "2024-01-03",
        "2024-01-04",
    ]


def test_read_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        csv_store.read("AAPL", tmp_path)


def test_read_rejects_csv_missing_columns(tmp_path):
    bad_path = tmp_path / "US" / "AAPL.csv"
    bad_path.parent.mkdir(parents=True)
    bad_path.write_text("Date,Open,High\n2024-01-02,1,2\n", encoding="utf-8")
    with pytest.raises(CsvStoreError, match="missing columns"):
        csv_store.read("AAPL", tmp_path)


def test_write_rejects_dataframe_without_required_columns(tmp_path):
    bad = pd.DataFrame(
        {"Open": [1.0], "High": [2.0]},
        index=pd.DatetimeIndex(pd.to_datetime(["2024-01-02"]), name="Date"),
    )
    with pytest.raises(CsvStoreError, match="missing required columns"):
        csv_store.write("AAPL", tmp_path, bad)


def test_write_rejects_non_datetime_index(tmp_path):
    bad = pd.DataFrame(
        {col: [1.0] for col in OHLCV_COLUMNS},
        index=pd.Index([0]),
    )
    with pytest.raises(CsvStoreError, match="DatetimeIndex"):
        csv_store.write("AAPL", tmp_path, bad)


def test_merge_writes_when_no_existing_file(tmp_path):
    df = _make_df(["2024-01-02", "2024-01-03"])
    merged = csv_store.merge("AAPL", tmp_path, df)

    assert csv_store.exists("AAPL", tmp_path)
    assert len(merged) == 2
    pd.testing.assert_frame_equal(
        csv_store.read("AAPL", tmp_path), df, check_freq=False
    )


def test_merge_appends_new_rows(tmp_path):
    initial = _make_df(["2024-01-02", "2024-01-03"])
    csv_store.write("AAPL", tmp_path, initial)

    new_rows = _make_df(["2024-01-04", "2024-01-05"])
    merged = csv_store.merge("AAPL", tmp_path, new_rows)

    assert len(merged) == 4
    assert merged.index.is_monotonic_increasing
    persisted = csv_store.read("AAPL", tmp_path)
    assert len(persisted) == 4


def test_merge_dedupes_overlapping_dates_with_new_winning(tmp_path):
    initial = _make_df(["2024-01-02", "2024-01-03", "2024-01-04"], close_offset=0.0)
    csv_store.write("AAPL", tmp_path, initial)

    overlapping = _make_df(["2024-01-04", "2024-01-05"], close_offset=10.0)
    merged = csv_store.merge("AAPL", tmp_path, overlapping)

    assert len(merged) == 4
    # 2024-01-04 should reflect the new frame's value (i=0 in the new frame,
    # so Close = 100.5 + 0 + 10 = 110.5), not the original (Close = 102.5).
    jan_4 = merged.loc[pd.Timestamp("2024-01-04")]
    assert jan_4["Close"] == pytest.approx(110.5)
    assert jan_4["Adj_Close"] == pytest.approx(110.5)


def test_latest_date_returns_none_when_no_file(tmp_path):
    assert csv_store.latest_date("AAPL", tmp_path) is None


def test_latest_date_returns_max_date(tmp_path):
    df = _make_df(["2024-01-02", "2024-01-05", "2024-01-03"])
    csv_store.write("AAPL", tmp_path, df)
    assert csv_store.latest_date("AAPL", tmp_path) == date(2024, 1, 5)


def test_detect_gaps_returns_empty_for_continuous(tmp_path):
    df = _make_df(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"])
    assert csv_store.detect_gaps(df) == []


def test_detect_gaps_finds_missing_weekday(tmp_path):
    # Skip 2024-01-04 (Thursday).
    df = _make_df(["2024-01-02", "2024-01-03", "2024-01-05"])
    gaps = csv_store.detect_gaps(df)
    assert gaps == [(date(2024, 1, 4), date(2024, 1, 4))]
