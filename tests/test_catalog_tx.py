"""P1.2: catalog mutations are atomic and audited."""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService
    from services.schemas import (
        CONS_COLS,
        CONTRACT_COLS,
        DEV_COLS,
        EMP_COLS,
        FIELD_DEF_COLS,
        FIELD_VAL_COLS,
        LIC_COLS,
        LIC_SEAT_COLS,
        REQUEST_COLS,
        RESERV_COLS,
    )

    db = os.path.join(tempfile.mkdtemp(), "cat.db")
    for name, table, cols in (
        ("consumables", "consumables", CONS_COLS),
        ("licenses", "licenses", LIC_COLS),
        ("license_seats", "license_seats", LIC_SEAT_COLS),
        ("contracts", "contracts", CONTRACT_COLS),
        ("field_defs", "field_defs", FIELD_DEF_COLS),
        ("field_values", "field_values", FIELD_VAL_COLS),
        ("requests", "requests", REQUEST_COLS),
        ("reservations", "reservations", RESERV_COLS),
        ("devices", "devices", DEV_COLS),
        ("employees", "employees", EMP_COLS),
    ):
        monkeypatch.setattr(app_mod, name, DbStore(db, table, cols))
    monkeypatch.setattr(
        app_mod, "history", HistoryService(DbStore(db, "history", HISTORY_COLS))
    )
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)
    return app_mod


def _boom(*args, **kwargs):
    raise RuntimeError("boom")


def _actions(app_mod):
    return [r["Action"] for r in app_mod.history.store.records()]


def test_seat_assign_rolls_back_when_seat_row_fails(monkeypatch):
    app_mod = _env(monkeypatch)
    app_mod.licenses.append_row(
        {"LicenseID": "L1", "Software": "IDE", "Seats": "3", "SeatsUsed": "0"}
    )
    app_mod.license_seats.append_row = _boom

    from routes.catalog import _license_seat_change

    with pytest.raises(RuntimeError):
        _license_seat_change("L1", 1, "E1", "LIC_ASSIGN")

    assert app_mod.licenses.find("LicenseID", "L1")["SeatsUsed"] == "0"
    assert app_mod.license_seats.records() == []
    assert app_mod.history.store.records() == []


def test_seat_revoke_rolls_back_when_delete_fails(monkeypatch):
    app_mod = _env(monkeypatch)
    app_mod.licenses.append_row(
        {"LicenseID": "L1", "Software": "IDE", "Seats": "2", "SeatsUsed": "1"}
    )
    app_mod.license_seats.append_row(
        {"SeatID": "SEAT000001", "LicenseID": "L1", "AssignedToID": "E1"}
    )
    app_mod.license_seats.delete_where = _boom

    from routes.catalog import _license_seat_change

    with pytest.raises(RuntimeError):
        _license_seat_change("L1", -1, "E1", "LIC_REVOKE")

    assert app_mod.licenses.find("LicenseID", "L1")["SeatsUsed"] == "1"
    assert len(app_mod.license_seats.records()) == 1


def test_consumable_issue_rolls_back_when_history_fails(monkeypatch):
    app_mod = _env(monkeypatch)
    app_mod.consumables.append_row(
        {"ConsumableID": "C1", "Name": "Кабел", "Quantity": "10", "MinLevel": "2"}
    )
    app_mod.history.log = _boom

    r = app_mod.app.test_client().post(
        "/consumables/issue", data={"consumable_id": "C1", "qty": "4"}
    )

    assert r.status_code == 500
    assert app_mod.consumables.find("ConsumableID", "C1")["Quantity"] == "10"


