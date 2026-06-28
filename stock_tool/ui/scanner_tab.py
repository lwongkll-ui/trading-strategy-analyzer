"""Scanner tab — filter HSI / S&P 500 constituents by SMA and RSI signals."""
from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt, pyqtSignal

from core.scanner_engine import ScanCriteria, ScanResult, ScanWorker, load_constituents

_COLUMNS = ["Symbol", "Name", "Market", "Price", "vs SMA200", "SMA10/50", "RSI"]

# Alignment per column
_ALIGN = [
    Qt.AlignmentFlag.AlignLeft,
    Qt.AlignmentFlag.AlignLeft,
    Qt.AlignmentFlag.AlignCenter,
    Qt.AlignmentFlag.AlignRight,
    Qt.AlignmentFlag.AlignRight,
    Qt.AlignmentFlag.AlignCenter,
    Qt.AlignmentFlag.AlignRight,
]

_GREEN = "#26a69a"
_RED = "#ef5350"


class ScannerTab(QtWidgets.QWidget):
    """Self-contained scanner tab.

    Emits ``ticker_selected(symbol)`` when the user double-clicks a result row
    so ``MainWindow`` can switch to the chart tab and load that symbol.
    """

    ticker_selected = pyqtSignal(str)

    def __init__(self, config, data_manager, parent=None) -> None:
        super().__init__(parent)
        self._config = config
        self._dm = data_manager
        self._worker: ScanWorker | None = None
        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        root.addWidget(self._build_filter_panel())
        root.addLayout(self._build_progress_row())
        root.addWidget(self._build_table())
        root.addWidget(self._build_footer())

    def _build_filter_panel(self) -> QtWidgets.QGroupBox:
        group = QtWidgets.QGroupBox("Scan Filters")
        row = QtWidgets.QHBoxLayout(group)
        row.setSpacing(16)

        # ── Market ────────────────────────────────────────────────────────────
        mkt = QtWidgets.QGroupBox("Market")
        mvbox = QtWidgets.QVBoxLayout(mkt)
        self._chk_hsi = QtWidgets.QCheckBox("Hang Seng (HK)")
        self._chk_sp500 = QtWidgets.QCheckBox("S&P 500 (US)")
        self._chk_hsi.setChecked(True)
        self._chk_sp500.setChecked(True)
        mvbox.addWidget(self._chk_hsi)
        mvbox.addWidget(self._chk_sp500)
        row.addWidget(mkt)

        # ── vs SMA 200 ────────────────────────────────────────────────────────
        sma200_grp = QtWidgets.QGroupBox("vs SMA 200")
        s200v = QtWidgets.QVBoxLayout(sma200_grp)
        self._combo_sma200 = QtWidgets.QComboBox()
        self._combo_sma200.addItems(["Any", "Above SMA 200", "Below SMA 200"])
        s200v.addWidget(self._combo_sma200)
        s200v.addStretch()
        row.addWidget(sma200_grp)

        # ── SMA 10 vs SMA 50 ──────────────────────────────────────────────────
        cross_grp = QtWidgets.QGroupBox("SMA 10 vs SMA 50")
        cv = QtWidgets.QVBoxLayout(cross_grp)
        self._combo_cross = QtWidgets.QComboBox()
        self._combo_cross.addItems([
            "Any",
            "SMA10 > SMA50  (Bullish)",
            "SMA10 < SMA50  (Bearish)",
        ])
        cv.addWidget(self._combo_cross)
        cv.addStretch()
        row.addWidget(cross_grp)

        # ── RSI ───────────────────────────────────────────────────────────────
        rsi_grp = QtWidgets.QGroupBox("RSI (14-period)")
        rv = QtWidgets.QVBoxLayout(rsi_grp)
        self._combo_rsi = QtWidgets.QComboBox()
        self._combo_rsi.addItems(["Any", "Overbought  > 80", "Oversold  < 20"])
        rv.addWidget(self._combo_rsi)
        rv.addStretch()
        row.addWidget(rsi_grp)

        row.addStretch()

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_col = QtWidgets.QVBoxLayout()
        self._scan_btn = QtWidgets.QPushButton("Scan  (cached only)")
        self._scan_btn.setMinimumHeight(32)
        self._dl_btn = QtWidgets.QPushButton("Download & Scan")
        self._dl_btn.setMinimumHeight(32)
        self._dl_btn.setToolTip(
            "Download daily data for every symbol in the selected markets,\n"
            "then run the scan. First run can take several minutes."
        )
        self._stop_btn = QtWidgets.QPushButton("Stop")
        self._stop_btn.setMinimumHeight(32)
        self._stop_btn.setEnabled(False)
        self._scan_btn.clicked.connect(self._on_scan)
        self._dl_btn.clicked.connect(self._on_download_scan)
        self._stop_btn.clicked.connect(self._on_stop)
        btn_col.addWidget(self._scan_btn)
        btn_col.addWidget(self._dl_btn)
        btn_col.addWidget(self._stop_btn)
        row.addLayout(btn_col)

        return group

    def _build_progress_row(self) -> QtWidgets.QHBoxLayout:
        hbox = QtWidgets.QHBoxLayout()
        self._progress = QtWidgets.QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(True)
        self._status_lbl = QtWidgets.QLabel("Select filters and click Scan")
        self._status_lbl.setMinimumWidth(360)
        hbox.addWidget(self._progress, stretch=1)
        hbox.addWidget(self._status_lbl)
        return hbox

    def _build_table(self) -> QtWidgets.QTableWidget:
        tbl = QtWidgets.QTableWidget(0, len(_COLUMNS))
        tbl.setHorizontalHeaderLabels(_COLUMNS)
        hdr = tbl.horizontalHeader()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        tbl.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        tbl.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        tbl.setSortingEnabled(True)
        tbl.verticalHeader().setVisible(False)
        tbl.setAlternatingRowColors(True)
        tbl.doubleClicked.connect(self._on_row_double_clicked)
        self._table = tbl
        return tbl

    def _build_footer(self) -> QtWidgets.QLabel:
        self._count_lbl = QtWidgets.QLabel("")
        self._count_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        font = self._count_lbl.font()
        font.setPointSize(font.pointSize() - 1)
        self._count_lbl.setFont(font)
        return self._count_lbl

    # ── scan control ──────────────────────────────────────────────────────────

    def _on_scan(self) -> None:
        self._start_scan(fetch_missing=False)

    def _on_download_scan(self) -> None:
        self._start_scan(fetch_missing=True)

    def _on_stop(self) -> None:
        if self._worker:
            self._worker.abort()

    def _start_scan(self, fetch_missing: bool) -> None:
        if self._worker and self._worker.isRunning():
            return

        markets = []
        if self._chk_hsi.isChecked():
            markets.append("HSI")
        if self._chk_sp500.isChecked():
            markets.append("SP500")
        if not markets:
            QtWidgets.QMessageBox.warning(self, "Scanner", "Select at least one market.")
            return

        symbols: list[tuple[str, str, str]] = []
        for market in markets:
            for ticker, name in load_constituents(market):
                symbols.append((ticker, name, market))

        if not symbols:
            self._status_lbl.setText("No constituent files found in resources/")
            return

        criteria = ScanCriteria(
            markets=markets,
            sma200=["any", "above", "below"][self._combo_sma200.currentIndex()],
            sma_cross=["any", "golden", "death"][self._combo_cross.currentIndex()],
            rsi=["any", "overbought", "oversold"][self._combo_rsi.currentIndex()],
            fetch_missing=fetch_missing,
        )

        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        self._progress.setRange(0, len(symbols))
        self._progress.setValue(0)
        self._count_lbl.setText("")

        self._scan_btn.setEnabled(False)
        self._dl_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)

        self._worker = ScanWorker(
            symbols,
            self._config.data.price_dir,
            criteria,
            data_manager=self._dm,
            parent=self,
        )
        self._worker.result_ready.connect(self._on_result)
        self._worker.progress.connect(self._on_progress)
        self._worker.status_update.connect(self._on_status_update)
        self._worker.scan_finished.connect(self._on_finished)
        self._worker.start()

    # ── worker callbacks (called from main thread via Qt signals) ─────────────

    def _on_result(self, result: ScanResult) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)

        vs200 = (
            f"{(result.price / result.sma200 - 1) * 100:+.1f}%"
            if result.sma200 else "—"
        )
        cross_text = (
            "Bullish  ▲" if result.sma10_above_sma50 is True
            else "Bearish  ▼" if result.sma10_above_sma50 is False
            else "—"
        )
        rsi_text = f"{result.rsi:.1f}" if result.rsi is not None else "—"

        values = [
            result.symbol,
            result.name,
            result.market,
            f"{result.price:.3f}",
            vs200,
            cross_text,
            rsi_text,
        ]

        for col, (text, align) in enumerate(zip(values, _ALIGN)):
            item = QtWidgets.QTableWidgetItem(text)
            item.setTextAlignment(align | Qt.AlignmentFlag.AlignVCenter)
            if col == 0:
                item.setData(Qt.ItemDataRole.UserRole, result.symbol)

            # Colour vs SMA200 column
            if col == 4:
                if result.above_sma200 is True:
                    item.setForeground(QtGui.QColor(_GREEN))
                elif result.above_sma200 is False:
                    item.setForeground(QtGui.QColor(_RED))

            # Colour SMA cross column
            if col == 5:
                if result.sma10_above_sma50 is True:
                    item.setForeground(QtGui.QColor(_GREEN))
                elif result.sma10_above_sma50 is False:
                    item.setForeground(QtGui.QColor(_RED))

            # Colour RSI extremes
            if col == 6 and result.rsi is not None:
                if result.rsi > 80:
                    item.setForeground(QtGui.QColor(_RED))
                elif result.rsi < 20:
                    item.setForeground(QtGui.QColor(_GREEN))

            self._table.setItem(row, col, item)

        self._count_lbl.setText(f"{self._table.rowCount()} result(s) — double-click to open in chart")

    def _on_progress(self, current: int, total: int) -> None:
        self._progress.setValue(current)
        self._status_lbl.setText(f"Scanning {current} / {total}…")

    def _on_status_update(self, text: str) -> None:
        self._status_lbl.setText(text)

    def _on_finished(self, matched: int, scanned: int) -> None:
        self._progress.setValue(self._progress.maximum())
        self._status_lbl.setText(
            f"Done — {matched} match(es) from {scanned} symbol(s) with cached data"
        )
        self._scan_btn.setEnabled(True)
        self._dl_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._table.setSortingEnabled(True)
        self._table.resizeColumnsToContents()
        # Re-apply stretch on Name column after resize
        self._table.horizontalHeader().setSectionResizeMode(
            1, QtWidgets.QHeaderView.ResizeMode.Stretch
        )

    # ── row interaction ───────────────────────────────────────────────────────

    def _on_row_double_clicked(self, index: QtCore.QModelIndex) -> None:
        sym_item = self._table.item(index.row(), 0)
        if sym_item:
            symbol = sym_item.data(Qt.ItemDataRole.UserRole) or sym_item.text()
            self.ticker_selected.emit(symbol)
