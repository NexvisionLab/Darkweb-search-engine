import math
import os

from opensearchpy import OpenSearch

INDEX_NAME = "pages"
_EMBED_MODEL_NAME = "all-MiniLM-L6-v2"
_embed_model = None


def get_client():
    return OpenSearch(
        hosts=[{"host": os.environ.get("OPENSEARCH_HOST", "127.0.0.1"), "port": 9200}],
        use_ssl=False,
        verify_certs=False,
    )


# Ransomware/marketplace operators routinely run the same site on
# several .onion addresses for takedown resilience - without
# deduplication, one real result becomes N near-identical cards in the
# same result page. Two same-domain pages are never merged (they're
# genuinely different pages on the same site); only cross-domain
# near-duplicates count as mirrors.
_MIRROR_SIMILARITY_THRESHOLD = 0.97


def _cosine_similarity(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _dedupe_mirrors(hits):
    """Groups cross-domain near-duplicate hits (by embedding cosine
    similarity) and collapses each group onto its highest-ranked member,
    attaching the rest as a `mirrors` list rather than dropping them
    silently. Hits without an embedding (older, pre-reindex pages) are
    left exactly as they were - never merged, never excluded."""
    n = len(hits)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[max(ri, rj)] = min(ri, rj)

    for i in range(n):
        emb_i = hits[i].get("embedding")
        if not emb_i:
            continue
        for j in range(i + 1, n):
            if hits[i]["domain"] == hits[j]["domain"]:
                continue
            emb_j = hits[j].get("embedding")
            if not emb_j:
                continue
            if _cosine_similarity(emb_i, emb_j) >= _MIRROR_SIMILARITY_THRESHOLD:
                union(i, j)

    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)

    deduped = []
    for members in groups.values():
        # Members are already in original (relevance-ranked) order since
        # we only ever union a later index into an earlier one - the
        # group's root is always its best-ranked member.
        canonical_idx = members[0]
        canonical = hits[canonical_idx]
        mirrors = [
            {"domain": hits[i]["domain"], "url": hits[i]["url"]}
            for i in members[1:]
        ]
        if mirrors:
            canonical = {**canonical, "mirrors": mirrors}
        deduped.append((canonical_idx, canonical))

    deduped.sort(key=lambda pair: pair[0])
    return [item for _, item in deduped]


def search_pages(client, query_text, category=None, domain=None, limit=20, offset=0):
    filters = []
    if category:
        filters.append({"term": {"content_category": category}})
    if domain:
        filters.append({"term": {"domain": domain}})

    body = {
        "from": offset,
        "size": limit,
        "_source": [
            "url",
            "domain",
            "title",
            "content_category",
            "language",
            "pii_present",
            "meta_description",
            "published_at",
            "crawled_at",
            "embedding",
        ],
    }

    query_text = (query_text or "").strip()
    if query_text:
        body["query"] = {
            "bool": {
                "must": [{"multi_match": {"query": query_text, "fields": ["title^2", "body_text", "meta_description", "image_text"]}}],
                "filter": filters,
            }
        }
        body["highlight"] = {"fields": {"body_text": {"fragment_size": 200, "number_of_fragments": 1}}}
    else:
        # browse mode: no search term, just filters - sort by recency since
        # there's no relevance score to sort by
        body["query"] = {"bool": {"filter": filters}} if filters else {"match_all": {}}
        body["sort"] = [{"crawled_at": {"order": "desc"}}]

    response = client.search(index=INDEX_NAME, body=body)
    total = response["hits"]["total"]["value"]
    hits = []
    for hit in response["hits"]["hits"]:
        source = hit["_source"]
        snippet = None
        highlight = hit.get("highlight", {}).get("body_text")
        if highlight:
            snippet = highlight[0]
        elif source.get("meta_description"):
            # no keyword match in the body, but the page has its own
            # author-written description - a better fallback than
            # nothing, same as Google preferring a real meta description
            snippet = source["meta_description"][:200]
        hits.append({**source, "snippet": snippet})

    hits = _dedupe_mirrors(hits)
    # embedding was only ever needed for the similarity comparison above -
    # never send a 384-float vector to the API/frontend layer.
    for h in hits:
        h.pop("embedding", None)
    return hits, total


def _get_embed_model():
    """Lazy-loaded, independent of the crawler's copy in
    classification.py - api/ deliberately never imports the crawler
    package (see this module's original docstring elsewhere in the
    project), so the same small model is loaded a second time here
    rather than shared. Same model, same 384-dim output, so a query
    embedded here is directly comparable to a page embedded there."""
    global _embed_model
    if _embed_model is None:
        from sentence_transformers import SentenceTransformer

        _embed_model = SentenceTransformer(_EMBED_MODEL_NAME)
    return _embed_model


def semantic_search(client, query_text, category=None, limit=20):
    """Finds conceptually similar pages, not just keyword matches -
    e.g. a query for "credential dump" can surface a page that never
    uses that exact phrase but is clearly the same kind of content.
    Complements search_pages() rather than replacing it; exposed as an
    explicit opt-in mode (see api/main.py's semantic= flag), not a
    silent blend, since vector relevance and keyword relevance aren't
    directly comparable scores."""
    query_text = (query_text or "").strip()
    if not query_text:
        return [], 0

    model = _get_embed_model()
    vector = model.encode(query_text[:2000], convert_to_tensor=False).tolist()

    knn_query = {"embedding": {"vector": vector, "k": limit}}
    filters = []
    if category:
        filters.append({"term": {"content_category": category}})

    body = {
        "size": limit,
        "_source": [
            "url",
            "domain",
            "title",
            "content_category",
            "language",
            "pii_present",
            "meta_description",
            "published_at",
            "crawled_at",
        ],
        "query": {"knn": knn_query} if not filters else {
            "bool": {"must": [{"knn": knn_query}], "filter": filters}
        },
    }

    response = client.search(index=INDEX_NAME, body=body)
    hits = []
    for hit in response["hits"]["hits"]:
        source = hit["_source"]
        snippet = source.get("meta_description", "")
        if snippet:
            snippet = snippet[:200]
        hits.append({**source, "snippet": snippet, "semantic_score": hit.get("_score")})
    return hits, len(hits)
