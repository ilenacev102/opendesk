"""Tests for Snipe-IT style granular license seat management."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _setup_env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService
    from services.schemas import DEV_COLS, EMP_COLS, LIC_COLS, LIC_SEAT_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "seats.db")
    monkeypatch.setattr(app_mod, "licenses", DbStore(db, "licenses", LIC_COLS))
    monkeypatch.setattr(app_mod, "license_seats", DbStore(db, "license_seats", LIC_SEAT_COLS))
    monkeypatch.setattr(app_mod, "devices", DbStore(db, "devices", DEV_COLS))
    monkeypatch.setattr(app_mod, "employees", DbStore(db, "employees", EMP_COLS))
    monkeypatch.setattr(
        app_mod, "history", HistoryService(DbStore(db, "history", HISTORY_COLS))
    )
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)
    return app_mod


def test_seat_allocation_to_employee_and_device(monkeypatch):
    app_mod = _setup_env(monkeypatch)
    c = app_mod.app.test_client()

    # Add a 3-seat license
    c.post(
        "/licenses",
        data={
            "action": "add",
            "LicenseID": "LIC-PRO",
            "Software": "IntelliJ IDEA Ultimate",
            "Seats": "3",
            "ExpiryDate": "2027-12-31",
        },
    )

    # Assign Seat 1 to an Employee
    r1 = c.post(
        "/licenses/assign",
        data={
            "license_id": "LIC-PRO",
            "assigned_to_type": "employee",
            "assigned_to_id": "EMP-007",
            "notes": "Backend lead license",
        },
    )
    assert r1.status_code == 302
    lic = app_mod.licenses.find("LicenseID", "LIC-PRO")
    assert lic["SeatsUsed"] == "1"
    seats = app_mod.license_seats.filter_eq("LicenseID", "LIC-PRO")
    assert len(seats) == 1
    assert seats[0]["AssignedToType"] == "employee"
    assert seats[0]["AssignedToID"] == "EMP-007"
    assert seats[0]["Notes"] == "Backend lead license"

    # Assign Seat 2 to a Device (Asset)
    r2 = c.post(
        "/licenses/assign",
        data={
            "license_id": "LIC-PRO",
            "assigned_to_type": "device",
            "assigned_to_id": "AST-SERVER-01",
            "notes": "CI build machine",
        },
    )
    assert r2.status_code == 302
    lic = app_mod.licenses.find("LicenseID", "LIC-PRO")
    assert lic["SeatsUsed"] == "2"
    seats = app_mod.license_seats.filter_eq("LicenseID", "LIC-PRO")
    assert len(seats) == 2

    # Check UI renders seats
    page = c.get("/licenses").get_data(as_text=True)
    assert "IntelliJ IDEA" in page
    assert "EMP-007" in page
    assert "AST-SERVER-01" in page


def test_seat_revoke_by_seat_id(monkeypatch):
    app_mod = _setup_env(monkeypatch)
    c = app_mod.app.test_client()

    c.post(
        "/licenses",
        data={
            "action": "add",
            "LicenseID": "LIC-SEAT-TEST",
            "Software": "Docker Desktop",
            "Seats": "2",
        },
    )
    c.post(
        "/licenses/assign",
        data={
            "license_id": "LIC-SEAT-TEST",
            "assigned_to_id": "EMP-001",
        },
    )
    seats = app_mod.license_seats.filter_eq("LicenseID", "LIC-SEAT-TEST")
    assert len(seats) == 1
    seat_id = seats[0]["SeatID"]

    # Revoke via /licenses/seat/revoke
    rev_resp = c.post(
        "/licenses/seat/revoke",
        data={"seat_id": seat_id},
    )
    assert rev_resp.status_code == 302
    assert len(app_mod.license_seats.filter_eq("LicenseID", "LIC-SEAT-TEST")) == 0
    lic = app_mod.licenses.find("LicenseID", "LIC-SEAT-TEST")
    assert lic["SeatsUsed"] == "0"


def test_over_allocation_prevented(monkeypatch):
    app_mod = _setup_env(monkeypatch)
    c = app_mod.app.test_client()

    c.post(
        "/licenses",
        data={
            "action": "add",
            "LicenseID": "LIC-SINGLE",
            "Software": "Special CAD",
            "Seats": "1",
        },
    )
    c.post("/licenses/assign", data={"license_id": "LIC-SINGLE", "assigned_to_id": "EMP-01"})
    # Second assignment must fail
    c.post("/licenses/assign", data={"license_id": "LIC-SINGLE", "assigned_to_id": "EMP-02"})
    assert app_mod.licenses.find("LicenseID", "LIC-SINGLE")["SeatsUsed"] == "1"
    assert len(app_mod.license_seats.filter_eq("LicenseID", "LIC-SINGLE")) == 1
