"""Incident watchers (Phase 4.2)."""

from services import notify_center
from utils.helpers import stamp


def watch(watchers, incident_id: str, username: str) -> bool:
    """Add a watcher; duplicates are no-ops. True when a row was added."""
    from services.db_service import store_transaction

    incident_id = (incident_id or "").strip()
    username = (username or "").strip()
    if not incident_id or not username:
        return False
    with store_transaction(watchers) as con:
        for row in watchers.records():
            if row.get("IncidentID") == incident_id and row.get("UserName") == username:
                return False
        watchers.append_row(
            {"IncidentID": incident_id, "UserName": username, "AddedAt": stamp()},
            con=con,
        )
    return True


def unwatch(watchers, incident_id: str, username: str) -> bool:
    """Remove a watcher. True when a row was removed."""
    incident_id = (incident_id or "").strip()
    username = (username or "").strip()
    removed = watchers.delete_where_all(
        {"IncidentID": incident_id, "UserName": username}
    )
    return bool(removed)


def list_watchers(watchers, incident_id: str) -> list[str]:
    """Usernames watching the incident, in insertion order."""
    return [
        str(r.get("UserName", "") or "")
        for r in watchers.records()
        if r.get("IncidentID") == incident_id
    ]


def notify_watchers(notif_store, watchers, incident_id: str, text: str = "") -> int:
    """Notify every watcher about a comment/status change. Returns count pushed."""
    count = 0
    for username in list_watchers(watchers, incident_id):
        if notify_center.push(notif_store, username, "incident", incident_id, text):
            count += 1
    return count
