"""Checks pending owner-verification claims against already-crawled page
text - if the claim's token has shown up on the domain since the claim
was submitted, mark it verified. Runs against existing crawl data
rather than a fresh fetch, so a claim completes on the next scheduled
crawl pass after the owner adds the token, not instantly."""
import sys
sys.path.insert(0, ".")
from darkweb_crawler import db

conn = db.get_connection()
claims = db.get_pending_verification_claims(conn)
verified = 0
for claim_id, host, token in claims:
    if db.domain_body_contains(conn, host, token):
        db.mark_verification_verified(conn, claim_id, host)
        verified += 1
        print(f"verified: {host}")
print(f"Checked {len(claims)} pending claims, verified {verified}")
conn.close()
