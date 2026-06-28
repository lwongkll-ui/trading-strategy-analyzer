"""
Silver Miners — Weekly Review (Job 2 in CRON_SPEC.md).
=====================================================
Computes WEEKLY-timeframe indicators and emits the "Key weekly observations"
analysis (silver structure, oversold STC, distribution volume, relative
strength, RSI washout check, bounce-vs-reversal test) plus a weekly-metrics
table image, posted to the Discord 'Silver' thread.

Usage:
    python weekly_review.py            # generate + post
    python weekly_review.py --no-post  # generate only
"""
from __future__ import annotations
import argparse
import os

import post_to_discord as ptd          # reuse posting + screenshot helpers (sets UTF-8 stdout)
from config import SILVER_MINERS, SILVER_SPOT
from fetcher import fetch_ohlcv
from indicators import compute_all
from datetime import datetime

REPORTS = ptd.REPORTS


# ── weekly data ──────────────────────────────────────────────────────────────

def _consec_down(close) -> int:
    n = 0
    for i in range(len(close) - 1, 0, -1):
        if close.iloc[i] < close.iloc[i - 1]:
            n += 1
        else:
            break
    return n


def _bb_pct(row) -> float | None:
    span = row["bb_upper"] - row["bb_lower"]
    return (row["Close"] - row["bb_lower"]) / span * 100 if span else None


def compute_weekly(stocks_order: list[str]) -> dict:
    rows = []
    for t in stocks_order:
        w = compute_all(fetch_ohlcv(t, "5y", "1wk"))
        c = w["Close"]
        last = w.iloc[-1]
        rows.append({
            "tk": t,
            "close": float(last["Close"]),
            "chg1": (c.iloc[-1] / c.iloc[-2] - 1) * 100 if len(c) > 1 else None,
            "chg13": (c.iloc[-1] / c.iloc[-14] - 1) * 100 if len(c) > 14 else None,
            "rsi": float(last["rsi"]),
            "stcf": float(last["stc_fast"]),
            "stcs": float(last["stc_slow"]),
            "macdh": float(last["macd_hist"]),
            "vol": float(last["vol_ratio"]) if last["vol_ratio"] == last["vol_ratio"] else None,
            "bb": _bb_pct(last),
            "sma50": float(last["sma50"]) if last["sma50"] == last["sma50"] else None,
            "above_sma200": bool(last["Close"] > last["sma200"]) if last["sma200"] == last["sma200"] else False,
        })

    sw = compute_all(fetch_ohlcv(SILVER_SPOT, "5y", "1wk"))
    sc = sw["Close"]
    peak = float(sw["High"].max())
    low = float(sw["Low"].min())
    now = float(sc.iloc[-1])
    silver = {
        "now": now, "consec_down": _consec_down(sc), "peak": peak, "low": low,
        "pct_from_peak": (now / peak - 1) * 100,
        "fib618": peak - 0.618 * (peak - low),
        "fib786": peak - 0.786 * (peak - low),
        "sma50": float(sw["sma50"].iloc[-1]),
        "stcf": float(sw["stc_fast"].iloc[-1]), "stcs": float(sw["stc_slow"].iloc[-1]),
        "rsi": float(sw["rsi"].iloc[-1]), "macdh": float(sw["macd_hist"].iloc[-1]),
        "chg1": (sc.iloc[-1] / sc.iloc[-2] - 1) * 100 if len(sc) > 1 else None,
    }
    return {"rows": rows, "silver": silver}


# ── narrative ────────────────────────────────────────────────────────────────

def _rng(vals):
    vals = [v for v in vals if v is not None]
    return (min(vals), max(vals)) if vals else (None, None)


