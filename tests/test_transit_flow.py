"""MS-4: custody transfers ship -> receive (transactional)."""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.validators import ValidationError


def _svc(asset_status="Available", emp=""):
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService
    from services.schemas import DEV_COLS
    from services.transit_service import TransitService

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "tr_flow.db")
    devices = DbStore(db, "devices", DEV_COLS)
    devices.append_row(
        {
            "AssetID": "AST001",
            "SerialNumber": "S1",
            "Manufacturer": "Dell",
            "Status": asset_status,
            "EmployeeID": emp,
            "Location": "Скопје",
        }
    )
    history = HistoryService(DbStore(db, "history", HISTORY_COLS))
    return TransitService(devices, history, db_path=db), devices, history


def test_ship_then_receive_grows_history_by_two():
    svc, devices, history = _svc()
    before = len(history.store.records())
    svc.ship("AST001", "Битола", by="mag")
    shipped = devices.find("AssetID", "AST001")
    assert shipped is not None
    assert shipped["Status"] == "InTransit"
    assert shipped["Location"] == "Битола"
    svc.receive("AST001", by="mag")
    received = devices.find("AssetID", "AST001")
    assert received is not None
    assert received["Status"] == "Available"
    assert len(history.store.records()) == before + 2


def test_receive_without_ship_rejected():
    svc, devices, history = _svc()
    with pytest.raises(ValidationError):
        svc.receive("AST001", by="mag")


def test_ship_forbidden_status_rejected():
    svc, devices, history = _svc(asset_status="Disposed")
    with pytest.raises(ValidationError):
        svc.ship("AST001", "Битола", by="mag")


def _ui_env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService
    from services.schemas import DEV_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "tr_flow_ui.db")
    dev_store = DbStore(db, "devices", DEV_COLS)
    dev_store.append_row(
        {"AssetID": "AST001", "Status": "Available", "Location": "Скопје"}
    )
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


def test_transit_routes_mag_ok_citac_forbidden(monkeypatch):
    from services import ratelimit as rl

    rl.reset()
    app_mod = _ui_env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        c.post("/login", data={"username": "cit", "password": "dolgapass123"})
        assert (
            c.post(
                "/transit/ship", data={"asset_id": "AST001", "to_loc": "Битола"}
            ).status_code
            == 403
        )
        c.post("/login", data={"username": "mag", "password": "dolgapass123"})
        assert (
            c.post(
                "/transit/ship", data={"asset_id": "AST001", "to_loc": "Битола"}
            ).status_code
            == 302
        )
        shipped = app_mod.devices.find("AssetID", "AST001")
        assert shipped is not None
        assert shipped["Status"] == "InTransit"
        assert (
            c.post("/transit/receive", data={"asset_id": "AST001"}).status_code == 302
        )
        received = app_mod.devices.find("AssetID", "AST001")
        assert received is not None
        assert received["Status"] == "Available"
    finally:
        _wipe_users()
