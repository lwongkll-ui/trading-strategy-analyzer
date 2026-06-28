"""StockTool entry point.

Usage::

    python main.py [--config path/to/config.yaml]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="StockTool — desktop charting app")
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to config.yaml (default: config.yaml next to main.py)",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = Path(__file__).parent / config_path

    from core.config import load_config
    config = load_config(config_path)

    from models.symbol import SymbolRegistry
    registry = SymbolRegistry()

    # Auto-load symbol list when symbols.csv lives next to main.py
    symbols_csv = Path(__file__).parent / "symbols.csv"
    if symbols_csv.is_file():
        try:
            n = registry.load_csv(symbols_csv)
            logger.info("Loaded %d symbols from %s", n, symbols_csv)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not load symbols.csv: %s", exc)

    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    app.setApplicationName("StockTool")
    app.setOrganizationName("StockTool")

    # Start background scheduler when enabled in config
    scheduler = None
    if config.scheduler.enabled:
        from core.data_manager import DataManager
        from core.scheduler import StockScheduler, SchedulerError
        dm = DataManager(config)
        scheduler = StockScheduler(config.scheduler, dm)
        try:
            scheduler.start()
        except SchedulerError as exc:
            logger.warning("Scheduler failed to start: %s", exc)

    from ui.main_window import MainWindow
    window = MainWindow(config, registry=registry)
    window.show()

    exit_code = app.exec()
    if scheduler is not None:
        scheduler.stop()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
