"""Incident comments: validated append + audit, listed oldest-first."""

from services.db_service import db_transaction
from utils.helpers import next_id_in, stamp

MAX_BODY = 2000


class CommentService:
    def __init__(self, comments, incidents, history, db_path=None):
        self.comments = comments
        self.incidents = incidents
        self.history = history
        self.db_path = db_path

    def _tx(self):
        if self.db_path:
            return db_transaction(self.db_path)
        from contextlib import nullcontext

        return nullcontext(None)

    def add(self, incident_id, author, body, performed_by="admin"):
        body = (body or "").strip()
        if not body:
            raise ValueError("Коментарот не може да биде празен.")
        if len(body) > MAX_BODY:
            raise ValueError(f"Коментарот е предолг (макс. {MAX_BODY} знаци).")
        with self._tx() as con:
            if self.incidents.find("IncidentID", incident_id) is None:
                raise ValueError(f"Инцидентот {incident_id} не постои.")
            cid = next_id_in(self.comments, "CommentID", "C", con)
            self.comments.append_row(
                {
                    "CommentID": cid,
                    "IncidentID": incident_id,
                    "Author": (author or "").strip(),
                    "Body": body,
                    "Created": stamp(),
                },
                con=con,
            )
            self.history.log(
                "INC_COMMENT",
                incident_id,
                "",
                "",
                "",
                "",
                body[:120],
                "",
                performed_by,
                "",
                con=con,
            )
        return self.comments.find("CommentID", cid)

    def for_incident(self, incident_id) -> list[dict[str, str]]:
        rows = self.comments.filter_eq("IncidentID", incident_id)
        rows.sort(key=lambda r: r.get("Created", ""))
        return rows
