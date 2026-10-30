"""Enterprise Wave1 todo 6: SLA breach badge + digest wiring (TDD)."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_breached_incidents_helper():
    from services.notify_service import breached_incidents

    rows = [
        {"IncidentID": "I1", "Status": "open", "DueDate": "2020-01-01"},
        {"IncidentID": "I2", "Status": "in-progress", "DueDate": "2020-06-01"},
        {"IncidentID": "I3", "Status": "resolved", "DueDate": "2020-01-01"},
        {"IncidentID": "I4", "Status": "open", "DueDate": ""},
        {"IncidentID": "I5", "Status": "open", "DueDate": "garbage"},
        {"IncidentID": "I6", "Status": "open", "DueDate": "2099-01-01"},
    ]
    out = breached_incidents(rows)
    assert {r["IncidentID"] for r in out} == {"I1", "I2"}


def test_digest_email_includes_breached_section():
    from services import notify_service as notify

    breached = [
        {
            "IncidentID": "I000001",
            "Title": "Скршен екран",
            "Assignee": "mag",
            "DueDate": "2020-01-01",
        },
    ]
    to, subject, body = notify.digest_email("a@x.mk", [], breached)
    assert to == "a@x.mk"
    assert "1" in subject
    assert "I000001" in body and "Скршен екран" in body


def test_digest_email_backward_compatible():
    from services import notify_service as notify

    to, subject, body = notify.digest_email("a@x.mk", [])
    assert to == "a@x.mk"


def _sla_env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService
    from services.schemas import DEV_COLS, EMP_COLS, INCIDENT_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "sla.db")
    monkeypatch.setattr(app_mod, "devices", DbStore(db, "devices", DEV_COLS))
    monkeypatch.setattr(app_mod, "employees", DbStore(db, "employees", EMP_COLS))
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
    svc.create(
        asset_id="AST001",
        title="Стар дефект",
        priority="high",
        assignee="mag",
        due_date="2020-01-01",
        performed_by="admin",
    )
    svc.create(asset_id="AST002", title="Без рок", priority="low", performed_by="admin")
    return app_mod


def _wipe_users():
    import sqlite3

    import app as app_mod

    con = sqlite3.connect(app_mod.DB_PATH)
    con.execute("DELETE FROM users")
    con.commit()
    con.close()


def test_list_shows_breach_badge(monkeypatch):
    app_mod = _sla_env(monkeypatch)
    try:
        html = app_mod.app.test_client().get("/incidents").get_data(as_text=True)
        assert "пробиен рок" in html
        assert html.count("пробиен рок") == 1  # only the overdue one
    finally:
        _wipe_users()


def test_notify_digest_mentions_breached(monkeypatch):
    app_mod = _sla_env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        r = c.post("/notify-digest")
        assert r.status_code == 302
        with c.session_transaction() as sess:
            flashes = sess.get("_flashes", [])
        assert any("пробиен" in msg for _, msg in flashes), flashes
    finally:
        _wipe_users()
