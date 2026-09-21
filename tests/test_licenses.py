"""Phase V.1: software licenses (TDD). Seats + assign/revoke + expiry flag."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _lic_env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.history_service import HistoryService, HISTORY_COLS
    from services.schemas import DEV_COLS, EMP_COLS, LIC_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "l.db")
    monkeypatch.setattr(app_mod, "licenses", DbStore(db, "licenses", LIC_COLS))
    monkeypatch.setattr(app_mod, "devices", DbStore(db, "devices", DEV_COLS))
    monkeypatch.setattr(app_mod, "employees", DbStore(db, "employees", EMP_COLS))
    monkeypatch.setattr(
        app_mod, "history", HistoryService(DbStore(db, "history", HISTORY_COLS))
    )
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)
    return app_mod


def _add(client, lid="LIC-001", seats="5", expiry="2027-06-01"):
    return client.post(
        "/licenses",
        data={
            "action": "add",
            "LicenseID": lid,
            "Software": "Microsoft 365",
            "Seats": seats,
            "ExpiryDate": expiry,
        },
    )


def test_add_license(monkeypatch):
    app_mod = _lic_env(monkeypatch)
    assert _add(app_mod.app.test_client()).status_code == 302
    row = app_mod.licenses.find("LicenseID", "LIC-001")
    assert row is not None and row.get("SeatsUsed") == "0"


def test_add_duplicate_rejected(monkeypatch):
    app_mod = _lic_env(monkeypatch)
    c = app_mod.app.test_client()
    _add(c)
    _add(c)
    assert len(app_mod.licenses.filter_eq("LicenseID", "LIC-001")) == 1


def test_assign_and_revoke_seat(monkeypatch):
    app_mod = _lic_env(monkeypatch)
    c = app_mod.app.test_client()
    _add(c)
    assert (
        c.post(
            "/licenses/assign",
            data={"license_id": "LIC-001", "emp_id": "E001"},
        ).status_code
        == 302
    )
    assert app_mod.licenses.find("LicenseID", "LIC-001").get("SeatsUsed") == "1"
    assert (
        c.post(
            "/licenses/revoke",
            data={"license_id": "LIC-001", "emp_id": "E001"},
        ).status_code
        == 302
    )
    assert app_mod.licenses.find("LicenseID", "LIC-001").get("SeatsUsed") == "0"
    actions = [h.get("Action") for h in app_mod.history.store.records()]
    assert "LIC_ASSIGN" in actions and "LIC_REVOKE" in actions


def test_assign_over_seats_rejected(monkeypatch):
    app_mod = _lic_env(monkeypatch)
    c = app_mod.app.test_client()
    _add(c, seats="1")
    c.post("/licenses/assign", data={"license_id": "LIC-001", "emp_id": "E1"})
    r = c.post("/licenses/assign", data={"license_id": "LIC-001", "emp_id": "E2"})
    assert r.status_code == 302
    assert app_mod.licenses.find("LicenseID", "LIC-001").get("SeatsUsed") == "1"


def test_expiring_flagged(monkeypatch):
    import datetime

    app_mod = _lic_env(monkeypatch)
    c = app_mod.app.test_client()
    soon = (datetime.date.today() + datetime.timedelta(days=10)).isoformat()
    _add(c, lid="LIC-EXP", expiry=soon)
    _add(c, lid="LIC-OK", expiry="2030-01-01")
    html = c.get("/licenses").get_data(as_text=True)
    assert "LIC-EXP" in html and "Истекува" in html
    assert "LIC-OK" in html