def test_request_decision_is_atomic_and_audited(monkeypatch):
    app_mod = _env(monkeypatch)
    c = app_mod.app.test_client()
    c.post(
        "/requests",
        data={"action": "file", "EmployeeID": "E1", "NeedText": "монитор"},
    )
    qid = app_mod.requests.records()[0]["RequestID"]

    assert (
        c.post(
            "/requests/decide",
            data={"request_id": qid, "decision": "approved"},
        ).status_code
        == 302
    )
    assert app_mod.requests.find("RequestID", qid)["Status"] == "approved"
    assert "REQ_DECIDE" in _actions(app_mod)

    app_mod.history.log = _boom
    assert (
        c.post(
            "/requests/decide",
            data={"request_id": qid, "decision": "rejected"},
        ).status_code
        == 500
    )
    assert app_mod.requests.find("RequestID", qid)["Status"] == "approved"


def test_reservation_cancel_is_atomic_and_audited(monkeypatch):
    app_mod = _env(monkeypatch)
    app_mod.devices.append_row(
        {"AssetID": "D1", "Type": "Laptop", "Status": "Available"}
    )
    c = app_mod.app.test_client()
    c.post(
        "/reservations",
        data={
            "AssetID": "D1",
            "FromDate": "2026-12-01",
            "ToDate": "2026-12-03",
        },
    )
    rid = app_mod.reservations.records()[0]["ReservationID"]

    assert (
        c.post("/reservations/cancel", data={"reservation_id": rid}).status_code == 302
    )
    assert app_mod.reservations.find("ReservationID", rid)["Status"] == "cancelled"
    assert "RES_CANCEL" in _actions(app_mod)


def test_device_fields_save_does_not_rewrite_the_whole_table(monkeypatch):
    app_mod = _env(monkeypatch)
    for aid in ("CF01", "CF02"):
        app_mod.devices.append_row(
            {"AssetID": aid, "Type": "Laptop", "Status": "Available"}
        )
    app_mod.field_defs.append_row({"FieldID": "F1", "FieldName": "Боја"})
    app_mod.field_values.replace_all = _boom

    c = app_mod.app.test_client()
    assert c.post("/device/CF01/fields", data={"field_F1": "црна"}).status_code == 302
    assert c.post("/device/CF02/fields", data={"field_F1": "бела"}).status_code == 302

    values = {(v["AssetID"], v["Value"]) for v in app_mod.field_values.records()}
    assert values == {("CF01", "црна"), ("CF02", "бела")}


def test_field_create_and_delete_are_audited(monkeypatch):
    app_mod = _env(monkeypatch)
    c = app_mod.app.test_client()
    c.post("/fields", data={"action": "add", "FieldName": "Боја"})
    fid = app_mod.field_defs.records()[0]["FieldID"]
    app_mod.field_values.append_row(
        {"AssetID": "CF01", "FieldID": fid, "Value": "црна"}
    )

    c.post("/fields", data={"action": "delete", "field_id": fid})

    assert app_mod.field_defs.records() == []
    assert app_mod.field_values.records() == []
    assert _actions(app_mod) == ["FIELD_CREATE", "FIELD_DELETE"]


def test_create_flows_are_audited(monkeypatch):
    app_mod = _env(monkeypatch)
    app_mod.devices.append_row(
        {"AssetID": "D1", "Type": "Laptop", "Status": "Available"}
    )
    c = app_mod.app.test_client()
    c.post("/consumables", data={"ConsumableID": "C1", "Name": "Кабел"})
    c.post("/licenses", data={"LicenseID": "L1", "Software": "IDE", "Seats": "1"})
    c.post("/contracts", data={"ContractID": "K1", "Title": "Договор"})
    c.post("/requests", data={"action": "file", "NeedText": "монитор"})
    c.post(
        "/reservations",
        data={"AssetID": "D1", "FromDate": "2026-12-01", "ToDate": "2026-12-02"},
    )

    actions = set(_actions(app_mod))
    assert {
        "CONSUMABLE_CREATE",
        "LICENSE_CREATE",
        "CONTRACT_CREATE",
        "REQ_CREATE",
        "RES_CREATE",
    } <= actions
