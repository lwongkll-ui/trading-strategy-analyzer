"""
Silver Miners — regenerate dashboard + summary and post to Discord.
=================================================================
Reuses dashboard.py's live data pipeline. Generates:
  - reports/dashboard.html          (self-contained interactive dashboard)
  - reports/change_summary.md       (data-driven "what changed" summary)
  - reports/dashboard.png           (only if playwright-python is installed)
then posts them to the Discord 'Silver' thread via the existing webhook.

Usage:
    python post_to_discord.py --mode daily          # post daily
    python post_to_discord.py --mode weekly         # post weekly
    python post_to_discord.py --mode daily --no-post  # generate only, don't post
    python post_to_discord.py --days 10             # lookback window for change table

Webhook resolution order:
    1. env SILVER_DISCORD_WEBHOOK
    2. DISCORD_WEBHOOK_DEFAULT in the US_trading_platform .env (shared, same server)
Thread:
    env SILVER_DISCORD_THREAD_ID, else the 'Silver' thread default below.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from datetime import datetime

import pandas as pd
import requests

import dashboard as dash  # reuse build_macro / build_stock / render_html (also sets UTF-8 stdout)
from config import SILVER_MINERS, SILVER_SPOT, SMA_LONG
from fetcher import fetch_ohlcv

DEFAULT_THREAD_ID = "1487359229965897880"  # #... 'Silver' thread
US_ENV = r"C:\Claude\US_trading_platform\backend\.env"
REPORTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")


# ── webhook resolution ───────────────────────────────────────────────────────

def _read_env_value(path: str, key: str):
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith(key + "="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return None


def resolve_webhook() -> str | None:
    return (os.environ.get("SILVER_DISCORD_WEBHOOK")
            or _read_env_value(US_ENV, "DISCORD_WEBHOOK_DEFAULT"))


def resolve_thread() -> str:
    return os.environ.get("SILVER_DISCORD_THREAD_ID") or DEFAULT_THREAD_ID


# ── history helpers (for the change table) ───────────────────────────────────

def price_n_sessions_ago(df: pd.DataFrame, n: int):
    if len(df) > n:
        return float(df["Close"].iloc[-1 - n]), df.index[-1 - n]
    return None, None


def sma200_break_date(df: pd.DataFrame):
    s = df["Close"].rolling(SMA_LONG).mean()
    d = df.assign(sma=s).dropna(subset=["sma"])
    above = d["Close"] > d["sma"]
    if above.empty or bool(above.iloc[-1]):
        return None  # currently above (or no data)
    for i in range(len(above) - 1, 0, -1):
        if above.iloc[i - 1] and not above.iloc[i]:
            return d.index[i]
    return None


def ladder_level(stock: dict, label: str):
    for r in stock["ladder"]:
        if r["label"] == label:
            return r["level"]
    return None


# ── summary generation ───────────────────────────────────────────────────────

def compute_summary_data(stocks: list[dict], macro: dict, days: int, mode: str) -> dict:
    """Compute everything the summary needs, once. Renderers below format it
    three ways: markdown (.md record), Discord message text, and tables HTML."""
    hist = {}
    ref_date = None
    for s in stocks:
        df = fetch_ohlcv(s["ticker"], "2y", "1d")
        past, pdate = price_n_sessions_ago(df, days)
        chg = (s["price"] / past - 1) * 100 if past else None
        hist[s["ticker"]] = {"past": past, "chg": chg, "break": sma200_break_date(df)}
        if pdate is not None:
            ref_date = pdate

    sdf = fetch_ohlcv(SILVER_SPOT, "2y", "1d")
    s_past, _ = price_n_sessions_ago(sdf, days)
    s_now = macro["silver"]
    s_chg = (s_now / s_past - 1) * 100 if (s_past and s_now) else None
    s_sma200 = macro.get("silver_sma200")

    n_below = sum(1 for s in stocks if not s["above_sma200"])
    n_total = len(stocks)
    bulls = [s["ticker"] for s in stocks if s["above_sma200"]]
    below = [s["ticker"] for s in stocks if not s["above_sma200"]]

    if n_below >= max(4, n_total - 1):
        headline = (f"Confirmed bear regime. {n_below} of {n_total} miners are below SMA200"
                    + (f"; only {', '.join(bulls)} still holds." if bulls else "."))
    elif n_below == 0:
        headline = f"Bull regime intact. All {n_total} miners are above SMA200."
    else:
        headline = f"Mixed regime. {n_below} of {n_total} miners below SMA200 ({', '.join(below)})."

    price_rows = []
    for s in sorted(stocks, key=lambda s: (hist[s["ticker"]]["chg"] if hist[s["ticker"]]["chg"] is not None else 0)):
        h = hist[s["ticker"]]
        price_rows.append({"tk": s["ticker"], "then": h["past"], "now": s["price"], "chg": h["chg"]})
    silver_row = {"tk": "Silver", "then": s_past, "now": s_now, "chg": s_chg}

    support_rows = []
    for s in stocks:
        f50, f618, sma200, price = (ladder_level(s, "Fib 50.0%"), ladder_level(s, "Fib 61.8%"),
                                    s.get("sma200"), s["price"])
        if s["above_sma200"]:
            status = "above SMA200 (last bull defense)"
        elif f618 and price < f618:
            status = "below 61.8% fib & SMA200"
        elif f618 and price >= f618 and f50 and price < f50:
            status = "between 50% & 61.8% fib"
        else:
            status = "below 50% fib"
        support_rows.append({"tk": s["ticker"], "now": price, "f50": f50, "f618": f618,
                             "sma200": sma200, "status": status, "bull": s["above_sma200"]})

    def below_both(s):
        e21, s50 = ladder_level(s, "EMA 21"), ladder_level(s, "SMA 50")
        return (e21 is not None and s["price"] < e21) and (s50 is not None and s["price"] < s50)
    n_below_short = sum(1 for s in stocks if below_both(s))
    short_txt = (f"All {n_total}" if n_below_short == n_total else f"{n_below_short} of {n_total}")
    if bulls:
        trend = (f"{short_txt} names trade below both EMA21 and SMA50; only {', '.join(bulls)} "
                 f"keeps a long-term uptrend (price > SMA200).")
    else:
        trend = f"{short_txt} names are below EMA21 and SMA50; trend down across timeframes."

    gate = ""
    if s_now and s_sma200:
        g = "below" if s_now < s_sma200 else "above"
        gate = (f"Silver is the gate: spot ${s_now:.2f} is {g} its SMA200 (${s_sma200:.2f}). "
                f"Until silver reclaims that zone, miner bounces are counter-trend. "
                f"Downside markers: $57.04 (weekly 61.8% fib), then $39.57.")

    broke = sorted([(s["ticker"], hist[s["ticker"]]["break"]) for s in stocks
                    if hist[s["ticker"]]["break"] is not None], key=lambda x: x[1])
    break_str = ", ".join(f"{t} {d.strftime('%b %d')}" for t, d in broke)

    return {
        "mode": mode, "days": days,
        "ref_str": ref_date.strftime("%b %d") if ref_date is not None else f"{days} sessions ago",
        "headline": headline, "price_rows": price_rows, "silver_row": silver_row,
        "support_rows": support_rows, "trend": trend, "gate": gate, "break_str": break_str,
    }


def _f(v):
    return f"${v:.2f}" if v is not None else "—"


def render_md(d: dict) -> str:
    """Full markdown record (code-fenced tables). Saved to reports/change_summary.md."""
    L = [f"# Silver Miners — {d['mode'].title()} Summary ({datetime.now():%Y-%m-%d})", "",
         d["headline"], "", f"## Price moves since {d['ref_str']} (~{d['days']} sessions)", "```",
         f"{'Ticker':<8}{'Then':>9}{'Now':>9}{'Change':>9}"]
    for r in d["price_rows"] + [d["silver_row"]]:
        chg = f"{r['chg']:+.1f}%" if r["chg"] is not None else "—"
        L.append(f"{r['tk']:<8}{_f(r['then']):>9}{_f(r['now']):>9}{chg:>9}")
    L.append("```")
    if d["break_str"]:
        L += [f"_SMA200 break dates: {d['break_str']}._", ""]
    L += ["## Critical support (52-week-range Fib)", "```",
          f"{'Tkr':<6}{'Now':>9}{'Fib50':>9}{'Fib61.8':>9}{'SMA200':>9}  Status"]
    for r in d["support_rows"]:
        L.append(f"{r['tk']:<6}{_f(r['now']):>9}{_f(r['f50']):>9}{_f(r['f618']):>9}"
                 f"{_f(r['sma200']):>9}  {r['status']}")
    L += ["```", "## Trend & silver gate", "", d["trend"]]
    if d["gate"]:
        L += ["", d["gate"]]
    L += ["", f"_Fundamentals omitted (Yahoo crumb 401s); price/technical/macro only. "
          f"Generated post_to_discord.py · {datetime.now():%Y-%m-%d %H:%M}._"]
    return "\n".join(L)


def render_message(d: dict) -> str:
    """Discord message text — narrative only. Tables go in the attached PNG."""
    L = [f"# Silver Miners — {d['mode'].title()} Summary ({datetime.now():%Y-%m-%d})", "",
         f"**{d['headline']}**", ""]
    if d["break_str"]:
        L += [f"SMA200 break dates: {d['break_str']}.", ""]
    L.append(d["trend"])
    if d["gate"]:
        L += ["", f"**{d['gate']}**"]
    L += ["", "_Tables (price moves + critical support) in the image above._"]
    return "\n".join(L)


def render_tables_html(d: dict) -> str:
    """Standalone dark-themed HTML of the two tables, for screenshot to PNG."""
    def chg_cell(v):
        if v is None:
            return '<td class="num">—</td>'
        return f'<td class="num {"pos" if v >= 0 else "neg"}">{v:+.1f}%</td>'
    price_html = "".join(
        f'<tr><td class="tk">{r["tk"]}</td><td class="num">{_f(r["then"])}</td>'
        f'<td class="num">{_f(r["now"])}</td>{chg_cell(r["chg"])}</tr>'
        for r in d["price_rows"])
    silver = d["silver_row"]
    price_html += (f'<tr class="silver"><td class="tk">Silver</td><td class="num">{_f(silver["then"])}</td>'
                   f'<td class="num">{_f(silver["now"])}</td>{chg_cell(silver["chg"])}</tr>')
    sup_html = "".join(
        f'<tr class="{"bull" if r["bull"] else "bear"}"><td class="tk">{r["tk"]}</td>'
        f'<td class="num">{_f(r["now"])}</td><td class="num">{_f(r["f50"])}</td>'
        f'<td class="num">{_f(r["f618"])}</td><td class="num">{_f(r["sma200"])}</td>'
        f'<td class="st">{r["status"]}</td></tr>'
        for r in d["support_rows"])
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
      body{{margin:0;background:#0d0d0f;color:#e6e6ea;font-family:'Segoe UI',system-ui,sans-serif;padding:22px;width:760px;}}
      h1{{font-size:19px;margin:0 0 2px;}} .sub{{color:#8a8a93;font-size:13px;margin:0 0 16px;}}
      h2{{font-size:15px;margin:18px 0 8px;color:#d9a441;}}
      table{{width:100%;border-collapse:collapse;font-size:14px;}}
      th,td{{padding:7px 10px;border-bottom:1px solid #23232a;text-align:left;}}
      th{{color:#8a8a93;font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.04em;}}
      .num{{text-align:right;font-variant-numeric:tabular-nums;}}
      .tk{{font-weight:700;}} .pos{{color:#5bbd62;}} .neg{{color:#e3604a;}}
      .st{{color:#c9c9d0;font-size:13px;}}
      tr.silver td{{border-top:2px solid #d9a441;font-weight:700;}}
      tr.bull .tk{{color:#5bbd62;}} tr.bear .tk{{color:#e3604a;}}
    </style></head><body>
      <h1>Silver Miners — {d['mode'].title()} Summary</h1>
      <div class="sub">{datetime.now():%B %d, %Y}  ·  {d['headline']}</div>
      <h2>Price moves since {d['ref_str']} (~{d['days']} sessions)</h2>
      <table><tr><th>Ticker</th><th class="num">Then</th><th class="num">Now</th><th class="num">Change</th></tr>{price_html}</table>
      <h2>Critical support (52-week-range Fib)</h2>
      <table><tr><th>Ticker</th><th class="num">Now</th><th class="num">Fib 50%</th><th class="num">Fib 61.8%</th><th class="num">SMA200</th><th>Status</th></tr>{sup_html}</table>
    </body></html>"""


