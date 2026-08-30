# Stock Selection — Local Setup & Handoff Spec

Everything a fresh **Claude Code CLI** session on your own machine needs to pick
this project up, run it against live data, and publish it to Cloudflare.

Written for Windows (matching the `.bat` runners elsewhere in this repo);
macOS/Linux equivalents are noted inline.

---

## What already exists

The page generator is **complete and tested** — 45 tests, verified end-to-end in
a browser against 440 synthetic constituents. What has *never* run is the live
Yahoo Finance fetch (the cloud sandbox that built it blocks Yahoo) and the
Cloudflare deployment. Those two are the work below.

| File | Role |
|---|---|
| `config.py` | Universes, factor weights, thresholds, palette, cache paths — **the single source of truth** |
| `universe.py` | Reads constituents from `stock_tool/resources/*.csv` |
| `fetcher.py` | Batched yfinance prices; `Ticker.info` profiles cached 7 days |
| `factors.py` | Per-ticker metrics, then percentile scoring within each market |
| `screener.py` | Pipeline orchestration + JSON payload |
| `render.py` | The self-contained HTML page (CSS + JS inline) |
| `demo.py` | Deterministic synthetic data for `--demo` |
| `main.py` | CLI |
| `tests/` | 45 pytest tests |

---

## Prerequisites

| Tool | Version | Why |
|---|---|---|
| Python | 3.11+ | the generator |
| Node.js | 18+ | `wrangler`, Cloudflare's CLI |
| git | any | pulling the branch |
| Claude Code | latest | `npm install -g @anthropic-ai/claude-code` |

A Cloudflare account (free tier is enough).

---

## Bootstrap

```bat
git clone https://github.com/lwongkll-ui/trading-strategy-analyzer.git
cd trading-strategy-analyzer
git checkout claude/stock-selection-page-mobrfx

python -m venv .venv
.venv\Scripts\activate
pip install -r stock_select\requirements.txt
pip install pytest
```

macOS/Linux: `source .venv/bin/activate`.

Verify before changing anything:

```bat
cd stock_select
python -m pytest tests\ -q
python main.py --demo --open
```

Expect **45 passed** and a page that opens in your browser with a "Demo data"
banner. If either fails, stop and fix that first — everything below assumes a
known-good baseline.

---

## Starting the Claude Code session

```bat
cd trading-strategy-analyzer
claude
```

The repo's root `CLAUDE.md` already documents `stock_select/`, so the session
picks up the architecture and scoring conventions automatically. Paste the
prompt in the last section of this file as your first message.

---

## The work

### Milestone A — first live run

The fetch path is unit-tested but has never touched the network.

```bat
cd stock_select
python main.py
```

**Acceptance:** `reports/stock_select.html` exists, the header shows no "no
fundamentals" chip, and the skipped-tickers chip is a small number (a handful of
recent listings, not dozens). Sectors in the heat map are real GICS names, not
`Unclassified`.

**Expect to spend time here.** The first run fetches ~440 profiles serially in
8 threads and takes several minutes. Watch for:

- **Yahoo rate limiting.** If profiles come back empty en masse, lower
  `PROFILE_WORKERS` in `config.py` (8 → 4) and re-run. `cache/profiles.json`
  persists what succeeded, so a re-run only retries the gaps.
- **Delisted or renamed tickers.** `stock_tool/resources/sp500_constituents.csv`
  is a static snapshot (365 names, not the full 503). If many are skipped, that
  list needs refreshing — a separate task, not a bug in the generator.
- **HK tickers** must keep their `.HK` suffix to resolve in yfinance.

### Milestone B — Cloudflare deployment

Static hosts serve `index.html`, so generate under that name:

```bat
python main.py --out reports\index.html
```

Create `stock_select/wrangler.toml`:

```toml
name = "stock-select"
compatibility_date = "2026-08-01"

[assets]
directory = "./reports"
```

```bat
npm install -g wrangler
wrangler login
wrangler deploy
```

**Acceptance:** the `*.workers.dev` URL loads, filters/sorting/heat map all work,
and the browser console is clean. The page is ~870 KB of self-contained HTML —
no CDN, no external fetches — so if anything fails to load, something has been
broken in `render.py`.

