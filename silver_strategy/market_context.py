"""
Non-technical / macro factors that affect silver prices and miner profitability.

Silver's dual nature - monetary metal + industrial commodity - means it is driven by:
  1. USD strength (DXY)          → inverse correlation with precious metals
  2. Real interest rates          → opportunity cost of holding non-yielding metal
  3. Gold price / Gold-Silver ratio → silver tends to follow gold but with more volatility
  4. Inflation expectations       → silver as inflation hedge (monetary demand)
  5. Industrial / Green demand    → solar panels, EVs, electronics (~60% of silver demand)
  6. Equity risk sentiment        → VIX, S&P trend (risk-on = bullish silver miners)
  7. Silver supply dynamics       → mining output often lags price by 18–24 months
  8. Miner leverage              → miners offer 2-4x leverage to silver spot moves
"""

from __future__ import annotations
import numpy as np
import pandas as pd


def _last(df: pd.DataFrame) -> float | None:
    if df is None or df.empty:
        return None
    return float(df["Close"].iloc[-1])


def _change_pct(df: pd.DataFrame, days: int = 20) -> float | None:
    if df is None or len(df) < days + 1:
        return None
    arr = df["Close"].values
    return float((arr[-1] - arr[-(days + 1)]) / arr[-(days + 1)] * 100)


def _above_sma(df: pd.DataFrame, period: int = 50) -> bool | None:
    if df is None or len(df) < period:
        return None
    c = df["Close"]
    return bool(c.iloc[-1] > c.rolling(period).mean().iloc[-1])


def _trend(change: float | None, thres_bull: float = 2.0, thres_bear: float = -2.0) -> str:
    if change is None:
        return "Unknown"
    if change > thres_bull:
        return "Bullish"
    if change < thres_bear:
        return "Bearish"
    return "Neutral"


