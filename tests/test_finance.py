"""Phase B.2: depreciation - linear book value (TDD). Pure functions."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import finance as fin


def test_book_value_new_device():
    import datetime

    today = datetime.date.today().isoformat()
    assert fin.book_value("1000", today) == 1000.0


def test_book_value_fully_depreciated():
    assert fin.book_value("1000", "2000-01-01") == 0.0


def test_book_value_invalid_inputs():
    assert fin.book_value("", "2026-01-01") is None
    assert fin.book_value("abc", "2026-01-01") is None
    assert fin.book_value("1000", "not-a-date") is None
    assert fin.book_value("1000", "") is None


def test_book_value_halfway():
    import datetime

    two_years_ago = (datetime.date.today() - datetime.timedelta(days=730)).isoformat()
    val = fin.book_value("1000", two_years_ago, years=4)
    assert val is not None and 400 <= val <= 600


def test_migration_adds_new_columns():
    import sqlite3

    from services.db_service import DbStore
    from services.schemas import DEV_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "m.db")
    con = sqlite3.connect(db)
    con.execute('CREATE TABLE "devices" ("AssetID" TEXT)')
    con.commit()
    con.close()
    store = DbStore(db, "devices", DEV_COLS)
    cols = [r[1] for r in sqlite3.connect(db).execute('PRAGMA table_info("devices")')]
    assert "PurchasePrice" in cols and "Supplier" in cols
    store.append_row({c: "" for c in DEV_COLS} | {"AssetID": "M1"})
    assert store.find("AssetID", "M1") is not None


def _fin_env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.history_service import HistoryService, HISTORY_COLS
    from services.schemas import DEV_COLS, EMP_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "f.db")
    monkeypatch.setattr(app_mod, "devices", DbStore(db, "devices", DEV_COLS))
    monkeypatch.setattr(app_mod, "employees", DbStore(db, "employees", EMP_COLS))
    monkeypatch.setattr(
        app_mod, "history", HistoryService(DbStore(db, "history", HISTORY_COLS))
    )
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)
    return app_mod


def test_device_new_persists_price(monkeypatch):
    from services.schemas import DEV_COLS

    app_mod = _fin_env(monkeypatch)
    data = {c: "" for c in DEV_COLS}
    data.update(
        {
            "AssetID": "FIN01",
            "Type": "Laptop",
            "SerialNumber": "SFIN1",
            "Status": "Available",
            "PurchasePrice": "45000",
            "Supplier": "Нептун",
        }
    )
    r = app_mod.app.test_client().post("/devices/new", data=data)
    assert r.status_code == 302
    saved = app_mod.devices.find("AssetID", "FIN01")
    assert saved is not None
    assert saved.get("PurchasePrice") == "45000"
    assert saved.get("Supplier") == "Нептун"


def test_old_csv_without_new_cols_still_imports(monkeypatch):
    import io

    from services.schemas import DEV_COLS

    app_mod = _fin_env(monkeypatch)
    old_cols = [c for c in DEV_COLS if c not in ("PurchasePrice", "Supplier")]
    lines = [",".join(old_cols)]
    vals = {c: "" for c in old_cols}
    vals.update(
        {
            "AssetID": "FIN02",
            "Type": "Монитор",
            "SerialNumber": "SFIN2",
            "Status": "Available",
        }
    )
    lines.append(",".join(vals[c] for c in old_cols))
    r = app_mod.app.test_client().post(
        "/import",
        data={
            "kind": "devices",
            "file": (io.BytesIO("\n".join(lines).encode("utf-8")), "old.csv"),
        },
    )
    assert r.status_code == 200
    saved = app_mod.devices.find("AssetID", "FIN02")
    assert saved is not None
    assert saved.get("PurchasePrice") == ""
