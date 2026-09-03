import os
import psycopg


def get_connection():
    return psycopg.connect(
        host=os.environ.get("DB_HOST", "127.0.0.1"),
        port=int(os.environ.get("DB_PORT", "5432")),
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        dbname=os.environ["POSTGRES_DB"],
        autocommit=True,
    )


def set_domain_source_type(conn, domain_id, source_type):
    with conn.cursor() as cur:
        cur.execute("UPDATE domains SET source_type = %s WHERE id = %s", (source_type, domain_id))


def upsert_domain(conn, host, title):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO domains (host, title, last_seen_at)
            VALUES (%s, %s, now())
            ON CONFLICT (host) DO UPDATE
                SET last_seen_at = now(),
                    title = COALESCE(EXCLUDED.title, domains.title)
            RETURNING id
            """,
            (host, title),
        )
        return cur.fetchone()[0]


def upsert_page(conn, domain_id, url, title, body_text, http_status, meta_description=None, published_at=None):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO pages (domain_id, url, title, body_text, http_status, meta_description, published_at, crawled_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, now())
            ON CONFLICT (url) DO UPDATE
                SET title = EXCLUDED.title,
                    body_text = EXCLUDED.body_text,
                    http_status = EXCLUDED.http_status,
                    meta_description = EXCLUDED.meta_description,
                    published_at = EXCLUDED.published_at,
                    crawled_at = now()
            RETURNING id
            """,
            (domain_id, url, title, body_text, http_status, meta_description, published_at),
        )
        return cur.fetchone()[0]


def upsert_authenticated_session(conn, host, encrypted_cookies, notes=None, expires_at=None):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO authenticated_sessions (host, cookies_encrypted, notes, expires_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (host) DO UPDATE
                SET cookies_encrypted = EXCLUDED.cookies_encrypted,
                    notes = EXCLUDED.notes,
                    expires_at = EXCLUDED.expires_at,
                    created_at = now(),
                    revoked_at = NULL
            RETURNING id
            """,
            (host, encrypted_cookies, notes, expires_at),
        )
        return cur.fetchone()[0]


def get_authenticated_session(conn, host):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT cookies_encrypted FROM authenticated_sessions
            WHERE host = %s AND revoked_at IS NULL AND (expires_at IS NULL OR expires_at > now())
            """,
            (host,),
        )
        row = cur.fetchone()
        return row[0] if row else None


def touch_authenticated_session(conn, host):
    with conn.cursor() as cur:
        cur.execute("UPDATE authenticated_sessions SET last_used_at = now() WHERE host = %s", (host,))


def list_authenticated_sessions(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT host, notes, created_at, expires_at, last_used_at, revoked_at "
            "FROM authenticated_sessions ORDER BY created_at DESC"
        )
        return cur.fetchall()


def revoke_authenticated_session(conn, host):
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE authenticated_sessions SET revoked_at = now() WHERE host = %s AND revoked_at IS NULL RETURNING id",
            (host,),
        )
        return cur.fetchone() is not None


def update_page_image_urls(conn, page_id, image_urls):
    if not image_urls:
        return
    with conn.cursor() as cur:
        cur.execute("UPDATE pages SET image_urls = %s WHERE id = %s", (image_urls, page_id))


def get_pages_needing_image_processing(conn, limit):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, domain_id, image_urls FROM pages
            WHERE images_processed_at IS NULL
              AND image_urls IS NOT NULL AND array_length(image_urls, 1) > 0
            ORDER BY crawled_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        return cur.fetchall()


def update_page_image_results(conn, page_id, ocr_text, qr_text):
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE pages SET image_ocr_text = %s, image_qr_text = %s, images_processed_at = now() WHERE id = %s",
            (ocr_text, qr_text, page_id),
        )


def update_domain_favicon_url(conn, domain_id, favicon_url):
    """Only sets it if not already set, so a later page on the same
    domain lacking a favicon link tag doesn't blank out a value a
    previous page already found."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE domains SET favicon_url = %s WHERE id = %s AND favicon_url IS NULL",
            (favicon_url, domain_id),
        )


def get_domains_needing_favicon(conn, limit):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, host, favicon_url FROM domains
            WHERE favicon_url IS NOT NULL AND favicon_captured_at IS NULL
            LIMIT %s
            """,
            (limit,),
        )
        return cur.fetchall()


def mark_domain_favicon_captured(conn, domain_id):
    with conn.cursor() as cur:
        cur.execute("UPDATE domains SET favicon_captured_at = now() WHERE id = %s", (domain_id,))


