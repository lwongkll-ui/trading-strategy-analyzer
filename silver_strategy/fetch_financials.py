"""
Silver Miners — fetch latest quarterly financials from yfinance and write
financials_data.py (consumed by financial_review.py).

Refreshes the QUANTITATIVE tables (revenue, net income, EPS, gross margin,
balance sheet, FCF, valuation) from yfinance quarterly statements — these
endpoints work even though .info returns Invalid-Crumb 401s.

Narrative (PROFILES, EXEC_SUMMARY, RISK matrix, CONCLUSIONS) is carried from the
curated baseline financials_q1_2026.py — those are analytical, not derivable
from raw statements, so they're imported as-is and flagged in the report.

Usage:
    python fetch_financials.py            # write financials_data.py
    python fetch_financials.py --dry      # print summary, don't write
"""
from __future__ import annotations
import argparse
import io
import json
import os
import sys

if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import math
import yfinance as yf
import financials_q1_2026 as base

TICKERS = ["ASM", "PAAS", "CDE", "AG", "USAS", "SVM"]
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "financials_data.py")


# ── helpers ──────────────────────────────────────────────────────────────────

def qlabel(ts) -> str:
    q = (ts.month - 1) // 3 + 1
    return f"Q{q}'{ts.year % 100:02d}"


def row(df, key):
    return df.loc[key] if (df is not None and key in df.index) else None


def val(series, i):
    if series is None or i >= len(series):
        return None
    v = series.iloc[i]
    return None if (v is None or (isinstance(v, float) and math.isnan(v))) else float(v)


def m(v):  # plain millions, comma for thousands
    if v is None:
        return "—"
    a = abs(v) / 1e6
    s = f"{a:,.0f}" if a >= 1000 else f"{a:.1f}"
    return f"({s})" if v < 0 else s


def money(v):  # $X M with sign in parens
    if v is None:
        return "—"
    a = abs(v) / 1e6
    s = f"${a:,.0f}M" if a >= 1000 else f"${a:.1f}M"
    return f"({s})" if v < 0 else s


def eps_str(v):
    if v is None:
        return "—"
    return f"(${abs(v):.3f})" if v < 0 else f"${v:.3f}"


def pct(v):  # v is a ratio (0.554)
    if v is None:
        return "—"
    return f"({abs(v)*100:.1f}%)" if v < 0 else f"{v*100:.1f}%"


# ── per-ticker extraction ────────────────────────────────────────────────────

def fetch_one(tk: str) -> dict:
    t = yf.Ticker(tk)
    inc, bs, cf = t.quarterly_income_stmt, t.quarterly_balance_sheet, t.quarterly_cashflow

    rev = row(inc, "Total Revenue")
    gp = row(inc, "Gross Profit")
    ni = row(inc, "Net Income")
    ebitda = row(inc, "EBITDA")
    dil = row(inc, "Diluted Average Shares")
    basic = row(inc, "Basic Average Shares")
    ocf = row(cf, "Operating Cash Flow")
    fcf = row(cf, "Free Cash Flow")
    capex = row(cf, "Capital Expenditure")
    assets = row(bs, "Total Assets")
    debt = row(bs, "Total Debt")
    cash = row(bs, "Cash And Cash Equivalents")
    equity = row(bs, "Stockholders Equity") if (bs is not None and "Stockholders Equity" in bs.index) else row(bs, "Common Stock Equity")
    cur_a = row(bs, "Current Assets")
    cur_l = row(bs, "Current Liabilities")
    shares_row = row(bs, "Ordinary Shares Number")

    dates = list(inc.columns)[:5]
    n = len(dates)

    def shares_at(i):
        return val(dil, i) or val(basic, i) or val(shares_row, i)

    # per-quarter series
    rev_q = [val(rev, i) for i in range(n)]
    ni_q = [val(ni, i) for i in range(n)]
    gm_q = [(val(gp, i) / rev_q[i]) if (val(gp, i) is not None and rev_q[i]) else None for i in range(n)]
    eps_q = [(ni_q[i] / shares_at(i)) if (ni_q[i] is not None and shares_at(i)) else None for i in range(n)]
    fcf_q = [val(fcf, i) for i in range(n)]

    rev_ttm = sum(x for x in rev_q[:4] if x is not None) if any(rev_q[:4]) else None
    ni_ttm = sum(x for x in ni_q[:4] if x is not None)
    fcf_ttm = sum(x for x in fcf_q[:4] if x is not None)
    ebitda_ttm = sum(val(ebitda, i) for i in range(min(4, n)) if val(ebitda, i) is not None)
    ocf_ttm = sum(val(ocf, i) for i in range(min(4, n)) if val(ocf, i) is not None)
    yoy = (rev_q[0] / rev_q[4] - 1) if (n >= 5 and rev_q[0] and rev_q[4]) else None

    shares = shares_at(0)
    price = float(t.history(period="5d")["Close"].iloc[-1])
    mktcap = price * shares if shares else None
    cash0, debt0, eq0 = val(cash, 0), val(debt, 0), val(equity, 0)
    netcash = (cash0 - debt0) if (cash0 is not None and debt0 is not None) else None
    eps_ttm = (ni_ttm / shares) if (ni_ttm is not None and shares) else None
    pe = (price / eps_ttm) if (eps_ttm and eps_ttm > 0) else None
    pb = (mktcap / eq0) if (mktcap and eq0) else None
    ev = (mktcap - netcash) if (mktcap is not None and netcash is not None) else None  # EV = mktcap + net debt
    ev_ebitda = (ev / ebitda_ttm) if (ev and ebitda_ttm and ebitda_ttm > 0) else None
    fcf_yield = (fcf_ttm / mktcap) if (mktcap and fcf_ttm is not None) else None
    cur_ratio = (val(cur_a, 0) / val(cur_l, 0)) if (val(cur_a, 0) and val(cur_l, 0)) else None
    de = (debt0 / eq0) if (debt0 is not None and eq0) else None
    nd_ebitda = ((debt0 - cash0) / ebitda_ttm) if (debt0 is not None and cash0 is not None and ebitda_ttm) else None
    shares_yoy = (val(shares_row, 0) / val(shares_row, 4) - 1) if (n >= 5 and val(shares_row, 0) and val(shares_row, 4)) else None

    return dict(tk=tk, dates=dates, rev_q=rev_q, ni_q=ni_q, gm_q=gm_q, eps_q=eps_q, fcf_q=fcf_q,
                rev_ttm=rev_ttm, ni_ttm=ni_ttm, fcf_ttm=fcf_ttm, ocf_ttm=ocf_ttm, yoy=yoy,
                price=price, mktcap=mktcap, netcash=netcash, eps_ttm=eps_ttm, pe=pe, pb=pb,
                ev_ebitda=ev_ebitda, fcf_yield=fcf_yield, cur_ratio=cur_ratio, de=de,
                nd_ebitda=nd_ebitda, shares_yoy=shares_yoy, assets0=val(assets, 0),
                debt0=debt0, cash0=cash0, eq0=eq0, capex0=val(capex, 0))


