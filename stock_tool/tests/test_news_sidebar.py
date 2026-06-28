"""Tests for ui.news_sidebar."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from core.news_fetcher import Article


def _make_article(title: str = "Test", sentiment: str = "neutral") -> Article:
    return Article(
        title=title,
        url="https://example.com/article",
        published=datetime(2024, 1, 15, tzinfo=timezone.utc),
        source="Test Source",
        sentiment=sentiment,
    )


def _make_fetcher(articles: list[Article] | None = None) -> MagicMock:
    fetcher = MagicMock()
    fetcher.fetch.return_value = articles if articles is not None else []
    return fetcher


# ── construction ──────────────────────────────────────────────────────────────

def test_news_sidebar_constructs(qapp):
    from ui.news_sidebar import NewsSidebar
    sidebar = NewsSidebar(_make_fetcher())
    assert sidebar.article_count == 0


def test_news_sidebar_starts_empty(qapp):
    from ui.news_sidebar import NewsSidebar
    sidebar = NewsSidebar(_make_fetcher())
    assert sidebar.article_count == 0


# ── load ──────────────────────────────────────────────────────────────────────

def test_load_displays_articles(qapp):
    from ui.news_sidebar import NewsSidebar
    articles = [_make_article(f"Headline {i}") for i in range(5)]
    fetcher = _make_fetcher(articles)
    sidebar = NewsSidebar(fetcher)
    sidebar.load("AAPL")
    assert sidebar.article_count == 5


def test_load_calls_fetcher_with_ticker(qapp):
    from ui.news_sidebar import NewsSidebar
    fetcher = _make_fetcher()
    sidebar = NewsSidebar(fetcher)
    sidebar.load("MSFT")
    fetcher.fetch.assert_called_once_with("MSFT")


def test_load_uppercases_ticker(qapp):
    from ui.news_sidebar import NewsSidebar
    fetcher = _make_fetcher()
    sidebar = NewsSidebar(fetcher)
    sidebar.load("aapl")
    fetcher.fetch.assert_called_once_with("AAPL")


def test_load_updates_label(qapp):
    from ui.news_sidebar import NewsSidebar
    sidebar = NewsSidebar(_make_fetcher())
    sidebar.load("AAPL")
    assert "AAPL" in sidebar._label.text()


def test_load_shows_zero_headline_status(qapp):
    from ui.news_sidebar import NewsSidebar
    sidebar = NewsSidebar(_make_fetcher([]))
    sidebar.load("AAPL")
    assert "No headlines" in sidebar._status.text() or "0" in sidebar._status.text()


def test_load_shows_article_count_in_status(qapp):
    from ui.news_sidebar import NewsSidebar
    articles = [_make_article() for _ in range(3)]
    sidebar = NewsSidebar(_make_fetcher(articles))
    sidebar.load("AAPL")
    assert "3" in sidebar._status.text()


# ── clear ─────────────────────────────────────────────────────────────────────

def test_clear_removes_all_articles(qapp):
    from ui.news_sidebar import NewsSidebar
    articles = [_make_article(f"H{i}") for i in range(4)]
    sidebar = NewsSidebar(_make_fetcher(articles))
    sidebar.load("AAPL")
    assert sidebar.article_count == 4
    sidebar.clear()
    assert sidebar.article_count == 0


def test_clear_resets_label(qapp):
    from ui.news_sidebar import NewsSidebar
    sidebar = NewsSidebar(_make_fetcher([_make_article()]))
    sidebar.load("AAPL")
    sidebar.clear()
    assert "AAPL" not in sidebar._label.text()


# ── refresh button ────────────────────────────────────────────────────────────

def test_refresh_button_refetches(qapp):
    from ui.news_sidebar import NewsSidebar
    fetcher = _make_fetcher([_make_article()])
    sidebar = NewsSidebar(fetcher)
    sidebar.load("AAPL")
    sidebar._on_refresh()
    assert fetcher.fetch.call_count == 2


def test_refresh_button_noop_when_no_ticker(qapp):
    from ui.news_sidebar import NewsSidebar
    fetcher = _make_fetcher()
    sidebar = NewsSidebar(fetcher)
    sidebar._on_refresh()
    fetcher.fetch.assert_not_called()


# ── error handling ────────────────────────────────────────────────────────────

def test_load_handles_fetcher_exception(qapp):
    from ui.news_sidebar import NewsSidebar
    fetcher = MagicMock()
    fetcher.fetch.side_effect = Exception("network failure")
    sidebar = NewsSidebar(fetcher)
    sidebar.load("AAPL")  # should not raise
    assert sidebar.article_count == 0
    assert "Error" in sidebar._status.text()


# ── sentiment coloring ────────────────────────────────────────────────────────

def test_item_text_contains_title(qapp):
    from ui.news_sidebar import NewsSidebar, _ArticleItem
    art = _make_article("Important Headline")
    item = _ArticleItem(art)
    assert "Important Headline" in item.text()


def test_item_sentiment_badge_positive(qapp):
    from ui.news_sidebar import _ArticleItem
    art = _make_article(sentiment="positive")
    item = _ArticleItem(art)
    assert "[P]" in item.text()


def test_item_sentiment_badge_negative(qapp):
    from ui.news_sidebar import _ArticleItem
    art = _make_article(sentiment="negative")
    item = _ArticleItem(art)
    assert "[N]" in item.text()
