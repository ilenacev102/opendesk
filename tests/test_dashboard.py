"""Dashboard numbers: employees + computers rendered, no CDN scripts (TDD)."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _dash_env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService
    from services.schemas import DEV_COLS, EMP_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "d.db")
    monkeypatch.setattr(app_mod, "devices", DbStore(db, "devices", DEV_COLS))
    monkeypatch.setattr(app_mod, "employees", DbStore(db, "employees", EMP_COLS))
    monkeypatch.setattr(
        app_mod, "history", HistoryService(DbStore(db, "history", HISTORY_COLS))
    )
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)
    for aid, typ, active in [
        ("PC01", "Компјутер", "Available"),
        ("LP01", "Laptop", "Assigned"),
        ("MN01", "Монитор", "Available"),
    ]:
        row = {c: "" for c in DEV_COLS}
        row.update({"AssetID": aid, "Type": typ, "Status": active})
        app_mod.devices.append_row(row)
    for eid, active in [("E1", "YES"), ("E2", "YES"), ("E3", "NO")]:
        row = {c: "" for c in EMP_COLS}
        row.update({"EmployeeID": eid, "Active": active})
        app_mod.employees.append_row(row)
    return app_mod


def test_dashboard_shows_employees_and_computers(monkeypatch):
    app_mod = _dash_env(monkeypatch)
    html = app_mod.app.test_client().get("/").get_data(as_text=True)
    assert 'data-count="2"' in html  # 2 active employees
    assert 'data-count="3"' in html  # 3 total devices
    assert "Вработени" in html
    assert "Компјутери" in html


def test_dashboard_has_no_cdn_scripts():
    tpl = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "templates_web",
        "dashboard.html",
    )
    with open(tpl, encoding="utf-8") as fh:
        src = fh.read()
    assert "cdn.jsdelivr.net" not in src
    assert "chart.umd.min.js" in src
