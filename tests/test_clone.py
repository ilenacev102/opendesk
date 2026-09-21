"""Brz vnes 2: duplicate device (?clone) prefills the new-device form."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _clone_env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.history_service import HistoryService, HISTORY_COLS
    from services.schemas import DEV_COLS, EMP_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "cl.db")
    monkeypatch.setattr(app_mod, "devices", DbStore(db, "devices", DEV_COLS))
    monkeypatch.setattr(app_mod, "employees", DbStore(db, "employees", EMP_COLS))
    monkeypatch.setattr(
        app_mod, "history", HistoryService(DbStore(db, "history", HISTORY_COLS))
    )
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)
    row = {c: "" for c in DEV_COLS}
    row.update(
        {
            "AssetID": "SRC01",
            "Type": "Монитор",
            "Manufacturer": "Dell",
            "Model": "P2422H",
            "SerialNumber": "SN-SRC",
            "Status": "Available",
            "Location": "Магацин",
            "PurchasePrice": "12000",
        }
    )
    app_mod.devices.append_row(row)
    return app_mod


def test_clone_prefills_form(monkeypatch):
    app_mod = _clone_env(monkeypatch)
    html = (
        app_mod.app.test_client().get("/devices/new?clone=SRC01").get_data(as_text=True)
    )
    assert 'value="Dell"' in html
    assert 'value="P2422H"' in html
    assert 'value="Магацин"' in html
    assert 'value="12000"' in html
    assert 'value="SRC01"' not in html
    assert 'value="SN-SRC"' not in html


def test_clone_missing_id_renders_empty_form(monkeypatch):
    app_mod = _clone_env(monkeypatch)
    r = app_mod.app.test_client().get("/devices/new?clone=NOPE")
    assert r.status_code == 200
    assert 'value="Dell"' not in r.get_data(as_text=True)


def test_device_page_links_clone(monkeypatch):
    app_mod = _clone_env(monkeypatch)
    html = app_mod.app.test_client().get("/device/SRC01").get_data(as_text=True)
    assert "/devices/new?clone=SRC01" in html
