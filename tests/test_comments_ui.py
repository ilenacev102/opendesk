"""Ticketing Pro todo 4: comments + activity thread (tests-after)."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.history_service import HistoryService, HISTORY_COLS
    from services.schemas import COMMENT_COLS, INCIDENT_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "cmt.db")
    monkeypatch.setattr(app_mod, "incidents", DbStore(db, "incidents", INCIDENT_COLS))
    monkeypatch.setattr(app_mod, "comments", DbStore(db, "comments", COMMENT_COLS))
    monkeypatch.setattr(
        app_mod, "history", HistoryService(DbStore(db, "history", HISTORY_COLS))
    )
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)
    from services.incident_service import IncidentService

    svc = IncidentService(
        app_mod.incidents,
        app_mod.history,
        db_path=getattr(app_mod.incidents, "db_path", None),
    )
    inc = svc.create(asset_id="AST001", title="Тест", performed_by="admin")
    app_mod.auth_svc.create_user("mag", "dolgapass123", role="magacioner")
    app_mod.auth_svc.create_user("cit", "dolgapass123", role="citac")
    return app_mod, inc["IncidentID"]


def _wipe_users():
    import sqlite3

    import app as app_mod

    con = sqlite3.connect(app_mod.DB_PATH)
    con.execute("DELETE FROM users")
    con.commit()
    con.close()


def _login(client, user, pw="dolgapass123"):
    return client.post("/login", data={"username": user, "password": pw})


def test_comment_post_visible_in_thread(monkeypatch):
    app_mod, iid = _env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        _login(c, "mag")
        r = c.post(
            "/incidents/comment",
            data={"incident_id": iid, "body": "Пробан кабел, работи."},
        )
        assert r.status_code == 302
        html = c.get(f"/incident/{iid}").get_data(as_text=True)
        assert "Пробан кабел, работи." in html
        assert "mag" in html
    finally:
        _wipe_users()


def test_comment_empty_rejected(monkeypatch):
    app_mod, iid = _env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        _login(c, "mag")
        r = c.post("/incidents/comment", data={"incident_id": iid, "body": "   "})
        assert r.status_code == 302
        assert app_mod.comments.records() == []
    finally:
        _wipe_users()


def test_comment_xss_escaped(monkeypatch):
    app_mod, iid = _env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        _login(c, "mag")
        c.post(
            "/incidents/comment",
            data={"incident_id": iid, "body": "<script>alert(1)</script>"},
        )
        html = c.get(f"/incident/{iid}").get_data(as_text=True)
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html
    finally:
        _wipe_users()


def test_citac_comment_blocked(monkeypatch):
    app_mod, iid = _env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        _login(c, "cit")
        r = c.post("/incidents/comment", data={"incident_id": iid, "body": "Здраво"})
        assert r.status_code == 403
        assert app_mod.comments.records() == []
    finally:
        _wipe_users()
