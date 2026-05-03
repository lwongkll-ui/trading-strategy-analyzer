"""
Chart generation for silver miner stocks.

Layout (per stock, daily timeframe):
    Panel 0  - Candlestick + SMA20/50/200 + EMA9/21 + Bollinger Bands
                Buy (^) / Sell (v) signal markers
    Panel 1  - Volume bars + 20-day avg volume line
    Panel 2  - MACD (line + signal + histogram)
    Panel 3  - Fast STC (10,23,3) and Slow STC (23,50,5) on same panel
    Panel 4  - RSI with 30/70 bands
"""

from __future__ import annotations
import os
import warnings
import numpy as np
import pandas as pd
import mplfinance as mpf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

warnings.filterwarnings("ignore")


STYLE = mpf.make_mpf_style(
    base_mpf_style="nightclouds",
    marketcolors=mpf.make_marketcolors(
        up="#26a69a", down="#ef5350",
        wick={"up": "#26a69a", "down": "#ef5350"},
        edge={"up": "#26a69a", "down": "#ef5350"},
        volume={"up": "#26a69a44", "down": "#ef535044"},
    ),
    figcolor="#131722",
    facecolor="#131722",
    edgecolor="#2a2e39",
    gridcolor="#2a2e39",
    gridstyle="--",
    gridaxis="both",
    y_on_right=True,
    rc={
        "axes.labelcolor":  "#9598a1",
        "axes.titlecolor":  "#d1d4dc",
        "xtick.color":      "#9598a1",
        "ytick.color":      "#9598a1",
        "font.size":        9,
    },
)

# Colours
C_SMA20  = "#29b6f6"
C_SMA50  = "#ffa726"
C_SMA200 = "#ef5350"
C_EMA9   = "#ce93d8"
C_EMA21  = "#80cbc4"
C_BB     = "#37474f"
C_MACD   = "#29b6f6"
C_SIG    = "#ef5350"
C_HIST_P = "#26a69a"
C_HIST_N = "#ef5350"
C_STC_F  = "#00e5ff"
C_STC_S  = "#ffab40"
C_RSI    = "#ab47bc"
C_BUY    = "#00e676"
C_SELL   = "#ff1744"


def _nan_series(index) -> pd.Series:
    return pd.Series(np.nan, index=index)


def _marker_series(df: pd.DataFrame, mask: pd.Series, price_col: str, offset_frac: float) -> pd.Series:
    s = _nan_series(df.index)
    s[mask] = df.loc[mask, price_col] * (1 + offset_frac)
    return s


