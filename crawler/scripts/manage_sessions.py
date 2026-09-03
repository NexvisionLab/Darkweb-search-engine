"""Lists or revokes stored authenticated sessions. Never prints cookie
values - only host/notes/timestamps, since the whole point of
session_crypto.py is that the encrypted material never surfaces in
plaintext outside a decrypt call made by the crawl itself.

Usage:
    python3 scripts/manage_sessions.py list
    python3 scripts/manage_sessions.py revoke <host>
"""
import sys

sys.path.insert(0, ".")
from darkweb_crawler import db


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("list", "revoke"):
        print(__doc__)
        sys.exit(1)

    conn = db.get_connection()
    try:
        if sys.argv[1] == "list":
            rows = db.list_authenticated_sessions(conn)
            if not rows:
                print("No authenticated sessions stored")
                return
            for host, notes, created_at, expires_at, last_used_at, revoked_at in rows:
                status = "revoked" if revoked_at else ("expired" if expires_at and expires_at.tzinfo else "active")
                print(f"{host}")
                print(f"  status: {'revoked' if revoked_at else 'active'}")
                print(f"  notes: {notes or '(none)'}")
                print(f"  created: {created_at}")
                print(f"  expires: {expires_at or '(never)'}")
                print(f"  last used: {last_used_at or '(never)'}")
        elif sys.argv[1] == "revoke":
            if len(sys.argv) < 3:
                print("Usage: python3 scripts/manage_sessions.py revoke <host>")
                sys.exit(1)
            host = sys.argv[2]
            if db.revoke_authenticated_session(conn, host):
                print(f"Revoked session for {host}")
            else:
                print(f"No active session found for {host}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
