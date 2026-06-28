"""Stock scanner engine — SMA200/50/10 and RSI for all cached tickers.

The heavy work runs in :class:`ScanWorker` (a QThread) so the UI stays
responsive. The main thread wires up signals and updates the results table.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from PyQt6.QtCore import QThread, pyqtSignal

from storage import csv_store

RESOURCES_DIR = Path(__file__).parent.parent / "resources"


# ── result / criteria dataclasses ─────────────────────────────────────────────

@dataclass
class ScanResult:
    symbol: str
    name: str
    market: str
    price: float
    sma200: float | None
    sma50: float | None
    sma10: float | None
    rsi: float | None
    above_sma200: bool | None       # price > SMA200
    sma10_above_sma50: bool | None  # SMA10 > SMA50


@dataclass
class ScanCriteria:
    markets: list[str]      # subset of ["HSI", "SP500"]
    sma200: str             # "any" | "above" | "below"
    sma_cross: str          # "any" | "golden" | "death"
    rsi: str                # "any" | "overbought" | "oversold"
    fetch_missing: bool = False


# ── constituent lists ─────────────────────────────────────────────────────────

def load_constituents(market: str) -> list[tuple[str, str]]:
    """Return [(ticker, name), ...] for *market* (``"HSI"`` or ``"SP500"``)."""
    fname = "hsi_constituents.csv" if market == "HSI" else "sp500_constituents.csv"
    path = RESOURCES_DIR / fname
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return [(row["ticker"], row["name"]) for row in reader]


# ── indicator helpers ─────────────────────────────────────────────────────────

def _sma(series: pd.Series, n: int) -> float | None:
    if len(series) < n:
        return None
    val = series.rolling(n).mean().iloc[-1]
    return float(val) if pd.notna(val) else None


def _rsi(series: pd.Series, period: int = 14) -> float | None:
    if len(series) < period + 1:
        return None
    delta = series.diff().dropna()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    val = (100 - 100 / (1 + rs)).iloc[-1]
    return float(val) if pd.notna(val) else None


# ── single-ticker scan ────────────────────────────────────────────────────────

def scan_ticker(
    ticker: str,
    name: str,
    market: str,
    price_dir: Path,
) -> ScanResult | None:
    """Compute scan metrics from the cached daily CSV.

    Returns ``None`` if no cache exists or data is too short.
    """
    if not csv_store.exists(ticker, price_dir):
        return None

    df = csv_store.read(ticker, price_dir)
    if df is None or df.empty or len(df) < 10:
        return None

    close = df["Close"]
    price = float(close.iloc[-1])
    sma200 = _sma(close, 200)
    sma50 = _sma(close, 50)
    sma10 = _sma(close, 10)
    rsi = _rsi(close)

    above_sma200 = (price > sma200) if sma200 is not None else None
    sma10_above_sma50 = (
        (sma10 > sma50)
        if (sma10 is not None and sma50 is not None)
        else None
    )

    return ScanResult(
        symbol=ticker,
        name=name,
        market=market,
        price=price,
        sma200=sma200,
        sma50=sma50,
        sma10=sma10,
        rsi=rsi,
        above_sma200=above_sma200,
        sma10_above_sma50=sma10_above_sma50,
    )


def matches(result: ScanResult, criteria: ScanCriteria) -> bool:
    """Return True if *result* satisfies all active filter criteria."""
    if criteria.sma200 == "above" and result.above_sma200 is not True:
        return False
    if criteria.sma200 == "below" and result.above_sma200 is not False:
        return False
    if criteria.sma_cross == "golden" and result.sma10_above_sma50 is not True:
        return False
    if criteria.sma_cross == "death" and result.sma10_above_sma50 is not False:
        return False
    if criteria.rsi == "overbought" and (result.rsi is None or result.rsi <= 80):
        return False
    if criteria.rsi == "oversold" and (result.rsi is None or result.rsi >= 20):
        return False
    return True


# ── background worker ─────────────────────────────────────────────────────────

class ScanWorker(QThread):
    """Iterates over a symbol list in a background thread, emitting matches."""

    result_ready = pyqtSignal(object)    # ScanResult
    progress = pyqtSignal(int, int)      # current index, total
    status_update = pyqtSignal(str)      # one-line text for the status label
    scan_finished = pyqtSignal(int, int) # matched count, scanned count

    def __init__(
        self,
        symbols: list[tuple[str, str, str]],  # (ticker, name, market)
        price_dir: Path,
        criteria: ScanCriteria,
        data_manager=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._symbols = symbols
        self._price_dir = price_dir
        self._criteria = criteria
        self._dm = data_manager
        self._abort = False

    def abort(self) -> None:
        self._abort = True

    def run(self) -> None:
        total = len(self._symbols)
        matched = 0
        scanned = 0

        for i, (ticker, name, market) in enumerate(self._symbols):
            if self._abort:
                break

            self.progress.emit(i + 1, total)

            if not csv_store.exists(ticker, self._price_dir):
                if self._criteria.fetch_missing and self._dm is not None:
                    self.status_update.emit(f"Downloading {ticker}…")
                    try:
                        self._dm.get_history(ticker)
                    except Exception:
                        scanned += 1
                        continue
                else:
                    scanned += 1
                    continue

            result = scan_ticker(ticker, name, market, self._price_dir)
            if result is not None:
                scanned += 1
                if matches(result, self._criteria):
                    matched += 1
                    self.result_ready.emit(result)

        self.scan_finished.emit(matched, scanned)
