"""P1.6: secondary mutations are atomic (onboard, templates, watchers, notify)."""

import os
import sys
import tempfile
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _db():
    return os.path.join(tempfile.mkdtemp(), "sec.db")


def _history(db):
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService

    return HistoryService(DbStore(db, "history", HISTORY_COLS))


def test_onboard_submit_rolls_back_when_audit_fails():
    from services.db_service import DbStore
    from services.onboard_service import OnboardService
    from services.schemas import ONBOARD_COLS

    db = _db()
    store = DbStore(db, "onboard", ONBOARD_COLS)
    history = _history(db)
    svc = OnboardService(store, [{"id": "std"}], history=history)

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    history.log = boom
    req = {
        "FullName": "Ана Аневска",
        "StartDate": "2099-01-10",
        "Package": "std",
    }
    with pytest.raises(RuntimeError):
        svc.submit(req, today="2099-01-01")
    assert store.records() == []


def test_import_project_rolls_back_when_a_type_fails():
    from services.db_service import DbStore
    from services.project_template import import_project
    from services.schemas import ISSUE_TYPE_COLS, PROJECT_COLS

    db = _db()
    projects = DbStore(db, "projects", PROJECT_COLS)
    types = DbStore(db, "issue_types", ISSUE_TYPE_COLS)
    history = _history(db)

    original = types.append_row
    calls = {"n": 0}

    def flaky(row, con=None):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("boom")
        return original(row, con=con)

    types.append_row = flaky
    with pytest.raises(RuntimeError):
        import_project(
            projects,
            types,
            history,
            {
                "name": "Клон",
                "key": "KLN",
                "types": [
                    {"name": "Incident", "workflow": "incident"},
                    {"name": "Task", "workflow": "task"},
                ],
            },
            db_path=db,
        )

    assert projects.records() == []
    assert types.records() == []
    assert history.store.records() == []


def test_unwatch_deletes_only_the_matching_row():
    from services.db_service import DbStore
    from services.schemas import WATCHER_COLS
    from services.watcher_service import unwatch, watch

    db = _db()
    watchers = DbStore(db, "watchers", WATCHER_COLS)
    watch(watchers, "I-1", "ana")
    watch(watchers, "I-1", "bob")
    watch(watchers, "I-2", "ana")

    def boom(*args, **kwargs):
        raise AssertionError("unwatch не смее да прави replace_all")

    watchers.replace_all = boom
    assert unwatch(watchers, "I-1", "ana") is True
    assert unwatch(watchers, "I-1", "ana") is False

    rows = {(r["IncidentID"], r["UserName"]) for r in watchers.records()}
    assert rows == {("I-1", "bob"), ("I-2", "ana")}


def test_notify_ids_stay_unique_under_concurrency():
    from services.db_service import DbStore
    from services.notify_center import push
    from services.schemas import NOTIF_COLS

    db = _db()
    store = DbStore(db, "notifications", NOTIF_COLS)
    errors = []

    def worker():
        try:
            for _ in range(10):
                push(store, "ana", "system", "ref", "текст")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, errors
    ids = [r["NotifID"] for r in store.records()]
    assert len(ids) == 30
    assert len(set(ids)) == 30
