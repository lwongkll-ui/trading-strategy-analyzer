"""Indicator sub-chart panel — Volume, RSI, MACD, STC, ATR, Stochastic, OBV.

Each sub-chart occupies a resizable pane inside a ``QSplitter`` below the
main price chart. Up to :data:`MAX_SUBCHARTS` can be shown simultaneously
(per spec §7.4).

Sub-charts compute their own indicator values from the loaded OHLCV DataFrame
using :mod:`core.indicator_engine`, so callers only need to call
:meth:`IndicatorPanel.set_data`.

Each sub-chart has a small header bar with a title label and a ⚙ (gear)
button.  Subcharts that have adjustable parameters show the gear button;
clicking it opens a parameter-edit dialog that immediately re-renders.

Supported indicator types
--------------------------
* ``"volume"`` — volume bars coloured by candle direction
* ``"rsi"``    — RSI line with overbought/oversold bands and 50-line fill
* ``"macd"``   — MACD line, signal line, and direction-coloured histogram
* ``"stc"``    — STC oscillator with 25/75 threshold lines
* ``"atr"``    — Average True Range
* ``"stoch"``  — Stochastic %K/%D with 80/20 lines
* ``"obv"``    — On-Balance Volume cumulative line
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd
import pyqtgraph as pg
from PyQt6 import QtCore, QtWidgets

import core.indicator_engine as ie
from ui.chart_panel import DateAxis

if TYPE_CHECKING:
    from core.config import Config

logger = logging.getLogger(__name__)

MAX_SUBCHARTS = 4
VALID_INDICATORS = ("volume", "rsi", "macd", "stc", "atr", "stoch", "obv")

_BULL = "#26a69a"
_BEAR = "#ef5350"
_GRID_ALPHA = 0.15


class IndicatorPanelError(ValueError):
    """Raised for invalid IndicatorPanel operations."""


# ─────────────────────────── param dialog helper ─────────────────────────────

def _param_dialog(
    parent: QtWidgets.QWidget,
    title: str,
    fields: list[dict],
) -> dict | None:
    """Open a small form dialog for editing sub-chart parameters.

    Args:
        parent: Parent widget for the dialog.
        title:  Window title.
        fields: List of field dicts with keys ``label``, ``key``, ``value``,
            ``min``, ``max``, and optionally ``decimals`` (int, for floats).

    Returns:
        ``{key: value}`` on accept; ``None`` on cancel.
    """
    dlg = QtWidgets.QDialog(parent)
    dlg.setWindowTitle(title)
    form = QtWidgets.QFormLayout(dlg)
    form.setContentsMargins(12, 8, 12, 8)
    form.setSpacing(6)
    widgets: dict[str, QtWidgets.QAbstractSpinBox] = {}
    for f in fields:
        decimals = int(f.get("decimals", 0))
        if decimals > 0:
            w: QtWidgets.QAbstractSpinBox = QtWidgets.QDoubleSpinBox(dlg)
            w.setDecimals(decimals)  # type: ignore[attr-defined]
            w.setRange(float(f["min"]), float(f["max"]))  # type: ignore[attr-defined]
            w.setValue(float(f["value"]))  # type: ignore[attr-defined]
        else:
            w = QtWidgets.QSpinBox(dlg)
            w.setRange(int(f["min"]), int(f["max"]))  # type: ignore[attr-defined]
            w.setValue(int(f["value"]))  # type: ignore[attr-defined]
        form.addRow(f["label"] + ":", w)
        widgets[f["key"]] = w
    btns = QtWidgets.QDialogButtonBox(
        QtWidgets.QDialogButtonBox.StandardButton.Ok
        | QtWidgets.QDialogButtonBox.StandardButton.Cancel,
        parent=dlg,
    )
    btns.accepted.connect(dlg.accept)
    btns.rejected.connect(dlg.reject)
    form.addRow(btns)
    if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
        return None
    return {k: w.value() for k, w in widgets.items()}


# ─────────────────────────── base sub-chart ──────────────────────────────────

class SubChart(ABC):
    """Abstract base for a single indicator sub-chart.

    Each subclass owns a ``pg.PlotWidget`` wrapped in a lightweight container
    widget (accessible via :attr:`widget`) that includes a header bar with the
    indicator label and an optional ⚙ parameter button.
    """

    def __init__(self, config: "Config", label: str) -> None:
        self._config = config
        self._label = label
        self._df: pd.DataFrame | None = None

        # ── plot widget ──────────────────────────────────────────────────────
        self._date_axis = DateAxis(orientation="bottom")
        self._plot_widget = pg.PlotWidget(axisItems={"bottom": self._date_axis})
        self._plot_widget.setBackground(config.chart.background_color)
        self._plot_widget.showGrid(x=True, y=True, alpha=_GRID_ALPHA)
        self._plot_widget.setMaximumHeight(190)
        self._plot_widget.setMinimumHeight(50)
        self._plot_item = self._plot_widget.getPlotItem()
        self._plot_item.setLabel("left", label, color="#888888")
        self._items: list[pg.GraphicsObject] = []

        # Crosshair — vertical line that mirrors the main chart cursor position
        self._crosshair_v = pg.InfiniteLine(
            angle=90, movable=False,
            pen=pg.mkPen("#888888", width=1, style=QtCore.Qt.PenStyle.DashLine),
        )
        self._crosshair_v.hide()
        self._plot_item.addItem(self._crosshair_v, ignoreBounds=True)

        # ── container: header bar + plot ─────────────────────────────────────
        self._container = QtWidgets.QWidget()
        vbox = QtWidgets.QVBoxLayout(self._container)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        hdr = QtWidgets.QWidget()
        hdr.setFixedHeight(22)
        hdr.setStyleSheet("background: #1a1f2e;")
        hdr_layout = QtWidgets.QHBoxLayout(hdr)
        hdr_layout.setContentsMargins(6, 2, 4, 2)
        hdr_layout.setSpacing(4)

        title_lbl = QtWidgets.QLabel(label)
        title_lbl.setStyleSheet("color: #aaaaaa; font-size: 9pt; font-weight: bold;")
        hdr_layout.addWidget(title_lbl)
        hdr_layout.addStretch()

        self._gear_btn = QtWidgets.QPushButton("⚙")
        self._gear_btn.setFixedSize(18, 18)
        self._gear_btn.setFlat(True)
        self._gear_btn.setToolTip("Edit parameters")
        self._gear_btn.setStyleSheet(
            "QPushButton { color: #666666; border: none; font-size: 10pt; }"
            "QPushButton:hover { color: #aaaaaa; }"
        )
        self._gear_btn.clicked.connect(self._on_edit_params)
        hdr_layout.addWidget(self._gear_btn)

        vbox.addWidget(hdr)
        vbox.addWidget(self._plot_widget)

    @property
    def widget(self) -> QtWidgets.QWidget:
        """The container QWidget (header + plot) to insert into the splitter."""
        return self._container

    @property
    def indicator(self) -> str:
        return self._label

    def set_data(self, df: pd.DataFrame) -> None:
        """Load OHLCV data and redraw."""
        self._df = df
        self._date_axis.set_dates(df.index)
        self._clear_items()
        self._render(df)

    def clear(self) -> None:
        self._df = None
        self._date_axis.set_dates([])
        self._clear_items()

    def _clear_items(self) -> None:
        for item in self._items:
            self._plot_item.removeItem(item)
        self._items.clear()

    def _add(self, item: pg.GraphicsObject) -> None:
        self._plot_item.addItem(item)
        self._items.append(item)

    def _hline(self, y: float, color: str = "#666666", style: Any = QtCore.Qt.PenStyle.DashLine) -> None:
        line = pg.InfiniteLine(
            pos=y,
            angle=0,
            movable=False,
            pen=pg.mkPen(color=color, width=1, style=style),
        )
        self._add(line)

    def link_x_axis(self, source_vb: pg.ViewBox) -> None:
        """Link this subchart's X-axis to *source_vb* (main chart ViewBox).

        After linking, pan and zoom on the main chart automatically mirror
        here, and the Y-axis auto-scales to the visible indicator values.
        """
        vb = self._plot_item.getViewBox()
        vb.setXLink(source_vb)
        vb.setAutoVisible(y=True)

    def update_crosshair(self, x: float | None) -> None:
        """Show the vertical crosshair at bar index *x*, or hide it if None."""
        if x is None:
            self._crosshair_v.hide()
        else:
            self._crosshair_v.setPos(x)
            self._crosshair_v.show()

    def _on_edit_params(self) -> None:
        """Override in subclasses to open a parameter-edit dialog."""

    @abstractmethod
    def _render(self, df: pd.DataFrame) -> None: ...


# ─────────────────────────── concrete sub-charts ─────────────────────────────

class VolumeSubChart(SubChart):
    """Volume bars coloured green (bull) / red (bear) by candle direction."""

    def __init__(self, config: "Config") -> None:
        super().__init__(config, "Volume")
        self._gear_btn.hide()
        self._plot_widget.setYRange(0, 1)

    def link_x_axis(self, source_vb: pg.ViewBox) -> None:
        vb = self._plot_item.getViewBox()
        vb.setXLink(source_vb)
        vb.setAutoVisible(y=True)
        vb.setLimits(yMin=0)

    def _render(self, df: pd.DataFrame) -> None:
        x = np.arange(len(df), dtype=float)
        vol = df["Volume"].to_numpy(dtype=float)
        direction = (df["Close"] >= df["Open"]).to_numpy()

        bull_mask = direction
        bear_mask = ~direction

        if bull_mask.any():
            bull_bars = pg.BarGraphItem(
                x=x[bull_mask],
                height=vol[bull_mask],
                width=0.7,
                brush=pg.mkBrush(_BULL),
                pen=pg.mkPen(None),
            )
            self._add(bull_bars)

        if bear_mask.any():
            bear_bars = pg.BarGraphItem(
                x=x[bear_mask],
                height=vol[bear_mask],
                width=0.7,
                brush=pg.mkBrush(_BEAR),
                pen=pg.mkPen(None),
            )
            self._add(bear_bars)

        self._plot_widget.setYRange(0, vol.max() * 1.1)


class RsiSubChart(SubChart):
    """RSI oscillator with overbought/oversold bands and fill toward 50."""

    def __init__(
        self,
        config: "Config",
        period: int | None = None,
        overbought: int | None = None,
        oversold: int | None = None,
    ) -> None:
        super().__init__(config, "RSI")
        self._period = period if period is not None else config.indicators.rsi_period
        self._overbought = overbought if overbought is not None else config.indicators.rsi_overbought
        self._oversold = oversold if oversold is not None else config.indicators.rsi_oversold
        self._plot_widget.setYRange(0, 100)

    def _on_edit_params(self) -> None:
        result = _param_dialog(
            self._container, "RSI Parameters",
            [
                {"label": "Period",     "key": "period",     "value": self._period,     "min": 2,  "max": 200},
                {"label": "Overbought", "key": "overbought", "value": self._overbought, "min": 50, "max": 99},
                {"label": "Oversold",   "key": "oversold",   "value": self._oversold,   "min": 1,  "max": 50},
            ],
        )
        if result:
            self._period = result["period"]
            self._overbought = result["overbought"]
            self._oversold = result["oversold"]
            if self._df is not None:
                self._clear_items()
                self._render(self._df)

    def _render(self, df: pd.DataFrame) -> None:
        x = np.arange(len(df), dtype=float)
        values = ie.rsi(df["Close"], self._period).to_numpy(dtype=float)

        self._hline(self._overbought, color=_BEAR)
        self._hline(50, color="#555555", style=QtCore.Qt.PenStyle.SolidLine)
        self._hline(self._oversold, color=_BULL)

        rsi_curve = pg.PlotDataItem(
            x=x,
            y=values,
            pen=pg.mkPen("#eeeeee", width=1.5),
            connect="finite",
        )
        self._add(rsi_curve)

        fill_mid = pg.PlotDataItem(
            x=x,
            y=np.full(len(x), 50.0),
            pen=pg.mkPen(None),
        )
        fill = pg.FillBetweenItem(
            rsi_curve,
            fill_mid,
            brush=pg.mkBrush(color=(255, 255, 255, 25)),
        )
        self._add(fill_mid)
        self._add(fill)

        self._plot_widget.setYRange(0, 100)


class MacdSubChart(SubChart):
    """MACD line, signal line, and direction-coloured histogram."""

    def __init__(
        self,
        config: "Config",
        fast: int | None = None,
        slow: int | None = None,
        signal: int | None = None,
    ) -> None:
        super().__init__(config, "MACD")
        self._fast = fast if fast is not None else config.indicators.macd_fast
        self._slow = slow if slow is not None else config.indicators.macd_slow
        self._signal = signal if signal is not None else config.indicators.macd_signal

    def _on_edit_params(self) -> None:
        result = _param_dialog(
            self._container, "MACD Parameters",
            [
                {"label": "Fast Period",   "key": "fast",   "value": self._fast,   "min": 2,  "max": 100},
                {"label": "Slow Period",   "key": "slow",   "value": self._slow,   "min": 5,  "max": 200},
                {"label": "Signal Period", "key": "signal", "value": self._signal, "min": 2,  "max": 50},
            ],
        )
        if result and result["fast"] < result["slow"]:
            self._fast = result["fast"]
            self._slow = result["slow"]
            self._signal = result["signal"]
            if self._df is not None:
                self._clear_items()
                self._render(self._df)

    def _render(self, df: pd.DataFrame) -> None:
        x = np.arange(len(df), dtype=float)
        result = ie.macd(df["Close"], self._fast, self._slow, self._signal)

        macd_vals = result["MACD"].to_numpy(dtype=float)
        sig_vals = result["Signal"].to_numpy(dtype=float)
        hist_vals = result["Histogram"].to_numpy(dtype=float)

        self._hline(0.0, color="#555555", style=QtCore.Qt.PenStyle.SolidLine)

        bull_hist = np.where(hist_vals >= 0, hist_vals, np.nan)
        bear_hist = np.where(hist_vals < 0, hist_vals, np.nan)

        if not np.all(np.isnan(bull_hist)):
            valid = ~np.isnan(bull_hist)
            self._add(pg.BarGraphItem(
                x=x[valid], height=bull_hist[valid], width=0.7,
                brush=pg.mkBrush(_BULL), pen=pg.mkPen(None),
            ))

        if not np.all(np.isnan(bear_hist)):
            valid = ~np.isnan(bear_hist)
            self._add(pg.BarGraphItem(
                x=x[valid], height=bear_hist[valid], width=0.7,
                brush=pg.mkBrush(_BEAR), pen=pg.mkPen(None),
            ))

        self._add(pg.PlotDataItem(x=x, y=macd_vals,
                                   pen=pg.mkPen("#2196F3", width=1.5), connect="finite"))
        self._add(pg.PlotDataItem(x=x, y=sig_vals,
                                   pen=pg.mkPen("#FF9800", width=1.5), connect="finite"))


class StcSubChart(SubChart):
    """Schaff Trend Cycle with 25 / 75 threshold lines."""

    def __init__(
        self,
        config: "Config",
        fast: int | None = None,
        slow: int | None = None,
        cycle: int | None = None,
        factor: float = 0.5,
    ) -> None:
        super().__init__(config, "STC")
        self._fast = fast if fast is not None else config.indicators.stc_fast
        self._slow = slow if slow is not None else config.indicators.stc_slow
        self._cycle = cycle if cycle is not None else config.indicators.stc_cycle
        self._factor = factor
        self._plot_widget.setYRange(0, 100)

    def _on_edit_params(self) -> None:
        result = _param_dialog(
            self._container, "STC Parameters",
            [
                {"label": "Fast Period",  "key": "fast",   "value": self._fast,   "min": 2,   "max": 100},
                {"label": "Slow Period",  "key": "slow",   "value": self._slow,   "min": 5,   "max": 200},
                {"label": "Cycle Period", "key": "cycle",  "value": self._cycle,  "min": 2,   "max": 50},
                {"label": "Factor",       "key": "factor", "value": self._factor, "min": 0.1, "max": 1.0, "decimals": 2},
            ],
        )
        if result and result["fast"] < result["slow"]:
            self._fast = result["fast"]
            self._slow = result["slow"]
            self._cycle = result["cycle"]
            self._factor = result["factor"]
            if self._df is not None:
                self._clear_items()
                self._render(self._df)

    def _render(self, df: pd.DataFrame) -> None:
        x = np.arange(len(df), dtype=float)
        values = ie.stc(df["Close"], self._fast, self._slow, self._cycle, self._factor)
        values = values.to_numpy(dtype=float)

        self._hline(75, color=_BEAR)
        self._hline(25, color=_BULL)

        self._add(pg.PlotDataItem(
            x=x, y=values,
            pen=pg.mkPen("#9C27B0", width=1.5),
            connect="finite",
        ))
        self._plot_widget.setYRange(0, 100)


class AtrSubChart(SubChart):
    """Average True Range oscillator."""

    def __init__(self, config: "Config", period: int | None = None) -> None:
        super().__init__(config, "ATR")
        self._period = period if period is not None else config.indicators.atr_period

    def _on_edit_params(self) -> None:
        result = _param_dialog(
            self._container, "ATR Parameters",
            [{"label": "Period", "key": "period", "value": self._period, "min": 1, "max": 200}],
        )
        if result:
            self._period = result["period"]
            if self._df is not None:
                self._clear_items()
                self._render(self._df)

    def _render(self, df: pd.DataFrame) -> None:
        x = np.arange(len(df), dtype=float)
        values = ie.atr(df["High"], df["Low"], df["Close"], self._period).to_numpy(dtype=float)
        self._add(pg.PlotDataItem(
            x=x, y=values,
            pen=pg.mkPen("#FF9800", width=1.5),
            connect="finite",
        ))


class StochSubChart(SubChart):
    """Stochastic Oscillator (%K and %D) with 80/20 overbought/oversold lines."""

    def __init__(
        self,
        config: "Config",
        k_period: int | None = None,
        d_period: int | None = None,
    ) -> None:
        super().__init__(config, "Stoch")
        self._k = k_period if k_period is not None else config.indicators.stoch_k
        self._d = d_period if d_period is not None else config.indicators.stoch_d
        self._plot_widget.setYRange(0, 100)

    def _on_edit_params(self) -> None:
        result = _param_dialog(
            self._container, "Stochastic Parameters",
            [
                {"label": "%K Period", "key": "k", "value": self._k, "min": 2, "max": 200},
                {"label": "%D Period", "key": "d", "value": self._d, "min": 1, "max": 50},
            ],
        )
        if result:
            self._k = result["k"]
            self._d = result["d"]
            if self._df is not None:
                self._clear_items()
                self._render(self._df)

    def _render(self, df: pd.DataFrame) -> None:
        x = np.arange(len(df), dtype=float)
        result = ie.stoch(df["High"], df["Low"], df["Close"], self._k, self._d)

        self._hline(80, color=_BEAR)
        self._hline(20, color=_BULL)

        self._add(pg.PlotDataItem(
            x=x, y=result["STOCH_K"].to_numpy(dtype=float),
            pen=pg.mkPen("#2196F3", width=1.5), connect="finite",
        ))
        self._add(pg.PlotDataItem(
            x=x, y=result["STOCH_D"].to_numpy(dtype=float),
            pen=pg.mkPen("#FF9800", width=1.5), connect="finite",
        ))
        self._plot_widget.setYRange(0, 100)


class ObvSubChart(SubChart):
    """On-Balance Volume cumulative line."""

    def __init__(self, config: "Config") -> None:
        super().__init__(config, "OBV")
        self._gear_btn.hide()

    def _render(self, df: pd.DataFrame) -> None:
        x = np.arange(len(df), dtype=float)
        values = ie.obv(df["Close"], df["Volume"]).to_numpy(dtype=float)
        self._add(pg.PlotDataItem(
            x=x, y=values,
            pen=pg.mkPen("#9C27B0", width=1.5),
            connect="finite",
        ))


# ─────────────────────────── factory ─────────────────────────────────────────

def _make_subchart(indicator: str, config: "Config", **kwargs: Any) -> SubChart:
    match indicator:
        case "volume":
            return VolumeSubChart(config)
        case "rsi":
            return RsiSubChart(config, **kwargs)
        case "macd":
            return MacdSubChart(config, **kwargs)
        case "stc":
            return StcSubChart(config, **kwargs)
        case "atr":
            return AtrSubChart(config, **kwargs)
        case "stoch":
            return StochSubChart(config, **kwargs)
        case "obv":
            return ObvSubChart(config)
        case _:
            raise IndicatorPanelError(
                f"Unknown indicator {indicator!r}; expected one of {VALID_INDICATORS}"
            )


# ─────────────────────────── panel ───────────────────────────────────────────

class IndicatorPanel(QtWidgets.QWidget):
    """Resizable stack of indicator sub-charts below the price chart.

    Each sub-chart is inserted into a vertical ``QSplitter`` so the user can
    drag the dividers to resize individual panes.

    Args:
        config: Loaded application config — sub-charts read default indicator
            periods from ``config.indicators``.

    Usage::

        panel = IndicatorPanel(config)
        panel.add_subchart("volume")
        panel.add_subchart("rsi")
        panel.set_data(df)       # triggers all sub-charts to render
    """

    def __init__(self, config: "Config", parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._df: pd.DataFrame | None = None
        self._charts: dict[str, SubChart] = {}
        self._order: list[str] = []
        self._source_vb: pg.ViewBox | None = None

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        layout.addWidget(self._splitter)

    # ── linking ───────────────────────────────────────────────────────────────

    def link_to_chart(self, chart_panel) -> None:
        """Sync all subcharts' X-axis and crosshair to *chart_panel*.

        Call once after both this panel and the chart panel are constructed.
        Subcharts added later via :meth:`add_subchart` are linked automatically.
        """
        self._source_vb = chart_panel._view_box
        for chart in self._charts.values():
            chart.link_x_axis(self._source_vb)
        chart_panel.sigCrosshairMoved.connect(self._on_crosshair_moved)

    def _on_crosshair_moved(self, x: float | None) -> None:
        for chart in self._charts.values():
            chart.update_crosshair(x)

    # ── data ──────────────────────────────────────────────────────────────────

    def set_data(self, df: pd.DataFrame) -> None:
        """Pass a new OHLCV DataFrame to all active sub-charts."""
        self._df = df
        for chart in self._charts.values():
            chart.set_data(df)

    def clear(self) -> None:
        """Clear all sub-charts and remove them from the panel."""
        for key in list(self._order):
            self.remove_subchart(key)

    # ── sub-chart lifecycle ───────────────────────────────────────────────────

    def add_subchart(self, indicator: str, **kwargs: Any) -> None:
        """Add an indicator sub-chart.

        Args:
            indicator: One of :data:`VALID_INDICATORS`.
            **kwargs:  Forwarded to the sub-chart constructor (e.g. ``period=7``
                for RSI, ``fast=5`` / ``slow=35`` for MACD).

        Raises:
            IndicatorPanelError: Unknown indicator, cap exceeded, or duplicate.
        """
        if indicator not in VALID_INDICATORS:
            raise IndicatorPanelError(
                f"Unknown indicator {indicator!r}; expected one of {VALID_INDICATORS}"
            )
        if len(self._charts) >= MAX_SUBCHARTS:
            raise IndicatorPanelError(
                f"At most {MAX_SUBCHARTS} sub-charts allowed (per spec §7.4)"
            )
        if indicator in self._charts:
            raise IndicatorPanelError(f"Sub-chart {indicator!r} is already active")

        chart = _make_subchart(indicator, self._config, **kwargs)
        self._charts[indicator] = chart
        self._order.append(indicator)
        self._splitter.addWidget(chart.widget)

        if self._source_vb is not None:
            chart.link_x_axis(self._source_vb)
        if self._df is not None:
            chart.set_data(self._df)

    def remove_subchart(self, indicator: str) -> None:
        """Remove and destroy a sub-chart by indicator name."""
        chart = self._charts.pop(indicator, None)
        if chart is None:
            return
        self._order.remove(indicator)
        widget = chart.widget
        self._splitter.widget(self._splitter.indexOf(widget)).setParent(None)  # type: ignore[arg-type]
        chart.clear()

    def active_indicators(self) -> list[str]:
        """Return indicator names in display order."""
        return list(self._order)

    @property
    def subchart_count(self) -> int:
        return len(self._charts)
