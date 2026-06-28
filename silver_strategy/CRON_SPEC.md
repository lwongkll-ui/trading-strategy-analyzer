# Silver Miners Monitor — Cron Job Specification

Automated daily and weekly market analysis using OpenClaw + DeepSeek V4 Flash.
Deploy this on any machine that has the `silver_strategy/` Python environment installed.

---

## Overview

Two scheduled jobs:

| Job | Schedule | Trigger | Output |
|-----|----------|---------|--------|
| `daily_check` | Mon–Fri, 09:00 local | After market open data is available | Daily trend + support check |
| `weekly_review` | Saturday, 08:00 local | After Friday close is settled | Full weekly technical summary |

---

## Prerequisites

### On the cron machine

```bash
# Python environment
pip install yfinance pandas numpy matplotlib mplfinance rich requests

# OpenClaw installed and authenticated
openclaw --version          # confirm it works
openclaw config set model deepseek-v4-flash

# Repo cloned
git clone <your-repo-url> ~/silver_strategy_monitor
```

### Environment variables

```bash
# ~/.bashrc or /etc/environment
export SILVER_STRATEGY_DIR="/home/<user>/silver_strategy_monitor/silver_strategy"
export OPENCLAW_MODEL="deepseek-v4-flash"
export MONITOR_LOG_DIR="/var/log/silver_monitor"
export ALERT_EMAIL="lwongkll@gmail.com"    # optional, if mail is configured
```

---

## Directory Layout

```
/var/log/silver_monitor/
  daily/
    YYYY-MM-DD.txt          # raw python main.py output
    YYYY-MM-DD_analysis.md  # LLM analysis output
  weekly/
    YYYY-WNN.txt            # raw weekly output
    YYYY-WNN_analysis.md    # LLM weekly analysis
  alerts/
    YYYY-MM-DD_ALERT.md     # written only when bearish flags trigger
  last_run.json             # state file: last prices, flags hit
```

---

## Job 1 — Daily Check

### Shell script: `run_daily.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

DATE=$(date +%Y-%m-%d)
LOG_DIR="${MONITOR_LOG_DIR}/daily"
mkdir -p "$LOG_DIR"

RAW_OUT="$LOG_DIR/${DATE}.txt"
ANALYSIS_OUT="$LOG_DIR/${DATE}_analysis.md"
ALERT_DIR="${MONITOR_LOG_DIR}/alerts"
mkdir -p "$ALERT_DIR"

# Step 1 — Collect data
cd "$SILVER_STRATEGY_DIR"
python main.py > "$RAW_OUT" 2>&1

# Step 2 — Build prompt
DATA=$(cat "$RAW_OUT")

PROMPT=$(cat <<PROMPT
You are a systematic silver miner stock analyst. Analyse today's data and answer
the 6 daily questions. Be concise and specific — numbers, not adjectives.

=== CONTEXT ===
Portfolio: ASM, PAAS, CDE, AG, USAS, SVM (long-only, no short selling).
Confirmed January 2026 peak (silver hit \$121). Monitoring for bear vs. recovery.

=== BEAR FLAG THRESHOLDS (trigger ALERT if ANY hit) ===
- Silver spot closes below \$57.04 (weekly 61.8% Fibonacci)
- Any miner closes below its SMA200:
    ASM SMA200 ~\$6.54  |  PAAS ~\$49.70  |  CDE ~\$18.95
    AG ~\$18.26          |  USAS ~\$5.64   |  SVM ~\$9.73
- SVM (leader) closes below \$11.50
- DXY breaks above 106
- Gold/Silver ratio expands above 80

=== RECOVERY THRESHOLDS (confirm bull case only if ALL hold) ===
- Silver closes above weekly SMA50 (\$63.09)
- Weekly MACD histogram turns positive for 4 of 6 names
- Weekly STC-Slow crosses above 20 (watch SVM first — was at 11)
- SVM holds above \$12.04 (23.6% weekly fib)

=== TODAY'S DATA ===
$DATA

=== YOUR TASK ===
Answer each section below. Use numbers. Flag anything that crossed a threshold.

## 1. Silver spot status
- Price vs yesterday (up/down, amount):
- Position vs \$57.04 support (distance %):
- Position vs \$63.09 resistance (distance %):
- 1-week trend (higher lows / lower lows):

## 2. SVM status (leading indicator)
- Price vs yesterday:
- STC-Fast value and direction (rising/falling):
- Price vs \$11.50 floor (above/below, distance):
- New signal triggered today (BUY/SELL/none):

## 3. Bear flag check
Answer YES or NO for each. If YES, describe what crossed.
- Silver below \$57.04: [YES/NO]
- Any miner below SMA200: [YES/NO — which ticker(s)]
- SVM below \$11.50: [YES/NO]
- DXY above 106: [YES/NO]
- Gold/Silver ratio above 80: [YES/NO]

## 4. Recovery check
Answer YES or NO for each.
- Silver above \$63.09 (weekly SMA50): [YES/NO]
- Weekly MACD histogram net positive (4+ of 6): [YES/NO]
- SVM STC-Slow above 20: [YES/NO]

## 5. Verdict
Choose exactly one:
- RECOVERY BUILDING — bull signals accumulating, hold positions
- WATCH AND WAIT — mixed signals, no new action
- BEARISH FLAG — one or more bear triggers hit, reduce exposure
- BEAR CONFIRMED — major top confirmed, exit remaining positions

## 6. Priority action today (one sentence, specific and actionable)
PROMPT
)

