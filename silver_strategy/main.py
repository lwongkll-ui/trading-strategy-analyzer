"""
Silver Miner Stocks - Trading Strategy Analyzer
================================================
Usage:
    python main.py              # terminal dashboard only
    python main.py --chart      # + save daily charts (silver_charts/)
    python main.py --weekly     # + save weekly overview charts
    python main.py --ticker AG  # analyze a single stock

Stocks covered: ASM, PAAS, CDE, AG, USAS, SVM
"""

from __future__ import annotations
import argparse
import sys
import os
import io
import time
from datetime import datetime

# Force UTF-8 output on Windows to avoid cp1252 encoding errors
if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# -- Rich --------------------------------------------------------------------
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.text import Text
from rich import box
from rich.rule import Rule

# -- Local modules ------------------------------------------------------------
from config import SILVER_MINERS, OUTPUT_DIR
from fetcher import fetch_all_data, fetch_macro
from indicators import compute_all
from fundamentals import score_fundamentals, fundamental_summary
from market_context import analyze_macro
from strategy import generate_historical_signals, get_current_signal

console = Console(force_terminal=True, highlight=False)


# -- Formatting helpers -------------------------------------------------------

def _color_signal(sig: str) -> str:
    return {"BUY": "[bold green]BUY[/]", "AVOID": "[bold red]AVOID[/]"}.get(sig, "[yellow]HOLD[/]")


def _color_score(s: int) -> str:
    if s >= 5:
        return f"[bold green]+{s}[/]"
    if s >= 2:
        return f"[green]+{s}[/]"
    if s >= 0:
        return f"[yellow]+{s}[/]" if s > 0 else f"[yellow]{s}[/]"
    if s >= -2:
        return f"[red]{s}[/]"
    return f"[bold red]{s}[/]"


def _color_change(v) -> str:
    if v is None:
        return "[dim]N/A[/]"
    if v > 0:
        return f"[green]+{v:.2f}%[/]"
    if v < 0:
        return f"[red]{v:.2f}%[/]"
    return f"[dim]{v:.2f}%[/]"


def _color_regime(r: str) -> str:
    return "[green]BULL[/]" if r == "BULL" else "[red]BEAR[/]"


def _fmt(v, decimals: int = 2) -> str:
    if v is None:
        return "N/A"
    if isinstance(v, float):
        return f"{v:.{decimals}f}"
    return str(v)


def _pct(v) -> str:
    if v is None:
        return "N/A"
    col = "green" if v > 0 else ("red" if v < 0 else "dim")
    return f"[{col}]{v:+.1f}%[/]"


# -- Dashboard sections -------------------------------------------------------

def render_header():
    console.print()
    console.print(Rule("[bold silver]SILVER MINER STOCKS - TRADING STRATEGY ANALYZER[/]",
                       style="bright_white"))
    console.print(f"[dim]Analysis date: {datetime.now().strftime('%Y-%m-%d %H:%M')}  |  "
                  f"Stocks: {', '.join(SILVER_MINERS)}[/]")
    console.print()


