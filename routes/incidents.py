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
    from app import comments, history, incidents
    from services.comment_service import CommentService

    inc = incidents.find("IncidentID", iid)
    if inc is None:
        abort(404)
    thread = CommentService(
        comments,
        incidents,
        history,
        db_path=getattr(comments, "db_path", None),
    ).for_incident(iid)
    linked_articles = _kb_link_service().for_incident(iid)
    return render_template(
        "incident.html",
        inc=inc,
        statuses=list(STATUSES),
        priorities=list(PRIORITIES),
        thread=thread,
        attachments=_attachments(iid),
        linked_articles=linked_articles,
    )


ALLOWED_ATTACH_EXTS = {".png", ".jpg", ".jpeg", ".pdf", ".log", ".txt"}


def _attach_dir(iid):
    import os

    import config

    return os.path.join(os.path.abspath(config.DOCUMENTS_DIR), "incidents", iid)


def _attachments(iid):
    import os

    target = _attach_dir(iid)
    if not os.path.isdir(target):
        return []
    return sorted(
        f for f in os.listdir(target) if os.path.isfile(os.path.join(target, f))
    )


@bp.route("/incidents/attach", methods=["POST"])
@require("admin", "magacioner")
def incident_attach():
    import os

    from app import backup_all, history, incidents

    import config

    iid = request.form.get("incident_id", "").strip()
    if incidents.find("IncidentID", iid) is None:
        abort(404)
    file = request.files.get("file")
    if not file or not file.filename:
        flash("ГРЕШКА: избери фајл.", "danger")
        return redirect(url_for("incidents.incident_detail", iid=iid))
    name = os.path.basename(file.filename.strip())
    ext = (name.rsplit(".", 1)[-1] if "." in name else "").lower()
    if not name or f".{ext}" not in ALLOWED_ATTACH_EXTS:
        flash("ГРЕШКА: дозволени се само png, jpg, pdf, log, txt фајлови.", "danger")
        return render_template(
            "incident.html",
            inc=incidents.find("IncidentID", iid),
            statuses=list(STATUSES),
            priorities=list(PRIORITIES),
            thread=[],
            attachments=_attachments(iid),
        )
    target_dir = _attach_dir(iid)
    os.makedirs(target_dir, exist_ok=True)
    full = os.path.abspath(os.path.join(target_dir, name))
    base = os.path.abspath(config.DOCUMENTS_DIR)
    if os.path.commonpath([base, full]) != base:
        abort(400)
    file.save(full)
    history.log("INC_ATTACH", iid, "", "", "", "", name, "", _who(), "")
    if config.BACKUP_ON_WRITE:
        backup_all([incidents])
    flash(f"Прилогот {name} е зачуван.", "success")
    return redirect(url_for("incidents.incident_detail", iid=iid))


@bp.route("/incidents/attach/<iid>/<name>")
def incident_attachment(iid, name):
    import os

    from flask import send_file

    import config

    from app import incidents

    if incidents.find("IncidentID", iid) is None:
        abort(404)
    clean = os.path.basename((name or "").strip())
    if not clean:
        abort(404)
    full = os.path.abspath(os.path.join(_attach_dir(iid), clean))
    base = os.path.abspath(config.DOCUMENTS_DIR)
    if os.path.commonpath([base, full]) != base or not os.path.isfile(full):
        abort(404)
    return send_file(full)


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


@bp.route("/incidents/escalate", methods=["POST"])
@require("admin", "magacioner")
def incident_escalate():
    from app import backup_all, history, incidents
    from services.escalation_service import EscalationService

    import config

    db_path = getattr(incidents, "db_path", None)
    svc = EscalationService(incidents, history, db_path=db_path)
    iid = request.form.get("incident_id", "").strip()
    try:
        if iid:
            result = svc.escalate(iid, performed_by=_who())
            if result["escalated"]:
                flash(f"Инцидентот {iid} е ескалиран.", "success")
            else:
                flash(f"Инцидентот {iid} не е за ескалација.", "warning")
        else:
            counts = svc.escalate_all(performed_by=_who())
            flash(
                f"Ескалирани {counts['escalated']}, прескокнати {counts['skipped']}.",
                "success",
            )
        if config.BACKUP_ON_WRITE:
            backup_all([incidents])
    except ValueError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")
    if iid:
        return redirect(url_for("incidents.incident_detail", iid=iid))
    return redirect(url_for("incidents.incident_list"))


