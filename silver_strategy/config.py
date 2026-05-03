SILVER_MINERS = {
    "ASM":  "Avino Silver & Gold Mines",
    "PAAS": "Pan American Silver Corp",
    "CDE":  "Coeur Mining",
    "AG":   "First Majestic Silver",
    "USAS": "Americas Gold and Silver",
    "SVM":  "Silvercorp Metals",
}

# Macro tickers
SILVER_SPOT = "SI=F"
GOLD_SPOT   = "GC=F"
DXY         = "DX-Y.NYB"
SP500       = "^GSPC"
VIX         = "^VIX"
TNX         = "^TNX"   # 10-Year Treasury yield
SIL_ETF     = "SIL"    # Silver Miners ETF (benchmark)

# Moving averages
SMA_SHORT = 20
SMA_MID   = 50
SMA_LONG  = 200
EMA_FAST  = 9
EMA_SLOW  = 21

# RSI
RSI_PERIOD    = 14
RSI_OVERSOLD  = 30
RSI_OVERBOUGHT = 70

# MACD
MACD_FAST   = 12
MACD_SLOW   = 26
MACD_SIGNAL = 9

# Bollinger Bands
BB_PERIOD = 20
BB_STD    = 2.0

# ATR
ATR_PERIOD = 14

# Fast STC — responsive, good for entry/exit timing
STC_FAST = dict(macd_fast=10, macd_slow=23, k=10, d=3)

# Slow STC — trend confirmation
STC_SLOW = dict(macd_fast=23, macd_slow=50, k=10, d=5)

STC_OVERSOLD   = 25
STC_OVERBOUGHT = 75

# Stochastic RSI smoothing
STOCH_K = 3
STOCH_D = 3

# Volume MA
VOL_MA_PERIOD = 20

# Signal scoring thresholds (pure technical, for historical chart signals)
BUY_THRESHOLD  = 5
SELL_THRESHOLD = -3

# Data periods
DAILY_PERIOD  = "2y"
WEEKLY_PERIOD = "5y"
HOURLY_PERIOD = "60d"

OUTPUT_DIR = "silver_charts"
