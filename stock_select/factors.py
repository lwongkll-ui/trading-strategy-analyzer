"""Per-ticker metrics and the cross-sectional four-factor scoring model.

Two layers:

* ``price_metrics`` / ``fundamental_metrics`` turn one ticker's raw data into a
  flat dict of comparable numbers. No ranking happens here.
* ``score_factors`` ranks those numbers *within each market* into 0–100
  percentiles and folds them into trend / momentum / quality / value factors and
  a weighted composite.

Ranking is percentile-based, so a single outlier multiple cannot distort the
scale the way a z-score would.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

import config

# ── moving-average / oscillator helpers ───────────────────────────────────────


def _sma(close: pd.Series, n: int) -> pd.Series:
    return close.rolling(n).mean()


def _last(series: pd.Series) -> float | None:
    if series is None or series.empty:
        return None
    val = series.iloc[-1]
    return float(val) if pd.notna(val) else None


def rsi(close: pd.Series, period: int = config.RSI_PERIOD) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def atr(high: pd.Series, low: pd.Series, close: pd.Series,
        period: int = config.ATR_PERIOD) -> pd.Series:
    prev = close.shift()
    tr = pd.concat([high - low, (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def _pct_change_over(close: pd.Series, bars: int) -> float | None:
    """Return over the last *bars* sessions, or ``None`` without enough history."""
    if len(close) <= bars:
        return None
    then, now = close.iloc[-1 - bars], close.iloc[-1]
    if not (pd.notna(then) and pd.notna(now)) or then <= 0:
        return None
    return float(now / then - 1)


def _detect_cross(fast: pd.Series, slow: pd.Series,
                  lookback: int = config.CROSS_LOOKBACK) -> str:
    """``"golden"`` / ``"death"`` / ``"none"`` for the SMA50-vs-SMA200 cross.

    A cross counts only if it happened within *lookback* bars, so a name that
    turned six months ago is not still advertised as a fresh signal.
    """
    diff = (fast - slow).dropna()
    if len(diff) < 2:
        return "none"
    window = diff.iloc[-(lookback + 1):]
    if len(window) < 2:
        return "none"
    sign = np.sign(window.to_numpy())
    flips = np.nonzero(np.diff(sign) != 0)[0]
    if flips.size == 0:
        return "none"
    return "golden" if sign[-1] > 0 else "death"


# ── price metrics ─────────────────────────────────────────────────────────────

SPARK_POINTS = 60


def price_metrics(df: pd.DataFrame) -> dict | None:
    """Flat metric dict for one ticker's OHLCV frame, or ``None`` if too short."""
    if df is None or len(df) < config.MIN_BARS:
        return None

    df = df.dropna(subset=["Close"])
    if len(df) < config.MIN_BARS:
        return None

    close, high, low = df["Close"], df["High"], df["Low"]
    volume = df["Volume"] if "Volume" in df else pd.Series(index=df.index, dtype=float)

    price = _last(close)
    if not price or price <= 0:
        return None

    sma10 = _last(_sma(close, config.SMA_FAST))
    sma50 = _last(_sma(close, config.SMA_MID))
    sma200_series = _sma(close, config.SMA_SLOW)
    sma200 = _last(sma200_series)

    m: dict = {
        "price": price,
        "sma10": sma10,
        "sma50": sma50,
        "sma200": sma200,
        "rsi": _last(rsi(close)),
    }

    # Trend components — all expressed as "% above", so bigger is stronger.
    m["px_vs_sma200"] = price / sma200 - 1 if sma200 else None
    m["sma50_vs_sma200"] = sma50 / sma200 - 1 if (sma50 and sma200) else None
    m["sma10_vs_sma50"] = sma10 / sma50 - 1 if (sma10 and sma50) else None

    slope = None
    if len(sma200_series.dropna()) > config.SLOPE_LOOKBACK:
        prev = sma200_series.dropna().iloc[-1 - config.SLOPE_LOOKBACK]
        if pd.notna(prev) and prev > 0 and sma200:
            slope = float(sma200 / prev - 1)
    m["sma200_slope"] = slope

    m["above_sma200"] = bool(sma200 and price > sma200)
    if sma10 and sma50 and sma200:
        if sma10 > sma50 > sma200:
            stack = "bull"
        elif sma10 < sma50 < sma200:
            stack = "bear"
        else:
            stack = "mixed"
    else:
        stack = "unknown"
    m["stack"] = stack
    m["cross"] = _detect_cross(_sma(close, config.SMA_MID), sma200_series)

    # Momentum components.
    m["ret_1m"] = _pct_change_over(close, 21)
    m["ret_3m"] = _pct_change_over(close, 63)
    m["ret_6m"] = _pct_change_over(close, 126)
    m["ret_12m"] = _pct_change_over(close, 252)

    # 12-1 momentum: the classic academic definition — a year's return excluding
    # the most recent month, which is dominated by short-term reversal.
    if len(close) > 252:
        a, b = close.iloc[-253], close.iloc[-22]
        m["mom_12_1"] = float(b / a - 1) if (pd.notna(a) and pd.notna(b) and a > 0) else None
    else:
        m["mom_12_1"] = None

    window = close.iloc[-252:]
    hi, lo = float(window.max()), float(window.min())
    m["high_52w"], m["low_52w"] = hi, lo
    m["dist_52w_high"] = price / hi - 1 if hi > 0 else None   # <= 0; nearer 0 is stronger
    m["dist_52w_low"] = price / lo - 1 if lo > 0 else None

    # Risk / liquidity.
    atr_val = _last(atr(high, low, close))
    m["atr_pct"] = atr_val / price if atr_val else None
    daily = close.pct_change().iloc[-63:].dropna()
    m["volatility"] = float(daily.std() * math.sqrt(252)) if len(daily) > 5 else None
    dollar_vol = (close * volume).iloc[-config.LIQUIDITY_LOOKBACK:].dropna()
    m["dollar_volume"] = float(dollar_vol.mean()) if not dollar_vol.empty else None

    # A 60-point normalised close series drives the row sparkline.
    spark = close.iloc[-SPARK_POINTS:].to_numpy(dtype=float)
    lo_s, hi_s = float(spark.min()), float(spark.max())
    span = hi_s - lo_s
    m["spark"] = ([round((v - lo_s) / span, 3) for v in spark] if span > 0
                  else [0.5] * len(spark))

    return m


