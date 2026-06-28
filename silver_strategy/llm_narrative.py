"""
Silver Miners — LLM narrative refresh.
======================================
Feeds the freshly-fetched quantitative tables (financials_data.py) plus the
prior curated narrative (financials_q1_2026.py) to Claude, and writes
narrative_data.py with regenerated PROFILES / EXEC_SUMMARY / RISK / CONCLUSIONS /
SILVER_THRESHOLDS so the report's prose stays in sync with the numbers.

Run AFTER fetch_financials.py. financials_data.py imports the narrative from
narrative_data.py if present (else falls back to the curated baseline).

Model: claude-opus-4-8 (structured JSON output). ~$0.10/run.

Key resolution: env SILVER_ANTHROPIC_KEY → env ANTHROPIC_API_KEY →
ANTHROPIC_API_KEY in the btc_trading_platform .env (shared, same machine).

Usage:
    python llm_narrative.py            # regenerate narrative_data.py
    python llm_narrative.py --dry      # print the generated narrative, don't write
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import io

if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from openai import OpenAI   # POE exposes an OpenAI-compatible API
import financials_q1_2026 as base
try:
    import financials_data as data   # fresh fetched tables
except Exception:
    data = base                       # fall back to baseline if no fetch yet

# Opus 4.8 served via POE's OpenAI-compatible endpoint (POE bot id "claude-opus-4.8").
MODEL = os.environ.get("SILVER_LLM_MODEL", "claude-opus-4.8")
BASE_URL = os.environ.get("SILVER_LLM_BASE_URL", "https://api.poe.com/v1")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "narrative_data.py")
US_ENV = r"C:\Claude\US_trading_platform\backend\.env"
TICKERS = ["ASM", "PAAS", "CDE", "AG", "USAS", "SVM"]


def resolve_key() -> str | None:
    for var in ("SILVER_POE_KEY", "SILVER_LLM_KEY", "POE_API_KEY"):
        if os.environ.get(var):
            return os.environ[var]
    try:
        with open(US_ENV, encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("POE_API_KEY="):
                    v = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if v:
                        return v
    except FileNotFoundError:
        pass
    return None


SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "profiles": {
            "type": "array",
            "items": {
                "type": "object", "additionalProperties": False,
                "properties": {"ticker": {"type": "string"}, "text": {"type": "string"}},
                "required": ["ticker", "text"],
            },
        },
        "exec_summary": {"type": "array", "items": {"type": "string"}},
        "risk": {
            "type": "array",
            "items": {
                "type": "object", "additionalProperties": False,
                "properties": {
                    "ticker": {"type": "string"},
                    "silver_price": {"type": "string"},
                    "balance_sheet": {"type": "string"},
                    "earnings_quality": {"type": "string"},
                    "dilution": {"type": "string"},
                    "overall": {"type": "string"},
                },
                "required": ["ticker", "silver_price", "balance_sheet",
                             "earnings_quality", "dilution", "overall"],
            },
        },
        "conclusions": {"type": "array", "items": {"type": "string"}},
        "silver_thresholds": {
            "type": "array",
            "items": {
                "type": "object", "additionalProperties": False,
                "properties": {"level": {"type": "string"}, "implication": {"type": "string"}},
                "required": ["level", "implication"],
            },
        },
    },
    "required": ["profiles", "exec_summary", "risk", "conclusions", "silver_thresholds"],
}

SYSTEM = (
    "You are a precise equity-research editor covering silver mining stocks. You rewrite a "
    "financial-report narrative so it is consistent with a fresh set of quarterly financial "
    "tables. Rules: (1) Update every figure to match the provided latest-quarter tables — "
    "revenue, net income, EPS, margins, net cash, FCF, valuation. (2) PRESERVE durable "
    "operational facts from the prior narrative that are NOT derivable from statements "
    "(mine names, geographies, business model, China/FX exposure, dilution history). "
    "(3) Be concise and factual, matching the prior tone. (4) Risk levels must be one of "
    "LOW / LOW-MODERATE / MODERATE / HIGH / VERY HIGH (earnings quality may use "
    "EXCELLENT/GOOD/COMPLEX/POOR). (5) Output ONLY the requested JSON."
)


def build_prompt() -> str:
    def tbl(name):
        return json.dumps(getattr(data, name), ensure_ascii=False)
    prior_profiles = {tk: {"name": v[0], "listing": v[1], "text": v[2]} for tk, v in base.PROFILES.items()}
    return (
        f"LATEST QUARTER: {getattr(data, 'AS_OF', base.AS_OF)}\n"
        f"SILVER REFERENCE: {getattr(data, 'SILVER_REF', base.SILVER_REF)}\n\n"
        "=== FRESH FINANCIAL TABLES (authoritative — update all numbers to these) ===\n"
        f"REVENUE: {tbl('REVENUE')}\n"
        f"NET_INCOME: {tbl('NET_INCOME')}\n"
        f"EPS: {tbl('EPS')}\n"
        f"GROSS_MARGIN: {tbl('GROSS_MARGIN')}\n"
        f"BALANCE: {tbl('BALANCE')}\n"
        f"FCF: {tbl('FCF')}\n"
        f"VALUATION: {tbl('VALUATION')}\n\n"
        "=== PRIOR NARRATIVE (preserve durable operational facts; refresh the numbers) ===\n"
        f"PROFILES: {json.dumps(prior_profiles, ensure_ascii=False)}\n"
        f"EXEC_SUMMARY: {json.dumps(base.EXEC_SUMMARY, ensure_ascii=False)}\n"
        f"RISK: {json.dumps(base.RISK, ensure_ascii=False)}\n"
        f"CONCLUSIONS: {json.dumps(base.CONCLUSIONS, ensure_ascii=False)}\n"
        f"SILVER_THRESHOLDS: {json.dumps(base.SILVER_THRESHOLDS, ensure_ascii=False)}\n\n"
        "TASK: Produce updated narrative as JSON with keys: profiles (one per ticker "
        f"{TICKERS}, each {{ticker, text}}), exec_summary (6-8 bullets), risk (one per ticker "
        "with silver_price/balance_sheet/earnings_quality/dilution/overall), conclusions "
        "(5-7 bullets), silver_thresholds (4 rows {level, implication}). Keep each profile to "
        "2-4 sentences."
    )


def _extract_json(text: str) -> dict:
    """POE-served Claude may wrap JSON in prose/markdown fences — be tolerant."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    t = text.strip()
    if "```" in t:
        t = t.split("```", 2)[1]
        if t.lstrip().lower().startswith("json"):
            t = t.lstrip()[4:]
    start, end = t.find("{"), t.rfind("}")
    if start != -1 and end != -1:
        return json.loads(t[start:end + 1])
    raise ValueError("no JSON object found in model response")


