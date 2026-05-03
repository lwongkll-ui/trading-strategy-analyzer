import numpy as np
import pandas as pd

from config import (
    SMA_SHORT, SMA_MID, SMA_LONG, EMA_FAST, EMA_SLOW,
    RSI_PERIOD, RSI_OVERSOLD, RSI_OVERBOUGHT,
    MACD_FAST, MACD_SLOW, MACD_SIGNAL,
    BB_PERIOD, BB_STD, ATR_PERIOD,
    STC_FAST, STC_SLOW, STC_OVERSOLD, STC_OVERBOUGHT,
    STOCH_K, STOCH_D, VOL_MA_PERIOD,
)


# ── Core helpers ────────────────────────────────────────────────────────────

def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, min_periods=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).clip(0, 100)


def macd(series: pd.Series,
         fast: int = MACD_FAST,
         slow: int = MACD_SLOW,
         signal: int = MACD_SIGNAL) -> tuple[pd.Series, pd.Series, pd.Series]:
    e_fast = ema(series, fast)
    e_slow = ema(series, slow)
    line   = e_fast - e_slow
    sig    = ema(line, signal)
    hist   = line - sig
    return line, sig, hist


def bollinger_bands(series: pd.Series,
                    period: int = BB_PERIOD,
                    n_std: float = BB_STD) -> tuple[pd.Series, pd.Series, pd.Series]:
    mid   = sma(series, period)
    std   = series.rolling(period, min_periods=period).std()
    upper = mid + n_std * std
    lower = mid - n_std * std
    return upper, mid, lower


def atr(high: pd.Series, low: pd.Series, close: pd.Series,
        period: int = ATR_PERIOD) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def _stochastic(series: pd.Series, k_period: int) -> pd.Series:
    lo  = series.rolling(k_period, min_periods=k_period).min()
    hi  = series.rolling(k_period, min_periods=k_period).max()
    denom = (hi - lo).replace(0, np.nan)
    return ((series - lo) / denom * 100).fillna(50).clip(0, 100)


def schaff_trend_cycle(close: pd.Series,
                       macd_fast: int, macd_slow: int,
                       k: int, d: int) -> pd.Series:
    """Schaff Trend Cycle — double-smoothed stochastic of MACD."""
    macd_line = ema(close, macd_fast) - ema(close, macd_slow)
    pk  = ema(_stochastic(macd_line, k), d)
    stc = ema(_stochastic(pk, k), d)
    return stc.clip(0, 100)


def stoch_rsi(series: pd.Series,
              rsi_period: int = RSI_PERIOD,
              k: int = STOCH_K,
              d: int = STOCH_D) -> tuple[pd.Series, pd.Series]:
    r    = rsi(series, rsi_period)
    raw_k = _stochastic(r, rsi_period)
    smooth_k = raw_k.rolling(k, min_periods=1).mean()
    smooth_d = smooth_k.rolling(d, min_periods=1).mean()
    return smooth_k, smooth_d


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff()).fillna(0)
    return (direction * volume).cumsum()


# ── Candlestick patterns ─────────────────────────────────────────────────────

def candlestick_patterns(df: pd.DataFrame) -> pd.Series:
    """
    Returns a Series of pattern names (or empty string) for each bar.
    Bullish patterns: positive score meaning.
    Bearish patterns: negative score meaning.
    """
    o = df["Open"]
    h = df["High"]
    l = df["Low"]
    c = df["Close"]

    body    = (c - o).abs()
    candle  = h - l
    is_bull = c > o

    def _b(s):
        return s.fillna(False).astype(bool)

    patterns = pd.Series("", index=df.index)

    # Doji
    doji = _b(body / candle.replace(0, np.nan) < 0.1)
    patterns[doji] = "Doji"

    # Hammer (bullish reversal at bottom)
    lower_wick = o.where(is_bull, c) - l
    upper_wick = h - c.where(is_bull, o)
    hammer = _b((lower_wick >= 2 * body) & (upper_wick < body) & is_bull)
    patterns[hammer] = "Hammer"

    # Shooting Star (bearish reversal at top)
    shoot = _b((upper_wick >= 2 * body) & (lower_wick < body) & ~is_bull)
    patterns[shoot] = "ShootStar"

    # Bullish Engulfing
    prev_bull = is_bull.shift(1).fillna(False).astype(bool)
    bull_eng  = _b((~prev_bull) & is_bull & (o < c.shift(1)) & (c > o.shift(1)))
    patterns[bull_eng] = "BullEngulf"

    # Bearish Engulfing
    bear_eng = _b(prev_bull & (~is_bull) & (o > c.shift(1)) & (c < o.shift(1)))
    patterns[bear_eng] = "BearEngulf"

    # Bullish Harami
    bull_har = _b((~prev_bull) & is_bull & (o > c.shift(1)) & (c < o.shift(1)))
    patterns[bull_har] = "BullHarami"

    # Morning Star (3-bar bullish reversal)
    mid_doji = _b((body.shift(1) / candle.shift(1).replace(0, np.nan)) < 0.25)
    is_bull_2 = is_bull.shift(2).fillna(False).astype(bool)
    morn_star = _b((~is_bull_2) & mid_doji & is_bull & (c > (o.shift(2) + c.shift(2)) / 2))
    patterns[morn_star] = "MornStar"

    # Evening Star (3-bar bearish reversal)
    eve_star = _b(is_bull_2 & mid_doji & (~is_bull) & (c < (o.shift(2) + c.shift(2)) / 2))
    patterns[eve_star] = "EveStar"

    return patterns


