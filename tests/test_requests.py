"""Phase G.3: simple requests intake (TDD). File + approve/reject."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _requests_env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService
    from services.schemas import DEV_COLS, EMP_COLS, REQUEST_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "q.db")
    monkeypatch.setattr(app_mod, "requests", DbStore(db, "requests", REQUEST_COLS))
    monkeypatch.setattr(app_mod, "devices", DbStore(db, "devices", DEV_COLS))
    monkeypatch.setattr(app_mod, "employees", DbStore(db, "employees", EMP_COLS))
    monkeypatch.setattr(
        app_mod, "history", HistoryService(DbStore(db, "history", HISTORY_COLS))
    )
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)
    return app_mod


def test_file_request(monkeypatch):
    app_mod = _requests_env(monkeypatch)
    r = app_mod.app.test_client().post(
        "/requests",
        data={
            "action": "file",
            "EmployeeID": "E001",
            "NeedText": "Ми треба лаптоп за нов колега",
        },
    )
    assert r.status_code == 302
    rows = app_mod.requests.records()
    assert len(rows) == 1
    assert rows[0]["Status"] == "open"
    assert "лаптоп" in rows[0]["NeedText"]


def test_file_empty_rejected(monkeypatch):
    app_mod = _requests_env(monkeypatch)
    r = app_mod.app.test_client().post(
        "/requests",
        data={"action": "file", "EmployeeID": "E001", "NeedText": "  "},
    )
    assert r.status_code == 302
    assert app_mod.requests.records() == []


def test_approve_and_reject(monkeypatch):
    app_mod = _requests_env(monkeypatch)
    c = app_mod.app.test_client()
    c.post(
        "/requests",
        data={"action": "file", "EmployeeID": "E1", "NeedText": "монитор"},
    )
    c.post(
        "/requests",
        data={"action": "file", "EmployeeID": "E2", "NeedText": "тастатура"},
    )
    ids = [r["RequestID"] for r in app_mod.requests.records()]
    assert (
        c.post(
            "/requests/decide",
            data={"request_id": ids[0], "decision": "approved"},
        ).status_code
        == 302
    )
    assert (
        c.post(
            "/requests/decide",
            data={"request_id": ids[1], "decision": "rejected"},
        ).status_code
        == 302
    )
    assert app_mod.requests.find("RequestID", ids[0])["Status"] == "approved"
    assert app_mod.requests.find("RequestID", ids[1])["Status"] == "rejected"
    html = c.get("/requests").get_data(as_text=True)
    assert "монитор" in html and "тастатура" in html
