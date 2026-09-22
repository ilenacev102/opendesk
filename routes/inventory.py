"""Inventory routes (Flask Blueprint): employees, devices, departments, locations.

App-owned names (stores, services, shared helpers) are imported lazily INSIDE
each view so they always resolve against the live ``app`` module object.
That keeps test monkeypatching of ``app`` attributes working.
"""

import sqlite3

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from services.schemas import DEV_COLS, EMP_COLS
from utils.validators import ValidationError

bp = Blueprint("inventory", __name__)

log = __import__("logging").getLogger("servicedesk")


@bp.route("/employees")
def employee_list():
    from app import employees

    return render_template("employees.html", employees=employees.records())


@bp.route("/employees/new", methods=["GET", "POST"])
def employee_new():
    from app import backup_all, employees

    import config

    if request.method == "POST":
        data = {c: request.form.get(c, "").strip() for c in EMP_COLS}
        try:
            if not data["EmployeeID"]:
                raise ValidationError("EmployeeID е задолжителен.")
            if employees.find("EmployeeID", data["EmployeeID"]):
                raise ValidationError(f"Вработениот {data['EmployeeID']} веќе постои.")
            if not data["Active"]:
                data["Active"] = "YES"
            employees.append_row(data)
            if config.BACKUP_ON_WRITE:
                backup_all([employees])
            same_name = [
                e
                for e in employees.records()
                if e.get("EmployeeID") != data["EmployeeID"]
                and (e.get("FirstName", ""), e.get("LastName", ""))
                == (data["FirstName"], data["LastName"])
                and (data["FirstName"] or data["LastName"])
            ]
            if same_name:
                flash(
                    f"ВНИМАНИЕ: можен дупликат — {data['FirstName']} "
                    f"{data['LastName']} веќе постои како "
                    f"{same_name[0].get('EmployeeID', '')}.",
                    "warning",
                )
            else:
                flash(f"Вработениот {data['EmployeeID']} е внесен.", "success")
            return redirect(
                url_for("inventory.employee_detail", emp_id=data["EmployeeID"])
            )
        except ValidationError as exc:
            flash(f"ГРЕШКА: {exc}", "danger")
    prefill = (request.args.get("prefill", "") or "").strip().split()
    return render_template(
        "employee_new.html",
        first=prefill[0] if len(prefill) > 0 else "",
        last=" ".join(prefill[1:]) if len(prefill) > 1 else "",
    )


@bp.route("/employee/<emp_id>")
def employee_detail(emp_id):
    from app import _row, devices, employees, history

    emp = _row(employees, "EmployeeID", emp_id)
    mine = devices.filter_eq("EmployeeID", emp_id)
    hist = history.for_employee(emp_id)
    return render_template("employee.html", emp=emp, devices=mine, hist=hist)


@bp.route("/devices/new", methods=["GET", "POST"])
def device_new():
    from app import backup_all, devices, history

    import config

    if request.method == "POST":
        data = {c: request.form.get(c, "").strip() for c in DEV_COLS}
        try:
            if not data["AssetID"]:
                raise ValidationError("Asset ID е задолжителен.")
            if devices.find("AssetID", data["AssetID"]):
                raise ValidationError(f"AssetID {data['AssetID']} веќе постои.")
            if data["SerialNumber"]:
                dup = [
                    d
                    for d in devices.records()
                    if d.get("SerialNumber") == data["SerialNumber"]
                ]
                if dup:
                    raise ValidationError(
                        f"Серискиот број веќе постои кај {dup[0]['AssetID']}."
                    )
            if not data["Status"]:
                data["Status"] = "Available"
            devices.append_row(data)
            if config.BACKUP_ON_WRITE:
                backup_all([devices])
            history.log(
                "CREATE",
                data["AssetID"],
                "",
                data["Status"],
                "",
                "",
                "Нов внес",
                "",
                "admin",
                "",
            )
            flash(f"Уредот {data['AssetID']} е внесен.", "success")
            if "add_another" in request.form:
                return redirect(url_for("inventory.device_new"))
            return redirect(
                url_for("inventory.device_detail", asset_id=data["AssetID"])
            )
        except ValidationError as exc:
            flash(f"ГРЕШКА: {exc}", "danger")
        except sqlite3.IntegrityError:
            flash("ГРЕШКА: Asset ID или серискиот број веќе постои.", "danger")
    prefill = {c: "" for c in DEV_COLS}
    src = devices.find("AssetID", (request.args.get("clone", "") or "").strip())
    if src is not None:
        for c in DEV_COLS:
            if c not in ("AssetID", "SerialNumber", "EmployeeID"):
                prefill[c] = src.get(c, "")
        prefill["Status"] = "Available"
    return render_template("device_new.html", prefill=prefill)


