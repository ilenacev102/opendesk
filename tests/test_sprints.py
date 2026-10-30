"""Phase 3: sprints — create/start/complete/move/backlog/burndown."""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.schemas import INCIDENT_COLS, SPRINT_COLS


def _db():
    return os.path.join(tempfile.mkdtemp(), "sprint.db")


def _store(db, table, cols):
    from services.db_service import DbStore

    return DbStore(db, table, cols)


def _mk(sprints, project="PRJ-1", start="2026-10-01", end="2026-10-04", name="SP1"):
    from services import sprint_service

    return sprint_service.create(sprints, project, name, start, end, goal="цел")


def _add_incident(incidents, iid, project="PRJ-1", status="open", **extra):
    row = {
        "IncidentID": iid,
        "Title": f"тикет {iid}",
        "Status": status,
        "ProjectID": project,
        "Assignee": "ana",
    }
    row.update(extra)
    incidents.append_row(row)
    return row


def test_create_rejects_end_before_or_equal_start():
    from services import sprint_service
    from utils.validators import ValidationError

    sprints = _store(_db(), "sprints", SPRINT_COLS)
    with pytest.raises(ValidationError):
        sprint_service.create(sprints, "PRJ-1", "SP1", "2026-10-10", "2026-10-01")
    with pytest.raises(ValidationError):
        sprint_service.create(sprints, "PRJ-1", "SP1", "2026-10-01", "2026-10-01")
    with pytest.raises(ValidationError):
        sprint_service.create(sprints, "PRJ-1", "SP1", "не-датум", "2026-10-05")
    with pytest.raises(ValidationError):
        sprint_service.create(sprints, "PRJ-1", "  ", "2026-10-01", "2026-10-04")
    assert sprints.records() == []


def test_two_active_sprints_rejected():
    from services import sprint_service
    from utils.validators import ValidationError

    db = _db()
    sprints = _store(db, "sprints", SPRINT_COLS)
    incidents = _store(db, "incidents", INCIDENT_COLS)
    s1 = _mk(sprints, name="SP1")
    sprint_service.start(sprints, incidents, s1["SprintID"])
    assert sprints.find("SprintID", s1["SprintID"])["Status"] == "active"
    s2 = _mk(sprints, start="2026-10-05", end="2026-10-18", name="SP2")
    with pytest.raises(ValidationError):
        sprint_service.start(sprints, incidents, s2["SprintID"])


def test_start_activates_and_binds_backlog():
    from services import sprint_service

    db = _db()
    sprints = _store(db, "sprints", SPRINT_COLS)
    incidents = _store(db, "incidents", INCIDENT_COLS)
    _add_incident(incidents, "I-1", status="open", Rank="2")
    _add_incident(incidents, "I-2", status="in-progress", Rank="1")
    _add_incident(incidents, "I-3", status="resolved")
    _add_incident(incidents, "I-4", project="PRJ-2", status="open")
    sp = _mk(sprints)

    bound = sprint_service.start(sprints, incidents, sp["SprintID"])
    assert bound == 2
    assert sprints.find("SprintID", sp["SprintID"])["Status"] == "active"
    assert incidents.find("IncidentID", "I-1")["SprintID"] == sp["SprintID"]
    assert incidents.find("IncidentID", "I-2")["SprintID"] == sp["SprintID"]
    assert incidents.find("IncidentID", "I-3")["SprintID"] == ""
    assert incidents.find("IncidentID", "I-4")["SprintID"] == ""


def test_complete_returns_unresolved_keeps_resolved_no_loss():
    from services import sprint_service

    db = _db()
    sprints = _store(db, "sprints", SPRINT_COLS)
    incidents = _store(db, "incidents", INCIDENT_COLS)
    _add_incident(incidents, "I-1", status="open")
    _add_incident(incidents, "I-2", status="open")
    sp = _mk(sprints)
    sprint_service.start(sprints, incidents, sp["SprintID"])
    incidents.update_where(
        "IncidentID", "I-2", {"Status": "resolved", "ClosedAt": "2026-10-03 12:00"}
    )

    moved = sprint_service.complete(sprints, incidents, sp["SprintID"])
    assert moved == 1
    assert sprints.find("SprintID", sp["SprintID"])["Status"] == "completed"
    assert incidents.find("IncidentID", "I-1")["SprintID"] == ""
    assert incidents.find("IncidentID", "I-2")["SprintID"] == sp["SprintID"]
    assert len(incidents.records()) == 2


