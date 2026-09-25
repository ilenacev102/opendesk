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

    from app import devices, history, incidents
    from services.notify_service import (
        breached_incidents,
        digest_email,
        send_email,
        warranty_expiring,
    )

    expiring = warranty_expiring(devices.records(), days=30)
    breached = breached_incidents(incidents.records())
    escalated_ids = {
        h.get("AssetID", "")
        for h in history.store.records()
        if h.get("Action") == "ESC_ESCALATE" and h.get("AssetID")
    }
    escalated = [
        inc for inc in incidents.records() if inc.get("IncidentID") in escalated_ids
    ]
    admin_email = _os.environ.get("SERVICEDESK_ADMIN_EMAIL", "").strip()
    if not expiring and not breached and not escalated:
        flash("Нема гаранции што истекуваат во следните 30 дена.", "success")
    elif not admin_email:
        flash(
            f"ГРЕШКА: поставете SERVICEDESK_ADMIN_EMAIL. "
            f"(гаранции {len(expiring)}, пробиени рокови {len(breached)}, "
            f"ескалирани {len(escalated)})",
            "danger",
        )
    else:
        to, subject, body = digest_email(admin_email, expiring, breached, escalated)
        if send_email(to, subject, body):
            flash(
                f"Digest испратен на {admin_email} ({len(expiring)} уреди, "
                f"пробиени рокови {len(breached)}, "
                f"ескалирани {len(escalated)}).",
                "success",
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


def _who():
    from flask_login import current_user as _cu

    return str(getattr(_cu, "id", "admin")) if _cu else "admin"


def _discovery_import():
    """Discovery CSV: preview (dry-run) or confirm step.

    Returns (preview, report). Preview writes nothing; confirm re-reconciles
    against live devices so verdicts are never stale, then writes.
    """
    import json as _json

    import config
    from app import backup_all, devices, history, staging
    from services.discovery_service import DISCOVERY_COLUMNS
    from services.discovery_service import confirm as _confirm
    from services.discovery_service import parse_discovery_csv as _parse
    from services.discovery_service import reconcile as _reconcile

    if request.form.get("confirm") == "1":
        try:
            raw = _json.loads(request.form.get("rows", "[]"))
            rows = [
                {c: str(r.get(c, "")) for c in DISCOVERY_COLUMNS}
                for r in raw
                if isinstance(r, dict)
            ]
        except ValueError:
            flash("ГРЕШКА: невалидни податоци за потврда.", "danger")
            return None, {"ok": 0, "errors": ["Невалидни податоци за потврда."]}
        if not rows:
            flash("ГРЕШКА: нема редови за потврда.", "danger")
            return None, {"ok": 0, "errors": ["Нема редови за потврда."]}
        preview = _reconcile(rows, devices)
        db_path = getattr(devices, "db_path", None)
        counts = _confirm(
            preview,
            devices,
            staging,
            history,
            performed_by=_who(),
            db_path=db_path,
        )
        if config.BACKUP_ON_WRITE:
            backup_all([devices, staging])
        flash(
            f"Внесени {counts['new']} нови, "
            f"ажурирани {counts['updated']}, "
            f"прескокнати {counts['skipped']}.",
            "success",
        )
        return None, {"ok": counts["new"] + counts["updated"], "errors": []}
    file = request.files.get("file")
    if not file or not file.filename:
        flash("ГРЕШКА: избери CSV фајл.", "danger")
        return None, None
    ext = (file.filename.rsplit(".", 1)[-1] if "." in file.filename else "").lower()
    if ext != "csv":
        msg = "Дозволени се само .csv фајлови."
        flash(f"ГРЕШКА: {msg}", "danger")
        return None, {"ok": 0, "errors": [msg]}
    try:
        rows = _parse(file.read())
    except ValueError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")
        return None, {"ok": 0, "errors": [str(exc)]}
    reconciled = _reconcile(rows, devices)
    counts = {"new": 0, "match": 0, "conflict": 0}
    for row in reconciled:
        counts[row["verdict"]] += 1
    preview = {
        "title": "Преглед на discovery увоз",
        "kind": "discovery",
        "rows": reconciled,
        "counts": counts,
        "rows_json": _json.dumps(rows),
    }
    return preview, None


def _intune_import():
    """Intune Graph: fetch (dry-run) preview or confirm step.

    Returns (preview, report). Preview writes nothing; confirm re-reconciles
    against live devices so verdicts are never stale, then writes.
    """
    import json as _json

    import config
    from app import backup_all, devices, history, staging
    from services.discovery_service import DISCOVERY_COLUMNS
    from services.discovery_service import confirm as _confirm
    from services.discovery_service import reconcile as _reconcile
    from services.intune_service import IntuneError
    from services.intune_service import fetch_devices as _fetch

    if request.form.get("confirm") == "1":
        try:
            raw = _json.loads(request.form.get("rows", "[]"))
            rows = [
                {c: str(r.get(c, "")) for c in DISCOVERY_COLUMNS}
                for r in raw
                if isinstance(r, dict)
            ]
        except ValueError:
            flash("ГРЕШКА: невалидни податоци за потврда.", "danger")
            return None, {"ok": 0, "errors": ["Невалидни податоци за потврда."]}
        if not rows:
            flash("ГРЕШКА: нема редови за потврда.", "danger")
            return None, {"ok": 0, "errors": ["Нема редови за потврда."]}
        preview = _reconcile(rows, devices)
        db_path = getattr(devices, "db_path", None)
        counts = _confirm(
            preview,
            devices,
            staging,
            history,
            performed_by=_who(),
            db_path=db_path,
        )
        if config.BACKUP_ON_WRITE:
            backup_all([devices, staging])
        flash(
            f"Внесени {counts['new']} нови, "
            f"ажурирани {counts['updated']}, "
            f"прескокнати {counts['skipped']}.",
            "success",
        )
        return None, {"ok": counts["new"] + counts["updated"], "errors": []}
    try:
        rows = _fetch()
    except IntuneError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")
        return None, {"ok": 0, "errors": [str(exc)]}
    reconciled = _reconcile(rows, devices)
    counts = {"new": 0, "match": 0, "conflict": 0}
    for row in reconciled:
        counts[row["verdict"]] += 1
    preview = {
        "title": "Преглед на Intune sync",
        "kind": "intune",
        "rows": reconciled,
        "counts": counts,
        "rows_json": _json.dumps(rows),
    }
    return preview, None


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
    preview = None
    if request.method == "POST":
        kind = request.form.get("kind", "devices")
        if kind == "discovery":
            preview, report = _discovery_import()
        elif kind == "intune":
            preview, report = _intune_import()
        elif (
            request.files.get("file") is None or not request.files.get("file").filename
        ):
            flash("ГРЕШКА: избери CSV фајл.", "danger")
        else:
            file = request.files.get("file")
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
    return render_template("import.html", report=report, preview=preview)


@bp.route("/reports/monthly-summary", methods=["POST"])
@require("admin", "magacioner")
def monthly_summary():
    import datetime
    import os as _os

    from app import devices, history, incidents
    from services import analytics_service as analytics
    from services.notify_service import send_email, summary_email

    today = datetime.date.today()
    devs = devices.records()
    inc_records = incidents.records()
    inc_status, _ = analytics.incidents_by(inc_records)
    open_count = sum(v for k, v in inc_status.items() if k in ("open", "in-progress"))
    escalated_ids = {
        h.get("AssetID", "")
        for h in history.store.records()
        if h.get("Action") == "ESC_ESCALATE" and h.get("AssetID")
    }
    stats = {
        "month": today.strftime("%Y-%m"),
        "total_devices": len(devs),
        "assigned": sum(1 for d in devs if d.get("Status") == "Assigned"),
        "warranty_fc": analytics.warranty_buckets(devs, today),
        "costs_total": round(sum(analytics.costs_by(devs, "Location").values()), 2),
        "inc_open": open_count,
        "breach_open": analytics.breach_counts(inc_records, today),
        "escalated": len(escalated_ids),
        "mttr": analytics.mttr_hours(inc_records),
    }
    admin_email = _os.environ.get("SERVICEDESK_ADMIN_EMAIL", "").strip()
    if not admin_email:
        flash("ГРЕШКА: поставете SERVICEDESK_ADMIN_EMAIL.", "danger")
        return redirect(url_for("reports.reports"))
    to, subject, body = summary_email(admin_email, stats)
    if send_email(to, subject, body):
        flash(f"Месечниот извештај е испратен на {admin_email}.", "success")
    else:
        flash("ГРЕШКА: mail не е испратен. Проверете SMTP-поставки.", "danger")
    return redirect(url_for("reports.reports"))
