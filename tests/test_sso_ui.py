"""SSO todo 3: login routes + button (tests-after)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CLAIMS_NEW = {"subject": "sub-1", "email": "nova@firma.mk", "username": "nova"}
CLAIMS_BOSS = {"subject": "sub-9", "email": "boss@firma.mk", "username": "bossx"}


def _patch_oidc(monkeypatch, claims=None, fail=None):
    import services.oidc_service as oidc

    monkeypatch.setenv("SERVICEDESK_OIDC_ISSUER", "https://idp.example")
    monkeypatch.setenv("SERVICEDESK_OIDC_CLIENT_ID", "cid")

    def fake_authorize(factory, redirect_uri, state):
        return {
            "url": "https://idp.example/authorize",
            "redirect_uri": redirect_uri,
            "state": state,
        }

    def fake_callback(factory, code, state, session_state):
        if fail:
            raise oidc.OidcError("провајдерот одби")
        if state != session_state:
            raise oidc.OidcError("невалидна сесија")
        return dict(claims or CLAIMS_NEW)

    monkeypatch.setattr(oidc, "authorize_url", fake_authorize)
    monkeypatch.setattr(oidc, "handle_callback", fake_callback)


def _wipe_users():
    import sqlite3

    import app as app_mod

    con = sqlite3.connect(app_mod.DB_PATH)
    con.execute("DELETE FROM users")
    con.commit()
    con.close()


def _login(client, user, pw="dolgapass123"):
    return client.post("/login", data={"username": user, "password": pw})


def test_button_shown_only_when_configured(monkeypatch):
    import app as app_mod

    try:
        c = app_mod.app.test_client()
        assert "login/sso" not in c.get("/login").get_data(as_text=True)
        _patch_oidc(monkeypatch)
        assert "login/sso" in c.get("/login").get_data(as_text=True)
    finally:
        _wipe_users()


def test_callback_creates_and_logs_in(monkeypatch):
    import app as app_mod

    _patch_oidc(monkeypatch)
    try:
        c = app_mod.app.test_client()
        with c.session_transaction() as sess:
            sess["sso_state"] = "st-1"
        r = c.get("/login/sso/callback?code=k&state=st-1")
        assert r.status_code == 302
        user = app_mod.auth_svc.get("nova")
        assert user is not None and user["Role"] == "citac"
        assert c.get("/incidents").status_code == 200
    finally:
        _wipe_users()


def test_second_login_preserves_admin_role(monkeypatch):
    import app as app_mod

    _patch_oidc(monkeypatch, claims=CLAIMS_BOSS)
    try:
        app_mod.auth_svc.create_user("boss", "dolgapass123", role="admin")
        app_mod.auth_svc.store.update_where(
            "UserName", "boss", {"Email": "boss@firma.mk"}
        )
        c = app_mod.app.test_client()
        with c.session_transaction() as sess:
            sess["sso_state"] = "st-2"
        r = c.get("/login/sso/callback?code=k&state=st-2")
        assert r.status_code == 302
        user = app_mod.auth_svc.get("boss")
        assert user is not None and user["Role"] == "admin"
        assert user["OIDCSubject"] == "sub-9"
    finally:
        _wipe_users()


def test_unconfigured_redirects_to_login(monkeypatch):
    import app as app_mod

    monkeypatch.delenv("SERVICEDESK_OIDC_ISSUER", raising=False)
    monkeypatch.delenv("SERVICEDESK_OIDC_CLIENT_ID", raising=False)
    try:
        c = app_mod.app.test_client()
        r = c.get("/login/sso", follow_redirects=False)
        assert r.status_code == 302
        assert "/login" in r.headers["Location"]
    finally:
        _wipe_users()


def test_provider_error_creates_nothing(monkeypatch):
    import app as app_mod

    _patch_oidc(monkeypatch, fail=True)
    try:
        c = app_mod.app.test_client()
        with c.session_transaction() as sess:
            sess["sso_state"] = "st-3"
        r = c.get("/login/sso/callback?code=k&state=st-3")
        assert r.status_code == 302
        assert len(app_mod.auth_svc.list_users()) == 0
    finally:
        _wipe_users()


def test_local_login_untouched(monkeypatch):
    import app as app_mod

    _patch_oidc(monkeypatch)
    try:
        app_mod.auth_svc.create_user("lok", "dolgapass123", role="magacioner")
        c = app_mod.app.test_client()
        _login(c, "lok")
        assert c.get("/incidents").status_code == 200
    finally:
        _wipe_users()
