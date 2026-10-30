"""@mentions in comments (Phase 4.1)."""

import re

from services import notify_center

_MENTION_RE = re.compile(r"@([A-Za-z0-9][A-Za-z0-9_-]*(?:\.[A-Za-z0-9_-]+)*)")


def extract(text: str) -> list[str]:
    """Usernames mentioned in text (@ime), unique, in order of appearance."""
    seen: list[str] = []
    for match in _MENTION_RE.finditer(text or ""):
        name = match.group(1)
        if name not in seen:
            seen.append(name)
    return seen


def notify(notif_store, users_store, mentions, incident_id, text: str = "") -> int:
    """Push a mention notification to each mentioned existing user.

    Unknown usernames are ignored (never an error).
    Returns the number of notifications created.
    """
    valid = {(u.get("UserName", "") or "") for u in users_store.records()}
    count = 0
    for name in mentions:
        if name not in valid:
            continue
        if notify_center.push(notif_store, name, "mention", incident_id, text):
            count += 1
    return count
