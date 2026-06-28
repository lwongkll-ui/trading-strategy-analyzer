"""Tests for ui.indicator_panel — headless via offscreen Qt platform."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from core.config import (
    ChartConfig, Config, DataConfig, DownloadConfig,
    IndicatorsConfig, NewsConfig, SchedulerConfig,
)


def _make_config() -> Config:
    return Config(
        data=DataConfig(price_dir=Path("./prices"), export_dir=Path("./exports")),
        download=DownloadConfig(
            default_start_date=date(2024, 1, 1), provider="yfinance",
            alpha_vantage_key="",
        ),
        news=NewsConfig(provider="newsapi", newsapi_key="", max_headlines=20),
        chart=ChartConfig(
            default_timeframe="D",
            candle_bull_color="#26a69a",
            candle_bear_color="#ef5350",
            background_color="#131722",
            ma_colors=("#2196F3", "#FF9800"),
            export_resolution=(1920, 1080),
        ),
        indicators=IndicatorsConfig(
            rsi_period=14, rsi_overbought=70, rsi_oversold=30,
            macd_fast=12, macd_slow=26, macd_signal=9,
            stc_fast=23, stc_slow=50, stc_cycle=10,
        ),
        scheduler=SchedulerConfig(
            enabled=False, cron="0 18 * * 1-5",
            symbols_file=Path("./watchlist.txt"),
        ),
        source_path=Path("./config.yaml"),
    )


def _make_ohlcv(n: int = 100, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    closes = 100.0 + np.cumsum(rng.normal(0, 1, n))
    opens = closes + rng.normal(0, 0.3, n)
    highs = np.maximum(opens, closes) + np.abs(rng.normal(0, 0.5, n))
    lows = np.minimum(opens, closes) - np.abs(rng.normal(0, 0.5, n))
    volumes = rng.integers(1_000_000, 5_000_000, n).astype(float)
    idx = pd.date_range("2024-01-02", periods=n, freq="B")
    return pd.DataFrame(
        {"Open": opens, "High": highs, "Low": lows,
         "Close": closes, "Volume": volumes, "Adj_Close": closes},
        index=idx,
    )


# ── IndicatorPanel construction ───────────────────────────────────────────────

def test_panel_constructs_empty(qapp):
    from ui.indicator_panel import IndicatorPanel
    panel = IndicatorPanel(_make_config())
    assert panel.active_indicators() == []
    assert panel.subchart_count == 0


def test_panel_splitter_is_vertical(qapp):
    from PyQt6.QtCore import Qt
    from ui.indicator_panel import IndicatorPanel
    panel = IndicatorPanel(_make_config())
    assert panel._splitter.orientation() == Qt.Orientation.Vertical


# ── add_subchart ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("indicator", ["volume", "rsi", "macd", "stc", "atr", "stoch", "obv"])
def test_add_all_indicator_types(qapp, indicator):
    from ui.indicator_panel import IndicatorPanel
    panel = IndicatorPanel(_make_config())
    panel.add_subchart(indicator)
    assert indicator in panel.active_indicators()
    assert panel.subchart_count == 1


def test_add_four_subcharts_ok(qapp):
    from ui.indicator_panel import IndicatorPanel
    panel = IndicatorPanel(_make_config())
    for ind in ["volume", "rsi", "macd", "stc"]:
        panel.add_subchart(ind)
    assert panel.subchart_count == 4
    assert panel.active_indicators() == ["volume", "rsi", "macd", "stc"]


def test_add_fifth_subchart_raises(qapp):
    from ui.indicator_panel import IndicatorPanel, IndicatorPanelError, MAX_SUBCHARTS
    panel = IndicatorPanel(_make_config())
    for ind in ["volume", "rsi", "macd", "stc"]:
        panel.add_subchart(ind)
    with pytest.raises(IndicatorPanelError, match=str(MAX_SUBCHARTS)):
        panel.add_subchart("volume")


def test_add_duplicate_raises(qapp):
    from ui.indicator_panel import IndicatorPanel, IndicatorPanelError
    panel = IndicatorPanel(_make_config())
    panel.add_subchart("rsi")
    with pytest.raises(IndicatorPanelError, match="already active"):
        panel.add_subchart("rsi")


def test_add_unknown_indicator_raises(qapp):
    from ui.indicator_panel import IndicatorPanel, IndicatorPanelError
    panel = IndicatorPanel(_make_config())
    with pytest.raises(IndicatorPanelError, match="Unknown indicator"):
        panel.add_subchart("bollinger")


def test_add_subchart_preserves_order(qapp):
    from ui.indicator_panel import IndicatorPanel
    panel = IndicatorPanel(_make_config())
    panel.add_subchart("macd")
    panel.add_subchart("rsi")
    panel.add_subchart("volume")
    assert panel.active_indicators() == ["macd", "rsi", "volume"]


# ── set_data ──────────────────────────────────────────────────────────────────

def test_set_data_renders_all_active_subcharts(qapp):
    from ui.indicator_panel import IndicatorPanel
    panel = IndicatorPanel(_make_config())
    panel.add_subchart("volume")
    panel.add_subchart("rsi")
    df = _make_ohlcv(60)
    panel.set_data(df)  # should not raise

    for key in panel.active_indicators():
        assert panel._charts[key]._df is not None


def test_add_subchart_after_set_data_auto_renders(qapp):
    from ui.indicator_panel import IndicatorPanel
    panel = IndicatorPanel(_make_config())
    df = _make_ohlcv(60)
    panel.set_data(df)

    panel.add_subchart("macd")
    assert panel._charts["macd"]._df is not None
    assert len(panel._charts["macd"]._items) > 0


# ── remove_subchart ───────────────────────────────────────────────────────────

def test_remove_subchart_removes_it(qapp):
    from ui.indicator_panel import IndicatorPanel
    panel = IndicatorPanel(_make_config())
    panel.add_subchart("rsi")
    panel.add_subchart("volume")
    panel.remove_subchart("rsi")
    assert "rsi" not in panel.active_indicators()
    assert panel.subchart_count == 1


def test_remove_unknown_subchart_is_noop(qapp):
    from ui.indicator_panel import IndicatorPanel
    panel = IndicatorPanel(_make_config())
    panel.remove_subchart("rsi")  # should not raise


def test_remove_then_readd_allowed(qapp):
    from ui.indicator_panel import IndicatorPanel
    panel = IndicatorPanel(_make_config())
    panel.add_subchart("rsi")
    panel.remove_subchart("rsi")
    panel.add_subchart("rsi")  # should not raise
    assert "rsi" in panel.active_indicators()


# ── clear ─────────────────────────────────────────────────────────────────────

def test_clear_removes_all_subcharts(qapp):
    from ui.indicator_panel import IndicatorPanel
    panel = IndicatorPanel(_make_config())
    for ind in ["volume", "rsi", "macd"]:
        panel.add_subchart(ind)
    panel.clear()
    assert panel.active_indicators() == []
    assert panel.subchart_count == 0


def test_clear_allows_re_adding(qapp):
    from ui.indicator_panel import IndicatorPanel
    panel = IndicatorPanel(_make_config())
    panel.add_subchart("volume")
    panel.clear()
    panel.add_subchart("volume")
    assert panel.subchart_count == 1


# ── sub-chart internals ───────────────────────────────────────────────────────

def test_volume_subchart_renders_items(qapp):
    from ui.indicator_panel import VolumeSubChart
    chart = VolumeSubChart(_make_config())
    chart.set_data(_make_ohlcv(30))
    assert len(chart._items) > 0


def test_rsi_subchart_uses_config_period_by_default(qapp):
    from ui.indicator_panel import RsiSubChart
    cfg = _make_config()
    chart = RsiSubChart(cfg)
    assert chart._period == cfg.indicators.rsi_period
    assert chart._overbought == cfg.indicators.rsi_overbought
    assert chart._oversold == cfg.indicators.rsi_oversold


def test_rsi_subchart_accepts_override_period(qapp):
    from ui.indicator_panel import RsiSubChart
    chart = RsiSubChart(_make_config(), period=7)
    assert chart._period == 7


def test_rsi_subchart_renders_items(qapp):
    from ui.indicator_panel import RsiSubChart
    chart = RsiSubChart(_make_config())
    chart.set_data(_make_ohlcv(60))
    assert len(chart._items) > 0


def test_macd_subchart_uses_config_defaults(qapp):
    from ui.indicator_panel import MacdSubChart
    cfg = _make_config()
    chart = MacdSubChart(cfg)
    assert chart._fast == cfg.indicators.macd_fast
    assert chart._slow == cfg.indicators.macd_slow
    assert chart._signal == cfg.indicators.macd_signal


def test_macd_subchart_renders_items(qapp):
    from ui.indicator_panel import MacdSubChart
    chart = MacdSubChart(_make_config())
    chart.set_data(_make_ohlcv(60))
    assert len(chart._items) > 0


def test_stc_subchart_uses_config_defaults(qapp):
    from ui.indicator_panel import StcSubChart
    cfg = _make_config()
    chart = StcSubChart(cfg)
    assert chart._fast == cfg.indicators.stc_fast
    assert chart._slow == cfg.indicators.stc_slow
    assert chart._cycle == cfg.indicators.stc_cycle


def test_stc_subchart_renders_items(qapp):
    from ui.indicator_panel import StcSubChart
    chart = StcSubChart(_make_config())
    chart.set_data(_make_ohlcv(100))
    assert len(chart._items) > 0


def test_subchart_clear_removes_items(qapp):
    from ui.indicator_panel import VolumeSubChart
    chart = VolumeSubChart(_make_config())
    chart.set_data(_make_ohlcv(30))
    assert len(chart._items) > 0
    chart.clear()
    assert len(chart._items) == 0


def test_subchart_set_data_replaces_previous_items(qapp):
    from ui.indicator_panel import RsiSubChart
    chart = RsiSubChart(_make_config())
    chart.set_data(_make_ohlcv(60))
    first_count = len(chart._items)
    chart.set_data(_make_ohlcv(60, seed=99))
    assert len(chart._items) == first_count  # same structure, fresh items


def test_atr_subchart_uses_config_period(qapp):
    from ui.indicator_panel import AtrSubChart
    cfg = _make_config()
    chart = AtrSubChart(cfg)
    assert chart._period == cfg.indicators.atr_period


def test_atr_subchart_renders_items(qapp):
    from ui.indicator_panel import AtrSubChart
    chart = AtrSubChart(_make_config())
    chart.set_data(_make_ohlcv(60))
    assert len(chart._items) > 0


def test_stoch_subchart_uses_config_defaults(qapp):
    from ui.indicator_panel import StochSubChart
    cfg = _make_config()
    chart = StochSubChart(cfg)
    assert chart._k == cfg.indicators.stoch_k
    assert chart._d == cfg.indicators.stoch_d


def test_stoch_subchart_renders_items(qapp):
    from ui.indicator_panel import StochSubChart
    chart = StochSubChart(_make_config())
    chart.set_data(_make_ohlcv(60))
    assert len(chart._items) > 0


def test_add_four_subcharts_with_new_indicators(qapp):
    from ui.indicator_panel import IndicatorPanel
    panel = IndicatorPanel(_make_config())
    for ind in ["rsi", "macd", "atr", "stoch"]:
        panel.add_subchart(ind)
    assert panel.subchart_count == 4
    assert panel.active_indicators() == ["rsi", "macd", "atr", "stoch"]


# ── OBV sub-chart ─────────────────────────────────────────────────────────────

def test_obv_subchart_in_valid_indicators(qapp):
    from ui.indicator_panel import VALID_INDICATORS
    assert "obv" in VALID_INDICATORS


def test_obv_subchart_renders_items(qapp):
    from ui.indicator_panel import ObvSubChart
    chart = ObvSubChart(_make_config())
    chart.set_data(_make_ohlcv(30))
    assert len(chart._items) > 0


def test_obv_subchart_clear_removes_items(qapp):
    from ui.indicator_panel import ObvSubChart
    chart = ObvSubChart(_make_config())
    chart.set_data(_make_ohlcv(30))
    chart.clear()
    assert len(chart._items) == 0


def test_add_obv_subchart_via_panel(qapp):
    from ui.indicator_panel import IndicatorPanel
    panel = IndicatorPanel(_make_config())
    panel.add_subchart("obv")
    assert "obv" in panel.active_indicators()
    assert panel.subchart_count == 1


def test_obv_subchart_auto_renders_on_set_data(qapp):
    from ui.indicator_panel import IndicatorPanel
    panel = IndicatorPanel(_make_config())
    df = _make_ohlcv(60)
    panel.set_data(df)
    panel.add_subchart("obv")
    assert panel._charts["obv"]._df is not None
    assert len(panel._charts["obv"]._items) > 0


# ── gear button visibility ────────────────────────────────────────────────────

def test_volume_subchart_gear_button_hidden(qapp):
    """VolumeSubChart calls hide() on the gear button — isHidden() must be True."""
    from ui.indicator_panel import VolumeSubChart
    chart = VolumeSubChart(_make_config())
    assert chart._gear_btn.isHidden()


def test_obv_subchart_gear_button_hidden(qapp):
    """ObvSubChart calls hide() on the gear button — isHidden() must be True."""
    from ui.indicator_panel import ObvSubChart
    chart = ObvSubChart(_make_config())
    assert chart._gear_btn.isHidden()


def test_rsi_subchart_gear_button_not_hidden(qapp):
    """RsiSubChart never hides the gear button — isHidden() must be False."""
    from ui.indicator_panel import RsiSubChart
    chart = RsiSubChart(_make_config())
    assert not chart._gear_btn.isHidden()


def test_macd_subchart_gear_button_not_hidden(qapp):
    from ui.indicator_panel import MacdSubChart
    chart = MacdSubChart(_make_config())
    assert not chart._gear_btn.isHidden()


def test_stc_subchart_gear_button_not_hidden(qapp):
    from ui.indicator_panel import StcSubChart
    chart = StcSubChart(_make_config())
    assert not chart._gear_btn.isHidden()


def test_atr_subchart_gear_button_not_hidden(qapp):
    from ui.indicator_panel import AtrSubChart
    chart = AtrSubChart(_make_config())
    assert not chart._gear_btn.isHidden()


def test_stoch_subchart_gear_button_not_hidden(qapp):
    from ui.indicator_panel import StochSubChart
    chart = StochSubChart(_make_config())
    assert not chart._gear_btn.isHidden()


# ── widget type ───────────────────────────────────────────────────────────────

def test_subchart_widget_is_qwidget_container(qapp):
    """widget property returns the container QWidget, not the PlotWidget."""
    from PyQt6.QtWidgets import QWidget
    from ui.indicator_panel import RsiSubChart
    import pyqtgraph as pg
    chart = RsiSubChart(_make_config())
    assert isinstance(chart.widget, QWidget)
    assert not isinstance(chart.widget, pg.PlotWidget)
