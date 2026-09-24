"""Minimal incidents: open -> in-progress -> resolved + SLA breach flag.

Every mutation is logged to HistoryService (INC_CREATE/INC_START/INC_RESOLVE)
inside the same transaction as the write, so audit can never diverge.
"""

import datetime

from services.db_service import db_transaction
from utils.helpers import next_id_in, stamp

PRIORITIES = ("low", "medium", "high", "urgent")
STATUSES = ("open", "in-progress", "resolved")

_TRANSITIONS = {
    "open": ("in-progress",),
    "in-progress": ("resolved",),
    "resolved": (),
}

_ACTION = {
    ("open", "in-progress"): "INC_START",
    ("in-progress", "resolved"): "INC_RESOLVE",
}


def breach(due_date, today=None) -> bool:
    """True when due date passed. Empty/garbage dates never breach."""
    raw = str(due_date or "").strip()[:10]
    if not raw:
        return False
    try:
        due = datetime.date.fromisoformat(raw)
    except ValueError:
        return False
    today = today or datetime.date.today()
    return due < today


class IncidentService:
    def __init__(self, store, history, db_path=None):
        self.store = store
        self.history = history
        self.db_path = db_path

    def _tx(self):
        if self.db_path:
            return db_transaction(self.db_path)
        from contextlib import nullcontext

        return nullcontext(None)

    def create(
        self,
        asset_id="",
        title="",
        priority="medium",
        employee_id="",
        assignee="",
        due_date="",
        notes="",
        performed_by="admin",
    ):
        title = (title or "").strip()
        if not title:
            raise ValueError("Насловот е задолжителен.")
        if priority not in PRIORITIES:
            raise ValueError(f"Невалиден приоритет: {priority}.")
        due = (due_date or "").strip()[:10]
        if due:
            try:
                datetime.date.fromisoformat(due)
            except ValueError:
                raise ValueError(f"Невалиден рок: {due_date}.")
        with self._tx() as con:
            iid = next_id_in(self.store, "IncidentID", "I", con)
            row = {
                "IncidentID": iid,
                "AssetID": (asset_id or "").strip(),
                "EmployeeID": (employee_id or "").strip(),
                "Title": title,
                "Priority": priority,
                "Status": "open",
                "Assignee": (assignee or "").strip(),
                "DueDate": due,
                "Created": stamp(),
                "ClosedAt": "",
                "Notes": (notes or "").strip(),
            }
            self.store.append_row(row, con=con)
            self.history.log(
                "INC_CREATE",
                iid,
                "",
                "open",
                row["EmployeeID"],
                "",
                f"{title} [{priority}]".strip(),
                "",
                performed_by,
                "",
                con=con,
            )
        return self.store.find("IncidentID", iid)

    def transition(self, incident_id, to_status, performed_by="admin"):
        if to_status not in STATUSES:
            raise ValueError(f"Невалиден статус: {to_status}.")
        with self._tx() as con:
            inc = self.store.find("IncidentID", incident_id)
            if inc is None:
                raise ValueError(f"Инцидентот {incident_id} не постои.")
            allowed = _TRANSITIONS.get(inc.get("Status", ""), ())
            if to_status not in allowed:
                raise ValueError(
                    f"Недозволен премин: {inc.get('Status')} -> {to_status}."
                )
            updates = {"Status": to_status}
            if to_status == "resolved":
                updates["ClosedAt"] = stamp()
            self.store.update_where("IncidentID", incident_id, updates, con=con)
            self.history.log(
                _ACTION[(inc.get("Status", ""), to_status)],
                incident_id,
                inc.get("Status", ""),
                to_status,
                inc.get("EmployeeID", ""),
                "",
                inc.get("Title", ""),
                "",
                performed_by,
                "",
                con=con,
            )
        return self.store.find("IncidentID", incident_id)

    def breached(self, incident, today=None) -> bool:
        if (incident.get("Status", "") or "") == "resolved":
            return False
        return breach(incident.get("DueDate", ""), today)
