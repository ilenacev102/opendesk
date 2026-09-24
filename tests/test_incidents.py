"""Enterprise Wave1 todo 4: incident lifecycle + SLA breach (TDD)."""

import os
import tempfile

import pytest

from services.db_service import DbStore
from services.history_service import HISTORY_COLS, HistoryService
from services.schemas import INCIDENT_COLS


@pytest.fixture()
def svc():
    from services.incident_service import IncidentService

    tmp = tempfile.mkdtemp(prefix="incident-test-")
    db = os.path.join(tmp, "i.db")
    store = DbStore(db, "incidents", INCIDENT_COLS)
    history = HistoryService(DbStore(db, "history", HISTORY_COLS))
    return IncidentService(store, history, db_path=db), store, history


def test_create_defaults_open(svc):
    service, store, history = svc
    inc = service.create(
        asset_id="AST001",
        title="Не работи тастатура",
        priority="high",
        assignee="mag",
        due_date="2026-10-01",
        performed_by="admin",
    )
    assert inc["Status"] == "open"
    assert inc["IncidentID"].startswith("I")
    assert inc["ClosedAt"] == ""
    assert store.find("IncidentID", inc["IncidentID"]) is not None


def test_create_rejects_bad_priority(svc):
    service, store, history = svc
    with pytest.raises(ValueError):
        service.create(asset_id="AST001", title="x", priority="critical")


def test_create_rejects_bad_due_date(svc):
    service, store, history = svc
    with pytest.raises(ValueError):
        service.create(asset_id="AST001", title="x", due_date="01-10-2026")


def test_transition_open_to_resolved_forbidden(svc):
    service, store, history = svc
    inc = service.create(asset_id="AST001", title="x")
    with pytest.raises(ValueError):
        service.transition(inc["IncidentID"], "resolved")
    assert store.find("IncidentID", inc["IncidentID"])["Status"] == "open"


def test_full_lifecycle_logs_history(svc):
    service, store, history = svc
    inc = service.create(asset_id="AST001", title="x", performed_by="admin")
    service.transition(inc["IncidentID"], "in-progress", performed_by="admin")
    assert store.find("IncidentID", inc["IncidentID"])["Status"] == "in-progress"
    service.transition(inc["IncidentID"], "resolved", performed_by="admin")
    done = store.find("IncidentID", inc["IncidentID"])
    assert done["Status"] == "resolved"
    assert done["ClosedAt"] != ""
    actions = [r.get("Action") for r in history.store.records()]
    assert actions.count("INC_CREATE") == 1
    assert actions.count("INC_START") == 1
    assert actions.count("INC_RESOLVE") == 1


def test_transition_unknown_incident(svc):
    service, store, history = svc
    with pytest.raises(ValueError):
        service.transition("I999999", "in-progress")


def test_breach():
    from services.incident_service import breach

    assert breach("2020-01-01") is True
    assert breach("") is False
    assert breach("2099-01-01") is False
    assert breach("not-a-date") is False
