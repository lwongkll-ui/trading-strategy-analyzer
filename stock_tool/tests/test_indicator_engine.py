"""Tests for core.indicator_engine."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.config import IndicatorsConfig
from core.indicator_engine import (
    IndicatorEngine,
    IndicatorError,
    atr,
    bband,
    ema,
    macd,
    obv,
    rsi,
    sma,
    stc,
    stoch,
    vwap,
    wma,
)


def _series(values: list[float]) -> pd.Series:
    idx = pd.date_range("2024-01-01", periods=len(values), freq="B")
    return pd.Series(values, index=idx, name="Close")


def _ramp(n: int, start: float = 100.0, step: float = 1.0) -> pd.Series:
    return _series([start + i * step for i in range(n)])


# ---------- SMA ----------

def test_sma_known_values():
    s = _series([1, 2, 3, 4, 5, 6])
    result = sma(s, 3)
    assert result.name == "SMA_3"
    assert pd.isna(result.iloc[0])
    assert pd.isna(result.iloc[1])
    assert result.iloc[2] == pytest.approx(2.0)  # mean(1,2,3)
    assert result.iloc[3] == pytest.approx(3.0)  # mean(2,3,4)
    assert result.iloc[5] == pytest.approx(5.0)  # mean(4,5,6)


def test_sma_preserves_index():
    s = _ramp(10)
    result = sma(s, 3)
    pd.testing.assert_index_equal(result.index, s.index)


def test_sma_invalid_period_raises():
    with pytest.raises(IndicatorError, match="period"):
        sma(_ramp(10), 0)
    with pytest.raises(IndicatorError, match="period"):
        sma(_ramp(10), -3)


def test_sma_rejects_non_series():
    with pytest.raises(IndicatorError, match="Series"):
        sma([1, 2, 3], 2)  # type: ignore[arg-type]


# ---------- EMA ----------

def test_ema_recursive_formula():
    # EMA[t] = alpha*close[t] + (1-alpha)*EMA[t-1], alpha = 2/(period+1)
    s = _series([10.0, 11.0, 12.0, 13.0])
    result = ema(s, 3)
    alpha = 2.0 / (3 + 1)  # 0.5

    # min_periods=3 → first two are NaN
    assert pd.isna(result.iloc[0])
    assert pd.isna(result.iloc[1])
    # Recursion seeds from close[0]: e0=10, e1=0.5*11+0.5*10=10.5, e2=0.5*12+0.5*10.5=11.25
    assert result.iloc[2] == pytest.approx(11.25)
    # e3 = 0.5*13 + 0.5*11.25 = 12.125
    assert result.iloc[3] == pytest.approx(12.125)


def test_ema_constant_input_converges_to_constant():
    s = _series([5.0] * 30)
    result = ema(s, 5)
    assert result.iloc[-1] == pytest.approx(5.0)


def test_ema_name_is_set():
    assert ema(_ramp(20), 10).name == "EMA_10"


# ---------- WMA ----------

def test_wma_known_values():
    s = _series([1, 2, 3, 4, 5])
    result = wma(s, 3)
    # weights = [1, 2, 3], denom = 6
    # row 2 (window 1,2,3): (1*1 + 2*2 + 3*3) / 6 = 14/6
    assert result.iloc[2] == pytest.approx(14 / 6)
    # row 3 (window 2,3,4): (1*2 + 2*3 + 3*4) / 6 = 20/6
    assert result.iloc[3] == pytest.approx(20 / 6)


def test_wma_recent_bar_weighted_higher_than_sma():
    # On a rising series, WMA tracks closer to the latest value than SMA.
    s = _ramp(20)
    last = s.iloc[-1]
    assert wma(s, 5).iloc[-1] > sma(s, 5).iloc[-1]
    assert wma(s, 5).iloc[-1] < last


def test_wma_name_is_set():
    assert wma(_ramp(10), 5).name == "WMA_5"


# ---------- RSI ----------

def test_rsi_constant_price_is_nan():
    # No gain, no loss → undefined. We mark as NaN.
    s = _series([50.0] * 30)
    result = rsi(s, 14)
    # All values where avg_gain==avg_loss==0 should be NaN.
    assert result.iloc[20:].isna().all()


def test_rsi_only_gains_is_100():
    # Strictly rising → no losses → RSI = 100.
    s = _ramp(40, start=100.0, step=1.0)
    result = rsi(s, 14)
    assert result.iloc[-1] == pytest.approx(100.0)


def test_rsi_only_losses_is_0():
    # Strictly falling → no gains → RSI = 0.
    s = _ramp(40, start=200.0, step=-1.0)
    result = rsi(s, 14)
    assert result.iloc[-1] == pytest.approx(0.0)


def test_rsi_in_range():
    rng = np.random.default_rng(42)
    s = _series(list(np.cumsum(rng.normal(0, 1, 200)) + 100))
    result = rsi(s, 14)
    valid = result.dropna()
    assert (valid >= 0.0).all()
    assert (valid <= 100.0).all()


def test_rsi_name_and_default_period():
    out = rsi(_ramp(40))
    assert out.name == "RSI_14"


# ---------- MACD ----------

def test_macd_returns_three_columns():
    s = _ramp(60)
    out = macd(s, fast=12, slow=26, signal=9)
    assert isinstance(out, pd.DataFrame)
    assert list(out.columns) == ["MACD", "Signal", "Histogram"]


def test_macd_histogram_equals_macd_minus_signal():
    s = _ramp(60)
    out = macd(s, fast=12, slow=26, signal=9)
    diff = out["MACD"] - out["Signal"]
    pd.testing.assert_series_equal(
        out["Histogram"].dropna(),
        diff.dropna().rename("Histogram"),
    )


def test_macd_macd_line_equals_fast_minus_slow():
    s = _ramp(60)
    out = macd(s, fast=12, slow=26, signal=9)
    expected = ema(s, 12) - ema(s, 26)
    pd.testing.assert_series_equal(
        out["MACD"].dropna(),
        expected.dropna().rename("MACD"),
    )


def test_macd_rejects_fast_geq_slow():
    s = _ramp(60)
    with pytest.raises(IndicatorError, match="fast"):
        macd(s, fast=26, slow=12)
    with pytest.raises(IndicatorError, match="fast"):
        macd(s, fast=12, slow=12)


# ---------- STC ----------

def test_stc_in_range_after_warmup():
    rng = np.random.default_rng(7)
    prices = np.cumsum(rng.normal(0, 1, 300)) + 200
    s = _series(list(prices))
    result = stc(s, fast=23, slow=50, cycle=10)
    valid = result.dropna()
    assert (valid >= 0.0).all()
    assert (valid <= 100.0).all()


def test_stc_name_includes_periods():
    s = _ramp(200)
    assert stc(s, fast=23, slow=50, cycle=10).name == "STC_23_50_10"


def test_stc_rejects_invalid_factor():
    s = _ramp(200)
    with pytest.raises(IndicatorError, match="factor"):
        stc(s, factor=0.0)
    with pytest.raises(IndicatorError, match="factor"):
        stc(s, factor=1.5)


def test_stc_rejects_fast_geq_slow():
    s = _ramp(200)
    with pytest.raises(IndicatorError, match="fast"):
        stc(s, fast=50, slow=23)


# ---------- IndicatorEngine ----------

def _make_indicators_config() -> IndicatorsConfig:
    return IndicatorsConfig(
        rsi_period=14,
        rsi_overbought=70,
        rsi_oversold=30,
        macd_fast=12,
        macd_slow=26,
        macd_signal=9,
        stc_fast=23,
        stc_slow=50,
        stc_cycle=10,
    )


def test_engine_uses_config_defaults():
    eng = IndicatorEngine(_make_indicators_config())
    s = _ramp(60)

    rsi_out = eng.rsi(s)
    assert rsi_out.name == "RSI_14"

    macd_out = eng.macd(s)
    expected = ema(s, 12) - ema(s, 26)
    pd.testing.assert_series_equal(
        macd_out["MACD"].dropna(),
        expected.dropna().rename("MACD"),
    )


def test_engine_overrides_config_when_period_given():
    eng = IndicatorEngine(_make_indicators_config())
    s = _ramp(60)
    out = eng.rsi(s, period=7)
    assert out.name == "RSI_7"


def test_engine_macd_uses_overrides():
    eng = IndicatorEngine(_make_indicators_config())
    s = _ramp(80)
    out = eng.macd(s, fast=5, slow=20, signal=3)
    expected = ema(s, 5) - ema(s, 20)
    pd.testing.assert_series_equal(
        out["MACD"].dropna(),
        expected.dropna().rename("MACD"),
    )


def test_engine_stc_uses_config():
    eng = IndicatorEngine(_make_indicators_config())
    s = _ramp(200)
    out = eng.stc(s)
    assert out.name == "STC_23_50_10"


# ---------- Bollinger Bands ----------

def _hlc(n: int) -> tuple[pd.Series, pd.Series, pd.Series]:
    close = _ramp(n)
    high = close + 0.5
    low = close - 0.5
    return high, low, close


def test_bband_returns_three_columns():
    out = bband(_ramp(50), period=20)
    assert isinstance(out, pd.DataFrame)
    assert list(out.columns) == ["BB_Upper", "BB_Mid", "BB_Lower"]


def test_bband_upper_above_lower():
    out = bband(_ramp(50), period=20)
    valid = out.dropna()
    assert (valid["BB_Upper"] > valid["BB_Lower"]).all()


def test_bband_mid_equals_sma():
    s = _ramp(50)
    out = bband(s, period=20)
    expected_mid = sma(s, 20).rename("BB_Mid")
    pd.testing.assert_series_equal(out["BB_Mid"].dropna(), expected_mid.dropna())


def test_bband_rejects_nonpositive_std_mult():
    with pytest.raises(IndicatorError, match="std_mult"):
        bband(_ramp(30), std_mult=0.0)
    with pytest.raises(IndicatorError, match="std_mult"):
        bband(_ramp(30), std_mult=-1.0)


def test_bband_preserves_index():
    s = _ramp(50)
    out = bband(s, period=20)
    pd.testing.assert_index_equal(out.index, s.index)


# ---------- ATR ----------

def test_atr_positive_after_warmup():
    high, low, close = _hlc(50)
    out = atr(high, low, close, period=14)
    valid = out.dropna()
    assert (valid > 0).all()


def test_atr_name_includes_period():
    high, low, close = _hlc(50)
    assert atr(high, low, close, period=14).name == "ATR_14"


def test_atr_flat_market_near_zero():
    n = 50
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    price = pd.Series([100.0] * n, index=idx)
    out = atr(price, price, price, period=5)
    assert out.dropna().abs().max() < 1e-9


def test_atr_rejects_non_series():
    with pytest.raises(IndicatorError, match="Series"):
        atr([1, 2], pd.Series([1, 2]), pd.Series([1, 2]))  # type: ignore[arg-type]


def test_atr_preserves_index():
    high, low, close = _hlc(50)
    out = atr(high, low, close)
    pd.testing.assert_index_equal(out.index, close.index)


# ---------- Stochastic ----------

def test_stoch_returns_two_columns():
    high, low, close = _hlc(50)
    out = stoch(high, low, close)
    assert isinstance(out, pd.DataFrame)
    assert list(out.columns) == ["STOCH_K", "STOCH_D"]


def test_stoch_k_in_range():
    rng = np.random.default_rng(99)
    prices = np.cumsum(rng.normal(0, 1, 100)) + 100
    close = _series(list(prices))
    high = close + 0.5
    low = close - 0.5
    out = stoch(high, low, close)
    valid_k = out["STOCH_K"].dropna()
    assert (valid_k >= 0.0).all()
    assert (valid_k <= 100.0).all()


def test_stoch_preserves_index():
    high, low, close = _hlc(50)
    out = stoch(high, low, close)
    pd.testing.assert_index_equal(out.index, close.index)


def test_stoch_rejects_non_series():
    with pytest.raises(IndicatorError, match="Series"):
        stoch([1, 2], pd.Series([1, 2]), pd.Series([1, 2]))  # type: ignore[arg-type]


# ---------- IndicatorEngine — new methods ----------

def test_engine_bband_uses_config():
    eng = IndicatorEngine(_make_indicators_config())
    s = _ramp(60)
    out = eng.bband(s)
    assert "BB_Upper" in out.columns
    assert "BB_Mid" in out.columns


def test_engine_atr_uses_config():
    high, low, close = _hlc(50)
    eng = IndicatorEngine(_make_indicators_config())
    out = eng.atr(high, low, close)
    assert out.name == "ATR_14"


def test_engine_stoch_uses_config():
    high, low, close = _hlc(50)
    eng = IndicatorEngine(_make_indicators_config())
    out = eng.stoch(high, low, close)
    assert list(out.columns) == ["STOCH_K", "STOCH_D"]


# ---------- OBV ----------

def _ohlcv_series(n: int) -> tuple[pd.Series, pd.Series]:
    """Return (close, volume) series of length n."""
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    close = pd.Series([100.0 + i for i in range(n)], index=idx, name="Close")
    volume = pd.Series([1_000_000.0] * n, index=idx, name="Volume")
    return close, volume


def test_obv_name():
    close, volume = _ohlcv_series(10)
    out = obv(close, volume)
    assert out.name == "OBV"


def test_obv_rising_price_adds_volume():
    """On a strictly rising series every bar adds volume."""
    close, volume = _ohlcv_series(5)  # close = 100,101,102,103,104
    out = obv(close, volume)
    # bar 0: OBV=0 (direction=0), bar 1+: OBV accumulates +1M each
    assert out.iloc[0] == pytest.approx(0.0)
    assert out.iloc[1] == pytest.approx(1_000_000.0)
    assert out.iloc[4] == pytest.approx(4_000_000.0)


def test_obv_falling_price_subtracts_volume():
    """On a strictly falling series every bar subtracts volume."""
    idx = pd.date_range("2024-01-01", periods=5, freq="B")
    close = pd.Series([104.0, 103.0, 102.0, 101.0, 100.0], index=idx)
    volume = pd.Series([1_000_000.0] * 5, index=idx)
    out = obv(close, volume)
    assert out.iloc[0] == pytest.approx(0.0)
    assert out.iloc[1] == pytest.approx(-1_000_000.0)
    assert out.iloc[4] == pytest.approx(-4_000_000.0)


def test_obv_flat_price_no_change():
    """When price doesn't move OBV stays at 0."""
    idx = pd.date_range("2024-01-01", periods=5, freq="B")
    close = pd.Series([100.0] * 5, index=idx)
    volume = pd.Series([1_000_000.0] * 5, index=idx)
    out = obv(close, volume)
    assert (out == 0.0).all()


