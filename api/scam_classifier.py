"""Shared classifier for the phishing/scam-checker tools cluster and the
live URL/site safety check - the same embedding-similarity approach as
the crawler's classification.py, applied on demand to text a user
submits or a live-fetched page, instead of a crawled one. One model
instance, two small category sets, reused across every tool in the
cluster rather than five separate models."""
from sentence_transformers import SentenceTransformer, util

SCAM_CATEGORY_DESCRIPTIONS = {
    "phishing": "A message impersonating a bank, company, or service asking the recipient to log in, verify an account, or click a link to avoid a suspended account.",
    "romance-scam": "A message building a romantic relationship online before asking for money, gifts, or financial help, often from someone claiming to be overseas or in the military.",
    "crypto-investment-scam": "A message promising guaranteed high returns on a cryptocurrency or investment opportunity, often urging quick action or an upfront deposit.",
    "fake-delivery": "A message claiming a package delivery failed or needs a fee paid, asking the recipient to click a link or provide payment details.",
    "tech-support-scam": "A message claiming the recipient's computer or account has a virus or security problem and instructing them to call a number or install remote-access software.",
    "job-scam": "A job offer requiring upfront payment, reshipping packages, or personal banking details before any real work begins, or promising unusually high pay for minimal effort.",
    "lottery-inheritance-scam": "A message claiming the recipient has won a lottery, prize, or inheritance they never entered, and must pay a fee or provide details to claim it.",
    "legitimate": "A normal, benign message with no request for money, credentials, personal financial information, or urgent action.",
}

SITE_CATEGORY_DESCRIPTIONS = {
    "phishing-clone": "A fake login page or clone of a well-known bank, service, or brand designed to steal credentials or payment details.",
    "scam-shop": "An online shop with unrealistic discounts, no verifiable contact details, and pressure to buy immediately.",
    "legitimate": "A normal, legitimate website - a real business, service, news outlet, or informational page with no signs of impersonation or fraud.",
    "other": "A page that doesn't clearly fit phishing, a scam shop, or a legitimate site.",
}

MODEL_NAME = "all-MiniLM-L6-v2"
SCAM_THRESHOLD = 0.28
SITE_THRESHOLD = 0.24

_model = None
_scam_embeddings = None
_site_embeddings = None
_scam_names = list(SCAM_CATEGORY_DESCRIPTIONS.keys())
_site_names = list(SITE_CATEGORY_DESCRIPTIONS.keys())


def _get_model():
    global _model, _scam_embeddings, _site_embeddings
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
        _scam_embeddings = _model.encode(list(SCAM_CATEGORY_DESCRIPTIONS.values()), convert_to_tensor=True)
        _site_embeddings = _model.encode(list(SITE_CATEGORY_DESCRIPTIONS.values()), convert_to_tensor=True)
    return _model


def classify_scam_text(text: str):
    text = (text or "").strip()
    if not text:
        return {"category": "legitimate", "confidence": 0.0}
    model = _get_model()
    embedding = model.encode(text[:4000], convert_to_tensor=True)
    scores = util.cos_sim(embedding, _scam_embeddings)[0]
    best_idx = int(scores.argmax())
    confidence = float(scores[best_idx])
    category = _scam_names[best_idx] if confidence >= SCAM_THRESHOLD else "legitimate"
    return {"category": category, "confidence": round(confidence, 3)}


def classify_site_text(text: str):
    text = (text or "").strip()
    if not text:
        return {"category": "other", "confidence": 0.0}
    model = _get_model()
    embedding = model.encode(text[:4000], convert_to_tensor=True)
    scores = util.cos_sim(embedding, _site_embeddings)[0]
    best_idx = int(scores.argmax())
    confidence = float(scores[best_idx])
    category = _site_names[best_idx] if confidence >= SITE_THRESHOLD else "other"
    return {"category": category, "confidence": round(confidence, 3)}
