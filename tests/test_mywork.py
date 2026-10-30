"""F1: my-work aggregator (read-only)."""

import os
import sys
import tempfile
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _inc(iid, assignee, status, due):
    return {
        "IncidentID": iid,
        "Assignee": assignee,
        "Status": status,
        "DueDate": due,
        "Title": "t",
    }


def test_empty_everything_zero():
    from services.mywork_service import collect

    out = collect("mag", [], [], [])
    assert out == {
        "my_open": [],
        "breached": [],
        "due_soon": [],
        "my_devices": [],
        "pending_receives": [],
    }


def test_breach_and_due_soon_split():
    from services.mywork_service import collect

    today = date.today()
    past = (today - timedelta(days=1)).isoformat()
    soon = (today + timedelta(days=1)).isoformat()
    incs = [
        _inc("I-1", "mag", "open", past),
        _inc("I-2", "mag", "in-progress", soon),
        _inc("I-3", "drug", "open", past),
        _inc("I-4", "mag", "resolved", past),
    ]
    out = collect("mag", incs, [], [], today=today.isoformat())
    assert {i["IncidentID"] for i in out["my_open"]} == {"I-1", "I-2"}
    assert [i["IncidentID"] for i in out["breached"]] == ["I-1"]
    assert [i["IncidentID"] for i in out["due_soon"]] == ["I-2"]


def test_devices_and_transit():
    from services.mywork_service import collect

    devs = [
        {"AssetID": "A1", "Status": "Assigned"},
        {"AssetID": "A2", "Status": "InTransit"},
    ]
    hist = [
        {"Action": "ASSIGN", "AssetID": "A1", "PerformedBy": "mag"},
        {"Action": "ASSIGN", "AssetID": "AX", "PerformedBy": "drug"},
    ]
    out = collect("mag", [], devs, hist)
    assert [d["AssetID"] for d in out["my_devices"]] == ["A1"]
    assert [d["AssetID"] for d in out["pending_receives"]] == ["A2"]


def test_mywork_page_renders(monkeypatch):
    from services import ratelimit as rl

    rl.reset()
    import app as app_mod
    from services.db_service import DbStore
    from services.schemas import DEV_COLS, INCIDENT_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "mw.db")
    inc_store = DbStore(db, "incidents", INCIDENT_COLS)
    inc_store.append_row(
        {"IncidentID": "I-000001", "Status": "open", "Assignee": "mag", "Title": "t"}
    )
    dev_store = DbStore(db, "devices", DEV_COLS)
    dev_store.append_row({"AssetID": "AST001", "Status": "InTransit"})
    monkeypatch.setattr(app_mod, "incidents", inc_store)
    monkeypatch.setattr(app_mod, "devices", dev_store)
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)
    app_mod.auth_svc.create_user("mag", "dolgapass123", role="magacioner")
    try:
        c = app_mod.app.test_client()
        c.post("/login", data={"username": "mag", "password": "dolgapass123"})
        r = c.get("/my-work")
        assert r.status_code == 200
        body = r.get_data(as_text=True)
        assert "Моја работа" in body
        assert "I-000001" in body
    finally:
        import sqlite3

        con = sqlite3.connect(app_mod.DB_PATH)
        con.execute("DELETE FROM users")
        con.commit()
        con.close()
