# Silver Miners Daily Monitoring Prompt

> Feed this entire file to your AI assistant each day to get a structured market check.
> Replace the `[PASTE TODAY'S DATA HERE]` section with fresh output from `python main.py`.

---

## Context: What You Are Monitoring

A portfolio of **6 silver miner stocks** held in a long-only strategy. The January 2026 peak has been confirmed (all stocks down 20–44% from highs). The open question is whether that was a **temporary correction** or a **major top**. Daily monitoring watches for resolution of this question.

### The Stocks

| Ticker | Company                  | 52W High  | Peak Date   | SMA200 (support) |
|--------|--------------------------|-----------|-------------|------------------|
| ASM    | Avino Silver & Gold      | $11.99    | Jan 29 '26  | ~$6.46 (thin!)   |
| PAAS   | Pan American Silver      | $69.58    | Jan 26 '26  | ~$49.25          |
| CDE    | Coeur Mining             | $27.74    | Jan 26 '26  | ~$18.83 (thin!)  |
| AG     | First Majestic Silver    | $32.01    | Feb 27 '26  | ~$17.93          |
| USAS   | Americas Gold and Silver | $10.50    | Jan 26 '26  | ~$5.54           |
| SVM    | Silvercorp Metals        | $15.75    | May 13 '26  | ~$9.52           |

### Macro Anchors

- **Silver spot** (SI=F): Peaked $121.30 on Jan 29 '26. Now ~$69–70. Critical support zone: **$65–70**.
- **DXY** (US Dollar): Rising DXY = bearish for silver. Watch for DXY >106.
- **Gold/Silver ratio**: Expanding ratio (>80) = silver underperforming gold = bearish signal.
- **SIL ETF**: Sector proxy. Break below its SMA50 = sector weakness confirmed.

---

## The Two Scenarios Being Watched (Point 6)

### BULL CASE — January 2026 was a correction, uptrend resumes
All of the following should be TRUE:
- [ ] Silver spot holds above $65 and ideally reclaims $80+
- [ ] At least 4 of 6 miners remain above their SMA200
- [ ] STC-Slow is turning UP from current extreme lows (target: crossing above 25)
- [ ] STC-Fast generates confirmed BUY signals (cross above 25 from oversold)
- [ ] SVM (the leader) pushes toward new 52W high
- [ ] MACD histograms turn positive for majority of names
- [ ] DXY stays below 106

### BEAR CASE — January 2026 was the major top, bear market confirmed
Any of the following triggers a BEARISH FLAG:
- [ ] Silver spot closes below **$65** on daily chart
- [ ] Any miner closes below its **SMA200** (especially ASM, CDE — thinnest cushion)
- [ ] SVM (the strongest name) breaks below $11.50 (SMA50 support)
- [ ] DXY breaks above **106**
- [ ] Gold/Silver ratio expands above **80**
- [ ] SIL ETF closes below its 50-day SMA
- [ ] STC-Slow turns DOWN from current readings (confirms momentum failure)
- [ ] MACD histogram stays negative for 3+ weeks (no recovery)

---

## Peak Detection Indicator Framework

### Stage 1 — Overbought (do not enter new longs)
- RSI > 75 AND STC-Fast > 85 on daily

### Stage 2 — Sell trigger (exit or reduce)
- STC-Fast crosses BELOW 75 from above
- MACD histogram flips from green to red (positive to negative)

### Stage 3 — Trend break (potential major top forming)
- Price closes below SMA50 on daily
- STC-Slow crosses below 50 and heads toward 25
- Note: 4 of 6 names are already in Stage 3 territory

### Stage 4 — Major top confirmed (bear market)
- Price closes below SMA200 (bear regime)
- Silver spot loses $65 support
- DXY rising + Gold/Silver ratio expanding simultaneously

**Current stage as of Jun 16, 2026**: Between Stage 2 and 3 for most names. SVM is the strongest (already recovering). ASM, AG, USAS are deepest in Stage 3.

---

## SVM as the Leading Indicator

**SVM is the canary.** It peaked 3.5 months later than the rest (May vs January), is the least oversold, and already completed a sell + re-buy cycle. Use it as the market leader:

- **SVM STC-Fast > 80 and rising** → bull case gaining traction
- **SVM STC-Fast < 40 and falling** → bear case gaining traction
- **SVM price closes below $11.50** → BEARISH FLAG for entire complex
- **SVM price closes above $14.00** → sector recovery likely underway

