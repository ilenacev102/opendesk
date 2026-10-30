"""Brz vnes 3: bulk serials (textarea -> N devices, one POST)."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _bulk_env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService
    from services.schemas import DEV_COLS, EMP_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "b.db")
    monkeypatch.setattr(app_mod, "devices", DbStore(db, "devices", DEV_COLS))
    monkeypatch.setattr(app_mod, "employees", DbStore(db, "employees", EMP_COLS))
    monkeypatch.setattr(
        app_mod, "history", HistoryService(DbStore(db, "history", HISTORY_COLS))
    )
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)
    row = {c: "" for c in DEV_COLS}
    row.update({"AssetID": "DUP-OLD", "SerialNumber": "SN-DUP", "Status": "Available"})
    app_mod.devices.append_row(row)
    return app_mod


def _post(client, serials, **extra):
    data = {
        "Type": "Монитор",
        "Manufacturer": "Dell",
        "Model": "P2422H",
        "Location": "Магацин",
        "serials": serials,
    }
    data.update(extra)
    return client.post("/devices/bulk", data=data)


def test_bulk_creates_many(monkeypatch):
    app_mod = _bulk_env(monkeypatch)
    r = _post(app_mod.app.test_client(), "SN-001\nSN-002\nSN-003")
    assert r.status_code == 302
    assert app_mod.devices.find("SerialNumber", "SN-001") is not None
    assert app_mod.devices.find("SerialNumber", "SN-002") is not None
    assert app_mod.devices.find("SerialNumber", "SN-003") is not None


def test_bulk_skips_duplicates_and_blanks(monkeypatch):
    app_mod = _bulk_env(monkeypatch)
    r = _post(app_mod.app.test_client(), "SN-NEW\nSN-DUP\n\n   \nSN-NEW")
    assert r.status_code == 302
    assert app_mod.devices.find("SerialNumber", "SN-NEW") is not None
    assert len(app_mod.devices.filter_eq("SerialNumber", "SN-DUP")) == 1
    assert len(app_mod.devices.filter_eq("SerialNumber", "SN-NEW")) == 1


def test_bulk_form_renders(monkeypatch):
    app_mod = _bulk_env(monkeypatch)
    r = app_mod.app.test_client().get("/devices/bulk")
    assert r.status_code == 200
    assert "serials" in r.get_data(as_text=True)
