"""Worklog time logging (Phase 4.3) — visibility only, no billing."""

import datetime

from utils.helpers import next_id
from utils.validators import ValidationError


def log(
    worklogs,
    incident_id: str,
    username: str,
    minutes,
    worked_date: str,
    note: str = "",
) -> dict[str, str]:
    """Validate and append a worklog row.

    Raises:
        ValidationError: minutes < 1 or worked_date invalid / in the future.
    """
    incident_id = (incident_id or "").strip()
    username = (username or "").strip()
    if not incident_id or not username:
        raise ValidationError("Тикетот и корисникот се задолжителни.")
    try:
        mins = int(str(minutes).strip())
    except ValueError as exc:
        raise ValidationError("Минутите мора да бидат цел број.") from exc
    if mins < 1:
        raise ValidationError("Минутите мора да бидат барем 1.")
    try:
        day = datetime.date.fromisoformat(str(worked_date or "").strip())
    except ValueError as exc:
        raise ValidationError("Невалиден датум на работа.") from exc
    if day > datetime.date.today():
        raise ValidationError("Датумот не може да биде во иднина.")
    row = {
        "WorklogID": next_id(worklogs, "WorklogID", "WL"),
        "IncidentID": incident_id,
        "UserName": username,
        "Minutes": str(mins),
        "WorkedDate": day.isoformat(),
        "Note": (note or "").strip(),
    }
    worklogs.append_row(row)
    return row


def _minutes(row) -> int:
    try:
        return int(str(row.get("Minutes", "")).strip())
    except ValueError:
        return 0


def total_minutes(worklogs, incident_id: str) -> int:
    """Total logged minutes on one incident (garbage-safe)."""
    return sum(
        _minutes(r) for r in worklogs.records() if r.get("IncidentID") == incident_id
    )


def minutes_by_assignee(worklogs, incidents) -> dict[str, int]:
    """Total minutes per assignee, joined through the incident's Assignee."""
    assignee_of = {
        str(r.get("IncidentID", "")): str(r.get("Assignee", "") or "")
        for r in incidents.records()
    }
    out: dict[str, int] = {}
    for row in worklogs.records():
        who = assignee_of.get(str(row.get("IncidentID", "")), "")
        if not who:
            continue
        out[who] = out.get(who, 0) + _minutes(row)
    return out
