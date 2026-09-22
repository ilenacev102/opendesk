"""Operations routes (Flask Blueprint): assign, return, replace, repair,
quick-return, dispose, packages.

App-owned names (stores, services, shared helpers) are imported lazily INSIDE
each view so they always resolve against the live ``app`` module object.
That keeps test monkeypatching of ``app`` attributes working.
"""

import json
import os
import uuid

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from utils.validators import ValidationError

bp = Blueprint("operations", __name__)

log = __import__("logging").getLogger("servicedesk")


def _save_signature(data_url):
    """Decode canvas dataURL into documents/signatures. Never raises."""
    from services.signature import decode_signature

    import config

    try:
        raw = decode_signature(data_url or "")
        if raw is None:
            return ""
        folder = os.path.join(config.DOCUMENTS_DIR, "signatures")
        os.makedirs(folder, exist_ok=True)
        fname = f"sig_{uuid.uuid4().hex[:8]}.png"
        with open(os.path.join(folder, fname), "wb") as fh:
            fh.write(raw)
        return os.path.join("documents", "signatures", fname)
    except Exception:
        log.exception("Signature save failed")
        return ""


def _load_packages():
    import config

    path = os.path.join(config.DATA_DIR, "Packages.json")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


@bp.route("/assign", methods=["GET", "POST"])
def assign():
    from app import _notify_assignment, assign_svc, devices, employees

    if request.method == "POST":
        try:
            picked = [a.strip() for a in request.form.getlist("asset_ids") if a.strip()]
            if not picked and request.form.get("asset_id", "").strip():
                picked = [request.form.get("asset_id", "").strip()]
            emp_id = request.form.get("emp_id", "").strip()
            reason = request.form.get("reason", "").strip()
            notes = request.form.get("notes", "").strip()
            sig_rel = _save_signature(request.form.get("signature", ""))
            if len(picked) == 1:
                tid, doc = assign_svc.confirm(
                    picked[0],
                    emp_id,
                    reason,
                    notes,
                    signature_path=sig_rel,
                )
                flash(f"Задолжување {tid} успешно. Документ: {doc}", "success")
                _notify_assignment(emp_id, picked, tid)
                return redirect(url_for("inventory.device_detail", asset_id=picked[0]))
            tids, doc = assign_svc.confirm_many(
                picked, emp_id, reason, notes, signature_path=sig_rel
            )
            flash(
                f"Задолжени {len(tids)} уреди ({', '.join(tids)}). Документ: {doc}",
                "success",
            )
            _notify_assignment(emp_id, picked, ", ".join(tids))
            return redirect(url_for("inventory.employee_detail", emp_id=emp_id))
        except ValidationError as exc:
            flash(f"ГРЕШКА: {exc}", "danger")
    return render_template(
        "assignment.html",
        employees=employees.records(),
        devices=[d for d in devices.records() if d.get("Status") == "Available"],
        preset_asset=request.args.get("asset", ""),
        preset_emp=request.args.get("emp", ""),
    )


