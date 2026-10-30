"""MS-2: overdue threshold + idempotent escalation."""

import os
import sys
import tempfile
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _ago(n):
    return (date.today() - timedelta(days=n)).isoformat() + " 10:00"


def test_under_threshold_not_overdue():
    from services.offboarding_service import overdue

    devs = [{"AssetID": "AST001", "EmployeeID": "EMP009"}]
    assert overdue(devs, {"AST001": _ago(3)}, 7, date.today().isoformat()) == []


def test_over_threshold_overdue():
    from services.offboarding_service import overdue

    devs = [{"AssetID": "AST001", "EmployeeID": "EMP009"}]
    out = overdue(devs, {"AST001": _ago(10)}, 7, date.today().isoformat())
    assert [d["AssetID"] for d in out] == ["AST001"]


def _history():
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService

    tmp = tempfile.mkdtemp()
    return HistoryService(
        DbStore(os.path.join(tmp, "off2.db"), "history", HISTORY_COLS)
    )


def test_double_escalation_writes_once():
    from services.offboarding_service import OFF_ESC_ACTION, escalate

    h = _history()
    first = escalate(h, "AST001", performed_by="mag")
    second = escalate(h, "AST001", performed_by="mag")
    assert first == {"escalated": True, "asset_id": "AST001"}
    assert second == {"escalated": False, "asset_id": "AST001"}
    rows = [r for r in h.store.records() if r.get("Action") == OFF_ESC_ACTION]
    assert len(rows) == 1


def _ui_env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService
    from services.schemas import DEV_COLS, EMP_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "off2_ui.db")
    emp_store = DbStore(db, "employees", EMP_COLS)
    dev_store = DbStore(db, "devices", DEV_COLS)
    emp_store.append_row(
        {"EmployeeID": "EMP009", "FirstName": "Заминат", "Active": "NO"}
    )
    dev_store.append_row(
        {"AssetID": "AST001", "EmployeeID": "EMP009", "Status": "Assigned"}
    )
    monkeypatch.setattr(app_mod, "employees", emp_store)
    monkeypatch.setattr(app_mod, "devices", dev_store)
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


def test_escalate_route_mag_ok_citac_forbidden(monkeypatch):
    from services import ratelimit as rl
    from services.offboarding_service import OFF_ESC_ACTION

    rl.reset()
    app_mod = _ui_env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        c.post("/login", data={"username": "cit", "password": "dolgapass123"})
        assert (
            c.post("/offboarding/escalate", data={"asset_id": "AST001"}).status_code
            == 403
        )
        c.post("/login", data={"username": "mag", "password": "dolgapass123"})
        r = c.post("/offboarding/escalate", data={"asset_id": "AST001"})
        assert r.status_code == 302
        rows = [
            x
            for x in app_mod.history.store.records()
            if x.get("Action") == OFF_ESC_ACTION and x.get("AssetID") == "AST001"
        ]
        assert len(rows) == 1
    finally:
        _wipe_users()
