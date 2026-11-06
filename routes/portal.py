"""Customer Self-Service Portal (Flask Blueprint): /portal.

Dedicated self-service interface for employees (citac role & staff) to:
- Browse the IT service catalog and request equipment or services.
- Report issues/incidents linked to their assigned hardware.
- View real-time status of their personal hardware and active requests.
- Experience real-time Knowledge Base deflection before submitting a ticket.
"""

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user

bp = Blueprint("portal", __name__)

log = __import__("logging").getLogger("servicedesk")


def _current_employee():
    from app import employees

    who = str(getattr(current_user, "id", "")).strip() if current_user else ""
    if not who:
        return None
    emp = employees.find("UserName", who)
    if emp is None:
        emp = employees.find("Email", who) or employees.find("EmployeeID", who)
    return emp


def _service():
    from app import PATHS, history, incidents
    from services.incident_service import IncidentService

    return IncidentService(incidents, history, db_path=PATHS.get("db"))


@bp.route("/portal")
def portal_home():
    from app import devices, incidents, requests

    emp = _current_employee()
    emp_id = emp.get("EmployeeID", "") if emp else ""
    who = str(getattr(current_user, "id", "")).strip() if current_user else ""

    if emp_id:
        my_devices = [
            d
            for d in devices.filter_eq("EmployeeID", emp_id)
            if d.get("Status") == "Assigned"
        ]
        my_requests = requests.filter_eq("EmployeeID", emp_id)
        my_incidents = incidents.filter_eq("EmployeeID", emp_id)
    else:
        # Fallback for admin or unlinked accounts
        my_devices = []
        my_requests = [r for r in requests.records() if r.get("EmployeeID") == who]
        my_incidents = [
            i
            for i in incidents.records()
            if i.get("EmployeeID") == who or i.get("Assignee") == who
        ]

    my_requests.sort(key=lambda r: r.get("Created", ""), reverse=True)
    my_incidents.sort(key=lambda r: r.get("Created", ""), reverse=True)

    return render_template(
        "portal.html",
        emp=emp,
        who=who,
        my_devices=my_devices,
        my_requests=my_requests,
        my_incidents=my_incidents,
    )


@bp.route("/portal/request", methods=["POST"])
def portal_request():
    import config
    from app import backup_all, requests
    from utils.helpers import next_id, stamp
    from utils.validators import ValidationError

    emp = _current_employee()
    emp_id = (
        emp.get("EmployeeID", "")
        if emp
        else str(getattr(current_user, "id", "")).strip()
    )
    need_text = request.form.get("need_text", "").strip()

    try:
        if not need_text:
            raise ValidationError("Опишете што ви е потребно.")
        qid = next_id(requests, "RequestID", "Q")
        requests.append_row(
            {
                "RequestID": qid,
                "EmployeeID": emp_id,
                "NeedText": need_text,
                "Status": "open",
                "Created": stamp().split(" ")[0],
                "DecidedBy": "",
            }
        )
        if config.BACKUP_ON_WRITE:
            backup_all([requests])
        flash(f"Вашето барање ({qid}) е успешно испратено до ИТ службата.", "success")
    except ValidationError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")

    return redirect(url_for("portal.portal_home"))


@bp.route("/portal/incident", methods=["POST"])
def portal_incident():
    import config
    from app import backup_all, incidents
    from utils.validators import ValidationError

    emp = _current_employee()
    emp_id = (
        emp.get("EmployeeID", "")
        if emp
        else str(getattr(current_user, "id", "")).strip()
    )
    who = str(getattr(current_user, "id", "")).strip() if current_user else "портал"

    title = request.form.get("title", "").strip()
    notes = request.form.get("notes", "").strip()
    asset_id = request.form.get("asset_id", "").strip()
    priority = request.form.get("priority", "medium").strip()

    try:
        if not title:
            raise ValidationError("Насловот на проблемот е задолжителен.")
        svc = _service()
        iid = svc.create(
            asset_id=asset_id,
            title=title,
            priority=priority,
            employee_id=emp_id,
            notes=notes,
            performed_by=who,
        )
        if config.BACKUP_ON_WRITE:
            backup_all([incidents])
        flash(
            f"Инцидентот ({iid}) е успешно пријавен. Нашите техничари ќе го прегледаат наскоро.",
            "success",
        )
    except (ValidationError, ValueError) as exc:
        flash(f"ГРЕШКА: {exc}", "danger")

    return redirect(url_for("portal.portal_home"))


@bp.route("/portal/kb-suggest")
def portal_kb_suggest():
    """Real-time KB deflection API endpoint."""
    from app import kb_articles

    q = (request.args.get("q", "") or "").strip().lower()
    words = q.split()
    if not words:
        return jsonify({"results": []})

    results = []
    for art in kb_articles.records():
        haystack = " ".join(
            [art.get("Title", ""), art.get("Body", ""), art.get("Tags", "")]
        ).lower()
        if any(w in haystack for w in words):
            body_clean = art.get("Body", "").replace("\n", " ")
            snippet = body_clean[:130] + ("..." if len(body_clean) > 130 else "")
            results.append(
                {
                    "id": art.get("ArticleID", ""),
                    "title": art.get("Title", ""),
                    "tags": art.get("Tags", ""),
                    "snippet": snippet,
                }
            )
            if len(results) >= 4:
                break

    return jsonify({"results": results})
