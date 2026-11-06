"""Tests for preventive maintenance scheduler (/maintenance)."""

import datetime as dt
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _setup_maint_env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService
    from services.schemas import DEV_COLS, INCIDENT_COLS, MAINT_SCHEDULE_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "maint.db")
    sched_store = DbStore(db, "maintenance_schedules", MAINT_SCHEDULE_COLS)
    devices_store = DbStore(db, "devices", DEV_COLS)
    inc_store = DbStore(db, "incidents", INCIDENT_COLS)
    hist_store = DbStore(db, "history", HISTORY_COLS)

    monkeypatch.setattr(app_mod, "maintenance_schedules", sched_store)
    monkeypatch.setattr(app_mod, "devices", devices_store)
    monkeypatch.setattr(app_mod, "incidents", inc_store)
    monkeypatch.setattr(app_mod, "history", HistoryService(hist_store))
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)
    monkeypatch.setitem(app_mod.PATHS, "db", db)

    devices_store.append_row({
        "AssetID": "UPS-APC-3000",
        "Category": "UPS",
        "Manufacturer": "APC",
        "Model": "Smart-UPS 3000",
        "Status": "Active",
    })

    return app_mod


def test_compute_maint_status():
    from routes.maintenance import compute_maint_status

    today = dt.date(2026, 6, 1)
    # Past
    assert compute_maint_status(dt.date(2026, 5, 20), today) == "overdue"
    assert compute_maint_status("2026-05-31", today) == "overdue"
    # Due soon (<= 14 days)
    assert compute_maint_status(dt.date(2026, 6, 1), today) == "due_soon"
    assert compute_maint_status(dt.date(2026, 6, 10), today) == "due_soon"
    # OK (> 14 days)
    assert compute_maint_status(dt.date(2026, 7, 1), today) == "ok"


def test_create_maintenance_schedule(monkeypatch):
    app_mod = _setup_maint_env(monkeypatch)
    c = app_mod.app.test_client()

    resp = c.post(
        "/maintenance/new",
        data={
            "asset_id": "UPS-APC-3000",
            "title": "Тестирање на батериски ќелии и калибрација",
            "frequency_days": "90",
            "last_serviced": "2026-01-01",
            "notes": "Овластен сервис APC",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    records = app_mod.maintenance_schedules.records()
    assert len(records) == 1
    m = records[0]
    assert m["AssetID"] == "UPS-APC-3000"
    assert m["FrequencyDays"] == "90"
    # 2026-01-01 + 90 days = 2026-04-01
    assert m["NextDue"] == "2026-04-01"

    # View page renders schedule
    page = c.get("/maintenance").get_data(as_text=True)
    assert "UPS-APC-3000" in page
    assert "Тестирање на батериски ќелии" in page


def test_complete_maintenance(monkeypatch):
    app_mod = _setup_maint_env(monkeypatch)
    c = app_mod.app.test_client()

    # Create schedule
    c.post(
        "/maintenance/new",
        data={
            "asset_id": "UPS-APC-3000",
            "title": "Периодична проверка",
            "frequency_days": "30",
            "last_serviced": "2026-01-01",
        },
    )
    m = app_mod.maintenance_schedules.records()[0]
    sid = m["ScheduleID"]

    # Mark complete on 2026-05-01
    resp = c.post(
        "/maintenance/complete",
        data={
            "schedule_id": sid,
            "service_date": "2026-05-01",
            "notes": "Батериите се во 98% капацитет.",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    updated = app_mod.maintenance_schedules.find("ScheduleID", sid)
    assert updated["LastServiced"] == "2026-05-01"
    # 2026-05-01 + 30 days = 2026-05-31
    assert updated["NextDue"] == "2026-05-31"


def test_create_ticket_from_schedule(monkeypatch):
    app_mod = _setup_maint_env(monkeypatch)
    c = app_mod.app.test_client()

    c.post(
        "/maintenance/new",
        data={
            "asset_id": "UPS-APC-3000",
            "title": "Годишен преглед",
            "frequency_days": "365",
            "last_serviced": "2025-01-01",
        },
    )
    m = app_mod.maintenance_schedules.records()[0]
    sid = m["ScheduleID"]

    # Create ticket
    resp = c.post(
        "/maintenance/create-ticket",
        data={"schedule_id": sid},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    incidents = app_mod.incidents.records()
    assert len(incidents) == 1
    inc = incidents[0]
    assert "[Превентивен Сервис]" in inc["Title"]
    assert inc["AssetID"] == "UPS-APC-3000"
    assert inc["Priority"] in ("high", "medium")
