"""Telegram ingest: reads PUBLIC channel preview pages (t.me/s/<channel>)
- no login, no phone number, no API session, so nothing that can be
banned or tied to a person. Deliberately NOT the MTProto client API.
Runs on a systemd timer (darkweb-social-telegram).

The channel list (social_telegram_channels) is seeded from the telegram
handles the dark-web crawl already found (page_entities) plus operator
additions. Every post from a listed channel is kept - the list is the
curation. A handle that is not a public channel (a user or bot page has
no preview feed) is marked inactive so it isn't retried forever.

Each poll reads the newest page (~20 posts); the first poll of a channel
also walks back a few pages for history. Cursor = highest message id
seen per channel."""
import json
import os
import re
import sys
import time
from datetime import datetime

sys.path.insert(0, ".")

import httpx
from lxml import html as lxml_html

from darkweb_crawler import db, social_ingest

BACKFILL_PAGES = int(os.environ.get("TELEGRAM_BACKFILL_PAGES", "3"))
# A handle that answers 302 (t.me/s/<h> -> t.me/<h>) has no web preview: a user, bot,
# private channel, or a channel that turned it off. That can change, so such a channel
# stays in the list and is re-checked this often instead of being dropped for good.
NO_PREVIEW_ERROR_PREFIX = "no public preview"
RECHECK_NO_PREVIEW_DAYS = 7
REQUEST_DELAY_S = 2.0
USER_AGENT = "Mozilla/5.0 (compatible; DarkNyx-social-ingest/1.0; public channel reader)"
_HANDLE_RE = re.compile(r"^t\.me/([A-Za-z][A-Za-z0-9_]{3,31})/?$")


def seed_channels(conn):
    """Adds any t.me handle found in the crawl that is not yet tracked."""
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT entity_value FROM page_entities WHERE entity_type = 'telegram_handle'")
        found = [row[0] for row in cur.fetchall()]
        added = 0
        for value in found:
            m = _HANDLE_RE.match(value.strip())
            if not m:
                continue
            cur.execute(
                "INSERT INTO social_telegram_channels (handle, origin) VALUES (%s, 'crawl') ON CONFLICT DO NOTHING",
                (m.group(1).lower(),),
            )
            added += cur.rowcount
    return added


def parse_channel_page(handle, page_html):
    """Returns (posts, oldest_id) parsed from a t.me/s/<channel> page."""
    tree = lxml_html.fromstring(page_html)
    posts = []
    for wrap in tree.xpath('//div[contains(@class,"tgme_widget_message_wrap")]'):
        msg = wrap.xpath('.//div[contains(@class,"tgme_widget_message") and @data-post]')
        if not msg:
            continue
        data_post = msg[0].get("data-post", "")
        try:
            message_id = int(data_post.rsplit("/", 1)[1])
        except (IndexError, ValueError):
            continue
        text_nodes = wrap.xpath('.//div[contains(@class,"tgme_widget_message_text")]')
        if not text_nodes:
            continue
        for br in text_nodes[0].xpath(".//br"):
            br.tail = "\n" + (br.tail or "")
        text = text_nodes[0].text_content().strip()
        if not text:
            continue
        times = wrap.xpath('.//time[@datetime]')
        posted_at = None
        if times:
            try:
                posted_at = datetime.fromisoformat(times[0].get("datetime"))
            except ValueError:
                pass
        photo_urls = [
            m.group(1)
            for style in wrap.xpath('.//a[contains(@class,"tgme_widget_message_photo_wrap")]/@style')
            for m in [re.search(r"url\(['\"]?([^'\")]+)", style)] if m
        ]
        posts.append({
            "platform": "telegram", "source": handle, "external_id": f"{handle}/{message_id}",
            "author_id": handle, "author_handle": handle, "text": text, "lang": None,
            "url": f"https://t.me/{handle}/{message_id}", "posted_at": posted_at,
            "hashtags": [t.lower() for t in re.findall(r"#(\w+)", text)],
            "links": wrap.xpath('.//div[contains(@class,"tgme_widget_message_text")]//a/@href'),
            "media_urls": photo_urls,
            "_id": message_id,
        })
    return posts


def poll_channel(conn, client, handle, stats):
    cursor = social_ingest.get_cursor(conn, "telegram", handle)
    last_seen = int(cursor) if cursor else 0
    max_pages = BACKFILL_PAGES if not cursor else 1
    before = None
    newest = last_seen
    for _ in range(max_pages):
        url = f"https://t.me/s/{handle}" + (f"?before={before}" if before else "")
        resp = client.get(url)
        if resp.status_code != 200 or "tgme_widget_message" not in resp.text:
            return False, f"no public preview (HTTP {resp.status_code})"
        posts = parse_channel_page(handle, resp.text)
        if not posts:
            break
        for post in posts:
            message_id = post.pop("_id")
            newest = max(newest, message_id)
            if message_id <= last_seen:
                continue
            stats["seen"] += 1
            keep, reasons, entities = social_ingest.should_keep(post["text"], curated=True)
            if keep and social_ingest.store_post(conn, post, reasons, entities):
                stats["stored"] += 1
        before = min(int(p["external_id"].rsplit("/", 1)[1]) for p in posts)
        if before <= last_seen + 1:
            break
        time.sleep(REQUEST_DELAY_S)
    if newest > last_seen:
        social_ingest.set_cursor(conn, "telegram", handle, newest)
    return True, None


def main():
    conn = db.get_connection()
    stats = {"seen": 0, "stored": 0, "channels_ok": 0, "channels_inactive": 0,
             "channels_reactivated": 0, "seeded": seed_channels(conn)}
    with conn.cursor() as cur:
        cur.execute(
            """SELECT handle, active FROM social_telegram_channels
               WHERE active
                  OR (last_error LIKE %s AND (last_polled_at IS NULL OR last_polled_at < now() - make_interval(days => %s)))
               ORDER BY last_polled_at NULLS FIRST""",
            (NO_PREVIEW_ERROR_PREFIX + "%", RECHECK_NO_PREVIEW_DAYS),
        )
        handles = cur.fetchall()
    with httpx.Client(timeout=20, headers={"User-Agent": USER_AGENT}, follow_redirects=False) as client:
        for handle, was_active in handles:
            try:
                ok, error = poll_channel(conn, client, handle, stats)
            except (httpx.HTTPError, ValueError) as e:
                ok, error = None, f"{type(e).__name__}: {e}"   # transient: stay active, retry next run
            with conn.cursor() as cur:
                if ok is False:
                    stats["channels_inactive"] += 1
                    cur.execute("UPDATE social_telegram_channels SET active = false, last_error = %s, last_polled_at = now() WHERE handle = %s", (error, handle))
                else:
                    if ok:
                        stats["channels_ok"] += 1
                        if not was_active:
                            stats["channels_reactivated"] += 1
                    # ok is None on a transient error: leave the channel's state alone.
                    cur.execute(
                        "UPDATE social_telegram_channels SET active = active OR %s, last_error = %s, last_polled_at = now() WHERE handle = %s",
                        (bool(ok), error, handle),
                    )
            time.sleep(REQUEST_DELAY_S)
    print(json.dumps(stats))


if __name__ == "__main__":
    main()
