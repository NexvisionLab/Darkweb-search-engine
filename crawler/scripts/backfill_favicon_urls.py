"""One-time backfill: re-fetches each already-known domain's homepage
(a lightweight GET, not a full crawl) just to find its favicon link
tag, reusing page_metadata.extract_favicon_url() via Scrapy's
HtmlResponse - domains crawled before onion_spider.py extracted this
have no favicon_url set, and wouldn't get one until their next
scheduled recrawl otherwise."""
import os
import sys

sys.path.insert(0, ".")
import requests
from darkweb_crawler import db, page_metadata
from scrapy.http import HtmlResponse

TOR_PROXY = os.environ.get("TOR_PROXY", "http://127.0.0.1:8118")
TIMEOUT = 20


def main():
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, host FROM domains WHERE favicon_url IS NULL")
    domains = cur.fetchall()
    found = 0
    for domain_id, host in domains:
        url = f"http://{host}/"
        try:
            resp = requests.get(
                url,
                proxies={"http": TOR_PROXY, "https": TOR_PROXY},
                timeout=TIMEOUT,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            scrapy_response = HtmlResponse(url=url, body=resp.content, encoding="utf-8")
            favicon_url = page_metadata.extract_favicon_url(scrapy_response)
            db.update_domain_favicon_url(conn, domain_id, favicon_url)
            found += 1
            print(f"found: {host}")
        except Exception as e:
            print(f"failed: {host} ({e})")
    print(f"Backfilled favicon_url for {found}/{len(domains)} domains")
    conn.close()


if __name__ == "__main__":
    main()