# Step 3 — Run LLM
echo "$PROMPT" | openclaw run \
  --model "$OPENCLAW_MODEL" \
  --system "You are a concise, data-driven silver mining stock analyst. Reply only with the structured analysis. No preamble." \
  --temperature 0.1 \
  --max-tokens 1200 \
  > "$ANALYSIS_OUT"

# Step 4 — Check for ALERT condition
if grep -q "BEARISH FLAG\|BEAR CONFIRMED" "$ANALYSIS_OUT"; then
  ALERT_FILE="$ALERT_DIR/${DATE}_ALERT.md"
  cp "$ANALYSIS_OUT" "$ALERT_FILE"
  echo "### ALERT triggered ${DATE}" >> "$ALERT_FILE"

  # Optional: send email if mail is configured
  if command -v mail &>/dev/null && [ -n "${ALERT_EMAIL:-}" ]; then
    mail -s "SILVER ALERT: $(grep -o 'BEARISH FLAG\|BEAR CONFIRMED' "$ANALYSIS_OUT" | head -1) — $DATE" \
      "$ALERT_EMAIL" < "$ALERT_FILE"
  fi
fi

# Step 5 — Update state file
VERDICT=$(grep -o 'RECOVERY BUILDING\|WATCH AND WAIT\|BEARISH FLAG\|BEAR CONFIRMED' "$ANALYSIS_OUT" | head -1 || echo "UNKNOWN")
python3 - <<PY
import json, datetime, os
state_path = os.path.join(os.environ['MONITOR_LOG_DIR'], 'last_run.json')
try:
    with open(state_path) as f:
        state = json.load(f)
except Exception:
    state = {}
state['last_daily'] = '$DATE'
state['last_verdict'] = '$VERDICT'
with open(state_path, 'w') as f:
    json.dump(state, f, indent=2)
PY

echo "Daily check complete: $VERDICT — $DATE"
echo "Analysis: $ANALYSIS_OUT"
```

---

## Job 2 — Weekly Review

### Shell script: `run_weekly.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

WEEK=$(date +%Y-W%V)
LOG_DIR="${MONITOR_LOG_DIR}/weekly"
mkdir -p "$LOG_DIR"

RAW_OUT="$LOG_DIR/${WEEK}.txt"
ANALYSIS_OUT="$LOG_DIR/${WEEK}_analysis.md"

# Step 1 — Collect data with weekly charts
cd "$SILVER_STRATEGY_DIR"
python main.py --weekly > "$RAW_OUT" 2>&1

DATA=$(cat "$RAW_OUT")

PROMPT=$(cat <<PROMPT
You are a systematic silver miner analyst doing an end-of-week review.
Provide a structured weekly analysis. Be specific — use numbers, not adjectives.

=== PORTFOLIO ===
ASM, PAAS, CDE, AG, USAS, SVM (long-only). January 2026 peak confirmed.
Monitoring: bear vs. recovery. SVM is the leading indicator.

=== WEEKLY REVERSAL CONDITIONS (all must be true for a bull call) ===
1. Silver closes above weekly SMA50 (\$63.09)
2. Weekly MACD histogram turns positive for 4+ of 6 names
3. Weekly STC-Slow crosses above 20 (SVM was at 11 last week)
4. No miner breaks below its SMA200

=== CRITICAL WEEKLY LEVELS ===
Silver: 61.8% weekly fib \$57.04 (last support before \$39.57)
ASM:  50% fib \$6.19 | SMA50w \$6.09   PAAS: 38.2% fib \$47.48 | SMA50w \$46.63
CDE:  38.2% fib \$17.91                AG:   50% fib \$18.07 (already below) | SMA50w \$16.66
USAS: 61.8% fib \$4.32 (near)          SVM:  23.6% fib \$12.04 | SMA50w \$8.88

=== THIS WEEK'S DATA ===
$DATA

=== YOUR TASK ===

## Weekly performance table
| Ticker | Price | 1W% | 4W% | 13W% | RSI | STC-F | STC-S | vs SMA200 |
(fill in from data)

## Silver weekly assessment
- This week's action (up/down, %, candle type):
- Consecutive down/up weeks:
- Position vs \$57.04 (61.8% fib):
- Weekly RSI and STC readings:
- Verdict for silver: HOLDING SUPPORT / BREAKING DOWN / RECOVERING

## Miner weekly assessment
For each of the 6 tickers:
  - Weekly candle character (body size, wick direction — is it showing rejection or continuation?):
  - Bollinger %B (near lower band = potential bounce; above 50% = strength):
  - Volume vs average (high volume down = distribution / high volume up = accumulation):
  - Key level proximity:

## SVM lead indicator check
- 13-week return vs peers (relative strength):
- Weekly STC-Slow: did it cross above 20? (reversal trigger):
- Price vs \$12.04 (23.6% fib):

## Weekly verdict
Choose exactly one:
- RECOVERY BUILDING — weekly reversal conditions being met
- WATCH AND WAIT — oversold bounce possible, no confirmed reversal
- BEARISH FLAG — critical support breaking down
- BEAR CONFIRMED — weekly structure broken, exit remaining positions

## Action plan for next week
Three specific, numbered actions with price triggers.
Example format: "1. If SVM holds \$10.50 Mon–Tue, add half position. 2. If silver breaks \$57, cut remaining longs 50%. 3. Watch CDE volume — high volume bounce = accumulation signal."
PROMPT
)

