"""One-off backfill: recomputes every domain's safety_rating against
today's fixed CATEGORY_PRIORITY/RATING_BY_CATEGORY (see
darkweb_crawler/safety_rating.py's 2026-09-03 change) without
re-crawling anything - carding/crypto-services/counterfeits domains
were silently falling through to "unclassified" before that fix, and
DBUpdatePipeline only recomputes a domain's rating when one of its
pages is freshly enriched, so already-crawled domains would otherwise
sit on the stale rating until their next natural recrawl.

Mirrors DBUpdatePipeline.process_item's exact rating logic (same
is_domain_verified / get_domain_page_categories / get_domain_risk_flags
/ safety_rating.rate() call sequence) rather than re-deriving it, so
this can never compute a different answer than the live pipeline would.
Only writes when the recomputed rating actually differs from what's
stored, and reports every domain that changed - not just a count - so
the before/after is auditable, not just trusted."""
import sys

sys.path.insert(0, ".")
from darkweb_crawler import db, safety_rating


def main():
    conn = db.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, host, safety_rating FROM domains ORDER BY id")
            domains = cur.fetchall()

        changed = []
        unchanged = 0
        for domain_id, host, current_rating in domains:
            if db.is_domain_verified(conn, domain_id):
                new_rating = "legitimate"
            else:
                categories = db.get_domain_page_categories(conn, domain_id)
                malware_flag, clone_suspect = db.get_domain_risk_flags(conn, domain_id)
                new_rating = safety_rating.rate(
                    categories, malware_flag=malware_flag, clone_suspect=clone_suspect
                )

            if new_rating != current_rating:
                db.update_domain_safety_rating(conn, domain_id, new_rating)
                changed.append((host, current_rating, new_rating))
            else:
                unchanged += 1

        print(f"Checked {len(domains)} domains.")
        print(f"Unchanged: {unchanged}")
        print(f"Changed: {len(changed)}")
        for host, before, after in changed:
            print(f"  {host}: {before} -> {after}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
