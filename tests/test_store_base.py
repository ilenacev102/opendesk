"""Enterprise Wave2 todo 11: store protocol abstraction (TDD)."""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROTOCOL_METHODS = (
    "records",
    "find",
    "filter_eq",
    "recent",
    "update_where",
    "append_row",
    "replace_all",
    "max_suffix",
    "max_suffix_con",
)


def test_dbstore_conforms_to_protocol():
    from services.db_service import DbStore
    from services.store_base import StoreProtocol, check_store

    tmp = tempfile.mkdtemp()
    store = DbStore(os.path.join(tmp, "p.db"), "devices", ["AssetID", "Notes"])
    assert isinstance(store, StoreProtocol)
    assert check_store(store) is True
    for name in PROTOCOL_METHODS:
        assert callable(getattr(store, name)), name


def test_protocol_smoke_behavior():
    from services.db_service import DbStore
    from services.store_base import check_store

    tmp = tempfile.mkdtemp()
    store = DbStore(os.path.join(tmp, "p.db"), "devices", ["AssetID", "Notes"])
    assert check_store(store) is True
    store.append_row({"AssetID": "A1", "Notes": "n"})
    found = store.find("AssetID", "A1")
    assert found is not None and found["Notes"] == "n"
    assert len(store.filter_eq("AssetID", "A1")) == 1
    assert len(store.recent(5)) == 1
    assert store.update_where("AssetID", "A1", {"Notes": "m"}) == 1
    assert store.max_suffix("AssetID", "A") == 1
    store.replace_all([{"AssetID": "B2", "Notes": ""}])
    assert store.find("AssetID", "B2") is not None
    assert store.find("AssetID", "A1") is None


def test_missing_method_rejected():
    from services.store_base import check_store

    class Broken:
        pass

    with pytest.raises(TypeError):
        check_store(Broken())


def test_open_store_returns_conforming_store():
    import app as app_mod
    from services.store_base import check_store

    for name in (
        "devices",
        "employees",
        "incidents",
        "staging",
        "ldapmap",
        "contracts",
        "reservations",
        "requests",
    ):
        assert check_store(getattr(app_mod, name)) is True, name
