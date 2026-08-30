"""Tests for the metric and scoring layer."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import config
import factors


def _frame(close, high=None, low=None, volume=None):
    n = len(close)
    idx = pd.bdate_range(end="2026-08-28", periods=n)
    return pd.DataFrame({
        "Open": close,
        "High": high if high is not None else [c * 1.01 for c in close],
        "Low": low if low is not None else [c * 0.99 for c in close],
        "Close": close,
        "Volume": volume if volume is not None else [1e6] * n,
    }, index=idx)


# ── price metrics ─────────────────────────────────────────────────────────────

def test_short_history_is_rejected():
    assert factors.price_metrics(_frame(list(range(1, 50)))) is None
    assert factors.price_metrics(None) is None


def test_steady_uptrend_reads_as_a_bull_stack():
    close = [100 * 1.001 ** i for i in range(400)]
    m = factors.price_metrics(_frame(close))
    assert m["stack"] == "bull"
    assert m["above_sma200"] is True
    assert m["px_vs_sma200"] > 0
    assert m["sma200_slope"] > 0
    assert m["dist_52w_high"] == pytest.approx(0, abs=1e-9)   # sitting at the high


def test_steady_downtrend_reads_as_a_bear_stack():
    close = [100 * 0.999 ** i for i in range(400)]
    m = factors.price_metrics(_frame(close))
    assert m["stack"] == "bear"
    assert m["above_sma200"] is False
    assert m["px_vs_sma200"] < 0


def test_momentum_12_1_excludes_the_last_month():
    # Flat for a year, then a sharp final-month spike: 12-1 must not see it.
    close = [100.0] * 380 + [400.0] * 21
    m = factors.price_metrics(_frame(close))
    assert m["mom_12_1"] == pytest.approx(0.0, abs=1e-9)
    assert m["ret_1m"] > 1.0


def test_golden_cross_detected_only_inside_the_lookback():
    # Down for a long stretch, then up — SMA50 crosses back above SMA200 late.
    close = [100 * 0.997 ** i for i in range(300)] + [
        100 * 0.997 ** 299 * 1.02 ** i for i in range(1, 60)]
    assert factors.price_metrics(_frame(close))["cross"] == "golden"


def test_no_cross_on_an_unbroken_trend():
    close = [100 * 1.001 ** i for i in range(400)]
    assert factors.price_metrics(_frame(close))["cross"] == "none"


def test_spark_is_normalised_into_the_unit_range():
    m = factors.price_metrics(_frame([100 * 1.001 ** i for i in range(400)]))
    assert len(m["spark"]) == factors.SPARK_POINTS
    assert min(m["spark"]) == 0.0 and max(m["spark"]) == 1.0


def test_flat_series_sparkline_does_not_divide_by_zero():
    m = factors.price_metrics(_frame([50.0] * 400))
    assert set(m["spark"]) == {0.5}


# ── fundamentals ──────────────────────────────────────────────────────────────

def test_loss_making_multiples_become_the_worst_sentinel():
    f = factors.fundamental_metrics({"trailingPE": -12.0, "priceToBook": 0})
    assert f["trailing_pe"] == float("inf")
    assert f["price_to_book"] == float("inf")


def test_negative_equity_leverage_becomes_the_worst_sentinel():
    assert factors.fundamental_metrics({"debtToEquity": -40.0})["debt_to_equity"] == float("inf")
    assert factors.fundamental_metrics({"debtToEquity": 40.0})["debt_to_equity"] == 40.0


def test_missing_profile_falls_back_to_the_unclassified_sector():
    assert factors.fundamental_metrics(None)["sector"] == config.UNKNOWN_SECTOR
    assert factors.fundamental_metrics({"sector": "  "})["sector"] == config.UNKNOWN_SECTOR


# ── cross-sectional scoring ───────────────────────────────────────────────────

def test_percentile_ranks_the_worst_sentinel_as_most_expensive():
    ranked = factors._percentile(pd.Series([5.0, 10.0, 20.0, np.inf]))
    assert ranked.iloc[3] == 100.0
    assert ranked.iloc[0] < ranked.iloc[2] < ranked.iloc[3]


def test_cheap_names_outrank_expensive_ones_on_value():
    frame = pd.DataFrame({
        "market": ["SP500"] * 4,
        "trailing_pe": [5.0, 15.0, 40.0, np.inf],     # last one is loss-making
        "price_to_book": [0.8, 2.0, 6.0, np.inf],
        "price_to_sales": [0.5, 1.5, 5.0, np.inf],
        "ev_to_ebitda": [3.0, 9.0, 25.0, np.inf],
    })
    scored = factors.score_factors(frame)
    v = scored["value_score"].tolist()
    assert v[0] > v[1] > v[2] > v[3], v
    # A loss-making name must score worst on value, never best.
    assert v[3] == pytest.approx(0.0)


def _trend_frame(markets, values):
    """A frame carrying every trend component, so trend is never imputed."""
    return pd.DataFrame({
        "market": markets,
        "px_vs_sma200": values,
        "sma50_vs_sma200": values,
        "sma10_vs_sma50": values,
        "sma200_slope": values,
    })


def test_a_factor_with_no_inputs_scores_neutral_and_is_flagged():
    scored = factors.score_factors(_trend_frame(["SP500"] * 3, [0.1, 0.2, 0.3]))
    assert scored["quality_score"].tolist() == [config.NEUTRAL_SCORE] * 3
    assert scored["quality_imputed"].all()
    assert not scored["trend_imputed"].any()


def test_a_mostly_missing_factor_is_imputed_rather_than_trusted():
    # Only one of the four trend components present — 65 % of the weight is
    # missing, past MAX_MISSING_SHARE, so trend must fall back to neutral.
    frame = pd.DataFrame({"market": ["SP500"] * 3, "px_vs_sma200": [0.1, 0.2, 0.3]})
    scored = factors.score_factors(frame)
    assert scored["trend_imputed"].all()
    assert scored["trend_score"].tolist() == [config.NEUTRAL_SCORE] * 3


def test_markets_are_scored_independently():
    # Identical shapes in each market must produce identical score ladders,
    # even though the HK raw values are an order of magnitude larger.
    scored = factors.score_factors(
        _trend_frame(["SP500"] * 3 + ["HSI"] * 3, [0.1, 0.2, 0.3, 10.0, 20.0, 30.0]))
    us = scored[scored.market == "SP500"]["trend_score"].tolist()
    hk = scored[scored.market == "HSI"]["trend_score"].tolist()
    assert us == hk
    assert scored[scored.market == "SP500"]["rank"].tolist() == [3, 2, 1]
    assert scored[scored.market == "HSI"]["rank"].tolist() == [3, 2, 1]


def test_grades_track_the_score_bands():
    assert factors.grade_for(95) == "A+"
    assert factors.grade_for(80) == "A"
    assert factors.grade_for(0) == "E"


def test_scoring_an_empty_frame_is_a_no_op():
    empty = pd.DataFrame(columns=["market"])
    assert factors.score_factors(empty).empty
