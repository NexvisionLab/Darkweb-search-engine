"""Language identification via py3langid - pure Python, bundled model,
no download, no network call. Plenty accurate for routing/labeling
purposes; not trying to be a translation-grade detector."""
import py3langid as langid


def detect(text: str):
    if not text or not text.strip():
        return None
    lang, _confidence = langid.classify(text[:4000])
    return lang
