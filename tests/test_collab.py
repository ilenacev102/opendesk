"""Phase 4a: mentions, watchers, worklogs."""

import datetime
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.auth_service import USER_COLS
from services.schemas import (
    INCIDENT_COLS,
    NOTIF_COLS,
    WATCHER_COLS,
    WORKLOG_COLS,
)


def _db():
    return os.path.join(tempfile.mkdtemp(), "collab.db")


def _store(db, table, cols):
    from services.db_service import DbStore

    return DbStore(db, table, cols)


def test_extract_unique_order_and_empty():
    from services.mention_service import extract

    assert extract("@ana и @bob, @ana!") == ["ana", "bob"]
    assert extract("") == []
    assert extract("нема спомени овде") == []


def test_extract_punctuation_boundaries():
    from services.mention_service import extract

    assert extract("здраво @ana, @bob; @carol.") == ["ana", "bob", "carol"]
    assert extract("контакт @first.last веќе") == ["first.last"]


def test_notify_valid_ignored_invalid_and_kind_allowed():
    from services import notify_center
    from services.mention_service import notify

    db = _db()
    users = _store(db, "users", USER_COLS)
    users.append_row({"UserName": "ana"})
    notifs = _store(db, "notifications", NOTIF_COLS)

    count = notify(notifs, users, ["ana", "ghost"], "I-1", "ви спомна")
    assert count == 1
    rows = notifs.records()
    assert len(rows) == 1
    assert rows[0]["UserName"] == "ana"
    assert rows[0]["Kind"] == "mention"
    assert rows[0]["RefID"] == "I-1"
    assert notify_center.validate_kind("mention") == "mention"


def test_watch_duplicate_single_row():
    from services.watcher_service import list_watchers, watch

    w = _store(_db(), "watchers", WATCHER_COLS)
    assert watch(w, "I-1", "ana") is True
    assert watch(w, "I-1", "ana") is False
    assert watch(w, "I-1", "bob") is True
    assert list_watchers(w, "I-1") == ["ana", "bob"]


def test_unwatch_toggle():
    from services.watcher_service import list_watchers, unwatch, watch

    w = _store(_db(), "watchers", WATCHER_COLS)
    watch(w, "I-1", "ana")
    assert unwatch(w, "I-1", "ana") is True
    assert list_watchers(w, "I-1") == []
    assert unwatch(w, "I-1", "ana") is False


def test_notify_watchers_only_matching_incident():
    from services.watcher_service import notify_watchers, watch

    db = _db()
    w = _store(db, "watchers", WATCHER_COLS)
    n = _store(db, "notifications", NOTIF_COLS)
    watch(w, "I-1", "ana")
    watch(w, "I-1", "bob")
    watch(w, "I-2", "carol")

    count = notify_watchers(n, w, "I-1", "нов коментар")
    assert count == 2
    rows = n.records()
    assert {r["UserName"] for r in rows} == {"ana", "bob"}
    assert all(r["RefID"] == "I-1" for r in rows)


def test_worklog_validation():
    from services.worklog_service import log
    from utils.validators import ValidationError

    wl = _store(_db(), "worklogs", WORKLOG_COLS)
    today = datetime.date.today().isoformat()
    tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()

    with pytest.raises(ValidationError):
        log(wl, "I-1", "ana", 0, today)
    with pytest.raises(ValidationError):
        log(wl, "I-1", "ana", "abc", today)
    with pytest.raises(ValidationError):
        log(wl, "I-1", "ana", 30, tomorrow)
    with pytest.raises(ValidationError):
        log(wl, "I-1", "ana", 30, "не-датум")

    row = log(wl, "I-1", "ana", 30, today, "работа")
    assert row["Minutes"] == "30"
    assert row["WorkedDate"] == today


def test_worklog_totals_per_incident_and_assignee():
    from services.worklog_service import log, minutes_by_assignee, total_minutes

    db = _db()
    wl = _store(db, "worklogs", WORKLOG_COLS)
    inc = _store(db, "incidents", INCIDENT_COLS)
    today = datetime.date.today().isoformat()
    log(wl, "I-1", "ana", 30, today)
    log(wl, "I-1", "ana", 45, today)
    log(wl, "I-2", "bob", 10, today)
    inc.append_row({"IncidentID": "I-1", "Assignee": "ana"})
    inc.append_row({"IncidentID": "I-2", "Assignee": "bob"})

    assert total_minutes(wl, "I-1") == 75
    assert total_minutes(wl, "I-3") == 0
    assert minutes_by_assignee(wl, inc) == {"ana": 75, "bob": 10}
