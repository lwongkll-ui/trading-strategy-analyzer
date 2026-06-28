"""Settings dialog for StockTool.

A tabbed QDialog that exposes every editable field from :class:`~core.config.Config`.
Accepting the dialog writes the updated config to disk via :func:`~core.config.save_config`.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6 import QtCore, QtWidgets

if TYPE_CHECKING:
    from core.config import Config

logger = logging.getLogger(__name__)


class SettingsDialog(QtWidgets.QDialog):
    """Modal settings dialog.

    Args:
        config: The current application config.
        parent: Optional parent widget.

    After :meth:`exec` returns ``Accepted``, call :attr:`updated_config` to
    retrieve the new :class:`~core.config.Config` (already saved to disk).
    """

    def __init__(self, config: "Config", parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(480)
        self._config = config
        self._updated: "Config | None" = None

        outer = QtWidgets.QVBoxLayout(self)

        self._tabs = QtWidgets.QTabWidget()
        outer.addWidget(self._tabs)

        self._build_data_tab()
        self._build_download_tab()
        self._build_chart_tab()
        self._build_indicators_tab()
        self._build_news_tab()
        self._build_scheduler_tab()

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    # ── public ────────────────────────────────────────────────────────────────

    @property
    def updated_config(self) -> "Config | None":
        """The new config after the dialog was accepted, or ``None``."""
        return self._updated

    # ── tab builders ──────────────────────────────────────────────────────────

    def _build_data_tab(self) -> None:
        w, form = _tab_widget()
        self._data_price_dir = _path_edit(str(self._config.data.price_dir))
        self._data_export_dir = _path_edit(str(self._config.data.export_dir))
        form.addRow("Price directory:", self._data_price_dir)
        form.addRow("Export directory:", self._data_export_dir)
        self._tabs.addTab(w, "Data")

    def _build_download_tab(self) -> None:
        w, form = _tab_widget()
        self._dl_provider = QtWidgets.QComboBox()
        self._dl_provider.addItems(["yfinance", "alpha_vantage"])
        self._dl_provider.setCurrentText(self._config.download.provider)

        self._dl_av_key = QtWidgets.QLineEdit(self._config.download.alpha_vantage_key)
        self._dl_av_key.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)

        cfg_date = self._config.download.default_start_date
        self._dl_start = QtWidgets.QDateEdit(
            QtCore.QDate(cfg_date.year, cfg_date.month, cfg_date.day)
        )
        self._dl_start.setDisplayFormat("yyyy-MM-dd")
        self._dl_start.setCalendarPopup(True)

        form.addRow("Provider:", self._dl_provider)
        form.addRow("Alpha Vantage key:", self._dl_av_key)
        form.addRow("Default start date:", self._dl_start)
        self._tabs.addTab(w, "Download")

    def _build_chart_tab(self) -> None:
        w, form = _tab_widget()
        self._chart_timeframe = QtWidgets.QComboBox()
        self._chart_timeframe.addItems(["D", "W", "M", "Q", "Y"])
        self._chart_timeframe.setCurrentText(self._config.chart.default_timeframe)

        self._chart_bull = _color_edit(self._config.chart.candle_bull_color)
        self._chart_bear = _color_edit(self._config.chart.candle_bear_color)
        self._chart_bg = _color_edit(self._config.chart.background_color)
        self._chart_ma_colors = QtWidgets.QLineEdit(
            ", ".join(self._config.chart.ma_colors)
        )
        self._chart_ma_colors.setToolTip("Comma-separated hex colors, e.g. #2196F3, #FF9800")

        res_w, res_h = self._config.chart.export_resolution
        res_layout = QtWidgets.QHBoxLayout()
        self._chart_res_w = QtWidgets.QSpinBox()
        self._chart_res_w.setRange(100, 7680)
        self._chart_res_w.setValue(res_w)
        self._chart_res_h = QtWidgets.QSpinBox()
        self._chart_res_h.setRange(100, 4320)
        self._chart_res_h.setValue(res_h)
        res_layout.addWidget(self._chart_res_w)
        res_layout.addWidget(QtWidgets.QLabel("×"))
        res_layout.addWidget(self._chart_res_h)
        res_layout.addStretch()
        res_widget = QtWidgets.QWidget()
        res_widget.setLayout(res_layout)

        form.addRow("Default timeframe:", self._chart_timeframe)
        form.addRow("Bull candle color:", self._chart_bull)
        form.addRow("Bear candle color:", self._chart_bear)
        form.addRow("Background color:", self._chart_bg)
        form.addRow("MA colors:", self._chart_ma_colors)
        form.addRow("Export resolution:", res_widget)
        self._tabs.addTab(w, "Chart")

    def _build_indicators_tab(self) -> None:
        w, form = _tab_widget()
        ind = self._config.indicators

        self._rsi_period = _spinbox(1, 200, ind.rsi_period)
        self._rsi_overbought = _spinbox(50, 100, ind.rsi_overbought)
        self._rsi_oversold = _spinbox(0, 50, ind.rsi_oversold)
        self._macd_fast = _spinbox(1, 200, ind.macd_fast)
        self._macd_slow = _spinbox(1, 200, ind.macd_slow)
        self._macd_signal = _spinbox(1, 200, ind.macd_signal)
        self._stc_fast = _spinbox(1, 200, ind.stc_fast)
        self._stc_slow = _spinbox(1, 200, ind.stc_slow)
        self._stc_cycle = _spinbox(1, 200, ind.stc_cycle)

        form.addRow("RSI period:", self._rsi_period)
        form.addRow("RSI overbought:", self._rsi_overbought)
        form.addRow("RSI oversold:", self._rsi_oversold)
        form.addRow("MACD fast:", self._macd_fast)
        form.addRow("MACD slow:", self._macd_slow)
        form.addRow("MACD signal:", self._macd_signal)
        form.addRow("STC fast:", self._stc_fast)
        form.addRow("STC slow:", self._stc_slow)
        form.addRow("STC cycle:", self._stc_cycle)
        self._tabs.addTab(w, "Indicators")

    def _build_news_tab(self) -> None:
        w, form = _tab_widget()
        self._news_provider = QtWidgets.QComboBox()
        self._news_provider.addItems(["newsapi", "rss"])
        self._news_provider.setCurrentText(self._config.news.provider)

        self._news_api_key = QtWidgets.QLineEdit(self._config.news.newsapi_key)
        self._news_api_key.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)

        self._news_max = _spinbox(1, 200, self._config.news.max_headlines)

        form.addRow("Provider:", self._news_provider)
        form.addRow("NewsAPI key:", self._news_api_key)
        form.addRow("Max headlines:", self._news_max)
        self._tabs.addTab(w, "News")

    def _build_scheduler_tab(self) -> None:
        w, form = _tab_widget()
        self._sched_enabled = QtWidgets.QCheckBox("Enable scheduler")
        self._sched_enabled.setChecked(self._config.scheduler.enabled)
        self._sched_cron = QtWidgets.QLineEdit(self._config.scheduler.cron)
        self._sched_symbols = _path_edit(str(self._config.scheduler.symbols_file))

        form.addRow("", self._sched_enabled)
        form.addRow("Cron expression:", self._sched_cron)
        form.addRow("Symbols file:", self._sched_symbols)
        self._tabs.addTab(w, "Scheduler")

    # ── accept handler ────────────────────────────────────────────────────────

    def _on_accept(self) -> None:
        from core.config import (
            ChartConfig, DataConfig, DownloadConfig,
            IndicatorsConfig, NewsConfig, SchedulerConfig, save_config,
        )

        # Parse MA colors
        raw_colors = [c.strip() for c in self._chart_ma_colors.text().split(",") if c.strip()]
        if not raw_colors:
            raw_colors = list(self._config.chart.ma_colors)

        qd = self._dl_start.date()
        start_date = date(qd.year(), qd.month(), qd.day())

        try:
            new_config = replace(
                self._config,
                data=DataConfig(
                    price_dir=Path(self._data_price_dir.text().strip()),
                    export_dir=Path(self._data_export_dir.text().strip()),
                ),
                download=DownloadConfig(
                    default_start_date=start_date,
                    provider=self._dl_provider.currentText(),
                    alpha_vantage_key=self._dl_av_key.text().strip(),
                ),
                news=NewsConfig(
                    provider=self._news_provider.currentText(),
                    newsapi_key=self._news_api_key.text().strip(),
                    max_headlines=self._news_max.value(),
                ),
                chart=ChartConfig(
                    default_timeframe=self._chart_timeframe.currentText(),
                    candle_bull_color=self._chart_bull.text().strip(),
                    candle_bear_color=self._chart_bear.text().strip(),
                    background_color=self._chart_bg.text().strip(),
                    ma_colors=tuple(raw_colors),
                    export_resolution=(self._chart_res_w.value(), self._chart_res_h.value()),
                ),
                indicators=IndicatorsConfig(
                    rsi_period=self._rsi_period.value(),
                    rsi_overbought=self._rsi_overbought.value(),
                    rsi_oversold=self._rsi_oversold.value(),
                    macd_fast=self._macd_fast.value(),
                    macd_slow=self._macd_slow.value(),
                    macd_signal=self._macd_signal.value(),
                    stc_fast=self._stc_fast.value(),
                    stc_slow=self._stc_slow.value(),
                    stc_cycle=self._stc_cycle.value(),
                ),
                scheduler=SchedulerConfig(
                    enabled=self._sched_enabled.isChecked(),
                    cron=self._sched_cron.text().strip(),
                    symbols_file=Path(self._sched_symbols.text().strip()),
                ),
            )
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Settings Error", str(exc))
            return

        try:
            save_config(new_config)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Save Error", str(exc))
            return

        self._updated = new_config
        self.accept()


# ── helpers ───────────────────────────────────────────────────────────────────

def _tab_widget() -> tuple[QtWidgets.QWidget, QtWidgets.QFormLayout]:
    w = QtWidgets.QWidget()
    form = QtWidgets.QFormLayout(w)
    form.setContentsMargins(12, 12, 12, 12)
    form.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows)
    return w, form


def _path_edit(text: str) -> QtWidgets.QLineEdit:
    le = QtWidgets.QLineEdit(text)
    le.setMinimumWidth(260)
    return le


def _color_edit(text: str) -> QtWidgets.QLineEdit:
    le = QtWidgets.QLineEdit(text)
    le.setMaximumWidth(100)
    return le


def _spinbox(lo: int, hi: int, value: int) -> QtWidgets.QSpinBox:
    sb = QtWidgets.QSpinBox()
    sb.setRange(lo, hi)
    sb.setValue(value)
    return sb
