"""P1.7: unique identity indexes guard every ID column."""

import os
import sqlite3
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _db():
    return os.path.join(tempfile.mkdtemp(), "ids.db")


def test_duplicate_incident_id_is_rejected():
    from services.db_service import DbStore
    from services.schemas import INCIDENT_COLS

    store = DbStore(_db(), "incidents", INCIDENT_COLS)
    store.append_row({"IncidentID": "I-1", "Title": "прв"})
    with pytest.raises(sqlite3.IntegrityError):
        store.append_row({"IncidentID": "I-1", "Title": "втор"})


def test_duplicate_sprint_id_is_rejected():
    from services.db_service import DbStore
    from services.schemas import SPRINT_COLS

    store = DbStore(_db(), "sprints", SPRINT_COLS)
    store.append_row({"SprintID": "SP1", "Name": "а"})
    with pytest.raises(sqlite3.IntegrityError):
        store.append_row({"SprintID": "SP1", "Name": "б"})


def test_composite_keys_reject_only_the_same_pair():
    from services.db_service import DbStore
    from services.schemas import KB_RATING_COLS

    store = DbStore(_db(), "kb_ratings", KB_RATING_COLS)
    store.append_row({"ArticleID": "A1", "UserName": "ana", "Score": "4"})
    store.append_row({"ArticleID": "A1", "UserName": "bob", "Score": "5"})
    with pytest.raises(sqlite3.IntegrityError):
        store.append_row({"ArticleID": "A1", "UserName": "ana", "Score": "1"})


def test_empty_identity_values_stay_allowed():
    from services.db_service import DbStore
    from services.schemas import NOTIF_COLS

    store = DbStore(_db(), "notifications", NOTIF_COLS)
    store.append_row({"NotifID": "", "UserName": "ana"})
    store.append_row({"NotifID": "", "UserName": "bob"})
    assert len(store.records()) == 2


def test_legacy_duplicates_do_not_block_startup():
    from services.db_service import DbStore
    from services.schemas import NOTIF_COLS

    db = _db()
    con = sqlite3.connect(db)
    cols = ", ".join(f'"{c}" TEXT' for c in NOTIF_COLS)
    con.execute(f'CREATE TABLE "notifications" ({cols})')
    con.executemany(
        'INSERT INTO "notifications" ("NotifID", "UserName") VALUES (?, ?)',
        [("N1", "ana"), ("N1", "bob")],
    )
    con.commit()
    con.close()

    store = DbStore(db, "notifications", NOTIF_COLS)  # must not raise
    assert len(store.records()) == 2


def test_duplicate_script_reports_and_exits_nonzero():
    from scripts.check_duplicate_ids import main

    db = _db()
    con = sqlite3.connect(db)
    con.execute('CREATE TABLE "sprints" ("SprintID" TEXT, "Name" TEXT)')
    con.executemany(
        'INSERT INTO "sprints" ("SprintID", "Name") VALUES (?, ?)',
        [("SP1", "а"), ("SP1", "б")],
    )
    con.commit()
    con.close()

    assert main(["--db", db]) == 1
