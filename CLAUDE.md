# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

BTC/USD trading strategy analyzer — bull & bear regime detection with full technical + macro analysis.

## Commands

```bash
# Install dependencies (run once)
pip install -r btc_strategy/requirements.txt

# BTC strategy
cd btc_strategy && python main.py
cd btc_strategy && python main.py --chart   # + price chart → btc_chart.png

# stock_select page
cd stock_select && python main.py                  # live scan → reports/stock_select.html
cd stock_select && python main.py --demo --open    # synthetic data, no network
cd stock_select && python -m pytest tests/
```

Scoring conventions (stock_select): every sub-metric is percentile-ranked **within its own
index** (never across markets); a `+inf` sentinel marks "worst possible"
(loss-making multiple, negative equity) and every component emitting it carries a
negative weight, so it inverts to a score of 0; a factor missing >50 % of its
weight scores a neutral 50 and is flagged `<factor>_imputed`.
