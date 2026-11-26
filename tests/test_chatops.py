"""P2.6: ChatOps macros CRUD, /api/v1/macros and its auth matrix."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.schemas import MACRO_COLS

    db = os.path.join(tempfile.mkdtemp(), "chatops.db")
    monkeypatch.setattr(app_mod, "macros", DbStore(db, "macros", MACRO_COLS))
    app_mod.auth_svc.create_user("adm", "dolgapass123", role="admin")
    app_mod.auth_svc.create_user("mag", "dolgapass123", role="magacioner")
    app_mod.auth_svc.create_user("cit", "dolgapass123", role="citac")
    return app_mod


def _login(client, user):
    return client.post("/login", data={"username": user, "password": "dolgapass123"})


def _wipe_users():
    import sqlite3

    import app as app_mod

    con = sqlite3.connect(app_mod.DB_PATH)
    con.execute("DELETE FROM users")
    con.commit()
    con.close()


def test_macro_crud_and_picker_api(monkeypatch):
    app_mod = _env(monkeypatch)
    try:
        admin = app_mod.app.test_client()
        _login(admin, "adm")
        r = admin.post(
            "/settings/macros",
            data={
                "title": "Ресетирање лозинка",
                "body": "Лозинката е ресетирана.",
                "category": "Пристап",
            },
        )
        assert r.status_code == 302
        rows = app_mod.macros.records()
        assert len(rows) == 1
        assert rows[0]["Title"] == "Ресетирање лозинка"
        macro_id = rows[0]["MacroID"]

        cit = app_mod.app.test_client()
        _login(cit, "cit")
        api = cit.get("/api/v1/macros")
        assert api.status_code == 200
        payload = api.get_json()
        assert payload == [
            {
                "MacroID": macro_id,
                "Title": "Ресетирање лозинка",
                "Category": "Пристап",
                "BodyText": "Лозинката е ресетирана.",
            }
        ]

        assert admin.post(f"/settings/macros/{macro_id}/delete").status_code == 302
        assert app_mod.macros.records() == []
    finally:
        _wipe_users()


def test_macro_validation_rejects_empty_fields(monkeypatch):
    app_mod = _env(monkeypatch)
    try:
        admin = app_mod.app.test_client()
        _login(admin, "adm")
        assert (
            admin.post("/settings/macros", data={"title": "", "body": ""}).status_code
            == 302
        )
        assert app_mod.macros.records() == []
    finally:
        _wipe_users()


def test_macro_admin_is_admin_only(monkeypatch):
    app_mod = _env(monkeypatch)
    try:
        anon = app_mod.app.test_client()
        assert anon.get("/settings/macros").status_code == 302
        assert anon.get("/api/v1/macros").status_code == 401

        for user in ("mag", "cit"):
            c = app_mod.app.test_client()
            _login(c, user)
            assert c.get("/settings/macros").status_code == 403, user
            assert c.post("/settings/macros", data={}).status_code == 403, user
            assert c.get("/api/v1/macros").status_code == 200, user
    finally:
        _wipe_users()
