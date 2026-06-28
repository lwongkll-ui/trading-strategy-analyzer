"""Tests for ui.watchlist_panel."""

from __future__ import annotations

from pathlib import Path

import pytest

from storage.db_store import DbStore


def _open_db(tmp_path: Path) -> DbStore:
    db = DbStore(tmp_path / "wl.db")
    db.open()
    return db


# ── construction ──────────────────────────────────────────────────────────────

def test_watchlist_panel_constructs(qapp, tmp_path):
    from ui.watchlist_panel import WatchlistPanel
    with _open_db(tmp_path) as db:
        panel = WatchlistPanel(db)
        assert panel.ticker_count == 0


def test_watchlist_panel_loads_existing_tickers(qapp, tmp_path):
    from ui.watchlist_panel import WatchlistPanel
    with _open_db(tmp_path) as db:
        db.add_to_watchlist("AAPL")
        db.add_to_watchlist("MSFT")
        panel = WatchlistPanel(db)
        assert panel.ticker_count == 2


# ── add ───────────────────────────────────────────────────────────────────────

def test_add_ticker_via_button(qapp, tmp_path):
    from ui.watchlist_panel import WatchlistPanel
    with _open_db(tmp_path) as db:
        panel = WatchlistPanel(db)
        panel._ticker_edit.setText("GOOG")
        panel._on_add()
        assert panel.ticker_count == 1
        assert db.in_watchlist("GOOG")


def test_add_ticker_uppercases(qapp, tmp_path):
    from ui.watchlist_panel import WatchlistPanel
    with _open_db(tmp_path) as db:
        panel = WatchlistPanel(db)
        panel._ticker_edit.setText("tsla")
        panel._on_add()
        assert db.in_watchlist("TSLA")


def test_add_clears_input_field(qapp, tmp_path):
    from ui.watchlist_panel import WatchlistPanel
    with _open_db(tmp_path) as db:
        panel = WatchlistPanel(db)
        panel._ticker_edit.setText("NVDA")
        panel._on_add()
        assert panel._ticker_edit.text() == ""


def test_add_blank_is_noop(qapp, tmp_path):
    from ui.watchlist_panel import WatchlistPanel
    with _open_db(tmp_path) as db:
        panel = WatchlistPanel(db)
        panel._ticker_edit.setText("   ")
        panel._on_add()
        assert panel.ticker_count == 0


def test_add_duplicate_does_not_double_entry(qapp, tmp_path):
    from ui.watchlist_panel import WatchlistPanel
    with _open_db(tmp_path) as db:
        panel = WatchlistPanel(db)
        panel._ticker_edit.setText("AAPL")
        panel._on_add()
        panel._ticker_edit.setText("AAPL")
        panel._on_add()
        assert panel.ticker_count == 1


def test_add_selects_new_ticker(qapp, tmp_path):
    from ui.watchlist_panel import WatchlistPanel
    with _open_db(tmp_path) as db:
        panel = WatchlistPanel(db)
        panel._ticker_edit.setText("META")
        panel._on_add()
        assert panel._list.currentItem() is not None
        assert panel._list.currentItem().text() == "META"


# ── remove ────────────────────────────────────────────────────────────────────

def test_remove_selected_ticker(qapp, tmp_path):
    from ui.watchlist_panel import WatchlistPanel
    with _open_db(tmp_path) as db:
        db.add_to_watchlist("AAPL")
        panel = WatchlistPanel(db)
        panel._list.setCurrentRow(0)
        panel._on_remove()
        assert panel.ticker_count == 0
        assert not db.in_watchlist("AAPL")


def test_remove_noop_when_nothing_selected(qapp, tmp_path):
    from ui.watchlist_panel import WatchlistPanel
    with _open_db(tmp_path) as db:
        db.add_to_watchlist("AAPL")
        panel = WatchlistPanel(db)
        panel._list.clearSelection()
        panel._on_remove()  # should not raise
        assert panel.ticker_count == 1


def test_remove_only_removes_selected(qapp, tmp_path):
    from ui.watchlist_panel import WatchlistPanel
    with _open_db(tmp_path) as db:
        db.add_to_watchlist("AAPL")
        db.add_to_watchlist("MSFT")
        panel = WatchlistPanel(db)
        # Select first item (AAPL after alphabetical sort from DB)
        panel._list.setCurrentRow(0)
        first = panel._list.currentItem().text()
        panel._on_remove()
        assert panel.ticker_count == 1
        assert not db.in_watchlist(first)


# ── ticker_selected signal ────────────────────────────────────────────────────

def test_item_activated_emits_signal(qapp, tmp_path):
    from ui.watchlist_panel import WatchlistPanel
    with _open_db(tmp_path) as db:
        db.add_to_watchlist("AAPL")
        panel = WatchlistPanel(db)
        received: list[str] = []
        panel.ticker_selected.connect(received.append)
        panel._on_item_activated(panel._list.item(0))
        assert received == ["AAPL"]


def test_signal_carries_ticker_text(qapp, tmp_path):
    from ui.watchlist_panel import WatchlistPanel
    with _open_db(tmp_path) as db:
        db.add_to_watchlist("NVDA")
        panel = WatchlistPanel(db)
        received: list[str] = []
        panel.ticker_selected.connect(received.append)
        panel._on_item_activated(panel._list.item(0))
        assert received[0] == "NVDA"


# ── refresh ───────────────────────────────────────────────────────────────────

def test_refresh_reflects_external_db_change(qapp, tmp_path):
    from ui.watchlist_panel import WatchlistPanel
    with _open_db(tmp_path) as db:
        panel = WatchlistPanel(db)
        assert panel.ticker_count == 0
        db.add_to_watchlist("AMD")
        panel.refresh()
        assert panel.ticker_count == 1


# ── select_ticker ─────────────────────────────────────────────────────────────

def test_select_ticker_highlights_row(qapp, tmp_path):
    from ui.watchlist_panel import WatchlistPanel
    with _open_db(tmp_path) as db:
        db.add_to_watchlist("AAPL")
        db.add_to_watchlist("MSFT")
        panel = WatchlistPanel(db)
        panel.select_ticker("MSFT")
        assert panel._list.currentItem() is not None
        assert panel._list.currentItem().text() == "MSFT"


def test_select_ticker_unknown_is_noop(qapp, tmp_path):
    from ui.watchlist_panel import WatchlistPanel
    with _open_db(tmp_path) as db:
        db.add_to_watchlist("AAPL")
        panel = WatchlistPanel(db)
        panel.select_ticker("UNKNOWN")  # should not raise