@bp.route("/devices/bulk", methods=["GET", "POST"])
def device_bulk():
    from app import ID_PREFIX, backup_all, devices, history

    import config

    if request.method == "POST":
        dtype = request.form.get("Type", "Друго").strip() or "Друго"
        shared = {
            "Type": dtype,
            "Manufacturer": request.form.get("Manufacturer", "").strip(),
            "Model": request.form.get("Model", "").strip(),
            "Location": request.form.get("Location", "").strip(),
            "PurchaseDate": request.form.get("PurchaseDate", "").strip(),
            "WarrantyUntil": request.form.get("WarrantyUntil", "").strip(),
            "PurchasePrice": request.form.get("PurchasePrice", "").strip(),
            "Supplier": request.form.get("Supplier", "").strip(),
            "Notes": request.form.get("Notes", "").strip(),
            "Status": "Available",
            "EmployeeID": "",
        }
        prefix = ID_PREFIX.get(dtype, "AST")
        best = 0
        for r in devices.records():
            aid = r.get("AssetID", "")
            if aid.startswith(prefix):
                try:
                    best = max(best, int(aid[len(prefix) :]))
                except ValueError:
                    continue
        created, skipped = [], []
        seen = set()
        for line in (request.form.get("serials", "") or "").splitlines():
            sn = line.strip()
            if not sn or sn in seen:
                continue
            seen.add(sn)
            dup = [d for d in devices.records() if d.get("SerialNumber") == sn]
            if dup:
                skipped.append(sn)
                continue
            best += 1
            aid = f"{prefix}{best:03d}"
            while devices.find("AssetID", aid):
                best += 1
                aid = f"{prefix}{best:03d}"
            data = dict(shared)
            data.update({"AssetID": aid, "SerialNumber": sn})
            try:
                devices.append_row(data)
            except sqlite3.IntegrityError:
                skipped.append(sn)
                continue
            history.log(
                "CREATE", aid, "", "Available", "", "", "Bulk внес", "", "admin", ""
            )
            created.append(aid)
        if config.BACKUP_ON_WRITE:
            backup_all([devices])
        flash(
            f"Создадени {len(created)} уреди"
            + (f" ({', '.join(created)})" if created else "")
            + (
                f". Прескокнати {len(skipped)}: {', '.join(skipped)}."
                if skipped
                else "."
            ),
            "success" if created else "warning",
        )
        return redirect(url_for("inventory.device_list"))
    return render_template("device_bulk.html")


