"""Crawls a single login-gated onion domain using a previously-imported
authenticated session (see scripts/import_session.py) - deliberately
separate from OnionSpider's broad, unattended sweep across every known
domain. This is a targeted, manually-invoked crawl of exactly one
domain a human already authenticated to by hand; it should never run
as part of the automatic recurring pipeline. An authenticated account
behaves differently than an anonymous visitor to whoever's watching
for bot behavior, and unattended aggressive crawling risks burning an
account someone went through real registration/vetting to obtain -
this spider is throttled harder than the default crawl for exactly
that reason.

Reuses OnionSpider's parse() entirely (title/body extraction, image
URLs, entity items, malware-link detection, bounded discovery) rather
than duplicating it - subclasses OnionSpider but replaces __init__ and
start_requests so it never loads the broad seeds file, only ever
targets the one authenticated host, and attaches the decrypted session
cookies to every request. allowed_domains is locked to that single
host, so cookies are never sent to (and can never leak to) any other
domain even if the crawl follows an off-site link during discovery.

Run by hand only, never scheduled:
    scrapy crawl onion_authenticated -a host=<host>
"""
import json
import sys

import scrapy

sys.path.insert(0, ".")
from .. import db, session_crypto
from .onion_spider import OnionSpider


class AuthenticatedSpider(OnionSpider):
    name = "onion_authenticated"

    # Meaningfully more conservative than the default crawl (2s delay,
    # 2 concurrent/domain) - a real account is worth protecting more
    # carefully than an anonymous crawl's own throughput.
    custom_settings = {
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
        "DOWNLOAD_DELAY": 5,
    }

    def __init__(self, host=None, *args, **kwargs):
        # Deliberately skip OnionSpider.__init__ - it loads a seeds file
        # plus every known domain for a broad sweep, which is exactly
        # the unattended behavior this spider exists to avoid.
        scrapy.Spider.__init__(self, *args, **kwargs)
        if not host:
            raise ValueError("host is required: scrapy crawl onion_authenticated -a host=<host>")

        self.allowed_domains = [host]
        self.start_urls = [f"http://{host}/"]
        self._target_host = host

        conn = db.get_connection()
        try:
            encrypted = db.get_authenticated_session(conn, host)
            if encrypted:
                db.touch_authenticated_session(conn, host)
        finally:
            conn.close()

        if not encrypted:
            raise ValueError(
                f"No active session for {host} - import one first: "
                f"python3 scripts/import_session.py {host} <cookie_json_file>"
            )

        raw = session_crypto.decrypt(encrypted)
        cookie_list = json.loads(raw)
        self.session_cookies = {
            c["name"]: c["value"] for c in cookie_list if "name" in c and "value" in c
        }
        self.logger.info(f"Loaded {len(self.session_cookies)} session cookies for {host}")

    def start_requests(self):
        for url in self.start_urls:
            yield scrapy.Request(url, callback=self.parse, cookies=self.session_cookies)
