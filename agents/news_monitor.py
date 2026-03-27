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

from core.config import NEWSAPI_KEY, NEWSAPI_SOURCES
from core.state import BotState, NewsItem

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------
# RSS feeds — no API key required
# -----------------------------------------------------------------------
RSS_FEEDS = [
    # Global finance
    "https://feeds.content.dowjones.io/public/rss/mw_topstories",        # MarketWatch
    "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",                     # WSJ Markets
    "https://feeds.bbci.co.uk/news/business/rss.xml",                    # BBC Business
    "https://www.cnbc.com/id/100003114/device/rss/rss.html",             # CNBC Top News
    "https://www.cnbc.com/id/10000664/device/rss/rss.html",              # CNBC Markets
    # Yahoo Finance (aggregates Reuters, AP, Bloomberg)
    "https://finance.yahoo.com/rss/topstories",
    "https://finance.yahoo.com/rss/2.0/headline?s=^GSPC&region=US&lang=en-US",
    # Reuters (alternate endpoints)
    "https://feeds.reuters.com/reuters/businessNews",
    "https://feeds.reuters.com/reuters/technologyNews",
    # Crypto
    "https://cointelegraph.com/rss",
    "https://decrypt.co/feed",
]

# Keywords that signal high-impact news (used only for RSS pre-filter — NewsAPI sends all)
HIGH_IMPACT_KEYWORDS = [
    # Monetary policy / central banks
    "interest rate", "rate hike", "rate cut", "rate decision",
    "federal reserve", "fed reserve", "ecb", "bce", "boj", "bank of england",
    "powell", "lagarde", "ueda", "fomc", "quantitative", "tapering",
    "inflation", "cpi", "pce", "ppi", "deflation", "stagflation",
    # Macro data
    "gdp", "unemployment", "nonfarm", "payroll", "retail sales",
    "pmi", "ism", "housing", "consumer confidence", "recession",
    # Political / trade / geopolitical
    "tariff", "sanction", "trade war", "embargo", "trade deal",
    "trump", "biden", "harris", "xi jinping", "putin",
    "china", "russia", "ukraine", "taiwan", "middle east",
    # Crypto / digital assets
    "bitcoin", "ethereum", "crypto", "btc", "eth", "stablecoin",
    "sec crypto", "crypto ban", "coinbase", "binance", "etf approval",
    # Corporate / market events
    "earnings", "guidance", "acquisition", "merger", "bankruptcy", "ipo",
    "layoffs", "buyback", "dividend", "split",
    # CEOs & key figures
    "musk", "elon", "bezos", "cook", "tim cook", "pichai", "zuckerberg",
    "jensen huang", "nvidia", "yellen",
    # Market stress
    "market crash", "sell off", "rally", "all-time high", "bear market",
    "bull market", "volatility", "vix", "yield curve", "spread",
    # Gold / oil
    "gold", "crude oil", "opec", "brent", "wti",
]

NEWSAPI_QUERIES = [
    "Federal Reserve interest rate inflation",
    "ECB European Central Bank rate decision",
    "cryptocurrency bitcoin ethereum regulation",
    "stock market S&P500 earnings forecast",
    "tariff trade war sanctions geopolitical",
    "oil gold commodities OPEC price",
    "GDP unemployment recession economic data",
    "merger acquisition IPO bankruptcy corporate",
]

# NewsAPI sources to prioritize (comma-separated for API)
NEWSAPI_SOURCES = "reuters,bloomberg,cnbc,the-wall-street-journal,financial-times,fortune"


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
                        "sources": NEWSAPI_SOURCES,
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
