"""CMDB minimal links view: one asset with its related records.

Read-only. Links are conventional (AssetID in license Notes, shared
Supplier, owner EmployeeID) — no invented foreign keys. Each store is read
at most once per request (no N+1).
"""

from flask import Blueprint, abort, render_template

bp = Blueprint("cmdb", __name__)

log = __import__("logging").getLogger("servicedesk")


@bp.route("/cmdb/<asset_id>")
def cmdb_detail(asset_id):
    from app import (
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
    return render_template(
        "cmdb.html",
        dev=dev,
        owner=owner,
        licenses=linked_licenses,
        contracts=linked_contracts,
        reservations=linked_reservations,
        requests=owner_requests,
        incidents=linked_incidents,
    )