def plot_stock(
    ticker: str,
    company: str,
    df: pd.DataFrame,
    output_dir: str,
) -> str:
    """
    Render and save the chart for one stock.
    df must already have all indicator columns added by indicators.compute_all().
    Returns the saved file path.
    """
    if len(df) < 60:
        return ""

    # Use last 400 trading days for readability
    df = df.tail(400).copy()

    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, f"{ticker}.png")

    buy_mask  = df["buy_signal"].fillna(False)
    sell_mask = df["sell_signal"].fillna(False)

    buy_markers  = _marker_series(df, buy_mask,  "Low",  -0.04)
    sell_markers = _marker_series(df, sell_mask, "High", +0.04)

    # Histogram colours
    hist_colors = [C_HIST_P if v >= 0 else C_HIST_N
                   for v in df["macd_hist"].fillna(0)]

    addplots = [
        # Price overlays
        mpf.make_addplot(df["sma20"],  color=C_SMA20,  width=0.9,  panel=0),
        mpf.make_addplot(df["sma50"],  color=C_SMA50,  width=1.1,  panel=0),
        mpf.make_addplot(df["sma200"], color=C_SMA200, width=1.5,  panel=0),
        mpf.make_addplot(df["ema9"],   color=C_EMA9,   width=0.8,  panel=0, linestyle="dashed"),
        mpf.make_addplot(df["ema21"],  color=C_EMA21,  width=0.8,  panel=0, linestyle="dashed"),
        mpf.make_addplot(df["bb_upper"], color=C_BB,   width=0.6,  panel=0, linestyle="dotted"),
        mpf.make_addplot(df["bb_lower"], color=C_BB,   width=0.6,  panel=0, linestyle="dotted"),

        # Buy / Sell markers on price panel
        mpf.make_addplot(buy_markers,  scatter=True, markersize=80,
                         marker="^", color=C_BUY,  panel=0),
        mpf.make_addplot(sell_markers, scatter=True, markersize=80,
                         marker="v", color=C_SELL, panel=0),

        # MACD (panel 2)
        mpf.make_addplot(df["macd"],      color=C_MACD, width=1.0, panel=2),
        mpf.make_addplot(df["macd_sig"],  color=C_SIG,  width=0.8, panel=2),
        mpf.make_addplot(df["macd_hist"], type="bar", color=hist_colors, panel=2, alpha=0.7),

        # STC (panel 3) - fast + slow
        mpf.make_addplot(df["stc_fast"], color=C_STC_F, width=1.2, panel=3),
        mpf.make_addplot(df["stc_slow"], color=C_STC_S, width=1.0, panel=3, linestyle="dashed"),

        # RSI (panel 4)
        mpf.make_addplot(df["rsi"], color=C_RSI, width=1.0, panel=4),
    ]

    fig, axes = mpf.plot(
        df,
        type="candle",
        style=STYLE,
        addplot=addplots,
        volume=True,
        volume_panel=1,
        panel_ratios=(4, 1, 1.5, 1.5, 1.5),
        figsize=(18, 13),
        title=f"\n{ticker}  -  {company}  |  Daily Chart",
        returnfig=True,
        warn_too_much_data=9999,
        tight_layout=False,
    )

    fig.patch.set_facecolor("#131722")

    # Axis labels
    panel_labels = {
        0: "Price & MAs",
        1: "Volume",
        2: "MACD (12,26,9)",
        3: "STC Fast (10,23,3)  /  Slow (23,50,5)",
        4: "RSI (14)",
    }
    for i, ax in enumerate(axes):
        if i in panel_labels:
            ax.set_ylabel(panel_labels[i], color="#9598a1", fontsize=8)
        ax.tick_params(colors="#9598a1")
        for spine in ax.spines.values():
            spine.set_edgecolor("#2a2e39")

    # STC overbought / oversold zones
    ax_stc = axes[3]
    ax_stc.axhline(25, color=C_BUY,  linewidth=0.7, linestyle="--", alpha=0.6)
    ax_stc.axhline(75, color=C_SELL, linewidth=0.7, linestyle="--", alpha=0.6)
    ax_stc.axhspan(0,  25, alpha=0.08, color=C_BUY)
    ax_stc.axhspan(75, 100, alpha=0.08, color=C_SELL)
    ax_stc.set_ylim(0, 100)

    # RSI bands
    ax_rsi = axes[4]
    ax_rsi.axhline(30, color=C_BUY,  linewidth=0.7, linestyle="--", alpha=0.6)
    ax_rsi.axhline(70, color=C_SELL, linewidth=0.7, linestyle="--", alpha=0.6)
    ax_rsi.axhspan(0,  30, alpha=0.08, color=C_BUY)
    ax_rsi.axhspan(70, 100, alpha=0.08, color=C_SELL)
    ax_rsi.set_ylim(0, 100)

    # MACD zero line
    axes[2].axhline(0, color="#555", linewidth=0.6, linestyle="--")

    # Legend - price panel
    legend_items = [
        mpatches.Patch(color=C_SMA20,  label="SMA 20"),
        mpatches.Patch(color=C_SMA50,  label="SMA 50"),
        mpatches.Patch(color=C_SMA200, label="SMA 200"),
        mpatches.Patch(color=C_EMA9,   label="EMA 9"),
        mpatches.Patch(color=C_EMA21,  label="EMA 21"),
        mpatches.Patch(color=C_BB,     label="Bollinger Bands"),
        mpatches.Patch(color=C_BUY,    label="Buy Signal ^"),
        mpatches.Patch(color=C_SELL,   label="Sell Signal v"),
    ]
    axes[0].legend(handles=legend_items, loc="upper left",
                   fontsize=7, facecolor="#1e222d",
                   edgecolor="#2a2e39", labelcolor="#d1d4dc",
                   ncol=4, framealpha=0.8)

    # STC legend
    stc_items = [
        mpatches.Patch(color=C_STC_F, label="STC Fast"),
        mpatches.Patch(color=C_STC_S, label="STC Slow"),
    ]
    axes[3].legend(handles=stc_items, loc="upper left",
                   fontsize=7, facecolor="#1e222d",
                   edgecolor="#2a2e39", labelcolor="#d1d4dc")

    plt.subplots_adjust(left=0.04, right=0.94, top=0.95, bottom=0.05, hspace=0.05)
    fig.savefig(out_path, dpi=130, bbox_inches="tight", facecolor="#131722")
    plt.close(fig)
    return out_path


