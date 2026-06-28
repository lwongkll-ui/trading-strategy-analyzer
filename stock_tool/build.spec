# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for StockTool.

Build with:
    pyinstaller build.spec

Or use the helper script:
    python build.py
"""

import sys
from pathlib import Path

HERE = Path(SPECPATH)  # noqa: F821 — SPECPATH is injected by PyInstaller

block_cipher = None

a = Analysis(
    [str(HERE / "main.py")],
    pathex=[str(HERE)],
    binaries=[],
    datas=[
        # Ship default config and symbol list alongside the executable
        (str(HERE / "config.yaml"), "."),
        (str(HERE / "symbols.csv"), "."),
    ],
    hiddenimports=[
        # PyQt6 plugins that are not auto-detected
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtWidgets",
        "PyQt6.QtPrintSupport",
        "PyQt6.sip",
        # pyqtgraph
        "pyqtgraph",
        "pyqtgraph.exporters",
        "pyqtgraph.exporters.ImageExporter",
        "pyqtgraph.graphicsItems",
        # pandas / numpy back-ends
        "pandas",
        "pandas._libs.tslibs.timedeltas",
        "pandas._libs.tslibs.np_datetime",
        "pandas._libs.tslibs.nattype",
        "pandas._libs.tslibs.base",
        "pandas._libs.skiplist",
        "numpy",
        # data / network
        "yfinance",
        "requests",
        "feedparser",
        "openpyxl",
        "openpyxl.styles",
        "openpyxl.utils",
        # scheduler
        "apscheduler",
        "apscheduler.schedulers.background",
        "apscheduler.triggers.cron",
        # storage
        "sqlite3",
        # application modules
        "core",
        "core.config",
        "core.data_manager",
        "core.indicator_engine",
        "core.news_fetcher",
        "core.scheduler",
        "models",
        "models.symbol",
        "storage",
        "storage.csv_store",
        "storage.db_store",
        "ui",
        "ui.chart_panel",
        "ui.compare_panel",
        "ui.drawing_tools",
        "ui.indicator_panel",
        "ui.main_window",
        "ui.news_sidebar",
        "ui.settings_dialog",
        "ui.watchlist_panel",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "IPython",
        "jupyter",
        "notebook",
        "pytest",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="StockTool",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,      # GUI app — no console window on Windows
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon="ui/assets/stocktool.ico",   # uncomment once an icon exists
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="StockTool",
)