def build_observations(d: dict) -> str:
    rows, s = d["rows"], d["silver"]
    by_tk = {r["tk"]: r for r in rows}

    # leader = least-negative 1-week move
    leader = max(rows, key=lambda r: (r["chg1"] if r["chg1"] is not None else -999))
    peers = [r for r in rows if r["tk"] != leader["tk"]]
    p1lo, p1hi = _rng([r["chg1"] for r in peers])
    p13lo, p13hi = _rng([r["chg13"] for r in peers])
    prlo, prhi = _rng([r["rsi"] for r in peers])

    # oversold STC: stc both crushed; exceptions = stc_slow meaningfully off zero
    exceptions = [r for r in rows if r["stcs"] > 5]
    exc_txt = (", ".join(f"{r['tk']} {r['stcf']:.0f}/{r['stcs']:.0f}" for r in exceptions)
               if exceptions else "none")
    n_crushed = len(rows) - len(exceptions)

    # distribution: above-average volume on a down week
    distrib = [r for r in rows if (r["vol"] and r["vol"] >= 1.5 and (r["chg1"] or 0) < 0)]
    distrib.sort(key=lambda r: -(r["vol"] or 0))

    rlo, rhi = _rng([r["rsi"] for r in rows])
    blo, bhi = _rng([r["bb"] for r in rows])

    # reversal conditions
    macd_pos = sum(1 for r in rows if r["macdh"] > 0)
    stcs_up = sum(1 for r in rows if r["stcs"] > 20)
    silver_above_sma50 = s["now"] > s["sma50"]

    if s["now"] < s["fib786"]:
        verdict = "BEAR CONFIRMED — silver below the 78.6% weekly fib; weekly structure broken."
    elif s["now"] < s["fib618"]:
        verdict = "BEARISH FLAG — silver below the 61.8% weekly fib ($57.04); critical support broken."
    elif silver_above_sma50 and macd_pos >= 4 and stcs_up >= 1:
        verdict = "RECOVERY BUILDING — weekly reversal conditions starting to line up."
    else:
        verdict = "WATCH AND WAIT — extreme oversold, bounce setup, but no confirmed reversal."

    dist_now = s["now"] - s["fib618"]
    L = []
    L.append(f"# Silver Miners — Weekly Review ({datetime.now():%Y-%m-%d})")
    L.append(f"**Verdict: {verdict}**")
    L.append("")
    L.append("## Key weekly observations")
    L.append("")
    # 1 — silver structure
    L.append(f"**1. Silver: {s['consec_down']} consecutive down weeks — approaching major support.** "
             f"Silver is down {abs(s['pct_from_peak']):.1f}% from its peak (~${s['peak']:.0f}). "
             f"The 61.8% weekly Fibonacci is **${s['fib618']:.2f}** — ${abs(dist_now):.2f} "
             f"{'below' if dist_now > 0 else 'above'} current (${s['now']:.2f}), the first major weekly support. "
             f"A weekly close below ${s['fib618']:.0f} targets **${s['fib786']:.2f}** (78.6% fib).")
    L.append("")
    # 2 — oversold STC
    L.append(f"**2. Weekly STC ~0 — extreme oversold.** {n_crushed} of {len(rows)} names show weekly "
             f"STC-Fast and STC-Slow at/near zero (exception: {exc_txt}). An extreme reading that often "
             f"precedes sharp bounces — but it is NOT a buy on its own: the STC must TURN UP from 0, "
             f"confirmed by weekly MACD-histogram improvement (currently {macd_pos}/{len(rows)} positive).")
    L.append("")
    # 3 — distribution volume
    if distrib:
        d0 = distrib[0]
        L.append(f"**3. {d0['tk']}: high volume on a down week — distribution.** {d0['tk']} printed "
                 f"{d0['vol']:.1f}× average weekly volume while falling {d0['chg1']:.1f}% — supply "
                 f"overwhelming demand (institutional selling). Other names ran roughly average volume "
                 f"(neutral — no panic, but no accumulation either).")
    else:
        L.append("**3. Volume neutral.** No name shows clear above-average down-week volume — "
                 "no distribution spike, but no accumulation either.")
    L.append("")
    # 4 — relative strength leader
    lr = leader
    L.append(f"**4. {lr['tk']}: relative-strength leader.** {lr['tk']} fell only {lr['chg1']:.1f}% this "
             f"week vs {p1hi:.1f}% to {p1lo:.1f}% for the rest. Its 13-week return is "
             f"{lr['chg13']:+.1f}% while peers are {p13hi:+.1f}% to {p13lo:+.1f}%. Weekly RSI {lr['rsi']:.0f} "
             f"vs {prlo:.0f}-{prhi:.0f} for peers; weekly SMA50 ${lr['sma50']:.2f} sits well below price — "
             f"most room to breathe. Watch it first for a recovery signal.")
    L.append("")
    # 5 — RSI washout check
    L.append(f"**5. Weekly RSI {rlo:.0f}-{rhi:.0f} — not yet washout.** Despite the extreme STC, weekly RSI "
             f"is only neutral. True capitulation bottoms usually reach RSI 25-35. The STC has been crushed "
             f"by the speed of the drop, but price hasn't reached levels where value buyers step in hard — "
             f"more downside possible before a lasting bottom.")
    L.append("")
    # 6 — bounce vs reversal
    bb_txt = f"{blo:.0f}-{bhi:.0f}%" if blo is not None else "low"
    L.append(f"**6. Bounce vs. reversal.** Weekly STC ~0 and Bollinger %B {bb_txt} make a technical bounce "
             f"likely. A lasting reversal needs ALL of: (1) silver weekly close above **${s['sma50']:.2f}** "
             f"(weekly SMA50), (2) weekly MACD histogram positive, (3) weekly STC-Slow above 20. "
             f"Met today: silver>{s['sma50']:.0f} = {silver_above_sma50}; MACD+ = {macd_pos}/{len(rows)}; "
             f"STC-S>20 = {stcs_up}/{len(rows)}. Trade bounces cautiously; don't call a reversal yet.")
    L.append("")
    L.append("_Tables (weekly metrics) in the image above. Weekly timeframe; price/technical only "
             f"(fundamentals omitted). Generated {datetime.now():%Y-%m-%d %H:%M}._")
    return "\n".join(L)


