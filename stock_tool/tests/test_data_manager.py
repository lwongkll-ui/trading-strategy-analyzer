"""Tests for core.data_manager.

yfinance is not actually called: a fake downloader is injected that returns
deterministic frames mimicking yfinance's output schema.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from core.config import (
    ChartConfig,
    Config,
    DataConfig,
    DownloadConfig,
    IndicatorsConfig,
    NewsConfig,
    SchedulerConfig,
)
from core.data_manager import DataManager, DataManagerError
from storage import csv_store


def _make_config(price_dir: Path) -> Config:
    return Config(
        data=DataConfig(price_dir=price_dir, export_dir=price_dir / "exports"),
        download=DownloadConfig(
            default_start_date=date(2024, 1, 1),
            provider="yfinance",
            alpha_vantage_key="",
        ),
        news=NewsConfig(provider="newsapi", newsapi_key="", max_headlines=20),
        chart=ChartConfig(
            default_timeframe="D",
            candle_bull_color="#26a69a",
            candle_bear_color="#ef5350",
            background_color="#131722",
            ma_colors=("#2196F3",),
            export_resolution=(1920, 1080),
        ),
        indicators=IndicatorsConfig(
            rsi_period=14,
            rsi_overbought=70,
            rsi_oversold=30,
            macd_fast=12,
            macd_slow=26,
            macd_signal=9,
            stc_fast=23,
            stc_slow=50,
            stc_cycle=10,
        ),
        scheduler=SchedulerConfig(
            enabled=False,
            cron="0 18 * * 1-5",
            symbols_file=price_dir / "watchlist.txt",
        ),
        source_path=price_dir / "config.yaml",
    )


def _yf_frame(dates: list[str]) -> pd.DataFrame:
    """Mimic yfinance output: 'Adj Close' (with space), DatetimeIndex named 'Date'."""
    idx = pd.DatetimeIndex(pd.to_datetime(dates), name="Date")
    n = len(idx)
    return pd.DataFrame(
        {
            "Open": [100.0 + i for i in range(n)],
            "High": [102.0 + i for i in range(n)],
            "Low": [99.0 + i for i in range(n)],
            "Close": [101.0 + i for i in range(n)],
            "Adj Close": [100.8 + i for i in range(n)],
            "Volume": [1_000_000 + i * 1_000 for i in range(n)],
        },
        index=idx,
    )


class FakeDownloader:
    """Stand-in for yfinance.download — records calls and returns canned frames."""

    def __init__(self, frame: pd.DataFrame | None = None):
        self.frame = frame if frame is not None else _yf_frame([])
        self.calls: list[dict] = []

    def __call__(self, ticker, start=None, end=None, **kwargs):
        self.calls.append({"ticker": ticker, "start": start, "end": end, **kwargs})
        if self.frame.empty:
            return self.frame
        # Filter by requested range to match yfinance's behaviour.
        df = self.frame
        if start is not None:
            df = df[df.index >= pd.Timestamp(start)]
        if end is not None:
            df = df[df.index < pd.Timestamp(end)]
        return df.copy()


def test_resample_daily_passthrough():
    df = pd.DataFrame(
        {col: [1.0, 2.0] for col in csv_store.OHLCV_COLUMNS},
        index=pd.DatetimeIndex(pd.to_datetime(["2024-01-02", "2024-01-03"]), name="Date"),
    )
    out = DataManager.resample(df, "D")
    pd.testing.assert_frame_equal(out, df)


def test_resample_weekly_aggregates_correctly():
    # Mon-Fri week: 2024-01-01 (Mon) to 2024-01-05 (Fri)
    dates = ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
    df = pd.DataFrame(
        {
            "Open": [100, 101, 102, 103, 104],
            "High": [110, 111, 112, 113, 114],
            "Low": [90, 91, 92, 93, 94],
            "Close": [105, 106, 107, 108, 109],
            "Volume": [1000, 2000, 3000, 4000, 5000],
            "Adj_Close": [105, 106, 107, 108, 109],
        },
        index=pd.DatetimeIndex(pd.to_datetime(dates), name="Date"),
    )
    out = DataManager.resample(df, "W")

    assert len(out) == 1
    week = out.iloc[0]
    assert week["Open"] == 100        # first
    assert week["High"] == 114        # max
    assert week["Low"] == 90          # min
    assert week["Close"] == 109       # last
    assert week["Volume"] == 15_000   # sum
    assert week["Adj_Close"] == 109   # last


def test_resample_monthly_buckets_by_month():
    dates = pd.date_range("2024-01-02", "2024-02-29", freq="B")
    df = pd.DataFrame(
        {col: range(len(dates)) for col in csv_store.OHLCV_COLUMNS},
        index=dates,
    )
    df.index.name = "Date"
    out = DataManager.resample(df, "M")
    assert len(out) == 2  # Jan and Feb buckets


def test_resample_quarterly_and_yearly():
    dates = pd.date_range("2023-01-02", "2024-12-31", freq="B")
    df = pd.DataFrame(
        {col: range(len(dates)) for col in csv_store.OHLCV_COLUMNS},
        index=dates,
    )
    df.index.name = "Date"

    q = DataManager.resample(df, "Q")
    assert len(q) == 8  # 2 years × 4 quarters

    y = DataManager.resample(df, "Y")
    assert len(y) == 2


def test_resample_invalid_timeframe_raises():
    df = pd.DataFrame(
        {col: [1.0] for col in csv_store.OHLCV_COLUMNS},
        index=pd.DatetimeIndex(pd.to_datetime(["2024-01-02"]), name="Date"),
    )
    with pytest.raises(DataManagerError, match="Invalid timeframe"):
        DataManager.resample(df, "X")


def test_get_history_downloads_when_no_cache(tmp_path):
    cfg = _make_config(tmp_path)
    fake = FakeDownloader(_yf_frame(["2024-01-02", "2024-01-03", "2024-01-04"]))
    dm = DataManager(cfg, downloader=fake)

    result = dm.get_history("AAPL", start=date(2024, 1, 1), end=date(2024, 1, 4))

    assert len(fake.calls) == 1
    assert fake.calls[0]["ticker"] == "AAPL"
    assert fake.calls[0]["auto_adjust"] is False
    assert fake.calls[0]["threads"] is False
    assert csv_store.exists("AAPL", tmp_path)
    assert list(result.columns) == list(csv_store.OHLCV_COLUMNS)
    assert len(result) == 3


def test_get_history_uses_cache_without_refresh(tmp_path):
    cfg = _make_config(tmp_path)

    # Pre-populate the cache.
    cached = pd.DataFrame(
        {col: [1.0, 2.0, 3.0] for col in csv_store.OHLCV_COLUMNS},
        index=pd.DatetimeIndex(
            pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]), name="Date"
        ),
    )
    csv_store.write("AAPL", tmp_path, cached)

    fake = FakeDownloader()  # Should never be called.
    dm = DataManager(cfg, downloader=fake)

    result = dm.get_history(
        "AAPL", start=date(2024, 1, 2), end=date(2024, 1, 4), refresh=False
    )

    assert fake.calls == []
    assert len(result) == 3


def test_get_history_refresh_fetches_only_new_rows(tmp_path):
    cfg = _make_config(tmp_path)

    cached = pd.DataFrame(
        {col: [1.0, 2.0] for col in csv_store.OHLCV_COLUMNS},
        index=pd.DatetimeIndex(pd.to_datetime(["2024-01-02", "2024-01-03"]), name="Date"),
    )
    csv_store.write("AAPL", tmp_path, cached)

    fake = FakeDownloader(_yf_frame(["2024-01-04", "2024-01-05"]))
    dm = DataManager(cfg, downloader=fake)

    result = dm.get_history(
        "AAPL", start=date(2024, 1, 2), end=date(2024, 1, 5), refresh=True
    )

    assert len(fake.calls) == 1
    # Should fetch from day after the cached max (Jan 3) → Jan 4.
    assert fake.calls[0]["start"] == "2024-01-04"
    assert len(result) == 4


def test_get_history_renames_yfinance_adj_close_column(tmp_path):
    cfg = _make_config(tmp_path)
    fake = FakeDownloader(_yf_frame(["2024-01-02"]))
    dm = DataManager(cfg, downloader=fake)

    result = dm.get_history("AAPL", start=date(2024, 1, 1), end=date(2024, 1, 2))

    assert "Adj_Close" in result.columns
    assert "Adj Close" not in result.columns


def test_get_history_writes_to_correct_market_subfolder(tmp_path):
    cfg = _make_config(tmp_path)
    fake = FakeDownloader(_yf_frame(["2024-01-02", "2024-01-03"]))
    dm = DataManager(cfg, downloader=fake)

    dm.get_history("0700.HK", start=date(2024, 1, 1), end=date(2024, 1, 3))

    assert (tmp_path / "HK" / "0700.HK.csv").is_file()
    assert not (tmp_path / "US" / "0700.HK.csv").exists()


def test_get_history_invalid_timeframe_raises(tmp_path):
    cfg = _make_config(tmp_path)
    dm = DataManager(cfg, downloader=FakeDownloader())
    with pytest.raises(DataManagerError, match="Invalid timeframe"):
        dm.get_history("AAPL", timeframe="X")


def test_get_history_empty_response_raises(tmp_path):
    cfg = _make_config(tmp_path)
    fake = FakeDownloader(_yf_frame([]))  # Empty.
    dm = DataManager(cfg, downloader=fake)
    with pytest.raises(DataManagerError, match="no data"):
        dm.get_history("AAPL", start=date(2024, 1, 1), end=date(2024, 1, 5))


def test_get_history_resamples_to_weekly(tmp_path):
    cfg = _make_config(tmp_path)
    fake = FakeDownloader(
        _yf_frame(
            ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
        )
    )
    dm = DataManager(cfg, downloader=fake)

    weekly = dm.get_history(
        "AAPL", start=date(2024, 1, 1), end=date(2024, 1, 5), timeframe="W"
    )

    assert len(weekly) == 1
    assert weekly.index[0].weekday() == 4  # Friday


def test_download_passes_inclusive_end_date(tmp_path):
    cfg = _make_config(tmp_path)
    fake = FakeDownloader(_yf_frame(["2024-01-02", "2024-01-03"]))
    dm = DataManager(cfg, downloader=fake)

    dm.download("AAPL", start=date(2024, 1, 2), end=date(2024, 1, 3))
    # yfinance end is exclusive, so we should pass Jan 4 to include Jan 3.
    assert fake.calls[0]["end"] == "2024-01-04"
    assert fake.calls[0]["start"] == "2024-01-02"
