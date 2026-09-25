"""SSO todo 1: USER_COLS Email/OIDCSubject + create_sso_user."""

import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_user_cols_extended():
    from services.auth_service import USER_COLS

    assert "Email" in USER_COLS
    assert "OIDCSubject" in USER_COLS


def _svc():
    from services.auth_service import USER_COLS, AuthService
    from services.db_service import DbStore

    tmp = tempfile.mkdtemp()
    store = DbStore(os.path.join(tmp, "u.db"), "users", USER_COLS)
    return AuthService(store)


def test_create_sso_user():
    svc = _svc()
    user = svc.create_sso_user(
        username="petar",
        email="petar@firma.mk",
        subject="sub-123",
        role="citac",
    )
    assert user["Email"] == "petar@firma.mk"
    assert user["OIDCSubject"] == "sub-123"
    assert user["PasswordHash"] == ""
    assert svc.verify("petar", "anything") is None  # no local login


def test_create_sso_user_duplicate_rejected():
    import pytest

    svc = _svc()
    svc.create_sso_user(username="petar", email="p@f.mk", subject="s1")
    with pytest.raises(ValueError):
        svc.create_sso_user(username="petar", email="p@f.mk", subject="s2")


def test_legacy_users_gain_cols():
    from services.auth_service import USER_COLS, AuthService
    from services.db_service import DbStore

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "legacy_u.db")
    con = sqlite3.connect(db)
    con.execute(
        'CREATE TABLE "users" ("UserID" TEXT, "UserName" TEXT, '
        '"PasswordHash" TEXT, "Role" TEXT, "Active" TEXT)'
    )
    con.execute("INSERT INTO \"users\" VALUES ('adm', 'adm', 'x', 'admin', 'YES')")
    con.commit()
    con.close()
    svc = AuthService(DbStore(db, "users", USER_COLS))
    row = svc.get("adm")
    assert row is not None
    assert row["Role"] == "admin"
    assert row["Email"] == ""
    assert row["OIDCSubject"] == ""
