"""Main application window — wires ChartPanel, IndicatorPanel, and toolbar.

Layout::

    ┌─────────────────────────────────────────────────┬──────────────┐
    │  Menu: File | View | Help                       │              │
    ├─────────────────────────────────────────────────┤   News       │
    │  [Symbol ____] [Market ▾] ║ [D][W][M][Q][Y]   │   Sidebar    │
    │  [Start  date] [End date] [↓ Download]          │   (dock)     │
    │  [MA: SMA▾] [Period  20] [+ Add MA] [Indicators]│              │
    │  [Mode:][▷][—][/][T]  [Del Drawings]            │              │
    ├─────────────────────────────────────────────────┤              │
    │                    ChartPanel                   │              │
    ├─────────────────────────────────────────────────┤              │
    │                   IndicatorPanel                │              │
    ├─────────────────────────────────────────────────┴──────────────┤
    │  Status bar                                                     │
    └─────────────────────────────────────────────────────────────────┘

Data flow:
    1. User enters symbol + clicks Download  → :meth:`_download`
    2. User enters symbol (CSV exists)       → :meth:`_load_from_cache`
    3. Timeframe changed                     → :meth:`_apply_timeframe`
    4. Add MA                                → :meth:`_add_ma`
    5. Toggle indicator                      → :meth:`_toggle_indicator`
    6. Drawing mode changed                  → :meth:`_on_drawing_mode_clicked`
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import TYPE_CHECKING

import pandas as pd
from PyQt6 import QtCore, QtGui, QtWidgets

from core.data_manager import DataManager, DataManagerError
from core.indicator_engine import IndicatorEngine, ema, sma, wma
from models.symbol import SymbolRegistry
from storage import csv_store
from ui.chart_panel import ChartPanel
from ui.indicator_panel import IndicatorPanel, IndicatorPanelError

if TYPE_CHECKING:
    from core.config import Config
    from core.news_fetcher import NewsFetcher
    from storage.db_store import DbStore

logger = logging.getLogger(__name__)

_TIMEFRAMES = ("D", "W", "M", "Q", "Y")
_MA_TYPES = ("SMA", "EMA", "WMA")
_INDICATORS = ("volume", "rsi", "macd", "stc", "atr", "stoch", "obv")

_DRAW_MODES = (
    ("▷", "none",       "Select / Pan"),
    ("—", "horizontal", "Horizontal level (click to place)"),
    ("/", "trend_line",  "Trend line (two clicks)"),
    ("ϕ", "fib",         "Fibonacci retracement (two clicks: high → low)"),
    ("□", "rect",        "Rectangle (two clicks: corner → corner)"),
    ("T", "text",        "Text annotation (click to place)"),
)


class MainWindow(QtWidgets.QMainWindow):
    """Top-level application window.

    Args:
        config:       Loaded application config.
        registry:     Pre-populated symbol registry for autocomplete.
        data_manager: Optional injected :class:`~core.data_manager.DataManager`.
        db_store:     Optional injected :class:`~storage.db_store.DbStore`.
                      When ``None``, one is created at
                      ``config.source_path.parent / "stocktool.db"`` and owned
                      by this window (closed when the window closes).
        news_fetcher: Optional injected :class:`~core.news_fetcher.NewsFetcher`.
    """

    def __init__(
        self,
        config: "Config",
        registry: SymbolRegistry | None = None,
        data_manager: DataManager | None = None,
        db_store: "DbStore | None" = None,
        news_fetcher: "NewsFetcher | None" = None,
    ) -> None:
        super().__init__()
        self._config = config
        self._registry = registry or SymbolRegistry()
        self._dm = data_manager or DataManager(config)
        self._engine = IndicatorEngine(config.indicators)
        self._daily_df: pd.DataFrame | None = None
        self._current_ticker: str = ""
        self._timeframe: str = "D"
        self._active_mas: dict[str, str] = {}

        # DbStore — own it if we created it
        if db_store is None:
            from storage.db_store import DbStore
            self._db: "DbStore" = DbStore(config.source_path.parent / "stocktool.db")
            self._db.open()
            self._db_owned = True
        else:
            self._db = db_store
            self._db_owned = False

        # NewsFetcher — create default if not injected
        if news_fetcher is None:
            from core.news_fetcher import NewsFetcher
            self._news_fetcher: "NewsFetcher" = NewsFetcher(config.news)
        else:
            self._news_fetcher = news_fetcher

        self.setWindowTitle("StockTool")
        self.resize(1400, 900)

        self._build_menus()
        self._build_toolbar()
        self._build_central()   # creates _chart, _drawing_manager, _news_sidebar
        self._build_shortcuts()
        self.statusBar().showMessage("Ready — enter a symbol to begin")

    # ─────────────────────────── lifecycle ───────────────────────────────────

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        if self._db_owned:
            try:
                self._db.close()
            except Exception:
                pass
        super().closeEvent(event)

    # ─────────────────────────── menu ────────────────────────────────────────

    def _build_menus(self) -> None:
        menubar = self.menuBar()

        file_menu = menubar.addMenu("&File")
        file_menu.addAction(
            QtGui.QAction("E&xport Chart…", self, triggered=self._on_export)
        )
        file_menu.addAction(
            QtGui.QAction("Export &Data…", self, triggered=self._on_export_data)
        )
        file_menu.addSeparator()
        file_menu.addAction(
            QtGui.QAction("&Settings…", self, triggered=self._on_settings)
        )
        file_menu.addSeparator()
        file_menu.addAction(
            QtGui.QAction("E&xit", self, triggered=self.close)
        )

        view_menu = menubar.addMenu("&View")
        for ind in _INDICATORS:
            action = QtGui.QAction(ind.upper(), self, checkable=True)
            action.setData(ind)
            action.triggered.connect(self._on_indicator_menu_toggled)
            view_menu.addAction(action)
        self._indicator_actions: dict[str, QtGui.QAction] = {
            a.data(): a for a in view_menu.actions() if a.data()
        }

        view_menu.addSeparator()
        self._compare_action = QtGui.QAction("&Compare Panel", self, checkable=True)
        self._compare_action.triggered.connect(self._on_compare_toggled)
        view_menu.addAction(self._compare_action)

        help_menu = menubar.addMenu("&Help")
        help_menu.addAction(
            QtGui.QAction("&About StockTool", self,
                          triggered=lambda: QtWidgets.QMessageBox.about(
                              self, "StockTool", "StockTool — Phase 1 MVP"))
        )

    # ─────────────────────────── toolbar ─────────────────────────────────────

    def _build_toolbar(self) -> None:
        toolbar_widget = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(toolbar_widget)
        outer.setContentsMargins(4, 4, 4, 2)
        outer.setSpacing(4)

        # ── Row 1: symbol / market / timeframe / dates / download ────────────
        row1 = QtWidgets.QHBoxLayout()
        row1.setSpacing(6)

        self._symbol_edit = QtWidgets.QLineEdit()
        self._symbol_edit.setPlaceholderText("Symbol (e.g. AAPL, 0700.HK)")
        self._symbol_edit.setMinimumWidth(180)
        self._symbol_edit.setMaximumWidth(240)
        self._symbol_edit.returnPressed.connect(self._on_symbol_entered)
        self._completer = QtWidgets.QCompleter(
            self._registry.all_tickers(), self
        )
        self._completer.setCaseSensitivity(QtCore.Qt.CaseSensitivity.CaseInsensitive)
        self._symbol_edit.setCompleter(self._completer)
        row1.addWidget(QtWidgets.QLabel("Symbol:"))
        row1.addWidget(self._symbol_edit)

        self._market_combo = QtWidgets.QComboBox()
        self._market_combo.addItems(["ALL", "US", "HK", "UK", "JP", "AU"])
        self._market_combo.setToolTip("Filter autocomplete by market")
        self._market_combo.currentTextChanged.connect(self._on_market_changed)
        row1.addWidget(self._market_combo)

        row1.addWidget(_vsep())

        self._tf_group = QtWidgets.QButtonGroup(self)
        self._tf_group.setExclusive(True)
        for tf in _TIMEFRAMES:
            btn = QtWidgets.QPushButton(tf)
            btn.setCheckable(True)
            btn.setFixedWidth(36)
            btn.setChecked(tf == "D")
            btn.setToolTip({"D": "Daily", "W": "Weekly", "M": "Monthly",
                            "Q": "Quarterly", "Y": "Yearly"}[tf])
            self._tf_group.addButton(btn)
            row1.addWidget(btn)
            btn.clicked.connect(lambda _, t=tf: self._on_timeframe_clicked(t))
        self._tf_buttons: dict[str, QtWidgets.QPushButton] = {
            _TIMEFRAMES[i]: self._tf_group.buttons()[i]
            for i in range(len(_TIMEFRAMES))
        }

        row1.addWidget(_vsep())

        row1.addWidget(QtWidgets.QLabel("Start:"))
        self._start_date = QtWidgets.QDateEdit()
        self._start_date.setCalendarPopup(True)
        self._start_date.setDate(
            QtCore.QDate(
                self._config.download.default_start_date.year,
                self._config.download.default_start_date.month,
                self._config.download.default_start_date.day,
            )
        )
        self._start_date.setDisplayFormat("yyyy-MM-dd")
        row1.addWidget(self._start_date)

        row1.addWidget(QtWidgets.QLabel("End:"))
        self._end_date = QtWidgets.QDateEdit()
        self._end_date.setCalendarPopup(True)
        today = date.today()
        self._end_date.setDate(QtCore.QDate(today.year, today.month, today.day))
        self._end_date.setDisplayFormat("yyyy-MM-dd")
        row1.addWidget(self._end_date)

        self._download_btn = QtWidgets.QPushButton("↓ Download")
        self._download_btn.setToolTip("Fetch data from yfinance and merge with local CSV")
        self._download_btn.clicked.connect(self._on_download_clicked)
        row1.addWidget(self._download_btn)

        self._watchlist_btn = QtWidgets.QPushButton("★")
        self._watchlist_btn.setFixedWidth(28)
        self._watchlist_btn.setToolTip("Add current symbol to watchlist")
        self._watchlist_btn.clicked.connect(self._on_add_to_watchlist)
        row1.addWidget(self._watchlist_btn)

        row1.addWidget(_vsep())

        row1.addWidget(QtWidgets.QLabel("Chart:"))
        self._chart_mode_group = QtWidgets.QButtonGroup(self)
        self._chart_mode_group.setExclusive(True)
        self._chart_mode_btns: dict[str, QtWidgets.QPushButton] = {}
        for mode_label, mode_key in (("Candle", "candle"), ("Line", "line")):
            btn = QtWidgets.QPushButton(mode_label)
            btn.setCheckable(True)
            btn.setFixedWidth(54)
            btn.setChecked(mode_key == "candle")
            btn.setToolTip(f"Switch to {mode_label.lower()} chart")
            self._chart_mode_group.addButton(btn)
            self._chart_mode_btns[mode_key] = btn
            btn.clicked.connect(lambda _, mk=mode_key: self._on_chart_mode_clicked(mk))
            row1.addWidget(btn)

        row1.addStretch()
        outer.addLayout(row1)

        # ── Row 2: MA overlay / indicator toggles ────────────────────────────
        row2 = QtWidgets.QHBoxLayout()
        row2.setSpacing(6)

        row2.addWidget(QtWidgets.QLabel("MA:"))
        self._ma_type_combo = QtWidgets.QComboBox()
        self._ma_type_combo.addItems(_MA_TYPES)
        self._ma_type_combo.setFixedWidth(60)
        row2.addWidget(self._ma_type_combo)

        self._ma_period_spin = QtWidgets.QSpinBox()
        self._ma_period_spin.setRange(2, 500)
        self._ma_period_spin.setValue(20)
        self._ma_period_spin.setFixedWidth(60)
        row2.addWidget(self._ma_period_spin)

        self._add_ma_btn = QtWidgets.QPushButton("+ Add MA")
        self._add_ma_btn.clicked.connect(self._on_add_ma)
        row2.addWidget(self._add_ma_btn)

        self._clear_ma_btn = QtWidgets.QPushButton("Clear MAs")
        self._clear_ma_btn.clicked.connect(self._on_clear_mas)
        row2.addWidget(self._clear_ma_btn)

        self._bb_btn = QtWidgets.QPushButton("BB")
        self._bb_btn.setCheckable(True)
        self._bb_btn.setFixedWidth(40)
        self._bb_btn.setToolTip("Toggle Bollinger Bands overlay on price chart")
        self._bb_btn.clicked.connect(self._on_bb_toggled)
        row2.addWidget(self._bb_btn)

        self._vwap_btn = QtWidgets.QPushButton("VWAP")
        self._vwap_btn.setCheckable(True)
        self._vwap_btn.setFixedWidth(52)
        self._vwap_btn.setToolTip("Toggle VWAP overlay on price chart")
        self._vwap_btn.clicked.connect(self._on_vwap_toggled)
        row2.addWidget(self._vwap_btn)

        self._fvg_btn = QtWidgets.QPushButton("FVG")
        self._fvg_btn.setCheckable(True)
        self._fvg_btn.setFixedWidth(40)
        self._fvg_btn.setToolTip(
            "Toggle Fair Value Gap zones\n"
            "Green = bullish (unfilled gap up)\n"
            "Red = bearish (unfilled gap down)"
        )
        self._fvg_btn.clicked.connect(self._on_fvg_toggled)
        row2.addWidget(self._fvg_btn)

        row2.addWidget(_vsep())

        row2.addWidget(QtWidgets.QLabel("Indicators:"))
        self._indicator_btns: dict[str, QtWidgets.QPushButton] = {}
        for ind in _INDICATORS:
            btn = QtWidgets.QPushButton(ind.upper())
            btn.setCheckable(True)
            btn.setFixedWidth(70)
            btn.clicked.connect(lambda checked, i=ind: self._toggle_indicator(i, checked))
            self._indicator_btns[ind] = btn
            row2.addWidget(btn)

        row2.addStretch()
        outer.addLayout(row2)

        # ── Row 3: drawing tools ──────────────────────────────────────────────
        row3 = QtWidgets.QHBoxLayout()
        row3.setSpacing(6)

        row3.addWidget(QtWidgets.QLabel("Draw:"))
        self._draw_mode_group = QtWidgets.QButtonGroup(self)
        self._draw_mode_group.setExclusive(True)
        self._draw_btns: dict[str, QtWidgets.QPushButton] = {}
        for label, mode_key, tooltip in _DRAW_MODES:
            btn = QtWidgets.QPushButton(label)
            btn.setCheckable(True)
            btn.setFixedWidth(32)
            btn.setToolTip(tooltip)
            btn.setChecked(mode_key == "none")
            self._draw_mode_group.addButton(btn)
            self._draw_btns[mode_key] = btn
            btn.clicked.connect(
                lambda _, mk=mode_key: self._on_drawing_mode_clicked(mk)
            )
            row3.addWidget(btn)

        self._del_drawings_btn = QtWidgets.QPushButton("Del Drawings")
        self._del_drawings_btn.setToolTip("Delete all drawings for current symbol/timeframe")
        self._del_drawings_btn.clicked.connect(self._on_delete_drawings)
        row3.addWidget(self._del_drawings_btn)

        row3.addStretch()
        outer.addLayout(row3)

        toolbar = QtWidgets.QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.addWidget(toolbar_widget)
        self.addToolBar(toolbar)

    # ─────────────────────────── central widget ───────────────────────────────

    def _build_central(self) -> None:
        from ui.ai_tab import AITab
        from ui.compare_panel import ComparePanel
        from ui.drawing_tools import DrawingManager
        from ui.news_sidebar import NewsSidebar
        from ui.scanner_tab import ScannerTab
        from ui.watchlist_panel import WatchlistPanel

        self._chart = ChartPanel(self._config)
        self._indicator_panel = IndicatorPanel(self._config)
        self._drawing_manager = DrawingManager(self._chart, self._db, parent=self)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        splitter.addWidget(self._chart)
        splitter.addWidget(self._indicator_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        self._indicator_panel.link_to_chart(self._chart)

        self._scanner_tab = ScannerTab(self._config, self._dm, parent=self)
        self._scanner_tab.ticker_selected.connect(self._on_scanner_ticker_selected)

        self._ai_tab = AITab(parent=self)
        self._ai_tab.signals_show_chart.connect(self._on_ai_show_chart)

        self._tab_widget = QtWidgets.QTabWidget()
        self._tab_widget.addTab(splitter, "Chart")
        self._tab_widget.addTab(self._scanner_tab, "Scanner")
        self._tab_widget.addTab(self._ai_tab, "AI Analysis")
        self.setCentralWidget(self._tab_widget)

        # Watchlist dock on the left
        self._watchlist_panel = WatchlistPanel(self._db, parent=self)
        self._watchlist_panel.ticker_selected.connect(self._on_watchlist_ticker_selected)
        self._watchlist_dock = QtWidgets.QDockWidget("Watchlist", self)
        self._watchlist_dock.setWidget(self._watchlist_panel)
        self._watchlist_dock.setAllowedAreas(
            QtCore.Qt.DockWidgetArea.LeftDockWidgetArea
            | QtCore.Qt.DockWidgetArea.RightDockWidgetArea
        )
        self._watchlist_dock.setMinimumWidth(160)
        self.addDockWidget(QtCore.Qt.DockWidgetArea.LeftDockWidgetArea, self._watchlist_dock)

        # News dock on the right
        self._news_sidebar = NewsSidebar(self._news_fetcher, parent=self)
        self._news_dock = QtWidgets.QDockWidget("News", self)
        self._news_dock.setWidget(self._news_sidebar)
        self._news_dock.setAllowedAreas(
            QtCore.Qt.DockWidgetArea.RightDockWidgetArea
            | QtCore.Qt.DockWidgetArea.LeftDockWidgetArea
        )
        self._news_dock.setMinimumWidth(260)
        self.addDockWidget(QtCore.Qt.DockWidgetArea.RightDockWidgetArea, self._news_dock)

        # Compare dock at the bottom (hidden by default)
        self._compare_panel = ComparePanel(self._config, self._dm, parent=self)
        self._compare_panel.sync_with(self._chart)
        self._compare_dock = QtWidgets.QDockWidget("Compare", self)
        self._compare_dock.setWidget(self._compare_panel)
        self._compare_dock.setAllowedAreas(
            QtCore.Qt.DockWidgetArea.BottomDockWidgetArea
            | QtCore.Qt.DockWidgetArea.RightDockWidgetArea
        )
        self._compare_dock.setMinimumHeight(180)
        self._compare_dock.visibilityChanged.connect(
            lambda visible: self._compare_action.setChecked(visible)
        )
        self.addDockWidget(QtCore.Qt.DockWidgetArea.BottomDockWidgetArea, self._compare_dock)
        self._compare_dock.hide()

    # ─────────────────────────── data loading ────────────────────────────────

    def load_ticker(
        self,
        ticker: str,
        start: date | None = None,
        end: date | None = None,
        refresh: bool = False,
    ) -> bool:
        """Load (or refresh) data for *ticker* and render all panels.

        Returns:
            ``True`` on success, ``False`` if data could not be loaded.
        """
        ticker = ticker.strip().upper()
        if not ticker:
            return False

        start = start or _qdate_to_date(self._start_date.date())
        end = end or _qdate_to_date(self._end_date.date())

        self.statusBar().showMessage(f"Loading {ticker}…")

        try:
            daily = self._dm.get_history(
                ticker, start=start, end=end, timeframe="D", refresh=refresh
            )
        except DataManagerError as exc:
            self.statusBar().showMessage(f"Error: {exc}")
            logger.warning("Failed to load %s: %s", ticker, exc)
            return False
        except Exception as exc:  # noqa: BLE001
            self.statusBar().showMessage(f"Unexpected error: {exc}")
            logger.exception("Unexpected error loading %s", ticker)
            return False

        self._daily_df = daily
        self._current_ticker = ticker
        self._chart.clear_overlays()
        self._chart.remove_bband_overlay()
        self._chart.remove_vwap_overlay()
        self._chart.remove_fvg_overlay()
        self._chart.clear_ai_signals()
        self._bb_btn.setChecked(False)
        self._vwap_btn.setChecked(False)
        self._fvg_btn.setChecked(False)
        self._active_mas.clear()
        self._apply_timeframe()
        self._drawing_manager.load(ticker, self._timeframe)
        self._ai_tab.set_chart_data(daily, ticker)
        self.setWindowTitle(f"StockTool — {ticker}")
        self.statusBar().showMessage(
            f"{ticker}  |  {len(daily)} bars  |  "
            f"{daily.index[0].date()} → {daily.index[-1].date()}"
        )
        return True

    def _apply_timeframe(self) -> None:
        if self._daily_df is None:
            return
        resampled = self._dm.resample(self._daily_df, self._timeframe)
        self._chart.set_data(resampled)
        self._indicator_panel.set_data(resampled)
        if self._fvg_btn.isChecked():
            self._render_fvg(resampled)

    # ─────────────────────────── toolbar slots ────────────────────────────────

    def _on_symbol_entered(self) -> None:
        ticker = self._symbol_edit.text().strip().upper()
        if not ticker:
            return
        has_cache = csv_store.exists(ticker, self._config.data.price_dir)
        if self.load_ticker(ticker, refresh=not has_cache):
            self._news_sidebar.load(ticker)

    def _on_market_changed(self, market: str) -> None:
        tickers = self._registry.all_tickers(market)
        model = QtCore.QStringListModel(tickers, self._completer)
        self._completer.setModel(model)

    def _on_timeframe_clicked(self, tf: str) -> None:
        self._timeframe = tf
        self._apply_timeframe()
        if self._current_ticker:
            self._drawing_manager.load(self._current_ticker, tf)

    def _on_download_clicked(self) -> None:
        ticker = self._symbol_edit.text().strip().upper()
        if not ticker:
            self.statusBar().showMessage("Enter a symbol first")
            return
        if self.load_ticker(ticker, refresh=True):
            self._news_sidebar.load(ticker)

    def _on_add_ma(self) -> None:
        if self._daily_df is None:
            self.statusBar().showMessage("Load a symbol first")
            return
        ma_type = self._ma_type_combo.currentText()
        period = self._ma_period_spin.value()
        name = f"{ma_type}_{period}"
        if name in self._active_mas:
            self.statusBar().showMessage(f"{name} is already on the chart")
            return

        resampled = self._dm.resample(self._daily_df, self._timeframe)
        close = resampled["Close"]
        match ma_type:
            case "SMA":
                series = sma(close, period)
            case "EMA":
                series = ema(close, period)
            case _:
                series = wma(close, period)

        try:
            self._chart.add_ma_overlay(name, series)
            self._active_mas[name] = ma_type
            self.statusBar().showMessage(f"Added {name}")
        except Exception as exc:  # noqa: BLE001
            self.statusBar().showMessage(f"Could not add MA: {exc}")

    def _on_clear_mas(self) -> None:
        self._chart.clear_overlays()
        self._active_mas.clear()
        self.statusBar().showMessage("Cleared all MA overlays")

    def _on_chart_mode_clicked(self, mode: str) -> None:
        self._chart.set_mode(mode)

    def _on_vwap_toggled(self, checked: bool) -> None:
        if checked:
            if self._daily_df is None:
                self.statusBar().showMessage("Load a symbol first")
                self._vwap_btn.setChecked(False)
                return
            import core.indicator_engine as ie
            resampled = self._dm.resample(self._daily_df, self._timeframe)
            vwap_series = ie.vwap(
                resampled["High"], resampled["Low"],
                resampled["Close"], resampled["Volume"],
            )
            try:
                self._chart.add_vwap_overlay(vwap_series)
            except Exception as exc:  # noqa: BLE001
                self.statusBar().showMessage(f"Could not add VWAP: {exc}")
                self._vwap_btn.setChecked(False)
        else:
            self._chart.remove_vwap_overlay()

    def _on_bb_toggled(self, checked: bool) -> None:
        if checked:
            if self._daily_df is None:
                self.statusBar().showMessage("Load a symbol first")
                self._bb_btn.setChecked(False)
                return
            import core.indicator_engine as ie
            resampled = self._dm.resample(self._daily_df, self._timeframe)
            bb = ie.bband(
                resampled["Close"],
                self._config.indicators.bb_period,
                self._config.indicators.bb_std,
            )
            try:
                self._chart.add_bband_overlay(bb)
            except Exception as exc:  # noqa: BLE001
                self.statusBar().showMessage(f"Could not add BB: {exc}")
                self._bb_btn.setChecked(False)
        else:
            self._chart.remove_bband_overlay()

    def _on_fvg_toggled(self, checked: bool) -> None:
        if checked:
            if self._daily_df is None:
                self.statusBar().showMessage("Load a symbol first")
                self._fvg_btn.setChecked(False)
                return
            resampled = self._dm.resample(self._daily_df, self._timeframe)
            self._render_fvg(resampled)
        else:
            self._chart.remove_fvg_overlay()

    def _render_fvg(self, df) -> None:
        import core.indicator_engine as ie
        gaps = ie.fvg(df)
        self._chart.add_fvg_overlay(gaps)
        self.statusBar().showMessage(
            f"FVG: {sum(1 for g in gaps if g['kind'] == 'bull')} bullish, "
            f"{sum(1 for g in gaps if g['kind'] == 'bear')} bearish unfilled zones"
        )

    def _toggle_indicator(self, indicator: str, checked: bool) -> None:
        if checked:
            try:
                self._indicator_panel.add_subchart(indicator)
                if self._daily_df is not None:
                    resampled = self._dm.resample(self._daily_df, self._timeframe)
                    self._indicator_panel._charts[indicator].set_data(resampled)
            except IndicatorPanelError as exc:
                self.statusBar().showMessage(str(exc))
                self._indicator_btns[indicator].setChecked(False)
                if indicator in self._indicator_actions:
                    self._indicator_actions[indicator].setChecked(False)
        else:
            self._indicator_panel.remove_subchart(indicator)

        if indicator in self._indicator_actions:
            self._indicator_actions[indicator].setChecked(checked)

    def _on_indicator_menu_toggled(self) -> None:
        action: QtGui.QAction = self.sender()  # type: ignore[assignment]
        indicator = action.data()
        checked = action.isChecked()
        self._indicator_btns[indicator].setChecked(checked)
        self._toggle_indicator(indicator, checked)

    def _on_drawing_mode_clicked(self, mode_key: str) -> None:
        from ui.drawing_tools import DrawingMode
        mode = DrawingMode(mode_key)
        self._drawing_manager.set_mode(mode)

    def _on_delete_drawings(self) -> None:
        if not self._current_ticker:
            self.statusBar().showMessage("No symbol loaded")
            return
        self._drawing_manager.delete_selected(self._current_ticker, self._timeframe)
        self.statusBar().showMessage(
            f"Deleted all drawings for {self._current_ticker}/{self._timeframe}"
        )

    def _on_export(self) -> None:
        if self._daily_df is None:
            QtWidgets.QMessageBox.information(self, "Export", "No chart to export.")
            return
        today = date.today().strftime("%Y%m%d")
        default_name = (
            self._config.data.export_dir
            / f"{self._current_ticker}_{self._timeframe}_{today}.png"
        )
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export Chart", str(default_name), "PNG Images (*.png)"
        )
        if path:
            try:
                self._chart.export_png(path)
                self.statusBar().showMessage(f"Export saved → {path}")
            except Exception as exc:
                QtWidgets.QMessageBox.critical(self, "Export Error", str(exc))

    def _on_add_to_watchlist(self) -> None:
        if not self._current_ticker:
            self.statusBar().showMessage("Load a symbol first")
            return
        self._db.add_to_watchlist(self._current_ticker)
        self._watchlist_panel.refresh()
        self._watchlist_panel.select_ticker(self._current_ticker)
        self.statusBar().showMessage(f"Added {self._current_ticker} to watchlist")

    def _on_watchlist_ticker_selected(self, ticker: str) -> None:
        self._symbol_edit.setText(ticker)
        self.load_ticker(ticker)

    def _on_scanner_ticker_selected(self, symbol: str) -> None:
        """Switch to the Chart tab and load the symbol selected in the Scanner."""
        self._tab_widget.setCurrentIndex(0)
        self._symbol_edit.setText(symbol)
        self.load_ticker(symbol)

    def _on_ai_show_chart(self, bars: list) -> None:
        """Switch to Chart tab and highlight AI-detected signal bars."""
        self._tab_widget.setCurrentIndex(0)
        if bars:
            self._chart.mark_ai_signals(bars)
            self.statusBar().showMessage(
                f"Showing {len(bars)} signal occurrence(s) on chart (orange dotted lines)"
            )
        else:
            self._chart.clear_ai_signals()
            self.statusBar().showMessage("AI signal markers cleared")

    def _on_settings(self) -> None:
        from ui.settings_dialog import SettingsDialog
        dlg = SettingsDialog(self._config, parent=self)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted and dlg.updated_config:
            self._config = dlg.updated_config
            self.statusBar().showMessage("Settings saved")

    def _on_export_data(self) -> None:
        """Export the current resampled OHLCV data to CSV or Excel."""
        if self._daily_df is None:
            QtWidgets.QMessageBox.information(self, "Export Data", "No data loaded.")
            return
        resampled = self._dm.resample(self._daily_df, self._timeframe)
        today_str = date.today().strftime("%Y%m%d")
        default_name = (
            self._config.data.export_dir
            / f"{self._current_ticker}_{self._timeframe}_{today_str}.csv"
        )
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export Data", str(default_name),
            "CSV Files (*.csv);;Excel Files (*.xlsx)",
        )
        if not path:
            return
        try:
            if path.lower().endswith(".xlsx"):
                resampled.to_excel(path, engine="openpyxl")
            else:
                if not path.lower().endswith(".csv"):
                    path += ".csv"
                resampled.to_csv(path)
            self.statusBar().showMessage(f"Data exported → {path}")
        except Exception as exc:  # noqa: BLE001
            QtWidgets.QMessageBox.critical(self, "Export Error", str(exc))

    def _on_compare_toggled(self, checked: bool = False) -> None:
        """Show or hide the Compare panel dock."""
        self._compare_dock.setVisible(not self._compare_dock.isVisible())

    # ─────────────────────────── keyboard shortcuts ───────────────────────────

    def _build_shortcuts(self) -> None:
        from PyQt6.QtGui import QKeySequence, QShortcut
        _shortcut_map = [
            ("D",       lambda: self._on_timeframe_clicked("D")),
            ("W",       lambda: self._on_timeframe_clicked("W")),
            ("M",       lambda: self._on_timeframe_clicked("M")),
            ("Q",       lambda: self._on_timeframe_clicked("Q")),
            ("Y",       lambda: self._on_timeframe_clicked("Y")),
            ("C",       lambda: self._on_chart_mode_clicked("candle")),
            ("L",       lambda: self._on_chart_mode_clicked("line")),
            ("Ctrl+E",  self._on_export),
            ("Escape",  lambda: self._on_drawing_mode_clicked("none")),
            ("Del",     self._on_delete_drawings),
        ]
        self._shortcuts: list[QShortcut] = []
        for key, slot in _shortcut_map:
            sc = QShortcut(QKeySequence(key), self)
            sc.activated.connect(slot)
            self._shortcuts.append(sc)

    # ─────────────────────────── public helpers ───────────────────────────────

    @property
    def chart(self) -> ChartPanel:
        return self._chart

    @property
    def indicator_panel(self) -> IndicatorPanel:
        return self._indicator_panel

    @property
    def current_ticker(self) -> str:
        return self._current_ticker

    @property
    def timeframe(self) -> str:
        return self._timeframe

    @property
    def drawing_manager(self):
        return self._drawing_manager

    @property
    def news_sidebar(self):
        return self._news_sidebar

    @property
    def watchlist_panel(self):
        return self._watchlist_panel

    @property
    def compare_panel(self):
        return self._compare_panel


# ─────────────────────────── helpers ─────────────────────────────────────────

def _vsep() -> QtWidgets.QFrame:
    sep = QtWidgets.QFrame()
    sep.setFrameShape(QtWidgets.QFrame.Shape.VLine)
    sep.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
    return sep


def _qdate_to_date(qdate: QtCore.QDate) -> date:
    return date(qdate.year(), qdate.month(), qdate.day())