def test_obv_no_warmup_all_values_finite():
    """OBV has no warmup period — every value should be finite."""
    close, volume = _ohlcv_series(30)
    out = obv(close, volume)
    assert out.notna().all()


def test_obv_preserves_index():
    close, volume = _ohlcv_series(20)
    out = obv(close, volume)
    pd.testing.assert_index_equal(out.index, close.index)


def test_obv_rejects_non_series_volume():
    close, _ = _ohlcv_series(10)
    with pytest.raises(IndicatorError, match="volume"):
        obv(close, [1_000_000.0] * 10)  # type: ignore[arg-type]


def test_obv_rejects_non_series_close():
    _, volume = _ohlcv_series(10)
    with pytest.raises(IndicatorError):
        obv([100.0] * 10, volume)  # type: ignore[arg-type]


def test_engine_obv_delegated():
    eng = IndicatorEngine(_make_indicators_config())
    close, volume = _ohlcv_series(20)
    out = eng.obv(close, volume)
    assert out.name == "OBV"


# ---------- VWAP ----------

def _hlcv(n: int) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    close = pd.Series([100.0 + i for i in range(n)], index=idx, name="Close")
    high = close + 0.5
    low = close - 0.5
    volume = pd.Series([1_000_000.0] * n, index=idx, name="Volume")
    return high, low, close, volume


