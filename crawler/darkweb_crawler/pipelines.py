import logging

from scrapy.exceptions import DropItem

from . import classification, clone_detect, db, email_extract, entity_extract, enrichment, price_extract, safety_rating, search
from .items import DiscoveryItem

logger = logging.getLogger(__name__)


class DiscoveryPipeline:
    """Records a candidate host and drops the item immediately -
    PageItem-shaped stages downstream (Postgres/Enrichment/OpenSearch)
    have no meaning for a link that was never actually crawled."""

    def open_spider(self, spider):
        self.conn = db.get_connection()

    def close_spider(self, spider):
        self.conn.close()

    def process_item(self, item, spider):
        if isinstance(item, DiscoveryItem):
            db.record_discovery_candidate(self.conn, item["host"], item.get("discovered_from"))
            raise DropItem("recorded as a discovery candidate, not crawled")
        return item


class PostgresPipeline:
    def open_spider(self, spider):
        self.conn = db.get_connection()

    def close_spider(self, spider):
        self.conn.close()

    def process_item(self, item, spider):
        domain_id = db.upsert_domain(self.conn, item["domain"], item.get("title"))
        page_id = db.upsert_page(
            self.conn,
            domain_id,
            item["url"],
            item.get("title"),
            item.get("body_text"),
            item.get("http_status"),
            item.get("meta_description"),
            item.get("published_at"),
        )
        if item.get("favicon_url"):
            db.update_domain_favicon_url(self.conn, domain_id, item["favicon_url"])
        if item.get("image_urls"):
            db.update_page_image_urls(self.conn, page_id, item["image_urls"])
        item["domain_id"] = domain_id
        item["page_id"] = page_id
        return item


class EnrichmentPipeline:
    """Classifies each page locally (category/language/PII flag), and -
    for anything not already known-legitimate - checks it against a
    reference set of known legitimate-mirror pages for a possible
    phishing clone. The reference set is built once per crawl run
    (open_spider), not recomputed per page."""

    def open_spider(self, spider):
        conn = db.get_connection()
        try:
            legit_pages = db.get_legitimate_mirror_pages(conn)
        finally:
            conn.close()
        self.reference_set = clone_detect.build_legitimate_reference_set(legit_pages)

    def process_item(self, item, spider):
        try:
            result = enrichment.classify_page(item.get("title"), item.get("body_text"))
        except Exception:
            logger.exception("Enrichment failed for %s, leaving it unenriched", item["url"])
            return item
        item["content_category"] = result["category"]
        item["language"] = result["language"]
        item["pii_present"] = result["pii_present"]

        if result["category"] == "marketplace":
            item["prices"] = price_extract.extract_prices(item.get("body_text"))

        if result["pii_present"]:
            item["email_hashes"] = email_extract.extract_email_hashes(item.get("body_text"))

        # Not gated by category - a crypto address or IP can appear on any
        # page type (a forum post, a leak listing, a marketplace vendor
        # profile), not just marketplaces.
        item["entities"] = entity_extract.extract_entities(item.get("body_text"))

        # Semantic-search embedding - reuses the same model already
        # loaded for classification above, no extra cost beyond the
        # encode() call itself. Never allowed to crash the crawl.
        try:
            item["embedding"] = classification.embed(
                f"{item.get('title') or ''}. {(item.get('body_text') or '')[:2000]}"
            )
        except Exception:
            logger.exception("Embedding failed for %s, indexing without one", item["url"])
            item["embedding"] = None

        if result["category"] != "legitimate-mirror":
            item["clone_suspect"] = clone_detect.is_clone_of_legitimate(
                item.get("body_text"), item.get("domain"), self.reference_set
            )

        return item


class DBUpdatePipeline:
    """Writes the EnrichmentPipeline's results back to Postgres, then
    recomputes the owning domain's safety rating from all of its pages'
    categories and risk signals seen so far - so a domain's rating stays
    current as more of its pages get crawled and classified, not just
    at the end of a full crawl."""

    def open_spider(self, spider):
        self.conn = db.get_connection()

    def close_spider(self, spider):
        self.conn.close()

    def process_item(self, item, spider):
        if "content_category" in item:
            db.update_page_enrichment(
                self.conn,
                item["page_id"],
                item["content_category"],
                item.get("language"),
                item.get("pii_present"),
            )

            if item.get("has_malware_link"):
                db.update_domain_malware_flag(self.conn, item["domain_id"], True)
            if item.get("clone_suspect"):
                db.update_domain_clone_suspect(self.conn, item["domain_id"], True)

            if db.is_domain_verified(self.conn, item["domain_id"]):
                rating = "legitimate"
            else:
                categories = db.get_domain_page_categories(self.conn, item["domain_id"])
                malware_flag, clone_suspect = db.get_domain_risk_flags(self.conn, item["domain_id"])
                rating = safety_rating.rate(
                    categories, malware_flag=malware_flag, clone_suspect=clone_suspect
                )
            db.update_domain_safety_rating(self.conn, item["domain_id"], rating)

        if item.get("prices"):
            db.clear_page_prices(self.conn, item["page_id"])
            db.insert_page_prices(self.conn, item["page_id"], item["domain_id"], item["prices"])

        if "entities" in item:
            db.insert_page_entities(self.conn, item["page_id"], item["domain_id"], item["entities"])

        for email_hash in item.get("email_hashes", []):
            db.upsert_breach_email_hash(self.conn, email_hash)

        return item


class OpenSearchPipeline:
    def open_spider(self, spider):
        self.client = search.get_client()
        search.ensure_index(self.client)

    def process_item(self, item, spider):
        search.index_page(
            self.client,
            item.get("domain_id") or item["url"],
            item["url"],
            item["domain"],
            item.get("title"),
            item.get("body_text"),
            item.get("content_category"),
            item.get("language"),
            item.get("pii_present"),
            item.get("meta_description"),
            item.get("published_at"),
            item.get("embedding"),
        )
        return item
