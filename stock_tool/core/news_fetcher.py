"""News fetching for StockTool.

Fetches recent headlines for a ticker symbol from NewsAPI (primary) with a
Yahoo Finance RSS feed as fallback.  Each article is scored for sentiment
using a simple keyword matching approach.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import feedparser
import requests

if TYPE_CHECKING:
    from core.config import NewsConfig

logger = logging.getLogger(__name__)

_NEWSAPI_URL = "https://newsapi.org/v2/everything"
_YAHOO_RSS_URL = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"

_POSITIVE_WORDS = frozenset(
    {
        "surge", "surges", "surged", "rally", "rallies", "rallied", "gain", "gains",
        "gained", "rise", "rises", "rose", "risen", "jump", "jumps", "jumped", "beat",
        "beats", "upgrade", "upgraded", "outperform", "profit", "profits", "growth",
        "record", "high", "strong", "strength", "bullish", "bull", "positive",
        "optimistic", "opportunity", "buy", "boost", "boosted", "soar", "soared",
    }
)

_NEGATIVE_WORDS = frozenset(
    {
        "fall", "falls", "fell", "fallen", "drop", "drops", "dropped", "decline",
        "declines", "declined", "loss", "losses", "miss", "misses", "missed",
        "downgrade", "downgraded", "underperform", "weak", "weakness", "bearish",
        "bear", "negative", "concern", "concerns", "risk", "risks", "sell", "crash",
        "crashes", "crashed", "plunge", "plunges", "plunged", "warning", "cut",
        "cuts", "lawsuit", "fraud", "investigation",
    }
)


@dataclass(frozen=True)
class Article:
    """A single news headline."""
    title: str
    url: str
    published: datetime   # UTC-aware
    source: str
    sentiment: str        # "positive" | "neutral" | "negative"


def _score_sentiment(text: str) -> str:
    words = set(text.lower().split())
    pos = len(words & _POSITIVE_WORDS)
    neg = len(words & _NEGATIVE_WORDS)
    if pos > neg:
        return "positive"
    if neg > pos:
        return "negative"
    return "neutral"


def _parse_rss_date(date_str: str) -> datetime:
    """Parse an RFC-2822 date string from feedparser into a UTC datetime."""
    import email.utils
    try:
        parsed = email.utils.parsedate_to_datetime(date_str)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return datetime.now(tz=timezone.utc)


class NewsFetcher:
    """Fetches news headlines for a given ticker symbol.

    Uses NewsAPI as the primary source when an API key is configured;
    falls back to the Yahoo Finance RSS feed otherwise.

    Args:
        config: :class:`~core.config.NewsConfig` with provider, key, and limit.
        session: Optional ``requests.Session`` for testing/injection.
    """

    def __init__(
        self,
        config: "NewsConfig",
        session: requests.Session | None = None,
    ) -> None:
        self._config = config
        self._session = session or requests.Session()

    def fetch(self, ticker: str, max_results: int | None = None) -> list[Article]:
        """Return up to *max_results* articles for *ticker*.

        Tries NewsAPI first (if key is configured), then falls back to RSS.
        Returns an empty list if both sources fail.
        """
        limit = max_results if max_results is not None else self._config.max_headlines
        articles: list[Article] = []

        if self._config.provider == "newsapi" and self._config.newsapi_key:
            try:
                articles = self._fetch_newsapi(ticker, limit)
            except Exception as exc:
                logger.warning("NewsAPI failed for %s: %s", ticker, exc)

        if not articles:
            try:
                articles = self._fetch_rss(ticker, limit)
            except Exception as exc:
                logger.warning("RSS fetch failed for %s: %s", ticker, exc)

        return articles[:limit]

    # ── private helpers ───────────────────────────────────────────────────────

    def _fetch_newsapi(self, ticker: str, limit: int) -> list[Article]:
        params = {
            "q": ticker,
            "apiKey": self._config.newsapi_key,
            "pageSize": min(limit, 100),
            "sortBy": "publishedAt",
            "language": "en",
        }
        resp = self._session.get(_NEWSAPI_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        articles: list[Article] = []
        for item in data.get("articles", []):
            title = (item.get("title") or "").strip()
            url = (item.get("url") or "").strip()
            if not title or not url:
                continue
            try:
                pub = datetime.fromisoformat(
                    item.get("publishedAt", "").replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                pub = datetime.now(tz=timezone.utc)
            source = (item.get("source") or {}).get("name") or "NewsAPI"
            articles.append(
                Article(
                    title=title,
                    url=url,
                    published=pub,
                    source=source,
                    sentiment=_score_sentiment(title),
                )
            )
        return articles

    def _fetch_rss(self, ticker: str, limit: int) -> list[Article]:
        url = _YAHOO_RSS_URL.format(ticker=ticker)
        feed = feedparser.parse(url)
        articles: list[Article] = []
        for entry in feed.entries[:limit]:
            title = getattr(entry, "title", "").strip()
            link = getattr(entry, "link", "").strip()
            if not title or not link:
                continue
            pub_str = getattr(entry, "published", "")
            pub = _parse_rss_date(pub_str) if pub_str else datetime.now(tz=timezone.utc)
            source = getattr(entry, "source", {})
            source_name = source.get("title", "Yahoo Finance") if isinstance(source, dict) else "Yahoo Finance"
            articles.append(
                Article(
                    title=title,
                    url=link,
                    published=pub,
                    source=source_name,
                    sentiment=_score_sentiment(title),
                )
            )
        return articles
