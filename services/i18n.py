import json
import os
from typing import Dict, Any
from flask import session, request

DEFAULT_LOCALE = "en"
SUPPORTED_LOCALES = ["en", "mk"]
_TRANSLATIONS: Dict[str, Dict[str, Any]] = {}

def load_translations(locales_dir: str = "locales") -> None:
    """Load JSON translation dictionaries into memory."""
    global _TRANSLATIONS
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_dir = os.path.join(base_dir, locales_dir)
    
    for loc in SUPPORTED_LOCALES:
        file_path = os.path.join(target_dir, f"{loc}.json")
        if os.path.isfile(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    _TRANSLATIONS[loc] = json.load(f)
            except Exception:
                _TRANSLATIONS[loc] = {}
        else:
            _TRANSLATIONS[loc] = {}

def get_current_locale() -> str:
    """Determine the active locale from session, cookie, or default."""
    if "locale" in session and session["locale"] in SUPPORTED_LOCALES:
        return session["locale"]
    cookie_locale = request.cookies.get("servicedesk_locale")
    if cookie_locale in SUPPORTED_LOCALES:
        return cookie_locale
    return DEFAULT_LOCALE

def set_current_locale(locale: str) -> bool:
    """Store the preferred locale in user session."""
    if locale in SUPPORTED_LOCALES:
        session["locale"] = locale
        return True
    return False

def translate(key: str, default: str | None = None, locale: str | None = None) -> str:
    """
    Look up a key (e.g. 'nav.dashboard' or 'common.save') in the active locale.
    Falls back to en, and finally to default or the key itself.
    """
    if not _TRANSLATIONS:
        load_translations()

    active = locale or get_current_locale()
    
    # Try active locale
    val = _lookup(active, key)
    if val is not None:
        return val

    # Try fallback locale (en)
    if active != DEFAULT_LOCALE:
        val = _lookup(DEFAULT_LOCALE, key)
        if val is not None:
            return val

    return default if default is not None else key

def _lookup(locale: str, dot_key: str) -> str | None:
    data = _TRANSLATIONS.get(locale, {})
    keys = dot_key.split(".")
    for k in keys:
        if isinstance(data, dict) and k in data:
            data = data[k]
        else:
            return None
    return str(data) if isinstance(data, (str, int, float)) else None
