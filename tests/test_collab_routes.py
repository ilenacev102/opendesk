"""Phase 4b: collaboration routes — watch/unwatch/worklog/mentions/fixversion."""

import datetime
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.schemas import (
    COMMENT_COLS,
    INCIDENT_COLS,
    NOTIF_COLS,
    VERSION_COLS,
    WATCHER_COLS,
    WORKLOG_COLS,
)


def _ui_env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "collab_routes.db")
    monkeypatch.setattr(app_mod, "incidents", DbStore(db, "incidents", INCIDENT_COLS))
    monkeypatch.setattr(app_mod, "comments", DbStore(db, "comments", COMMENT_COLS))
    monkeypatch.setattr(
        app_mod, "history", HistoryService(DbStore(db, "history", HISTORY_COLS))
    )
    monkeypatch.setattr(
        app_mod, "notifications", DbStore(db, "notifications", NOTIF_COLS)
    )
    monkeypatch.setattr(app_mod, "watchers", DbStore(db, "watchers", WATCHER_COLS))
    monkeypatch.setattr(app_mod, "worklogs", DbStore(db, "worklogs", WORKLOG_COLS))
    monkeypatch.setattr(app_mod, "versions", DbStore(db, "versions", VERSION_COLS))
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)
    app_mod.auth_svc.create_user("adm", "dolgapass123", role="admin")
    app_mod.auth_svc.create_user("cit", "dolgapass123", role="citac")
    app_mod.auth_svc.create_user("ana", "dolgapass123", role="magacioner")
    app_mod.auth_svc.create_user("bob", "dolgapass123", role="magacioner")
    from services.incident_service import IncidentService

    svc = IncidentService(
        app_mod.incidents,
        app_mod.history,
        db_path=getattr(app_mod.incidents, "db_path", None),
    )
    inc = svc.create(asset_id="AST001", title="Тест тикет", performed_by="admin")
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


def test_citac_watch_forbidden(monkeypatch):
    from services import ratelimit as rl

    rl.reset()
    app_mod, iid = _ui_env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        _login(c, "cit")
        r = c.post(f"/incidents/{iid}/watch")
        assert r.status_code == 403
        assert app_mod.watchers.records() == []
    finally:
        _wipe_users()


def test_watch_dedup_and_unwatch(monkeypatch):
    from services import ratelimit as rl

    rl.reset()
    app_mod, iid = _ui_env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        _login(c, "adm")
        assert c.post(f"/incidents/{iid}/watch").status_code == 302
        assert c.post(f"/incidents/{iid}/watch").status_code == 302
        rows = app_mod.watchers.records()
        assert len(rows) == 1
        assert rows[0]["UserName"] == "adm"
        assert c.post(f"/incidents/{iid}/unwatch").status_code == 302
        assert app_mod.watchers.records() == []
        assert c.post(f"/incidents/{iid}/unwatch").status_code == 302
        assert app_mod.watchers.records() == []
    finally:
        _wipe_users()


def test_worklog_valid_and_total_shown(monkeypatch):
    from services import ratelimit as rl

    rl.reset()
    app_mod, iid = _ui_env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        _login(c, "adm")
        today = datetime.date.today().isoformat()
        r = c.post(
            f"/incidents/{iid}/log",
            data={"minutes": "45", "worked_date": today, "note": "тест"},
        )
        assert r.status_code == 302
        rows = app_mod.worklogs.records()
        assert len(rows) == 1
        assert rows[0]["Minutes"] == "45"
        assert rows[0]["UserName"] == "adm"
        html = c.get(f"/incident/{iid}").get_data(as_text=True)
        assert "Вкупно: 45 мин" in html
    finally:
        _wipe_users()


def test_worklog_invalid_rejected(monkeypatch):
    from services import ratelimit as rl

    rl.reset()
    app_mod, iid = _ui_env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        _login(c, "adm")
        today = datetime.date.today().isoformat()
        future = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
        c.post(f"/incidents/{iid}/log", data={"minutes": "0", "worked_date": today})
        c.post(f"/incidents/{iid}/log", data={"minutes": "30", "worked_date": future})
        c.post(
            f"/incidents/{iid}/log",
            data={"minutes": "30", "worked_date": "не-датум"},
        )
        assert app_mod.worklogs.records() == []
    finally:
        _wipe_users()


def test_comment_mention_notifies(monkeypatch):
    from services import ratelimit as rl

    rl.reset()
    app_mod, iid = _ui_env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        _login(c, "ana")
        r = c.post(
            "/incidents/comment",
            data={"incident_id": iid, "body": "@bob види го ова"},
        )
        assert r.status_code == 302
        rows = app_mod.notifications.records()
        mentions = [n for n in rows if n.get("Kind") == "mention"]
        assert len(mentions) == 1
        assert mentions[0]["UserName"] == "bob"
        assert mentions[0]["RefID"] == iid
    finally:
        _wipe_users()


def test_transition_notifies_watchers(monkeypatch):
    from services import ratelimit as rl

    rl.reset()
    app_mod, iid = _ui_env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        _login(c, "adm")
        c.post(f"/incidents/{iid}/watch")
        r = c.post(
            "/incidents/transition",
            data={"incident_id": iid, "to_status": "in-progress"},
        )
        assert r.status_code == 302
        rows = app_mod.notifications.records()
        assert any(
            n.get("Kind") == "incident"
            and n.get("UserName") == "adm"
            and n.get("RefID") == iid
            for n in rows
        )
    finally:
        _wipe_users()


def test_fixversion_set_and_invalid(monkeypatch):
    from services import ratelimit as rl

    rl.reset()
    app_mod, iid = _ui_env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        _login(c, "adm")
        app_mod.versions.append_row(
            {"VersionID": "V-000001", "ProjectID": "", "Name": "v1.0"}
        )
        r = c.post(f"/incidents/{iid}/fixversion", data={"fix_version": "V-000001"})
        assert r.status_code == 302
        assert app_mod.incidents.find("IncidentID", iid)["FixVersion"] == "V-000001"
        r = c.post(f"/incidents/{iid}/fixversion", data={"fix_version": "V-999999"})
        assert r.status_code == 302
        assert app_mod.incidents.find("IncidentID", iid)["FixVersion"] == "V-000001"
        r = c.post(f"/incidents/{iid}/fixversion", data={"fix_version": ""})
        assert r.status_code == 302
        assert app_mod.incidents.find("IncidentID", iid)["FixVersion"] == ""
    finally:
        _wipe_users()


def test_epic_workflow_and_default_type():
    from services.project_service import DEFAULT_TYPES, workflow_columns

    assert workflow_columns("epic") == ("Backlog", "In Progress", "Done")
    assert ("Epic", "epic") in DEFAULT_TYPES
