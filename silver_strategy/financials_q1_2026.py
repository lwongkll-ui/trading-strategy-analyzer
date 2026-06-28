"""
Silver Miners — Q1 2026 financial dataset (as of March 31, 2026).
Transcribed from Silver_Miners_Financial_Analysis.docx. Update this file each
quarter; financial_review.py renders it to per-section PNGs for Discord.

All figures USD millions unless noted. Parentheses = negative.
"""

AS_OF = "Q1 2026 (March 31, 2026)"
ANALYSIS_DATE = "June 28, 2026"
SILVER_REF = "$59.22/oz at report; live spot ~$59.67"

EXEC_SUMMARY = [
    "Silver miners peaked Jan–Feb 2026 at silver $121/oz; silver has since fallen to ~$59 (−51%).",
    "All 6 reported their strongest-ever quarter in Q1 2026 — but those results reflect silver at $70–80+. Forward earnings compress materially at $59.",
    "All 6 hold NET CASH positions (more cash than debt) — exceptional resilience vs the 2015–16 bear.",
    "Gross margins expanded sharply 2025 → Q1 2026 as silver rose.",
    "USAS only turned profitable in Q1 2026 after 4 loss quarters — most fragile.",
    "SVM has the best mine economics (68% gross margin) but GAAP net income is distorted by FX/depletion.",
    "CDE EPS is declining despite revenue growth due to share dilution (642M → 1,035M shares).",
    "PAAS is the cheapest profitable name at 14.8x TTM P/E with $1.31B TTM free cash flow.",
]

# Section 2 — company profiles: (name, listing, text)
PROFILES = {
    "ASM":  ("Avino Silver & Gold Mines", "TSX/NYSE: ASM",
             "Small-cap silver miner operating the Avino Mine in Durango, Mexico. Market cap ~$1.08B. "
             "Virtually debt-free (D/E 0.03) with $138.6M cash vs $8.3M debt. Revenue more than doubled "
             "from $18.8M (Q1'25) to $39.4M (Q1'26). Stock issuance is the primary funding mechanism — "
             "shares grew 141.7M → 175.3M over the year."),
    "PAAS": ("Pan American Silver Corp", "NASDAQ: PAAS",
             "Largest miner in the group ($19.15B). TTM revenue ~$4.0B, TTM net income ~$1.27B, TTM FCF "
             "$1.31B. Net cash $650M. Only name with consistently strong EPS across all 5 quarters "
             "($0.40–$1.08). At 14.8x TTM P/E, the cheapest among profitable names."),
    "CDE":  ("Coeur Mining", "NYSE: CDE",
             "Mid-cap US silver/gold miner ($16.5B) in Nevada, Idaho, Alaska, Mexico. Share count doubled "
             "~642M → ~1,035M via equity offering, suppressing per-share metrics despite revenue growth "
             "$360M (Q1'25) → $856M (Q1'26). Strong FCF ($915M TTM). Net cash $69.9M."),
    "AG":   ("First Majestic Silver", "NYSE: AG",
             "Pure-play silver miner ($8.34B) in Mexico and Nevada. Fastest gross-margin improvement: "
             "25.9% (Q1'25) → 55.4% (Q1'26). Net cash $671M (largest relative to size). EPS $0.013 → "
             "$0.299 over the year — strongest per-share earnings trajectory."),
    "USAS": ("Americas Gold and Silver", "NYSE: USAS",
             "Small-cap ($1.62B) operating Relief Canyon (Nevada) and Cosala (Mexico). Riskiest name — "
             "loss-making for 4 quarters, profitable only in Q1'26 ($10M). Below $60 silver it likely "
             "returns to operating losses. Gross margin swung −13% → +55% in a year — highest price leverage."),
    "SVM":  ("Silvercorp Metals", "NYSE: SVM",
             "Chinese silver miner ($2.40B) operating the Ying Mining District, Henan. Best gross margins "
             "(67.8% Q1'26). Strong operating cash flow ($310M TTM) but GAAP net income negative on "
             "non-cash charges (depletion) and CNY/USD FX losses. Key risk: China exposure."),
}

