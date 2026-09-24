"""Incidents routes (Flask Blueprint): list/detail/create/transition.

App-owned names are imported lazily INSIDE each view so they always resolve
against the live ``app`` module (test monkeypatching keeps working).
"""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from routes._roles import require
from services.incident_service import PRIORITIES, STATUSES

bp = Blueprint("incidents", __name__)

log = __import__("logging").getLogger("servicedesk")


def _service():
    from app import history, incidents
    from services.incident_service import IncidentService

    db_path = getattr(incidents, "db_path", None)
    return IncidentService(incidents, history, db_path=db_path)


def _who():
    from flask_login import current_user as _cu

    return str(getattr(_cu, "id", "admin")) if _cu else "admin"


@bp.route("/incidents")
def incident_list():
    from app import incidents
    from services.incident_service import breach as _breach

    st = request.args.get("status", "").strip()
    pr = request.args.get("priority", "").strip()
    ag = request.args.get("assignee", "").strip()
    q = request.args.get("q", "").strip().lower()

    rows = incidents.records()
    assignees = sorted({r.get("Assignee", "") for r in rows if r.get("Assignee")})
    filtered = []
    for r in rows:
        if st and r.get("Status") != st:
            continue
        if pr and r.get("Priority") != pr:
            continue
        if ag and r.get("Assignee") != ag:
            continue
        if q:
            haystack = " ".join(
                [
                    r.get("IncidentID", ""),
                    r.get("AssetID", ""),
                    r.get("Title", ""),
                    r.get("Notes", ""),
                ]
            ).lower()
            if not all(w in haystack for w in q.split()):
                continue
        filtered.append(r)
    filtered.sort(key=lambda r: r.get("Created", ""), reverse=True)
    for r in filtered:
        r["Breached"] = r.get("Status") != "resolved" and _breach(r.get("DueDate", ""))
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
        "incidents.html",
        rows=filtered[start : start + per],
        total=total,
        page=page,
        per=per,
        total_pages=total_pages,
        f_status=st,
        f_priority=pr,
        f_assignee=ag,
        f_q=request.args.get("q", ""),
        statuses=list(STATUSES),
        priorities=list(PRIORITIES),
        assignees=assignees,
    )


@bp.route("/incident/<iid>")
def incident_detail(iid):
    from app import incidents

    inc = incidents.find("IncidentID", iid)
    if inc is None:
        abort(404)
    return render_template(
        "incident.html",
        inc=inc,
        statuses=list(STATUSES),
        priorities=list(PRIORITIES),
    )


@bp.route("/incidents/new", methods=["POST"])
@require("admin", "magacioner")
def incident_new():
    from app import backup_all, incidents

    import config

    svc = _service()
    try:
        inc = svc.create(
            asset_id=request.form.get("AssetID", ""),
            title=request.form.get("Title", ""),
            priority=request.form.get("Priority", "medium") or "medium",
            employee_id=request.form.get("EmployeeID", ""),
            assignee=request.form.get("Assignee", ""),
            due_date=request.form.get("DueDate", ""),
            notes=request.form.get("Notes", ""),
            performed_by=_who(),
        )
        if config.BACKUP_ON_WRITE:
            backup_all([incidents])
        flash(f"Инцидентот {inc['IncidentID']} е заведен.", "success")
        return redirect(url_for("incidents.incident_detail", iid=inc["IncidentID"]))
    except ValueError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")
        return redirect(url_for("incidents.incident_list"))


@bp.route("/incidents/transition", methods=["POST"])
@require("admin", "magacioner")
def incident_transition():
    from app import backup_all, incidents

    import config

    svc = _service()
    iid = request.form.get("incident_id", "").strip()
    to_status = request.form.get("to_status", "").strip()
    try:
        svc.transition(iid, to_status, performed_by=_who())
        if config.BACKUP_ON_WRITE:
            backup_all([incidents])
        flash(f"Инцидентот {iid}: {to_status}.", "success")
    except ValueError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")
    return redirect(url_for("incidents.incident_detail", iid=iid))
