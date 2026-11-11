"""CMDB Topology Graph & Impact Analysis Engine.

Provides:
- Visual dependency graph (/cmdb/topology)
- Graph data API (/api/v1/cmdb/graph)
- Blast Radius & Impact Calculator (/api/v1/cmdb/impact/<asset_id>)
- CI relationship management (/cmdb/relations/new, /cmdb/relations/delete)
- Detailed asset links view (/cmdb/<asset_id>)
"""

from collections import deque

from flask import (
    Blueprint,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from utils.helpers import next_id
from utils.validators import ValidationError

bp = Blueprint("cmdb", __name__)

log = __import__("logging").getLogger("servicedesk")


@bp.route("/cmdb/<asset_id>")
def cmdb_detail(asset_id):
    from app import (
        cmdb_relations,
        contracts,
        devices,
        employees,
        incidents,
        licenses,
        requests,
        reservations,
    )

    dev = devices.find("AssetID", asset_id)
    if dev is None:
        abort(404)
    emp_id = (dev.get("EmployeeID", "") or "").strip()
    owner = employees.find("EmployeeID", emp_id) if emp_id else None
    linked_licenses = [
        lic for lic in licenses.records() if asset_id in (lic.get("Notes", "") or "")
    ]
    supplier = (dev.get("Supplier", "") or "").strip()
    linked_contracts = contracts.filter_eq("Supplier", supplier) if supplier else []
    linked_reservations = reservations.filter_eq("AssetID", asset_id)
    owner_requests = requests.filter_eq("EmployeeID", emp_id) if emp_id else []
    linked_incidents = incidents.filter_eq("AssetID", asset_id)

    # Custom CMDB explicit relations
    custom_relations = []
    if hasattr(cmdb_relations, "records"):
        for rel in cmdb_relations.records():
            if rel.get("SourceID") == asset_id or rel.get("TargetID") == asset_id:
                custom_relations.append(rel)

    return render_template(
        "cmdb.html",
        dev=dev,
        owner=owner,
        licenses=linked_licenses,
        contracts=linked_contracts,
        reservations=linked_reservations,
        requests=owner_requests,
        incidents=linked_incidents,
        custom_relations=custom_relations,
    )


@bp.route("/cmdb/topology")
def cmdb_topology():
    """Renders the interactive CMDB Topology Graph and Blast Radius view."""
    import app as app_mod

    devices_store = getattr(app_mod, "devices", None)
    employees_store = getattr(app_mod, "employees", None)
    racks_store = getattr(app_mod, "racks", None)

    all_devices = devices_store.records() if devices_store else []
    all_employees = employees_store.records() if employees_store else []
    all_racks = racks_store.records() if racks_store else []

    root_id = request.args.get("root", "").strip()

    return render_template(
        "cmdb_topology.html",
        root_id=root_id,
        devices=all_devices,
        employees=all_employees,
        racks=all_racks,
    )


@bp.route("/api/v1/cmdb/graph")
def api_cmdb_graph():
    """Returns JSON representation of nodes and edges for the topology view."""
    import app as app_mod

    devices_store = getattr(app_mod, "devices", None)
    employees_store = getattr(app_mod, "employees", None)
    racks_store = getattr(app_mod, "racks", None)
    rack_items_store = getattr(app_mod, "rack_items", None)
    relations_store = getattr(app_mod, "cmdb_relations", None)

    root_id = request.args.get("root", "").strip()
    category_filter = request.args.get("type", "").strip()

    nodes_map = {}
    edges = []

    # 1. Device Nodes
    dev_records = devices_store.records() if devices_store else []
    for d in dev_records:
        aid = d.get("AssetID", "").strip()
        if not aid:
            continue
        dev_type = d.get("Type", "Опрема").strip() or "Опрема"
        model_name = f"{d.get('Manufacturer', '')} {d.get('Model', '')}".strip() or dev_type

        # Device categorization
        cat = "other"
        lower_type = dev_type.lower()
        if any(w in lower_type for w in ["server", "сервер", "blade", "vm", "virtual"]):
            cat = "server"
        elif any(w in lower_type for w in ["switch", "свич", "router", "рутер", "firewall", "мреж"]):
            cat = "network"
        elif any(w in lower_type for w in ["laptop", "лаптоп", "desktop", "компјутер", "pc", "workstation"]):
            cat = "endpoint"
        elif any(w in lower_type for w in ["ups", "напојување", "pdu"]):
            cat = "power"

        nodes_map[aid] = {
            "id": aid,
            "label": f"{aid} - {model_name}",
            "type": "device",
            "category": cat,
            "raw_type": dev_type,
            "status": d.get("Status", "Active"),
            "location": d.get("Location", ""),
            "owner": d.get("EmployeeID", ""),
            "is_root": (aid == root_id),
        }

    # 2. Employee Nodes & Implicit "uses" Edges
    emp_records = employees_store.records() if employees_store else []
    emp_by_id = {e.get("EmployeeID", "").strip(): e for e in emp_records if e.get("EmployeeID")}

    for d in dev_records:
        aid = d.get("AssetID", "").strip()
        eid = (d.get("EmployeeID", "") or "").strip()
        if aid and eid and eid in emp_by_id:
            emp = emp_by_id[eid]
            if eid not in nodes_map:
                full_name = f"{emp.get('FirstName', '')} {emp.get('LastName', '')}".strip() or eid
                nodes_map[eid] = {
                    "id": eid,
                    "label": full_name,
                    "type": "employee",
                    "category": "employee",
                    "raw_type": "Вработен",
                    "status": "Active" if emp.get("Active", "YES") == "YES" else "Inactive",
                    "location": emp.get("Location", ""),
                    "dept": emp.get("Department", ""),
                    "is_root": (eid == root_id),
                }
            edges.append({
                "id": f"rel-assign-{aid}-{eid}",
                "source": aid,
                "target": eid,
                "relation": "uses",
                "label": "користи",
                "notes": "Задолжено средство",
            })

    # 3. Rack Nodes & Rack Items "hosts" Edges
    if racks_store:
        for r in racks_store.records():
            rid = r.get("RackID", "").strip()
            if not rid:
                continue
            nodes_map[rid] = {
                "id": rid,
                "label": f"Ормар: {r.get('Name', rid)}",
                "type": "rack",
                "category": "rack",
                "raw_type": "Рек ормар",
                "status": "Active",
                "location": r.get("Location", ""),
                "is_root": (rid == root_id),
            }

    if rack_items_store:
        for item in rack_items_store.records():
            rid = item.get("RackID", "").strip()
            aid = item.get("AssetID", "").strip()
            if rid and aid and rid in nodes_map and aid in nodes_map:
                unit = item.get("StartUnit", "")
                edges.append({
                    "id": f"rel-rack-{rid}-{aid}",
                    "source": rid,
                    "target": aid,
                    "relation": "hosts",
                    "label": f"сместен во (U{unit})" if unit else "сместен во",
                    "notes": item.get("Notes", ""),
                })

    # 4. Explicit CMDB Relations
    if relations_store:
        for rel in relations_store.records():
            sid = rel.get("SourceID", "").strip()
            tid = rel.get("TargetID", "").strip()
            rid = rel.get("RelID", "").strip()
            relation = rel.get("Relation", "connected_to").strip()
            stype = rel.get("SourceType", "device").strip()
            ttype = rel.get("TargetType", "device").strip()

            if not sid or not tid:
                continue

            # Ensure virtual service / external nodes exist
            for nid, ntype in [(sid, stype), (tid, ttype)]:
                if nid not in nodes_map:
                    nodes_map[nid] = {
                        "id": nid,
                        "label": nid,
                        "type": ntype,
                        "category": ntype if ntype in ("service", "software") else "other",
                        "raw_type": ntype.title(),
                        "status": "Active",
                        "is_root": (nid == root_id),
                    }

            edges.append({
                "id": rid or f"rel-{sid}-{tid}-{relation}",
                "source": sid,
                "target": tid,
                "relation": relation,
                "label": relation,
                "notes": rel.get("Notes", ""),
            })

    # Optional category filter
    nodes_list = list(nodes_map.values())
    if category_filter:
        nodes_list = [n for n in nodes_list if n.get("category") == category_filter or n.get("type") == category_filter]
        allowed_ids = {n["id"] for n in nodes_list}
        edges = [e for e in edges if e["source"] in allowed_ids and e["target"] in allowed_ids]

    return jsonify({"nodes": nodes_list, "edges": edges, "root": root_id})


@bp.route("/api/v1/cmdb/impact/<asset_id>")
def api_cmdb_impact(asset_id):
    """Calculates the Blast Radius and cascading dependencies of an asset during an outage or change."""
    import app as app_mod

    devices_store = getattr(app_mod, "devices", None)
    employees_store = getattr(app_mod, "employees", None)
    racks_store = getattr(app_mod, "racks", None)
    rack_items_store = getattr(app_mod, "rack_items", None)
    relations_store = getattr(app_mod, "cmdb_relations", None)

    dev_records = {d["AssetID"]: d for d in devices_store.records() if d.get("AssetID")} if devices_store else {}
    emp_records = {e["EmployeeID"]: e for e in employees_store.records() if e.get("EmployeeID")} if employees_store else {}
    rack_records = {r["RackID"]: r for r in racks_store.records() if r.get("RackID")} if racks_store else {}

    root_dev = dev_records.get(asset_id)
    root_rack = rack_records.get(asset_id)

    # Build adjacency list: node -> set of neighbors
    adj = {}

    def add_edge(u, v):
        adj.setdefault(u, set()).add(v)
        adj.setdefault(v, set()).add(u)

    # 1. Device <-> Employee
    for aid, d in dev_records.items():
        eid = (d.get("EmployeeID", "") or "").strip()
        if eid:
            add_edge(aid, eid)

    # 2. Rack <-> Device
    if rack_items_store:
        for item in rack_items_store.records():
            rid = item.get("RackID", "").strip()
            aid = item.get("AssetID", "").strip()
            if rid and aid:
                add_edge(rid, aid)

    # 3. CMDB Relations
    if relations_store:
        for rel in relations_store.records():
            sid = rel.get("SourceID", "").strip()
            tid = rel.get("TargetID", "").strip()
            if sid and tid:
                add_edge(sid, tid)

    # Breadth-First Search (BFS) to compute Blast Radius
    visited = set()
    queue = deque([(asset_id, 0)])
    visited.add(asset_id)

    max_hops = 4
    impacted_devices = []
    impacted_employees = []
    impacted_services = []
    impacted_racks = []

    while queue:
        curr, depth = queue.popleft()
        if depth >= max_hops:
            continue

        for neighbor in adj.get(curr, []):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, depth + 1))

                # Classify impacted entity
                if neighbor in dev_records:
                    d = dev_records[neighbor]
                    impacted_devices.append({
                        "id": neighbor,
                        "name": f"{d.get('Manufacturer', '')} {d.get('Model', '')}".strip() or d.get("Type", "Уред"),
                        "type": d.get("Type", "Уред"),
                        "status": d.get("Status", ""),
                        "location": d.get("Location", ""),
                        "owner": d.get("EmployeeID", ""),
                    })
                elif neighbor in emp_records:
                    e = emp_records[neighbor]
                    impacted_employees.append({
                        "id": neighbor,
                        "name": f"{e.get('FirstName', '')} {e.get('LastName', '')}".strip() or neighbor,
                        "dept": e.get("Department", ""),
                        "email": e.get("Email", ""),
                    })
                elif neighbor in rack_records:
                    r = rack_records[neighbor]
                    impacted_racks.append({
                        "id": neighbor,
                        "name": r.get("Name", neighbor),
                        "location": r.get("Location", ""),
                    })
                else:
                    # Generic service or software
                    impacted_services.append({
                        "id": neighbor,
                        "name": neighbor,
                    })

    total_impacted = len(impacted_devices) + len(impacted_employees) + len(impacted_services) + len(impacted_racks)

    # Calculate severity score
    if total_impacted >= 10:
        score = "critical"
        label = "Критичен"
    elif total_impacted >= 5:
        score = "high"
        label = "Висок"
    elif total_impacted >= 2:
        score = "medium"
        label = "Среден"
    else:
        score = "low"
        label = "Низок"

    target_name = asset_id
    target_type = "CI"
    target_status = ""
    target_location = ""
    if root_dev:
        target_name = f"{root_dev.get('Manufacturer', '')} {root_dev.get('Model', '')}".strip() or asset_id
        target_type = root_dev.get("Type", "Уред")
        target_status = root_dev.get("Status", "")
        target_location = root_dev.get("Location", "")
    elif root_rack:
        target_name = f"Ормар {root_rack.get('Name', asset_id)}"
        target_type = "Рек ормар"
        target_location = root_rack.get("Location", "")

    return jsonify({
        "target": {
            "id": asset_id,
            "name": target_name,
            "type": target_type,
            "status": target_status,
            "location": target_location,
        },
        "impacted_devices": impacted_devices,
        "impacted_employees": impacted_employees,
        "impacted_services": impacted_services,
        "impacted_racks": impacted_racks,
        "total_impacted": total_impacted,
        "blast_radius_score": score,
        "blast_radius_label": label,
        "affected_ids": list(visited),
    })