# ── derived qualitative bits (kept consistent with fresh numbers) ─────────────

def eps_trend(d):
    last4 = [x for x in d["eps_q"][:4] if x is not None]
    if not last4:
        return "n/a"
    if d["eps_ttm"] is not None and d["eps_ttm"] <= 0:
        return "GAAP negative — ops better (see cash flow)" if (d["ocf_ttm"] or 0) > 0 else "Loss-making"
    if all(x > 0 for x in last4):
        return "Strongly improving" if last4[0] > last4[-1] else "Positive"
    return "Turned positive (fragile)"


def gm_comment(d):
    now, yago = d["gm_q"][0], (d["gm_q"][4] if len(d["gm_q"]) > 4 else None)
    if now is None:
        return ""
    if yago is not None:
        return f"{now*100:.1f}% now ({(now-yago)*100:+.0f}pp YoY)"
    return f"{now*100:.1f}% now"


def val_verdict(d):
    if d["eps_ttm"] is None or d["eps_ttm"] <= 0:
        return "Ops strong, GAAP distorted" if (d["ocf_ttm"] or 0) > 0 else "Speculative — no earnings base"
    if d["pe"] and d["pe"] < 16 and (d["fcf_yield"] or 0) > 0.05:
        return "Cheap + strong FCF"
    if d["pb"] and d["pb"] < 1.8:
        return "Cheap on P/B"
    if d["pe"] and d["pe"] > 25:
        return "Premium valuation"
    return "Fair value"


# ── build tables in the baseline schema ──────────────────────────────────────

