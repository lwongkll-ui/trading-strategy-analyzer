"""CSV-backed OHLCV storage for daily price files.

Each ticker is stored in its own file under a market-specific subfolder of
``config.data.price_dir`` (e.g. ``US/AAPL.csv``, ``HK/0700.HK.csv``).

In-memory shape: a ``pandas.DataFrame`` with a ``DatetimeIndex`` named
``"Date"`` and columns ``[Open, High, Low, Close, Volume, Adj_Close]``.

On disk: header + rows, dates as ``YYYY-MM-DD``::

    Date,Open,High,Low,Close,Volume,Adj_Close
    2024-01-02,187.15,188.44,183.89,185.64,82488700,184.95
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

OHLCV_COLUMNS: tuple[str, ...] = (
    "Open",
    "High",
    "Low",
    "Close",
    "Volume",
    "Adj_Close",
)
INDEX_NAME = "Date"
DATE_FORMAT = "%Y-%m-%d"

_MARKET_BY_SUFFIX: dict[str, str] = {
    ".HK": "HK",
    ".L": "LSE",
    ".TO": "TSX",
    ".AX": "ASX",
    ".T": "JP",
}


class CsvStoreError(ValueError):
    """Raised when an OHLCV CSV is malformed or a DataFrame violates the schema."""


def market_subfolder(ticker: str) -> str:
    """Return the market subfolder name for a yfinance-style ticker.

    Examples:
        >>> market_subfolder("AAPL")
        'US'
        >>> market_subfolder("0700.HK")
        'HK'
        >>> market_subfolder("BP.L")
        'LSE'
    """
    upper = ticker.upper()
    for suffix, folder in _MARKET_BY_SUFFIX.items():
        if upper.endswith(suffix):
            return folder
    return "US"


def csv_path(ticker: str, base_dir: Path) -> Path:
    """Return the absolute path to the CSV file for ``ticker``.

    Note:
        This does not create any directories. Call :func:`write` or
        :func:`merge` to create the parent directory on demand.
    """
    return Path(base_dir) / market_subfolder(ticker) / f"{ticker}.csv"


def exists(ticker: str, base_dir: Path) -> bool:
    """Return ``True`` if a CSV file already exists for ``ticker``."""
    return csv_path(ticker, base_dir).is_file()


def _validate_df(df: pd.DataFrame) -> None:
    missing = [c for c in OHLCV_COLUMNS if c not in df.columns]
    if missing:
        raise CsvStoreError(f"DataFrame is missing required columns: {missing}")
    if not isinstance(df.index, pd.DatetimeIndex):
        raise CsvStoreError(
            f"DataFrame index must be a DatetimeIndex; got {type(df.index).__name__}"
        )


def read(ticker: str, base_dir: Path) -> pd.DataFrame:
    """Read the OHLCV CSV for ``ticker``.

    Returns:
        DataFrame with a ``DatetimeIndex`` named ``"Date"``. The frame is
        sorted ascending by date and any duplicate dates are dropped (keeping
        the last occurrence).

    Raises:
        FileNotFoundError: The CSV file does not exist.
        CsvStoreError: The file is missing required columns.
    """
    path = csv_path(ticker, base_dir)
    if not path.is_file():
        raise FileNotFoundError(f"No CSV for ticker {ticker!r} at {path}")

    df = pd.read_csv(path, parse_dates=["Date"])
    if "Date" not in df.columns:
        raise CsvStoreError(f"CSV {path} is missing the 'Date' column")
    df = df.set_index("Date")
    df.index.name = INDEX_NAME

    missing = [c for c in OHLCV_COLUMNS if c not in df.columns]
    if missing:
        raise CsvStoreError(f"CSV {path} is missing columns: {missing}")

    df = df[list(OHLCV_COLUMNS)]
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df


def write(ticker: str, base_dir: Path, df: pd.DataFrame) -> Path:
    """Write ``df`` to the CSV file for ``ticker``, overwriting any existing file.

    The frame is normalised before writing: sorted ascending, duplicate dates
    dropped (last wins), columns reordered to the canonical OHLCV layout.

    Returns:
        The path that was written.
    """
    _validate_df(df)
    path = csv_path(ticker, base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)

    out = df[list(OHLCV_COLUMNS)].copy()
    out = out[~out.index.duplicated(keep="last")].sort_index()
    out.index.name = INDEX_NAME
    out.to_csv(path, index=True, date_format=DATE_FORMAT)
    logger.debug("Wrote %d rows to %s", len(out), path)
    return path


def merge(ticker: str, base_dir: Path, new_df: pd.DataFrame) -> pd.DataFrame:
    """Merge ``new_df`` into the existing CSV for ``ticker`` and persist the result.

    Behaviour:
        - If the CSV does not exist, ``new_df`` is written as-is.
        - If it does exist, rows are concatenated; on duplicate dates, rows
          from ``new_df`` win (treated as the more recent source of truth).
        - The merged frame is sorted ascending and written back.

    Returns:
        The merged DataFrame that was persisted.
    """
    _validate_df(new_df)
    path = csv_path(ticker, base_dir)
    if path.is_file():
        existing = read(ticker, base_dir)
        combined = pd.concat([existing, new_df[list(OHLCV_COLUMNS)]])
        combined = combined[~combined.index.duplicated(keep="last")].sort_index()
    else:
        combined = new_df[list(OHLCV_COLUMNS)].copy().sort_index()

    write(ticker, base_dir, combined)
    return combined


def latest_date(ticker: str, base_dir: Path) -> date | None:
    """Return the most recent date present in the CSV, or ``None`` if no CSV.

    Useful for incremental downloads: fetch from ``latest_date + 1`` to today.
    """
    if not exists(ticker, base_dir):
        return None
    df = read(ticker, base_dir)
    if df.empty:
        return None
    return df.index.max().date()


def detect_gaps(df: pd.DataFrame) -> list[tuple[date, date]]:
    """Detect missing business days inside the date range covered by ``df``.

    Only weekdays are considered (Mon–Fri). Holidays are not modelled, so this
    will report holidays as gaps; treat the result as a hint, not a definitive
    integrity check.

    Returns:
        A list of ``(gap_start, gap_end)`` inclusive ranges of missing weekdays.
    """
    _validate_df(df)
    if df.empty:
        return []

    expected = pd.bdate_range(start=df.index.min(), end=df.index.max())
    present = df.index.normalize()
    missing = expected.difference(present)
    if missing.empty:
        return []

    gaps: list[tuple[date, date]] = []
    run_start = run_end = missing[0]
    for ts in missing[1:]:
        if (ts - run_end).days <= 3:
            run_end = ts
        else:
            gaps.append((run_start.date(), run_end.date()))
            run_start = run_end = ts
    gaps.append((run_start.date(), run_end.date()))
    return gaps
