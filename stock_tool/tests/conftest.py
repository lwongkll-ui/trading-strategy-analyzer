"""Shared pytest fixtures for stock_tool tests."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Make the stock_tool package directory importable as the test root.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Force Qt to use the offscreen platform plugin BEFORE any Qt module is
# imported anywhere in the test process. This makes UI tests headless.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402  (env var must be set first)


@pytest.fixture(scope="session")
def qapp():
    """Session-scoped QApplication for UI tests.

    Importing PyQt6 inside the fixture (instead of at module load) keeps
    non-UI tests free of any Qt overhead.
    """
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
    # Don't call app.quit() — re-using a single QApplication across the
    # session is fine, and quitting can crash on Windows when other tests
    # still hold widget references.