def render_macro(ctx: dict):
    table = Table(title="[bold]MACRO & SILVER MARKET CONTEXT[/]",
                  box=box.SIMPLE_HEAD, show_header=True,
                  header_style="bold cyan", min_width=80)
    table.add_column("Metric",  style="dim", width=28)
    table.add_column("Value",   justify="right", width=12)
    table.add_column("1-Month", justify="right", width=12)
    table.add_column("Signal",  justify="center", width=12)

    def _row(metric, px, chg, sig="-"):
        px_str  = f"${px:.2f}" if isinstance(px, float) else str(px)
        chg_str = _color_change(chg)
        return metric, px_str, chg_str, sig

    ag_px  = ctx.get("ag_price")
    gold_px = ctx.get("gold_px")
    gs      = ctx.get("gs_ratio")

    rows = [
        ("Silver Spot (SI=F)",
         ag_px, ctx.get("ag_1m"),
         "[green]^[/]" if (ctx.get("ag_1m") or 0) > 0 else "[red]v[/]"),
        ("Gold Spot (GC=F)",
         gold_px, None, "-"),
        ("Gold/Silver Ratio",
         f"{gs:.1f}x" if gs else "N/A", None,
         "[green]Silver Cheap[/]" if gs and gs > 85 else
         ("[red]Silver Rich[/]" if gs and gs < 60 else "[yellow]Neutral[/]")),
        ("DXY (USD Index)",
         ctx.get("dxy_px"), ctx.get("dxy_1m"),
         "[red]Headwind[/]" if (ctx.get("dxy_1m") or 0) > 1.5 else
         "[green]Tailwind[/]" if (ctx.get("dxy_1m") or 0) < -1.5 else "[yellow]Neutral[/]"),
        ("10Y Treasury Yield (%)",
         ctx.get("tnx_px"), None,
         "[red]High[/]" if (ctx.get("tnx_px") or 0) > 5 else
         "[green]Low[/]"  if (ctx.get("tnx_px") or 0) < 3.5 else "[yellow]Normal[/]"),
        ("VIX (Fear Index)",
         ctx.get("vix_px"), None,
         "[red]Fear[/]" if (ctx.get("vix_px") or 0) > 30 else
         "[green]Calm[/]" if (ctx.get("vix_px") or 0) < 15 else "[yellow]Normal[/]"),
        ("S&P 500 (1-month)",
         None, ctx.get("sp_1m"), "-"),
        ("SIL ETF (sector, 1-month)",
         None, ctx.get("sil_1m"), "-"),
    ]
    for metric, px, chg, sig in rows:
        px_str = (f"${px:.2f}" if isinstance(px, float) else str(px)) if px else "-"
        chg_str = _color_change(chg) if isinstance(chg, float) else str(chg)
        table.add_row(metric, px_str, chg_str, sig)

    macro_score_str = _color_score(ctx["score"])
    console.print(table)
    console.print(f"  [bold]Macro Score:[/] {macro_score_str}  "
                  f"([green]{len(ctx['bullish'])} bullish[/] / [red]{len(ctx['bearish'])} bearish[/] factors)\n")

    if ctx["bullish"]:
        console.print("  [green bold]Macro Tailwinds:[/]")
        for b in ctx["bullish"]:
            console.print(f"    [green]+[/] {b}")
    if ctx["bearish"]:
        console.print("  [red bold]Macro Headwinds:[/]")
        for b in ctx["bearish"]:
            console.print(f"    [red]x[/] {b}")
    console.print()

    # Silver market structural notes
    structural = [n for n in ctx["notes"] if n.startswith("Solar") or n.startswith("EV")
                  or n.startswith("Industrial") or n.startswith("Global")
                  or n.startswith("Miner") or n.startswith("Silver")]
    if structural:
        console.print("  [cyan bold]Silver Market Dynamics:[/]")
        for n in structural[:6]:
            console.print(f"    [dim]-[/] {n}")
    console.print()


