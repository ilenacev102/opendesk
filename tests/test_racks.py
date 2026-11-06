"""Tests for visual 42U rack elevation designer (/racks)."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _setup_rack_env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.schemas import DEV_COLS, RACK_COLS, RACK_ITEM_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "racks.db")
    racks_store = DbStore(db, "racks", RACK_COLS)
    rack_items_store = DbStore(db, "rack_items", RACK_ITEM_COLS)
    devices_store = DbStore(db, "devices", DEV_COLS)

    monkeypatch.setattr(app_mod, "racks", racks_store)
    monkeypatch.setattr(app_mod, "rack_items", rack_items_store)
    monkeypatch.setattr(app_mod, "devices", devices_store)
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)

    # Seed test rack
    racks_store.append_row({
        "RackID": "RCK-01",
        "Name": "Главен Серверски Ормар 1",
        "Location": "Сервер сала",
        "Units": "42",
        "Notes": "Тест ормар",
    })

    # Seed test device
    devices_store.append_row({
        "AssetID": "SRV-DELL-R740",
        "Category": "Сервер",
        "Manufacturer": "Dell",
        "Model": "PowerEdge R740",
        "SerialNumber": "SN-R740-01",
        "Status": "Active",
    })
    devices_store.append_row({
        "AssetID": "SW-CISCO-2960",
        "Category": "Мрежа",
        "Manufacturer": "Cisco",
        "Model": "Catalyst 2960",
        "SerialNumber": "SN-CISCO-01",
        "Status": "Active",
    })

    return app_mod


def test_racks_home_and_auto_seed(monkeypatch):
    app_mod = _setup_rack_env(monkeypatch)
    c = app_mod.app.test_client()

    r = c.get("/racks")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Серверски Рек Ормари" in html
    assert "42U" in html
    # Seeded default rack exists
    assert len(app_mod.racks.records()) >= 1


def test_create_new_rack(monkeypatch):
    app_mod = _setup_rack_env(monkeypatch)
    c = app_mod.app.test_client()

    resp = c.post(
        "/racks",
        data={
            "rack_id": "RCK-DC2",
            "name": "Втор ормар за сториџ",
            "location": "Сервер сала 2",
            "units": "48",
            "notes": "Висок 48U ормар",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    rack = app_mod.racks.find("RackID", "RCK-DC2")
    assert rack is not None
    assert rack["Units"] == "48"
    assert "Втор ормар" in rack["Name"]


def test_mount_and_unmount_server(monkeypatch):
    app_mod = _setup_rack_env(monkeypatch)
    c = app_mod.app.test_client()

    # Mount 2U server at U10
    resp = c.post(
        "/racks/assign",
        data={
            "rack_id": "RCK-01",
            "asset_id": "SRV-DELL-R740",
            "start_unit": "10",
            "height_units": "2",
            "notes": "Примарен база сервер",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    items = app_mod.rack_items.filter_eq("RackID", "RCK-01")
    assert len(items) == 1
    item = items[0]
    assert item["AssetID"] == "SRV-DELL-R740"
    assert item["StartUnit"] == "10"
    assert item["HeightUnits"] == "2"

    # View page renders server
    page = c.get("/racks?rack_id=RCK-01").get_data(as_text=True)
    assert "SRV-DELL-R740" in page
    assert "PowerEdge R740" in page

    # Unmount server
    unmount = c.post(
        "/racks/remove",
        data={"item_id": item["ItemID"], "rack_id": "RCK-01"},
        follow_redirects=True,
    )
    assert unmount.status_code == 200
    assert len(app_mod.rack_items.filter_eq("RackID", "RCK-01")) == 0


def test_collision_detection_prevents_overlap(monkeypatch):
    app_mod = _setup_rack_env(monkeypatch)
    c = app_mod.app.test_client()

    # Mount 2U server on U10..U11
    c.post(
        "/racks/assign",
        data={
            "rack_id": "RCK-01",
            "asset_id": "SRV-DELL-R740",
            "start_unit": "10",
            "height_units": "2",
        },
    )

    # Attempt to mount switch on U11..U11 (collision with U11)
    c.post(
        "/racks/assign",
        data={
            "rack_id": "RCK-01",
            "asset_id": "SW-CISCO-2960",
            "start_unit": "11",
            "height_units": "1",
        },
    )
    # Switch must not be mounted
    assert len(app_mod.rack_items.filter_eq("AssetID", "SW-CISCO-2960")) == 0

    # Mount on free slot U12..U12 succeeds
    c.post(
        "/racks/assign",
        data={
            "rack_id": "RCK-01",
            "asset_id": "SW-CISCO-2960",
            "start_unit": "12",
            "height_units": "1",
        },
    )
    assert len(app_mod.rack_items.filter_eq("AssetID", "SW-CISCO-2960")) == 1
