"""P2.7: book value is back in the devices CSV (finance module in use)."""

import csv
import datetime
import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService
    from services.schemas import DEV_COLS, EMP_COLS

    db = os.path.join(tempfile.mkdtemp(), "reports.db")
    devices = DbStore(db, "devices", DEV_COLS)
    monkeypatch.setattr(app_mod, "devices", devices)
    monkeypatch.setattr(app_mod, "employees", DbStore(db, "employees", EMP_COLS))
    monkeypatch.setattr(
        app_mod, "history", HistoryService(DbStore(db, "history", HISTORY_COLS))
    )
    app_mod.auth_svc.create_user("adm", "dolgapass123", role="admin")
    return app_mod, devices


def _wipe_users():
    import sqlite3

    import app as app_mod

    con = sqlite3.connect(app_mod.DB_PATH)
    con.execute("DELETE FROM users")
    con.commit()
    con.close()


def test_devices_csv_contains_computed_book_value(monkeypatch):
    app_mod, devices = _env(monkeypatch)
    try:
        two_years = (datetime.date.today() - datetime.timedelta(days=730)).isoformat()
        devices.append_row(
            {
                "AssetID": "D1",
                "PurchasePrice": "1000",
                "PurchaseDate": two_years,
            }
        )
        devices.append_row({"AssetID": "D2", "PurchasePrice": "", "PurchaseDate": ""})

        c = app_mod.app.test_client()
        c.post("/login", data={"username": "adm", "password": "dolgapass123"})
        r = c.get("/reports?export=devices")
        assert r.status_code == 200
        rows = {
            row["AssetID"]: row
            for row in csv.DictReader(io.StringIO(r.get_data(as_text=True)))
        }
        assert "BookValue" in rows["D1"]
        assert 450 <= float(rows["D1"]["BookValue"]) <= 550
        assert rows["D2"]["BookValue"] == ""
    finally:
        _wipe_users()
