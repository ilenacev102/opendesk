"""Central audit trail - every mutation writes here."""

from typing import Any

from services.csv_service import CsvStore
from utils.helpers import next_id, next_id_in, stamp

HISTORY_COLS = [
    "HistoryID",
    "DateTime",
    "Action",
    "AssetID",
    "OldStatus",
    "NewStatus",
    "EmployeeID",
    "EmployeeName",
    "Reason",
    "Notes",
    "PerformedBy",
    "DocumentPath",
]


class HistoryService:
    def __init__(self, store_or_path):
        if isinstance(store_or_path, str):
            self.store = CsvStore(store_or_path, HISTORY_COLS)
        else:
            self.store = store_or_path

    def log(
        self,
        action,
        asset_id,
        old_status,
        new_status,
        emp_id="",
        emp_name="",
        reason="",
        notes="",
        performed_by="admin",
        doc_path="",
        con=None,
    ):
        hid = (
            next_id_in(self.store, "HistoryID", "H", con)
            if con is not None
            else next_id(self.store, "HistoryID", "H")
        )
        data = {
            "HistoryID": hid,
            "DateTime": stamp(),
            "Action": action,
            "AssetID": asset_id,
            "OldStatus": old_status,
            "NewStatus": new_status,
            "EmployeeID": emp_id,
            "EmployeeName": emp_name,
            "Reason": reason,
            "Notes": notes,
            "PerformedBy": performed_by,
            "DocumentPath": doc_path,
        }
        append_fn = getattr(self.store, "append_row", None)
        if append_fn:
            import inspect

            sig = inspect.signature(append_fn)
            if "con" in sig.parameters:
                return append_fn(data, con=con)
            return append_fn(data)
        return data

    def for_asset(self, asset_id) -> list[dict[str, Any]]:
        f = getattr(self.store, "filter_eq", None)
        if callable(f):
            from typing import Any, cast
            from collections.abc import Callable

            res: Any = cast(Callable[..., Any], f)("AssetID", asset_id)
            return cast(list[dict[str, Any]], res)
        return [r for r in self.store.records() if r.get("AssetID") == asset_id]

    def for_employee(self, emp_id) -> list[dict[str, Any]]:
        f = getattr(self.store, "filter_eq", None)
        if callable(f):
            from typing import Any, cast
            from collections.abc import Callable

            res: Any = cast(Callable[..., Any], f)("EmployeeID", emp_id)
            return cast(list[dict[str, Any]], res)
        return [r for r in self.store.records() if r.get("EmployeeID") == emp_id]

    def recent(self, limit=20) -> list[dict[str, Any]]:
        f = getattr(self.store, "recent", None)
        if callable(f):
            from typing import Any, cast
            from collections.abc import Callable

            res: Any = cast(Callable[..., Any], f)(limit)
            return cast(list[dict[str, Any]], res)
        return self.store.records()[-limit:][::-1]
