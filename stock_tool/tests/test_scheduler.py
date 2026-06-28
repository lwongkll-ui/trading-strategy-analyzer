"""Tests for core.scheduler.StockScheduler."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.scheduler import SchedulerError, StockScheduler


def _make_scheduler(tmp_path: Path, cron: str = "0 18 * * 1-5") -> StockScheduler:
    from core.config import SchedulerConfig
    from core.data_manager import DataManager

    cfg = SchedulerConfig(
        enabled=True,
        cron=cron,
        symbols_file=tmp_path / "symbols.txt",
    )
    dm = MagicMock(spec=DataManager)
    return StockScheduler(cfg, dm)


# ── initial state ─────────────────────────────────────────────────────────────

def test_not_running_initially(tmp_path):
    sched = _make_scheduler(tmp_path)
    assert sched.is_running() is False


# ── start / stop ──────────────────────────────────────────────────────────────

def test_start_and_stop(tmp_path):
    sched = _make_scheduler(tmp_path)
    sched.start()
    assert sched.is_running() is True
    sched.stop()
    assert sched.is_running() is False


def test_stop_when_not_running_is_noop(tmp_path):
    sched = _make_scheduler(tmp_path)
    sched.stop()  # should not raise
    assert sched.is_running() is False


def test_start_twice_raises(tmp_path):
    sched = _make_scheduler(tmp_path)
    sched.start()
    try:
        with pytest.raises(SchedulerError, match="already running"):
            sched.start()
    finally:
        sched.stop()


# ── cron validation ───────────────────────────────────────────────────────────

def test_invalid_cron_raises(tmp_path):
    sched = _make_scheduler(tmp_path, cron="not-a-cron")
    with pytest.raises(SchedulerError):
        sched.start()


def test_five_field_cron_accepted(tmp_path):
    sched = _make_scheduler(tmp_path, cron="*/30 9-17 * * 1-5")
    sched.start()
    assert sched.is_running()
    sched.stop()


# ── _run_downloads ────────────────────────────────────────────────────────────

def test_run_downloads_missing_file_logs_warning(tmp_path, caplog):
    import logging
    sched = _make_scheduler(tmp_path)
    with caplog.at_level(logging.WARNING, logger="core.scheduler"):
        sched._run_downloads()
    assert "not found" in caplog.text.lower()


def test_run_downloads_calls_get_history(tmp_path):
    symbols_file = tmp_path / "symbols.txt"
    symbols_file.write_text("AAPL\nMSFT\nGOOGL\n", encoding="utf-8")

    from core.config import SchedulerConfig
    from core.data_manager import DataManager

    cfg = SchedulerConfig(
        enabled=True, cron="0 18 * * 1-5", symbols_file=symbols_file
    )
    dm = MagicMock(spec=DataManager)
    sched = StockScheduler(cfg, dm)
    sched._run_downloads()

    calls = [c.args[0] for c in dm.get_history.call_args_list]
    assert calls == ["AAPL", "MSFT", "GOOGL"]
    for call in dm.get_history.call_args_list:
        assert call.kwargs.get("refresh") is True


def test_run_downloads_skips_blank_lines(tmp_path):
    symbols_file = tmp_path / "symbols.txt"
    symbols_file.write_text("AAPL\n\n  \nMSFT\n", encoding="utf-8")

    from core.config import SchedulerConfig
    from core.data_manager import DataManager

    cfg = SchedulerConfig(
        enabled=True, cron="0 18 * * 1-5", symbols_file=symbols_file
    )
    dm = MagicMock(spec=DataManager)
    sched = StockScheduler(cfg, dm)
    sched._run_downloads()

    assert dm.get_history.call_count == 2


def test_run_downloads_skips_comment_lines(tmp_path):
    symbols_file = tmp_path / "symbols.txt"
    symbols_file.write_text("# US stocks\nAAPL\nMSFT\n", encoding="utf-8")

    from core.config import SchedulerConfig
    from core.data_manager import DataManager

    cfg = SchedulerConfig(
        enabled=True, cron="0 18 * * 1-5", symbols_file=symbols_file
    )
    dm = MagicMock(spec=DataManager)
    sched = StockScheduler(cfg, dm)
    sched._run_downloads()

    assert dm.get_history.call_count == 2


def test_run_downloads_continues_after_error(tmp_path):
    symbols_file = tmp_path / "symbols.txt"
    symbols_file.write_text("AAPL\nBAD\nMSFT\n", encoding="utf-8")

    from core.config import SchedulerConfig
    from core.data_manager import DataManager, DataManagerError

    cfg = SchedulerConfig(
        enabled=True, cron="0 18 * * 1-5", symbols_file=symbols_file
    )
    dm = MagicMock(spec=DataManager)

    def _side_effect(ticker, **_kwargs):
        if ticker == "BAD":
            raise DataManagerError("no data")

    dm.get_history.side_effect = _side_effect
    sched = StockScheduler(cfg, dm)
    sched._run_downloads()  # should not raise

    assert dm.get_history.call_count == 3


def test_run_downloads_normalises_ticker_case(tmp_path):
    symbols_file = tmp_path / "symbols.txt"
    symbols_file.write_text("aapl\nmsft\n", encoding="utf-8")

    from core.config import SchedulerConfig
    from core.data_manager import DataManager

    cfg = SchedulerConfig(
        enabled=True, cron="0 18 * * 1-5", symbols_file=symbols_file
    )
    dm = MagicMock(spec=DataManager)
    sched = StockScheduler(cfg, dm)
    sched._run_downloads()

    calls = [c.args[0] for c in dm.get_history.call_args_list]
    assert calls == ["AAPL", "MSFT"]
