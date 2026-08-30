# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

BTC/USD trading strategy analyzer — bull & bear regime detection with full technical + macro analysis.

## Commands

```bash
# Install dependencies (run once)
pip install -r btc_strategy/requirements.txt

# Run full analysis
cd btc_strategy && python main.py

# Run with price chart saved as btc_chart.png
cd btc_strategy && python main.py --chart
```

## Architecture

### btc_strategy/
- `config.py` — all thresholds, tickers, API URLs
- `fetcher.py` — yfinance (BTC, DXY, S&P500, VIX, TNX), Fear&Greed API, Binance funding rate
- `indicators.py` — SMA200/50, EMA20, RSI, MACD, Bollinger Bands, ATR, StochRSI, OBV, candlestick patterns, divergence, key levels
- `market_context.py` — macro/sentiment interpretation with score impact
- `strategy.py` — bull market rules (price > 200 SMA) and bear market rules (price < 200 SMA), signal scoring
- `main.py` — rich terminal dashboard + optional matplotlib chart

### stock_select/
Self-contained HTML stock selection page for the S&P 500 + Hang Seng.

```bash
cd stock_select && python main.py            # live scan → reports/stock_select.html
cd stock_select && python main.py --demo --open   # synthetic data, no network
cd stock_select && python -m pytest tests/
```

- `config.py` — universes, factor weights, thresholds, palette
- `universe.py` — reads constituents from `stock_tool/resources/*.csv` (shared with StockTool)
- `fetcher.py` — batched yfinance prices; `Ticker.info` profiles cached 7 days in `cache/`
- `factors.py` — per-ticker metrics, then **percentile** scoring within each market
- `screener.py` — pipeline + JSON payload; `render.py` — the page; `demo.py` — synthetic data

Scoring conventions: every sub-metric is percentile-ranked **within its own
index** (never across markets); a `+inf` sentinel marks "worst possible"
(loss-making multiple, negative equity) and every component emitting it carries a
negative weight, so it inverts to a score of 0; a factor missing >50 % of its
weight scores a neutral 50 and is flagged `<factor>_imputed`.
