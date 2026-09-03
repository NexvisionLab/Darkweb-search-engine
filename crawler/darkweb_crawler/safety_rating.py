"""Derives a domain-level safety rating from the aggregate content
categories seen across its crawled pages, plus a small set of
independent risk signals (a linked executable, a near-duplicate of a
known-legitimate page from a different domain) that override the
category-based rating outright - a domain linking to malware, or
impersonating a verified service, is dangerous regardless of what
category its own pages otherwise fall into.

csam is checked ahead of every other signal, including the malware/
clone overrides above - a single csam-classified page makes the whole
domain csam-confirmed unconditionally, never softened to a lower
rating by whatever else is on the site. api/labels.py treats this
rating as suppressed: a csam-confirmed domain is dropped from search
results, entity search, and domain lookups entirely, not merely shown
behind a Dangerous reveal-gate like every other rating here.

carding/crypto-services/counterfeits were added to classification.py's
CATEGORY_DESCRIPTIONS during an earlier pass but never given a
priority/rating entry here - a domain whose pages were only ever
classified into one of those three had no matching CATEGORY_PRIORITY
entry and silently fell through to "unclassified" regardless of how
serious the actual content was. Fixed below alongside adding the 2026
taxonomy-research categories, not a separate change - same file, same
review pass."""

# most specific / highest concern first - the first match wins. csam and
# extremism-violence sit at the top since they're the two categories
# INTERNAL_ONLY_CATEGORIES (classification.py) never exposes as a filter,
# but the safety-rating engine still needs to weigh them most heavily
# when they're present at all.
CATEGORY_PRIORITY = [
    "extremism-violence",
    "leak-dump",
    "ransomware",
    "breach-forum",
    "fraud",
    "carding",
    "hacking-services",
    "weapons",
    "crypto-services",
    "counterfeits",
    "drugs",
    "marketplace",
    "forum",
    "legitimate-mirror",
]

RATING_BY_CATEGORY = {
    "extremism-violence": "extremism-risk",
    "leak-dump": "confirmed-leak",
    "ransomware": "confirmed-leak",
    "breach-forum": "confirmed-leak",
    "fraud": "fraud-risk",
    "carding": "fraud-risk",
    "hacking-services": "hacking-services-risk",
    "weapons": "illicit-marketplace",
    "crypto-services": "illicit-marketplace",
    "counterfeits": "illicit-marketplace",
    "drugs": "illicit-marketplace",
    "marketplace": "illicit-marketplace",
    "forum": "forum",
    "legitimate-mirror": "legitimate",
}

DEFAULT_RATING = "unclassified"

MALWARE_RATING = "malware-risk"
CLONE_RATING = "phishing-clone-suspect"
EXIT_SCAM_RATING = "exit-scam-suspect"
CSAM_RATING = "csam-confirmed"


def rate(categories, malware_flag=False, clone_suspect=False) -> str:
    present = {c for c in categories if c}
    if "csam" in present:
        return CSAM_RATING
    if malware_flag:
        return MALWARE_RATING
    if clone_suspect:
        return CLONE_RATING
    for category in CATEGORY_PRIORITY:
        if category in present:
            return RATING_BY_CATEGORY[category]
    return DEFAULT_RATING
