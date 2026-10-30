"""MS-6: auditor evidence export (pure, no I/O).

One click proves repeatability: who did what, when, and why — for any period.
"""

import datetime as _dt
from collections.abc import Iterable
from typing import Any


def _day(raw: Any) -> _dt.date:
    return _dt.date.fromisoformat(str(raw or "").strip()[:10])


def export_changes(
    rows: Iterable[dict[str, Any]], frm: Any, to: Any
) -> list[dict[str, str]]:
    """Filter history rows to [frm, to] and map to evidence rows.

    Args:
        rows: History row dicts (DateTime/Action/AssetID/PerformedBy/Reason).
        frm: Start date (YYYY-MM-DD).
        to: End date (YYYY-MM-DD).

    Returns:
        List of ``{when, who, what, why}`` dicts, oldest first.

    Raises:
        ValueError: On garbage dates or an inverted range.
    """
    try:
        start, end = _day(frm), _day(to)
    except ValueError:
        raise ValueError("Невалиден опсег (YYYY-MM-DD).")
    if start > end:
        raise ValueError("Почетокот е по крајот.")
    out = []
    for r in rows:
        try:
            day = _day(r.get("DateTime", ""))
        except ValueError:
            continue
        if not (start <= day <= end):
            continue
        what = f"{r.get('Action', '')} {r.get('AssetID', '')}".strip()
        out.append(
            {
                "when": str(r.get("DateTime", "")),
                "who": str(r.get("PerformedBy", "")),
                "what": what,
                "why": str(r.get("Reason", "")),
            }
        )
    out.sort(key=lambda e: e["when"])
    return out
