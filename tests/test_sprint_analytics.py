"""Sprint 6: sprint analytics — velocity (committed vs completed) + /analytics page."""

import os
import sqlite3
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.schemas import INCIDENT_COLS, SPRINT_COLS


def _store(db, table, cols):
    from services.db_service import DbStore

    return DbStore(db, table, cols)


def _db():
    return os.path.join(tempfile.mkdtemp(), "analytics.db")


def _mk_sprint(
    sprints, name="SP", start="2026-10-01", end="2026-10-04", status="planned"
):
    from services import sprint_service

    row = sprint_service.create(sprints, "PRJ-1", name, start, end, goal="цел")
    if status != "planned":
        sprints.update_where("SprintID", row["SprintID"], {"Status": status})
    return row


def _add_ticket(incidents, iid, sprint_id, status="open", points="5"):
    incidents.append_row(
        {
            "IncidentID": iid,
            "Title": f"тикет {iid}",
            "Status": status,
            "ProjectID": "PRJ-1",
            "SprintID": sprint_id,
            "StoryPoints": points,
            "ClosedAt": "2026-10-02 10:00:00" if status == "resolved" else "",
        }
    )


def test_velocity_sums_committed_and_completed_points():
    """Committed = total points of tickets ever bound to the sprint; completed = points of tickets still bound and resolved."""
    from services import sprint_service

    db = _db()
    sprints = _store(db, "sprints", SPRINT_COLS)
    incidents = _store(db, "incidents", INCIDENT_COLS)
    sp = _mk_sprint(sprints, name="SP1", status="completed")
    _add_ticket(incidents, "I-1", sp["SprintID"], status="resolved", points="5")
    _add_ticket(incidents, "I-2", sp["SprintID"], status="open", points="3")
    _add_ticket(incidents, "I-3", sp["SprintID"], status="resolved", points="2")

    rows = sprint_service.velocity(sprints, incidents)
    assert len(rows) == 1
    row = rows[0]
    assert row["SprintID"] == sp["SprintID"]
    assert row["Committed"] == 10
    assert row["Completed"] == 7


def test_velocity_includes_unplanned_carried_tickets_in_committed():
    """Tickets completed late but still bound at sprint completion stay counted."""
    from services import sprint_service

    db = _db()
    sprints = _store(db, "sprints", SPRINT_COLS)
    incidents = _store(db, "incidents", INCIDENT_COLS)
    sp = _mk_sprint(sprints, name="SP2", status="completed")
    _add_ticket(incidents, "I-9", sp["SprintID"], status="resolved", points="8")

    rows = sprint_service.velocity(sprints, incidents)
    assert rows[0]["Committed"] == 8
    assert rows[0]["Completed"] == 8


def test_velocity_ignores_active_and_planned_sprints():
    from services import sprint_service

    db = _db()
    sprints = _store(db, "sprints", SPRINT_COLS)
    incidents = _store(db, "incidents", INCIDENT_COLS)
    _mk_sprint(sprints, name="SP-act", status="active")
    _mk_sprint(sprints, name="SP-plan", status="planned")
    _add_ticket(incidents, "I-5", "", status="open", points="5")

    assert sprint_service.velocity(sprints, incidents) == []


def test_velocity_orders_completed_sprints_by_end_date():
    from services import sprint_service

    db = _db()
    sprints = _store(db, "sprints", SPRINT_COLS)
    incidents = _store(db, "incidents", INCIDENT_COLS)
    later = _mk_sprint(
        sprints,
        name="SP-late",
        start="2026-11-01",
        end="2026-11-05",
        status="completed",
    )
    earlier = _mk_sprint(sprints, name="SP-early", status="completed")

    rows = sprint_service.velocity(sprints, incidents)
    assert [r["SprintID"] for r in rows] == [earlier["SprintID"], later["SprintID"]]


def test_garbage_points_treated_as_zero():
    from services import sprint_service

    db = _db()
    sprints = _store(db, "sprints", SPRINT_COLS)
    incidents = _store(db, "incidents", INCIDENT_COLS)
    sp = _mk_sprint(sprints, name="SP3", status="completed")
    _add_ticket(incidents, "I-7", sp["SprintID"], status="resolved", points="abc")
    _add_ticket(incidents, "I-8", sp["SprintID"], status="resolved", points="3")

    rows = sprint_service.velocity(sprints, incidents)
    assert rows[0]["Committed"] == 3
    assert rows[0]["Completed"] == 3


@pytest.fixture()
def web_env(monkeypatch):
    """Flask app wired to temp stores with one completed sprint (10 committed, 7 completed)."""
    import app as app_mod
    from services import ratelimit as rl
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService
    from services.schemas import ISSUE_TYPE_COLS, PROJECT_COLS

    rl.reset()
    db = _db()
    sprints = _store(db, "sprints", SPRINT_COLS)
    incidents = _store(db, "incidents", INCIDENT_COLS)
    sp = _mk_sprint(sprints, name="SPX", status="completed")
    _add_ticket(incidents, "I-1", sp["SprintID"], status="resolved", points="5")
    _add_ticket(incidents, "I-2", sp["SprintID"], status="open", points="3")
    _add_ticket(incidents, "I-3", sp["SprintID"], status="resolved", points="2")

    monkeypatch.setattr(app_mod, "sprints", sprints)
    monkeypatch.setattr(app_mod, "incidents", incidents)
    monkeypatch.setattr(app_mod, "projects", DbStore(db, "projects", PROJECT_COLS))
    monkeypatch.setattr(
        app_mod, "project_types", DbStore(db, "issue_types", ISSUE_TYPE_COLS)
    )
    monkeypatch.setattr(
        app_mod, "history", HistoryService(DbStore(db, "history", HISTORY_COLS))
    )
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)

    app_mod.auth_svc.create_user("admin", "dolgapass123", role="admin")

    def _wipe():
        con = sqlite3.connect(app_mod.DB_PATH)
        con.execute("DELETE FROM users")
        con.commit()
        con.close()

    try:
        yield {
            "app": app_mod,
            "sprints": sprints,
            "incidents": incidents,
            "sprint_id": sp["SprintID"],
        }
    finally:
        _wipe()


def _login(client):
    client.post("/login", data={"username": "admin", "password": "dolgapass123"})


def test_analytics_page_renders_completed_sprint(web_env):
    client = web_env["app"].app.test_client()
    _login(client)
    r = client.get(f"/sprints/{web_env['sprint_id']}/analytics")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Burndown" in body
    assert "Velocity" in body
    assert web_env["sprint_id"] in body


def test_analytics_unknown_sprint_404(web_env):
    client = web_env["app"].app.test_client()
    _login(client)
    assert client.get("/sprints/NOPE/analytics").status_code == 404


def test_analytics_includes_burndown_data_for_canvas(web_env):
    client = web_env["app"].app.test_client()
    _login(client)
    r = client.get(f"/sprints/{web_env['sprint_id']}/analytics")
    body = r.get_data(as_text=True)
    # chart payload serialised for the vanilla JS canvas renderer
    assert "sdBurndown" in body
    assert "sdVelocity" in body


def test_analytics_requires_login(web_env):
    client = web_env["app"].app.test_client()
    r = client.get(f"/sprints/{web_env['sprint_id']}/analytics")
    assert r.status_code in (302, 401)
