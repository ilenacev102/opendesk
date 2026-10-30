"""Incident watchers (Phase 4.2)."""

from services import notify_center
from utils.helpers import stamp


def watch(watchers, incident_id: str, username: str) -> bool:
    """Add a watcher; duplicates are no-ops. True when a row was added."""
    incident_id = (incident_id or "").strip()
    username = (username or "").strip()
    if not incident_id or not username:
        return False
    for row in watchers.records():
        if row.get("IncidentID") == incident_id and row.get("UserName") == username:
            return False
    watchers.append_row(
        {"IncidentID": incident_id, "UserName": username, "AddedAt": stamp()}
    )
    return True


def unwatch(watchers, incident_id: str, username: str) -> bool:
    """Remove a watcher. True when a row was removed."""
    incident_id = (incident_id or "").strip()
    username = (username or "").strip()
    rows = watchers.records()
    remaining = [
        r
        for r in rows
        if not (r.get("IncidentID") == incident_id and r.get("UserName") == username)
    ]
    if len(remaining) == len(rows):
        return False
    watchers.replace_all(remaining)
    return True


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
