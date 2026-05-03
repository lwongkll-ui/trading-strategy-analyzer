"""
Fundamental analysis and scoring for silver miner stocks.
Scores range from -4 to +4 based on quality, value, and balance-sheet health.
"""

from __future__ import annotations


def _fmt_m(v) -> str:
    if v is None:
        return "N/A"
    if abs(v) >= 1e9:
        return f"${v/1e9:.2f}B"
    if abs(v) >= 1e6:
        return f"${v/1e6:.1f}M"
    return f"${v:.0f}"


def _pct(v) -> str:
    return f"{v*100:.1f}%" if v is not None else "N/A"


def _fmt(v, decimals: int = 2, suffix: str = "") -> str:
    return f"{v:.{decimals}f}{suffix}" if v is not None else "N/A"


def score_fundamentals(info: dict) -> tuple[int, list[str], list[str]]:
    """
    Returns (score, positives, negatives).
    Score: -4 (worst) to +4 (best).
    """
    score = 0
    positives: list[str] = []
    negatives: list[str] = []

    # -- Valuation -----------------------------------------------------------
    pe = info.get("trailing_pe")
    fpe = info.get("forward_pe")
    pb = info.get("pb_ratio")

    if pe is not None:
        if pe < 20:
            score += 1; positives.append(f"Reasonable P/E ({pe:.1f}x)")
        elif pe > 50:
            score -= 1; negatives.append(f"Expensive P/E ({pe:.1f}x)")

    if fpe is not None and pe is not None:
        if fpe < pe * 0.85:
            score += 1; positives.append(f"Earnings expected to grow (fwd P/E {fpe:.1f}x)")
        elif fpe > pe * 1.15:
            score -= 1; negatives.append(f"Earnings expected to shrink (fwd P/E {fpe:.1f}x)")

    if pb is not None:
        if pb < 1.5:
            score += 1; positives.append(f"Attractive P/B ({pb:.2f}x)")
        elif pb > 5:
            score -= 1; negatives.append(f"High P/B ({pb:.2f}x)")

    # -- Balance sheet --------------------------------------------------------
    net_debt = info.get("net_debt", 0) or 0
    ebitda   = info.get("ebitda")
    debt_ebitda = info.get("debt_to_ebitda")
    current_r   = info.get("current_ratio")
    quick_r     = info.get("quick_ratio")

    if debt_ebitda is not None:
        if debt_ebitda < 1.0:
            score += 1; positives.append(f"Low leverage (Debt/EBITDA {debt_ebitda:.1f}x)")
        elif debt_ebitda > 3.0:
            score -= 1; negatives.append(f"High leverage (Debt/EBITDA {debt_ebitda:.1f}x)")
    elif net_debt < 0:
        score += 1; positives.append("Net cash position")
    elif net_debt > 5e8:
        score -= 1; negatives.append("Significant net debt")

    if current_r is not None:
        if current_r > 2.0:
            score += 1; positives.append(f"Strong liquidity (Current Ratio {current_r:.1f}x)")
        elif current_r < 1.0:
            score -= 1; negatives.append(f"Liquidity concern (Current Ratio {current_r:.1f}x)")

    # -- Profitability --------------------------------------------------------
    op_margin = info.get("operating_margins")
    prof_margin = info.get("profit_margins")
    roe = info.get("return_on_equity")
    fcf = info.get("free_cash_flow")

    if op_margin is not None:
        if op_margin > 0.20:
            score += 1; positives.append(f"High operating margin ({op_margin*100:.0f}%)")
        elif op_margin < 0:
            score -= 1; negatives.append(f"Operating at a loss (margin {op_margin*100:.0f}%)")

    if roe is not None:
        if roe > 0.15:
            score += 1; positives.append(f"Good ROE ({roe*100:.0f}%)")
        elif roe < 0:
            score -= 1; negatives.append(f"Negative ROE ({roe*100:.0f}%)")

    if fcf is not None:
        if fcf > 0:
            positives.append("Positive free cash flow")
        else:
            negatives.append("Negative free cash flow (cash burn)")

    # -- Growth --------------------------------------------------------------
    rev_growth = info.get("revenue_growth")
    earn_growth = info.get("earnings_growth")

    if rev_growth is not None:
        if rev_growth > 0.10:
            score += 1; positives.append(f"Revenue growing +{rev_growth*100:.0f}% YoY")
        elif rev_growth < -0.15:
            score -= 1; negatives.append(f"Revenue declining {rev_growth*100:.0f}% YoY")

    if earn_growth is not None and earn_growth > 0.20:
        score += 1; positives.append(f"Earnings growing +{earn_growth*100:.0f}% YoY")

    return max(-4, min(4, score)), positives, negatives


def fundamental_summary(info: dict) -> dict:
    """Human-readable summary dict for dashboard display."""
    score, pos, neg = score_fundamentals(info)

    price = info.get("current_price")
    hi52  = info.get("fifty_two_high")
    lo52  = info.get("fifty_two_low")

    pct_from_high = None
    pct_from_low  = None
    if price and hi52:
        pct_from_high = (price - hi52) / hi52 * 100
    if price and lo52:
        pct_from_low  = (price - lo52) / lo52 * 100

    return {
        "score":          score,
        "positives":      pos,
        "negatives":      neg,
        "market_cap":     _fmt_m(info.get("market_cap")),
        "trailing_pe":    _fmt(info.get("trailing_pe"), 1, "x"),
        "forward_pe":     _fmt(info.get("forward_pe"),  1, "x"),
        "pb_ratio":       _fmt(info.get("pb_ratio"),    2, "x"),
        "net_debt":       _fmt_m(info.get("net_debt")),
        "debt_ebitda":    _fmt(info.get("debt_to_ebitda"), 1, "x"),
        "current_ratio":  _fmt(info.get("current_ratio"),  1, "x"),
        "op_margin":      _pct(info.get("operating_margins")),
        "prof_margin":    _pct(info.get("profit_margins")),
        "roe":            _pct(info.get("return_on_equity")),
        "rev_growth":     _pct(info.get("revenue_growth")),
        "earn_growth":    _pct(info.get("earnings_growth")),
        "fcf":            _fmt_m(info.get("free_cash_flow")),
        "short_ratio":    _fmt(info.get("short_ratio"), 1, "d"),
        "beta":           _fmt(info.get("beta"), 2),
        "dividend_yield": _pct(info.get("dividend_yield")),
        "analyst_target": _fmt(info.get("analyst_target"), 2, ""),
        "recommendation": (info.get("recommendation") or "-").upper(),
        "52w_high":       _fmt(hi52, 2),
        "52w_low":        _fmt(lo52, 2),
        "pct_from_high":  f"{pct_from_high:.1f}%" if pct_from_high is not None else "N/A",
        "pct_from_low":   f"+{pct_from_low:.1f}%" if pct_from_low is not None else "N/A",
        "inst_hold":      _pct(info.get("inst_hold")),
        "description":    (info.get("business_summary") or "")[:300],
        "country":        info.get("country", "Unknown"),
        "employees":      f"{info.get('employees'):,}" if info.get("employees") else "N/A",
    }
