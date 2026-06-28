"""
Silver Miners — HTML Support-Ladder Dashboard
=============================================
Generates a single self-contained HTML file showing all 6 miners as
"support ladder" cards (Fibonacci retracement + SMA50/SMA200/EMA21 rungs),
a macro strip, and a bull/bear regime banner.

Reuses the same data pipeline as main.py (fetcher / indicators / strategy).

Usage:
    python dashboard.py                 # writes reports/dashboard.html
    python dashboard.py --open          # also open it in the browser
    python dashboard.py --out path.html # custom output path
"""
from __future__ import annotations
import argparse
import os
import sys
import io
import webbrowser
from datetime import datetime

if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import pandas as pd

from config import SILVER_MINERS, SILVER_SPOT, SMA_LONG
from fetcher import fetch_all_data, fetch_macro, fetch_ohlcv
from indicators import compute_all
from fundamentals import score_fundamentals
from market_context import analyze_macro
from strategy import generate_historical_signals, get_current_signal

FIBS = [(0.382, "38.2%"), (0.50, "50.0%"), (0.618, "61.8%")]


# ── data assembly ────────────────────────────────────────────────────────────

def _pct(level: float, price: float) -> float:
    return (level - price) / price * 100.0


def build_stock(ticker: str, macro_score: int) -> dict | None:
    try:
        data = fetch_all_data(ticker)
    except Exception as e:
        print(f"  ! {ticker}: fetch failed ({e})")
        return None

    df_d = compute_all(data["daily"])
    df_w = compute_all(data["weekly"]) if not data["weekly"].empty else data["weekly"]
    df_h = compute_all(data["hourly"]) if not data["hourly"].empty else data["hourly"]
    df_d = generate_historical_signals(df_d)
    if not df_w.empty:
        df_w = generate_historical_signals(df_w)

    fund = data["fundamentals"]
    fund_score, _, _ = score_fundamentals(fund)
    cur = get_current_signal(df_d, df_w, df_h, fund_score, macro_score)

    price = cur.get("price") or float(df_d["Close"].iloc[-1])
    sma50 = cur.get("sma50")
    sma200 = cur.get("sma200")
    ema21 = float(df_d["ema21"].iloc[-1]) if "ema21" in df_d else None

    # Fib swing: retracement of the 52-week range (high -> low), from clean
    # fundamentals fields, falling back to the daily window if absent.
    swing_high = fund.get("fifty_two_high") or float(df_d["High"].max())
    swing_low = fund.get("fifty_two_low") or float(df_d["Low"].min())
    rng = swing_high - swing_low

    rungs = []  # (sort_price, label, level, descriptor)
    for ratio, name in FIBS:
        level = swing_high - ratio * rng
        desc = {"38.2%": "shallow retr.", "50.0%": "key mid-swing",
                "61.8%": "golden-ratio support"}[name]
        rungs.append((level, f"Fib {name}", level, desc))
    if sma50:
        rungs.append((sma50, "SMA 50", sma50, "mid-term MA"))
    if sma200:
        rungs.append((sma200, "SMA 200", sma200, "regime line"))
    if ema21:
        rungs.append((ema21, "EMA 21", ema21, "short-term MA"))

    # sort high -> low, attach side/pct relative to price
    rungs.sort(key=lambda x: x[0], reverse=True)
    ladder = []
    for _, label, level, desc in rungs:
        pct = _pct(level, price)
        ladder.append({
            "label": label, "level": level, "pct": pct,
            "side": "resistance" if level >= price else "support",
            "desc": desc,
        })

    # nearest support / resistance for the note
    res = [r for r in ladder if r["side"] == "resistance"]
    sup = [r for r in ladder if r["side"] == "support"]
    nearest_res = min(res, key=lambda r: r["pct"]) if res else None
    nearest_sup = max(sup, key=lambda r: r["pct"]) if sup else None

    high52 = fund.get("fifty_two_high")
    pct_from_high = (price - high52) / high52 * 100 if high52 else None

    return {
        "ticker": ticker,
        "company": SILVER_MINERS.get(ticker, ticker),
        "price": price,
        "regime": cur.get("regime", "BEAR"),
        "above_sma200": bool(sma200 and price > sma200),
        "score": cur.get("total_score"),
        "rsi": cur.get("rsi"),
        "stc_f": cur.get("stc_fast"),
        "stc_s": cur.get("stc_slow"),
        "trend": "UP" if cur.get("regime") == "BULL" else "DOWN",
        "pct_from_high": pct_from_high,
        "ladder": ladder,
        "nearest_res": nearest_res,
        "nearest_sup": nearest_sup,
        "sma200": sma200,
    }


