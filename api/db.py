import os
from urllib.parse import quote

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


def get_domain_meta(conn, hosts):
    if not hosts:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT host, safety_rating, is_up, last_seen_at, preview_description FROM domains WHERE host = ANY(%s)",
            (hosts,),
        )
        rows = cur.fetchall()
    return {
        host: {"safety_rating": rating, "is_up": is_up, "last_seen_at": last_seen_at, "preview_description": desc}
        for host, rating, is_up, last_seen_at, desc in rows
    }


def get_domain_summary(conn, host):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT d.host, d.safety_rating, d.title, d.first_seen_at, d.last_seen_at, d.is_up,
                   count(p.id) AS page_count
            FROM domains d
            LEFT JOIN pages p ON p.domain_id = d.id
            WHERE d.host = %s
            GROUP BY d.id
            """,
            (host,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        columns = ["host", "safety_rating", "title", "first_seen_at", "last_seen_at", "is_up", "page_count"]
        return dict(zip(columns, row))


# Categories/ratings that exist purely for internal safety-classification
# precision and must never leak into a public payload - not just never be
# filterable (api/main.py's VALID_CATEGORIES already blocks that), but
# never show up as a count either, since "csam: 3" in a stats response
# would itself be the leak. Duplicated here rather than imported from
# crawler.darkweb_crawler.classification/api.labels on purpose - api/ and
# crawler/ are deliberately separate deployable packages (see main.py's
# module docstring), so this list is kept in the one place (db.py) that
# builds the raw, ungated aggregate.
_INTERNAL_ONLY_CATEGORIES = {"extremism-violence", "csam"}
_SUPPRESSED_RATINGS = {"csam-confirmed"}


def get_stats(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM domains")
        domain_count = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM pages")
        page_count = cur.fetchone()[0]
        cur.execute(
            """
            SELECT content_category, count(*)
            FROM pages
            WHERE content_category IS NOT NULL
            GROUP BY content_category
            ORDER BY count(*) DESC
            """
        )
        category_counts = {
            category: count for category, count in cur.fetchall()
            if category not in _INTERNAL_ONLY_CATEGORIES
        }
        cur.execute(
            """
            SELECT safety_rating, count(*)
            FROM domains
            GROUP BY safety_rating
            """
        )
        rating_counts = {
            rating: count for rating, count in cur.fetchall()
            if rating not in _SUPPRESSED_RATINGS
        }
        cur.execute("SELECT status, count(*) FROM discovery_candidates GROUP BY status")
        discovery_counts = dict(cur.fetchall())
    return {
        "domain_count": domain_count,
        "page_count": page_count,
        "category_counts": category_counts,
        "rating_counts": rating_counts,
        "discovery_counts": discovery_counts,
    }


def get_ransomware_victims(conn, group=None, limit=50, offset=0):
    with conn.cursor() as cur:
        if group:
            cur.execute(
                """
                SELECT id, group_name, victim_name, discovered_at, description, link, magnet, has_screenshot
                FROM ransomware_victims
                WHERE group_name = %s ORDER BY discovered_at DESC NULLS LAST LIMIT %s OFFSET %s
                """,
                (group, limit, offset),
            )
        else:
            cur.execute(
                """
                SELECT id, group_name, victim_name, discovered_at, description, link, magnet, has_screenshot
                FROM ransomware_victims
                ORDER BY discovered_at DESC NULLS LAST LIMIT %s OFFSET %s
                """,
                (limit, offset),
            )
        rows = cur.fetchall()
        if group:
            cur.execute("SELECT count(*) FROM ransomware_victims WHERE group_name = %s", (group,))
        else:
            cur.execute("SELECT count(*) FROM ransomware_victims")
        total = cur.fetchone()[0]
    victims = [
        {
            "id": i,
            "group_name": g,
            "victim_name": v,
            "discovered_at": d,
            "description": desc,
            # RansomLook's per-post "link" field (confirmed via a live check
            # across every distinct pattern present in this table on
            # 2026-09-03 - /blog/disclosures/*, /site/*, /n/*, /post/*,
            # /r/*, /target/*, /news/* - every single one 404s, including
            # ones their own API returned for victims imported that same
            # morning, so this isn't stale historical data going bad, it's
            # their API currently serving dead post-level paths) is not
            # used for the public link anymore. /group/{name} is verified
            # live and stable, so every victim links to its group page
            # instead - never a specific post that can 404.
            "link": f"https://www.ransomlook.io/group/{quote(g, safe='')}",
            "magnet": mg,
            "has_screenshot": bool(hs),
        }
        for i, g, v, d, desc, lk, mg, hs in rows
    ]
    return victims, total


def get_all_victim_names(conn, limit=2000):
    """All victim names ordered most-recent-first, for a new watchlist's
    retro-hunt pass - capped, since this exists to bound a single
    creation request's scan, not to page through every victim ever."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, group_name, victim_name FROM ransomware_victims "
            "ORDER BY discovered_at DESC NULLS LAST LIMIT %s",
            (limit,),
        )
        return cur.fetchall()


