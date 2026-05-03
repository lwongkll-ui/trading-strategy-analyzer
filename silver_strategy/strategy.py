"""
Signal generation for silver miner stocks.

Strategy philosophy
-------------------
Long-only (no short selling).

Regime detection
    Bull  : price > SMA-200 -> look for pullbacks to buy
    Bear  : price < SMA-200 -> stay out or wait for confirmed reversal

Entry scoring (technical, -10 -> +10)
    Trend :  price vs MAs, golden/death cross
    Momentum : EMA cross, MACD, STC fast + slow
    Volatility/pattern : RSI zone, OBV, candlestick pattern, volume confirmation

Historical chart signals (rule-based, no fundamental/macro)
    BUY  : Fast STC crosses above 25 AND (MACD positive OR MACD cross up)
    SELL : Fast STC crosses below 75  OR  MACD line crosses below signal

Current signal
    Adds fundamental score (-4..+4) + macro score (-4..+4)
    BUY threshold  >= +5    SELL threshold <= -3    else HOLD
"""

from __future__ import annotations
import numpy as np
import pandas as pd

from config import (
    STC_OVERSOLD, STC_OVERBOUGHT, RSI_OVERSOLD, RSI_OVERBOUGHT,
    BUY_THRESHOLD, SELL_THRESHOLD,
)
from indicators import BULLISH_PATTERNS, BEARISH_PATTERNS


# -- Technical scoring --------------------------------------------------------

def score_technical(df: pd.DataFrame) -> int:
    """Score the LATEST bar of an indicator-enriched DataFrame."""
    if df.empty:
        return 0
    row = df.iloc[-1]
    score = 0

    # Trend (-5 to +5)
    if row.get("above_sma200", False):
        score += 2
    else:
        score -= 2
    if row.get("above_sma50", False):
        score += 1
    else:
        score -= 1
    if row.get("above_sma20", False):
        score += 1
    if row.get("golden_cross", False):
        score += 1
    else:
        score -= 1

    # Momentum (-4 to +4)
    if row.get("ema_bull", False):
        score += 1
    if row.get("macd_bull", False):
        score += 1
    else:
        score -= 1
    hist = row.get("macd_hist", 0) or 0
    prev_hist = df["macd_hist"].iloc[-2] if len(df) > 1 else hist
    if hist > 0 and hist > prev_hist:
        score += 1

    stc_f = row.get("stc_fast", 50) or 50
    stc_s = row.get("stc_slow", 50) or 50
    if stc_f > 50:
        score += 1
    if stc_f < STC_OVERSOLD:
        score -= 1
    if stc_s > 50:
        score += 1

    # RSI zone (-2 to +2)
    rsi_v = row.get("rsi", 50) or 50
    if RSI_OVERSOLD < rsi_v < RSI_OVERBOUGHT:
        score += 1   # healthy momentum
    if rsi_v > RSI_OVERBOUGHT:
        score -= 1   # overbought - risk of reversal
    if rsi_v < RSI_OVERSOLD:
        score -= 1   # extreme oversold (may bounce, but current pain)
    if rsi_v > 50:
        score += 1

    # Volume / OBV (0 to +1)
    if row.get("obv_bull", False):
        score += 1

    # Candlestick (-1 to +1)
    pattern = row.get("pattern", "")
    if pattern in BULLISH_PATTERNS:
        score += 1
    elif pattern in BEARISH_PATTERNS:
        score -= 1

    return score


def score_weekly_trend(df_weekly: pd.DataFrame) -> int:
    """
    Returns -2 / 0 / +2 based on weekly chart regime.
    Used as a multiplier/filter for daily signals.
    """
    if df_weekly is None or df_weekly.empty:
        return 0
    row = df_weekly.iloc[-1]
    s = 0
    if row.get("above_sma200", False):
        s += 1
    if row.get("golden_cross", False):
        s += 1
    if row.get("macd_bull", False):
        s += 1
    if s >= 2:
        return 2
    if s == 0:
        return -2
    return 0


