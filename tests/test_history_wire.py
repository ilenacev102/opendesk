"""Enterprise Wave1 todo 8: history wiring atomicity + current user (TDD)."""

import io
import json
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DISC_CSV = (
    "Hostname,SerialNumber,Manufacturer,Model,OS,LastSeen,Source\n"
    "PC-01,HIST01,Dell,Latitude,Win11,2026-09-01,Intune\n"
)


def _env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService
    from services.schemas import DEV_COLS, EMP_COLS, INCIDENT_COLS, STAGING_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "hist.db")
    monkeypatch.setattr(app_mod, "devices", DbStore(db, "devices", DEV_COLS))
    monkeypatch.setattr(app_mod, "employees", DbStore(db, "employees", EMP_COLS))
    monkeypatch.setattr(app_mod, "incidents", DbStore(db, "incidents", INCIDENT_COLS))
    monkeypatch.setattr(app_mod, "staging", DbStore(db, "staging", STAGING_COLS))
    monkeypatch.setattr(
        app_mod, "history", HistoryService(DbStore(db, "history", HISTORY_COLS))
    )
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)
    app_mod.auth_svc.create_user("mag", "dolgapass123", role="magacioner")
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


def test_discovery_confirm_logs_summary_with_user(monkeypatch):
    app_mod = _env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        _login(c, "mag")
        r = c.post(
            "/import",
            data={
                "kind": "discovery",
                "file": (io.BytesIO(DISC_CSV.encode()), "d.csv"),
            },
        )
        m = re.search(r'name="rows" value="([^"]+)"', r.get_data(as_text=True))
        assert m
        import html as _html

        rows = json.loads(_html.unescape(m.group(1)))
        c.post(
            "/import",
            data={"kind": "discovery", "confirm": "1", "rows": json.dumps(rows)},
        )
        summaries = [
            h
            for h in app_mod.history.store.records()
            if h.get("Action") == "DISCOVERY_IMPORT"
        ]
        assert len(summaries) == 1
        assert "new=1" in summaries[0].get("Reason", "")
        assert summaries[0].get("PerformedBy") == "mag"
    finally:
        _wipe_users()


def test_incident_create_logs_user(monkeypatch):
    app_mod = _env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        _login(c, "mag")
        c.post("/incidents/new", data={"AssetID": "AST001", "Title": "Тест"})
        creates = [
            h
            for h in app_mod.history.store.records()
            if h.get("Action") == "INC_CREATE"
        ]
        assert len(creates) == 1
        assert creates[0].get("PerformedBy") == "mag"
    finally:
        _wipe_users()


def test_rolled_back_confirm_writes_no_history(monkeypatch):
    app_mod = _env(monkeypatch)
    try:

        def flaky(row, con=None):
            raise OSError("simulated disk failure")

        monkeypatch.setattr(app_mod.devices, "append_row", flaky)
        c = app_mod.app.test_client()
        _login(c, "mag")
        r = c.post(
            "/import",
            data={
                "kind": "discovery",
                "file": (io.BytesIO(DISC_CSV.encode()), "d.csv"),
            },
        )
        m = re.search(r'name="rows" value="([^"]+)"', r.get_data(as_text=True))
        assert m
        import html as _html

        rows = json.loads(_html.unescape(m.group(1)))
        c.post(
            "/import",
            data={"kind": "discovery", "confirm": "1", "rows": json.dumps(rows)},
        )
        assert app_mod.devices.records() == []
        assert app_mod.history.store.records() == []
        assert app_mod.staging.records() == []
    finally:
        _wipe_users()
