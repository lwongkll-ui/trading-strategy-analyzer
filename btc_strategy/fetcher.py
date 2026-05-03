"""Market data fetching — price, macro, sentiment, funding."""

import requests
import yfinance as yf
import pandas as pd
from config import (
    BTC_TICKER, DXY_TICKER, SP500_TICKER, GOLD_TICKER,
    VIX_TICKER, TNX_TICKER,
    DAILY_PERIOD, WEEKLY_PERIOD,
    FEAR_GREED_URL, BINANCE_FUNDING_URL,
)


def fetch_ohlcv(ticker: str, period: str = DAILY_PERIOD, interval: str = "1d") -> pd.DataFrame:
    df = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=True)
    # yfinance >=1.0 returns MultiIndex columns — flatten to level 0
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0].lower() for c in df.columns]
    else:
        df.columns = [c.lower() for c in df.columns]
    df.index.name = "date"
    return df.dropna()


def fetch_btc_daily() -> pd.DataFrame:
    return fetch_ohlcv(BTC_TICKER, DAILY_PERIOD, "1d")


def fetch_btc_weekly() -> pd.DataFrame:
    return fetch_ohlcv(BTC_TICKER, WEEKLY_PERIOD, "1wk")


def fetch_macro() -> dict:
    """Return latest values for macro instruments."""
    tickers = {
        "DXY":   DXY_TICKER,
        "SP500": SP500_TICKER,
        "GOLD":  GOLD_TICKER,
        "VIX":   VIX_TICKER,
        "TNX":   TNX_TICKER,
    }
    result = {}
    for name, t in tickers.items():
        try:
            df = fetch_ohlcv(t, "5d", "1d")
            if len(df) >= 2:
                latest = float(df["close"].iloc[-1])
                prev   = float(df["close"].iloc[-2])
                result[name] = {
                    "price":  latest,
                    "change": round((latest - prev) / prev * 100, 2),
                }
            else:
                result[name] = {"price": None, "change": None}
        except Exception:
            result[name] = {"price": None, "change": None}
    return result


def fetch_fear_greed() -> dict:
    try:
        r = requests.get(FEAR_GREED_URL, timeout=8)
        data = r.json()["data"][0]
        return {
            "value":       int(data["value"]),
            "label":       data["value_classification"],
            "timestamp":   data["timestamp"],
        }
    except Exception:
        return {"value": None, "label": "Unavailable", "timestamp": None}


def fetch_funding_rate() -> dict:
    try:
        r = requests.get(BINANCE_FUNDING_URL, timeout=8)
        data = r.json()
        if data:
            rate = float(data[0]["fundingRate"]) * 100  # convert to %
            return {"rate_pct": round(rate, 4), "symbol": "BTCUSDT"}
    except Exception:
        pass
    return {"rate_pct": None, "symbol": "BTCUSDT"}
