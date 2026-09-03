import os
from urllib.parse import urlparse

import scrapy

from .. import page_metadata
from ..items import DiscoveryItem, PageItem
from .. import db

DANGEROUS_EXTENSIONS = {
    ".exe", ".scr", ".bat", ".cmd", ".msi", ".dll", ".jar",
    ".apk", ".vbs", ".ps1", ".com", ".pif",
}

DISCOVERY_LIMIT_PER_PAGE = 5
IMAGE_URLS_PER_PAGE = 5


class OnionSpider(scrapy.Spider):
    """Crawls .onion seed URLs listed one-per-line in seeds.txt (repo root
    of the crawler/ dir, or pass -a seeds_file=path), plus every domain
    already known in the database - so a domain discovered on a previous
    run keeps getting recrawled going forward without needing to be
    re-seeded from a file every time, and so does an older RansomLook
    seed that has since dropped off the "top N groups" refresh. Seeds
    are deliberately NOT hardcoded - real, currently-live onion addresses
    have to come from a maintained source rather than a guess baked into
    source code, since onion addresses change constantly.

    Also does bounded open-link discovery: a link to a .onion host that
    isn't already known gets recorded as a candidate (see
    scripts/verify_discoveries.py), never crawled directly - the same
    "follow links, find new sites" method real dark-web search engines
    like Ahmia use, capped per page so one link-farm page can't flood
    the candidate list."""

    name = "onion"
    allowed_domains = []  # populated from seeds + known domains at runtime

    def __init__(self, seeds_file=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        seeds_file = seeds_file or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "seeds.txt"
        )
        self.start_urls = []
        if os.path.exists(seeds_file):
            with open(seeds_file) as f:
                self.start_urls = [
                    line.strip() for line in f if line.strip() and not line.startswith("#")
                ]

        try:
            conn = db.get_connection()
            known_hosts = db.get_all_domain_hosts(conn)
            conn.close()
            existing = {urlparse(u).hostname for u in self.start_urls}
            for host in known_hosts:
                if host not in existing:
                    self.start_urls.append(f"http://{host}/")
        except Exception as e:
            self.log(f"Could not load known domains from DB: {e}")

        for url in self.start_urls:
            host = urlparse(url).hostname
            if host and host not in self.allowed_domains:
                self.allowed_domains.append(host)

    def parse(self, response):
        # Real leak sites link directly to non-HTML resources (a JSON API
        # response, or an actual stolen-data file like .xlsx/.pdf/.zip) as
        # part of extortion posts. response.css() raises on both - a
        # binary response has no text content at all, and Scrapy's JSON
        # auto-detection returns a selector type CSS can't query. Record
        # that the resource exists without trying to parse it as a page,
        # rather than letting either case crash the whole request.
        meta_description = None
        published_at = None
        favicon_url = None

        try:
            title = response.css("title::text").get(default="").strip()
            paragraphs = response.css(
                "p ::text, h1 ::text, h2 ::text, h3 ::text, article ::text"
            ).getall()
            content_text = paragraphs if paragraphs else response.css("body *::text").getall()
            body_text = " ".join(t.strip() for t in content_text if t.strip()).strip()[:20000]
            is_html = True
            meta_description = page_metadata.extract_meta_description(response)
            published_at = page_metadata.extract_published_at(response)
            favicon_url = page_metadata.extract_favicon_url(response)
        except (scrapy.exceptions.NotSupported, ValueError) as e:
            self.log(f"Non-HTML resource at {response.url} ({e}) - recording, not parsing")
            title = response.url.rsplit("/", 1)[-1] or response.url
            body_text = None
            is_html = False

        has_malware_link = False
        image_urls = []

        if is_html:
            hrefs = response.css("a::attr(href)").getall()
            for href in hrefs:
                path = urlparse(href).path.lower()
                if any(path.endswith(ext) for ext in DANGEROUS_EXTENSIONS):
                    has_malware_link = True
                    break
            # Recorded here, processed later (see scripts/process_page_images.py)
            # - OCR/QR decoding is real per-image work and has no business
            # running inline in the crawl loop, same reasoning as preview
            # capture. Capped per page so one image-heavy listing page
            # can't blow up the processing queue on its own.
            image_urls = [
                response.urljoin(src)
                for src in response.css("img::attr(src)").getall()
                if src and not src.startswith("data:")
            ][:IMAGE_URLS_PER_PAGE]

        yield PageItem(
            url=response.url,
            domain=urlparse(response.url).hostname,
            title=title,
            body_text=body_text,
            http_status=response.status,
            has_malware_link=has_malware_link,
            meta_description=meta_description,
            published_at=published_at,
            favicon_url=favicon_url,
            image_urls=image_urls,
        )

        if not is_html:
            return

        discovered_count = 0
        for href in hrefs:
            # Never follow a link to an executable - recording that the
            # domain links to one (above) is enough; actually requesting
            # it would mean downloading the file.
            path = urlparse(href).path.lower()
            if any(path.endswith(ext) for ext in DANGEROUS_EXTENSIONS):
                continue
            next_url = response.urljoin(href)
            host = urlparse(next_url).hostname
            if not host:
                continue
            if host in self.allowed_domains:
                yield scrapy.Request(next_url, callback=self.parse)
            elif host.endswith(".onion") and discovered_count < DISCOVERY_LIMIT_PER_PAGE:
                yield DiscoveryItem(host=host, discovered_from=response.url)
                discovered_count += 1
