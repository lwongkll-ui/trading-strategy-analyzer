"""Tests for storage.db_store."""

from __future__ import annotations

from pathlib import Path

import pytest

from storage.db_store import DbStore, DbStoreError


def _open_db(tmp_path: Path) -> DbStore:
    db = DbStore(tmp_path / "test.db")
    db.open()
    return db


# ── lifecycle ─────────────────────────────────────────────────────────────────

def test_open_creates_file(tmp_path):
    db = _open_db(tmp_path)
    db.close()
    assert (tmp_path / "test.db").is_file()


def test_context_manager(tmp_path):
    with DbStore(tmp_path / "cm.db") as db:
        db.set_setting("x", "1")
    assert (tmp_path / "cm.db").is_file()


def test_error_when_not_open(tmp_path):
    db = DbStore(tmp_path / "x.db")
    with pytest.raises(DbStoreError, match="not open"):
        db.get_setting("k")


def test_creates_parent_directories(tmp_path):
    nested = tmp_path / "a" / "b" / "c" / "db.db"
    with DbStore(nested) as db:
        db.set_setting("k", "v")
    assert nested.is_file()


# ── drawings ──────────────────────────────────────────────────────────────────

def test_save_and_load_drawing(tmp_path):
    with _open_db(tmp_path) as db:
        params = {"price": 185.5, "color": "#FF0000"}
        did = db.save_drawing("AAPL", "D", "horizontal", params)
        assert isinstance(did, int)

        rows = db.load_drawings("AAPL", "D")
        assert len(rows) == 1
        assert rows[0]["id"] == did
        assert rows[0]["drawing_type"] == "horizontal"
        assert rows[0]["params"] == params


def test_load_drawings_empty_when_none(tmp_path):
    with _open_db(tmp_path) as db:
        assert db.load_drawings("AAPL", "D") == []


def test_load_drawings_filters_by_ticker_and_timeframe(tmp_path):
    with _open_db(tmp_path) as db:
        db.save_drawing("AAPL", "D", "horizontal", {"price": 180.0})
        db.save_drawing("MSFT", "D", "horizontal", {"price": 300.0})
        db.save_drawing("AAPL", "W", "horizontal", {"price": 175.0})

        aapl_d = db.load_drawings("AAPL", "D")
        assert len(aapl_d) == 1
        assert aapl_d[0]["params"]["price"] == 180.0


def test_load_drawings_ticker_case_insensitive(tmp_path):
    with _open_db(tmp_path) as db:
        db.save_drawing("aapl", "D", "horizontal", {"price": 1.0})
        rows = db.load_drawings("AAPL", "D")
        assert len(rows) == 1


def test_delete_drawing(tmp_path):
    with _open_db(tmp_path) as db:
        did = db.save_drawing("AAPL", "D", "horizontal", {"price": 100.0})
        db.delete_drawing(did)
        assert db.load_drawings("AAPL", "D") == []


def test_delete_nonexistent_drawing_is_noop(tmp_path):
    with _open_db(tmp_path) as db:
        db.delete_drawing(9999)  # should not raise


def test_delete_all_drawings(tmp_path):
    with _open_db(tmp_path) as db:
        db.save_drawing("AAPL", "D", "horizontal", {"price": 100.0})
        db.save_drawing("AAPL", "D", "horizontal", {"price": 200.0})
        db.save_drawing("AAPL", "W", "horizontal", {"price": 150.0})

        db.delete_all_drawings("AAPL", "D")
        assert db.load_drawings("AAPL", "D") == []
        assert len(db.load_drawings("AAPL", "W")) == 1  # other timeframe intact


def test_drawing_count(tmp_path):
    with _open_db(tmp_path) as db:
        db.save_drawing("AAPL", "D", "horizontal", {"price": 100.0})
        db.save_drawing("AAPL", "D", "trend_line", {"date1": "2024-01-02"})
        assert db.drawing_count("AAPL", "D") == 2
        assert db.drawing_count("MSFT", "D") == 0


def test_save_complex_params_roundtrip(tmp_path):
    params = {
        "date1": "2024-01-02", "price1": 180.0,
        "date2": "2024-06-15", "price2": 210.5,
        "color": "#00FF00",
    }
    with _open_db(tmp_path) as db:
        db.save_drawing("AAPL", "W", "trend_line", params)
        rows = db.load_drawings("AAPL", "W")
        assert rows[0]["params"] == params


def test_drawings_ordered_oldest_first(tmp_path):
    with _open_db(tmp_path) as db:
        db.save_drawing("AAPL", "D", "horizontal", {"price": 1.0})
        db.save_drawing("AAPL", "D", "horizontal", {"price": 2.0})
        db.save_drawing("AAPL", "D", "horizontal", {"price": 3.0})
        rows = db.load_drawings("AAPL", "D")
        prices = [r["params"]["price"] for r in rows]
        assert prices == [1.0, 2.0, 3.0]


# ── settings ──────────────────────────────────────────────────────────────────

def test_set_and_get_setting(tmp_path):
    with _open_db(tmp_path) as db:
        db.set_setting("theme", "dark")
        assert db.get_setting("theme") == "dark"


def test_get_missing_setting_returns_default(tmp_path):
    with _open_db(tmp_path) as db:
        assert db.get_setting("missing") == ""
        assert db.get_setting("missing", "fallback") == "fallback"


def test_set_setting_overwrites(tmp_path):
    with _open_db(tmp_path) as db:
        db.set_setting("key", "v1")
        db.set_setting("key", "v2")
        assert db.get_setting("key") == "v2"


def test_all_settings(tmp_path):
    with _open_db(tmp_path) as db:
        db.set_setting("a", "1")
        db.set_setting("b", "2")
        assert db.all_settings() == {"a": "1", "b": "2"}


# ── watchlist ─────────────────────────────────────────────────────────────────

def test_add_and_get_watchlist(tmp_path):
    with _open_db(tmp_path) as db:
        db.add_to_watchlist("AAPL")
        db.add_to_watchlist("MSFT")
        assert set(db.get_watchlist()) == {"AAPL", "MSFT"}


def test_watchlist_case_normalised(tmp_path):
    with _open_db(tmp_path) as db:
        db.add_to_watchlist("aapl")
        assert "AAPL" in db.get_watchlist()


def test_add_duplicate_is_noop(tmp_path):
    with _open_db(tmp_path) as db:
        db.add_to_watchlist("AAPL")
        db.add_to_watchlist("AAPL")
        assert db.get_watchlist().count("AAPL") == 1


def test_remove_from_watchlist(tmp_path):
    with _open_db(tmp_path) as db:
        db.add_to_watchlist("AAPL")
        db.remove_from_watchlist("AAPL")
        assert "AAPL" not in db.get_watchlist()


def test_remove_missing_is_noop(tmp_path):
    with _open_db(tmp_path) as db:
        db.remove_from_watchlist("AAPL")  # should not raise


def test_in_watchlist(tmp_path):
    with _open_db(tmp_path) as db:
        db.add_to_watchlist("AAPL")
        assert db.in_watchlist("AAPL") is True
        assert db.in_watchlist("MSFT") is False
