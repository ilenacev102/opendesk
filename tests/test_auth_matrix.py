"""Auth matrix: anonymous/login/roles behavior locked by tests."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _auth_env(monkeypatch):
    import app as app_mod

    tmp = tempfile.mkdtemp()
    monkeypatch.setenv("SERVICEDESK_DB", os.path.join(tmp, "auth.db"))
    app_mod.auth_svc.create_user("adm", "dolgapass123", role="admin")
    app_mod.auth_svc.create_user("cit", "dolgapass123", role="citac")
    return app_mod


def _wipe_users():
    import sqlite3

    import app as app_mod

    con = sqlite3.connect(app_mod.DB_PATH)
    con.execute("DELETE FROM users")
    con.commit()
    con.close()


def _login(client, user, pw="dolgapass123"):
    return client.post("/login", data={"username": user, "password": pw})


def test_anonymous_redirected_with_users(monkeypatch):
    app_mod = _auth_env(monkeypatch)
    try:
        assert app_mod.app.test_client().get("/").status_code == 302
        assert app_mod.app.test_client().get("/api/v1/devices").status_code == 401
    finally:
        _wipe_users()


def test_roles_matrix(monkeypatch):
    app_mod = _auth_env(monkeypatch)
    try:
        ca, cc = app_mod.app.test_client(), app_mod.app.test_client()
        _login(ca, "adm")
        _login(cc, "cit")
        assert ca.get("/users").status_code == 200
        assert cc.get("/").status_code == 200
        assert cc.get("/users").status_code == 403
        assert cc.post("/devices/new", data={}).status_code == 403
        assert cc.post("/consumables", data={}).status_code == 403
        assert ca.post("/devices/new", data={}).status_code == 200
    finally:
        _wipe_users()
