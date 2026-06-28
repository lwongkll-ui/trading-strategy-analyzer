# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

StockTool — a MetaStock-inspired PyQt6 desktop charting application. Displays OHLCV candlestick/line charts with technical indicators, drawing tools, watchlist, news sidebar, and a side-by-side comparison panel.

## Commands

```bash
# Install runtime dependencies
pip install -r requirements.txt

# Install dev dependencies (adds pytest + pyinstaller)
pip install -r requirements-dev.txt

# Run the app
python main.py
python main.py --config path/to/config.yaml

# Or double-click / run the launcher script
run.bat

# Run all tests (headless via offscreen Qt platform)
python -m pytest tests/

# Run a single test file
python -m pytest tests/test_chart_panel.py

# Run a single test by name
python -m pytest tests/test_indicator_engine.py::test_obv_rising_price_adds_volume

# Build a distributable (one-folder)
python build.py
python build.py --clean        # wipe dist/ and build/ first
python build.py --onefile      # single-file EXE
```

## Architecture

### Entry point & wiring
`main.py` boots `QApplication`, loads `Config`, auto-loads `symbols.csv` into `SymbolRegistry`, optionally starts `StockScheduler`, then creates and shows `MainWindow`.

### Config (`core/config.py`)
All settings are frozen dataclasses (`Config`, `DataConfig`, `IndicatorsConfig`, etc.) loaded from `config.yaml` via `load_config()`. Relative paths in the YAML are resolved against the YAML file's directory. New indicator fields **must** have Python default values in `IndicatorsConfig` so existing `config.yaml` files remain valid without adding the key.

### Data flow
```
yfinance → DataManager.get_history() → csv_store (daily CSV cache)
                                      ↓
                              DataManager.resample()   ← always in-memory for W/M/Q/Y
                                      ↓
                             ChartPanel.set_data()  +  IndicatorPanel.set_data()
```
- **`storage/csv_store.py`** — one CSV per ticker under `data/prices/<MARKET>/<TICKER>.csv`. Market subfolder is inferred from ticker suffix (`.HK`, `.L`, `.AX`, etc.; default `US`).
- **`core/data_manager.py`** — merges fresh yfinance data with the existing CSV, never stores resampled frames to disk.
- **`storage/db_store.py`** — SQLite at `<config_dir>/stocktool.db`. Tables: `drawings`, `settings`, `watchlist`.

### UI layer (`ui/`)
All widgets are constructed in `MainWindow.__init__` → `_build_menus()` → `_build_toolbar()` → `_build_central()` → `_build_shortcuts()`.

| Widget | Role |
|---|---|
| `ChartPanel` | pyqtgraph `PlotWidget` wrapper. Bar-index x-axis (no weekend gaps). Owns candle/line item, MA overlays, BB overlay, VWAP overlay, crosshair, tooltip. |
| `IndicatorPanel` | Vertical `QSplitter` of up to 4 `SubChart` instances. `set_data(df)` fans out to all active sub-charts. |
| `DrawingManager` | Attaches to `ChartPanel`'s scene via `sigMouseClicked`. Persists to `DbStore`. Drawings are keyed by date string, not bar index. |
| `ComparePanel` | Self-contained second chart in a bottom dock. Bidirectional x-axis sync via `sigXRangeChanged` with a `_syncing` reentrancy guard. |
| `NewsSidebar` | Right dock; fetches headlines via `NewsFetcher`. |
| `WatchlistPanel` | Left dock; reads/writes `DbStore.watchlist`. |

### Indicators (`core/indicator_engine.py`)
Pure pandas/numpy functions — no pandas-ta. Each function returns a named `Series` or `DataFrame` aligned with the input index. The `IndicatorEngine` class is a thin wrapper that reads default periods from `IndicatorsConfig`.

Supported: `sma`, `ema`, `wma`, `rsi`, `macd`, `stc`, `bband`, `atr`, `stoch`, `obv`, `vwap`.

### Indicator sub-charts (`ui/indicator_panel.py`)
Each indicator type is a `SubChart` subclass. The base class creates a `QWidget` container with a header bar (title label + `_gear_btn`). Subcharts that expose parameters show the gear button; `VolumeSubChart` and `ObvSubChart` call `self._gear_btn.hide()`. Adding a new indicator requires: a new `SubChart` subclass, a `case` in `_make_subchart()`, adding the name to `VALID_INDICATORS`, and adding the button in `MainWindow._build_toolbar()`.

### Drawing tools (`ui/drawing_tools.py`)
`DrawingMode` enum: `NONE`, `HORIZONTAL`, `TREND_LINE`, `FIB`, `RECT`, `TEXT`. The `_DrawingRecord.item` field is `Any` — it holds either a single `pg.GraphicsObject` or a `list` for Fibonacci (7 `InfiniteLine` items). `_remove_item()` handles both cases.

### Scheduler (`core/scheduler.py`)
APScheduler `BackgroundScheduler` with `CronTrigger.from_crontab()`. Enabled/disabled via `config.scheduler.enabled`. Reads symbols from `config.scheduler.symbols_file`.

## Key conventions

- **x-axis is always bar index** (`0..N-1`), not timestamps. `DateAxis` maps indices back to date strings for tick labels.
- **Daily data only on disk**. `DataManager.resample()` produces W/M/Q/Y frames in memory from the daily cache.
- Tests use `QT_QPA_PLATFORM=offscreen` (set in `conftest.py`) and a session-scoped `qapp` fixture. UI tests receive `qapp` as a parameter to ensure `QApplication` exists.
- Drawings are stored with `date1`/`date2` strings (`YYYY-MM-DD`), resolved back to bar indices via `searchsorted` on load — they survive data refreshes and timeframe changes.
- `Config` dataclasses are frozen; never mutate them. `save_config()` serialises back to YAML.
