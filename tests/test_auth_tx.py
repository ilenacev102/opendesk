"""P1.4: user and API-token mutations are atomic and audited."""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _env():
    from services.api_token_service import TOKEN_COLS, ApiTokenService
    from services.auth_service import USER_COLS, AuthService
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService

    db = os.path.join(tempfile.mkdtemp(), "auth.db")
    users = DbStore(db, "users", USER_COLS)
    tokens = DbStore(db, "api_tokens", TOKEN_COLS)
    history = HistoryService(DbStore(db, "history", HISTORY_COLS))
    return AuthService(users, history), ApiTokenService(tokens, history), history


def _actions(history):
    return [r["Action"] for r in history.store.records()]


def test_create_user_writes_audit_without_secrets():
    auth, _tokens, history = _env()
    auth.create_user("ana", "dolgapass123", role="admin", performed_by="root")

    rows = history.store.records()
    assert [r["Action"] for r in rows] == ["USER_CREATE"]
    assert rows[0]["AssetID"] == "ana"
    assert rows[0]["NewStatus"] == "admin"
    assert rows[0]["PerformedBy"] == "root"
    blob = " ".join(str(v) for r in rows for v in r.values())
    assert "dolgapass123" not in blob
    assert auth.get("ana")["PasswordHash"] not in blob


def test_role_and_active_changes_are_audited():
    auth, _tokens, history = _env()
    auth.create_user("ana", "dolgapass123", role="magacioner")
    auth.set_role("ana", "admin", performed_by="root")
    auth.set_active("ana", False, performed_by="root")
    auth.set_active("ana", True, performed_by="root")

    rows = history.store.records()
    assert [r["Action"] for r in rows] == [
        "USER_CREATE",
        "USER_ROLE",
        "USER_DEACTIVATE",
        "USER_ACTIVATE",
    ]
    assert rows[1]["OldStatus"] == "magacioner"
    assert rows[1]["NewStatus"] == "admin"


def test_password_change_is_audited_without_the_hash():
    auth, _tokens, history = _env()
    auth.create_user("ana", "dolgapass123")
    auth.change_password("ana", "novalozinka123", performed_by="ana")

    rows = history.store.records()
    assert rows[-1]["Action"] == "USER_PASS"
    blob = " ".join(str(v) for r in rows for v in r.values())
    assert "novalozinka123" not in blob
    assert auth.get("ana")["PasswordHash"] not in blob


def test_set_role_rolls_back_when_audit_fails():
    auth, _tokens, history = _env()
    auth.create_user("ana", "dolgapass123", role="magacioner")

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    history.log = boom
    with pytest.raises(RuntimeError):
        auth.set_role("ana", "admin")
    assert auth.get("ana")["Role"] == "magacioner"


def test_token_create_and_revoke_are_audited():
    auth, tokens, history = _env()
    auth.create_user("ana", "dolgapass123")
    plain = tokens.create("ana", "cli")

    assert _actions(history)[-1] == "TOKEN_CREATE"
    tid = tokens.list("ana")[0]["TokenID"]
    tokens.revoke(tid, "ana")

    rows = history.store.records()
    assert rows[-1]["Action"] == "TOKEN_REVOKE"
    blob = " ".join(str(v) for r in rows for v in r.values())
    assert plain not in blob
    assert tokens.list("ana")[0]["TokenHash"] not in blob


def test_token_revoke_rolls_back_when_audit_fails():
    auth, tokens, history = _env()
    auth.create_user("ana", "dolgapass123")
    tokens.create("ana", "cli")
    tid = tokens.list("ana")[0]["TokenID"]

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    history.log = boom
    with pytest.raises(RuntimeError):
        tokens.revoke(tid, "ana")
    assert tokens.list("ana")[0]["Active"] == "YES"


def test_sso_link_is_audited():
    auth, _tokens, history = _env()
    auth.create_user("ana", "dolgapass123")
    auth.link_sso("ana", "sub-123", performed_by="system")

    assert auth.get("ana")["OIDCSubject"] == "sub-123"
    assert _actions(history)[-1] == "USER_SSO_LINK"
