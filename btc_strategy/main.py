"""
BTC Trading Strategy Analyzer — main entry point.

Usage:
    python main.py          # full analysis
    python main.py --chart  # save price chart to btc_chart.png
"""

import sys
import io
import warnings
warnings.filterwarnings("ignore")

# Force UTF-8 output on Windows (avoids cp1252 UnicodeEncodeError)
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich import box
from rich.text import Text

from fetcher import fetch_btc_daily, fetch_btc_weekly
from indicators import add_all_indicators, detect_candlestick_pattern, detect_rsi_divergence, key_levels
from market_context import get_full_context
from strategy import generate_signal
from swing_trader import scan_setups, ACCOUNT_SIZE_USD, RISK_PER_TRADE

console = Console(legacy_windows=False)


# ── Color helpers ──────────────────────────────────────────────────────────────

def score_color(score: int) -> str:
    if score >= 2:  return "bright_green"
    if score == 1:  return "green"
    if score == 0:  return "yellow"
    if score == -1: return "orange3"
    return "bright_red"


def pct_color(v: float) -> str:
    return "bright_green" if v > 0 else ("bright_red" if v < 0 else "white")


def regime_style(regime: str) -> str:
    return "bold bright_green on dark_green" if regime == "BULL" else "bold bright_red on dark_red"


# ── Sections ───────────────────────────────────────────────────────────────────

def print_header(sig: dict):
    regime = sig["regime"]
    close  = sig["close"]
    sma200 = sig["sma200"]
    dist   = sig["dist_200_pct"]
    sign   = "+" if dist >= 0 else ""

    title = Text(justify="center")
    title.append("  BTC/USD TRADING DASHBOARD  ", style=regime_style(regime))
    title.append(f"\n${close:,.0f}  |  200 SMA: ${sma200:,.0f}  |  Distance: {sign}{dist:.1f}%")

    console.print(Panel(title, box=box.DOUBLE, padding=(0, 2)))


def print_market_regime(sig: dict, df):
    regime   = sig["regime"]
    sma50    = float(df["sma50"].iloc[-1])
    ema20    = float(df["ema20"].iloc[-1])
    dist     = sig["dist_200_pct"]

    table = Table(title="Market Regime", box=box.SIMPLE_HEAD, show_header=True)
    table.add_column("Indicator", style="bold cyan", width=18)
    table.add_column("Value", justify="right", width=14)
    table.add_column("Signal", width=30)

    regime_color = "bright_green" if regime == "BULL" else "bright_red"
    table.add_row("Regime", f"[{regime_color}]{regime}[/{regime_color}]",
                  "Above 200 SMA" if regime == "BULL" else "Below 200 SMA")
    table.add_row("Price", f"${sig['close']:,.0f}", "")
    table.add_row("200 SMA", f"${sig['sma200']:,.0f}",
                  f"{'✓ Support' if regime == 'BULL' else '✗ Resistance'}")
    table.add_row("50 SMA",  f"${sma50:,.0f}",
                  "Above ✓" if sig["close"] > sma50 else "Below ✗")
    table.add_row("20 EMA",  f"${ema20:,.0f}",
                  "Above ✓" if sig["close"] > ema20 else "Below ✗")
    sign = "+" if dist >= 0 else ""
    table.add_row("Dist 200 SMA", f"{sign}{dist:.1f}%",
                  "[yellow]Overextended ⚠[/yellow]" if abs(dist) > 30 else "Normal range")
    console.print(table)


