"""Analytics aggregations: pure functions (record lists in, dicts out).

No stores, no I/O, no network. Empty and garbage inputs yield zeros —
never exceptions.
"""

import datetime

_STAMP_FMT = "%Y-%m-%d %H:%M"


def _parse_day(raw):
    try:
        return datetime.date.fromisoformat(str(raw or "").strip()[:10])
    except ValueError:
        return None


def _parse_stamp(raw):
    try:
        return datetime.datetime.strptime(str(raw or "").strip(), _STAMP_FMT)
    except ValueError:
        return None


def _to_float(raw) -> float:
    try:
        return float(str(raw or "").strip().replace(",", "."))
    except (ValueError, TypeError):
        return 0.0


def devices_by(records, field) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in records or []:
        key = (r.get(field, "") or "").strip() or "—"
        out[key] = out.get(key, 0) + 1
    return out


def warranty_buckets(records, today=None) -> dict[str, int]:
    today = today or datetime.date.today()
    out = {"expired": 0, "d30": 0, "d60": 0, "d90": 0}
    for r in records or []:
        day = _parse_day(r.get("WarrantyUntil", ""))
        if day is None:
            continue
        delta = (day - today).days
        if delta < 0:
            out["expired"] += 1
        elif delta <= 30:
            out["d30"] += 1
        elif delta <= 60:
            out["d60"] += 1
        elif delta <= 90:
            out["d90"] += 1
    return out


def costs_by(records, field) -> dict[str, float]:
    out: dict[str, float] = {}
    for r in records or []:
        key = (r.get(field, "") or "").strip() or "—"
        out[key] = out.get(key, 0.0) + _to_float(r.get("PurchasePrice", ""))
    return {k: round(v, 2) for k, v in out.items()}


def incidents_by(records):
    by_status: dict[str, int] = {}
    by_priority: dict[str, int] = {}
    for r in records or []:
        st = (r.get("Status", "") or "").strip() or "—"
        pr = (r.get("Priority", "") or "").strip() or "—"
        by_status[st] = by_status.get(st, 0) + 1
        by_priority[pr] = by_priority.get(pr, 0) + 1
    return by_status, by_priority


def breach_counts(records, today=None) -> int:
    today = today or datetime.date.today()
    count = 0
    for r in records or []:
        if (r.get("Status", "") or "") == "resolved":
            continue
        due = _parse_day(r.get("DueDate", ""))
        if due is not None and today > due:
            count += 1
    return count


def mttr_hours(records):
    total, count = 0.0, 0
    for r in records or []:
        if (r.get("Status", "") or "") != "resolved":
            continue
        start = _parse_stamp(r.get("Created", ""))
        end = _parse_stamp(r.get("ClosedAt", ""))
        if start is None or end is None or end < start:
            continue
        total += (end - start).total_seconds() / 3600.0
        count += 1
    if not count:
        return None
    return round(total / count, 1)


def aging_buckets(records, today=None) -> dict[str, int]:
    today = today or datetime.date.today()
    out = {"d7": 0, "d30": 0, "over30": 0}
    for r in records or []:
        if (r.get("Status", "") or "") == "resolved":
            continue
        start = _parse_stamp(r.get("Created", ""))
        if start is None:
            continue
        age = (today - start.date()).days
        if age < 0:
            continue
        if age <= 7:
            out["d7"] += 1
        elif age <= 30:
            out["d30"] += 1
        else:
            out["over30"] += 1
    return out


def license_expiry(records, today=None, days: int = 30) -> list[dict[str, str]]:
    today = today or datetime.date.today()
    out = []
    for r in records or []:
        day = _parse_day(r.get("ExpiryDate", ""))
        if day is None:
            continue
        delta = (day - today).days
        if 0 <= delta <= days:
            out.append(r)
    out.sort(key=lambda r: str(r.get("ExpiryDate", "")))
    return out
