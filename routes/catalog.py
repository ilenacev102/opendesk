"""Catalog routes (Flask Blueprint): consumables, licenses, contracts,
reservations, requests, custom fields.

App-owned names (stores, services, shared helpers) are imported lazily INSIDE
each view so they always resolve against the live ``app`` module object.
That keeps test monkeypatching of ``app`` attributes working.
"""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from routes._roles import require
from utils.validators import ValidationError

bp = Blueprint("catalog", __name__)

log = __import__("logging").getLogger("servicedesk")


def _parse_seats(raw):
    try:
        val = int(str(raw or "").strip())
    except ValueError:
        raise ValidationError("Бројот на седишта мора да е цел број.")
    if val < 0:
        raise ValidationError("Бројот на седишта не може да е негативен.")
    return val


def _license_seat_change(lid, delta, emp_id, action):
    from app import backup_all, history, licenses

    import config

    row = licenses.find("LicenseID", lid)
    if row is None:
        raise ValidationError(f"Лиценцата {lid} не постои.")
    seats = _parse_seats(row.get("Seats", "0"))
    used = _parse_seats(row.get("SeatsUsed", "0"))
    new_used = used + delta
    if new_used < 0 or new_used > seats:
        raise ValidationError(f"Недозволено: зафатени {used} од {seats} седишта.")
    licenses.update_where("LicenseID", lid, {"SeatsUsed": str(new_used)})
    if config.BACKUP_ON_WRITE:
        backup_all([licenses])
    history.log(action, lid, str(used), str(new_used), emp_id, "", "", "", "admin", "")
    return new_used


def _parse_day(raw, label):
    import datetime as _dt

    try:
        return _dt.date.fromisoformat((raw or "").strip()[:10])
    except ValueError:
        raise ValidationError(f"Невалиден датум: {label}.")


@bp.route("/consumables", methods=["GET", "POST"])
def consumables_view():
    from app import _parse_qty, backup_all, consumables, history

    import config

    if request.method == "POST":
        cid = request.form.get("ConsumableID", "").strip()
        try:
            if not cid:
                raise ValidationError("ID е задолжителен.")
            if consumables.find("ConsumableID", cid):
                raise ValidationError(f"{cid} веќе постои.")
            consumables.append_row(
                {
                    "ConsumableID": cid,
                    "Name": request.form.get("Name", "").strip(),
                    "Category": request.form.get("Category", "").strip(),
                    "Quantity": str(_parse_qty(request.form.get("Quantity", "0"))),
                    "MinLevel": str(_parse_qty(request.form.get("MinLevel", "0"))),
                    "Location": request.form.get("Location", "").strip(),
                    "Notes": request.form.get("Notes", "").strip(),
                }
            )
            if config.BACKUP_ON_WRITE:
                backup_all([consumables])
            flash(f"Материјалот {cid} е внесен.", "success")
        except ValidationError as exc:
            flash(f"ГРЕШКА: {exc}", "danger")
        return redirect(url_for("catalog.consumables_view"))
    rows = consumables.records()
    low_ids = set()
    for r in rows:
        try:
            if int(r.get("Quantity") or 0) <= int(r.get("MinLevel") or 0):
                low_ids.add(r.get("ConsumableID", ""))
        except ValueError:
            pass
    return render_template("consumables.html", rows=rows, low_ids=low_ids)


