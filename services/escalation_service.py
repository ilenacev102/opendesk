"""Escalation runner: bump priority of breached in-progress incidents.

Idempotent: an incident with an ESC_ESCALATE history entry is never
escalated twice. Each escalation (bump + audit) runs in one transaction.
"""

from services.db_service import db_transaction
from services.incident_service import breach

_PRIORITY_LADDER = ("low", "medium", "high", "urgent")


def _bump(priority: str) -> str:
    try:
        idx = _PRIORITY_LADDER.index((priority or "").strip())
    except ValueError:
        return "medium"
    return _PRIORITY_LADDER[min(idx + 1, len(_PRIORITY_LADDER) - 1)]


class EscalationService:
    def __init__(self, incidents, history, db_path=None):
        self.incidents = incidents
        self.history = history
        self.db_path = db_path

    def _tx(self):
        if self.db_path:
            return db_transaction(self.db_path)
        from contextlib import nullcontext

        return nullcontext(None)

    def _escalated_ids(self) -> set[str]:
        return {
            h.get("AssetID", "")
            for h in self.history.store.records()
            if h.get("Action") == "ESC_ESCALATE" and h.get("AssetID")
        }

    def eligible(self, today=None) -> list[dict[str, str]]:
        done = self._escalated_ids()
        out = []
        for inc in self.incidents.records():
            if (inc.get("Status", "") or "") != "in-progress":
                continue
            if not breach(inc.get("DueDate", ""), today):
                continue
            if inc.get("IncidentID") in done:
                continue
            out.append(inc)
        return out

    def escalate(self, incident_id, performed_by="admin") -> dict[str, object]:
        with self._tx() as con:
            inc = self.incidents.find("IncidentID", incident_id)
            if inc is None:
                raise ValueError(f"Инцидентот {incident_id} не постои.")
            if (
                (inc.get("Status", "") or "") != "in-progress"
                or not breach(inc.get("DueDate", ""))
                or incident_id in self._escalated_ids()
            ):
                return {"escalated": False, "incident": inc}
            old = (inc.get("Priority", "") or "medium").strip() or "medium"
            new = _bump(old)
            self.incidents.update_where(
                "IncidentID", incident_id, {"Priority": new}, con=con
            )
            self.history.log(
                "ESC_ESCALATE",
                incident_id,
                old,
                new,
                inc.get("EmployeeID", ""),
                "",
                inc.get("Title", ""),
                "",
                performed_by,
                "",
                con=con,
            )
        return {
            "escalated": True,
            "incident": self.incidents.find("IncidentID", incident_id),
        }

    def escalate_all(self, performed_by="admin") -> dict[str, int]:
        counts = {"escalated": 0, "skipped": 0}
        for inc in self.eligible():
            result = self.escalate(inc["IncidentID"], performed_by=performed_by)
            counts["escalated" if result["escalated"] else "skipped"] += 1
        return counts
