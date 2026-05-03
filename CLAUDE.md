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
