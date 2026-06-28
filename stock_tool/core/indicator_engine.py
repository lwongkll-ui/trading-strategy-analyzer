"""Technical indicators computed in pure pandas/numpy.

Each function takes a price ``Series`` (typically ``Close``) and returns a
named ``Series`` (or a multi-column ``DataFrame`` for MACD). All functions
preserve the input's index so results align directly with the source frame.

The :class:`IndicatorEngine` class is a thin convenience wrapper that pulls
default periods from :class:`core.config.IndicatorsConfig`.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from core.config import IndicatorsConfig

logger = logging.getLogger(__name__)


class IndicatorError(ValueError):
    """Raised when an indicator is called with invalid input."""


def _validate_close(close: pd.Series) -> None:
    if not isinstance(close, pd.Series):
        raise IndicatorError(f"Expected pandas Series; got {type(close).__name__}")


def _validate_period(period: int, name: str = "period") -> None:
    if not isinstance(period, (int, np.integer)) or period < 1:
        raise IndicatorError(f"{name} must be a positive integer; got {period!r}")


def sma(close: pd.Series, period: int) -> pd.Series:
    """Simple Moving Average over ``period`` bars.

    Returns:
        Series named ``SMA_{period}`` aligned with ``close``. The first
        ``period - 1`` values are NaN.
    """
    _validate_close(close)
    _validate_period(period)
    out = close.rolling(window=period, min_periods=period).mean()
    return out.rename(f"SMA_{period}")


def ema(close: pd.Series, period: int) -> pd.Series:
    """Exponential Moving Average using ``alpha = 2 / (period + 1)``.

    Uses ``adjust=False`` so values match the recursive formula
    ``EMA[t] = alpha * close[t] + (1 - alpha) * EMA[t-1]``.

    Returns:
        Series named ``EMA_{period}`` aligned with ``close``. The first
        ``period - 1`` values are NaN.
    """
    _validate_close(close)
    _validate_period(period)
    out = close.ewm(span=period, adjust=False, min_periods=period).mean()
    return out.rename(f"EMA_{period}")


def wma(close: pd.Series, period: int) -> pd.Series:
    """Weighted Moving Average with linearly increasing weights ``1..period``.

    Most-recent bar gets weight ``period``; oldest gets weight ``1``.

    Returns:
        Series named ``WMA_{period}`` aligned with ``close``.
    """
    _validate_close(close)
    _validate_period(period)
    weights = np.arange(1, period + 1, dtype=float)
    denom = weights.sum()

    def _wma(window: np.ndarray) -> float:
        return float(np.dot(window, weights) / denom)

    out = close.rolling(window=period, min_periods=period).apply(_wma, raw=True)
    return out.rename(f"WMA_{period}")


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index using Wilder's smoothing.

    Wilder's smoothing is equivalent to an EMA with ``alpha = 1 / period``.
    Result is in the range ``[0, 100]``.

    Returns:
        Series named ``RSI_{period}`` aligned with ``close``. Initial values
        before enough history is available are NaN.
    """
    _validate_close(close)
    _validate_period(period)

    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)

    alpha = 1.0 / period
    avg_gain = gain.ewm(alpha=alpha, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=alpha, adjust=False, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - (100.0 / (1.0 + rs))
    # If avg_loss is 0 the ratio is infinite → RSI = 100.
    out = out.where(avg_loss != 0.0, 100.0)
    # If both are 0 (flat price), RSI is undefined; mark as NaN.
    out = out.where(~((avg_gain == 0.0) & (avg_loss == 0.0)), np.nan)
    return out.rename(f"RSI_{period}")


def macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    """Moving Average Convergence Divergence.

    Args:
        close: Price series.
        fast: Fast EMA period (default 12).
        slow: Slow EMA period (default 26).
        signal: Signal EMA period applied to the MACD line (default 9).

    Returns:
        DataFrame with three columns:
            - ``MACD``      — fast EMA minus slow EMA
            - ``Signal``    — EMA of MACD over ``signal`` periods
            - ``Histogram`` — MACD minus Signal
    """
    _validate_close(close)
    _validate_period(fast, "fast")
    _validate_period(slow, "slow")
    _validate_period(signal, "signal")
    if fast >= slow:
        raise IndicatorError(f"fast ({fast}) must be < slow ({slow})")

    fast_ema = close.ewm(span=fast, adjust=False, min_periods=fast).mean()
    slow_ema = close.ewm(span=slow, adjust=False, min_periods=slow).mean()
    macd_line = fast_ema - slow_ema
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    hist = macd_line - signal_line

    return pd.DataFrame(
        {"MACD": macd_line, "Signal": signal_line, "Histogram": hist},
        index=close.index,
    )


def stc(
    close: pd.Series,
    fast: int = 23,
    slow: int = 50,
    cycle: int = 10,
    factor: float = 0.5,
) -> pd.Series:
    """Schaff Trend Cycle.

    Computes a double-smoothed stochastic of the MACD line. The result
    oscillates in ``[0, 100]`` with conventional overbought/oversold lines
    at 75 / 25.

    Algorithm:
        1. ``macd_line = ema(close, fast) - ema(close, slow)``
        2. First %K: stochastic of ``macd_line`` over ``cycle`` periods
        3. Smooth with EMA factor ``factor`` to get %D
        4. Second %K: stochastic of %D over ``cycle`` periods
        5. Smooth again with EMA factor ``factor`` to get STC

    Returns:
        Series named ``STC_{fast}_{slow}_{cycle}`` aligned with ``close``.
    """
    _validate_close(close)
    _validate_period(fast, "fast")
    _validate_period(slow, "slow")
    _validate_period(cycle, "cycle")
    if fast >= slow:
        raise IndicatorError(f"fast ({fast}) must be < slow ({slow})")
    if not 0.0 < factor <= 1.0:
        raise IndicatorError(f"factor must be in (0, 1]; got {factor!r}")

    fast_ema = close.ewm(span=fast, adjust=False, min_periods=fast).mean()
    slow_ema = close.ewm(span=slow, adjust=False, min_periods=slow).mean()
    macd_line = fast_ema - slow_ema

    def _stoch(series: pd.Series, length: int) -> pd.Series:
        rmin = series.rolling(window=length, min_periods=length).min()
        rmax = series.rolling(window=length, min_periods=length).max()
        rng = (rmax - rmin).replace(0.0, np.nan)
        return ((series - rmin) / rng) * 100.0

    k1 = _stoch(macd_line, cycle).ffill()
    d1 = k1.ewm(alpha=factor, adjust=False).mean()

    k2 = _stoch(d1, cycle).ffill()
    out = k2.ewm(alpha=factor, adjust=False).mean()
    out = out.clip(lower=0.0, upper=100.0)
    return out.rename(f"STC_{fast}_{slow}_{cycle}")


def bband(
    close: pd.Series,
    period: int = 20,
    std_mult: float = 2.0,
) -> pd.DataFrame:
    """Bollinger Bands.

    Returns:
        DataFrame with columns ``BB_Upper``, ``BB_Mid``, ``BB_Lower`` aligned
        with ``close``.  The first ``period - 1`` rows are NaN.
    """
    _validate_close(close)
    _validate_period(period)
    if std_mult <= 0:
        raise IndicatorError(f"std_mult must be positive; got {std_mult!r}")
    mid = close.rolling(window=period, min_periods=period).mean()
    std = close.rolling(window=period, min_periods=period).std(ddof=1)
    band = std_mult * std
    return pd.DataFrame(
        {"BB_Upper": mid + band, "BB_Mid": mid, "BB_Lower": mid - band},
        index=close.index,
    )


def atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """Average True Range using Wilder's smoothing.

    True Range = max(High - Low, |High - prev_Close|, |Low - prev_Close|)

    Returns:
        Series named ``ATR_{period}`` aligned with ``close``.
    """
    for s, name in ((high, "high"), (low, "low"), (close, "close")):
        if not isinstance(s, pd.Series):
            raise IndicatorError(f"Expected pandas Series for {name}")
    _validate_period(period)
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    alpha = 1.0 / period
    out = tr.ewm(alpha=alpha, adjust=False, min_periods=period).mean()
    return out.rename(f"ATR_{period}")


def stoch(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    k_period: int = 14,
    d_period: int = 3,
) -> pd.DataFrame:
    """Stochastic Oscillator (%K and %D).

    %K = (Close - Lowest_Low) / (Highest_High - Lowest_Low) × 100
    %D = SMA(%K, d_period)

    Returns:
        DataFrame with columns ``STOCH_K`` and ``STOCH_D`` aligned with ``close``.
    """
    for s, name in ((high, "high"), (low, "low"), (close, "close")):
        if not isinstance(s, pd.Series):
            raise IndicatorError(f"Expected pandas Series for {name}")
    _validate_period(k_period, "k_period")
    _validate_period(d_period, "d_period")
    lowest = low.rolling(window=k_period, min_periods=k_period).min()
    highest = high.rolling(window=k_period, min_periods=k_period).max()
    rng = (highest - lowest).replace(0.0, np.nan)
    k = ((close - lowest) / rng * 100.0).rename("STOCH_K")
    d = k.rolling(window=d_period, min_periods=d_period).mean().rename("STOCH_D")
    return pd.DataFrame({"STOCH_K": k, "STOCH_D": d}, index=close.index)


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """On-Balance Volume (cumulative direction-weighted volume).

    OBV[t] = OBV[t-1] + Volume[t]  if Close[t] > Close[t-1]
    OBV[t] = OBV[t-1] - Volume[t]  if Close[t] < Close[t-1]
    OBV[t] = OBV[t-1]               if Close[t] == Close[t-1]

    Returns:
        Series named ``OBV`` aligned with ``close``.  No warmup period.
    """
    _validate_close(close)
    if not isinstance(volume, pd.Series):
        raise IndicatorError(
            f"Expected pandas Series for volume; got {type(volume).__name__}"
        )
    delta = close.diff()
    direction = np.sign(delta.to_numpy(dtype=float))
    direction[0] = 0.0  # first bar — no previous close
    obv_vals = (pd.Series(direction, index=close.index) * volume).cumsum()
    return obv_vals.rename("OBV")


def vwap(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
) -> pd.Series:
    """Volume Weighted Average Price (cumulative from start of the data window).

    Typical Price = (High + Low + Close) / 3
    VWAP = Σ(TP × Volume) / Σ(Volume)

    Returns:
        Series named ``VWAP`` aligned with ``close``.
    """
    for s, name in ((high, "high"), (low, "low"), (close, "close"), (volume, "volume")):
        if not isinstance(s, pd.Series):
            raise IndicatorError(f"Expected pandas Series for {name}")
    tp = (high + low + close) / 3.0
    cum_tpv = (tp * volume).cumsum()
    cum_vol = volume.cumsum().replace(0.0, np.nan)
    return (cum_tpv / cum_vol).rename("VWAP")


def fvg(df: pd.DataFrame, lookback: int = 500) -> list[dict]:
    """Detect unfilled Fair Value Gaps (FVG) in OHLCV data.

    A three-candle price imbalance pattern:
    - **Bullish FVG**: High[i-2] < Low[i]  — gap between those two wicks, price
      gapped up and has not yet retraced into the zone.
    - **Bearish FVG**: Low[i-2] > High[i] — gap between those two wicks, price
      gapped down and has not yet retraced into the zone.

    Only *unfilled* FVGs are returned. A bullish FVG is considered filled when any
    subsequent bar's Low touches the top of the gap (Low[i]); a bearish FVG is
    filled when any subsequent bar's High touches the bottom of the gap (High[i]).

    Args:
        df:       OHLCV DataFrame with at least ``High``, ``Low`` columns.
        lookback: Only scan the most recent *lookback* bars (default 500).

    Returns:
        List of dicts, each with keys:
        ``kind`` ('bull'/'bear'), ``bar`` (int, 0-based bar index of the third
        candle), ``gap_low`` (float), ``gap_high`` (float).
    """
    if len(df) < 3:
        return []

    highs = df["High"].to_numpy(dtype=float)
    lows = df["Low"].to_numpy(dtype=float)
    n = len(df)
    start = max(2, n - lookback)

    gaps: list[dict] = []
    for i in range(start, n):
        h_first, l_first = highs[i - 2], lows[i - 2]
        h_third, l_third = highs[i], lows[i]

        if h_first < l_third:  # bullish FVG
            gap_low, gap_high = h_first, l_third
            # Filled when any later bar's Low <= gap_high (enters gap from above)
            filled = i < n - 1 and bool(np.any(lows[i + 1 :] <= gap_high))
            if not filled:
                gaps.append({"kind": "bull", "bar": i, "gap_low": gap_low, "gap_high": gap_high})

        elif l_first > h_third:  # bearish FVG
            gap_low, gap_high = h_third, l_first
            # Filled when any later bar's High >= gap_low (enters gap from below)
            filled = i < n - 1 and bool(np.any(highs[i + 1 :] >= gap_low))
            if not filled:
                gaps.append({"kind": "bear", "bar": i, "gap_low": gap_low, "gap_high": gap_high})

    return gaps


class IndicatorEngine:
    """Convenience wrapper that supplies default periods from a config object.

    Pure indicator math lives in the module-level functions; this class is
    just an ergonomic shortcut for callers that already have a loaded
    :class:`core.config.Config`.
    """

    def __init__(self, config: "IndicatorsConfig") -> None:
        self._config = config

    @property
    def config(self) -> "IndicatorsConfig":
        return self._config

    def sma(self, close: pd.Series, period: int) -> pd.Series:
        return sma(close, period)

    def ema(self, close: pd.Series, period: int) -> pd.Series:
        return ema(close, period)

    def wma(self, close: pd.Series, period: int) -> pd.Series:
        return wma(close, period)

    def rsi(self, close: pd.Series, period: int | None = None) -> pd.Series:
        return rsi(close, period if period is not None else self._config.rsi_period)

    def macd(
        self,
        close: pd.Series,
        fast: int | None = None,
        slow: int | None = None,
        signal: int | None = None,
    ) -> pd.DataFrame:
        return macd(
            close,
            fast=fast if fast is not None else self._config.macd_fast,
            slow=slow if slow is not None else self._config.macd_slow,
            signal=signal if signal is not None else self._config.macd_signal,
        )

    def stc(
        self,
        close: pd.Series,
        fast: int | None = None,
        slow: int | None = None,
        cycle: int | None = None,
        factor: float = 0.5,
    ) -> pd.Series:
        return stc(
            close,
            fast=fast if fast is not None else self._config.stc_fast,
            slow=slow if slow is not None else self._config.stc_slow,
            cycle=cycle if cycle is not None else self._config.stc_cycle,
            factor=factor,
        )

    def bband(
        self,
        close: pd.Series,
        period: int | None = None,
        std_mult: float | None = None,
    ) -> pd.DataFrame:
        return bband(
            close,
            period=period if period is not None else self._config.bb_period,
            std_mult=std_mult if std_mult is not None else self._config.bb_std,
        )

    def atr(
        self,
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        period: int | None = None,
    ) -> pd.Series:
        return atr(
            high, low, close,
            period=period if period is not None else self._config.atr_period,
        )

    def stoch(
        self,
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        k_period: int | None = None,
        d_period: int | None = None,
    ) -> pd.DataFrame:
        return stoch(
            high, low, close,
            k_period=k_period if k_period is not None else self._config.stoch_k,
            d_period=d_period if d_period is not None else self._config.stoch_d,
        )

    def obv(self, close: pd.Series, volume: pd.Series) -> pd.Series:
        return obv(close, volume)

    def vwap(
        self,
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        volume: pd.Series,
    ) -> pd.Series:
        return vwap(high, low, close, volume)