@bp.route("/consumables/issue", methods=["POST"])
def consumables_issue():
    from app import _parse_qty, backup_all, consumables, history

    import config

    cid = request.form.get("consumable_id", "").strip()
    try:
        row = consumables.find("ConsumableID", cid)
        if row is None:
            raise ValidationError(f"Материјалот {cid} не постои.")
        qty = _parse_qty(request.form.get("qty", "0"))
        if qty <= 0:
            raise ValidationError("Количината мора да е позитивна.")
        stock = _parse_qty(row.get("Quantity", "0"))
        if qty > stock:
            raise ValidationError(f"Нема доволно залиха (достапно: {stock}).")
        new_stock = stock - qty
        consumables.update_where("ConsumableID", cid, {"Quantity": str(new_stock)})
        if config.BACKUP_ON_WRITE:
            backup_all([consumables])
        history.log(
            "CONSUME",
            cid,
            str(stock),
            str(new_stock),
            request.form.get("emp_id", "").strip(),
            "",
            request.form.get("notes", "").strip(),
            "",
            "admin",
            "",
        )
        flash(f"Издадени {qty} од {cid}. Преостанато: {new_stock}.", "success")
    except ValidationError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")
    return redirect(url_for("catalog.consumables_view"))


@bp.route("/licenses", methods=["GET", "POST"])
def licenses_view():
    from app import backup_all, licenses

    import config

    if request.method == "POST":
        lid = request.form.get("LicenseID", "").strip()
        try:
            if not lid:
                raise ValidationError("ID е задолжителен.")
            if licenses.find("LicenseID", lid):
                raise ValidationError(f"{lid} веќе постои.")
            licenses.append_row(
                {
                    "LicenseID": lid,
                    "Software": request.form.get("Software", "").strip(),
                    "LicenseKey": request.form.get("LicenseKey", "").strip(),
                    "Seats": str(_parse_seats(request.form.get("Seats", "1"))),
                    "SeatsUsed": "0",
                    "ExpiryDate": request.form.get("ExpiryDate", "").strip(),
                    "Supplier": request.form.get("Supplier", "").strip(),
                    "Notes": request.form.get("Notes", "").strip(),
                }
            )
            if config.BACKUP_ON_WRITE:
                backup_all([licenses])
            flash(f"Лиценцата {lid} е внесена.", "success")
        except ValidationError as exc:
            flash(f"ГРЕШКА: {exc}", "danger")
        return redirect(url_for("catalog.licenses_view"))
    import datetime as _dt

    rows = licenses.records()
    today = _dt.date.today()
    expiring_ids = set()
    for r in rows:
        try:
            exp = _dt.date.fromisoformat((r.get("ExpiryDate") or "").strip()[:10])
        except ValueError:
            continue
        if today <= exp <= today + _dt.timedelta(days=30):
            expiring_ids.add(r.get("LicenseID", ""))
    return render_template("licenses.html", rows=rows, expiring_ids=expiring_ids)


@bp.route("/licenses/assign", methods=["POST"])
def licenses_assign():
    try:
        new_used = _license_seat_change(
            request.form.get("license_id", "").strip(),
            1,
            request.form.get("emp_id", "").strip(),
            "LIC_ASSIGN",
        )
        flash(f"Седиште доделено. Зафатени: {new_used}.", "success")
    except ValidationError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")
    return redirect(url_for("catalog.licenses_view"))


@bp.route("/licenses/revoke", methods=["POST"])
def licenses_revoke():
    try:
        new_used = _license_seat_change(
            request.form.get("license_id", "").strip(),
            -1,
            request.form.get("emp_id", "").strip(),
            "LIC_REVOKE",
        )
        flash(f"Седиште ослободено. Зафатени: {new_used}.", "success")
    except ValidationError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")
    return redirect(url_for("catalog.licenses_view"))


