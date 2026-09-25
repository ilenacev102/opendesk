"""OIDC login: generic issuer (Entra ID, Google, Keycloak), local fallback kept.

Client is injectable so tests run with zero network. The live path uses
Authlib with server metadata discovery. Secrets never enter logs.
"""

import os

ENV_ISSUER = "SERVICEDESK_OIDC_ISSUER"
ENV_CLIENT_ID = "SERVICEDESK_OIDC_CLIENT_ID"
ENV_CLIENT_SECRET = "SERVICEDESK_OIDC_CLIENT_SECRET"
ENV_NAME = "SERVICEDESK_OIDC_NAME"
ENV_DEFAULT_ROLE = "SERVICEDESK_OIDC_DEFAULT_ROLE"


class OidcError(ValueError):
    """Friendly OIDC failure (unconfigured, unreachable, bad response)."""


def configured() -> bool:
    return bool(
        os.environ.get(ENV_ISSUER, "").strip()
        and os.environ.get(ENV_CLIENT_ID, "").strip()
    )


def provider_name() -> str:
    return os.environ.get(ENV_NAME, "").strip() or "SSO"


def default_role() -> str:
    return os.environ.get(ENV_DEFAULT_ROLE, "").strip() or "citac"


def _require_configured():
    if not configured():
        raise OidcError(
            f"SSO не е конфигуриран: поставете {ENV_ISSUER} и {ENV_CLIENT_ID}."
        )


def _live_client():
    try:
        from authlib.integrations.flask_client import OAuth
    except ImportError:
        raise OidcError("Authlib недостасува: инсталирајте authlib.")
    issuer = os.environ.get(ENV_ISSUER, "").strip().rstrip("/")
    oauth = OAuth()
    return oauth.register(
        name="sso",
        client_id=os.environ.get(ENV_CLIENT_ID, "").strip(),
        client_secret=os.environ.get(ENV_CLIENT_SECRET, ""),
        server_metadata_url=f"{issuer}/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )


def authorize_url(client_factory, redirect_uri: str, state: str) -> dict:
    _require_configured()
    client = client_factory() if client_factory else _live_client()
    try:
        target = client.authorize_redirect(redirect_uri, state)
    except OidcError:
        raise
    except Exception as exc:
        raise OidcError(f"SSO редирекцијата не успеа: {exc}")
    if isinstance(target, dict):
        return {
            "url": target.get("url", ""),
            "redirect_uri": target.get("redirect_uri", redirect_uri),
            "state": target.get("state", state),
        }
    return {"url": str(target), "redirect_uri": redirect_uri, "state": state}


def map_claims(raw) -> dict:
    if not isinstance(raw, dict):
        raise OidcError("SSO одговорот е невалиден.")
    subject = str(raw.get("sub", "") or "").strip()
    if not subject:
        raise OidcError("SSO одговорот нема subject.")
    email = str(raw.get("email", "") or "").strip()
    username = str(raw.get("preferred_username", "") or "").strip()
    if not username and email and "@" in email:
        username = email.split("@")[0].lower()
    if not username:
        username = (
            str(raw.get("name", "") or "").strip().lower().replace(" ", ".") or subject
        )
    return {"subject": subject, "email": email, "username": username}


def handle_callback(client_factory, code: str, state: str, session_state: str) -> dict:
    _require_configured()
    if not state or state != session_state:
        raise OidcError("SSO сесијата е невалидна. Обидете се повторно.")
    client = client_factory() if client_factory else _live_client()
    try:
        raw = client.authorize_access_token(code, state, session_state)
    except OidcError:
        raise
    except Exception as exc:
        raise OidcError(f"SSO најавата не успеа: {exc}")
    try:
        return map_claims(raw)
    except OidcError:
        raise
    except Exception as exc:
        raise OidcError(f"SSO одговорот е невалиден: {exc}")