def update_ransomware_victim_detail(conn, victim_id, description, link, magnet, has_screenshot):
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE ransomware_victims
            SET description = %s, link = %s, magnet = %s, has_screenshot = %s, detail_fetched_at = now()
            WHERE id = %s
            """,
            (description, link, magnet, has_screenshot, victim_id),
        )


def get_all_domain_hosts(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT host FROM domains")
        return [row[0] for row in cur.fetchall()]


def record_discovery_candidate(conn, host, discovered_from):
    """Skips hosts already tracked in domains - a candidate is only
    useful for something genuinely new."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO discovery_candidates (host, discovered_from)
            SELECT %s, %s
            WHERE NOT EXISTS (SELECT 1 FROM domains WHERE host = %s)
            ON CONFLICT (host) DO NOTHING
            """,
            (host, discovered_from, host),
        )


def get_pending_discovery_candidates(conn, limit):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, host FROM discovery_candidates WHERE status = 'pending' ORDER BY discovered_at ASC LIMIT %s",
            (limit,),
        )
        return cur.fetchall()


def mark_discovery_verified(conn, candidate_id, title):
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE discovery_candidates SET status = 'verified', verified_at = now(), title = %s WHERE id = %s",
            (title, candidate_id),
        )


def mark_discovery_dead(conn, candidate_id):
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE discovery_candidates SET status = 'dead', verified_at = now() WHERE id = %s",
            (candidate_id,),
        )


def get_discovery_stats(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT status, count(*) FROM discovery_candidates GROUP BY status")
        return dict(cur.fetchall())


def get_ransomware_victims_needing_detail(conn, limit):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, group_name, victim_name FROM ransomware_victims
            WHERE detail_fetched_at IS NULL
            ORDER BY discovered_at DESC NULLS LAST
            LIMIT %s
            """,
            (limit,),
        )
        return cur.fetchall()


def update_page_enrichment(conn, page_id, category, language, pii_present):
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE pages
            SET content_category = %s, language = %s, pii_present = %s, enriched_at = now()
            WHERE id = %s
            """,
            (category, language, pii_present, page_id),
        )


def get_domain_page_categories(conn, domain_id):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT content_category FROM pages WHERE domain_id = %s AND content_category IS NOT NULL",
            (domain_id,),
        )
        return [row[0] for row in cur.fetchall()]


def update_domain_safety_rating(conn, domain_id, rating):
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE domains SET safety_rating = %s WHERE id = %s",
            (rating, domain_id),
        )


def get_all_domains(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT id, host FROM domains")
        return cur.fetchall()


def update_domain_liveness(conn, domain_id, is_up):
    with conn.cursor() as cur:
        if is_up:
            cur.execute(
                "UPDATE domains SET is_up = true, last_seen_at = now() WHERE id = %s",
                (domain_id,),
            )
        else:
            cur.execute("UPDATE domains SET is_up = false WHERE id = %s", (domain_id,))


def upsert_ransomware_victim(conn, group_name, victim_name, discovered_at):
    """Returns the new row's id if one was actually inserted, else None
    (a duplicate hit ON CONFLICT DO NOTHING)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ransomware_victims (group_name, victim_name, discovered_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (group_name, victim_name, discovered_at) DO NOTHING
            RETURNING id
            """,
            (group_name, victim_name, discovered_at),
        )
        row = cur.fetchone()
        return row[0] if row else None


def insert_page_prices(conn, page_id, domain_id, prices):
    if not prices:
        return
    with conn.cursor() as cur:
        for p in prices:
            cur.execute(
                """
                INSERT INTO page_prices (page_id, domain_id, amount, currency, raw_text)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (page_id, domain_id, p["amount"], p["currency"], p["raw_text"]),
            )


def clear_page_prices(conn, page_id):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM page_prices WHERE page_id = %s", (page_id,))


def get_marketplace_pages(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, domain_id, body_text FROM pages WHERE content_category = 'marketplace' AND body_text IS NOT NULL"
        )
        return cur.fetchall()


def upsert_breach_email_hash(conn, email_hash):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO breach_emails (email_hash)
            VALUES (%s)
            ON CONFLICT (email_hash) DO UPDATE
                SET last_seen_at = now(), sighting_count = breach_emails.sighting_count + 1
            """,
            (email_hash,),
        )


def get_pii_pages(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT id, body_text FROM pages WHERE pii_present = true AND body_text IS NOT NULL")
        return cur.fetchall()


def is_domain_verified(conn, domain_id):
    with conn.cursor() as cur:
        cur.execute("SELECT owner_verified FROM domains WHERE id = %s", (domain_id,))
        row = cur.fetchone()
        return bool(row and row[0])


def get_all_watchlists(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT id, keyword, webhook_url FROM watchlists")
        return cur.fetchall()


def touch_watchlist(conn, watchlist_id):
    with conn.cursor() as cur:
        cur.execute("UPDATE watchlists SET last_triggered_at = now() WHERE id = %s", (watchlist_id,))


def get_pending_verification_claims(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT id, host, token FROM verification_claims WHERE status = 'pending'")
        return cur.fetchall()


def domain_body_contains(conn, host, token):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM pages p JOIN domains d ON d.id = p.domain_id
            WHERE d.host = %s AND p.body_text LIKE %s LIMIT 1
            """,
            (host, f"%{token}%"),
        )
        return cur.fetchone() is not None


def mark_verification_verified(conn, claim_id, host):
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE verification_claims SET status = 'verified', verified_at = now() WHERE id = %s",
            (claim_id,),
        )
        cur.execute("UPDATE domains SET owner_verified = true WHERE host = %s", (host,))


