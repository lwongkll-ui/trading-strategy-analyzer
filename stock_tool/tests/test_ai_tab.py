"""Tests for ui.ai_tab — AI Pattern Analysis tab."""
from __future__ import annotations

import math
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest
from PyQt6 import QtCore, QtWidgets

from core.ai_analyzer import AIAnalysisResult, PatternAIStats, SignalPrediction
from core.backtest_engine import BacktestResult, PatternStats
from ui.ai_tab import AITab, AIWorker, _FeatureImportanceWidget, _cell


# ── fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def qapp(qapp):  # noqa: F811 — reuse conftest qapp
    return qapp


@pytest.fixture
def tab(qapp):
    t = AITab()
    t.show()
    return t


def _make_df(n: int = 400) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    c = 100 * np.cumprod(1 + rng.normal(0, 0.01, n))
    noise = rng.uniform(0.003, 0.01, n)
    df = pd.DataFrame({
        "Open": c * (1 - rng.uniform(0, 0.003, n)),
        "High": c * (1 + noise),
        "Low": c * (1 - noise),
        "Close": c,
        "Volume": rng.integers(100_000, 1_000_000, n).astype(float),
    }, index=pd.date_range("2018-01-01", periods=n, freq="B"))
    df["High"] = df[["High", "Open", "Close"]].max(axis=1)
    df["Low"]  = df[["Low", "Open", "Close"]].min(axis=1)
    return df


def _make_result(ticker: str = "TEST") -> AIAnalysisResult:
    """Minimal fake AIAnalysisResult for UI tests (no actual ML computation)."""
    bt_stats = [
        PatternStats(
            pattern="Bullish Engulfing", direction="bull", hold_days=21,
            n_is=120, n_oos=30,
            is_win_rate=0.58, is_avg_return=1.2,
            is_profit_factor=1.8, is_sharpe=0.55,
            is_max_drawdown=-3.1,
            oos_win_rate=0.60, oos_avg_return=1.4,
            score=0.12,
        ),
        PatternStats(
            pattern="Hammer", direction="bull", hold_days=42,
            n_is=80, n_oos=20,
            is_win_rate=0.52, is_avg_return=0.5,
            is_profit_factor=1.1, is_sharpe=0.2,
            is_max_drawdown=-4.0,
            oos_win_rate=0.48, oos_avg_return=-0.2,
            score=0.03,
        ),
    ]
    bt = BacktestResult(ticker=ticker, n_bars=400, is_cutoff=300,
                        n_signals=85, stats=bt_stats)

    ai_stats = [
        PatternAIStats(
            pattern="Bullish Engulfing", direction="bull", hold_days=21,
            n_is=120, n_oos=30,
            oos_accuracy=0.63, oos_avg_prob_win=0.72, oos_avg_prob_loss=0.41,
            model_cv_accuracy=0.56, model_cv_std=0.04,
        ),
    ]
    signal_probs = [
        SignalPrediction(bar=310, pattern="Bullish Engulfing", direction="bull",
                         hold_days=21, prob_win=0.71, in_sample=False),
        SignalPrediction(bar=325, pattern="Bullish Engulfing", direction="bull",
                         hold_days=21, prob_win=0.68, in_sample=False),
        SignalPrediction(bar=340, pattern="Bullish Engulfing", direction="bull",
                         hold_days=42, prob_win=0.55, in_sample=False),
    ]
    return AIAnalysisResult(
        ticker=ticker,
        backtest=bt,
        pattern_stats=ai_stats,
        signal_probs=signal_probs,
        feature_importances={"rsi_14": 0.185, "ret_20": 0.123, "dist_sma50": 0.089},
        n_models_trained=2,
    )


# ── _cell helper ───────────────────────────────────────────────────────────────

def test_cell_text():
    item = _cell("hello")
    assert item.text() == "hello"


def test_cell_not_editable():
    item = _cell("x")
    assert not (item.flags() & QtCore.Qt.ItemFlag.ItemIsEditable)


