"""Enterprise Wave1 todo 5: incidents UI list/detail/create/transition."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _ui_env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.history_service import HistoryService, HISTORY_COLS
    from services.schemas import INCIDENT_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "inc_ui.db")
    monkeypatch.setattr(app_mod, "incidents", DbStore(db, "incidents", INCIDENT_COLS))
    monkeypatch.setattr(
        app_mod, "history", HistoryService(DbStore(db, "history", HISTORY_COLS))
    )
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)
    app_mod.auth_svc.create_user("mag", "dolgapass123", role="magacioner")
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


def _seed(app_mod):
    from services.incident_service import IncidentService

    svc = IncidentService(
        app_mod.incidents,
        app_mod.history,
        db_path=getattr(app_mod.incidents, "db_path", None),
    )
    svc.create(
        asset_id="AST001",
        title="Не работи тастатура",
        priority="high",
        assignee="mag",
        performed_by="admin",
    )
    svc.create(
        asset_id="AST002",
        title="Скршен екран",
        priority="urgent",
        assignee="mag",
        performed_by="admin",
    )


def test_list_renders(monkeypatch):
    app_mod = _ui_env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        _login(c, "mag")
        r = c.get("/incidents")
        assert r.status_code == 200
        assert "Инциденти" in r.get_data(as_text=True)
    finally:
        _wipe_users()


def test_create_post_redirects_and_filters(monkeypatch):
    app_mod = _ui_env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        _login(c, "mag")
        r = c.post(
            "/incidents/new",
            data={
                "AssetID": "AST009",
                "Title": "Тест инцидент",
                "Priority": "low",
                "Assignee": "",
            },
        )
        assert r.status_code == 302
        r2 = c.get("/incidents?status=open")
        assert "Тест инцидент" in r2.get_data(as_text=True)
        r3 = c.get("/incidents?priority=urgent")
        assert "Тест инцидент" not in r3.get_data(as_text=True)
    finally:
        _wipe_users()


def test_detail_and_transition(monkeypatch):
    app_mod = _ui_env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        _login(c, "mag")
        _seed(app_mod)
        iid = app_mod.incidents.records()[0]["IncidentID"]
        r = c.get(f"/incident/{iid}")
        assert r.status_code == 200
        assert "Не работи тастатура" in r.get_data(as_text=True)
        r2 = c.post(
            "/incidents/transition",
            data={"incident_id": iid, "to_status": "in-progress"},
        )
        assert r2.status_code == 302
        updated = app_mod.incidents.find("IncidentID", iid)
        assert updated is not None and updated["Status"] == "in-progress"
        assert c.get("/incident/NOPE").status_code == 404
    finally:
        _wipe_users()


def test_citac_post_blocked(monkeypatch):
    app_mod = _ui_env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        _login(c, "cit")
        assert c.get("/incidents").status_code == 200  # read allowed
        assert c.post("/incidents/new", data={"Title": "x"}).status_code == 403
        assert (
            c.post(
                "/incidents/transition",
                data={"incident_id": "I000001", "to_status": "in-progress"},
            ).status_code
            == 403
        )
        assert app_mod.incidents.records() == []
    finally:
        _wipe_users()


def test_post_without_csrf_token_forbidden(monkeypatch):
    app_mod = _ui_env(monkeypatch)
    app_mod.app.config["CSRF_ENABLED"] = True
    try:
        c = app_mod.app.test_client()
        c.get("/login")
        with c.session_transaction() as sess:
            tok = sess.get("_csrf_token")
        assert tok
        c.post(
            "/login",
            data={"username": "mag", "password": "dolgapass123", "_csrf_token": tok},
        )
        r = c.post("/incidents/new", data={"Title": "без токен"})
        assert r.status_code == 403
        assert app_mod.incidents.records() == []
    finally:
        app_mod.app.config["CSRF_ENABLED"] = False
        _wipe_users()
