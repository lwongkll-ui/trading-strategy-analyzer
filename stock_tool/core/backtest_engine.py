"""Candlestick pattern backtesting engine.

Usage
-----
>>> from core.backtest_engine import run_backtest
>>> result = run_backtest(df, ticker="AAPL")
>>> for s in result.top(10):
...     print(s.pattern, s.direction, f"{s.oos_win_rate:.0%}", f"{s.oos_avg_return:.2f}%")

Walk-forward split
------------------
The dataset is divided into **in-sample** (first 75 %) and **out-of-sample**
(last 25 %) at detection time, NOT at signal-generation time.  All detected
signals are tagged with their region so IS and OOS metrics are computed
separately.

Simulation
----------
* Entry  : Close of the signal bar.
* Exit   : Close of bar ``(signal_bar + hold_days)``; skipped if the exit bar
           is beyond the last available row.
* Long   : pct_return = (exit − entry) / entry × 100
* Short  : pct_return = (entry − exit) / entry × 100

Positive ``pct_return`` always means the trade was profitable regardless of
direction.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from core.pattern_engine import PatternSignal, detect_all

# ── constants ──────────────────────────────────────────────────────────────────

DEFAULT_HOLD_PERIODS: list[int] = [21, 42, 63]   # ≈ 1, 2, 3 months
DEFAULT_MIN_SAMPLES: int = 50                      # IS minimum to report
IS_RATIO: float = 0.75                            # fraction used for in-sample


# ── data types ─────────────────────────────────────────────────────────────────

@dataclass
class TradeResult:
    """Single simulated trade outcome."""
    bar: int
    pattern: str
    direction: str         # 'bull' | 'bear'
    hold_days: int
    entry: float
    exit_price: float
    pct_return: float      # positive = profit for both long and short
    in_sample: bool


@dataclass
class PatternStats:
    """Aggregated statistics for one (pattern × direction × hold_period) group.

    Attributes:
        pattern:          Pattern name (e.g. ``"Bullish Engulfing"``).
        direction:        ``"bull"`` or ``"bear"``.
        hold_days:        Hold duration in trading days.
        n_is:             Number of in-sample trades.
        n_oos:            Number of out-of-sample trades.
        is_win_rate:      Fraction of IS trades that were profitable.
        is_avg_return:    Mean return (%) across IS trades.
        is_profit_factor: Sum of winning returns / abs(sum of losing returns).
        is_sharpe:        IS mean / std of returns (simplified daily Sharpe).
        is_max_drawdown:  Worst single losing trade return (%) in IS.
        oos_win_rate:     Fraction of OOS trades that were profitable.
        oos_avg_return:   Mean return (%) across OOS trades.
        score:            Composite ranking score (higher = better).
    """
    pattern: str
    direction: str
    hold_days: int
    n_is: int
    n_oos: int
    is_win_rate: float
    is_avg_return: float
    is_profit_factor: float
    is_sharpe: float
    is_max_drawdown: float
    oos_win_rate: float
    oos_avg_return: float
    score: float

    @property
    def is_valid(self) -> bool:
        """True if the group meets minimum quality thresholds for display."""
        return self.n_is >= DEFAULT_MIN_SAMPLES and self.n_oos >= 5


@dataclass
class BacktestResult:
    """Complete backtest output for one ticker.

    Attributes:
        ticker:      Ticker symbol.
        n_bars:      Total number of bars in the input DataFrame.
        is_cutoff:   Bar index where in-sample ends (exclusive for OOS).
        n_signals:   Total pattern signals detected across all bars.
        stats:       All :class:`PatternStats` sorted by ``score`` descending.
    """
    ticker: str
    n_bars: int
    is_cutoff: int
    n_signals: int
    stats: list[PatternStats] = field(default_factory=list)

    def top(self, n: int = 10) -> list[PatternStats]:
        """Return at most *n* highest-scoring valid pattern groups."""
        return [s for s in self.stats if s.is_valid][:n]

    def for_pattern(self, pattern: str) -> list[PatternStats]:
        """Return all stats rows matching *pattern* (any hold period)."""
        return [s for s in self.stats if s.pattern == pattern]


# ── internal helpers ───────────────────────────────────────────────────────────

def _simulate_trades(
    signals: list[PatternSignal],
    close: np.ndarray,
    is_cutoff: int,
    hold_periods: list[int],
) -> list[TradeResult]:
    """Convert pattern signals into simulated trade outcomes."""
    n = len(close)
    trades: list[TradeResult] = []
    for sig in signals:
        entry = close[sig.bar]
        if entry <= 0:
            continue
        in_sample = sig.bar < is_cutoff
        for hp in hold_periods:
            exit_bar = sig.bar + hp
            if exit_bar >= n:
                continue
            exit_price = close[exit_bar]
            if sig.direction == "bull":
                pct = (exit_price - entry) / entry * 100.0
            else:
                pct = (entry - exit_price) / entry * 100.0
            trades.append(TradeResult(
                bar=sig.bar,
                pattern=sig.pattern,
                direction=sig.direction,
                hold_days=hp,
                entry=entry,
                exit_price=exit_price,
                pct_return=pct,
                in_sample=in_sample,
            ))
    return trades


def _compute_stats(
    is_trades: list[TradeResult],
    oos_trades: list[TradeResult],
    pattern: str,
    direction: str,
    hold_days: int,
) -> PatternStats:
    """Compute :class:`PatternStats` from pre-split trade lists."""
    is_ret = np.array([t.pct_return for t in is_trades], dtype=float)
    oos_ret = np.array([t.pct_return for t in oos_trades], dtype=float) if oos_trades else np.empty(0)

    # ── IS metrics ────────────────────────────────────────────────────────────
    is_wins = is_ret[is_ret > 0]
    is_losses = is_ret[is_ret <= 0]
    is_win_rate = len(is_wins) / len(is_ret)
    is_avg = float(is_ret.mean())
    is_std = float(is_ret.std(ddof=1)) if len(is_ret) > 1 else 1e-9
    is_sharpe = is_avg / is_std if is_std > 0 else 0.0

    win_sum = float(is_wins.sum()) if len(is_wins) > 0 else 0.0
    loss_sum = abs(float(is_losses.sum())) if len(is_losses) > 0 else 1e-9
    profit_factor = win_sum / loss_sum

    is_max_dd = float(is_ret.min()) if len(is_ret) > 0 else 0.0  # worst single return

    # ── OOS metrics ───────────────────────────────────────────────────────────
    oos_win_rate = float(np.mean(oos_ret > 0)) if len(oos_ret) > 0 else 0.0
    oos_avg = float(oos_ret.mean()) if len(oos_ret) > 0 else 0.0

    # ── composite score ───────────────────────────────────────────────────────
    # Confidence rises from 0 → 1 as IS sample count goes from 50 → 200.
    confidence = min(1.0, (len(is_trades) - DEFAULT_MIN_SAMPLES + 1) / 150.0)

    # OOS component: rewards both high win-rate (above 50 %) AND positive returns.
    oos_edge = max(0.0, oos_win_rate - 0.50) * max(0.0, oos_avg)

    # IS component: Sharpe-like quality, capped to avoid extreme outlier bias.
    is_edge = min(max(0.0, is_sharpe), 2.0) / 2.0

    score = (0.65 * oos_edge + 0.35 * is_edge) * confidence

    return PatternStats(
        pattern=pattern,
        direction=direction,
        hold_days=hold_days,
        n_is=len(is_trades),
        n_oos=len(oos_trades),
        is_win_rate=is_win_rate,
        is_avg_return=is_avg,
        is_profit_factor=profit_factor,
        is_sharpe=is_sharpe,
        is_max_drawdown=is_max_dd,
        oos_win_rate=oos_win_rate,
        oos_avg_return=oos_avg,
        score=score,
    )


# ── public API ─────────────────────────────────────────────────────────────────

def run_backtest(
    df: pd.DataFrame,
    ticker: str,
    hold_periods: list[int] = DEFAULT_HOLD_PERIODS,
    min_samples: int = DEFAULT_MIN_SAMPLES,
    progress_cb=None,
) -> BacktestResult:
    """Run a full candlestick pattern backtest on *df*.

    Args:
        df:           Daily OHLCV DataFrame (columns: Open, High, Low, Close).
                      Must have at least 3 rows; 500+ rows recommended.
        ticker:       Ticker label for the returned result object.
        hold_periods: Hold durations in trading days to test.
        min_samples:  Minimum in-sample occurrences for a group to be included.
        progress_cb:  Optional ``callable(step: int, total: int)`` for progress
                      reporting (e.g. from a background QThread).

    Returns:
        :class:`BacktestResult` with ``stats`` sorted by composite score
        descending.  Call ``.top(n)`` to get the best *n* valid patterns.
    """
    n = len(df)
    is_cutoff = int(n * IS_RATIO)
    close = df["Close"].to_numpy(dtype=float)

    # Step 1: detect patterns
    if progress_cb:
        progress_cb(0, 3)
    signals = detect_all(df)

    # Step 2: simulate trades
    if progress_cb:
        progress_cb(1, 3)
    trades = _simulate_trades(signals, close, is_cutoff, hold_periods)

    # Step 3: aggregate per (pattern, direction, hold_period)
    if progress_cb:
        progress_cb(2, 3)

    # Group trades
    groups: dict[tuple[str, str, int], tuple[list, list]] = {}
    for t in trades:
        key = (t.pattern, t.direction, t.hold_days)
        if key not in groups:
            groups[key] = ([], [])
        bucket = groups[key][0] if t.in_sample else groups[key][1]
        bucket.append(t)

    stats_list: list[PatternStats] = []
    for (pat, dirn, hp), (is_t, oos_t) in groups.items():
        if len(is_t) < min_samples:
            continue
        stats_list.append(_compute_stats(is_t, oos_t, pat, dirn, hp))

    stats_list.sort(key=lambda s: s.score, reverse=True)

    if progress_cb:
        progress_cb(3, 3)

    return BacktestResult(
        ticker=ticker,
        n_bars=n,
        is_cutoff=is_cutoff,
        n_signals=len(signals),
        stats=stats_list,
    )