# ── fundamental metrics ───────────────────────────────────────────────────────

_WORST = float("inf")   # sorts to the worst end of any "lower is better" ranking


def _positive_or_worst(value) -> float | None:
    """Multiples are only meaningful when positive.

    A negative P/E means the company lost money — it is not "cheap". Mapping it
    to +inf ranks it as the most expensive name rather than the cheapest.
    """
    if value is None:
        return None
    try:
        val = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(val):
        return None
    return val if val > 0 else _WORST


def _plain(value) -> float | None:
    if value is None:
        return None
    try:
        val = float(value)
    except (TypeError, ValueError):
        return None
    return val if math.isfinite(val) else None


def fundamental_metrics(profile: dict | None) -> dict:
    """Normalise a yfinance profile dict into the fields the factors consume."""
    p = profile or {}
    debt = _plain(p.get("debtToEquity"))
    return {
        "sector": (p.get("sector") or config.UNKNOWN_SECTOR).strip() or config.UNKNOWN_SECTOR,
        "industry": (p.get("industry") or "").strip(),
        "market_cap": _plain(p.get("marketCap")),
        "trailing_pe": _positive_or_worst(p.get("trailingPE")),
        "forward_pe": _positive_or_worst(p.get("forwardPE")),
        "price_to_book": _positive_or_worst(p.get("priceToBook")),
        "price_to_sales": _positive_or_worst(p.get("priceToSalesTrailing12Months")),
        "ev_to_ebitda": _positive_or_worst(p.get("enterpriseToEbitda")),
        "return_on_equity": _plain(p.get("returnOnEquity")),
        "profit_margin": _plain(p.get("profitMargins")),
        "revenue_growth": _plain(p.get("revenueGrowth")),
        "earnings_growth": _plain(p.get("earningsGrowth")),
        # Negative equity produces a negative ratio that would otherwise rank as
        # the least-levered name; it is the opposite.
        "debt_to_equity": _WORST if (debt is not None and debt < 0) else debt,
        "dividend_yield": _plain(p.get("dividendYield")),
    }


