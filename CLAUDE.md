# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Trading strategy analyzers. Three independent projects:

- `btc_strategy/` — BTC/USD bull & bear regime detection (technical + macro).
- `silver_strategy/` — silver miner (ASM, PAAS, CDE, AG, USAS, SVM) dashboard,
  daily/weekly Discord reports, and a quarterly financial report. See
  `silver_strategy/CRON_SPEC.md` and `SETUP.md`.
- `stock_tool/` — PyQt6 desktop charting app. See `stock_tool/CLAUDE.md`.

Read the directory to see the module layout; it is not duplicated here.

## Commands

```bash
# BTC
pip install -r btc_strategy/requirements.txt
cd btc_strategy && python main.py            # terminal dashboard
cd btc_strategy && python main.py --chart    # + save btc_chart.png

# Silver
pip install -r silver_strategy/requirements.txt
cd silver_strategy && python main.py                 # terminal dashboard
cd silver_strategy && python main.py --chart --weekly # + daily/weekly PNGs
cd silver_strategy && python dashboard.py            # HTML support-ladder dashboard
```

## Conventions

- On Windows, invoke Python via the `py` launcher — bare `python` resolves to the
  Microsoft Store stub and fails.
- yfinance `.info` returns `Invalid Crumb` 401s; price/technical/macro and the
  quarterly *statement* endpoints still work. Fundamentals are sourced from
  `silver_strategy/financials_q1_2026.py` instead.
- `silver_strategy/financials_data.py` and `narrative_data.py` are auto-generated
  each month — never hand-edit them; edit the curated baseline instead.
