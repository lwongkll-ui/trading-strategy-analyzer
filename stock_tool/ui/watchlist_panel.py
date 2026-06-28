"""Watchlist sidebar panel for StockTool.

Displays the user's saved tickers.  Double-clicking a row emits
:attr:`ticker_selected` which the main window connects to ``load_ticker``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtCore import pyqtSignal

if TYPE_CHECKING:
    from storage.db_store import DbStore

logger = logging.getLogger(__name__)


class WatchlistPanel(QtWidgets.QWidget):
    """Widget that shows, adds, and removes watchlist tickers.

    Args:
        db:     An open :class:`~storage.db_store.DbStore`.
        parent: Optional parent widget.

    Signals:
        ticker_selected(str): Emitted when the user activates a row (double-click
            or Enter).  The argument is the uppercase ticker string.
    """

    ticker_selected = pyqtSignal(str)

    def __init__(self, db: "DbStore", parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._db = db
        self._build_ui()
        self._refresh()

    # ── public API ────────────────────────────────────────────────────────────

    @property
    def ticker_count(self) -> int:
        """Number of tickers currently shown in the list."""
        return self._list.count()

    def refresh(self) -> None:
        """Reload the watchlist from the database."""
        self._refresh()

    def select_ticker(self, ticker: str) -> None:
        """Highlight *ticker* in the list if it is present (no signal emitted)."""
        ticker = ticker.upper()
        for i in range(self._list.count()):
            if self._list.item(i).text() == ticker:
                self._list.setCurrentRow(i)
                return

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Header
        header = QtWidgets.QHBoxLayout()
        lbl = QtWidgets.QLabel("Watchlist")
        lbl.setStyleSheet("font-weight: bold;")
        header.addWidget(lbl)
        header.addStretch()
        layout.addLayout(header)

        # Add row: text input + "+" button
        add_row = QtWidgets.QHBoxLayout()
        add_row.setSpacing(4)
        self._ticker_edit = QtWidgets.QLineEdit()
        self._ticker_edit.setPlaceholderText("Symbol…")
        self._ticker_edit.setMaximumWidth(120)
        self._ticker_edit.returnPressed.connect(self._on_add)
        add_row.addWidget(self._ticker_edit)
        self._add_btn = QtWidgets.QPushButton("+")
        self._add_btn.setFixedWidth(28)
        self._add_btn.setToolTip("Add to watchlist")
        self._add_btn.clicked.connect(self._on_add)
        add_row.addWidget(self._add_btn)
        add_row.addStretch()
        layout.addLayout(add_row)

        # Ticker list — drag-and-drop reordering enabled
        self._list = QtWidgets.QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.setDragDropMode(
            QtWidgets.QAbstractItemView.DragDropMode.InternalMove
        )
        self._list.setDefaultDropAction(QtCore.Qt.DropAction.MoveAction)
        self._list.itemActivated.connect(self._on_item_activated)
        self._list.model().rowsMoved.connect(self._on_reorder)
        layout.addWidget(self._list)

        # Remove button
        self._remove_btn = QtWidgets.QPushButton("Remove")
        self._remove_btn.setToolTip("Remove selected ticker from watchlist")
        self._remove_btn.clicked.connect(self._on_remove)
        layout.addWidget(self._remove_btn)

    # ── slots ─────────────────────────────────────────────────────────────────

    def _on_add(self) -> None:
        ticker = self._ticker_edit.text().strip().upper()
        if not ticker:
            return
        self._db.add_to_watchlist(ticker)
        self._ticker_edit.clear()
        self._refresh()
        self.select_ticker(ticker)

    def _on_remove(self) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        self._db.remove_from_watchlist(item.text())
        self._refresh()

    def _on_item_activated(self, item: QtWidgets.QListWidgetItem) -> None:
        self.ticker_selected.emit(item.text())

    def _on_reorder(self) -> None:
        """Persist the new ticker order after a drag-and-drop move."""
        tickers = [self._list.item(i).text() for i in range(self._list.count())]
        self._db.reorder_watchlist(tickers)

    # ── internal ──────────────────────────────────────────────────────────────

    def _refresh(self) -> None:
        self._list.clear()
        for ticker in self._db.get_watchlist():
            self._list.addItem(ticker)