# ── cross-sectional scoring ───────────────────────────────────────────────────


def _percentile(series: pd.Series) -> pd.Series:
    """Rank *series* into 0–100. NaNs stay NaN so callers can renormalise.

    The ``+inf`` sentinel (a loss-making multiple, or negative equity) is ranked
    at the *top* of the raw scale — it is the most expensive / most levered name,
    not a missing one. Every component that emits the sentinel carries a negative
    weight, so ``_blend`` then flips that 100 to 0: the worst possible score.
    """
    # ``rank`` orders +inf above every finite value on its own, which is exactly
    # the sentinel's meaning — no special-casing needed.
    return pd.to_numeric(series, errors="coerce").rank(pct=True, na_option="keep") * 100.0


def _blend(frame: pd.DataFrame, components: dict[str, float]) -> tuple[pd.Series, pd.Series]:
    """Weighted blend of percentile-ranked components.

    A negative weight flips the ranking (lower raw value scores higher).
    Returns ``(score, missing_share)`` — the share of weight that had no data.
    """
    total = sum(abs(w) for w in components.values())
    acc = pd.Series(0.0, index=frame.index)
    used = pd.Series(0.0, index=frame.index)

    for column, weight in components.items():
        raw = frame[column] if column in frame else pd.Series(np.nan, index=frame.index)
        pct = _percentile(raw)
        if weight < 0:
            pct = 100.0 - pct
        present = pct.notna()
        acc = acc.add((pct.fillna(0.0) * abs(weight)).where(present, 0.0), fill_value=0.0)
        used = used.add(pd.Series(abs(weight), index=frame.index).where(present, 0.0),
                        fill_value=0.0)

    score = (acc / used.replace(0, np.nan)).fillna(config.NEUTRAL_SCORE)
    missing = 1.0 - (used / total if total else 0.0)
    return score, missing


def score_factors(frame: pd.DataFrame) -> pd.DataFrame:
    """Add ``<factor>_score``, ``score``, ``rank`` and ``grade`` columns.

    Scoring runs **per market**: a Hang Seng name is percentiled against Hang
    Seng peers, never against the S&P 500, so differing multiple regimes and
    currencies never bleed across markets.
    """
    if frame.empty:
        return frame

    out = frame.copy()
    for factor in config.FACTOR_COMPONENTS:
        out[f"{factor}_score"] = np.nan
        out[f"{factor}_imputed"] = False
    out["score"] = np.nan

    for market, group in out.groupby("market", sort=False):
        composite = pd.Series(0.0, index=group.index)
        for factor, components in config.FACTOR_COMPONENTS.items():
            score, missing = _blend(group, components)
            imputed = missing > config.MAX_MISSING_SHARE
            score = score.where(~imputed, config.NEUTRAL_SCORE)
            out.loc[group.index, f"{factor}_score"] = score.round(1)
            out.loc[group.index, f"{factor}_imputed"] = imputed
            composite += score * config.FACTOR_WEIGHTS[factor]

        # Re-percentile the composite so every market's scores span 0–100 and
        # "80" means the same thing — top quintile of its own index.
        out.loc[group.index, "score"] = (_percentile(composite)
                                         .fillna(config.NEUTRAL_SCORE).round(1))

    out["rank"] = (out.groupby("market", sort=False)["score"]
                      .rank(ascending=False, method="min").astype(int))
    out["grade"] = out["score"].map(grade_for)
    return out


def grade_for(score: float) -> str:
    for floor, letter in config.GRADE_BANDS:
        if score >= floor:
            return letter
    return config.GRADE_BANDS[-1][1]