def generate() -> dict:
    key = resolve_key()
    if not key:
        raise SystemExit("ERROR: no POE key (set SILVER_POE_KEY or POE_API_KEY).")
    client = OpenAI(api_key=key, base_url=BASE_URL)
    resp = client.chat.completions.create(
        model=MODEL,
        max_tokens=4096,
        temperature=0.2,
        response_format={"type": "json_object"},   # hint; honoured by OpenAI-compatible endpoints
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": build_prompt()},
        ],
    )
    text = resp.choices[0].message.content
    u = resp.usage
    if u:
        print(f"  model={resp.model} in={u.prompt_tokens} out={u.completion_tokens} tokens")
    return _extract_json(text)


def to_report_structures(n: dict) -> dict:
    prof_text = {p["ticker"]: p["text"] for p in n["profiles"]}
    PROFILES = {}
    for tk in TICKERS:
        name, listing, _ = base.PROFILES[tk]
        PROFILES[tk] = [name, listing, prof_text.get(tk, base.PROFILES[tk][2])]
    risk_by = {r["ticker"]: r for r in n["risk"]}
    RISK = {
        "headers": ["Ticker", "Silver Price", "Balance Sheet", "Earnings Quality", "Dilution", "Overall"],
        "rows": [[tk, risk_by[tk]["silver_price"], risk_by[tk]["balance_sheet"],
                  risk_by[tk]["earnings_quality"], risk_by[tk]["dilution"], risk_by[tk]["overall"]]
                 for tk in TICKERS if tk in risk_by],
    }
    SILVER_THRESHOLDS = [[t["level"], t["implication"]] for t in n["silver_thresholds"]]
    return {"PROFILES": PROFILES, "EXEC_SUMMARY": n["exec_summary"], "RISK": RISK,
            "CONCLUSIONS": n["conclusions"], "SILVER_THRESHOLDS": SILVER_THRESHOLDS}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    print(f"Generating narrative with {MODEL}...")
    n = generate()
    s = to_report_structures(n)
    as_of = getattr(data, "AS_OF", base.AS_OF)

    if args.dry:
        print(json.dumps(s, indent=2, ensure_ascii=False))
        return

    parts = [
        "# AUTO-GENERATED by llm_narrative.py — do not edit by hand.",
        f"# Narrative regenerated by {MODEL} from {as_of} financial tables.",
        f"NARRATIVE_NOTE = \"Narrative regenerated by {MODEL} from {as_of} financials; figures auto-fetched from yfinance.\"",
        "",
    ]
    for name in ["PROFILES", "EXEC_SUMMARY", "RISK", "CONCLUSIONS", "SILVER_THRESHOLDS"]:
        parts.append(f"{name} = {json.dumps(s[name], indent=2, ensure_ascii=False)}")
        parts.append("")
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
