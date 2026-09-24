"""Sliding-window rate limiter with swappable backend.

MemoryLimiter is process-local (default, zero setup). FileLimiter shares
state across workers through an fcntl-locked JSON file. Select via
SERVICEDESK_RATELIMIT=file|memory (default memory) and
SERVICEDESK_RATELIMIT_FILE (default data/ratelimit.json).

Module-level is_allowed()/reset() keep working and delegate to the active
backend selected at import time.
"""

import fcntl
import json
import os
import time
from typing import Protocol, runtime_checkable


@runtime_checkable
class RateLimiter(Protocol):
    def is_allowed(self, key: str, limit: int, window_sec: int, now=None) -> bool: ...
    def reset(self) -> None: ...


def _prune(bucket: list[float], now: float, window_sec: int) -> list[float]:
    cutoff = now - window_sec
    return [t for t in bucket if t > cutoff]


class MemoryLimiter:
    def __init__(self):
        self._hits: dict[str, list[float]] = {}

    def is_allowed(self, key: str, limit: int, window_sec: int, now=None) -> bool:
        now = time.time() if now is None else now
        bucket = _prune(self._hits.setdefault(key, []), now, window_sec)
        if len(bucket) >= limit:
            self._hits[key] = bucket
            return False
        bucket.append(now)
        self._hits[key] = bucket
        return True

    def reset(self) -> None:
        self._hits.clear()


class FileLimiter:
    def __init__(self, path: str):
        self.path = path
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)

    def _read_locked(self, fh) -> dict[str, object]:
        try:
            fh.seek(0)
            raw = fh.read()
            data = json.loads(raw) if raw.strip() else {}
            return data if isinstance(data, dict) else {}
        except (ValueError, OSError):
            return {}

    def _with_state(self, fn):
        with open(self.path, "a+", encoding="utf-8") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                state = self._read_locked(fh)
                result, state = fn(state)
                fh.seek(0)
                fh.truncate()
                fh.write(json.dumps(state))
                return result
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

    def is_allowed(self, key: str, limit: int, window_sec: int, now=None) -> bool:
        now = time.time() if now is None else now

        def _check(state):
            bucket = _prune(state.get(key, []), now, window_sec)
            if len(bucket) >= limit:
                state[key] = bucket
                return False, state
            bucket.append(now)
            state[key] = bucket
            return True, state

        return self._with_state(_check)

    def reset(self) -> None:
        def _clear(state):
            return None, {}

        self._with_state(_clear)


def _default_file_path() -> str:
    try:
        import config as _config

        base = getattr(_config, "DATA_DIR", ".")
    except Exception:
        base = "."
    return os.environ.get(
        "SERVICEDESK_RATELIMIT_FILE", os.path.join(base, "ratelimit.json")
    )


def get_limiter() -> RateLimiter:
    mode = os.environ.get("SERVICEDESK_RATELIMIT", "memory").strip().lower()
    if mode == "file":
        return FileLimiter(_default_file_path())
    return MemoryLimiter()


_active: RateLimiter = get_limiter()


def is_allowed(key: str, limit: int, window_sec: int, now=None) -> bool:
    return _active.is_allowed(key, limit, window_sec, now=now)


def reset() -> None:
    _active.reset()
