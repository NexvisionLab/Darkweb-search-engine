"""Flags a page as a possible phishing clone if its content is nearly
identical to a page already classified legitimate-mirror but served
from a different domain - the classic fake-mirror pattern (a cloned
login page for a known service, or an impostor of a verified onion
service). Reuses the same embedding model classification.py already
loads, rather than a second model instance."""
from sentence_transformers import util

from . import classification

CLONE_SIMILARITY_THRESHOLD = 0.92


def build_legitimate_reference_set(legitimate_pages):
    """legitimate_pages: iterable of (domain, body_text). Returns a list
    of (domain, embedding) pairs, computed once per crawl run - this is
    meant to be cached by the caller (see pipelines.EnrichmentPipeline),
    not recomputed per page."""
    model = classification._get_model()
    refs = []
    for domain, body_text in legitimate_pages:
        if body_text:
            embedding = model.encode(body_text[:2000], convert_to_tensor=True)
            refs.append((domain, embedding))
    return refs


def is_clone_of_legitimate(body_text, domain, reference_set):
    if not body_text or not reference_set:
        return False
    model = classification._get_model()
    embedding = model.encode(body_text[:2000], convert_to_tensor=True)
    for ref_domain, ref_embedding in reference_set:
        if ref_domain == domain:
            continue
        score = float(util.cos_sim(embedding, ref_embedding)[0][0])
        if score >= CLONE_SIMILARITY_THRESHOLD:
            return True
    return False