@bp.route("/contracts", methods=["GET", "POST"])
def contracts_view():
    from app import backup_all, contracts

    import config

    if request.method == "POST":
        cid = request.form.get("ContractID", "").strip()
        try:
            if not cid:
                raise ValidationError("ID е задолжителен.")
            if contracts.find("ContractID", cid):
                raise ValidationError(f"{cid} веќе постои.")
            contracts.append_row(
                {
                    "ContractID": cid,
                    "Title": request.form.get("Title", "").strip(),
                    "Supplier": request.form.get("Supplier", "").strip(),
                    "ValidUntil": request.form.get("ValidUntil", "").strip(),
                    "Value": request.form.get("Value", "").strip(),
                    "Notes": request.form.get("Notes", "").strip(),
                }
            )
            if config.BACKUP_ON_WRITE:
                backup_all([contracts])
            flash(f"Договорот {cid} е внесен.", "success")
        except ValidationError as exc:
            flash(f"ГРЕШКА: {exc}", "danger")
        return redirect(url_for("catalog.contracts_view"))
    import datetime as _dt

    rows = contracts.records()
    today = _dt.date.today()
    expiring_ids = set()
    for r in rows:
        try:
            exp = _dt.date.fromisoformat((r.get("ValidUntil") or "").strip()[:10])
        except ValueError:
            continue
        if today <= exp <= today + _dt.timedelta(days=30):
            expiring_ids.add(r.get("ContractID", ""))
    return render_template("contracts.html", rows=rows, expiring_ids=expiring_ids)


@bp.route("/reservations", methods=["GET", "POST"])
def reservations_view():
    from app import backup_all, devices, reservations

    import config

    if request.method == "POST":
        try:
            asset_id = request.form.get("AssetID", "").strip()
            if devices.find("AssetID", asset_id) is None:
                raise ValidationError(f"Уредот {asset_id} не постои.")
            start = _parse_day(request.form.get("FromDate", ""), "од")
            end = _parse_day(request.form.get("ToDate", ""), "до")
            if end < start:
                raise ValidationError("Крајот е пред почетокот.")
            for r in reservations.records():
                if r.get("AssetID") != asset_id or r.get("Status") != "active":
                    continue
                try:
                    import datetime as _dt

                    rs = _dt.date.fromisoformat(r.get("FromDate", "")[:10])
                    re_ = _dt.date.fromisoformat(r.get("ToDate", "")[:10])
                except ValueError:
                    continue
                if start <= re_ and rs <= end:
                    raise ValidationError(
                        f"Преклопување со {r.get('ReservationID')} "
                        f"({r.get('FromDate')}–{r.get('ToDate')})."
                    )
            from utils.helpers import next_id as _next_id

            rid = _next_id(reservations, "ReservationID", "R")
            reservations.append_row(
                {
                    "ReservationID": rid,
                    "AssetID": asset_id,
                    "EmployeeID": request.form.get("EmployeeID", "").strip(),
                    "FromDate": start.isoformat(),
                    "ToDate": end.isoformat(),
                    "Status": "active",
                    "Notes": request.form.get("Notes", "").strip(),
                }
            )
            if config.BACKUP_ON_WRITE:
                backup_all([reservations])
            flash(f"Резервацијата {rid} е внесена.", "success")
        except ValidationError as exc:
            flash(f"ГРЕШКА: {exc}", "danger")
        return redirect(url_for("catalog.reservations_view"))
    rows = reservations.records()
    return render_template("reservations.html", rows=rows)


@bp.route("/reservations/cancel", methods=["POST"])
def reservations_cancel():
    from app import backup_all, reservations

    import config

    rid = request.form.get("reservation_id", "").strip()
    if reservations.find("ReservationID", rid) is None:
        flash(f"ГРЕШКА: резервацијата {rid} не постои.", "danger")
    else:
        reservations.update_where("ReservationID", rid, {"Status": "cancelled"})
        if config.BACKUP_ON_WRITE:
            backup_all([reservations])
        flash(f"Резервацијата {rid} е откажана.", "success")
    return redirect(url_for("catalog.reservations_view"))


