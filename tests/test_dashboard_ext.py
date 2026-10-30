"""Analytics todo 2: dashboard extension cards + charts (tests-after)."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _env(monkeypatch, seed=True):
    import app as app_mod
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService
    from services.schemas import DEV_COLS, EMP_COLS, INCIDENT_COLS, LIC_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "dash.db")
    monkeypatch.setattr(app_mod, "devices", DbStore(db, "devices", DEV_COLS))
    monkeypatch.setattr(app_mod, "employees", DbStore(db, "employees", EMP_COLS))
    monkeypatch.setattr(app_mod, "incidents", DbStore(db, "incidents", INCIDENT_COLS))
    monkeypatch.setattr(app_mod, "licenses", DbStore(db, "licenses", LIC_COLS))
    monkeypatch.setattr(
        app_mod, "history", HistoryService(DbStore(db, "history", HISTORY_COLS))
    )
    if seed:
        app_mod.devices.append_row(
            {
                "AssetID": "A1",
                "Type": "Лаптоп",
                "Status": "Available",
                "Location": "Скопје",
                "WarrantyUntil": "2026-10-10",
                "PurchasePrice": "30000",
                "Manufacturer": "Dell",
            }
        )
        app_mod.devices.append_row(
            {
                "AssetID": "A2",
                "Type": "Монитор",
                "Status": "Broken",
                "Location": "Битола",
                "WarrantyUntil": "2020-01-01",
                "PurchasePrice": "8000",
                "Manufacturer": "HP",
            }
        )
        from services.incident_service import IncidentService

        svc = IncidentService(
            app_mod.incidents,
            app_mod.history,
            db_path=getattr(app_mod.incidents, "db_path", None),
        )
        a = svc.create(
            asset_id="A1",
            title="Скршен екран",
            priority="high",
            due_date="2020-01-01",
            performed_by="admin",
        )
        svc.transition(a["IncidentID"], "in-progress", performed_by="admin")
        b = svc.create(
            asset_id="A2", title="Бавен", priority="low", performed_by="admin"
        )
        svc.transition(b["IncidentID"], "in-progress", performed_by="admin")
        svc.transition(b["IncidentID"], "resolved", performed_by="admin")
        app_mod.licenses.append_row(
            {"LicenseID": "L1", "Software": "Office", "ExpiryDate": "2026-10-05"}
        )
    return app_mod


def _wipe_users():
    import sqlite3

    import app as app_mod

    con = sqlite3.connect(app_mod.DB_PATH)
    con.execute("DELETE FROM users")
    con.commit()
    con.close()


def test_dashboard_shows_analytics(monkeypatch):
    from services.analytics_service import (
        breach_counts,
        mttr_hours,
        warranty_buckets,
    )

    app_mod = _env(monkeypatch)
    try:
        html = app_mod.app.test_client().get("/").get_data(as_text=True)
        assert "Инциденти по статус" in html
        assert "Гарантна прогноза" in html
        assert "Трошоци по локација" in html
        assert "MTTR" in html
        assert 'id="chIncidents"' in html
        assert 'id="chWarranty"' in html
        assert str(mttr_hours(app_mod.incidents.records())) in html
        assert str(breach_counts(app_mod.incidents.records())) in html
        wb = warranty_buckets(app_mod.devices.records())
        assert str(wb["expired"]) in html
        assert "Скопје" in html and "30000" in html
    finally:
        _wipe_users()


def test_dashboard_empty_db_zeros(monkeypatch):
    app_mod = _env(monkeypatch, seed=False)
    try:
        r = app_mod.app.test_client().get("/")
        assert r.status_code == 200
        html = r.get_data(as_text=True)
        assert "Инциденти по статус" in html
        assert "MTTR" in html
    finally:
        _wipe_users()
