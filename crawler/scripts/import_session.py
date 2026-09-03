"""Imports an authenticated session (cookies) for a single login-gated
onion domain, obtained manually - log into the forum once through a
real browser (create the account yourself, solve any CAPTCHA/vetting
gate), then export cookies via a browser extension like Cookie-Editor
as JSON ([{"name":..., "value":...}, ...]). This script never attempts
to register or log into anywhere on its own.

Reads the cookie data from a file, never a CLI argument or stdin paste
- a CLI arg lands in .bash_history in plaintext, and a real login
credential for a forum account shouldn't ever touch shell history.
Encrypted before it ever reaches Postgres (see session_crypto.py).

Usage:
    python3 scripts/import_session.py <host> <cookie_json_file> [--notes "..."] [--expires-days N] [--shred]

--shred overwrites and deletes the plaintext cookie file after a
successful import, so it doesn't sit on disk once it's encrypted in
the database.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, ".")
from darkweb_crawler import db, session_crypto


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", help="the .onion address this session belongs to")
    parser.add_argument("cookie_file", help="path to a JSON file of exported cookies")
    parser.add_argument("--notes", default=None, help="e.g. which account, when it was created")
    parser.add_argument("--expires-days", type=int, default=None, help="mark the session stale after N days")
    parser.add_argument("--shred", action="store_true", help="overwrite and delete the cookie file after import")
    args = parser.parse_args()

    if not os.path.exists(args.cookie_file):
        print(f"No such file: {args.cookie_file}")
        sys.exit(1)

    with open(args.cookie_file, "r", encoding="utf-8") as f:
        raw = f.read()

    try:
        cookies = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"Not valid JSON: {e}")
        sys.exit(1)

    if not isinstance(cookies, list) or not cookies:
        print('Expected a non-empty JSON array of cookie objects, e.g. [{"name": "...", "value": "..."}]')
        sys.exit(1)
    if not all(isinstance(c, dict) and "name" in c and "value" in c for c in cookies):
        print('Every cookie object needs at least "name" and "value" fields')
        sys.exit(1)

    encrypted = session_crypto.encrypt(raw)

    expires_at = None
    if args.expires_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=args.expires_days)

    conn = db.get_connection()
    try:
        session_id = db.upsert_authenticated_session(conn, args.host, encrypted, args.notes, expires_at)
    finally:
        conn.close()

    print(f"Imported session for {args.host} (id={session_id}, {len(cookies)} cookies, encrypted at rest)")
    if expires_at:
        print(f"Expires: {expires_at.isoformat()}")

    if args.shred:
        length = os.path.getsize(args.cookie_file)
        with open(args.cookie_file, "r+b") as f:
            f.write(os.urandom(length))
            f.flush()
            os.fsync(f.fileno())
        os.remove(args.cookie_file)
        print(f"Shredded {args.cookie_file}")


if __name__ == "__main__":
    main()
