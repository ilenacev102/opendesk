"""Phase G.1: contracts (TDD). CRUD + expiry flag."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _contracts_env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService
    from services.schemas import CONTRACT_COLS, DEV_COLS, EMP_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "g.db")
    monkeypatch.setattr(app_mod, "contracts", DbStore(db, "contracts", CONTRACT_COLS))
    monkeypatch.setattr(app_mod, "devices", DbStore(db, "devices", DEV_COLS))
    monkeypatch.setattr(app_mod, "employees", DbStore(db, "employees", EMP_COLS))
    monkeypatch.setattr(
        app_mod, "history", HistoryService(DbStore(db, "history", HISTORY_COLS))
    )
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)
    return app_mod


def test_add_contract(monkeypatch):
    app_mod = _contracts_env(monkeypatch)
    r = app_mod.app.test_client().post(
        "/contracts",
        data={
            "action": "add",
            "ContractID": "DOG-001",
            "Title": "Одржување печатачи",
            "Supplier": "Принт ДОО",
            "ValidUntil": "2027-12-31",
        },
    )
    assert r.status_code == 302
    row = app_mod.contracts.find("ContractID", "DOG-001")
    assert row is not None and row.get("Supplier") == "Принт ДОО"


def test_add_duplicate_rejected(monkeypatch):
    app_mod = _contracts_env(monkeypatch)
    c = app_mod.app.test_client()
    data = {"action": "add", "ContractID": "DOG-001", "Title": "X"}
    c.post("/contracts", data=data)
    c.post("/contracts", data=data)
    assert len(app_mod.contracts.filter_eq("ContractID", "DOG-001")) == 1


def test_expiring_flagged(monkeypatch):
    import datetime

    app_mod = _contracts_env(monkeypatch)
    c = app_mod.app.test_client()
    soon = (datetime.date.today() + datetime.timedelta(days=20)).isoformat()
    c.post(
        "/contracts",
        data={
            "action": "add",
            "ContractID": "DOG-EXP",
            "Title": "Y",
            "ValidUntil": soon,
        },
    )
    c.post(
        "/contracts",
        data={
            "action": "add",
            "ContractID": "DOG-OK",
            "Title": "Z",
            "ValidUntil": "2030-01-01",
        },
    )
    html = c.get("/contracts").get_data(as_text=True)
    assert "DOG-EXP" in html and "Истекува" in html
    assert "DOG-OK" in html