@bp.route("/requests", methods=["GET", "POST"])
def requests_view():
    from app import backup_all, requests
    from utils.helpers import stamp

    import config

    if request.method == "POST":
        try:
            need = request.form.get("NeedText", "").strip()
            if not need:
                raise ValidationError("Опишете што ви треба.")
            from utils.helpers import next_id as _next_id

            qid = _next_id(requests, "RequestID", "Q")
            requests.append_row(
                {
                    "RequestID": qid,
                    "EmployeeID": request.form.get("EmployeeID", "").strip(),
                    "NeedText": need,
                    "Status": "open",
                    "Created": stamp().split(" ")[0],
                    "DecidedBy": "",
                }
            )
            if config.BACKUP_ON_WRITE:
                backup_all([requests])
            flash(f"Барањето {qid} е заведено.", "success")
        except ValidationError as exc:
            flash(f"ГРЕШКА: {exc}", "danger")
        return redirect(url_for("catalog.requests_view"))
    rows = requests.records()
    return render_template("requests.html", rows=rows)


@bp.route("/requests/decide", methods=["POST"])
@require("admin", "magacioner")
def requests_decide():
    from app import backup_all, requests

    import config

    qid = request.form.get("request_id", "").strip()
    decision = request.form.get("decision", "").strip()
    try:
        if requests.find("RequestID", qid) is None:
            raise ValidationError(f"Барањето {qid} не постои.")
        if decision not in ("approved", "rejected"):
            raise ValidationError("Невалидна одлука.")
        from flask_login import current_user as _cu

        who = getattr(_cu, "id", "admin") if _cu else "admin"
        requests.update_where(
            "RequestID", qid, {"Status": decision, "DecidedBy": str(who)}
        )
        if config.BACKUP_ON_WRITE:
            backup_all([requests])
        flash(f"Барањето {qid}: {decision}.", "success")
    except ValidationError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")
    return redirect(url_for("catalog.requests_view"))


@bp.route("/fields", methods=["GET", "POST"])
@require("admin", "magacioner")
def field_defs_view():
    from app import backup_all, field_defs, field_values

    import config

    if request.method == "POST":
        action = request.form.get("action", "add")
        try:
            if action == "add":
                name = request.form.get("FieldName", "").strip()
                if not name:
                    raise ValidationError("Името е задолжително.")
                if any(d.get("FieldName") == name for d in field_defs.records()):
                    raise ValidationError(f"Полето {name} веќе постои.")
                from utils.helpers import next_id as _next_id

                fid = _next_id(field_defs, "FieldID", "F")
                field_defs.append_row({"FieldID": fid, "FieldName": name})
                if config.BACKUP_ON_WRITE:
                    backup_all([field_defs])
                flash(f"Полето {name} е додадено.", "success")
            elif action == "delete":
                fid = request.form.get("field_id", "").strip()
                field_defs.replace_all(
                    [d for d in field_defs.records() if d.get("FieldID") != fid]
                )
                field_values.replace_all(
                    [v for v in field_values.records() if v.get("FieldID") != fid]
                )
                if config.BACKUP_ON_WRITE:
                    backup_all([field_defs, field_values])
                flash("Полето е избришано.", "success")
        except ValidationError as exc:
            flash(f"ГРЕШКА: {exc}", "danger")
        return redirect(url_for("catalog.field_defs_view"))
    return render_template("fields.html", defs=field_defs.records())


@bp.route("/device/<asset_id>/fields", methods=["POST"])
@require("admin", "magacioner")
def device_fields_save(asset_id):
    from app import backup_all, devices, field_defs, field_values

    import config

    dev = devices.find("AssetID", asset_id)
    if dev is None:
        abort(404)
    defs = {d.get("FieldID", ""): d for d in field_defs.records()}
    kept = [
        v
        for v in field_values.records()
        if not (v.get("AssetID") == asset_id and v.get("FieldID") in defs)
    ]
    for fid in defs:
        val = request.form.get(f"field_{fid}", "").strip()
        if val:
            kept.append({"AssetID": asset_id, "FieldID": fid, "Value": val})
    field_values.replace_all(kept)
    if config.BACKUP_ON_WRITE:
        backup_all([field_values])
    flash("Дополнителните полиња се зачувани.", "success")
    return redirect(url_for("device_detail", asset_id=asset_id))