def print_technical(df):
    rsi       = float(df["rsi"].iloc[-1])
    macd      = float(df["macd"].iloc[-1])
    macd_sig  = float(df["macd_signal"].iloc[-1])
    macd_hist = float(df["macd_hist"].iloc[-1])
    stoch_k   = float(df["stoch_k"].iloc[-1])
    bb_upper  = float(df["bb_upper"].iloc[-1])
    bb_mid    = float(df["bb_mid"].iloc[-1])
    bb_lower  = float(df["bb_lower"].iloc[-1])
    bb_width  = float(df["bb_width"].iloc[-1])
    atr       = float(df["atr"].iloc[-1])
    vol_ratio = float(df["vol_ratio"].iloc[-1])
    close     = float(df["close"].iloc[-1])

    table = Table(title="Technical Indicators", box=box.SIMPLE_HEAD)
    table.add_column("Indicator",  style="bold cyan", width=18)
    table.add_column("Value",      justify="right", width=14)
    table.add_column("Reading",    width=35)

    rsi_color = "bright_green" if rsi < 40 else ("bright_red" if rsi > 70 else "yellow")
    table.add_row("RSI (14)", f"[{rsi_color}]{rsi:.1f}[/{rsi_color}]",
                  "Oversold" if rsi < 30 else "Overbought" if rsi > 70 else
                  "Neutral" if rsi > 45 else "Weak momentum")

    macd_cross = "Bull Cross ✓" if float(df["macd_bull_cross"].iloc[-1]) else \
                 "Bear Cross ✗" if float(df["macd_bear_cross"].iloc[-1]) else \
                 ("Positive" if macd > macd_sig else "Negative")
    table.add_row("MACD", f"{macd:+.0f}", macd_cross)
    table.add_row("MACD Hist", f"{macd_hist:+.0f}",
                  "Expanding ↑" if macd_hist > float(df["macd_hist"].iloc[-2]) else "Contracting ↓")

    sk_color = "bright_green" if stoch_k < 20 else ("bright_red" if stoch_k > 80 else "white")
    table.add_row("StochRSI K", f"[{sk_color}]{stoch_k:.1f}[/{sk_color}]",
                  "Oversold" if stoch_k < 20 else "Overbought" if stoch_k > 80 else "Neutral")

    bb_pos = (close - bb_lower) / (bb_upper - bb_lower) * 100 if bb_upper != bb_lower else 50
    table.add_row("BB Position", f"{bb_pos:.0f}%",
                  f"Upper: ${bb_upper:,.0f}  Lower: ${bb_lower:,.0f}")
    table.add_row("BB Width", f"{bb_width:.1f}%",
                  "Tight — breakout likely" if bb_width < 10 else "Wide — high volatility")

    vol_color = "bright_green" if vol_ratio > 1.5 else ("yellow" if vol_ratio > 1.0 else "white")
    table.add_row("Volume Ratio", f"[{vol_color}]{vol_ratio:.2f}x[/{vol_color}]",
                  "High volume" if vol_ratio > 1.5 else "Below average" if vol_ratio < 0.8 else "Normal")
    table.add_row("ATR (14)", f"${atr:,.0f}", f"≈ {atr/float(df['close'].iloc[-1])*100:.1f}% daily range")

    # Candlestick & divergence
    pattern   = detect_candlestick_pattern(df)
    divergence = detect_rsi_divergence(df)
    table.add_row("Candle Pattern", "", pattern)
    table.add_row("RSI Divergence", "", divergence)
    console.print(table)


def print_macro(ctx: dict):
    table = Table(title="Macro & Sentiment Context", box=box.SIMPLE_HEAD)
    table.add_column("Factor",  style="bold cyan", width=16)
    table.add_column("Value",   justify="right", width=12)
    table.add_column("Impact",  width=55)

    macro = ctx["macro"]
    msgs  = ctx["messages"]

    for key in ["DXY", "SP500", "VIX", "TNX"]:
        d = macro.get(key, {})
        price = d.get("price")
        chg   = d.get("change")
        val_str = f"${price:,.2f}" if price else "N/A"
        if chg is not None:
            chg_color = pct_color(chg)
            val_str += f"  [{chg_color}]{'+' if chg >= 0 else ''}{chg:.2f}%[/{chg_color}]"
        table.add_row(key, val_str, msgs[key])

    # Fear & Greed
    fg = ctx["fg"]
    fg_val = fg.get("value")
    fg_color = ("bright_green" if fg_val and fg_val < 30
                else "bright_red" if fg_val and fg_val > 70
                else "yellow")
    table.add_row("Fear & Greed",
                  f"[{fg_color}]{fg_val if fg_val else 'N/A'}[/{fg_color}]",
                  msgs["FG"])

    # Funding Rate
    fr = ctx["fr"]
    fr_val = fr.get("rate_pct")
    fr_str = f"{fr_val:+.4f}%" if fr_val is not None else "N/A"
    table.add_row("Funding Rate", fr_str, msgs["FR"])

    console.print(table)


def print_signals(sig: dict):
    table = Table(title=f"Strategy Signals ({sig['regime']} Market)",
                  box=box.SIMPLE_HEAD)
    table.add_column("Score", justify="center", width=7)
    table.add_column("Reason", width=65)

    for score, reason in sig["signals"]:
        color = score_color(score)
        arrow = "▲" if score > 0 else ("▼" if score < 0 else "●")
        table.add_row(f"[{color}]{arrow}{score:+d}[/{color}]", reason)
    console.print(table)