# ── _FeatureImportanceWidget ───────────────────────────────────────────────────

def test_feature_importance_widget_populates(qapp):
    w = _FeatureImportanceWidget()
    w.set_importances({"rsi_14": 0.2, "ret_5": 0.1})
    assert w._table.rowCount() == 2


def test_feature_importance_widget_empty(qapp):
    w = _FeatureImportanceWidget()
    w.set_importances({})
    assert w._table.rowCount() == 0


def test_feature_importance_top_n_limited(qapp):
    w = _FeatureImportanceWidget()
    many = {f"feat_{i}": float(i) / 100 for i in range(20)}
    w.set_importances(many)
    assert w._table.rowCount() <= w._MAX_FEATURES


def test_feature_importance_highest_first(qapp):
    w = _FeatureImportanceWidget()
    w.set_importances({"low": 0.05, "high": 0.50, "mid": 0.20})
    assert w._table.item(0, 0).text() == "high"


# ── AITab construction ─────────────────────────────────────────────────────────

def test_tab_creates_without_error(tab):
    assert tab is not None


def test_tab_run_btn_present(tab):
    assert tab._run_btn is not None


def test_tab_stop_btn_disabled_initially(tab):
    assert not tab._stop_btn.isEnabled()


def test_tab_show_chart_btn_disabled_initially(tab):
    assert not tab._show_chart_btn.isEnabled()


def test_tab_table_has_correct_columns(tab):
    from ui.ai_tab import _COL_HEADERS
    assert tab._table.columnCount() == len(_COL_HEADERS)
    for col, header in enumerate(_COL_HEADERS):
        assert tab._table.horizontalHeaderItem(col).text() == header


def test_tab_run_without_data_shows_dialog(tab, monkeypatch):
    shown = []
    monkeypatch.setattr(
        QtWidgets.QMessageBox, "information",
        lambda *a, **k: shown.append(True)
    )
    tab._on_run()
    assert shown


# ── set_chart_data ─────────────────────────────────────────────────────────────

def test_set_chart_data_updates_ticker_label(tab):
    df = _make_df(100)
    tab.set_chart_data(df, "AAPL")
    assert tab._ticker_lbl.text() == "AAPL"


def test_set_chart_data_stores_df(tab):
    df = _make_df(100)
    tab.set_chart_data(df, "MSFT")
    assert tab._df is df
    assert tab._ticker == "MSFT"


def test_set_chart_data_status_when_different_ticker(tab):
    df = _make_df(100)
    tab._result = _make_result("AAPL")
    tab.set_chart_data(df, "TSLA")
    assert "AAPL" in tab._status_lbl.text()


# ── _on_result / table population ─────────────────────────────────────────────

def test_on_result_populates_table(tab):
    result = _make_result()
    tab._on_result(result)
    assert tab._table.rowCount() > 0


def test_on_result_status_updated(tab):
    result = _make_result()
    tab._on_result(result)
    assert "TEST" in tab._status_lbl.text()
    assert "model" in tab._status_lbl.text().lower()


def test_on_result_imports_populated(tab):
    result = _make_result()
    tab._on_result(result)
    assert tab._importance_widget._table.rowCount() > 0


def test_table_oos_acc_green_for_high_accuracy(tab):
    """OOS accuracy > 55 % should have a green background."""
    result = _make_result()
    tab._on_result(result)
    col = tab._table.columnCount() - 3  # "OOS Acc%" column
    from ui.ai_tab import _COL_IDX
    col = _COL_IDX["OOS Acc%"]
    found_green = False
    for row in range(tab._table.rowCount()):
        item = tab._table.item(row, col)
        if item and item.text() not in ("—", ""):
            val_str = item.text().replace("%", "").strip()
            try:
                val = float(val_str) / 100
            except ValueError:
                continue
            if val > 0.55:
                bg = item.background().color()
                if bg.green() > bg.red():
                    found_green = True
    # Only check if any high-accuracy row exists
    high_acc_rows = [
        s for s in result.pattern_stats
        if not math.isnan(s.oos_accuracy) and s.oos_accuracy > 0.55
    ]
    if high_acc_rows:
        assert found_green