---

## Daily Check Instructions

Each day, run `python main.py` from the `silver_strategy/` directory and paste the output below. Then answer the following questions:

### Daily Output
```
[PASTE TODAY'S python main.py OUTPUT HERE]
```

---

## Questions to Answer Each Day

**1. Silver Spot Status**
- Current price vs yesterday: up or down?
- Is it above or below $70 (key level)?
- Is it approaching $65 (critical support) or $80 (recovery target)?
- 1-week trend: higher lows forming, or lower lows?

**2. SVM Status (leading indicator)**
- STC-Fast: above or below 75? Trend direction?
- Price vs SMA50 ($12.33): above or below?
- New BUY or SELL signal triggered today?

**3. Bearish Flag Check** (answer YES/NO for each)
- Silver below $65? [YES/NO]
- Any miner closed below SMA200? [YES/NO — name which one]
- SVM below $11.50? [YES/NO]
- DXY above 106? [YES/NO]
- Gold/Silver ratio above 80? [YES/NO]

**4. Bull Recovery Check** (answer YES/NO for each)
- Silver above $75 and rising? [YES/NO]
- STC-Slow turning up for majority of names? [YES/NO]
- MACD histograms net positive (4 of 6 positive)? [YES/NO]
- SVM STC-Fast > 80? [YES/NO]

**5. Overall Verdict for Today**
Choose one:
- **RECOVERY BUILDING** — bull signals accumulating, hold positions
- **WATCH AND WAIT** — mixed signals, no new action
- **BEARISH FLAG** — one or more bear triggers hit, reduce exposure
- **BEAR CONFIRMED** — major top confirmed, exit remaining positions

**6. Priority Action (if any)**
State any specific action needed today (e.g., "CDE approaching SMA200 at $18.83 — set alert", "Silver broke $65 — review positions").

---

## Thresholds Quick Reference Card

| Item             | Bullish Above | Bearish Below | Current (Jun 16 '26) |
|------------------|--------------|---------------|----------------------|
| Silver spot      | $80          | $65           | ~$70 (neutral zone)  |
| DXY              | —            | 106 (rising)  | check daily          |
| Gold/Silver ratio| —            | 80 (expanding)| check daily          |
| SVM price        | $14.00       | $11.50        | $12.55               |
| ASM price        | $8.00        | $6.46 (SMA200)| $6.80 (thin!)        |
| PAAS price       | $60.00       | $49.25 (SMA200)| $51.78              |
| CDE price        | $22.00       | $18.83 (SMA200)| $18.93 (thin!)      |
| AG price         | $25.00       | $17.93 (SMA200)| $19.15              |
| USAS price       | $7.50        | $5.54 (SMA200) | $5.84               |
| SVM price        | $14.00       | $9.52 (SMA200) | $12.55              |
| STC-Fast (any)   | > 75 (bull)  | < 25 (bear extreme) | ASM:14, CDE:14, AG:12, USAS:18, PAAS:68, SVM:82 |
| STC-Slow (any)   | > 50         | < 20 (danger zone)  | ASM:6, AG:5, USAS:6, CDE:15, PAAS:19, SVM:41 |

---

## How to Run the Daily Data Pull

```bash
cd silver_strategy
python main.py
```

For charts (weekly or before key decisions):
```bash
python main.py --chart --weekly
```

Charts are saved to `silver_strategy/silver_charts/`.

---

## Background: Why This Matters

Silver miners provide **leveraged exposure to silver price**. A 10% move in silver typically produces 20–40% moves in junior miners (ASM, USAS) and 15–25% in mid-caps (PAAS, CDE, AG). This leverage works both ways. The -42% decline in silver from $121 to $70 produced the -20% to -44% declines currently observed.

The key non-technical driver to watch:
- **DXY (US Dollar)**: Real rates and dollar strength are the primary silver headwind
- **Industrial demand**: Solar panel and EV demand provides a structural floor under silver
- **Gold/Silver ratio**: When gold outperforms silver (ratio rising), institutional money is defensive — not a risk-on environment favorable to silver miners
- **Fed policy**: Rate cut expectations weaken DXY, which is bullish for silver and miners

---

*Last updated: June 16, 2026. Baseline established after confirmed January 2026 peak.*
*Strategy tool: silver_strategy/ (Python). Run `python main.py` for fresh data.*
