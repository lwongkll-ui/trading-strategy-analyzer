"""Price chart widget — candle / line display with MA overlays and PNG export.

Built on ``pyqtgraph.PlotWidget``. The x-axis uses bar indices (``0..N-1``)
rather than timestamps so weekends and holidays do not create gaps; a custom
:class:`DateAxis` maps tick positions back to ``YYYY-MM-DD`` labels.

Drawing tools and indicator sub-charts live in separate modules.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
import pyqtgraph as pg
from PyQt6 import QtCore, QtGui, QtWidgets

if TYPE_CHECKING:
    from core.config import Config

logger = logging.getLogger(__name__)

MAX_MA_OVERLAYS = 5
VALID_MODES = ("candle", "line")
_REQUIRED_COLUMNS = ("Open", "High", "Low", "Close", "Volume")


class ChartPanelError(ValueError):
    """Raised when ChartPanel is given invalid input."""


class DateAxis(pg.AxisItem):
    """Axis that translates bar indices into ``YYYY-MM-DD`` tick labels."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._dates: list[pd.Timestamp] = []

    def set_dates(self, dates) -> None:
        self._dates = [pd.Timestamp(d) for d in dates]
        self.picture = None
        self.update()

    def tickStrings(self, values, scale, spacing):  # noqa: N802 (pyqtgraph API)
        n = len(self._dates)
        labels: list[str] = []
        for v in values:
            i = int(round(v))
            if 0 <= i < n:
                labels.append(self._dates[i].strftime("%Y-%m-%d"))
            else:
                labels.append("")
        return labels


class CandlestickItem(pg.GraphicsObject):
    """Custom OHLC candlestick drawn from a pre-baked ``QPicture``.

    The picture is regenerated whenever the data or colours change, so paint
    is O(1) regardless of bar count.
    """

    def __init__(
        self,
        ohlc: np.ndarray,
        bull_color: str = "#26a69a",
        bear_color: str = "#ef5350",
        width: float = 0.7,
    ) -> None:
        super().__init__()
        self._ohlc = np.asarray(ohlc, dtype=float)
        self._bull = bull_color
        self._bear = bear_color
        self._width = float(width)
        self._picture = QtGui.QPicture()
        self._generate_picture()

    def _generate_picture(self) -> None:
        self._picture = QtGui.QPicture()
        if len(self._ohlc) == 0:
            return

        painter = QtGui.QPainter(self._picture)
        try:
            half = self._width / 2.0
            bull = QtGui.QColor(self._bull)
            bear = QtGui.QColor(self._bear)
            for x, o, h, l, c in self._ohlc:
                color = bull if c >= o else bear
                pen = QtGui.QPen(color)
                pen.setWidth(0)
                painter.setPen(pen)
                painter.setBrush(QtGui.QBrush(color))

                if h == l:
                    # Zero-range bar (O=H=L=C): draw a horizontal dash at the
                    # price level.  A degenerate drawLine(p, p) produces
                    # undefined Qt behaviour — some versions render a full-height
                    # stroke — so we handle this case explicitly.
                    tick = half * 0.8
                    painter.drawLine(
                        QtCore.QPointF(x - tick, c),
                        QtCore.QPointF(x + tick, c),
                    )
                    continue

                painter.drawLine(QtCore.QPointF(x, l), QtCore.QPointF(x, h))
                top = max(o, c)
                bot = min(o, c)
                body_h = top - bot if top != bot else self._width * 0.05
                painter.drawRect(QtCore.QRectF(x - half, bot, self._width, body_h))
        finally:
            painter.end()

    def paint(self, painter, option, widget=None) -> None:  # noqa: ARG002 (pyqtgraph API)
        painter.drawPicture(0, 0, self._picture)

    def boundingRect(self) -> QtCore.QRectF:  # noqa: N802 (pyqtgraph API)
        return QtCore.QRectF(self._picture.boundingRect())


_BBAND_STYLES = [
    ("BB_Upper", QtCore.Qt.PenStyle.DashLine),
    ("BB_Mid",   QtCore.Qt.PenStyle.SolidLine),
    ("BB_Lower", QtCore.Qt.PenStyle.DashLine),
]


