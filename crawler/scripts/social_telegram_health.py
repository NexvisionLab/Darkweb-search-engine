"""Health of the public-Telegram ingest: which channels are being read, which
are not and why, and whether the feed as a whole is starved.

    crawler/.venv/bin/python3 scripts/social_telegram_health.py            # report
    crawler/.venv/bin/python3 scripts/social_telegram_health.py --check    # exit 1 if starved
    crawler/.venv/bin/python3 scripts/social_telegram_health.py --check --days 5

Why this exists: darkweb-social-telegram exits 0 whether it stored 500 posts
or none, so a feed with no readable channels looks healthy. --check turns
"nothing has been stored for N days" (default 3) or "no active channels" into a
non-zero exit, which shows up as a failed unit when run from
darkweb-social-telegram-health.timer.

A channel that is inactive with 'no public preview' is not broken - Telegram
serves no web preview for users, bots, private channels or channels that turned
it off (t.me/s/<handle> 302s to t.me/<handle>). The poller re-checks those
weekly in case a channel enables its preview."""
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, ".")

from darkweb_crawler import db

DEFAULT_STARVATION_DAYS = 3


def is_starved(last_stored_at, now, days):
    """True when nothing was stored in the last `days` days (or ever)."""
    if last_stored_at is None:
        return True
    return now - last_stored_at > timedelta(days=days)


def channel_rows(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.handle, c.origin, c.active, c.last_polled_at, c.last_error,
                   count(p.id) AS posts_total,
                   count(p.id) FILTER (WHERE p.first_seen_at > now() - interval '24 hours') AS posts_24h,
                   max(p.first_seen_at) AS last_stored_at,
                   c.public
            FROM social_telegram_channels c
            LEFT JOIN social_posts p ON p.platform = 'telegram' AND p.source = c.handle
            GROUP BY c.handle
            ORDER BY c.active DESC, posts_24h DESC, c.handle
            """
        )
        return cur.fetchall()


def evaluate(rows, now, days):
    """Returns (problems, summary_line) from channel_rows output."""
    active = [r for r in rows if r[2]]
    last_stored = max((r[7] for r in rows if r[7] is not None), default=None)
    problems = []
    if not rows:
        problems.append("no Telegram channels are configured")
    elif not active:
        problems.append("no active channels - every channel is inactive")
    if rows and is_starved(last_stored, now, days):
        when = f"last stored {last_stored:%Y-%m-%d %H:%M} UTC" if last_stored else "nothing was ever stored"
        problems.append(f"no Telegram post stored in the last {days} day(s) ({when})")
    summary = f"{len(rows)} channels, {len(active)} active, {sum(r[6] for r in rows)} posts stored in the last 24h"
    return problems, summary


def main(argv):
    check = "--check" in argv
    days = DEFAULT_STARVATION_DAYS
    if "--days" in argv:
        days = int(argv[argv.index("--days") + 1])
    conn = db.get_connection()
    try:
        rows = channel_rows(conn)
    finally:
        conn.close()
    now = datetime.now(timezone.utc)
    problems, summary = evaluate(rows, now, days)

    print(summary)
    print(f"{'handle':28} {'origin':9} {'state':8} {'free site':9} {'24h':>5} {'total':>6}  last polled / note")
    for handle, origin, active, polled, error, total, last_24h, _, public in rows:
        state = "active" if active else "inactive"
        note = f"{polled:%m-%d %H:%M}" if polled else "never polled"
        if error:
            note += f"  [{error}]"
        print(f"{handle:28} {origin:9} {state:8} {'public' if public else 'private':9} {last_24h:>5} {total:>6}  {note}")
    for problem in problems:
        print(f"PROBLEM: {problem}")
    return 1 if (check and problems) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
