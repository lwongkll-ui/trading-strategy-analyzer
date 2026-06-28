"""Candlestick pattern detection engine.

Pure numpy/pandas — no external TA library.  Each detector scans the full
OHLCV DataFrame and returns :class:`PatternSignal` records.

The main entry point is :func:`detect_all`, which runs every detector and
returns a flat, bar-sorted list.

Pattern catalogue
-----------------
Single-bar:
    Doji, Hammer, Hanging Man, Shooting Star, Inverted Hammer,
    Bullish Marubozu, Bearish Marubozu, Bullish Pin Bar, Bearish Pin Bar

Two-bar:
    Bullish Engulfing, Bearish Engulfing,
    Bullish Harami, Bearish Harami,
    Piercing Line, Dark Cloud Cover,
    Tweezer Bottom, Tweezer Top

Three-bar:
    Morning Star, Evening Star,
    Three White Soldiers, Three Black Crows,
    Inside Bar (directional)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


# ── public data type ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PatternSignal:
    """A single detected candlestick pattern occurrence.

    Attributes:
        bar:       0-based bar index of the *last* candle of the pattern.
        pattern:   Human-readable pattern name.
        direction: ``"bull"`` (long signal) or ``"bear"`` (short signal).
    """
    bar: int
    pattern: str
    direction: str


# ── detection constants ────────────────────────────────────────────────────────

_TREND_LOOKBACK: int = 20   # bars checked for prior trend context (~1 calendar month)
_GAP_TOL: float = 0.002     # 0.2 % tolerance for gap checks; covers minimal overnight gaps

# ── precomputation helpers ─────────────────────────────────────────────────────

def _pre(df: pd.DataFrame):
    """Return per-bar numpy arrays: o, h, l, c, rng, body, btop, bbot, uw, lw, is_bull."""
    o = df["Open"].to_numpy(dtype=float)
    h = df["High"].to_numpy(dtype=float)
    l = df["Low"].to_numpy(dtype=float)
    c = df["Close"].to_numpy(dtype=float)
    rng = h - l
    rng = np.where(rng == 0, 1e-10, rng)
    body = np.abs(c - o)
    btop = np.maximum(o, c)
    bbot = np.minimum(o, c)
    uw = h - btop
    lw = bbot - l
    is_bull = c >= o
    return o, h, l, c, rng, body, btop, bbot, uw, lw, is_bull


def _trend(c: np.ndarray, i: int, lookback: int = 20) -> int:
    """Return 1 (uptrend), -1 (downtrend), 0 (neutral) based on *lookback*-bar slope."""
    if i < lookback or c[i - lookback] <= 0:
        return 0
    chg = c[i] / c[i - lookback] - 1.0
    if chg > 0.03:
        return 1
    if chg < -0.03:
        return -1
    return 0


# ── single-bar patterns ────────────────────────────────────────────────────────

def _detect_doji(df: pd.DataFrame) -> list[PatternSignal]:
    """Doji: body < 10 % of range.  Direction implied by prior trend."""
    o, h, l, c, rng, body, *_ = _pre(df)
    out = []
    for i in range(1, len(df)):
        if body[i] / rng[i] >= 0.10:
            continue
        t = _trend(c, i)
        direction = "bull" if t <= 0 else "bear"
        out.append(PatternSignal(i, "Doji", direction))
    return out


def _detect_hammer_hanging_man(df: pd.DataFrame) -> list[PatternSignal]:
    """Hammer (bull, downtrend) / Hanging Man (bear, uptrend).

    Shape: lower wick ≥ 2.5× body; upper wick ≤ 0.5× body (small body near top).
    Trend is evaluated on bar i-1 (the bar before the signal) so the signal
    candle's own close does not inflate / deflate the trend reading.
    """
    o, h, l, c, rng, body, btop, bbot, uw, lw, is_bull = _pre(df)
    out = []
    for i in range(1, len(df)):
        if body[i] < 1e-8 or rng[i] < 1e-8:
            continue
        if lw[i] < 2.5 * body[i] or uw[i] > 0.5 * body[i]:
            continue
        t = _trend(c, i - 1)
        if t <= -1:
            out.append(PatternSignal(i, "Hammer", "bull"))
        elif t >= 1:
            out.append(PatternSignal(i, "Hanging Man", "bear"))
    return out


def _detect_shooting_star_inv_hammer(df: pd.DataFrame) -> list[PatternSignal]:
    """Shooting Star (bear, uptrend) / Inverted Hammer (bull, downtrend).

    Shape: upper wick ≥ 2.5× body; lower wick ≤ 0.5× body (small body near bottom).
    Trend is evaluated on bar i-1 so the signal candle's own close does not
    inflate / deflate the trend reading.
    """
    o, h, l, c, rng, body, btop, bbot, uw, lw, is_bull = _pre(df)
    out = []
    for i in range(1, len(df)):
        if body[i] < 1e-8 or rng[i] < 1e-8:
            continue
        if uw[i] < 2.5 * body[i] or lw[i] > 0.5 * body[i]:
            continue
        t = _trend(c, i - 1)
        if t >= 1:
            out.append(PatternSignal(i, "Shooting Star", "bear"))
        elif t <= -1:
            out.append(PatternSignal(i, "Inverted Hammer", "bull"))
    return out


def _detect_marubozu(df: pd.DataFrame) -> list[PatternSignal]:
    """Marubozu: body ≥ 85 % of range; wicks each < 5 % of body."""
    o, h, l, c, rng, body, btop, bbot, uw, lw, is_bull = _pre(df)
    out = []
    for i in range(len(df)):
        if body[i] < rng[i] * 0.85:
            continue
        if uw[i] > body[i] * 0.05 or lw[i] > body[i] * 0.05:
            continue
        if is_bull[i]:
            out.append(PatternSignal(i, "Bullish Marubozu", "bull"))
        else:
            out.append(PatternSignal(i, "Bearish Marubozu", "bear"))
    return out


def _detect_pin_bar(df: pd.DataFrame) -> list[PatternSignal]:
    """Pin bar: shadow ≥ 3× body; body in outer 40 % of range.

    Less strict than Hammer/Shooting Star — no trend requirement, so it
    captures key-level rejections regardless of context.
    """
    o, h, l, c, rng, body, btop, bbot, uw, lw, is_bull = _pre(df)
    out = []
    for i in range(len(df)):
        if body[i] < 1e-8 or rng[i] < 1e-8:
            continue
        # Bullish pin: long lower wick, body in upper 40 %
        if lw[i] >= 3.0 * body[i] and bbot[i] >= l[i] + rng[i] * 0.60:
            out.append(PatternSignal(i, "Bullish Pin Bar", "bull"))
        # Bearish pin: long upper wick, body in lower 40 %
        elif uw[i] >= 3.0 * body[i] and btop[i] <= l[i] + rng[i] * 0.40:
            out.append(PatternSignal(i, "Bearish Pin Bar", "bear"))
    return out


# ── two-bar patterns ───────────────────────────────────────────────────────────

def _detect_engulfing(df: pd.DataFrame) -> list[PatternSignal]:
    """Bullish / Bearish Engulfing: current body completely engulfs previous body."""
    o, h, l, c, rng, body, btop, bbot, uw, lw, is_bull = _pre(df)
    out = []
    for i in range(1, len(df)):
        po, pc = o[i - 1], c[i - 1]
        co, cc = o[i], c[i]
        # Bullish: prev bear, curr bull engulfs prev body
        if not is_bull[i - 1] and is_bull[i]:
            if co <= pc and cc >= po and body[i] > body[i - 1]:
                out.append(PatternSignal(i, "Bullish Engulfing", "bull"))
        # Bearish: prev bull, curr bear engulfs prev body
        elif is_bull[i - 1] and not is_bull[i]:
            if co >= pc and cc <= po and body[i] > body[i - 1]:
                out.append(PatternSignal(i, "Bearish Engulfing", "bear"))
    return out


def _detect_harami(df: pd.DataFrame) -> list[PatternSignal]:
    """Bullish / Bearish Harami: small candle contained within a large prior body."""
    o, h, l, c, rng, body, btop, bbot, uw, lw, is_bull = _pre(df)
    out = []
    for i in range(1, len(df)):
        pb = body[i - 1]
        if pb < rng[i - 1] * 0.40:
            continue
        if body[i] > pb * 0.50:
            continue
        # Bullish harami: prev bear, curr small bull contained in prev body
        if not is_bull[i - 1] and is_bull[i]:
            if o[i] > c[i - 1] and c[i] < o[i - 1]:
                out.append(PatternSignal(i, "Bullish Harami", "bull"))
        # Bearish harami: prev bull, curr small bear contained in prev body
        elif is_bull[i - 1] and not is_bull[i]:
            if o[i] < c[i - 1] and c[i] > o[i - 1]:
                out.append(PatternSignal(i, "Bearish Harami", "bear"))
    return out


def _detect_piercing_dark_cloud(df: pd.DataFrame) -> list[PatternSignal]:
    """Piercing Line (bull) / Dark Cloud Cover (bear).

    Requires previous candle to be significant (body ≥ 40 % of range) and
    current close to penetrate beyond the midpoint of the prior body.
    """
    o, h, l, c, rng, body, btop, bbot, uw, lw, is_bull = _pre(df)
    out = []
    for i in range(1, len(df)):
        if body[i - 1] < rng[i - 1] * 0.40:
            continue
        mid = (o[i - 1] + c[i - 1]) / 2.0
        # Piercing Line: prev bear, curr bull opens ≤ prev close, closes > midpoint
        if not is_bull[i - 1] and is_bull[i]:
            if o[i] <= c[i - 1] and c[i] > mid and c[i] < o[i - 1]:
                out.append(PatternSignal(i, "Piercing Line", "bull"))
        # Dark Cloud Cover: prev bull, curr bear opens ≥ prev close, closes < midpoint
        elif is_bull[i - 1] and not is_bull[i]:
            if o[i] >= c[i - 1] and c[i] < mid and c[i] > o[i - 1]:
                out.append(PatternSignal(i, "Dark Cloud Cover", "bear"))
    return out


def _detect_tweezer(df: pd.DataFrame) -> list[PatternSignal]:
    """Tweezer Bottom (bull) / Top (bear): matching lows/highs within 0.2 %."""
    o, h, l, c, rng, body, btop, bbot, uw, lw, is_bull = _pre(df)
    out = []
    for i in range(1, len(df)):
        ref_h = max(h[i], h[i - 1])
        ref_l = max(l[i], l[i - 1])
        tol_h = ref_h * 0.002
        tol_l = ref_l * 0.002
        # Tweezer bottom: matching lows, prev bear → curr bull
        if abs(l[i] - l[i - 1]) <= tol_l and not is_bull[i - 1] and is_bull[i]:
            out.append(PatternSignal(i, "Tweezer Bottom", "bull"))
        # Tweezer top: matching highs, prev bull → curr bear
        elif abs(h[i] - h[i - 1]) <= tol_h and is_bull[i - 1] and not is_bull[i]:
            out.append(PatternSignal(i, "Tweezer Top", "bear"))
    return out


# ── three-bar patterns ─────────────────────────────────────────────────────────

def _detect_morning_evening_star(df: pd.DataFrame) -> list[PatternSignal]:
    """Morning Star (bull) / Evening Star (bear).

    Per Investopedia definition:
      Morning Star — prior downtrend → large bear candle (i-2) → small star
        body of any direction (i-1, gaps down from i-2) → large bull candle
        that gaps up from star and closes above midpoint of bar i-2 (i).
      Evening Star — prior uptrend → large bull candle (i-2) → small star
        (i-1, gaps up from i-2) → large bear candle that gaps down from star
        and closes below midpoint of bar i-2 (i).

    Trend window  : _TREND_LOOKBACK bars ending at bar i-2 (≈ 1 calendar month).
    Gap tolerance : _GAP_TOL (0.2 %) — accepts near-gap opens for stocks where
                    true overnight gaps are rarer than in crypto.
    """
    o, h, l, c, rng, body, btop, bbot, uw, lw, is_bull = _pre(df)
    out = []
    for i in range(2, len(df)):
        b0 = body[i - 2]
        if b0 < rng[i - 2] * 0.40:
            continue
        if body[i - 1] > b0 * 0.40:
            continue
        mid0 = (o[i - 2] + c[i - 2]) / 2.0

        # Morning Star: prior downtrend → bear → small (any dir) → bull > midpoint
        if not is_bull[i - 2] and is_bull[i] and c[i] > mid0:
            if _trend(c, i - 2, lookback=_TREND_LOOKBACK) < 0:
                # Star opens at or below bar i-2 close (gap down); bull opens at
                # or above star close (gap up) — both with _GAP_TOL tolerance
                star_gap_down = o[i - 1] <= c[i - 2] * (1 + _GAP_TOL)
                bull_gap_up   = o[i]     >= c[i - 1] * (1 - _GAP_TOL)
                if star_gap_down and bull_gap_up:
                    out.append(PatternSignal(i, "Morning Star", "bull"))

        # Evening Star: prior uptrend → bull → small (any dir) → bear < midpoint
        elif is_bull[i - 2] and not is_bull[i] and c[i] < mid0:
            if _trend(c, i - 2, lookback=_TREND_LOOKBACK) > 0:
                # Star opens at or above bar i-2 close (gap up); bear opens at
                # or below star close (gap down) — both with _GAP_TOL tolerance
                star_gap_up   = o[i - 1] >= c[i - 2] * (1 - _GAP_TOL)
                bear_gap_down = o[i]     <= c[i - 1] * (1 + _GAP_TOL)
                if star_gap_up and bear_gap_down:
                    out.append(PatternSignal(i, "Evening Star", "bear"))
    return out


def _detect_three_soldiers_crows(df: pd.DataFrame) -> list[PatternSignal]:
    """Three White Soldiers (bull) / Three Black Crows (bear).

    Three consecutive same-direction candles, each with a large body and
    each closing beyond the prior close; minimal opposing wick.
    """
    o, h, l, c, rng, body, btop, bbot, uw, lw, is_bull = _pre(df)
    out = []
    for i in range(2, len(df)):
        i0, i1, i2 = i - 2, i - 1, i
        # Three White Soldiers
        if all(is_bull[k] for k in (i0, i1, i2)):
            if all(body[k] >= rng[k] * 0.50 for k in (i0, i1, i2)):
                if c[i2] > c[i1] > c[i0]:
                    if uw[i2] < body[i2] * 0.30 and uw[i1] < body[i1] * 0.30:
                        out.append(PatternSignal(i, "Three White Soldiers", "bull"))
        # Three Black Crows
        if all(not is_bull[k] for k in (i0, i1, i2)):
            if all(body[k] >= rng[k] * 0.50 for k in (i0, i1, i2)):
                if c[i2] < c[i1] < c[i0]:
                    if lw[i2] < body[i2] * 0.30 and lw[i1] < body[i1] * 0.30:
                        out.append(PatternSignal(i, "Three Black Crows", "bear"))
    return out


def _detect_inside_bar(df: pd.DataFrame) -> list[PatternSignal]:
    """Inside Bar: current high/low fully contained within prior high/low.

    Direction follows the prior candle: after a bear candle → bull signal
    (potential reversal/consolidation breakout); after bull → bear.
    """
    o, h, l, c, rng, body, btop, bbot, uw, lw, is_bull = _pre(df)
    out = []
    for i in range(1, len(df)):
        if h[i] < h[i - 1] and l[i] > l[i - 1]:
            direction = "bull" if not is_bull[i - 1] else "bear"
            out.append(PatternSignal(i, "Inside Bar", direction))
    return out


# ── registry & public API ──────────────────────────────────────────────────────

_DETECTORS = [
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
]

ALL_PATTERN_NAMES: list[str] = [
    "Doji",
    "Hammer", "Hanging Man",
    "Shooting Star", "Inverted Hammer",
    "Bullish Marubozu", "Bearish Marubozu",
    "Bullish Pin Bar", "Bearish Pin Bar",
    "Bullish Engulfing", "Bearish Engulfing",
    "Bullish Harami", "Bearish Harami",
    "Piercing Line", "Dark Cloud Cover",
    "Tweezer Bottom", "Tweezer Top",
    "Morning Star", "Evening Star",
    "Three White Soldiers", "Three Black Crows",
    "Inside Bar",
]


def detect_all(df: pd.DataFrame) -> list[PatternSignal]:
    """Run every detector and return bar-sorted, unique-signal list.

    Args:
        df: OHLCV DataFrame with at least Open, High, Low, Close columns
            and a minimum of 3 rows.

    Returns:
        List of :class:`PatternSignal` objects sorted by ``bar`` ascending.
        A single bar may carry signals from multiple detectors.
    """
    if len(df) < 3:
        return []

    signals: list[PatternSignal] = []
    for fn in _DETECTORS:
        signals.extend(fn(df))

    signals.sort(key=lambda s: s.bar)
    return signals
