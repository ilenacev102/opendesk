"""MS-5: HR intake for onboarding (validation + submit, preview before write).

Rule on the page: without an HR request at least 2 days before the start
date, no account on time. Packages must exist in Packages.json.
"""

import datetime as _dt
from typing import Any

from utils.validators import ValidationError

MIN_LEAD_DAYS = 2


def _today(today: Any = None) -> _dt.date:
    if today is None:
        return _dt.date.today()
    if isinstance(today, _dt.date):
        return today
    return _dt.date.fromisoformat(str(today)[:10])


class OnboardService:
    def __init__(self, store: Any, packages: Any = None, history: Any = None):
        self.store = store
        self.packages = list(packages or [])
        self.history = history

    def _package_ids(self) -> set[str]:
        return {str(p.get("id", "")) for p in self.packages if p.get("id")}

    def validate(self, req: dict[str, Any], today: Any = None) -> dict[str, str]:
        """Check an intake request; return cleaned row (no RequestID)."""
        full = str(req.get("FullName", "")).strip()
        if not full:
            raise ValidationError("Името и презимето се задолжителни.")
        try:
            start = _dt.date.fromisoformat(str(req.get("StartDate", "")).strip()[:10])
        except ValueError:
            raise ValidationError("Невалиден датум на почеток (YYYY-MM-DD).")
        earliest = _today(today) + _dt.timedelta(days=MIN_LEAD_DAYS)
        if start < earliest:
            raise ValidationError(
                f"Пријавата мора најмалку {MIN_LEAD_DAYS} дена пред почеток "
                f"(најрано {earliest.isoformat()} за старт {start.isoformat()})."
            )
        pkg = str(req.get("Package", "")).strip()
        if pkg not in self._package_ids():
            raise ValidationError(f"Непознат пакет: {pkg}.")
        return {
            "FullName": full,
            "Position": str(req.get("Position", "")).strip(),
            "StartDate": start.isoformat(),
            "Package": pkg,
            "RequestedBy": str(req.get("RequestedBy", "")).strip(),
        }

    def submit(
        self, req: dict[str, Any], requested_by: str = "", today: Any = None
    ) -> dict[str, str]:
        """Validate, assign RequestID and store the request."""
        from services.db_service import store_transaction
        from utils.helpers import next_id_in

        clean = self.validate(req, today=today)
        with store_transaction(self.store, getattr(self.history, "store", None)) as con:
            rid = str(req.get("RequestID", "")).strip() or next_id_in(
                self.store, "RequestID", "OB", con
            )
            if self.store.find("RequestID", rid) is not None:
                raise ValidationError(f"Барањето {rid} веќе постои.")
            row = {"RequestID": rid, **clean}
            if not row["RequestedBy"]:
                row["RequestedBy"] = (requested_by or "").strip()
            self.store.append_row(row, con=con)
            if self.history is not None:
                self.history.log(
                    "ONBOARD_CREATE",
                    rid,
                    "",
                    clean["StartDate"],
                    "",
                    clean["FullName"],
                    clean["Package"],
                    "",
                    requested_by or "admin",
                    "",
                    con=con,
                )
        return row
