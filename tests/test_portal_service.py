"""P3: portal ticket ownership, thread, reopen window and pagination."""

import datetime
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _env():
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService
    from services.schemas import COMMENT_COLS, INCIDENT_COLS

    db = os.path.join(tempfile.mkdtemp(), "portal_service.db")
    incidents = DbStore(db, "incidents", INCIDENT_COLS)
    comments = DbStore(db, "comments", COMMENT_COLS)
    history = HistoryService(DbStore(db, "history", HISTORY_COLS))
    return incidents, comments, history


def _incident(store, iid="I1", employee="EMP-001", status="resolved"):
    store.append_row(
        {
            "IncidentID": iid,
            "EmployeeID": employee,
            "Title": "Тикет",
            "Status": status,
            "Assignee": "mag",
        }
    )


def test_ownership_matches_employee_or_username():
    from services import portal_service

    inc = {"EmployeeID": "EMP-001"}
    assert portal_service.owns(inc, {"EmployeeID": "EMP-001"}, "alek") is True
    assert portal_service.owns(inc, None, "EMP-001") is True
    assert portal_service.owns(inc, {"EmployeeID": "EMP-002"}, "bora") is False
    assert portal_service.owns({"EmployeeID": ""}, None, "") is False


def test_ticket_lookup_separates_missing_from_foreign():
    from services import portal_service

    incidents, _, _ = _env()
    _incident(incidents)

    with pytest.raises(LookupError):
        portal_service.ticket(incidents, "NOPE", None, "alek")
    with pytest.raises(PermissionError):
        portal_service.ticket(incidents, "I1", {"EmployeeID": "EMP-002"}, "bora")
    assert portal_service.ticket(incidents, "I1", None, "EMP-001")["IncidentID"] == "I1"


def test_thread_is_oldest_first():
    from services import portal_service

    _, comments, _ = _env()
    comments.append_row(
        {
            "CommentID": "C2",
            "IncidentID": "I1",
            "Body": "втор",
            "Created": "2026-01-02 10:00",
        }
    )
    comments.append_row(
        {
            "CommentID": "C1",
            "IncidentID": "I1",
            "Body": "прв",
            "Created": "2026-01-01 10:00",
        }
    )
    comments.append_row(
        {
            "CommentID": "C3",
            "IncidentID": "I2",
            "Body": "друг",
            "Created": "2026-01-01 09:00",
        }
    )
    rows = portal_service.thread(comments, "I1")
    assert [r["Body"] for r in rows] == ["прв", "втор"]


def test_reopen_requires_resolved_status():
    from services import portal_service

    incidents, _, history = _env()
    _incident(incidents, status="open")
    with pytest.raises(ValueError):
        portal_service.reopen(incidents, history, "I1", performed_by="alek")


def test_reopen_is_limited_to_once_per_seven_days():
    from services import portal_service

    incidents, _, history = _env()
    _incident(incidents)

    row = portal_service.reopen(incidents, history, "I1", performed_by="alek")
    assert row["Status"] == "open"
    audit = [h for h in history.store.records() if h.get("Action") == "INC_REOPEN"]
    assert len(audit) == 1
    assert audit[0].get("PerformedBy") == "alek"

    incidents.update_where("IncidentID", "I1", {"Status": "resolved"})
    with pytest.raises(ValueError):
        portal_service.reopen(incidents, history, "I1", performed_by="alek")

    old = (datetime.datetime.now() - datetime.timedelta(days=8)).strftime(
        "%Y-%m-%d %H:%M"
    )
    history.store.update_where("HistoryID", audit[0]["HistoryID"], {"DateTime": old})
    assert (
        portal_service.reopen(incidents, history, "I1", performed_by="alek")["Status"]
        == "open"
    )


def test_paginate_clamps_page_and_reports_totals():
    from services import portal_service

    rows = list(range(12))
    page_rows, page, total_pages, total = portal_service.paginate(rows, 2, per_page=10)
    assert page_rows == [10, 11]
    assert (page, total_pages, total) == (2, 2, 12)

    page_rows, page, total_pages, total = portal_service.paginate(rows, 99, per_page=10)
    assert page_rows == [10, 11]
    assert (page, total_pages, total) == (2, 2, 12)

    page_rows, page, total_pages, total = portal_service.paginate(rows, 0, per_page=10)
    assert page_rows == list(range(10))
    assert (page, total_pages, total) == (1, 2, 12)

    page_rows, page, total_pages, total = portal_service.paginate([], 1, per_page=10)
    assert page_rows == []
    assert (page, total_pages, total) == (1, 1, 0)


def test_attachment_path_blocks_traversal():
    from services import portal_service

    base = tempfile.mkdtemp()
    target = os.path.join(base, "incidents", "I1")
    os.makedirs(target)
    with open(os.path.join(target, "log.txt"), "w", encoding="utf-8") as fh:
        fh.write("ok")

    assert portal_service.attachment_path(base, "I1", "log.txt") == os.path.join(
        target, "log.txt"
    )
    assert portal_service.attachment_path(base, "I1", "../svc.db") is None
    assert portal_service.attachment_path(base, "I1", "") is None
    assert portal_service.attachment_path(base, "I1", "missing.txt") is None


def test_comment_service_can_audit_portal_action():
    from services.comment_service import CommentService

    incidents, comments, history = _env()
    _incident(incidents, status="open")
    svc = CommentService(
        comments, incidents, history, db_path=getattr(incidents, "db_path", None)
    )
    row = svc.add(
        "I1", "alek", "Здраво", performed_by="alek", action="PORTAL_COMMENT"
    )
    assert row["Body"] == "Здраво"
    actions = [h.get("Action") for h in history.store.records()]
    assert actions == ["PORTAL_COMMENT"]


def test_attachments_lists_only_files_for_that_ticket():
    from services import portal_service

    base = tempfile.mkdtemp()
    target = os.path.join(base, "incidents", "I1")
    os.makedirs(target)
    os.makedirs(os.path.join(target, "nested"))
    with open(os.path.join(target, "b.txt"), "w", encoding="utf-8") as fh:
        fh.write("b")
    with open(os.path.join(target, "a.txt"), "w", encoding="utf-8") as fh:
        fh.write("a")

    assert portal_service.attachments(base, "I1") == ["a.txt", "b.txt"]
    assert portal_service.attachments(base, "NOPE") == []
