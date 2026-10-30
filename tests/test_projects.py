"""Phase 1: projects + issue types (Jira-like grouping for tickets)."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _stores():
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService
    from services.schemas import INCIDENT_COLS, ISSUE_TYPE_COLS, PROJECT_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "proj.db")
    projects = DbStore(db, "projects", PROJECT_COLS)
    types = DbStore(db, "issue_types", ISSUE_TYPE_COLS)
    incidents = DbStore(db, "incidents", INCIDENT_COLS)
    history = HistoryService(DbStore(db, "history", HISTORY_COLS))
    return projects, types, incidents, history


def test_create_project_normalizes_key():
    from services.project_service import create_project

    projects, _types, _incidents, history = _stores()
    p = create_project(projects, history, "Маркетинг", "mkt", lead="admin")
    assert p["Key"] == "MKT"
    assert p["Status"] == "active"
    assert p["ProjectID"].startswith("PRJ")
    assert p["Name"] == "Маркетинг"


def test_duplicate_key_rejected():
    from services.project_service import create_project
    from utils.validators import ValidationError

    projects, _types, _incidents, history = _stores()
    create_project(projects, history, "Прв", "ops")
    try:
        create_project(projects, history, "Втор", "OPS")
    except ValidationError:
        pass
    else:
        raise AssertionError("дупликат клуч мора да е одбиен")
    assert len(projects.records()) == 1


def test_bad_key_rejected():
    from services.project_service import create_project
    from utils.validators import ValidationError

    projects, _types, _incidents, history = _stores()
    for bad in ("X", "AB CD", "12AB", "АБВ"):
        try:
            create_project(projects, history, "Име", bad)
        except ValidationError:
            continue
        raise AssertionError(f"невалиден клуч мора да е одбиен: {bad}")
    assert projects.records() == []


def test_ensure_defaults_idempotent():
    from services.project_service import ensure_defaults

    projects, types, incidents, _history = _stores()
    first = ensure_defaults(projects, types, incidents)
    second = ensure_defaults(projects, types, incidents)
    assert first["types_created"] == 5
    assert second["types_created"] == 0
    assert len(projects.records()) == 1
    assert len(types.records()) == 5
    assert first["project"]["Key"] == "IT"


def test_ensure_backfills_existing_incidents():
    from services.project_service import ensure_defaults

    projects, types, incidents, _history = _stores()
    for i in range(1, 4):
        incidents.append_row(
            {"IncidentID": f"I-{i:06d}", "Title": f"t{i}", "Status": "open"}
        )
    out = ensure_defaults(projects, types, incidents)
    assert out["backfilled"] == 3
    for row in incidents.records():
        assert row["ProjectID"] == out["project"]["ProjectID"]
        assert row["TypeID"] != ""
    again = ensure_defaults(projects, types, incidents)
    assert again["backfilled"] == 0


def test_validate_type_wrong_project_rejected():
    from services.project_service import (
        create_project,
        ensure_defaults,
        validate_type,
    )
    from utils.validators import ValidationError

    projects, types, incidents, history = _stores()
    out = ensure_defaults(projects, types, incidents)
    other = create_project(projects, history, "Друг", "drz")
    inc_type = out["incident_type"]
    try:
        validate_type(inc_type["TypeID"], other["ProjectID"], types)
    except ValidationError:
        pass
    else:
        raise AssertionError("тип од друг проект мора да е одбиен")
    ok = validate_type(inc_type["TypeID"], out["project"]["ProjectID"], types)
    assert ok["Name"] == "Incident"


def test_workflow_columns_known_and_unknown():
    from services.project_service import workflow_columns
    from utils.validators import ValidationError

    assert workflow_columns("incident") == ("open", "in-progress", "resolved")
    try:
        workflow_columns("nope")
    except ValidationError:
        pass
    else:
        raise AssertionError("непознат workflow мора да е одбиен")


def _ui_env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService
    from services.schemas import INCIDENT_COLS, ISSUE_TYPE_COLS, PROJECT_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "proj_ui.db")
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


def test_projects_page_renders(monkeypatch):
    from services import ratelimit as rl

    rl.reset()
    app_mod = _ui_env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        c.post("/login", data={"username": "cit", "password": "dolgapass123"})
        r = c.get("/projects")
        assert r.status_code == 200
        body = r.get_data(as_text=True)
        assert "Проекти" in body
        assert "IT ServiceDesk" in body
    finally:
        _wipe_users()


def test_post_project_admin_ok_citac_forbidden(monkeypatch):
    from services import ratelimit as rl

    rl.reset()
    app_mod = _ui_env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        c.post("/login", data={"username": "cit", "password": "dolgapass123"})
        denied = c.post("/projects", data={"name": "Оддел", "key": "odd"})
        assert denied.status_code == 403
        c.post("/login", data={"username": "adm", "password": "dolgapass123"})
        r = c.post("/projects", data={"name": "Оддел", "key": "odd", "lead": "adm"})
        assert r.status_code == 302
        assert app_mod.projects.find("Key", "ODD") is not None
    finally:
        _wipe_users()


def test_project_detail_renders(monkeypatch):
    from services import ratelimit as rl

    rl.reset()
    app_mod = _ui_env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        c.post("/login", data={"username": "cit", "password": "dolgapass123"})
        c.get("/projects")
        default = app_mod.projects.find("Key", "IT")
        assert default is not None
        r = c.get(f"/projects/{default['ProjectID']}")
        assert r.status_code == 200
        body = r.get_data(as_text=True)
        assert "IT ServiceDesk" in body
        assert "Incident" in body
    finally:
        _wipe_users()
