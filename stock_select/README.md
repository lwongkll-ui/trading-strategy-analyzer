# Stock Selection

A single self-contained HTML page that scans the **S&P 500** and the **Hang Seng**,
scores every constituent on four factors, and lets you filter, sort and map the
result in the browser. No server, no CDN, no build step — the generator writes
one file you can open from disk or drop on any static host.

```bash
pip install -r requirements.txt

cd stock_select
python main.py                 # live scan of both indices → reports/stock_select.html
python main.py --demo --open   # synthetic data, opens in a browser (no network)
python main.py --markets SP500 # one index only
python main.py --no-fundamentals   # price factors only — much faster
python main.py --limit 25      # 25 names per market, for a quick look
python -m pytest tests/        # 44 tests
```

Constituent lists are read from `stock_tool/resources/*.csv`, so the desktop app
and this page always scan the same universe.

## What the page shows

| Section | Contents |
|---|---|
| **Universe breadth** | Per-index context — % above SMA200, bull stacks, golden/death crosses. Sits *above* the filters because it describes the whole index. |
| **Filters** | Market, trend state, MA cross, RSI band, sector, minimum score, text search. One row; everything below re-renders against the same slice. |
| **Selection stats** | Names matching, % above SMA200, median score, median 1-month return — all scoped to the current filter. |
| **Ranked table** | Every name with price, trend badges, a 60-day sparkline, 1M/3M/12M returns, RSI, the four factor micro-bars and the composite score. Click any row for the full metric breakdown; click a column header to sort; **T M Q V** in the header sort by that factor. |
| **Heat map** | Sector-grouped tiles, sized by market cap, coloured by 1-month return. Click a tile to jump to its table row. |
| **Methodology** | The factor definitions and weights, generated from `config.py`. |

`Export CSV` downloads the current selection with all 34 underlying columns.

## The factor model

Four factors, each scored 0–100, blended into a composite:

| Factor | Weight | Inputs |
|---|---|---|
| **Trend** | 30 % | price vs SMA200, SMA50 vs SMA200, SMA10 vs SMA50, SMA200 slope |
| **Momentum** | 30 % | 12-1 month momentum, 3-month return, distance from the 52-week high, 1-month return |
| **Quality** | 20 % | return on equity, profit margin, revenue growth, less debt/equity |
| **Value** | 20 % | trailing P/E, price/book, price/sales, EV/EBITDA — cheaper ranks higher |

Three properties worth knowing:

* **Percentile, not z-score.** Every sub-metric is ranked against peers, so one
  absurd multiple cannot distort the scale.
* **Ranked within its own index.** A Hang Seng name is only ever compared with
  Hang Seng names. A score of 80 means "top 20 % of its own index" in both
  markets, so the two are directly comparable even though their multiple
  regimes and currencies are not.
* **Loss-making is not cheap.** A negative P/E, a non-positive book value, or
  negative equity ranks at the *worst* end of the value and quality scales, not
  the best. A factor missing more than half its inputs scores a neutral 50 and
  its micro-bar is drawn hatched rather than silently pretending to be data.

Weights, thresholds and the moving-average periods all live in `config.py`.

## Layout

| File | Role |
|---|---|
| `config.py` | Universes, factor weights, thresholds, palette, cache paths |
| `universe.py` | Reads the constituent CSVs |
| `fetcher.py` | Batched yfinance price download; profile fetch with a 7-day disk cache |
| `factors.py` | Per-ticker metrics, then cross-sectional percentile scoring |
| `screener.py` | Pipeline orchestration and the JSON payload |
| `demo.py` | Deterministic synthetic data for `--demo` |
| `render.py` | The HTML/CSS/JS page |
| `main.py` | CLI |

## Notes

* The first live run fetches ~440 profiles from Yahoo and takes a few minutes.
  They are cached in `cache/profiles.json` for a week, so later runs are fast.
  `--refresh-profiles` forces a refetch; `--no-fundamentals` skips them entirely
  and scores quality and value as neutral.
* Names with fewer than 210 sessions of history cannot produce an SMA200 and are
  skipped; the count appears as a chip in the page header.
* Figures are objective calculations from end-of-day prices and reported
  fundamentals. Scores are relative rankings, not forecasts, and nothing the
  page produces is investment advice.
