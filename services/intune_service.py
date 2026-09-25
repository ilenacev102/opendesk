"""Intune Graph sync: fetch managed devices, map to discovery rows.

Manual trigger only (no daemon). Secrets live in env and never enter logs.
The Graph client is injectable so tests run with zero network; the live
path uses MSAL client-credentials and raises a clean error when msal or
credentials are missing.
"""

import os

from services.discovery_service import normalize_serial

ENV_TENANT = "SERVICEDESK_INTUNE_TENANT"
ENV_CLIENT_ID = "SERVICEDESK_INTUNE_CLIENT_ID"
ENV_CLIENT_SECRET = "SERVICEDESK_INTUNE_CLIENT_SECRET"

GRAPH_SCOPE = ["https://graph.microsoft.com/.default"]
DEVICES_ENDPOINT = "https://graph.microsoft.com/v1.0/deviceManagement/managedDevices"

try:
    import msal  # noqa: F401

    _HAS_MSAL = True
except ImportError:
    _HAS_MSAL = False


class IntuneError(ValueError):
    """Friendly Intune failure (unconfigured, unreachable, bad credentials)."""


def configured() -> bool:
    return bool(
        os.environ.get(ENV_TENANT, "").strip()
        and os.environ.get(ENV_CLIENT_ID, "").strip()
    )


def to_discovery_row(device) -> dict:
    last_seen = str(device.get("lastSyncDateTime", "") or "")[:10]
    os_name = str(device.get("operatingSystem", "") or "").strip()
    os_ver = str(device.get("osVersion", "") or "").strip()
    os_full = f"{os_name} {os_ver}".strip()
    return {
        "Hostname": str(device.get("deviceName", "") or "").strip(),
        "SerialNumber": normalize_serial(device.get("serialNumber", "")),
        "Manufacturer": str(device.get("manufacturer", "") or "").strip(),
        "Model": str(device.get("model", "") or "").strip(),
        "OS": os_full,
        "LastSeen": last_seen,
        "Source": "intune",
    }


class _LiveGraph:
    def __init__(self):
        import msal
        import requests

        tenant = os.environ.get(ENV_TENANT, "").strip()
        client_id = os.environ.get(ENV_CLIENT_ID, "").strip()
        secret = os.environ.get(ENV_CLIENT_SECRET, "")
        try:
            msal_app = msal.ConfidentialClientApplication(
                client_id,
                authority=f"https://login.microsoftonline.com/{tenant}",
                client_credential=secret,
            )
            result = msal_app.acquire_token_for_client(scopes=GRAPH_SCOPE)
        except Exception as exc:
            raise IntuneError(f"Intune автентикацијата не успеа: {exc}")
        if "access_token" not in result:
            raise IntuneError(
                "Intune автентикацијата е одбиена (проверете TENANT/ID/SECRET)."
            )
        self._token = result["access_token"]
        self._requests = requests

    def get_devices_page(self, url=None):
        try:
            resp = self._requests.get(
                url or DEVICES_ENDPOINT,
                headers={"Authorization": f"Bearer {self._token}"},
                timeout=20,
            )
            resp.raise_for_status()
            return resp.json()
        except IntuneError:
            raise
        except Exception as exc:
            raise IntuneError(f"Intune серверот е недостапен: {exc}")


def _live_client():
    if not _HAS_MSAL:
        raise IntuneError(
            "MSAL библиотеката недостасува: инсталирајте msal за Intune sync."
        )
    if not configured():
        raise IntuneError(
            f"Intune не е конфигуриран: поставете {ENV_TENANT} и {ENV_CLIENT_ID}."
        )
    return _LiveGraph()


def fetch_devices(client_factory=None):
    if not configured():
        raise IntuneError(
            f"Intune не е конфигуриран: поставете {ENV_TENANT} и {ENV_CLIENT_ID}."
        )
    client = client_factory() if client_factory else _live_client()
    rows, url, seen_urls = [], None, set()
    try:
        while True:
            page = client.get_devices_page(url)
            for device in page.get("value", []) or []:
                rows.append(to_discovery_row(device))
            nxt = page.get("@odata.nextLink")
            if not nxt or nxt in seen_urls:
                break
            seen_urls.add(nxt)
            url = nxt
    except IntuneError:
        raise
    except Exception as exc:
        raise IntuneError(f"Intune серверот е недостапен: {exc}")
    return rows
