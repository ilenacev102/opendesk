"""Phase 2: Kanban board — grouping, filters, routes."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _issues():
    return [
        {
            "IncidentID": "I-1",
            "Title": "a",
            "Status": "open",
            "Priority": "high",
            "Assignee": "ana",
            "TypeID": "TY1",
            "StoryPoints": "3",
        },
        {
            "IncidentID": "I-2",
            "Title": "b",
            "Status": "in-progress",
            "Priority": "low",
            "Assignee": "bob",
            "TypeID": "TY2",
            "StoryPoints": "",
        },
        {
            "IncidentID": "I-3",
            "Title": "c",
            "Status": "resolved",
            "Priority": "medium",
            "Assignee": "ana",
            "TypeID": "TY1",
            "StoryPoints": "5",
        },
    ]


def test_group_three_statuses_exact_counts():
    from services.board_service import columns_for, group_issues

    cols = columns_for("incident")
    groups = group_issues(_issues(), cols)
    assert [len(groups[c]) for c in cols] == [1, 1, 1]
    assert groups["open"][0]["IncidentID"] == "I-1"
    assert groups["resolved"][0]["IncidentID"] == "I-3"


def test_unknown_status_falls_to_first_column():
    from services.board_service import columns_for, group_issues

    cols = columns_for("incident")
    rows = _issues() + [
        {"IncidentID": "I-4", "Title": "d", "Status": "weird"},
        {"IncidentID": "I-5", "Title": "e", "Status": ""},
    ]
    groups = group_issues(rows, cols)
    assert len(groups["open"]) == 3
    assert sum(len(v) for v in groups.values()) == 5


def test_apply_filters_equality():
    from services.board_service import apply_filters

    rows = _issues()
    assert len(apply_filters(rows)) == 3
    assert len(apply_filters(rows, assignee="ana")) == 2
    assert len(apply_filters(rows, assignee="ana", itype="TY1")) == 2
    assert len(apply_filters(rows, itype="TY2")) == 1
    assert len(apply_filters(rows, priority="high")) == 1
    assert len(apply_filters(rows, assignee="ana", priority="high")) == 1


def test_board_payload_shape_and_points():
    from services.board_service import board_payload

    payload = board_payload(_issues(), "incident", {})
    assert payload["total"] == 3
    assert [c["count"] for c in payload["columns"]] == [1, 1, 1]
    assert payload["columns"][0]["points"] == 3
    assert payload["columns"][1]["points"] == 0
    assert payload["columns"][2]["points"] == 5
    assert payload["columns"][0]["name"] == "open"


def test_columns_for_unknown_workflow_rejected():
    from services.board_service import columns_for
    from utils.validators import ValidationError

    try:
        columns_for("nope")
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
    db = os.path.join(tmp, "board.db")
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


def test_project_board_renders(monkeypatch):
    from services import ratelimit as rl

    rl.reset()
    app_mod = _ui_env(monkeypatch)
    try:
        c = _login(app_mod)
        r = c.get("/projects/PRJ-NOPE/board")
        assert r.status_code == 404
        c.get("/my-board")
        default = app_mod.projects.find("Key", "IT")
        assert default is not None
        pid = default["ProjectID"]
        r = c.get(f"/projects/{pid}/board")
        assert r.status_code == 200
        body = r.get_data(as_text=True)
        assert "Канбан" in body
        assert "нема тикети" in body
        app_mod.incidents.append_row(
            {
                "IncidentID": "I-100",
                "Title": "прв тикет",
                "Status": "open",
                "Priority": "high",
                "Assignee": "cit",
                "ProjectID": pid,
            }
        )
        r = c.get(f"/projects/{pid}/board")
        body = r.get_data(as_text=True)
        assert "прв тикет" in body
        assert "I-100" in body
    finally:
        _wipe_users()


def test_board_mine_filter(monkeypatch):
    from services import ratelimit as rl

    rl.reset()
    app_mod = _ui_env(monkeypatch)
    try:
        c = _login(app_mod)
        app_mod.incidents.append_row(
            {"IncidentID": "I-101", "Title": "мој", "Status": "open", "Assignee": "cit"}
        )
        app_mod.incidents.append_row(
            {
                "IncidentID": "I-102",
                "Title": "туѓ",
                "Status": "open",
                "Assignee": "ana",
            }
        )
        r = c.get("/my-board")
        body = r.get_data(as_text=True)
        assert r.status_code == 200
        assert "мој" in body
        assert "I-102" not in body
    finally:
        _wipe_users()


def test_project_board_mine_query(monkeypatch):
    from services import ratelimit as rl

    rl.reset()
    app_mod = _ui_env(monkeypatch)
    try:
        c = _login(app_mod)
        c.get("/projects")
        pid = app_mod.projects.find("Key", "IT")["ProjectID"]
        app_mod.incidents.append_row(
            {
                "IncidentID": "I-103",
                "Title": "мој на табла",
                "Status": "open",
                "Assignee": "cit",
                "ProjectID": pid,
            }
        )
        app_mod.incidents.append_row(
            {
                "IncidentID": "I-104",
                "Title": "туѓ на табла",
                "Status": "open",
                "Assignee": "ana",
                "ProjectID": pid,
            }
        )
        r = c.get(f"/projects/{pid}/board?mine=1")
        body = r.get_data(as_text=True)
        assert r.status_code == 200
        assert "мој на табла" in body
        assert "I-104" not in body
        r = c.get(f"/projects/{pid}/board?priority=high")
        assert r.status_code == 200
    finally:
        _wipe_users()