@bp.route("/incidents/comment", methods=["POST"])
@require("admin", "magacioner")
def incident_comment():
    from app import backup_all, comments, history, incidents
    from services.comment_service import CommentService

    import config

    db_path = getattr(comments, "db_path", None)
    svc = CommentService(comments, incidents, history, db_path=db_path)
    iid = request.form.get("incident_id", "").strip()
    try:
        svc.add(
            iid,
            _who(),
            request.form.get("body", ""),
            performed_by=_who(),
        )
        if config.BACKUP_ON_WRITE:
            backup_all([comments])
        flash("Коментарот е додаден.", "success")
    except ValueError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")
    return redirect(url_for("incidents.incident_detail", iid=iid))


def _kb_link_service():
    from app import history, incidents, kb_articles, kb_links
    from services.kb_link_service import KbLinkService

    return KbLinkService(
        kb_links,
        incidents,
        kb_articles,
        history,
        db_path=getattr(kb_links, "db_path", None),
    )


@bp.route("/incidents/link-kb", methods=["POST"])
@require("admin", "magacioner")
def incident_link_kb():
    from app import backup_all, kb_links

    import config

    iid = request.form.get("incident_id", "").strip()
    aid = request.form.get("article_id", "").strip()
    try:
        _kb_link_service().link(iid, aid, performed_by=_who())
        if config.BACKUP_ON_WRITE:
            backup_all([kb_links])
        flash(f"Написот {aid} е поврзан со {iid}.", "success")
    except ValueError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")
    return redirect(url_for("incidents.incident_detail", iid=iid))


@bp.route("/incidents/resolve-kb", methods=["POST"])
@require("admin", "magacioner")
def incident_resolve_kb():
    from app import backup_all, incidents, kb_links

    import config

    iid = request.form.get("incident_id", "").strip()
    aid = request.form.get("article_id", "").strip()
    try:
        _kb_link_service().resolve_from_article(iid, aid, performed_by=_who())
        if config.BACKUP_ON_WRITE:
            backup_all([incidents, kb_links])
        flash(f"Инцидентот {iid} е решен од написот {aid}.", "success")
    except ValueError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")
    return redirect(url_for("incidents.incident_detail", iid=iid))


@bp.route("/incidents/inbox", methods=["GET", "POST"])
@require("admin", "magacioner")
def incident_inbox():
    import json as _json

    from app import backup_all, comments, history, incidents
    from services.mail_ingest import (
        MailError,
        configured,
        confirm as _confirm,
    )
    from services.mail_ingest import fetch_unseen as _fetch
    from services.mail_ingest import reconcile as _reconcile

    import config

    if not configured():
        return render_template("inbox.html", preview=None, hint=True)
    if request.method == "POST" and request.form.get("confirm") == "1":
        try:
            raw = _json.loads(request.form.get("rows", "[]"))
            rows = [r for r in raw if isinstance(r, dict)]
        except ValueError:
            flash("ГРЕШКА: невалидни податоци за потврда.", "danger")
            return redirect(url_for("incidents.incident_inbox"))
        if not rows:
            flash("ГРЕШКА: нема редови за потврда.", "danger")
            return redirect(url_for("incidents.incident_inbox"))
        preview = _reconcile(rows, incidents, comments, history)
        db_path = getattr(incidents, "db_path", None)
        counts = _confirm(
            preview,
            incidents,
            comments,
            history,
            performed_by=_who(),
            db_path=db_path,
        )
        if config.BACKUP_ON_WRITE:
            backup_all([incidents, comments])
        flash(
            f"Од mail: нови {counts['new']}, одговори {counts['replies']}, "
            f"прескокнати {counts['skipped']}.",
            "success",
        )
        return redirect(url_for("incidents.incident_list"))
    try:
        mails = _fetch()
    except MailError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")
        return render_template("inbox.html", preview=None, hint=False)
    preview = _reconcile(mails, incidents, comments, history)
    counts = {"new": 0, "reply": 0, "duplicate": 0}
    for row in preview:
        counts[row["verdict"]] += 1
    return render_template(
        "inbox.html",
        preview={"rows": preview, "counts": counts, "rows_json": _json.dumps(mails)},
        hint=False,
    )