def render_summary_table(results: list[dict]):
    table = Table(title="[bold]SILVER MINERS - SIGNAL SUMMARY[/]",
                  box=box.SIMPLE_HEAD, show_header=True,
                  header_style="bold cyan", border_style="bright_black",
                  expand=False)

    table.add_column("Ticker",  justify="center", width=6,  style="bold")
    table.add_column("Company", justify="left",   width=20)
    table.add_column("Price",   justify="right",  width=8)
    table.add_column("Regime",  justify="center", width=6)
    table.add_column("Signal",  justify="center", width=7)
    table.add_column("Score",   justify="center", width=7)
    table.add_column("RSI",     justify="right",  width=5)
    table.add_column("STC-F",   justify="right",  width=6)
    table.add_column("Pattern", justify="center", width=10)

    for r in results:
        sig  = r["signal"]
        cur  = r["current"]
        price = cur.get("price", 0) or 0
        price_str = f"${price:.3f}" if price < 10 else f"${price:.2f}"

        rsi_v = cur.get("rsi")
        rsi_col = "red" if rsi_v and rsi_v > 70 else ("green" if rsi_v and rsi_v < 30 else "white")
        rsi_str = f"[{rsi_col}]{rsi_v:.0f}[/]" if rsi_v else "N/A"

        sig_color = {"BUY": "green", "AVOID": "red"}.get(sig, "yellow")
        regime = cur.get("regime", "BEAR")
        regime_color = "green" if regime == "BULL" else "red"

        table.add_row(
            r["ticker"],
            SILVER_MINERS.get(r["ticker"], r["ticker"])[:20],
            price_str,
            f"[{regime_color}]{regime}[/]",
            f"[bold {sig_color}]{sig}[/]",
            _color_score(cur["total_score"]),
            rsi_str,
            f"{cur.get('stc_fast', 0):.0f}" if cur.get("stc_fast") else "N/A",
            cur.get("pattern") or "-",
        )

    console.print(table)
    console.print()


def render_stock_detail(r: dict):
    ticker = r["ticker"]
    company = SILVER_MINERS.get(ticker, ticker)
    cur  = r["current"]
    fund = r["fund_summary"]
    sig  = r["signal"]

    # Header panel
    regime_str = _color_regime(cur.get("regime", "BEAR"))
    signal_str = _color_signal(sig)
    price = cur.get("price", 0)
    price_str = f"${price:.3f}" if price < 10 else f"${price:.2f}"

    console.print(Panel(
        f"[bold white]{ticker}[/]  {company}\n"
        f"Price [bold]{price_str}[/]  |  Regime {regime_str}  |  Signal {signal_str}  |  "
        f"Total Score {_color_score(cur['total_score'])}",
        border_style="bright_black", expand=False,
    ))

    # Two-column layout: technicals | fundamentals
    tech_table = Table(box=box.SIMPLE, show_header=False, min_width=38)
    tech_table.add_column("Key",   style="dim", width=18)
    tech_table.add_column("Value", justify="right", width=18)

    sma50  = cur.get("sma50")
    sma200 = cur.get("sma200")
    tech_rows = [
        ("Tech Score",      _color_score(cur["tech_score"])),
        ("Weekly Trend",    _color_score(cur["weekly_score"])),
        ("Hourly Momentum", _color_score(cur["hourly_score"])),
        ("SMA 50",          f"${sma50:.2f}" if sma50 else "N/A"),
        ("SMA 200",         f"${sma200:.2f}" if sma200 else "N/A"),
        ("RSI (14)",        f"{cur.get('rsi', 0):.1f}" if cur.get("rsi") else "N/A"),
        ("STC Fast",        f"{cur.get('stc_fast', 0):.1f}" if cur.get("stc_fast") else "N/A"),
        ("STC Slow",        f"{cur.get('stc_slow', 0):.1f}" if cur.get("stc_slow") else "N/A"),
        ("MACD Hist",       f"{cur.get('macd_hist', 0):.4f}" if cur.get("macd_hist") is not None else "N/A"),
        ("ATR",             f"${cur.get('atr', 0):.3f}" if cur.get("atr") else "N/A"),
        ("Vol Ratio",       f"{cur.get('vol_ratio', 0):.2f}x" if cur.get("vol_ratio") else "N/A"),
        ("Pattern",         cur.get("pattern") or "-"),
    ]
    for k, v in tech_rows:
        tech_table.add_row(k, v)

    fund_table = Table(box=box.SIMPLE, show_header=False, min_width=38)
    fund_table.add_column("Key",   style="dim", width=18)
    fund_table.add_column("Value", justify="right", width=18)

    fund_rows = [
        ("Fund Score",       _color_score(fund["score"])),
        ("Market Cap",       fund["market_cap"]),
        ("Trailing P/E",     fund["trailing_pe"]),
        ("Forward P/E",      fund["forward_pe"]),
        ("P/Book",           fund["pb_ratio"]),
        ("Net Debt",         fund["net_debt"]),
        ("Debt/EBITDA",      fund["debt_ebitda"]),
        ("Current Ratio",    fund["current_ratio"]),
        ("Op Margin",        fund["op_margin"]),
        ("ROE",              fund["roe"]),
        ("Rev Growth YoY",   fund["rev_growth"]),
        ("Free Cash Flow",   fund["fcf"]),
        ("Beta",             fund["beta"]),
        ("Short Ratio",      fund["short_ratio"]),
        ("52W High",         fund["52w_high"]),
        ("52W Low",          fund["52w_low"]),
        ("From 52W High",    fund["pct_from_high"]),
        ("Analyst Target",   fund["analyst_target"]),
        ("Recommendation",   fund["recommendation"]),
        ("Inst. Held",       fund["inst_hold"]),
    ]
    for k, v in fund_rows:
        fund_table.add_row(k, v)

    console.print(Columns([tech_table, fund_table]))

    # Positives / Negatives
    if fund["positives"]:
        console.print("  [green bold]Fundamental Positives:[/]")
        for p in fund["positives"]:
            console.print(f"    [green]+[/] {p}")
    if fund["negatives"]:
        console.print("  [red bold]Fundamental Concerns:[/]")
        for n in fund["negatives"]:
            console.print(f"    [red]x[/] {n}")

    # Entry hints
    if cur.get("entry_hints"):
        console.print("  [cyan bold]Entry Guidance:[/]")
        for h in cur["entry_hints"]:
            console.print(f"    [cyan]->[/] {h}")

    # Company description snippet
    desc = fund.get("description", "")
    if desc:
        console.print(f"\n  [dim]{desc[:250]}...[/]" if len(desc) > 250 else f"\n  [dim]{desc}[/]")
    console.print()


