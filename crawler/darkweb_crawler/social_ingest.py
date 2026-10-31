"""Shared ingest logic for the social/narrative-intelligence sources
(2026-09-19; scope: social-narrative-intelligence-scope.md in the plans
dir). The three collectors (Bluesky Jetstream, Mastodon timelines,
public Telegram channel pages) all funnel through here so the filter,
retention and erasure rules are identical everywhere.

Design rules, each deliberate:
- FILTER AT INGEST. Bluesky alone is millions of posts a day; an
  unfiltered archive is not viable and would also hoard personal data
  for no purpose. A post is stored only if should_keep() finds a
  threat-relevant signal, and the reason is recorded on the row.
- Telegram channels are the exception: the channel list is curated
  (handles the dark-web crawl found, or operator-added), so every post
  from a listed channel is kept.
- Posts expire after RETENTION_DAYS (schema default) and can be erased
  per author, which also suppresses re-ingest - see erase_author().
- Text and links only. Media URLs are recorded but never fetched here;
  fetching media has to go through the csam/sensitivity gates first.
- Posts self-labelled adult by their author are dropped, not stored."""
import re

import psycopg

from . import entity_extract

RETENTION_DAYS = 30
MAX_TEXT_CHARS = 4000

# Entity types that mean something on their own. Deliberately excludes
# the noisy ones entity_extract also emits (phone, ip, price, postcodes,
# domain_mention, telegram_handle - t.me links are everywhere on social).
HIGH_SIGNAL_ENTITY_TYPES = frozenset({
    "btc", "eth", "xmr", "altcoin_address", "bitcoin_private_key",
    "crypto_wallet_seed_phrase", "cve", "onion_link", "session_token",
    "api_key", "private_key", "ransom_amount",
})

# Threat-relevant vocabulary. Broad classes, not a group-name list that
# would rot; group names come in through watches.
VOCAB_RE = re.compile(
    r"\b(ransomware|ransom\s+note|leak\s+site|data\s+leak|leaked\s+(?:database|data|credentials)|"
    r"db\s+leak|data\s+breach|breached|infostealer|stealer\s+logs?|combolists?|credential\s+dump|"
    r"initial\s+access|access\s+broker|zero-?day|0-?day|exploited\s+in\s+the\s+wild|"
    r"dark\s?web|darknet|threat\s+actor|apt\d{1,2}|c2\s+server|botnet|phishing\s+kit|"
    r"malware|exfiltrat\w+|extortion)\b",
    re.IGNORECASE,
)

# Cheap substring markers checked before running the (heavier) entity
# extractor, so the firehose path stays fast.
_ENTITY_HINTS = ("0x", "bc1", ".onion", "CVE-", "cve-", "xmr", "BEGIN ", "ransom", "eyJ")

_ADULT_LABELS = {"porn", "sexual", "nudity", "graphic-media"}


def load_watch_terms(conn):
    """Active social-watch terms (pro's social_watches table), lower-cased,
    or None if that table doesn't exist yet. A post matching one is kept
    at ingest even when it would fail the generic filter - otherwise a
    watch could only ever match posts that happened to pass it."""
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT lower(term) FROM social_watches WHERE NOT revoked")
            return [row[0] for row in cur.fetchall() if row[0] and len(row[0]) >= 3]
    except psycopg.errors.UndefinedTable:
        return None


def compile_watch_terms(terms):
    """One case-insensitive alternation over all terms (longest first), or
    None when there are none."""
    if not terms:
        return None
    return re.compile("|".join(re.escape(t) for t in sorted(set(terms), key=len, reverse=True)), re.IGNORECASE)


def should_keep(text, curated=False, watch_re=None):
    """Returns (keep, reasons, entities). `curated=True` (Telegram
    channels from the curated list) keeps everything but still records
    entities and vocabulary hits for later analysis. `watch_re` is the
    compiled active watch terms; a match keeps the post (reason "watch")."""
    if not text:
        return False, [], []
    text = text[:MAX_TEXT_CHARS]
    reasons = []
    entities = []

    if VOCAB_RE.search(text):
        reasons.append("vocab")
    if watch_re is not None and watch_re.search(text):
        reasons.append("watch")
    if curated or reasons or any(h in text for h in _ENTITY_HINTS):
        entities = [e for e in entity_extract.extract_entities(text) if e["entity_type"] in HIGH_SIGNAL_ENTITY_TYPES]
        if entities:
            reasons.append("entity:" + ",".join(sorted({e["entity_type"] for e in entities})))
    if curated:
        reasons.append("curated-source")
    return bool(reasons), reasons, entities


