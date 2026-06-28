"""Drawing tool overlay engine for ChartPanel.

Manages five drawing tool types:

* **Horizontal level**    — single click places a draggable price line.
* **Trend line**          — two clicks create a two-point line segment.
* **Fibonacci retracement** — two clicks (high + low) draw 7 standard levels.
* **Rectangle**           — two clicks draw a resizable price/time box.
* **Text annotation**     — single click prompts for text, then places a label.

:class:`DrawingManager` attaches to a :class:`~ui.chart_panel.ChartPanel` by
connecting to its internal ``pyqtgraph`` scene.  All drawings are stored as
plain dicts and persisted via :class:`~storage.db_store.DbStore`.

Drawings are keyed by *date* (``YYYY-MM-DD``) rather than bar index, so they
survive data refreshes and timeframe resampling.
"""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import pandas as pd
import pyqtgraph as pg
from PyQt6 import QtCore, QtWidgets

if TYPE_CHECKING:
    from storage.db_store import DbStore
    from ui.chart_panel import ChartPanel

logger = logging.getLogger(__name__)

_DEFAULT_COLOR = "#FFD700"
_DEFAULT_LINE_WIDTH = 1

_FIB_LEVELS = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
_FIB_COLORS = ["#26a69a", "#2196F3", "#FF9800", "#FFD700", "#FF9800", "#2196F3", "#26a69a"]


class DrawingMode(enum.Enum):
    NONE = "none"
    HORIZONTAL = "horizontal"
    TREND_LINE = "trend_line"
    FIB = "fib"
    RECT = "rect"
    TEXT = "text"


@dataclass
class _DrawingRecord:
    """In-memory representation of one placed drawing."""
    drawing_type: str
    params: dict[str, Any]
    item: Any          # pg.GraphicsObject or list[pg.GraphicsObject]
    db_id: int | None = None
    pending_point: dict | None = field(default=None, repr=False)


def _color(params: dict, key: str = "color") -> str:
    return params.get(key, _DEFAULT_COLOR)


