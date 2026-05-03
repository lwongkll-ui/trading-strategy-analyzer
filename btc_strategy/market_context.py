"""Macro & sentiment context interpreter."""

from __future__ import annotations
from fetcher import fetch_macro, fetch_fear_greed, fetch_funding_rate


def interpret_dxy(change_pct: float | None) -> tuple[str, int]:
    """
    Returns (narrative, score_impact).
    Positive score = bullish for BTC, negative = bearish.
    """
    if change_pct is None:
        return "DXY data unavailable", 0
    if change_pct > 0.5:
        return f"DXY surging +{change_pct}% → headwind for BTC (risk-off)", -2
    if change_pct > 0.2:
        return f"DXY rising +{change_pct}% → mild headwind for BTC", -1
    if change_pct < -0.5:
        return f"DXY falling {change_pct}% → tailwind for BTC (risk-on)", +2
    if change_pct < -0.2:
        return f"DXY softening {change_pct}% → mild tailwind for BTC", +1
    return f"DXY flat ({change_pct}%) → neutral for BTC", 0


def interpret_vix(price: float | None) -> tuple[str, int]:
    if price is None:
        return "VIX data unavailable", 0
    if price > 35:
        return f"VIX {price:.1f} — extreme fear / capitulation zone → contrarian bullish", +1
    if price > 25:
        return f"VIX {price:.1f} — elevated fear → caution, risk-off environment", -1
    if price > 18:
        return f"VIX {price:.1f} — moderate uncertainty → watch closely", 0
    return f"VIX {price:.1f} — complacency / low volatility → neutral-bullish", +1


def interpret_tnx(price: float | None, change_pct: float | None) -> tuple[str, int]:
    if price is None:
        return "10Y yield data unavailable", 0
    if price > 5.0:
        return f"10Y yield {price:.2f}% — very restrictive FED → bearish for risk assets", -2
    if price > 4.5:
        return f"10Y yield {price:.2f}% — restrictive territory → mild bearish", -1
    if price < 3.5:
        return f"10Y yield {price:.2f}% — low rates → bullish for risk assets", +2
    return f"10Y yield {price:.2f}% — neutral territory", 0


def interpret_fear_greed(fg: dict) -> tuple[str, int]:
    v = fg.get("value")
    label = fg.get("label", "")
    if v is None:
        return "Fear & Greed unavailable", 0
    if v <= 10:
        return f"Fear & Greed {v} ({label}) — extreme fear → strong contrarian BUY signal", +3
    if v <= 25:
        return f"Fear & Greed {v} ({label}) — fear zone → accumulation opportunity", +2
    if v <= 45:
        return f"Fear & Greed {v} ({label}) — cautious → slight bearish bias", -1
    if v <= 55:
        return f"Fear & Greed {v} ({label}) — neutral", 0
    if v <= 75:
        return f"Fear & Greed {v} ({label}) — greed building → take partial profits", -1
    return f"Fear & Greed {v} ({label}) — extreme greed → reduce exposure / near top zone", -3


def interpret_funding_rate(fr: dict) -> tuple[str, int]:
    rate = fr.get("rate_pct")
    if rate is None:
        return "Funding rate unavailable", 0
    if rate > 0.1:
        return f"Funding +{rate}% — longs heavily leveraged → short squeeze risk, bearish bias", -2
    if rate > 0.05:
        return f"Funding +{rate}% — mild long bias → caution at highs", -1
    if rate < -0.05:
        return f"Funding {rate}% — shorts dominant → potential short squeeze, bullish bias", +2
    if rate < -0.02:
        return f"Funding {rate}% — slight short bias → mild bullish", +1
    return f"Funding {rate}% — balanced → neutral", 0


def get_full_context() -> dict:
    macro = fetch_macro()
    fg    = fetch_fear_greed()
    fr    = fetch_funding_rate()

    dxy_msg,  dxy_score  = interpret_dxy(macro["DXY"].get("change"))
    vix_msg,  vix_score  = interpret_vix(macro["VIX"].get("price"))
    tnx_msg,  tnx_score  = interpret_tnx(macro["TNX"].get("price"), macro["TNX"].get("change"))
    fg_msg,   fg_score   = interpret_fear_greed(fg)
    fr_msg,   fr_score   = interpret_funding_rate(fr)

    sp500_chg = macro["SP500"].get("change", 0) or 0
    sp500_score = 1 if sp500_chg > 0.5 else (-1 if sp500_chg < -0.5 else 0)
    sp500_msg = (
        f"S&P500 {'+' if sp500_chg >= 0 else ''}{sp500_chg:.2f}% — "
        + ("risk-on, BTC tailwind" if sp500_chg > 0.5
           else "risk-off, BTC headwind" if sp500_chg < -0.5
           else "neutral")
    )

    macro_score = dxy_score + vix_score + tnx_score + sp500_score
    sentiment_score = fg_score + fr_score

    return {
        "macro":    macro,
        "fg":       fg,
        "fr":       fr,
        "messages": {
            "DXY":    dxy_msg,
            "VIX":    vix_msg,
            "TNX":    tnx_msg,
            "SP500":  sp500_msg,
            "FG":     fg_msg,
            "FR":     fr_msg,
        },
        "macro_score":     macro_score,
        "sentiment_score": sentiment_score,
        "total_context_score": macro_score + sentiment_score,
    }