> Cloudflare now recommends Workers static assets over Pages for new projects.
> Pages still works if you prefer it: `wrangler pages deploy reports`.

### Milestone C — access control

**The page is public the moment it deploys.** Anyone with the URL sees your full
screen output. Gate it before sharing the URL anywhere:

Cloudflare dashboard → Zero Trust → Access → Applications → Add a self-hosted
application pointing at the Worker, with a policy allowing your email. Free for
up to 50 users.

**Acceptance:** an incognito window hits an auth prompt, not the page.

### Milestone D — scheduled refresh

The page is a snapshot, not live. Pick one:

**Local (recommended to start).** Add `stock_select/run_refresh.bat` following
the pattern of `silver_strategy/run_daily.bat`: activate the venv, run
`python main.py --out reports\index.html`, then `wrangler deploy`. Schedule it in
Task Scheduler for a weekday evening after the US close (HK data is settled by
then too).

**GitHub Actions.** No machine to keep on, but shared CI IPs get rate-limited by
Yahoo far more aggressively than a home connection. If you go this route, budget
for retries and consider `--no-fundamentals` on the scheduled run, using the
7-day profile cache from a manual local run for the fundamental factors. Store
the Cloudflare API token as a repository secret — **never** in the repo.

**Acceptance:** the deployed page's "Generated" timestamp advances on schedule
without you touching it.

---

## Conventions to preserve

These are load-bearing. A change that violates one is a bug, not a refactor.

- **`config.py` is the single source of truth.** Weights, thresholds, MA periods
  and the palette are all read from it — including by the page's own methodology
  section. Never hardcode a threshold in `render.py` or `factors.py`.
- **Percentile-rank within each market, never across.** A Hang Seng name is only
  compared with Hang Seng names. This is what makes a score of 80 mean the same
  thing in both indices despite different multiple regimes and currencies.
- **Loss-making is not cheap.** A negative P/E, non-positive book value or
  negative equity carries a `+inf` sentinel. Every component that can emit it has
  a **negative weight**, so it inverts to a score of 0. If you add a value or
  quality component, keep that invariant or the sentinel silently becomes a
  perfect score. There is a test for exactly this
  (`test_cheap_names_outrank_expensive_ones_on_value`).
- **A factor missing >50 % of its weight scores a neutral 50** and is flagged
  `<factor>_imputed`, drawn as a hatched micro-bar. Don't let sparse data
  masquerade as a real score.
- **The page stays self-contained.** No CDN, no external stylesheet, no remote
  image — `test_page_is_self_contained` enforces it. It must open from `file://`.
- **Untrusted text goes in via `textContent`.** Tickers, company names and
  sectors come from CSVs and Yahoo. `test_hostile_company_name_cannot_break_out_of_the_script_block`
  enforces it.
- **Never commit `reports/` or `cache/`** — both are gitignored.
- Tests stay green: `python -m pytest tests\ -q`.

---

## Known gotchas

| Symptom | Cause | Fix |
|---|---|---|
| Every sector is `Unclassified`, quality/value all 50 | profiles empty | Yahoo rate limit — lower `PROFILE_WORKERS`, re-run; cache keeps partial progress |
| Cloudflare serves a 404 | output is `stock_select.html` | regenerate with `--out reports\index.html` |
| Many names skipped | <210 sessions of history | expected for recent listings; a large count means a stale constituent CSV |
| Page loads but is empty below the filters | JS error | open devtools; the payload is `window.__SELECT__` |
| Stale numbers after a code change | browser cache | hard-reload; the file has no cache-busting |

---

## First prompt for the CLI session

Paste this verbatim:

> I'm continuing work on `stock_select/` in this repo. Read `stock_select/SETUP.md`
> and the root `CLAUDE.md` first — SETUP.md is the spec for what I need done and
> lists conventions that are load-bearing.
>
> Baseline is already verified: 45 tests pass and `python main.py --demo` builds a
> working page. What has never run is the live Yahoo fetch or any deployment.
>
> Start with Milestone A: run `python main.py` for real, diagnose anything that
> comes back empty or skipped, and report what the live data actually looks like
> before changing any code. Don't touch the scoring conventions in the
> "Conventions to preserve" section without flagging it to me first.

Then work Milestones B–D in order. Each has explicit acceptance criteria above.
