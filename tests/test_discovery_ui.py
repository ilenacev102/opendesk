"""Enterprise Wave1 todo 3: discovery import UI preview + confirm (tests-after)."""

import io
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DISC_CSV = (
    "Hostname,SerialNumber,Manufacturer,Model,OS,LastSeen,Source\n"
    "PC-01,NEW001,Dell,Latitude 5440,Win11,2026-09-01,Intune\n"
    "PC-02,MAT001,Lenovo,T14,Win11,2026-09-02,Intune\n"
    "PC-03,CON001,Dell,XPS,Win11,2026-09-02,Intune\n"
)


def _ui_env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService
    from services.schemas import DEV_COLS, EMP_COLS, STAGING_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "disc_ui.db")
    monkeypatch.setattr(app_mod, "devices", DbStore(db, "devices", DEV_COLS))
    monkeypatch.setattr(app_mod, "employees", DbStore(db, "employees", EMP_COLS))
    monkeypatch.setattr(
        app_mod, "history", HistoryService(DbStore(db, "history", HISTORY_COLS))
    )
    monkeypatch.setattr(app_mod, "staging", DbStore(db, "staging", STAGING_COLS))
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)
    # one matchable device + one assigned device (conflict)
    app_mod.devices.append_row(
        {
            "AssetID": "AST001",
            "SerialNumber": "MAT001",
            "Manufacturer": "Lenovo",
            "Model": "T14",
            "Status": "Available",
            "EmployeeID": "",
        }
    )
    app_mod.devices.append_row(
        {
            "AssetID": "AST002",
            "SerialNumber": "CON001",
            "Manufacturer": "Dell",
            "Model": "XPS",
            "Status": "Assigned",
            "EmployeeID": "E001",
        }
    )
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


def _upload(client, payload, filename="disc.csv"):
    return client.post(
        "/import",
        data={"kind": "discovery", "file": (io.BytesIO(payload), filename)},
    )


def test_import_get_renders_discovery_option(monkeypatch):
    app_mod = _ui_env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        _login(c, "mag")
        r = c.get("/import")
        assert r.status_code == 200
        html = r.get_data(as_text=True)
        assert 'value="discovery"' in html
        assert "nonce=" in html  # CSP nonce present via base template
    finally:
        _wipe_users()


def test_preview_shows_counts_and_writes_nothing(monkeypatch):
    app_mod = _ui_env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        _login(c, "mag")
        before = len(app_mod.devices.records())
        r = _upload(c, DISC_CSV.encode("utf-8"))
        assert r.status_code == 200
        html = r.get_data(as_text=True)
        assert "Преглед" in html
        assert "нови: 1" in html and "совпаѓања: 1" in html
        assert "конфликти: 1" in html
        assert "NEW001" in html and "MAT001" in html and "CON001" in html
        assert len(app_mod.devices.records()) == before  # dry-run: zero writes
    finally:
        _wipe_users()


def test_confirm_writes_new_and_match_only(monkeypatch):
    app_mod = _ui_env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        _login(c, "mag")
        r = _upload(c, DISC_CSV.encode("utf-8"))
        html = r.get_data(as_text=True)
        import html as _html
        import re

        m = re.search(r'name="rows" value="([^"]+)"', html)
        assert m, "preview must carry rows payload for confirm"
        rows = json.loads(_html.unescape(m.group(1)))
        assert len(rows) == 3
        r2 = c.post(
            "/import",
            data={"kind": "discovery", "confirm": "1", "rows": json.dumps(rows)},
        )
        assert r2.status_code == 200
        assert app_mod.devices.find("SerialNumber", "NEW001") is not None
        matched = app_mod.devices.find("SerialNumber", "MAT001")
        assert matched is not None
        assert "2026-09-02" in matched.get("Notes", "")
        assigned = app_mod.devices.find("SerialNumber", "CON001")
        assert assigned is not None
        assert assigned.get("AssetID") == "AST002"  # untouched
        assert "Внесени" in r2.get_data(as_text=True)
    finally:
        _wipe_users()


def test_citac_post_blocked(monkeypatch):
    app_mod = _ui_env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        _login(c, "cit")
        r = _upload(c, DISC_CSV.encode("utf-8"))
        assert r.status_code == 403
        assert len(app_mod.devices.records()) == 2
    finally:
        _wipe_users()


def test_xlsx_rejected_with_zero_writes(monkeypatch):
    app_mod = _ui_env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        _login(c, "mag")
        before = len(app_mod.devices.records())
        r = _upload(c, DISC_CSV.encode("utf-8"), filename="disc.xlsx")
        assert r.status_code == 200
        assert "само .csv" in r.get_data(as_text=True)
        assert len(app_mod.devices.records()) == before
    finally:
        _wipe_users()
