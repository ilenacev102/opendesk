"""F1: my-work aggregator (pure, no I/O)."""

import datetime as _dt
from collections.abc import Iterable
from typing import Any

from services.incident_service import breach


def _today(today: Any = None) -> _dt.date:
    if today is None:
        return _dt.date.today()
    if isinstance(today, _dt.date):
        return today
    return _dt.date.fromisoformat(str(today)[:10])


def days_left(due: Any, today: Any = None) -> int | None:
    """Days until DueDate (negative when breached, None for garbage)."""
    try:
        day = _dt.date.fromisoformat(str(due or "").strip()[:10])
    except ValueError:
        return None
    return (day - _today(today)).days


def collect(
    username: str,
    incidents: Iterable[dict[str, Any]],
    devices: Iterable[dict[str, Any]],
    history: Iterable[dict[str, Any]],
    today: Any = None,
) -> dict[str, Any]:
    """Aggregate one user's burning items (read-only)."""
    who = (username or "").strip()
    day = _today(today)
    mine = [
        i
        for i in incidents
        if (i.get("Assignee", "") or "") == who
        and (i.get("Status", "") or "") != "resolved"
    ]
    breached = [i for i in mine if breach(i.get("DueDate", ""), day)]
    due_soon = [
        i
        for i in mine
        if (lambda n: n is not None and 0 <= n <= 2)(
            days_left(i.get("DueDate", ""), day)
        )
    ]
    seen: list[str] = []
    for h in history:
        if h.get("Action") != "ASSIGN" or (h.get("PerformedBy", "") or "") != who:
            continue
        aid = str(h.get("AssetID", ""))
        if aid and aid not in seen:
            seen.append(aid)
        if len(seen) >= 20:
            break
    by_asset = {str(d.get("AssetID", "")): d for d in devices}
    my_devices = [by_asset[a] for a in seen if a in by_asset]
    pending_receives = [
        d for d in devices if (d.get("Status", "") or "") == "InTransit"
    ]
    return {
        "my_open": mine,
        "breached": breached,
        "due_soon": due_soon,
        "my_devices": my_devices,
        "pending_receives": pending_receives,
    }
