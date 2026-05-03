"""Technical indicator calculation using pandas-ta."""

import pandas as pd
import pandas_ta as ta
import numpy as np
from config import (
    SMA_200, SMA_50, EMA_20,
    RSI_LEN, MACD_FAST, MACD_SLOW, MACD_SIGNAL,
    BB_LEN, BB_STD, ATR_LEN, STOCH_K, STOCH_D, VOL_SMA,
)


def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Attach all indicators to the OHLCV dataframe in-place."""
    df = df.copy()

    # ── Trend ──────────────────────────────────────────────────────────────────
    df["sma200"] = ta.sma(df["close"], length=SMA_200)
    df["sma50"]  = ta.sma(df["close"], length=SMA_50)
    df["ema20"]  = ta.ema(df["close"], length=EMA_20)

    # ── Momentum ───────────────────────────────────────────────────────────────
    df["rsi"] = ta.rsi(df["close"], length=RSI_LEN)

    macd = ta.macd(df["close"], fast=MACD_FAST, slow=MACD_SLOW, signal=MACD_SIGNAL)
    df["macd"]        = macd[f"MACD_{MACD_FAST}_{MACD_SLOW}_{MACD_SIGNAL}"]
    df["macd_signal"] = macd[f"MACDs_{MACD_FAST}_{MACD_SLOW}_{MACD_SIGNAL}"]
    df["macd_hist"]   = macd[f"MACDh_{MACD_FAST}_{MACD_SLOW}_{MACD_SIGNAL}"]

    stoch = ta.stochrsi(df["close"], length=RSI_LEN, rsi_length=RSI_LEN, k=STOCH_K, d=STOCH_D)
    df["stoch_k"] = stoch[f"STOCHRSIk_{RSI_LEN}_{RSI_LEN}_{STOCH_K}_{STOCH_D}"]
    df["stoch_d"] = stoch[f"STOCHRSId_{RSI_LEN}_{RSI_LEN}_{STOCH_K}_{STOCH_D}"]

    # ── Volatility ─────────────────────────────────────────────────────────────
    bb = ta.bbands(df["close"], length=BB_LEN, std=BB_STD)
    # pandas-ta >=0.4 names: BBU_{len}_{std}_{std} — find dynamically
    bb_upper_col = [c for c in bb.columns if c.startswith("BBU_")][0]
    bb_mid_col   = [c for c in bb.columns if c.startswith("BBM_")][0]
    bb_lower_col = [c for c in bb.columns if c.startswith("BBL_")][0]
    df["bb_upper"] = bb[bb_upper_col]
    df["bb_mid"]   = bb[bb_mid_col]
    df["bb_lower"] = bb[bb_lower_col]
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"] * 100

    df["atr"] = ta.atr(df["high"], df["low"], df["close"], length=ATR_LEN)

    # ── Volume ─────────────────────────────────────────────────────────────────
    df["vol_sma"]   = ta.sma(df["volume"], length=VOL_SMA)
    df["vol_ratio"] = df["volume"] / df["vol_sma"]   # >1 = above-avg volume
    df["obv"]       = ta.obv(df["close"], df["volume"])

    # ── Derived signals ────────────────────────────────────────────────────────
    df["above_200"] = (df["close"] > df["sma200"]).astype(int)
    df["golden_cross"] = (
        (df["sma50"] > df["sma200"]) & (df["sma50"].shift(1) <= df["sma200"].shift(1))
    ).astype(int)
    df["death_cross"] = (
        (df["sma50"] < df["sma200"]) & (df["sma50"].shift(1) >= df["sma200"].shift(1))
    ).astype(int)
    df["macd_bull_cross"] = (
        (df["macd"] > df["macd_signal"]) & (df["macd"].shift(1) <= df["macd_signal"].shift(1))
    ).astype(int)
    df["macd_bear_cross"] = (
        (df["macd"] < df["macd_signal"]) & (df["macd"].shift(1) >= df["macd_signal"].shift(1))
    ).astype(int)

    # Distance from 200 SMA (%)
    df["dist_200_pct"] = (df["close"] - df["sma200"]) / df["sma200"] * 100

    return df


# ── Candlestick Pattern Detection ──────────────────────────────────────────────

def detect_candlestick_pattern(df: pd.DataFrame) -> str:
    """Identify the most recent notable candlestick pattern."""
    if len(df) < 3:
        return "None"
    o, h, l, c = (
        df["open"].values,
        df["high"].values,
        df["low"].values,
        df["close"].values,
    )
    i = -1  # last candle
    body    = abs(c[i] - o[i])
    range_  = h[i] - l[i]
    upper_w = h[i] - max(c[i], o[i])
    lower_w = min(c[i], o[i]) - l[i]
    bullish = c[i] > o[i]

    if range_ == 0:
        return "None"

    # Doji
    if body / range_ < 0.1:
        return "Doji (indecision)"

    # Hammer / Inverted Hammer
    if lower_w > 2 * body and upper_w < 0.1 * range_ and c[i] > o[i]:
        return "Hammer (bullish reversal)"
    if upper_w > 2 * body and lower_w < 0.1 * range_ and c[i] < o[i]:
        return "Shooting Star (bearish reversal)"

    # Engulfing
    if (c[i] > o[i] and c[i-1] < o[i-1]
            and c[i] > o[i-1] and o[i] < c[i-1]):
        return "Bullish Engulfing"
    if (c[i] < o[i] and c[i-1] > o[i-1]
            and c[i] < o[i-1] and o[i] > c[i-1]):
        return "Bearish Engulfing"

    # Marubozu (strong trend candle)
    if body / range_ > 0.9 and bullish:
        return "Bullish Marubozu (strong buying)"
    if body / range_ > 0.9 and not bullish:
        return "Bearish Marubozu (strong selling)"

    # Three consecutive candles
    if c[i] > o[i] and c[i-1] > o[i-1] and c[i-2] > o[i-2]:
        return "Three White Soldiers (strong uptrend)"
    if c[i] < o[i] and c[i-1] < o[i-1] and c[i-2] < o[i-2]:
        return "Three Black Crows (strong downtrend)"

    return "Standard candle"


# ── Divergence Detection ───────────────────────────────────────────────────────

def detect_rsi_divergence(df: pd.DataFrame, lookback: int = 14) -> str:
    """Simple hidden/regular divergence on recent window."""
    sub = df.tail(lookback).copy()
    price_higher = sub["close"].iloc[-1] > sub["close"].iloc[0]
    rsi_higher   = sub["rsi"].iloc[-1]   > sub["rsi"].iloc[0]

    if price_higher and not rsi_higher:
        return "Bearish Divergence (momentum weakening)"
    if not price_higher and rsi_higher:
        return "Bullish Divergence (momentum building)"
    if not price_higher and not rsi_higher:
        return "Hidden Bearish Divergence"
    return "No significant divergence"


# ── Support / Resistance Levels ────────────────────────────────────────────────

def key_levels(df: pd.DataFrame, n: int = 90) -> dict:
    """Approximate swing highs/lows as S/R zones."""
    sub = df.tail(n)
    return {
        "resistance": round(float(sub["high"].max()), 0),
        "support":    round(float(sub["low"].min()),  0),
        "pivot":      round(float(
            (sub["high"].iloc[-1] + sub["low"].iloc[-1] + sub["close"].iloc[-1]) / 3
        ), 0),
    }
