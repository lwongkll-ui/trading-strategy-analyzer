"""News sidebar panel for StockTool.

Displays a scrollable list of news headlines for the currently loaded ticker.
Each headline shows a coloured sentiment badge, source, and title.
Clicking a row opens the article URL in the default browser.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from PyQt6 import QtCore, QtGui, QtWidgets

if TYPE_CHECKING:
    from core.config import NewsConfig
    from core.news_fetcher import Article, NewsFetcher

logger = logging.getLogger(__name__)

_SENTIMENT_COLORS = {
    "positive": "#26a69a",
    "negative": "#ef5350",
    "neutral": "#888888",
}


class _ArticleItem(QtWidgets.QListWidgetItem):
    """QListWidgetItem that also stores the article URL and full data."""

    def __init__(self, article: "Article") -> None:
        super().__init__()
        self.url = article.url
        self.article = article

        pub_str = article.published.strftime("%Y-%m-%d")
        badge = article.sentiment[0].upper()  # P / N / N
        text = f"[{badge}] {article.source}  {pub_str}\n{article.title}"
        self.setText(text)

        color = _SENTIMENT_COLORS.get(article.sentiment, "#888888")
        self.setForeground(QtGui.QColor(color))


class NewsSidebar(QtWidgets.QWidget):
    """Sidebar panel showing news headlines for a ticker.

    Args:
        fetcher: A :class:`~core.news_fetcher.NewsFetcher` instance.
        parent:  Optional parent widget.
    """

    def __init__(
        self,
        fetcher: "NewsFetcher",
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._fetcher = fetcher
        self._ticker: str = ""

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Header row
        header = QtWidgets.QHBoxLayout()
        self._label = QtWidgets.QLabel("News")
        self._label.setStyleSheet("font-weight: bold;")
        header.addWidget(self._label)
        header.addStretch()
        self._refresh_btn = QtWidgets.QPushButton("Refresh")
        self._refresh_btn.setFixedHeight(24)
        self._refresh_btn.clicked.connect(self._on_refresh)
        header.addWidget(self._refresh_btn)
        layout.addLayout(header)

        # Status line
        self._status = QtWidgets.QLabel("")
        self._status.setStyleSheet("color: #888888; font-size: 11px;")
        layout.addWidget(self._status)

        # Headline list
        self._list = QtWidgets.QListWidget()
        self._list.setWordWrap(True)
        self._list.setSpacing(2)
        self._list.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._list)

    # ── public API ────────────────────────────────────────────────────────────

    def load(self, ticker: str) -> None:
        """Fetch and display headlines for *ticker*."""
        self._ticker = ticker.upper()
        self._label.setText(f"News — {self._ticker}")
        self._status.setText("Loading…")
        QtWidgets.QApplication.processEvents()
        self._refresh()

    def clear(self) -> None:
        """Clear all displayed articles."""
        self._list.clear()
        self._ticker = ""
        self._label.setText("News")
        self._status.setText("")

    @property
    def article_count(self) -> int:
        return self._list.count()

    # ── slots ─────────────────────────────────────────────────────────────────

    def _on_refresh(self) -> None:
        if self._ticker:
            self._refresh()

    def _on_item_clicked(self, item: QtWidgets.QListWidgetItem) -> None:
        if isinstance(item, _ArticleItem) and item.url:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl(item.url))

    # ── internal ──────────────────────────────────────────────────────────────

    def _refresh(self) -> None:
        self._list.clear()
        try:
            articles = self._fetcher.fetch(self._ticker)
        except Exception as exc:
            logger.exception("News fetch error for %s", self._ticker)
            self._status.setText(f"Error: {exc}")
            return

        for art in articles:
            self._list.addItem(_ArticleItem(art))

        count = len(articles)
        self._status.setText(
            f"{count} headline{'s' if count != 1 else ''}"
            if count > 0
            else "No headlines found."
        )