def print_swing_setups(setups):
    grade_color = {"A": "bright_green", "B": "yellow", "C": "orange3"}
    dir_color   = {"LONG": "bright_green", "SHORT": "bright_red"}

    if not setups:
        console.print(Panel(
            "[yellow]No high-probability swing setups detected right now.\n"
            "Wait for price to reach a key level or indicator extreme.[/yellow]",
            title="[bold white]Swing Trade Setups[/bold white]", box=box.SIMPLE_HEAD
        ))
        return

    console.print(f"\n[bold white]  Swing Trade Setups  "
                  f"[dim](Account: ${ACCOUNT_SIZE_USD:,}  |  Risk/trade: {RISK_PER_TRADE*100:.0f}%)[/dim]\n")

    for i, s in enumerate(setups, 1):
        gc = grade_color[s.grade]
        dc = dir_color[s.direction]
        rr_color = "bright_green" if s.rr >= 3 else ("green" if s.rr >= 2 else "yellow")

        # Header panel
        header = (
            f"[{gc}]Grade {s.grade}[/{gc}]  "
            f"[{dc}]{s.direction}[/{dc}]  "
            f"[bold]{s.name}[/bold]  "
            f"  R:R [{rr_color}]{s.rr:.1f}:1[/{rr_color}]"
        )

        # Trade plan table
        t = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
        t.add_column("Label",  style="cyan",  width=22)
        t.add_column("Value",  justify="right", width=14)
        t.add_column("Note",   width=42)

        t.add_row("Entry",
                  f"[bold]${s.entry:,.0f}[/bold]",
                  f"Zone: ${s.entry_zone_lo:,.0f} – ${s.entry_zone_hi:,.0f}")
        t.add_row("Stop Loss",
                  f"[bright_red]${s.stop:,.0f}[/bright_red]",
                  f"Risk: ${abs(s.entry - s.stop):,.0f} / BTC  "
                  f"({abs(s.entry-s.stop)/s.entry*100:.1f}%)")
        t.add_row("TP1  [dim](close 50%)[/dim]",
                  f"[green]${s.tp1:,.0f}[/green]",
                  f"+{abs(s.tp1-s.entry)/s.entry*100:.1f}%  →  move stop to breakeven")
        t.add_row("TP2  [dim](close 30%)[/dim]",
                  f"[bright_green]${s.tp2:,.0f}[/bright_green]",
                  f"+{abs(s.tp2-s.entry)/s.entry*100:.1f}%  →  trail stop by ATR")
        t.add_row("TP3  [dim](runner 20%)[/dim]",
                  f"[bold bright_green]${s.tp3:,.0f}[/bold bright_green]",
                  f"+{abs(s.tp3-s.entry)/s.entry*100:.1f}%  →  trailing stop")
        t.add_row("Position Size",
                  f"${s.position_size:,.0f}",
                  f"{s.qty_btc:.5f} BTC  (1R = ${ACCOUNT_SIZE_USD*RISK_PER_TRADE:,.0f})")
        t.add_row("Breakeven at",  f"${s.breakeven_at:,.0f}", "Move stop to entry when hit")
        t.add_row("Trailing Stop", f"${s.trailing_stop:,.0f}", "ATR-based trail after TP1")
        t.add_row("Time Stop",     f"{s.time_stop_bars} bars", "Cancel if entry not triggered")
        t.add_row("[yellow]Invalidation[/yellow]", "", f"[yellow]{s.invalidation}[/yellow]")

        # Rationale
        rationale_text = "\n".join(f"  • {r}" for r in s.rationale)

        console.print(Panel(
            f"{header}\n",
            box=box.ROUNDED,
            border_style=gc,
        ))
        console.print(t)
        console.print(f"[dim]  Rationale:[/dim]\n[dim]{rationale_text}[/dim]\n")


def print_verdict(sig: dict, ctx: dict):
    total  = sig["total_score"]
    action = sig["action"]
    color  = score_color(total)

    panel_text = Text(justify="center")
    panel_text.append(f"TA Score: {sig['ta_score']:+d}  |  "
                      f"Macro/Sentiment: {ctx['total_context_score']:+d}  |  "
                      f"Total: {total:+d}\n\n")
    panel_text.append(action, style=f"bold {color}")

    console.print(Panel(panel_text, title="[bold white]TRADING VERDICT[/bold white]",
                        border_style=color, box=box.DOUBLE, padding=(1, 4)))


