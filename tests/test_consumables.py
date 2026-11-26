"""Phase B.3b: consumables (TDD). Add + issue via routes on isolated stores."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _cons_env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService
    from services.schemas import CONS_COLS, DEV_COLS, EMP_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "c.db")
    monkeypatch.setattr(app_mod, "consumables", DbStore(db, "consumables", CONS_COLS))
    monkeypatch.setattr(app_mod, "devices", DbStore(db, "devices", DEV_COLS))
    monkeypatch.setattr(app_mod, "employees", DbStore(db, "employees", EMP_COLS))
    monkeypatch.setattr(
        app_mod, "history", HistoryService(DbStore(db, "history", HISTORY_COLS))
    )
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)
    return app_mod


def test_add_consumable(monkeypatch):
    app_mod = _cons_env(monkeypatch)
    r = app_mod.app.test_client().post(
        "/consumables",
        data={
            "action": "add",
            "ConsumableID": "TONER-001",
            "Name": "Тонер HP 36A",
            "Category": "Тонери",
            "Quantity": "10",
            "MinLevel": "2",
            "Location": "Магацин",
        },
    )
    assert r.status_code == 302
    row = app_mod.consumables.find("ConsumableID", "TONER-001")
    assert row is not None and row.get("Quantity") == "10"


def test_add_duplicate_rejected(monkeypatch):
    app_mod = _cons_env(monkeypatch)
    c = app_mod.app.test_client()
    data = {
        "action": "add",
        "ConsumableID": "TONER-001",
        "Name": "Тонер",
        "Quantity": "5",
    }
    assert c.post("/consumables", data=data).status_code == 302
    assert c.post("/consumables", data=data).status_code == 302
    rows = app_mod.consumables.filter_eq("ConsumableID", "TONER-001")
    assert len(rows) == 1


def test_issue_decrements_and_logs(monkeypatch):
    app_mod = _cons_env(monkeypatch)
    c = app_mod.app.test_client()
    c.post(
        "/consumables",
        data={
            "action": "add",
            "ConsumableID": "CABLE-01",
            "Name": "Кабел HDMI",
            "Quantity": "10",
            "MinLevel": "3",
        },
    )
    r = c.post(
        "/consumables/issue",
        data={"consumable_id": "CABLE-01", "qty": "4", "notes": "сала 3"},
    )
    assert r.status_code == 302
    row = app_mod.consumables.find("ConsumableID", "CABLE-01")
    assert row is not None and row.get("Quantity") == "6"
    actions = [h.get("Action") for h in app_mod.history.store.records()]
    assert "CONSUME" in actions


def test_issue_attributed_to_current_user(monkeypatch):
    """Audit integrity: history rows record the acting user, never hardcoded 'admin'."""
    import tempfile as _tf

    app_mod = _cons_env(monkeypatch)
    monkeypatch.setenv("SERVICEDESK_DB", os.path.join(_tf.mkdtemp(), "u.db"))
    app_mod.auth_svc.create_user("mag", "dolgapass123", role="magacioner")
    try:
        c = app_mod.app.test_client()
        c.post("/login", data={"username": "mag", "password": "dolgapass123"})
        c.post(
            "/consumables",
            data={
                "action": "add",
                "ConsumableID": "CABLE-09",
                "Name": "Кабел",
                "Quantity": "5",
                "MinLevel": "1",
            },
        )
        r = c.post(
            "/consumables/issue",
            data={"consumable_id": "CABLE-09", "qty": "1", "notes": ""},
        )
        assert r.status_code == 302
        last = [
            h for h in app_mod.history.store.records() if h.get("Action") == "CONSUME"
        ][-1]
        assert last.get("PerformedBy") == "mag"
    finally:
        import sqlite3

        con = sqlite3.connect(app_mod.DB_PATH)
        con.execute("DELETE FROM users")
        con.commit()
        con.close()


def test_issue_over_stock_rejected(monkeypatch):
    app_mod = _cons_env(monkeypatch)
    c = app_mod.app.test_client()
    c.post(
        "/consumables",
        data={
            "action": "add",
            "ConsumableID": "CABLE-02",
            "Name": "Кабел",
            "Quantity": "2",
        },
    )
    r = c.post("/consumables/issue", data={"consumable_id": "CABLE-02", "qty": "5"})
    assert r.status_code == 302
    row = app_mod.consumables.find("ConsumableID", "CABLE-02")
    assert row is not None and row.get("Quantity") == "2"


def test_low_stock_flagged(monkeypatch):
    app_mod = _cons_env(monkeypatch)
    c = app_mod.app.test_client()
    c.post(
        "/consumables",
        data={
            "action": "add",
            "ConsumableID": "PAPER-A4",
            "Name": "Хартија А4",
            "Quantity": "1",
            "MinLevel": "5",
        },
    )
    html = c.get("/consumables").get_data(as_text=True)
    assert "PAPER-A4" in html and "Ниска залиха" in html