def get_ransomware_group_counts(conn, limit=25):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT group_name, count(*) FROM ransomware_victims
            GROUP BY group_name ORDER BY count(*) DESC LIMIT %s
            """,
            (limit,),
        )
        return [{"group_name": g, "victim_count": c} for g, c in cur.fetchall()]


def create_watchlist(conn, keyword, webhook_url, unsubscribe_token):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO watchlists (keyword, webhook_url, unsubscribe_token)
            VALUES (%s, %s, %s) RETURNING id
            """,
            (keyword, webhook_url, unsubscribe_token),
        )
        return cur.fetchone()[0]


def delete_watchlist(conn, unsubscribe_token):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM watchlists WHERE unsubscribe_token = %s RETURNING id", (unsubscribe_token,))
        return cur.fetchone() is not None


def touch_watchlist(conn, watchlist_id):
    with conn.cursor() as cur:
        cur.execute("UPDATE watchlists SET last_triggered_at = now() WHERE id = %s", (watchlist_id,))


def create_site_report(conn, host, reason):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO site_reports (host, reason) VALUES (%s, %s) RETURNING id",
            (host, reason),
        )
        return cur.fetchone()[0]


def get_pending_reports(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, host, reason, reported_at FROM site_reports WHERE status = 'pending' ORDER BY reported_at DESC"
        )
        return [
            {"id": i, "host": h, "reason": r, "reported_at": t}
            for i, h, r, t in cur.fetchall()
        ]


