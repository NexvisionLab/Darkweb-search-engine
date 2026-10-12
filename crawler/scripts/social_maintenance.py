"""Retention and erasure for the social ingest tables.
    crawler/.venv/bin/python3 scripts/social_maintenance.py purge
    crawler/.venv/bin/python3 scripts/social_maintenance.py erase <platform> <author-id-or-handle>
    crawler/.venv/bin/python3 scripts/social_maintenance.py add-channel <telegram-handle>
    crawler/.venv/bin/python3 scripts/social_maintenance.py add-channels <file>
    crawler/.venv/bin/python3 scripts/social_maintenance.py publish-channel <handle>
    crawler/.venv/bin/python3 scripts/social_maintenance.py unpublish-channel <handle>
    crawler/.venv/bin/python3 scripts/social_maintenance.py unpublish-all

`purge` runs daily on a timer (posts expire after 30 days). `erase` is
the GDPR erasure path: deletes every stored post by that author and
suppresses them from future ingest. `add-channel` adds an operator-chosen
public Telegram channel to the poll list; `add-channels` does the same for a file with
one handle or t.me link per line (blank lines and # comments ignored) and reports
any line it could not use. `publish-channel` / `unpublish-channel` control whether the
darknyx.com Free site shows a channel's recent posts (default: not shown);
`unpublish-all` is the one-command way to take every channel off the Free site."""
import re
import sys

sys.path.insert(0, ".")

from darkweb_crawler import db, social_ingest

_HANDLE_RE = re.compile(r"[a-z][a-z0-9_]{3,31}")
# First path segments Telegram uses for its own URLs, which look like handles but are not.
_RESERVED = {"joinchat", "addstickers", "addemoji", "addlist", "share", "proxy", "socks",
             "iv", "boost", "login", "invoice", "setlanguage", "contact", "giftcode"}


def normalize_handle(raw):
    """Public channel handle from '@x', 'x', 't.me/x', 'https://t.me/s/x' or a
    message link, lower-cased; None for anything that is not a public handle
    (invite links, t.me/+..., t.me/c/... and the like)."""
    handle = (raw or "").strip().lstrip("@")
    for prefix in ("https://", "http://"):
        handle = handle.removeprefix(prefix)
    handle = handle.removeprefix("t.me/").removeprefix("s/")
    handle = handle.split("/")[0].split("?")[0].lower()
    return handle if _HANDLE_RE.fullmatch(handle) and handle not in _RESERVED else None


def add_channel(conn, handle, origin="operator"):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO social_telegram_channels (handle, origin) VALUES (%s, %s) "
            "ON CONFLICT (handle) DO UPDATE SET active = true, last_error = NULL",
            (handle, origin),
        )


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    conn = db.get_connection()
    command = argv[0]
    if command == "purge":
        print(f"purged {social_ingest.purge_expired(conn)} expired post(s)")
    elif command == "erase" and len(argv) == 3:
        print(f"erased {social_ingest.erase_author(conn, argv[1], argv[2])} post(s); author suppressed from future ingest")
    elif command == "add-channel" and len(argv) == 2:
        handle = normalize_handle(argv[1])
        if not handle:
            print("not a valid public channel handle")
            return 2
        add_channel(conn, handle)
        print(f"channel {handle} will be polled on the next run")
    elif command in ("publish-channel", "unpublish-channel") and len(argv) == 2:
        handle = normalize_handle(argv[1])
        if not handle:
            print("not a valid public channel handle")
            return 2
        with conn.cursor() as cur:
            cur.execute("UPDATE social_telegram_channels SET public = %s WHERE handle = %s RETURNING handle",
                        (command == "publish-channel", handle))
            found = cur.fetchone()
        if not found:
            print(f"{handle} is not in the channel list (add it with add-channel first)")
            return 2
        print(f"{handle} is now {'PUBLISHED on' if command == 'publish-channel' else 'hidden from'} the Free site")
    elif command == "unpublish-all" and len(argv) == 1:
        with conn.cursor() as cur:
            cur.execute("UPDATE social_telegram_channels SET public = false WHERE public")
            print(f"{cur.rowcount} channel(s) hidden from the Free site")
    elif command == "add-channels" and len(argv) == 2:
        added, skipped = [], []
        with open(argv[1]) as f:
            for lineno, line in enumerate(f, 1):
                line = line.split("#")[0].strip()
                if not line:
                    continue
                handle = normalize_handle(line)
                if handle:
                    add_channel(conn, handle)
                    added.append(handle)
                else:
                    skipped.append(f"line {lineno}: {line!r}")
        print(f"{len(added)} channel(s) queued for the next poll: {', '.join(added) or '-'}")
        for item in skipped:
            print(f"skipped {item} (not a public channel handle)")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
