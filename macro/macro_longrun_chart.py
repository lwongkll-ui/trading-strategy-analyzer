"""
Long-run macro chart, 1940-present: nominal yield, inflation, EX-POST REAL yield,
yield curve, unemployment, equities, federal debt, debt/GDP, gold.

Why this differs from macro_30y_chart.py:
  * Real yield is EX-POST (10Y nominal minus trailing 12m CPI), not TIPS. TIPS
    only exist from 2003; ex-post real is the only measure that reaches 1940,
    and it is the standard long-history proxy.
  * The 10Y is spliced: LTGOVTBD (long-term govt bond, 1940-1953) then GS10.
    They correlate 0.988 over their 47-year overlap; LTGOVTBD is longer-maturity
    so it sits ~0.37pp higher. Flagged on-chart, not silently blended.
  * Curve is 10Y minus 3M T-bill. The 2Y series only starts 1976, so 10Y-2Y
    cannot reach 1940.
  * Equities splice Shiller's S&P composite (1871-) with ^GSPC from 1985.
  * Federal debt: gross debt, annual fiscal-year (FYGFD) until quarterly GFDEBTN
    starts in 1966. Debt/GDP is debt HELD BY THE PUBLIC (FYPUGDA188S annual to
    1969, FYGFGDQ188S quarterly after) - same definition across the splice. Gross
    debt/GDP (incl. trust funds) is higher and only exists from 1966; its latest
    value is quoted on-chart.
  * Gold is a monthly series 1915-present (macro/data/gold_monthly_1915.csv),
    supplied by the user and verified before use: no gaps or duplicates;
    annual values repeated monthly before 1968 (the $35 official era, with
    London free-market deviations such as 1949); month-END values thereafter;
    against Yahoo GC=F over 2000-2026 corr 0.99987, median |diff| 0.34%.
    Pre-Aug-1971 prices are policy-set, so the panel shades that era.

Sources: FRED, Yahoo Finance, Shiller (Yale).
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter
import pandas as pd, numpy as np, yfinance as yf, requests, io, os, warnings
warnings.filterwarnings("ignore")

START = "1940-01-01"
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e2e1dc"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
REC, NEG = "#ebe9e4", "#f6d9cf"


def fred(s):
    df = pd.read_csv(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={s}")
    df.columns = ["d", "v"]
    df["d"] = pd.to_datetime(df["d"])
    df["v"] = pd.to_numeric(df["v"], errors="coerce")
    return df.dropna().set_index("d")["v"]


def shiller_sp():
    r = requests.get("http://www.econ.yale.edu/~shiller/data/ie_data.xls",
                     timeout=60, headers={"User-Agent": "Mozilla/5.0"})
    df = pd.ExcelFile(io.BytesIO(r.content)).parse("Data", skiprows=7)
    df = df.rename(columns={df.columns[0]: "date", df.columns[1]: "P"})
    df = df[pd.to_numeric(df["date"], errors="coerce").notna()].copy()
    df["date"] = pd.to_numeric(df["date"])
    yr = df["date"].astype(int)
    mo = (df["date"] - yr).round(2).mul(100).round().astype(int).replace(0, 10)
    df["dt"] = pd.to_datetime(dict(year=yr, month=mo, day=1), errors="coerce")
    return df.dropna(subset=["dt"]).set_index("dt")["P"].astype(float).dropna()


def load():
    lt, gs = fred("LTGOVTBD"), fred("GS10")
    n10 = pd.concat([lt[lt.index < "1953-04-01"], gs]).sort_index()
    tb = fred("TB3MS")
    cpi = fred("CPIAUCNS")
    infl = (cpi / cpi.shift(12) - 1) * 100

    sp_old = shiller_sp()
    sp_new = yf.download("^GSPC", start="1985-01-01", interval="1mo",
                         progress=False, auto_adjust=True)["Close"]
    sp_new = (sp_new.iloc[:, 0] if hasattr(sp_new, "columns") else sp_new).dropna()
    sp_new.index = pd.to_datetime(sp_new.index).tz_localize(None)
    sp_new = sp_new.resample("MS").last()
    spx = pd.concat([sp_old[sp_old.index < "1985-01-01"], sp_new]).sort_index()

    gp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "gold_monthly_1915.csv")
    if not os.path.exists(gp):
        raise SystemExit(f"Missing {gp}: the 100-year gold CSV is not in git "
                         "(source/licence unknown). Put a Date,Value (MM/DD/YYYY) monthly file there.")
    gdf = pd.read_csv(gp)
    gold = pd.Series(gdf["Value"].astype(float).values,
                     index=pd.to_datetime(gdf["Date"], format="%m/%d/%Y")).sort_index()

    fy, qd = fred("FYGFD") / 1e3, fred("GFDEBTN") / 1e6          # both -> $ trillions
    debt = pd.concat([fy[fy.index < "1966-01-01"], qd]).sort_index()
    dg_old, dg_new = fred("FYPUGDA188S"), fred("FYGFGDQ188S")
    dgdp = pd.concat([dg_old[dg_old.index < "1970-01-01"], dg_new]).sort_index()

    d = {"n10": n10, "tb": tb, "infl": infl, "unemp": fred("UNRATE"),
         "spx": spx, "gold": gold, "rec": fred("USREC"),
         "debt": debt, "dgdp": dgdp, "dgross": fred("GFDEGDQ188S")}
    d["real"] = (n10 - infl.reindex(n10.index).ffill()).dropna()
    d["curve"] = (n10 - tb.reindex(n10.index).ffill()).dropna()
    return {k: v[v.index >= START] for k, v in d.items()}


def rec_bands(ax, rec):
    on = None
    for dt, v in rec.items():
        if v == 1 and on is None:
            on = dt
        elif v == 0 and on is not None:
            ax.axvspan(on, dt, color=REC, zorder=0, lw=0)
            on = None
    if on is not None:
        ax.axvspan(on, rec.index[-1], color=REC, zorder=0, lw=0)


def style(ax, label, color, last_txt, note=None):
    ax.set_facecolor(SURFACE)
    ax.grid(True, axis="y", color=GRID, lw=0.8, ls="-", zorder=1)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.spines["bottom"].set_linewidth(0.8)
    ax.tick_params(colors=INK2, labelsize=9, length=0)
    ax.text(0.005, 0.95, label, transform=ax.transAxes, ha="left", va="top",
            fontsize=11, fontweight="bold", color=INK)
    ax.text(0.995, 0.95, last_txt, transform=ax.transAxes, ha="right", va="top",
            fontsize=10, fontweight="bold", color=color)
    if note:
        ax.text(0.005, 0.06, note, transform=ax.transAxes, fontsize=8.5, color=INK2)


def main():
    d = load()
    n10, infl, real, curve = d["n10"], d["infl"], d["real"], d["curve"]
    un, spx, gold, rec = d["unemp"], d["spx"], d["gold"], d["rec"]
    debt, dgdp, dgross = d["debt"], d["dgdp"], d["dgross"]

    H = 26.0
    fig, axes = plt.subplots(9, 1, figsize=(13, H), sharex=True,
                             gridspec_kw={"hspace": 0.17})
    fig.patch.set_facecolor(SURFACE)

    ax = axes[0]
    rec_bands(ax, rec)
    ax.plot(n10.index, n10, color=BLUE, lw=1.8, zorder=4)
    ax.set_ylim(0, n10.max() * 1.30)
    style(ax, "10Y Treasury yield  (%)", BLUE, f"{n10.iloc[-1]:.2f}%",
          "pre-1953 = long-term govt bond yield (longer maturity, sits ~0.4pp high)")

    ax = axes[1]
    rec_bands(ax, rec)
    ax.fill_between(infl.index, infl, 0, where=infl < 0, color=NEG, zorder=2, interpolate=True)
    ax.axhline(0, color=INK2, lw=1.0, zorder=3)
    ax.plot(infl.index, infl, color=ORANGE, lw=1.8, zorder=4)
    ax.set_ylim(min(infl.min() * 1.2, -4), infl.max() * 1.28)
    style(ax, "CPI inflation, YoY  (%)", ORANGE, f"{infl.iloc[-1]:.1f}%")

    ax = axes[2]
    rec_bands(ax, rec)
    ax.fill_between(real.index, real, 0, where=real < 0, color=NEG, zorder=2, interpolate=True)
    ax.axhline(0, color=INK2, lw=1.0, zorder=3)
    ax.plot(real.index, real, color=BLUE, lw=1.8, zorder=4)
    ax.set_ylim(real.min() * 1.2, real.max() * 1.45)
    style(ax, "Ex-post REAL 10Y yield  (%)  - nominal minus trailing CPI", BLUE,
          f"{real.iloc[-1]:.2f}%",
          "below 0 = savers lose to inflation (shaded) - the gold-friendly regime")

    ax = axes[3]
    rec_bands(ax, rec)
    ax.fill_between(curve.index, curve, 0, where=curve < 0, color=NEG, zorder=2, interpolate=True)
    ax.axhline(0, color=INK2, lw=1.0, zorder=3)
    ax.plot(curve.index, curve, color=BLUE, lw=1.8, zorder=4)
    ax.set_ylim(curve.min() * 1.25, curve.max() * 1.35)
    style(ax, "Yield curve: 10Y - 3M  (pp)", BLUE, f"{curve.iloc[-1]:+.2f} pp",
          "2Y series starts 1976, so 10Y-3M is used for the long run")

    ax = axes[4]
    rec_bands(ax, rec)
    ax.plot(un.index, un, color=ORANGE, lw=1.8, zorder=4)
    ax.set_ylim(0, un.max() * 1.30)
    style(ax, "US unemployment rate  (%)", ORANGE, f"{un.iloc[-1]:.1f}%", "series begins 1948")

    ax = axes[5]
    rec_bands(ax, rec)
    ax.plot(spx.index, spx, color=AQUA, lw=1.8, zorder=4)
    ax.set_yscale("log")
    ax.minorticks_off()
    ax.set_yticks([10, 50, 250, 1250, 6250])
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, p: f"{v:,.0f}"))
    ax.set_ylim(spx.min() * 0.42, spx.max() * 2.2)   # floor low enough that the source note clears the line
    style(ax, "S&P 500  (log scale)", AQUA, f"{spx.iloc[-1]:,.0f}",
          "Shiller composite pre-1985, ^GSPC after")

    # Fiscal panels sit directly above gold so the eye can compare them.
    ax = axes[6]
    rec_bands(ax, rec)
    ax.plot(debt.index, debt, color=BLUE, lw=1.8, zorder=4)
    ax.set_yscale("log")
    ax.minorticks_off()
    ax.set_yticks([0.1, 1, 10])
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, p: f"${v:g}T"))
    ax.set_ylim(debt.min() * 0.25, debt.max() * 2.6)
    style(ax, "Federal debt, gross  ($ trillions, log scale)", BLUE, f"${debt.iloc[-1]:.1f}T",
          "annual fiscal-year totals pre-1966, quarterly after")

    ax = axes[7]
    rec_bands(ax, rec)
    ax.plot(dgdp.index, dgdp, color=BLUE, lw=1.8, zorder=4)
    ax.set_ylim(0, dgdp.max() * 1.32)
    pk_dt, pk = dgdp.idxmax(), dgdp.max()
    ax.text(pk_dt + pd.DateOffset(years=2), pk, f"{pk_dt:%Y} WWII peak {pk:.0f}%",
            fontsize=8.5, color=INK2, va="center")
    style(ax, "Federal debt held by the public  (% of GDP)", BLUE, f"{dgdp.iloc[-1]:.0f}%",
          f"gross debt incl. trust funds is higher: {dgross.iloc[-1]:.0f}% of GDP (series from 1966)")

    ax = axes[8]
    # Fixed/official era first (so recession bands draw over it): the flat line
    # there is policy, not a market, and should not read as price stability.
    ax.axvspan(pd.Timestamp("1940-01-01"), pd.Timestamp("1971-08-15"),
               color="#f1f0ec", zorder=0, lw=0)
    rec_bands(ax, rec)
    ax.axvline(pd.Timestamp("1971-08-15"), color=INK2, lw=1.0, zorder=3, ymin=0.14)  # stop above the note
    ax.text(pd.Timestamp("1972-06-01"), gold.max() * 0.9, "Aug 1971\nwindow closed",
            fontsize=8.5, color=INK2, va="top")
    ax.plot(gold.index, gold, color=AQUA, lw=1.8, zorder=4)
    ax.set_yscale("log")
    ax.minorticks_off()
    ax.set_yticks([25, 100, 400, 1600, 6400])
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, p: f"{v:,.0f}"))
    ax.set_ylim(gold.min() * 0.35, gold.max() * 2.4)
    pk = gold.idxmax()
    style(ax, "Gold  ($/oz, log scale)", AQUA, f"${gold.iloc[-1]:,.0f}",
          f"fixed/official era shaded (annual values pre-1968) - month-end prices after - "
          f"peak ${gold.max():,.0f} {pk:%b %Y}")

    ax.xaxis.set_major_locator(mdates.YearLocator(10))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    # Title/subtitle/footer positioned in inches so they survive height changes.
    fig.suptitle("The long run - rates, inflation, debt and assets since 1940",
                 x=0.055, y=1 - 0.17 / H, ha="left", fontsize=17, fontweight="bold", color=INK)
    fig.text(0.055, 1 - 0.605 / H,
             "Grey bands = NBER recessions.  blue = rates/policy/fiscal - orange = real economy - aqua = assets.",
             ha="left", fontsize=10.5, color=INK2)
    fig.text(0.055, 0.15 / H,
             "Sources: FRED (LTGOVTBD, GS10, TB3MS, CPIAUCNS, UNRATE, USREC, FYGFD, GFDEBTN, FYPUGDA188S, "
             "FYGFGDQ188S, GFDEGDQ188S),\n"
             "Yahoo Finance (^GSPC), Shiller/Yale (S&P pre-1985), gold monthly 1915- (verified vs GC=F).",
             ha="left", va="bottom", fontsize=8.5, color=INK2, linespacing=1.5)
    fig.subplots_adjust(left=0.055, right=0.988, top=1 - 1.03 / H, bottom=0.9 / H)
    fig.savefig("macro_longrun.png", dpi=150, facecolor=SURFACE)
    print("wrote macro_longrun.png")

    tbl = pd.DataFrame({"10Y": n10, "CPI_YoY": infl, "RealYield": real,
                        "Curve10Y3M": curve, "Unemp": un, "SP500": spx,
                        "Debt_T": debt, "DebtPublic_pctGDP": dgdp, "Gold": gold})
    tbl.resample("YS").last().round(2).to_csv("macro_longrun.csv")
    print("wrote macro_longrun.csv")

    print("\n=== EX-POST REAL 10Y YIELD by decade (mean %) ===")
    dec = real.groupby((real.index.year // 10) * 10).mean().round(2)
    for k, v in dec.items():
        print(f"  {k}s: {v:+.2f}%   {'NEGATIVE' if v < 0 else ''}")
    neg = (real < 0)
    print(f"\n  months with negative real yield: {neg.sum()} of {len(real)} ({neg.mean()*100:.0f}%)")
    print(f"  1940s share negative: {neg['1940':'1949'].mean()*100:.0f}%"
          f" | 1970s: {neg['1970':'1979'].mean()*100:.0f}%"
          f" | 2020s: {neg['2020':'2029'].mean()*100:.0f}%")


if __name__ == "__main__":
    main()
