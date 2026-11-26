"""P2.2: TLS mode is opt-in (SERVICEDESK_TLS=1) for cookie Secure + HSTS."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _env(monkeypatch, tls: bool):
    import app as app_mod

    tmp = tempfile.mkdtemp()
    monkeypatch.setenv("SERVICEDESK_DB", os.path.join(tmp, "tls.db"))
    monkeypatch.setitem(app_mod.app.config, "TLS_ENABLED", tls)
    monkeypatch.setitem(app_mod.app.config, "SESSION_COOKIE_SECURE", tls)
    return app_mod


def test_tls_helper_defaults_off(monkeypatch):
    import config

    monkeypatch.delenv("SERVICEDESK_TLS", raising=False)
    assert config.tls_enabled() is False
    monkeypatch.setenv("SERVICEDESK_TLS", "0")
    assert config.tls_enabled() is False
    monkeypatch.setenv("SERVICEDESK_TLS", "1")
    assert config.tls_enabled() is True


def test_default_install_has_no_hsts(monkeypatch):
    app_mod = _env(monkeypatch, False)
    r = app_mod.app.test_client().get("/login")
    assert "Strict-Transport-Security" not in r.headers


def test_tls_mode_adds_hsts_and_secure_cookie(monkeypatch):
    app_mod = _env(monkeypatch, True)
    r = app_mod.app.test_client().get("/login")
    assert r.headers.get("Strict-Transport-Security", "").startswith("max-age=")
    cookie = r.headers.get("Set-Cookie", "")
    assert "Secure" in cookie
