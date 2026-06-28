"""Tests for core.pattern_engine — candlestick pattern detection."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.pattern_engine import (
    PatternSignal,
    detect_all,
    _detect_doji,
    _detect_hammer_hanging_man,
    _detect_shooting_star_inv_hammer,
    _detect_marubozu,
    _detect_pin_bar,
    _detect_engulfing,
    _detect_harami,
    _detect_piercing_dark_cloud,
    _detect_tweezer,
    _detect_morning_evening_star,
    _detect_three_soldiers_crows,
    _detect_inside_bar,
)


# ── helpers ────────────────────────────────────────────────────────────────────

def _make_df(rows: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    """Build a minimal OHLCV DataFrame from (o, h, l, c) tuples."""
    o, h, l, c = zip(*rows)
    return pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c, "Volume": 1})


def _sig_at(sigs: list[PatternSignal], bar: int, pattern: str) -> PatternSignal | None:
    return next((s for s in sigs if s.bar == bar and s.pattern == pattern), None)


# ── PatternSignal ──────────────────────────────────────────────────────────────

def test_pattern_signal_immutable():
    sig = PatternSignal(bar=1, pattern="Doji", direction="bull")
    with pytest.raises(Exception):
        sig.bar = 99  # frozen dataclass


def test_detect_all_returns_sorted_by_bar():
    # 30 neutral bars then a bullish marubozu on bar 5
    rows = [(10, 10.5, 9.5, 10.1)] * 30
    rows[5] = (10.0, 12.0, 9.99, 12.0)  # big bull candle
    df = _make_df(rows)
    sigs = detect_all(df)
    bars = [s.bar for s in sigs]
    assert bars == sorted(bars)


def test_detect_all_empty_on_short_df():
    df = _make_df([(10, 11, 9, 10), (10, 11, 9, 10)])
    assert detect_all(df) == []


# ── Doji ──────────────────────────────────────────────────────────────────────

def test_doji_detected_on_tiny_body():
    # body = 0.05, range = 2.0 → ratio 2.5 % < 10 %
    rows = [(10.0, 10.5, 10.0, 10.0)] * 25
    rows[10] = (10.00, 11.00, 9.00, 10.05)  # tiny body inside wide candle
    df = _make_df(rows)
    sigs = _detect_doji(df)
    assert any(s.bar == 10 for s in sigs)


def test_doji_not_detected_on_large_body():
    rows = [(10.0, 12.0, 9.0, 12.0)] * 5  # big bull body
    df = _make_df(rows)
    sigs = _detect_doji(df)
    assert not any(s.pattern == "Doji" for s in sigs)


# ── Hammer / Hanging Man ──────────────────────────────────────────────────────

def test_hammer_detected_in_downtrend():
    # 25 bars declining 1 pt/bar (100 → 76) creates a -20% trend (> 3% threshold)
    rows = []
    for i in range(25):
        p = 100.0 - i * 1.0
        rows.append((p, p + 0.2, p - 0.1, p))
    # Hammer: lower_wick ≈ 4, body = 0.15, upper_wick = 0.05
    rows.append((76.0, 76.2, 72.0, 76.15))
    df = _make_df(rows)
    sigs = _detect_hammer_hanging_man(df)
    hammers = [s for s in sigs if s.pattern == "Hammer"]
    assert len(hammers) > 0


def test_hanging_man_detected_in_uptrend():
    rows = []
    for i in range(25):
        p = 100 + i * 0.5
        rows.append((p, p + 0.2, p - 0.1, p + 0.2))
    # Hanging man: long lower wick in uptrend
    rows.append((115.0, 115.3, 111.0, 115.2))
    df = _make_df(rows)
    sigs = _detect_hammer_hanging_man(df)
    hm = [s for s in sigs if s.pattern == "Hanging Man"]
    assert len(hm) > 0


# ── Shooting Star / Inverted Hammer ──────────────────────────────────────────

def test_shooting_star_detected_in_uptrend():
    rows = []
    for i in range(25):
        p = 100 + i * 0.5
        rows.append((p, p + 0.2, p - 0.1, p + 0.2))
    # Shooting star: long upper wick, body near bottom, in uptrend
    rows.append((115.0, 119.0, 114.9, 115.2))  # upper_wick 3.8, body 0.2
    df = _make_df(rows)
    sigs = _detect_shooting_star_inv_hammer(df)
    stars = [s for s in sigs if s.pattern == "Shooting Star"]
    assert len(stars) > 0 and stars[0].direction == "bear"


# ── Marubozu ──────────────────────────────────────────────────────────────────

def test_bullish_marubozu_near_zero_wicks():
    rows = [(10.0, 10.5, 9.5, 10.1)] * 5
    rows[2] = (10.0, 12.01, 9.99, 12.0)  # body ≈ range; tiny wicks
    df = _make_df(rows)
    sigs = _detect_marubozu(df)
    assert any(s.pattern == "Bullish Marubozu" and s.bar == 2 for s in sigs)


def test_bearish_marubozu_detected():
    rows = [(12.0, 12.01, 9.99, 10.0)] * 1  # bear, body ~= range
    df = _make_df(rows)
    sigs = _detect_marubozu(df)
    assert any(s.pattern == "Bearish Marubozu" for s in sigs)


def test_marubozu_not_detected_with_large_wick():
    rows = [(10.0, 14.0, 9.0, 12.0)] * 1  # large upper wick relative to body
    df = _make_df(rows)
    sigs = _detect_marubozu(df)
    assert not sigs


# ── Pin Bar ───────────────────────────────────────────────────────────────────

def test_bullish_pin_bar_detected():
    # lower wick 4, body 0.3, upper wick 0.2 — lower_wick >= 3 × body ✓
    rows = [(100.3, 100.5, 96.0, 100.0)] * 3
    df = _make_df(rows)
    sigs = _detect_pin_bar(df)
    assert any(s.pattern == "Bullish Pin Bar" for s in sigs)


def test_bearish_pin_bar_detected():
    # upper wick 4, body 0.3, lower wick 0.2
    rows = [(100.0, 104.3, 99.8, 100.3)] * 3
    df = _make_df(rows)
    sigs = _detect_pin_bar(df)
    assert any(s.pattern == "Bearish Pin Bar" for s in sigs)


# ── Engulfing ─────────────────────────────────────────────────────────────────

def test_bullish_engulfing_detected():
    rows = [
        (100.0, 100.5, 99.0, 99.5, 1),   # bear candle (close < open)
        (99.0, 102.0, 98.8, 101.5, 1),   # bull, opens below prev close, closes above prev open
    ]
    df = pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"])
    sigs = _detect_engulfing(df)
    assert any(s.pattern == "Bullish Engulfing" and s.bar == 1 for s in sigs)


def test_bearish_engulfing_detected():
    rows = [
        (99.0, 101.5, 98.8, 101.0, 1),   # bull
        (101.5, 102.0, 98.5, 99.0, 1),   # bear, opens above prev close, closes below prev open
    ]
    df = pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"])
    sigs = _detect_engulfing(df)
    assert any(s.pattern == "Bearish Engulfing" and s.bar == 1 for s in sigs)


def test_engulfing_not_triggered_if_smaller_body():
    # Current body is smaller than prev — not engulfing
    rows = [
        (99.0, 101.0, 98.5, 100.5, 1),  # bull, body 1.5
        (100.5, 101.0, 100.0, 99.8, 1), # bear, body 0.7 < 1.5
    ]
    df = pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"])
    assert not _detect_engulfing(df)


# ── Harami ────────────────────────────────────────────────────────────────────

def test_bullish_harami_detected():
    rows = [
        (105.0, 106.0, 99.0, 100.0, 1),  # big bear: o=105, c=100, body=5
        (101.0, 103.0, 100.5, 102.5, 1), # small bull inside prev body: o > prev c, c < prev o
    ]
    df = pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"])
    sigs = _detect_harami(df)
    assert any(s.pattern == "Bullish Harami" and s.bar == 1 for s in sigs)


def test_bearish_harami_detected():
    rows = [
        (100.0, 106.0, 99.0, 105.0, 1),  # big bull: body=5
        (104.0, 104.5, 103.0, 103.5, 1), # small bear inside prev body
    ]
    df = pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"])
    sigs = _detect_harami(df)
    assert any(s.pattern == "Bearish Harami" and s.bar == 1 for s in sigs)


# ── Piercing Line / Dark Cloud Cover ─────────────────────────────────────────

def test_piercing_line_detected():
    rows = [
        (105.0, 106.0, 99.0, 100.0, 1),  # bear: o=105, c=100 → midpoint=102.5
        (99.5, 104.0, 99.0, 103.0, 1),   # bull: o<prev_close, c>midpoint(102.5) and c<prev_open
    ]
    df = pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"])
    sigs = _detect_piercing_dark_cloud(df)
    assert any(s.pattern == "Piercing Line" for s in sigs)


def test_dark_cloud_cover_detected():
    rows = [
        (100.0, 106.0, 99.0, 105.0, 1),  # bull: o=100, c=105 → midpoint=102.5
        (105.5, 107.0, 100.5, 102.0, 1), # bear: o>prev_close, c<midpoint, c>prev_open
    ]
    df = pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"])
    sigs = _detect_piercing_dark_cloud(df)
    assert any(s.pattern == "Dark Cloud Cover" for s in sigs)


# ── Tweezer ───────────────────────────────────────────────────────────────────

def test_tweezer_bottom_detected():
    rows = [
        (102.0, 103.0, 100.0, 101.0, 1),  # bear, low = 100.0
        (101.0, 103.5, 100.0, 103.0, 1),  # bull, low = 100.0 (matching)
    ]
    df = pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"])
    sigs = _detect_tweezer(df)
    assert any(s.pattern == "Tweezer Bottom" for s in sigs)


def test_tweezer_top_detected():
    rows = [
        (100.0, 104.0, 99.0, 103.0, 1),  # bull, high = 104.0
        (103.0, 104.0, 100.5, 101.0, 1), # bear, high = 104.0
    ]
    df = pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"])
    sigs = _detect_tweezer(df)
    assert any(s.pattern == "Tweezer Top" for s in sigs)


# ── Morning Star / Evening Star ───────────────────────────────────────────────

def test_morning_star_detected():
    # 25 declining bars to establish downtrend (needed by _trend with lookback=20)
    rows = [(120.0 - k * 0.8, 120.3 - k * 0.8, 119.8 - k * 0.8, 120.0 - k * 0.8, 1)
            for k in range(25)]
    # bar i-2 (index 25): large bear candle; midpoint = (103 + 96) / 2 = 99.5
    rows.append((103.0, 104.0, 95.0, 96.0, 1))
    # bar i-1 (index 26): small star (body=0.5 < 40% of 7.0); direction doesn't matter
    rows.append((95.5, 97.0, 94.5, 96.0, 1))
    # bar i (index 27): bull, close 101 > midpoint 99.5
    rows.append((96.0, 104.0, 95.5, 101.0, 1))
    df = pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"])
    sigs = _detect_morning_evening_star(df)
    assert any(s.pattern == "Morning Star" and s.bar == 27 for s in sigs)


def test_evening_star_detected():
    # 25 rising bars to establish uptrend (needed by _trend with lookback=20)
    rows = [(90.0 + k * 0.8, 90.3 + k * 0.8, 89.8 + k * 0.8, 90.0 + k * 0.8, 1)
            for k in range(25)]
    # bar i-2 (index 25): large bull candle; midpoint = (108 + 116) / 2 = 112
    rows.append((108.0, 118.0, 107.5, 116.0, 1))
    # bar i-1 (index 26): small star (body=0.5 < 40% of 8.0); direction doesn't matter
    rows.append((116.5, 118.0, 115.5, 117.0, 1))
    # bar i (index 27): bear, close 111 < midpoint 112
    rows.append((117.0, 117.5, 108.0, 111.0, 1))
    df = pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"])
    sigs = _detect_morning_evening_star(df)
    assert any(s.pattern == "Evening Star" and s.bar == 27 for s in sigs)


# ── Three White Soldiers / Three Black Crows ──────────────────────────────────

def test_three_white_soldiers_detected():
    rows = [
        (100.0, 103.5, 99.8, 103.0, 1),  # bull, body 3.0, range 3.7
        (103.0, 107.5, 102.8, 107.0, 1), # bull, each closing higher
        (107.0, 111.5, 106.8, 111.0, 1), # bull, small upper wick
    ]
    df = pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"])
    sigs = _detect_three_soldiers_crows(df)
    assert any(s.pattern == "Three White Soldiers" for s in sigs)


def test_three_black_crows_detected():
    rows = [
        (111.0, 111.2, 107.5, 108.0, 1), # bear
        (108.0, 108.2, 104.5, 105.0, 1), # bear, each closing lower
        (105.0, 105.2, 101.5, 102.0, 1), # bear
    ]
    df = pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"])
    sigs = _detect_three_soldiers_crows(df)
    assert any(s.pattern == "Three Black Crows" for s in sigs)


# ── Inside Bar ────────────────────────────────────────────────────────────────

def test_inside_bar_detected_after_bear():
    rows = [
        (105.0, 106.0, 99.0, 100.0, 1),  # bear mother bar
        (101.0, 104.0, 100.5, 103.0, 1), # inside bar (h<106, l>99)
    ]
    df = pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"])
    sigs = _detect_inside_bar(df)
    ib = [s for s in sigs if s.pattern == "Inside Bar" and s.bar == 1]
    assert ib and ib[0].direction == "bull"


def test_inside_bar_not_detected_when_range_exceeds_mother():
    rows = [
        (105.0, 106.0, 99.0, 100.0, 1),
        (101.0, 107.0, 98.0, 103.0, 1),  # breaks both high and low of mother
    ]
    df = pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"])
    assert not _detect_inside_bar(df)


# ── detect_all integration ────────────────────────────────────────────────────

def test_detect_all_finds_engulfing_among_random_bars():
    rows = [(10.0, 10.5, 9.5, 10.1)] * 10
    # Insert a clear bullish engulfing at bar 7
    rows[6] = (10.5, 11.0, 10.0, 10.2, )  # bear
    rows[7] = (10.0, 12.0, 9.9, 11.8)     # bull engulfs bar6
    df = _make_df(rows)
    sigs = detect_all(df)
    assert any(s.pattern == "Bullish Engulfing" and s.bar == 7 for s in sigs)


def test_detect_all_direction_is_bull_or_bear():
    rows = [(10 + i * 0.1, 10 + i * 0.1 + 1, 10 + i * 0.1 - 0.5, 10 + i * 0.1 + 0.8) for i in range(50)]
    df = _make_df(rows)
    for sig in detect_all(df):
        assert sig.direction in ("bull", "bear"), f"Bad direction: {sig}"
