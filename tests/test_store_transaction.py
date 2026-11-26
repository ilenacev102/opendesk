"""P1.0: store_transaction — one write transaction across store backends.

RED first: the helper does not exist yet.
"""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

COLS = ["ID", "Value"]


def _db():
    return os.path.join(tempfile.mkdtemp(), "tx.db")


def _store(db, table="t1"):
    from services.db_service import DbStore

    return DbStore(db, table, COLS)


class _PgStub:
    """Looks like PgStore for the backend check; never connects."""

    dsn = "dbname=stub"


def test_sqlite_commit_visible_after_block():
    from services.db_service import store_transaction

    db = _db()
    store = _store(db)
    with store_transaction(store) as con:
        store.append_row({"ID": "1", "Value": "a"}, con=con)
    assert store.find("ID", "1")["Value"] == "a"


def test_sqlite_rollback_leaves_nothing():
    from services.db_service import store_transaction

    db = _db()
    store = _store(db)
    with pytest.raises(RuntimeError):
        with store_transaction(store) as con:
            store.append_row({"ID": "1", "Value": "a"}, con=con)
            raise RuntimeError("boom")
    assert store.records() == []


def test_two_stores_same_db_share_one_transaction():
    from services.db_service import store_transaction

    db = _db()
    left = _store(db, "left")
    right = _store(db, "right")
    with pytest.raises(RuntimeError):
        with store_transaction(left, right) as con:
            left.append_row({"ID": "1", "Value": "a"}, con=con)
            right.append_row({"ID": "1", "Value": "b"}, con=con)
            raise RuntimeError("boom")
    assert left.records() == []
    assert right.records() == []


def test_different_sqlite_files_rejected():
    from services.db_service import store_transaction

    with pytest.raises(RuntimeError):
        with store_transaction(_store(_db(), "a"), _store(_db(), "b")):
            pass


def test_mixed_backends_rejected():
    from services.db_service import store_transaction

    with pytest.raises(RuntimeError):
        with store_transaction(_PgStub(), _store(_db())):
            pass


def test_no_stores_yields_none():
    from services.db_service import store_transaction

    with store_transaction() as con:
        assert con is None


def test_fallback_path_for_legacy_store():
    from services.db_service import DbStore, store_transaction

    db = _db()
    store = DbStore(db, "legacy", COLS)
    with store_transaction(None, fallback_path=db) as con:
        store.append_row({"ID": "1", "Value": "a"}, con=con)
    assert store.find("ID", "1")["Value"] == "a"


def test_postgres_rollback_when_dsn_available():
    dsn = os.environ.get("SERVICEDESK_DB_URL", "").strip()
    if not dsn:
        pytest.skip("no SERVICEDESK_DB_URL")
    try:
        import psycopg2
    except ImportError:
        pytest.skip("psycopg2 not installed")
    try:
        psycopg2.connect(dsn, connect_timeout=3).close()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"no Postgres server: {exc}")

    from services.db_service import store_transaction
    from services.pg_store import PgStore

    table = "pg_store_tx_test"
    left = PgStore(dsn, table, COLS)
    right = PgStore(dsn, table, COLS)
    con = psycopg2.connect(dsn)
    con.autocommit = True
    with con.cursor() as cur:
        cur.execute(f'DELETE FROM "{table}"')
    con.close()

    with pytest.raises(RuntimeError):
        with store_transaction(left, right) as tx:
            left.append_row({"ID": "1", "Value": "a"}, con=tx)
            raise RuntimeError("boom")
    assert left.records() == []
