"""Phase V.2: custom device fields (TDD). Definitions + values on isolated stores."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _fields_env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.history_service import HistoryService, HISTORY_COLS
    from services.schemas import (
        DEV_COLS,
        EMP_COLS,
        FIELD_DEF_COLS,
        FIELD_VAL_COLS,
    )

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "f2.db")
    monkeypatch.setattr(
        app_mod, "field_defs", DbStore(db, "field_defs", FIELD_DEF_COLS)
    )
    monkeypatch.setattr(
        app_mod, "field_values", DbStore(db, "field_values", FIELD_VAL_COLS)
    )
    monkeypatch.setattr(app_mod, "devices", DbStore(db, "devices", DEV_COLS))
    monkeypatch.setattr(app_mod, "employees", DbStore(db, "employees", EMP_COLS))
    monkeypatch.setattr(
        app_mod, "history", HistoryService(DbStore(db, "history", HISTORY_COLS))
    )
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)
    dev = {c: "" for c in DEV_COLS}
    dev.update({"AssetID": "CF01", "Type": "Laptop", "Status": "Available"})
    app_mod.devices.append_row(dev)
    return app_mod


def test_add_field_definition(monkeypatch):
    app_mod = _fields_env(monkeypatch)
    r = app_mod.app.test_client().post(
        "/fields", data={"action": "add", "FieldName": "IMEI"}
    )
    assert r.status_code == 302
    defs = app_mod.field_defs.records()
    assert len(defs) == 1 and defs[0]["FieldName"] == "IMEI"


def test_duplicate_field_rejected(monkeypatch):
    app_mod = _fields_env(monkeypatch)
    c = app_mod.app.test_client()
    c.post("/fields", data={"action": "add", "FieldName": "IMEI"})
    c.post("/fields", data={"action": "add", "FieldName": "IMEI"})
    assert len(app_mod.field_defs.records()) == 1


def test_set_and_show_value(monkeypatch):
    app_mod = _fields_env(monkeypatch)
    c = app_mod.app.test_client()
    c.post("/fields", data={"action": "add", "FieldName": "IMEI"})
    fid = app_mod.field_defs.records()[0]["FieldID"]
    r = c.post("/device/CF01/fields", data={f"field_{fid}": "356938035643809"})
    assert r.status_code == 302
    html = c.get("/device/CF01").get_data(as_text=True)
    assert "IMEI" in html and "356938035643809" in html


def test_delete_definition_removes_values(monkeypatch):
    app_mod = _fields_env(monkeypatch)
    c = app_mod.app.test_client()
    c.post("/fields", data={"action": "add", "FieldName": "MAC"})
    fid = app_mod.field_defs.records()[0]["FieldID"]
    c.post("/device/CF01/fields", data={f"field_{fid}": "AA:BB"})
    c.post("/fields", data={"action": "delete", "field_id": fid})
    assert app_mod.field_defs.records() == []
    assert app_mod.field_values.records() == []
