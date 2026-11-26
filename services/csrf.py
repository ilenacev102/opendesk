"""Session-based CSRF protection for cookie-authenticated POSTs.

No external dependencies: token lives in the Flask session, forms carry a
hidden field (or clients may send ``X-CSRF-Token``). ``/api/`` requests that
authenticate with ``Authorization: Bearer`` are exempt — they do not rely on
ambient cookie auth. A cookie-authenticated ``/api/`` POST is *not* exempt.
"""

import hmac
import secrets
from typing import Final

SESSION_KEY: Final = "_csrf_token"
FORM_FIELD: Final = "_csrf_token"
HEADER_FIELD: Final = "X-CSRF-Token"
API_PREFIX: Final = "/api/"


def ensure_token(session) -> str:
    """Return the session CSRF token, creating one if absent."""
    token = session.get(SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[SESSION_KEY] = token
    return token


def provided_token(request) -> str:
    """Extract the submitted token from form body or header."""
    return request.form.get(FORM_FIELD) or request.headers.get(HEADER_FIELD) or ""


def is_valid(session, request) -> bool:
    """Constant-time compare of submitted token against the session token."""
    expected = session.get(SESSION_KEY) or ""
    got = provided_token(request)
    if not expected or not got:
        return False
    return hmac.compare_digest(expected, got)


def should_enforce(path: str, authorization: str = "") -> bool:
    """CSRF applies to browser POSTs; only Bearer /api/ clients are exempt."""
    if not (path or "").startswith(API_PREFIX):
        return True
    return not (authorization or "").strip().lower().startswith("bearer ")
