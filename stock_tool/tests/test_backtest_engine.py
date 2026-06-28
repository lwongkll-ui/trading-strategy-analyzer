"""Tests for core.backtest_engine."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.backtest_engine import (
    DEFAULT_HOLD_PERIODS,
    DEFAULT_MIN_SAMPLES,
    IS_RATIO,
    BacktestResult,
    PatternStats,
    TradeResult,
    _compute_stats,
    _simulate_trades,
    run_backtest,
)
from core.pattern_engine import PatternSignal


# ── helpers ────────────────────────────────────────────────────────────────────

def _make_ohlcv(n: int, start: float = 100.0, drift: float = 0.0) -> pd.DataFrame:
    """Create a flat or trending OHLCV DataFrame of length *n*."""
    closes = np.full(n, start, dtype=float) + np.arange(n) * drift
    data = {
        "Open": closes - 0.5,
        "High": closes + 1.0,
        "Low": closes - 1.0,
        "Close": closes,
        "Volume": np.ones(n) * 1000,
    }
    return pd.DataFrame(data)


def _make_trade(
    pct: float,
    in_sample: bool = True,
    pattern: str = "Hammer",
    direction: str = "bull",
    hold_days: int = 21,
) -> TradeResult:
    return TradeResult(
        bar=0, pattern=pattern, direction=direction,
        hold_days=hold_days, entry=100.0, exit_price=100.0 * (1 + pct / 100),
        pct_return=pct, in_sample=in_sample,
    )


# ── _simulate_trades ──────────────────────────────────────────────────────────

def test_simulate_trades_long_return():
    close = np.array([100.0, 102.0, 105.0])
    signals = [PatternSignal(bar=0, pattern="P", direction="bull")]
    trades = _simulate_trades(signals, close, is_cutoff=2, hold_periods=[1])
    assert len(trades) == 1
    assert abs(trades[0].pct_return - 2.0) < 1e-6


def test_simulate_trades_short_return():
    close = np.array([100.0, 95.0, 90.0])
    signals = [PatternSignal(bar=0, pattern="P", direction="bear")]
    trades = _simulate_trades(signals, close, is_cutoff=2, hold_periods=[1])
    assert len(trades) == 1
    assert abs(trades[0].pct_return - 5.0) < 1e-6  # short profit: (100-95)/100 × 100


def test_simulate_trades_skips_beyond_end():
    close = np.array([100.0, 102.0])
    signals = [PatternSignal(bar=0, pattern="P", direction="bull")]
    trades = _simulate_trades(signals, close, is_cutoff=1, hold_periods=[21])
    assert trades == []  # exit bar 21 >= len(2)


def test_simulate_trades_in_sample_flag():
    close = np.array([100.0] * 10)
    signals = [
        PatternSignal(bar=0, pattern="P", direction="bull"),  # bar < is_cutoff(7) → IS
        PatternSignal(bar=8, pattern="P", direction="bull"),  # bar >= 7 → OOS
    ]
    trades = _simulate_trades(signals, close, is_cutoff=7, hold_periods=[1])
    assert trades[0].in_sample is True
    assert trades[1].in_sample is False


def test_simulate_trades_skips_zero_entry():
    close = np.array([0.0, 102.0, 105.0])
    signals = [PatternSignal(bar=0, pattern="P", direction="bull")]
    trades = _simulate_trades(signals, close, is_cutoff=2, hold_periods=[1])
    assert trades == []


# ── _compute_stats ─────────────────────────────────────────────────────────────

def test_compute_stats_win_rate_all_wins():
    is_t = [_make_trade(+2.0)] * 60
    stats = _compute_stats(is_t, [], "Hammer", "bull", 21)
    assert stats.is_win_rate == pytest.approx(1.0)


def test_compute_stats_profit_factor_no_losses():
    is_t = [_make_trade(+1.0)] * 60
    stats = _compute_stats(is_t, [], "Hammer", "bull", 21)
    assert stats.is_profit_factor > 100  # effectively infinite


def test_compute_stats_oos_metrics_populated():
    is_t = [_make_trade(+1.0)] * 60
    oos_t = [_make_trade(+1.5, in_sample=False)] * 20
    stats = _compute_stats(is_t, oos_t, "Hammer", "bull", 21)
    assert stats.oos_win_rate == pytest.approx(1.0)
    assert stats.oos_avg_return == pytest.approx(1.5)


def test_compute_stats_oos_empty():
    is_t = [_make_trade(+1.0)] * 60
    stats = _compute_stats(is_t, [], "Hammer", "bull", 21)
    assert stats.n_oos == 0
    assert stats.oos_win_rate == pytest.approx(0.0)


def test_compute_stats_score_higher_for_better_oos():
    is_trades = [_make_trade(+1.0)] * 60
    oos_good = [_make_trade(+2.0, False)] * 20
    oos_bad = [_make_trade(-2.0, False)] * 20
    s_good = _compute_stats(is_trades, oos_good, "P", "bull", 21)
    s_bad = _compute_stats(is_trades, oos_bad, "P", "bull", 21)
    assert s_good.score > s_bad.score


def test_compute_stats_is_valid_requires_min_samples():
    is_t = [_make_trade(+1.0)] * (DEFAULT_MIN_SAMPLES - 1)
    stats = _compute_stats(is_t, [], "P", "bull", 21)
    assert not stats.is_valid


def test_compute_stats_is_valid_passes_threshold():
    is_t = [_make_trade(+1.0)] * DEFAULT_MIN_SAMPLES
    oos_t = [_make_trade(+1.0, False)] * 5
    stats = _compute_stats(is_t, oos_t, "P", "bull", 21)
    assert stats.is_valid


# ── run_backtest ──────────────────────────────────────────────────────────────

def test_run_backtest_returns_result_type():
    df = _make_ohlcv(300)
    result = run_backtest(df, ticker="TEST")
    assert isinstance(result, BacktestResult)
    assert result.ticker == "TEST"
    assert result.n_bars == 300


def test_run_backtest_is_cutoff_correct():
    n = 400
    df = _make_ohlcv(n)
    result = run_backtest(df, ticker="T")
    assert result.is_cutoff == int(n * IS_RATIO)


def test_run_backtest_stats_sorted_by_score_desc():
    df = _make_ohlcv(500, drift=0.05)
    result = run_backtest(df, ticker="T")
    scores = [s.score for s in result.stats]
    assert scores == sorted(scores, reverse=True)


def test_run_backtest_top_filters_invalid():
    df = _make_ohlcv(200)
    result = run_backtest(df, ticker="T")
    for s in result.top(20):
        assert s.is_valid


def test_run_backtest_min_samples_respected():
    df = _make_ohlcv(300)
    result = run_backtest(df, ticker="T", min_samples=500)
    # With min_samples=500 on a 300-bar DataFrame, nothing should pass IS filter
    assert result.stats == []


def test_run_backtest_progress_cb_called():
    calls = []
    df = _make_ohlcv(200)
    run_backtest(df, ticker="T", progress_cb=lambda cur, tot: calls.append((cur, tot)))
    assert len(calls) >= 3
    assert calls[0] == (0, 3)
    assert calls[-1] == (3, 3)


def test_run_backtest_direction_labels():
    df = _make_ohlcv(500, drift=0.1)
    result = run_backtest(df, ticker="T")
    for s in result.stats:
        assert s.direction in ("bull", "bear")


def test_backtest_result_for_pattern_filters():
    df = _make_ohlcv(500, drift=0.05)
    result = run_backtest(df, ticker="T")
    if not result.stats:
        pytest.skip("No patterns found with this synthetic data")
    pat_name = result.stats[0].pattern
    filtered = result.for_pattern(pat_name)
    assert all(s.pattern == pat_name for s in filtered)


def test_run_backtest_hold_periods_respected():
    df = _make_ohlcv(500, drift=0.05)
    custom_periods = [5, 10]
    result = run_backtest(df, ticker="T", hold_periods=custom_periods)
    for s in result.stats:
        assert s.hold_days in custom_periods
