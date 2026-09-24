"""Popis routes (Flask Blueprint): start, detail with scanning and zapisnik.

App-owned names (stores, services) are imported lazily INSIDE each view so
they always resolve against the live ``app`` module object. That keeps test
monkeypatching of ``app`` attributes working.
"""

import json

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

bp = Blueprint("popis", __name__)

log = __import__("logging").getLogger("servicedesk")


@bp.route("/popis", methods=["GET", "POST"])
def popis_start():
    from app import devices, employees, popis_svc

    emps = employees.records()
    devs = devices.records()
    locs = sorted({d.get("Location", "") for d in devs if d.get("Location")})
    deps = sorted({e.get("Department", "") for e in emps if e.get("Department")})
    if request.method == "POST":
        scope = request.form.get("scope", "location")
        name = request.form.get("name", "").strip()
        if scope == "location":
            expected = [d["AssetID"] for d in devs if d.get("Location") == name]
        else:
            ids = {e["EmployeeID"] for e in emps if e.get("Department") == name}
            expected = [d["AssetID"] for d in devs if d.get("EmployeeID") in ids]
        if not expected:
            flash("ГРЕШКА: нема уреди за тој опсег.", "danger")
        else:
            pid = popis_svc.start(scope, name, expected)
            return redirect(url_for("popis.popis_detail", pid=pid))
    popisi = []
    for rec in popis_svc.store.records():
        try:
            expected_ids = json.loads(rec.get("Expected") or "[]")
            found_ids = json.loads(rec.get("Found") or "[]")
        except (ValueError, TypeError):
            expected_ids, found_ids = [], []
        popisi.append(
            {
                "id": rec.get("PopisID", ""),
                "scope": rec.get("Scope", ""),
                "name": rec.get("Name", ""),
                "status": rec.get("Status", ""),
                "found": len(found_ids),
                "total": len(expected_ids),
                "doc": rec.get("DocumentPath", ""),
            }
        )
    popisi.sort(key=lambda r: r["status"] != "OPEN")
    return render_template("popis.html", locs=locs, deps=deps, popisi=popisi)


@bp.route("/popis/<pid>", methods=["GET", "POST"])
def popis_detail(pid):
    from services.document_service import fill_template, mk_date

    from app import devices, history, popis_svc

    rec = popis_svc.get(pid)
    if rec is None:
        abort(404)
    if request.method == "POST":
        if "scan" in request.form:
            code = request.form.get("code", "").strip()
            dev = devices.find("AssetID", code)
            if dev is None:
                for r in devices.records():
                    if r.get("SerialNumber") == code:
                        dev = r
                        break
            if dev is None:
                flash(f"ГРЕШКА: {code} не постои.", "danger")
            else:
                res = popis_svc.scan(pid, dev["AssetID"])
                if res is True:
                    flash(f"✔ {dev['AssetID']} евидентиран.", "success")
                elif res is False:
                    flash(f"⚠ {dev['AssetID']} не припаѓа на овој попис.", "warning")
            return redirect(url_for("popis.popis_detail", pid=pid))
        result = popis_svc.finish(pid)
        if result is None:
            abort(404)
        missing = result["missing"]
        scope_name = rec["Scope"] or ""
        rec_name = rec["Name"] or ""
        doc_rel = fill_template(
            "Popis_Template.docx",
            {
                "«ОПФАТ»": f"{scope_name}: {rec_name}",
                "«ДАТУМ»": mk_date(),
                "«ОЧЕКУВАНИ»": str(len(result["expected"])),
                "«НАЈДЕНИ»": str(len(result["found"])),
                "«НЕДОСТАСУВААТ»": ", ".join(missing) if missing else "—",
            },
            f"Popis_{pid}.docx",
            "popis",
        )
        popis_svc.finish(pid, doc_rel)
        for aid in missing:
            dev = devices.find("AssetID", aid)
            history.log(
                "POPIS_MISSING",
                aid,
                dev.get("Status", "") if dev else "",
                dev.get("Status", "") if dev else "",
                dev.get("EmployeeID", "") if dev else "",
                "",
                f"Попис {pid}",
                "",
                "admin",
                doc_rel,
            )
        flash(
            f"Попис {pid} завршен. Недостасуваат: {len(missing)}.",
            "success" if not missing else "warning",
        )
        return redirect(url_for("popis.popis_detail", pid=pid))
    rec2 = popis_svc.get(pid)
    if rec2 is None:
        abort(404)
    items = []
    for aid in rec2["ExpectedIDs"]:
        dev = devices.find("AssetID", aid)
        items.append(
            {
                "AssetID": aid,
                "Model": f"{dev.get('Manufacturer', '')} {dev.get('Model', '')}"
                if dev
                else "",
                "Found": aid in rec2["FoundIDs"],
            }
        )
    return render_template("popis_detail.html", rec=rec2, items=items)


@bp.route("/popis/<pid>/scan")
def popis_scan(pid):
    from app import popis_svc

    rec = popis_svc.get(pid)
    if rec is None:
        abort(404)
    return render_template(
        "popis_scan.html",
        pid=pid,
        total=len(rec["ExpectedIDs"]),
        found=len(rec["FoundIDs"]),
        status=rec.get("Status", ""),
    )


@bp.route("/popis/<pid>/found", methods=["POST"])
def popis_found(pid):
    from app import popis_svc

    rec = popis_svc.get(pid)
    if rec is None or rec.get("Status") != "OPEN":
        return jsonify(ok=False, error="Пописот не постои или е затворен."), 404
    data = request.get_json(silent=True) or {}
    code = str(data.get("asset_id", "")).strip()
    if not code:
        return jsonify(ok=False, error="Недостасува asset_id."), 400
    res = popis_svc.scan(pid, code)
    if res is None:
        return jsonify(ok=False, error="Пописот е затворен."), 404
    if res is False:
        return jsonify(ok=False, error=f"{code} не припаѓа на овој попис."), 404
    rec2 = popis_svc.get(pid)
    if rec2 is None:
        return jsonify(ok=False, error="Пописот е затворен."), 404
    return jsonify(
        ok=True,
        asset_id=code,
        found=len(rec2["FoundIDs"]),
        total=len(rec2["ExpectedIDs"]),
    )
