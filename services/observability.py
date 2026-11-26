"""Process-local request metrics and JSON logging.

Design: docs/superpowers/specs/2026-11-16-observability-design.md

Counters are deliberately in memory: no DB write per request. The JSON access
log is the durable, cross-process record; ``scripts/log_report.py`` aggregates
it across restarts and gunicorn workers.
"""

import bisect
import json
import logging
import logging.handlers
import os
import sys
import threading
import time
from collections import Counter, deque
from datetime import datetime, timezone
from math import ceil

BUCKET_EDGES_MS = (5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000)

_BUCKETS = len(BUCKET_EDGES_MS) + 1  # last bucket is "above the top edge"
_LOCK = threading.Lock()
_STATE = {
    "started_at": time.time(),
    "total": 0,
    "classes": Counter(),
    "rate_limited": 0,
    "routes": {},
    "hist": [0] * _BUCKETS,
    "problems": deque(maxlen=100),
}

_installed: list[logging.Handler] = []


def _iso(ts: float) -> str:
    return (
        datetime.fromtimestamp(ts, tz=timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _p95(hist: list[int], total: int) -> int | None:
    """Estimated p95: the upper edge of the bucket holding the 95th request."""
    if total <= 0:
        return None
    target = ceil(0.95 * total)
    seen = 0
    for idx, count in enumerate(hist):
        seen += count
        if seen >= target:
            if idx < len(BUCKET_EDGES_MS):
                return BUCKET_EDGES_MS[idx]
            return BUCKET_EDGES_MS[-1]
    return BUCKET_EDGES_MS[-1]


def record(
    method: str,
    route: str,
    status: int,
    duration_ms: float,
    request_id: str = "",
    now: float | None = None,
) -> None:
    """Count one finished request and keep it if it was slow or failed."""
    status = int(status)
    idx = bisect.bisect_left(BUCKET_EDGES_MS, duration_ms)
    stamp = time.time() if now is None else now
    with _LOCK:
        _STATE["total"] += 1
        _STATE["classes"][f"{status // 100}xx"] += 1
        if status == 429:
            _STATE["rate_limited"] += 1
        key = (method, route)
        row = _STATE["routes"].setdefault(
            key,
            {"count": 0, "errors": 0, "rate_limited": 0, "hist": [0] * _BUCKETS},
        )
        row["count"] += 1
        row["hist"][idx] += 1
        _STATE["hist"][idx] += 1
        if status >= 500:
            row["errors"] += 1
        if status == 429:
            row["rate_limited"] += 1
        if status >= 500 or duration_ms >= 1000:
            _STATE["problems"].appendleft(
                {
                    "ts": _iso(stamp),
                    "request_id": request_id,
                    "method": method,
                    "route": route,
                    "status": status,
                    "duration_ms": round(duration_ms, 1),
                }
            )


def snapshot() -> dict:
    """Immutable view for the admin page and tests."""
    with _LOCK:
        routes = []
        for (method, rule), row in _STATE["routes"].items():
            routes.append(
                {
                    "method": method,
                    "route": rule,
                    "count": row["count"],
                    "errors": row["errors"],
                    "rate_limited": row["rate_limited"],
                    "p95_ms": _p95(row["hist"], row["count"]),
                }
            )
        routes.sort(key=lambda r: (-r["errors"], -r["count"], r["route"]))
        return {
            "started_at": _iso(_STATE["started_at"]),
            "uptime_sec": round(time.time() - _STATE["started_at"], 1),
            "pid": os.getpid(),
            "total": _STATE["total"],
            "classes": {
                k: _STATE["classes"].get(k, 0) for k in ("2xx", "3xx", "4xx", "5xx")
            },
            "errors": _STATE["classes"].get("5xx", 0),
            "rate_limited": _STATE["rate_limited"],
            "p95_ms": _p95(_STATE["hist"], _STATE["total"]),
            "routes": routes,
            "problems": list(_STATE["problems"]),
        }


def reset() -> None:
    with _LOCK:
        _STATE["started_at"] = time.time()
        _STATE["total"] = 0
        _STATE["classes"].clear()
        _STATE["rate_limited"] = 0
        _STATE["routes"].clear()
        _STATE["hist"] = [0] * _BUCKETS
        _STATE["problems"].clear()


class JsonFormatter(logging.Formatter):
    """One JSON object per line; never raises on unusual records."""

    _REQUEST_KEYS = (
        "request_id",
        "role",
        "method",
        "path",
        "route",
        "status",
        "duration_ms",
    )

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": _iso(record.created),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "pid": getattr(record, "pid", None) or os.getpid(),
        }
        for key in self._REQUEST_KEYS:
            value = getattr(record, key, None)
            if value is not None and value != "":
                payload[key] = value
        exc = getattr(record, "exc_info_text", "")
        if not exc and record.exc_info:
            exc = self.formatException(record.exc_info)
        if exc:
            payload["exc"] = exc
        return json.dumps(payload, ensure_ascii=False)


class RequestContextFilter(logging.Filter):
    """Stamp request_id/role/pid on records emitted inside a request."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            from flask import g, has_request_context

            if has_request_context():
                if not getattr(record, "request_id", None):
                    record.request_id = g.get("request_id", "")
                if not getattr(record, "role", None):
                    record.role = g.get("role", "")
        except Exception:  # observability must never break a log call
            return True
        if not getattr(record, "pid", None):
            record.pid = os.getpid()
        return True


def configure_logging(
    log_file: str | None,
    *,
    stream: bool = True,
    force: bool = False,
    level: int = logging.INFO,
) -> None:
    """Attach JSON handlers to the root logger; idempotent across calls."""
    global _installed
    root = logging.getLogger()
    if _installed and not force:
        # A second import of app.py (python3 app.py + `from app import ...`
        # in lazy views) must not attach duplicate handlers.
        root.setLevel(level)
        return
    if force:
        for handler in _installed:
            root.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass
        _installed = []

    formatter = JsonFormatter()
    context = RequestContextFilter()

    # werkzeug logs the client IP and query string on every request; our access
    # record replaces it (and would otherwise duplicate each line).
    werkzeug = logging.getLogger("werkzeug")
    werkzeug.propagate = False
    for handler in list(werkzeug.handlers):
        werkzeug.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass
    werkzeug.addHandler(logging.NullHandler())

    if log_file:
        directory = os.path.dirname(log_file)
        if directory:
            os.makedirs(directory, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10_000_000,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler.addFilter(context)
        root.addHandler(file_handler)
        _installed.append(file_handler)

    if stream:
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        stream_handler.addFilter(context)
        root.addHandler(stream_handler)
        _installed.append(stream_handler)

    root.setLevel(level)
