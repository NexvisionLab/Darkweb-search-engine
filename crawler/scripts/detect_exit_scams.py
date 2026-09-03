"""Flags a domain as a possible exit scam: it was an active marketplace
(3+ pages, at least one detected price) and has now gone down - the
documented dark-market exit-scam pattern (a spike in listings/activity
immediately followed by the site going dark). Runs after check_liveness.py
in the scheduled pipeline, since it depends on is_up already being
current for this run."""
import sys
sys.path.insert(0, ".")
from darkweb_crawler import db, safety_rating

conn = db.get_connection()
domain_ids = db.get_marketplace_domains_gone_down(conn)
for domain_id in domain_ids:
    db.update_domain_exit_scam_suspect(conn, domain_id, True)
    db.update_domain_safety_rating(conn, domain_id, safety_rating.EXIT_SCAM_RATING)
print(f"Flagged {len(domain_ids)} domain(s) as possible exit scams")
conn.close()
