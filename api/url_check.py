"""On-demand URL/site safety check - the shared engine behind the URL
checker, fake-shop checker, and (via a decoded URL) the QR checker.
Checks the platform's own crawled index first (fast, and backed by
real crawl history); only falls back to a live fetch for a URL that
hasn't been seen before, and that live fetch is a lightweight spot
check, not a full crawl."""
import os
import re
from urllib.parse import urlparse

import requests

from . import scam_classifier

TOR_PROXY = os.environ.get("TOR_PROXY", "http://127.0.0.1:8118")
TIMEOUT = 20
MAX_FETCH_BYTES = 2_000_000

TAG_RE = re.compile(r"<[^>]+>")
SCRIPT_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)


def _strip_html(html: str) -> str:
    html = SCRIPT_STYLE_RE.sub(" ", html)
    text = TAG_RE.sub(" ", html)
    return re.sub(r"\s+", " ", text).strip()


def fetch_and_classify(url: str):
    parsed = urlparse(url if "://" in url else f"http://{url}")
    host = parsed.hostname
    if not host:
        return {"error": "not a valid URL"}

    is_onion = host.endswith(".onion")
    proxies = {"http": TOR_PROXY, "https": TOR_PROXY} if is_onion else None

    try:
        resp = requests.get(
            url if "://" in url else f"http://{url}",
            proxies=proxies,
            timeout=TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0"},
            stream=True,
        )
        content = resp.raw.read(MAX_FETCH_BYTES, decode_content=True)
        text = _strip_html(content.decode(resp.encoding or "utf-8", errors="ignore"))
    except requests.RequestException as e:
        return {"host": host, "reachable": False, "error": str(e)}

    result = scam_classifier.classify_site_text(text)
    return {
        "host": host,
        "reachable": True,
        "http_status": resp.status_code,
        "category": result["category"],
        "confidence": result["confidence"],
    }