def test_move_resolved_rejected_open_ok():
    from services import sprint_service
    from utils.validators import ValidationError

    db = _db()
    sprints = _store(db, "sprints", SPRINT_COLS)
    incidents = _store(db, "incidents", INCIDENT_COLS)
    _add_incident(incidents, "I-1", status="resolved")
    _add_incident(incidents, "I-2", status="open")
    _add_incident(incidents, "I-3", project="PRJ-2", status="open")
    sp = _mk(sprints)

    with pytest.raises(ValidationError):
        sprint_service.move_to_sprint(incidents, sprints, "I-1", sp["SprintID"])
    with pytest.raises(ValidationError):
        sprint_service.move_to_sprint(incidents, sprints, "I-3", sp["SprintID"])
    sprint_service.move_to_sprint(incidents, sprints, "I-2", sp["SprintID"])
    assert incidents.find("IncidentID", "I-2")["SprintID"] == sp["SprintID"]


def test_burndown_exact_remaining_per_day():
    from services import sprint_service

    db = _db()
    sprints = _store(db, "sprints", SPRINT_COLS)
    incidents = _store(db, "incidents", INCIDENT_COLS)
    sp = _mk(sprints)
    _add_incident(
        incidents,
        "I-1",
        status="resolved",
        SprintID=sp["SprintID"],
        StoryPoints="3",
        Created="2026-09-30 10:00",
        ClosedAt="2026-10-03 12:00",
    )
    _add_incident(
        incidents,
        "I-2",
        status="open",
        SprintID=sp["SprintID"],
        StoryPoints="2",
        Created="2026-10-02 09:00",
    )

    chart = sprint_service.burndown(sprints, incidents, sp["SprintID"])
    assert chart["days"] == [
        "2026-10-01",
        "2026-10-02",
        "2026-10-03",
        "2026-10-04",
    ]
    assert chart["remaining"] == [3, 5, 2, 2]
    assert chart["total"] == 5
    assert chart["ideal"][0] == 5.0
    assert chart["ideal"][-1] == 0.0


def test_backlog_sorted_by_rank_garbage_last():
    from services import sprint_service

    incidents = _store(_db(), "incidents", INCIDENT_COLS)
    _add_incident(incidents, "I-1", Rank="5")
    _add_incident(incidents, "I-2", Rank="1")
    _add_incident(incidents, "I-3", Rank="abc")
    _add_incident(incidents, "I-4", Rank="")
    rows = sprint_service.backlog(incidents, "PRJ-1")
    assert [r["IncidentID"] for r in rows] == ["I-2", "I-1", "I-3", "I-4"]


def _ui_env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService
    from services.schemas import ISSUE_TYPE_COLS, PROJECT_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "sprintui.db")
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


def _login(app_mod, username="cit"):
    c = app_mod.app.test_client()
    c.post("/login", data={"username": username, "password": "dolgapass123"})
    return c


def test_backlog_route_200_and_role_guard(monkeypatch):
    from services import ratelimit as rl

    rl.reset()
    app_mod = _ui_env(monkeypatch)
    try:
        c = _login(app_mod, "cit")
        c.get("/projects")
        pid = app_mod.projects.find("Key", "IT")["ProjectID"]
        r = c.get(f"/projects/{pid}/backlog")
        assert r.status_code == 200
        body = r.get_data(as_text=True)
        assert "Backlog" in body
        r = c.post(
            f"/projects/{pid}/sprints",
            data={
                "name": "SP",
                "start_date": "2026-10-01",
                "end_date": "2026-10-14",
            },
        )
        assert r.status_code == 403
        a = _login(app_mod, "adm")
        r = a.post(
            f"/projects/{pid}/sprints",
            data={
                "name": "SP1",
                "start_date": "2026-10-01",
                "end_date": "2026-10-14",
                "goal": "цел",
            },
        )
        assert r.status_code == 302
        assert any(s["Name"] == "SP1" for s in app_mod.sprints.records())
        sid = next(
            s["SprintID"] for s in app_mod.sprints.records() if s["Name"] == "SP1"
        )
        r = a.get(f"/sprints/{sid}")
        assert r.status_code == 200
        assert "SP1" in r.get_data(as_text=True)
    finally:
        _wipe_users()
