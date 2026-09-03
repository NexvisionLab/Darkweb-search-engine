"""Extracts the standard-search-result metadata fields (favicon,
meta description, publish date) from a raw crawled response - has to
happen at crawl time, since onion_spider.py only stores the stripped
body_text downstream, not the raw HTML these live in."""
from datetime import datetime, timezone

DATE_SELECTORS = [
    'meta[property="article:published_time"]::attr(content)',
    'meta[property="og:updated_time"]::attr(content)',
    'meta[name="date"]::attr(content)',
    'time[datetime]::attr(datetime)',
]


def extract_favicon_url(response):
    href = response.css(
        'link[rel="icon"]::attr(href), link[rel="shortcut icon"]::attr(href), '
        'link[rel="apple-touch-icon"]::attr(href)'
    ).get()
    # a data: URI favicon is inlined, sometimes tens of KB of base64 - not
    # worth storing in the domains table or worth a special decode path
    # here; falling back to /favicon.ico is a fine trade for simplicity
    if href and not href.startswith("data:"):
        return response.urljoin(href)
    return response.urljoin("/favicon.ico")


def extract_meta_description(response):
    return response.css('meta[name="description"]::attr(content)').get(default="").strip() or None


def extract_published_at(response):
    for selector in DATE_SELECTORS:
        raw = response.css(selector).get()
        if not raw:
            continue
        parsed = _parse_date(raw.strip())
        if parsed:
            return parsed
    return None


def _parse_date(raw):
    try:
        # fromisoformat handles "Z" suffix and offsets on Python 3.11+
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None
