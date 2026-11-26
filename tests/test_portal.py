"""Tests for the Customer Self-Service Portal (/portal)."""

import os
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _setup_portal_env():
    import app as app_mod
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService
    from services.schemas import (
        DEV_COLS,
        EMP_COLS,
        INCIDENT_COLS,
        KB_COLS,
        REQUEST_COLS,
    )

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "portal_test.db")

    dev_store = DbStore(db, "devices", DEV_COLS)
    emp_store = DbStore(db, "employees", EMP_COLS)
    req_store = DbStore(db, "requests", REQUEST_COLS)
    inc_store = DbStore(db, "incidents", INCIDENT_COLS)
    hist_store = DbStore(db, "history", HISTORY_COLS)
    kb_store = DbStore(db, "kb_articles", KB_COLS)

    # Seed an employee and assigned device
    emp_store.append_row(
        {
            "EmployeeID": "EMP-001",
            "FirstName": "Александар",
            "LastName": "Македонски",
            "Department": "IT",
            "UserName": "alek",
            "Email": "alek@example.com",
        }
    )
    dev_store.append_row(
        {
            "AssetID": "AST-100",
            "Category": "Лаптоп",
            "Manufacturer": "Dell",
            "Model": "Latitude 5520",
            "SerialNumber": "SN-DELL-100",
            "Status": "Assigned",
            "EmployeeID": "EMP-001",
        }
    )
    # Seed a KB article for deflection testing
    kb_store.append_row(
        {
            "ArticleID": "KB-001",
            "Title": "Како да се поврзете на корпоративниот WiFi",
            "Category": "Мрежа",
            "Tags": "wifi internet bezicna mreza",
            "Body": "За поврзување на корпоративниот WiFi користете ги вашите кориснички податоци.",
            "Created": "2026-01-01",
            "Author": "admin",
            "Views": "0",
        }
    )

    return {
        "app_mod": app_mod,
        "db": db,
        "devices": dev_store,
        "employees": emp_store,
        "requests": req_store,
        "incidents": inc_store,
        "history": HistoryService(hist_store),
        "kb": kb_store,
    }


def test_portal_home_renders():
    env = _setup_portal_env()
    app_mod = env["app_mod"]

    with (
        mock.patch.object(app_mod, "devices", env["devices"]),
        mock.patch.object(app_mod, "employees", env["employees"]),
        mock.patch.object(app_mod, "requests", env["requests"]),
        mock.patch.object(app_mod, "incidents", env["incidents"]),
        mock.patch.object(app_mod, "history", env["history"]),
        mock.patch.object(app_mod, "kb_articles", env["kb"]),
        mock.patch.object(app_mod, "backup_all", lambda stores: None),
    ):
        client = app_mod.app.test_client()
        r = client.get("/portal")
        assert r.status_code == 200
        html = r.get_data(as_text=True)
        assert "Кориснички Портал" in html or "Здраво" in html
        assert "Барам нова опрема" in html
        assert "Пријави дефект" in html


