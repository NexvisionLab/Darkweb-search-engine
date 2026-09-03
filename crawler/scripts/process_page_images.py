"""OCR + QR extraction for images found on crawled pages - deferred
from the crawl itself (see onion_spider.py, which only records image
URLs), same reasoning as capture_previews.py: real per-image work has
no business running inline in the crawl loop.

Downloads each image over the same Tor/Privoxy proxy the crawler uses,
runs a self-hosted OCR engine (RapidOCR/onnxruntime - no system
package, unlike Tesseract) and pyzbar (already used for the public QR
checker tool) against it, and writes the combined text back so it's
searchable via image_text. Unlike the preview-screenshot pipeline, this
never stores or serves the image itself - only text extracted from it
- so the NudeNet sensitivity gate that applies to screenshots doesn't
apply here; there's no raw image being persisted or displayed."""
import io
import sys

import requests
from PIL import Image
from pyzbar.pyzbar import decode as decode_qr

sys.path.insert(0, ".")
from darkweb_crawler import db, entity_extract, search

TOR_PROXY = "http://127.0.0.1:8118"
PAGES_PER_RUN = 50
IMAGE_TIMEOUT_SECONDS = 20
MAX_IMAGE_BYTES = 8 * 1024 * 1024

_ocr_engine = None


def _get_ocr_engine():
    global _ocr_engine
    if _ocr_engine is None:
        from rapidocr_onnxruntime import RapidOCR

        _ocr_engine = RapidOCR()
    return _ocr_engine


def _fetch_image(url):
    resp = requests.get(
        url,
        proxies={"http": TOR_PROXY, "https": TOR_PROXY},
        timeout=IMAGE_TIMEOUT_SECONDS,
        stream=True,
    )
    resp.raise_for_status()
    content = resp.raw.read(MAX_IMAGE_BYTES + 1, decode_content=True)
    if len(content) > MAX_IMAGE_BYTES:
        raise ValueError("image too large, skipping")
    return content


def _process_image(image_bytes):
    ocr_text = ""
    qr_text = ""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.load()
    except Exception:
        return ocr_text, qr_text

    try:
        qr_results = decode_qr(img)
        qr_text = " ".join(r.data.decode("utf-8", errors="replace") for r in qr_results)
    except Exception:
        pass

    try:
        import numpy as np

        ocr_result, _ = _get_ocr_engine()(np.array(img.convert("RGB")))
        if ocr_result:
            ocr_text = " ".join(r[1] for r in ocr_result)
    except Exception:
        pass

    return ocr_text, qr_text


def main():
    conn = db.get_connection()
    pages = db.get_pages_needing_image_processing(conn, PAGES_PER_RUN)
    if not pages:
        print("No pages need image processing")
        conn.close()
        return

    client = search.get_client()
    processed = 0
    total_images = 0
    for page_id, domain_id, image_urls in pages:
        page_ocr_parts = []
        page_qr_parts = []
        for url in image_urls:
            try:
                image_bytes = _fetch_image(url)
            except Exception as e:
                print(f"  failed to fetch {url}: {e}")
                continue
            total_images += 1
            ocr_text, qr_text = _process_image(image_bytes)
            if ocr_text:
                page_ocr_parts.append(ocr_text)
            if qr_text:
                page_qr_parts.append(qr_text)

        combined_ocr = " ".join(page_ocr_parts)[:5000]
        combined_qr = " ".join(page_qr_parts)[:2000]
        db.update_page_image_results(conn, page_id, combined_ocr or None, combined_qr or None)

        image_text_for_search = (combined_ocr + " " + combined_qr).strip()
        if image_text_for_search:
            try:
                search.update_image_text(client, page_id, image_text_for_search)
            except Exception as e:
                print(f"  OpenSearch update failed for page {page_id}: {e}")

            found_entities = entity_extract.extract_entities(image_text_for_search)
            if found_entities:
                db.insert_page_entities(conn, page_id, domain_id, found_entities)

        processed += 1
        print(f"processed page {page_id}: {len(image_urls)} images, "
              f"{'OCR text found' if combined_ocr else 'no OCR text'}, "
              f"{'QR found' if combined_qr else 'no QR'}")

    print(f"Processed {processed} pages, {total_images} images total")
    conn.close()


if __name__ == "__main__":
    main()
