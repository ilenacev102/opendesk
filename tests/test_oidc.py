"""SSO todo 2: OIDC service with injectable client (TDD)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class FakeClient:
    def __init__(self, claims=None, fail=None):
        self._claims = claims or {
            "sub": "sub-123",
            "email": "petar@firma.mk",
            "preferred_username": "petar",
            "name": "Petar P",
        }
        self.fail = fail
        self.authorized_with = None

    def authorize_redirect(self, redirect_uri, state):
        return {
            "url": "https://idp.example/authorize",
            "redirect_uri": redirect_uri,
            "state": state,
        }

    def authorize_access_token(self, code, state, session_state):
        if self.fail:
            raise ConnectionError("unreachable")
        if state != session_state:
            raise ValueError("state mismatch")
        self.authorized_with = code
        return dict(self._claims)


def _factory(claims=None, fail=None):
    return lambda: FakeClient(claims=claims, fail=fail)


def test_configured(monkeypatch):
    from services import oidc_service as oidc

    monkeypatch.delenv("SERVICEDESK_OIDC_ISSUER", raising=False)
    monkeypatch.delenv("SERVICEDESK_OIDC_CLIENT_ID", raising=False)
    assert oidc.configured() is False
    monkeypatch.setenv("SERVICEDESK_OIDC_ISSUER", "https://idp.example")
    monkeypatch.setenv("SERVICEDESK_OIDC_CLIENT_ID", "cid")
    assert oidc.configured() is True


def test_authorize_url(monkeypatch):
    from services import oidc_service as oidc

    monkeypatch.setenv("SERVICEDESK_OIDC_ISSUER", "https://idp.example")
    monkeypatch.setenv("SERVICEDESK_OIDC_CLIENT_ID", "cid")
    result = oidc.authorize_url(
        _factory(), "http://127.0.0.1:5000/login/sso/callback", "st-1"
    )
    assert result["url"] == "https://idp.example/authorize"
    assert result["state"] == "st-1"
    assert result["redirect_uri"].endswith("/login/sso/callback")


def test_callback_maps_claims(monkeypatch):
    from services import oidc_service as oidc

    monkeypatch.setenv("SERVICEDESK_OIDC_ISSUER", "https://idp.example")
    monkeypatch.setenv("SERVICEDESK_OIDC_CLIENT_ID", "cid")
    claims = oidc.handle_callback(_factory(), "code-1", "st-1", "st-1")
    assert claims["subject"] == "sub-123"
    assert claims["email"] == "petar@firma.mk"
    assert claims["username"] == "petar"


def test_callback_username_fallback(monkeypatch):
    from services import oidc_service as oidc

    monkeypatch.setenv("SERVICEDESK_OIDC_ISSUER", "https://idp.example")
    monkeypatch.setenv("SERVICEDESK_OIDC_CLIENT_ID", "cid")
    factory = _factory(claims={"sub": "s9", "email": "", "name": "No Mail"})
    claims = oidc.handle_callback(factory, "code-1", "st-1", "st-1")
    assert claims["username"] != ""


def test_callback_state_mismatch():
    import pytest

    from services import oidc_service as oidc
    from services.oidc_service import OidcError

    with pytest.raises(OidcError):
        oidc.handle_callback(_factory(), "code-1", "st-1", "other")


def test_callback_unreachable():
    import pytest

    from services import oidc_service as oidc
    from services.oidc_service import OidcError

    with pytest.raises(OidcError):
        oidc.handle_callback(_factory(fail=True), "code-1", "st-1", "st-1")


def test_missing_env_clean_message(monkeypatch):
    import pytest

    from services import oidc_service as oidc
    from services.oidc_service import OidcError

    monkeypatch.delenv("SERVICEDESK_OIDC_ISSUER", raising=False)
    monkeypatch.delenv("SERVICEDESK_OIDC_CLIENT_ID", raising=False)
    with pytest.raises(OidcError, match="OIDC|конфигур"):
        oidc.handle_callback(_factory(), "code-1", "st-1", "st-1")
