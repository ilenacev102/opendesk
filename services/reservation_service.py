"""Reservation conflict helpers (F4): pure overlap math + guarded create.

Dates are ISO (YYYY-MM-DD); unparseable values raise ValueError so callers
must validate input before reaching the service (routes use ``_parse_day``).
"""

import datetime

from utils.validators import ValidationError


def _d(value):
    return datetime.date.fromisoformat((value or "")[:10])


def overlaps(a_from, a_to, b_from, b_to):
    """True when two inclusive date ranges touch or overlap.

    Touching endpoints (a_to == b_from) count as a conflict — a reservation
    cannot end the day another one starts. Raises ValueError on bad dates.
    """
    a1, a2 = _d(a_from), _d(a_to)
    b1, b2 = _d(b_from), _d(b_to)
    return a1 <= b2 and b1 <= a2


def conflicts(existing, asset_id, frm, to):
    """First active reservation of the asset overlapping [frm, to], else None."""
    start, end = _d(frm), _d(to)
    for r in existing:
        if r.get("AssetID") != asset_id or r.get("Status") != "active":
            continue
        try:
            rs, re_ = _d(r.get("FromDate", "")), _d(r.get("ToDate", ""))
        except ValueError:
            continue
        if start <= re_ and rs <= end:
            return r
    return None


def create(
    store,
    asset_id,
    frm,
    to,
    employee_id="",
    notes="",
    *,
    history=None,
    performed_by="admin",
    con=None,
):
    """Append an active reservation; ValidationError on inverted/conflicting range."""
    start, end = _d(frm), _d(to)
    if end < start:
        raise ValidationError("Крајот е пред почетокот.")
    clash = conflicts(store.records(), asset_id, frm, to)
    if clash is not None:
        raise ValidationError(
            f"Преклопување со {clash.get('ReservationID')} "
            f"({clash.get('FromDate')}–{clash.get('ToDate')})."
        )
    from utils.helpers import next_id, next_id_in

    rid = (
        next_id_in(store, "ReservationID", "R", con)
        if con is not None
        else next_id(store, "ReservationID", "R")
    )
    store.append_row(
        {
            "ReservationID": rid,
            "AssetID": asset_id,
            "EmployeeID": (employee_id or "").strip(),
            "FromDate": start.isoformat(),
            "ToDate": end.isoformat(),
            "Status": "active",
            "Notes": (notes or "").strip(),
        },
        con=con,
    )
    if history is not None:
        history.log(
            "RES_CREATE",
            rid,
            "",
            "active",
            (employee_id or "").strip(),
            "",
            "",
            (notes or "").strip(),
            performed_by,
            "",
            con=con,
        )
    return rid
