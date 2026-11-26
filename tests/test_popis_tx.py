"""P1.5: popis start/scan/finish/mark_scanned are atomic and audited."""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _svc():
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService
    from services.popis_service import PopisService

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "popis.db")
    history = HistoryService(DbStore(db, "history", HISTORY_COLS))
    svc = PopisService(db, os.path.join(tmp, "popis.csv"), history=history)
    return svc, history


def _actions(history):
    return [r["Action"] for r in history.store.records()]


def test_start_scan_and_finish_write_audit_rows():
    svc, history = _svc()
    pid = svc.start("location", "HQ", ["A1", "A2"], performed_by="ana")
    svc.scan(pid, "A1", performed_by="ana")
    result = svc.finish(pid, "Popis_1.docx", performed_by="ana")

    assert result["missing"] == ["A2"]
    assert _actions(history) == [
        "POPIS_START",
        "POPIS_SCAN",
        "POPIS_CLOSE",
        "POPIS_MISSING",
    ]
    assert {r["PerformedBy"] for r in history.store.records()} == {"ana"}


def test_finish_rolls_back_when_audit_fails():
    svc, history = _svc()
    pid = svc.start("location", "HQ", ["A1"])

    original = history.log

    def flaky(action, *args, **kwargs):
        if action == "POPIS_CLOSE":
            raise RuntimeError("boom")
        return original(action, *args, **kwargs)

    history.log = flaky
    with pytest.raises(RuntimeError):
        svc.finish(pid, "Popis_1.docx")

    rec = svc.get(pid)
    assert rec["Status"] == "OPEN"
    assert rec["DocumentPath"] == ""
    assert "POPIS_CLOSE" not in _actions(history)


def test_preview_finish_does_not_change_state():
    svc, _history = _svc()
    pid = svc.start("location", "HQ", ["A1", "A2"])
    preview = svc.preview_finish(pid)

    assert preview["missing"] == ["A1", "A2"]
    assert svc.get(pid)["Status"] == "OPEN"


def test_mark_scanned_is_audited_and_atomic():
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService
    from services.popis_service import mark_scanned
    from services.schemas import DEV_COLS

    db = os.path.join(tempfile.mkdtemp(), "scan.db")
    devices = DbStore(db, "devices", DEV_COLS)
    history = HistoryService(DbStore(db, "history", HISTORY_COLS))
    devices.append_row({"AssetID": "D1", "Type": "Laptop", "Status": "Available"})

    due = mark_scanned(devices, "D1", "2026-01-01", history=history, performed_by="ana")
    assert devices.find("AssetID", "D1")["NextAuditDate"] == due
    assert _actions(history) == ["AUDIT_SCAN"]

    original = history.log
    history.log = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    with pytest.raises(RuntimeError):
        mark_scanned(devices, "D1", "2026-06-01", history=history)
    history.log = original
    assert devices.find("AssetID", "D1")["NextAuditDate"] == due