def test_vwap_name():
    high, low, close, volume = _hlcv(10)
    out = vwap(high, low, close, volume)
    assert out.name == "VWAP"


def test_vwap_preserves_index():
    high, low, close, volume = _hlcv(20)
    out = vwap(high, low, close, volume)
    pd.testing.assert_index_equal(out.index, close.index)


def test_vwap_all_finite():
    high, low, close, volume = _hlcv(30)
    out = vwap(high, low, close, volume)
    assert out.notna().all()


def test_vwap_uniform_volume_equals_typical_price():
    """With equal volume every bar, VWAP[t] == cumulative average of TP."""
    n = 10
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    close = pd.Series([100.0] * n, index=idx)
    high = close + 1.0
    low = close - 1.0
    volume = pd.Series([1.0] * n, index=idx)
    tp = (high + low + close) / 3.0   # = 100.0 for all bars
    out = vwap(high, low, close, volume)
    # With constant TP and equal volume, VWAP must equal TP everywhere
    np.testing.assert_allclose(out.to_numpy(), tp.to_numpy(), rtol=1e-9)


def test_vwap_weighted_more_recent_high_volume():
    """Higher volume on the last bar should push VWAP toward last bar's TP."""
    n = 3
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    close = pd.Series([100.0, 100.0, 200.0], index=idx)
    high = close + 0.5
    low = close - 0.5
    # Last bar has 9× the volume of earlier bars
    volume = pd.Series([1.0, 1.0, 9.0], index=idx)
    out = vwap(high, low, close, volume)
    # Final VWAP = (TP[0]*1 + TP[1]*1 + TP[2]*9) / 11
    tp = (high + low + close) / 3.0
    expected_final = (tp.iloc[0] + tp.iloc[1] + tp.iloc[2] * 9) / 11.0
    assert out.iloc[-1] == pytest.approx(expected_final)


def test_vwap_rejects_non_series():
    high, low, close, volume = _hlcv(10)
    with pytest.raises(IndicatorError, match="high"):
        vwap(list(high), low, close, volume)  # type: ignore[arg-type]
    with pytest.raises(IndicatorError, match="low"):
        vwap(high, list(low), close, volume)  # type: ignore[arg-type]
    with pytest.raises(IndicatorError, match="close"):
        vwap(high, low, list(close), volume)  # type: ignore[arg-type]
    with pytest.raises(IndicatorError, match="volume"):
        vwap(high, low, close, list(volume))  # type: ignore[arg-type]


def test_engine_vwap_delegated():
    eng = IndicatorEngine(_make_indicators_config())
    high, low, close, volume = _hlcv(20)
    out = eng.vwap(high, low, close, volume)
    assert out.name == "VWAP"
