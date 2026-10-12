"""Public (Free tier) view of the Telegram ingest.

What the darknyx.com Telegram tab shows: recent posts from channels an operator
has explicitly published (social_telegram_channels.public, default false),
newest first, as short redacted snippets that link back to the original t.me
post. Deliberately narrower than what Pro sees:
- only channels flagged public, only the last FREE_WINDOW_DAYS days (Pro keeps
  the full retention window) - except that a channel with nothing in that
  window still shows its newest FALLBACK_POSTS posts, flagged `older`, so a
  dormant channel is not a blank row - only text, no media, no author beyond
  the channel;
- snippets are capped at SNIPPET_CHARS, and any link in one is reduced to its
  host ("[link: example.com]"), because posts in ransomware/leak channels
  routinely carry direct links to stolen data and a public page should not
  hand those out. Emails, phone numbers, SSNs and card numbers are masked by
  redact.redact, same as every other Free response.

A post detected as non-English carries its machine translation (text_en, filled in by an
optional translation job - this repository ships only the columns, see
db/schema_social_translation.sql, so without one no translation is shown) beside the original, redacted the same way.

Reads social_posts directly, so the 30-day expiry and the GDPR author erasure
(social_maintenance.py erase) apply here automatically - there is no separate
public copy to keep in sync."""
import re
from urllib.parse import urlparse

from . import redact

SNIPPET_CHARS = 300
FREE_WINDOW_DAYS = 7
FALLBACK_POSTS = 3

_HANDLE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{3,31}$")
_TME_POST_RE = re.compile(r"^https://t\.me/[A-Za-z][A-Za-z0-9_]{3,31}/\d+$")
# One pass over both forms, so an onion host inside a URL is never rewritten a second time
# (a URL pass followed by an onion pass produced "[link: [link: host]]").
_LINK_RE = re.compile(r"https?://[^\s<>\"']+|\b[a-z2-7]{16,56}\.onion(?:/\S*)?", re.IGNORECASE)
_TRAILING_PUNCT = ".,;:!?)]}>"
_MAGNET_RE = re.compile(r"magnet:\?\S+", re.IGNORECASE)

# The text a search may match: the visible excerpt of the original and of its translation.
_SEARCHABLE_TEXT = f"left(v.text, {SNIPPET_CHARS})"
_SEARCHABLE_TEXT_EN = f"left(coalesce(v.text_en, ''), {SNIPPET_CHARS})"

# Content-time of a post: when Telegram says it was posted, else when we first saw it.
_POST_TIME = "COALESCE(p.posted_at, p.first_seen_at)"


def is_valid_handle(handle):
    return bool(handle and _HANDLE_RE.match(handle))


def keyword_boundary_regex(term):
    """PostgreSQL regex for `term` delimited by non-alphanumerics on both sides
    (or the text ends); whitespace inside a multi-word term matches any run of
    whitespace. Same rule as the Pro social watches (pro/db.py) - full-text
    search alone misses a name inside 'example.press' or 't.me/example_news'.
    None if the term has no non-space characters."""
    parts = [re.escape(part) for part in term.split()]
    if not parts:
        return None
    return r"(^|[^[:alnum:]])" + r"\s+".join(parts) + r"($|[^[:alnum:]])"


def _defang_link(match):
    raw = match.group(0)
    link = raw.rstrip(_TRAILING_PUNCT)  # sentence punctuation is not part of the link
    tail = raw[len(link):]
    if link.lower().startswith("http"):
        host = urlparse(link).hostname
    else:
        host = link.split("/")[0].lower()
    return (f"[link: {host}]" if host else "[link]") + tail


def make_snippet(text, limit=SNIPPET_CHARS):
    """Public-safe excerpt: links reduced to their host, whitespace collapsed,
    PII masked, capped at `limit` characters on a word boundary."""
    text = text or ""
    text = _MAGNET_RE.sub("[magnet link]", text)
    text = _LINK_RE.sub(_defang_link, text)
    text = redact.redact(" ".join(text.split()))
    if len(text) <= limit:
        return text
    head = text[:limit]
    if " " in head:
        head = head.rsplit(" ", 1)[0]
    return head.rstrip(" ,.;:-") + "…"


