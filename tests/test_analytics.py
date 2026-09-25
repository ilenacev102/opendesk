"""Analytics todo 1: metrics service pure aggregations (TDD)."""

import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TODAY = datetime.date(2026, 9, 25)

DEVICES = [
    {
        "AssetID": "A1",
        "Type": "Лаптоп",
        "Status": "Available",
        "Location": "Скопје",
        "WarrantyUntil": "2026-10-10",
        "PurchasePrice": "30000",
        "Manufacturer": "Dell",
    },
    {
        "AssetID": "A2",
        "Type": "Лаптоп",
        "Status": "Assigned",
        "Location": "Скопје",
        "WarrantyUntil": "2026-11-20",
        "PurchasePrice": "25000",
        "Manufacturer": "HP",
    },
    {
        "AssetID": "A3",
        "Type": "Монитор",
        "Status": "Broken",
        "Location": "Битола",
        "WarrantyUntil": "2026-09-01",
        "PurchasePrice": "8000",
        "Manufacturer": "Dell",
    },
    {
        "AssetID": "A4",
        "Type": "Монитор",
        "Status": "Available",
        "Location": "",
        "WarrantyUntil": "",
        "PurchasePrice": "garbage",
        "Manufacturer": "",
    },
]

INCIDENTS = [
    {
        "IncidentID": "I1",
        "Status": "open",
        "Priority": "high",
        "Created": "2026-09-20 10:00",
        "ClosedAt": "",
        "DueDate": "2026-09-22",
    },
    {
        "IncidentID": "I2",
        "Status": "in-progress",
        "Priority": "urgent",
        "Created": "2026-09-10 10:00",
        "ClosedAt": "",
        "DueDate": "2099-01-01",
    },
    {
        "IncidentID": "I3",
        "Status": "resolved",
        "Priority": "low",
        "Created": "2026-09-20 10:00",
        "ClosedAt": "2026-09-21 12:00",
        "DueDate": "",
    },
    {
        "IncidentID": "I4",
        "Status": "open",
        "Priority": "low",
        "Created": "garbage",
        "ClosedAt": "",
        "DueDate": "",
    },
]

LICENSES = [
    {"LicenseID": "L1", "Software": "Office", "ExpiryDate": "2026-10-05"},
    {"LicenseID": "L2", "Software": "CAD", "ExpiryDate": "2027-01-01"},
    {"LicenseID": "L3", "Software": "Old", "ExpiryDate": ""},
]


def test_devices_by():
    from services.analytics_service import devices_by

    assert devices_by(DEVICES, "Status") == {"Available": 2, "Assigned": 1, "Broken": 1}
    assert devices_by(DEVICES, "Type") == {"Лаптоп": 2, "Монитор": 2}
    assert devices_by([], "Status") == {}


def test_warranty_buckets():
    from services.analytics_service import warranty_buckets

    out = warranty_buckets(DEVICES, TODAY)
    assert out == {"expired": 1, "d30": 1, "d60": 1, "d90": 0}
    assert warranty_buckets([], TODAY) == {"expired": 0, "d30": 0, "d60": 0, "d90": 0}


def test_costs_by():
    from services.analytics_service import costs_by

    out = costs_by(DEVICES, "Location")
    assert out["Скопје"] == 55000.0
    assert out["Битола"] == 8000.0
    assert costs_by([], "Location") == {}


def test_incidents_by():
    from services.analytics_service import incidents_by

    by_status, by_priority = incidents_by(INCIDENTS)
    assert by_status == {"open": 2, "in-progress": 1, "resolved": 1}
    assert by_priority == {"high": 1, "urgent": 1, "low": 2}


def test_breach_counts():
    from services.analytics_service import breach_counts

    assert breach_counts(INCIDENTS, TODAY) == 1


def test_mttr_hours():
    from services.analytics_service import mttr_hours

    assert mttr_hours(INCIDENTS) == 26.0
    assert mttr_hours([]) is None


def test_aging_buckets():
    from services.analytics_service import aging_buckets

    out = aging_buckets(INCIDENTS, TODAY)
    assert out == {"d7": 1, "d30": 1, "over30": 0}


def test_license_expiry():
    from services.analytics_service import license_expiry

    out = license_expiry(LICENSES, TODAY)
    assert [r["LicenseID"] for r in out] == ["L1"]
    assert license_expiry([], TODAY) == []
