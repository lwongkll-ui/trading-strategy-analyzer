"""
20-year monthly macro chart: 10Y-2Y Treasury spread, Fed funds rate, S&P 500.

Small multiples (three panels, one shared time axis) rather than a dual-axis
overlay: the three series span incompatible scales (spread ~-1..+3pp, policy
rate 0-5.5%, index 700-6800), and stacking two y-scales on one frame is the
classic way to manufacture a false visual correlation.

Sources: FRED (T10Y2Y, FEDFUNDS, USREC) + yfinance (^GSPC). No API key needed.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd, yfinance as yf

YEARS, START = 20, "2006-01-01"
# dataviz reference palette, categorical slots 1-3 (validated all-pairs, light)
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e2e1dc"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
REC, NEG = "#ebe9e4", "#f6d9cf"


def fred(series):
    df = pd.read_csv(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}")
    df.columns = ["date", "value"]
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna().set_index("date")["value"]


def load():
    spread = fred("T10Y2Y").resample("MS").mean()          # daily -> monthly avg
    ff     = fred("FEDFUNDS")                              # already monthly
    rec    = fred("USREC")
    sp     = yf.download("^GSPC", start="2004-01-01", interval="1mo",
                         progress=False, auto_adjust=True)["Close"]
    if hasattr(sp, "columns"):
        sp = sp.iloc[:, 0]
    sp.index = pd.to_datetime(sp.index).tz_localize(None)
    sp = sp.resample("MS").last()
    d = {"spread": spread, "ff": ff, "sp": sp, "rec": rec}
    return {k: v[v.index >= START] for k, v in d.items()}


def rec_bands(ax, rec):
    """Shade NBER recessions across every panel for shared context."""
    on = None
    for dt, v in rec.items():
        if v == 1 and on is None:
            on = dt
        elif v == 0 and on is not None:
            ax.axvspan(on, dt, color=REC, zorder=0, lw=0); on = None
    if on is not None:
        ax.axvspan(on, rec.index[-1], color=REC, zorder=0, lw=0)


def style(ax, label, color, last_txt):
    ax.set_facecolor(SURFACE)
    ax.grid(True, axis="y", color=GRID, lw=0.8, ls="-", zorder=1)  # solid hairline, never dashed
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID); ax.spines["bottom"].set_linewidth(0.8)
    ax.tick_params(colors=INK2, labelsize=9, length=0)
    # direct label per panel: one series per panel, so no legend box is needed
    ax.text(0.006, 0.94, label, transform=ax.transAxes, ha="left", va="top",
            fontsize=11, fontweight="bold", color=INK)
    ax.text(0.994, 0.94, last_txt, transform=ax.transAxes, ha="right", va="top",
            fontsize=10, fontweight="bold", color=color)


def main():
    d = load()
    sp_, ff_, spx, rec = d["spread"], d["ff"], d["sp"], d["rec"]

    fig, axes = plt.subplots(3, 1, figsize=(12, 10.5), sharex=True,
                             gridspec_kw={"hspace": 0.16})
    fig.patch.set_facecolor(SURFACE)

    # 1 — 10Y-2Y spread: polarity matters, so mark zero and shade inversions
    ax = axes[0]; rec_bands(ax, rec)
    inv = sp_ < 0
    ax.fill_between(sp_.index, sp_, 0, where=inv, color=NEG, zorder=2, interpolate=True)
    ax.axhline(0, color=INK2, lw=1.0, zorder=3)
    ax.plot(sp_.index, sp_, color=BLUE, lw=2, zorder=4)
    ax.set_ylim(min(sp_.min() * 1.25, -1.0), sp_.max() + 1.15)   # headroom for the label band
    style(ax, "10Y − 2Y Treasury spread  (percentage points)", BLUE, f"{sp_.iloc[-1]:+.2f} pp")
    ax.text(0.006, 0.06, "below 0 = inverted curve (shaded)", transform=ax.transAxes,
            fontsize=9, color=INK2)

    # 2 — Fed funds (the policy lever)
    ax = axes[1]; rec_bands(ax, rec)
    ax.plot(ff_.index, ff_, color=ORANGE, lw=2, zorder=4)
    ax.set_ylim(0, ff_.max() * 1.30)                              # headroom for the label band
    style(ax, "Effective Fed funds rate  (%)", ORANGE, f"{ff_.iloc[-1]:.2f}%")

    # 3 — S&P 500, log scale so early and late drawdowns are comparable
    ax = axes[2]; rec_bands(ax, rec)
    ax.plot(spx.index, spx, color=AQUA, lw=2, zorder=4)
    ax.set_yscale("log")
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, p: f"{v:,.0f}"))
    ax.set_yticks([800, 1500, 3000, 6000])
    ax.minorticks_off()                                           # log minor ticks read as noise
    ax.set_ylim(spx.min() * 0.80, spx.max() * 1.85)               # headroom for the label band
    style(ax, "S&P 500  (log scale)", AQUA, f"{spx.iloc[-1]:,.0f}")

    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    fig.suptitle("Yield curve, policy rate and equities — 20 years, monthly",
                 x=0.062, y=0.972, ha="left", fontsize=16, fontweight="bold", color=INK)
    fig.text(0.062, 0.943,
             "Grey bands = NBER recessions.  Each curve inversion since 2006 has been "
             "followed by Fed cuts and an equity drawdown.",
             ha="left", fontsize=10.5, color=INK2)
    fig.text(0.062, 0.022,
             "Sources: FRED (T10Y2Y, FEDFUNDS, USREC), Yahoo Finance (^GSPC). "
             "Monthly; spread = monthly average of daily.",
             ha="left", fontsize=8.5, color=INK2)
    fig.subplots_adjust(left=0.062, right=0.986, top=0.915, bottom=0.062)

    out = "yield_curve_20y.png"
    fig.savefig(out, dpi=150, facecolor=SURFACE)
    print("wrote", out)
    # table view (the relief rule + an accessible read of the same data)
    tbl = pd.DataFrame({"10Y-2Y": sp_, "FedFunds": ff_, "SP500": spx}).dropna()
    tbl.resample("YS").last().round(2).to_csv("yield_curve_20y.csv")
    print("wrote yield_curve_20y.csv  (annual table view)")
    print(tbl.resample("YS").last().round(2).tail(21).to_string())


if __name__ == "__main__":
    main()
