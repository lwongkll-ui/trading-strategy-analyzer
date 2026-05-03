"""
Swing Trading Engine for BTC/USD
---------------------------------
Detects high-probability setups and returns precise trade plans:
  - Entry zone (limit / market)
  - Stop Loss (hard + rationale)
  - TP1 / TP2 / TP3 (scale-out levels)
  - Risk:Reward ratio
  - Position size (based on configurable account & risk %)
  - Trade management rules (breakeven trigger, trailing stop)
  - Setup grade (A / B / C)
  - Invalidation condition
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal
import pandas as pd

# ── Account / Risk Config (edit these) ────────────────────────────────────────
ACCOUNT_SIZE_USD  = 10_000   # total trading capital
RISK_PER_TRADE    = 0.01     # 1 % risk per trade
MIN_RR            = 2.0      # minimum acceptable R:R

# ── Setup types ────────────────────────────────────────────────────────────────
SetupType = Literal[
    "MA Pullback Long",
    "MA Pullback Short",
    "Breakout Long",
    "Breakdown Short",
    "Oversold Bounce",
    "Overbought Fade",
    "MACD Cross Long",
    "MACD Cross Short",
    "BB Squeeze Breakout",
    "BB Squeeze Breakdown",
    "Bear Rally Short",
    "Double Bottom Long",
    "Lower High Short",
]

Grade = Literal["A", "B", "C"]


@dataclass
class SwingSetup:
    name:           SetupType
    grade:          Grade
    direction:      Literal["LONG", "SHORT"]
    entry:          float          # ideal entry price
    entry_zone_lo:  float          # limit zone lower bound
    entry_zone_hi:  float          # limit zone upper bound
    stop:           float          # hard stop loss
    tp1:            float          # 50% exit
    tp2:            float          # 30% exit
    tp3:            float          # 20% runner
    rr:             float          # risk:reward to TP2
    position_size:  float          # USD position size
    qty_btc:        float          # BTC quantity
    breakeven_at:   float          # move stop to entry when price hits this
    trailing_stop:  float          # trail stop distance (ATR-based) after TP1
    invalidation:   str
    rationale:      list[str]      = field(default_factory=list)
    time_stop_bars: int            = 5    # cancel if not triggered within N bars


# ── Helper math ───────────────────────────────────────────────────────────────

def _pos_size(entry: float, stop: float) -> tuple[float, float]:
    """Return (usd_size, btc_qty) based on 1R = RISK_PER_TRADE * ACCOUNT."""
    risk_usd  = ACCOUNT_SIZE_USD * RISK_PER_TRADE
    risk_per_btc = abs(entry - stop)
    if risk_per_btc == 0:
        return 0.0, 0.0
    qty = risk_usd / risk_per_btc
    return round(qty * entry, 2), round(qty, 6)


def _rr(entry: float, stop: float, target: float) -> float:
    risk   = abs(entry - stop)
    reward = abs(target - entry)
    return round(reward / risk, 2) if risk else 0.0


def _latest(df: pd.DataFrame, col: str) -> float:
    return float(df[col].iloc[-1])


def _prev(df: pd.DataFrame, col: str, n: int = 1) -> float:
    return float(df[col].iloc[-1 - n])


# ── Individual Setup Detectors ─────────────────────────────────────────────────

def _ma_pullback_long(df: pd.DataFrame) -> SwingSetup | None:
    """Bull market: price pulls back to SMA50 or EMA20, bouncing up."""
    close  = _latest(df, "close")
    sma50  = _latest(df, "sma50")
    ema20  = _latest(df, "ema20")
    sma200 = _latest(df, "sma200")
    rsi    = _latest(df, "rsi")
    atr    = _latest(df, "atr")
    vol_r  = _latest(df, "vol_ratio")
    macd_h = _latest(df, "macd_hist")
    macd_h_prev = _prev(df, "macd_hist")

    if close <= sma200:
        return None  # only in bull

    # Must be near SMA50 or EMA20
    near_sma50 = abs(close - sma50) / sma50 < 0.04
    near_ema20 = abs(close - ema20) / ema20 < 0.025
    if not (near_sma50 or near_ema20):
        return None

    # RSI should be in dip zone
    if rsi > 55:
        return None

    support = sma50 if near_sma50 else ema20
    entry   = close
    stop    = support - 1.5 * atr
    tp1     = entry + 1.5 * atr
    tp2     = entry + 3.0 * atr
    tp3     = entry + 5.0 * atr
    rr2     = _rr(entry, stop, tp2)

    if rr2 < MIN_RR:
        return None

    grade = "A" if (near_sma50 and rsi < 45 and macd_h > macd_h_prev) else \
            "B" if (near_sma50 or rsi < 45) else "C"

    usd, qty = _pos_size(entry, stop)
    rationale = [
        f"Price ${close:,.0f} near {'SMA50' if near_sma50 else 'EMA20'} (${support:,.0f})",
        f"RSI {rsi:.1f} — dip zone in bull market",
        f"Volume ratio {vol_r:.2f}x — {'low vol pullback (healthy)' if vol_r < 0.9 else 'normal'}",
        f"MACD histogram {'turning up ✓' if macd_h > macd_h_prev else 'still falling'}",
    ]
    return SwingSetup(
        name="MA Pullback Long", grade=grade, direction="LONG",
        entry=entry, entry_zone_lo=support, entry_zone_hi=entry + 0.3*atr,
        stop=stop, tp1=tp1, tp2=tp2, tp3=tp3, rr=rr2,
        position_size=usd, qty_btc=qty,
        breakeven_at=tp1, trailing_stop=1.5*atr,
        invalidation=f"Candle close below SMA50 ${sma50:,.0f} invalidates setup",
        rationale=rationale,
    )


def _ma_pullback_short(df: pd.DataFrame) -> SwingSetup | None:
    """Bear market: price rallies to SMA50 / EMA20 / SMA200 — short the rejection."""
    close  = _latest(df, "close")
    sma50  = _latest(df, "sma50")
    ema20  = _latest(df, "ema20")
    sma200 = _latest(df, "sma200")
    rsi    = _latest(df, "rsi")
    atr    = _latest(df, "atr")
    macd_h = _latest(df, "macd_hist")
    macd_h_prev = _prev(df, "macd_hist")

    if close >= sma200:
        return None  # only in bear

    near_sma50  = abs(close - sma50)  / sma50  < 0.04
    near_ema20  = abs(close - ema20)  / ema20  < 0.025
    near_sma200 = abs(close - sma200) / sma200 < 0.04

    if not (near_sma50 or near_ema20 or near_sma200):
        return None

    if rsi < 45:
        return None  # not overbought enough for a short

    resistance = sma200 if near_sma200 else (sma50 if near_sma50 else ema20)
    entry = close
    stop  = resistance + 1.5 * atr
    tp1   = entry - 1.5 * atr
    tp2   = entry - 3.0 * atr
    tp3   = entry - 5.0 * atr
    rr2   = _rr(entry, stop, tp2)

    if rr2 < MIN_RR:
        return None

    grade = "A" if (near_sma200 and rsi > 55 and macd_h < macd_h_prev) else \
            "B" if (near_sma200 or rsi > 55) else "C"

    usd, qty = _pos_size(entry, stop)
    rationale = [
        f"Price ${close:,.0f} testing {'200 SMA' if near_sma200 else 'SMA50' if near_sma50 else 'EMA20'} resistance (${resistance:,.0f})",
        f"RSI {rsi:.1f} — overbought in bear = sell-rally signal",
        f"MACD histogram {'rolling over ✓' if macd_h < macd_h_prev else 'still rising — wait'}",
    ]
    return SwingSetup(
        name="MA Pullback Short", grade=grade, direction="SHORT",
        entry=entry, entry_zone_lo=entry - 0.3*atr, entry_zone_hi=resistance + 0.5*atr,
        stop=stop, tp1=tp1, tp2=tp2, tp3=tp3, rr=rr2,
        position_size=usd, qty_btc=qty,
        breakeven_at=tp1, trailing_stop=1.5*atr,
        invalidation=f"Candle close above {'200 SMA' if near_sma200 else 'SMA50'} ${resistance:,.0f} invalidates",
        rationale=rationale,
    )


def _breakout_long(df: pd.DataFrame) -> SwingSetup | None:
    """Price breaks above 90-day resistance with above-average volume."""
    close     = _latest(df, "close")
    high_90d  = float(df["high"].tail(90).iloc[:-1].max())  # exclude today
    vol_ratio = _latest(df, "vol_ratio")
    atr       = _latest(df, "atr")
    rsi       = _latest(df, "rsi")
    sma200    = _latest(df, "sma200")

    # Breakout: today's close > 90d high with volume confirmation
    if close <= high_90d * 1.005:
        return None
    if vol_ratio < 1.3:
        return None  # need volume confirmation

    entry = close
    stop  = high_90d - 0.5 * atr  # stop just below old resistance (now support)
    tp1   = entry + 2.0 * atr
    tp2   = entry + 4.0 * atr
    tp3   = entry + 7.0 * atr
    rr2   = _rr(entry, stop, tp2)

    if rr2 < MIN_RR:
        return None

    grade = "A" if (close > sma200 and vol_ratio > 2.0 and rsi < 75) else \
            "B" if (vol_ratio > 1.5 or close > sma200) else "C"

    usd, qty = _pos_size(entry, stop)
    return SwingSetup(
        name="Breakout Long", grade=grade, direction="LONG",
        entry=entry, entry_zone_lo=high_90d, entry_zone_hi=entry + 0.5*atr,
        stop=stop, tp1=tp1, tp2=tp2, tp3=tp3, rr=rr2,
        position_size=usd, qty_btc=qty,
        breakeven_at=tp1, trailing_stop=2.0*atr,
        invalidation=f"Close back below old resistance ${high_90d:,.0f} = failed breakout",
        rationale=[
            f"Breakout above 90d high ${high_90d:,.0f} — resistance becomes support",
            f"Volume {vol_ratio:.1f}x above average — institutional participation",
            f"RSI {rsi:.1f} — {'healthy, room to run' if rsi < 70 else 'high, expect consolidation first'}",
        ],
    )


def _breakdown_short(df: pd.DataFrame) -> SwingSetup | None:
    """Price breaks below 90-day support with above-average volume."""
    close     = _latest(df, "close")
    low_90d   = float(df["low"].tail(90).iloc[:-1].min())
    vol_ratio = _latest(df, "vol_ratio")
    atr       = _latest(df, "atr")
    rsi       = _latest(df, "rsi")

    if close >= low_90d * 0.995:
        return None
    if vol_ratio < 1.3:
        return None

    entry = close
    stop  = low_90d + 0.5 * atr
    tp1   = entry - 2.0 * atr
    tp2   = entry - 4.0 * atr
    tp3   = entry - 7.0 * atr
    rr2   = _rr(entry, stop, tp2)

    if rr2 < MIN_RR:
        return None

    grade = "A" if (vol_ratio > 2.0 and rsi > 30) else \
            "B" if vol_ratio > 1.5 else "C"

    usd, qty = _pos_size(entry, stop)
    return SwingSetup(
        name="Breakdown Short", grade=grade, direction="SHORT",
        entry=entry, entry_zone_lo=entry - 0.5*atr, entry_zone_hi=low_90d,
        stop=stop, tp1=tp1, tp2=tp2, tp3=tp3, rr=rr2,
        position_size=usd, qty_btc=qty,
        breakeven_at=tp1, trailing_stop=2.0*atr,
        invalidation=f"Close back above old support ${low_90d:,.0f} = failed breakdown",
        rationale=[
            f"Breakdown below 90d low ${low_90d:,.0f} — support becomes resistance",
            f"Volume {vol_ratio:.1f}x above average — confirmed selling",
            f"RSI {rsi:.1f}",
        ],
    )


def _oversold_bounce(df: pd.DataFrame) -> SwingSetup | None:
    """Extreme RSI oversold + price near support + bullish candle."""
    rsi    = _latest(df, "rsi")
    close  = _latest(df, "close")
    open_  = _latest(df, "open")
    low_20 = float(df["low"].tail(20).min())
    atr    = _latest(df, "atr")
    stoch  = _latest(df, "stoch_k")

    if rsi > 30:
        return None
    if close < open_:  # must be bullish close
        return None

    near_low = abs(close - low_20) / low_20 < 0.03
    if not near_low:
        return None

    entry = close
    stop  = low_20 - 0.5 * atr
    tp1   = entry + 2.0 * atr
    tp2   = entry + 4.0 * atr
    tp3   = entry + 6.5 * atr
    rr2   = _rr(entry, stop, tp2)

    if rr2 < MIN_RR:
        return None

    grade = "A" if (rsi < 25 and stoch < 10) else "B" if rsi < 28 else "C"

    usd, qty = _pos_size(entry, stop)
    return SwingSetup(
        name="Oversold Bounce", grade=grade, direction="LONG",
        entry=entry, entry_zone_lo=low_20, entry_zone_hi=entry + 0.5*atr,
        stop=stop, tp1=tp1, tp2=tp2, tp3=tp3, rr=rr2,
        position_size=usd, qty_btc=qty,
        breakeven_at=tp1, trailing_stop=1.5*atr,
        invalidation=f"New low below ${low_20:,.0f} — selling continues",
        rationale=[
            f"RSI {rsi:.1f} — extreme oversold (historical bounce zone)",
            f"StochRSI {stoch:.1f} — also deeply oversold",
            f"Price near 20d low ${low_20:,.0f} — tactical support",
            "Bullish close candle confirms buyers stepping in",
        ],
    )


def _overbought_fade(df: pd.DataFrame) -> SwingSetup | None:
    """Extreme RSI overbought + near resistance + bearish candle."""
    rsi    = _latest(df, "rsi")
    close  = _latest(df, "close")
    open_  = _latest(df, "open")
    high_20 = float(df["high"].tail(20).max())
    atr    = _latest(df, "atr")
    stoch  = _latest(df, "stoch_k")

    if rsi < 75:
        return None
    if close > open_:  # must be bearish close
        return None

    near_high = abs(close - high_20) / high_20 < 0.03
    if not near_high:
        return None

    entry = close
    stop  = high_20 + 0.5 * atr
    tp1   = entry - 2.0 * atr
    tp2   = entry - 4.0 * atr
    tp3   = entry - 6.5 * atr
    rr2   = _rr(entry, stop, tp2)

    if rr2 < MIN_RR:
        return None

    grade = "A" if (rsi > 80 and stoch > 90) else "B" if rsi > 78 else "C"

    usd, qty = _pos_size(entry, stop)
    return SwingSetup(
        name="Overbought Fade", grade=grade, direction="SHORT",
        entry=entry, entry_zone_lo=entry - 0.5*atr, entry_zone_hi=high_20,
        stop=stop, tp1=tp1, tp2=tp2, tp3=tp3, rr=rr2,
        position_size=usd, qty_btc=qty,
        breakeven_at=tp1, trailing_stop=1.5*atr,
        invalidation=f"New high above ${high_20:,.0f} — momentum continues up",
        rationale=[
            f"RSI {rsi:.1f} — extreme overbought",
            f"StochRSI {stoch:.1f} — also overbought",
            f"Bearish close near 20d high ${high_20:,.0f}",
        ],
    )


def _macd_cross_long(df: pd.DataFrame) -> SwingSetup | None:
    """Fresh MACD bullish crossover above signal line."""
    crossed = bool(_latest(df, "macd_bull_cross"))
    if not crossed:
        return None

    close  = _latest(df, "close")
    sma200 = _latest(df, "sma200")
    atr    = _latest(df, "atr")
    rsi    = _latest(df, "rsi")
    bb_low = _latest(df, "bb_lower")

    entry = close
    stop  = close - 2.0 * atr
    tp1   = close + 1.5 * atr
    tp2   = close + 3.5 * atr
    tp3   = close + 6.0 * atr
    rr2   = _rr(entry, stop, tp2)

    if rr2 < MIN_RR:
        return None

    grade = "A" if close > sma200 else "B"

    usd, qty = _pos_size(entry, stop)
    return SwingSetup(
        name="MACD Cross Long", grade=grade, direction="LONG",
        entry=entry, entry_zone_lo=entry - 0.3*atr, entry_zone_hi=entry + 0.3*atr,
        stop=stop, tp1=tp1, tp2=tp2, tp3=tp3, rr=rr2,
        position_size=usd, qty_btc=qty,
        breakeven_at=tp1, trailing_stop=1.5*atr,
        invalidation="MACD crosses back below signal line before TP1",
        rationale=[
            "Fresh MACD bullish crossover — momentum shift",
            f"RSI {rsi:.1f}",
            f"Regime: {'Bull ✓ higher conviction' if close > sma200 else 'Bear — lower conviction, smaller size'}",
        ],
    )


def _macd_cross_short(df: pd.DataFrame) -> SwingSetup | None:
    """Fresh MACD bearish crossover below signal line."""
    crossed = bool(_latest(df, "macd_bear_cross"))
    if not crossed:
        return None

    close  = _latest(df, "close")
    sma200 = _latest(df, "sma200")
    atr    = _latest(df, "atr")
    rsi    = _latest(df, "rsi")

    entry = close
    stop  = close + 2.0 * atr
    tp1   = close - 1.5 * atr
    tp2   = close - 3.5 * atr
    tp3   = close - 6.0 * atr
    rr2   = _rr(entry, stop, tp2)

    if rr2 < MIN_RR:
        return None

    grade = "A" if close < sma200 else "B"

    usd, qty = _pos_size(entry, stop)
    return SwingSetup(
        name="MACD Cross Short", grade=grade, direction="SHORT",
        entry=entry, entry_zone_lo=entry - 0.3*atr, entry_zone_hi=entry + 0.3*atr,
        stop=stop, tp1=tp1, tp2=tp2, tp3=tp3, rr=rr2,
        position_size=usd, qty_btc=qty,
        breakeven_at=tp1, trailing_stop=1.5*atr,
        invalidation="MACD crosses back above signal line before TP1",
        rationale=[
            "Fresh MACD bearish crossover — momentum shift down",
            f"RSI {rsi:.1f}",
            f"Regime: {'Bear ✓ higher conviction' if close < sma200 else 'Bull — lower conviction, smaller size'}",
        ],
    )


def _bb_squeeze(df: pd.DataFrame) -> SwingSetup | None:
    """Bollinger Band squeeze (tight bands) — detect direction from price action."""
    bb_width   = _latest(df, "bb_width")
    avg_width  = float(df["bb_width"].tail(50).mean())
    close      = _latest(df, "close")
    bb_mid     = _latest(df, "bb_mid")
    bb_upper   = _latest(df, "bb_upper")
    bb_lower   = _latest(df, "bb_lower")
    atr        = _latest(df, "atr")
    sma200     = _latest(df, "sma200")

    if bb_width > avg_width * 0.7:  # not tight enough
        return None

    # Determine direction from price vs midline
    bullish_bias = close > bb_mid

    if bullish_bias:
        entry = bb_upper  # buy on break above upper band
        stop  = bb_lower
        tp1   = entry + 1.5 * atr
        tp2   = entry + 3.0 * atr
        tp3   = entry + 5.5 * atr
        direction = "LONG"
        name = "BB Squeeze Breakout"
        inv = f"Close below BB mid ${bb_mid:,.0f}"
    else:
        entry = bb_lower  # short on break below lower band
        stop  = bb_upper
        tp1   = entry - 1.5 * atr
        tp2   = entry - 3.0 * atr
        tp3   = entry - 5.5 * atr
        direction = "SHORT"
        name = "BB Squeeze Breakdown"
        inv = f"Close above BB mid ${bb_mid:,.0f}"

    rr2 = _rr(entry, stop, tp2)
    if rr2 < MIN_RR:
        return None

    grade = "A" if bb_width < avg_width * 0.5 else "B"
    regime_aligned = (direction == "LONG" and close > sma200) or \
                     (direction == "SHORT" and close < sma200)
    if not regime_aligned:
        grade = "C"

    usd, qty = _pos_size(entry, stop)
    return SwingSetup(
        name=name, grade=grade, direction=direction,
        entry=entry, entry_zone_lo=min(entry, bb_mid), entry_zone_hi=max(entry, bb_mid),
        stop=stop, tp1=tp1, tp2=tp2, tp3=tp3, rr=rr2,
        position_size=usd, qty_btc=qty,
        breakeven_at=tp1, trailing_stop=atr,
        invalidation=inv,
        rationale=[
            f"BB width {bb_width:.1f}% vs 50d avg {avg_width:.1f}% — tight squeeze building",
            f"Price {'above' if bullish_bias else 'below'} BB midline — {'bullish' if bullish_bias else 'bearish'} bias",
            f"Regime: {'aligned ✓' if regime_aligned else 'counter-trend — lower size'}",
            "Enter on confirmed band break, not before",
        ],
        time_stop_bars=3,
    )


def _bear_rally_short(df: pd.DataFrame) -> SwingSetup | None:
    """Bear market: multi-day rally losing steam below 200 SMA — short continuation."""
    close  = _latest(df, "close")
    sma200 = _latest(df, "sma200")
    if close >= sma200:
        return None

    rsi      = _latest(df, "rsi")
    atr      = _latest(df, "atr")
    macd_h   = _latest(df, "macd_hist")
    prev_h   = _prev(df, "macd_hist")
    stoch    = _latest(df, "stoch_k")

    # Rally peaking: RSI in overbought-for-bear zone AND histogram rolling over
    if rsi < 50:
        return None
    if not (macd_h < prev_h):  # histogram must be contracting
        return None
    if stoch < 70:
        return None

    entry = close
    stop  = close + 2.0 * atr
    tp1   = close - 2.0 * atr
    tp2   = close - 4.5 * atr
    tp3   = close - 8.0 * atr
    rr2   = _rr(entry, stop, tp2)

    if rr2 < MIN_RR:
        return None

    grade = "A" if (rsi > 58 and stoch > 80) else "B"

    usd, qty = _pos_size(entry, stop)
    return SwingSetup(
        name="Bear Rally Short", grade=grade, direction="SHORT",
        entry=entry, entry_zone_lo=entry - 0.5*atr, entry_zone_hi=entry + 0.5*atr,
        stop=stop, tp1=tp1, tp2=tp2, tp3=tp3, rr=rr2,
        position_size=usd, qty_btc=qty,
        breakeven_at=tp1, trailing_stop=2.0*atr,
        invalidation=f"Close above 200 SMA ${sma200:,.0f} cancels short thesis",
        rationale=[
            f"Bear market rally fading: RSI {rsi:.1f}, StochRSI {stoch:.1f}",
            "MACD histogram contracting — momentum rolling over",
            f"200 SMA ${sma200:,.0f} acting as ceiling — sell into it",
            "Classic bear rally short: lower high in progress",
        ],
    )


# ── Master Scanner ─────────────────────────────────────────────────────────────

DETECTORS = [
    _ma_pullback_long,
    _ma_pullback_short,
    _breakout_long,
    _breakdown_short,
    _oversold_bounce,
    _overbought_fade,
    _macd_cross_long,
    _macd_cross_short,
    _bb_squeeze,
    _bear_rally_short,
]


def scan_setups(df: pd.DataFrame) -> list[SwingSetup]:
    """Run all detectors and return valid setups sorted by grade."""
    setups = []
    for detector in DETECTORS:
        try:
            s = detector(df)
            if s is not None:
                setups.append(s)
        except Exception:
            pass
    grade_order = {"A": 0, "B": 1, "C": 2}
    return sorted(setups, key=lambda s: (grade_order[s.grade], -s.rr))
