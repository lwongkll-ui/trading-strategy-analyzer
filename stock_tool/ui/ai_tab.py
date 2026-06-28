"""AI Pattern Analysis tab — Phase 3 of the AI backtester.

Layout::

    ┌───────────────────────────────────────────────────────────┐
    │ Controls: [Ticker ____] [Hold ▾] [Min ⬆] [▶ Run] [■ Stop]│
    │           Status label               [===== progress ====] │
    ├───────────────────────────────────────────────────────────┤
    │ [▶ Show on Chart] [✕ Clear]    Hold filter [All ▾]  N rows │
    │                                                            │
    │  Pattern  Dir  Hold  IS n  IS Win  OOS Win  OOS Ret  …    │  ← sortable
    │  ───────────────────────────────────────────────────────── │
    │  …                                                         │
    ├───────────────────────────────────────────────────────────┤
    │  Feature Importance                                        │
    │  rsi_14  ████████████████ 18.5 %                          │
    │  ret_20  █████████░░░░░░░ 12.3 %                          │
    └───────────────────────────────────────────────────────────┘

Signal flow:
    User clicks Run  →  AIWorker.run()  →  run_ai_analysis()
                     →  result_ready(AIAnalysisResult)
                     →  AITab._on_result(result)  →  populate table

    User selects row + clicks Show on Chart
                     →  AITab.signals_show_chart(list[int])
                     →  MainWindow._on_ai_show_chart(bars)
                     →  ChartPanel.mark_ai_signals(bars)
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PyQt6 import QtCore, QtGui, QtWidgets

from core.ai_analyzer import AIAnalysisResult, PatternAIStats, SignalPrediction, run_ai_analysis

if TYPE_CHECKING:
    import pandas as pd


# ── column definitions ─────────────────────────────────────────────────────────

_COLS = [
    ("Pattern",    180, QtCore.Qt.AlignmentFlag.AlignLeft),
    ("Dir",         40, QtCore.Qt.AlignmentFlag.AlignCenter),
    ("Hold",        44, QtCore.Qt.AlignmentFlag.AlignCenter),
    ("IS n",        50, QtCore.Qt.AlignmentFlag.AlignRight),
    ("IS Win%",     62, QtCore.Qt.AlignmentFlag.AlignRight),
    ("IS Ret%",     62, QtCore.Qt.AlignmentFlag.AlignRight),
    ("OOS Win%",    68, QtCore.Qt.AlignmentFlag.AlignRight),
    ("OOS Ret%",    68, QtCore.Qt.AlignmentFlag.AlignRight),
    ("CV Acc%",     62, QtCore.Qt.AlignmentFlag.AlignRight),
    ("OOS Acc%",    68, QtCore.Qt.AlignmentFlag.AlignRight),
    ("Lift",        48, QtCore.Qt.AlignmentFlag.AlignRight),
    ("Prob Gap",    68, QtCore.Qt.AlignmentFlag.AlignRight),
]

_COL_HEADERS = [c[0] for c in _COLS]
_COL_IDX = {h: i for i, h in enumerate(_COL_HEADERS)}

_HOLD_LABELS = {"21d": 21, "42d": 42, "63d": 63}

_GREEN = QtGui.QColor(46, 125, 50, 60)
_RED   = QtGui.QColor(183, 28, 28, 60)
_BULL_FG = QtGui.QColor("#26a69a")
_BEAR_FG = QtGui.QColor("#ef5350")


# ── background worker ──────────────────────────────────────────────────────────

class AIWorker(QtCore.QThread):
    """Runs :func:`~core.ai_analyzer.run_ai_analysis` off the UI thread."""

    progress      = QtCore.pyqtSignal(int, int)          # step, total
    status_update = QtCore.pyqtSignal(str)
    result_ready  = QtCore.pyqtSignal(object)            # AIAnalysisResult
    error         = QtCore.pyqtSignal(str)

    def __init__(
        self,
        df: "pd.DataFrame",
        ticker: str,
        hold_periods: list[int],
        min_samples: int,
        parent: QtCore.QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._df = df
        self._ticker = ticker
        self._hold_periods = hold_periods
        self._min_samples = min_samples
        self._abort = False

    def stop(self) -> None:
        self._abort = True

    def run(self) -> None:
        try:
            self.status_update.emit("Detecting patterns…")
            result = run_ai_analysis(
                self._df,
                self._ticker,
                hold_periods=self._hold_periods,
                min_samples=self._min_samples,
                progress_cb=lambda s, t: self.progress.emit(s, t),
            )
            if not self._abort:
                self.result_ready.emit(result)
        except ImportError as exc:
            self.error.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self.error.emit(f"Analysis failed: {exc}")


# ── feature importance widget ──────────────────────────────────────────────────

class _FeatureImportanceWidget(QtWidgets.QWidget):
    """Simple bar-text display of RF feature importances (top N features)."""

    _MAX_FEATURES = 12

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        hdr = QtWidgets.QLabel("Feature Importance (mean across models)")
        hdr.setStyleSheet("font-weight: bold; color: #aaaaaa; font-size: 11px;")
        layout.addWidget(hdr)

        self._table = QtWidgets.QTableWidget(0, 3, self)
        self._table.setHorizontalHeaderLabels(["Feature", "Importance", "%"])
        self._table.horizontalHeader().setSectionResizeMode(
            0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.horizontalHeader().setSectionResizeMode(
            1, QtWidgets.QHeaderView.ResizeMode.Stretch
        )
        self._table.horizontalHeader().setSectionResizeMode(
            2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.verticalHeader().setDefaultSectionSize(20)
        self._table.verticalHeader().hide()
        self._table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        self._table.setShowGrid(False)
        self._table.setAlternatingRowColors(True)
        layout.addWidget(self._table)

    def set_importances(self, importances: dict[str, float]) -> None:
        if not importances:
            self._table.setRowCount(0)
            return
        ranked = sorted(importances.items(), key=lambda kv: kv[1], reverse=True)
        top = ranked[: self._MAX_FEATURES]
        max_val = top[0][1] if top else 1.0
        self._table.setRowCount(len(top))
        for row, (name, val) in enumerate(top):
            self._table.setItem(row, 0, _cell(name))
            # Visual bar using block characters
            pct = val / max_val if max_val > 0 else 0
            filled = int(round(pct * 18))
            bar = "█" * filled + "░" * (18 - filled)
            bar_item = _cell(bar)
            bar_item.setForeground(QtGui.QColor("#5c9bd6"))
            bar_item.setFont(QtGui.QFont("Consolas, Courier New", 9))
            self._table.setItem(row, 1, bar_item)
            self._table.setItem(row, 2, _cell(f"{val * 100:.1f}%"))


# ── main tab widget ────────────────────────────────────────────────────────────

class AITab(QtWidgets.QWidget):
    """AI Pattern Analysis tab.

    Signals:
        signals_show_chart(list[int]): Emits bar indices for the main window
            to highlight on the price chart.
    """

    signals_show_chart = QtCore.pyqtSignal(list)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._result: AIAnalysisResult | None = None
        self._worker: AIWorker | None = None
        self._df: "pd.DataFrame | None" = None
        self._ticker: str = ""

        self._build_ui()

    # ── public interface ───────────────────────────────────────────────────────

    def set_chart_data(self, df: "pd.DataFrame", ticker: str) -> None:
        """Called by MainWindow when the chart ticker changes.

        Updates the ticker label so the user knows what analysis will run
        without having to type anything.
        """
        self._df = df
        self._ticker = ticker
        self._ticker_lbl.setText(ticker or "—")
        if self._result and self._result.ticker != ticker:
            self._status_lbl.setText(
                f"Results shown for {self._result.ticker}. "
                f"Click ▶ Run to analyse {ticker}."
            )

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)

        # ── control row ───────────────────────────────────────────────────────
        ctrl = QtWidgets.QHBoxLayout()
        ctrl.setSpacing(8)

        ctrl.addWidget(QtWidgets.QLabel("Ticker:"))
        self._ticker_lbl = QtWidgets.QLabel("—")
        self._ticker_lbl.setStyleSheet("font-weight: bold; min-width: 80px;")
        ctrl.addWidget(self._ticker_lbl)

        ctrl.addWidget(_vsep())

        ctrl.addWidget(QtWidgets.QLabel("Hold:"))
        self._hold_combo = QtWidgets.QComboBox()
        self._hold_combo.addItems(["All", "21d", "42d", "63d"])
        self._hold_combo.setFixedWidth(70)
        self._hold_combo.setToolTip("Hold period(s) to include in analysis")
        ctrl.addWidget(self._hold_combo)

        ctrl.addWidget(QtWidgets.QLabel("Min samples:"))
        self._min_spin = QtWidgets.QSpinBox()
        self._min_spin.setRange(10, 500)
        self._min_spin.setSingleStep(10)
        self._min_spin.setValue(50)
        self._min_spin.setFixedWidth(70)
        self._min_spin.setToolTip("Minimum in-sample occurrences required to show a pattern")
        ctrl.addWidget(self._min_spin)

        ctrl.addWidget(_vsep())

        self._run_btn = QtWidgets.QPushButton("▶  Run Analysis")
        self._run_btn.setToolTip("Run AI pattern backtest for the current chart ticker")
        self._run_btn.clicked.connect(self._on_run)
        ctrl.addWidget(self._run_btn)

        self._stop_btn = QtWidgets.QPushButton("■  Stop")
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._on_stop)
        ctrl.addWidget(self._stop_btn)

        ctrl.addStretch()

        self._progress = QtWidgets.QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setFixedWidth(180)
        self._progress.setTextVisible(False)
        self._progress.hide()
        ctrl.addWidget(self._progress)

        root.addLayout(ctrl)

        # ── status row ────────────────────────────────────────────────────────
        self._status_lbl = QtWidgets.QLabel("Load a ticker and click ▶ Run Analysis.")
        self._status_lbl.setStyleSheet("color: #888888; font-size: 11px;")
        root.addWidget(self._status_lbl)

        # ── splitter: table (top) / feature importance (bottom) ───────────────
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)

        # ── table panel ───────────────────────────────────────────────────────
        table_panel = QtWidgets.QWidget()
        table_layout = QtWidgets.QVBoxLayout(table_panel)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(4)

        # Table toolbar
        tbar = QtWidgets.QHBoxLayout()
        tbar.setSpacing(6)

        self._show_chart_btn = QtWidgets.QPushButton("▶  Show on Chart")
        self._show_chart_btn.setToolTip(
            "Switch to Chart tab and mark where the selected pattern was detected"
        )
        self._show_chart_btn.setEnabled(False)
        self._show_chart_btn.clicked.connect(self._on_show_chart)
        tbar.addWidget(self._show_chart_btn)

        self._clear_btn = QtWidgets.QPushButton("✕  Clear Markers")
        self._clear_btn.setEnabled(False)
        self._clear_btn.clicked.connect(self._on_clear_markers)
        tbar.addWidget(self._clear_btn)

        tbar.addWidget(_vsep())

        tbar.addWidget(QtWidgets.QLabel("Filter hold:"))
        self._filter_hold_combo = QtWidgets.QComboBox()
        self._filter_hold_combo.addItems(["All", "21d", "42d", "63d"])
        self._filter_hold_combo.setFixedWidth(70)
        self._filter_hold_combo.currentTextChanged.connect(self._apply_hold_filter)
        tbar.addWidget(self._filter_hold_combo)

        tbar.addStretch()

        self._count_lbl = QtWidgets.QLabel("")
        self._count_lbl.setStyleSheet("color: #888888; font-size: 11px;")
        tbar.addWidget(self._count_lbl)

        table_layout.addLayout(tbar)

        # Results table
        self._table = QtWidgets.QTableWidget(0, len(_COLS))
        self._table.setHorizontalHeaderLabels(_COL_HEADERS)
        self._table.setSortingEnabled(True)
        self._table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().hide()
        self._table.setShowGrid(False)

        hdr = self._table.horizontalHeader()
        for col_idx, (_, width, _) in enumerate(_COLS):
            self._table.setColumnWidth(col_idx, width)
            if col_idx == 0:
                hdr.setSectionResizeMode(col_idx, QtWidgets.QHeaderView.ResizeMode.Stretch)
            else:
                hdr.setSectionResizeMode(col_idx, QtWidgets.QHeaderView.ResizeMode.Fixed)

        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self._table.doubleClicked.connect(lambda _: self._on_show_chart())
        table_layout.addWidget(self._table)

        splitter.addWidget(table_panel)

        # ── feature importance panel ──────────────────────────────────────────
        self._importance_widget = _FeatureImportanceWidget()
        self._importance_widget.setMinimumHeight(160)
        splitter.addWidget(self._importance_widget)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter)

    # ── run / stop ─────────────────────────────────────────────────────────────

    def _on_run(self) -> None:
        if self._df is None or not self._ticker:
            QtWidgets.QMessageBox.information(
                self, "No Data", "Load a ticker in the Chart tab first."
            )
            return

        hold_text = self._hold_combo.currentText()
        if hold_text == "All":
            hold_periods = [21, 42, 63]
        else:
            hold_periods = [_HOLD_LABELS[hold_text]]

        min_samples = self._min_spin.value()

        self._table.setRowCount(0)
        self._importance_widget.set_importances({})
        self._count_lbl.setText("")
        self._status_lbl.setText(f"Running analysis for {self._ticker}…")
        self._run_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._progress.setValue(0)
        self._progress.show()
        self._show_chart_btn.setEnabled(False)

        self._worker = AIWorker(self._df, self._ticker, hold_periods, min_samples, self)
        self._worker.progress.connect(self._on_progress)
        self._worker.status_update.connect(self._status_lbl.setText)
        self._worker.result_ready.connect(self._on_result)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    def _on_stop(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._worker.quit()
            self._worker.wait(3000)
            self._status_lbl.setText("Analysis stopped.")
        self._on_worker_finished()

    def _on_worker_finished(self) -> None:
        self._run_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._progress.hide()

    def _on_progress(self, step: int, total: int) -> None:
        if total > 0:
            self._progress.setValue(int(step / total * 100))

    def _on_error(self, msg: str) -> None:
        self._status_lbl.setText(f"Error: {msg}")
        QtWidgets.QMessageBox.warning(self, "Analysis Error", msg)

    # ── result handling ────────────────────────────────────────────────────────

    def _on_result(self, result: AIAnalysisResult) -> None:
        self._result = result
        bt = result.backtest

        # Merge backtest stats + AI stats by key
        bt_lookup = {(s.pattern, s.direction, s.hold_days): s for s in bt.stats}
        ai_lookup = {(s.pattern, s.direction, s.hold_days): s for s in result.pattern_stats}
        all_keys = sorted(
            set(bt_lookup) | set(ai_lookup),
            key=lambda k: -(bt_lookup[k].score if k in bt_lookup else 0),
        )

        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(all_keys))

        for row, key in enumerate(all_keys):
            pat, dirn, hp = key
            bt_s = bt_lookup.get(key)
            ai_s = ai_lookup.get(key)
            self._populate_row(row, pat, dirn, hp, bt_s, ai_s)

        self._table.setSortingEnabled(True)
        self._apply_hold_filter(self._filter_hold_combo.currentText())
        self._importance_widget.set_importances(result.feature_importances)

        n_valid = sum(1 for s in result.pattern_stats if s.is_valid)
        self._status_lbl.setText(
            f"Analysis complete for {result.ticker}  |  "
            f"{result.n_models_trained} models trained  |  "
            f"{result.backtest.n_signals} patterns detected  |  "
            f"{n_valid} valid AI results"
        )

    def _populate_row(
        self,
        row: int,
        pattern: str,
        direction: str,
        hold_days: int,
        bt_s,  # PatternStats | None
        ai_s: PatternAIStats | None,
    ) -> None:
        t = self._table

        def _set(col_name: str, text: str, numeric_val: float | None = None) -> None:
            col = _COL_IDX[col_name]
            item = _cell(text)
            item.setTextAlignment(_COLS[col][2])
            if numeric_val is not None:
                item.setData(QtCore.Qt.ItemDataRole.UserRole, numeric_val)
            t.setItem(row, col, item)

        _set("Pattern", pattern)

        dir_item = _cell(direction)
        dir_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        dir_item.setForeground(_BULL_FG if direction == "bull" else _BEAR_FG)
        t.setItem(row, _COL_IDX["Dir"], dir_item)

        _set("Hold", f"{hold_days}d", numeric_val=hold_days)

        if bt_s:
            _set("IS n",    str(bt_s.n_is),              numeric_val=bt_s.n_is)
            _set("IS Win%", f"{bt_s.is_win_rate:.0%}",   numeric_val=bt_s.is_win_rate)
            _set("IS Ret%", f"{bt_s.is_avg_return:+.2f}%", numeric_val=bt_s.is_avg_return)
            _set("OOS Win%", f"{bt_s.oos_win_rate:.0%}",  numeric_val=bt_s.oos_win_rate)
            _set("OOS Ret%", f"{bt_s.oos_avg_return:+.2f}%", numeric_val=bt_s.oos_avg_return)
        else:
            for col_name in ("IS n", "IS Win%", "IS Ret%", "OOS Win%", "OOS Ret%"):
                _set(col_name, "—")

        if ai_s:
            _set("CV Acc%",  f"{ai_s.model_cv_accuracy:.0%}", numeric_val=ai_s.model_cv_accuracy)
            oos_acc = ai_s.oos_accuracy
            oos_text = f"{oos_acc:.0%}" if not math.isnan(oos_acc) else "—"
            oos_item = _cell(oos_text)
            oos_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
            if not math.isnan(oos_acc):
                oos_item.setData(QtCore.Qt.ItemDataRole.UserRole, oos_acc)
                if oos_acc > 0.55:
                    oos_item.setBackground(_GREEN)
                elif oos_acc < 0.45:
                    oos_item.setBackground(_RED)
            t.setItem(row, _COL_IDX["OOS Acc%"], oos_item)

            _set("Lift", f"{ai_s.lift:.2f}×", numeric_val=ai_s.lift)

            win_p = ai_s.oos_avg_prob_win
            loss_p = ai_s.oos_avg_prob_loss
            if not math.isnan(win_p) and not math.isnan(loss_p):
                gap = win_p - loss_p
                _set("Prob Gap", f"{gap:+.2f}", numeric_val=gap)
            else:
                _set("Prob Gap", "—")
        else:
            for col_name in ("CV Acc%", "OOS Acc%", "Lift", "Prob Gap"):
                _set(col_name, "—")

        # Row tooltip with hold info stored as UserRole on first column
        t.item(row, 0).setData(QtCore.Qt.ItemDataRole.UserRole + 1, (pattern, direction))

    # ── table interactions ─────────────────────────────────────────────────────

    def _apply_hold_filter(self, filter_text: str) -> None:
        hold_val = _HOLD_LABELS.get(filter_text)  # None means "All"
        visible = 0
        for row in range(self._table.rowCount()):
            hold_item = self._table.item(row, _COL_IDX["Hold"])
            if hold_item is None:
                continue
            row_hold = hold_item.data(QtCore.Qt.ItemDataRole.UserRole)
            show = hold_val is None or row_hold == hold_val
            self._table.setRowHidden(row, not show)
            if show:
                visible += 1
        self._count_lbl.setText(f"{visible} result{'s' if visible != 1 else ''}")

    def _on_selection_changed(self) -> None:
        has_selection = bool(self._table.selectedItems())
        has_result = self._result is not None
        self._show_chart_btn.setEnabled(has_selection and has_result)

    def _on_show_chart(self) -> None:
        if self._result is None:
            return
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return

        row = rows[0].row()
        meta_item = self._table.item(row, 0)
        if meta_item is None:
            return
        pattern, direction = meta_item.data(QtCore.Qt.ItemDataRole.UserRole + 1)
        hold_item = self._table.item(row, _COL_IDX["Hold"])
        hold_val = hold_item.data(QtCore.Qt.ItemDataRole.UserRole) if hold_item else None

        bars = [
            sp.bar
            for sp in self._result.signal_probs
            if sp.pattern == pattern
            and sp.direction == direction
            and (hold_val is None or sp.hold_days == hold_val)
        ]
        bars = sorted(set(bars))  # unique bar positions

        self._clear_btn.setEnabled(True)
        self.signals_show_chart.emit(bars)

    def _on_clear_markers(self) -> None:
        self.signals_show_chart.emit([])  # empty list → clear markers
        self._clear_btn.setEnabled(False)


# ── helpers ────────────────────────────────────────────────────────────────────

def _cell(text: str) -> QtWidgets.QTableWidgetItem:
    item = QtWidgets.QTableWidgetItem(text)
    item.setFlags(QtCore.Qt.ItemFlag.ItemIsSelectable | QtCore.Qt.ItemFlag.ItemIsEnabled)
    return item


def _vsep() -> QtWidgets.QFrame:
    sep = QtWidgets.QFrame()
    sep.setFrameShape(QtWidgets.QFrame.Shape.VLine)
    sep.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
    return sep
