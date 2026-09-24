"""Ticketing Pro todo 5: incident attachments (tests-after)."""

import io
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
    db = os.path.join(tmp, "att.db")
    monkeypatch.setattr(app_mod, "incidents", DbStore(db, "incidents", INCIDENT_COLS))
    monkeypatch.setattr(app_mod, "comments", DbStore(db, "comments", COMMENT_COLS))
    monkeypatch.setattr(
        app_mod, "history", HistoryService(DbStore(db, "history", HISTORY_COLS))
    )
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)
    docs = os.path.join(tmp, "documents")
    os.makedirs(docs, exist_ok=True)
    monkeypatch.setattr("config.DOCUMENTS_DIR", docs)
    from services.incident_service import IncidentService

    svc = IncidentService(
        app_mod.incidents,
        app_mod.history,
        db_path=getattr(app_mod.incidents, "db_path", None),
    )
    inc = svc.create(asset_id="AST001", title="Тест", performed_by="admin")
    app_mod.auth_svc.create_user("mag", "dolgapass123", role="magacioner")
    app_mod.auth_svc.create_user("cit", "dolgapass123", role="citac")
    return app_mod, inc["IncidentID"], docs


def _wipe_users():
    import sqlite3

    import app as app_mod

    con = sqlite3.connect(app_mod.DB_PATH)
    con.execute("DELETE FROM users")
    con.commit()
    con.close()


def _login(client, user, pw="dolgapass123"):
    return client.post("/login", data={"username": user, "password": pw})


def test_upload_listed_and_downloadable(monkeypatch):
    app_mod, iid, docs = _env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        _login(c, "mag")
        r = c.post(
            "/incidents/attach",
            data={
                "incident_id": iid,
                "file": (io.BytesIO(b"fake-png-bytes"), "screen.png"),
            },
        )
        assert r.status_code == 302
        html = c.get(f"/incident/{iid}").get_data(as_text=True)
        assert "screen.png" in html
        dl = c.get(f"/incidents/attach/{iid}/screen.png")
        assert dl.status_code == 200
        assert dl.get_data() == b"fake-png-bytes"
    finally:
        _wipe_users()


def test_traversal_blocked(monkeypatch):
    app_mod, iid, docs = _env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        _login(c, "mag")
        r = c.post(
            "/incidents/attach",
            data={"incident_id": iid, "file": (io.BytesIO(b"x"), "../../evil.txt")},
        )
        assert r.status_code in (302, 400)
        assert not os.path.exists(os.path.join(docs, "evil.txt"))
        assert c.get("/incidents/attach/NOPE/x.png").status_code == 404
    finally:
        _wipe_users()


def test_exe_rejected(monkeypatch):
    app_mod, iid, docs = _env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        _login(c, "mag")
        r = c.post(
            "/incidents/attach",
            data={"incident_id": iid, "file": (io.BytesIO(b"MZ\x90"), "run.exe")},
        )
        assert r.status_code == 200
        assert "само" in r.get_data(as_text=True)
    finally:
        _wipe_users()


def test_citac_upload_blocked(monkeypatch):
    app_mod, iid, docs = _env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        _login(c, "cit")
        r = c.post(
            "/incidents/attach",
            data={"incident_id": iid, "file": (io.BytesIO(b"x"), "a.png")},
        )
        assert r.status_code == 403
    finally:
        _wipe_users()
