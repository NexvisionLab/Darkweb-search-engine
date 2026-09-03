import sys
sys.path.insert(0, ".")
from darkweb_crawler import db, email_extract

conn = db.get_connection()
pages = db.get_pii_pages(conn)
total_hashes = 0
for page_id, body_text in pages:
    for email_hash in email_extract.extract_email_hashes(body_text):
        db.upsert_breach_email_hash(conn, email_hash)
        total_hashes += 1
print(f"Processed {len(pages)} PII-flagged pages, {total_hashes} email hash upserts")
conn.close()
