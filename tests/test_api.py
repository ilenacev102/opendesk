"""Phase A.2: API tokens (TDD). Service-level tests on temp DB."""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.api_token_service import TOKEN_COLS, ApiTokenService
from services.auth_service import USER_COLS, AuthService
from services.db_service import DbStore


@pytest.fixture
def svc():
    tmp = tempfile.mkdtemp()
    auth = AuthService(DbStore(os.path.join(tmp, "t.db"), "users", USER_COLS))
    tokens = ApiTokenService(
        DbStore(os.path.join(tmp, "t.db"), "api_tokens", TOKEN_COLS)
    )
    auth.create_user("apiuser", "dolgapass123", role="magacioner")
    return auth, tokens


def test_create_returns_plaintext_once(svc):
    _, tokens = svc
    plain = tokens.create("apiuser", "telefon")
    assert isinstance(plain, str) and len(plain) >= 32
    stored = tokens.list("apiuser")
    assert len(stored) == 1
    assert stored[0]["TokenHash"] != plain


def test_verify_valid_and_wrong(svc):
    auth, tokens = svc
    plain = tokens.create("apiuser", "skripta")
    user = tokens.verify(plain, auth)
    assert user is not None and user["UserName"] == "apiuser"
    assert tokens.verify("nepostecki-token", auth) is None


def test_revoke_kills_token(svc):
    auth, tokens = svc
    plain = tokens.create("apiuser", "staro")
    tid = tokens.list("apiuser")[0]["TokenID"]
    tokens.revoke(tid, "apiuser")
    assert tokens.verify(plain, auth) is None


def test_inactive_user_token_rejected(svc):
    auth, tokens = svc
    plain = tokens.create("apiuser", "x")
    auth.set_active("apiuser", False)
    assert tokens.verify(plain, auth) is None


def test_cannot_revoke_foreign_token(svc):
    auth, tokens = svc
    auth.create_user("drug", "dolgapass456", role="citac")
    plain = tokens.create("drug", "negov")
    tid = tokens.list("drug")[0]["TokenID"]
    with pytest.raises(ValueError):
        tokens.revoke(tid, "apiuser")
    assert tokens.verify(plain, auth) is not None


def test_v1_open_in_setup_mode():
    """Given no users exist / When GET /api/v1/devices without token / Then 200."""
    import app as app_mod

    assert not app_mod.auth_svc.auth_required()
    r = app_mod.app.test_client().get("/api/v1/devices")
    assert r.status_code == 200