def plot_weekly_overview(
    ticker: str,
    company: str,
    df_weekly: pd.DataFrame,
    output_dir: str,
) -> str:
    """Secondary weekly chart for long-term trend context."""
    if df_weekly is None or len(df_weekly) < 50:
        return ""

    df = df_weekly.tail(260).copy()  # ~5 years
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, f"{ticker}_weekly.png")

    hist_colors = [C_HIST_P if v >= 0 else C_HIST_N
                   for v in df["macd_hist"].fillna(0)]

    addplots = [
        mpf.make_addplot(df["sma50"],  color=C_SMA50,  width=1.2, panel=0),
        mpf.make_addplot(df["sma200"], color=C_SMA200, width=1.5, panel=0),
        mpf.make_addplot(df["bb_upper"], color=C_BB,   width=0.6, panel=0, linestyle="dotted"),
        mpf.make_addplot(df["bb_lower"], color=C_BB,   width=0.6, panel=0, linestyle="dotted"),
        mpf.make_addplot(df["macd"],     color=C_MACD, width=1.0, panel=2),
        mpf.make_addplot(df["macd_sig"], color=C_SIG,  width=0.8, panel=2),
        mpf.make_addplot(df["macd_hist"], type="bar", color=hist_colors, panel=2, alpha=0.7),
        mpf.make_addplot(df["stc_slow"], color=C_STC_S, width=1.2, panel=3),
        mpf.make_addplot(df["rsi"],      color=C_RSI,   width=1.0, panel=4),
    ]

    fig, axes = mpf.plot(
        df, type="candle", style=STYLE,
        addplot=addplots, volume=True, volume_panel=1,
        panel_ratios=(4, 1, 1.5, 1.5, 1.5),
        figsize=(18, 13),
        title=f"\n{ticker}  -  {company}  |  Weekly Chart (5-Year Trend)",
        returnfig=True, warn_too_much_data=9999,
    )

    fig.patch.set_facecolor("#131722")
    axes[3].axhline(25, color=C_BUY,  linewidth=0.7, linestyle="--", alpha=0.6)
    axes[3].axhline(75, color=C_SELL, linewidth=0.7, linestyle="--", alpha=0.6)
    axes[3].set_ylim(0, 100)
    axes[4].axhline(30, color=C_BUY,  linewidth=0.7, linestyle="--", alpha=0.6)
    axes[4].axhline(70, color=C_SELL, linewidth=0.7, linestyle="--", alpha=0.6)
    axes[4].set_ylim(0, 100)
    axes[2].axhline(0, color="#555", linewidth=0.6, linestyle="--")

    plt.subplots_adjust(left=0.04, right=0.94, top=0.95, bottom=0.05, hspace=0.05)
    fig.savefig(out_path, dpi=130, bbox_inches="tight", facecolor="#131722")
    plt.close(fig)
    return out_path