# ── optional headless screenshot ─────────────────────────────────────────────

def try_screenshot(html_path: str, png_path: str, width: int = 1600, height: int = 1000) -> str | None:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        print("  (playwright-python not installed — skipping PNG)")
        return None
    try:
        url = "file:///" + os.path.abspath(html_path).replace("\\", "/")
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(viewport={"width": width, "height": height})
            pg.goto(url)
            pg.screenshot(path=png_path, full_page=True)
            b.close()
        return png_path
    except Exception as e:
        print(f"  (screenshot failed: {e})")
        return None


# ── discord post ─────────────────────────────────────────────────────────────

def _chunk(text: str, limit: int = 1900) -> list[str]:
    """Split on line boundaries into <=limit pieces, keeping ``` fences balanced."""
    chunks, cur, in_fence = [], [], False
    for line in text.split("\n"):
        # +1 for newline; close+reopen a fence if a chunk would overflow mid-table
        if sum(len(x) + 1 for x in cur) + len(line) + 1 > limit and cur:
            if in_fence:
                cur.append("```")
            chunks.append("\n".join(cur))
            cur = ["```"] if in_fence else []
        cur.append(line)
        if line.strip() == "```":
            in_fence = not in_fence
    if cur:
        chunks.append("\n".join(cur))
    return chunks


