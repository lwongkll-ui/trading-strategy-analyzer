# Silver Miners Monitor — Setup & Porting Guide

Complete instructions to deploy this project on any Linux/Mac/Windows machine
with full daily + weekly dashboards and automated cron job scheduling.

---

## What This Project Contains

| File / Folder | Purpose |
|---|---|
| `main.py` | Terminal dashboard — run manually or via cron |
| `charts.py` | mplfinance chart generator (daily + weekly PNGs) |
| `DAILY_MONITOR_PROMPT.md` | Prompt template for AI daily/weekly analysis |
| `CRON_SPEC.md` | Full cron job spec with shell scripts for OpenClaw + DeepSeek |
| `Silver_Miners_Financial_Analysis.docx` | Q1 2026 financial analysis report (download copy) |
| `requirements.txt` | Python dependencies |
| `config.py` | All tickers, thresholds, MA periods |
| `strategy.py` | Signal logic — buy/sell/hold scoring |
| `indicators.py` | All technical indicators (STC, MACD, RSI, etc.) |
| `fetcher.py` | yfinance data fetching with 401 fallback |
| `market_context.py` | Macro scoring (silver, DXY, VIX, SIL ETF) |
| `fundamentals.py` | Fundamental scoring (PE, debt, margins) |

---

## Step 1 — Clone the Repository

```bash
git clone https://github.com/lwongkll/silver-strategy.git
cd silver-strategy/silver_strategy
```

Or if cloning the full monorepo:
```bash
git clone <your-repo-url>
cd <repo>/silver_strategy
```

---

## Step 2 — Python Environment

**Requires Python 3.10+**

```bash
# Create virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate          # Linux/Mac
# .venv\Scripts\activate           # Windows

# Install dependencies
pip install -r requirements.txt
```

### requirements.txt contents
```
yfinance>=0.2.36
pandas>=2.0.0
numpy>=1.24.0
matplotlib>=3.7.0
mplfinance>=0.12.10b0
rich>=13.5.0
requests>=2.31.0
```

### Verify installation
```bash
python main.py --ticker SVM
```
Expected: Rich terminal dashboard with SVM analysis. If you see Unicode errors on Windows, see Troubleshooting below.

---

## Step 3 — Run the Dashboards

### Daily dashboard (all 6 tickers)
```bash
python main.py
```

### Daily dashboard + save charts
```bash
python main.py --chart
# Charts saved to: silver_strategy/silver_charts/ASM.png, PAAS.png, etc.
```

### Weekly dashboard + save weekly charts
```bash
python main.py --weekly
# Charts saved to: silver_strategy/silver_charts/ASM_weekly.png, etc.
```

### Single ticker
```bash
python main.py --ticker PAAS
python main.py --ticker SVM --chart --weekly
```

---

## Step 4 — Set Up Cron Jobs (Linux/Mac)

See `CRON_SPEC.md` for the full specification. Quick setup:

### 4a. Create the shell scripts

```bash
mkdir -p ~/scripts
mkdir -p /var/log/silver_monitor/daily
mkdir -p /var/log/silver_monitor/weekly
mkdir -p /var/log/silver_monitor/alerts
```

Copy `run_daily.sh` and `run_weekly.sh` from `CRON_SPEC.md` into `~/scripts/`.

Update these variables at the top of each script:
```bash
SILVER_STRATEGY_DIR="/path/to/silver_strategy"   # absolute path
OPENCLAW_MODEL="deepseek-v4-flash"
MONITOR_LOG_DIR="/var/log/silver_monitor"
ALERT_EMAIL="your@email.com"
```

Make executable:
```bash
chmod +x ~/scripts/run_daily.sh ~/scripts/run_weekly.sh
```

### 4b. Add crontab entries

```bash
crontab -e
```

Add these lines:
```cron
# Silver miners — daily check (Mon–Fri at 09:00 local time)
0 9 * * 1-5 /home/<user>/scripts/run_daily.sh >> /var/log/silver_monitor/cron.log 2>&1

# Silver miners — weekly review (Saturday at 08:00)
0 8 * * 6 /home/<user>/scripts/run_weekly.sh >> /var/log/silver_monitor/cron.log 2>&1
```

### 4c. Test manually
```bash
bash ~/scripts/run_daily.sh
cat /var/log/silver_monitor/daily/$(date +%Y-%m-%d)_analysis.md
```

---

## Step 5 — Configure OpenClaw (AI Analysis)

The cron scripts pipe `python main.py` output into OpenClaw with DeepSeek V4 Flash.

Verify OpenClaw is installed and the model is available:
```bash
openclaw --version
openclaw config set model deepseek-v4-flash
echo "Test prompt" | openclaw run --model deepseek-v4-flash --max-tokens 50
```

If your OpenClaw uses different CLI flags, edit the `openclaw run` call in `run_daily.sh` and `run_weekly.sh`. The logical interface required is:
- Accept prompt via stdin or `--file`
- Accept `--model`, `--temperature`, `--max-tokens` flags
- Write response to stdout

