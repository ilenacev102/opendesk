"""Phase G.2: reservations (TDD). Overlap protection on isolated stores."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _reserv_env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService
    from services.schemas import DEV_COLS, EMP_COLS, RESERV_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "r.db")
    monkeypatch.setattr(
        app_mod, "reservations", DbStore(db, "reservations", RESERV_COLS)
    )
    monkeypatch.setattr(app_mod, "devices", DbStore(db, "devices", DEV_COLS))
    monkeypatch.setattr(app_mod, "employees", DbStore(db, "employees", EMP_COLS))
    monkeypatch.setattr(
        app_mod, "history", HistoryService(DbStore(db, "history", HISTORY_COLS))
    )
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)
    dev = {c: "" for c in DEV_COLS}
    dev.update({"AssetID": "RES01", "Type": "Laptop", "Status": "Available"})
    app_mod.devices.append_row(dev)
    return app_mod


def test_add_reservation(monkeypatch):
    app_mod = _reserv_env(monkeypatch)
    r = app_mod.app.test_client().post(
        "/reservations",
        data={
            "action": "add",
            "AssetID": "RES01",
            "EmployeeID": "E001",
            "FromDate": "2026-10-01",
            "ToDate": "2026-10-05",
        },
    )
    assert r.status_code == 302
    rows = app_mod.reservations.records()
    assert len(rows) == 1 and rows[0]["Status"] == "active"


def test_overlap_rejected(monkeypatch):
    app_mod = _reserv_env(monkeypatch)
    c = app_mod.app.test_client()
    base = {
        "action": "add",
        "AssetID": "RES01",
        "EmployeeID": "E001",
        "FromDate": "2026-10-01",
        "ToDate": "2026-10-05",
    }
    c.post("/reservations", data=base)
    overlap = dict(base)
    overlap.update({"FromDate": "2026-10-04", "ToDate": "2026-10-08"})
    c.post("/reservations", data=overlap)
    assert len(app_mod.reservations.records()) == 1
    adjacent = dict(base)
    adjacent.update({"FromDate": "2026-10-06", "ToDate": "2026-10-08"})
    c.post("/reservations", data=adjacent)
    assert len(app_mod.reservations.records()) == 2


def test_bad_dates_rejected(monkeypatch):
    app_mod = _reserv_env(monkeypatch)
    r = app_mod.app.test_client().post(
        "/reservations",
        data={
            "action": "add",
            "AssetID": "RES01",
            "EmployeeID": "E001",
            "FromDate": "2026-10-10",
            "ToDate": "2026-10-05",
        },
    )
    assert r.status_code == 302
    assert app_mod.reservations.records() == []


def test_cancel_reservation(monkeypatch):
    app_mod = _reserv_env(monkeypatch)
    c = app_mod.app.test_client()
    c.post(
        "/reservations",
        data={
            "action": "add",
            "AssetID": "RES01",
            "EmployeeID": "E001",
            "FromDate": "2026-11-01",
            "ToDate": "2026-11-03",
        },
    )
    rid = app_mod.reservations.records()[0]["ReservationID"]
    r = c.post("/reservations/cancel", data={"reservation_id": rid})
    assert r.status_code == 302
    assert app_mod.reservations.find("ReservationID", rid)["Status"] == "cancelled"
