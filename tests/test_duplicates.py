"""Ticketing Pro todo 9: duplicate linking via LinkedTo (TDD)."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService
    from services.schemas import INCIDENT_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "dup.db")
    monkeypatch.setattr(app_mod, "incidents", DbStore(db, "incidents", INCIDENT_COLS))
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
    a = svc.create(asset_id="AST001", title="Принтер молчи", performed_by="admin")
    b = svc.create(asset_id="AST002", title="Принтер не печати", performed_by="admin")
    app_mod.auth_svc.create_user("mag", "dolgapass123", role="magacioner")
    app_mod.auth_svc.create_user("cit", "dolgapass123", role="citac")
    return app_mod, a["IncidentID"], b["IncidentID"]


def _wipe_users():
    import sqlite3

    import app as app_mod

    con = sqlite3.connect(app_mod.DB_PATH)
    con.execute("DELETE FROM users")
    con.commit()
    con.close()


def _login(client, user, pw="dolgapass123"):
    return client.post("/login", data={"username": user, "password": pw})


def test_link_unlink_display(monkeypatch):
    app_mod, aid, bid = _env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        _login(c, "mag")
        r = c.post("/incidents/link", data={"incident_id": aid, "target_id": bid})
        assert r.status_code == 302
        row = app_mod.incidents.find("IncidentID", aid)
        assert row is not None and row.get("LinkedTo") == bid
        html = c.get(f"/incident/{aid}").get_data(as_text=True)
        assert bid in html
        assert "дупликат" in html
        r2 = c.post("/incidents/unlink", data={"incident_id": aid})
        assert r2.status_code == 302
        row2 = app_mod.incidents.find("IncidentID", aid)
        assert row2 is not None and row2.get("LinkedTo", "") == ""
    finally:
        _wipe_users()


def test_self_link_refused(monkeypatch):
    app_mod, aid, bid = _env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        _login(c, "mag")
        r = c.post("/incidents/link", data={"incident_id": aid, "target_id": aid})
        assert r.status_code == 302
        row = app_mod.incidents.find("IncidentID", aid)
        assert row is not None and row.get("LinkedTo", "") == ""
        assert "ГРЕШКА" in c.get(f"/incident/{aid}").get_data(as_text=True)
    finally:
        _wipe_users()


def test_unknown_target_refused(monkeypatch):
    app_mod, aid, bid = _env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        _login(c, "mag")
        r = c.post("/incidents/link", data={"incident_id": aid, "target_id": "I999999"})
        assert r.status_code == 302
        row = app_mod.incidents.find("IncidentID", aid)
        assert row is not None and row.get("LinkedTo", "") == ""
    finally:
        _wipe_users()


def test_citac_link_blocked(monkeypatch):
    app_mod, aid, bid = _env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        _login(c, "cit")
        assert (
            c.post(
                "/incidents/link", data={"incident_id": aid, "target_id": bid}
            ).status_code
            == 403
        )
        assert c.post("/incidents/unlink", data={"incident_id": aid}).status_code == 403
    finally:
        _wipe_users()