def render_strategy_notes():
    notes = Panel(
        "[bold cyan]STRATEGY NOTES - Long Only, No Short Selling[/]\n\n"
        "[bold]Entry rules (all timeframes must align):[/]\n"
        "  [green]^[/] Weekly: price above SMA-200 and SMA-50 > SMA-200 (golden cross zone)\n"
        "  [green]^[/] Daily: Fast STC crosses above 25 (oversold->momentum)  AND  MACD supportive\n"
        "  [green]^[/] Hourly: EMA-9 > EMA-21 for intraday entry timing\n"
        "  [green]^[/] Macro: Silver spot rising, DXY weakening, rates stable/falling\n\n"
        "[bold]Exit rules:[/]\n"
        "  [red]v[/] Fast STC crosses below 75 from above  OR  MACD line crosses below signal\n"
        "  [red]v[/] Death cross event (SMA-50 crosses below SMA-200) - hard exit\n"
        "  [red]v[/] RSI > 75 - consider partial profit-taking (1/3 position)\n\n"
        "[bold]Position sizing:[/]\n"
        "  - Full position: Score >= +7, strong macro + fundamental backdrop\n"
        "  - Half position: Score +5 to +6, or macro/fundamental concern\n"
        "  - No position: Score < +5, bear regime, or AVOID signal\n"
        "  - Stop loss: 2x ATR below entry  |  Target: 3x ATR above entry (min 2:3 R:R)\n\n"
        "[bold]Silver miner leverage:[/]\n"
        "  - Primary silver miners (AG, USAS, SVM) move 2-4x silver spot\n"
        "  - Diversified miners (PAAS, CDE) move 1.5-2.5x silver spot\n"
        "  - Small-caps (ASM, USAS) carry higher volatility - use smaller size\n\n"
        "[bold]Non-technical watch list:[/]\n"
        "  - Silver industrial demand: solar panel capacity data, EV adoption rates\n"
        "  - Fed meeting dates (rate decisions drive DXY and yield moves)\n"
        "  - Silver Institute quarterly supply/demand report\n"
        "  - COT (Commitment of Traders) report - commercial short positions\n"
        "  - Inflation prints (CPI, PCE) - above-expectation = bullish precious metals",
        border_style="bright_black",
        title="[bold]STRATEGY REFERENCE[/]",
        expand=True,
    )
    console.print(notes)
    console.print()