# Section 3
REVENUE = {
    "headers": ["Ticker", "Q1'26", "Q4'25", "Q3'25", "Q2'25", "Q1'25", "TTM", "YoY"],
    "rows": [
        ["ASM", "39.4", "30.5", "21.0", "21.8", "18.8", "112.7", "+110%"],
        ["PAAS", "1,154", "1,179", "855", "812", "773", "4,000", "+49%"],
        ["CDE", "856", "675", "555", "481", "360", "2,567", "+138%"],
        ["AG", "481", "468", "287", "265", "246", "1,501", "+96%"],
        ["USAS", "67.8", "36.9", "30.6", "26.9", "23.5", "162.2", "+189%"],
        ["SVM", "147.4", "126.1", "83.3", "81.3", "75.1", "438.1", "+96%"],
    ],
}
NET_INCOME = {
    "headers": ["Ticker", "Q1'26", "Q4'25", "Q3'25", "Q2'25", "Q1'25", "TTM"],
    "rows": [
        ["ASM", "15.9", "10.5", "7.7", "2.9", "5.6", "37.0"],
        ["PAAS", "457", "452", "169", "189", "169", "1,267"],
        ["CDE", "247", "215", "267", "70.7", "33.4", "799.5"],
        ["AG", "147.5", "83.1", "27.0", "56.6", "6.2", "314.2"],
        ["USAS", "10.0", "(37.7)", "(15.7)", "(15.1)", "(19.7)", "(58.5)"],
        ["SVM", "(0.7)", "(15.8)", "(11.5)", "18.1", "(7.6)", "(9.9)"],
    ],
}

# Section 4
EPS = {
    "headers": ["Ticker", "Q1'26", "Q4'25", "Q3'25", "Q2'25", "Q1'25", "Trend"],
    "rows": [
        ["ASM", "$0.094", "$0.064", "$0.050", "$0.020", "$0.040", "Strongly improving"],
        ["PAAS", "$1.084", "$1.070", "$0.400", "$0.523", "$0.467", "Strongly improving"],
        ["CDE", "$0.239", "$0.335", "$0.416", "$0.110", "$0.052", "Peaked Q3'25, declining (dilution)"],
        ["AG", "$0.299", "$0.169", "$0.055", "$0.116", "$0.013", "Strongly improving"],
        ["USAS", "$0.031", "($0.118)", "($0.057)", "($0.023)", "($0.030)", "Turned positive Q1'26 (fragile)"],
        ["SVM", "($0.003)", "($0.072)", "($0.053)", "$0.083", "($0.035)", "Erratic — GAAP distorted"],
    ],
    "note": ("SVM operating income is strongly positive ($228M TTM) but GAAP net income is negative due to "
             "large non-cash charges (depletion, amortization) and CNY/USD FX losses. Operating cash flow "
             "($310M TTM) is the better profitability indicator for SVM."),
}

# Section 5
GROSS_MARGIN = {
    "headers": ["Ticker", "Q1'26", "Q4'25", "Q3'25", "Q2'25", "Q1'25", "Commentary"],
    "rows": [
        ["SVM", "67.8%", "61.1%", "49.0%", "44.0%", "34.8%", "Best margins — efficient ops, low AISC"],
        ["ASM", "59.4%", "58.4%", "47.1%", "46.9%", "56.1%", "Consistently high — well-run small miner"],
        ["AG", "55.4%", "50.8%", "34.6%", "18.6%", "25.9%", "Most dramatic improvement"],
        ["USAS", "54.7%", "30.5%", "22.1%", "(11.3%)", "(13.2%)", "Turnaround — negative to positive in a year"],
        ["PAAS", "52.7%", "48.2%", "36.6%", "33.7%", "32.5%", "Steadily expanding — diversified portfolio"],
        ["CDE", "49.8%", "57.1%", "42.0%", "39.5%", "31.3%", "Q4'25 peak; Q1'26 slight compression"],
    ],
    "warning": ("All margins reflect silver at $70–80+. With silver at ~$59 today, Q2 2026 margins are "
                "estimated to compress 10–20 percentage points across the group."),
}

# Section 6
BALANCE = {
    "headers": ["Ticker", "Assets", "Debt", "Cash", "Net Cash", "Equity", "D/E", "NetDebt/EBITDA", "Rating"],
    "rows": [
        ["ASM", "$318.8M", "$8.3M", "$138.6M", "$130.3M", "$275.4M", "0.03", "(2.42x)", "Fortress"],
        ["PAAS", "$10,132M", "$845M", "$1,495M", "$650M", "$7,354M", "0.11", "(0.30x)", "Net Cash"],
        ["CDE", "$15,261M", "$773M", "$843M", "$70M", "$10,412M", "0.07", "(0.05x)", "Net Cash"],
        ["AG", "$4,819M", "$314M", "$985M", "$671M", "$2,895M", "0.09", "(0.82x)", "Net Cash"],
        ["USAS", "$438.6M", "$54.4M", "$122.4M", "$68M", "$238.6M", "0.23", "(1.99x)", "Net Cash"],
        ["SVM", "$1,464M", "$118.4M", "$422M", "$304M", "$941M", "0.11", "(1.31x)", "Net Cash"],
    ],
    "current_ratio": [
        ["ASM", "5.8x (exceptional)"], ["PAAS", "2.8x"], ["CDE", "3.7x"],
        ["AG", "2.7x"], ["USAS", "1.7x"], ["SVM", "3.6x"],
    ],
    "note": "All 6 miners hold more cash than debt (net cash) — rare in the mining sector.",
}

