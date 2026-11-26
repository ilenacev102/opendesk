"""F2: in-app notifications (bell). Never raises for empty username."""

from typing import Any

from utils.helpers import next_id_in, stamp
from utils.validators import ValidationError


def push(
    store: Any, username: str, kind: str, ref_id: str = "", text: str = ""
) -> dict[str, str] | None:
    """Store one notification; None when no recipient (never an error)."""
    from services.db_service import store_transaction

    username = (username or "").strip()
    if not username:
        return None
    with store_transaction(store) as con:
        row = {
            "NotifID": next_id_in(store, "NotifID", "N", con),
            "UserName": username,
            "Kind": (kind or "").strip(),
            "RefID": (ref_id or "").strip(),
            "Text": (text or "").strip(),
            "Created": stamp(),
            "ReadAt": "",
        }
        store.append_row(row, con=con)
    return row


def unread(store: Any, username: str) -> list[dict[str, Any]]:
    """Unread notifications for a user, newest first."""
    username = (username or "").strip()
    rows = [
        r
        for r in store.records()
        if (r.get("UserName", "") or "") == username and not r.get("ReadAt")
    ]
    rows.sort(key=lambda r: str(r.get("Created", "")), reverse=True)
    return rows


def mark_read(store: Any, username: str, notif_id: str = "") -> int:
    """Mark one (or all when empty id) as read; returns count changed."""
    from services.db_service import store_transaction

    username = (username or "").strip()
    notif_id = (notif_id or "").strip()
    changed = 0
    with store_transaction(store) as con:
        for r in store.records():
            if (r.get("UserName", "") or "") != username or r.get("ReadAt"):
                continue
            if notif_id and str(r.get("NotifID", "")) != notif_id:
                continue
            store.update_where(
                "NotifID", str(r.get("NotifID", "")), {"ReadAt": stamp()}, con=con
            )
            changed += 1
    return changed


def validate_kind(kind: str) -> str:
    """Allowed notification kinds (attformat prevents bell spam)."""
    allowed = {"incident", "transit", "onboard", "system", "mention"}
    kind = (kind or "").strip()
    if kind not in allowed:
        raise ValidationError(f"Непознат вид известување: {kind}.")
    return kind
