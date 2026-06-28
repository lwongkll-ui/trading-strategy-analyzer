"""Tests for core.ai_analyzer — AI win-probability layer."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from core.ai_analyzer import (
    FEATURE_NAMES,
    AIAnalysisResult,
    PatternAIStats,
    SignalPrediction,
    _atr_array,
    _build_feature_arrays,
    _make_y,
    _rsi_array,
    _signals_to_X,
    _sma,
    run_ai_analysis,
)
from core.pattern_engine import PatternSignal, ALL_PATTERN_NAMES


# ── helpers ────────────────────────────────────────────────────────────────────

def _make_df(n: int = 600, drift: float = 0.0, seed: int = 0) -> pd.DataFrame:
    """Synthetic daily OHLCV, optionally with a slow upward/downward drift."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(drift / 252, 0.01, n)
    closes = 100.0 * np.cumprod(1 + returns)
    noise = rng.uniform(0.002, 0.01, n)
    data = {
        "Open": closes * (1 - rng.uniform(0, 0.005, n)),
        "High": closes * (1 + noise),
        "Low": closes * (1 - noise),
        "Close": closes,
        "Volume": rng.integers(500_000, 5_000_000, n).astype(float),
    }
    # Ensure High >= Open/Close and Low <= Open/Close
    df = pd.DataFrame(data)
    df["High"] = df[["High", "Open", "Close"]].max(axis=1)
    df["Low"] = df[["Low", "Open", "Close"]].min(axis=1)
    return df


# ── internal helpers ───────────────────────────────────────────────────────────

def test_sma_length_matches_input():
    c = np.arange(1, 51, dtype=float)
    s = _sma(c, 20)
    assert len(s) == 50


def test_sma_first_n_minus_1_are_nan():
    c = np.arange(1, 21, dtype=float)
    s = _sma(c, 5)
    assert all(math.isnan(v) for v in s[:4])
    assert not math.isnan(s[4])


def test_rsi_array_length_and_initial_nans():
    c = np.linspace(100, 120, 50)
    r = _rsi_array(c, 14)
    assert len(r) == 50
    assert all(math.isnan(r[i]) for i in range(14))
    assert not math.isnan(r[14])


def test_rsi_bounded_0_100():
    c = np.abs(np.random.default_rng(1).normal(100, 5, 200))
    r = _rsi_array(c, 14)
    valid = r[~np.isnan(r)]
    assert np.all(valid >= 0) and np.all(valid <= 100)


def test_rsi_rising_series_above_50():
    c = np.linspace(100, 200, 100)
    r = _rsi_array(c, 14)
    valid = r[~np.isnan(r)]
    assert np.all(valid > 50)


def test_atr_array_shape_and_nans():
    df = _make_df(50)
    a = _atr_array(df["High"].to_numpy(), df["Low"].to_numpy(), df["Close"].to_numpy(), 20)
    assert len(a) == 50
    assert math.isnan(a[18])  # period-1 = 19 is first valid
    assert not math.isnan(a[19])


def test_atr_positive():
    df = _make_df(100)
    a = _atr_array(df["High"].to_numpy(), df["Low"].to_numpy(), df["Close"].to_numpy(), 10)
    valid = a[~np.isnan(a)]
    assert np.all(valid > 0)


def test_build_feature_arrays_keys():
    df = _make_df(100)
    fa = _build_feature_arrays(df)
    expected = {
        "ret5", "ret10", "ret20", "rsi", "vol_ratio",
        "dist_sma20", "dist_sma50", "atr_norm",
        "body_ratio", "uw_ratio", "lw_ratio", "range_ratio",
    }
    assert set(fa.keys()) == expected


def test_build_feature_arrays_lengths():
    n = 150
    df = _make_df(n)
    fa = _build_feature_arrays(df)
    for key, arr in fa.items():
        assert len(arr) == n, f"Length mismatch for {key}"


def test_signals_to_X_shape():
    df = _make_df(200)
    from core.pattern_engine import detect_all
    sigs = detect_all(df)
    if not sigs:
        pytest.skip("No signals in synthetic data")
    feats = _build_feature_arrays(df)
    X, bars, patterns, directions = _signals_to_X(sigs, feats)
    assert X.shape == (len(sigs), len(FEATURE_NAMES))
    assert len(bars) == len(sigs)
    assert len(patterns) == len(sigs)
    assert len(directions) == len(sigs)


def test_signals_to_X_onehot_sum_one_per_row():
    """Each row should have exactly 1 pattern one-hot bit set."""
    df = _make_df(200)
    from core.pattern_engine import detect_all
    sigs = detect_all(df)
    if not sigs:
        pytest.skip("No signals")
    feats = _build_feature_arrays(df)
    X, *_ = _signals_to_X(sigs, feats)
    n_num = 12  # numeric features
    onehot_block = X[:, n_num:]
    row_sums = np.nansum(onehot_block, axis=1)
    assert np.all(row_sums == 1)


