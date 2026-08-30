"""Tests for universe loading and the end-to-end screening pipeline."""
from __future__ import annotations

import json
import math

import pandas as pd
import pytest

import config
import demo
import factors
import screener
import universe
from universe import Constituent


# ── universe ──────────────────────────────────────────────────────────────────

def test_every_configured_universe_loads():
    for market in config.UNIVERSES:
        names = universe.load_universe(market)
        assert names, f"{market} constituent list is empty"
        assert all(c.market == market for c in names)


def test_universe_drops_duplicate_tickers():
    tickers = [c.ticker for c in universe.load_universe("SP500")]
    assert len(tickers) == len(set(tickers))


def test_unknown_market_is_rejected():
    with pytest.raises(KeyError):
        universe.load_universe("NIKKEI")


def test_hong_kong_tickers_keep_their_yfinance_suffix():
    assert all(c.ticker.endswith(".HK") for c in universe.load_universe("HSI"))


# ── row building ──────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def scored():
    names = [Constituent(t, t + " Inc.", "SP500") for t in ("AAA", "BBB", "CCC", "DDD")]
    names += [Constituent(t, t + " Ltd.", "HSI") for t in ("0001.HK", "0002.HK", "0003.HK")]
    tickers = [c.ticker for c in names]
    return names, screener.build_rows(
        names, demo.synth_prices_many(tickers), demo.synth_profiles_many(tickers))


def test_every_name_is_scored(scored):
    names, frame = scored
    assert len(frame) == len(names)
    assert frame["score"].between(0, 100).all()
    assert frame["grade"].isin([g for _, g in config.GRADE_BANDS]).all()


def test_ranks_restart_per_market(scored):
    _, frame = scored
    assert sorted(frame[frame.market == "SP500"]["rank"]) == [1, 2, 3, 4]
    assert sorted(frame[frame.market == "HSI"]["rank"]) == [1, 2, 3]


def test_a_ticker_without_price_history_is_skipped():
    names = [Constituent("AAA", "A", "SP500"), Constituent("BBB", "B", "SP500")]
    frame = screener.build_rows(names, {"AAA": demo.synth_prices("AAA")}, {})
    assert frame["ticker"].tolist() == ["AAA"]


def test_no_scorable_names_yields_an_empty_frame():
    frame = screener.build_rows([Constituent("AAA", "A", "SP500")], {}, {})
    assert frame.empty


# ── payload ───────────────────────────────────────────────────────────────────

def test_payload_is_strict_json(scored):
    _, frame = scored
    payload = screener.to_payload(frame)
    # allow_nan=False rejects NaN and Infinity, which JSON.parse cannot read.
    json.dumps(payload, allow_nan=False)
    assert set(payload[0]) == set(screener.ROW_FIELDS)


def test_payload_converts_the_worst_sentinel_to_null():
    frame = pd.DataFrame([{
        "ticker": "AAA", "market": "SP500", "trailing_pe": float("inf"),
        "price_to_book": float("nan"), "score": 50.0,
    }])
    row = screener.to_payload(frame)[0]
    assert row["trailing_pe"] is None
    assert row["price_to_book"] is None


def test_payload_of_an_empty_frame_is_empty():
    assert screener.to_payload(pd.DataFrame(columns=screener.ROW_FIELDS)) == []


# ── summary ───────────────────────────────────────────────────────────────────

def test_summary_counts_agree_with_the_rows(scored):
    _, frame = scored
    for entry in screener.summarise(frame):
        group = frame[frame.market == entry["market"]]
        assert entry["count"] == len(group)
        assert entry["above_sma200"] == int(group["above_sma200"].sum())
        assert 0 <= entry["breadth"] <= 100
        assert isinstance(entry["breadth"], float)   # not a numpy scalar


def test_summary_of_an_empty_frame_is_empty():
    assert screener.summarise(pd.DataFrame(columns=["market"])) == []


# ── full run ──────────────────────────────────────────────────────────────────

def test_demo_run_produces_a_renderable_result():
    result = screener.run(["SP500", "HSI"], limit=5, demo_mode=True, log=lambda *a: None)
    assert result["demo"] is True
    assert len(result["rows"]) == 10
    assert {s["market"] for s in result["summary"]} == {"SP500", "HSI"}
    json.dumps(result, allow_nan=False)


def test_limit_applies_per_market_so_both_indices_survive():
    result = screener.run(["SP500", "HSI"], limit=3, demo_mode=True, log=lambda *a: None)
    markets = [r["market"] for r in result["rows"]]
    assert markets.count("SP500") == 3
    assert markets.count("HSI") == 3


def test_no_fundamentals_leaves_quality_and_value_neutral():
    result = screener.run(["SP500"], limit=5, fundamentals=False, demo_mode=True,
                          log=lambda *a: None)
    assert result["fundamentals"] is False
    for row in result["rows"]:
        assert row["quality_score"] == config.NEUTRAL_SCORE
        assert row["value_score"] == config.NEUTRAL_SCORE
        assert row["quality_imputed"] and row["value_imputed"]
        assert row["sector"] == config.UNKNOWN_SECTOR
        # Trend and momentum still come from prices, so the page stays useful.
        assert not row["trend_imputed"]
