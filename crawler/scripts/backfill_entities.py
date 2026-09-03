import sys
sys.path.insert(0, ".")
from darkweb_crawler import db, entity_extract

conn = db.get_connection()
pages = db.get_all_pages_with_body(conn)
total_entities = 0
pages_with_entities = 0
for page_id, domain_id, body_text in pages:
    entities = entity_extract.extract_entities(body_text)
    if entities:
        db.clear_page_entities(conn, page_id)
        db.insert_page_entities(conn, page_id, domain_id, entities)
        total_entities += len(entities)
        pages_with_entities += 1
print(f"Scanned {len(pages)} pages, found {total_entities} entities across {pages_with_entities} pages")
conn.close()
