"""Encrypts stored authenticated-session cookies at rest. Real login
credentials for a (often illicit) forum account are meaningfully more
sensitive than anything else this platform stores - everything else in
Postgres is either crawled public content or a hash, this is a live
key to someone's account. Fernet symmetric encryption via
SESSION_ENCRYPTION_KEY (generated once into .env, never printed to a
terminal or committed). There's no fallback if the key is missing -
encryption is refused outright, not silently skipped."""
import os

from cryptography.fernet import Fernet

_fernet = None


def _get_fernet():
    global _fernet
    if _fernet is None:
        key = os.environ.get("SESSION_ENCRYPTION_KEY")
        if not key:
            raise RuntimeError(
                "SESSION_ENCRYPTION_KEY not set in .env - cannot encrypt or decrypt session data"
            )
        _fernet = Fernet(key.encode())
    return _fernet


def encrypt(plaintext):
    return _get_fernet().encrypt(plaintext.encode("utf-8"))


def decrypt(ciphertext):
    return _get_fernet().decrypt(bytes(ciphertext)).decode("utf-8")
