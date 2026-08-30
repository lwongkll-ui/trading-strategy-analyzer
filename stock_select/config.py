"""Configuration for the stock selection page — universes, factors, thresholds.

Every tunable lives here so `screener.py` and `render.py` stay free of magic
numbers. Mirrors the convention used by ``btc_strategy/config.py`` and
``silver_strategy/config.py``.
"""
from __future__ import annotations

from pathlib import Path

# ── paths ─────────────────────────────────────────────────────────────────────

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parent

# Constituent lists are shared with the StockTool desktop app rather than
# duplicated here — one source of truth per index.
CONSTITUENTS_DIR = REPO_ROOT / "stock_tool" / "resources"

CACHE_DIR = PACKAGE_DIR / "cache"
REPORTS_DIR = PACKAGE_DIR / "reports"
DEFAULT_OUTPUT = REPORTS_DIR / "stock_select.html"

# ── universes ─────────────────────────────────────────────────────────────────

UNIVERSES: dict[str, dict] = {
    "SP500": {
        "label": "S&P 500",
        "csv": "sp500_constituents.csv",
        "currency": "$",
        "region": "US",
    },
    "HSI": {
        "label": "Hang Seng",
        "csv": "hsi_constituents.csv",
        "currency": "HK$",
        "region": "HK",
    },
}

DEFAULT_MARKETS = ["SP500", "HSI"]

# ── price history ─────────────────────────────────────────────────────────────

HISTORY_PERIOD = "3y"       # enough for SMA200 plus a 12-month momentum window
MIN_BARS = 210              # a ticker with less history cannot produce an SMA200
DOWNLOAD_BATCH = 40         # tickers per yfinance request
DOWNLOAD_WORKERS = 4        # concurrent batches

# ── moving averages (the "three-line" trend system) ───────────────────────────

SMA_FAST = 10
SMA_MID = 50
SMA_SLOW = 200
SLOPE_LOOKBACK = 20         # bars used to measure the SMA200 slope
CROSS_LOOKBACK = 60         # bars in which a golden/death cross still counts as "recent"

# ── oscillators / risk ────────────────────────────────────────────────────────

RSI_PERIOD = 14
RSI_OVERBOUGHT = 70.0
RSI_OVERSOLD = 30.0
ATR_PERIOD = 14
LIQUIDITY_LOOKBACK = 20     # bars for average dollar volume

# ── factor model ──────────────────────────────────────────────────────────────
# Four factors, each scored 0–100 as a cross-sectional percentile *within its
# own market* (so HK names are never ranked against US names on raw multiples).
# The composite is the weighted mean, re-percentiled within the market.

FACTOR_WEIGHTS: dict[str, float] = {
    "trend": 0.30,
    "momentum": 0.30,
    "quality": 0.20,
    "value": 0.20,
}

# Sub-metric weights inside each factor. Keys map to columns produced by
# `factors.price_metrics()` / `factors.fundamental_metrics()`.
# A negative weight means "lower is better" (cheap multiples, low leverage).
TREND_COMPONENTS: dict[str, float] = {
    "px_vs_sma200": 0.35,
    "sma50_vs_sma200": 0.30,
    "sma10_vs_sma50": 0.20,
    "sma200_slope": 0.15,
}
MOMENTUM_COMPONENTS: dict[str, float] = {
    "mom_12_1": 0.40,
    "ret_3m": 0.30,
    "dist_52w_high": 0.20,   # already negative-is-far, so higher = nearer the high
    "ret_1m": 0.10,
}
QUALITY_COMPONENTS: dict[str, float] = {
    "return_on_equity": 0.30,
    "profit_margin": 0.25,
    "revenue_growth": 0.25,
    "debt_to_equity": -0.20,
}
VALUE_COMPONENTS: dict[str, float] = {
    "trailing_pe": -0.30,
    "price_to_book": -0.25,
    "price_to_sales": -0.25,
    "ev_to_ebitda": -0.20,
}

FACTOR_COMPONENTS: dict[str, dict[str, float]] = {
    "trend": TREND_COMPONENTS,
    "momentum": MOMENTUM_COMPONENTS,
    "quality": QUALITY_COMPONENTS,
    "value": VALUE_COMPONENTS,
}

# Score a factor as neutral (50) rather than dropping the name when this share
# of its sub-metrics is missing or worse. Keeps tickers with sparse fundamentals
# in the table instead of silently deleting them.
NEUTRAL_SCORE = 50.0
MAX_MISSING_SHARE = 0.5

# Letter grades applied to the composite score.
GRADE_BANDS: list[tuple[float, str]] = [
    (90.0, "A+"),
    (80.0, "A"),
    (70.0, "B+"),
    (60.0, "B"),
    (50.0, "C+"),
    (40.0, "C"),
    (25.0, "D"),
    (0.0, "E"),
]

# ── fundamentals ──────────────────────────────────────────────────────────────

FETCH_FUNDAMENTALS = True
PROFILE_WORKERS = 8
PROFILE_CACHE_DAYS = 7      # `.info` is slow; re-use it for a week
PROFILE_CACHE = CACHE_DIR / "profiles.json"

UNKNOWN_SECTOR = "Unclassified"

# ── page palette ──────────────────────────────────────────────────────────────
# Diverging poles validated with the dataviz palette checker against the card
# surface (#16161a, dark): aqua-green ↔ red clears the lightness band, chroma
# floor, normal-vision floor and 3:1 contrast, with CVD ΔE in the 6–8 band that
# is legal because every tile carries a direct % label and a table-view twin.
PALETTE = {
    "page": "#0d0d0f",
    "card": "#16161a",
    "card2": "#1b1b20",
    "line": "#2a2a31",
    "text": "#e6e6ea",
    "dim": "#8a8a93",
    "muted": "#898781",
    "pos": "#1baf7a",       # diverging pole — gains
    "neg": "#e34948",       # diverging pole — losses
    "mid": "#383835",       # neutral diverging midpoint
    "accent": "#3987e5",    # sequential hue — score magnitude
    "gold": "#d9a441",
}
