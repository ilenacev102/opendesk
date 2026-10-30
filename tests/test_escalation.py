"""Ticketing Pro todo 3: escalation runner + digest (TDD)."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _env():
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService
    from services.schemas import INCIDENT_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "esc.db")
    incidents = DbStore(db, "incidents", INCIDENT_COLS)
    history = HistoryService(DbStore(db, "history", HISTORY_COLS))
    from services.incident_service import IncidentService

    inc_svc = IncidentService(incidents, history, db_path=db)
    a = inc_svc.create(
        asset_id="AST001",
        title="Стар дефект",
        priority="high",
        due_date="2020-01-01",
        performed_by="admin",
    )
    inc_svc.transition(a["IncidentID"], "in-progress", performed_by="admin")
    b = inc_svc.create(
        asset_id="AST002",
        title="Свеж дефект",
        priority="low",
        due_date="2099-01-01",
        performed_by="admin",
    )
    inc_svc.transition(b["IncidentID"], "in-progress", performed_by="admin")
    c = inc_svc.create(
        asset_id="AST003",
        title="Отворен стар",
        priority="medium",
        due_date="2020-01-01",
        performed_by="admin",
    )
    from services.escalation_service import EscalationService

    return (
        EscalationService(incidents, history, db_path=db),
        incidents,
        history,
        a["IncidentID"],
    )


def test_eligible_detects_overdue_in_progress():
    svc, _, _, aid = _env()
    eligible = svc.eligible()
    assert [e["IncidentID"] for e in eligible] == [aid]


def test_escalate_bumps_and_logs():
    svc, incidents, history, aid = _env()
    result = svc.escalate(aid, performed_by="admin")
    assert result["escalated"] is True
    updated = incidents.find("IncidentID", aid)
    assert updated is not None and updated["Priority"] == "urgent"
    actions = [h.get("Action") for h in history.store.records()]
    assert "ESC_ESCALATE" in actions


def test_escalate_idempotent():
    svc, incidents, history, aid = _env()
    svc.escalate(aid, performed_by="admin")
    before = len(history.store.records())
    result = svc.escalate(aid, performed_by="admin")
    assert result["escalated"] is False
    assert len(history.store.records()) == before


def test_escalate_unknown_raises():
    import pytest

    svc, _, _, _ = _env()
    with pytest.raises(ValueError):
        svc.escalate("I999999", performed_by="admin")


def test_escalate_all_counts():
    svc, _, _, aid = _env()
    counts = svc.escalate_all(performed_by="admin")
    assert counts == {"escalated": 1, "skipped": 0}
    counts2 = svc.escalate_all(performed_by="admin")
    assert counts2 == {"escalated": 0, "skipped": 0}


def test_digest_includes_escalated():
    from services import notify_service as notify

    svc, _, _, aid = _env()
    svc.escalate(aid, performed_by="admin")
    esc = [{"IncidentID": aid, "Title": "Стар дефект", "Priority": "urgent"}]
    to, subject, body = notify.digest_email("a@x.mk", [], [], esc)
    assert "ескалирани" in subject
    assert aid in body