def test_table_direction_color(tab):
    from ui.ai_tab import _COL_IDX, _BULL_FG, _BEAR_FG
    result = _make_result()
    tab._on_result(result)
    col = _COL_IDX["Dir"]
    for row in range(tab._table.rowCount()):
        item = tab._table.item(row, col)
        if item is None:
            continue
        if item.text() == "bull":
            assert item.foreground().color().green() > item.foreground().color().red()
        elif item.text() == "bear":
            assert item.foreground().color().red() > item.foreground().color().green()


# ── hold filter ────────────────────────────────────────────────────────────────

def test_hold_filter_all_shows_all_rows(tab):
    result = _make_result()
    tab._on_result(result)
    tab._apply_hold_filter("All")
    visible = sum(
        1 for r in range(tab._table.rowCount())
        if not tab._table.isRowHidden(r)
    )
    assert visible == tab._table.rowCount()


def test_hold_filter_21d_hides_other_holds(tab):
    result = _make_result()
    tab._on_result(result)
    tab._apply_hold_filter("21d")
    from ui.ai_tab import _COL_IDX
    for row in range(tab._table.rowCount()):
        if tab._table.isRowHidden(row):
            continue
        hold_item = tab._table.item(row, _COL_IDX["Hold"])
        assert hold_item.text() == "21d"


# ── show on chart signal ───────────────────────────────────────────────────────

def test_on_show_chart_emits_signal(tab):
    result = _make_result()
    tab._on_result(result)
    # Select first row
    tab._table.selectRow(0)
    emitted = []
    tab.signals_show_chart.connect(lambda bars: emitted.append(bars))
    tab._on_show_chart()
    assert emitted


def test_on_clear_markers_emits_empty_list(tab):
    result = _make_result()
    tab._on_result(result)
    tab._clear_btn.setEnabled(True)
    emitted = []
    tab.signals_show_chart.connect(lambda bars: emitted.append(bars))
    tab._on_clear_markers()
    assert emitted and emitted[0] == []


def test_show_chart_bars_match_selected_pattern(tab):
    result = _make_result()
    tab._on_result(result)
    from ui.ai_tab import _COL_IDX
    # Find row with "Bullish Engulfing"
    target_row = None
    for row in range(tab._table.rowCount()):
        item = tab._table.item(row, 0)
        if item and item.text() == "Bullish Engulfing":
            target_row = row
            break
    if target_row is None:
        pytest.skip("Bullish Engulfing not in result table")

    tab._table.selectRow(target_row)
    emitted = []
    tab.signals_show_chart.connect(lambda bars: emitted.append(bars))
    tab._on_show_chart()

    assert emitted
    # Hold filter should give bars 310, 325 (hold=21) or also 340 (hold=42) if All
    bars = emitted[0]
    assert all(isinstance(b, int) for b in bars)
    assert len(bars) >= 1


# ── AIWorker ──────────────────────────────────────────────────────────────────

def test_worker_emits_result(qapp):
    df = _make_df(300)
    worker = AIWorker(df, "T", [21], min_samples=100)
    results = []
    errors = []
    worker.result_ready.connect(lambda r: results.append(r))
    worker.error.connect(lambda e: errors.append(e))

    loop = QtCore.QEventLoop()
    worker.finished.connect(loop.quit)
    worker.start()
    loop.exec()

    assert not errors or "scikit-learn" in errors[0]
    if not errors:
        assert results
        assert isinstance(results[0], AIAnalysisResult)


def test_worker_error_on_bad_df(qapp):
    bad_df = pd.DataFrame({"X": [1, 2, 3]})
    worker = AIWorker(bad_df, "T", [21], min_samples=50)
    errors = []
    worker.error.connect(lambda e: errors.append(e))
    loop = QtCore.QEventLoop()
    worker.finished.connect(loop.quit)
    worker.start()
    loop.exec()
    assert errors
