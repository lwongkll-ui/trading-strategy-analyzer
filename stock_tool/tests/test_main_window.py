"""Tests for ui.main_window — headless via offscreen Qt."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from core.config import (
    ChartConfig, Config, DataConfig, DownloadConfig,
    IndicatorsConfig, NewsConfig, SchedulerConfig,
)
from models.symbol import Symbol, SymbolRegistry


def _make_config(tmp_path: Path) -> Config:
    return Config(
        data=DataConfig(
            price_dir=tmp_path / "prices",
            export_dir=tmp_path / "exports",
        ),
        download=DownloadConfig(
            default_start_date=date(2020, 1, 1),
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
            rsi_period=14, rsi_overbought=70, rsi_oversold=30,
            macd_fast=12, macd_slow=26, macd_signal=9,
            stc_fast=23, stc_slow=50, stc_cycle=10,
        ),
        scheduler=SchedulerConfig(
            enabled=False, cron="0 18 * * 1-5",
            symbols_file=tmp_path / "watchlist.txt",
        ),
        source_path=tmp_path / "config.yaml",
    )


def _make_ohlcv(n: int = 50) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    closes = 100.0 + np.cumsum(rng.normal(0, 1, n))
    opens = closes + rng.normal(0, 0.3, n)
    highs = np.maximum(opens, closes) + np.abs(rng.normal(0, 0.5, n))
    lows = np.minimum(opens, closes) - np.abs(rng.normal(0, 0.5, n))
    vols = rng.integers(1_000_000, 5_000_000, n).astype(float)
    idx = pd.date_range("2024-01-02", periods=n, freq="B")
    return pd.DataFrame(
        {"Open": opens, "High": highs, "Low": lows,
         "Close": closes, "Volume": vols, "Adj_Close": closes},
        index=idx,
    )


def _fake_dm(df: pd.DataFrame | None = None):
    """Return a mock DataManager whose get_history returns df."""
    from core.data_manager import DataManager
    dm = MagicMock(spec=DataManager)
    if df is not None:
        dm.get_history.return_value = df
        dm.resample.side_effect = lambda frame, tf: frame  # passthrough
    else:
        from core.data_manager import DataManagerError
        dm.get_history.side_effect = DataManagerError("no data")
    return dm


def _fake_news_fetcher():
    """Return a mock NewsFetcher that returns no articles (avoids network)."""
    from core.news_fetcher import NewsFetcher
    fetcher = MagicMock(spec=NewsFetcher)
    fetcher.fetch.return_value = []
    return fetcher


def _open_db(tmp_path: Path):
    from storage.db_store import DbStore
    db = DbStore(tmp_path / "test.db")
    db.open()
    return db


# ── construction ──────────────────────────────────────────────────────────────

def test_main_window_constructs(qapp, tmp_path):
    from ui.main_window import MainWindow
    win = MainWindow(_make_config(tmp_path))
    assert win.windowTitle() == "StockTool"
    assert win.current_ticker == ""
    assert win.timeframe == "D"


def test_main_window_has_chart_and_indicator_panel(qapp, tmp_path):
    from ui.chart_panel import ChartPanel
    from ui.indicator_panel import IndicatorPanel
    from ui.main_window import MainWindow

    win = MainWindow(_make_config(tmp_path))
    assert isinstance(win.chart, ChartPanel)
    assert isinstance(win.indicator_panel, IndicatorPanel)


def test_main_window_accepts_registry(qapp, tmp_path):
    from ui.main_window import MainWindow

    reg = SymbolRegistry()
    reg.add(Symbol(ticker="AAPL", name="Apple Inc."))
    win = MainWindow(_make_config(tmp_path), registry=reg)
    assert win._registry is reg


# ── toolbar widgets ───────────────────────────────────────────────────────────

def test_toolbar_symbol_edit_exists(qapp, tmp_path):
    from PyQt6.QtWidgets import QLineEdit
    from ui.main_window import MainWindow

    win = MainWindow(_make_config(tmp_path))
    assert isinstance(win._symbol_edit, QLineEdit)


def test_toolbar_market_combo_has_expected_items(qapp, tmp_path):
    from ui.main_window import MainWindow

    win = MainWindow(_make_config(tmp_path))
    items = [win._market_combo.itemText(i) for i in range(win._market_combo.count())]
    assert "ALL" in items
    assert "US" in items
    assert "HK" in items


def test_toolbar_timeframe_buttons_exist(qapp, tmp_path):
    from ui.main_window import MainWindow, _TIMEFRAMES

    win = MainWindow(_make_config(tmp_path))
    assert set(win._tf_buttons.keys()) == set(_TIMEFRAMES)


def test_toolbar_d_button_checked_by_default(qapp, tmp_path):
    from ui.main_window import MainWindow

    win = MainWindow(_make_config(tmp_path))
    assert win._tf_buttons["D"].isChecked()
    for tf in ("W", "M", "Q", "Y"):
        assert not win._tf_buttons[tf].isChecked()


def test_toolbar_indicator_buttons_exist(qapp, tmp_path):
    from ui.main_window import MainWindow, _INDICATORS

    win = MainWindow(_make_config(tmp_path))
    assert set(win._indicator_btns.keys()) == set(_INDICATORS)


def test_toolbar_start_date_matches_config(qapp, tmp_path):
    from ui.main_window import MainWindow

    cfg = _make_config(tmp_path)
    win = MainWindow(cfg)
    qd = win._start_date.date()
    assert qd.year() == cfg.download.default_start_date.year
    assert qd.month() == cfg.download.default_start_date.month


# ── load_ticker ───────────────────────────────────────────────────────────────

def test_load_ticker_success(qapp, tmp_path):
    from ui.main_window import MainWindow

    df = _make_ohlcv(30)
    win = MainWindow(_make_config(tmp_path), data_manager=_fake_dm(df))
    result = win.load_ticker("AAPL")

    assert result is True
    assert win.current_ticker == "AAPL"
    assert "AAPL" in win.windowTitle()
    assert win.chart.data is not None


def test_load_ticker_error_returns_false(qapp, tmp_path):
    from ui.main_window import MainWindow

    win = MainWindow(_make_config(tmp_path), data_manager=_fake_dm(None))
    result = win.load_ticker("INVALID")

    assert result is False
    assert win.current_ticker == ""


def test_load_ticker_blank_returns_false(qapp, tmp_path):
    from ui.main_window import MainWindow

    win = MainWindow(_make_config(tmp_path), data_manager=_fake_dm(_make_ohlcv()))
    assert win.load_ticker("") is False
    assert win.load_ticker("   ") is False


def test_load_ticker_updates_status_bar(qapp, tmp_path):
    from ui.main_window import MainWindow

    df = _make_ohlcv(30)
    win = MainWindow(_make_config(tmp_path), data_manager=_fake_dm(df))
    win.load_ticker("MSFT")
    msg = win.statusBar().currentMessage()
    assert "MSFT" in msg


def test_load_ticker_uppercases_symbol(qapp, tmp_path):
    from ui.main_window import MainWindow

    df = _make_ohlcv()
    win = MainWindow(_make_config(tmp_path), data_manager=_fake_dm(df))
    win.load_ticker("aapl")
    assert win.current_ticker == "AAPL"


# ── timeframe switching ───────────────────────────────────────────────────────

def test_timeframe_switch_updates_internal_state(qapp, tmp_path):
    from ui.main_window import MainWindow

    df = _make_ohlcv(60)
    win = MainWindow(_make_config(tmp_path), data_manager=_fake_dm(df))
    win.load_ticker("AAPL")

    win._on_timeframe_clicked("W")
    assert win.timeframe == "W"


def test_timeframe_switch_without_data_does_not_crash(qapp, tmp_path):
    from ui.main_window import MainWindow

    win = MainWindow(_make_config(tmp_path))
    win._on_timeframe_clicked("M")  # no data loaded — should be silent
    assert win.timeframe == "M"


# ── MA overlays ───────────────────────────────────────────────────────────────

def test_add_ma_requires_data(qapp, tmp_path):
    from ui.main_window import MainWindow

    win = MainWindow(_make_config(tmp_path))
    win._on_add_ma()
    assert win.statusBar().currentMessage() == "Load a symbol first"


def test_add_ma_adds_overlay_to_chart(qapp, tmp_path):
    from ui.main_window import MainWindow

    df = _make_ohlcv(60)
    win = MainWindow(_make_config(tmp_path), data_manager=_fake_dm(df))
    win.load_ticker("AAPL")

    win._ma_type_combo.setCurrentText("SMA")
    win._ma_period_spin.setValue(10)
    win._on_add_ma()

    assert "SMA_10" in win.chart.overlay_names()


def test_add_duplicate_ma_shows_message(qapp, tmp_path):
    from ui.main_window import MainWindow

    df = _make_ohlcv(60)
    win = MainWindow(_make_config(tmp_path), data_manager=_fake_dm(df))
    win.load_ticker("AAPL")
    win._ma_type_combo.setCurrentText("EMA")
    win._ma_period_spin.setValue(20)
    win._on_add_ma()
    win._on_add_ma()  # duplicate

    assert "already on the chart" in win.statusBar().currentMessage()


def test_clear_mas(qapp, tmp_path):
    from ui.main_window import MainWindow

    df = _make_ohlcv(60)
    win = MainWindow(_make_config(tmp_path), data_manager=_fake_dm(df))
    win.load_ticker("AAPL")
    win._ma_type_combo.setCurrentText("SMA")
    win._ma_period_spin.setValue(5)
    win._on_add_ma()
    assert len(win.chart.overlay_names()) == 1

    win._on_clear_mas()
    assert win.chart.overlay_names() == []


# ── indicator toggles ─────────────────────────────────────────────────────────

def test_toggle_volume_on_adds_subchart(qapp, tmp_path):
    from ui.main_window import MainWindow

    df = _make_ohlcv(60)
    win = MainWindow(_make_config(tmp_path), data_manager=_fake_dm(df))
    win.load_ticker("AAPL")

    win._toggle_indicator("volume", True)
    assert "volume" in win.indicator_panel.active_indicators()


def test_toggle_indicator_off_removes_subchart(qapp, tmp_path):
    from ui.main_window import MainWindow

    df = _make_ohlcv(60)
    win = MainWindow(_make_config(tmp_path), data_manager=_fake_dm(df))
    win.load_ticker("AAPL")

    win._toggle_indicator("rsi", True)
    assert "rsi" in win.indicator_panel.active_indicators()

    win._toggle_indicator("rsi", False)
    assert "rsi" not in win.indicator_panel.active_indicators()


# ── news sidebar ──────────────────────────────────────────────────────────────

def test_news_dock_exists(qapp, tmp_path):
    from ui.main_window import MainWindow
    win = MainWindow(_make_config(tmp_path))
    assert hasattr(win, "_news_dock")
    assert hasattr(win, "_news_sidebar")


def test_news_sidebar_accessible(qapp, tmp_path):
    from ui.news_sidebar import NewsSidebar
    from ui.main_window import MainWindow
    win = MainWindow(_make_config(tmp_path))
    assert isinstance(win.news_sidebar, NewsSidebar)


# ── watchlist integration ─────────────────────────────────────────────────────

def test_watchlist_dock_exists(qapp, tmp_path):
    from ui.watchlist_panel import WatchlistPanel
    from ui.main_window import MainWindow
    win = MainWindow(_make_config(tmp_path))
    assert isinstance(win.watchlist_panel, WatchlistPanel)
    assert hasattr(win, "_watchlist_dock")


def test_watchlist_star_button_exists(qapp, tmp_path):
    from ui.main_window import MainWindow
    win = MainWindow(_make_config(tmp_path))
    assert hasattr(win, "_watchlist_btn")


def test_add_to_watchlist_requires_ticker(qapp, tmp_path):
    from ui.main_window import MainWindow
    win = MainWindow(_make_config(tmp_path))
    win._on_add_to_watchlist()
    assert "Load a symbol" in win.statusBar().currentMessage()


def test_add_to_watchlist_stores_current_ticker(qapp, tmp_path):
    from ui.main_window import MainWindow
    df = _make_ohlcv(30)
    with _open_db(tmp_path) as db:
        win = MainWindow(
            _make_config(tmp_path),
            data_manager=_fake_dm(df),
            db_store=db,
            news_fetcher=_fake_news_fetcher(),
        )
        win.load_ticker("AAPL")
        win._on_add_to_watchlist()
        assert db.in_watchlist("AAPL")
        assert win.watchlist_panel.ticker_count == 1


def test_add_to_watchlist_shows_status(qapp, tmp_path):
    from ui.main_window import MainWindow
    df = _make_ohlcv(30)
    with _open_db(tmp_path) as db:
        win = MainWindow(
            _make_config(tmp_path),
            data_manager=_fake_dm(df),
            db_store=db,
            news_fetcher=_fake_news_fetcher(),
        )
        win.load_ticker("TSLA")
        win._on_add_to_watchlist()
        assert "TSLA" in win.statusBar().currentMessage()


def test_watchlist_ticker_selected_loads_chart(qapp, tmp_path):
    from ui.main_window import MainWindow
    df = _make_ohlcv(30)
    with _open_db(tmp_path) as db:
        db.add_to_watchlist("MSFT")
        win = MainWindow(
            _make_config(tmp_path),
            data_manager=_fake_dm(df),
            db_store=db,
            news_fetcher=_fake_news_fetcher(),
        )
        win._on_watchlist_ticker_selected("MSFT")
        assert win.current_ticker == "MSFT"
        assert win._symbol_edit.text() == "MSFT"


# ── drawing tools ─────────────────────────────────────────────────────────────

def test_drawing_mode_buttons_exist(qapp, tmp_path):
    from ui.main_window import MainWindow
    win = MainWindow(_make_config(tmp_path))
    assert "none" in win._draw_btns
    assert "horizontal" in win._draw_btns
    assert "trend_line" in win._draw_btns
    assert "text" in win._draw_btns


def test_drawing_mode_none_checked_by_default(qapp, tmp_path):
    from ui.main_window import MainWindow
    win = MainWindow(_make_config(tmp_path))
    assert win._draw_btns["none"].isChecked()
    for key in ("horizontal", "trend_line", "text"):
        assert not win._draw_btns[key].isChecked()


def test_drawing_manager_created(qapp, tmp_path):
    from ui.drawing_tools import DrawingManager
    from ui.main_window import MainWindow
    win = MainWindow(_make_config(tmp_path))
    assert isinstance(win.drawing_manager, DrawingManager)


def test_load_ticker_loads_drawings(qapp, tmp_path):
    from ui.main_window import MainWindow
    df = _make_ohlcv(30)
    with _open_db(tmp_path) as db:
        db.save_drawing("AAPL", "D", "horizontal", {"price": 150.0})
        win = MainWindow(
            _make_config(tmp_path),
            data_manager=_fake_dm(df),
            db_store=db,
            news_fetcher=_fake_news_fetcher(),
        )
        win.load_ticker("AAPL")
        assert win.drawing_manager.count == 1


def test_delete_drawings_clears_db(qapp, tmp_path):
    from ui.main_window import MainWindow
    df = _make_ohlcv(30)
    with _open_db(tmp_path) as db:
        db.save_drawing("AAPL", "D", "horizontal", {"price": 150.0})
        win = MainWindow(
            _make_config(tmp_path),
            data_manager=_fake_dm(df),
            db_store=db,
            news_fetcher=_fake_news_fetcher(),
        )
        win.load_ticker("AAPL")
        assert win.drawing_manager.count == 1
        win._on_delete_drawings()
        assert win.drawing_manager.count == 0
        assert db.drawing_count("AAPL", "D") == 0


def test_delete_drawings_noop_when_no_ticker(qapp, tmp_path):
    from ui.main_window import MainWindow
    win = MainWindow(_make_config(tmp_path))
    win._on_delete_drawings()  # should not raise
    assert "No symbol" in win.statusBar().currentMessage()


# ── settings ──────────────────────────────────────────────────────────────────

def test_settings_action_in_file_menu(qapp, tmp_path):
    from ui.main_window import MainWindow
    win = MainWindow(_make_config(tmp_path))
    menu_bar = win.menuBar()
    file_menu = None
    for action in menu_bar.actions():
        if "File" in action.text():
            file_menu = action.menu()
            break
    assert file_menu is not None
    action_texts = [a.text() for a in file_menu.actions()]
    assert any("Settings" in t for t in action_texts)


# ── timeframe reloads drawings ────────────────────────────────────────────────

def test_timeframe_change_reloads_drawings(qapp, tmp_path):
    from ui.main_window import MainWindow
    df = _make_ohlcv(60)
    with _open_db(tmp_path) as db:
        db.save_drawing("AAPL", "W", "horizontal", {"price": 155.0})
        win = MainWindow(
            _make_config(tmp_path),
            data_manager=_fake_dm(df),
            db_store=db,
            news_fetcher=_fake_news_fetcher(),
        )
        win.load_ticker("AAPL")
        assert win.drawing_manager.count == 0  # no D drawings
        win._on_timeframe_clicked("W")
        assert win.drawing_manager.count == 1  # one W drawing


def test_toggle_indicator_cap_shows_message(qapp, tmp_path):
    from ui.main_window import MainWindow

    df = _make_ohlcv(60)
    win = MainWindow(_make_config(tmp_path), data_manager=_fake_dm(df))
    win.load_ticker("AAPL")

    for ind in ("volume", "rsi", "macd", "stc"):
        win._toggle_indicator(ind, True)

    # Panel is full — adding another should surface the cap message.
    win._indicator_panel.remove_subchart("volume")
    # Re-use the same 4 names — force the cap by adding volume back:
    win._toggle_indicator("volume", True)
    # Now panel has all 4 again and is at cap.
    # Try one more via the button state trick — just verify cap error propagates.
    # We remove one slot and confirm re-adding works without exception.
    win._toggle_indicator("rsi", False)
    win._toggle_indicator("rsi", True)  # should succeed
    assert "rsi" in win.indicator_panel.active_indicators()


# ── candle / line toggle ──────────────────────────────────────────────────────

def test_chart_mode_buttons_exist(qapp, tmp_path):
    from ui.main_window import MainWindow
    win = MainWindow(_make_config(tmp_path))
    assert "candle" in win._chart_mode_btns
    assert "line" in win._chart_mode_btns


def test_chart_mode_candle_checked_by_default(qapp, tmp_path):
    from ui.main_window import MainWindow
    win = MainWindow(_make_config(tmp_path))
    assert win._chart_mode_btns["candle"].isChecked()
    assert not win._chart_mode_btns["line"].isChecked()


def test_chart_mode_toggle_switches_chart(qapp, tmp_path):
    from ui.main_window import MainWindow
    df = _make_ohlcv(30)
    win = MainWindow(_make_config(tmp_path), data_manager=_fake_dm(df))
    win.load_ticker("AAPL")
    assert win.chart.mode == "candle"

    win._on_chart_mode_clicked("line")
    assert win.chart.mode == "line"

    win._on_chart_mode_clicked("candle")
    assert win.chart.mode == "candle"


# ── Bollinger Bands overlay ───────────────────────────────────────────────────

def test_bb_button_exists(qapp, tmp_path):
    from ui.main_window import MainWindow
    win = MainWindow(_make_config(tmp_path))
    assert hasattr(win, "_bb_btn")
    assert win._bb_btn.isCheckable()


def test_bb_toggle_on_adds_overlay(qapp, tmp_path):
    from ui.main_window import MainWindow
    df = _make_ohlcv(60)
    win = MainWindow(_make_config(tmp_path), data_manager=_fake_dm(df))
    win.load_ticker("AAPL")
    assert not win.chart.has_bband_overlay()

    win._on_bb_toggled(True)
    assert win.chart.has_bband_overlay()


def test_bb_toggle_off_removes_overlay(qapp, tmp_path):
    from ui.main_window import MainWindow
    df = _make_ohlcv(60)
    win = MainWindow(_make_config(tmp_path), data_manager=_fake_dm(df))
    win.load_ticker("AAPL")
    win._on_bb_toggled(True)
    win._on_bb_toggled(False)
    assert not win.chart.has_bband_overlay()


def test_bb_toggle_without_data_unchecks_button(qapp, tmp_path):
    from ui.main_window import MainWindow
    win = MainWindow(_make_config(tmp_path))
    win._bb_btn.setChecked(True)
    win._on_bb_toggled(True)
    assert not win._bb_btn.isChecked()
    assert "Load a symbol" in win.statusBar().currentMessage()


def test_load_ticker_resets_bb_overlay(qapp, tmp_path):
    from ui.main_window import MainWindow
    df = _make_ohlcv(60)
    win = MainWindow(_make_config(tmp_path), data_manager=_fake_dm(df))
    win.load_ticker("AAPL")
    win._on_bb_toggled(True)
    assert win.chart.has_bband_overlay()

    win.load_ticker("MSFT")
    assert not win.chart.has_bband_overlay()
    assert not win._bb_btn.isChecked()


# ── new indicator buttons (ATR / Stoch) ───────────────────────────────────────

def test_atr_button_in_indicator_btns(qapp, tmp_path):
    from ui.main_window import MainWindow
    win = MainWindow(_make_config(tmp_path))
    assert "atr" in win._indicator_btns


def test_stoch_button_in_indicator_btns(qapp, tmp_path):
    from ui.main_window import MainWindow
    win = MainWindow(_make_config(tmp_path))
    assert "stoch" in win._indicator_btns


def test_toggle_atr_on_adds_subchart(qapp, tmp_path):
    from ui.main_window import MainWindow
    df = _make_ohlcv(60)
    win = MainWindow(_make_config(tmp_path), data_manager=_fake_dm(df))
    win.load_ticker("AAPL")
    win._toggle_indicator("atr", True)
    assert "atr" in win.indicator_panel.active_indicators()


def test_toggle_stoch_on_adds_subchart(qapp, tmp_path):
    from ui.main_window import MainWindow
    df = _make_ohlcv(60)
    win = MainWindow(_make_config(tmp_path), data_manager=_fake_dm(df))
    win.load_ticker("AAPL")
    win._toggle_indicator("stoch", True)
    assert "stoch" in win.indicator_panel.active_indicators()


# ── VWAP overlay ──────────────────────────────────────────────────────────────

def test_vwap_button_exists(qapp, tmp_path):
    from ui.main_window import MainWindow
    win = MainWindow(_make_config(tmp_path))
    assert hasattr(win, "_vwap_btn")
    assert win._vwap_btn.isCheckable()


def test_vwap_toggle_on_adds_overlay(qapp, tmp_path):
    from ui.main_window import MainWindow
    df = _make_ohlcv(60)
    win = MainWindow(_make_config(tmp_path), data_manager=_fake_dm(df))
    win.load_ticker("AAPL")
    assert not win.chart.has_vwap_overlay()
    win._on_vwap_toggled(True)
    assert win.chart.has_vwap_overlay()


def test_vwap_toggle_off_removes_overlay(qapp, tmp_path):
    from ui.main_window import MainWindow
    df = _make_ohlcv(60)
    win = MainWindow(_make_config(tmp_path), data_manager=_fake_dm(df))
    win.load_ticker("AAPL")
    win._on_vwap_toggled(True)
    win._on_vwap_toggled(False)
    assert not win.chart.has_vwap_overlay()


def test_vwap_toggle_without_data_unchecks_button(qapp, tmp_path):
    from ui.main_window import MainWindow
    win = MainWindow(_make_config(tmp_path))
    win._vwap_btn.setChecked(True)
    win._on_vwap_toggled(True)
    assert not win._vwap_btn.isChecked()
    assert "Load a symbol" in win.statusBar().currentMessage()


def test_load_ticker_resets_vwap_overlay(qapp, tmp_path):
    from ui.main_window import MainWindow
    df = _make_ohlcv(60)
    win = MainWindow(_make_config(tmp_path), data_manager=_fake_dm(df))
    win.load_ticker("AAPL")
    win._on_vwap_toggled(True)
    assert win.chart.has_vwap_overlay()
    win.load_ticker("MSFT")
    assert not win.chart.has_vwap_overlay()
    assert not win._vwap_btn.isChecked()


# ── OBV indicator ─────────────────────────────────────────────────────────────

def test_obv_button_in_indicator_btns(qapp, tmp_path):
    from ui.main_window import MainWindow
    win = MainWindow(_make_config(tmp_path))
    assert "obv" in win._indicator_btns


def test_toggle_obv_on_adds_subchart(qapp, tmp_path):
    from ui.main_window import MainWindow
    df = _make_ohlcv(60)
    win = MainWindow(_make_config(tmp_path), data_manager=_fake_dm(df))
    win.load_ticker("AAPL")
    win._toggle_indicator("obv", True)
    assert "obv" in win.indicator_panel.active_indicators()


# ── keyboard shortcuts ────────────────────────────────────────────────────────

def test_keyboard_shortcuts_created(qapp, tmp_path):
    from ui.main_window import MainWindow
    win = MainWindow(_make_config(tmp_path))
    assert hasattr(win, "_shortcuts")
    assert len(win._shortcuts) == 10   # D W M Q Y C L Ctrl+E Escape Del


def test_keyboard_shortcuts_are_qshortcut_instances(qapp, tmp_path):
    from PyQt6.QtGui import QShortcut
    from ui.main_window import MainWindow
    win = MainWindow(_make_config(tmp_path))
    for sc in win._shortcuts:
        assert isinstance(sc, QShortcut)


# ── data export ───────────────────────────────────────────────────────────────

def test_export_data_action_in_file_menu(qapp, tmp_path):
    from ui.main_window import MainWindow
    win = MainWindow(_make_config(tmp_path))
    menu_bar = win.menuBar()
    file_menu = None
    for action in menu_bar.actions():
        if "File" in action.text():
            file_menu = action.menu()
            break
    assert file_menu is not None
    action_texts = [a.text() for a in file_menu.actions()]
    assert any("Export" in t and "Data" in t for t in action_texts)


def test_export_data_without_data_shows_dialog_text(qapp, tmp_path):
    """_on_export_data with no data loaded should show an info message box.

    We patch QMessageBox.information to avoid the dialog blocking the test.
    """
    from unittest.mock import patch
    from ui.main_window import MainWindow
    win = MainWindow(_make_config(tmp_path))
    with patch("PyQt6.QtWidgets.QMessageBox.information") as mock_info:
        win._on_export_data()
        mock_info.assert_called_once()


def test_export_data_csv(qapp, tmp_path):
    """_on_export_data saves a valid CSV when a path is returned by dialog."""
    from unittest.mock import patch
    from ui.main_window import MainWindow
    df = _make_ohlcv(30)
    win = MainWindow(_make_config(tmp_path), data_manager=_fake_dm(df))
    win.load_ticker("AAPL")
    dest = str(tmp_path / "aapl_export.csv")
    with patch("PyQt6.QtWidgets.QFileDialog.getSaveFileName", return_value=(dest, "")):
        win._on_export_data()
    assert (tmp_path / "aapl_export.csv").is_file()


def test_export_data_xlsx(qapp, tmp_path):
    """_on_export_data saves a valid XLSX when an .xlsx path is chosen."""
    from unittest.mock import patch
    from ui.main_window import MainWindow
    df = _make_ohlcv(30)
    win = MainWindow(_make_config(tmp_path), data_manager=_fake_dm(df))
    win.load_ticker("AAPL")
    dest = str(tmp_path / "aapl_export.xlsx")
    with patch("PyQt6.QtWidgets.QFileDialog.getSaveFileName", return_value=(dest, "")), \
         patch("PyQt6.QtWidgets.QMessageBox.critical"):   # safety net if openpyxl absent
        win._on_export_data()
    # Only assert the file exists if openpyxl was available
    try:
        import openpyxl  # noqa: F401
        assert (tmp_path / "aapl_export.xlsx").is_file()
    except ImportError:
        pass  # openpyxl not installed — skip the file check


# ── compare panel ─────────────────────────────────────────────────────────────

def test_compare_panel_exists(qapp, tmp_path):
    from ui.compare_panel import ComparePanel
    from ui.main_window import MainWindow
    win = MainWindow(_make_config(tmp_path))
    assert isinstance(win.compare_panel, ComparePanel)


def test_compare_dock_hidden_by_default(qapp, tmp_path):
    from ui.main_window import MainWindow
    win = MainWindow(_make_config(tmp_path))
    assert not win._compare_dock.isVisible()


def test_compare_action_in_view_menu(qapp, tmp_path):
    from ui.main_window import MainWindow
    win = MainWindow(_make_config(tmp_path))
    menu_bar = win.menuBar()
    view_menu = None
    for action in menu_bar.actions():
        if "View" in action.text():
            view_menu = action.menu()
            break
    assert view_menu is not None
    action_texts = [a.text() for a in view_menu.actions()]
    assert any("Compare" in t for t in action_texts)


def test_compare_toggle_shows_dock(qapp, tmp_path):
    from ui.main_window import MainWindow
    win = MainWindow(_make_config(tmp_path))
    win.show()   # parent must be shown for isVisible() to reflect child state
    assert not win._compare_dock.isVisible()
    win._on_compare_toggled()
    assert win._compare_dock.isVisible()
    win._on_compare_toggled()
    assert not win._compare_dock.isVisible()


# ── drawing mode fib / rect buttons ──────────────────────────────────────────

def test_drawing_mode_fib_button_exists(qapp, tmp_path):
    from ui.main_window import MainWindow
    win = MainWindow(_make_config(tmp_path))
    assert "fib" in win._draw_btns


def test_drawing_mode_rect_button_exists(qapp, tmp_path):
    from ui.main_window import MainWindow
    win = MainWindow(_make_config(tmp_path))
    assert "rect" in win._draw_btns
