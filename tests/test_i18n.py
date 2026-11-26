from services.i18n import load_translations, translate, set_current_locale
from flask import Flask

def test_i18n_translation_lookup():
    app = Flask(__name__)
    app.secret_key = "test-secret"
    load_translations()

    with app.test_request_context("/"):
        # Default should resolve to English
        assert translate("nav.dashboard") == "Dashboard"
        assert translate("common.save") == "Save"

        # Explicit locale lookup
        assert translate("nav.dashboard", locale="mk") == "Контролна табла"
        assert translate("common.save", locale="mk") == "Зачувај"

        # Non-existing key fallback
        assert translate("non.existing.key", default="Custom Fallback") == "Custom Fallback"
        assert translate("non.existing.key") == "non.existing.key"

def test_i18n_session_locale_switch():
    app = Flask(__name__)
    app.secret_key = "test-secret"
    load_translations()

    with app.test_request_context("/"):
        assert set_current_locale("mk") is True
        assert translate("nav.devices") == "Уреди"
        
        assert set_current_locale("en") is True
        assert translate("nav.devices") == "Devices"

        # Invalid locale
        assert set_current_locale("invalid_lang") is False

def test_language_switch_endpoint():
    from app import app
    client = app.test_client()
    res = client.get("/set-language/en", follow_redirects=False)
    assert res.status_code == 302
    assert "servicedesk_locale=en" in res.headers.get("Set-Cookie", "")

    res_mk = client.get("/set-language/mk", follow_redirects=False)
    assert res_mk.status_code == 302
    assert "servicedesk_locale=mk" in res_mk.headers.get("Set-Cookie", "")
