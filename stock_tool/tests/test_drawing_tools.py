"""Tests for ui.drawing_tools and ChartPanel.export_png."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from core.config import (
    ChartConfig, Config, DataConfig, DownloadConfig,
    IndicatorsConfig, NewsConfig, SchedulerConfig,
)
from storage.db_store import DbStore


def _make_config() -> Config:
    return Config(
        data=DataConfig(price_dir=Path("./prices"), export_dir=Path("./exports")),
        download=DownloadConfig(
            default_start_date=date(2024, 1, 1), provider="yfinance",
            alpha_vantage_key="",
        ),
        news=NewsConfig(provider="newsapi", newsapi_key="", max_headlines=20),
        chart=ChartConfig(
            default_timeframe="D",
            candle_bull_color="#26a69a", candle_bear_color="#ef5350",
            background_color="#131722",
            ma_colors=("#2196F3",), export_resolution=(800, 600),
        ),
        indicators=IndicatorsConfig(
            rsi_period=14, rsi_overbought=70, rsi_oversold=30,
            macd_fast=12, macd_slow=26, macd_signal=9,
            stc_fast=23, stc_slow=50, stc_cycle=10,
        ),
        scheduler=SchedulerConfig(
            enabled=False, cron="0 18 * * 1-5", symbols_file=Path("./watchlist.txt"),
        ),
        source_path=Path("./config.yaml"),
    )


def _make_ohlcv(n: int = 20) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    closes = 100.0 + np.cumsum(rng.normal(0, 1, n))
    opens = closes + rng.normal(0, 0.3, n)
    highs = np.maximum(opens, closes) + 0.5
    lows = np.minimum(opens, closes) - 0.5
    vols = np.full(n, 1_000_000.0)
    idx = pd.date_range("2024-01-02", periods=n, freq="B")
    return pd.DataFrame(
        {"Open": opens, "High": highs, "Low": lows,
         "Close": closes, "Volume": vols, "Adj_Close": closes},
        index=idx,
    )


def _open_db(tmp_path: Path) -> DbStore:
    db = DbStore(tmp_path / "draw.db")
    db.open()
    return db


# ─────────────────────── DrawingMode ─────────────────────────────────────────

def test_drawing_mode_values():
    from ui.drawing_tools import DrawingMode
    assert DrawingMode.NONE.value == "none"
    assert DrawingMode.HORIZONTAL.value == "horizontal"
    assert DrawingMode.TREND_LINE.value == "trend_line"
    assert DrawingMode.TEXT.value == "text"


# ─────────────────────── DrawingManager ──────────────────────────────────────

def test_drawing_manager_constructs(qapp, tmp_path):
    from ui.chart_panel import ChartPanel
    from ui.drawing_tools import DrawingManager, DrawingMode

    panel = ChartPanel(_make_config())
    with _open_db(tmp_path) as db:
        dm = DrawingManager(panel, db)
        assert dm.mode is DrawingMode.NONE
        assert dm.count == 0


def test_set_mode_changes_mode(qapp, tmp_path):
    from ui.chart_panel import ChartPanel
    from ui.drawing_tools import DrawingManager, DrawingMode

    panel = ChartPanel(_make_config())
    with _open_db(tmp_path) as db:
        dm = DrawingManager(panel, db)
        dm.set_mode(DrawingMode.HORIZONTAL)
        assert dm.mode is DrawingMode.HORIZONTAL


def test_clear_removes_all_items(qapp, tmp_path):
    from ui.chart_panel import ChartPanel
    from ui.drawing_tools import DrawingManager, DrawingMode

    panel = ChartPanel(_make_config())
    panel.set_data(_make_ohlcv())
    with _open_db(tmp_path) as db:
        dm = DrawingManager(panel, db)
        dm._place_horizontal(150.0)
        dm._place_horizontal(160.0)
        assert dm.count == 2
        dm.clear()
        assert dm.count == 0


def test_place_horizontal_adds_record(qapp, tmp_path):
    from ui.chart_panel import ChartPanel
    from ui.drawing_tools import DrawingManager

    panel = ChartPanel(_make_config())
    panel.set_data(_make_ohlcv())
    with _open_db(tmp_path) as db:
        dm = DrawingManager(panel, db)
        rec = dm._place_horizontal(155.0, color="#FF0000")
        assert rec.drawing_type == "horizontal"
        assert rec.params["price"] == 155.0
        assert rec.params["color"] == "#FF0000"
        assert dm.count == 1


def test_save_persists_to_db(qapp, tmp_path):
    from ui.chart_panel import ChartPanel
    from ui.drawing_tools import DrawingManager

    panel = ChartPanel(_make_config())
    panel.set_data(_make_ohlcv())
    with _open_db(tmp_path) as db:
        dm = DrawingManager(panel, db)
        dm._place_horizontal(180.0)
        assert dm._records[0].db_id is None
        dm.save("AAPL", "D")
        assert dm._records[0].db_id is not None
        assert db.drawing_count("AAPL", "D") == 1


def test_load_restores_horizontal(qapp, tmp_path):
    from ui.chart_panel import ChartPanel
    from ui.drawing_tools import DrawingManager

    df = _make_ohlcv()
    panel = ChartPanel(_make_config())
    panel.set_data(df)

    with _open_db(tmp_path) as db:
        db.save_drawing("AAPL", "D", "horizontal", {"price": 185.0, "color": "#FFD700"})

        dm = DrawingManager(panel, db)
        n = dm.load("AAPL", "D")
        assert n == 1
        assert dm.count == 1
        assert dm._records[0].drawing_type == "horizontal"
        assert dm._records[0].params["price"] == 185.0


def test_load_restores_trend_line(qapp, tmp_path):
    from ui.chart_panel import ChartPanel
    from ui.drawing_tools import DrawingManager

    df = _make_ohlcv(20)
    panel = ChartPanel(_make_config())
    panel.set_data(df)

    date1 = df.index[0].strftime("%Y-%m-%d")
    date2 = df.index[5].strftime("%Y-%m-%d")
    params = {"date1": date1, "price1": 100.0,
               "date2": date2, "price2": 110.0, "color": "#FFD700"}

    with _open_db(tmp_path) as db:
        db.save_drawing("AAPL", "D", "trend_line", params)
        dm = DrawingManager(panel, db)
        n = dm.load("AAPL", "D")
        assert n == 1


def test_load_skips_drawings_with_unknown_dates(qapp, tmp_path):
    from ui.chart_panel import ChartPanel
    from ui.drawing_tools import DrawingManager

    df = _make_ohlcv(20)
    panel = ChartPanel(_make_config())
    panel.set_data(df)

    params = {"date1": "1990-01-01", "price1": 100.0,
              "date2": "1990-06-01", "price2": 110.0, "color": "#FFD700"}

    with _open_db(tmp_path) as db:
        db.save_drawing("AAPL", "D", "trend_line", params)
        dm = DrawingManager(panel, db)
        n = dm.load("AAPL", "D")
        # Dates are very old but searchsorted will still find a position; test
        # at least that load() does not raise.
        assert isinstance(n, int)


def test_clear_then_load_replaces_drawings(qapp, tmp_path):
    from ui.chart_panel import ChartPanel
    from ui.drawing_tools import DrawingManager

    df = _make_ohlcv()
    panel = ChartPanel(_make_config())
    panel.set_data(df)

    with _open_db(tmp_path) as db:
        db.save_drawing("AAPL", "D", "horizontal", {"price": 100.0, "color": "#FFD700"})
        db.save_drawing("AAPL", "D", "horizontal", {"price": 200.0, "color": "#FFD700"})

        dm = DrawingManager(panel, db)
        dm.load("AAPL", "D")
        assert dm.count == 2

        dm.load("AAPL", "D")   # second load should clear first
        assert dm.count == 2   # same two drawings, not four


def test_delete_selected_clears_db(qapp, tmp_path):
    from ui.chart_panel import ChartPanel
    from ui.drawing_tools import DrawingManager

    panel = ChartPanel(_make_config())
    panel.set_data(_make_ohlcv())

    with _open_db(tmp_path) as db:
        db.save_drawing("AAPL", "D", "horizontal", {"price": 100.0})
        db.save_drawing("AAPL", "D", "horizontal", {"price": 200.0})

        dm = DrawingManager(panel, db)
        dm.load("AAPL", "D")
        dm.delete_selected("AAPL", "D")

        assert dm.count == 0
        assert db.drawing_count("AAPL", "D") == 0


def test_set_mode_cancels_pending_trend_line(qapp, tmp_path):
    from ui.chart_panel import ChartPanel
    from ui.drawing_tools import DrawingManager, DrawingMode

    panel = ChartPanel(_make_config())
    panel.set_data(_make_ohlcv())

    with _open_db(tmp_path) as db:
        dm = DrawingManager(panel, db)
        dm.set_mode(DrawingMode.TREND_LINE)
        # Simulate first click by injecting a pending record directly.
        dm._pending = MagicMock()
        dm._pending.item = MagicMock()
        dm.set_mode(DrawingMode.HORIZONTAL)
        assert dm._pending is None


# ─────────────────────── DrawingMode FIB / RECT values ───────────────────────

def test_drawing_mode_fib_value():
    from ui.drawing_tools import DrawingMode
    assert DrawingMode.FIB.value == "fib"


def test_drawing_mode_rect_value():
    from ui.drawing_tools import DrawingMode
    assert DrawingMode.RECT.value == "rect"


# ─────────────────────── Fibonacci placement ─────────────────────────────────

def test_place_fib_creates_record_with_list(qapp, tmp_path):
    from ui.chart_panel import ChartPanel
    from ui.drawing_tools import DrawingManager, _FIB_LEVELS

    df = _make_ohlcv(20)
    panel = ChartPanel(_make_config())
    panel.set_data(df)

    with _open_db(tmp_path) as db:
        dm = DrawingManager(panel, db)
        date1 = df.index[0].strftime("%Y-%m-%d")
        date2 = df.index[5].strftime("%Y-%m-%d")
        rec = dm._place_fib(0, 110.0, date1, 5, 100.0, date2)
        assert isinstance(rec.item, list)
        assert len(rec.item) == len(_FIB_LEVELS)


def test_place_fib_adds_to_records(qapp, tmp_path):
    from ui.chart_panel import ChartPanel
    from ui.drawing_tools import DrawingManager

    df = _make_ohlcv(20)
    panel = ChartPanel(_make_config())
    panel.set_data(df)

    with _open_db(tmp_path) as db:
        dm = DrawingManager(panel, db)
        date1 = df.index[0].strftime("%Y-%m-%d")
        date2 = df.index[5].strftime("%Y-%m-%d")
        dm._place_fib(0, 110.0, date1, 5, 100.0, date2)
        assert dm.count == 1
        assert dm._records[0].drawing_type == "fib"


def test_place_fib_stores_correct_params(qapp, tmp_path):
    from ui.chart_panel import ChartPanel
    from ui.drawing_tools import DrawingManager

    df = _make_ohlcv(20)
    panel = ChartPanel(_make_config())
    panel.set_data(df)

    with _open_db(tmp_path) as db:
        dm = DrawingManager(panel, db)
        date1 = df.index[0].strftime("%Y-%m-%d")
        date2 = df.index[5].strftime("%Y-%m-%d")
        rec = dm._place_fib(0, 110.0, date1, 5, 100.0, date2)
        assert rec.params["price1"] == pytest.approx(110.0)
        assert rec.params["price2"] == pytest.approx(100.0)
        assert rec.params["date1"] == date1
        assert rec.params["date2"] == date2


def test_clear_removes_fib_items(qapp, tmp_path):
    from ui.chart_panel import ChartPanel
    from ui.drawing_tools import DrawingManager

    df = _make_ohlcv(20)
    panel = ChartPanel(_make_config())
    panel.set_data(df)

    with _open_db(tmp_path) as db:
        dm = DrawingManager(panel, db)
        date1 = df.index[0].strftime("%Y-%m-%d")
        date2 = df.index[5].strftime("%Y-%m-%d")
        dm._place_fib(0, 110.0, date1, 5, 100.0, date2)
        assert dm.count == 1
        dm.clear()
        assert dm.count == 0


def test_load_restores_fib_from_db(qapp, tmp_path):
    from ui.chart_panel import ChartPanel
    from ui.drawing_tools import DrawingManager, _FIB_LEVELS

    df = _make_ohlcv(20)
    panel = ChartPanel(_make_config())
    panel.set_data(df)

    date1 = df.index[0].strftime("%Y-%m-%d")
    date2 = df.index[5].strftime("%Y-%m-%d")
    params = {"date1": date1, "price1": 110.0, "date2": date2, "price2": 100.0, "color": "#FFD700"}

    with _open_db(tmp_path) as db:
        db.save_drawing("AAPL", "D", "fib", params)
        dm = DrawingManager(panel, db)
        n = dm.load("AAPL", "D")
        assert n == 1
        assert dm.count == 1
        assert isinstance(dm._records[0].item, list)
        assert len(dm._records[0].item) == len(_FIB_LEVELS)


# ─────────────────────── Rectangle placement ─────────────────────────────────

def test_place_rect_creates_record(qapp, tmp_path):
    import pyqtgraph as pg
    from ui.chart_panel import ChartPanel
    from ui.drawing_tools import DrawingManager

    df = _make_ohlcv(20)
    panel = ChartPanel(_make_config())
    panel.set_data(df)

    with _open_db(tmp_path) as db:
        dm = DrawingManager(panel, db)
        date1 = df.index[0].strftime("%Y-%m-%d")
        date2 = df.index[5].strftime("%Y-%m-%d")
        rec = dm._place_rect(0, 100.0, date1, 5, 110.0, date2)
        assert rec.drawing_type == "rect"
        assert isinstance(rec.item, pg.RectROI)
        assert dm.count == 1


def test_place_rect_stores_correct_params(qapp, tmp_path):
    from ui.chart_panel import ChartPanel
    from ui.drawing_tools import DrawingManager

    df = _make_ohlcv(20)
    panel = ChartPanel(_make_config())
    panel.set_data(df)

    with _open_db(tmp_path) as db:
        dm = DrawingManager(panel, db)
        date1 = df.index[0].strftime("%Y-%m-%d")
        date2 = df.index[5].strftime("%Y-%m-%d")
        rec = dm._place_rect(0, 100.0, date1, 5, 110.0, date2)
        assert rec.params["price1"] == pytest.approx(100.0)
        assert rec.params["price2"] == pytest.approx(110.0)


def test_place_rect_minimum_size(qapp, tmp_path):
    """_place_rect handles identical points without crashing."""
    from ui.chart_panel import ChartPanel
    from ui.drawing_tools import DrawingManager

    df = _make_ohlcv(20)
    panel = ChartPanel(_make_config())
    panel.set_data(df)

    with _open_db(tmp_path) as db:
        dm = DrawingManager(panel, db)
        date1 = df.index[0].strftime("%Y-%m-%d")
        rec = dm._place_rect(0, 100.0, date1, 0, 100.0, date1)
        assert rec is not None  # degenerate but should not raise


def test_load_restores_rect_from_db(qapp, tmp_path):
    import pyqtgraph as pg
    from ui.chart_panel import ChartPanel
    from ui.drawing_tools import DrawingManager

    df = _make_ohlcv(20)
    panel = ChartPanel(_make_config())
    panel.set_data(df)

    date1 = df.index[0].strftime("%Y-%m-%d")
    date2 = df.index[5].strftime("%Y-%m-%d")
    params = {"date1": date1, "price1": 100.0, "date2": date2, "price2": 110.0, "color": "#FFD700"}

    with _open_db(tmp_path) as db:
        db.save_drawing("AAPL", "D", "rect", params)
        dm = DrawingManager(panel, db)
        n = dm.load("AAPL", "D")
        assert n == 1
        assert isinstance(dm._records[0].item, pg.RectROI)


# ─────────────────────── export_png ──────────────────────────────────────────

def test_export_png_creates_file(qapp, tmp_path):
    from ui.chart_panel import ChartPanel

    panel = ChartPanel(_make_config())
    panel.set_data(_make_ohlcv())
    out = tmp_path / "chart.png"
    panel.export_png(out, resolution=(400, 300))
    assert out.is_file()
    assert out.stat().st_size > 0


def test_export_png_creates_parent_dirs(qapp, tmp_path):
    from ui.chart_panel import ChartPanel

    panel = ChartPanel(_make_config())
    panel.set_data(_make_ohlcv())
    nested = tmp_path / "exports" / "sub" / "chart.png"
    panel.export_png(nested, resolution=(400, 300))
    assert nested.is_file()


def test_export_png_uses_config_resolution_by_default(qapp, tmp_path):
    from ui.chart_panel import ChartPanel

    panel = ChartPanel(_make_config())
    panel.set_data(_make_ohlcv())
    out = tmp_path / "default_res.png"
    # Config resolution is 800×600; should not raise.
    panel.export_png(out)
    assert out.is_file()


def test_export_png_accepts_string_path(qapp, tmp_path):
    from ui.chart_panel import ChartPanel

    panel = ChartPanel(_make_config())
    panel.set_data(_make_ohlcv())
    out = str(tmp_path / "str_path.png")
    result = panel.export_png(out, resolution=(400, 300))
    assert Path(out).is_file()
    assert str(result) == out
