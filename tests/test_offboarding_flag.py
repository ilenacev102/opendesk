"""MS-1: offboarding flagged list (read-only)."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _dev(asset, emp):
    return {
        "AssetID": asset,
        "SerialNumber": "S-" + asset,
        "Manufacturer": "Dell",
        "Model": "M1",
        "EmployeeID": emp,
        "Location": "Скопје",
    }


def test_empty_when_nobody_departed():
    from services.offboarding_service import flagged_devices

    devs = [_dev("AST001", "EMP001")]
    assert flagged_devices(devs, set()) == []


def test_flags_two_devices_of_departed():
    from services.offboarding_service import flagged_devices

    devs = [
        _dev("AST001", "EMP009"),
        _dev("AST002", "EMP009"),
        _dev("AST003", "EMP001"),
    ]
    flagged = flagged_devices(devs, {"EMP009"})
    assert {d["AssetID"] for d in flagged} == {"AST001", "AST002"}


def test_departed_without_devices():
    from services.offboarding_service import departed_ids, flagged_devices

    emps = [{"EmployeeID": "EMP009", "Active": "NO"}]
    assert flagged_devices([], departed_ids(emps)) == []


def _ui_env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.schemas import DEV_COLS, EMP_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "off_ui.db")
    emp_store = DbStore(db, "employees", EMP_COLS)
    dev_store = DbStore(db, "devices", DEV_COLS)
    emp_store.append_row(
        {"EmployeeID": "EMP009", "FirstName": "Заминат", "Active": "NO"}
    )
    emp_store.append_row(
        {"EmployeeID": "EMP001", "FirstName": "Активен", "Active": "YES"}
    )
    dev_store.append_row(_dev("AST001", "EMP009"))
    dev_store.append_row(_dev("AST002", "EMP001"))
    monkeypatch.setattr(app_mod, "employees", emp_store)
    monkeypatch.setattr(app_mod, "devices", dev_store)
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)
    app_mod.auth_svc.create_user("mag", "dolgapass123", role="magacioner")
    return app_mod


def _wipe_users():
    import sqlite3

    import app as app_mod

    con = sqlite3.connect(app_mod.DB_PATH)
    con.execute("DELETE FROM users")
    con.commit()
    con.close()


def test_flagged_page_renders(monkeypatch):
    from services import ratelimit as rl

    rl.reset()
    app_mod = _ui_env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        c.post("/login", data={"username": "mag", "password": "dolgapass123"})
        r = c.get("/offboarding/flagged")
        assert r.status_code == 200
        body = r.get_data(as_text=True)
        assert "Заминати со опрема" in body
        assert "AST001" in body
        assert "AST002" not in body
    finally:
        _wipe_users()
