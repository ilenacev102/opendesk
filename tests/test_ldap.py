"""Enterprise Wave2 todo 9: LDAP read-only sync with dry-run (TDD)."""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FAKE_ENTRIES = [
    {
        "dn": "CN=Petar P,OU=Users,DC=firma,DC=mk",
        "cn": "Petar P",
        "mail": "petar@firma.mk",
        "department": "IT",
        "samaccountname": "petar",
    },
    {
        "dn": "CN=Ana A,OU=Users,DC=firma,DC=mk",
        "cn": "Ana A",
        "mail": "ana@firma.mk",
        "department": "Finance",
        "samaccountname": "ana",
    },
    {
        "dn": "CN=Bob B,OU=Users,DC=firma,DC=mk",
        "cn": "Bob B",
        "mail": "",
        "department": "IT",
        "samaccountname": "bob",
    },
    {
        "dn": "CN=New N,OU=Users,DC=firma,DC=mk",
        "cn": "New N",
        "mail": "new@firma.mk",
        "department": "HR",
    },
    {
        "dn": "CN=Other O,OU=Users,DC=firma,DC=mk",
        "cn": "Other O",
        "mail": "other@firma.mk",
        "department": "HR",
    },
]


class FakeConnection:
    def __init__(self, entries, fail=False):
        self._entries = entries
        self.fail = fail
        self.bound = False

    def search(self, base, flt, attributes=None):
        if self.fail:
            raise ConnectionError("unreachable")
        return list(self._entries)


def _svc(monkeypatch=None):
    import app as app_mod
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService
    from services.schemas import EMP_COLS, LDAPMAP_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "ldap.db")
    employees = DbStore(db, "employees", EMP_COLS)
    ldapmap = DbStore(db, "ldapmap", LDAPMAP_COLS)
    history = HistoryService(DbStore(db, "history", HISTORY_COLS))
    employees.append_row(
        {
            "EmployeeID": "E001",
            "FirstName": "Petar",
            "LastName": "P",
            "UserName": "petar",
            "Email": "petar@firma.mk",
            "Department": "IT",
            "Active": "YES",
        }
    )
    employees.append_row(
        {
            "EmployeeID": "E002",
            "FirstName": "Ana",
            "LastName": "A",
            "UserName": "ana",
            "Email": "",
            "Department": "Finance",
            "Active": "YES",
        }
    )
    employees.append_row(
        {
            "EmployeeID": "E003",
            "FirstName": "Bob",
            "LastName": "B",
            "UserName": "bob",
            "Email": "bob@firma.mk",
            "Department": "IT",
            "Active": "YES",
        }
    )
    if monkeypatch is not None:
        monkeypatch.setattr(app_mod, "employees", employees)
        monkeypatch.setattr(app_mod, "ldapmap", ldapmap)
        monkeypatch.setattr(app_mod, "history", history)
    from services.ldap_service import LdapService

    return (
        LdapService(employees, ldapmap, history, db_path=db),
        employees,
        ldapmap,
        history,
        db,
    )


def test_fetch_maps_fields():
    svc, _, _, _, _ = _svc()
    users = svc.fetch_users(connection_factory=lambda: FakeConnection(FAKE_ENTRIES))
    assert len(users) == 5
    assert users[0]["UserName"] != ""
    assert users[0]["Email"] == "petar@firma.mk"
    assert users[0]["DN"].startswith("CN=Petar")


def test_reconcile_matches_by_email_then_username():
    svc, _, _, _, _ = _svc()
    users = svc.fetch_users(connection_factory=lambda: FakeConnection(FAKE_ENTRIES))
    result = svc.reconcile(users)
    matched = {
        m["ldap"]["mail"] or m["ldap"]["UserName"]: m["employee"]["EmployeeID"]
        for m in result["matched"]
    }
    assert matched["petar@firma.mk"] == "E001"  # by email
    assert matched["ana@firma.mk"] == "E002"  # by username fallback (empty local email)
    assert matched.get("bob@firma.mk") == "E003" or matched.get("bob") == "E003"
    assert len(result["staged"]) == 2  # new + other


def test_dry_run_writes_nothing():
    svc, _, ldapmap, history, _ = _svc()
    users = svc.fetch_users(connection_factory=lambda: FakeConnection(FAKE_ENTRIES))
    before_hist = len(history.store.records())
    result = svc.sync(users, dry_run=True, performed_by="admin")
    assert result["dry_run"] is True
    assert ldapmap.records() == []
    assert len(history.store.records()) == before_hist


def test_confirm_writes_map_and_summary():
    svc, _, ldapmap, history, _ = _svc()
    users = svc.fetch_users(connection_factory=lambda: FakeConnection(FAKE_ENTRIES))
    result = svc.sync(users, dry_run=False, performed_by="admin")
    assert result["matched"] == 3
    assert result["staged"] == 2
    assert len(ldapmap.records()) == 5
    actions = [h.get("Action") for h in history.store.records()]
    assert "LDAP_SYNC" in actions


def test_unreachable_server_zero_writes():
    svc, _, ldapmap, history, _ = _svc()
    from services.ldap_service import LdapError

    with pytest.raises(LdapError):
        svc.fetch_users(connection_factory=lambda: FakeConnection([], fail=True))
    assert ldapmap.records() == []
    assert history.store.records() == []


def test_missing_env_clean_message(monkeypatch):
    from services.ldap_service import configured

    monkeypatch.delenv("SERVICEDESK_LDAP_URL", raising=False)
    monkeypatch.delenv("SERVICEDESK_LDAP_BASE", raising=False)
    assert configured() is False
    svc, _, _, _, _ = _svc()
    from services.ldap_service import LdapError

    with pytest.raises(LdapError, match="LDAP|URL|конфигур"):
        svc.fetch_users()
