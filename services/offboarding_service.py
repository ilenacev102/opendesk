"""MS-1: offboarding flags (pure functions, no I/O).

A device is flagged when it is still assigned to a departed employee
(any employee whose Active is not "YES"). Read-only: nothing here writes.
"""

from collections.abc import Iterable
from datetime import date
from typing import Any

OFF_ESC_ACTION = "OFF_ESC"


def _today_str(today: Any = None) -> str:
    if today is None:
        return date.today().isoformat()
    return str(today)[:10]


def days_since(date_str: str, today: Any = None) -> int | None:
    """Days between a "YYYY-MM-DD..." stamp and today.

    Args:
        date_str: Stamp like ``stamp()`` ("YYYY-MM-DD HH:MM").
        today: Override for today ("YYYY-MM-DD" or None).

    Returns:
        Day count, or None for empty/garbage input.
    """
    try:
        day = str(date_str or "")[:10]
        delta = _today_str(today)[:10]
        d1 = date(int(day[0:4]), int(day[5:7]), int(day[8:10]))
        d2 = date(int(delta[0:4]), int(delta[5:7]), int(delta[8:10]))
        return (d2 - d1).days
    except (ValueError, TypeError, IndexError):
        return None


def overdue(
    flagged: Iterable[dict[str, Any]],
    since_map: dict[str, str],
    days: int,
    today: Any = None,
) -> list[dict[str, Any]]:
    """Subset of flagged devices unreturned for at least ``days`` days.

    Args:
        flagged: Devices from :func:`flagged_devices`.
        since_map: ``{AssetID: last-touch "YYYY-MM-DD..." stamp}``.
        days: Threshold in days.
        today: Override for today.

    Returns:
        Flagged devices whose stamp is ``days`` or older. Devices without
        a parseable stamp are never overdue (cannot be proven).
    """
    out = []
    for dev in flagged:
        age = days_since(since_map.get(str(dev.get("AssetID", "")), ""), today)
        if age is not None and age >= days:
            out.append(dev)
    return out


def escalate(
    history: Any, asset_id: str, performed_by: str = "admin"
) -> dict[str, Any]:
    """Flag one unreturned device in the audit trail, idempotently.

    Args:
        history: HistoryService (or compatible ``log`` + ``store``).
        asset_id: Device to escalate.
        performed_by: Who escalates.

    Returns:
        ``{"escalated": True/False}`` — False when already escalated.
    """
    asset_id = (asset_id or "").strip()
    if not asset_id:
        raise ValueError("AssetID е задолжителен.")
    for row in history.store.records():
        if row.get("Action") == OFF_ESC_ACTION and row.get("AssetID") == asset_id:
            return {"escalated": False, "asset_id": asset_id}
    history.log(
        OFF_ESC_ACTION,
        asset_id,
        "",
        "",
        reason="Невратен уред кај заминат вработен",
        performed_by=performed_by,
    )
    return {"escalated": True, "asset_id": asset_id}


def departed_ids(employees: Iterable[dict[str, Any]]) -> set[str]:
    """Collect EmployeeIDs of departed employees.

    Args:
        employees: Employee row dicts with EmployeeID/Active.

    Returns:
        Set of EmployeeID strings with Active != "YES".
    """
    return {
        str(e.get("EmployeeID", ""))
        for e in employees
        if e.get("EmployeeID") and e.get("Active") != "YES"
    }


def flagged_devices(
    devices: Iterable[dict[str, Any]], departed: Iterable[Any]
) -> list[dict[str, Any]]:
    """Return devices still assigned to departed employees.

    Args:
        devices: Device row dicts with AssetID/EmployeeID.
        departed: Iterable of departed EmployeeID values.

    Returns:
        List of device dicts whose EmployeeID is in departed.
    """
    gone = {str(d) for d in departed}
    return [d for d in devices if str(d.get("EmployeeID", "")) in gone]
