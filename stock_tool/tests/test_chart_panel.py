"""Tests for ui.chart_panel.

Run headless via the ``offscreen`` Qt platform set in ``conftest.py``.
The ``qapp`` fixture provides a session-scoped ``QApplication``.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
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


def _make_config() -> Config:
    return Config(
        data=DataConfig(price_dir=Path("./prices"), export_dir=Path("./exports")),
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
            ma_colors=("#2196F3", "#FF9800", "#E91E63", "#9C27B0", "#00BCD4"),
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
            enabled=False, cron="0 18 * * 1-5", symbols_file=Path("./watchlist.txt")
        ),
        source_path=Path("./config.yaml"),
    )


def _make_ohlcv(n: int = 30, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    closes = 100 + np.cumsum(rng.normal(0, 1, n))
    opens = closes + rng.normal(0, 0.3, n)
    highs = np.maximum(opens, closes) + np.abs(rng.normal(0, 0.5, n))
    lows = np.minimum(opens, closes) - np.abs(rng.normal(0, 0.5, n))
    volumes = rng.integers(1_000_000, 5_000_000, n)
    idx = pd.date_range("2024-01-02", periods=n, freq="B")
    return pd.DataFrame(
        {
            "Open": opens,
            "High": highs,
            "Low": lows,
            "Close": closes,
            "Volume": volumes,
            "Adj_Close": closes,
        },
        index=idx,
    )


# ---------- ChartPanel construction ----------

def test_chart_panel_constructs(qapp):
    from ui.chart_panel import ChartPanel

    panel = ChartPanel(_make_config())
    assert panel.mode == "candle"
    assert panel.data is None
    assert panel.overlay_names() == []


def test_chart_panel_uses_background_color_from_config(qapp):
    from ui.chart_panel import ChartPanel

    panel = ChartPanel(_make_config())
    # PyQt's QColor normalises to uppercase hex; sanity check it was applied.
    assert panel._plot_widget.backgroundBrush().color().name().lower() == "#131722"


# ---------- set_data ----------

def test_set_data_stores_dataframe(qapp):
    from ui.chart_panel import ChartPanel

    panel = ChartPanel(_make_config())
    df = _make_ohlcv(20)
    panel.set_data(df)

    assert panel.data is not None
    pd.testing.assert_frame_equal(panel.data, df)


def test_set_data_creates_candle_item_in_candle_mode(qapp):
    from ui.chart_panel import ChartPanel, CandlestickItem

    panel = ChartPanel(_make_config())
    panel.set_data(_make_ohlcv(15))

    assert isinstance(panel._candle_item, CandlestickItem)
    assert panel._line_item is None


def test_set_data_creates_line_item_in_line_mode(qapp):
    from ui.chart_panel import ChartPanel
    import pyqtgraph as pg

    panel = ChartPanel(_make_config())
    panel.set_mode("line")
    panel.set_data(_make_ohlcv(15))

    assert panel._candle_item is None
    assert isinstance(panel._line_item, pg.PlotDataItem)


def test_set_data_rejects_missing_columns(qapp):
    from ui.chart_panel import ChartPanel, ChartPanelError

    panel = ChartPanel(_make_config())
    bad = _make_ohlcv(10).drop(columns=["Volume"])
    with pytest.raises(ChartPanelError, match="missing"):
        panel.set_data(bad)


def test_set_data_rejects_non_datetime_index(qapp):
    from ui.chart_panel import ChartPanel, ChartPanelError

    panel = ChartPanel(_make_config())
    bad = _make_ohlcv(10).reset_index(drop=True)
    with pytest.raises(ChartPanelError, match="DatetimeIndex"):
        panel.set_data(bad)


def test_set_data_rejects_empty_frame(qapp):
    from ui.chart_panel import ChartPanel, ChartPanelError

    panel = ChartPanel(_make_config())
    empty = _make_ohlcv(5).iloc[0:0]
    with pytest.raises(ChartPanelError, match="empty"):
        panel.set_data(empty)


# ---------- set_mode ----------

def test_set_mode_switches_between_candle_and_line(qapp):
    from ui.chart_panel import ChartPanel

    panel = ChartPanel(_make_config())
    panel.set_data(_make_ohlcv(15))
    assert panel._candle_item is not None
    assert panel._line_item is None

    panel.set_mode("line")
    assert panel.mode == "line"
    assert panel._candle_item is None
    assert panel._line_item is not None

    panel.set_mode("candle")
    assert panel.mode == "candle"
    assert panel._candle_item is not None
    assert panel._line_item is None


def test_set_mode_rejects_unknown_mode(qapp):
    from ui.chart_panel import ChartPanel, ChartPanelError

    panel = ChartPanel(_make_config())
    with pytest.raises(ChartPanelError, match="Invalid mode"):
        panel.set_mode("ohlc")


def test_set_mode_no_op_when_unchanged(qapp):
    from ui.chart_panel import ChartPanel

    panel = ChartPanel(_make_config())
    panel.set_data(_make_ohlcv(10))
    item_before = panel._candle_item
    panel.set_mode("candle")  # same mode
    assert panel._candle_item is item_before  # not recreated


# ---------- MA overlays ----------

def test_add_ma_overlay_requires_data(qapp):
    from ui.chart_panel import ChartPanel, ChartPanelError

    panel = ChartPanel(_make_config())
    series = pd.Series([1.0, 2.0, 3.0])
    with pytest.raises(ChartPanelError, match="set_data"):
        panel.add_ma_overlay("SMA_20", series)


def test_add_ma_overlay_appears_in_overlay_names(qapp):
    from ui.chart_panel import ChartPanel

    panel = ChartPanel(_make_config())
    df = _make_ohlcv(30)
    panel.set_data(df)
    sma = df["Close"].rolling(5).mean()

    panel.add_ma_overlay("SMA_5", sma)
    assert panel.overlay_names() == ["SMA_5"]


def test_add_ma_overlay_caps_at_five(qapp):
    from ui.chart_panel import ChartPanel, ChartPanelError, MAX_MA_OVERLAYS

    panel = ChartPanel(_make_config())
    df = _make_ohlcv(30)
    panel.set_data(df)
    sma = df["Close"].rolling(5).mean()

    for i in range(MAX_MA_OVERLAYS):
        panel.add_ma_overlay(f"MA_{i}", sma)

    with pytest.raises(ChartPanelError, match="At most"):
        panel.add_ma_overlay("MA_extra", sma)


def test_add_ma_overlay_rejects_duplicate_name(qapp):
    from ui.chart_panel import ChartPanel, ChartPanelError

    panel = ChartPanel(_make_config())
    df = _make_ohlcv(30)
    panel.set_data(df)
    sma = df["Close"].rolling(5).mean()
    panel.add_ma_overlay("SMA_5", sma)

    with pytest.raises(ChartPanelError, match="already exists"):
        panel.add_ma_overlay("SMA_5", sma)


def test_add_ma_overlay_rejects_misaligned_series(qapp):
    from ui.chart_panel import ChartPanel, ChartPanelError

    panel = ChartPanel(_make_config())
    panel.set_data(_make_ohlcv(30))
    misaligned = pd.Series(np.zeros(20))

    with pytest.raises(ChartPanelError, match="length"):
        panel.add_ma_overlay("SMA_5", misaligned)


def test_add_ma_overlay_uses_explicit_color(qapp):
    from ui.chart_panel import ChartPanel

    panel = ChartPanel(_make_config())
    df = _make_ohlcv(30)
    panel.set_data(df)
    sma = df["Close"].rolling(5).mean()

    panel.add_ma_overlay("SMA_5", sma, color="#ff0000")
    item = panel._overlays["SMA_5"]
    assert item.opts["pen"].color().name().lower() == "#ff0000"


def test_add_ma_overlay_cycles_through_palette(qapp):
    from ui.chart_panel import ChartPanel

    cfg = _make_config()
    panel = ChartPanel(cfg)
    df = _make_ohlcv(30)
    panel.set_data(df)
    sma = df["Close"].rolling(5).mean()

    panel.add_ma_overlay("A", sma)
    panel.add_ma_overlay("B", sma)
    a_color = panel._overlays["A"].opts["pen"].color().name().lower()
    b_color = panel._overlays["B"].opts["pen"].color().name().lower()
    assert a_color == cfg.chart.ma_colors[0].lower()
    assert b_color == cfg.chart.ma_colors[1].lower()


def test_remove_ma_overlay(qapp):
    from ui.chart_panel import ChartPanel

    panel = ChartPanel(_make_config())
    df = _make_ohlcv(30)
    panel.set_data(df)
    sma = df["Close"].rolling(5).mean()
    panel.add_ma_overlay("SMA_5", sma)

    panel.remove_ma_overlay("SMA_5")
    assert panel.overlay_names() == []


def test_remove_unknown_overlay_is_a_noop(qapp):
    from ui.chart_panel import ChartPanel

    panel = ChartPanel(_make_config())
    panel.remove_ma_overlay("does_not_exist")  # should not raise


def test_clear_overlays_removes_all(qapp):
    from ui.chart_panel import ChartPanel

    panel = ChartPanel(_make_config())
    df = _make_ohlcv(30)
    panel.set_data(df)
    sma = df["Close"].rolling(5).mean()
    panel.add_ma_overlay("A", sma)
    panel.add_ma_overlay("B", sma)

    panel.clear_overlays()
    assert panel.overlay_names() == []
    # And the colour cursor resets so the next overlay starts at index 0.
    panel.add_ma_overlay("C", sma)
    assert (
        panel._overlays["C"].opts["pen"].color().name().lower()
        == _make_config().chart.ma_colors[0].lower()
    )


# ---------- clear ----------

def test_clear_resets_state(qapp):
    from ui.chart_panel import ChartPanel

    panel = ChartPanel(_make_config())
    df = _make_ohlcv(30)
    panel.set_data(df)
    sma = df["Close"].rolling(5).mean()
    panel.add_ma_overlay("SMA_5", sma)

    panel.clear()
    assert panel.data is None
    assert panel.overlay_names() == []
    assert panel._candle_item is None
    assert panel._line_item is None


# ---------- Bollinger Bands overlay ----------

def _make_bband_df(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    import core.indicator_engine as ie
    return ie.bband(df["Close"], period)


def test_add_bband_overlay_requires_data(qapp):
    from ui.chart_panel import ChartPanel, ChartPanelError
    panel = ChartPanel(_make_config())
    bb = pd.DataFrame({"BB_Upper": [1.0], "BB_Mid": [1.0], "BB_Lower": [1.0]})
    with pytest.raises(ChartPanelError, match="set_data"):
        panel.add_bband_overlay(bb)


def test_add_bband_overlay_adds_three_items(qapp):
    from ui.chart_panel import ChartPanel
    panel = ChartPanel(_make_config())
    df = _make_ohlcv(50)
    panel.set_data(df)
    bb = _make_bband_df(df)
    panel.add_bband_overlay(bb)
    assert panel.has_bband_overlay()
    assert len(panel._bband_items) == 3
    assert set(panel._bband_items.keys()) == {"BB_Upper", "BB_Mid", "BB_Lower"}


def test_add_bband_overlay_twice_raises(qapp):
    from ui.chart_panel import ChartPanel, ChartPanelError
    panel = ChartPanel(_make_config())
    df = _make_ohlcv(50)
    panel.set_data(df)
    bb = _make_bband_df(df)
    panel.add_bband_overlay(bb)
    with pytest.raises(ChartPanelError, match="already exists"):
        panel.add_bband_overlay(bb)


def test_add_bband_overlay_rejects_misaligned(qapp):
    from ui.chart_panel import ChartPanel, ChartPanelError
    panel = ChartPanel(_make_config())
    df = _make_ohlcv(50)
    panel.set_data(df)
    bb_short = pd.DataFrame({"BB_Upper": [1.0] * 20, "BB_Mid": [1.0] * 20, "BB_Lower": [1.0] * 20})
    with pytest.raises(ChartPanelError, match="length"):
        panel.add_bband_overlay(bb_short)


def test_remove_bband_overlay(qapp):
    from ui.chart_panel import ChartPanel
    panel = ChartPanel(_make_config())
    df = _make_ohlcv(50)
    panel.set_data(df)
    bb = _make_bband_df(df)
    panel.add_bband_overlay(bb)
    panel.remove_bband_overlay()
    assert not panel.has_bband_overlay()
    assert panel._bband_items == {}


def test_remove_bband_when_absent_is_noop(qapp):
    from ui.chart_panel import ChartPanel
    panel = ChartPanel(_make_config())
    panel.remove_bband_overlay()  # should not raise


def test_clear_also_removes_bband(qapp):
    from ui.chart_panel import ChartPanel
    panel = ChartPanel(_make_config())
    df = _make_ohlcv(50)
    panel.set_data(df)
    bb = _make_bband_df(df)
    panel.add_bband_overlay(bb)
    panel.clear()
    assert not panel.has_bband_overlay()


# ---------- CandlestickItem ----------

def test_candlestick_item_handles_empty_array(qapp):
    from ui.chart_panel import CandlestickItem

    item = CandlestickItem(np.empty((0, 5)))
    assert item.boundingRect().isEmpty() or item.boundingRect().width() == 0


def test_candlestick_item_bounding_rect_covers_data(qapp):
    from ui.chart_panel import CandlestickItem

    ohlc = np.array(
        [
            [0.0, 100.0, 105.0, 95.0, 102.0],
            [1.0, 102.0, 108.0, 100.0, 107.0],
            [2.0, 107.0, 110.0, 103.0, 104.0],
        ]
    )
    item = CandlestickItem(ohlc)
    rect = item.boundingRect()
    # Width should span at least bar 0 → bar 2.
    assert rect.width() >= 2.0
    # Height should cover the low (95) → high (110) range, with some slack.
    assert rect.height() >= 14.0


# ---------- VWAP overlay ----------

def _make_vwap_series(df: pd.DataFrame) -> pd.Series:
    import core.indicator_engine as ie
    return ie.vwap(df["High"], df["Low"], df["Close"], df["Volume"])


def test_add_vwap_overlay_requires_data(qapp):
    from ui.chart_panel import ChartPanel, ChartPanelError
    panel = ChartPanel(_make_config())
    vwap_s = pd.Series([100.0, 101.0, 102.0])
    with pytest.raises(ChartPanelError, match="set_data"):
        panel.add_vwap_overlay(vwap_s)


def test_add_vwap_overlay_appears_on_chart(qapp):
    from ui.chart_panel import ChartPanel
    panel = ChartPanel(_make_config())
    df = _make_ohlcv(30)
    panel.set_data(df)
    vwap_s = _make_vwap_series(df)
    panel.add_vwap_overlay(vwap_s)
    assert panel.has_vwap_overlay()
    assert panel._vwap_item is not None


def test_add_vwap_overlay_twice_raises(qapp):
    from ui.chart_panel import ChartPanel, ChartPanelError
    panel = ChartPanel(_make_config())
    df = _make_ohlcv(30)
    panel.set_data(df)
    vwap_s = _make_vwap_series(df)
    panel.add_vwap_overlay(vwap_s)
    with pytest.raises(ChartPanelError, match="already exists"):
        panel.add_vwap_overlay(vwap_s)


def test_add_vwap_overlay_rejects_misaligned(qapp):
    from ui.chart_panel import ChartPanel, ChartPanelError
    panel = ChartPanel(_make_config())
    df = _make_ohlcv(30)
    panel.set_data(df)
    short = pd.Series([100.0] * 10)
    with pytest.raises(ChartPanelError, match="length"):
        panel.add_vwap_overlay(short)


def test_remove_vwap_overlay(qapp):
    from ui.chart_panel import ChartPanel
    panel = ChartPanel(_make_config())
    df = _make_ohlcv(30)
    panel.set_data(df)
    vwap_s = _make_vwap_series(df)
    panel.add_vwap_overlay(vwap_s)
    panel.remove_vwap_overlay()
    assert not panel.has_vwap_overlay()
    assert panel._vwap_item is None


def test_remove_vwap_when_absent_is_noop(qapp):
    from ui.chart_panel import ChartPanel
    panel = ChartPanel(_make_config())
    panel.remove_vwap_overlay()   # should not raise


def test_has_vwap_overlay_default_false(qapp):
    from ui.chart_panel import ChartPanel
    panel = ChartPanel(_make_config())
    assert not panel.has_vwap_overlay()


def test_clear_also_removes_vwap(qapp):
    from ui.chart_panel import ChartPanel
    panel = ChartPanel(_make_config())
    df = _make_ohlcv(30)
    panel.set_data(df)
    vwap_s = _make_vwap_series(df)
    panel.add_vwap_overlay(vwap_s)
    panel.clear()
    assert not panel.has_vwap_overlay()


def test_vwap_item_uses_cyan_pen(qapp):
    from ui.chart_panel import ChartPanel
    panel = ChartPanel(_make_config())
    df = _make_ohlcv(30)
    panel.set_data(df)
    vwap_s = _make_vwap_series(df)
    panel.add_vwap_overlay(vwap_s)
    pen_color = panel._vwap_item.opts["pen"].color().name().lower()
    assert pen_color == "#00bcd4"


# ------------------------------------------------------------------ y-autoscale

def test_fit_y_to_visible_clips_to_visible_bars(qapp):
    """Y range must reflect only the High/Low of bars in the current x window."""
    from ui.chart_panel import ChartPanel

    panel = ChartPanel(_make_config())
    df = _make_ohlcv(50)
    panel.set_data(df)

    # Narrow the view to bars 10..19 and trigger fit manually
    panel._fit_y_to_visible(x_range=(10.0, 19.0))
    y_lo, y_hi = panel._view_box.viewRange()[1]

    visible = df.iloc[10:20]
    expected_lo = float(visible["Low"].min())
    expected_hi = float(visible["High"].max())

    assert y_lo < expected_lo          # padding added below
    assert y_hi > expected_hi          # padding added above
    assert y_lo > float(df["Low"].min()) - 1   # not showing off-screen lows


def test_fit_y_to_visible_noop_without_data(qapp):
    """Calling _fit_y_to_visible before set_data must not raise."""
    from ui.chart_panel import ChartPanel

    panel = ChartPanel(_make_config())
    panel._fit_y_to_visible(x_range=(0.0, 20.0))  # no exception


def test_fit_y_to_visible_out_of_range_clamps(qapp):
    """x_range extending beyond the data length must not raise."""
    from ui.chart_panel import ChartPanel

    panel = ChartPanel(_make_config())
    df = _make_ohlcv(20)
    panel.set_data(df)
    panel._fit_y_to_visible(x_range=(-5.0, 100.0))  # wider than data — no error

def test_mark_ai_signals_adds_items(qapp):
    from ui.chart_panel import ChartPanel
    panel = ChartPanel(_make_config())
    df = _make_ohlcv(50)
    panel.set_data(df)
    panel.mark_ai_signals([10, 20, 30])
    assert panel.has_ai_signals()
    assert len(panel._ai_signal_items) == 3


def test_clear_ai_signals_removes_all(qapp):
    from ui.chart_panel import ChartPanel
    panel = ChartPanel(_make_config())
    df = _make_ohlcv(50)
    panel.set_data(df)
    panel.mark_ai_signals([5, 15])
    panel.clear_ai_signals()
    assert not panel.has_ai_signals()
    assert panel._ai_signal_items == []


def test_mark_ai_signals_replaces_previous(qapp):
    from ui.chart_panel import ChartPanel
    panel = ChartPanel(_make_config())
    df = _make_ohlcv(50)
    panel.set_data(df)
    panel.mark_ai_signals([1, 2, 3])
    panel.mark_ai_signals([5])
    assert len(panel._ai_signal_items) == 1


def test_mark_ai_signals_empty_list_is_noop(qapp):
    from ui.chart_panel import ChartPanel
    panel = ChartPanel(_make_config())
    df = _make_ohlcv(50)
    panel.set_data(df)
    panel.mark_ai_signals([])
    assert not panel.has_ai_signals()