def get_legitimate_mirror_pages(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT d.host, p.body_text FROM pages p JOIN domains d ON d.id = p.domain_id
            WHERE p.content_category = 'legitimate-mirror' AND p.body_text IS NOT NULL
            """
        )
        return cur.fetchall()


def update_domain_clone_suspect(conn, domain_id, flag):
    with conn.cursor() as cur:
        cur.execute("UPDATE domains SET clone_suspect = %s WHERE id = %s", (flag, domain_id))


def get_domain_risk_flags(conn, domain_id):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT malware_link_flag, clone_suspect FROM domains WHERE id = %s", (domain_id,)
        )
        row = cur.fetchone()
        return (bool(row[0]), bool(row[1])) if row else (False, False)


def update_domain_malware_flag(conn, domain_id, flag):
    with conn.cursor() as cur:
        cur.execute("UPDATE domains SET malware_link_flag = %s WHERE id = %s", (flag, domain_id))


def get_marketplace_domains_gone_down(conn):
    """Domains rated illicit-marketplace, currently down, with enough
    prior activity (3+ pages, at least one detected price) to make a
    sudden disappearance a real exit-scam signal rather than routine
    onion-address churn - and not already flagged, so this only reports
    newly-detected cases each run."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT d.id FROM domains d
            WHERE d.safety_rating = 'illicit-marketplace'
              AND d.is_up = false
              AND d.exit_scam_suspect = false
              AND (SELECT count(*) FROM pages p WHERE p.domain_id = d.id) >= 3
              AND EXISTS (SELECT 1 FROM page_prices pp WHERE pp.domain_id = d.id)
            """
        )
        return [row[0] for row in cur.fetchall()]


def update_domain_exit_scam_suspect(conn, domain_id, flag):
    with conn.cursor() as cur:
        cur.execute("UPDATE domains SET exit_scam_suspect = %s WHERE id = %s", (flag, domain_id))


def get_domains_needing_preview(conn, stale_days, limit):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, host, safety_rating FROM domains
            WHERE is_up = true
              AND (preview_updated_at IS NULL OR preview_updated_at < now() - make_interval(days => %s))
            ORDER BY preview_updated_at ASC NULLS FIRST
            LIMIT %s
            """,
            (stale_days, limit),
        )
        return cur.fetchall()


def update_domain_preview_captured(conn, domain_id):
    with conn.cursor() as cur:
        cur.execute("UPDATE domains SET preview_updated_at = now() WHERE id = %s", (domain_id,))


def update_domain_preview_description(conn, domain_id, description):
    with conn.cursor() as cur:
        cur.execute("UPDATE domains SET preview_description = %s WHERE id = %s", (description, domain_id))


def insert_page_entities(conn, page_id, domain_id, entities):
    """Upserts this crawl's entities for the page, preserving history:
    every existing row for the page is first marked still_present=false,
    then each entity found this crawl is inserted (first sighting) or,
    on a repeat, has last_seen_at/sighting_count bumped and
    still_present flipped back true. An entity that isn't in this
    crawl's list stays in the table with still_present=false rather
    than being deleted, so a value that disappears between crawls is
    still queryable instead of silently vanishing."""
    with conn.cursor() as cur:
        cur.execute("UPDATE page_entities SET still_present = false WHERE page_id = %s", (page_id,))
        for e in entities:
            cur.execute(
                """
                INSERT INTO page_entities (page_id, domain_id, entity_type, entity_value)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (page_id, entity_type, entity_value) DO UPDATE
                    SET last_seen_at = now(),
                        sighting_count = page_entities.sighting_count + 1,
                        still_present = true
                """,
                (page_id, domain_id, e["entity_type"], e["entity_value"]),
            )


def get_all_pages_with_body(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT id, domain_id, body_text FROM pages WHERE body_text IS NOT NULL")
        return cur.fetchall()


def get_new_ransomware_victims_since(conn, since):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT group_name, victim_name FROM ransomware_victims WHERE discovered_at >= %s ORDER BY discovered_at DESC",
            (since,),
        )
        return [{"group_name": g, "victim_name": v} for g, v in cur.fetchall()]


def get_newly_flagged_domains_since(conn, since):
    dangerous_or_suspicious = ("illicit-marketplace", "exit-scam-suspect", "fraud-risk", "confirmed-leak", "malware-risk", "phishing-clone-suspect")
    with conn.cursor() as cur:
        cur.execute(
            "SELECT host, safety_rating FROM domains WHERE safety_rating = ANY(%s) AND last_seen_at >= %s ORDER BY last_seen_at DESC",
            (list(dangerous_or_suspicious), since),
        )
        return [{"host": h, "safety_rating": r} for h, r in cur.fetchall()]


def get_active_digest_subscriptions(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT email, unsubscribe_token FROM digest_subscriptions WHERE active = true")
        return [{"email": e, "unsubscribe_token": t} for e, t in cur.fetchall()]
