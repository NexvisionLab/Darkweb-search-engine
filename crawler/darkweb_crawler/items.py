import scrapy


class PageItem(scrapy.Item):
    url = scrapy.Field()
    domain = scrapy.Field()
    title = scrapy.Field()
    body_text = scrapy.Field()
    http_status = scrapy.Field()
    domain_id = scrapy.Field()
    page_id = scrapy.Field()
    content_category = scrapy.Field()
    language = scrapy.Field()
    pii_present = scrapy.Field()
    prices = scrapy.Field()
    email_hashes = scrapy.Field()
    has_malware_link = scrapy.Field()
    clone_suspect = scrapy.Field()
    meta_description = scrapy.Field()
    published_at = scrapy.Field()
    favicon_url = scrapy.Field()
    entities = scrapy.Field()
    embedding = scrapy.Field()
    image_urls = scrapy.Field()


class DiscoveryItem(scrapy.Item):
    """A .onion host linked-to from a crawled page that isn't already
    known - see onion_spider.py's bounded open-link-following. Never
    crawled directly; recorded as a candidate for verify_discoveries.py
    to check and promote separately."""

    host = scrapy.Field()
    discovered_from = scrapy.Field()
