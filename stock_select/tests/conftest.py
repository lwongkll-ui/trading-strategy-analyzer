"""Put the package directory on the path so tests can import it flat.

Mirrors how `main.py` runs (`cd stock_select && python main.py`), which is the
same convention `stock_tool/tests` uses.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
