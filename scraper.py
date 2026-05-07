import feedparser
import requests
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def scrape_rss(url: str, max_items: int = 10) -> list[str]:
    try:
        feed = feedparser.parse(url, request_headers=HEADERS)
        headlines = []
        for entry in feed.entries[:max_items]:
            title = entry.get("title", "").strip()
            if title:
                headlines.append(f"- {title}")
        return headlines
    except Exception as e:
        logger.warning(f"RSS scrape failed for {url}: {e}")
        return []


def scrape_html(url: str, selector: str, max_items: int = 10) -> list[str]:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        headlines = []
        for el in soup.select(selector)[:max_items]:
            text = el.get_text(strip=True)
            if text and len(text) > 5:
                headlines.append(f"- {text}")
        return headlines
    except Exception as e:
        logger.warning(f"HTML scrape failed for {url}: {e}")
        return []


def scrape_source(site: dict, max_items: int = 10) -> list[str]:
    source_type = site.get("type", "rss")
    if source_type == "rss":
        return scrape_rss(site["url"], max_items)
    if source_type == "html":
        return scrape_html(site["url"], site.get("selector", "h2 a"), max_items)
    logger.warning(f"Unknown source type '{source_type}' for {site.get('name')}")
    return []