def resolve_site_report(conn, report_id, note, override_rating=None):
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE site_reports SET status = 'resolved', resolved_at = now(), resolution_note = %s
            WHERE id = %s RETURNING host
            """,
            (note, report_id),
        )
        row = cur.fetchone()
    if row and override_rating:
        with conn.cursor() as cur:
            cur.execute("UPDATE domains SET safety_rating = %s WHERE host = %s", (override_rating, row[0]))
    return row is not None


def create_verification_claim(conn, host, token):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO verification_claims (host, token) VALUES (%s, %s) RETURNING id",
            (host, token),
        )
        return cur.fetchone()[0]


def get_verification_status(conn, host):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT status, created_at, verified_at FROM verification_claims
            WHERE host = %s ORDER BY created_at DESC LIMIT 1
            """,
            (host,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    status, created, verified = row
    return {"status": status, "created_at": created, "verified_at": verified}


def check_breach_email(conn, email_hash):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT first_seen_at, last_seen_at, sighting_count FROM breach_emails WHERE email_hash = %s",
            (email_hash,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    first_seen, last_seen, count = row
    return {"first_seen_at": first_seen, "last_seen_at": last_seen, "sighting_count": count}


def get_marketplace_trends(conn, domain=None):
    with conn.cursor() as cur:
        query = """
            SELECT d.host, pp.currency, count(*), avg(pp.amount), min(pp.amount), max(pp.amount)
            FROM page_prices pp
            JOIN domains d ON d.id = pp.domain_id
        """
        params = []
        if domain:
            query += " WHERE d.host = %s"
            params.append(domain)
        query += " GROUP BY d.host, pp.currency ORDER BY d.host, pp.currency"
        cur.execute(query, params)
        rows = cur.fetchall()
    return [
        {
            "domain": host,
            "currency": currency,
            "count": count,
            "avg_price": float(avg),
            "min_price": float(mn),
            "max_price": float(mx),
        }
        for host, currency, count, avg, mn, mx in rows
    ]


def search_entities(conn, entity_type, value, limit=20, offset=0):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT p.url, p.title, p.content_category, p.published_at,
                   d.host, d.safety_rating, d.is_up, d.last_seen_at, pe.entity_value
            FROM page_entities pe
            JOIN pages p ON p.id = pe.page_id
            JOIN domains d ON d.id = pe.domain_id
            WHERE pe.entity_type = %s AND pe.entity_value = %s
            ORDER BY p.crawled_at DESC
            LIMIT %s OFFSET %s
            """,
            (entity_type, value, limit, offset),
        )
        rows = cur.fetchall()
        cur.execute(
            "SELECT count(*) FROM page_entities WHERE entity_type = %s AND entity_value = %s",
            (entity_type, value),
        )
        total = cur.fetchone()[0]
    results = [
        {
            "url": url,
            "title": title,
            "content_category": category,
            "published_at": published,
            "domain": host,
            "safety_rating": rating,
            "is_up": is_up,
            "last_seen_at": last_seen,
            "snippet": f"Matched {entity_type}: {entity_value}",
        }
        for url, title, category, published, host, rating, is_up, last_seen, entity_value in rows
    ]
    return results, total


def get_page_by_url(conn, url):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT title, body_text, content_category FROM pages WHERE url = %s",
            (url,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    title, body_text, category = row
    return {"title": title, "body_text": body_text, "content_category": category}


def get_recent_cve_mentions(conn, limit=20):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT entity_value, count(*) AS mentions, max(extracted_at) AS last_seen
            FROM page_entities
            WHERE entity_type = %s
            GROUP BY entity_value
            ORDER BY last_seen DESC
            LIMIT %s
            """,
            ("cve", limit),
        )
        rows = cur.fetchall()
    return [
        {"cve_id": cve_id, "mentions": mentions, "last_seen_at": last_seen}
        for cve_id, mentions, last_seen in rows
    ]


def get_transparency_stats(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM site_reports WHERE status = %s AND resolved_at >= now() - interval '30 days'",
            ("resolved",),
        )
        reports_resolved_30d = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM site_reports WHERE status = %s", ("pending",))
        reports_pending = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM verification_claims WHERE status = %s", ("verified",))
        verifications_approved = cur.fetchone()[0]
        cur.execute("SELECT safety_rating, count(*) FROM domains GROUP BY safety_rating")
        rating_breakdown = dict(cur.fetchall())
    return {
        "reports_resolved_last_30d": reports_resolved_30d,
        "reports_pending": reports_pending,
        "verifications_approved": verifications_approved,
        "rating_breakdown": rating_breakdown,
    }


def create_digest_subscription(conn, email, unsubscribe_token):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO digest_subscriptions (email, unsubscribe_token)
            VALUES (%s, %s)
            ON CONFLICT (email) DO UPDATE SET active = true, unsubscribe_token = EXCLUDED.unsubscribe_token
            RETURNING id
            """,
            (email, unsubscribe_token),
        )
        return cur.fetchone()[0]


def delete_digest_subscription(conn, unsubscribe_token):
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE digest_subscriptions SET active = false WHERE unsubscribe_token = %s RETURNING id",
            (unsubscribe_token,),
        )
        return cur.fetchone() is not None
