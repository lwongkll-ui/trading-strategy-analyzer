# ── Tickers ────────────────────────────────────────────────────────────────────
BTC_TICKER   = "BTC-USD"
DXY_TICKER   = "UUP"        # Invesco Dollar Index ETF (proxy for DXY)
SP500_TICKER = "^GSPC"
GOLD_TICKER  = "GC=F"
VIX_TICKER   = "^VIX"
TNX_TICKER   = "^TNX"        # 10-year Treasury yield

# ── Timeframes ─────────────────────────────────────────────────────────────────
DAILY_PERIOD   = "1y"
WEEKLY_PERIOD  = "2y"
INTRADAY_4H_PERIOD = "60d"

# ── Key Indicators ─────────────────────────────────────────────────────────────
SMA_200  = 200
SMA_50   = 50
EMA_20   = 20
RSI_LEN  = 14
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
BB_LEN, BB_STD = 20, 2.0
ATR_LEN  = 14
STOCH_K, STOCH_D = 14, 3
VOL_SMA  = 20       # volume moving average length

# ── Bull Market Thresholds ──────────────────────────────────────────────────────
BULL_RSI_OVERSOLD   = 45   # dip-buy zone in bull
BULL_RSI_OVERBOUGHT = 75   # take-profit zone in bull
BULL_RSI_HEALTHY    = (50, 65)

# ── Bear Market Thresholds ──────────────────────────────────────────────────────
BEAR_RSI_OVERBOUGHT  = 55  # short-rally zone in bear
BEAR_RSI_OVERSOLD    = 28  # cover-short / caution zone
BEAR_RSI_EXHAUSTION  = (45, 55)

# ── Extended distance from 200 SMA (mean-reversion caution) ──────────────────
OVEREXTENDED_PCT = 30      # % above/below 200 SMA triggers caution

# ── Fear & Greed API ───────────────────────────────────────────────────────────
FEAR_GREED_URL = "https://api.alternative.me/fng/?limit=1&format=json"

# ── Binance Funding Rate ───────────────────────────────────────────────────────
BINANCE_FUNDING_URL = (
    "https://fapi.binance.com/fapi/v1/fundingRate"
    "?symbol=BTCUSDT&limit=1"
)