@bp.route("/devices")
def device_list():
    from app import devices, warranty_days, warranty_level

    wf = request.args.get("w", "")
    st = request.args.get("status", "").strip()
    tp = request.args.get("type", "").strip()
    loc = request.args.get("loc", "").strip()
    q = request.args.get("q", "").strip().lower()

    raw_devs = devices.records()
    statuses = sorted({d.get("Status") for d in raw_devs if d.get("Status")})
    types = sorted({d.get("Type") for d in raw_devs if d.get("Type")})
    locations = sorted({d.get("Location") for d in raw_devs if d.get("Location")})

    filtered = []
    for d in raw_devs:
        if st and d.get("Status") != st:
            continue
        if tp and d.get("Type") != tp:
            continue
        if loc and d.get("Location") != loc:
            continue
        if q:
            haystack = " ".join(
                [
                    d.get("AssetID", ""),
                    d.get("SerialNumber", ""),
                    d.get("Manufacturer", ""),
                    d.get("Model", ""),
                    d.get("EmployeeID", ""),
                    d.get("Notes", ""),
                ]
            ).lower()
            if not all(w in haystack for w in q.split()):
                continue
        days = warranty_days(d.get("WarrantyUntil", ""))
        if days is not None:
            level, text = warranty_level(days)
            d["WLevel"], d["WText"] = level, text
        if wf in ("expiring", "expired"):
            if days is None or (
                days >= 0 if wf == "expired" else not (0 <= days <= 90)
            ):
                continue
        filtered.append(d)

    try:
        page = max(1, int(request.args.get("page", "1")))
    except ValueError:
        page = 1
    try:
        per = min(500, max(10, int(request.args.get("per", "50"))))
    except ValueError:
        per = 50
    total = len(filtered)
    total_pages = max(1, (total + per - 1) // per)
    if page > total_pages:
        page = total_pages
    start = (page - 1) * per
    return render_template(
        "devices.html",
        devices=filtered[start : start + per],
        wf=wf,
        st=st,
        tp=tp,
        loc=loc,
        q=q,
        statuses=statuses,
        types=types,
        locations=locations,
        page=page,
        per=per,
        total=total,
        total_pages=total_pages,
    )


@bp.route("/device/<asset_id>")
def device_detail(asset_id):
    from app import _row, devices, employees, field_defs, field_values, history

    dev = _row(devices, "AssetID", asset_id)
    emp = None
    if dev.get("EmployeeID"):
        holder = employees.find("EmployeeID", dev["EmployeeID"])
        if holder is not None:
            emp = f"{holder['FirstName']} {holder['LastName']}"
    hist = history.for_asset(asset_id)
    docs = [h for h in hist if h.get("DocumentPath")]
    emails = {}
    for h in hist:
        eid = h.get("EmployeeID", "")
        if eid and eid not in emails:
            holder_rec = employees.find("EmployeeID", eid)
            emails[eid] = holder_rec.get("Email", "") if holder_rec else ""
    status = dev.get("Status", "")
    actions = []
    if status == "Available":
        actions = [("Задолжи", f"/assign?asset={asset_id}", "primary")]
    elif status == "Assigned":
        actions = [
            ("Раздолжи", f"/return?asset={asset_id}", "secondary"),
            (
                "Замени",
                f"/replace?old={asset_id}&emp={dev.get('EmployeeID', '')}",
                "warning",
            ),
            ("Пријави расипан", f"/repair?asset={asset_id}", "danger"),
        ]
    elif status == "Broken":
        actions = [("Испрати на сервис", f"/repair?asset={asset_id}", "warning")]
    elif status in ("Repair", "Repaired"):
        actions = [("Следен сервис-статус", f"/repair?asset={asset_id}", "primary")]
    if status != "Disposed":
        actions.append(("Расход", f"/dispose?asset={asset_id}", "danger"))
    _val_by_field = {
        v.get("FieldID", ""): v.get("Value", "")
        for v in field_values.records()
        if v.get("AssetID") == asset_id
    }
    cfields = [
        {
            "FieldID": d.get("FieldID", ""),
            "FieldName": d.get("FieldName", ""),
            "Value": _val_by_field.get(d.get("FieldID", ""), ""),
        }
        for d in field_defs.records()
    ]
    return render_template(
        "device.html",
        dev=dev,
        emp=emp,
        docs=docs,
        actions=actions,
        hist=hist,
        emails=emails,
        cfields=cfields,
    )


@bp.route("/departments")
def department_list():
    from app import devices, employees

    emps = employees.records()
    devs = devices.records()
    names = sorted({e.get("Department", "") for e in emps if e.get("Department")})
    cards = []
    for name in names:
        members = [e for e in emps if e.get("Department") == name]
        ids = {e["EmployeeID"] for e in members}
        mine = [d for d in devs if d.get("EmployeeID") in ids]
        cards.append(
            {
                "name": name,
                "people": len(members),
                "devices": len(mine),
                "assigned": sum(1 for d in mine if d.get("Status") == "Assigned"),
            }
        )
    return render_template("departments.html", cards=cards)


@bp.route("/department/<name>")
def department_detail(name):
    from app import devices, employees, warranty_days, warranty_level

    emps = employees.records()
    members = [e for e in emps if e.get("Department") == name]
    if not members:
        abort(404)
    devs = devices.records()
    ids = {e["EmployeeID"] for e in members}
    mine = [d for d in devs if d.get("EmployeeID") in ids]
    for d in mine:
        holder = employees.find("EmployeeID", d.get("EmployeeID", ""))
        d["HolderName"] = (
            f"{holder['FirstName']} {holder['LastName']}" if holder else ""
        )
        days = warranty_days(d.get("WarrantyUntil", ""))
        level, text = warranty_level(days)
        d["WLevel"], d["WText"] = level, text
    return render_template("department.html", name=name, members=members, devices=mine)


@bp.route("/locations")
def location_list():
    from app import devices, employees

    emps = employees.records()
    devs = devices.records()
    names = sorted(
        {e.get("Location", "") for e in emps if e.get("Location")}
        | {d.get("Location", "") for d in devs if d.get("Location")}
    )
    cards = []
    for name in names:
        members = [e for e in emps if e.get("Location") == name]
        mine = [d for d in devs if d.get("Location") == name]
        cards.append(
            {
                "name": name,
                "people": len(members),
                "devices": len(mine),
                "assigned": sum(1 for d in mine if d.get("Status") == "Assigned"),
            }
        )
    return render_template("locations.html", cards=cards)


@bp.route("/location/<name>")
def location_detail(name):
    from app import devices, employees, warranty_days, warranty_level

    emps = employees.records()
    devs = devices.records()
    members = [e for e in emps if e.get("Location") == name]
    mine = [d for d in devs if d.get("Location") == name]
    if not members and not mine:
        abort(404)
    for d in mine:
        holder = employees.find("EmployeeID", d.get("EmployeeID", ""))
        d["HolderName"] = (
            f"{holder['FirstName']} {holder['LastName']}" if holder else "—"
        )
        days = warranty_days(d.get("WarrantyUntil", ""))
        level, text = warranty_level(days)
        d["WLevel"], d["WText"] = level, text
    return render_template("location.html", name=name, members=members, devices=mine)