---

## Key Thresholds to Know (June 28, 2026 baseline)

These are embedded in `DAILY_MONITOR_PROMPT.md` and the cron scripts.
**Update them monthly** as SMA200 levels drift:

### Bear flag triggers (any one = ALERT)
| Condition | Threshold |
|---|---|
| Silver spot | Below **$57.04** (weekly 61.8% Fibonacci) |
| ASM | Below **$6.54** (SMA200) |
| PAAS | Below **$49.70** (SMA200) |
| CDE | Below **$18.95** (SMA200) |
| AG | Below **$18.26** (SMA200) |
| USAS | Below **$5.64** (SMA200) |
| SVM | Below **$9.73** (SMA200) |
| SVM floor | Below **$11.50** (early warning) |
| DXY | Above **106** |
| Gold/Silver ratio | Above **80** |

### Recovery confirmation (all must be true)
| Condition | Threshold |
|---|---|
| Silver | Above **$63.09** (weekly SMA50) |
| Weekly MACD histogram | Positive for 4+ of 6 names |
| SVM weekly STC-Slow | Above **20** (was 11 on Jun 28) |

### Update SMA200 levels
Run this to get current SMA200 for all tickers:
```bash
python - <<'EOF'
import warnings; warnings.filterwarnings("ignore")
from fetcher import fetch_ohlcv
from indicators import compute_all
from config import SILVER_MINERS
for t, co in SILVER_MINERS.items():
    df = fetch_ohlcv(t, "2y", "1d")
    df = compute_all(df)
    last = df.iloc[-1]
    print(f"{t}: SMA200=${last['sma200']:.2f}  Price=${last['Close']:.2f}  {'ABOVE' if last['Close']>last['sma200'] else 'BELOW'}")
EOF
```

---

## File Reference: What Each Output File Is For

### `DAILY_MONITOR_PROMPT.md`
The master context document. Feed this + today's `python main.py` output to any AI to get a structured daily check. Contains:
- Portfolio context and peak history
- Bull case vs bear case conditions
- 4-stage peak detection framework
- All price thresholds
- The 6 daily questions to answer

### `CRON_SPEC.md`
Technical specification for automating the daily/weekly AI analysis. Contains:
- `run_daily.sh` — full shell script (copy-paste ready)
- `run_weekly.sh` — full shell script (copy-paste ready)
- Crontab entries
- OpenClaw CLI usage
- Alert/email setup
- Log file structure

### `Silver_Miners_Financial_Analysis.docx`
Professional Word document covering Q1 2026 financials for all 6 miners:
- Revenue, net income, EPS per quarter (5 quarters)
- Gross margin expansion table
- Balance sheet: net cash positions, D/E ratios
- Free cash flow and capex
- Valuation: P/E, P/B, EV/EBITDA, FCF yield
- Risk matrix
- Silver price threshold scenarios

---

## Troubleshooting

### Windows: Unicode errors in terminal
Add this to the top of `main.py` (already done in this repo):
```python
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
```
Run from Windows Terminal (not cmd.exe) for best results.

### Yahoo Finance 401 errors
```
HTTP Error 401: Invalid Crumb
```
This is a known yfinance issue. The `fetcher.py` already handles it with a `fast_info` fallback for price/market cap data. Full fundamental data (PE, margins from `.info`) may be unavailable. OHLCV price data always works via `yf.download()`.

Workaround if persistent:
```bash
pip install --upgrade yfinance
```

### Charts not generating
```bash
pip install mplfinance matplotlib
# On headless Linux servers, add this to charts.py (already present):
# matplotlib.use("Agg")
```

### lxml missing (for earnings dates)
```bash
pip install lxml
```

---

## Updating Thresholds After Market Moves

When silver or miner prices move significantly, update the thresholds in:
1. `CRON_SPEC.md` — in the `PROMPT` strings inside `run_daily.sh` and `run_weekly.sh`
2. `DAILY_MONITOR_PROMPT.md` — the Thresholds Quick Reference Card table

Run `python main.py` to get fresh SMA200 readings, then edit those two files.

---

## Market Context as of June 28, 2026 (deployment baseline)

| Item | Value | Status |
|---|---|---|
| Silver spot | $59.22 | -51% from $121 high; below SMA200 |
| ASM | $6.15 | Below SMA200 — BEAR |
| PAAS | $45.45 | Below SMA200 — BEAR |
| CDE | $16.02 | Below SMA200 — BEAR |
| AG | $16.89 | Below SMA200 — BEAR |
| USAS | $4.81 | Below SMA200 — BEAR |
| SVM | $10.87 | Above SMA200 — BULL (only one) |
| Silver weekly | 7 consecutive down weeks |
| Weekly STC | All at 0 (extreme oversold) |
| Verdict | BEARISH FLAG — bear confirmed for 5 of 6 |

---

*Generated: June 28, 2026 | Strategy tool: silver_strategy/ | Repo: github.com/lwongkll*
