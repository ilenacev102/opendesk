"""Phase 5: project settings, dashboard stats, template export/import."""

import io
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _stats_rows():
    return [
        {
            "ProjectID": "P1",
            "Status": "open",
            "DueDate": "2026-10-01",
            "Created": "2026-09-01 10:00:00",
        },
        {
            "ProjectID": "P1",
            "Status": "in-progress",
            "DueDate": "",
            "Created": "2026-08-01 09:00:00",
        },
        {
            "ProjectID": "P1",
            "Status": "resolved",
            "DueDate": "2026-09-01",
            "Created": "2026-07-01 09:00:00",
        },
        {
            "ProjectID": "P2",
            "Status": "open",
            "DueDate": "2026-12-01",
            "Created": "2026-10-01 08:00:00",
        },
        {"ProjectID": "", "Status": "open", "DueDate": "bad", "Created": ""},
    ]


def test_by_project_stats():
    import datetime

    from services.analytics_service import by_project

    today = datetime.date(2026, 10, 5)
    out = by_project(_stats_rows(), today=today)
    p1 = out["P1"]
    assert p1["total"] == 3
    assert p1["open"] == 2
    assert p1["closed"] == 1
    assert p1["breached"] == 1
    assert p1["oldest_open"] == "2026-08-01 09:00:00"
    p2 = out["P2"]
    assert p2["total"] == 1
    assert p2["breached"] == 0
    assert out["—"]["total"] == 1


def _ui_env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService
    from services.schemas import INCIDENT_COLS, ISSUE_TYPE_COLS, PROJECT_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "prjadmin.db")
    monkeypatch.setattr(app_mod, "projects", DbStore(db, "projects", PROJECT_COLS))
    monkeypatch.setattr(
        app_mod, "project_types", DbStore(db, "issue_types", ISSUE_TYPE_COLS)
    )
    monkeypatch.setattr(app_mod, "incidents", DbStore(db, "incidents", INCIDENT_COLS))
    monkeypatch.setattr(
        app_mod,
        "history",
        HistoryService(DbStore(db, "history", HISTORY_COLS)),
    )
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)
    app_mod.auth_svc.create_user("adm", "dolgapass123", role="admin")
    app_mod.auth_svc.create_user("cit", "dolgapass123", role="citac")
    return app_mod


def _wipe_users():
    import sqlite3

    import app as app_mod

    con = sqlite3.connect(app_mod.DB_PATH)
    con.execute("DELETE FROM users")
    con.commit()
    con.close()


def _login(app_mod, username="adm"):
    c = app_mod.app.test_client()
    c.post("/login", data={"username": username, "password": "dolgapass123"})
    return c


def test_settings_requires_admin(monkeypatch):
    from services import ratelimit as rl

    rl.reset()
    app_mod = _ui_env(monkeypatch)
    try:
        c = _login(app_mod, "cit")
        c.get("/projects")
        default = app_mod.projects.find("Key", "IT")
        assert default is not None
        pid = default["ProjectID"]
        r = c.get(f"/projects/{pid}/settings")
        assert r.status_code == 403
        a = _login(app_mod, "adm")
        r = a.get(f"/projects/{pid}/settings")
        assert r.status_code == 200
        body = r.get_data(as_text=True)
        assert "Поставки" in body
        assert "Колони на табла" in body
    finally:
        _wipe_users()


def test_settings_rename_post(monkeypatch):
    from services import ratelimit as rl

    rl.reset()
    app_mod = _ui_env(monkeypatch)
    try:
        c = _login(app_mod, "adm")
        c.get("/projects")
        default = app_mod.projects.find("Key", "IT")
        assert default is not None
        pid = default["ProjectID"]
        r = c.post(
            f"/projects/{pid}/settings",
            data={"name": "Нов назив", "lead": "ana", "description": "опис"},
        )
        assert r.status_code == 302
        row = app_mod.projects.find("ProjectID", pid)
        assert row is not None
        assert row["Name"] == "Нов назив"
        assert row["Lead"] == "ana"
        assert row["Description"] == "опис"
    finally:
        _wipe_users()


