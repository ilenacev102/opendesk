"""MS-8: CSAT rating 1-5 on resolved incidents."""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _svc():
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService
    from services.incident_service import IncidentService
    from services.schemas import INCIDENT_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "csat.db")
    store = DbStore(db, "incidents", INCIDENT_COLS)
    history = HistoryService(DbStore(db, "history", HISTORY_COLS))
    return IncidentService(store, history, db_path=db)


def _resolved(svc):
    inc = svc.create(asset_id="AST001", title="x")
    svc.transition(inc["IncidentID"], "in-progress")
    svc.transition(inc["IncidentID"], "resolved")
    return inc["IncidentID"]


def test_valid_rating_stored_and_averaged():
    from services.incident_service import csat_average

    svc = _svc()
    iid = _resolved(svc)
    done = svc.rate(iid, "5")
    assert done is not None
    assert done["Satisfaction"] == "5"
    assert csat_average(svc.store.records()) == 5.0


def test_rating_open_incident_rejected():
    svc = _svc()
    iid = svc.create(asset_id="AST001", title="x")["IncidentID"]
    assert iid is not None
    with pytest.raises(ValueError):
        svc.rate(iid, "5")


def test_rating_out_of_range_rejected():
    svc = _svc()
    iid = _resolved(svc)
    with pytest.raises(ValueError):
        svc.rate(iid, "6")
    with pytest.raises(ValueError):
        svc.rate(iid, "0")
