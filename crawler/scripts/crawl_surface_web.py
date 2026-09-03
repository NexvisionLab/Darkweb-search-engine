"""Crawls surface-web carding/leak-dump sites - a genuinely different
target from the Tor crawler: these sites don't want to be scraped
(anti-bot protection, some behind a registration wall), so this uses a
real browser (Playwright) rather than plain HTTP requests, unlike
onion_spider.py's Scrapy pipeline. Standalone script, not a Scrapy
spider - same reasoning as capture_previews.py/process_page_images.py,
real per-page browser rendering has no business inside Scrapy's
request-response model.

Reuses the same domains/pages schema, classification, entity
extraction, and OpenSearch indexing as the Tor crawler - only the
fetch mechanism differs. domains.source_type distinguishes 'tor' from
'surface_web' origin for future Free/Pro gating and UI filtering.

Card numbers are masked (pii.mask_card_numbers) on body_text before it
is ever written to Postgres - stricter than the existing leak-dump PII
handling, which masks at display time and keeps the raw text for
Pro/breach-checker matching. A live card number is different in kind
from an email or a name (see pii.py's docstring) - it never gets
stored unmasked here at all.

Reuses today's authenticated-session mechanism (session_crypto.py) for
any host with a manually-imported session - same rule as
authenticated_spider.py, sessions are never created by this script.

SURFACE_WEB_PROXY (e.g. http://user:pass@host:port) is optional - most
of the seed list is Cloudflare-protected and unreachable without a
residential proxy, but this runs directly against the subset that
isn't (confirmed via direct reachability checks before writing this,
not assumed).

Usage:
    python3 scripts/crawl_surface_web.py <host> [<host2> ...]
"""
import json
import os
import re
import sys

sys.path.insert(0, ".")
from darkweb_crawler import classification, db, entity_extract, pii, search, session_crypto
from playwright.sync_api import sync_playwright

PROXY = os.environ.get("SURFACE_WEB_PROXY")
PAGE_TIMEOUT_MS = 30000
MAX_PAGES_PER_DOMAIN = 15
DEPTH_LIMIT = 2

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

_CONTENT_PATH_HINT_RE = re.compile(r"/(?:thread|topic|post|category|forum|showthread)", re.IGNORECASE)
_SKIP_PATH_RE = re.compile(r"/(?:login|register|logout|auth|password)", re.IGNORECASE)


def _extract_page_text(page):
    try:
        texts = page.locator("p, h1, h2, h3, article, td").all_inner_texts()
    except Exception:
        texts = []
    if not texts:
        try:
            texts = [page.locator("body").inner_text()]
        except Exception:
            texts = []
    return " ".join(t.strip() for t in texts if t.strip())[:20000]


def _same_domain_content_links(page, host):
    try:
        hrefs = page.locator("a[href]").evaluate_all("els => els.map(e => e.href)")
    except Exception:
        hrefs = []
    links = []
    for href in hrefs:
        if host not in href:
            continue
        if _SKIP_PATH_RE.search(href):
            continue
        if _CONTENT_PATH_HINT_RE.search(href):
            links.append(href.split("#")[0])
    return list(dict.fromkeys(links))


def crawl_domain(host, browser, conn, opensearch_client):
    domain_id = db.upsert_domain(conn, host, None)
    db.set_domain_source_type(conn, domain_id, "surface_web")

    context = browser.new_context(user_agent=USER_AGENT)

    session_cookies = None
    try:
        encrypted = db.get_authenticated_session(conn, host)
        if encrypted:
            session_cookies = json.loads(session_crypto.decrypt(encrypted))
            db.touch_authenticated_session(conn, host)
    except Exception as e:
        print(f"  session lookup failed for {host}: {e}")

    if session_cookies:
        context.add_cookies([
            {"name": c["name"], "value": c["value"], "domain": host, "path": "/"}
            for c in session_cookies if "name" in c and "value" in c
        ])
        print(f"  attached {len(session_cookies)} session cookies for {host}")

    page = context.new_page()
    seen = set()
    queue = [(f"https://{host}/", 0)]
    crawled = 0

    while queue and crawled < MAX_PAGES_PER_DOMAIN:
        url, depth = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        try:
            page.goto(url, timeout=PAGE_TIMEOUT_MS, wait_until="domcontentloaded")
        except Exception as e:
            print(f"  failed to load {url}: {e}")
            continue

        title = page.title()
        raw_text = _extract_page_text(page)
        body_text = pii.mask_card_numbers(raw_text)

        page_id = db.upsert_page(conn, domain_id, url, title, body_text, 200)
        category = classification.classify(title, body_text)
        pii_present = pii.detect(body_text)
        db.update_page_enrichment(conn, page_id, category, None, pii_present)

        entities = entity_extract.extract_entities(body_text)
        if entities:
            db.insert_page_entities(conn, page_id, domain_id, entities)

        embedding = classification.embed(f"{title or ''}. {body_text[:2000]}")
        search.index_page(
            opensearch_client, page_id, url, host, title, body_text, category, None,
            pii_present, None, None, embedding,
        )

        crawled += 1
        print(f"  [{crawled}] {category}: {url}")

        if depth < DEPTH_LIMIT:
            for link in _same_domain_content_links(page, host):
                if link not in seen:
                    queue.append((link, depth + 1))

    context.close()
    return crawled


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/crawl_surface_web.py <host> [<host2> ...]")
        sys.exit(1)

    hosts = sys.argv[1:]
    conn = db.get_connection()
    opensearch_client = search.get_client()
    search.ensure_index(opensearch_client)

    launch_kwargs = {}
    if PROXY:
        launch_kwargs["proxy"] = {"server": PROXY}

    with sync_playwright() as p:
        browser = p.chromium.launch(**launch_kwargs)
        for host in hosts:
            print(f"=== {host} ===")
            try:
                n = crawl_domain(host, browser, conn, opensearch_client)
                print(f"  crawled {n} pages")
            except Exception as e:
                print(f"  failed: {e}")
        browser.close()

    conn.close()


if __name__ == "__main__":
    main()
