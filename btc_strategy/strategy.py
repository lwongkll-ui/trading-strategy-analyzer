"""
Bull & Bear strategy rules — returns scored signal with rationale.

Signal score scale:
  +3 Strong Buy   +2 Buy       +1 Lean Long
   0 Neutral
  -1 Lean Short  -2 Sell      -3 Strong Sell / Short
"""

from __future__ import annotations
import pandas as pd
from config import (
    BULL_RSI_OVERSOLD, BULL_RSI_OVERBOUGHT, BULL_RSI_HEALTHY,
    BEAR_RSI_OVERBOUGHT, BEAR_RSI_OVERSOLD,
    OVEREXTENDED_PCT, SMA_200,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _latest(df: pd.DataFrame, col: str):
    return float(df[col].iloc[-1])


def _prev(df: pd.DataFrame, col: str):
    return float(df[col].iloc[-2])


# ── Bull Market Logic (BTC > 200 SMA) ─────────────────────────────────────────

def bull_signals(df: pd.DataFrame) -> list[tuple[int, str]]:
    """Return list of (score, reason) tuples for bull market."""
    sigs = []
    rsi       = _latest(df, "rsi")
    macd      = _latest(df, "macd")
    macd_sig  = _latest(df, "macd_signal")
    macd_hist = _latest(df, "macd_hist")
    prev_hist = _prev(df, "macd_hist")
    close     = _latest(df, "close")
    sma50     = _latest(df, "sma50")
    ema20     = _latest(df, "ema20")
    bb_lower  = _latest(df, "bb_lower")
    bb_upper  = _latest(df, "bb_upper")
    vol_ratio = _latest(df, "vol_ratio")
    dist200   = _latest(df, "dist_200_pct")
    stoch_k   = _latest(df, "stoch_k")
    golden    = _latest(df, "golden_cross")

    # ─ Trend alignment ────────────────────────────────────────────────────────
    if close > sma50 > _latest(df, "sma200"):
        sigs.append((+2, "Price > SMA50 > SMA200 — perfect bull alignment"))
    elif close > ema20:
        sigs.append((+1, "Price above EMA20 — short-term uptrend intact"))
    else:
        sigs.append((-1, "Price below EMA20 — short-term weakness in bull trend"))

    if golden:
        sigs.append((+3, "GOLDEN CROSS just formed — major bull signal"))

    # ─ RSI ────────────────────────────────────────────────────────────────────
    if rsi < BULL_RSI_OVERSOLD:
        sigs.append((+3, f"RSI {rsi:.1f} < {BULL_RSI_OVERSOLD} — oversold dip in bull → Strong Buy"))
    elif BULL_RSI_HEALTHY[0] <= rsi <= BULL_RSI_HEALTHY[1]:
        sigs.append((+1, f"RSI {rsi:.1f} — healthy bull momentum zone"))
    elif rsi > BULL_RSI_OVERBOUGHT:
        sigs.append((-2, f"RSI {rsi:.1f} > {BULL_RSI_OVERBOUGHT} — overbought → take partial profits"))
    elif rsi > 70:
        sigs.append((-1, f"RSI {rsi:.1f} — approaching overbought, reduce risk"))

    # ─ MACD ───────────────────────────────────────────────────────────────────
    if _latest(df, "macd_bull_cross"):
        sigs.append((+2, "MACD bullish crossover — momentum turning up"))
    elif _latest(df, "macd_bear_cross"):
        sigs.append((-2, "MACD bearish crossover — momentum rolling over"))
    elif macd > macd_sig and macd_hist > prev_hist:
        sigs.append((+1, "MACD above signal & histogram expanding — bullish momentum"))
    elif macd < macd_sig:
        sigs.append((-1, "MACD below signal — weakening momentum"))

    # ─ Bollinger Bands ────────────────────────────────────────────────────────
    if close <= bb_lower:
        sigs.append((+2, "Price at lower BB — oversold squeeze, buy signal in uptrend"))
    elif close >= bb_upper:
        sigs.append((-1, "Price at upper BB — extended, expect mean reversion"))

    # ─ Volume ─────────────────────────────────────────────────────────────────
    if vol_ratio > 1.5 and close > _prev(df, "close"):
        sigs.append((+1, f"Volume {vol_ratio:.1f}x above average on up-move — conviction buying"))
    elif vol_ratio > 1.5 and close < _prev(df, "close"):
        sigs.append((-2, f"Volume {vol_ratio:.1f}x above average on down-move — distribution warning"))

    # ─ Stochastic RSI ─────────────────────────────────────────────────────────
    if stoch_k < 20:
        sigs.append((+2, f"StochRSI {stoch_k:.1f} — oversold, high probability bounce"))
    elif stoch_k > 80:
        sigs.append((-1, f"StochRSI {stoch_k:.1f} — overbought area"))

    # ─ Overextension ──────────────────────────────────────────────────────────
    if dist200 > OVEREXTENDED_PCT:
        sigs.append((-2, f"Price {dist200:.1f}% above 200 SMA — historically overextended, reduce size"))
    elif 15 <= dist200 <= OVEREXTENDED_PCT:
        sigs.append((-1, f"Price {dist200:.1f}% above 200 SMA — elevated, set trailing stops"))

    # ─ Dip-buy near SMA50 ─────────────────────────────────────────────────────
    sma50_dist = (close - sma50) / sma50 * 100
    if -3 <= sma50_dist <= 3:
        sigs.append((+2, f"Price testing SMA50 (±3%) — classic bull dip-buy zone"))

    return sigs


# ── Bear Market Logic (BTC < 200 SMA) ─────────────────────────────────────────

def bear_signals(df: pd.DataFrame) -> list[tuple[int, str]]:
    """Return list of (score, reason) tuples for bear market."""
    sigs = []
    rsi       = _latest(df, "rsi")
    macd      = _latest(df, "macd")
    macd_sig  = _latest(df, "macd_signal")
    macd_hist = _latest(df, "macd_hist")
    prev_hist = _prev(df, "macd_hist")
    close     = _latest(df, "close")
    sma200    = _latest(df, "sma200")
    sma50     = _latest(df, "sma50")
    ema20     = _latest(df, "ema20")
    bb_lower  = _latest(df, "bb_lower")
    bb_upper  = _latest(df, "bb_upper")
    vol_ratio = _latest(df, "vol_ratio")
    dist200   = _latest(df, "dist_200_pct")  # negative in bear
    stoch_k   = _latest(df, "stoch_k")
    death     = _latest(df, "death_cross")

    # ─ Trend alignment ────────────────────────────────────────────────────────
    if close < sma50 < sma200:
        sigs.append((-2, "Price < SMA50 < SMA200 — confirmed bear alignment, stay cautious"))
    elif close < ema20:
        sigs.append((-1, "Price below EMA20 — short-term downtrend"))
    else:
        sigs.append((0, "Price above EMA20 but below 200 SMA — bear rally zone"))

    if death:
        sigs.append((-3, "DEATH CROSS just formed — major bear signal, reduce all longs"))

    # ─ RSI ────────────────────────────────────────────────────────────────────
    if rsi > BEAR_RSI_OVERBOUGHT:
        sigs.append((-2, f"RSI {rsi:.1f} > {BEAR_RSI_OVERBOUGHT} in bear — sell rally signal"))
    elif rsi < BEAR_RSI_OVERSOLD:
        sigs.append((+2, f"RSI {rsi:.1f} < {BEAR_RSI_OVERSOLD} — extreme oversold, cover shorts / caution"))
    elif 40 <= rsi <= BEAR_RSI_OVERBOUGHT:
        sigs.append((-1, f"RSI {rsi:.1f} — bear rally zone, not a buy"))
    elif rsi < 35:
        sigs.append((0, f"RSI {rsi:.1f} — weak but not capitulation, wait"))

    # ─ MACD ───────────────────────────────────────────────────────────────────
    if _latest(df, "macd_bear_cross"):
        sigs.append((-2, "MACD bearish crossover in bear market — short signal"))
    elif _latest(df, "macd_bull_cross"):
        sigs.append((+1, "MACD bullish crossover in bear — possible dead-cat bounce, not a trend change"))
    elif macd < macd_sig and macd_hist < prev_hist:
        sigs.append((-1, "MACD expanding negative — selling pressure increasing"))

    # ─ Bollinger Bands ────────────────────────────────────────────────────────
    if close >= bb_upper:
        sigs.append((-2, "Price at upper BB in bear — strong resistance, short signal"))
    if close <= bb_lower:
        sigs.append((+1, "Price at lower BB — possible oversold bounce (not trend reversal)"))

    # ─ Resistance at 200 SMA ──────────────────────────────────────────────────
    dist200_pct = abs(dist200)
    if dist200_pct < 3:
        sigs.append((-3, f"Price testing 200 SMA from below — KEY RESISTANCE, expect rejection"))

    # ─ Volume ─────────────────────────────────────────────────────────────────
    if vol_ratio > 2.0 and close < _prev(df, "close"):
        sigs.append((-2, f"Volume {vol_ratio:.1f}x on down-move — capitulation or panic selling"))
    elif vol_ratio > 1.5 and close > _prev(df, "close"):
        sigs.append((0, f"Volume {vol_ratio:.1f}x on up-move — watch if sustained"))

    # ─ Stochastic RSI ─────────────────────────────────────────────────────────
    if stoch_k > 80:
        sigs.append((-2, f"StochRSI {stoch_k:.1f} overbought in bear — sell signal"))
    elif stoch_k < 20:
        sigs.append((+1, f"StochRSI {stoch_k:.1f} oversold — potential short-term bounce only"))

    # ─ Overextension (downside) ───────────────────────────────────────────────
    if dist200 < -OVEREXTENDED_PCT:
        sigs.append((+2, f"Price {dist200:.1f}% below 200 SMA — historically oversold, cover shorts partially"))

    return sigs


# ── Master Signal Aggregator ───────────────────────────────────────────────────

def generate_signal(df: pd.DataFrame, context_score: int = 0) -> dict:
    close   = float(df["close"].iloc[-1])
    sma200  = float(df["sma200"].iloc[-1])
    is_bull = close > sma200
    regime  = "BULL" if is_bull else "BEAR"

    ta_sigs = bull_signals(df) if is_bull else bear_signals(df)
    ta_score = sum(s[0] for s in ta_sigs)
    total    = ta_score + context_score

    # Clamp to [-9, +9]
    total = max(-9, min(9, total))

    action = _score_to_action(total, is_bull)

    return {
        "regime":         regime,
        "close":          close,
        "sma200":         sma200,
        "dist_200_pct":   float(df["dist_200_pct"].iloc[-1]),
        "ta_score":       ta_score,
        "context_score":  context_score,
        "total_score":    total,
        "action":         action,
        "signals":        ta_sigs,
    }


def _score_to_action(score: int, is_bull: bool) -> str:
    if is_bull:
        if score >= 6:  return "STRONG BUY — high conviction long"
        if score >= 3:  return "BUY — add to long positions"
        if score >= 1:  return "LEAN LONG — hold / small add"
        if score == 0:  return "NEUTRAL — wait for clarity"
        if score >= -2: return "REDUCE LONGS — take partial profits"
        return          "TAKE PROFITS — overbought/overextended, trim significantly"
    else:
        if score <= -6: return "STRONG AVOID / SHORT — high conviction bear"
        if score <= -3: return "AVOID LONGS / SHORT RALLIES"
        if score <= -1: return "LEAN SHORT — reduce exposure"
        if score == 0:  return "NEUTRAL — possible dead-cat, no new longs"
        if score >= 2:  return "COVER SHORTS — extreme oversold, reduce shorts"
        return          "WATCH FOR REVERSAL — extreme readings, could be capitulation"
