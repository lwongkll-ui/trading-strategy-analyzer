"""Build helper — runs PyInstaller with the project spec file.

Usage::

    python build.py               # one-folder distribution
    python build.py --clean       # wipe dist/ and build/ first
    python build.py --onefile     # single-file EXE (slower startup)

The script must be run from the *stock_tool/* directory (the folder that
contains this file and ``main.py``).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _clean() -> None:
    for d in ("dist", "build"):
        p = HERE / d
        if p.exists():
            print(f"Removing {p} …")
            shutil.rmtree(p)


def _run_pyinstaller(onefile: bool) -> int:
    cmd = [sys.executable, "-m", "PyInstaller"]
    if onefile:
        # Override the spec's COLLECT step with --onefile flag.
        # We regenerate a temporary spec or pass the flag directly.
        cmd += [
            "--onefile",
            "--noconsole",
            "--name", "StockTool",
            "--add-data", "config.yaml:.",
            "--add-data", "symbols.csv:.",
            "main.py",
        ]
    else:
        cmd.append(str(HERE / "build.spec"))

    print("Running:", " ".join(cmd))
    result = subprocess.run(cmd, cwd=HERE)
    return result.returncode


def main() -> None:
    parser = argparse.ArgumentParser(description="Build StockTool distribution")
    parser.add_argument("--clean", action="store_true",
                        help="Remove dist/ and build/ before building")
    parser.add_argument("--onefile", action="store_true",
                        help="Produce a single EXE instead of a folder")
    args = parser.parse_args()

    if args.clean:
        _clean()

    code = _run_pyinstaller(args.onefile)
    if code == 0:
        dist = HERE / "dist" / "StockTool"
        print(f"\n✓ Build succeeded.  Artefacts in: {dist}")
    else:
        print(f"\n✗ PyInstaller exited with code {code}", file=sys.stderr)
    sys.exit(code)


if __name__ == "__main__":
    main()