def test_portal_submit_request():
    env = _setup_portal_env()
    app_mod = env["app_mod"]

    with (
        mock.patch.object(app_mod, "devices", env["devices"]),
        mock.patch.object(app_mod, "employees", env["employees"]),
        mock.patch.object(app_mod, "requests", env["requests"]),
        mock.patch.object(app_mod, "incidents", env["incidents"]),
        mock.patch.object(app_mod, "history", env["history"]),
        mock.patch.object(app_mod, "backup_all", lambda stores: None),
    ):
        client = app_mod.app.test_client()
        # Post valid request
        resp = client.post(
            "/portal/request",
            data={"need_text": "Ми треба нов безжичен глушец и тастатура."},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        recs = env["requests"].records()
        assert len(recs) == 1
        assert "безжичен глушец" in recs[0]["NeedText"]
        assert recs[0]["Status"] == "open"

        # Post empty request should fail validation
        resp_empty = client.post(
            "/portal/request",
            data={"need_text": ""},
            follow_redirects=True,
        )
        assert resp_empty.status_code == 200
        assert len(env["requests"].records()) == 1


def test_portal_submit_incident():
    env = _setup_portal_env()
    app_mod = env["app_mod"]

    with (
        mock.patch.object(app_mod, "devices", env["devices"]),
        mock.patch.object(app_mod, "employees", env["employees"]),
        mock.patch.object(app_mod, "requests", env["requests"]),
        mock.patch.object(app_mod, "incidents", env["incidents"]),
        mock.patch.object(app_mod, "history", env["history"]),
        mock.patch.object(app_mod, "backup_all", lambda stores: None),
        mock.patch.dict(app_mod.PATHS, {"db": env["db"]}),
    ):
        client = app_mod.app.test_client()
        # Post incident linked to asset
        resp = client.post(
            "/portal/incident",
            data={
                "title": "Екранот трепка и се гаси",
                "asset_id": "AST-100",
                "priority": "high",
                "notes": "Почна од утрово по ажурирање на Windows.",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        recs = env["incidents"].records()
        assert len(recs) == 1
        assert recs[0]["Title"] == "Екранот трепка и се гаси"
        assert recs[0]["AssetID"] == "AST-100"
        assert recs[0]["Priority"] == "high"


def test_portal_kb_deflection():
    env = _setup_portal_env()
    app_mod = env["app_mod"]

    with (
        mock.patch.object(app_mod, "kb_articles", env["kb"]),
    ):
        client = app_mod.app.test_client()

        # Query matching seeded KB
        resp = client.get("/portal/kb-suggest?q=wifi")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data.get("results", [])) == 1
        assert (
            data["results"][0]["title"] == "Како да се поврзете на корпоративниот WiFi"
        )
        assert "KB-001" == data["results"][0]["id"]

        # Empty query
        resp_blank = client.get("/portal/kb-suggest?q=")
        assert resp_blank.status_code == 200
        assert resp_blank.get_json().get("results") == []

        # Non-matching query
        resp_none = client.get("/portal/kb-suggest?q=nonexistentkwxyz")
        assert resp_none.status_code == 200
        assert resp_none.get_json().get("results") == []


def test_portal_incident_with_attachment_and_stepper():
    import io

    env = _setup_portal_env()
    app_mod = env["app_mod"]

    with (
        mock.patch.object(app_mod, "devices", env["devices"]),
        mock.patch.object(app_mod, "employees", env["employees"]),
        mock.patch.object(app_mod, "requests", env["requests"]),
        mock.patch.object(app_mod, "incidents", env["incidents"]),
        mock.patch.object(app_mod, "history", env["history"]),
        mock.patch.object(app_mod, "kb_articles", env["kb"]),
        mock.patch.object(app_mod, "backup_all", lambda stores: None),
        mock.patch.dict(app_mod.PATHS, {"db": env["db"]}),
    ):
        client = app_mod.app.test_client()
        resp = client.post(
            "/portal/incident",
            data={
                "title": "Грешка при стартување на програма",
                "asset_id": "AST-100",
                "priority": "medium",
                "notes": "Погледнете го скриншотот.",
                "file": (io.BytesIO(b"PNG_MOCK_BYTES"), "error_screenshot.png"),
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        recs = env["incidents"].records()
        assert len(recs) == 1
        iid = recs[0]["IncidentID"]

        # Verify attachment file saved
        from routes.incidents import _attach_dir
        attach_path = os.path.join(_attach_dir(iid), "error_screenshot.png")
        assert os.path.exists(attach_path)
        with open(attach_path, "rb") as fh:
            assert fh.read() == b"PNG_MOCK_BYTES"

        # Verify portal renders ticket stepper and dropzone
        home_resp = client.get("/portal")
        html = home_resp.get_data(as_text=True)
        assert "ticket-stepper" in html
        assert "portal-dropzone" in html
