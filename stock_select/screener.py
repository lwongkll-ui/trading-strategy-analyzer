"""Orchestration — turn a list of markets into scored, ranked rows."""
from __future__ import annotations

import math
from datetime import datetime

import pandas as pd

import config
import factors
from universe import Constituent, load_universes

# Columns the HTML page consumes. Anything else stays out of the payload so the
# generated file does not carry dead weight.
ROW_FIELDS = [
    "ticker", "name", "market", "market_label", "currency", "sector", "industry",
    "price", "sma10", "sma50", "sma200", "rsi",
    "px_vs_sma200", "sma50_vs_sma200", "sma10_vs_sma50", "sma200_slope",
    "above_sma200", "stack", "cross",
    "ret_1m", "ret_3m", "ret_6m", "ret_12m", "mom_12_1",
    "high_52w", "low_52w", "dist_52w_high", "dist_52w_low",
    "atr_pct", "volatility", "dollar_volume", "market_cap",
    "trailing_pe", "forward_pe", "price_to_book", "price_to_sales", "ev_to_ebitda",
    "return_on_equity", "profit_margin", "revenue_growth", "earnings_growth",
    "debt_to_equity", "dividend_yield",
    "trend_score", "momentum_score", "quality_score", "value_score",
    "trend_imputed", "momentum_imputed", "quality_imputed", "value_imputed",
    "score", "rank", "grade", "spark",
]


def build_rows(constituents: list[Constituent],
               prices: dict[str, pd.DataFrame],
               profiles: dict[str, dict]) -> pd.DataFrame:
    """Join price metrics and fundamentals, then score every name."""
    records = []
    for c in constituents:
        metrics = factors.price_metrics(prices.get(c.ticker))
        if metrics is None:
            continue    # not enough history to compute an SMA200 — cannot be scored
        record = {
            "ticker": c.ticker,
            "name": c.name,
            "market": c.market,
            "market_label": c.market_label,
            "currency": config.UNIVERSES[c.market]["currency"],
        }
        record.update(metrics)
        record.update(factors.fundamental_metrics(profiles.get(c.ticker)))
        records.append(record)

    if not records:
        return pd.DataFrame(columns=ROW_FIELDS)

    frame = pd.DataFrame.from_records(records)
    frame = factors.score_factors(frame)
    return frame.sort_values(["market", "rank"]).reset_index(drop=True)


def to_payload(frame: pd.DataFrame) -> list[dict]:
    """JSON-ready row dicts, with NaN collapsed to ``None``."""
    if frame.empty:
        return []
    slim = frame.reindex(columns=ROW_FIELDS)
    payload = []
    for record in slim.to_dict(orient="records"):
        clean = {}
        for key, value in record.items():
            if hasattr(value, "item"):          # numpy scalar → python scalar
                value = value.item()
            if isinstance(value, float) and not math.isfinite(value):
                # NaN, and the +inf "worst possible multiple" sentinel used by
                # the value factor, are both "no number to show" on the page.
                clean[key] = None
            else:
                clean[key] = value
        payload.append(clean)
    return payload


def summarise(frame: pd.DataFrame) -> list[dict]:
    """Per-market breadth stats for the header tiles."""
    if frame.empty:
        return []
    out = []
    for market, group in frame.groupby("market", sort=False):
        total = len(group)
        out.append({
            "market": market,
            "label": config.UNIVERSES[market]["label"],
            "count": total,
            "above_sma200": int(group["above_sma200"].sum()),
            "breadth": round(100.0 * float(group["above_sma200"].sum()) / total, 1),
            "bull_stack": int((group["stack"] == "bull").sum()),
            "bear_stack": int((group["stack"] == "bear").sum()),
            "golden": int((group["cross"] == "golden").sum()),
            "death": int((group["cross"] == "death").sum()),
            "median_ret_1m": round(100.0 * float(group["ret_1m"].median(skipna=True)), 2)
            if group["ret_1m"].notna().any() else None,
        })
    return out


def run(markets: list[str], *, period: str = config.HISTORY_PERIOD,
        fundamentals: bool = True, refresh_profiles: bool = False,
        limit: int | None = None, demo_mode: bool = False,
        log=print) -> dict:
    """Full pipeline. Returns the dict `render.build_page` expects."""
    constituents = load_universes(markets)
    if limit:
        # Keep the cap per market so a small --limit still shows both indices.
        capped: list[Constituent] = []
        for market in markets:
            capped += [c for c in constituents if c.market == market][:limit]
        constituents = capped

    tickers = [c.ticker for c in constituents]
    log(f"Universe: {len(tickers)} tickers across {', '.join(markets)}")

    if demo_mode:
        import demo
        log("Demo mode — generating synthetic prices and fundamentals")
        prices = demo.synth_prices_many(tickers)
        # --no-fundamentals is honoured in demo mode too, so the price-only
        # path can be exercised without the network.
        profiles = demo.synth_profiles_many(tickers) if fundamentals else {}
    else:
        import fetcher
        log("Downloading price history…")
        prices = fetcher.fetch_prices(
            tickers, period=period,
            progress=lambda d, t, n: log(f"  prices {d}/{t} batches · {n} tickers"),
        )
        log(f"Got price history for {len(prices)}/{len(tickers)} tickers")
        if fundamentals:
            log("Fetching fundamentals (cached for "
                f"{config.PROFILE_CACHE_DAYS} days)…")
            profiles = fetcher.fetch_profiles(
                tickers, refresh=refresh_profiles,
                progress=lambda d, t: (log(f"  profiles {d}/{t}") if d % 50 == 0 or d == t
                                       else None),
            )
        else:
            log("Skipping fundamentals — quality and value score as neutral")
            profiles = {}

    frame = build_rows(constituents, prices, profiles)
    log(f"Scored {len(frame)} names")

    return {
        "rows": to_payload(frame),
        "summary": summarise(frame),
        "markets": markets,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "demo": demo_mode,
        "fundamentals": bool(profiles),
        "skipped": len(constituents) - len(frame),
    }
