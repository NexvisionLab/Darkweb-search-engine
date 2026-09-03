import os
from opensearchpy import OpenSearch

INDEX_NAME = "pages"

# 384 dims - matches all-MiniLM-L6-v2's real output size (see
# classification.py's embed(), which reuses the same model already
# loaded for content classification). The original placeholder here
# said "adjust once the actual model is chosen" - this is that.
EMBEDDING_DIMENSION = 384

INDEX_BODY = {
    "settings": {"index.knn": True},
    "mappings": {
        "properties": {
            "url": {"type": "keyword"},
            "domain": {"type": "keyword"},
            "title": {"type": "text"},
            "body_text": {"type": "text"},
            "content_category": {"type": "keyword"},
            "language": {"type": "keyword"},
            "pii_present": {"type": "boolean"},
            "meta_description": {"type": "text"},
            "image_text": {"type": "text"},
            "published_at": {"type": "date"},
            "crawled_at": {"type": "date"},
            "embedding": {"type": "knn_vector", "dimension": EMBEDDING_DIMENSION},
        }
    },
}


def get_client():
    return OpenSearch(
        hosts=[{"host": os.environ.get("OPENSEARCH_HOST", "127.0.0.1"), "port": 9200}],
        use_ssl=False,
        verify_certs=False,
    )


def ensure_index(client):
    if not client.indices.exists(index=INDEX_NAME):
        client.indices.create(index=INDEX_NAME, body=INDEX_BODY)


def index_page(
    client,
    page_id,
    url,
    domain,
    title,
    body_text,
    content_category=None,
    language=None,
    pii_present=None,
    meta_description=None,
    published_at=None,
    embedding=None,
    image_text=None,
):
    body = {
        "url": url,
        "domain": domain,
        "title": title,
        "body_text": body_text,
        "content_category": content_category,
        "language": language,
        "pii_present": pii_present,
        "meta_description": meta_description,
        "published_at": published_at.isoformat() if published_at else None,
    }
    if embedding is not None:
        body["embedding"] = embedding
    if image_text:
        body["image_text"] = image_text

    client.index(index=INDEX_NAME, id=str(page_id), body=body)


def update_image_text(client, page_id, image_text):
    """Partial update, not a full re-index - OCR/QR processing runs well
    after the initial crawl (see scripts/process_page_images.py), and a
    full index_page() call would silently overwrite body_text/embedding
    with whatever the caller happens to have on hand at that later
    point. This only ever touches the one field. doc_as_upsert covers
    a page whose own OpenSearch document doesn't exist yet (enrichment
    and image processing aren't guaranteed to run in a fixed order) -
    without it this would 404 and the image text would be lost for
    good, since images_processed_at is only ever set once."""
    client.update(
        index=INDEX_NAME,
        id=str(page_id),
        body={"doc": {"image_text": image_text}, "doc_as_upsert": True},
    )
