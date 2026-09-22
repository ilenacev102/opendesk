"""JSON API routes (Flask Blueprint): helpers + v1.

App-owned names are imported lazily INSIDE each view so they always resolve
against the live ``app`` module (test monkeypatching keeps working).
Flask/stdlib names are plain top-level imports (no cycle possible).
"""

import time

from flask import Blueprint, request

bp = Blueprint("api", __name__)


@bp.route("/api/v1/devices")
def api_v1_devices():
    from app import _api_user, _require_api_roles, devices

    denied = _require_api_roles("magacioner", "citac")
    if denied is not None:
        return denied
    st = (request.args.get("status") or "").strip()
    tp = (request.args.get("type") or "").strip()
    loc = (request.args.get("location") or "").strip()
    q = (request.args.get("q") or "").strip().lower()
    out = []
    for d in devices.records():
        if st and d.get("Status") != st:
            continue
        if tp and d.get("Type") != tp:
            continue
        if loc and d.get("Location") != loc:
            continue
        if (
            q
            and q
            not in " ".join(
                [
                    d.get("AssetID", ""),
                    d.get("SerialNumber", ""),
                    d.get("Manufacturer", ""),
                    d.get("Model", ""),
                    d.get("EmployeeID", ""),
                ]
            ).lower()
        ):
            continue
        out.append(d)
    return {"results": out, "count": len(out)}


@bp.route("/api/v1/devices/<asset_id>")
def api_v1_device_detail(asset_id):
    from app import _require_api_roles, devices
    from flask import jsonify as _jsonify

    denied = _require_api_roles("magacioner", "citac")
    if denied is not None:
        return denied
    dev = devices.find("AssetID", asset_id)
    if dev is None:
        return _jsonify({"error": "not_found"}), 404
    return dev


@bp.route("/api/v1/employees")
def api_v1_employees():
    from app import _require_api_roles, employees

    denied = _require_api_roles("magacioner", "citac")
    if denied is not None:
        return denied
    return {"results": employees.records()}


@bp.route("/api/v1/checkout", methods=["POST"])
def api_v1_checkout():
    from app import _api_user, _require_api_roles, assign_svc
    from flask import jsonify as _jsonify

    from utils.validators import ValidationError

    denied = _require_api_roles("magacioner")
    if denied is not None:
        return denied
    data = request.get_json(silent=True) or {}
    try:
        tid, doc = assign_svc.confirm(
            (data.get("asset_id") or "").strip(),
            (data.get("emp_id") or "").strip(),
            (data.get("reason") or "").strip(),
            (data.get("notes") or "").strip(),
            getattr(_api_user(), "id", "api"),
        )
    except ValidationError as exc:
        return _jsonify({"error": str(exc)}), 422
    return {"transaction_id": tid, "document": doc}, 201


@bp.route("/api/v1/checkin", methods=["POST"])
def api_v1_checkin():
    from app import _api_user, _require_api_roles, return_svc
    from flask import jsonify as _jsonify

    from utils.validators import ValidationError

    denied = _require_api_roles("magacioner")
    if denied is not None:
        return denied
    data = request.get_json(silent=True) or {}
    try:
        tid, doc = return_svc.confirm(
            (data.get("asset_id") or "").strip(),
            (data.get("emp_id") or "").strip(),
            (data.get("reason") or "").strip(),
            (data.get("condition") or "Good").strip(),
            (data.get("notes") or "").strip(),
            getattr(_api_user(), "id", "api"),
        )
    except ValidationError as exc:
        return _jsonify({"error": str(exc)}), 422
    return {"transaction_id": tid, "document": doc}, 201


@bp.route("/api/v1/history")
def api_v1_history():
    from app import _require_api_roles, history

    denied = _require_api_roles("magacioner", "citac")
    if denied is not None:
        return denied
    asset_id = (request.args.get("asset_id") or "").strip()
    try:
        limit = min(200, max(1, int(request.args.get("limit", "50"))))
    except ValueError:
        limit = 50
    rows = history.recent(5000)
    if asset_id:
        rows = [h for h in rows if h.get("AssetID") == asset_id]
    return {"results": rows[:limit], "count": min(len(rows), limit)}


