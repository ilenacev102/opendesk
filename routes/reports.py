"""Reports routes (Flask Blueprint): notify-digest, reports, import.

App-owned names are imported lazily INSIDE each view so they always resolve
against the live ``app`` module (test monkeypatching keeps working).
"""

from collections import Counter

from flask import (
    Blueprint,
    Response,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from routes._roles import require

bp = Blueprint("reports", __name__)

log = __import__("logging").getLogger("servicedesk")


@bp.route("/notify-digest", methods=["POST"])
@require("admin", "magacioner")
def notify_digest():
    import os as _os

    from app import devices
    from services.notify_service import digest_email, send_email, warranty_expiring

    expiring = warranty_expiring(devices.records(), days=30)
    admin_email = _os.environ.get("SERVICEDESK_ADMIN_EMAIL", "").strip()
    if not expiring:
        flash("Нема гаранции што истекуваат во следните 30 дена.", "success")
    elif not admin_email:
        flash("ГРЕШКА: поставете SERVICEDESK_ADMIN_EMAIL.", "danger")
    else:
        to, subject, body = digest_email(admin_email, expiring)
        if send_email(to, subject, body):
            flash(
                f"Digest испратен на {admin_email} ({len(expiring)} уреди).", "success"
            )
        else:
            flash("ГРЕШКА: mail не е испратен. Проверете SMTP-поставки.", "danger")
    return redirect(url_for("reports.reports"))


@bp.route("/reports")
def reports():
    import config
    from app import backup_all, devices, employees, history
    from services.schemas import EMP_COLS

    devs = devices.records()
    by = lambda key: dict(Counter(r.get(key, "") or "—" for r in devs))
    hist = history.recent(1000)
    monthly = Counter()
    for h in hist:
        if h.get("Action") in ("REPAIR_REPAIR", "REPLACE_IN", "DISPOSE"):
            monthly[h.get("DateTime", "")[:7]] += 1
    if request.args.get("export") == "devices":
        import csv
        import io

        def _safe(v):
            s = str(v or "")
            if s[:1] in ("=", "+", "-", "@", "\t", "\r"):
                s = "'" + s
            return s

        buf = io.StringIO()
        w = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
        w.writerow(
            [
                "AssetID",
                "Type",
                "Manufacturer",
                "Model",
                "SerialNumber",
                "Status",
                "EmployeeID",
                "Location",
                "PurchasePrice",
                "Supplier",
            ]
        )
        for r in devs:
            w.writerow(
                _safe(r.get(c, ""))
                for c in [
                    "AssetID",
                    "Type",
                    "Manufacturer",
                    "Model",
                    "SerialNumber",
                    "Status",
                    "EmployeeID",
                    "Location",
                    "PurchasePrice",
                    "Supplier",
                ]
            )
        return Response(
            buf.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment;filename=devices.csv"},
        )
    if request.args.get("export") == "employees":
        import csv
        import io

        def _safe2(v):
            s = str(v or "")
            if s[:1] in ("=", "+", "-", "@", "\t", "\r"):
                s = "'" + s
            return s

        emps = employees.records()
        buf = io.StringIO()
        w = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
        w.writerow(EMP_COLS)
        for r in emps:
            w.writerow(_safe2(r.get(c, "")) for c in EMP_COLS)
        return Response(
            buf.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment;filename=employees.csv"},
        )
    return render_template(
        "reports.html",
        by_status=by("Status"),
        by_type=by("Type"),
        by_mfr=by("Manufacturer"),
        by_loc=by("Location"),
        by_emp=by("EmployeeID"),
        monthly=dict(sorted(monthly.items())),
    )


@bp.route("/import", methods=["GET", "POST"])
def import_bulk():
    import io

    import pandas as pd

    import config
    from app import backup_all, devices, employees, history
    from services.db_service import db_transaction
    from services.schemas import DEV_COLS as _DC, EMP_COLS as _EC
    from services.schemas import OPTIONAL_DEV_COLS as _OPT

    report = None
    if request.method == "POST":
        kind = request.form.get("kind", "devices")
        file = request.files.get("file")
        if not file or not file.filename:
            flash("ГРЕШКА: избери CSV фајл.", "danger")
        else:
            try:
                ext = (
                    file.filename.rsplit(".", 1)[-1] if "." in file.filename else ""
                ).lower()
                if ext != "csv":
                    raise ValueError("Дозволени се само .csv фајлови.")
                df = pd.read_csv(io.BytesIO(file.read()), dtype=str).fillna("")
                cols = list(_DC) if kind == "devices" else list(_EC)
                optional = set(_OPT) if kind == "devices" else set()
                missing = [c for c in cols if c not in df.columns and c not in optional]
                if missing:
                    raise ValueError(f"Недостасуваат колони: {missing}")
                store = devices if kind == "devices" else employees
                key = "AssetID" if kind == "devices" else "EmployeeID"
                seen = {r.get(key) for r in store.records()}
                dup_file = df[df.duplicated(subset=[key], keep=False)][key].tolist()
                dup_base = [v for v in df[key].tolist() if v in seen]
                serials = set()
                dup_sn = []
                if kind == "devices":
                    for v in df["SerialNumber"].tolist():
                        if v and v in serials:
                            dup_sn.append(v)
                        serials.add(v)
                    base_sn = {r.get("SerialNumber") for r in store.records()}
                    dup_sn += [
                        v for v in df["SerialNumber"].tolist() if v and v in base_sn
                    ]
                errors = []
                if dup_file:
                    errors.append(
                        f"Дупликати во фајлот: {sorted(str(v) for v in set(dup_file) if v)}"
                    )
                if dup_base:
                    errors.append(
                        f"Веќе постојат: {sorted(str(v) for v in set(dup_base) if v)}"
                    )
                if dup_sn:
                    errors.append(
                        f"Дупли сериски: {sorted(str(v) for v in set(dup_sn) if v)}"
                    )
                valid_status = {
                    "Available",
                    "Assigned",
                    "Broken",
                    "Repair",
                    "Repaired",
                    "Disposed",
                    "Lost",
                    "Stolen",
                }
                if kind == "devices" and "Status" in df.columns:
                    bad_status = sorted(
                        {
                            str(v)
                            for v in df["Status"].tolist()
                            if str(v) not in valid_status
                        }
                    )
                    if bad_status:
                        errors.append(f"Непознат статус: {bad_status}")
                if errors:
                    report = {"ok": 0, "errors": errors}
                else:
                    rows = [
                        {c: str(df.at[i, c]) if c in df.columns else "" for c in cols}
                        for i in df.index
                    ]
                    db_path = getattr(store, "db_path", None)
                    if db_path:
                        with db_transaction(db_path) as con:
                            for row in rows:
                                store.append_row(row, con=con)
                                if kind == "devices":
                                    history.log(
                                        "IMPORT",
                                        row.get("AssetID", ""),
                                        "",
                                        row.get("Status", ""),
                                        row.get("EmployeeID", ""),
                                        "",
                                        "Bulk import",
                                        "",
                                        "admin",
                                        "",
                                        con=con,
                                    )
                    else:
                        for row in rows:
                            store.append_row(row)
                    if config.BACKUP_ON_WRITE:
                        backup_all([store])
                    report = {"ok": len(rows), "errors": []}
            except (ValueError, KeyError) as exc:
                flash(f"ГРЕШКА: {exc}", "danger")
            except Exception as exc:
                # Import boundary: user file + bulk write can fail mid-way
                # (transaction rolls back); present clean failure, keep traceback in log.
                log.exception("Import failed")
                flash(f"ГРЕШКА при увоз: {exc}", "danger")
                report = {"ok": 0, "errors": [str(exc)]}
    return render_template("import.html", report=report)
