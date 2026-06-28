"""
Silver Miners — Financial Review report → per-section PNGs → Discord.
====================================================================
Renders the Q1 2026 financial dataset (financials_q1_2026.py) as 9 section
images styled like the source report, then posts them to the 'Silver' thread
with the executive summary as the message text.

Usage:
    python financial_review.py            # generate + post
    python financial_review.py --no-post  # generate PNGs only
"""
from __future__ import annotations
import argparse
import os

import post_to_discord as ptd          # reuse posting helpers + REPORTS (sets UTF-8 stdout)
try:
    import financials_data as F          # auto-fetched tables (fetch_financials.py)
except Exception:
    import financials_q1_2026 as F       # curated baseline fallback

REPORTS = ptd.REPORTS
FIN_DIR = os.path.join(REPORTS, "financials")

# ── shared styling (mirrors the docx: navy headers, light-blue alt rows) ──────
CSS = """
  body{margin:0;background:#ffffff;color:#1a1a1a;font-family:'Segoe UI',Arial,sans-serif;padding:26px;}
  h1{font-size:21px;color:#1F4E79;margin:0 0 4px;}
  .meta{color:#666;font-size:12.5px;margin:0 0 18px;}
  h2{font-size:14px;color:#1F4E79;margin:18px 0 8px;}
  table{width:100%;border-collapse:collapse;font-size:13px;margin-bottom:6px;}
  th{background:#1F4E79;color:#fff;font-weight:600;font-size:12px;text-align:right;padding:8px 10px;border:1px solid #cfd8e3;}
  th:first-child{text-align:left;}
  td{padding:7px 10px;border:1px solid #d9d9d9;text-align:right;}
  td:first-child{text-align:left;font-weight:700;}
  td.txt{text-align:left;font-weight:400;color:#333;}
  tr:nth-child(even) td{background:#EAF0F8;}
  .neg{color:#c0392b;} .pos{color:#1e7a34;}
  .note{font-size:12px;color:#555;font-style:italic;margin:8px 0 0;line-height:1.5;}
  .warn{font-size:12.5px;color:#8a4b00;background:#fff4e0;border:1px solid #f0c987;border-radius:6px;padding:10px 12px;margin:10px 0 0;}
  .lvl-low{color:#1e7a34;font-weight:600;} .lvl-mod{color:#b8860b;font-weight:600;}
  .lvl-high{color:#c0392b;font-weight:700;} .lvl-exc{color:#0a6b2e;font-weight:700;}
  .profile{border:1px solid #d9d9d9;border-left:4px solid #1F4E79;border-radius:6px;padding:12px 14px;margin-bottom:10px;}
  .profile h3{margin:0 0 4px;font-size:14px;color:#1F4E79;}
  .profile .sub{color:#888;font-size:11.5px;margin-bottom:6px;}
  .profile p{margin:0;font-size:12.5px;line-height:1.5;color:#333;}
  ul{margin:6px 0;padding-left:20px;} li{font-size:13px;margin:5px 0;line-height:1.5;}
  .ladder td:first-child{color:#1F4E79;}
"""


def _doc(title: str, body: str, width: int = 1040) -> str:
    return (f'<!doctype html><html><head><meta charset="utf-8">'
            f'<style>body{{width:{width}px;}}{CSS}</style></head><body>'
            f'<h1>{title}</h1>'
            f'<div class="meta">Silver Miners Financial Analysis · {F.AS_OF} · {F.SILVER_REF}</div>'
            f'{body}</body></html>')


def _num_cell(v: str) -> str:
    cls = "neg" if (v.startswith("(") or v.startswith("-")) else ("pos" if v.startswith("+") else "")
    return f'<td class="{cls}">{v}</td>'


def _table(headers, rows, text_last=False, ladder=False) -> str:
    th = "".join(f"<th>{h}</th>" for h in headers)
    trs = []
    for r in rows:
        cells = [f"<td>{r[0]}</td>"]
        for i, v in enumerate(r[1:], start=1):
            if text_last and i == len(r) - 1:
                cells.append(f'<td class="txt">{v}</td>')
            else:
                cells.append(_num_cell(v))
        trs.append("<tr>" + "".join(cells) + "</tr>")
    cls = ' class="ladder"' if ladder else ""
    return f"<table{cls}><tr>{th}</tr>{''.join(trs)}</table>"


def _risk_cell(v: str) -> str:
    u = v.upper()
    if u.startswith("EXCELLENT"):
        c = "lvl-exc"
    elif u.startswith("VERY HIGH") or u.startswith("HIGH") or u.startswith("POOR"):
        c = "lvl-high"
    elif u.startswith("LOW-MOD") or u.startswith("MODERATE") or u.startswith("GOOD BUT") or u.startswith("COMPLEX"):
        c = "lvl-mod"
    elif u.startswith("LOW") or u.startswith("GOOD"):
        c = "lvl-low"
    else:
        c = ""
    return f'<td class="txt"><span class="{c}">{v}</span></td>'


# ── section renderers ────────────────────────────────────────────────────────

def s2_profiles() -> str:
    cards = ""
    for tk, (name, listing, text) in F.PROFILES.items():
        cards += (f'<div class="profile"><h3>{tk} — {name}</h3>'
                  f'<div class="sub">{listing}</div><p>{text}</p></div>')
    return _doc("2. Company Profiles", cards, width=1040)


