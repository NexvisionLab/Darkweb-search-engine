import hashlib
import os
import re
from datetime import datetime, timezone

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
            # Fingerprint of the page's opening text (see dup_group()): pages on different hosts with the same value are copies of
            # one another, which is what the Clone clusters list groups on.
            "dup_group": {"type": "keyword"},
            # The owning domain's rating when the page was indexed. Display only (the clusters' safety mix): hiding suppressed
            # hosts never relies on it.
            "safety_rating": {"type": "keyword"},
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
    else:
        # an index built before dup_group and safety_rating existed: add them (idempotent) so they are keywords, not dynamic text
        client.indices.put_mapping(
            index=INDEX_NAME,
            body={"properties": {name: INDEX_BODY["mappings"]["properties"][name] for name in ("dup_group", "safety_rating")}},
        )


DUP_MIN_WORDS = 40          # shorter pages are too generic to call copies of each other
DUP_WORDS = 400             # how much of the opening text is fingerprinted


def dup_group(body_text):
    """A short fingerprint of the first DUP_WORDS words of a page, ignoring case, punctuation and spacing, or None for a page with
    fewer than DUP_MIN_WORDS words. Two pages with the same value carry the same opening text (an onion mirror of a site, a
    copied scam kit, a placeholder page)."""
    words = re.findall(r"[^\W_]+", (body_text or "").lower())
    if len(words) < DUP_MIN_WORDS:
        return None
    return hashlib.sha1(" ".join(words[:DUP_WORDS]).encode("utf-8", "replace")).hexdigest()[:16]


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
    safety_rating=None,
    crawled_at=None,
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
        "crawled_at": (crawled_at or datetime.now(timezone.utc)).isoformat(),
    }
    group = dup_group(body_text)
    if group:
        body["dup_group"] = group
    if safety_rating:
        body["safety_rating"] = safety_rating
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
