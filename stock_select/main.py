"""Build the stock selection page.

    python main.py                      # live scan of the S&P 500 + Hang Seng
    python main.py --demo --open        # synthetic data, opens in a browser
    python main.py --markets SP500      # one index only
    python main.py --no-fundamentals    # price factors only, much faster
"""
from __future__ import annotations

import argparse
import io
import sys
import webbrowser
from pathlib import Path

if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import config
import render
import screener


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Generate the stock selection page.")
    ap.add_argument("--markets", nargs="+", choices=sorted(config.UNIVERSES),
                    default=config.DEFAULT_MARKETS,
                    help="indices to scan (default: %(default)s)")
    ap.add_argument("--period", default=config.HISTORY_PERIOD,
                    help="yfinance history period (default: %(default)s)")
    ap.add_argument("--out", type=Path, default=config.DEFAULT_OUTPUT,
                    help="output HTML path (default: %(default)s)")
    ap.add_argument("--limit", type=int, default=None,
                    help="cap the number of tickers per market (useful for a quick test)")
    ap.add_argument("--no-fundamentals", action="store_true",
                    help="skip the slow profile fetch; quality and value score as neutral")
    ap.add_argument("--refresh-profiles", action="store_true",
                    help="ignore the cached fundamentals and refetch them")
    ap.add_argument("--demo", action="store_true",
                    help="use synthetic data instead of the network")
    ap.add_argument("--open", dest="open_browser", action="store_true",
                    help="open the generated page in a browser")
    ap.add_argument("--quiet", action="store_true", help="suppress progress output")
    return ap.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    log = (lambda *a: None) if args.quiet else print

    result = screener.run(
        args.markets,
        period=args.period,
        fundamentals=not args.no_fundamentals,
        refresh_profiles=args.refresh_profiles,
        limit=args.limit,
        demo_mode=args.demo,
        log=log,
    )

    if not result["rows"]:
        print("No tickers could be scored — check network access and the "
              "constituent lists.", file=sys.stderr)
        return 1

    html = render.build_page(result)
    out = args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")

    log(f"Wrote {out}  ({len(html) / 1024:.0f} KB, {len(result['rows'])} names)")
    if args.open_browser:
        webbrowser.open(out.resolve().as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
