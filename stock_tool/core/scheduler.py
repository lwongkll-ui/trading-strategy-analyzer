"""Background download scheduler using APScheduler.

Reads :attr:`~core.config.SchedulerConfig.symbols_file`, fires on the
configured cron schedule, and calls
:meth:`~core.data_manager.DataManager.get_history` for every ticker listed
in the file (one per line).

Wire-up in ``main.py``::

    if config.scheduler.enabled:
        sched = StockScheduler(config.scheduler, data_manager)
        sched.start()
        ...
        sched.stop()
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.config import SchedulerConfig
    from core.data_manager import DataManager

logger = logging.getLogger(__name__)


class SchedulerError(RuntimeError):
    """Raised for scheduler configuration or runtime errors."""


class StockScheduler:
    """Wraps APScheduler to download fresh price data on a cron schedule.

    Args:
        config:       The ``scheduler`` section from the application config.
        data_manager: Pre-built :class:`~core.data_manager.DataManager`.
    """

    def __init__(
        self,
        config: "SchedulerConfig",
        data_manager: "DataManager",
    ) -> None:
        self._config = config
        self._dm = data_manager
        self._scheduler = None

    # ── public API ────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the background scheduler.

        Raises:
            SchedulerError: If already running, APScheduler is not installed,
                or the cron expression is invalid.
        """
        if self.is_running():
            raise SchedulerError("Scheduler is already running")

        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.triggers.cron import CronTrigger
        except ImportError as exc:
            raise SchedulerError(
                "APScheduler is not installed — run: pip install apscheduler"
            ) from exc

        try:
            trigger = CronTrigger.from_crontab(self._config.cron)
        except ValueError as exc:
            raise SchedulerError(
                f"Invalid cron expression {self._config.cron!r}: {exc}"
            ) from exc

        sched = BackgroundScheduler()
        sched.add_job(self._run_downloads, trigger)
        sched.start()
        self._scheduler = sched
        logger.info("Scheduler started with cron %r", self._config.cron)

    def stop(self) -> None:
        """Stop the scheduler if it is running."""
        if self._scheduler is not None:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None
            logger.info("Scheduler stopped")

    def is_running(self) -> bool:
        """Return ``True`` when the background scheduler is active."""
        return self._scheduler is not None and self._scheduler.running

    # ── internal ──────────────────────────────────────────────────────────────

    def _run_downloads(self) -> None:
        """Download fresh data for every ticker in the symbols file."""
        symbols_file = Path(self._config.symbols_file)
        if not symbols_file.is_file():
            logger.warning("Symbols file not found: %s", symbols_file)
            return

        with symbols_file.open(encoding="utf-8") as fh:
            tickers = [
                line.strip().upper()
                for line in fh
                if line.strip() and not line.startswith("#")
            ]

        logger.info("Scheduled run: downloading %d symbols", len(tickers))
        for ticker in tickers:
            try:
                self._dm.get_history(ticker, refresh=True)
                logger.debug("Downloaded %s", ticker)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to download %s: %s", ticker, exc)
