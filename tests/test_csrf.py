"""CSRF: cookie-authenticated POSTs require a session token (TDD)."""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def csrf_app():
    """App with CSRF enforcement on; suite default is off via SERVICEDESK_CSRF."""
    import app as app_mod

    app_mod.app.config["CSRF_ENABLED"] = True
    yield app_mod
    app_mod.app.config["CSRF_ENABLED"] = False


def _token(client) -> str:
    with client.session_transaction() as sess:
        tok = sess.get("_csrf_token")
    assert tok, "session must expose a CSRF token after a GET"
    return tok


def test_login_post_without_token_forbidden(csrf_app):
    """Given CSRF on / When POST /login without token / Then 403."""
    c = csrf_app.app.test_client()
    r = c.post("/login", data={"username": "x", "password": "y"})
    assert r.status_code == 403


def test_login_post_with_token_allowed(csrf_app):
    """Given a session token / When POST /login with it / Then not 403."""
    c = csrf_app.app.test_client()
    c.get("/login")
    tok = _token(c)
    r = c.post(
        "/login",
        data={"username": "x", "password": "y", "_csrf_token": tok},
    )
    assert r.status_code != 403


def test_login_post_wrong_token_forbidden(csrf_app):
    """Given a forged token / When POST /login / Then 403."""
    c = csrf_app.app.test_client()
    c.get("/login")
    r = c.post(
        "/login",
        data={"username": "x", "password": "y", "_csrf_token": "forged-token"},
    )
    assert r.status_code == 403


def test_get_login_html_contains_csrf_field(csrf_app):
    """Given CSRF on / When GET /login / Then form embeds _csrf_token."""
    c = csrf_app.app.test_client()
    html = c.get("/login").get_data(as_text=True)
    assert 'name="_csrf_token"' in html
    assert 'value="' in html


def test_api_v1_cookie_post_without_csrf_forbidden(csrf_app):
    """Given cookie auth / When POST /api/v1/checkout without CSRF / Then 403."""
    c = csrf_app.app.test_client()
    r = c.post(
        "/api/v1/checkout",
        json={"asset_id": "X", "emp_id": "Y", "reason": "t", "notes": ""},
    )
    assert r.status_code == 403


def test_api_v1_bearer_post_exempt_from_csrf(csrf_app):
    """Given Bearer API / When POST /api/v1/checkout without CSRF / Then not 403."""
    c = csrf_app.app.test_client()
    r = c.post(
        "/api/v1/checkout",
        json={"asset_id": "X", "emp_id": "Y", "reason": "t", "notes": ""},
        headers={"Authorization": "Bearer test-token"},
    )
    assert r.status_code != 403


def test_suite_default_csrf_off_keeps_plain_post_working():
    """Given suite env / When app loads / Then CSRF_ENABLED is False by default."""
    import app as app_mod

    assert csrf_env_default() is False
    assert app_mod.app.config["CSRF_ENABLED"] is False


def csrf_env_default() -> bool:
    return os.environ.get("SERVICEDESK_CSRF", "0") == "1"


def test_post_forms_across_templates_declare_token_field():
    """Given all templates / When scanned / Then every POST form has _csrf_token."""
    root = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "templates_web",
    )
    missing = []
    for name in os.listdir(root):
        if not name.endswith(".html"):
            continue
        path = os.path.join(root, name)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        for m in re.finditer(r"<form\s+method=\"post\"[^>]*>", text):
            window = text[m.end() : m.end() + 400]
            if "_csrf_token" not in window:
                missing.append(f"{name}:{text[: m.start()].count(chr(10)) + 1}")
    assert not missing, f"POST forms missing csrf field: {missing}"