echo "$PROMPT" | openclaw run \
  --model "$OPENCLAW_MODEL" \
  --system "You are a concise, data-driven silver mining stock analyst. Reply only with the structured analysis. No preamble." \
  --temperature 0.1 \
  --max-tokens 2000 \
  > "$ANALYSIS_OUT"

if grep -q "BEARISH FLAG\|BEAR CONFIRMED" "$ANALYSIS_OUT"; then
  ALERT_FILE="${MONITOR_LOG_DIR}/alerts/${WEEK}_WEEKLY_ALERT.md"
  cp "$ANALYSIS_OUT" "$ALERT_FILE"
  if command -v mail &>/dev/null && [ -n "${ALERT_EMAIL:-}" ]; then
    mail -s "SILVER WEEKLY ALERT: $WEEK" "$ALERT_EMAIL" < "$ALERT_FILE"
  fi
fi

echo "Weekly review complete — $WEEK"
echo "Analysis: $ANALYSIS_OUT"
```

---

## Crontab Entries

```cron
# Silver miners — daily check (Mon–Fri at 09:00)
0 9 * * 1-5 /home/<user>/scripts/run_daily.sh >> /var/log/silver_monitor/cron.log 2>&1

# Silver miners — weekly review (Saturday at 08:00)
0 8 * * 6 /home/<user>/scripts/run_weekly.sh >> /var/log/silver_monitor/cron.log 2>&1
```

Install:
```bash
chmod +x run_daily.sh run_weekly.sh
crontab -e
# paste the two lines above
```

Verify:
```bash
crontab -l
# manual test run:
bash run_daily.sh
```

---

## OpenClaw Call Summary

The scripts pipe a prompt to `openclaw run` via stdin. Adjust flags to match
your OpenClaw version's exact CLI syntax — the logical interface is:

```
openclaw run \
  --model deepseek-v4-flash \
  --system "<system prompt>" \
  --temperature 0.1 \
  --max-tokens <N> \
  < prompt_file.txt
```

If your OpenClaw version uses positional arguments or a different flag set:

```bash
# Alternative: prompt file approach
echo "$PROMPT" > /tmp/silver_prompt.txt
openclaw chat --model deepseek-v4-flash \
              --file /tmp/silver_prompt.txt \
              --output "$ANALYSIS_OUT"

# Alternative: if openclaw reads from a config
openclaw run --config /etc/openclaw/silver.yaml < /tmp/silver_prompt.txt
```

### Model choice note
DeepSeek V4 Flash is chosen for:
- Low latency (daily check should complete in <30s)
- Low cost per run (hundreds of tokens of structured output)
- Sufficient reasoning for quantitative template-fill tasks

If DeepSeek V4 Flash is not available, fallback order:
`deepseek-v3` → `deepseek-chat` → `qwen2.5-72b-instruct`

---

## Alert Logic Summary

```
Verdict           → Action
─────────────────────────────────────────────────
RECOVERY BUILDING → Log only, no alert
WATCH AND WAIT    → Log only, no alert
BEARISH FLAG      → Write to alerts/, send email
BEAR CONFIRMED    → Write to alerts/, send email
```

A BEARISH FLAG requires ANY ONE of:
- Silver < $57.04
- Any ticker below SMA200
- SVM < $11.50
- DXY > 106
- Gold/Silver ratio > 80

---

## Viewing Outputs

```bash
# Today's analysis
cat /var/log/silver_monitor/daily/$(date +%Y-%m-%d)_analysis.md

# This week's review
cat /var/log/silver_monitor/weekly/$(date +%Y-W%V)_analysis.md

# Any active alerts
ls /var/log/silver_monitor/alerts/

# Last known verdict
cat /var/log/silver_monitor/last_run.json
```

---

## Adjusting Thresholds

All price thresholds in the prompt strings correspond to the levels defined in
`silver_strategy/DAILY_MONITOR_PROMPT.md`. If SMA200 levels drift significantly
(they move ~$0.05–0.10 per week), update the thresholds in both:
- This file (`CRON_SPEC.md`)
- `DAILY_MONITOR_PROMPT.md`

Re-run `python main.py` weekly to get current SMA200 readings and update as needed.

---

*Spec version: June 28, 2026. Based on daily analysis showing 5 of 6 miners below SMA200 and silver at $59.22 (-51% from $121 high).*
