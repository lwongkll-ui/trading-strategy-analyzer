"""Deterministic synthetic data, so the page can be built and previewed offline.

`main.py --demo` swaps the yfinance calls for these generators. The numbers are
plausible but invented — the page renders a DEMO DATA banner so a synthetic run
can never be mistaken for a live one.
"""
from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

import config

SECTORS = [
    "Information Technology", "Financials", "Health Care", "Consumer Discretionary",
    "Industrials", "Communication Services", "Consumer Staples", "Energy",
    "Materials", "Utilities", "Real Estate",
]

TRADING_DAYS = 760          # ~3 years


def _seed(ticker: str) -> int:
    """Stable per-ticker seed, so repeated demo runs produce the same page."""
    return int(hashlib.sha256(ticker.encode()).hexdigest()[:8], 16)


def synth_prices(ticker: str, bars: int = TRADING_DAYS) -> pd.DataFrame:
    """A geometric-random-walk OHLCV frame with a ticker-specific drift and vol."""
    rng = np.random.default_rng(_seed(ticker))

    drift = rng.normal(0.0004, 0.0009)          # ≈ −20 %/yr … +30 %/yr
    vol = float(np.clip(rng.normal(0.018, 0.007), 0.006, 0.05))
    start = float(rng.uniform(8, 400))

    shocks = rng.normal(drift, vol, bars)
    # A slow sinusoidal component gives the series regime changes, so SMA
    # crosses and 52-week extremes actually occur instead of a pure trend.
    cycle = 0.0009 * np.sin(np.linspace(0, rng.uniform(2, 7) * np.pi, bars))
    close = start * np.exp(np.cumsum(shocks + cycle))

    intraday = np.abs(rng.normal(0, vol * 0.6, bars))
    high = close * (1 + intraday)
    low = close * (1 - intraday)
    open_ = np.concatenate([[close[0]], close[:-1]])
    volume = rng.lognormal(mean=13.5, sigma=0.8, size=bars)

    index = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=bars)
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=index,
    )


def synth_profile(ticker: str) -> dict:
    """Plausible sector + fundamentals, correlated so quality/value aren't noise."""
    rng = np.random.default_rng(_seed(ticker) + 1)

    quality = rng.beta(2.2, 2.2)                # 0 = weak business, 1 = strong
    # Better businesses trade richer — the classic quality/value tension, so the
    # two factors genuinely pull against each other in the demo page.
    richness = float(np.clip(rng.normal(quality, 0.22), 0.02, 0.98))

    return {
        "sector": SECTORS[_seed(ticker) % len(SECTORS)],
        "industry": "",
        "marketCap": float(rng.lognormal(mean=23.5, sigma=1.4)),
        "trailingPE": round(6 + richness * 48 + rng.normal(0, 3), 2),
        "forwardPE": round(5 + richness * 42 + rng.normal(0, 3), 2),
        "priceToBook": round(0.5 + richness * 9 + rng.normal(0, 0.6), 2),
        "priceToSalesTrailing12Months": round(0.3 + richness * 11 + rng.normal(0, 0.5), 2),
        "enterpriseToEbitda": round(3 + richness * 26 + rng.normal(0, 2), 2),
        "returnOnEquity": round(-0.05 + quality * 0.42 + rng.normal(0, 0.04), 4),
        "profitMargins": round(-0.04 + quality * 0.34 + rng.normal(0, 0.03), 4),
        "revenueGrowth": round(-0.10 + quality * 0.32 + rng.normal(0, 0.06), 4),
        "earningsGrowth": round(-0.15 + quality * 0.45 + rng.normal(0, 0.10), 4),
        "debtToEquity": round(max(0.0, rng.normal(85, 55)), 2),
        "dividendYield": round(max(0.0, rng.normal(0.021, 0.016)), 4),
    }


def synth_prices_many(tickers: list[str]) -> dict[str, pd.DataFrame]:
    return {t: synth_prices(t) for t in tickers}


def synth_profiles_many(tickers: list[str]) -> dict[str, dict]:
    return {t: synth_profile(t) for t in tickers}
