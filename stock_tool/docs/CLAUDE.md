# StockTool — Claude Code Context

## Project purpose
A desktop stock charting application inspired by MetaStock. Fetches OHLCV data 
for US, HK, and global markets via yfinance, stores it locally as CSV, and 
renders interactive charts with technical indicators and drawing tools.

## Stack
- Python 3.11+
- PyQt6 (UI framework — not PySide6)
- pyqtgraph (charting)
- yfinance (data provider)
- pandas-ta (indicators — not TA-Lib)
- SQLite via sqlite3 (watchlists, annotations, settings)
- pytest (testing)

## Directory structure
See StockTool_Spec.md for the full layout. Key folders:
- core/         — data, indicators, news, scheduler
- ui/           — all PyQt6 widgets
- storage/      — CSV and SQLite access
- data/prices/  — local OHLCV CSV files
- data/exports/ — PNG chart exports

## Coding conventions
- Type hints on all function signatures
- Google-style docstrings
- Max line length: 100 characters
- Logging via Python `logging` module (not print statements)
- All config read from config.yaml via core/config.py — no hardcoded paths

## Commands
- Run app:   python main.py
- Run tests: pytest tests/
- Lint:      ruff check .

## Rules
- Never add a dependency without asking first
- Do not start UI code until core/ and storage/ modules are complete and tested
- CSV format: Date, Open, High, Low, Close, Volume, Adj_Close (see sample in data/sample/AAPL.csv)
- Resampled timeframes are computed in memory — never written to disk