"""P1.1: sprint mutations are atomic and audited."""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _db():
    return os.path.join(tempfile.mkdtemp(), "sprinttx.db")


def _stores(db):
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService
    from services.schemas import INCIDENT_COLS, SPRINT_COLS

    return (
        DbStore(db, "sprints", SPRINT_COLS),
        DbStore(db, "incidents", INCIDENT_COLS),
        HistoryService(DbStore(db, "history", HISTORY_COLS)),
    )


def _add(incidents, iid, project="PRJ-1", status="open"):
    incidents.append_row(
        {
            "IncidentID": iid,
            "Title": f"тикет {iid}",
            "Status": status,
            "ProjectID": project,
        }
    )


def _sprint(sprints, name="SP1"):
    from services import sprint_service

    return sprint_service.create(sprints, "PRJ-1", name, "2026-10-01", "2026-10-04")


def test_start_rolls_back_when_a_ticket_write_fails():
    from services import sprint_service

    db = _db()
    sprints, incidents, history = _stores(db)
    sp = _sprint(sprints)
    for iid in ("I-1", "I-2", "I-3"):
        _add(incidents, iid)

    original = incidents.update_where
    calls = {"n": 0}

    def flaky(col, value, updates, con=None):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("boom")
        return original(col, value, updates, con=con)

    incidents.update_where = flaky
    with pytest.raises(RuntimeError):
        sprint_service.start(
            sprints, incidents, sp["SprintID"], history=history, db_path=db
        )

    assert sprints.find("SprintID", sp["SprintID"])["Status"] == "planned"
    assert all(r["SprintID"] == "" for r in incidents.records())
    assert history.store.records() == []


def test_start_logs_sprint_and_each_bound_ticket():
    from services import sprint_service

    db = _db()
    sprints, incidents, history = _stores(db)
    sp = _sprint(sprints)
    _add(incidents, "I-1")
    _add(incidents, "I-2")

    bound = sprint_service.start(
        sprints,
        incidents,
        sp["SprintID"],
        history=history,
        performed_by="ana",
        db_path=db,
    )

    assert bound == 2
    rows = history.store.records()
    actions = [r["Action"] for r in rows]
    assert "SPRINT_START" in actions
    assert actions.count("INC_SPRINT_ADD") == 2
    assert {r["PerformedBy"] for r in rows} == {"ana"}
    assert {r["AssetID"] for r in rows if r["Action"] == "INC_SPRINT_ADD"} == {
        "I-1",
        "I-2",
    }


def test_complete_rolls_back_when_a_ticket_write_fails():
    from services import sprint_service

    db = _db()
    sprints, incidents, history = _stores(db)
    sp = _sprint(sprints)
    _add(incidents, "I-1")
    _add(incidents, "I-2")
    sprint_service.start(sprints, incidents, sp["SprintID"])

    original = incidents.update_where
    calls = {"n": 0}

    def flaky(col, value, updates, con=None):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("boom")
        return original(col, value, updates, con=con)

    incidents.update_where = flaky
    with pytest.raises(RuntimeError):
        sprint_service.complete(
            sprints, incidents, sp["SprintID"], history=history, db_path=db
        )

    assert sprints.find("SprintID", sp["SprintID"])["Status"] == "active"
    assert all(r["SprintID"] == sp["SprintID"] for r in incidents.records())
    assert history.store.records() == []


def test_create_and_move_write_history():
    from services import sprint_service

    db = _db()
    sprints, incidents, history = _stores(db)
    sp = sprint_service.create(
        sprints,
        "PRJ-1",
        "SP1",
        "2026-10-01",
        "2026-10-04",
        history=history,
        performed_by="ana",
        db_path=db,
    )
    _add(incidents, "I-1")
    sprint_service.move_to_sprint(
        incidents,
        sprints,
        "I-1",
        sp["SprintID"],
        history=history,
        performed_by="ana",
        db_path=db,
    )

    actions = [r["Action"] for r in history.store.records()]
    assert actions == ["SPRINT_CREATE", "INC_SPRINT_ADD"]


def test_set_rank_and_points_are_audited():
    from services import sprint_service

    db = _db()
    _sprints, incidents, history = _stores(db)
    _add(incidents, "I-1")

    sprint_service.set_rank(
        incidents,
        "PRJ-1",
        "I-1",
        "3",
        history=history,
        performed_by="ana",
        db_path=db,
    )
    sprint_service.set_points(
        incidents,
        "PRJ-1",
        "I-1",
        "5",
        history=history,
        performed_by="ana",
        db_path=db,
    )

    row = incidents.find("IncidentID", "I-1")
    assert row["Rank"] == "3"
    assert row["StoryPoints"] == "5"
    assert [r["Action"] for r in history.store.records()] == ["INC_RANK", "INC_POINTS"]
