"""Backlog + sprints views (Phase 3)."""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from routes._roles import require
from services import sprint_service
from services.project_service import ensure_defaults
from utils.validators import ValidationError

bp = Blueprint("sprints", __name__)


def _who():
    from flask_login import current_user as _cu

    return str(getattr(_cu, "id", "admin")) if _cu else "admin"


def _bootstrap():
    from app import incidents, project_types, projects, sprints

    ensure_defaults(projects, project_types, incidents)
    return projects, incidents, sprints


def _can_plan():
    from flask_login import current_user as _cu

    return bool(_cu and getattr(_cu, "role", "") in ("admin", "magacioner"))


@bp.route("/projects/<pid>/backlog")
def backlog_view(pid):
    projects, incidents, sprints = _bootstrap()
    project = projects.find("ProjectID", pid)
    if project is None:
        abort(404)
    rows = sprint_service.backlog(incidents, pid)
    project_sprints = sorted(
        [s for s in sprints.records() if s.get("ProjectID") == pid],
        key=lambda s: (s.get("StartDate", ""), s.get("Created", "")),
    )
    openable = [s for s in project_sprints if s.get("Status") in ("planned", "active")]
    return render_template(
        "backlog.html",
        project=project,
        rows=rows,
        sprints=project_sprints,
        openable=openable,
        can_plan=_can_plan(),
        points_choices=sprint_service.POINTS,
    )


@bp.route("/projects/<pid>/backlog/reorder", methods=["POST"])
@require("admin", "magacioner")
def backlog_reorder(pid):
    from app import history, incidents

    incident_id = request.form.get("incident", "").strip()
    raw_rank = request.form.get("rank", "").strip()
    try:
        if not incident_id:
            raise ValidationError("Изберете тикет.")
        rank = sprint_service.set_rank(
            incidents,
            pid,
            incident_id,
            raw_rank,
            history=history,
            performed_by=_who(),
            db_path=getattr(incidents, "db_path", None),
        )
        flash(f"Тикетот {incident_id} е преместен на позиција {rank}.", "success")
    except (ValidationError, ValueError):
        flash("ГРЕШКА: невалиден ранг.", "danger")
    return redirect(url_for("sprints.backlog_view", pid=pid))


@bp.route("/projects/<pid>/backlog/points", methods=["POST"])
@require("admin", "magacioner")
def backlog_points(pid):
    from app import history, incidents

    incident_id = request.form.get("incident", "").strip()
    points = request.form.get("story_points", "").strip()
    try:
        points = sprint_service.set_points(
            incidents,
            pid,
            incident_id,
            points,
            history=history,
            performed_by=_who(),
            db_path=getattr(incidents, "db_path", None),
        )
        flash(f"Поените на {incident_id} се {points}.", "success")
    except ValidationError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")
    return redirect(url_for("sprints.backlog_view", pid=pid))


@bp.route("/projects/<pid>/sprints", methods=["POST"])
@require("admin", "magacioner")
def sprint_create(pid):
    from app import history, sprints

    try:
        row = sprint_service.create(
            sprints,
            pid,
            request.form.get("name", ""),
            request.form.get("start_date", ""),
            request.form.get("end_date", ""),
            goal=request.form.get("goal", ""),
            history=history,
            performed_by=_who(),
            db_path=getattr(sprints, "db_path", None),
        )
        flash(f"Спринтот {row['Name']} е креиран.", "success")
        return redirect(url_for("sprints.sprint_detail", sid=row["SprintID"]))
    except ValidationError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")
        return redirect(url_for("sprints.backlog_view", pid=pid))


@bp.route("/sprints/<sid>/start", methods=["POST"])
@require("admin", "magacioner")
def sprint_start(sid):
    from app import history, incidents, sprints

    try:
        bound = sprint_service.start(
            sprints,
            incidents,
            sid,
            history=history,
            performed_by=_who(),
            db_path=getattr(sprints, "db_path", None),
        )
        flash(f"Спринтот е активиран ({bound} тикети врзани).", "success")
    except ValidationError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")
    return redirect(url_for("sprints.sprint_detail", sid=sid))


@bp.route("/sprints/<sid>/complete", methods=["POST"])
@require("admin", "magacioner")
def sprint_complete(sid):
    from app import history, incidents, sprints

    try:
        back = sprint_service.complete(
            sprints,
            incidents,
            sid,
            history=history,
            performed_by=_who(),
            db_path=getattr(sprints, "db_path", None),
        )
        flash(f"Спринтот е завршен ({back} тикети назад во backlog).", "success")
    except ValidationError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")
    return redirect(url_for("sprints.sprint_detail", sid=sid))


@bp.route("/sprints/<sid>/move", methods=["POST"])
@require("admin", "magacioner")
def sprint_move(sid):
    from app import history, incidents, sprints

    incident_id = request.form.get("incident", "").strip()
    try:
        sprint_service.move_to_sprint(
            incidents,
            sprints,
            incident_id,
            sid,
            history=history,
            performed_by=_who(),
            db_path=getattr(sprints, "db_path", None),
        )
        flash(f"Тикетот {incident_id} е додаден во спринтот.", "success")
    except ValidationError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")
    return redirect(url_for("sprints.sprint_detail", sid=sid))


@bp.route("/sprints/<sid>/analytics")
def sprint_analytics(sid):
    """Burndown curve + velocity chart for one sprint (vanilla-canvas view)."""
    from app import incidents, projects, sprints

    sprint = sprints.find("SprintID", sid)
    if sprint is None:
        abort(404)
    project = projects.find("ProjectID", sprint.get("ProjectID", ""))
    burndown_chart = sprint_service.burndown(sprints, incidents, sid)
    velocity_rows = [
        r
        for r in sprint_service.velocity(sprints, incidents)
        if r["SprintID"]
        in {
            s.get("SprintID", "")
            for s in sprints.records()
            if s.get("ProjectID") == sprint.get("ProjectID", "")
        }
    ]
    return render_template(
        "sprint_analytics.html",
        sprint=sprint,
        project=project,
        burndown=burndown_chart,
        velocity=velocity_rows,
    )


@bp.route("/sprints/<sid>")
def sprint_detail(sid):
    from app import incidents, projects, sprints

    sprint = sprints.find("SprintID", sid)
    if sprint is None:
        abort(404)
    project = projects.find("ProjectID", sprint.get("ProjectID", ""))
    tickets = [r for r in incidents.records() if r.get("SprintID") == sid]
    tickets.sort(key=lambda r: str(r.get("IncidentID", "")))
    chart = sprint_service.burndown(sprints, incidents, sid)
    total_points = chart["total"]
    return render_template(
        "sprint.html",
        sprint=sprint,
        project=project,
        tickets=tickets,
        chart=chart,
        total_points=total_points,
        can_plan=_can_plan(),
    )
