"""Portal self-service tickets: ownership, thread, reopen window, pagination.

The portal is a requester-facing surface. Everything here answers one
question for a route: may this logged-in user act on this incident, and if
so, what may they see or do? Ownership is the incident's ``EmployeeID``
matched against the linked employee row or the account username.
"""

import datetime
import os

from services.db_service import store_transaction

PAGE_SIZE = 10
REOPEN_WINDOW_DAYS = 7
COMMENT_LIMIT = 10
COMMENT_WINDOW_SEC = 60


def _employee_ids(emp, who):
    ids = set()
    if emp:
        ids.add(str(emp.get("EmployeeID", "")).strip())
    ids.add(str(who or "").strip())
    ids.discard("")
    return ids


def owns(incident, emp, who):
    """True when the incident belongs to the employee or the account."""
    owner = str((incident or {}).get("EmployeeID", "")).strip()
    return bool(owner) and owner in _employee_ids(emp, who)


def ticket(incidents, iid, emp, who):
    """Return the incident when owned.

    Raises:
        LookupError: no such incident (route answers 404).
        PermissionError: incident belongs to somebody else (route answers 403).
    """
    inc = incidents.find("IncidentID", iid)
    if inc is None:
        raise LookupError(iid)
    if not owns(inc, emp, who):
        raise PermissionError(iid)
    return inc


def thread(comments, iid):
    """Public comments for one incident, oldest first."""
    rows = comments.filter_eq("IncidentID", iid)
    rows.sort(key=lambda r: r.get("Created", ""))
    return rows


def _last_reopen(history, iid):
    stamps = [
        h.get("DateTime", "")
        for h in history.store.records()
        if h.get("Action") == "INC_REOPEN" and h.get("AssetID") == iid
    ]
    stamps = [s for s in stamps if s]
    return max(stamps) if stamps else ""


def reopen(incidents, history, iid, performed_by="portal"):
    """Reopen a resolved ticket; at most once per seven days.

    Raises:
        LookupError: no such incident.
        ValueError: not resolved, or reopened too recently.
    """
    with store_transaction(
        incidents, fallback_path=getattr(incidents, "db_path", None)
    ) as con:
        inc = incidents.find("IncidentID", iid)
        if inc is None:
            raise LookupError(iid)
        if (inc.get("Status", "") or "") != "resolved":
            raise ValueError("Повторно може да се отвори само решен тикет.")
        last = _last_reopen(history, iid)
        if last:
            try:
                last_dt = datetime.datetime.fromisoformat(last)
            except ValueError:
                last_dt = None
            if last_dt is not None:
                age = datetime.datetime.now() - last_dt
                if age < datetime.timedelta(days=REOPEN_WINDOW_DAYS):
                    raise ValueError(
                        "Тикетот може да се отвори повторно само еднаш на 7 дена."
                    )
        incidents.update_where(
            "IncidentID", iid, {"Status": "open", "ClosedAt": ""}, con=con
        )
        history.log(
            "INC_REOPEN",
            iid,
            "resolved",
            "open",
            inc.get("EmployeeID", ""),
            "",
            inc.get("Title", ""),
            "",
            performed_by,
            "",
            con=con,
        )
    return incidents.find("IncidentID", iid)


def paginate(rows, page, per_page=PAGE_SIZE):
    """Slice rows for a page; returns (rows, page, total_pages, total)."""
    rows = list(rows or [])
    try:
        per_page = max(1, int(per_page))
    except (TypeError, ValueError):
        per_page = PAGE_SIZE
    try:
        page = max(1, int(page))
    except (TypeError, ValueError):
        page = 1
    total = len(rows)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)
    start = (page - 1) * per_page
    return rows[start : start + per_page], page, total_pages, total


def attachment_path(documents_dir, iid, name):
    """Absolute path for a ticket attachment, or None on traversal/absence."""
    clean = os.path.basename((name or "").strip())
    if not clean or clean in (".", ".."):
        return None
    base = os.path.abspath(documents_dir or ".")
    target = os.path.join(base, "incidents", iid, clean)
    full = os.path.abspath(target)
    if os.path.commonpath([base, full]) != base:
        return None
    return full if os.path.isfile(full) else None


def attachments(documents_dir, iid):
    """File names attached to one ticket, sorted; empty when none."""
    folder = os.path.join(os.path.abspath(documents_dir or "."), "incidents", iid)
    if not os.path.isdir(folder):
        return []
    return sorted(
        name
        for name in os.listdir(folder)
        if os.path.isfile(os.path.join(folder, name))
    )