def build_macro() -> dict:
    raw = fetch_macro()
    ctx = analyze_macro(raw)

    def last_close(key):
        df = raw.get(key)
        return float(df["Close"].iloc[-1]) if isinstance(df, pd.DataFrame) and not df.empty else None

    def chg_1m(key):
        df = raw.get(key)
        if isinstance(df, pd.DataFrame) and len(df) > 21:
            return (df["Close"].iloc[-1] / df["Close"].iloc[-22] - 1) * 100
        return None

    # silver SMA200 needs >6mo history -> dedicated fetch
    silver_sma200 = None
    try:
        sdf = fetch_ohlcv(SILVER_SPOT, "2y", "1d")
        if len(sdf) >= SMA_LONG:
            silver_sma200 = float(sdf["Close"].rolling(SMA_LONG).mean().iloc[-1])
    except Exception:
        pass

    return {
        "ctx": ctx,
        "silver": ctx.get("ag_price"),
        "silver_1m": ctx.get("ag_1m"),
        "silver_sma200": silver_sma200,
        "sil_etf": last_close("sil"),
        "sil_1m": ctx.get("sil_1m"),
        "dxy": ctx.get("dxy_px"),
        "dxy_1m": ctx.get("dxy_1m"),
        "vix": ctx.get("vix_px"),
        "vix_1m": chg_1m("vix"),
        "gs_ratio": ctx.get("gs_ratio"),
    }


# ── HTML rendering ───────────────────────────────────────────────────────────

def _fmt_price(v):
    if v is None:
        return "—"
    return f"{v:,.3f}" if v < 10 else f"{v:,.2f}"


def _pct_span(v, invert=False):
    if v is None:
        return '<span class="dim">—</span>'
    up = v >= 0
    cls = "pos" if (up != invert) else "neg"
    word = "above" if up else "below"
    return f'<span class="{cls}">{abs(v):.1f}% {word}</span>'


def render_macro_card(label, value, sub):
    return f"""
    <div class="mcard">
      <div class="mlabel">{label}</div>
      <div class="mval">{value}</div>
      <div class="msub">{sub}</div>
    </div>"""


def render_ladder_rows(s):
    rows = []
    price_inserted = False
    for r in s["ladder"]:
        # insert the PRICE marker once we cross below current price
        if not price_inserted and r["side"] == "support":
            rows.append(f"""
        <div class="rung price">
          <div class="rlabel">PRICE</div>
          <div class="rlevel">${_fmt_price(s['price'])}</div>
          <div class="rpct"></div>
          <div class="rdesc"></div>
        </div>""")
            price_inserted = True
        side_cls = "res" if r["side"] == "resistance" else "sup"
        rows.append(f"""
        <div class="rung {side_cls}">
          <div class="rlabel">{r['label']}</div>
          <div class="rlevel">${_fmt_price(r['level'])}</div>
          <div class="rpct">{_pct_span(r['pct'])}</div>
          <div class="rdesc">{r['desc']}</div>
        </div>""")
    if not price_inserted:  # price below all rungs
        rows.append(f"""
        <div class="rung price">
          <div class="rlabel">PRICE</div>
          <div class="rlevel">${_fmt_price(s['price'])}</div>
          <div class="rpct"></div><div class="rdesc"></div>
        </div>""")
    return "".join(rows)


def render_note(s):
    bits = []
    if s["nearest_sup"]:
        n = s["nearest_sup"]
        bits.append(f"Nearest support {n['label']} (${_fmt_price(n['level'])}, {abs(n['pct']):.1f}% below).")
    if s["nearest_res"]:
        n = s["nearest_res"]
        bits.append(f"Overhead {n['label']} (${_fmt_price(n['level'])}, {n['pct']:.1f}% above).")
    return " ".join(bits)


def render_stock_card(s):
    regime_cls = "bull" if s["above_sma200"] else "bear"
    regime_tag = "Bull" if s["above_sma200"] else "Bear"
    status = ("Still in bull regime — above SMA200" if s["above_sma200"]
              else "Bear confirmed — below SMA200")
    return f"""
    <div class="card {regime_cls}">
      <div class="chead">
        <div>
          <div class="ticker">{s['ticker']}</div>
          <div class="company">{s['company']}</div>
        </div>
        <div class="tag {regime_cls}">{regime_tag}</div>
      </div>
      <div class="price">{_fmt_price(s['price'])}
        <span class="fromhigh">{f"{s['pct_from_high']:.1f}% from 52W high" if s['pct_from_high'] is not None else ""}</span>
      </div>
      <div class="status {regime_cls}">{status}</div>
      <div class="ladder-title">Key levels (resistance above / support below)</div>
      <div class="ladder">{render_ladder_rows(s)}</div>
      <div class="note">{render_note(s)}</div>
      <div class="footer">
        <span>RSI <b>{s['rsi']:.0f}</b></span>
        <span>STC-F <b>{s['stc_f']:.0f}</b></span>
        <span>STC-S <b>{s['stc_s']:.0f}</b></span>
        <span>Trend <b class="{'pos' if s['trend']=='UP' else 'neg'}">{s['trend']}</b></span>
      </div>
    </div>"""


