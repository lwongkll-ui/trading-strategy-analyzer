import yfinance as yf
import pandas as pd
import numpy as np

from config import (
    SILVER_MINERS, SILVER_SPOT, GOLD_SPOT, DXY, SP500, VIX, TNX, SIL_ETF,
    DAILY_PERIOD, WEEKLY_PERIOD, HOURLY_PERIOD,
)


def fetch_ohlcv(ticker: str, period: str, interval: str) -> pd.DataFrame:
    df = yf.download(ticker, period=period, interval=interval,
                     auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    df.index = pd.to_datetime(df.index)
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    return df


def _row(df, *names):
    """Newest-first list of floats for the first matching row label of a yfinance statement."""
    for n in names:
        if n in df.index:
            return [float(x) for x in df.loc[n].tolist() if pd.notna(x)]
    return []


def _derive_info_from_statements(t, info: dict) -> None:
    """Yahoo's .info endpoint is blocked (401 'unable to access this feature', since ~2026-11); the statement
    endpoints still work. Fill the .info-style keys the scorer needs from the quarterly statements plus the
    already-set marketCap. Only fills keys that are missing, so a working .info is left untouched.
    Forward P/E, analyst target, beta etc. cannot be derived and stay None."""
    def put(key, val):
        if val is not None and not info.get(key):
            info[key] = val
    try:
        inc, bs, cf = t.quarterly_income_stmt, t.quarterly_balance_sheet, t.quarterly_cashflow
        mcap = info.get("marketCap")
        rev = _row(inc, "Total Revenue")
        ni = _row(inc, "Net Income Common Stockholders", "Net Income")
        ebitda = _row(inc, "EBITDA", "Normalized EBITDA")
        opi = _row(inc, "Operating Income")
        fcf = _row(cf, "Free Cash Flow")
        debt = _row(bs, "Total Debt")
        cash = _row(bs, "Cash Cash Equivalents And Short Term Investments", "Cash And Cash Equivalents")
        eq = _row(bs, "Stockholders Equity", "Common Stock Equity")
        ca, cl = _row(bs, "Current Assets"), _row(bs, "Current Liabilities")
        ttm = lambda v: sum(v[:4]) if len(v) >= 4 else None
        rev_t, ni_t = ttm(rev), ttm(ni)
        put("totalRevenue", rev_t)
        put("netIncomeToCommon", ni_t)
        put("ebitda", ttm(ebitda))
        put("freeCashflow", ttm(fcf))
        put("totalDebt", debt[0] if debt else None)
        put("totalCash", cash[0] if cash else None)
        if rev_t and opi and ttm(opi) is not None:
            put("operatingMargins", ttm(opi) / rev_t)
        if rev_t and ni_t is not None:
            put("profitMargins", ni_t / rev_t)
        if mcap and ni_t and ni_t > 0:
            put("trailingPE", mcap / ni_t)
        if mcap and eq and eq[0] > 0:
            put("priceToBook", mcap / eq[0])
        if ni_t is not None and eq and eq[0] > 0:
            put("returnOnEquity", ni_t / eq[0])
        if ca and cl and cl[0]:
            put("currentRatio", ca[0] / cl[0])
        if len(rev) >= 5 and rev[4] > 0:
            put("revenueGrowth", rev[0] / rev[4] - 1)
        if len(ni) >= 5 and ni[4] > 0:
            put("earningsGrowth", ni[0] / ni[4] - 1)
    except Exception:
        pass


def fetch_fundamentals(ticker: str) -> dict:
    t = yf.Ticker(ticker)
    try:
        info = t.info or {}
    except Exception:
        info = {}
    # Supplement missing keys with fast_info where available
    try:
        fi = t.fast_info
        if not info.get("marketCap") and hasattr(fi, "market_cap"):
            info["marketCap"] = fi.market_cap
        if not info.get("currentPrice") and hasattr(fi, "last_price"):
            info["currentPrice"] = fi.last_price
        if not info.get("fiftyTwoWeekHigh") and hasattr(fi, "year_high"):
            info["fiftyTwoWeekHigh"] = fi.year_high
        if not info.get("fiftyTwoWeekLow") and hasattr(fi, "year_low"):
            info["fiftyTwoWeekLow"] = fi.year_low
    except Exception:
        pass
    if not info.get("totalRevenue"):          # .info blocked or empty -> rebuild from statements
        _derive_info_from_statements(t, info)

    def _get(key, default=None):
        v = info.get(key, default)
        return v if v not in (None, "None", "N/A", float("inf"), float("-inf")) else default

    market_cap = _get("marketCap", 0)
    total_debt = _get("totalDebt", 0)
    total_cash = _get("totalCash", 0)
    total_revenue = _get("totalRevenue", 0)
    ebitda = _get("ebitda", 0)
    net_income = _get("netIncomeToCommon", 0)
    free_cash_flow = _get("freeCashflow", 0)
    operating_margins = _get("operatingMargins", None)
    profit_margins = _get("profitMargins", None)
    trailing_pe = _get("trailingPE", None)
    forward_pe = _get("forwardPE", None)
    pb_ratio = _get("priceToBook", None)
    ps_ratio = _get("priceToSalesTrailing12Months", None)
    beta = _get("beta", None)
    short_ratio = _get("shortRatio", None)
    revenue_growth = _get("revenueGrowth", None)
    earnings_growth = _get("earningsGrowth", None)
    current_ratio = _get("currentRatio", None)
    quick_ratio = _get("quickRatio", None)
    return_on_equity = _get("returnOnEquity", None)
    return_on_assets = _get("returnOnAssets", None)
    shares_outstanding = _get("sharesOutstanding", 0)
    float_shares = _get("floatShares", 0)
    inst_hold = _get("institutionalHoldingsPct", None) or _get("heldPercentInstitutions", None)
    dividend_yield = _get("dividendYield", 0)
    fifty_two_high = _get("fiftyTwoWeekHigh", None)
    fifty_two_low = _get("fiftyTwoWeekLow", None)
    current_price = _get("currentPrice", None) or _get("regularMarketPrice", None)
    business_summary = _get("longBusinessSummary", "No description available.")
    sector = _get("sector", "Materials")
    industry = _get("industry", "Silver")
    country = _get("country", "Unknown")
    employees = _get("fullTimeEmployees", None)
    analyst_target = _get("targetMeanPrice", None)
    recommendation = _get("recommendationKey", "—")

    net_debt = (total_debt or 0) - (total_cash or 0)
    debt_to_ebitda = (net_debt / ebitda) if (ebitda and ebitda != 0) else None
    debt_to_equity = _get("debtToEquity", None)

    return {
        "ticker": ticker,
        "market_cap": market_cap,
        "total_debt": total_debt,
        "total_cash": total_cash,
        "net_debt": net_debt,
        "total_revenue": total_revenue,
        "ebitda": ebitda,
        "net_income": net_income,
        "free_cash_flow": free_cash_flow,
        "operating_margins": operating_margins,
        "profit_margins": profit_margins,
        "trailing_pe": trailing_pe,
        "forward_pe": forward_pe,
        "pb_ratio": pb_ratio,
        "ps_ratio": ps_ratio,
        "beta": beta,
        "short_ratio": short_ratio,
        "revenue_growth": revenue_growth,
        "earnings_growth": earnings_growth,
        "current_ratio": current_ratio,
        "quick_ratio": quick_ratio,
        "return_on_equity": return_on_equity,
        "return_on_assets": return_on_assets,
        "debt_to_ebitda": debt_to_ebitda,
        "debt_to_equity": debt_to_equity,
        "shares_outstanding": shares_outstanding,
        "float_shares": float_shares,
        "inst_hold": inst_hold,
        "dividend_yield": dividend_yield,
        "fifty_two_high": fifty_two_high,
        "fifty_two_low": fifty_two_low,
        "current_price": current_price,
        "analyst_target": analyst_target,
        "recommendation": recommendation,
        "business_summary": business_summary,
        "sector": sector,
        "industry": industry,
        "country": country,
        "employees": employees,
    }


def fetch_macro() -> dict:
    results = {}
    tickers = {
        "silver": SILVER_SPOT,
        "gold":   GOLD_SPOT,
        "dxy":    DXY,
        "sp500":  SP500,
        "vix":    VIX,
        "tnx":    TNX,
        "sil":    SIL_ETF,
    }
    for key, t in tickers.items():
        try:
            df = fetch_ohlcv(t, "6mo", "1d")
            if not df.empty:
                results[key] = df
        except Exception:
            results[key] = pd.DataFrame()
    return results


def fetch_all_data(ticker: str) -> dict:
    return {
        "daily":  fetch_ohlcv(ticker, DAILY_PERIOD, "1d"),
        "weekly": fetch_ohlcv(ticker, WEEKLY_PERIOD, "1wk"),
        "hourly": fetch_ohlcv(ticker, HOURLY_PERIOD, "1h"),
        "fundamentals": fetch_fundamentals(ticker),
    }
