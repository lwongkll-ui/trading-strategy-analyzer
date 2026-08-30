"""Data acquisition — batched yfinance price history plus cached profiles.

Prices are downloaded in batches (yfinance is far faster with many tickers per
request than one at a time). Profiles come from ``Ticker.info``, which is slow
and rate-limited, so they are cached on disk and re-used for a week.
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pandas as pd

import config


def _batches(items: list, size: int) -> list[list]:
    return [items[i:i + size] for i in range(0, len(items), size)]


# ── prices ────────────────────────────────────────────────────────────────────

def _split_frame(raw: pd.DataFrame, tickers: list[str]) -> dict[str, pd.DataFrame]:
    """Split a (possibly multi-index) yfinance frame into one frame per ticker."""
    out: dict[str, pd.DataFrame] = {}
    if raw is None or raw.empty:
        return out

    if isinstance(raw.columns, pd.MultiIndex):
        for ticker in tickers:
            if ticker not in raw.columns.get_level_values(0):
                continue
            sub = raw[ticker].dropna(how="all")
            if not sub.empty:
                out[ticker] = sub
    elif len(tickers) == 1:
        sub = raw.dropna(how="all")
        if not sub.empty:
            out[tickers[0]] = sub
    return out


def fetch_prices(tickers: list[str], period: str = config.HISTORY_PERIOD,
                 progress=None) -> dict[str, pd.DataFrame]:
    """Download daily OHLCV for *tickers*. Missing tickers are simply absent."""
    import yfinance as yf   # imported lazily so --demo runs without the dependency

    batches = _batches(list(dict.fromkeys(tickers)), config.DOWNLOAD_BATCH)
    frames: dict[str, pd.DataFrame] = {}
    done = 0

    def _one(batch: list[str]) -> dict[str, pd.DataFrame]:
        for attempt in range(3):
            try:
                raw = yf.download(batch, period=period, interval="1d",
                                  auto_adjust=True, group_by="ticker",
                                  progress=False, threads=True)
                return _split_frame(raw, batch)
            except Exception:
                if attempt == 2:
                    return {}
                time.sleep(2 ** attempt)
        return {}

    with ThreadPoolExecutor(max_workers=config.DOWNLOAD_WORKERS) as pool:
        for result in pool.map(_one, batches):
            frames.update(result)
            done += 1
            if progress:
                progress(done, len(batches), len(frames))

    return frames


# ── profiles (sector + fundamentals) ──────────────────────────────────────────

_PROFILE_FIELDS = (
    "sector", "industry", "marketCap", "trailingPE", "forwardPE", "priceToBook",
    "priceToSalesTrailing12Months", "enterpriseToEbitda", "returnOnEquity",
    "profitMargins", "revenueGrowth", "earningsGrowth", "debtToEquity",
    "dividendYield",
)


def _load_cache() -> dict:
    if not config.PROFILE_CACHE.exists():
        return {}
    try:
        return json.loads(config.PROFILE_CACHE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(cache: dict) -> None:
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    config.PROFILE_CACHE.write_text(json.dumps(cache, indent=1), encoding="utf-8")


def _is_fresh(entry: dict) -> bool:
    stamp = entry.get("_fetched_at")
    if not stamp:
        return False
    try:
        age = datetime.now(timezone.utc) - datetime.fromisoformat(stamp)
    except ValueError:
        return False
    return age.days < config.PROFILE_CACHE_DAYS


def fetch_profiles(tickers: list[str], refresh: bool = False,
                   progress=None) -> dict[str, dict]:
    """Return ``{ticker: profile}``, hitting the network only for stale entries."""
    import yfinance as yf   # lazy, as above

    cache = {} if refresh else _load_cache()
    stale = [t for t in tickers if not _is_fresh(cache.get(t, {}))]

    def _one(ticker: str) -> tuple[str, dict]:
        try:
            info = yf.Ticker(ticker).info or {}
        except Exception:
            info = {}
        entry = {k: info.get(k) for k in _PROFILE_FIELDS}
        entry["_fetched_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return ticker, entry

    if stale:
        with ThreadPoolExecutor(max_workers=config.PROFILE_WORKERS) as pool:
            for done, (ticker, entry) in enumerate(pool.map(_one, stale), start=1):
                cache[ticker] = entry
                if progress:
                    progress(done, len(stale))
        _save_cache(cache)

    return {t: cache.get(t, {}) for t in tickers}
