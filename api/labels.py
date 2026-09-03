"""Maps the internal safety_rating (computed in the crawler from page
categories - see darkweb_crawler/safety_rating.py) to the small, fixed
public label set a general-audience search UI should show. A bare
numeric score or the internal category name isn't the right thing to
put in front of an anonymous visitor deciding whether to open a
result; a small vocabulary they can learn once is.

SUPPRESSED_RATINGS is a stricter tier than anything in PUBLIC_LABELS:
every rating above is still shown, just gated behind the existing
Dangerous/Suspicious reveal-click UX. csam-confirmed is different in
kind, not degree - a domain rated this way must never appear in a
search result, entity-search hit, or /domains/{host} lookup at all, in
either tier, regardless of query. is_suppressed() is the single check
every result-shaping endpoint in api/main.py calls before a raw
safety_rating is either returned or converted via public_label() -
one place to keep this rule instead of re-deriving it per endpoint.
Still mapped in PUBLIC_LABELS too (as Dangerous) so anything that ever
calls public_label() directly without checking is_suppressed() first
fails safe rather than silently defaulting to Unrated."""

PUBLIC_LABELS = {
    "legitimate": {"label": "Verified", "severity": "good"},
    "forum": {"label": "Unrated", "severity": "neutral"},
    "unclassified": {"label": "Unrated", "severity": "neutral"},
    "unrated": {"label": "Unrated", "severity": "neutral"},
    "illicit-marketplace": {"label": "Suspicious", "severity": "warn"},
    "fraud-risk": {"label": "Dangerous", "severity": "bad"},
    "confirmed-leak": {"label": "Dangerous", "severity": "bad"},
    "malware-risk": {"label": "Dangerous", "severity": "bad"},
    "phishing-clone-suspect": {"label": "Dangerous", "severity": "bad"},
    "exit-scam-suspect": {"label": "Suspicious", "severity": "warn"},
    "extremism-risk": {"label": "Dangerous", "severity": "bad"},
    "hacking-services-risk": {"label": "Dangerous", "severity": "bad"},
    "csam-confirmed": {"label": "Dangerous", "severity": "bad"},
}

DEFAULT_LABEL = {"label": "Unrated", "severity": "neutral"}

# Ratings that must never reach a caller in any form - see the module
# docstring. Currently just csam-confirmed, kept as a set (not a single
# constant) since a future rating could plausibly join it without
# every call site needing to change.
SUPPRESSED_RATINGS = {"csam-confirmed"}


def public_label(safety_rating):
    return PUBLIC_LABELS.get(safety_rating, DEFAULT_LABEL)


def is_suppressed(safety_rating):
    return safety_rating in SUPPRESSED_RATINGS
