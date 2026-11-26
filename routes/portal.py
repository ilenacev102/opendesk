"""Customer Self-Service Portal (Flask Blueprint): /portal.

Dedicated self-service interface for employees (citac role & staff) to:
- Browse the IT service catalog and request equipment or services.
- Report issues/incidents linked to their assigned hardware.
- View real-time status of their personal hardware and active requests.
- Experience real-time Knowledge Base deflection before submitting a ticket.
"""

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
from flask_login import current_user

bp = Blueprint("portal", __name__)

log = __import__("logging").getLogger("servicedesk")


def _who():
    return str(getattr(current_user, "id", "")).strip() if current_user else ""


def _my_incidents():
    """Incidents the current account requested, newest first."""
    from app import incidents

    emp = _current_employee()
    emp_id = emp.get("EmployeeID", "") if emp else ""
    who = _who()
    if emp_id:
        rows = list(incidents.filter_eq("EmployeeID", emp_id))
    elif who:
        rows = list(incidents.filter_eq("EmployeeID", who))
    else:
        rows = []
    rows.sort(key=lambda r: r.get("Created", ""), reverse=True)
    return rows


def _owned_ticket(iid):
    """404 when missing, 403 when the ticket belongs to somebody else."""
    from app import incidents
    from services import portal_service

    try:
        return portal_service.ticket(incidents, iid, _current_employee(), _who())
    except LookupError:
        abort(404)
    except PermissionError:
        abort(403)


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

    from app import notifications
    from services.notify_center import unread

    role = str(getattr(current_user, "role", "")) if current_user else ""
    return render_template(
        "portal.html",
        emp=emp,
        who=who,
        my_devices=my_devices,
        my_requests=my_requests,
        my_incidents=my_incidents,
        notifications_rows=unread(notifications, who),
        needs_mapping=bool(who and role not in ("admin", "magacioner") and emp is None),
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
        inc_row = svc.create(
            asset_id=asset_id,
            title=title,
            priority=priority,
            employee_id=emp_id,
            notes=notes,
            performed_by=who,
        )
        iid = (
            inc_row.get("IncidentID", "")
            if isinstance(inc_row, dict)
            else str(inc_row or "")
        )
        if config.BACKUP_ON_WRITE:
            backup_all([incidents])

        file = request.files.get("file") or request.files.get("attachment")
        if file and file.filename and iid:
            from routes.incidents import save_attachment

            try:
                save_attachment(iid, file, performed_by=who)
            except ValidationError as exc:
                flash(f"ГРЕШКА: прилогот не е зачуван ({exc}).", "warning")

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


@bp.route("/portal/tickets")
def portal_tickets():
    """Requester ticket list: status filter + pagination + empty state."""
    from services import portal_service

    status = request.args.get("status", "").strip()
    if status not in ("open", "in-progress", "resolved"):
        status = ""
    rows = _my_incidents()
    counts = {
        "all": len(rows),
        "open": sum(1 for r in rows if r.get("Status") == "open"),
        "in-progress": sum(1 for r in rows if r.get("Status") == "in-progress"),
        "resolved": sum(1 for r in rows if r.get("Status") == "resolved"),
    }
    if status:
        rows = [r for r in rows if r.get("Status") == status]
    page_rows, page, total_pages, total = portal_service.paginate(
        rows, request.args.get("page", "1"), per_page=portal_service.PAGE_SIZE
    )
    return render_template(
        "portal_tickets.html",
        rows=page_rows,
        page=page,
        total_pages=total_pages,
        total=total,
        status=status,
        counts=counts,
        emp=_current_employee(),
    )


@bp.route("/portal/ticket/<iid>")
def portal_ticket(iid):
    """Ticket detail for its requester: status, thread, attachments, actions."""
    import config
    from app import comments
    from services import portal_service

    inc = _owned_ticket(iid)
    return render_template(
        "portal_ticket.html",
        inc=inc,
        thread=portal_service.thread(comments, iid),
        attachments=portal_service.attachments(config.DOCUMENTS_DIR, iid),
        emp=_current_employee(),
    )


@bp.route("/portal/ticket/<iid>/comment", methods=["POST"])
def portal_comment(iid):
    """Requester comment: comments row + PORTAL_COMMENT audit, per-user limit."""
    from app import comments, history, incidents
    from services import portal_service
    from services.comment_service import CommentService
    from services.ratelimit import is_allowed

    _owned_ticket(iid)
    who = _who()
    if not is_allowed(
        f"portal-comment|{who}",
        portal_service.COMMENT_LIMIT,
        portal_service.COMMENT_WINDOW_SEC,
    ):
        return "Too many requests", 429, {"Retry-After": "60"}
    try:
        CommentService(
            comments,
            incidents,
            history,
            db_path=getattr(comments, "db_path", None),
        ).add(
            iid,
            who,
            request.form.get("body", ""),
            performed_by=who,
            action="PORTAL_COMMENT",
        )
        flash("Коментарот е испратен до ИТ службата.", "success")
    except ValueError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")
    return redirect(url_for("portal.portal_ticket", iid=iid))


@bp.route("/portal/ticket/<iid>/rate", methods=["POST"])
def portal_rate(iid):
    """Requester CSAT (1-5) on a resolved ticket they own."""
    _owned_ticket(iid)
    try:
        _service().rate(iid, request.form.get("score", ""), performed_by=_who())
        flash("Ви благодариме за оценката.", "success")
    except ValueError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")
    return redirect(url_for("portal.portal_ticket", iid=iid))


@bp.route("/portal/ticket/<iid>/reopen", methods=["POST"])
def portal_reopen(iid):
    """Requester reopen: resolved -> open, once per seven days, notify assignee."""
    from app import history, incidents, notifications
    from services import notify_center, portal_service

    inc = _owned_ticket(iid)
    try:
        portal_service.reopen(incidents, history, iid, performed_by=_who())
        notify_center.push(
            notifications,
            inc.get("Assignee", ""),
            "incident",
            iid,
            f"Тикетот {iid} е повторно отворен од корисникот.",
        )
        flash("Тикетот е повторно отворен.", "success")
    except (ValueError, LookupError) as exc:
        flash(f"ГРЕШКА: {exc}", "danger")
    return redirect(url_for("portal.portal_ticket", iid=iid))


@bp.route("/portal/ticket/<iid>/attach/<path:name>")
def portal_attachment(iid, name):
    """Attachment download for the owner only, with traversal protection."""
    from flask import send_file

    import config
    from services import portal_service

    _owned_ticket(iid)
    full = portal_service.attachment_path(config.DOCUMENTS_DIR, iid, name)
    if full is None:
        abort(404)
    return send_file(full)


@bp.route("/portal/notifications/read", methods=["POST"])
def portal_notifications_read():
    """Mark one (or all) of the requester's notifications as read."""
    from app import notifications
    from services.notify_center import mark_read

    mark_read(notifications, _who(), request.form.get("notif_id", ""))
    return redirect(url_for("portal.portal_home"))