def public_channels(conn):
    """Published channels: posts inside the Free window, how many posts Free
    will actually show for the channel (the window's posts, or up to
    FALLBACK_POSTS older ones when it is dormant), and its newest post."""
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT c.handle,
                   count(p.id) FILTER (WHERE {_POST_TIME} >= now() - make_interval(days => %s)) AS posts_in_window,
                   count(p.id) AS stored_posts,
                   max({_POST_TIME}) AS last_post_at
            FROM social_telegram_channels c
            LEFT JOIN social_posts p
                   ON p.platform = 'telegram' AND p.source = c.handle AND p.expires_at > now()
            WHERE c.public
            GROUP BY c.handle
            ORDER BY posts_in_window DESC, c.handle
            """,
            (FREE_WINDOW_DAYS,),
        )
        rows = cur.fetchall()
    return [
        {
            "channel": handle,
            "posts_in_window": in_window,
            "showing_older": in_window == 0 and stored > 0,
            "visible_posts": in_window if in_window else min(stored, FALLBACK_POSTS),
            "last_post_at": last,
        }
        for handle, in_window, stored, last in rows
    ]


# A post is visible to Free if it is inside the window, or if its channel has nothing
# inside the window and it is one of the channel's newest FALLBACK_POSTS. Search and
# the channel filter apply on top of that visible set, never widen it.
_VISIBLE_CTE = f"""
WITH ranked AS (
    SELECT p.source, p.url, p.text, p.id, p.lang, p.text_en, {_POST_TIME} AS t,
           row_number() OVER (PARTITION BY p.source ORDER BY {_POST_TIME} DESC, p.id DESC) AS rn,
           count(*) FILTER (WHERE {_POST_TIME} >= now() - make_interval(days => %s))
               OVER (PARTITION BY p.source) AS recent_n
    FROM social_posts p JOIN social_telegram_channels c ON c.handle = p.source
    WHERE c.public AND p.platform = 'telegram' AND p.expires_at > now()
), visible AS (
    SELECT *, (t >= now() - make_interval(days => %s)) AS is_recent
    FROM ranked
    WHERE t >= now() - make_interval(days => %s) OR (recent_n = 0 AND rn <= %s)
)
"""


def public_posts(conn, channel=None, q=None, limit=20, offset=0):
    """Returns (posts, total) of what Free may see, newest first. `q` matches as
    a full-text phrase or as a whole token inside a URL/handle. Each post has
    `older`: True when it is outside the window and shown only because its
    channel is dormant."""
    cte_params = [FREE_WINDOW_DAYS, FREE_WINDOW_DAYS, FREE_WINDOW_DAYS, FALLBACK_POSTS]
    where = []
    params = []
    if channel:
        where.append("v.source = %s")
        params.append(channel.lower())
    if q:
        # matches the original text or its English translation, so an English-speaking
        # visitor searching "drone" also finds a Ukrainian post about one
        # Search covers only what a visitor can SEE: the first SNIPPET_CHARS of the post (and of its
        # translation). Matching the full text would let someone confirm that a name appears in the
        # part of a post the page deliberately does not show (decided 2026-09-21).
        clause = (f"(to_tsvector('simple', {_SEARCHABLE_TEXT}) @@ phraseto_tsquery('simple', %s)"
                  f" OR to_tsvector('simple', {_SEARCHABLE_TEXT_EN}) @@ phraseto_tsquery('simple', %s))")
        params.extend([q, q])
        boundary = keyword_boundary_regex(q)
        if boundary:
            clause = f"({clause} OR {_SEARCHABLE_TEXT} ~* %s OR {_SEARCHABLE_TEXT_EN} ~* %s)"
            params.extend([boundary, boundary])
        where.append(clause)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    with conn.cursor() as cur:
        cur.execute(f"{_VISIBLE_CTE} SELECT count(*) FROM visible v {where_sql}", cte_params + params)
        total = cur.fetchone()[0]
        cur.execute(
            f"""{_VISIBLE_CTE}
            SELECT v.source, v.t, v.url, v.text, v.is_recent, v.lang, v.text_en
            FROM visible v {where_sql}
            ORDER BY v.t DESC, v.id DESC
            LIMIT %s OFFSET %s""",
            cte_params + params + [limit, offset],
        )
        rows = cur.fetchall()
    posts = [
        {
            "channel": source,
            "posted_at": posted_at,
            "older": not is_recent,
            # only ever a plain t.me message link, never an arbitrary stored URL
            "url": url if url and _TME_POST_RE.match(url) else None,
            "snippet": make_snippet(text),
            # machine translation, only for a post detected as non-English and translated;
            # goes through the same link/PII redaction as the original snippet
            "lang": lang if lang and lang != "en" else None,
            "translation": make_snippet(text_en) if text_en and lang and lang != "en" else None,
        }
        for source, posted_at, url, text, is_recent, lang, text_en in rows
    ]
    return posts, total
