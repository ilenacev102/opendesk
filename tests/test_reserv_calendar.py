"""F4: reservation conflict service + weekly calendar route."""

import datetime
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _monday():
    today = datetime.date.today()
    return today - datetime.timedelta(days=today.weekday())


def test_overlaps_boundary_touch_conflict():
    from services.reservation_service import overlaps

    assert overlaps("2026-10-10", "2026-10-12", "2026-10-12", "2026-10-14") is True
    assert overlaps("2026-10-10", "2026-10-12", "2026-10-11", "2026-10-20") is True
    assert overlaps("2026-10-10", "2026-10-11", "2026-10-13", "2026-10-14") is False


def test_overlaps_garbage_raises():
    from services.reservation_service import overlaps

    try:
        overlaps("garbage", "2026-10-12", "2026-10-12", "2026-10-14")
    except ValueError:
        pass
    else:
        raise AssertionError("невалиден датум мора да фрли ValueError")


def test_create_rejects_conflict():
    from services.db_service import DbStore
    from services.reservation_service import create
    from services.schemas import RESERV_COLS
    from utils.validators import ValidationError

    tmp = tempfile.mkdtemp()
    store = DbStore(os.path.join(tmp, "rsv.db"), "reservations", RESERV_COLS)
    rid = create(store, "A1", "2026-10-10", "2026-10-12")
    assert rid.startswith("R")
    try:
        create(store, "A1", "2026-10-12", "2026-10-14")
    except ValidationError:
        pass
    else:
        raise AssertionError("допир на граници мора да е одбиен")
    create(store, "A1", "2026-10-20", "2026-10-21")
    create(store, "A2", "2026-10-11", "2026-10-13")
    assert len(store.records()) == 3


def _env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.schemas import DEV_COLS, RESERV_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "rc.db")
    monkeypatch.setattr(
        app_mod, "reservations", DbStore(db, "reservations", RESERV_COLS)
    )
    monkeypatch.setattr(app_mod, "devices", DbStore(db, "devices", DEV_COLS))
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)
    return app_mod


def test_calendar_route_current_week(monkeypatch):
    app_mod = _env(monkeypatch)
    r = app_mod.app.test_client().get("/reservations/calendar")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Календар" in body
    assert _monday().isoformat() in body


def test_calendar_garbage_week_falls_back(monkeypatch):
    app_mod = _env(monkeypatch)
    r = app_mod.app.test_client().get("/reservations/calendar?week=garbage")
    assert r.status_code == 200
    assert _monday().isoformat() in r.get_data(as_text=True)


def test_calendar_places_reservation_in_day(monkeypatch):
    app_mod = _env(monkeypatch)
    monday = _monday()
    frm = monday + datetime.timedelta(days=1)
    to = monday + datetime.timedelta(days=2)
    app_mod.reservations.append_row(
        {
            "ReservationID": "R000001",
            "AssetID": "CAL01",
            "EmployeeID": "E1",
            "FromDate": frm.isoformat(),
            "ToDate": to.isoformat(),
            "Status": "active",
            "Notes": "",
        }
    )
    body = (
        app_mod.app.test_client().get("/reservations/calendar").get_data(as_text=True)
    )
    cells = re.findall(r'data-day="([^"]+)"(.*?)</td>', body, re.DOTALL)
    hit_days = [day for day, content in cells if "R000001" in content]
    assert hit_days == [frm.isoformat(), to.isoformat()]