@bp.route("/return", methods=["GET", "POST"])
def return_device():
    from app import _notify_return, devices, employees, return_svc

    if request.method == "POST":
        mode = request.form.get("mode", "single")
        try:
            if mode == "bulk":
                emp_id = request.form.get("emp_id", "").strip()
                picked = [
                    a.strip()
                    for a in request.form.getlist("bulk_asset_ids")
                    if a.strip()
                ]
                if not picked:
                    raise ValidationError("Изберете барем еден уред за враќање.")
                tids, doc = return_svc.confirm_many(
                    picked,
                    emp_id,
                    request.form.get("reason", "").strip()
                    or "Раздолжување при заминување",
                    request.form.get("condition", "Good").strip(),
                    request.form.get("notes", "").strip(),
                )
                flash(
                    f"Успешно раздолжени {len(tids)} уреди за {emp_id} ({', '.join(tids)}). Документ: {doc}",
                    "success",
                )
                _notify_return(emp_id, picked, ", ".join(tids))
                return redirect(url_for("inventory.employee_detail", emp_id=emp_id))
            else:
                asset_id = request.form.get("asset_id", "").strip()
                emp_id = request.form.get("emp_id", "").strip()
                if not emp_id:
                    dev = devices.find("AssetID", asset_id)
                    if dev is not None:
                        emp_id = dev.get("EmployeeID", "")
                tid, doc = return_svc.confirm(
                    asset_id,
                    emp_id,
                    request.form.get("reason", "").strip(),
                    request.form.get("condition", "Good").strip(),
                    request.form.get("notes", "").strip(),
                )
                reason = request.form.get("reason", "")
                flash(f"Раздолжување {tid} успешно. Документ: {doc}", "success")
                _notify_return(emp_id, [asset_id], tid)
                if reason == "Расипан – не се поправа":
                    flash("Уредот е расипан: следен чекор е расход.", "warning")
                    return redirect(
                        url_for("operations.dispose") + f"?asset={asset_id}"
                    )
                if reason == "Расипан – на сервис":
                    return redirect(url_for("operations.repair") + f"?asset={asset_id}")
                return redirect(url_for("inventory.device_detail", asset_id=asset_id))
        except ValidationError as exc:
            flash(f"ГРЕШКА: {exc}", "danger")
    return render_template(
        "return.html",
        employees=employees.records(),
        devices=[
            d
            for d in devices.records()
            if d.get("Status")
            not in ("Available", "Disposed", "Lost", "Stolen", "Repair")
        ],
        preset_asset=request.args.get("asset", ""),
        preset_emp=request.args.get("emp", ""),
    )


@bp.route("/replace", methods=["GET", "POST"])
def replace():
    from app import devices, employees, replace_svc

    if request.method == "POST":
        try:
            tid, doc = replace_svc.confirm(
                request.form.get("old_id", "").strip(),
                request.form.get("new_id", "").strip(),
                request.form.get("emp_id", "").strip(),
                request.form.get("reason", "").strip(),
                request.form.get("notes", "").strip(),
                "admin",
                request.form.get("old_condition", "Available").strip(),
            )
            flash(f"Замена {tid} успешна. Документ: {doc}", "success")
            return redirect(
                url_for("inventory.device_detail", asset_id=request.form.get("new_id"))
            )
        except ValidationError as exc:
            flash(f"ГРЕШКА: {exc}", "danger")
    return render_template(
        "replacement.html",
        employees=employees.records(),
        assigned=[d for d in devices.records() if d.get("Status") == "Assigned"],
        available=[d for d in devices.records() if d.get("Status") == "Available"],
        preset_old=request.args.get("old", ""),
        preset_emp=request.args.get("emp", ""),
    )


@bp.route("/repair", methods=["GET", "POST"])
def repair():
    from app import devices, employees, repair_close_svc, repair_svc

    if request.method == "POST":
        action = request.form.get("action", "report")
        asset = request.form.get("asset_id", "").strip()
        try:
            if action == "report":
                tid = repair_svc.report_broken(
                    asset,
                    request.form.get("problem", "").strip(),
                    request.form.get("notes", "").strip(),
                    "admin",
                    request.form.get("emp_id", "").strip(),
                )
            elif action == "unrepairable":
                tid = repair_close_svc.mark_unrepairable(
                    asset,
                    request.form.get("reason", "Не се поправа").strip(),
                    request.form.get("notes", "").strip(),
                    "admin",
                )
                flash(f"Уредот {asset} е расходуван како непоправлив.", "warning")
                return redirect(url_for("inventory.device_detail", asset_id=asset))
            else:
                return_to_emp = "return_to_emp" in request.form
                tid, _ = repair_svc.advance(
                    asset,
                    request.form.get("provider", "").strip(),
                    request.form.get("notes", "").strip(),
                    "admin",
                    return_to_emp=return_to_emp,
                )
            flash(f"Сервис операција {tid} успешна.", "success")
            return redirect(url_for("inventory.device_detail", asset_id=asset))
        except ValidationError as exc:
            flash(f"ГРЕШКА: {exc}", "danger")
    return render_template(
        "repair.html",
        devices=devices.records(),
        employees=employees.records(),
        preset_asset=request.args.get("asset", ""),
    )