@bp.route("/api/search")
def api_search():
    from app import devices, employees

    t0 = time.time()
    q = (request.args.get("q") or "").strip().lower()
    out = []
    if len(q) >= 2:
        words = q.split()
        for d in devices.records():
            hay = " ".join(
                [
                    d.get("AssetID", ""),
                    d.get("SerialNumber", ""),
                    d.get("Manufacturer", ""),
                    d.get("Model", ""),
                    d.get("Type", ""),
                    d.get("Status", ""),
                    d.get("EmployeeID", ""),
                ]
            ).lower()
            if all(w in hay for w in words):
                out.append(
                    {
                        "kind": "device",
                        "id": d.get("AssetID", ""),
                        "title": f"{d.get('AssetID', '')} "
                        f"{d.get('Manufacturer', '')} "
                        f"{d.get('Model', '')}",
                        "sub": f"{d.get('SerialNumber', '')} | {d.get('Status', '')}",
                        "url": f"/device/{d.get('AssetID', '')}",
                    }
                )
                if len(out) >= 12:
                    break
        for e in employees.records():
            hay = " ".join(
                [
                    e.get("EmployeeID", ""),
                    e.get("FirstName", ""),
                    e.get("LastName", ""),
                    e.get("UserName", ""),
                    e.get("Email", ""),
                    e.get("Department", ""),
                ]
            ).lower()
            if all(w in hay for w in words):
                out.append(
                    {
                        "kind": "employee",
                        "id": e.get("EmployeeID", ""),
                        "title": f"{e.get('FirstName', '')} {e.get('LastName', '')}",
                        "sub": f"{e.get('EmployeeID', '')} | {e.get('Department', '')}",
                        "url": f"/employee/{e.get('EmployeeID', '')}",
                    }
                )
                if len(out) >= 20:
                    break
    ms = round((time.time() - t0) * 1000)
    return {"results": out, "ms": ms}


@bp.route("/api/next-id")
def api_next_id():
    from app import ID_PREFIX, devices

    dtype = request.args.get("type", "Друго")
    prefix = ID_PREFIX.get(dtype, "AST")
    best = 0
    for r in devices.records():
        aid = r.get("AssetID", "")
        if aid.startswith(prefix):
            try:
                best = max(best, int(aid[len(prefix) :]))
            except ValueError:
                continue
    return {"next_id": f"{prefix}{best + 1:03d}"}


@bp.route("/api/check-serial")
def api_check_serial():
    from app import devices

    sn = (request.args.get("q") or "").strip()
    if not sn:
        return {"exists": False}
    for r in devices.records():
        if r.get("SerialNumber") == sn:
            return {"exists": True, "asset": r.get("AssetID", "")}
    return {"exists": False}


@bp.route("/api/check-asset")
def api_check_asset():
    from app import devices

    aid = (request.args.get("q") or "").strip()
    if not aid:
        return {"exists": False}
    for r in devices.records():
        if r.get("AssetID") == aid:
            return {
                "exists": True,
                "info": f"{r.get('Manufacturer', '')} "
                f"{r.get('Model', '')} | SN: "
                f"{r.get('SerialNumber', '')} | "
                f"{r.get('Status', '')}",
            }
    return {"exists": False}


@bp.route("/api/values")
def api_values():
    from app import devices, employees

    fields = ["Manufacturer", "Model", "Location"]
    out = {}
    for field in fields:
        seen = []
        for r in devices.records():
            val = r.get(field, "")
            if val and val not in seen:
                seen.append(val)
        out[field] = sorted(seen)
    for field in ["Department", "Organization", "Location"]:
        seen = []
        for r in employees.records():
            val = r.get(field, "")
            if val and val not in seen:
                seen.append(val)
        if field == "Location":
            out[field] = sorted(set(out[field]) | set(seen))
        else:
            out[field] = sorted(seen)
    return out
