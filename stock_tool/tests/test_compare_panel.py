"""Tests for ui.compare_panel — headless via offscreen Qt platform."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

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
            candle_bull_color="#26a69a", candle_bear_color="#ef5350",
            background_color="#131722",
            ma_colors=("#2196F3",), export_resolution=(800, 600),
        ),
        indicators=IndicatorsConfig(
            rsi_period=14, rsi_overbought=70, rsi_oversold=30,
            macd_fast=12, macd_slow=26, macd_signal=9,
            stc_fast=23, stc_slow=50, stc_cycle=10,
        ),
        scheduler=SchedulerConfig(
            enabled=False, cron="0 18 * * 1-5", symbols_file=Path("./watchlist.txt"),
        ),
        source_path=Path("./config.yaml"),
    )


def _make_ohlcv(n: int = 30) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    closes = 100.0 + np.cumsum(rng.normal(0, 1, n))
    opens = closes + rng.normal(0, 0.3, n)
    highs = np.maximum(opens, closes) + 0.5
    lows = np.minimum(opens, closes) - 0.5
    vols = np.full(n, 1_000_000.0)
    idx = pd.date_range("2024-01-02", periods=n, freq="B")
    return pd.DataFrame(
        {"Open": opens, "High": highs, "Low": lows,
         "Close": closes, "Volume": vols, "Adj_Close": closes},
        index=idx,
    )


def _fake_dm(df: pd.DataFrame | None = None):
    from core.data_manager import DataManager
    dm = MagicMock(spec=DataManager)
    if df is not None:
        dm.get_history.return_value = df
    else:
        from core.data_manager import DataManagerError
        dm.get_history.side_effect = DataManagerError("no data")
    return dm


# ── construction ──────────────────────────────────────────────────────────────

def test_compare_panel_constructs(qapp):
    from ui.compare_panel import ComparePanel
    panel = ComparePanel(_make_config(), _fake_dm())
    assert panel is not None


def test_compare_panel_has_embedded_chart(qapp):
    from ui.chart_panel import ChartPanel
    from ui.compare_panel import ComparePanel
    panel = ComparePanel(_make_config(), _fake_dm())
    assert isinstance(panel.chart, ChartPanel)


def test_compare_panel_lock_axes_default_true(qapp):
    from ui.compare_panel import ComparePanel
    panel = ComparePanel(_make_config(), _fake_dm())
    assert panel.lock_axes is True


def test_compare_panel_lock_cb_checked_by_default(qapp):
    from ui.compare_panel import ComparePanel
    panel = ComparePanel(_make_config(), _fake_dm())
    assert panel._lock_cb.isChecked()


def test_compare_panel_symbol_edit_exists(qapp):
    from PyQt6.QtWidgets import QLineEdit
    from ui.compare_panel import ComparePanel
    panel = ComparePanel(_make_config(), _fake_dm())
    assert isinstance(panel._symbol_edit, QLineEdit)


def test_compare_panel_status_label_exists(qapp):
    from PyQt6.QtWidgets import QLabel
    from ui.compare_panel import ComparePanel
    panel = ComparePanel(_make_config(), _fake_dm())
    assert isinstance(panel._status, QLabel)


# ── lock_axes toggle ──────────────────────────────────────────────────────────

def test_lock_cb_toggle_updates_lock_axes(qapp):
    from ui.compare_panel import ComparePanel
    panel = ComparePanel(_make_config(), _fake_dm())
    assert panel.lock_axes is True

    panel._lock_cb.setChecked(False)
    assert panel.lock_axes is False

    panel._lock_cb.setChecked(True)
    assert panel.lock_axes is True


# ── data loading ──────────────────────────────────────────────────────────────

def test_on_load_with_blank_symbol_does_nothing(qapp):
    from ui.compare_panel import ComparePanel
    panel = ComparePanel(_make_config(), _fake_dm(_make_ohlcv()))
    panel._symbol_edit.setText("")
    initial_status = panel._status.text()
    panel._on_load()
    assert panel._status.text() == initial_status   # unchanged


def test_on_load_success_updates_status(qapp):
    from ui.compare_panel import ComparePanel
    df = _make_ohlcv(30)
    panel = ComparePanel(_make_config(), _fake_dm(df))
    panel._symbol_edit.setText("AAPL")
    panel._on_load()
    assert "AAPL" in panel._status.text()
    assert "30" in panel._status.text()


def test_on_load_success_populates_chart(qapp):
    from ui.compare_panel import ComparePanel
    df = _make_ohlcv(30)
    panel = ComparePanel(_make_config(), _fake_dm(df))
    panel._symbol_edit.setText("MSFT")
    panel._on_load()
    assert panel.chart.data is not None


def test_on_load_error_shows_error_in_status(qapp):
    from ui.compare_panel import ComparePanel
    panel = ComparePanel(_make_config(), _fake_dm(None))
    panel._symbol_edit.setText("FAKE")
    panel._on_load()
    assert "Error" in panel._status.text()


# ── x-axis sync ───────────────────────────────────────────────────────────────

def test_sync_with_connects_main_chart(qapp):
    from ui.chart_panel import ChartPanel
    from ui.compare_panel import ComparePanel
    cfg = _make_config()
    main_chart = ChartPanel(cfg)
    panel = ComparePanel(cfg, _fake_dm())
    # sync_with should not raise
    panel.sync_with(main_chart)
    assert panel._main_chart is main_chart


def test_sync_reentrancy_guard_starts_false(qapp):
    from ui.compare_panel import ComparePanel
    panel = ComparePanel(_make_config(), _fake_dm())
    assert panel._syncing is False


def test_on_main_range_changed_skips_when_locked_off(qapp):
    """When lock_axes is False, syncing should be skipped."""
    from ui.chart_panel import ChartPanel
    from ui.compare_panel import ComparePanel
    cfg = _make_config()
    main_chart = ChartPanel(cfg)
    panel = ComparePanel(cfg, _fake_dm())
    panel.sync_with(main_chart)
    panel._lock_cb.setChecked(False)
    # No assertion needed — just verifies it does not raise
    panel._on_main_range_changed(None, (0.0, 100.0))


def test_on_compare_range_skips_when_syncing(qapp):
    """Reentrancy guard prevents infinite loops."""
    from ui.chart_panel import ChartPanel
    from ui.compare_panel import ComparePanel
    cfg = _make_config()
    main_chart = ChartPanel(cfg)
    panel = ComparePanel(cfg, _fake_dm())
    panel.sync_with(main_chart)
    panel._syncing = True
    panel._on_compare_range_changed(None, (0.0, 100.0))
    # _syncing should still be True (we didn't enter the handler body)
    assert panel._syncing is True


# ── chart property ────────────────────────────────────────────────────────────

def test_chart_property_returns_embedded_panel(qapp):
    from ui.chart_panel import ChartPanel
    from ui.compare_panel import ComparePanel
    panel = ComparePanel(_make_config(), _fake_dm())
    assert isinstance(panel.chart, ChartPanel)
    assert panel.chart is panel._chart