# Section 7
FCF = {
    "headers": ["Ticker", "Q1'26", "Q4'25", "Q3'25", "Q2'25", "TTM FCF", "Capex Q1'26", "FCF Yield"],
    "rows": [
        ["ASM", "11.0", "5.9", "(8.6)", "4.4", "12.7", "(2.7)", "1.2%"],
        ["PAAS", "400", "462", "218", "233", "1,313", "(105)", "6.9%"],
        ["CDE", "267", "313", "189", "146", "915", "(74)", "5.5%"],
        ["AG", "189", "221", "55", "41", "506", "(47.5)", "6.1%"],
        ["USAS", "(0.9)", "(31.9)", "(21.7)", "(5.0)", "(59.5)", "(22.8)", "-3.7%"],
        ["SVM", "(29.1)", "128.3", "11.4", "48.3", "158.9", "(119.3)", "6.6%*"],
    ],
    "note": ("SVM Q1'26 FCF negative due to a $119.3M capex spike (mine development). USAS negative TTM FCF "
             "funded by a $128.8M equity raise in Q4 2025."),
}

# Section 8
VALUATION = {
    "headers": ["Ticker", "Price", "Mkt Cap", "TTM P/E", "P/B", "EV/EBITDA", "FCF Yield", "Verdict"],
    "rows": [
        ["ASM", "$6.15", "$1.08B", "27.0x", "3.9x", "~18x", "1.2%", "Fair value, watch margins"],
        ["PAAS", "$45.45", "$19.2B", "14.8x", "2.6x", "8.4x", "6.9%", "Best value in group"],
        ["CDE", "$16.02", "$16.5B", "14.6x", "1.6x", "11.2x", "5.5%", "Cheap P/B, dilution risk"],
        ["AG", "$16.89", "$8.34B", "26.4x", "2.9x", "9.5x", "6.1%", "Premium for pure-play silver"],
        ["USAS", "$4.81", "$1.62B", "N/M", "6.8x", "N/M", "-3.7%", "Speculative — no earnings base"],
        ["SVM", "$10.87", "$2.40B", "N/M", "2.6x", "~9.7x", "6.6%*", "GAAP distorted; ops strong"],
    ],
}

# Section 9 — risk matrix (values get color-coded by level)
RISK = {
    "headers": ["Ticker", "Silver Price", "Balance Sheet", "Earnings Quality", "Dilution", "Overall"],
    "rows": [
        ["ASM", "HIGH", "LOW — fortress", "GOOD", "MODERATE", "MODERATE"],
        ["PAAS", "LOW", "LOW — $650M net cash", "EXCELLENT", "LOW", "LOW"],
        ["CDE", "MODERATE", "LOW — net cash", "GOOD but diluted", "HIGH — shares doubled", "MODERATE"],
        ["AG", "MODERATE", "LOW — $671M net cash", "GOOD", "LOW", "LOW-MODERATE"],
        ["USAS", "VERY HIGH", "MODERATE", "POOR — 1 qtr positive", "HIGH", "HIGH"],
        ["SVM", "MODERATE", "LOW — $304M net cash", "COMPLEX — GAAP distorted", "LOW", "MODERATE"],
    ],
}

# Section 10
CONCLUSIONS = [
    "Financial health is strong — all 6 can survive a silver bear without bankruptcy. Net cash across the board is a major positive vs the 2015–16 bear.",
    "Forward earnings will compress. Q1'26 reflected silver $70–80+. At $59, model 20–35% EBITDA compression for Q2'26 vs Q1'26.",
    "USAS is most vulnerable. One quarter at $59 likely pushes it back to operating losses; ~2–3 quarters of cash runway before financing needed.",
    "PAAS is the highest-quality name at current valuations — 14.8x P/E, $1.3B FCF, net cash, most consistent EPS. Best risk-adjusted return if silver recovers.",
    "CDE dilution is a structural negative. Doubled share count means EPS growth needs silver well above recent levels to deliver per-share value.",
    "SVM operational quality is masked by GAAP. 68% gross margin and $310M TTM operating cash flow tell a better story than negative net income — track op cash flow, not GAAP EPS.",
]
SILVER_THRESHOLDS = [
    ("Above $75", "all 6 profitable"),
    ("$60–75", "PAAS / CDE / AG / SVM profitable, ASM marginal, USAS breakeven"),
    ("Below $60", "USAS loss-making — re-evaluate all positions"),
    ("Below $50", "only SVM and PAAS likely remain strongly profitable"),
]
