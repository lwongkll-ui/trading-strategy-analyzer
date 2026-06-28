"""SQLite-backed storage for drawings, settings, and watchlist.

A single ``.db`` file lives next to the price CSV directory (its path comes
from ``config``). The file is created on first use; all tables are set up via
:meth:`DbStore.open`.

Schema
------
``drawings``
    Persists per-ticker-per-timeframe drawing annotations.  ``params`` holds a
    JSON blob whose keys depend on ``drawing_type``:

    * ``"horizontal"`` → ``{price, color, style}``
    * ``"trend_line"``  → ``{date1, price1, date2, price2, color, style}``
    * ``"text"``        → ``{date, price, text, color}``

``settings``
    Key/value string table for user preferences.

``watchlist``
    Flat list of ticker strings (Phase 2 feature; schema created now so the
    table exists when it is needed).
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

logger = logging.getLogger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS drawings (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker       TEXT    NOT NULL,
    timeframe    TEXT    NOT NULL,
    drawing_type TEXT    NOT NULL,
    params       TEXT    NOT NULL,
    created_at   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_drawings_ticker_tf
    ON drawings (ticker, timeframe);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS watchlist (
    ticker    TEXT PRIMARY KEY,
    added_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now'))
);
"""


class DbStoreError(RuntimeError):
    """Raised when a database operation fails unexpectedly."""


class DbStore:
    """Thin wrapper around a SQLite database.

    Args:
        db_path: Filesystem path to the ``.db`` file.  The parent directory
                 must already exist (or be created by the caller).
    """

    def __init__(self, db_path: str | Path) -> None:
        self._path = Path(db_path)
        self._conn: sqlite3.Connection | None = None

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def open(self) -> None:
        """Open (or create) the database and apply the schema."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_DDL)
        self._migrate()
        self._conn.commit()
        logger.debug("Opened database: %s", self._path)

    def _migrate(self) -> None:
        """Apply incremental schema changes to existing databases."""
        assert self._conn is not None
        cols = {row[1] for row in self._conn.execute("PRAGMA table_info(watchlist)")}
        if "sort_order" not in cols:
            self._conn.execute(
                "ALTER TABLE watchlist ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0"
            )
            # Seed sort_order from current insertion order so existing watchlists
            # keep their relative sequence after the migration.
            self._conn.execute(
                "UPDATE watchlist SET sort_order = ("
                "  SELECT COUNT(*) FROM watchlist w2"
                "  WHERE w2.added_at < watchlist.added_at"
                "  OR (w2.added_at = watchlist.added_at AND w2.ticker < watchlist.ticker)"
                ")"
            )

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "DbStore":
        self.open()
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    @contextmanager
    def _cursor(self) -> Iterator[sqlite3.Cursor]:
        if self._conn is None:
            raise DbStoreError("Database is not open — call open() first")
        cur = self._conn.cursor()
        try:
            yield cur
            self._conn.commit()
        except sqlite3.Error as exc:
            self._conn.rollback()
            raise DbStoreError(str(exc)) from exc
        finally:
            cur.close()

    # ── drawings ──────────────────────────────────────────────────────────────

    def save_drawing(
        self, ticker: str, timeframe: str, drawing_type: str, params: dict[str, Any]
    ) -> int:
        """Insert a drawing and return its auto-generated ``id``."""
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO drawings (ticker, timeframe, drawing_type, params) "
                "VALUES (?, ?, ?, ?)",
                (ticker.upper(), timeframe, drawing_type, json.dumps(params)),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def load_drawings(self, ticker: str, timeframe: str) -> list[dict[str, Any]]:
        """Return all drawings for *ticker* + *timeframe*, oldest first."""
        with self._cursor() as cur:
            cur.execute(
                "SELECT id, drawing_type, params, created_at "
                "FROM drawings WHERE ticker = ? AND timeframe = ? "
                "ORDER BY id ASC",
                (ticker.upper(), timeframe),
            )
            rows = cur.fetchall()
        result = []
        for row in rows:
            result.append(
                {
                    "id": row["id"],
                    "drawing_type": row["drawing_type"],
                    "params": json.loads(row["params"]),
                    "created_at": row["created_at"],
                }
            )
        return result

    def delete_drawing(self, drawing_id: int) -> None:
        """Delete the drawing with the given *id*. No-op if it does not exist."""
        with self._cursor() as cur:
            cur.execute("DELETE FROM drawings WHERE id = ?", (drawing_id,))

    def delete_all_drawings(self, ticker: str, timeframe: str) -> None:
        """Delete every drawing for *ticker* + *timeframe*."""
        with self._cursor() as cur:
            cur.execute(
                "DELETE FROM drawings WHERE ticker = ? AND timeframe = ?",
                (ticker.upper(), timeframe),
            )

    def drawing_count(self, ticker: str, timeframe: str) -> int:
        """Return the number of saved drawings for *ticker* + *timeframe*."""
        with self._cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM drawings WHERE ticker = ? AND timeframe = ?",
                (ticker.upper(), timeframe),
            )
            return cur.fetchone()[0]

    # ── settings ──────────────────────────────────────────────────────────────

    def get_setting(self, key: str, default: str = "") -> str:
        """Return the stored value for *key*, or *default* if absent."""
        with self._cursor() as cur:
            cur.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cur.fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        """Upsert a settings key/value pair."""
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def all_settings(self) -> dict[str, str]:
        """Return every stored setting as a plain dict."""
        with self._cursor() as cur:
            cur.execute("SELECT key, value FROM settings ORDER BY key")
            return {row["key"]: row["value"] for row in cur.fetchall()}

    # ── watchlist ─────────────────────────────────────────────────────────────

    def add_to_watchlist(self, ticker: str) -> None:
        """Add *ticker* to the watchlist. Silently no-ops if already present."""
        with self._cursor() as cur:
            cur.execute(
                "SELECT COALESCE(MAX(sort_order) + 1, 0) FROM watchlist"
            )
            next_order = cur.fetchone()[0]
            cur.execute(
                "INSERT OR IGNORE INTO watchlist (ticker, sort_order) VALUES (?, ?)",
                (ticker.upper(), next_order),
            )

    def remove_from_watchlist(self, ticker: str) -> None:
        """Remove *ticker* from the watchlist. No-op if absent."""
        with self._cursor() as cur:
            cur.execute("DELETE FROM watchlist WHERE ticker = ?", (ticker.upper(),))

    def get_watchlist(self) -> list[str]:
        """Return all watchlist tickers in user-defined order."""
        with self._cursor() as cur:
            cur.execute("SELECT ticker FROM watchlist ORDER BY sort_order, added_at, ticker")
            return [row["ticker"] for row in cur.fetchall()]

    def reorder_watchlist(self, tickers: list[str]) -> None:
        """Persist a new display order for all watchlist tickers."""
        with self._cursor() as cur:
            cur.executemany(
                "UPDATE watchlist SET sort_order = ? WHERE ticker = ?",
                [(i, t.upper()) for i, t in enumerate(tickers)],
            )

    def in_watchlist(self, ticker: str) -> bool:
        """Return ``True`` if *ticker* is in the watchlist."""
        with self._cursor() as cur:
            cur.execute("SELECT 1 FROM watchlist WHERE ticker = ?", (ticker.upper(),))
            return cur.fetchone() is not None