# ── weekly table image ───────────────────────────────────────────────────────

def render_weekly_html(d: dict) -> str:
    rows, s = d["rows"], d["silver"]

    def col(v, fmt, cls=""):
        if v is None:
            return '<td class="num">—</td>'
        return f'<td class="num {cls}">{format(v, fmt)}</td>'

    def pct(v):
        if v is None:
            return '<td class="num">—</td>'
        return f'<td class="num {"pos" if v >= 0 else "neg"}">{v:+.1f}%</td>'

    def stc(v):
        cls = "neg" if v <= 5 else ("pos" if v >= 20 else "")
        return f'<td class="num {cls}">{v:.0f}</td>'

    body = ""
    for r in sorted(rows, key=lambda r: (r["chg13"] if r["chg13"] is not None else -999), reverse=True):
        vol_cls = "neg" if (r["vol"] and r["vol"] >= 1.5 and (r["chg1"] or 0) < 0) else ""
        body += (f'<tr><td class="tk">{r["tk"]}</td>'
                 f'{col(r["close"], ".2f")}{pct(r["chg1"])}{pct(r["chg13"])}'
                 f'{col(r["rsi"], ".0f")}{stc(r["stcf"])}{stc(r["stcs"])}'
                 f'{col(r["macdh"], ".2f")}{col(r["vol"], ".2f", vol_cls)}'
                 f'{col(r["bb"], ".0f")}{col(r["sma50"], ".2f")}</tr>')

    sub = (f"{s['consec_down']} down weeks · {s['pct_from_peak']:.1f}% from ${s['peak']:.0f} peak · "
           f"61.8% fib ${s['fib618']:.2f} · 78.6% ${s['fib786']:.2f} · weekly SMA50 ${s['sma50']:.2f}")
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
      body{{margin:0;background:#0d0d0f;color:#e6e6ea;font-family:'Segoe UI',system-ui,sans-serif;padding:22px;width:900px;}}
      h1{{font-size:19px;margin:0 0 2px;}} .sub{{color:#8a8a93;font-size:12.5px;margin:0 0 14px;}}
      .silver{{color:#d9a441;font-weight:600;font-size:13px;margin:0 0 16px;}}
      table{{width:100%;border-collapse:collapse;font-size:13.5px;}}
      th,td{{padding:7px 8px;border-bottom:1px solid #23232a;text-align:left;}}
      th{{color:#8a8a93;font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.03em;}}
      .num{{text-align:right;font-variant-numeric:tabular-nums;}}
      .tk{{font-weight:700;}} .pos{{color:#5bbd62;}} .neg{{color:#e3604a;}}
    </style></head><body>
      <h1>Silver Miners — Weekly Metrics</h1>
      <div class="sub">{datetime.now():%B %d, %Y} · weekly timeframe</div>
      <div class="silver">Silver ${s['now']:.2f} — {sub}</div>
      <table>
        <tr><th>Ticker</th><th class="num">Close</th><th class="num">1W</th><th class="num">13W</th>
            <th class="num">RSI</th><th class="num">STC-F</th><th class="num">STC-S</th>
            <th class="num">MACDh</th><th class="num">Vol×</th><th class="num">%B</th><th class="num">SMA50</th></tr>
        {body}
      </table>
      <div class="sub" style="margin-top:12px;">STC red ≤5 (crushed) · green ≥20 (turning up) · Vol× red = high volume on a down week (distribution)</div>
    </body></html>"""


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-post", action="store_true")
    args = ap.parse_args()

    os.makedirs(REPORTS, exist_ok=True)
    order = list(SILVER_MINERS.keys())
    print("Computing weekly indicators...")
    d = compute_weekly(order)

    obs = build_observations(d)
    md_path = os.path.join(REPORTS, "weekly_review.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(obs)
    html_path = os.path.join(REPORTS, "weekly_tables.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(render_weekly_html(d))
    print(f"Wrote {md_path}\nWrote {html_path}")

    png = ptd.try_screenshot(html_path, os.path.join(REPORTS, "weekly_tables.png"), width=900, height=10)

    if args.no_post:
        print(f"\n--no-post. weekly PNG: {png}")
        print(f"\n--- observations ({len(obs)} chars) ---\n{obs}")
        return

    ok = ptd.post_summary(obs, [png] if png else [])
    print("Posted OK" if ok else "Post FAILED")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