# -- Main ----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Silver Miner Trading Strategy Analyzer")
    parser.add_argument("--chart",  action="store_true", help="Save daily charts as PNG")
    parser.add_argument("--weekly", action="store_true", help="Also save weekly charts")
    parser.add_argument("--ticker", default=None,
                        help="Analyze a single ticker (e.g. --ticker AG)")
    args = parser.parse_args()

    tickers = ([args.ticker.upper()] if args.ticker
               else list(SILVER_MINERS.keys()))

    render_header()

    # -- Fetch macro ----------------------------------------------------------
    console.print("[dim]Fetching macro data (silver, gold, DXY, VIX, TNX, S&P, SIL)...[/]")
    macro_raw = fetch_macro()
    macro_ctx = analyze_macro(macro_raw)
    render_macro(macro_ctx)

    # -- Fetch & analyze each stock -------------------------------------------
    results = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        transient=True,
    ) as progress:
        task = progress.add_task("[cyan]Analyzing stocks...", total=len(tickers))

        for ticker in tickers:
            progress.update(task, description=f"[cyan]Fetching {ticker}...")
            try:
                data = fetch_all_data(ticker)

                df_d = compute_all(data["daily"])
                df_w = compute_all(data["weekly"]) if not data["weekly"].empty else data["weekly"]
                df_h = compute_all(data["hourly"]) if not data["hourly"].empty else data["hourly"]

                df_d = generate_historical_signals(df_d)
                if not df_w.empty:
                    df_w = generate_historical_signals(df_w)

                fund_info = data["fundamentals"]
                fund_score, _, _ = score_fundamentals(fund_info)
                fund_sum  = fundamental_summary(fund_info)

                cur = get_current_signal(df_d, df_w, df_h, fund_score, macro_ctx["score"])

                results.append({
                    "ticker":       ticker,
                    "signal":       cur["signal"],
                    "current":      cur,
                    "fund_summary": fund_sum,
                    "df_daily":     df_d,
                    "df_weekly":    df_w,
                    "df_hourly":    df_h,
                })

                if args.chart or args.weekly:
                    progress.update(task, description=f"[cyan]Charting {ticker}...")
                    from charts import plot_stock, plot_weekly_overview
                    if args.chart:
                        path = plot_stock(ticker, SILVER_MINERS.get(ticker, ticker), df_d, OUTPUT_DIR)
                        if path:
                            progress.print(f"  [dim]Saved {path}[/]")
                    if args.weekly and not df_w.empty:
                        wpath = plot_weekly_overview(ticker, SILVER_MINERS.get(ticker, ticker),
                                                     df_w, OUTPUT_DIR)
                        if wpath:
                            progress.print(f"  [dim]Saved {wpath}[/]")

            except Exception as e:
                console.print(f"  [red]Error processing {ticker}: {e}[/]")

            progress.advance(task)

    if not results:
        console.print("[red]No results to display.[/]")
        return

    # -- Render outputs -------------------------------------------------------
    render_summary_table(results)

    # Sort: BUY first, then HOLD, then AVOID
    order = {"BUY": 0, "HOLD": 1, "AVOID": 2}
    results.sort(key=lambda r: (order.get(r["signal"], 1), -r["current"]["total_score"]))

    for r in results:
        render_stock_detail(r)

    render_strategy_notes()

    if args.chart or args.weekly:
        console.print(f"[green]Charts saved to:[/] [bold]{os.path.abspath(OUTPUT_DIR)}/[/]")
        console.print()


if __name__ == "__main__":
    main()
