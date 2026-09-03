"""Decodes a QR code image so its target URL can be safety-checked
before anyone opens it blind. Uses pyzbar (a thin wrapper over the
zbar C library, via the libzbar0 system package) - a small, well-
established dependency, not a heavy new one."""
import io

from PIL import Image
from pyzbar.pyzbar import decode


def decode_qr(image_bytes: bytes):
    img = Image.open(io.BytesIO(image_bytes))
    results = decode(img)
    return [r.data.decode("utf-8", errors="replace") for r in results]