BULLISH_PATTERNS = {"Hammer", "BullEngulf", "BullHarami", "MornStar", "Doji"}
BEARISH_PATTERNS = {"ShootStar", "BearEngulf", "EveStar"}


# ── Full indicator suite ─────────────────────────────────────────────────────

def compute_all(df: pd.DataFrame) -> pd.DataFrame:
    """Add all indicator columns to df (modifies a copy)."""
    df = df.copy()
    c = df["Close"]

    df["sma20"]  = sma(c, SMA_SHORT)
    df["sma50"]  = sma(c, SMA_MID)
    df["sma200"] = sma(c, SMA_LONG)
    df["ema9"]   = ema(c, EMA_FAST)
    df["ema21"]  = ema(c, EMA_SLOW)

    df["bb_upper"], df["bb_mid"], df["bb_lower"] = bollinger_bands(c)
    df["atr"] = atr(df["High"], df["Low"], c)

    df["rsi"] = rsi(c)
    df["stk_rsi_k"], df["stk_rsi_d"] = stoch_rsi(c)

    df["macd"], df["macd_sig"], df["macd_hist"] = macd(c)

    df["stc_fast"] = schaff_trend_cycle(c, **STC_FAST)
    df["stc_slow"] = schaff_trend_cycle(c, **STC_SLOW)

    df["obv"]    = obv(c, df["Volume"])
    df["vol_ma"] = sma(df["Volume"], VOL_MA_PERIOD)
    df["vol_ratio"] = df["Volume"] / df["vol_ma"].replace(0, np.nan)

    df["pattern"] = candlestick_patterns(df)

    def _bool(s):
        return s.fillna(False).astype(bool)

    # Trend flags
    df["above_sma200"] = _bool(c > df["sma200"])
    df["above_sma50"]  = _bool(c > df["sma50"])
    df["above_sma20"]  = _bool(c > df["sma20"])
    df["golden_cross"] = _bool(df["sma50"] > df["sma200"])
    df["ema_bull"]     = _bool(df["ema9"] > df["ema21"])

    # Golden / death cross events
    df["gc_event"] = df["golden_cross"] & ~df["golden_cross"].shift(1).fillna(False).astype(bool)
    df["dc_event"] = ~df["golden_cross"] & df["golden_cross"].shift(1).fillna(True).astype(bool)

    # MACD crossovers
    df["macd_bull"] = _bool(df["macd"] > df["macd_sig"])
    df["macd_cross_up"]   = df["macd_bull"] & ~df["macd_bull"].shift(1).fillna(False).astype(bool)
    df["macd_cross_down"] = ~df["macd_bull"] & df["macd_bull"].shift(1).fillna(True).astype(bool)

    # STC crossovers
    df["stc_fast_cross_up25"] = _bool(
        (df["stc_fast"] > STC_OVERSOLD) & (df["stc_fast"].shift(1).fillna(STC_OVERSOLD) <= STC_OVERSOLD)
    )
    df["stc_fast_cross_dn75"] = _bool(
        (df["stc_fast"] < STC_OVERBOUGHT) & (df["stc_fast"].shift(1).fillna(STC_OVERBOUGHT) >= STC_OVERBOUGHT)
    )

    # OBV trend (20-day MA of OBV)
    df["obv_ma"]   = sma(df["obv"], VOL_MA_PERIOD)
    df["obv_bull"] = _bool(df["obv"] > df["obv_ma"])

    return df