def post_summary(summary: str, png_paths: list[str]) -> bool:
    """Post the summary as message text (chunked if >2000 chars), with the PNG
    images attached to the first message. HTML/MD are NOT attached."""
    wh = resolve_webhook()
    if not wh or "/webhooks/" not in wh:
        print("ERROR: no webhook configured (set SILVER_DISCORD_WEBHOOK).")
        return False
    url = f"{wh}?thread_id={resolve_thread()}&wait=true"
    chunks = _chunk(summary)
    pngs = [p for p in png_paths if p and os.path.exists(p)]
    ok = True
    for i, chunk in enumerate(chunks):
        files, handles = {}, []
        if i == 0:
            for j, p in enumerate(pngs):
                fh = open(p, "rb")
                handles.append(fh)
                files[f"files[{j}]"] = (os.path.basename(p), fh)
        try:
            r = requests.post(url, data={"payload_json": json.dumps({"content": chunk})},
                              files=files or None, timeout=30)
        finally:
            for fh in handles:
                fh.close()
        print(f"  msg {i+1}/{len(chunks)} -> HTTP {r.status_code}", end="")
        if r.status_code >= 400:
            print(" ERROR:", r.text[:200]); ok = False
        else:
            try:
                print("  id", r.json().get("id"))
            except Exception:
                print()
    return ok


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["daily", "weekly"], default="daily")
    ap.add_argument("--days", type=int, default=10, help="lookback sessions for the change table")
    ap.add_argument("--no-post", action="store_true", help="generate files but do not post")
    args = ap.parse_args()

    os.makedirs(REPORTS, exist_ok=True)
    print("Fetching macro...")
    macro = dash.build_macro()
    macro_score = macro["ctx"]["score"]

    stocks = []
    for t in SILVER_MINERS:
        print(f"Analyzing {t}...")
        s = dash.build_stock(t, macro_score)
        if s:
            stocks.append(s)
    stocks.sort(key=lambda s: (not s["above_sma200"], s["pct_from_high"] or 0))

    # Compute summary data once, render three ways.
    data = compute_summary_data(stocks, macro, args.days, args.mode)
    md_text = render_md(data)
    msg_text = render_message(data)

    generated_at = datetime.now().strftime("%B %d, %Y  %H:%M")
    html_path = os.path.join(REPORTS, "dashboard.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(dash.render_html(stocks, macro, generated_at))
    tables_html_path = os.path.join(REPORTS, "summary_tables.html")
    with open(tables_html_path, "w", encoding="utf-8") as f:
        f.write(render_tables_html(data))
    md_path = os.path.join(REPORTS, "change_summary.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_text)
    print(f"Wrote {html_path}\nWrote {tables_html_path}\nWrote {md_path}")

    # Two images: the dashboard cards, and the tables (readable on mobile).
    dash_png = try_screenshot(html_path, os.path.join(REPORTS, "dashboard.png"), width=1600)
    tables_png = try_screenshot(tables_html_path, os.path.join(REPORTS, "summary_tables.png"), width=800, height=10)
    pngs = [p for p in [dash_png, tables_png] if p]
    if not pngs:
        print("WARNING: no PNGs generated (playwright missing?) — posting text only.")

    if args.no_post:
        print("\n--no-post: skipping Discord post. Files generated:")
        for p in [dash_png, tables_png, html_path, md_path]:
            if p:
                print("  ", p)
        print(f"\n--- message preview ({len(msg_text)} chars) ---\n{msg_text}")
        return

    # Post: dashboard PNG + tables PNG (inline) + narrative as message text.
    ok = post_summary(msg_text, pngs)
    print("Posted OK" if ok else "Post FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
