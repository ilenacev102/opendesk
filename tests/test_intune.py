"""Discovery Pro todo 5: Intune Graph sync service (TDD)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PAGE_1 = {
    "value": [
        {
            "id": "g1",
            "deviceName": "PC-01",
            "serialNumber": "abc123",
            "manufacturer": "Dell",
            "model": "Latitude 5440",
            "operatingSystem": "Windows",
            "osVersion": "11",
            "lastSyncDateTime": "2026-09-20T10:00:00Z",
        },
        {
            "id": "g2",
            "deviceName": "PC-02",
            "serialNumber": "DEF456",
            "manufacturer": "Lenovo",
            "model": "T14",
            "operatingSystem": "Windows",
            "osVersion": "11",
            "lastSyncDateTime": "2026-09-20T11:00:00Z",
        },
    ],
    "@odata.nextLink": "https://graph/next?page=2",
}
PAGE_2 = {
    "value": [
        {
            "id": "g3",
            "deviceName": "PC-03",
            "serialNumber": "",
            "manufacturer": "HP",
            "model": "EliteBook",
            "operatingSystem": "Windows",
            "osVersion": "10",
            "lastSyncDateTime": "2026-09-19T10:00:00Z",
        },
    ],
}


class FakeGraph:
    def __init__(self, pages=None, fail=None):
        self._pages = pages or [PAGE_1, PAGE_2]
        self.fail = fail
        self.calls = []

    def get_devices_page(self, url=None):
        if self.fail:
            raise ConnectionError(self.fail)
        self.calls.append(url or "first")
        idx = len(self.calls) - 1
        if idx < len(self._pages):
            return self._pages[idx]
        return {"value": []}


def _env():
    return {
        "SERVICEDESK_INTUNE_TENANT": "tenant-id",
        "SERVICEDESK_INTUNE_CLIENT_ID": "cid",
        "SERVICEDESK_INTUNE_CLIENT_SECRET": "csecret",
    }


def test_fetch_paging_and_mapping(monkeypatch):
    from services import intune_service as intune

    for key, val in _env().items():
        monkeypatch.setenv(key, val)
    rows = intune.fetch_devices(client_factory=lambda: FakeGraph())
    assert len(rows) == 3
    first = rows[0]
    assert first["Hostname"] == "PC-01"
    assert first["SerialNumber"] == "ABC123"
    assert first["Manufacturer"] == "Dell"
    assert first["Model"] == "Latitude 5440"
    assert "Windows" in first["OS"]
    assert first["Source"] == "intune"
    assert first["LastSeen"] == "2026-09-20"


def test_empty_serial_rows_kept_for_preview():
    from services.intune_service import to_discovery_row

    row = to_discovery_row(PAGE_2["value"][0])
    assert row["SerialNumber"] == ""
    assert row["Hostname"] == "PC-03"


def test_bad_credentials_friendly_error(monkeypatch):
    import pytest

    from services import intune_service as intune
    from services.intune_service import IntuneError

    for key, val in _env().items():
        monkeypatch.setenv(key, val)
    with pytest.raises(IntuneError):
        intune.fetch_devices(client_factory=lambda: FakeGraph(fail="401 unauthorized"))


def test_missing_env_clean_message(monkeypatch):
    import pytest

    from services import intune_service as intune
    from services.intune_service import IntuneError

    monkeypatch.delenv("SERVICEDESK_INTUNE_TENANT", raising=False)
    monkeypatch.delenv("SERVICEDESK_INTUNE_CLIENT_ID", raising=False)
    with pytest.raises(IntuneError, match="INTUNE|конфигур"):
        intune.fetch_devices(client_factory=lambda: FakeGraph())
