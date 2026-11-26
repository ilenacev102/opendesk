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


def test_login_next_open_redirect_blocked(monkeypatch):
    """M4: `next` must never redirect off-site after successful login."""
    app_mod = _auth_env(monkeypatch)
    try:
        for evil in ("//evil.com", "https://evil.com", "http://evil.com"):
            c = app_mod.app.test_client()
            r = c.post(
                f"/login?next={evil}",
                data={"username": "adm", "password": "dolgapass123"},
            )
            assert r.status_code == 302, evil
            assert "evil.com" not in r.headers["Location"], evil
        # local paths still honoured
        c = app_mod.app.test_client()
        r = c.post(
            "/login?next=/users", data={"username": "adm", "password": "dolgapass123"}
        )
        assert r.headers["Location"].endswith("/users")
    finally:
        _wipe_users()


def test_citac_portal_post_allowed(monkeypatch):
    """M5: citac must be able to submit portal self-service forms (the portal's
    whole purpose) while every other POST stays blocked."""
    app_mod = _auth_env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        _login(c, "cit")
        r = c.post("/portal/incident", data={"title": "Проблем"})
        assert r.status_code in (200, 302), r.status_code
        r2 = c.post("/portal/request", data={})
        assert r2.status_code in (200, 302), r2.status_code
        # everything else stays blocked
        assert c.post("/devices/new", data={}).status_code == 403
        assert c.post("/consumables/issue", data={}).status_code == 403
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


def test_new_blueprints_auth(monkeypatch):
    """files/reports blueprints honor the same auth matrix."""
    app_mod = _auth_env(monkeypatch)
    try:
        anon = app_mod.app.test_client()
        ca, cc = app_mod.app.test_client(), app_mod.app.test_client()
        _login(ca, "adm")
        _login(cc, "cit")
        # anonymous: pages redirect, api 401
        assert anon.get("/labels").status_code == 302
        assert anon.get("/reports").status_code == 302
        assert anon.get("/import").status_code == 302
        # logged-in GET allowed for both roles
        assert ca.get("/labels").status_code == 200
        assert cc.get("/labels").status_code == 200
        assert ca.get("/reports").status_code == 200
        assert cc.get("/reports").status_code == 200
        assert ca.get("/import").status_code == 200
        assert cc.get("/import").status_code == 200
        # citac POST blocked, admin POST passes guard (may 200/302, never 403)
        assert cc.post("/notify-digest", data={}).status_code == 403
        assert cc.post("/import", data={}).status_code == 403
        assert ca.post("/notify-digest", data={}).status_code in (200, 302)
        # observability page is admin-only
        assert anon.get("/system/observability").status_code == 302
        assert ca.get("/system/observability").status_code == 200
        assert cc.get("/system/observability").status_code == 403
    finally:
        _wipe_users()


def test_session_cookie_flags(monkeypatch):
    app_mod = _auth_env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        resp = _login(c, "adm")
        cookie = resp.headers.get("Set-Cookie", "")
        assert "HttpOnly" in cookie
        assert "SameSite" in cookie
    finally:
        _wipe_users()


def test_files_traversal_blocked(monkeypatch):
    app_mod = _auth_env(monkeypatch)
    try:
        ca = app_mod.app.test_client()
        _login(ca, "adm")
        assert ca.get("/doc/../app.py").status_code == 404
        assert ca.get("/doc/documents/../../app.py").status_code == 404
        assert ca.get("/pdf/../app.py").status_code == 404
        assert ca.get("/pdf/etc/passwd").status_code == 404
    finally:
        _wipe_users()


def _login_all(app_mod):
    clients = {}
    for role, user in (
        ("admin", "adm"),
        ("magacioner", "mag"),
        ("citac", "cit"),
    ):
        c = app_mod.app.test_client()
        _login(c, user)
        clients[role] = c
    return clients


def test_blueprint_matrix(monkeypatch):
    """One row per blueprint: admin / magacioner / citac / anonymous."""
    app_mod = _auth_env(monkeypatch)
    app_mod.auth_svc.create_user("mag", "dolgapass123", role="magacioner")
    try:
        from services.project_service import ensure_defaults

        ensure_defaults(app_mod.projects, app_mod.project_types, app_mod.incidents)
        pid = app_mod.projects.records()[0]["ProjectID"]
        anon = app_mod.app.test_client()
        clients = _login_all(app_mod)

        pages = [
            ("chatops", "/settings/macros", {"magacioner": 403, "citac": 403}),
            ("sprints", f"/projects/{pid}/backlog", {}),
            ("itsm", "/problems", {}),
            ("maintenance", "/maintenance", {}),
            ("racks", "/racks", {}),
            ("cmdb", "/cmdb/topology", {}),
            ("popis", "/popis", {}),
            ("portal", "/portal", {}),
            ("portal_tickets", "/portal/tickets", {}),
            ("portal_ticket", "/portal/ticket/NOPE", {}),
            ("system", "/notifications", {}),
            ("boards", f"/projects/{pid}/board", {}),
        ]
        for name, path, expected in pages:
            assert anon.get(path).status_code == 302, (name, "anon")
            for role, client in clients.items():
                status = client.get(path).status_code
                if role in expected:
                    assert status == expected[role], (name, role, status)
                else:
                    assert status not in (302, 401, 403), (name, role, status)

        posts = [
            ("chatops", "/settings/macros", {"magacioner": 403}),
            ("sprints", "/sprints/NOPE/start", {}),
            ("itsm", "/problems/resolve", {}),
            ("maintenance", "/maintenance/complete", {}),
            ("racks", "/racks/remove", {}),
            ("cmdb", "/cmdb/relations/delete/NOPE", {}),
            ("popis", "/popis/NOPE/found", {}),
            ("portal", "/portal/request", {"citac": 302}),
            ("portal_ticket_comment", "/portal/ticket/NOPE/comment", {}),
            ("portal_ticket_rate", "/portal/ticket/NOPE/rate", {}),
            ("portal_ticket_reopen", "/portal/ticket/NOPE/reopen", {}),
            ("portal_notifications_read", "/portal/notifications/read", {}),
            ("system", "/notifications/read", {}),
        ]
        for name, path, expected in posts:
            for role, client in clients.items():
                status = client.post(path, data={}).status_code
                if role == "citac" and not name.startswith("portal"):
                    assert status == 403, (name, role, status)
                elif role in expected:
                    assert status == expected[role], (name, role, status)
                else:
                    assert status != 403, (name, role, status)
    finally:
        _wipe_users()


def test_new_api_blueprints_auth(monkeypatch):
    """cmdb/macros APIs: anonymous 401, any logged-in role 200."""
    app_mod = _auth_env(monkeypatch)
    app_mod.auth_svc.create_user("mag", "dolgapass123", role="magacioner")
    try:
        anon = app_mod.app.test_client()
        assert anon.get("/api/v1/cmdb/graph").status_code == 401
        assert anon.get("/api/v1/macros").status_code == 401
        for user in ("adm", "mag", "cit"):
            c = app_mod.app.test_client()
            _login(c, user)
            assert c.get("/api/v1/cmdb/graph").status_code == 200, user
            assert c.get("/api/v1/macros").status_code == 200, user
    finally:
        _wipe_users()
