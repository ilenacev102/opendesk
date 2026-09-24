"""Enterprise Wave2 todo 10: LDAP sync UI admin-only (tests-after)."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CANNED = [
    {
        "DN": "CN=A A,DC=firma,DC=mk",
        "cn": "A A",
        "mail": "a@firma.mk",
        "Email": "a@firma.mk",
        "UserName": "a",
        "Department": "IT",
    },
    {
        "DN": "CN=New N,DC=firma,DC=mk",
        "cn": "New N",
        "mail": "n@firma.mk",
        "Email": "n@firma.mk",
        "UserName": "n",
        "Department": "HR",
    },
]


def _env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.history_service import HistoryService, HISTORY_COLS
    from services.schemas import EMP_COLS, LDAPMAP_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "ldapui.db")
    monkeypatch.setattr(app_mod, "employees", DbStore(db, "employees", EMP_COLS))
    monkeypatch.setattr(app_mod, "ldapmap", DbStore(db, "ldapmap", LDAPMAP_COLS))
    monkeypatch.setattr(
        app_mod, "history", HistoryService(DbStore(db, "history", HISTORY_COLS))
    )
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)
    monkeypatch.setenv("SERVICEDESK_LDAP_URL", "ldap://fake:389")
    monkeypatch.setenv("SERVICEDESK_LDAP_BASE", "DC=firma,DC=mk")
    app_mod.employees.append_row(
        {
            "EmployeeID": "E1",
            "FirstName": "A",
            "LastName": "A",
            "UserName": "a",
            "Email": "a@firma.mk",
            "Department": "IT",
            "Active": "YES",
        }
    )
    app_mod.auth_svc.create_user("adm", "dolgapass123", role="admin")
    app_mod.auth_svc.create_user("mag", "dolgapass123", role="magacioner")
    app_mod.auth_svc.create_user("cit", "dolgapass123", role="citac")
    monkeypatch.setattr(
        "services.ldap_service.LdapService.fetch_users",
        lambda self, connection_factory=None: list(CANNED),
    )
    return app_mod


def _wipe_users():
    import sqlite3

    import app as app_mod

    con = sqlite3.connect(app_mod.DB_PATH)
    con.execute("DELETE FROM users")
    con.commit()
    con.close()


def _login(client, user, pw="dolgapass123"):
    return client.post("/login", data={"username": user, "password": pw})


def test_admin_preview_and_confirm(monkeypatch):
    app_mod = _env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        _login(c, "adm")
        r = c.get("/users/sync")
        assert r.status_code == 200
        html = r.get_data(as_text=True)
        assert "Преглед" in html
        assert "a@firma.mk" in html and "n@firma.mk" in html
        r2 = c.post("/users/sync", data={"confirm": "1"})
        assert r2.status_code == 302
        assert len(app_mod.ldapmap.records()) == 2
        actions = [h.get("Action") for h in app_mod.history.store.records()]
        assert "LDAP_SYNC" in actions
    finally:
        _wipe_users()


def test_non_admin_blocked(monkeypatch):
    app_mod = _env(monkeypatch)
    try:
        for user in ("mag", "cit"):
            c = app_mod.app.test_client()
            _login(c, user)
            assert c.get("/users/sync").status_code == 403
            assert c.post("/users/sync", data={"confirm": "1"}).status_code == 403
        assert app_mod.ldapmap.records() == []
    finally:
        _wipe_users()


def test_missing_env_shows_hint(monkeypatch):
    app_mod = _env(monkeypatch)
    monkeypatch.delenv("SERVICEDESK_LDAP_URL", raising=False)
    monkeypatch.delenv("SERVICEDESK_LDAP_BASE", raising=False)
    try:
        c = app_mod.app.test_client()
        _login(c, "adm")
        r = c.get("/users/sync")
        assert r.status_code == 200
        assert "SERVICEDESK_LDAP_URL" in r.get_data(as_text=True)
    finally:
        _wipe_users()
