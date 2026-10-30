"""Backlog observability: X-Request-ID on every response."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_health_carries_request_id():
    import app as app_mod

    c = app_mod.app.test_client()
    r = c.get("/health")
    assert r.status_code == 200
    rid = r.headers.get("X-Request-ID", "")
    assert rid and len(rid) <= 64


def test_request_id_echoed_when_valid():
    import app as app_mod

    c = app_mod.app.test_client()
    r = c.get("/health", headers={"X-Request-ID": "probe-123"})
    assert r.headers.get("X-Request-ID") == "probe-123"


def test_request_id_replaced_when_garbage():
    import app as app_mod

    c = app_mod.app.test_client()
    r = c.get("/health", headers={"X-Request-ID": "bad id with spaces!"})
    assert r.headers.get("X-Request-ID") != "bad id with spaces!"
    assert r.headers.get("X-Request-ID", "")
