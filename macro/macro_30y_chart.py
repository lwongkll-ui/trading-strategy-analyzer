"""
30-year monthly macro chart: 10Y-2Y spread, Fed funds, unemployment, S&P 500, gold.

Small multiples (five panels, one shared time axis), not a dual-axis overlay:
the series span incompatible scales and stacking y-scales manufactures false
correlation.

Colour encodes CATEGORY, not series identity. Empirically, none of the 56
possible 5-colour subsets of the reference palette clears the all-pairs CVD
gate in both light and dark, so the five panels reuse the three validated
slots by domain: blue = rates/policy, orange = real economy, aqua = assets.
Each panel is directly labelled, so identity is never colour-alone.

Sources: FRED (T10Y2Y, FEDFUNDS, UNRATE, USREC) + yfinance (^GSPC, GC=F).
Gold futures begin Aug 2000, so that panel covers 26 of the 30 years.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter
import pandas as pd, yfinance as yf, warnings
warnings.filterwarnings("ignore")

START = "1996-01-01"
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e2e1dc"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"   # validated slots 1-3
REC, NEG = "#ebe9e4", "#f6d9cf"


def fred(series):
    df = pd.read_csv(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}")
    df.columns = ["date", "value"]
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna().set_index("date")["value"]


def yahoo(ticker):
    s = yf.download(ticker, start="1995-01-01", interval="1mo",
                    progress=False, auto_adjust=True)["Close"]
    if hasattr(s, "columns"):
        s = s.iloc[:, 0]
    s.index = pd.to_datetime(s.index).tz_localize(None)
    return s.resample("MS").last().dropna()


def load():
    d = {"spread": fred("T10Y2Y").resample("MS").mean(),
         "ff":     fred("FEDFUNDS"),
         "unemp":  fred("UNRATE"),
         "rec":    fred("USREC"),
         "sp":     yahoo("^GSPC"),
         "gold":   yahoo("GC=F"),
         "real":   fred("REAINTRATREARAT10Y"),      # Cleveland Fed 10Y real rate, 1982+
         "tips":   fred("DFII10").resample("MS").mean(),   # market 10Y TIPS, 2003+
         "be":     fred("T10YIE").resample("MS").mean(),   # 10Y breakeven inflation, 2003+
         "n10":    fred("DGS10").resample("MS").mean()}    # 10Y nominal
    return {k: v[v.index >= START] for k, v in d.items()}


def rec_bands(ax, rec):
    on = None
    for dt, v in rec.items():
        if v == 1 and on is None:
            on = dt
        elif v == 0 and on is not None:
            ax.axvspan(on, dt, color=REC, zorder=0, lw=0); on = None
    if on is not None:
        ax.axvspan(on, rec.index[-1], color=REC, zorder=0, lw=0)


def style(ax, label, color, last_txt, note=None):
    ax.set_facecolor(SURFACE)
    ax.grid(True, axis="y", color=GRID, lw=0.8, ls="-", zorder=1)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID); ax.spines["bottom"].set_linewidth(0.8)
    ax.tick_params(colors=INK2, labelsize=9, length=0)
    ax.text(0.006, 0.95, label, transform=ax.transAxes, ha="left", va="top",
            fontsize=11, fontweight="bold", color=INK)
    ax.text(0.994, 0.95, last_txt, transform=ax.transAxes, ha="right", va="top",
            fontsize=10, fontweight="bold", color=color)
    if note:
        ax.text(0.006, 0.06, note, transform=ax.transAxes, fontsize=8.5, color=INK2)


def main():
    d = load()
    sp_, ff_, un, spx, gold, rec = (d["spread"], d["ff"], d["unemp"],
                                    d["sp"], d["gold"], d["rec"])
    real, tips, be, n10 = d["real"], d["tips"], d["be"], d["n10"]
    # Rolling 36m correlation between the LEVEL of the real yield and log(gold).
    # Deliberately levels, not monthly changes: the month-to-month correlation of
    # gold returns vs changes in real yields is ~0 in every era (-0.02 / -0.14 /
    # -0.05), so a changes-based panel would show noise. The regime shift lives in
    # the multi-year trend relationship, which levels capture.
    import numpy as np
    j = pd.DataFrame({"g": np.log(gold), "r": real.reindex(gold.index).ffill()}).dropna()
    corr = j["r"].rolling(36).corr(j["g"]).dropna()

    fig, axes = plt.subplots(8, 1, figsize=(12.5, 23.0), sharex=True,
                             gridspec_kw={"hspace": 0.17})
    fig.patch.set_facecolor(SURFACE)

    # 1 — yield curve (leading signal)
    ax = axes[0]; rec_bands(ax, rec)
    ax.fill_between(sp_.index, sp_, 0, where=sp_ < 0, color=NEG, zorder=2, interpolate=True)
    ax.axhline(0, color=INK2, lw=1.0, zorder=3)
    ax.plot(sp_.index, sp_, color=BLUE, lw=2, zorder=4)
    ax.set_ylim(min(sp_.min() * 1.25, -1.2), sp_.max() + 1.2)
    style(ax, "10Y − 2Y Treasury spread  (pp)", BLUE, f"{sp_.iloc[-1]:+.2f} pp",
          "below 0 = inverted curve (shaded)")

    # 2 — policy rate
    ax = axes[1]; rec_bands(ax, rec)
    ax.plot(ff_.index, ff_, color=BLUE, lw=2, zorder=4)
    ax.set_ylim(0, ff_.max() * 1.32)
    style(ax, "Effective Fed funds rate  (%)", BLUE, f"{ff_.iloc[-1]:.2f}%")

    # 3 — real economy
    ax = axes[2]; rec_bands(ax, rec)
    ax.plot(un.index, un, color=ORANGE, lw=2, zorder=4)
    ax.set_ylim(0, un.max() * 1.30)
    style(ax, "US unemployment rate  (%)", ORANGE, f"{un.iloc[-1]:.1f}%")

    # 4 — equities (log: makes 2000/2008/2020 drawdowns comparable)
    ax = axes[3]; rec_bands(ax, rec)
    ax.plot(spx.index, spx, color=AQUA, lw=2, zorder=4)
    ax.set_yscale("log"); ax.minorticks_off()
    ax.set_yticks([800, 1600, 3200, 6400])
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, p: f"{v:,.0f}"))
    ax.set_ylim(spx.min() * 0.78, spx.max() * 1.95)
    style(ax, "S&P 500  (log scale)", AQUA, f"{spx.iloc[-1]:,.0f}")

    # 5 — gold (log; futures history starts Aug 2000)
    ax = axes[4]; rec_bands(ax, rec)
    ax.plot(gold.index, gold, color=AQUA, lw=2, zorder=4)
    ax.set_yscale("log"); ax.minorticks_off()
    ax.set_yticks([300, 600, 1200, 2400, 4800])
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, p: f"{v:,.0f}"))
    ax.set_ylim(gold.min() * 0.78, gold.max() * 1.95)
    style(ax, "Gold  ($/oz, log scale)", AQUA, f"${gold.iloc[-1]:,.0f}",
          f"futures series begins {gold.index.min():%b %Y}")

    # 6 - real yield: the variable that actually links bonds and gold
    ax = axes[5]; rec_bands(ax, rec)
    ax.fill_between(real.index, real, 0, where=real < 0, color=NEG, zorder=2, interpolate=True)
    ax.axhline(0, color=INK2, lw=1.0, zorder=3)
    ax.plot(real.index, real, color=BLUE, lw=2, zorder=4)
    ax.set_ylim(min(real.min() * 1.3, -1.5), real.max() + 1.6)
    style(ax, "10Y real interest rate  (%)", BLUE, f"{real.iloc[-1]:.2f}%",
          f"below 0 = negative real rates (shaded) · market 10Y TIPS today {tips.iloc[-1]:.2f}%")

    # 7 - is the gold/real-yield link intact?
    ax = axes[6]; rec_bands(ax, rec)
    ax.fill_between(corr.index, corr, 0, where=corr > 0, color=NEG, zorder=2, interpolate=True)
    ax.axhline(0, color=INK2, lw=1.0, zorder=3)
    ax.plot(corr.index, corr, color=AQUA, lw=2, zorder=4)
    ax.set_ylim(-1.05, 1.45)
    style(ax, "Gold vs real yield - 36m rolling correlation (levels)", AQUA, f"{corr.iloc[-1]:+.2f}",
          "negative = textbook (real yields up, gold down) · above 0 (shaded) = link inverted")

    # 8 - nominal 10Y split into its two drivers. A rise driven by REAL yields
    # raises gold's opportunity cost (hostile); one driven by BREAKEVENS is an
    # inflation signal (friendly). Two lines rather than a stacked area because
    # the real yield goes negative (2020-22) and stacks mis-render negatives.
    ax = axes[7]; rec_bands(ax, rec)
    ax.fill_between(tips.index, tips, 0, where=tips < 0, color=NEG, zorder=2, interpolate=True)
    ax.axhline(0, color=INK2, lw=1.0, zorder=3)
    ax.plot(tips.index, tips, color=BLUE, lw=2, zorder=4, label="real (10Y TIPS)")
    ax.plot(be.index, be, color=ORANGE, lw=2, zorder=4, label="breakeven inflation")
    ax.set_ylim(min(tips.min() * 1.35, -1.5), max(be.max(), tips.max()) + 1.5)
    ax.legend(loc="upper left", bbox_to_anchor=(0.0, 0.80), frameon=False,
              fontsize=9, labelcolor=INK2, ncol=2, handlelength=1.6)
    # Direct labels at the right edge, in-series colour. The two series often
    # converge (currently 0.08pp apart), so stagger them vertically or the
    # labels overlap and both become unreadable.
    ends = sorted(((tips.iloc[-1], BLUE), (be.iloc[-1], ORANGE)), key=lambda t: -t[0])
    for (v, col), dy in zip(ends, (9, -13)):
        ax.annotate(f"{v:.2f}%", (tips.index[-1], v), textcoords="offset points",
                    xytext=(7, dy), fontsize=9, fontweight="bold", color=col,
                    zorder=5, clip_on=False)
    style(ax, "10Y nominal decomposed  (%)", INK, f"nominal {n10.iloc[-1]:.2f}%",
          "series begin 2003 · nominal = real + breakeven · real<0 shaded (gold-friendly)")

    ax.xaxis.set_major_locator(mdates.YearLocator(3))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    fig.suptitle("Rates, jobs and assets — 30 years, monthly",
                 x=0.058, y=0.9905, ha="left", fontsize=17, fontweight="bold", color=INK)
    fig.text(0.058, 0.9635,
             "Grey bands = NBER recessions.  Colour groups the domain: "
             "blue = rates/policy · orange = real economy · aqua = assets.",
             ha="left", fontsize=10.5, color=INK2)
    fig.text(0.058, 0.016,
             "Sources: FRED (T10Y2Y, FEDFUNDS, UNRATE, USREC, REAINTRATREARAT10Y, DFII10), "
             "DGS10, T10YIE), Yahoo Finance (^GSPC, GC=F). Monthly; spread = monthly avg of daily.",
             ha="left", fontsize=8.5, color=INK2)
    fig.subplots_adjust(left=0.058, right=0.986, top=0.936, bottom=0.042)

    fig.savefig("macro_30y.png", dpi=150, facecolor=SURFACE)
    print("wrote macro_30y.png")

    tbl = pd.DataFrame({"10Y-2Y": sp_, "FedFunds": ff_, "Unemp": un,
                        "SP500": spx, "Gold": gold, "RealYield": real,
                        "GoldRealCorr": corr, "TIPS10": tips, "Breakeven10": be})
    tbl.resample("YS").last().round(2).to_csv("macro_30y.csv")
    print("wrote macro_30y.csv  (annual table view)")
    print(tbl.resample("YS").last().round(2).tail(31).to_string())


if __name__ == "__main__":
    main()