def analyze_macro(macro: dict) -> dict:
    """
    Scores macro environment for silver miners.
    Returns score (-4 to +4) plus contextual notes.
    """
    score    = 0
    bullish  = []
    bearish  = []
    notes    = []

    # ── Silver spot ──────────────────────────────────────────────────────────
    ag_df  = macro.get("silver")
    ag_px  = _last(ag_df)
    ag_1m  = _change_pct(ag_df, 20)
    ag_3m  = _change_pct(ag_df, 60)

    if ag_px:
        notes.append(f"Silver spot ${ag_px:.2f}/oz")
    if ag_1m is not None:
        if ag_1m > 5:
            score += 2; bullish.append(f"Silver +{ag_1m:.1f}% (1-month, strong momentum)")
        elif ag_1m > 0:
            score += 1; bullish.append(f"Silver +{ag_1m:.1f}% (1-month)")
        elif ag_1m < -5:
            score -= 2; bearish.append(f"Silver {ag_1m:.1f}% (1-month, selling pressure)")
        elif ag_1m < 0:
            score -= 1; bearish.append(f"Silver {ag_1m:.1f}% (1-month)")

    # ── Gold / Silver ratio ──────────────────────────────────────────────────
    gold_df = macro.get("gold")
    gold_px = _last(gold_df)
    if ag_px and gold_px:
        gs_ratio = gold_px / ag_px
        notes.append(f"Gold/Silver ratio {gs_ratio:.1f}x")
        if gs_ratio > 85:
            score += 1
            bullish.append(f"Gold/Silver ratio {gs_ratio:.0f}x - silver historically cheap vs gold (mean-reversion potential)")
        elif gs_ratio < 60:
            score -= 1
            bearish.append(f"Gold/Silver ratio {gs_ratio:.0f}x - silver relatively expensive vs gold")
        else:
            notes.append(f"Gold/Silver ratio neutral ({gs_ratio:.0f}x, normal range 65–80)")

    # ── DXY ──────────────────────────────────────────────────────────────────
    dxy_df  = macro.get("dxy")
    dxy_1m  = _change_pct(dxy_df, 20)
    dxy_sma = _above_sma(dxy_df, 50)
    dxy_px  = _last(dxy_df)
    if dxy_px:
        notes.append(f"DXY {dxy_px:.2f}")
    if dxy_1m is not None:
        if dxy_1m < -1.5:
            score += 1; bullish.append(f"DXY weakening ({dxy_1m:.1f}%) - tailwind for precious metals")
        elif dxy_1m > 1.5:
            score -= 1; bearish.append(f"DXY strengthening (+{dxy_1m:.1f}%) - headwind for precious metals")

    # ── 10Y Treasury yield (TNX) ─────────────────────────────────────────────
    tnx_df = macro.get("tnx")
    tnx_px = _last(tnx_df)
    tnx_1m = _change_pct(tnx_df, 20)
    if tnx_px:
        notes.append(f"10Y Treasury {tnx_px:.2f}%")
    if tnx_px is not None:
        if tnx_px > 5.0:
            score -= 1; bearish.append(f"10Y yield {tnx_px:.2f}% - high opportunity cost vs non-yielding silver")
        elif tnx_px < 3.5:
            score += 1; bullish.append(f"10Y yield {tnx_px:.2f}% - low real rates supportive of silver")
    if tnx_1m is not None and tnx_1m < -10:
        score += 1; bullish.append("Rates falling - positive for precious metals")
    elif tnx_1m is not None and tnx_1m > 10:
        score -= 1; bearish.append("Rates rising - headwind for precious metals")

    # ── VIX / Risk sentiment ─────────────────────────────────────────────────
    vix_df = macro.get("vix")
    vix_px = _last(vix_df)
    if vix_px:
        notes.append(f"VIX {vix_px:.1f}")
    if vix_px is not None:
        if vix_px > 30:
            # High VIX: flight to gold, but silver miners sell off with equities
            score -= 1; bearish.append(f"VIX {vix_px:.0f} - elevated fear; miner equities vulnerable")
        elif vix_px < 15:
            score += 1; bullish.append(f"VIX {vix_px:.0f} - low volatility; risk appetite supports mining equities")

    # ── S&P 500 trend ────────────────────────────────────────────────────────
    sp_df  = macro.get("sp500")
    sp_1m  = _change_pct(sp_df, 20)
    sp_sma = _above_sma(sp_df, 50)
    if sp_1m is not None:
        if sp_1m > 3:
            score += 1; bullish.append(f"S&P 500 +{sp_1m:.1f}% - risk-on environment benefits miners")
        elif sp_1m < -5:
            score -= 1; bearish.append(f"S&P 500 {sp_1m:.1f}% - risk-off may drag mining equities")

    # ── SIL ETF (silver miners sector) ──────────────────────────────────────
    sil_df  = macro.get("sil")
    sil_1m  = _change_pct(sil_df, 20)
    sil_sma = _above_sma(sil_df, 50)
    if sil_1m is not None:
        notes.append(f"SIL ETF (sector): {sil_1m:+.1f}% (1-month)")
    if sil_sma is True:
        score += 1; bullish.append("Silver miners sector (SIL) above 50-day MA - sector momentum positive")
    elif sil_sma is False:
        score -= 1; bearish.append("Silver miners sector (SIL) below 50-day MA - sector under pressure")

    # ── Non-technical structural factors ─────────────────────────────────────
    # These are qualitative; we include as notes since live data isn't readily available:
    structural = [
        "Solar panel demand: ~14% of global silver demand (growing ~15% YoY as solar capacity expands)",
        "EV sector: silver used in charging infrastructure and EV electronics",
        "Industrial demand ~60% of total silver use - GDP growth is a key driver",
        "Global silver deficit expected to continue (Silver Institute data) - supply inelastic",
        "Miner AISC (All-In Sustaining Cost) typically $12-18/oz for primary silver miners",
        "Silver miners provide 2-4x operational leverage to silver spot price moves",
    ]
    notes.extend(structural)

    final_score = max(-4, min(4, score))
    return {
        "score":    final_score,
        "bullish":  bullish,
        "bearish":  bearish,
        "notes":    notes,
        "ag_price": ag_px,
        "ag_1m":    ag_1m,
        "ag_3m":    ag_3m,
        "gold_px":  gold_px,
        "gs_ratio": (gold_px / ag_px) if (ag_px and gold_px) else None,
        "dxy_px":   dxy_px,
        "dxy_1m":   dxy_1m,
        "tnx_px":   tnx_px,
        "vix_px":   vix_px,
        "sp_1m":    sp_1m,
        "sil_1m":   sil_1m,
    }
