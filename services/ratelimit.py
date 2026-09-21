"""Phase E: in-memory sliding-window rate limiter. Process-local by design."""

import time

_hits: dict[str, list[float]] = {}


def is_allowed(key: str, limit: int, window_sec: int, now=None) -> bool:
    now = time.time() if now is None else now
    bucket = _hits.setdefault(key, [])
    cutoff = now - window_sec
    while bucket and bucket[0] <= cutoff:
        bucket.pop(0)
    if len(bucket) >= limit:
        return False
    bucket.append(now)
    return True


def reset() -> None:
    _hits.clear()
