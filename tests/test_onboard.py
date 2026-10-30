"""MS-5: HR intake validation + submit."""

import os
import sys
import tempfile
from datetime import date, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.validators import ValidationError

PKGS = [{"id": "std", "name": "Стандард"}, {"id": "dev", "name": "Девелопер"}]


def _svc():
    from services.db_service import DbStore
    from services.onboard_service import OnboardService
    from services.schemas import ONBOARD_COLS

    tmp = tempfile.mkdtemp()
    store = DbStore(os.path.join(tmp, "ob.db"), "onboard", ONBOARD_COLS)
    return OnboardService(store, PKGS), store


def _req(**kw):
    base = {
        "FullName": "Јана Јаневска",
        "Position": "Сметководство",
        "StartDate": (date.today() + timedelta(days=5)).isoformat(),
        "Package": "std",
        "RequestedBy": "hr",
    }
    base.update(kw)
    return base


def test_valid_submit_ok():
    svc, store = _svc()
    row = svc.submit(_req())
    assert row["RequestID"].startswith("OB")
    assert store.find("RequestID", row["RequestID"]) is not None


def test_start_tomorrow_rejected():
    svc, store = _svc()
    with pytest.raises(ValidationError):
        svc.submit(_req(StartDate=(date.today() + timedelta(days=1)).isoformat()))


def test_unknown_package_rejected():
    svc, store = _svc()
    with pytest.raises(ValidationError):
        svc.submit(_req(Package="nope"))


def test_duplicate_request_rejected():
    svc, store = _svc()
    store.append_row(
        {
            "RequestID": "OB000001",
            "FullName": "Постоечки",
            "Position": "",
            "StartDate": (date.today() + timedelta(days=5)).isoformat(),
            "Package": "std",
            "RequestedBy": "hr",
        }
    )
    with pytest.raises(ValidationError):
        svc.submit(_req(RequestID="OB000001"))


def test_onboard_page_renders_and_confirms(monkeypatch):
    from services import ratelimit as rl

    rl.reset()
    import app as app_mod

    app_mod.auth_svc.create_user("mag", "dolgapass123", role="magacioner")
    try:
        c = app_mod.app.test_client()
        c.post("/login", data={"username": "mag", "password": "dolgapass123"})
        assert c.get("/onboard").status_code == 200
        assert "Нов вработен" in c.get("/onboard").get_data(as_text=True)
        start = (date.today() + timedelta(days=5)).isoformat()
        r = c.post(
            "/onboard",
            data={
                "action": "confirm",
                "FullName": "Тест Тестов",
                "Position": "",
                "StartDate": start,
                "Package": "nov-vraboten-standard",
                "RequestedBy": "hr",
            },
        )
        assert r.status_code == 302
    finally:
        import sqlite3

        con = sqlite3.connect(app_mod.DB_PATH)
        con.execute("DELETE FROM users")
        con.commit()
        con.close()