def score_hourly_trend(df_hourly: pd.DataFrame) -> int:
    """Returns -1 / 0 / +1 based on intraday momentum (entry timing)."""
    if df_hourly is None or df_hourly.empty:
        return 0
    row = df_hourly.iloc[-1]
    s = 0
    if row.get("ema_bull", False):
        s += 1
    if row.get("macd_bull", False):
        s += 1
    if s >= 2:
        return 1
    if s == 0:
        return -1
    return 0


# -- Historical signals for chart ---------------------------------------------

def generate_historical_signals(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds 'buy_signal' and 'sell_signal' boolean columns.
    Uses a state machine so we alternate buy -> sell -> buy.
    """
    df = df.copy()
    df["buy_signal"]  = False
    df["sell_signal"] = False

    in_position = False

    for i in range(len(df)):
        row = df.iloc[i]

        if not in_position:
            # Buy: STC fast crosses above oversold AND MACD supporting
            stc_cross = bool(row.get("stc_fast_cross_up25", False))
            macd_ok   = bool(row.get("macd_bull", False)) or bool(row.get("macd_cross_up", False))
            above_200 = bool(row.get("above_sma200", False))

            if stc_cross and macd_ok:
                df.iat[i, df.columns.get_loc("buy_signal")] = True
                in_position = True
            elif above_200 and bool(row.get("gc_event", False)):
                # Golden cross - buy even without STC signal
                df.iat[i, df.columns.get_loc("buy_signal")] = True
                in_position = True
        else:
            # Sell: STC fast crosses below overbought OR MACD turns negative
            stc_exit  = bool(row.get("stc_fast_cross_dn75", False))
            macd_exit = bool(row.get("macd_cross_down", False))
            dc_exit   = bool(row.get("dc_event", False))

            if stc_exit or macd_exit or dc_exit:
                df.iat[i, df.columns.get_loc("sell_signal")] = True
                in_position = False

    return df


# -- Current signal ------------------------------------------------------------

def get_current_signal(
    df_daily: pd.DataFrame,
    df_weekly: pd.DataFrame,
    df_hourly: pd.DataFrame,
    fund_score: int,
    macro_score: int,
) -> dict:
    tech  = score_technical(df_daily)
    wkly  = score_weekly_trend(df_weekly)
    hrly  = score_hourly_trend(df_hourly)
    total = tech + wkly + fund_score + macro_score

    # Current bar data
    row = df_daily.iloc[-1] if not df_daily.empty else {}

    def _g(k, d=None):
        try:
            return row.get(k, d)
        except Exception:
            return d

    signal = "HOLD"
    if total >= BUY_THRESHOLD:
        signal = "BUY"
    elif total <= SELL_THRESHOLD:
        signal = "AVOID"

    price = _g("Close", 0)
    sma50 = _g("sma50")
    sma200 = _g("sma200")
    regime = "BULL" if _g("above_sma200", False) else "BEAR"

    # Entry zone hints
    atr_v = _g("atr", 0)
    entry_hints = []
    if signal == "BUY":
        sma20_v = _g("sma20")
        bb_lower_v = _g("bb_lower")
        if price and sma20_v:
            entry_hints.append(f"Entry near SMA20 ${sma20_v:.2f}")
        if price and bb_lower_v:
            entry_hints.append(f"BB lower ${bb_lower_v:.2f} as support")
        if price and atr_v:
            stop = price - 2 * atr_v
            target = price + 3 * atr_v
            entry_hints.append(f"Stop ~${stop:.2f} | Target ~${target:.2f} (2:3 R:R)")

    return {
        "signal":       signal,
        "total_score":  total,
        "tech_score":   tech,
        "weekly_score": wkly,
        "hourly_score": hrly,
        "fund_score":   fund_score,
        "macro_score":  macro_score,
        "regime":       regime,
        "price":        price,
        "sma50":        sma50,
        "sma200":       sma200,
        "rsi":          _g("rsi"),
        "stc_fast":     _g("stc_fast"),
        "stc_slow":     _g("stc_slow"),
        "macd_hist":    _g("macd_hist"),
        "pattern":      _g("pattern", ""),
        "atr":          atr_v,
        "vol_ratio":    _g("vol_ratio"),
        "entry_hints":  entry_hints,
    }
