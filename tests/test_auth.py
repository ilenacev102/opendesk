"""Phase A.1: authentication + roles (TDD). Service-level tests on temp DB."""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.auth_service import (
    USER_COLS,
    AuthService,
    hash_password,
    verify_password,
)
from services.db_service import DbStore


@pytest.fixture
def auth():
    tmp = tempfile.mkdtemp()
    store = DbStore(os.path.join(tmp, "t.db"), "users", USER_COLS)
    return AuthService(store)


def test_password_is_hashed_not_plaintext():
    h = hash_password("tajna123")
    assert h != "tajna123"
    assert verify_password("tajna123", h) is True
    assert verify_password("pogresna", h) is False


def test_create_and_verify_admin(auth):
    auth.create_user("admin", "silna-lozinka", role="admin")
    user = auth.verify("admin", "silna-lozinka")
    assert user is not None
    assert user["Role"] == "admin"
    assert auth.verify("admin", "greshka") is None


def test_duplicate_username_raises(auth):
    auth.create_user("admin", "x" * 8)
    with pytest.raises(ValueError):
        auth.create_user("admin", "y" * 8)


def test_short_password_raises(auth):
    with pytest.raises(ValueError):
        auth.create_user("pero", "kratka")


def test_inactive_user_cannot_login(auth):
    auth.create_user("pero", "dolgapass", role="magacioner")
    auth.set_active("pero", False)
    assert auth.verify("pero", "dolgapass") is None


def test_roles_and_change_password(auth):
    auth.create_user("citac1", "dolgapass1", role="citac")
    assert auth.get("citac1")["Role"] == "citac"
    auth.change_password("citac1", "nova-dolga")
    assert auth.verify("citac1", "dolgapass1") is None
    assert auth.verify("citac1", "nova-dolga") is not None


def test_auth_required_only_when_users_exist(auth):
    assert auth.auth_required() is False
    auth.create_user("admin", "silna-lozinka", role="admin")
    assert auth.auth_required() is True


def test_unknown_role_raises(auth):
    with pytest.raises(ValueError):
        auth.create_user("x", "dolgapassx", role="sef")
