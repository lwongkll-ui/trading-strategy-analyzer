"""Side-by-side chart comparison panel.

:class:`ComparePanel` is a QWidget that embeds its own symbol picker and
:class:`~ui.chart_panel.ChartPanel`.  It can optionally synchronise its
x-axis with the main chart so panning/zooming one chart mirrors the other.

Wire-up in ``MainWindow._build_central``::

    self._compare_panel = ComparePanel(config, data_manager, parent=self)
    self._compare_panel.sync_with(self._chart)
    # …add to a dock widget…
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import TYPE_CHECKING

from PyQt6 import QtCore, QtWidgets

from ui.chart_panel import ChartPanel

if TYPE_CHECKING:
    from core.config import Config
    from core.data_manager import DataManager

logger = logging.getLogger(__name__)


class ComparePanel(QtWidgets.QWidget):
    """A self-contained mini chart widget for comparing a second symbol.

    Args:
        config:       Application config (passed to the embedded ChartPanel).
        data_manager: Pre-built DataManager used to load the compare symbol.
        parent:       Optional Qt parent widget.
    """

    def __init__(
        self,
        config: "Config",
        data_manager: "DataManager",
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._dm = data_manager
        self._main_chart: ChartPanel | None = None
        self._lock_axes: bool = True
        self._syncing: bool = False

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # ── header row ────────────────────────────────────────────────────────
        header = QtWidgets.QHBoxLayout()
        header.setSpacing(6)

        self._symbol_edit = QtWidgets.QLineEdit()
        self._symbol_edit.setPlaceholderText("Compare symbol (e.g. MSFT, 0700.HK)…")
        self._symbol_edit.returnPressed.connect(self._on_load)
        header.addWidget(self._symbol_edit)

        self._load_btn = QtWidgets.QPushButton("Load")
        self._load_btn.setFixedWidth(56)
        self._load_btn.clicked.connect(self._on_load)
        header.addWidget(self._load_btn)

        self._lock_cb = QtWidgets.QCheckBox("Lock X-axis")
        self._lock_cb.setChecked(True)
        self._lock_cb.setToolTip("Synchronise x-axis pan/zoom with the main chart")
        self._lock_cb.toggled.connect(self._on_lock_toggled)
        header.addWidget(self._lock_cb)

        layout.addLayout(header)

        # ── embedded chart ────────────────────────────────────────────────────
        self._chart = ChartPanel(config, parent=self)
        layout.addWidget(self._chart)

        # ── status bar ────────────────────────────────────────────────────────
        self._status = QtWidgets.QLabel("Enter a symbol above and click Load")
        self._status.setStyleSheet("color: #888888; font-size: 9pt;")
        layout.addWidget(self._status)

    # ── x-axis sync ───────────────────────────────────────────────────────────

    def sync_with(self, main_chart: ChartPanel) -> None:
        """Attach to *main_chart* for bidirectional x-axis synchronisation."""
        self._main_chart = main_chart
        main_chart._view_box.sigXRangeChanged.connect(self._on_main_range_changed)
        self._chart._view_box.sigXRangeChanged.connect(self._on_compare_range_changed)

    def _on_main_range_changed(self, vb: object, x_range: tuple) -> None:
        if not self._lock_axes or self._syncing:
            return
        self._syncing = True
        try:
            self._chart._view_box.setXRange(*x_range, padding=0)
        finally:
            self._syncing = False

    def _on_compare_range_changed(self, vb: object, x_range: tuple) -> None:
        if not self._lock_axes or self._syncing or self._main_chart is None:
            return
        self._syncing = True
        try:
            self._main_chart._view_box.setXRange(*x_range, padding=0)
        finally:
            self._syncing = False

    def _on_lock_toggled(self, checked: bool) -> None:
        self._lock_axes = checked

    # ── data loading ──────────────────────────────────────────────────────────

    def _on_load(self) -> None:
        ticker = self._symbol_edit.text().strip().upper()
        if not ticker:
            return
        self._status.setText(f"Loading {ticker}…")
        try:
            end = date.today()
            start = end - timedelta(days=365 * 10)
            df = self._dm.get_history(ticker, start=start, end=end)
            self._chart.clear()
            self._chart.set_data(df)
            self._status.setText(
                f"{ticker}  |  {len(df)} bars  |  "
                f"{df.index[0].date()} → {df.index[-1].date()}"
            )
            logger.info("Compare panel loaded %s (%d bars)", ticker, len(df))
        except Exception as exc:  # noqa: BLE001
            self._status.setText(f"Error: {exc}")
            logger.warning("Compare panel failed to load %s: %s", ticker, exc)

    # ── public access ─────────────────────────────────────────────────────────

    @property
    def chart(self) -> ChartPanel:
        """The embedded ChartPanel."""
        return self._chart

    @property
    def lock_axes(self) -> bool:
        return self._lock_axes