def is_adult_labelled(labels):
    """Bluesky self-labels arrive as a list of label values."""
    return bool(labels) and any(str(v).lower() in _ADULT_LABELS for v in labels)


def _author_key(value):
    return (value or "").strip().lower()


def is_suppressed(conn, platform, author_id, author_handle):
    keys = [k for k in (_author_key(author_id), _author_key(author_handle)) if k]
    if not keys:
        return False
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM social_suppressed_authors WHERE platform = %s AND author_key = ANY(%s) LIMIT 1",
            (platform, keys),
        )
        return cur.fetchone() is not None


def store_post(conn, post, reasons, entities):
    """Inserts one post (dict with platform, source, external_id, author_id,
    author_handle, text, lang, url, posted_at, hashtags, links, media_urls).
    Returns the new row id, or None if it was a duplicate or the author is
    suppressed."""
    if is_suppressed(conn, post["platform"], post.get("author_id"), post.get("author_handle")):
        return None
    # The URL comes from a third party and ends up in an href downstream;
    # anything that isn't plain http(s) (javascript:, data:) is dropped.
    if post.get("url") and not re.match(r"https?://", post["url"], re.IGNORECASE):
        post = {**post, "url": None}
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO social_posts
                (platform, source, external_id, author_id, author_handle, text, lang, url,
                 posted_at, hashtags, links, media_urls, keep_reasons, author_created_at, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now() + (%s || ' days')::interval)
            ON CONFLICT (platform, external_id) DO NOTHING
            RETURNING id
            """,
            (
                post["platform"], post["source"], post["external_id"], post.get("author_id"),
                post.get("author_handle"), post["text"][:MAX_TEXT_CHARS], post.get("lang"), post.get("url"),
                post.get("posted_at"), post.get("hashtags", []), post.get("links", []),
                post.get("media_urls", []), reasons, post.get("author_created_at"), str(RETENTION_DAYS),
            ),
        )
        row = cur.fetchone()
        if row is None:
            return None
        post_id = row[0]
        for e in entities:
            cur.execute(
                "INSERT INTO social_post_entities (post_id, entity_type, entity_value) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                (post_id, e["entity_type"], e["entity_value"]),
            )
    return post_id


def get_cursor(conn, platform, source):
    with conn.cursor() as cur:
        cur.execute("SELECT cursor FROM social_cursors WHERE platform = %s AND source = %s", (platform, source))
        row = cur.fetchone()
    return row[0] if row else None


def set_cursor(conn, platform, source, cursor):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO social_cursors (platform, source, cursor) VALUES (%s, %s, %s)
            ON CONFLICT (platform, source) DO UPDATE SET cursor = EXCLUDED.cursor, updated_at = now()
            """,
            (platform, source, str(cursor)),
        )


def purge_expired(conn):
    """Deletes expired posts (entities cascade). Returns rows removed."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM social_posts WHERE expires_at < now()")
        return cur.rowcount


def erase_author(conn, platform, author, reason="erasure request"):
    """GDPR erasure: deletes every stored post by this author (matched on
    author_id OR handle, case-insensitive) and suppresses them from future
    ingest. Returns the number of posts deleted."""
    key = _author_key(author)
    if not key:
        raise ValueError("author is required")
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM social_posts WHERE platform = %s AND (lower(author_id) = %s OR lower(author_handle) = %s)",
            (platform, key, key),
        )
        deleted = cur.rowcount
        cur.execute(
            """
            INSERT INTO social_suppressed_authors (platform, author_key, reason) VALUES (%s, %s, %s)
            ON CONFLICT (platform, author_key) DO NOTHING
            """,
            (platform, key, reason),
        )
    return deleted