def test_make_y_long_profitable():
    bars = np.array([0])
    close = np.array([100.0, 110.0])
    y = _make_y(bars, close, "bull", 1)
    assert y[0] == 1


def test_make_y_long_loss():
    bars = np.array([0])
    close = np.array([100.0, 90.0])
    y = _make_y(bars, close, "bull", 1)
    assert y[0] == 0


def test_make_y_short_profitable():
    bars = np.array([0])
    close = np.array([100.0, 90.0])
    y = _make_y(bars, close, "bear", 1)
    assert y[0] == 1


def test_make_y_short_loss():
    bars = np.array([0])
    close = np.array([100.0, 110.0])
    y = _make_y(bars, close, "bear", 1)
    assert y[0] == 0


def test_make_y_no_exit_returns_minus1():
    bars = np.array([0])
    close = np.array([100.0, 105.0])
    y = _make_y(bars, close, "bull", 5)  # exit bar = 5 >= len=2 → -1
    assert y[0] == -1


def test_make_y_zero_entry_returns_minus1():
    bars = np.array([0])
    close = np.array([0.0, 105.0])
    y = _make_y(bars, close, "bull", 1)
    assert y[0] == -1


# ── run_ai_analysis integration ───────────────────────────────────────────────

@pytest.fixture(scope="module")
def ai_result_long():
    """Run analysis once; reuse across tests in this module."""
    df = _make_df(n=800, drift=0.05, seed=42)
    return run_ai_analysis(df, ticker="SYNTH", hold_periods=[21, 42], min_samples=30)


def test_run_ai_analysis_returns_correct_type(ai_result_long):
    assert isinstance(ai_result_long, AIAnalysisResult)
    assert ai_result_long.ticker == "SYNTH"


def test_run_ai_analysis_backtest_populated(ai_result_long):
    from core.backtest_engine import BacktestResult
    assert isinstance(ai_result_long.backtest, BacktestResult)
    assert ai_result_long.backtest.n_bars == 800


def test_run_ai_analysis_models_trained(ai_result_long):
    # Expect at least one model to train (direction × hold_period)
    assert ai_result_long.n_models_trained >= 1


def test_pattern_stats_directions_valid(ai_result_long):
    for s in ai_result_long.pattern_stats:
        assert s.direction in ("bull", "bear")


def test_pattern_stats_hold_days_in_requested(ai_result_long):
    for s in ai_result_long.pattern_stats:
        assert s.hold_days in (21, 42)


def test_pattern_stats_oos_accuracy_bounded(ai_result_long):
    for s in ai_result_long.pattern_stats:
        if not math.isnan(s.oos_accuracy):
            assert 0.0 <= s.oos_accuracy <= 1.0


def test_pattern_stats_cv_accuracy_bounded(ai_result_long):
    for s in ai_result_long.pattern_stats:
        assert 0.0 <= s.model_cv_accuracy <= 1.0


def test_signal_probs_direction_valid(ai_result_long):
    for sp in ai_result_long.signal_probs:
        assert sp.direction in ("bull", "bear")


def test_signal_probs_probability_bounded(ai_result_long):
    for sp in ai_result_long.signal_probs:
        assert 0.0 <= sp.prob_win <= 1.0


def test_signal_probs_all_oos(ai_result_long):
    """Only OOS signal probs are returned."""
    for sp in ai_result_long.signal_probs:
        assert not sp.in_sample


def test_feature_importances_keys_match_names(ai_result_long):
    if not ai_result_long.feature_importances:
        pytest.skip("No models trained")
    for key in ai_result_long.feature_importances:
        assert key in FEATURE_NAMES


def test_feature_importances_non_negative(ai_result_long):
    for val in ai_result_long.feature_importances.values():
        assert val >= 0.0


def test_progress_cb_called(tmp_path):
    calls = []
    df = _make_df(300, seed=7)
    run_ai_analysis(df, "T", hold_periods=[21], min_samples=100,
                    progress_cb=lambda s, t: calls.append((s, t)))
    assert len(calls) > 0
    assert calls[0][0] < calls[0][1]  # step < total


def test_run_ai_analysis_empty_df_returns_empty():
    df = pd.DataFrame({"Open": [10.0], "High": [11.0], "Low": [9.0], "Close": [10.5], "Volume": [1000]})
    result = run_ai_analysis(df, "X", min_samples=50)
    assert result.pattern_stats == []
    assert result.signal_probs == []
    assert result.n_models_trained == 0


def test_lift_property_valid(ai_result_long):
    for s in ai_result_long.pattern_stats:
        if s.is_valid and not math.isnan(s.oos_accuracy):
            assert s.lift == pytest.approx(s.oos_accuracy / 0.5)


def test_sklearn_not_available_raises(monkeypatch):
    import core.ai_analyzer as mod
    monkeypatch.setattr(mod, "_SKLEARN_OK", False)
    df = _make_df(100)
    with pytest.raises(ImportError, match="scikit-learn"):
        run_ai_analysis(df, "T")
