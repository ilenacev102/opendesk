"""Enterprise Wave2 todo 12: Postgres option via SERVICEDESK_DB_URL (TDD)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TEST_TABLE = "pg_test_devices"
TEST_COLS = ["AssetID", "SerialNumber", "Notes"]


def _admin_dsn():
    return os.environ.get("SERVICEDESK_DB_URL", "").strip() or "dbname=postgres"


def _ensure_test_db():
    import psycopg2
    from psycopg2 import errors

    try:
        admin = psycopg2.connect(_admin_dsn(), connect_timeout=3)
    except Exception as exc:
        pytest.skip(f"no Postgres server: {exc}")
    admin.autocommit = True
    try:
        with admin.cursor() as cur:
            cur.execute("CREATE DATABASE servicedesk_test")
    except errors.DuplicateDatabase:
        pass
    except Exception as exc:
        admin.close()
        pytest.skip(f"cannot create test db: {exc}")
    admin.close()
    base = _admin_dsn()
    if "dbname=" in base:
        import re

        return re.sub(r"dbname=\S+", "dbname=servicedesk_test", base)
    return base + " dbname=servicedesk_test"


def _pg_store(dsn):
    from services.pg_store import PgStore

    store = PgStore(dsn, TEST_TABLE, TEST_COLS)
    store._connect().close()
    return store


def test_open_store_sqlite_default(monkeypatch):
    monkeypatch.delenv("SERVICEDESK_DB_URL", raising=False)
    from services.db_service import DbStore, open_store

    store = open_store("/tmp/x.db", "t", None, ["A"])
    assert isinstance(store, DbStore)


def test_open_store_pg_when_env(monkeypatch):
    dsn = _ensure_test_db()
    monkeypatch.setenv("SERVICEDESK_DB_URL", dsn)
    from services.db_service import open_store
    from services.pg_store import PgStore
    from services.store_base import check_store

    store = open_store("/tmp/x.db", TEST_TABLE, None, TEST_COLS)
    assert isinstance(store, PgStore)
    assert check_store(store) is True


def test_pg_crud_parity():
    dsn = _ensure_test_db()
    store = _pg_store(dsn)
    store.replace_all([])
    store.append_row({"AssetID": "P1", "SerialNumber": "S1", "Notes": "n"})
    found = store.find("AssetID", "P1")
    assert found is not None and found["Notes"] == "n"
    assert len(store.filter_eq("AssetID", "P1")) == 1
    assert len(store.recent(5)) == 1
    assert store.update_where("AssetID", "P1", {"Notes": "m"}) == 1
    assert store.max_suffix("AssetID", "P") == 1
    store.replace_all([{"AssetID": "P2", "SerialNumber": "", "Notes": ""}])
    assert store.find("AssetID", "P2") is not None
    assert store.find("AssetID", "P1") is None
    store.replace_all([])


def test_pg_unique_enforced():
    dsn = _ensure_test_db()
    store = _pg_store(dsn)
    store.replace_all([])
    store.append_row({"AssetID": "DUP", "SerialNumber": "", "Notes": ""})
    with pytest.raises(Exception):
        store.append_row({"AssetID": "DUP", "SerialNumber": "", "Notes": ""})
    store.replace_all([])
