"""One-time backfill for pages that never got enriched because of the
PageItem missing-field bug (fixed in items.py) - every page crawled
while that bug was live got dropped by EnrichmentPipeline before
DBUpdatePipeline/OpenSearchPipeline ever ran, so content_category,
language, pii_present, entities, embedding, and the owning domain's
safety_rating were all silently skipped. Runs the exact same pipeline
classes the live crawl uses, directly against each broken page's
already-stored body_text - no re-crawl over Tor needed."""
import sys
sys.path.insert(0, ".")

from darkweb_crawler import db
from darkweb_crawler.pipelines import EnrichmentPipeline, DBUpdatePipeline, OpenSearchPipeline
from darkweb_crawler.items import PageItem


class FakeSpider:
    pass


def main():
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT p.id, p.domain_id, p.url, d.host, p.title, p.body_text
        FROM pages p JOIN domains d ON d.id = p.domain_id
        WHERE p.enriched_at IS NULL AND p.body_text IS NOT NULL
        """
    )
    rows = cur.fetchall()
    conn.close()
    print(f"{len(rows)} pages need enrichment backfill")

    spider = FakeSpider()
    enrichment_pipeline = EnrichmentPipeline()
    enrichment_pipeline.open_spider(spider)
    db_pipeline = DBUpdatePipeline()
    db_pipeline.open_spider(spider)
    os_pipeline = OpenSearchPipeline()
    os_pipeline.open_spider(spider)

    done = 0
    failed = 0
    for page_id, domain_id, url, host, title, body_text in rows:
        item = PageItem()
        item["url"] = url
        item["domain"] = host
        item["title"] = title
        item["body_text"] = body_text
        item["domain_id"] = domain_id
        item["page_id"] = page_id
        try:
            item = enrichment_pipeline.process_item(item, spider)
            db_pipeline.process_item(item, spider)
            os_pipeline.process_item(item, spider)
            done += 1
        except Exception as e:
            failed += 1
            print(f"failed: {url} ({e})")
        if done % 100 == 0 and done:
            print(f"...{done}/{len(rows)}")

    db_pipeline.conn.close()
    print(f"Backfilled {done}/{len(rows)} pages, {failed} failed")


if __name__ == "__main__":
    main()