def build(data: dict, labels: list[str]) -> dict:
    order = TICKERS
    rev_rows, ni_rows, eps_rows, gm_rows, bal_rows, cr_rows, fcf_rows, val_rows = ([] for _ in range(8))
    for tk in order:
        d = data[tk]
        rev_rows.append([tk] + [m(x) for x in d["rev_q"][:5]] + [m(d["rev_ttm"]), (f"{d['yoy']*100:+.0f}%" if d["yoy"] is not None else "—")])
        ni_rows.append([tk] + [m(x) for x in d["ni_q"][:5]] + [m(d["ni_ttm"])])
        eps_rows.append([tk] + [eps_str(x) for x in d["eps_q"][:5]] + [eps_trend(d)])
        gm_rows.append([tk] + [pct(x) for x in d["gm_q"][:5]] + [gm_comment(d)])
        rating = "Net Cash" if (d["netcash"] or 0) >= 0 else "Net Debt"
        if (d["netcash"] or 0) > 0 and (d["cur_ratio"] or 0) >= 5:
            rating = "Fortress"
        bal_rows.append([tk, money(d["assets0"]), money(d["debt0"]), money(d["cash0"]), money(d["netcash"]),
                         money(d["eq0"]), (f"{d['de']:.2f}" if d["de"] is not None else "—"),
                         (f"({abs(d['nd_ebitda']):.2f}x)" if (d["nd_ebitda"] is not None and d["nd_ebitda"] < 0) else (f"{d['nd_ebitda']:.2f}x" if d["nd_ebitda"] is not None else "—")),
                         rating])
        cr_rows.append([tk, (f"{d['cur_ratio']:.1f}x" if d["cur_ratio"] else "—")])
        fcf_rows.append([tk] + [m(x) for x in d["fcf_q"][:4]] + [m(d["fcf_ttm"]), m(d["capex0"]),
                                (f"{d['fcf_yield']*100:.1f}%" if d["fcf_yield"] is not None else "—")])
        val_rows.append([tk, f"${d['price']:.2f}",
                         (f"${d['mktcap']/1e9:.2f}B" if d["mktcap"] else "—"),
                         (f"{d['pe']:.1f}x" if d["pe"] else "N/M"),
                         (f"{d['pb']:.1f}x" if d["pb"] else "—"),
                         (f"{d['ev_ebitda']:.1f}x" if d["ev_ebitda"] else "N/M"),
                         (f"{d['fcf_yield']*100:.1f}%" if d["fcf_yield"] is not None else "—"),
                         val_verdict(d)])

    return {
        "REVENUE": {"headers": ["Ticker"] + labels[:5] + ["TTM", "YoY"], "rows": rev_rows},
        "NET_INCOME": {"headers": ["Ticker"] + labels[:5] + ["TTM"], "rows": ni_rows},
        "EPS": {"headers": ["Ticker"] + labels[:5] + ["Trend"], "rows": eps_rows, "note": base.EPS["note"]},
        "GROSS_MARGIN": {"headers": ["Ticker"] + labels[:5] + ["Commentary"], "rows": gm_rows, "warning": base.GROSS_MARGIN["warning"]},
        "BALANCE": {"headers": ["Ticker", "Assets", "Debt", "Cash", "Net Cash", "Equity", "D/E", "NetDebt/EBITDA", "Rating"],
                    "rows": bal_rows, "current_ratio": cr_rows, "note": base.BALANCE["note"]},
        "FCF": {"headers": ["Ticker"] + labels[:4] + ["TTM FCF", f"Capex {labels[0]}", "FCF Yield"], "rows": fcf_rows, "note": base.FCF["note"]},
        "VALUATION": {"headers": ["Ticker", "Price", "Mkt Cap", "TTM P/E", "P/B", "EV/EBITDA", "FCF Yield", "Verdict"], "rows": val_rows},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    data = {}
    for tk in TICKERS:
        print(f"Fetching {tk}...")
        data[tk] = fetch_one(tk)

    labels = [qlabel(ts) for ts in data["AG"]["dates"]]
    tables = build(data, labels)
    as_of = f"{labels[0]} ({data['AG']['dates'][0].date()})"

    print(f"\nLatest quarter: {as_of}")
    for tk in TICKERS:
        d = data[tk]
        print(f"  {tk:5} rev {m(d['rev_q'][0]):>8}  NI {m(d['ni_q'][0]):>8}  "
              f"EPS {eps_str(d['eps_q'][0]):>9}  P/E {(f'{d['pe']:.1f}x' if d['pe'] else 'N/M'):>6}  "
              f"netcash {money(d['netcash']):>9}")

    if args.dry:
        print("\n--dry: not writing financials_data.py")
        return

    parts = ["# AUTO-GENERATED by fetch_financials.py — do not edit by hand.",
             f"# Quantitative tables fetched from yfinance quarterly statements.",
             "# Narrative: LLM-regenerated (narrative_data.py) if present, else curated baseline.",
             "try:",
             "    from narrative_data import PROFILES, EXEC_SUMMARY, RISK, CONCLUSIONS, SILVER_THRESHOLDS, NARRATIVE_NOTE",
             "except Exception:",
             "    from financials_q1_2026 import PROFILES, EXEC_SUMMARY, RISK, CONCLUSIONS, SILVER_THRESHOLDS",
             "    NARRATIVE_NOTE = None",
             "",
             f"AS_OF = {json.dumps(as_of)}",
             f"SILVER_REF = {json.dumps(base.SILVER_REF)}",
             "DATA_NOTE = \"Tables auto-fetched from yfinance quarterly statements; narrative carried from last curated review.\"",
             ""]
    for name in ["REVENUE", "NET_INCOME", "EPS", "GROSS_MARGIN", "BALANCE", "FCF", "VALUATION"]:
        parts.append(f"{name} = {json.dumps(tables[name], indent=2, ensure_ascii=False)}")
        parts.append("")
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
