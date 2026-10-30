"""Sprint planning: create/start/complete/move/backlog/burndown (Phase 3)."""

import datetime

from services.board_service import _points
from utils.helpers import next_id, stamp
from utils.validators import ValidationError

_STATUSES = ("planned", "active", "completed")


def _parse_day(raw, label):
    try:
        return datetime.date.fromisoformat(str(raw or "").strip())
    except ValueError as exc:
        raise ValidationError(f"Невалиден {label} датум.") from exc


def _sprint(sprints, sprint_id):
    row = sprints.find("SprintID", sprint_id)
    if row is None:
        raise ValidationError("Спринтот не постои.")
    return row


def create(sprints, project_id, name, start, end, goal=""):
    """Create a planned sprint; end must be strictly after start."""
    name = (name or "").strip()
    if not name:
        raise ValidationError("Името на спринтот е задолжително.")
    if not (project_id or "").strip():
        raise ValidationError("Проектот е задолжителен.")
    start_day = _parse_day(start, "почетен")
    end_day = _parse_day(end, "завршен")
    if end_day <= start_day:
        raise ValidationError("Завршниот датум мора да е после почетниот.")
    row = {
        "SprintID": next_id(sprints, "SprintID", "SP"),
        "ProjectID": project_id.strip(),
        "Name": name,
        "Goal": (goal or "").strip(),
        "StartDate": start_day.isoformat(),
        "EndDate": end_day.isoformat(),
        "Status": "planned",
        "Created": stamp(),
    }
    sprints.append_row(row)
    return row


def start(sprints, incidents, sprint_id):
    """Activate a sprint and bind the project's open backlog by Rank.

    Raises:
        ValidationError: unknown/finished sprint or another active sprint
            exists in the same project.
    """
    row = _sprint(sprints, sprint_id)
    if row.get("Status") != "planned":
        raise ValidationError("Само планиран спринт може да се започне.")
    for other in sprints.records():
        if (
            other.get("ProjectID") == row.get("ProjectID")
            and other.get("Status") == "active"
            and other.get("SprintID") != sprint_id
        ):
            raise ValidationError("Веќе постои активен спринт во проектот.")
    sprints.update_where("SprintID", sprint_id, {"Status": "active"})

    backlog_rows = [
        r
        for r in incidents.records()
        if (r.get("SprintID") or "") == ""
        and r.get("ProjectID") == row.get("ProjectID")
        and r.get("Status") in ("open", "in-progress")
    ]
    backlog_rows.sort(key=_rank_key)
    for r in backlog_rows:
        incidents.update_where(
            "IncidentID", r.get("IncidentID", ""), {"SprintID": sprint_id}
        )
    return len(backlog_rows)


def complete(sprints, incidents, sprint_id):
    """Finish a sprint; unresolved tickets return to backlog, none are lost."""
    row = _sprint(sprints, sprint_id)
    if row.get("Status") != "active":
        raise ValidationError("Само активен спринт може да се заврши.")
    sprints.update_where("SprintID", sprint_id, {"Status": "completed"})
    moved = 0
    for r in incidents.records():
        if r.get("SprintID") != sprint_id:
            continue
        if r.get("Status") == "resolved":
            continue
        incidents.update_where("IncidentID", r.get("IncidentID", ""), {"SprintID": ""})
        moved += 1
    return moved


def move_to_sprint(incidents, sprints, issue_id, sprint_id):
    """Bind an open ticket of the same project to a planned/active sprint."""
    sprint = _sprint(sprints, sprint_id)
    if sprint.get("Status") not in ("planned", "active"):
        raise ValidationError("Тикети не може да се додаваат во завршен спринт.")
    issue = incidents.find("IncidentID", issue_id)
    if issue is None:
        raise ValidationError("Тикетот не постои.")
    if issue.get("ProjectID") != sprint.get("ProjectID"):
        raise ValidationError("Тикетот не припаѓа на проектот на спринтот.")
    if issue.get("Status") != "open":
        raise ValidationError("Само отворен тикет може да се стави во спринт.")
    incidents.update_where("IncidentID", issue_id, {"SprintID": sprint_id})
    return issue


def _rank_key(row):
    try:
        return int(str(row.get("Rank", "")).strip())
    except ValueError:
        return 1_000_000


def backlog(incidents, project_id):
    """Project backlog: tickets without a sprint, ordered by Rank."""
    rows = [
        r
        for r in incidents.records()
        if (r.get("SprintID") or "") == "" and r.get("ProjectID") == project_id
    ]
    rows.sort(key=_rank_key)
    return rows


def _day_of(raw):
    try:
        return datetime.date.fromisoformat(str(raw or "").strip()[:10])
    except ValueError:
        return None


def burndown(sprints, incidents, sprint_id, today=None):
    """Daily remaining vs ideal StoryPoints for one sprint."""
    sprint = _sprint(sprints, sprint_id)
    start = _parse_day(sprint.get("StartDate"), "почетен")
    end = _parse_day(sprint.get("EndDate"), "завршен")
    if end < start:
        raise ValidationError("Завршниот датум мора да е после почетниот.")
    tickets = [r for r in incidents.records() if r.get("SprintID") == sprint_id]
    total = sum(_points([r]) for r in tickets)

    days = []
    day = start
    while day <= end:
        days.append(day)
        day += datetime.timedelta(days=1)

    remaining = []
    for current in days:
        left = 0
        for t in tickets:
            created = _day_of(t.get("Created"))
            if created is not None and created > current:
                continue
            closed = _day_of(t.get("ClosedAt"))
            if closed is not None and closed <= current:
                continue
            left += _points([t])
        remaining.append(left)

    n = len(days)
    ideal = [
        round(total * (n - 1 - i) / (n - 1), 1) if n > 1 else 0.0 for i in range(n)
    ]
    return {
        "days": [d.isoformat() for d in days],
        "remaining": remaining,
        "ideal": ideal,
        "total": total,
    }
