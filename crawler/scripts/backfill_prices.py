import sys
sys.path.insert(0, ".")
from darkweb_crawler import db, price_extract

conn = db.get_connection()
pages = db.get_marketplace_pages(conn)
total_prices = 0
for page_id, domain_id, body_text in pages:
    prices = price_extract.extract_prices(body_text)
    if prices:
        db.clear_page_prices(conn, page_id)
        db.insert_page_prices(conn, page_id, domain_id, prices)
        total_prices += len(prices)
print(f"Backfilled {len(pages)} marketplace pages, found {total_prices} price mentions")
conn.close()
