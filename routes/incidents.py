"""Incidents routes (Flask Blueprint): list/detail/create/transition.

App-owned names are imported lazily INSIDE each view so they always resolve
against the live ``app`` module (test monkeypatching keeps working).
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

from routes._roles import require
from services import duplicate_service, macro_service
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


def _can_act():
    from flask_login import current_user as _cu

    return bool(_cu and getattr(_cu, "role", "") in ("admin", "magacioner"))


def _collab_ctx(inc):
    """Collab context for incident.html: watchers, worklog, versions, mentions."""
    import datetime as _dt

    from app import auth_svc, versions, watchers, worklogs
    from services import watcher_service, worklog_service

    iid = inc.get("IncidentID", "")
    watch_list = watcher_service.list_watchers(watchers, iid)
    wl_rows = [r for r in worklogs.records() if r.get("IncidentID") == iid]
    wl_rows.sort(key=lambda r: r.get("WorkedDate", ""))
    pid = (inc.get("ProjectID", "") or "").strip()
    ver_rows = [
        v for v in versions.records() if not pid or v.get("ProjectID", "") == pid
    ]
    fix_ver = (inc.get("FixVersion", "") or "").strip()
    fix_name = ""
    if fix_ver:
        for v in ver_rows:
            if v.get("VersionID") == fix_ver:
                fix_name = v.get("Name", "")
                break
    return {
        "watchers": watch_list,
        "is_watching": _who() in watch_list,
        "worklog_rows": wl_rows,
        "worklog_total": worklog_service.total_minutes(worklogs, iid),
        "versions": ver_rows,
        "fixversion_name": fix_name or fix_ver,
        "usernames": sorted(
            {u.get("UserName", "") for u in auth_svc.list_users() if u.get("UserName")}
        ),
        "today": _dt.date.today().isoformat(),
        "can_act": _can_act(),
    }


def _notify_collab(iid, text, body=""):
    """Notify mentions (Kind=mention), then assignee+watchers (Kind=incident)."""
    from app import auth_svc, incidents, notifications, watchers
    from services import mention_service, notify_center, watcher_service

    inc = incidents.find("IncidentID", iid) or {}
    notified = set()
    if body:
        for name in mention_service.extract(body):
            mention_service.notify(notifications, auth_svc.store, [name], iid, body)
            notified.add(name)

    def _push(username, msg):
        username = (username or "").strip()
        if not username or username in notified:
            return
        if notify_center.push(notifications, username, "incident", iid, msg):
            notified.add(username)

    _push(inc.get("Assignee", ""), text)
    for username in watcher_service.list_watchers(watchers, iid):
        _push(username, text)


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
    page = min(page, total_pages)
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
    from app import comments, history, incidents, macros
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
    svc = _service()
    similar = (
        duplicate_service.detect(incidents, inc.get("Title", ""), exclude_id=iid)
        if (
            inc.get("Status") in ("open", "in-progress")
            and not (inc.get("LinkedTo") or "").strip()
        )
        else []
    )
    return render_template(
        "incident.html",
        inc=inc,
        statuses=list(STATUSES),
        priorities=list(PRIORITIES),
        thread=thread,
        attachments=_attachments(iid),
        linked_articles=linked_articles,
        respond_at=svc.first_response_at(iid),
        reopened=svc.reopen_count(iid),
        macros=macro_service.for_picker(macros),
        similar=similar,
        **_collab_ctx(inc),
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

    import config
    from app import backup_all, history, incidents

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
        inc = incidents.find("IncidentID", iid)
        return render_template(
            "incident.html",
            inc=inc,
            statuses=list(STATUSES),
            priorities=list(PRIORITIES),
            thread=[],
            attachments=_attachments(iid),
            respond_at=_service().first_response_at(iid),
            reopened=_service().reopen_count(iid),
            **_collab_ctx(inc),
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


@bp.route("/api/v1/incidents/detect-duplicates")
def api_detect_duplicates():
    """JSON duplicate suggestions for a title (Jaccard over active incidents)."""
    from app import incidents
    from services import duplicate_service

    title = request.args.get("title", "")
    exclude_id = request.args.get("exclude", "")
    matches = duplicate_service.detect(incidents, title, exclude_id=exclude_id)
    return jsonify({"matches": matches})


@bp.route("/incidents/new", methods=["POST"])
@require("admin", "magacioner")
def incident_new():
    import config
    from app import backup_all, incidents

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
        if inc.get("Priority") == "critical":
            from services import webhook_service

            webhook_service.dispatch(
                incidents,
                "incident.critical_created",
                {
                    "IncidentID": inc["IncidentID"],
                    "Title": inc.get("Title", ""),
                    "Priority": inc.get("Priority", ""),
                    "Assignee": inc.get("Assignee", ""),
                },
            )
        flash(f"Инцидентот {inc['IncidentID']} е заведен.", "success")
        return redirect(url_for("incidents.incident_detail", iid=inc["IncidentID"]))
    except ValueError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")
        return redirect(url_for("incidents.incident_list"))


@bp.route("/incidents/transition", methods=["POST"])
@require("admin", "magacioner")
def incident_transition():
    from flask import jsonify

    import config
    from app import backup_all, incidents

    is_ajax = (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.is_json
        or request.form.get("ajax") == "1"
    )
    svc = _service()
    if request.is_json:
        data = request.get_json(silent=True) or {}
        iid = str(data.get("incident_id", "")).strip()
        to_status = str(data.get("to_status", "")).strip()
    else:
        iid = request.form.get("incident_id", "").strip()
        to_status = request.form.get("to_status", "").strip()
    try:
        svc.transition(iid, to_status, performed_by=_who())
        if config.BACKUP_ON_WRITE:
            backup_all([incidents])
        _notify_collab(iid, f"Статус на {iid}: {to_status}.")
        if is_ajax:
            return jsonify({"ok": True, "incident_id": iid, "status": to_status})
        flash(f"Инцидентот {iid}: {to_status}.", "success")
    except ValueError as exc:
        if is_ajax:
            return jsonify({"ok": False, "error": str(exc)}), 400
        flash(f"ГРЕШКА: {exc}", "danger")
    return redirect(url_for("incidents.incident_detail", iid=iid))


@bp.route("/incidents/<iid>/rate", methods=["POST"])
@require("admin", "magacioner")
def incident_rate(iid):
    """MS-8: CSAT rating 1-5 for resolved incidents."""
    svc = _service()
    try:
        svc.rate(iid, request.form.get("score", ""), performed_by=_who())
        flash("Оцената е запишана.", "success")
    except ValueError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")
    return redirect(url_for("incidents.incident_detail", iid=iid))


@bp.route("/incidents/<iid>/watch", methods=["POST"])
@require("admin", "magacioner")
def incident_watch(iid):
    import config
    from app import backup_all, incidents, watchers
    from services import watcher_service

    if incidents.find("IncidentID", iid) is None:
        abort(404)
    if watcher_service.watch(watchers, iid, _who()):
        if config.BACKUP_ON_WRITE:
            backup_all([watchers])
        flash(f"Го следите {iid}.", "success")
    else:
        flash(f"Веќе го следите {iid}.", "info")
    return redirect(url_for("incidents.incident_detail", iid=iid))


@bp.route("/incidents/<iid>/unwatch", methods=["POST"])
@require("admin", "magacioner")
def incident_unwatch(iid):
    import config
    from app import backup_all, incidents, watchers
    from services import watcher_service

    if incidents.find("IncidentID", iid) is None:
        abort(404)
    if watcher_service.unwatch(watchers, iid, _who()):
        if config.BACKUP_ON_WRITE:
            backup_all([watchers])
        flash(f"Веќе не го следите {iid}.", "success")
    else:
        flash(f"Не го следите {iid}.", "info")
    return redirect(url_for("incidents.incident_detail", iid=iid))


@bp.route("/incidents/<iid>/log", methods=["POST"])
@require("admin", "magacioner")
def incident_log(iid):
    import config
    from app import backup_all, incidents, worklogs
    from services import worklog_service
    from utils.validators import ValidationError

    if incidents.find("IncidentID", iid) is None:
        abort(404)
    try:
        row = worklog_service.log(
            worklogs,
            iid,
            _who(),
            request.form.get("minutes", ""),
            request.form.get("worked_date", ""),
            request.form.get("note", ""),
        )
        if config.BACKUP_ON_WRITE:
            backup_all([worklogs])
        flash(f"Запишани {row['Minutes']} минути на {iid}.", "success")
    except ValidationError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")
    return redirect(url_for("incidents.incident_detail", iid=iid))


@bp.route("/incidents/<iid>/fixversion", methods=["POST"])
@require("admin", "magacioner")
def incident_fixversion(iid):
    import config
    from app import backup_all, incidents, versions

    inc = incidents.find("IncidentID", iid)
    if inc is None:
        abort(404)
    value = request.form.get("fix_version", "").strip()
    if value:
        ver = versions.find("VersionID", value)
        pid = (inc.get("ProjectID", "") or "").strip()
        if ver is None or (pid and ver.get("ProjectID", "") != pid):
            flash("ГРЕШКА: невалидна верзија за овој проект.", "danger")
            return redirect(url_for("incidents.incident_detail", iid=iid))
    incidents.update_where("IncidentID", iid, {"FixVersion": value})
    if config.BACKUP_ON_WRITE:
        backup_all([incidents])
    flash("FixVersion е зачуван.", "success")
    return redirect(url_for("incidents.incident_detail", iid=iid))


@bp.route("/incidents/escalate", methods=["POST"])
@require("admin", "magacioner")
def incident_escalate():
    import config
    from app import backup_all, history, incidents
    from services.escalation_service import EscalationService

    db_path = getattr(incidents, "db_path", None)
    svc = EscalationService(incidents, history, db_path=db_path)
    iid = request.form.get("incident_id", "").strip()
    try:
        if iid:
            result = svc.escalate(iid, performed_by=_who())
            if result["escalated"]:
                flash(f"Инцидентот {iid} е ескалиран.", "success")
                from app import notifications as _notif
                from services.notify_center import push as _push

                _inc = incidents.find("IncidentID", iid)
                _push(
                    _notif,
                    (_inc.get("Assignee", "") if _inc else ""),
                    "incident",
                    iid,
                    f"Ескалиран тикет {iid}.",
                )
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
    import config
    from app import backup_all, comments, history, incidents
    from services.comment_service import CommentService

    db_path = getattr(comments, "db_path", None)
    svc = CommentService(comments, incidents, history, db_path=db_path)
    iid = request.form.get("incident_id", "").strip()
    body = request.form.get("body", "")
    try:
        svc.add(
            iid,
            _who(),
            body,
            performed_by=_who(),
        )
        if config.BACKUP_ON_WRITE:
            backup_all([comments])
        _notify_collab(iid, f"Нов коментар на {iid}.", body)
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
    import config
    from app import backup_all, kb_links

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
    import config
    from app import backup_all, incidents, kb_links

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

    import config
    from app import backup_all, comments, history, incidents
    from services.mail_ingest import (
        MailError,
        configured,
    )
    from services.mail_ingest import (
        confirm as _confirm,
    )
    from services.mail_ingest import fetch_unseen as _fetch
    from services.mail_ingest import reconcile as _reconcile

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


@bp.route("/incidents/link", methods=["POST"])
@require("admin", "magacioner")
def incident_link():
    from app import history, incidents

    iid = request.form.get("incident_id", "").strip()
    target = request.form.get("target_id", "").strip()
    try:
        if not iid or not target:
            raise ValueError("Пополнете ги двете полиња.")
        if iid == target:
            raise ValueError("Инцидентот не може да биде дупликат на самиот себе.")
        if incidents.find("IncidentID", iid) is None:
            raise ValueError(f"Инцидентот {iid} не постои.")
        if incidents.find("IncidentID", target) is None:
            raise ValueError(f"Целта {target} не постои.")
        incidents.update_where("IncidentID", iid, {"LinkedTo": target})
        history.log(
            "INC_LINK",
            iid,
            "",
            target,
            "",
            "",
            f"Дупликат на {target}",
            "",
            _who(),
            "",
        )
        flash(f"Инцидентот {iid} е означен како дупликат на {target}.", "success")
    except ValueError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")
    return redirect(url_for("incidents.incident_detail", iid=iid))


@bp.route("/incidents/unlink", methods=["POST"])
@require("admin", "magacioner")
def incident_unlink():
    from app import history, incidents

    iid = request.form.get("incident_id", "").strip()
    try:
        inc = incidents.find("IncidentID", iid)
        if inc is None:
            raise ValueError(f"Инцидентот {iid} не постои.")
        old = (inc.get("LinkedTo", "") or "").strip()
        if not old:
            flash("Нема врска за отстранување.", "warning")
        else:
            incidents.update_where("IncidentID", iid, {"LinkedTo": ""})
            history.log(
                "INC_UNLINK",
                iid,
                old,
                "",
                "",
                "",
                f"Отстранет дупликат {old}",
                "",
                _who(),
                "",
            )
            flash("Врската е отстранета.", "success")
    except ValueError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")
    return redirect(url_for("incidents.incident_detail", iid=iid))