def s3_revenue_ni() -> str:
    body = ("<h2>Quarterly Revenue (USD Millions)</h2>"
            + _table(F.REVENUE["headers"], F.REVENUE["rows"])
            + "<h2>Quarterly Net Income (USD Millions)</h2>"
            + _table(F.NET_INCOME["headers"], F.NET_INCOME["rows"]))
    return _doc("3. Quarterly Revenue & Net Income", body)


def s4_eps() -> str:
    body = (_table(F.EPS["headers"], F.EPS["rows"], text_last=True)
            + f'<p class="note">{F.EPS["note"]}</p>')
    return _doc("4. Earnings Per Share (Diluted)", body)


def s5_margin() -> str:
    body = (_table(F.GROSS_MARGIN["headers"], F.GROSS_MARGIN["rows"], text_last=True)
            + f'<div class="warn">⚠ {F.GROSS_MARGIN["warning"]}</div>')
    return _doc("5. Gross Margin Expansion", body)


def s6_balance() -> str:
    body = (_table(F.BALANCE["headers"], F.BALANCE["rows"], text_last=True)
            + f'<p class="note">{F.BALANCE["note"]}</p>'
            + "<h2>Current Ratio</h2>"
            + _table(["Ticker", "Current Ratio"], F.BALANCE["current_ratio"], text_last=True))
    return _doc("6. Balance Sheet Strength", body)


def s7_fcf() -> str:
    body = (_table(F.FCF["headers"], F.FCF["rows"])
            + f'<p class="note">{F.FCF["note"]}</p>')
    return _doc("7. Free Cash Flow", body)


def s8_valuation() -> str:
    return _doc("8. Valuation Comparison",
                _table(F.VALUATION["headers"], F.VALUATION["rows"], text_last=True))


def s9_risk() -> str:
    th = "".join(f"<th>{h}</th>" for h in F.RISK["headers"])
    trs = ""
    for r in F.RISK["rows"]:
        trs += "<tr><td>" + r[0] + "</td>" + "".join(_risk_cell(v) for v in r[1:]) + "</tr>"
    return _doc("9. Risk Assessment", f"<table><tr>{th}</tr>{trs}</table>")


def s10_conclusions() -> str:
    bullets = "".join(f"<li>{c}</li>" for c in F.CONCLUSIONS)
    ladder = _table(["Silver price", "Implication"],
                    [[lvl, imp] for lvl, imp in F.SILVER_THRESHOLDS], text_last=True, ladder=True)
    body = (f"<ul>{bullets}</ul>"
            "<h2>Critical silver-price thresholds</h2>" + ladder)
    return _doc("10. Key Conclusions", body)


SECTIONS = [
    ("02_profiles", s2_profiles), ("03_revenue_ni", s3_revenue_ni), ("04_eps", s4_eps),
    ("05_margin", s5_margin), ("06_balance", s6_balance), ("07_fcf", s7_fcf),
    ("08_valuation", s8_valuation), ("09_risk", s9_risk), ("10_conclusions", s10_conclusions),
]


# ── batch screenshot (one browser for all sections) ──────────────────────────

def render_all() -> list[str]:
    os.makedirs(FIN_DIR, exist_ok=True)
    pairs = []
    for slug, fn in SECTIONS:
        html_path = os.path.join(FIN_DIR, slug + ".html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(fn())
        pairs.append((slug, html_path))

    pngs = []
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch()
            for slug, html_path in pairs:
                png = os.path.join(FIN_DIR, slug + ".png")
                pg = b.new_page(viewport={"width": 1100, "height": 10}, device_scale_factor=2)
                pg.goto("file:///" + os.path.abspath(html_path).replace("\\", "/"))
                pg.screenshot(path=png, full_page=True)
                pg.close()
                pngs.append(png)
                print("  rendered", os.path.basename(png))
            b.close()
    except Exception as e:
        print(f"  screenshot error ({e}) — install playwright? No PNGs produced.")
        return []
    return pngs


def exec_message() -> str:
    L = [f"# Silver Miners — Financial Review ({F.AS_OF})",
         f"_{F.SILVER_REF}_", "", "## Executive summary"]
    L += [f"• {b}" for b in F.EXEC_SUMMARY]
    note = getattr(F, "NARRATIVE_NOTE", None) or getattr(F, "DATA_NOTE", "")
    if note:
        L += ["", f"_{note}_"]
    L += ["", "_Sections 2–10 in the 9 images attached (company profiles, revenue/NI, EPS, margins, "
          "balance sheet, FCF, valuation, risk, conclusions)._"]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-post", action="store_true")
    args = ap.parse_args()

    print("Rendering financial sections...")
    pngs = render_all()
    if not pngs:
        print("No images generated; aborting.")
        raise SystemExit(1)

    msg = exec_message()
    if args.no_post:
        print(f"\n--no-post. {len(pngs)} PNGs in {FIN_DIR}")
        print(f"\n--- message ({len(msg)} chars) ---\n{msg}")
        return

    ok = ptd.post_summary(msg, pngs)   # exec summary text + 9 images on first message
    print("Posted OK" if ok else "Post FAILED")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