def test_export_valid_json(monkeypatch):
    from services import ratelimit as rl

    rl.reset()
    app_mod = _ui_env(monkeypatch)
    try:
        c = _login(app_mod, "adm")
        c.get("/projects")
        default = app_mod.projects.find("Key", "IT")
        assert default is not None
        pid = default["ProjectID"]
        r = c.get(f"/projects/{pid}/export")
        assert r.status_code == 200
        assert "attachment" in r.headers.get("Content-Disposition", "")
        payload = json.loads(r.get_data(as_text=True))
        assert payload["key"] == "IT"
        assert len(payload["types"]) == 5
        names = {t["name"] for t in payload["types"]}
        assert "Incident" in names
    finally:
        _wipe_users()


def test_import_creates_project_with_types(monkeypatch):
    from services import ratelimit as rl

    rl.reset()
    app_mod = _ui_env(monkeypatch)
    try:
        c = _login(app_mod, "adm")
        c.get("/projects")
        payload = {
            "name": "Клон проект",
            "key": "IT",
            "lead": "ana",
            "description": "од шаблон",
            "types": [
                {
                    "name": "Incident",
                    "workflow": "incident",
                    "default_priority": "high",
                },
                {"name": "Задача", "workflow": "task", "default_priority": "low"},
            ],
        }
        body = json.dumps(payload, ensure_ascii=False)
        buf = io.BytesIO(body.encode("utf-8"))
        r = c.post(
            "/projects/import",
            data={"file": (buf, "tpl.json")},
            content_type="multipart/form-data",
        )
        assert r.status_code == 302
        clones = [
            p for p in app_mod.projects.records() if p.get("Name") == "Клон проект"
        ]
        assert len(clones) == 1
        cid = clones[0]["ProjectID"]
        assert clones[0]["Key"] != "IT"
        types = [
            t for t in app_mod.project_types.records() if t.get("ProjectID") == cid
        ]
        assert len(types) == 2
        workflows = {t["Workflow"] for t in types}
        assert workflows == {"incident", "task"}

        buf2 = io.BytesIO(body.encode("utf-8"))
        r = c.post(
            "/projects/import",
            data={"file": (buf2, "tpl.json")},
            content_type="multipart/form-data",
        )
        assert r.status_code == 302
        clones2 = [
            p for p in app_mod.projects.records() if p.get("Name") == "Клон проект"
        ]
        assert len(clones2) == 2
        assert len({p["Key"] for p in clones2}) == 2
    finally:
        _wipe_users()


def test_import_invalid_json_400(monkeypatch):
    from services import ratelimit as rl

    rl.reset()
    app_mod = _ui_env(monkeypatch)
    try:
        c = _login(app_mod, "adm")
        r = c.post(
            "/projects/import",
            data={"file": (io.BytesIO(b"{oops"), "bad.json")},
            content_type="multipart/form-data",
        )
        assert r.status_code == 400
    finally:
        _wipe_users()


def test_dashboard_columns(monkeypatch):
    from services import ratelimit as rl

    rl.reset()
    app_mod = _ui_env(monkeypatch)
    try:
        c = _login(app_mod, "cit")
        r = c.get("/projects")
        assert r.status_code == 200
        body = r.get_data(as_text=True)
        assert "Пробиени" in body
        assert "Најстари отворен" in body
        assert "Затворени" in body
    finally:
        _wipe_users()


def test_type_toggle_and_no_resurrect(monkeypatch):
    from services import ratelimit as rl

    rl.reset()
    app_mod = _ui_env(monkeypatch)
    try:
        c = _login(app_mod, "adm")
        c.get("/projects")
        default = app_mod.projects.find("Key", "IT")
        assert default is not None
        pid = default["ProjectID"]
        tid = next(
            t["TypeID"]
            for t in app_mod.project_types.records()
            if t["ProjectID"] == pid and t["Name"] == "Task"
        )
        r = c.post(f"/projects/{pid}/types/{tid}/toggle")
        assert r.status_code == 302
        trow = app_mod.project_types.find("TypeID", tid)
        assert trow is not None
        assert trow["Active"] == "NO"

        c.get("/projects")
        trow = app_mod.project_types.find("TypeID", tid)
        assert trow is not None
        assert trow["Active"] == "NO"

        c.post(f"/projects/{pid}/types/{tid}/toggle")
        trow = app_mod.project_types.find("TypeID", tid)
        assert trow is not None
        assert trow["Active"] == "YES"
    finally:
        _wipe_users()
