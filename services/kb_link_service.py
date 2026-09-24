"""KB article ↔ incident links + resolve-from-article.

One transaction per mutation (link + audit, resolve + audit). Resolve sets
Status resolved with ClosedAt and appends the article reference to Notes.
"""

from services.db_service import db_transaction
from utils.helpers import stamp


class KbLinkService:
    def __init__(self, kb_links, incidents, kb_articles, history, db_path=None):
        self.kb_links = kb_links
        self.incidents = incidents
        self.kb_articles = kb_articles
        self.history = history
        self.db_path = db_path

    def _tx(self):
        if self.db_path:
            return db_transaction(self.db_path)
        from contextlib import nullcontext

        return nullcontext(None)

    def _linked_pairs(self) -> set[tuple[str, str]]:
        return {
            (r.get("ArticleID", ""), r.get("IncidentID", ""))
            for r in self.kb_links.records()
        }

    def link(self, incident_id, article_id, performed_by="admin") -> dict[str, str]:
        with self._tx() as con:
            if self.incidents.find("IncidentID", incident_id) is None:
                raise ValueError(f"Инцидентот {incident_id} не постои.")
            if self.kb_articles.find("ArticleID", article_id) is None:
                raise ValueError(f"Написот {article_id} не постои.")
            if (article_id, incident_id) in self._linked_pairs():
                raise ValueError("Врската веќе постои.")
            row = {"ArticleID": article_id, "IncidentID": incident_id}
            self.kb_links.append_row(row, con=con)
            self.history.log(
                "KB_LINK",
                incident_id,
                "",
                "",
                "",
                "",
                article_id,
                "",
                performed_by,
                "",
                con=con,
            )
        return row

    def for_incident(self, incident_id) -> list[dict[str, str]]:
        out = []
        for link in self.kb_links.filter_eq("IncidentID", incident_id):
            art = self.kb_articles.find("ArticleID", link.get("ArticleID", ""))
            if art is not None:
                out.append(art)
        return out

    def resolve_from_article(self, incident_id, article_id, performed_by="admin"):
        with self._tx() as con:
            inc = self.incidents.find("IncidentID", incident_id)
            if inc is None:
                raise ValueError(f"Инцидентот {incident_id} не постои.")
            if (inc.get("Status", "") or "") == "resolved":
                raise ValueError(f"Инцидентот {incident_id} е веќе затворен.")
            if (article_id, incident_id) not in self._linked_pairs():
                raise ValueError("Нема врска со тој напис.")
            notes = (inc.get("Notes", "") or "").strip()
            ref = f"[KB:{article_id}]"
            if ref not in notes:
                notes = f"{notes} {ref}".strip()
            self.incidents.update_where(
                "IncidentID",
                incident_id,
                {"Status": "resolved", "ClosedAt": stamp(), "Notes": notes},
                con=con,
            )
            self.history.log(
                "INC_RESOLVE",
                incident_id,
                inc.get("Status", ""),
                "resolved",
                inc.get("EmployeeID", ""),
                "",
                f"{inc.get('Title', '')} {ref}".strip(),
                "",
                performed_by,
                "",
                con=con,
            )
        return self.incidents.find("IncidentID", incident_id)