@bp.route("/quick-return")
def quick_return():
    from app import devices, employees

    q = (request.args.get("q") or "").strip()
    found, holder = None, None
    if q:
        dev = devices.find("AssetID", q)
        if dev is None:
            dev = devices.find("SerialNumber", q)
        if dev is None:
            ql = q.lower()
            for r in devices.records():
                hay = " ".join(
                    [
                        r.get("AssetID", ""),
                        r.get("SerialNumber", ""),
                        r.get("Manufacturer", ""),
                        r.get("Model", ""),
                    ]
                )
                if ql in hay.lower():
                    dev = r
                    break
        if dev is not None:
            found = dev
            if dev.get("EmployeeID"):
                holder = employees.find("EmployeeID", dev["EmployeeID"])
    return render_template(
        "quick_return.html",
        q=q,
        found=found,
        holder=holder,
        devices=devices.records(),
        scan=request.args.get("scan") == "1",
    )


@bp.route("/dispose", methods=["GET", "POST"])
def dispose():
    from app import devices, dispose_svc, employees

    if request.method == "POST":
        try:
            picked = [a.strip() for a in request.form.getlist("asset_ids") if a.strip()]
            if not picked and request.form.get("asset_id", "").strip():
                picked = [request.form.get("asset_id", "").strip()]
            reason = request.form.get("reason", "").strip()
            method = request.form.get("method", "").strip()
            notes = request.form.get("notes", "").strip()
            if len(picked) == 1:
                tid, doc = dispose_svc.confirm(picked[0], reason, method, notes)
                flash(f"Расход {tid} успешен. Документ: {doc}", "success")
                return redirect(url_for("inventory.device_detail", asset_id=picked[0]))
            tids, doc = dispose_svc.confirm_many(picked, reason, method, notes)
            flash(
                f"Расходувани {len(tids)} уреди ({', '.join(tids)}). Документ: {doc}",
                "success",
            )
            return redirect(url_for("reports.reports"))
        except ValidationError as exc:
            flash(f"ГРЕШКА: {exc}", "danger")
    return render_template(
        "dispose.html",
        devices=[d for d in devices.records() if d.get("Status") != "Disposed"],
        employees=employees.records(),
    )


@bp.route("/packages")
def packages():
    return render_template("packages.html", packages=_load_packages())


@bp.route("/package/<pkg_id>", methods=["GET", "POST"])
def package_assign(pkg_id):
    from app import assign_svc, devices, employees

    pkgs = {p["id"]: p for p in _load_packages()}
    pkg = pkgs.get(pkg_id)
    if pkg is None:
        abort(404)
    devs = devices.records()
    if request.method == "POST":
        emp_id = request.form.get("emp_id", "").strip()
        picked = [a.strip() for a in request.form.getlist("asset_ids") if a.strip()]
        try:
            if len(picked) <= 1 and picked:
                tid, doc = assign_svc.confirm(
                    picked[0], emp_id, f"Пакет: {pkg['name']}", ""
                )
            else:
                tids, doc = assign_svc.confirm_many(
                    picked, emp_id, f"Пакет: {pkg['name']}", ""
                )
                tid = ",".join(tids)
            flash(f"Пакет доделен ({tid}). Документ: {doc}", "success")
            return redirect(url_for("inventory.employee_detail", emp_id=emp_id))
        except ValidationError as exc:
            flash(f"ГРЕШКА: {exc}", "danger")
    pool = [d for d in devs if d.get("Status") == "Available"]
    suggested = []
    for want in pkg.get("types", []):
        for d in pool:
            if d["AssetID"] not in suggested and d.get("Type") == want:
                suggested.append(d["AssetID"])
                break
    return render_template(
        "package.html",
        pkg=pkg,
        employees=employees.records(),
        available=pool,
        suggested=suggested,
    )
