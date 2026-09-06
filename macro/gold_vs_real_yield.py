"""
Gold vs the 10Y real interest rate, 2000-present.

The textbook relationship is a downward-sloping cloud: higher real yields ->
lower gold (gold pays no coupon, so real yields are its opportunity cost).
Colour is SEQUENTIAL by year (one hue, light->dark) because time is a magnitude
here, not an identity - so the eye reads the drift of the regime, not categories.
"""
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import numpy as np
import pandas as pd, yfinance as yf, warnings
warnings.filterwarnings("ignore")

SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e2e1dc"
ACCENT = "#eb6834"
# Truncate the ramp: stock 'Blues' starts near-white and the earliest points
# vanish against an off-white surface. Floor it at 0.28 so every year is visible.
from matplotlib.colors import LinearSegmentedColormap
BLUES = LinearSegmentedColormap.from_list(
    "blues_hi", plt.get_cmap("Blues")(np.linspace(0.28, 1.0, 256)))

def fred(s):
    df = pd.read_csv(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={s}")
    df.columns = ["d", "v"]; df["d"] = pd.to_datetime(df["d"])
    df["v"] = pd.to_numeric(df["v"], errors="coerce")
    return df.dropna().set_index("d")["v"]

real = fred("REAINTRATREARAT10Y")
g = yf.download("GC=F", start="2000-01-01", interval="1mo", progress=False, auto_adjust=True)["Close"]
g = (g.iloc[:, 0] if hasattr(g, "columns") else g).dropna()
g.index = pd.to_datetime(g.index).tz_localize(None); g = g.resample("MS").last()

df = pd.DataFrame({"real": real, "gold": g}).dropna()
df["yr"] = df.index.year

fig, ax = plt.subplots(figsize=(11, 8))
fig.patch.set_facecolor(SURFACE); ax.set_facecolor(SURFACE)
sc = ax.scatter(df["real"], df["gold"], c=df["yr"], cmap=BLUES,
                s=34, edgecolor=SURFACE, linewidth=0.6, zorder=3)   # 2px surface ring

recent = df.tail(12)
ax.scatter(recent["real"], recent["gold"], s=70, facecolor="none",
           edgecolor=ACCENT, linewidth=2, zorder=4, label="last 12 months")
last = df.iloc[-1]
ax.annotate(f"{df.index[-1]:%b %Y}\n{last['real']:.2f}% real · ${last['gold']:,.0f}",
            (last["real"], last["gold"]), textcoords="offset points", xytext=(-14, 16),
            ha="right", fontsize=10, fontweight="bold", color=ACCENT)

ax.set_yscale("log"); ax.minorticks_off()
ax.set_yticks([300, 600, 1200, 2400, 4800])
ax.yaxis.set_major_formatter(FuncFormatter(lambda v, p: f"${v:,.0f}"))
ax.axvline(0, color=INK2, lw=1.0, zorder=2)
ax.grid(True, color=GRID, lw=0.8, ls="-", zorder=1); ax.set_axisbelow(True)
for sp in ("top", "right"): ax.spines[sp].set_visible(False)
for sp in ("left", "bottom"): ax.spines[sp].set_color(GRID); ax.spines[sp].set_linewidth(0.8)
ax.tick_params(colors=INK2, labelsize=10, length=0)
ax.set_xlabel("10Y real interest rate  (%)", fontsize=11, color=INK2)
ax.set_ylabel("Gold  ($/oz, log scale)", fontsize=11, color=INK2)
ax.legend(loc="lower left", frameon=False, fontsize=10, labelcolor=INK2)

cb = fig.colorbar(sc, ax=ax, pad=0.015); cb.set_label("year", color=INK2, fontsize=10)
cb.ax.tick_params(colors=INK2, labelsize=9, length=0); cb.outline.set_visible(False)

fig.suptitle("Gold vs real yields — has the textbook link broken?",
             x=0.055, y=0.978, ha="left", fontsize=15, fontweight="bold", color=INK)
fig.text(0.055, 0.9385,
         "Textbook: higher real yields → lower gold. Points drift up-and-right after 2023 — "
         "gold rising WITH real yields.", ha="left", fontsize=10, color=INK2)
fig.text(0.055, 0.022, "Sources: FRED (REAINTRATREARAT10Y), Yahoo Finance (GC=F). Monthly.",
         ha="left", fontsize=8.5, color=INK2)
fig.subplots_adjust(left=0.088, right=1.0, top=0.895, bottom=0.085)
fig.savefig("gold_vs_real_yield.png", dpi=150, facecolor=SURFACE)
print("wrote gold_vs_real_yield.png")

for lo, hi, lbl in [(2003, 2012, "2003-2012"), (2013, 2021, "2013-2021"), (2022, 2026, "2022-2026")]:
    w = df[(df["yr"] >= lo) & (df["yr"] <= hi)]
    print(f"  {lbl}: corr(real, log gold) = {w['real'].corr(w['gold'].apply(lambda x: pd.np.log(x)) if False else w['gold'].pipe(lambda s: s.apply(float).pipe(lambda t: t.rank()))):+.2f}"
          f"   real {w['real'].min():.2f}..{w['real'].max():.2f}%   gold ${w['gold'].min():,.0f}..${w['gold'].max():,.0f}")
