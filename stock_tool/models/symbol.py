"""Symbol metadata model and registry.

:class:`Symbol` is a lightweight descriptor for a tradable instrument.
:class:`SymbolRegistry` loads a CSV of known symbols and supports prefix
search used by the toolbar autocompleter (spec §7.1).

CSV format (one header row required)::

    ticker,name,market,exchange
    AAPL,Apple Inc.,US,NASDAQ
    0700.HK,Tencent Holdings,HK,HKEX
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

VALID_MARKETS = ("ALL", "US", "HK", "UK", "JP", "AU", "CUSTOM")


@dataclass(frozen=True)
class Symbol:
    """Metadata for a single tradable instrument.

    Args:
        ticker:   Yahoo Finance-compatible symbol (e.g. ``"AAPL"``, ``"0700.HK"``).
        name:     Human-readable company/fund name.
        market:   Market identifier (``"US"``, ``"HK"``, ``"UK"``, …).
        exchange: Exchange code (``"NASDAQ"``, ``"HKEX"``, …).
    """

    ticker: str
    name: str = ""
    market: str = "US"
    exchange: str = ""

    def __post_init__(self) -> None:
        if not self.ticker:
            raise ValueError("ticker must not be empty")

    def display(self) -> str:
        """Return ``'TICKER — Name'`` for use in autocomplete lists."""
        return f"{self.ticker} — {self.name}" if self.name else self.ticker


class SymbolRegistryError(ValueError):
    """Raised when the symbol CSV is malformed."""


class SymbolRegistry:
    """In-memory store of known symbols with prefix-search for autocomplete.

    The registry is populated from a CSV file at startup. If no file is
    available the registry is empty — the app still functions (users can
    type any ticker manually), autocomplete just has no suggestions.
    """

    REQUIRED_COLUMNS = {"ticker"}

    def __init__(self) -> None:
        self._symbols: list[Symbol] = []
        self._by_ticker: dict[str, Symbol] = {}

    # ── loading ───────────────────────────────────────────────────────────────

    def load_csv(self, path: str | Path) -> int:
        """Load symbols from *path*. Returns number of symbols loaded.

        Raises:
            FileNotFoundError: File does not exist.
            SymbolRegistryError: Missing required columns or malformed rows.
        """
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(f"Symbol file not found: {path}")

        loaded: list[Symbol] = []
        with path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames is None:
                raise SymbolRegistryError(f"Symbol CSV {path} appears to be empty")
            missing = self.REQUIRED_COLUMNS - set(reader.fieldnames)
            if missing:
                raise SymbolRegistryError(
                    f"Symbol CSV {path} is missing columns: {missing}"
                )
            for i, row in enumerate(reader, start=2):
                ticker = row.get("ticker", "").strip().upper()
                if not ticker:
                    logger.debug("Skipping blank ticker on row %d", i)
                    continue
                loaded.append(
                    Symbol(
                        ticker=ticker,
                        name=row.get("name", "").strip(),
                        market=row.get("market", "US").strip().upper(),
                        exchange=row.get("exchange", "").strip(),
                    )
                )

        self._symbols = loaded
        self._by_ticker = {s.ticker: s for s in loaded}
        logger.info("Loaded %d symbols from %s", len(loaded), path)
        return len(loaded)

    def add(self, symbol: Symbol) -> None:
        """Add a single symbol, replacing any existing entry with the same ticker."""
        self._by_ticker[symbol.ticker] = symbol
        self._symbols = list(self._by_ticker.values())

    def clear(self) -> None:
        self._symbols.clear()
        self._by_ticker.clear()

    # ── lookup ────────────────────────────────────────────────────────────────

    def get(self, ticker: str) -> Symbol | None:
        """Return the Symbol for *ticker*, or ``None`` if not found."""
        return self._by_ticker.get(ticker.upper())

    def search(
        self,
        query: str,
        market: str = "ALL",
        limit: int = 20,
    ) -> list[Symbol]:
        """Return up to *limit* symbols whose ticker or name starts with *query*.

        Args:
            query:  Case-insensitive prefix to match against ticker and name.
            market: Filter to a specific market; ``"ALL"`` skips filtering.
            limit:  Maximum results to return.
        """
        q = query.strip().upper()
        results: list[Symbol] = []
        for sym in self._symbols:
            if market != "ALL" and sym.market != market.upper():
                continue
            if sym.ticker.startswith(q) or sym.name.upper().startswith(q):
                results.append(sym)
            if len(results) >= limit:
                break
        return results

    def all_tickers(self, market: str = "ALL") -> list[str]:
        """Return all ticker strings, optionally filtered by *market*."""
        if market == "ALL":
            return [s.ticker for s in self._symbols]
        return [s.ticker for s in self._symbols if s.market == market.upper()]

    def __len__(self) -> int:
        return len(self._symbols)
