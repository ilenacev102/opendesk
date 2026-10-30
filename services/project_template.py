"""Project template export/import (Phase 5.3)."""

from typing import Any, TypedDict

from services.project_service import WORKFLOWS, create_project
from utils.helpers import next_id
from utils.validators import ValidationError


class ImportResult(TypedDict):
    project: dict[str, Any]
    types_created: int


def export_project(projects, types, project_id):
    """Return a JSON-ready template of a project: metadata + issue types.

    Raises:
        ValidationError: when the project does not exist.
    """
    project = projects.find("ProjectID", project_id)
    if project is None:
        raise ValidationError("Проектот не постои.")
    rows = [t for t in types.records() if t.get("ProjectID") == project_id]
    return {
        "name": project.get("Name", ""),
        "key": project.get("Key", ""),
        "lead": project.get("Lead", ""),
        "description": project.get("Description", ""),
        "types": [
            {
                "name": t.get("Name", ""),
                "workflow": t.get("Workflow", ""),
                "default_priority": t.get("DefaultPriority", ""),
            }
            for t in rows
        ],
    }


def _unique_key(projects, base):
    """First free project key derived from base (≤6 chars, starts with a letter)."""
    base = (base or "PRJ").upper()
    if not base.isascii() or not base.isalnum() or not base[0].isalpha():
        base = "PRJ"
    taken = {(r.get("Key", "") or "").upper() for r in projects.records()}
    if base[:6] not in taken:
        return base[:6]
    for i in range(1, 100):
        suffix = str(i)
        candidate = base[: 6 - len(suffix)] + suffix
        if candidate and candidate[0].isalpha() and candidate not in taken:
            return candidate
    raise ValidationError("Не може да се изведе слободен клуч.")


def import_project(
    projects, types, history, data, performed_by="admin", db_path=None
) -> ImportResult:
    """Create a project with its issue types from an exported template dict.

    The project key is uniquified so the same template can be cloned
    repeatedly (new client / new department).

    Raises:
        ValidationError: on malformed template data.
    """
    if not isinstance(data, dict):
        raise ValidationError("Шаблонот мора да биде JSON објект.")
    name = str(data.get("name") or "").strip()
    if not name:
        raise ValidationError("Името на проектот е задолжително.")
    raw_types = data.get("types", [])
    if not isinstance(raw_types, list):
        raise ValidationError("Полето types мора да биде листа.")
    normalized = []
    for entry in raw_types:
        if not isinstance(entry, dict):
            raise ValidationError("Секој тип мора да биде објект.")
        tname = str(entry.get("name") or "").strip()
        if not tname:
            raise ValidationError("Типот мора да има име.")
        workflow = str(entry.get("workflow") or "").strip()
        if workflow not in WORKFLOWS:
            raise ValidationError(f"Непознат workflow: {workflow}.")
        priority = str(entry.get("default_priority") or "medium").strip()
        normalized.append((tname, workflow, priority or "medium"))
    if not normalized:
        normalized = [("Incident", "incident", "medium")]

    key = _unique_key(projects, str(data.get("key") or "").strip().upper() or "PRJ")
    project = create_project(
        projects,
        history,
        name,
        key,
        lead=str(data.get("lead") or ""),
        description=str(data.get("description") or ""),
        performed_by=performed_by,
        db_path=db_path,
    )
    created = 0
    for tname, workflow, priority in normalized:
        types.append_row(
            {
                "TypeID": next_id(types, "TypeID", "TY"),
                "ProjectID": project["ProjectID"],
                "Name": tname,
                "Icon": "",
                "DefaultPriority": priority,
                "Workflow": workflow,
                "Active": "YES",
            }
        )
        created += 1
    return {"project": project, "types_created": created}
