"""Discovery Pro todo 5: Intune preview/confirm UI (tests-after)."""

import io
import json
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

GRAPH_ROWS = [
    {
        "Hostname": "PC-10",
        "SerialNumber": "IN1001",
        "Manufacturer": "Dell",
        "Model": "Latitude",
        "OS": "Windows 11",
        "LastSeen": "2026-09-20",
        "Source": "intune",
    },
    {
        "Hostname": "PC-11",
        "SerialNumber": "IN1002",
        "Manufacturer": "HP",
        "Model": "EliteBook",
        "OS": "Windows 10",
        "LastSeen": "2026-09-20",
        "Source": "intune",
    },
]


def _env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.history_service import HistoryService, HISTORY_COLS
    from services.schemas import DEV_COLS, STAGING_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "intui.db")
    monkeypatch.setattr(app_mod, "devices", DbStore(db, "devices", DEV_COLS))
    monkeypatch.setattr(app_mod, "staging", DbStore(db, "staging", STAGING_COLS))
    monkeypatch.setattr(
        app_mod, "history", HistoryService(DbStore(db, "history", HISTORY_COLS))
    )
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)
    monkeypatch.setenv("SERVICEDESK_INTUNE_TENANT", "t")
    monkeypatch.setenv("SERVICEDESK_INTUNE_CLIENT_ID", "c")
    app_mod.auth_svc.create_user("mag", "dolgapass123", role="magacioner")
    app_mod.auth_svc.create_user("cit", "dolgapass123", role="citac")
    monkeypatch.setattr(
        "services.intune_service.fetch_devices",
        lambda client_factory=None: list(GRAPH_ROWS),
    )
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


def test_intune_option_and_preview(monkeypatch):
    app_mod = _env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        _login(c, "mag")
        assert 'value="intune"' in c.get("/import").get_data(as_text=True)
        r = c.post("/import", data={"kind": "intune"})
        assert r.status_code == 200
        html = r.get_data(as_text=True)
        assert "Преглед" in html
        assert "нови: 2" in html
        assert "IN1001" in html and "IN1002" in html
        assert len(app_mod.devices.records()) == 0  # dry-run
    finally:
        _wipe_users()


def test_intune_confirm_writes(monkeypatch):
    import html as _html

    app_mod = _env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        _login(c, "mag")
        r = c.post("/import", data={"kind": "intune"})
        m = re.search(r'name="rows" value="([^"]+)"', r.get_data(as_text=True))
        assert m
        rows = json.loads(_html.unescape(m.group(1)))
        r2 = c.post(
            "/import", data={"kind": "intune", "confirm": "1", "rows": json.dumps(rows)}
        )
        assert r2.status_code == 200
        assert app_mod.devices.find("SerialNumber", "IN1001") is not None
        assert "Внесени" in r2.get_data(as_text=True)
    finally:
        _wipe_users()


def test_citac_intune_blocked(monkeypatch):
    app_mod = _env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        _login(c, "cit")
        assert c.post("/import", data={"kind": "intune"}).status_code == 403
    finally:
        _wipe_users()
