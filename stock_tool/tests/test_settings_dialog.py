"""Tests for ui.settings_dialog."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from core.config import (
    ChartConfig, Config, DataConfig, DownloadConfig,
    IndicatorsConfig, NewsConfig, SchedulerConfig,
)


def _make_config(source_path: Path | None = None) -> Config:
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
            ma_colors=("#2196F3",),
            export_resolution=(800, 600),
        ),
        indicators=IndicatorsConfig(
            rsi_period=14, rsi_overbought=70, rsi_oversold=30,
            macd_fast=12, macd_slow=26, macd_signal=9,
            stc_fast=23, stc_slow=50, stc_cycle=10,
        ),
        scheduler=SchedulerConfig(
            enabled=False,
            cron="0 18 * * 1-5",
            symbols_file=Path("./watchlist.txt"),
        ),
        source_path=source_path or Path("./config.yaml"),
    )


# ── construction ──────────────────────────────────────────────────────────────

def test_dialog_constructs(qapp):
    from ui.settings_dialog import SettingsDialog
    dlg = SettingsDialog(_make_config())
    assert dlg is not None


def test_dialog_has_six_tabs(qapp):
    from ui.settings_dialog import SettingsDialog
    dlg = SettingsDialog(_make_config())
    assert dlg._tabs.count() == 6


def test_dialog_tabs_names(qapp):
    from ui.settings_dialog import SettingsDialog
    dlg = SettingsDialog(_make_config())
    tab_names = [dlg._tabs.tabText(i) for i in range(dlg._tabs.count())]
    assert "Data" in tab_names
    assert "Download" in tab_names
    assert "Chart" in tab_names
    assert "Indicators" in tab_names
    assert "News" in tab_names
    assert "Scheduler" in tab_names


# ── initial values ────────────────────────────────────────────────────────────

def test_initial_rsi_period(qapp):
    from ui.settings_dialog import SettingsDialog
    dlg = SettingsDialog(_make_config())
    assert dlg._rsi_period.value() == 14


def test_initial_chart_bull_color(qapp):
    from ui.settings_dialog import SettingsDialog
    dlg = SettingsDialog(_make_config())
    assert dlg._chart_bull.text() == "#26a69a"


def test_initial_news_max_headlines(qapp):
    from ui.settings_dialog import SettingsDialog
    dlg = SettingsDialog(_make_config())
    assert dlg._news_max.value() == 20


def test_initial_scheduler_disabled(qapp):
    from ui.settings_dialog import SettingsDialog
    dlg = SettingsDialog(_make_config())
    assert not dlg._sched_enabled.isChecked()


def test_initial_download_provider(qapp):
    from ui.settings_dialog import SettingsDialog
    dlg = SettingsDialog(_make_config())
    assert dlg._dl_provider.currentText() == "yfinance"


def test_initial_chart_resolution(qapp):
    from ui.settings_dialog import SettingsDialog
    dlg = SettingsDialog(_make_config())
    assert dlg._chart_res_w.value() == 800
    assert dlg._chart_res_h.value() == 600


# ── updated_config before accept ─────────────────────────────────────────────

def test_updated_config_is_none_before_accept(qapp):
    from ui.settings_dialog import SettingsDialog
    dlg = SettingsDialog(_make_config())
    assert dlg.updated_config is None


# ── accept produces new config ────────────────────────────────────────────────

def test_accept_produces_updated_config(qapp, tmp_path):
    from ui.settings_dialog import SettingsDialog

    cfg = _make_config(source_path=tmp_path / "config.yaml")
    dlg = SettingsDialog(cfg)

    # Change RSI period to 21
    dlg._rsi_period.setValue(21)

    with patch("core.config.save_config") as mock_save:
        mock_save.return_value = tmp_path / "config.yaml"
        dlg._on_accept()

    assert dlg.updated_config is not None
    assert dlg.updated_config.indicators.rsi_period == 21


def test_accept_saves_config_to_disk(qapp, tmp_path):
    from ui.settings_dialog import SettingsDialog

    cfg = _make_config(source_path=tmp_path / "config.yaml")
    dlg = SettingsDialog(cfg)

    with patch("core.config.save_config") as mock_save:
        mock_save.return_value = tmp_path / "config.yaml"
        dlg._on_accept()
        mock_save.assert_called_once()


def test_accept_preserves_unedited_fields(qapp, tmp_path):
    from ui.settings_dialog import SettingsDialog

    cfg = _make_config(source_path=tmp_path / "config.yaml")
    dlg = SettingsDialog(cfg)

    with patch("core.config.save_config"):
        dlg._on_accept()

    new = dlg.updated_config
    assert new is not None
    assert new.indicators.macd_fast == 12
    assert new.indicators.macd_slow == 26
    assert new.chart.candle_bear_color == "#ef5350"


def test_accept_updates_news_max(qapp, tmp_path):
    from ui.settings_dialog import SettingsDialog

    cfg = _make_config(source_path=tmp_path / "config.yaml")
    dlg = SettingsDialog(cfg)
    dlg._news_max.setValue(50)

    with patch("core.config.save_config"):
        dlg._on_accept()

    assert dlg.updated_config.news.max_headlines == 50


def test_accept_enables_scheduler(qapp, tmp_path):
    from ui.settings_dialog import SettingsDialog

    cfg = _make_config(source_path=tmp_path / "config.yaml")
    dlg = SettingsDialog(cfg)
    dlg._sched_enabled.setChecked(True)

    with patch("core.config.save_config"):
        dlg._on_accept()

    assert dlg.updated_config.scheduler.enabled is True


def test_accept_parses_ma_colors(qapp, tmp_path):
    from ui.settings_dialog import SettingsDialog

    cfg = _make_config(source_path=tmp_path / "config.yaml")
    dlg = SettingsDialog(cfg)
    dlg._chart_ma_colors.setText("#FF0000, #00FF00, #0000FF")

    with patch("core.config.save_config"):
        dlg._on_accept()

    assert dlg.updated_config.chart.ma_colors == ("#FF0000", "#00FF00", "#0000FF")


def test_accept_updates_export_resolution(qapp, tmp_path):
    from ui.settings_dialog import SettingsDialog

    cfg = _make_config(source_path=tmp_path / "config.yaml")
    dlg = SettingsDialog(cfg)
    dlg._chart_res_w.setValue(1920)
    dlg._chart_res_h.setValue(1080)

    with patch("core.config.save_config"):
        dlg._on_accept()

    assert dlg.updated_config.chart.export_resolution == (1920, 1080)
