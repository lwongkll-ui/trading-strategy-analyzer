"""Tests for models.symbol."""

from __future__ import annotations

from pathlib import Path

import pytest

from models.symbol import Symbol, SymbolRegistry, SymbolRegistryError


# ── Symbol dataclass ──────────────────────────────────────────────────────────

def test_symbol_requires_ticker():
    with pytest.raises(ValueError, match="ticker"):
        Symbol(ticker="")


def test_symbol_display_with_name():
    s = Symbol(ticker="AAPL", name="Apple Inc.")
    assert s.display() == "AAPL — Apple Inc."


def test_symbol_display_without_name():
    s = Symbol(ticker="AAPL")
    assert s.display() == "AAPL"


def test_symbol_is_frozen():
    s = Symbol(ticker="AAPL", name="Apple Inc.")
    with pytest.raises(Exception):
        s.ticker = "MSFT"  # type: ignore[misc]


# ── SymbolRegistry loading ────────────────────────────────────────────────────

def _write_csv(tmp_path: Path, content: str, filename: str = "symbols.csv") -> Path:
    path = tmp_path / filename
    path.write_text(content, encoding="utf-8")
    return path


VALID_CSV = """\
ticker,name,market,exchange
AAPL,Apple Inc.,US,NASDAQ
MSFT,Microsoft Corp.,US,NASDAQ
0700.HK,Tencent Holdings,HK,HKEX
BP.L,BP PLC,UK,LSE
"""


def test_registry_loads_valid_csv(tmp_path):
    reg = SymbolRegistry()
    n = reg.load_csv(_write_csv(tmp_path, VALID_CSV))
    assert n == 4
    assert len(reg) == 4


def test_registry_get_by_ticker(tmp_path):
    reg = SymbolRegistry()
    reg.load_csv(_write_csv(tmp_path, VALID_CSV))
    sym = reg.get("AAPL")
    assert sym is not None
    assert sym.name == "Apple Inc."
    assert sym.market == "US"


def test_registry_get_case_insensitive(tmp_path):
    reg = SymbolRegistry()
    reg.load_csv(_write_csv(tmp_path, VALID_CSV))
    assert reg.get("aapl") is not None


def test_registry_get_unknown_returns_none(tmp_path):
    reg = SymbolRegistry()
    reg.load_csv(_write_csv(tmp_path, VALID_CSV))
    assert reg.get("XYZ") is None


def test_registry_missing_file_raises():
    reg = SymbolRegistry()
    with pytest.raises(FileNotFoundError):
        reg.load_csv("/nonexistent/symbols.csv")


def test_registry_missing_ticker_column_raises(tmp_path):
    bad = "name,market\nApple,US\n"
    with pytest.raises(SymbolRegistryError, match="ticker"):
        SymbolRegistry().load_csv(_write_csv(tmp_path, bad))


def test_registry_skips_blank_tickers(tmp_path):
    csv = "ticker,name\nAAPL,Apple\n,Blank\nMSFT,Microsoft\n"
    reg = SymbolRegistry()
    n = reg.load_csv(_write_csv(tmp_path, csv))
    assert n == 2


# ── search ────────────────────────────────────────────────────────────────────

def test_search_prefix_match(tmp_path):
    reg = SymbolRegistry()
    reg.load_csv(_write_csv(tmp_path, VALID_CSV))
    results = reg.search("AA")
    tickers = [s.ticker for s in results]
    assert "AAPL" in tickers


def test_search_case_insensitive(tmp_path):
    reg = SymbolRegistry()
    reg.load_csv(_write_csv(tmp_path, VALID_CSV))
    assert len(reg.search("aapl")) > 0


def test_search_filters_by_market(tmp_path):
    reg = SymbolRegistry()
    reg.load_csv(_write_csv(tmp_path, VALID_CSV))
    hk = reg.search("", market="HK")
    assert all(s.market == "HK" for s in hk)
    assert any(s.ticker == "0700.HK" for s in hk)


def test_search_all_market_returns_all(tmp_path):
    reg = SymbolRegistry()
    reg.load_csv(_write_csv(tmp_path, VALID_CSV))
    all_results = reg.search("", market="ALL", limit=100)
    assert len(all_results) == 4


def test_search_respects_limit(tmp_path):
    reg = SymbolRegistry()
    reg.load_csv(_write_csv(tmp_path, VALID_CSV))
    results = reg.search("", limit=2)
    assert len(results) <= 2


def test_search_no_match_returns_empty(tmp_path):
    reg = SymbolRegistry()
    reg.load_csv(_write_csv(tmp_path, VALID_CSV))
    assert reg.search("ZZZZZ") == []


# ── all_tickers ───────────────────────────────────────────────────────────────

def test_all_tickers_unfiltered(tmp_path):
    reg = SymbolRegistry()
    reg.load_csv(_write_csv(tmp_path, VALID_CSV))
    tickers = reg.all_tickers()
    assert set(tickers) == {"AAPL", "MSFT", "0700.HK", "BP.L"}


def test_all_tickers_filtered_by_market(tmp_path):
    reg = SymbolRegistry()
    reg.load_csv(_write_csv(tmp_path, VALID_CSV))
    us = reg.all_tickers(market="US")
    assert set(us) == {"AAPL", "MSFT"}


# ── add / clear ───────────────────────────────────────────────────────────────

def test_add_symbol(tmp_path):
    reg = SymbolRegistry()
    reg.add(Symbol(ticker="NVDA", name="NVIDIA", market="US"))
    assert reg.get("NVDA") is not None
    assert len(reg) == 1


def test_add_replaces_existing_ticker(tmp_path):
    reg = SymbolRegistry()
    reg.add(Symbol(ticker="AAPL", name="Old Name"))
    reg.add(Symbol(ticker="AAPL", name="Apple Inc."))
    assert reg.get("AAPL").name == "Apple Inc."
    assert len(reg) == 1


def test_clear_empties_registry(tmp_path):
    reg = SymbolRegistry()
    reg.load_csv(_write_csv(tmp_path, VALID_CSV))
    reg.clear()
    assert len(reg) == 0
    assert reg.get("AAPL") is None
