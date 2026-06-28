"""Tests for core.news_fetcher."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from core.config import NewsConfig
from core.news_fetcher import Article, NewsFetcher, _score_sentiment


# ── sentiment scoring ─────────────────────────────────────────────────────────

def test_positive_sentiment():
    assert _score_sentiment("AAPL surges to record high on strong earnings beat") == "positive"


def test_negative_sentiment():
    assert _score_sentiment("Stock falls after company misses earnings forecast") == "negative"


def test_neutral_sentiment():
    assert _score_sentiment("Company announces quarterly results") == "neutral"


def test_positive_beats_negative():
    # More positive hits than negative
    assert _score_sentiment("rally gain rise surge") == "positive"


def test_negative_beats_positive():
    assert _score_sentiment("crash fall decline drop loss warning") == "negative"


# ── Article dataclass ─────────────────────────────────────────────────────────

def test_article_is_frozen():
    art = Article(
        title="Test", url="http://example.com",
        published=datetime.now(tz=timezone.utc),
        source="Test", sentiment="neutral",
    )
    with pytest.raises(Exception):
        art.title = "Changed"  # type: ignore[misc]


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_config(provider: str = "newsapi", key: str = "testkey") -> NewsConfig:
    return NewsConfig(provider=provider, newsapi_key=key, max_headlines=10)


def _newsapi_response(articles: list[dict]) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"status": "ok", "articles": articles}
    return mock_resp


def _rss_feed(entries: list[dict]) -> MagicMock:
    mock_feed = MagicMock()
    mock_entries = []
    for e in entries:
        entry = MagicMock()
        entry.title = e.get("title", "")
        entry.link = e.get("link", "")
        entry.published = e.get("published", "Mon, 01 Jan 2024 00:00:00 +0000")
        entry.source = {}
        mock_entries.append(entry)
    mock_feed.entries = mock_entries
    return mock_feed


# ── fetch via NewsAPI ─────────────────────────────────────────────────────────

def test_fetch_newsapi_returns_articles():
    cfg = _make_config()
    session = MagicMock()
    session.get.return_value = _newsapi_response([
        {
            "title": "AAPL surges",
            "url": "https://example.com/1",
            "publishedAt": "2024-01-15T10:00:00Z",
            "source": {"name": "Bloomberg"},
        }
    ])
    fetcher = NewsFetcher(cfg, session=session)
    articles = fetcher.fetch("AAPL")
    assert len(articles) == 1
    assert articles[0].title == "AAPL surges"
    assert articles[0].source == "Bloomberg"
    assert articles[0].sentiment == "positive"


def test_fetch_newsapi_respects_max_results():
    cfg = _make_config()
    session = MagicMock()
    session.get.return_value = _newsapi_response([
        {"title": f"Headline {i}", "url": f"https://example.com/{i}",
         "publishedAt": "2024-01-15T10:00:00Z", "source": {"name": "Reuters"}}
        for i in range(20)
    ])
    fetcher = NewsFetcher(cfg, session=session)
    articles = fetcher.fetch("AAPL", max_results=5)
    assert len(articles) == 5


def test_fetch_newsapi_skips_blank_entries():
    cfg = _make_config()
    session = MagicMock()
    session.get.return_value = _newsapi_response([
        {"title": "", "url": "https://example.com/1",
         "publishedAt": "2024-01-15T10:00:00Z", "source": {"name": "Reuters"}},
        {"title": "Valid headline", "url": "",
         "publishedAt": "2024-01-15T10:00:00Z", "source": {"name": "Reuters"}},
        {"title": "Good article", "url": "https://example.com/3",
         "publishedAt": "2024-01-15T10:00:00Z", "source": {"name": "Reuters"}},
    ])
    fetcher = NewsFetcher(cfg, session=session)
    articles = fetcher.fetch("AAPL")
    assert len(articles) == 1
    assert articles[0].title == "Good article"


def test_fetch_newsapi_bad_date_uses_now():
    cfg = _make_config()
    session = MagicMock()
    session.get.return_value = _newsapi_response([
        {"title": "Article", "url": "https://example.com",
         "publishedAt": "not-a-date", "source": {"name": "Test"}},
    ])
    fetcher = NewsFetcher(cfg, session=session)
    articles = fetcher.fetch("AAPL")
    assert len(articles) == 1
    assert isinstance(articles[0].published, datetime)


# ── RSS fallback ──────────────────────────────────────────────────────────────

def test_fetch_falls_back_to_rss_when_no_key():
    cfg = _make_config(provider="newsapi", key="")
    session = MagicMock()
    fetcher = NewsFetcher(cfg, session=session)

    with patch("feedparser.parse") as mock_parse:
        mock_parse.return_value = _rss_feed([
            {"title": "AAPL drops", "link": "https://finance.yahoo.com/1"},
        ])
        articles = fetcher.fetch("AAPL")

    assert len(articles) == 1
    assert articles[0].title == "AAPL drops"
    session.get.assert_not_called()


def test_fetch_falls_back_to_rss_on_newsapi_error():
    cfg = _make_config()
    session = MagicMock()
    session.get.side_effect = Exception("network error")
    fetcher = NewsFetcher(cfg, session=session)

    with patch("feedparser.parse") as mock_parse:
        mock_parse.return_value = _rss_feed([
            {"title": "RSS headline", "link": "https://finance.yahoo.com/2"},
        ])
        articles = fetcher.fetch("AAPL")

    assert len(articles) == 1
    assert articles[0].title == "RSS headline"


def test_fetch_returns_empty_when_both_fail():
    cfg = _make_config()
    session = MagicMock()
    session.get.side_effect = Exception("network error")
    fetcher = NewsFetcher(cfg, session=session)

    with patch("feedparser.parse") as mock_parse:
        mock_parse.side_effect = Exception("rss error")
        articles = fetcher.fetch("AAPL")

    assert articles == []


def test_fetch_rss_skips_blank_entries():
    cfg = _make_config(key="")
    fetcher = NewsFetcher(cfg)

    with patch("feedparser.parse") as mock_parse:
        mock_parse.return_value = _rss_feed([
            {"title": "", "link": "https://example.com/1"},
            {"title": "Good", "link": ""},
            {"title": "Valid", "link": "https://example.com/2"},
        ])
        articles = fetcher.fetch("AAPL")

    assert len(articles) == 1
    assert articles[0].title == "Valid"


def test_fetch_rss_respects_max_results():
    cfg = _make_config(key="")
    fetcher = NewsFetcher(cfg)

    with patch("feedparser.parse") as mock_parse:
        mock_parse.return_value = _rss_feed([
            {"title": f"Headline {i}", "link": f"https://example.com/{i}"}
            for i in range(15)
        ])
        articles = fetcher.fetch("AAPL", max_results=4)

    assert len(articles) == 4


def test_fetch_uses_config_max_headlines():
    cfg = NewsConfig(provider="newsapi", newsapi_key="", max_headlines=3)
    fetcher = NewsFetcher(cfg)

    with patch("feedparser.parse") as mock_parse:
        mock_parse.return_value = _rss_feed([
            {"title": f"H{i}", "link": f"https://example.com/{i}"}
            for i in range(10)
        ])
        articles = fetcher.fetch("AAPL")

    assert len(articles) == 3


# ── provider=rss uses RSS directly ───────────────────────────────────────────

def test_rss_provider_skips_newsapi():
    cfg = _make_config(provider="rss", key="testkey")
    session = MagicMock()
    fetcher = NewsFetcher(cfg, session=session)

    with patch("feedparser.parse") as mock_parse:
        mock_parse.return_value = _rss_feed([
            {"title": "RSS only", "link": "https://example.com"},
        ])
        articles = fetcher.fetch("AAPL")

    session.get.assert_not_called()
    assert len(articles) == 1
