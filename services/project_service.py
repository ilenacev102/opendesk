"""Projects + issue types: Jira-like grouping for tickets (Phase 1).

Module-level functions (no class) — mirrors the flat style used by
notify_service. Writes use db_transaction when a db_path is supplied so the
row and its audit entry commit atomically; with db_path=None (unit tests,
legacy callers) each write falls back to its own connection.
"""

from contextlib import nullcontext

from services.db_service import db_transaction
from utils.helpers import next_id, next_id_in, stamp
from utils.validators import ValidationError

WORKFLOWS = {
    "incident": ("open", "in-progress", "resolved"),
    "request": ("open", "in-progress", "resolved"),
    "task": ("open", "in-progress", "resolved"),
    "change": ("open", "in-progress", "resolved"),
    "epic": ("Backlog", "In Progress", "Done"),
}

DEFAULT_PROJECT_NAME = "IT ServiceDesk"
DEFAULT_PROJECT_KEY = "IT"
DEFAULT_TYPES = (
    ("Incident", "incident"),
    ("Service Request", "request"),
    ("Task", "task"),
    ("Change", "change"),
    ("Epic", "epic"),
)


def _tx(db_path):
    return db_transaction(db_path) if db_path else nullcontext(None)


def _normalize_key(key):
    key = (key or "").strip().upper()
    if (
        not 2 <= len(key) <= 6
        or not key.isascii()
        or not key.isalnum()
        or not key[0].isalpha()
    ):
        raise ValidationError(
            "Клучот мора да е 2-6 букви/цифри, да почнува со буква "
            f"(A-Z, без празници): {key or '(празно)'}."
        )
    return key


def create_project(
    projects,
    history,
    name,
    key,
    lead="",
    description="",
    performed_by="admin",
    db_path=None,
):
    """Create a project; key is normalized to uppercase and validated."""
    name = (name or "").strip()
    if not name:
        raise ValidationError("Името на проектот е задолжително.")
    key = _normalize_key(key)
    for row in projects.records():
        if (row.get("Key") or "").upper() == key:
            raise ValidationError(f"Проект со клуч {key} веќе постои.")
    with _tx(db_path) as con:
        pid = (
            next_id_in(projects, "ProjectID", "PRJ", con)
            if con is not None
            else next_id(projects, "ProjectID", "PRJ")
        )
        row = {
            "ProjectID": pid,
            "Name": name,
            "Key": key,
            "Lead": (lead or "").strip(),
            "Description": (description or "").strip(),
            "Status": "active",
            "Created": stamp(),
            "Updated": stamp(),
        }
        projects.append_row(row, con=con)
        if history is not None:
            history.log(
                "PRJ_CREATE",
                pid,
                "",
                "active",
                notes=f"{name} [{key}]",
                performed_by=performed_by,
                con=con,
            )
    return projects.find("ProjectID", pid)


def default_project(projects):
    """Return the main active project, creating it when the store is empty."""
    rows = projects.records()
    if not rows:
        return create_project(
            projects,
            None,
            DEFAULT_PROJECT_NAME,
            DEFAULT_PROJECT_KEY,
            description="Автоматски создаден главен проект.",
            performed_by="system",
        )
    for row in rows:
        if row.get("Status") == "active" and row.get("Key") == DEFAULT_PROJECT_KEY:
            return row
    for row in rows:
        if row.get("Status") == "active":
            return row
    return None


def validate_type(type_id, project_id, types):
    """Return the issue type when it exists, belongs to the project, is active."""
    row = types.find("TypeID", type_id)
    if row is None:
        raise ValidationError(f"Типот {type_id} не постои.")
    if row.get("ProjectID", "") != project_id:
        raise ValidationError("Типот припаѓа на друг проект.")
    if row.get("Active", "") != "YES":
        raise ValidationError(f"Типот {row.get('Name', type_id)} е деактивиран.")
    return row


def workflow_columns(workflow_key):
    """Return the ordered status columns for a known workflow."""
    if workflow_key not in WORKFLOWS:
        raise ValidationError(f"Непознат workflow: {workflow_key}.")
    return WORKFLOWS[workflow_key]


def ensure_defaults(projects, types, incidents):
    """Idempotent bootstrap: default project, four default types, backfill.

    Legacy incidents without a project are attached to the default project
    and typed as Incident, so board/statistics queries see every ticket.
    Returns {"project", "types_created", "backfilled", "incident_type"}.
    """
    project = default_project(projects)
    if project is None:
        return {
            "project": None,
            "types_created": 0,
            "backfilled": 0,
            "incident_type": None,
        }
    pid = project["ProjectID"]

    types_created = 0
    for name, workflow in DEFAULT_TYPES:
        # Match by name regardless of Active so a user-deactivated default
        # type is NOT resurrected on the next bootstrap.
        existing = [
            t
            for t in types.records()
            if t.get("ProjectID") == pid and t.get("Name") == name
        ]
        if existing:
            continue
        types.append_row(
            {
                "TypeID": next_id(types, "TypeID", "TY"),
                "ProjectID": pid,
                "Name": name,
                "Icon": "",
                "DefaultPriority": "medium",
                "Workflow": workflow,
                "Active": "YES",
            }
        )
        types_created += 1

    active_types = [
        t
        for t in types.records()
        if t.get("ProjectID") == pid and t.get("Active") == "YES"
    ]
    incident_type = next(
        (t for t in active_types if t.get("Workflow") == "incident"), None
    )
    if incident_type is None:
        incident_type = next(
            (t for t in active_types if t.get("Name") == "Incident"), None
        )
    type_id = incident_type["TypeID"] if incident_type else ""

    backfilled = 0
    for row in incidents.records():
        if (row.get("ProjectID") or "").strip():
            continue
        incidents.update_where(
            "IncidentID",
            row.get("IncidentID", ""),
            {"ProjectID": pid, "TypeID": type_id},
        )
        backfilled += 1

    return {
        "project": project,
        "types_created": types_created,
        "backfilled": backfilled,
        "incident_type": incident_type,
    }