class ChartPanel(QtWidgets.QWidget):
    """Main price chart: candle / line + MA overlays + crosshair tooltip.

    Public API:
        - :meth:`set_data` — load an OHLCV DataFrame
        - :meth:`set_mode` — switch between ``"candle"`` and ``"line"``
        - :meth:`add_ma_overlay` / :meth:`remove_ma_overlay` / :meth:`clear_overlays`
        - :meth:`add_bband_overlay` / :meth:`remove_bband_overlay`
        - :meth:`clear` — drop all data and overlays

    The widget pulls colours and the default mode from ``config.chart``.
    Indicator computation happens elsewhere (``core.indicator_engine``); this
    panel only renders pre-computed series.
    """

    # Emits the bar index (float) when the mouse is over the chart, or None
    # when it leaves. Indicator subcharts connect this to sync their crosshair.
    sigCrosshairMoved = QtCore.pyqtSignal(object)

    def __init__(self, config: "Config", parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._df: pd.DataFrame | None = None
        self._mode: str = "candle"
        self._candle_item: CandlestickItem | None = None
        self._line_item: pg.PlotDataItem | None = None
        self._overlays: dict[str, pg.PlotDataItem] = {}
        self._bband_items: dict[str, pg.PlotDataItem] = {}
        self._vwap_item: pg.PlotDataItem | None = None
        self._fvg_items: list[QtWidgets.QGraphicsRectItem] = []
        self._ai_signal_items: list[pg.InfiniteLine] = []
        self._color_cursor: int = 0

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._date_axis = DateAxis(orientation="bottom")
        self._plot_widget = pg.PlotWidget(axisItems={"bottom": self._date_axis})
        self._plot_widget.setBackground(config.chart.background_color)
        self._plot_widget.showGrid(x=True, y=True, alpha=0.2)
        self._plot_widget.setMouseEnabled(x=True, y=True)
        layout.addWidget(self._plot_widget)

        self._plot_item = self._plot_widget.getPlotItem()
        self._view_box = self._plot_item.getViewBox()

        self._crosshair_v = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen("#888888", width=1))
        self._crosshair_h = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen("#888888", width=1))
        self._crosshair_v.hide()
        self._crosshair_h.hide()
        self._plot_item.addItem(self._crosshair_v, ignoreBounds=True)
        self._plot_item.addItem(self._crosshair_h, ignoreBounds=True)

        self._tooltip = pg.TextItem(color="#dddddd", anchor=(0, 1))
        self._tooltip.setZValue(100)
        self._tooltip.hide()
        self._plot_item.addItem(self._tooltip, ignoreBounds=True)

        self._plot_item.scene().sigMouseMoved.connect(self._on_mouse_moved)
        self._view_box.sigXRangeChanged.connect(self._fit_y_to_visible)

    # ------------------------------------------------------------------ data

    def set_data(self, df: pd.DataFrame) -> None:
        """Load a new OHLCV DataFrame and redraw in the current mode."""
        self._validate_df(df)
        self._df = df.copy()
        self._date_axis.set_dates(df.index)
        self._render()

    def clear(self) -> None:
        """Drop all data, overlays, and reset the view."""
        self._df = None
        self.clear_overlays()
        self.remove_bband_overlay()
        self.remove_vwap_overlay()
        if self._candle_item is not None:
            self._plot_item.removeItem(self._candle_item)
            self._candle_item = None
        if self._line_item is not None:
            self._plot_item.removeItem(self._line_item)
            self._line_item = None
        self._date_axis.set_dates([])
        self._tooltip.hide()
        self._crosshair_v.hide()
        self._crosshair_h.hide()

    @property
    def data(self) -> pd.DataFrame | None:
        return self._df

    # ------------------------------------------------------------------ mode

    def set_mode(self, mode: str) -> None:
        """Switch between ``"candle"`` and ``"line"`` display modes."""
        if mode not in VALID_MODES:
            raise ChartPanelError(
                f"Invalid mode {mode!r}; expected one of {VALID_MODES}"
            )
        if mode == self._mode:
            return
        self._mode = mode
        if self._df is not None:
            self._render()

    @property
    def mode(self) -> str:
        return self._mode

    # ---------------------------------------------------------------- overlay

    def add_ma_overlay(
        self,
        name: str,
        series: pd.Series,
        color: str | None = None,
    ) -> None:
        """Plot a moving-average series as an overlay on top of the price chart.

        Args:
            name: Unique key (e.g. ``"SMA_50"``); used to remove the overlay later.
            series: Pre-computed series indexed compatibly with the loaded data.
            color: Hex colour string. If ``None``, cycles through ``config.chart.ma_colors``.

        Raises:
            ChartPanelError: If ``set_data`` has not been called, the cap of
                :data:`MAX_MA_OVERLAYS` is exceeded, an overlay with the same
                name already exists, or the series is misaligned.
        """
        if self._df is None:
            raise ChartPanelError("Call set_data() before adding overlays")
        if name in self._overlays:
            raise ChartPanelError(f"Overlay {name!r} already exists")
        if len(self._overlays) >= MAX_MA_OVERLAYS:
            raise ChartPanelError(
                f"At most {MAX_MA_OVERLAYS} MA overlays allowed (per spec §7.3)"
            )
        if not isinstance(series, pd.Series):
            raise ChartPanelError("series must be a pandas Series")
        if len(series) != len(self._df):
            raise ChartPanelError(
                f"series length {len(series)} does not match data length {len(self._df)}"
            )

        chosen = color if color is not None else self._next_color()
        x = np.arange(len(self._df), dtype=float)
        y = series.to_numpy(dtype=float)
        item = pg.PlotDataItem(
            x=x,
            y=y,
            pen=pg.mkPen(chosen, width=2),
            name=name,
            connect="finite",
        )
        self._plot_item.addItem(item)
        self._overlays[name] = item

    def remove_ma_overlay(self, name: str) -> None:
        item = self._overlays.pop(name, None)
        if item is not None:
            self._plot_item.removeItem(item)

    def clear_overlays(self) -> None:
        for item in self._overlays.values():
            self._plot_item.removeItem(item)
        self._overlays.clear()
        self._color_cursor = 0

    def overlay_names(self) -> list[str]:
        return list(self._overlays.keys())

    # -------------------------------------------------------- bband overlay

    def add_bband_overlay(self, bb_df: pd.DataFrame) -> None:
        """Plot Bollinger Bands (Upper / Mid / Lower) on the price chart.

        Args:
            bb_df: DataFrame with columns ``BB_Upper``, ``BB_Mid``, ``BB_Lower``
                aligned with the loaded OHLCV data (same length).

        Raises:
            ChartPanelError: If set_data has not been called, bands are already
                shown, or the DataFrame is misaligned.
        """
        if self._df is None:
            raise ChartPanelError("Call set_data() before adding overlays")
        if self._bband_items:
            raise ChartPanelError("Bollinger Bands overlay already exists; call remove_bband_overlay() first")
        if len(bb_df) != len(self._df):
            raise ChartPanelError(
                f"bb_df length {len(bb_df)} does not match data length {len(self._df)}"
            )
        x = np.arange(len(self._df), dtype=float)
        for col, style in _BBAND_STYLES:
            item = pg.PlotDataItem(
                x=x,
                y=bb_df[col].to_numpy(dtype=float),
                pen=pg.mkPen("#2196F3", width=1, style=style),
                connect="finite",
            )
            self._plot_item.addItem(item)
            self._bband_items[col] = item

    def remove_bband_overlay(self) -> None:
        """Remove Bollinger Bands overlay if present."""
        for item in self._bband_items.values():
            self._plot_item.removeItem(item)
        self._bband_items.clear()

    def has_bband_overlay(self) -> bool:
        return bool(self._bband_items)

    # --------------------------------------------------------- vwap overlay

    def add_vwap_overlay(self, vwap_series: pd.Series) -> None:
        """Plot VWAP as a single cyan line on the price chart.

        Raises:
            ChartPanelError: If set_data has not been called, VWAP is already
                shown, or the series is misaligned.
        """
        if self._df is None:
            raise ChartPanelError("Call set_data() before adding overlays")
        if self._vwap_item is not None:
            raise ChartPanelError("VWAP overlay already exists; call remove_vwap_overlay() first")
        if len(vwap_series) != len(self._df):
            raise ChartPanelError(
                f"vwap_series length {len(vwap_series)} does not match data length {len(self._df)}"
            )
        x = np.arange(len(self._df), dtype=float)
        self._vwap_item = pg.PlotDataItem(
            x=x,
            y=vwap_series.to_numpy(dtype=float),
            pen=pg.mkPen("#00BCD4", width=1.5),
            connect="finite",
        )
        self._plot_item.addItem(self._vwap_item)

    def remove_vwap_overlay(self) -> None:
        """Remove VWAP overlay if present."""
        if self._vwap_item is not None:
            self._plot_item.removeItem(self._vwap_item)
            self._vwap_item = None

    def has_vwap_overlay(self) -> bool:
        return self._vwap_item is not None

    # ----------------------------------------------------------------- FVG

    def add_fvg_overlay(self, gaps: list[dict]) -> None:
        """Draw Fair Value Gap zones as semi-transparent rectangles.

        Each item in *gaps* is a dict produced by :func:`core.indicator_engine.fvg`:
        ``{'kind': 'bull'/'bear', 'bar': int, 'gap_low': float, 'gap_high': float}``.

        Clears any existing FVG overlay before drawing the new one so this
        method is safe to call repeatedly (e.g. on timeframe change).
        """
        self.remove_fvg_overlay()
        if self._df is None or not gaps:
            return

        n = len(self._df)
        for g in gaps:
            bar = g["bar"]
            x_start = bar - 2          # first candle of the 3-candle pattern
            x_end = n - 1              # extend to right edge of chart
            width = max(1, x_end - x_start)
            height = g["gap_high"] - g["gap_low"]
            if height <= 0:
                continue

            if g["kind"] == "bull":
                brush = pg.mkBrush(38, 166, 154, 45)   # teal, low opacity
                pen = pg.mkPen(38, 166, 154, 120, width=1)
            else:
                brush = pg.mkBrush(239, 83, 80, 45)    # red, low opacity
                pen = pg.mkPen(239, 83, 80, 120, width=1)

            rect = QtWidgets.QGraphicsRectItem(x_start, g["gap_low"], width, height)
            rect.setPen(pen)
            rect.setBrush(brush)
            self._plot_item.addItem(rect)
            self._fvg_items.append(rect)

    def remove_fvg_overlay(self) -> None:
        """Remove all FVG zone rectangles from the chart."""
        for item in self._fvg_items:
            self._plot_item.removeItem(item)
        self._fvg_items.clear()

    # ---------------------------------------------------------- AI markers

    def mark_ai_signals(self, bars: list[int], color: str = "#FF8C00") -> None:
        """Draw vertical marker lines at the given bar indices.

        Used by the AI tab's "Show on Chart" button to highlight where a
        particular candlestick pattern was detected in the OOS period.
        Replaces any previously drawn markers.
        """
        self.clear_ai_signals()
        pen = pg.mkPen(color, width=1.5, style=QtCore.Qt.PenStyle.DotLine)
        for bar in bars:
            line = pg.InfiniteLine(pos=bar, angle=90, pen=pen, movable=False)
            self._plot_item.addItem(line, ignoreBounds=True)
            self._ai_signal_items.append(line)

    def clear_ai_signals(self) -> None:
        """Remove all AI signal marker lines."""
        for item in self._ai_signal_items:
            self._plot_item.removeItem(item)
        self._ai_signal_items.clear()

    def has_ai_signals(self) -> bool:
        return bool(self._ai_signal_items)

    # --------------------------------------------------------------- internal

    def _validate_df(self, df: pd.DataFrame) -> None:
        if not isinstance(df, pd.DataFrame):
            raise ChartPanelError("df must be a pandas DataFrame")
        missing = [c for c in _REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            raise ChartPanelError(f"DataFrame is missing columns: {missing}")
        if not isinstance(df.index, pd.DatetimeIndex):
            raise ChartPanelError("DataFrame index must be a DatetimeIndex")
        if df.empty:
            raise ChartPanelError("DataFrame is empty")

    def _render(self) -> None:
        if self._df is None:
            return

        if self._candle_item is not None:
            self._plot_item.removeItem(self._candle_item)
            self._candle_item = None
        if self._line_item is not None:
            self._plot_item.removeItem(self._line_item)
            self._line_item = None

        x = np.arange(len(self._df), dtype=float)
        if self._mode == "candle":
            ohlc = np.column_stack(
                [
                    x,
                    self._df["Open"].to_numpy(dtype=float),
                    self._df["High"].to_numpy(dtype=float),
                    self._df["Low"].to_numpy(dtype=float),
                    self._df["Close"].to_numpy(dtype=float),
                ]
            )
            self._candle_item = CandlestickItem(
                ohlc,
                bull_color=self._config.chart.candle_bull_color,
                bear_color=self._config.chart.candle_bear_color,
            )
            self._plot_item.addItem(self._candle_item)
        else:
            close = self._df["Close"].to_numpy(dtype=float)
            self._line_item = pg.PlotDataItem(
                x=x,
                y=close,
                pen=pg.mkPen(self._config.chart.candle_bull_color, width=2),
                connect="finite",
            )
            self._plot_item.addItem(self._line_item)

        self._view_box.autoRange()

    def _next_color(self) -> str:
        palette = self._config.chart.ma_colors
        if not palette:
            return "#FFFFFF"
        color = palette[self._color_cursor % len(palette)]
        self._color_cursor += 1
        return color

    def _fit_y_to_visible(self, _vb=None, x_range: tuple | None = None) -> None:
        """Refit the Y-axis to the High/Low of bars currently visible on screen.

        Called automatically whenever the X range changes (pan or zoom).
        """
        if self._df is None:
            return
        if x_range is None:
            x_range = self._view_box.viewRange()[0]

        lo, hi = x_range
        n = len(self._df)
        i0 = max(0, int(np.floor(lo)))
        i1 = min(n - 1, int(np.ceil(hi)))
        if i0 > i1:
            return

        visible = self._df.iloc[i0 : i1 + 1]
        y_min = float(visible["Low"].min())
        y_max = float(visible["High"].max())
        if y_min >= y_max:
            return

        pad = (y_max - y_min) * 0.05
        self._view_box.setYRange(y_min - pad, y_max + pad, padding=0)

    def _on_mouse_moved(self, scene_pos) -> None:
        if self._df is None:
            return
        if not self._plot_item.sceneBoundingRect().contains(scene_pos):
            self._tooltip.hide()
            self._crosshair_v.hide()
            self._crosshair_h.hide()
            self.sigCrosshairMoved.emit(None)
            return

        view_pt = self._view_box.mapSceneToView(scene_pos)
        bar = int(round(view_pt.x()))
        n = len(self._df)
        if not (0 <= bar < n):
            self._tooltip.hide()
            self._crosshair_v.hide()
            self._crosshair_h.hide()
            self.sigCrosshairMoved.emit(None)
            return

        self._crosshair_v.setPos(bar)
        self._crosshair_h.setPos(view_pt.y())
        self._crosshair_v.show()
        self._crosshair_h.show()
        self.sigCrosshairMoved.emit(float(bar))

        row = self._df.iloc[bar]
        date_str = self._df.index[bar].strftime("%Y-%m-%d")
        text = (
            f"{date_str}\n"
            f"O {row['Open']:.2f}  H {row['High']:.2f}\n"
            f"L {row['Low']:.2f}  C {row['Close']:.2f}\n"
            f"V {int(row['Volume']):,}"
        )
        self._tooltip.setText(text)
        self._tooltip.setPos(view_pt.x(), view_pt.y())
        self._tooltip.show()

    # ----------------------------------------------------------------- export

    def export_png(self, path: "Path | str", resolution: tuple[int, int] | None = None) -> "Path":
        """Render the chart to a PNG file.

        Args:
            path: Destination file path.  Parent directory is created if needed.
            resolution: ``(width, height)`` in pixels.  Defaults to
                ``config.chart.export_resolution`` (1920 × 1080).

        Returns:
            The resolved path that was written.
        """
        from pathlib import Path as _Path
        from pyqtgraph.exporters import ImageExporter

        dest = _Path(path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        w, h = resolution if resolution is not None else self._config.chart.export_resolution
        exporter = ImageExporter(self._plot_item)
        exporter.parameters()["width"] = w
        exporter.parameters()["height"] = h
        exporter.export(str(dest))
        return dest
