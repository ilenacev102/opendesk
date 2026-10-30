"""Projects + issue types blueprint (Phase 1)."""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from routes._roles import require
from services.project_service import (
    WORKFLOWS,
    create_project,
    ensure_defaults,
)
from utils.validators import ValidationError

bp = Blueprint("projects", __name__)


def _who():
    from flask_login import current_user as _cu

    return str(getattr(_cu, "id", "admin")) if _cu else "admin"


def _bootstrap():
    """Ensure default project/types and backfill legacy tickets, then load."""
    from app import incidents, project_types, projects

    ensure_defaults(projects, project_types, incidents)
    return projects, project_types, incidents


@bp.route("/projects")
def project_list():
    projects, project_types, incidents = _bootstrap()
    rows = sorted(
        projects.records(),
        key=lambda r: (r.get("Status", "") != "active", r.get("Name", "")),
    )
    from services.analytics_service import by_project

    counts = by_project(incidents.records())
    return render_template("projects.html", projects=rows, counts=counts)


@bp.route("/projects/<pid>")
def project_detail(pid):
    projects, project_types, incidents = _bootstrap()
    project = projects.find("ProjectID", pid)
    if project is None:
        abort(404)
    stats = {"total": 0, "open": 0, "in-progress": 0, "resolved": 0}
    for inc in incidents.records():
        if inc.get("ProjectID") != pid:
            continue
        stats["total"] += 1
        status = inc.get("Status", "")
        if status in stats:
            stats[status] += 1
    types = [
        t
        for t in project_types.records()
        if t.get("ProjectID") == pid and t.get("Active") == "YES"
    ]
    return render_template(
        "project_detail.html", project=project, stats=stats, types=types
    )


@bp.route("/projects", methods=["POST"])
@require("admin")
def project_create():
    from app import history, projects

    try:
        row = create_project(
            projects,
            history,
            request.form.get("name", ""),
            request.form.get("key", ""),
            lead=request.form.get("lead", ""),
            description=request.form.get("description", ""),
            performed_by=_who(),
            db_path=getattr(projects, "db_path", None),
        )
        flash(f"Проектот {row['Name']} е креиран.", "success")
        return redirect(url_for("projects.project_detail", pid=row["ProjectID"]))
    except ValidationError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")
        return redirect(url_for("projects.project_list"))


@bp.route("/projects/<pid>/archive", methods=["POST"])
@require("admin")
def project_archive(pid):
    from app import history, projects
    from services.db_service import db_transaction
    from utils.helpers import stamp

    project = projects.find("ProjectID", pid)
    if project is None:
        abort(404)
    try:
        with db_transaction(getattr(projects, "db_path", None)) as con:
            projects.update_where(
                "ProjectID", pid, {"Status": "archived", "Updated": stamp()}, con=con
            )
            history.log(
                "PRJ_ARCHIVE",
                pid,
                project.get("Status", ""),
                "archived",
                performed_by=_who(),
                con=con,
            )
        flash(f"Проектот {project['Name']} е архивиран.", "success")
    except ValidationError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")
    return redirect(url_for("projects.project_list"))


@bp.route("/projects/<pid>/types", methods=["POST"])
@require("admin")
def project_add_type(pid):
    from app import project_types, projects
    from utils.helpers import next_id

    project = projects.find("ProjectID", pid)
    if project is None or project.get("Status") != "active":
        abort(404)
    name = request.form.get("name", "").strip()
    workflow = request.form.get("workflow", "").strip()
    priority = request.form.get("default_priority", "medium").strip()
    try:
        if not name:
            raise ValidationError("Името на типот е задолжително.")
        if workflow not in WORKFLOWS:
            raise ValidationError(f"Непознат workflow: {workflow}.")
        for t in project_types.records():
            if (
                t.get("ProjectID") == pid
                and t.get("Active") == "YES"
                and t.get("Name") == name
            ):
                raise ValidationError(f"Типот {name} веќе постои во проектот.")
        project_types.append_row(
            {
                "TypeID": next_id(project_types, "TypeID", "TY"),
                "ProjectID": pid,
                "Name": name,
                "Icon": "",
                "DefaultPriority": priority,
                "Workflow": workflow,
                "Active": "YES",
            }
        )
        flash(f"Типот {name} е додаден.", "success")
    except ValidationError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")
    return redirect(url_for("projects.project_detail", pid=pid))