@bp.route("/cmdb/relations/new", methods=["POST"])
def cmdb_relation_new():
    """Creates a new CI dependency relation in CMDB."""
    import app as app_mod
    import config

    relations_store = getattr(app_mod, "cmdb_relations", None)

    is_json = request.is_json
    data = request.get_json(silent=True) or request.form

    source_type = data.get("source_type", "device").strip()
    source_id = data.get("source_id", "").strip()
    relation = data.get("relation", "connected_to").strip()
    target_type = data.get("target_type", "device").strip()
    target_id = data.get("target_id", "").strip()
    notes = data.get("notes", "").strip()

    try:
        if not source_id or not target_id:
            raise ValidationError("Изворното и целното средство/CI се задолжителни.")
        if source_id == target_id:
            raise ValidationError("Средството не може да биде поврзано само со себе.")
        if not relations_store:
            raise ValidationError("Складиштето за CMDB релации е недостапно.")

        rel_id = next_id(relations_store, "RelID", "REL-")
        relations_store.append_row({
            "RelID": rel_id,
            "SourceType": source_type,
            "SourceID": source_id,
            "Relation": relation,
            "TargetType": target_type,
            "TargetID": target_id,
            "Notes": notes,
        })

        if config.BACKUP_ON_WRITE and hasattr(app_mod, "backup_all"):
            app_mod.backup_all([relations_store])

        if is_json:
            return jsonify({"status": "ok", "rel_id": rel_id})

        flash(f"Успешно креирана CMDB релација {rel_id}: {source_id} -> {relation} -> {target_id}", "success")
        return redirect(url_for("cmdb.cmdb_topology", root=source_id))

    except ValidationError as exc:
        if is_json:
            return jsonify({"status": "error", "message": str(exc)}), 400
        flash(f"ГРЕШКА: {exc}", "danger")
        return redirect(url_for("cmdb.cmdb_topology", root=source_id))


@bp.route("/cmdb/relations/delete/<rel_id>", methods=["POST"])
def cmdb_relation_delete(rel_id):
    """Deletes an explicit CMDB relation."""
    import app as app_mod
    import config

    relations_store = getattr(app_mod, "cmdb_relations", None)
    redirect_target = request.form.get("redirect_to", "")

    try:
        if not relations_store:
            raise ValidationError("Складиштето за CMDB релации е недостапно.")

        if hasattr(relations_store, "delete_where"):
            relations_store.delete_where("RelID", rel_id)

        if config.BACKUP_ON_WRITE and hasattr(app_mod, "backup_all"):
            app_mod.backup_all([relations_store])

        flash(f"CMDB релацијата {rel_id} е успешно избришана.", "success")
    except ValidationError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")

    if redirect_target:
        return redirect(redirect_target)
    return redirect(url_for("cmdb.cmdb_topology"))
