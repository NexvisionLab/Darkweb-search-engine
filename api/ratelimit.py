"""Fixed-window per-IP rate limiting backed by Valkey - provisioned in
the stack from the start but unused until now. A free public API with
no auth needs abuse protection from day one, not as an afterthought."""
import os
import time

import redis

_client = None


def get_client():
    global _client
    if _client is None:
        _client = redis.Redis(
            host=os.environ.get("VALKEY_HOST", "127.0.0.1"),
            port=int(os.environ.get("VALKEY_PORT", "6379")),
            decode_responses=True,
        )
    return _client


def check_rate_limit(client_ip: str, bucket: str, limit: int, window_seconds: int) -> bool:
    """True if this request is allowed, False if the caller is over the limit."""
    client = get_client()
    window = int(time.time()) // window_seconds
    key = f"ratelimit:{bucket}:{client_ip}:{window}"
    count = client.incr(key)
    if count == 1:
        client.expire(key, window_seconds)
    return count <= limit
