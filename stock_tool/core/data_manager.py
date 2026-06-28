"""High-level OHLCV access: yfinance fetcher + CSV cache + resampling.

Daily data is fetched from yfinance and persisted via :mod:`storage.csv_store`.
Higher timeframes (W/M/Q/Y) are computed on demand from the daily frame and
are *never* written to disk.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

import pandas as pd
import yfinance as yf

from core.config import Config
from storage import csv_store

logger = logging.getLogger(__name__)

VALID_TIMEFRAMES: tuple[str, ...] = ("D", "W", "M", "Q", "Y")

_RESAMPLE_RULE: dict[str, str] = {
    "W": "W-FRI",
    "M": "ME",
    "Q": "QE",
    "Y": "YE",
}

_OHLCV_AGG: dict[str, str] = {
    "Open": "first",
    "High": "max",
    "Low": "min",
    "Close": "last",
    "Volume": "sum",
    "Adj_Close": "last",
}


class DataManagerError(RuntimeError):
    """Raised when a data fetch or resample operation fails."""


def _to_date(value: date | str | None) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _normalise_yf_frame(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Coerce a yfinance frame into the on-disk OHLCV schema."""
    if df is None or df.empty:
        return pd.DataFrame(
            columns=list(csv_store.OHLCV_COLUMNS),
            index=pd.DatetimeIndex([], name=csv_store.INDEX_NAME),
        )

    if isinstance(df.columns, pd.MultiIndex):
        # yfinance multi-ticker mode returns (Field, Ticker); pick our slice.
        if ticker in df.columns.get_level_values(1):
            df = df.xs(ticker, axis=1, level=1)
        else:
            df = df.droplevel(1, axis=1)

    df = df.rename(columns={"Adj Close": "Adj_Close"})
    if "Adj_Close" not in df.columns and "Close" in df.columns:
        # auto_adjust=True drops the Adj Close column; mirror Close into it.
        df["Adj_Close"] = df["Close"]

    missing = [c for c in csv_store.OHLCV_COLUMNS if c not in df.columns]
    if missing:
        raise DataManagerError(
            f"yfinance frame for {ticker!r} missing columns: {missing}"
        )

    df = df[list(csv_store.OHLCV_COLUMNS)].copy()
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    df.index.name = csv_store.INDEX_NAME
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df = df.dropna(how="all")
    return df


class DataManager:
    """Fetches, caches, and resamples OHLCV price data.

    Args:
        config: Loaded :class:`core.config.Config`.
        downloader: Optional callable matching ``yfinance.download``'s
            signature. Injected for tests; defaults to :func:`yfinance.download`.
    """

    def __init__(
        self,
        config: Config,
        downloader: Any = None,
    ) -> None:
        self._config = config
        self._download_fn = downloader if downloader is not None else yf.download

    @property
    def price_dir(self):
        return self._config.data.price_dir

    def download(
        self,
        ticker: str,
        start: date | str,
        end: date | str | None = None,
    ) -> pd.DataFrame:
        """Download daily OHLCV for ``ticker`` from yfinance.

        The end date is exclusive in yfinance, so we pass ``end + 1 day`` when
        a value is provided to make the range inclusive of ``end``.

        Returns:
            DataFrame with a ``DatetimeIndex`` named ``"Date"`` and the
            canonical OHLCV columns. May be empty if yfinance returned no data.
        """
        start_d = _to_date(start)
        end_d = _to_date(end)
        if start_d is None:
            raise DataManagerError("start date is required for download()")

        end_arg = (end_d + timedelta(days=1)).isoformat() if end_d else None
        logger.info(
            "Downloading %s from %s to %s", ticker, start_d.isoformat(), end_arg
        )
        raw = self._download_fn(
            ticker,
            start=start_d.isoformat(),
            end=end_arg,
            auto_adjust=False,
            threads=False,
            progress=False,
        )
        return _normalise_yf_frame(raw, ticker)

    def get_history(
        self,
        ticker: str,
        start: date | str | None = None,
        end: date | str | None = None,
        timeframe: str = "D",
        refresh: bool = False,
    ) -> pd.DataFrame:
        """Return OHLCV for ``ticker`` resampled to ``timeframe``.

        Behaviour:
            - If a local CSV exists, it is used as the cache.
            - If ``refresh`` is True, missing rows from the cache's last date
              up to ``end`` (or today) are fetched and merged.
            - If no CSV exists, the full range is downloaded starting from
              ``start`` (or ``config.download.default_start_date``).
            - The daily frame is resampled to ``timeframe`` in memory.

        Args:
            ticker: Yahoo Finance symbol (e.g. ``"AAPL"``, ``"0700.HK"``).
            start: Start date. Defaults to ``config.download.default_start_date``.
            end: End date. Defaults to today.
            timeframe: One of ``D``, ``W``, ``M``, ``Q``, ``Y``.
            refresh: Force a fetch of any rows newer than the cache.

        Returns:
            DataFrame with the canonical OHLCV columns, indexed by date.
        """
        if timeframe not in VALID_TIMEFRAMES:
            raise DataManagerError(
                f"Invalid timeframe {timeframe!r}; expected one of {VALID_TIMEFRAMES}"
            )

        start_d = _to_date(start) or self._config.download.default_start_date
        end_d = _to_date(end) or date.today()

        cached = (
            csv_store.read(ticker, self.price_dir)
            if csv_store.exists(ticker, self.price_dir)
            else None
        )

        if cached is None or cached.empty:
            fresh = self.download(ticker, start=start_d, end=end_d)
            if fresh.empty:
                raise DataManagerError(
                    f"yfinance returned no data for {ticker!r} "
                    f"between {start_d} and {end_d}"
                )
            csv_store.write(ticker, self.price_dir, fresh)
            daily = fresh
        else:
            daily = cached
            if refresh:
                latest = cached.index.max().date()
                fetch_from = latest + timedelta(days=1)
                if fetch_from <= end_d:
                    new_rows = self.download(ticker, start=fetch_from, end=end_d)
                    if not new_rows.empty:
                        daily = csv_store.merge(ticker, self.price_dir, new_rows)

        daily = daily.loc[
            (daily.index >= pd.Timestamp(start_d)) & (daily.index <= pd.Timestamp(end_d))
        ]
        return self.resample(daily, timeframe)

    @staticmethod
    def resample(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
        """Resample a daily OHLCV frame to ``D/W/M/Q/Y``.

        Aggregation: Open=first, High=max, Low=min, Close=last,
        Volume=sum, Adj_Close=last. Empty bars are dropped.
        """
        if timeframe not in VALID_TIMEFRAMES:
            raise DataManagerError(
                f"Invalid timeframe {timeframe!r}; expected one of {VALID_TIMEFRAMES}"
            )
        if not isinstance(df.index, pd.DatetimeIndex):
            raise DataManagerError("resample requires a DatetimeIndex")
        if timeframe == "D" or df.empty:
            return df.copy()

        rule = _RESAMPLE_RULE[timeframe]
        agg = {c: _OHLCV_AGG[c] for c in df.columns if c in _OHLCV_AGG}
        out = df.resample(rule).agg(agg).dropna(how="all")
        out.index.name = csv_store.INDEX_NAME
        return out
