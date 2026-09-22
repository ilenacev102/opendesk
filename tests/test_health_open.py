"""Health endpoint must stay open even when auth is enabled."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_health_open_when_auth_required(monkeypatch):
    import app as app_mod

    monkeypatch.setattr(app_mod.auth_svc, "auth_required", lambda: True)

    c = app_mod.app.test_client()
    r = c.get("/health")
    assert r.status_code == 200
    assert r.get_json() == {"status": "ok"}


def test_login_still_open_when_auth_required(monkeypatch):
    import app as app_mod

    monkeypatch.setattr(app_mod.auth_svc, "auth_required", lambda: True)

    c = app_mod.app.test_client()
    r = c.get("/login")
    assert r.status_code == 200


def test_setup_redirects_when_auth_required(monkeypatch):
    import app as app_mod

    monkeypatch.setattr(app_mod.auth_svc, "auth_required", lambda: True)

    c = app_mod.app.test_client()
    r = c.get("/setup")
    assert r.status_code == 302
    assert "/login" in r.headers.get("Location", "")
