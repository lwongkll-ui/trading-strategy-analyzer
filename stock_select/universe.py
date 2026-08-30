"""Load index constituents for the markets the screener covers."""
from __future__ import annotations

import csv
from dataclasses import dataclass

from config import CONSTITUENTS_DIR, UNIVERSES


@dataclass(frozen=True)
class Constituent:
    ticker: str
    name: str
    market: str          # universe key, e.g. "SP500"

    @property
    def market_label(self) -> str:
        return UNIVERSES[self.market]["label"]


def load_universe(market: str) -> list[Constituent]:
    """Return the constituents of *market* (a key of ``config.UNIVERSES``)."""
    if market not in UNIVERSES:
        raise KeyError(f"unknown market {market!r}; expected one of {sorted(UNIVERSES)}")

    path = CONSTITUENTS_DIR / UNIVERSES[market]["csv"]
    if not path.exists():
        raise FileNotFoundError(f"constituent list not found: {path}")

    out: list[Constituent] = []
    seen: set[str] = set()
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            ticker = (row.get("ticker") or "").strip()
            if not ticker or ticker in seen:
                continue
            seen.add(ticker)
            out.append(Constituent(ticker, (row.get("name") or ticker).strip(), market))
    return out


def load_universes(markets: list[str]) -> list[Constituent]:
    """Concatenate the constituents of every market in *markets*."""
    return [c for m in markets for c in load_universe(m)]
