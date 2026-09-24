"""Enterprise Wave1 todo 2: discovery CSV normalize + reconcile + confirm (TDD)."""

import os
import tempfile

import pytest

from services.db_service import DbStore
from services.schemas import DEV_COLS, STAGING_COLS
from services.history_service import HISTORY_COLS, HistoryService

CSV_VALID = """Hostname,SerialNumber,Manufacturer,Model,OS,LastSeen,Source
PC-01,abc123,Dell,Latitude 5440,Win11,2026-09-01,Intune
PC-02,DEF456,Lenovo,T14,Win11,2026-09-02,Intune
"""

CSV_DUP = """Hostname,SerialNumber,Manufacturer,Model,OS,LastSeen,Source
PC-01,abc123,Dell,Latitude 5440,Win11,2026-09-01,Intune
PC-09,ABC123,Dell,Latitude 5440,Win11,2026-09-03,Intune
"""

CSV_NO_SERIAL_COL = """Hostname,Manufacturer,Model
PC-01,Dell,Latitude
"""


@pytest.fixture()
def stores():
    tmp = tempfile.mkdtemp(prefix="discovery-test-")
    db = os.path.join(tmp, "t.db")
    devices = DbStore(db, "devices", DEV_COLS)
    staging = DbStore(db, "staging", STAGING_COLS)
    hist_store = DbStore(db, "history", HISTORY_COLS)
    return devices, staging, HistoryService(hist_store), db


def test_parse_normalizes_serial(stores):
    from services.discovery_service import parse_discovery_csv

    rows = parse_discovery_csv(CSV_VALID.encode("utf-8"))
    assert len(rows) == 2
    assert rows[0]["SerialNumber"] == "ABC123"
    assert rows[0]["Hostname"] == "PC-01"


def test_parse_rejects_missing_serial_column(stores):
    from services.discovery_service import parse_discovery_csv

    with pytest.raises(ValueError):
        parse_discovery_csv(CSV_NO_SERIAL_COL.encode("utf-8"))


def test_parse_rejects_duplicate_serials(stores):
    from services.discovery_service import parse_discovery_csv

    devices, staging, history, db = stores
    with pytest.raises(ValueError):
        parse_discovery_csv(CSV_DUP.encode("utf-8"))
    assert devices.records() == []
    assert staging.records() == []


def test_reconcile_verdicts(stores):
    from services.discovery_service import parse_discovery_csv, reconcile

    devices, staging, history, db = stores
    devices.append_row(
        {
            "AssetID": "AST001",
            "SerialNumber": "DEF456",
            "Manufacturer": "Lenovo",
            "Model": "T14",
            "Status": "Available",
            "EmployeeID": "",
        }
    )
    devices.append_row(
        {
            "AssetID": "AST002",
            "SerialNumber": "TAKEN1",
            "Manufacturer": "Dell",
            "Model": "XPS",
            "Status": "Assigned",
            "EmployeeID": "E001",
        }
    )
    devices.append_row(
        {
            "AssetID": "AST003",
            "SerialNumber": "DIFF1",
            "Manufacturer": "HP",
            "Model": "EliteBook",
            "Status": "Available",
            "EmployeeID": "",
        }
    )
    rows = parse_discovery_csv(
        (
            "Hostname,SerialNumber,Manufacturer,Model,OS,LastSeen,Source\n"
            "PC-01,abc123,Dell,Latitude 5440,Win11,2026-09-01,Intune\n"
            "PC-02,def456,Lenovo,T14,Win11,2026-09-02,Intune\n"
            "PC-03,taken1,Dell,XPS,Win11,2026-09-02,Intune\n"
            "PC-04,diff1,Dell,Latitude 5440,Win11,2026-09-02,Intune\n"
        ).encode("utf-8")
    )
    out = {r["SerialNumber"]: r["verdict"] for r in reconcile(rows, devices)}
    assert out == {
        "ABC123": "new",
        "DEF456": "match",
        "TAKEN1": "conflict",
        "DIFF1": "conflict",
    }


def test_confirm_writes_new_and_updates_match(stores):
    from services.discovery_service import (
        confirm,
        parse_discovery_csv,
        reconcile,
    )

    devices, staging, history, db = stores
    devices.append_row(
        {
            "AssetID": "AST001",
            "SerialNumber": "DEF456",
            "Manufacturer": "Lenovo",
            "Model": "T14",
            "Status": "Available",
            "EmployeeID": "",
            "Notes": "",
        }
    )
    rows = reconcile(parse_discovery_csv(CSV_VALID.encode("utf-8")), devices)
    counts = confirm(rows, devices, staging, history, performed_by="admin", db_path=db)
    assert counts == {"new": 1, "updated": 1, "skipped": 0}
    created = devices.find("SerialNumber", "ABC123")
    assert created is not None
    assert created["Status"] == "Available"
    assert created["AssetID"].startswith("AST")
    matched = devices.find("SerialNumber", "DEF456")
    assert "2026-09-02" in matched["Notes"]
    assert len(history.store.records()) == 3
    summaries = [
        h for h in history.store.records() if h.get("Action") == "DISCOVERY_IMPORT"
    ]
    assert len(summaries) == 1
    assert "new=1" in summaries[0].get("Reason", "")


def test_confirm_never_touches_assigned(stores):
    from services.discovery_service import (
        confirm,
        parse_discovery_csv,
        reconcile,
    )

    devices, staging, history, db = stores
    devices.append_row(
        {
            "AssetID": "AST002",
            "SerialNumber": "TAKEN1",
            "Manufacturer": "Dell",
            "Model": "XPS",
            "Status": "Assigned",
            "EmployeeID": "E001",
            "Notes": "orig",
        }
    )
    rows = reconcile(
        parse_discovery_csv(
            (
                "Hostname,SerialNumber,Manufacturer,Model,OS,LastSeen,Source\n"
                "PC-03,taken1,Dell,XPS,Win11,2026-09-02,Intune\n"
            ).encode("utf-8")
        ),
        devices,
    )
    counts = confirm(rows, devices, staging, history, performed_by="admin", db_path=db)
    assert counts == {"new": 0, "updated": 0, "skipped": 1}
    untouched = devices.find("SerialNumber", "TAKEN1")
    assert untouched["Notes"] == "orig"
