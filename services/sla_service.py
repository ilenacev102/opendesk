"""SLA engine: business-hours due dates + breach levels.

Work calendar: Monday–Friday 08:00–16:00, plus caller-supplied holiday dates.
Levels: ok (before warn) / warning (warn..due) / breached (past due).
Garbage dates never breach.
"""

import datetime

WORK_START_HOUR = 8
WORK_END_HOUR = 16

DEFAULT_POLICIES = [
    {"Priority": "low", "WarnHours": "72", "BreachHours": "120"},
    {"Priority": "medium", "WarnHours": "24", "BreachHours": "48"},
    {"Priority": "high", "WarnHours": "8", "BreachHours": "24"},
    {"Priority": "urgent", "WarnHours": "2", "BreachHours": "8"},
]

_STAMP_FMT = "%Y-%m-%d %H:%M"


def _is_workday(day, holidays) -> bool:
    return day.weekday() < 5 and day.isoformat() not in holidays


def _snap_to_work(value, holidays):
    while not _is_workday(value.date(), holidays) or not (
        WORK_START_HOUR <= value.hour < WORK_END_HOUR
        or (value.hour == WORK_START_HOUR and value.minute >= 0)
    ):
        if value.hour >= WORK_END_HOUR or not _is_workday(value.date(), holidays):
            nxt = value.date() + datetime.timedelta(days=1)
            value = datetime.datetime.combine(nxt, datetime.time(WORK_START_HOUR))
        else:
            value = value.replace(hour=WORK_START_HOUR, minute=0)
    if value.hour < WORK_START_HOUR:
        value = value.replace(hour=WORK_START_HOUR, minute=0)
    return value


def add_work_hours(start, hours: float, holidays=()) -> datetime.datetime:
    """Add work hours skipping nights, weekends and holidays."""
    holidays = set(holidays or ())
    current = _snap_to_work(start, holidays)
    remaining = float(hours)
    while remaining > 0:
        if not _is_workday(current.date(), holidays):
            nxt = current.date() + datetime.timedelta(days=1)
            current = datetime.datetime.combine(nxt, datetime.time(WORK_START_HOUR))
            continue
        end = current.replace(hour=WORK_END_HOUR, minute=0)
        if current >= end:
            nxt = current.date() + datetime.timedelta(days=1)
            current = datetime.datetime.combine(nxt, datetime.time(WORK_START_HOUR))
            continue
        chunk = min(remaining, (end - current).total_seconds() / 3600.0)
        current = current + datetime.timedelta(hours=chunk)
        remaining -= chunk
    return current


def _policy_for(policies, priority):
    for p in policies or []:
        if (p.get("Priority", "") or "") == priority:
            return p
    for p in policies or []:
        if (p.get("Priority", "") or "") == "medium":
            return p
    return {"WarnHours": "24", "BreachHours": "48"}


def due_date(created: str, priority: str, policies, holidays=()) -> str:
    try:
        start = datetime.datetime.strptime((created or "").strip(), _STAMP_FMT)
    except ValueError:
        raise ValueError(f"Невалиден датум на креирање: {created}.")
    policy = _policy_for(policies, (priority or "").strip())
    try:
        hours = float(policy.get("BreachHours", "48"))
    except (ValueError, TypeError):
        hours = 48.0
    return add_work_hours(start, hours, holidays).strftime(_STAMP_FMT)


def warn_date(due: str, warn_hours) -> str:
    try:
        moment = datetime.datetime.strptime((due or "").strip(), _STAMP_FMT)
        delta = float(warn_hours)
    except (ValueError, TypeError):
        return ""
    return (moment - datetime.timedelta(hours=delta)).strftime(_STAMP_FMT)


def level(due: str, warn: str, today=None) -> str:
    try:
        due_day = datetime.date.fromisoformat((due or "").strip()[:10])
    except ValueError:
        return "ok"
    try:
        warn_day = datetime.date.fromisoformat((warn or "").strip()[:10])
    except ValueError:
        warn_day = None
    today = today or datetime.date.today()
    if today > due_day:
        return "breached"
    if warn_day is not None and today >= warn_day:
        return "warning"
    return "ok"


def seed_defaults(store) -> int:
    if store.records():
        return 0
    for i, policy in enumerate(DEFAULT_POLICIES, start=1):
        store.append_row(
            {
                "PolicyID": f"P{i}",
                "Priority": policy["Priority"],
                "WarnHours": policy["WarnHours"],
                "BreachHours": policy["BreachHours"],
                "Active": "YES",
            }
        )
    return len(DEFAULT_POLICIES)


PAUSE_REASONS = (
    "Чекање корисник",
    "Чекање добавувач",
    "Чекање надворешен сервис",
)


def pause_allowed(reason: str) -> bool:
    """True only for the 3 audited pause reasons (anti SLA-gaming gate)."""
    return (reason or "").strip() in PAUSE_REASONS


def will_breach(due, within_days: int = 2, today=None) -> bool:
    """True when DueDate falls in [today, today + within_days]."""
    import datetime as _dt

    try:
        day = _dt.date.fromisoformat(str(due or "").strip()[:10])
    except ValueError:
        return False
    if today is None:
        today = _dt.date.today()
    if isinstance(today, str):
        try:
            today = _dt.date.fromisoformat(today[:10])
        except ValueError:
            return False
    try:
        delta = (day - today).days
    except TypeError:
        return False
    return 0 <= delta <= int(within_days)


def forecast(incidents, days: int = 2, today=None):
    """Open incidents breaching within `days`, sorted by DueDate."""
    out = [
        i
        for i in incidents or []
        if (i.get("Status", "") or "") != "resolved"
        and will_breach(i.get("DueDate", ""), days, today)
    ]
    out.sort(key=lambda i: str(i.get("DueDate", "")))
    return out