class DrawingManager:
    """Attaches drawing tool logic to an existing :class:`~ui.chart_panel.ChartPanel`.

    Args:
        chart:    The chart panel whose scene this manager intercepts.
        db:       An open :class:`~storage.db_store.DbStore` for persistence.
        parent:   Optional parent QObject for Qt ownership (usually the window).
    """

    def __init__(
        self,
        chart: "ChartPanel",
        db: "DbStore",
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        self._chart = chart
        self._db = db
        self._parent = parent
        self._mode = DrawingMode.NONE
        self._records: list[_DrawingRecord] = []
        self._pending: _DrawingRecord | None = None  # awaiting 2nd click

        self._chart._plot_item.scene().sigMouseClicked.connect(self._on_click)

    # ── public API ────────────────────────────────────────────────────────────

    @property
    def mode(self) -> DrawingMode:
        return self._mode

    def set_mode(self, mode: DrawingMode) -> None:
        """Switch the active drawing tool.  Cancels any in-progress two-click drawing."""
        if mode != self._mode and self._pending is not None:
            self._cancel_pending()
        self._mode = mode
        logger.debug("Drawing mode → %s", mode.value)

    def load(self, ticker: str, timeframe: str) -> int:
        """Restore saved drawings for *ticker*/*timeframe* from the database."""
        self.clear()
        rows = self._db.load_drawings(ticker, timeframe)
        df = self._chart.data
        restored = 0
        for row in rows:
            item = self._restore(row["drawing_type"], row["params"], df)
            if item is not None:
                rec = _DrawingRecord(
                    drawing_type=row["drawing_type"],
                    params=row["params"],
                    item=item,
                    db_id=row["id"],
                )
                self._records.append(rec)
                restored += 1
        logger.debug("Restored %d/%d drawings for %s/%s", restored, len(rows), ticker, timeframe)
        return restored

    def save(self, ticker: str, timeframe: str) -> None:
        """Persist all in-memory drawings (that have no db_id yet) to the database."""
        for rec in self._records:
            if rec.db_id is None:
                rec.db_id = self._db.save_drawing(
                    ticker, timeframe, rec.drawing_type, rec.params
                )

    def clear(self) -> None:
        """Remove all drawing items from the chart and reset state."""
        self._cancel_pending()
        for rec in self._records:
            self._remove_item(rec.item)
        self._records.clear()

    def delete_selected(self, ticker: str, timeframe: str) -> None:
        """Delete all drawings for *ticker*/*timeframe* from both chart and DB."""
        self.clear()
        self._db.delete_all_drawings(ticker, timeframe)

    @property
    def count(self) -> int:
        return len(self._records)

    # ── mouse handler ─────────────────────────────────────────────────────────

    def _on_click(self, event: Any) -> None:
        if self._mode is DrawingMode.NONE:
            return
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            return

        scene_pos = event.scenePos()
        vb = self._chart._view_box
        plot_rect = self._chart._plot_item.sceneBoundingRect()
        if not plot_rect.contains(scene_pos):
            return

        view_pt = vb.mapSceneToView(scene_pos)
        bar = int(round(view_pt.x()))
        price = float(view_pt.y())
        df = self._chart.data
        n = len(df) if df is not None else 0

        match self._mode:
            case DrawingMode.HORIZONTAL:
                self._place_horizontal(price)
                event.accept()

            case DrawingMode.TREND_LINE:
                if 0 <= bar < n and df is not None:
                    date_str = df.index[bar].strftime("%Y-%m-%d")
                    self._handle_trend_click(bar, price, date_str)
                    event.accept()

            case DrawingMode.FIB:
                if 0 <= bar < n and df is not None:
                    date_str = df.index[bar].strftime("%Y-%m-%d")
                    self._handle_fib_click(bar, price, date_str)
                    event.accept()

            case DrawingMode.RECT:
                if 0 <= bar < n and df is not None:
                    date_str = df.index[bar].strftime("%Y-%m-%d")
                    self._handle_rect_click(bar, price, date_str)
                    event.accept()

            case DrawingMode.TEXT:
                if 0 <= bar < n and df is not None:
                    date_str = df.index[bar].strftime("%Y-%m-%d")
                    self._place_text(bar, price, date_str)
                    event.accept()

    # ── placement helpers ─────────────────────────────────────────────────────

    def _place_horizontal(self, price: float, color: str = _DEFAULT_COLOR) -> _DrawingRecord:
        line = pg.InfiniteLine(
            pos=price,
            angle=0,
            movable=True,
            pen=pg.mkPen(color, width=_DEFAULT_LINE_WIDTH),
        )
        self._chart._plot_item.addItem(line)
        params = {"price": price, "color": color}
        rec = _DrawingRecord("horizontal", params, line)
        self._records.append(rec)
        return rec

    def _handle_trend_click(self, bar: int, price: float, date_str: str) -> None:
        if self._pending is None:
            params = {"date1": date_str, "price1": price,
                      "date2": date_str, "price2": price,
                      "color": _DEFAULT_COLOR}
            seg = pg.LineSegmentROI(
                positions=[(bar, price), (bar, price)],
                movable=True,
                pen=pg.mkPen(_DEFAULT_COLOR, width=_DEFAULT_LINE_WIDTH),
            )
            self._chart._plot_item.addItem(seg)
            self._pending = _DrawingRecord("trend_line", params, seg)
        else:
            rec = self._pending
            self._pending = None
            rec.params["date2"] = date_str
            rec.params["price2"] = price
            seg = rec.item
            start_bar = self._date_to_bar(rec.params["date1"], self._chart.data) \
                if self._chart.data is not None else bar
            seg.setPos(0, 0)
            seg.movePoint(0, (int(start_bar), rec.params["price1"]))
            seg.movePoint(1, (bar, price))
            self._records.append(rec)

    def _handle_fib_click(self, bar: int, price: float, date_str: str) -> None:
        if self._pending is None:
            # First click — store a temporary marker line
            params = {"date1": date_str, "price1": price,
                      "date2": date_str, "price2": price,
                      "color": _DEFAULT_COLOR}
            temp = pg.InfiniteLine(
                pos=price, angle=0, movable=False,
                pen=pg.mkPen(_DEFAULT_COLOR, width=1, style=QtCore.Qt.PenStyle.DashLine),
            )
            self._chart._plot_item.addItem(temp)
            self._pending = _DrawingRecord("fib", params, temp)
        else:
            rec = self._pending
            self._pending = None
            self._remove_item(rec.item)   # remove temp marker
            df = self._chart.data
            bar1 = self._date_to_bar(rec.params["date1"], df) if df is not None else bar
            self._place_fib(
                bar1, rec.params["price1"], rec.params["date1"],
                bar, price, date_str,
            )

    def _place_fib(
        self,
        bar1: int, price1: float, date1: str,
        bar2: int, price2: float, date2: str,
        color: str = _DEFAULT_COLOR,
    ) -> _DrawingRecord:
        high = max(price1, price2)
        low = min(price1, price2)
        rng = high - low if high != low else 1.0

        items: list[Any] = []
        for level, lvl_color in zip(_FIB_LEVELS, _FIB_COLORS):
            p = high - level * rng
            line = pg.InfiniteLine(
                pos=p, angle=0, movable=False,
                pen=pg.mkPen(lvl_color, width=1, style=QtCore.Qt.PenStyle.DashLine),
                label=f"{level * 100:.1f}%",
                labelOpts={"color": lvl_color, "position": 0.02},
            )
            self._chart._plot_item.addItem(line)
            items.append(line)

        params = {"date1": date1, "price1": price1, "date2": date2, "price2": price2, "color": color}
        rec = _DrawingRecord("fib", params, items)
        self._records.append(rec)
        return rec

    def _handle_rect_click(self, bar: int, price: float, date_str: str) -> None:
        if self._pending is None:
            params = {"date1": date_str, "price1": price,
                      "date2": date_str, "price2": price,
                      "color": _DEFAULT_COLOR}
            temp = pg.InfiniteLine(
                pos=price, angle=0, movable=False,
                pen=pg.mkPen(_DEFAULT_COLOR, width=1, style=QtCore.Qt.PenStyle.DashLine),
            )
            self._chart._plot_item.addItem(temp)
            self._pending = _DrawingRecord("rect", params, temp)
        else:
            rec = self._pending
            self._pending = None
            self._remove_item(rec.item)
            df = self._chart.data
            bar1 = self._date_to_bar(rec.params["date1"], df) if df is not None else bar
            self._place_rect(
                bar1, rec.params["price1"], rec.params["date1"],
                bar, price, date_str,
            )

    def _place_rect(
        self,
        bar1: int, price1: float, date1: str,
        bar2: int, price2: float, date2: str,
        color: str = _DEFAULT_COLOR,
    ) -> _DrawingRecord:
        x = min(bar1, bar2)
        y = min(price1, price2)
        w = max(abs(bar2 - bar1), 1)
        h = max(abs(price2 - price1), 0.01)
        rect = pg.RectROI(
            pos=[x, y], size=[w, h],
            movable=True, rotatable=False, resizable=True,
            pen=pg.mkPen(color, width=_DEFAULT_LINE_WIDTH),
        )
        self._chart._plot_item.addItem(rect)
        params = {"date1": date1, "price1": price1, "date2": date2, "price2": price2, "color": color}
        rec = _DrawingRecord("rect", params, rect)
        self._records.append(rec)
        return rec

    def _place_text(self, bar: int, price: float, date_str: str) -> _DrawingRecord | None:
        text, ok = QtWidgets.QInputDialog.getText(
            self._parent, "Text Annotation", "Label:"
        )
        if not ok or not text.strip():
            return None
        label = pg.TextItem(text=text.strip(), color=_DEFAULT_COLOR, anchor=(0, 1))
        label.setPos(bar, price)
        self._chart._plot_item.addItem(label)
        params = {"date": date_str, "price": price, "text": text.strip(), "color": _DEFAULT_COLOR}
        rec = _DrawingRecord("text", params, label)
        self._records.append(rec)
        return rec

    # ── restore from DB ───────────────────────────────────────────────────────

    def _restore(
        self, drawing_type: str, params: dict, df: pd.DataFrame | None
    ) -> object | None:
        match drawing_type:
            case "horizontal":
                line = pg.InfiniteLine(
                    pos=params["price"],
                    angle=0,
                    movable=True,
                    pen=pg.mkPen(_color(params), width=_DEFAULT_LINE_WIDTH),
                )
                self._chart._plot_item.addItem(line)
                return line

            case "trend_line":
                if df is None:
                    return None
                bar1 = self._date_to_bar(params["date1"], df)
                bar2 = self._date_to_bar(params["date2"], df)
                if bar1 is None or bar2 is None:
                    return None
                seg = pg.LineSegmentROI(
                    positions=[(bar1, params["price1"]), (bar2, params["price2"])],
                    movable=True,
                    pen=pg.mkPen(_color(params), width=_DEFAULT_LINE_WIDTH),
                )
                self._chart._plot_item.addItem(seg)
                return seg

            case "fib":
                p1 = params["price1"]
                p2 = params["price2"]
                high = max(p1, p2)
                low = min(p1, p2)
                rng = high - low if high != low else 1.0
                items: list[Any] = []
                for level, lvl_color in zip(_FIB_LEVELS, _FIB_COLORS):
                    p = high - level * rng
                    line = pg.InfiniteLine(
                        pos=p, angle=0, movable=False,
                        pen=pg.mkPen(lvl_color, width=1, style=QtCore.Qt.PenStyle.DashLine),
                        label=f"{level * 100:.1f}%",
                        labelOpts={"color": lvl_color, "position": 0.02},
                    )
                    self._chart._plot_item.addItem(line)
                    items.append(line)
                return items

            case "rect":
                if df is None:
                    return None
                bar1 = self._date_to_bar(params["date1"], df)
                bar2 = self._date_to_bar(params["date2"], df)
                if bar1 is None or bar2 is None:
                    return None
                x = min(bar1, bar2)
                y = min(params["price1"], params["price2"])
                w = max(abs(bar2 - bar1), 1)
                h = max(abs(params["price2"] - params["price1"]), 0.01)
                rect = pg.RectROI(
                    pos=[x, y], size=[w, h],
                    movable=True, rotatable=False, resizable=True,
                    pen=pg.mkPen(_color(params), width=_DEFAULT_LINE_WIDTH),
                )
                self._chart._plot_item.addItem(rect)
                return rect

            case "text":
                if df is None:
                    return None
                bar = self._date_to_bar(params["date"], df)
                if bar is None:
                    return None
                label = pg.TextItem(
                    text=params.get("text", ""),
                    color=_color(params),
                    anchor=(0, 1),
                )
                label.setPos(bar, params["price"])
                self._chart._plot_item.addItem(label)
                return label

            case _:
                logger.warning("Unknown drawing type %r — skipped", drawing_type)
                return None

    # ── internal helpers ──────────────────────────────────────────────────────

    def _cancel_pending(self) -> None:
        if self._pending is not None:
            self._remove_item(self._pending.item)
            self._pending = None

    def _remove_item(self, item: Any) -> None:
        items = item if isinstance(item, list) else [item]
        for i in items:
            try:
                self._chart._plot_item.removeItem(i)  # type: ignore[arg-type]
            except Exception:  # noqa: BLE001
                pass

    @staticmethod
    def _date_to_bar(date_str: str, df: pd.DataFrame) -> int | None:
        ts = pd.Timestamp(date_str)
        if ts in df.index:
            return int(df.index.get_loc(ts))
        pos = df.index.searchsorted(ts)
        if pos < len(df):
            return int(pos)
        return None
