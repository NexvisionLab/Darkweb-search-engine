import sys
sys.path.insert(0, ".")
from darkweb_crawler import classification, db, search

client = search.get_client()
if client.indices.exists(index=search.INDEX_NAME):
    client.indices.delete(index=search.INDEX_NAME)
search.ensure_index(client)

conn = db.get_connection()
cur = conn.cursor()
cur.execute(
    """
    SELECT p.id, p.url, d.host, p.title, p.body_text, p.content_category, p.language, p.pii_present,
           p.meta_description, p.published_at
    FROM pages p
    JOIN domains d ON d.id = p.domain_id
    """
)
rows = cur.fetchall()
embedded_count = 0
for page_id, url, domain, title, body_text, category, language, pii_present, meta_description, published_at in rows:
    try:
        embedding = classification.embed(f"{title or ''}. {(body_text or '')[:2000]}")
    except Exception:
        embedding = None
    if embedding is not None:
        embedded_count += 1
    search.index_page(
        client, page_id, url, domain, title, body_text, category, language, pii_present,
        meta_description, published_at, embedding,
    )

print(f"Reindexed {len(rows)} pages, {embedded_count} with embeddings")
conn.close()
