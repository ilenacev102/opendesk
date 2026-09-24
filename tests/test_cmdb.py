"""Enterprise Wave2 todo 14: CMDB minimal links view (tests-after)."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.history_service import HistoryService, HISTORY_COLS
    from services.schemas import (
        CONTRACT_COLS,
        DEV_COLS,
        EMP_COLS,
        INCIDENT_COLS,
        LIC_COLS,
        REQUEST_COLS,
        RESERV_COLS,
    )

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "cmdb.db")
    monkeypatch.setattr(app_mod, "devices", DbStore(db, "devices", DEV_COLS))
    monkeypatch.setattr(app_mod, "employees", DbStore(db, "employees", EMP_COLS))
    monkeypatch.setattr(app_mod, "licenses", DbStore(db, "licenses", LIC_COLS))
    monkeypatch.setattr(app_mod, "contracts", DbStore(db, "contracts", CONTRACT_COLS))
    monkeypatch.setattr(
        app_mod, "reservations", DbStore(db, "reservations", RESERV_COLS)
    )
    monkeypatch.setattr(app_mod, "requests", DbStore(db, "requests", REQUEST_COLS))
    monkeypatch.setattr(app_mod, "incidents", DbStore(db, "incidents", INCIDENT_COLS))
    monkeypatch.setattr(
        app_mod, "history", HistoryService(DbStore(db, "history", HISTORY_COLS))
    )
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)
    app_mod.devices.append_row(
        {
            "AssetID": "AST001",
            "Manufacturer": "Dell",
            "Model": "Latitude",
            "Status": "Assigned",
            "EmployeeID": "E001",
            "Supplier": "SUP1",
        }
    )
    app_mod.devices.append_row(
        {
            "AssetID": "AST999",
            "Manufacturer": "HP",
            "Model": "EliteBook",
            "Status": "Available",
            "EmployeeID": "",
            "Supplier": "",
        }
    )
    app_mod.employees.append_row(
        {
            "EmployeeID": "E001",
            "FirstName": "Петар",
            "LastName": "Петров",
            "UserName": "petar",
            "Department": "IT",
            "Active": "YES",
        }
    )
    app_mod.licenses.append_row(
        {
            "LicenseID": "L1",
            "Software": "Office",
            "Seats": "10",
            "Notes": "покрива AST001 и AST002",
        }
    )
    app_mod.contracts.append_row(
        {
            "ContractID": "C1",
            "Title": "Одржување",
            "Supplier": "SUP1",
            "ValidUntil": "2027-01-01",
        }
    )
    app_mod.reservations.append_row(
        {
            "ReservationID": "R1",
            "AssetID": "AST001",
            "EmployeeID": "E001",
            "FromDate": "2026-10-01",
            "ToDate": "2026-10-05",
            "Status": "active",
        }
    )
    app_mod.requests.append_row(
        {
            "RequestID": "Q1",
            "EmployeeID": "E001",
            "NeedText": "Нов монитор",
            "Status": "open",
            "Created": "2026-09-01",
        }
    )
    from services.incident_service import IncidentService

    svc = IncidentService(
        app_mod.incidents,
        app_mod.history,
        db_path=getattr(app_mod.incidents, "db_path", None),
    )
    svc.create(asset_id="AST001", title="Скршен екран", performed_by="admin")
    return app_mod


def _wipe_users():
    import sqlite3

    import app as app_mod

    con = sqlite3.connect(app_mod.DB_PATH)
    con.execute("DELETE FROM users")
    con.commit()
    con.close()


def test_cmdb_shows_linked_rows(monkeypatch):
    app_mod = _env(monkeypatch)
    try:
        html = app_mod.app.test_client().get("/cmdb/AST001").get_data(as_text=True)
        assert "AST001" in html
        assert "Петар Петров" in html
        assert "Office" in html
        assert "Одржување" in html
        assert "R1" in html
        assert "Нов монитор" in html
        assert "Скршен екран" in html
    finally:
        _wipe_users()


def test_cmdb_unknown_asset_404(monkeypatch):
    app_mod = _env(monkeypatch)
    try:
        assert app_mod.app.test_client().get("/cmdb/NOPE").status_code == 404
    finally:
        _wipe_users()


def test_cmdb_empty_state(monkeypatch):
    app_mod = _env(monkeypatch)
    try:
        html = app_mod.app.test_client().get("/cmdb/AST999").get_data(as_text=True)
        assert "AST999" in html
        assert "Нема поврзани записи" in html
    finally:
        _wipe_users()
