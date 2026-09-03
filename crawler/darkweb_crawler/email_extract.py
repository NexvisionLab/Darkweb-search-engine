"""Extracts distinct email addresses from page text for the breach
checker's exposure index. Deliberately narrow: only the hash of each
address is ever stored (see db.upsert_breach_email) - never the raw
address - consistent with "PII flagged, not extracted" for anything
that persists."""
import hashlib
import re

EMAIL_RE = re.compile(r"\b[a-zA-Z0-9_.+-]{1,50}@[a-zA-Z0-9-]{1,50}\.[a-zA-Z0-9-.]{1,50}[a-zA-Z0-9]\b")


def extract_email_hashes(text):
    if not text:
        return []
    emails = {m.group(0).lower() for m in EMAIL_RE.finditer(text)}
    return [hashlib.sha256(email.encode("utf-8")).hexdigest() for email in emails]


def hash_email(email):
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()
