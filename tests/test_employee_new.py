"""Brz vnes 6+7: manual employee creation + datalists + duplicate warning."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _emp_env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.history_service import HistoryService, HISTORY_COLS
    from services.schemas import DEV_COLS, EMP_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "e.db")
    monkeypatch.setattr(app_mod, "devices", DbStore(db, "devices", DEV_COLS))
    monkeypatch.setattr(app_mod, "employees", DbStore(db, "employees", EMP_COLS))
    monkeypatch.setattr(
        app_mod, "history", HistoryService(DbStore(db, "history", HISTORY_COLS))
    )
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)
    row = {c: "" for c in EMP_COLS}
    row.update(
        {
            "EmployeeID": "E001",
            "FirstName": "Ана",
            "LastName": "Тест",
            "Department": "ИТ",
            "Active": "YES",
        }
    )
    app_mod.employees.append_row(row)
    return app_mod


def test_employee_new_renders(monkeypatch):
    app_mod = _emp_env(monkeypatch)
    html = app_mod.app.test_client().get("/employees/new").get_data(as_text=True)
    assert "FirstName" in html and "Department" in html


def test_create_employee(monkeypatch):
    app_mod = _emp_env(monkeypatch)
    r = app_mod.app.test_client().post(
        "/employees/new",
        data={
            "EmployeeID": "E002",
            "FirstName": "Петар",
            "LastName": "Петров",
            "Department": "ИТ",
        },
    )
    assert r.status_code == 302
    saved = app_mod.employees.find("EmployeeID", "E002")
    assert saved is not None and saved.get("Active") == "YES"


def test_duplicate_id_rejected(monkeypatch):
    app_mod = _emp_env(monkeypatch)
    app_mod.app.test_client().post(
        "/employees/new",
        data={"EmployeeID": "E001", "FirstName": "X", "LastName": "Y"},
    )
    assert len(app_mod.employees.filter_eq("EmployeeID", "E001")) == 1


def test_duplicate_name_warns_but_creates(monkeypatch):
    app_mod = _emp_env(monkeypatch)
    c = app_mod.app.test_client()
    with c.session_transaction():
        pass
    r = c.post(
        "/employees/new",
        data={"EmployeeID": "E009", "FirstName": "Ана", "LastName": "Тест"},
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert app_mod.employees.find("EmployeeID", "E009") is not None
    assert "дупликат" in r.get_data(as_text=True).lower()


def test_prefill_name(monkeypatch):
    app_mod = _emp_env(monkeypatch)
    html = (
        app_mod.app.test_client()
        .get("/employees/new?prefill=Марко Марков")
        .get_data(as_text=True)
    )
    assert 'value="Марко"' in html and 'value="Марков"' in html


def test_values_api_has_employee_fields(monkeypatch):
    _emp_env(monkeypatch)
    import app as app_mod

    r = app_mod.app.test_client().get("/api/values")
    data = r.get_json()
    assert "Department" in data and "ИТ" in data["Department"]
    assert "Organization" in data
