"""MS-7: SLA pause gate + reopen counter (anti-gaming)."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_pause_allowed_only_three_reasons():
    from services.sla_service import PAUSE_REASONS, pause_allowed

    assert len(PAUSE_REASONS) == 3
    for reason in PAUSE_REASONS:
        assert pause_allowed(reason) is True
        assert pause_allowed("  " + reason + "  ") is True


def test_pause_denied_for_gaming():
    from services.sla_service import pause_allowed

    assert pause_allowed("Пауза") is False
    assert pause_allowed("") is False
    assert pause_allowed("on hold") is False


def _svc():
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService
    from services.incident_service import IncidentService
    from services.schemas import INCIDENT_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "sla.db")
    store = DbStore(db, "incidents", INCIDENT_COLS)
    history = HistoryService(DbStore(db, "history", HISTORY_COLS))
    return IncidentService(store, history, db_path=db)


def _cycle(svc):
    inc = svc.create(asset_id="AST001", title="x")
    svc.transition(inc["IncidentID"], "in-progress")
    svc.transition(inc["IncidentID"], "resolved")
    svc.transition(inc["IncidentID"], "open")
    return inc["IncidentID"]


def test_reopen_counts_twice_and_clears_closed():
    svc = _svc()
    iid = _cycle(svc)
    svc.transition(iid, "in-progress")
    svc.transition(iid, "resolved")
    svc.transition(iid, "open")
    assert svc.reopen_count(iid) == 2
    done = svc.store.find("IncidentID", iid)
    assert done is not None
    assert done["Status"] == "open"
    assert done["ClosedAt"] == ""


def test_new_incident_does_not_reset_old_counter():
    svc = _svc()
    old = _cycle(svc)
    new = svc.create(asset_id="AST002", title="y")["IncidentID"]
    assert svc.reopen_count(new) == 0
    assert svc.reopen_count(old) == 1
