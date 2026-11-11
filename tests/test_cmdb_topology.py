"""Tests for Sprint 5: CMDB Topology Graph & Impact Analysis Engine (/cmdb/topology)."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _setup_topology_env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.schemas import (
        CMDB_REL_COLS,
        DEV_COLS,
        EMP_COLS,
        RACK_COLS,
        RACK_ITEM_COLS,
    )

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "topo.db")

    dev_store = DbStore(db, "devices", DEV_COLS)
    emp_store = DbStore(db, "employees", EMP_COLS)
    rack_store = DbStore(db, "racks", RACK_COLS)
    rack_item_store = DbStore(db, "rack_items", RACK_ITEM_COLS)
    rel_store = DbStore(db, "cmdb_relations", CMDB_REL_COLS)

    monkeypatch.setattr(app_mod, "devices", dev_store)
    monkeypatch.setattr(app_mod, "employees", emp_store)
    monkeypatch.setattr(app_mod, "racks", rack_store)
    monkeypatch.setattr(app_mod, "rack_items", rack_item_store)
    monkeypatch.setattr(app_mod, "cmdb_relations", rel_store)
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)
    monkeypatch.setitem(app_mod.PATHS, "db", db)

    # Seed test topology:
    # Rack 1 (RCK-01) hosts Switch 1 (SW-CORE-01) and Server 1 (SRV-APP-01)
    rack_store.append_row({
        "RackID": "RCK-01",
        "Name": "Server Rack A1",
        "Location": "Датацентар Скопје",
        "Units": "42",
        "Notes": "Главен рек",
    })

    dev_store.append_row({
        "AssetID": "SW-CORE-01",
        "Type": "Switch",
        "Manufacturer": "Cisco",
        "Model": "Catalyst 9300",
        "SerialNumber": "FOC12345678",
        "Status": "Active",
        "EmployeeID": "",
        "Location": "Датацентар Скопје",
    })
    dev_store.append_row({
        "AssetID": "SRV-APP-01",
        "Type": "Server",
        "Manufacturer": "Dell",
        "Model": "PowerEdge R750",
        "SerialNumber": "CN12345678",
        "Status": "Active",
        "EmployeeID": "",
        "Location": "Датацентар Скопје",
    })
    dev_store.append_row({
        "AssetID": "LAP-001",
        "Type": "Laptop",
        "Manufacturer": "Lenovo",
        "Model": "ThinkPad T14",
        "SerialNumber": "PF12345678",
        "Status": "Active",
        "EmployeeID": "EMP-001",
        "Location": "ИТ Канцеларија",
    })

    emp_store.append_row({
        "EmployeeID": "EMP-001",
        "FirstName": "Ана",
        "LastName": "Стојанова",
        "UserName": "ana.s",
        "Email": "ana@example.com",
        "Department": "Развој",
        "Active": "YES",
    })

    rack_item_store.append_row({
        "ItemID": "ITM-01",
        "RackID": "RCK-01",
        "AssetID": "SW-CORE-01",
        "StartUnit": "40",
        "HeightUnits": "1",
        "Notes": "Core Switch",
    })
    rack_item_store.append_row({
        "ItemID": "ITM-02",
        "RackID": "RCK-01",
        "AssetID": "SRV-APP-01",
        "StartUnit": "20",
        "HeightUnits": "2",
        "Notes": "App Server",
    })

    # Explicit relations:
    # Switch connects to Server
    # Server hosts ERP Service
    rel_store.append_row({
        "RelID": "REL-000001",
        "SourceType": "device",
        "SourceID": "SW-CORE-01",
        "Relation": "connected_to",
        "TargetType": "device",
        "TargetID": "SRV-APP-01",
        "Notes": "Trunk port Gi1/0/1",
    })
    rel_store.append_row({
        "RelID": "REL-000002",
        "SourceType": "device",
        "SourceID": "SRV-APP-01",
        "Relation": "hosts",
        "TargetType": "service",
        "TargetID": "SRV-ERP-SYSTEM",
        "Notes": "Docker Production ERP",
    })

    return app_mod


def test_cmdb_topology_render(monkeypatch):
    """GET /cmdb/topology renders page with canvas and controls."""
    app_mod = _setup_topology_env(monkeypatch)
    c = app_mod.app.test_client()

    resp = c.get("/cmdb/topology?root=SW-CORE-01")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "cmdbCanvas" in html
    assert "SW-CORE-01" in html
    assert "Blast Radius" in html
    assert "btnCalcImpact" in html
    assert "cmdb-graph.js" in html


def test_cmdb_graph_api_returns_nodes_and_edges(monkeypatch):
    """GET /api/v1/cmdb/graph returns full topology graph data in JSON format."""
    app_mod = _setup_topology_env(monkeypatch)
    c = app_mod.app.test_client()

    resp = c.get("/api/v1/cmdb/graph")
    assert resp.status_code == 200
    data = resp.get_json()

    assert "nodes" in data
    assert "edges" in data

    node_ids = {n["id"] for n in data["nodes"]}
    # Check that devices, racks, employees, and virtual services exist in nodes
    assert "SW-CORE-01" in node_ids
    assert "SRV-APP-01" in node_ids
    assert "LAP-001" in node_ids
    assert "EMP-001" in node_ids
    assert "RCK-01" in node_ids
    assert "SRV-ERP-SYSTEM" in node_ids

    # Check edges
    edge_pairs = {(e["source"], e["target"], e["relation"]) for e in data["edges"]}
    assert ("SW-CORE-01", "SRV-APP-01", "connected_to") in edge_pairs
    assert ("SRV-APP-01", "SRV-ERP-SYSTEM", "hosts") in edge_pairs
    assert ("LAP-001", "EMP-001", "uses") in edge_pairs


def test_cmdb_impact_analysis_engine(monkeypatch):
    """GET /api/v1/cmdb/impact/<id> traverses graph and calculates cascading blast radius."""
    app_mod = _setup_topology_env(monkeypatch)
    c = app_mod.app.test_client()

    # Calculate impact of taking down SW-CORE-01
    resp = c.get("/api/v1/cmdb/impact/SW-CORE-01")
    assert resp.status_code == 200
    impact = resp.get_json()

    assert impact["target"]["id"] == "SW-CORE-01"
    assert impact["target"]["type"] == "Switch"

    affected = set(impact["affected_ids"])
    # Downstream server, ERP service, and rack host should be in affected
    assert "SRV-APP-01" in affected
    assert "SRV-ERP-SYSTEM" in affected
    assert "RCK-01" in affected

    assert impact["total_impacted"] >= 3
    assert impact["blast_radius_score"] in ("medium", "high", "critical")
    assert impact["blast_radius_label"] in ("Среден", "Висок", "Критичен")


def test_cmdb_relations_create_and_validation(monkeypatch):
    """POST /cmdb/relations/new creates relation and rejects invalid inputs."""
    app_mod = _setup_topology_env(monkeypatch)
    c = app_mod.app.test_client()

    # Self-referencing link must fail
    resp_fail = c.post(
        "/cmdb/relations/new",
        json={
            "source_id": "SW-CORE-01",
            "target_id": "SW-CORE-01",
            "relation": "connected_to",
        },
    )
    assert resp_fail.status_code == 400
    assert "само со себе" in resp_fail.get_json()["message"]

    # Valid link via JSON
    resp_ok = c.post(
        "/cmdb/relations/new",
        json={
            "source_type": "device",
            "source_id": "SW-CORE-01",
            "relation": "connected_to",
            "target_type": "device",
            "target_id": "LAP-001",
            "notes": "Access Port Gi1/0/5",
        },
    )
    assert resp_ok.status_code == 200
    data = resp_ok.get_json()
    assert data["status"] == "ok"
    assert data["rel_id"].startswith("REL-")

    # Verify link is saved in store
    rel_row = app_mod.cmdb_relations.find("RelID", data["rel_id"])
    assert rel_row is not None
    assert rel_row["SourceID"] == "SW-CORE-01"
    assert rel_row["TargetID"] == "LAP-001"


def test_cmdb_relations_delete(monkeypatch):
    """POST /cmdb/relations/delete/<rel_id> removes relation from store."""
    app_mod = _setup_topology_env(monkeypatch)
    c = app_mod.app.test_client()

    # Precondition: REL-000001 exists
    assert app_mod.cmdb_relations.find("RelID", "REL-000001") is not None

    resp = c.post("/cmdb/relations/delete/REL-000001", follow_redirects=True)
    assert resp.status_code == 200
    assert app_mod.cmdb_relations.find("RelID", "REL-000001") is None
