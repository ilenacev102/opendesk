"""P2.1: CSRF protects cookie-authenticated /api POSTs; Bearer stays exempt."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_should_enforce_rules():
    from services.csrf import should_enforce

    assert should_enforce("/api/v1/checkout") is True
    assert should_enforce("/api/v1/checkout", "Bearer abc") is False
    assert should_enforce("/api/v1/checkout", "bearer abc") is False
    assert should_enforce("/devices", "Bearer abc") is True
    assert should_enforce("/devices") is True


def _env(monkeypatch):
    import app as app_mod

    tmp = tempfile.mkdtemp()
    monkeypatch.setenv("SERVICEDESK_DB", os.path.join(tmp, "csrf.db"))
    app_mod.auth_svc.create_user("adm", "dolgapass123", role="admin")
    monkeypatch.setitem(app_mod.app.config, "CSRF_ENABLED", True)
    return app_mod


def _login(client):
    with client.session_transaction() as sess:
        sess["_csrf_token"] = "login-tok"
    return client.post(
        "/login",
        data={
            "username": "adm",
            "password": "dolgapass123",
            "_csrf_token": "login-tok",
        },
    )


def _wipe_users():
    import sqlite3

    import app as app_mod

    con = sqlite3.connect(app_mod.DB_PATH)
    con.execute("DELETE FROM users")
    con.commit()
    con.close()


def test_cookie_api_post_without_token_is_rejected(monkeypatch):
    app_mod = _env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        _login(c)
        r = c.post("/api/v1/checkout", json={"asset_id": "A1", "emp_id": "E1"})
        assert r.status_code == 403
    finally:
        _wipe_users()


def test_cookie_api_post_with_session_token_passes_csrf(monkeypatch):
    app_mod = _env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        _login(c)
        with c.session_transaction() as sess:
            sess["_csrf_token"] = "tok-123"
        r = c.post(
            "/api/v1/checkout",
            json={"asset_id": "A1", "emp_id": "E1"},
            headers={"X-CSRF-Token": "tok-123"},
        )
        assert r.status_code != 403
    finally:
        _wipe_users()


def test_bearer_api_post_is_exempt_from_csrf(monkeypatch):
    app_mod = _env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        r = c.post(
            "/api/v1/checkout",
            json={"asset_id": "A1", "emp_id": "E1"},
            headers={"Authorization": "Bearer not-a-real-token"},
        )
        # CSRF must not be the reason for rejection; auth answers 401.
        assert r.status_code != 403
    finally:
        _wipe_users()
