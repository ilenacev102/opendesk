"""Ticketing Pro todo 6: KB articles CRUD + search (tests-after)."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.history_service import HistoryService, HISTORY_COLS
    from services.schemas import KB_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "kb.db")
    monkeypatch.setattr(app_mod, "kb_articles", DbStore(db, "kb_articles", KB_COLS))
    monkeypatch.setattr(
        app_mod, "history", HistoryService(DbStore(db, "history", HISTORY_COLS))
    )
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)
    app_mod.auth_svc.create_user("adm", "dolgapass123", role="admin")
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


def test_kb_crud_and_search(monkeypatch):
    app_mod = _env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        _login(c, "mag")
        assert c.get("/kb").status_code == 200
        r = c.post(
            "/kb/new",
            data={
                "Title": "Принтер не печати",
                "Body": "Провери кабел и драјвер.",
                "Tags": "принтер, хардвер",
            },
        )
        assert r.status_code == 302
        assert "Принтер не печати" in c.get("/kb").get_data(as_text=True)
        assert "Принтер" in c.get("/kb?q=печати").get_data(as_text=True)
        assert "Принтер" not in c.get("/kb?q=монитор").get_data(as_text=True)
        aid = app_mod.kb_articles.records()[0]["ArticleID"]
        assert c.get(f"/kb/{aid}").status_code == 200
        r2 = c.post(
            f"/kb/{aid}/edit",
            data={"Title": "Принтер — ажурирано", "Body": "Нов текст.", "Tags": ""},
        )
        assert r2.status_code == 302
        assert "ажурирано" in c.get(f"/kb/{aid}").get_data(as_text=True)
        assert c.get("/kb/NOPE").status_code == 404
    finally:
        _wipe_users()


def test_kb_empty_title_rejected(monkeypatch):
    app_mod = _env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        _login(c, "mag")
        r = c.post("/kb/new", data={"Title": "  ", "Body": "текст"})
        assert r.status_code == 302
        assert app_mod.kb_articles.records() == []
    finally:
        _wipe_users()


def test_citac_kb_write_blocked(monkeypatch):
    app_mod = _env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        _login(c, "cit")
        assert c.get("/kb").status_code == 200
        assert c.post("/kb/new", data={"Title": "x", "Body": "y"}).status_code == 403
        assert app_mod.kb_articles.records() == []
    finally:
        _wipe_users()
