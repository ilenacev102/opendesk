"""Pure Kanban helpers for the board view (Phase 2)."""

from services.project_service import WORKFLOWS
from utils.validators import ValidationError


def columns_for(workflow_key):
    """Return the ordered status columns of a workflow.

    Raises:
        ValidationError: when the workflow key is unknown.
    """
    if workflow_key not in WORKFLOWS:
        raise ValidationError(f"Непознат workflow: {workflow_key}.")
    return tuple(WORKFLOWS[workflow_key])


def group_issues(issues, columns):
    """Bucket issues per column; unknown or empty status lands in the first column."""
    groups = {c: [] for c in columns}
    first = columns[0]
    for issue in issues:
        status = issue.get("Status", "")
        groups[status if status in groups else first].append(issue)
    return groups


def apply_filters(issues, assignee=None, itype=None, priority=None):
    """Return issues matching the given equality filters (None means no filter)."""
    filtered = []
    for issue in issues:
        if assignee and issue.get("Assignee", "") != assignee:
            continue
        if itype and issue.get("TypeID", "") != itype:
            continue
        if priority and issue.get("Priority", "") != priority:
            continue
        filtered.append(issue)
    return filtered


def _points(rows):
    """Sum StoryPoints, ignoring blank or garbage values."""
    total = 0
    for row in rows:
        try:
            total += int(row.get("StoryPoints") or 0)
        except (TypeError, ValueError):
            continue
    return total


def board_payload(issues, workflow_key, filters=None):
    """Build a JSON-ready board dict: columns with counts plus filtered issues.

    Args:
        issues: incident row dicts.
        workflow_key: key into project_service.WORKFLOWS.
        filters: optional dict for apply_filters (assignee/itype/priority).
    """
    columns = columns_for(workflow_key)
    filtered = apply_filters(issues, **(filters or {}))
    groups = group_issues(filtered, columns)
    cols = [
        {
            "name": name,
            "count": len(groups[name]),
            "points": _points(groups[name]),
            "issues": groups[name],
        }
        for name in columns
    ]
    return {"columns": cols, "total": len(filtered)}