@bp.route("/projects/<pid>/settings")
@require("admin")
def project_settings(pid):
    projects, project_types, _incidents = _bootstrap()
    project = projects.find("ProjectID", pid)
    if project is None:
        abort(404)
    types = [t for t in project_types.records() if t.get("ProjectID") == pid]
    return render_template(
        "project_settings.html",
        project=project,
        types=types,
        workflows=WORKFLOWS,
    )


@bp.route("/projects/<pid>/settings", methods=["POST"])
@require("admin")
def project_settings_save(pid):
    from app import history, projects
    from services.db_service import db_transaction
    from utils.helpers import stamp

    project = projects.find("ProjectID", pid)
    if project is None:
        abort(404)
    name = request.form.get("name", "").strip()
    lead = request.form.get("lead", "").strip()
    description = request.form.get("description", "").strip()
    try:
        if not name:
            raise ValidationError("Името е задолжително.")
        with db_transaction(getattr(projects, "db_path", None)) as con:
            projects.update_where(
                "ProjectID",
                pid,
                {
                    "Name": name,
                    "Lead": lead,
                    "Description": description,
                    "Updated": stamp(),
                },
                con=con,
            )
            history.log(
                "PRJ_UPDATE",
                pid,
                project.get("Name", ""),
                name,
                performed_by=_who(),
                con=con,
            )
        flash("Проектот е ажуриран.", "success")
    except ValidationError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")
    return redirect(url_for("projects.project_settings", pid=pid))


@bp.route("/projects/<pid>/types/<tid>/toggle", methods=["POST"])
@require("admin")
def project_type_toggle(pid, tid):
    from app import project_types
    from services.db_service import db_transaction

    row = project_types.find("TypeID", tid)
    if row is None or row.get("ProjectID") != pid:
        abort(404)
    active = "NO" if row.get("Active") == "YES" else "YES"
    with db_transaction(getattr(project_types, "db_path", None)) as con:
        project_types.update_where("TypeID", tid, {"Active": active}, con=con)
    state = "активиран" if active == "YES" else "деактивиран"
    flash(f"Типот {row.get('Name', '')} е {state}.", "success")
    return redirect(url_for("projects.project_settings", pid=pid))


@bp.route("/projects/<pid>/export")
@require("admin")
def project_export(pid):
    import json

    from services.project_template import export_project

    projects, project_types, _incidents = _bootstrap()
    try:
        payload = export_project(projects, project_types, pid)
    except ValidationError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")
        return redirect(url_for("projects.project_list"))
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    return (
        body,
        200,
        {
            "Content-Type": "application/json; charset=utf-8",
            "Content-Disposition": f'attachment; filename="project-{pid}.json"',
        },
    )


@bp.route("/projects/import", methods=["POST"])
@require("admin")
def project_import():
    import json

    from app import history, project_types, projects
    from services.project_template import import_project

    file = request.files.get("file")
    if file is None or not file.filename:
        flash("ГРЕШКА: изберете JSON датотека.", "danger")
        return redirect(url_for("projects.project_list"))
    try:
        data = json.loads(file.read().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "Невалиден JSON", 400
    try:
        row = import_project(
            projects,
            project_types,
            history,
            data,
            performed_by=_who(),
            db_path=getattr(projects, "db_path", None),
        )
        flash(
            f"Проектот {row['project']['Name']} е увезен "
            f"({row['types_created']} типови).",
            "success",
        )
        return redirect(
            url_for("projects.project_detail", pid=row["project"]["ProjectID"])
        )
    except ValidationError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")
        return redirect(url_for("projects.project_list"))
