"""Multiloc todo 1: Postgres mover service (TDD)."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class FakePgStore:
    def __init__(self, table, columns, fail_on=None):
        self.table = table
        self.columns = list(columns)
        self._rows = []
        self.fail_on = fail_on

    @property
    def _data(self):
        return self._rows

    def records(self):
        return [dict(r) for r in self._rows]

    def append_row(self, row, con=None):
        if self.fail_on == row.get("AssetID"):
            raise ConnectionError("injected copy failure")
        self._rows.append({c: str(row.get(c, "")) for c in self.columns})
        return dict(self._rows[-1])


def _sqlite_store(tmp, table="devices"):
    from services.db_service import DbStore
    from services.schemas import DEV_COLS

    store = DbStore(os.path.join(tmp, "m.db"), table, DEV_COLS)
    store.append_row(
        {
            "AssetID": "AST001",
            "SerialNumber": "S1",
            "Manufacturer": "Dell",
            "Status": "Available",
        }
    )
    store.append_row(
        {
            "AssetID": "AST002",
            "SerialNumber": "S2",
            "Manufacturer": "HP",
            "Status": "Assigned",
        }
    )
    return store


def test_move_all_copies_with_counts():
    from services.pg_mover import move_all

    tmp = tempfile.mkdtemp()
    src = _sqlite_store(tmp)
    dst = FakePgStore("devices", src.columns)
    report = move_all({"devices": (src, dst)}, dry_run=False)
    assert report["devices"] == {"source": 2, "target": 2, "copied": 2}
    assert len(dst.records()) == 2


def test_dry_run_writes_nothing():
    from services.pg_mover import move_all

    tmp = tempfile.mkdtemp()
    src = _sqlite_store(tmp)
    dst = FakePgStore("devices", src.columns)
    report = move_all({"devices": (src, dst)}, dry_run=True)
    assert report["devices"] == {"source": 2, "target": 0, "copied": 0}
    assert dst.records() == []


def test_verify_counts_match():
    from services.pg_mover import move_all, verify_all

    tmp = tempfile.mkdtemp()
    src = _sqlite_store(tmp)
    dst = FakePgStore("devices", src.columns)
    move_all({"devices": (src, dst)}, dry_run=False)
    assert verify_all({"devices": (src, dst)}) == {"devices": True}


def test_copy_failure_reported():
    import pytest

    from services.pg_mover import MoverError, move_all

    tmp = tempfile.mkdtemp()
    src = _sqlite_store(tmp)
    dst = FakePgStore("devices", src.columns, fail_on="AST002")
    with pytest.raises(MoverError):
        move_all({"devices": (src, dst)}, dry_run=False)


def test_unreachable_target_zero_writes():
    import pytest

    from services.pg_mover import MoverError, move_table

    tmp = tempfile.mkdtemp()
    src = _sqlite_store(tmp)

    class DeadStore(FakePgStore):
        def records(self):
            raise ConnectionError("no route to host")

    with pytest.raises(MoverError):
        move_table(src, DeadStore("devices", src.columns), dry_run=False)
    assert len(src.records()) == 2
