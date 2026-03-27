"""NewsMonitorAgent — fetches recent news from NewsAPI and RSS feeds.

Monitors political/economic news that typically cause market fluctuations:
- Central bank statements (Fed, ECB, Bank of England)
- Political announcements (tariffs, sanctions, elections)
- CEO/executive statements about major companies
- Macro events (inflation, employment data)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import xml.etree.ElementTree as ET

import requests

from core.config import NEWSAPI_KEY
from core.state import BotState, NewsItem

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------
# RSS feeds — no API key required
# -----------------------------------------------------------------------
RSS_FEEDS = [
    "https://feeds.content.dowjones.io/public/rss/mw_topstories",        # MarketWatch
    "https://www.ft.com/?format=rss",                                     # Financial Times
    "https://feeds.reuters.com/reuters/businessNews",                     # Reuters business
    "https://www.investing.com/rss/news.rss",                             # Investing.com
    "https://feeds.bbci.co.uk/news/business/rss.xml",                    # BBC Business
]

# Keywords that signal high-impact news
HIGH_IMPACT_KEYWORDS = [
    # Monetary policy
    "interest rate", "fed rate", "ecb rate", "rate hike", "rate cut",
    "quantitative easing", "tapering", "inflation", "cpi", "ppi",
    # Political / trade
    "tariff", "sanction", "trade war", "embargo", "trade deal",
    "trump", "biden", "powell", "lagarde",
    # Crypto specific
    "bitcoin", "ethereum", "crypto ban", "sec crypto", "btc",
    # Market events
    "recession", "gdp", "unemployment", "nonfarm", "earnings",
    # CEO / corporate
    "musk", "bezos", "cook", "pichai", "zuckerberg",
    "acquisition", "merger", "bankruptcy", "ipo",
]

NEWSAPI_QUERIES = [
    "interest rate central bank",
    "cryptocurrency regulation bitcoin",
    "stock market ETF gold",
    "tariff trade war sanctions",
    "CEO acquisition merger bankruptcy",
]


def run(state: BotState) -> BotState:
    """Fetch news items and return updated state."""
    items: list[NewsItem] = []
    seen_urls: set[str] = set()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=3)

    # --- NewsAPI ---
    if NEWSAPI_KEY:
        for query in NEWSAPI_QUERIES:
            try:
                resp = requests.get(
                    "https://newsapi.org/v2/everything",
                    params={
                        "q": query,
                        "language": "en",
                        "sortBy": "publishedAt",
                        "pageSize": 10,
                        "from": cutoff.strftime("%Y-%m-%dT%H:%M:%S"),
                        "apiKey": NEWSAPI_KEY,
                    },
                    timeout=10,
                )
                resp.raise_for_status()
                for article in resp.json().get("articles", []):
                    url = article.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        items.append(NewsItem(
                            title=article.get("title") or "",
                            source=article.get("source", {}).get("name", "NewsAPI"),
                            url=url,
                            published_at=article.get("publishedAt", ""),
                            raw_text=(article.get("title") or "") + " " + (article.get("description") or ""),
                        ))
            except Exception as exc:
                logger.warning("NewsAPI error (query=%r): %s", query, exc)
                state["errors"].append(f"NewsAPI: {exc}")

    # --- RSS feeds (parsed with stdlib xml.etree.ElementTree) ---
    for feed_url in RSS_FEEDS:
        try:
            resp = requests.get(feed_url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
            ns = {"atom": "http://www.w3.org/2005/Atom"}

            # Support both RSS 2.0 and Atom feeds
            items_el = root.findall(".//item") or root.findall(".//atom:entry", ns)
            channel_title = (root.findtext(".//channel/title") or
                             root.findtext("atom:feed/atom:title", namespaces=ns) or
                             feed_url)

            for entry in items_el[:15]:
                title = (entry.findtext("title") or
                         entry.findtext("atom:title", namespaces=ns) or "")
                url = (entry.findtext("link") or
                       (entry.find("link") is not None and entry.find("link").get("href")) or "")  # type: ignore[union-attr]
                published = entry.findtext("pubDate") or entry.findtext("atom:published", namespaces=ns) or ""
                description = entry.findtext("description") or entry.findtext("atom:summary", namespaces=ns) or ""

                if not url or url in seen_urls:
                    continue
                text_lower = title.lower()
                if not any(kw in text_lower for kw in HIGH_IMPACT_KEYWORDS):
                    continue
                seen_urls.add(url)
                items.append(NewsItem(
                    title=title,
                    source=channel_title,
                    url=url,
                    published_at=published,
                    raw_text=f"{title} {description}",
                ))
        except Exception as exc:
            logger.warning("RSS error (%s): %s", feed_url, exc)

    logger.info("NewsMonitor: fetched %d items", len(items))
    state["news_items"] = items
    return state
