"""MS-9: NextAuditDate discipline (scan stamps +30d, missing campaign)."""

import os
import sys
import tempfile
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _store():
    from services.db_service import DbStore
    from services.schemas import DEV_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "audit.db")
    devices = DbStore(db, "devices", DEV_COLS)
    devices.append_row(
        {"AssetID": "AST001", "Status": "Available", "Location": "Скопје"}
    )
    return devices


def test_scanned_stamps_plus_30_days():
    from services.popis_service import mark_scanned

    devices = _store()
    today = date.today().isoformat()
    due = mark_scanned(devices, "AST001", today=today)
    assert due == (date.today() + timedelta(days=30)).isoformat()
    row = devices.find("AssetID", "AST001")
    assert row is not None
    assert row["NextAuditDate"] == due


def test_expired_appears_future_does_not():
    from services.popis_service import mark_scanned, missing

    devices = _store()
    devices.append_row({"AssetID": "AST002", "Status": "Available"})
    mark_scanned(
        devices, "AST001", today=(date.today() - timedelta(days=40)).isoformat()
    )
    mark_scanned(devices, "AST002", today=date.today().isoformat())
    ids = {d["AssetID"] for d in missing(devices, today=date.today().isoformat())}
    assert ids == {"AST001"}


def test_unstamped_never_missing():
    from services.popis_service import missing

    devices = _store()
    assert missing(devices, today=date.today().isoformat()) == []


def test_missing_page_renders(monkeypatch):
    from datetime import timedelta

    from services import ratelimit as rl

    rl.reset()
    import app as app_mod
    from services.db_service import DbStore
    from services.schemas import DEV_COLS

    tmp = tempfile.mkdtemp()
    dev_store = DbStore(os.path.join(tmp, "audit_ui.db"), "devices", DEV_COLS)
    past = (date.today() - timedelta(days=5)).isoformat()
    dev_store.append_row(
        {"AssetID": "AST001", "Status": "Available", "NextAuditDate": past}
    )
    monkeypatch.setattr(app_mod, "devices", dev_store)
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)
    app_mod.auth_svc.create_user("mag", "dolgapass123", role="magacioner")
    try:
        c = app_mod.app.test_client()
        c.post("/login", data={"username": "mag", "password": "dolgapass123"})
        r = c.get("/popis/missing")
        assert r.status_code == 200
        body = r.get_data(as_text=True)
        assert "Неаудитирани" in body
        assert "AST001" in body
    finally:
        import sqlite3

        con = sqlite3.connect(app_mod.DB_PATH)
        con.execute("DELETE FROM users")
        con.commit()
        con.close()
