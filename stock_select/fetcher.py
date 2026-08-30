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


def _prime_profile_session() -> None:
    """Work around yfinance's cookie bootstrap failing on locked-down networks.

    yfinance seeds its Yahoo auth cookie from ``https://fc.yahoo.com`` — a
    tracking domain that many networks, DNS resolvers and ad blocklists drop.
    When that connection fails the whole crumb handshake aborts and every
    ``Ticker.info`` comes back empty with a 401 "Invalid Crumb", which silently
    zeroes out sectors and every fundamental factor. Warming the shared session
    on the real finance page collects a usable cookie, after which yfinance's
    own crumb fetch succeeds. Best-effort: any failure leaves the default path
    untouched, so this can only help.
    """
    try:
        from yfinance import data as yfdata

        singleton = yfdata.YfData()
        if getattr(singleton, "_cookie", None):
            return
        resp = singleton._session.get(
            "https://finance.yahoo.com", timeout=20, allow_redirects=True)
        if resp.status_code == 200 and len(singleton._session.cookies) > 0:
            singleton._cookie = True
        # Fetch the crumb once here, single-threaded. Otherwise the first wave of
        # profile worker threads all race to fetch it at once and Yahoo rejects
        # the concurrent requests, silently dropping those tickers' fundamentals.
        # Priming it means every worker reuses one cached crumb.
        singleton._get_crumb_basic()
    except Exception:
        pass


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

    def _resolved(info: dict) -> bool:
        # A real constituent's profile always carries at least a sector or a
        # market cap. Anything without both came back empty — a throttled 401,
        # not a company that genuinely has no sector.
        return bool(info.get("sector") or info.get("marketCap"))

    def _one(ticker: str, attempts: int = 1) -> tuple[str, dict]:
        info: dict = {}
        for attempt in range(attempts):
            try:
                info = yf.Ticker(ticker).info or {}
            except Exception:
                info = {}
            if _resolved(info):
                break
            if attempt + 1 < attempts:
                time.sleep(0.5 * (attempt + 1))
        entry = {k: info.get(k) for k in _PROFILE_FIELDS}
        # Only stamp entries that actually resolved. An empty fetch is left
        # unstamped so it reads as stale and is retried on the next run, rather
        # than being cached blank for a week and silently imputed.
        if _resolved(info):
            entry["_fetched_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return ticker, entry

    if stale:
        _prime_profile_session()
        # Pass 1 — bulk fetch at low concurrency. Yahoo throttles bursts of
        # calls to its ``quoteSummary`` endpoint (the one behind ``.info``) with
        # a 401, so PROFILE_WORKERS is kept small to stay under that limit; a
        # wide fan-out trips the throttle and silently drops fundamentals.
        with ThreadPoolExecutor(max_workers=config.PROFILE_WORKERS) as pool:
            for done, (ticker, entry) in enumerate(pool.map(_one, stale), start=1):
                cache[ticker] = entry
                if progress:
                    progress(done, len(stale))
        # Pass 2 — gap-fill any stragglers one at a time, after a short cooldown
        # so a throttle tripped mid-pass has a chance to subside. Whatever still
        # fails is left unstamped (see _one) and simply retried on the next run,
        # so the on-disk cache converges over successive scheduled refreshes
        # rather than a single 401 masquerading as missing fundamentals.
        missing = [t for t in stale if "_fetched_at" not in cache.get(t, {})]
        if missing:
            time.sleep(20)
            for ticker in missing:
                _, entry = _one(ticker, attempts=3)
                cache[ticker] = entry
        _save_cache(cache)

    return {t: cache.get(t, {}) for t in tickers}
