"""Kanban board views (Phase 2)."""

from flask import Blueprint, abort, render_template, request

from services.board_service import board_payload
from services.project_service import ensure_defaults

bp = Blueprint("boards", __name__)


def _who():
    from flask_login import current_user as _cu

    return str(getattr(_cu, "id", "")) if _cu else ""


def _query_filters():
    """Collect assignee/type/priority filters from the query string."""
    filters = {}
    for arg in ("assignee", "itype", "priority"):
        value = request.args.get(arg, "").strip()
        if value:
            filters[arg] = value
    return filters


def _workflow_for(project_id, project_types):
    """Workflow of the project's first active type (fallback: incident)."""
    for row in project_types.records():
        if row.get("ProjectID") == project_id and row.get("Active") == "YES":
            return row.get("Workflow") or "incident"
    return "incident"


def _assignees(rows):
    return sorted({r.get("Assignee", "") for r in rows if r.get("Assignee")})


@bp.route("/projects/<pid>/board")
def project_board(pid):
    from app import incidents, project_types, projects

    ensure_defaults(projects, project_types, incidents)
    project = projects.find("ProjectID", pid)
    if project is None:
        abort(404)
    rows = [r for r in incidents.records() if r.get("ProjectID") == pid]
    if request.args.get("sprint") == "active":
        from app import sprints

        active = next(
            (
                s["SprintID"]
                for s in sprints.records()
                if s.get("ProjectID") == pid and s.get("Status") == "active"
            ),
            None,
        )
        rows = [r for r in rows if active and r.get("SprintID") == active]
    filters = _query_filters()
    mine = request.args.get("mine") == "1"
    if mine:
        filters["assignee"] = _who()
    workflow = _workflow_for(pid, project_types)
    payload = board_payload(rows, workflow, filters)
    types = [
        t
        for t in project_types.records()
        if t.get("ProjectID") == pid and t.get("Active") == "YES"
    ]
    return render_template(
        "board.html",
        project=project,
        payload=payload,
        filters=filters,
        mine=mine,
        types=types,
        assignees=_assignees(rows),
    )


@bp.route("/my-board")
def my_board():
    from app import incidents

    who = _who()
    rows = [r for r in incidents.records() if r.get("Assignee") == who]
    filters = _query_filters()
    payload = board_payload(rows, "incident", filters)
    return render_template(
        "board.html",
        project=None,
        payload=payload,
        filters=filters,
        mine=True,
        types=[],
        assignees=_assignees(rows),
    )