def print_levels(df):
    levels = key_levels(df)
    close  = float(df["close"].iloc[-1])
    atr    = float(df["atr"].iloc[-1])

    table = Table(title="Key Price Levels", box=box.SIMPLE_HEAD)
    table.add_column("Level",     style="bold cyan", width=20)
    table.add_column("Price",     justify="right",   width=14)
    table.add_column("Distance",  justify="right",   width=12)

    for label, price in [
        ("90d Resistance", levels["resistance"]),
        ("Pivot",          levels["pivot"]),
        ("Current Price",  close),
        ("90d Support",    levels["support"]),
        ("+1 ATR Target",  close + atr),
        ("-1 ATR Stop",    close - atr),
    ]:
        dist_pct = (price - close) / close * 100
        dist_str = f"{'+' if dist_pct >= 0 else ''}{dist_pct:.1f}%"
        color = pct_color(dist_pct)
        table.add_row(label, f"${price:,.0f}", f"[{color}]{dist_str}[/{color}]")
    console.print(table)


# ── Chart (optional) ──────────────────────────────────────────────────────────

def save_chart(df, sig, filename="btc_chart.png"):
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(14, 10),
                                          gridspec_kw={"height_ratios": [3, 1, 1]},
                                          sharex=True)
    fig.suptitle(f"BTC/USD — {sig['regime']} Market  |  Action: {sig['action']}", fontsize=13)
    fig.patch.set_facecolor("#0d1117")
    for ax in [ax1, ax2, ax3]:
        ax.set_facecolor("#0d1117")
        ax.tick_params(colors="white")
        ax.spines[:].set_color("#30363d")

    idx = df.index[-90:]
    sub = df.tail(90)

    # Price + MAs
    ax1.plot(idx, sub["close"],  color="#58a6ff", linewidth=1.5, label="BTC")
    ax1.plot(idx, sub["sma200"], color="#ff7b72", linewidth=1.5, label="SMA200")
    ax1.plot(idx, sub["sma50"],  color="#3fb950", linewidth=1.2, label="SMA50")
    ax1.plot(idx, sub["ema20"],  color="#d29922", linewidth=1.0, linestyle="--", label="EMA20")
    ax1.fill_between(idx, sub["bb_upper"], sub["bb_lower"], alpha=0.07, color="white")
    ax1.legend(facecolor="#161b22", labelcolor="white", fontsize=8)
    ax1.set_ylabel("Price (USD)", color="white")
    ax1.yaxis.set_tick_params(labelcolor="white")

    # Volume
    colors = ["#3fb950" if c >= o else "#ff7b72"
              for c, o in zip(sub["close"], sub["open"])]
    ax2.bar(idx, sub["volume"], color=colors, alpha=0.8)
    ax2.plot(idx, sub["vol_sma"], color="white", linewidth=1.0, label="Vol SMA")
    ax2.set_ylabel("Volume", color="white")

    # RSI
    ax3.plot(idx, sub["rsi"], color="#bc8cff", linewidth=1.2)
    ax3.axhline(70, color="#ff7b72", linewidth=0.8, linestyle="--")
    ax3.axhline(30, color="#3fb950", linewidth=0.8, linestyle="--")
    ax3.axhline(50, color="gray", linewidth=0.5)
    ax3.set_ylim(0, 100)
    ax3.set_ylabel("RSI", color="white")

    ax3.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    plt.tight_layout()
    plt.savefig(filename, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    console.print(f"\n[green]Chart saved → {filename}[/green]")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    do_chart = "--chart" in sys.argv

    console.print("\n[bold cyan]Fetching BTC price data...[/bold cyan]")
    df_raw = fetch_btc_daily()

    console.print("[bold cyan]Calculating indicators...[/bold cyan]")
    df = add_all_indicators(df_raw)
    df = df.dropna()

    console.print("[bold cyan]Fetching macro & sentiment data...[/bold cyan]")
    ctx = get_full_context()

    console.print("[bold cyan]Scanning swing trade setups...[/bold cyan]\n")
    sig    = generate_signal(df, ctx["total_context_score"])
    setups = scan_setups(df)

    print_header(sig)
    console.print()

    print_market_regime(sig, df)
    print_technical(df)
    print_macro(ctx)
    print_signals(sig)
    print_levels(df)
    print_verdict(sig, ctx)
    print_swing_setups(setups)

    if do_chart:
        save_chart(df, sig)

    console.print("\n[dim]Data via Yahoo Finance · Fear&Greed via alternative.me · "
                  "Funding via Binance · Not financial advice[/dim]\n")


if __name__ == "__main__":
    main()