def render_html(stocks, macro, generated_at):
    n_below = sum(1 for s in stocks if not s["above_sma200"])
    n_total = len(stocks)
    below_names = [s["ticker"] for s in stocks if not s["above_sma200"]]
    bull_names = [s["ticker"] for s in stocks if s["above_sma200"]]

    sv = macro["silver"]
    sv_sma = macro["silver_sma200"]
    silver_below = (sv is not None and sv_sma is not None and sv < sv_sma)
    silver_line = (f" Silver spot is also below its SMA200 (${_fmt_price(sv_sma)}) at ${_fmt_price(sv)}."
                   if silver_below else
                   (f" Silver spot ${_fmt_price(sv)} is holding above its SMA200." if sv else ""))
    bull_line = (f" {', '.join(bull_names)} {'is' if len(bull_names)==1 else 'are'} the only name"
                 f"{'' if len(bull_names)==1 else 's'} still in bull regime." if bull_names
                 else " No miner remains in a bull regime.")

    if n_below >= 4:
        banner_cls, banner_title = "alert", "Bear case triggered."
        banner = (f"{n_below} of {n_total} miners ({', '.join(below_names)}) have broken below SMA200."
                  f"{silver_line}{bull_line}")
    elif n_below == 0:
        banner_cls, banner_title = "ok", "Bull regime intact."
        banner = f"All {n_total} miners are above SMA200.{silver_line}"
    else:
        banner_cls, banner_title = "warn", "Mixed regime."
        banner = (f"{n_below} of {n_total} miners below SMA200 ({', '.join(below_names)})."
                  f"{silver_line}{bull_line}")

    def chg_sub(v, suffix="/ 1m"):
        if v is None:
            return ""
        cls = "pos" if v >= 0 else "neg"
        return f'<span class="{cls}">{v:+.1f}% {suffix}</span>'

    macro_cards = "".join([
        render_macro_card("Silver spot", f"${_fmt_price(macro['silver'])}" if macro['silver'] else "—",
                          (chg_sub(macro['silver_1m']) +
                           (" • below SMA200" if silver_below else (" • above SMA200" if sv else "")))),
        render_macro_card("SIL ETF (sector)", f"${_fmt_price(macro['sil_etf'])}" if macro['sil_etf'] else "—",
                          chg_sub(macro['sil_1m'])),
        render_macro_card("DXY (dollar)", f"{_fmt_price(macro['dxy'])}" if macro['dxy'] else "—",
                          chg_sub(macro['dxy_1m'])),
        render_macro_card("VIX (volatility)", f"{_fmt_price(macro['vix'])}" if macro['vix'] else "—",
                          chg_sub(macro['vix_1m'])),
    ])

    cards = "".join(render_stock_card(s) for s in stocks)

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Silver Miners Dashboard — {generated_at}</title>
<style>
  :root {{
    --bg:#0d0d0f; --card:#16161a; --card2:#1b1b20; --line:#2a2a31;
    --txt:#e6e6ea; --dim:#8a8a93; --pos:#5bbd62; --neg:#e3604a;
    --bull:#3fb950; --bear:#d0473a; --gold:#d9a441;
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--txt);
    font-family:'Segoe UI',system-ui,-apple-system,sans-serif; padding:28px; }}
  .pos {{ color:#5bbd62; }} .neg {{ color:#e3604a; }} .dim {{ color:var(--dim); }}
  .topbar {{ display:flex; align-items:center; justify-content:center; gap:16px; margin-bottom:18px; }}
  .badge {{ background:#3a1414; color:#e3604a; border:1px solid #5a1d1d;
    padding:6px 14px; border-radius:20px; font-weight:600; font-size:14px; }}
  .badge.ok {{ background:#13301a; color:#5bbd62; border-color:#23502f; }}
  .date {{ color:var(--dim); font-size:14px; }}
  .banner {{ border-radius:10px; padding:16px 20px; margin-bottom:24px; font-size:15px; line-height:1.5; }}
  .banner.alert {{ background:linear-gradient(90deg,#2a1608,#140d05); border:1px solid #5a3a12; }}
  .banner.warn {{ background:#241c08; border:1px solid #4a3a12; }}
  .banner.ok {{ background:#0e2414; border:1px solid #1f4a2c; }}
  .banner b {{ color:var(--gold); }}
  .sect {{ color:var(--dim); letter-spacing:.12em; font-size:12px; font-weight:600;
    text-transform:uppercase; margin:18px 0 10px; }}
  .macro {{ display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin-bottom:8px; }}
  .mcard {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px 16px; }}
  .mlabel {{ color:var(--dim); font-size:13px; }}
  .mval {{ font-size:26px; font-weight:600; margin:4px 0; }}
  .msub {{ font-size:12.5px; color:var(--dim); }}
  .grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:16px; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:12px;
    padding:18px; border-left:3px solid var(--bear); }}
  .card.bull {{ border-left-color:var(--bull); }}
  .chead {{ display:flex; justify-content:space-between; align-items:flex-start; }}
  .ticker {{ font-size:22px; font-weight:700; }}
  .company {{ color:var(--dim); font-size:13px; margin-top:2px; }}
  .tag {{ font-size:12px; font-weight:600; padding:3px 10px; border-radius:6px; }}
  .tag.bear {{ background:#3a1414; color:#e3604a; }}
  .tag.bull {{ background:#13301a; color:#5bbd62; }}
  .price {{ font-size:30px; font-weight:700; margin:14px 0 2px; }}
  .fromhigh {{ font-size:13px; font-weight:400; color:#e3604a; margin-left:8px; }}
  .status {{ font-size:13px; margin-bottom:14px; }}
  .status.bear {{ color:#e3604a; }} .status.bull {{ color:#5bbd62; }}
  .ladder-title {{ font-size:13px; font-weight:600; margin-bottom:6px; }}
  .ladder {{ border-top:1px dashed var(--line); padding-top:8px; }}
  .rung {{ display:grid; grid-template-columns:78px 70px 110px 1fr; gap:8px;
    align-items:center; padding:3px 0; font-size:13px; }}
  .rung .rlabel {{ color:var(--dim); }}
  .rung.res .rlevel {{ color:#e3604a; }}
  .rung.sup .rlevel {{ color:#5bbd62; }}
  .rung .rdesc {{ color:var(--dim); font-size:12px; text-align:right; }}
  .rung.price {{ border-top:1px solid var(--gold); border-bottom:1px solid var(--gold);
    margin:4px 0; padding:5px 0; }}
  .rung.price .rlabel, .rung.price .rlevel {{ color:var(--gold); font-weight:700; }}
  .note {{ font-style:italic; color:var(--dim); font-size:12.5px; margin:12px 0; line-height:1.45; }}
  .footer {{ display:flex; gap:18px; border-top:1px solid var(--line); padding-top:10px; font-size:13px; }}
  .footer b {{ color:var(--txt); }}
  @media(max-width:1100px){{ .grid{{grid-template-columns:repeat(2,1fr);}} .macro{{grid-template-columns:repeat(2,1fr);}} }}
  @media(max-width:720px){{ .grid,.macro{{grid-template-columns:1fr;}} }}
</style></head>
<body>
  <div class="topbar">
    <span class="badge {'ok' if n_below==0 else ''}">{n_below} of {n_total} below SMA200</span>
    <span class="date">{generated_at}</span>
  </div>
  <div class="banner {banner_cls}"><b>{banner_title}</b> {banner}</div>

  <div class="sect">Macro</div>
  <div class="macro">{macro_cards}</div>

  <div class="sect">Per-stock support ladder</div>
  <div class="grid">{cards}</div>

  <p class="note" style="margin-top:22px;">
    Fib rungs = retracement of each name's 52-week range (low → high).
    Regime = price vs SMA200. Data via yfinance (fundamentals omitted — Yahoo crumb 401s).
    Generated by dashboard.py · {generated_at}.
  </p>
</body></html>"""


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join("reports", "dashboard.html"))
    ap.add_argument("--open", action="store_true", help="open the file in a browser")
    args = ap.parse_args()

    print("Fetching macro...")
    macro = build_macro()
    macro_score = macro["ctx"]["score"]

    stocks = []
    for t in SILVER_MINERS:
        print(f"Analyzing {t}...")
        s = build_stock(t, macro_score)
        if s:
            stocks.append(s)

    # bulls first, then deepest bears
    stocks.sort(key=lambda s: (not s["above_sma200"], s["pct_from_high"] or 0))

    generated_at = datetime.now().strftime("%B %d, %Y  %H:%M")
    html = render_html(stocks, macro, generated_at)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)
    out_abs = os.path.abspath(args.out)
    print(f"\nWrote {out_abs}")
    if args.open:
        webbrowser.open("file:///" + out_abs.replace("\\", "/"))


if __name__ == "__main__":
    main()
