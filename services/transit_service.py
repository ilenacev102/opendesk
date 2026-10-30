"""MS-3: device status transition table (pure, no I/O, not wired to routes).

Grounded in existing rules: validators (require_assignable/returnable/disposable),
repair FLOW (Broken -> Repair -> Repaired -> Available), mark_unrepairable
(Broken/Repair -> Disposed), plus the new InTransit custody state.
"""

from typing import Any

from services.db_service import db_transaction, open_store
from services.schemas import TRANSIT_COLS
from utils.helpers import next_id, next_id_in, stamp
from utils.validators import ValidationError

TRANSITIONS: dict[str, tuple[str, ...]] = {
    "Available": ("Assigned", "Broken", "InTransit", "Disposed"),
    "Assigned": ("Available", "Broken", "InTransit"),
    "InTransit": ("Available", "Assigned"),
    "Broken": ("Repair", "Disposed"),
    "Repair": ("Repaired", "Disposed"),
    "Repaired": ("Available", "Assigned"),
    "Lost": ("Disposed",),
    "Stolen": ("Disposed",),
    "Disposed": (),
}

STATUSES: tuple[str, ...] = tuple(TRANSITIONS)


def allowed(frm: Any) -> tuple[str, ...]:
    """Destinations reachable from ``frm`` (empty for unknown/terminal)."""
    return TRANSITIONS.get(str(frm or "").strip(), ())


def can_move(frm: Any, to: Any) -> bool:
    """True when a direct ``frm`` -> ``to`` transition is allowed."""
    src = str(frm or "").strip()
    dst = str(to or "").strip()
    if not src or not dst or src == dst:
        return False
    return dst in TRANSITIONS.get(src, ())


class TransitService:
    """Custody transfers: ship (→ InTransit) + receive (→ Available/Assigned).

    Every move writes a transit row and a history record in one transaction.
    """

    def __init__(self, devices: Any, history: Any, db_path: Any = None):
        self.devices = devices
        self.history = history
        self.db_path = db_path
        self.store = open_store(db_path, "transit", None, TRANSIT_COLS)

    def _tx(self) -> Any:
        if self.db_path:
            return db_transaction(self.db_path)
        from contextlib import nullcontext

        return nullcontext(None)

    def _new_id(self, con: Any) -> str:
        if con is not None:
            return next_id_in(self.store, "TransitID", "TR", con)
        return next_id(self.store, "TransitID", "TR")

    def ship(self, asset_id: str, to_loc: str, by: str = "admin") -> dict[str, Any]:
        """Send a device into transit (Status → InTransit)."""
        asset_id = (asset_id or "").strip()
        to_loc = (to_loc or "").strip()
        if not asset_id:
            raise ValidationError("AssetID е задолжителен.")
        if not to_loc:
            raise ValidationError("Одредишната локација е задолжителна.")
        dev = self.devices.find("AssetID", asset_id)
        if dev is None:
            raise ValidationError(f"Невалиден AssetID: {asset_id}.")
        if not can_move(dev.get("Status", ""), "InTransit"):
            raise ValidationError(
                f"Уредот {asset_id} со статус {dev.get('Status')} не може во транзит."
            )
        from_loc = dev.get("Location", "")
        with self._tx() as con:
            tid = self._new_id(con)
            row = {
                "TransitID": tid,
                "DateTime": stamp(),
                "AssetID": asset_id,
                "FromLoc": from_loc,
                "ToLoc": to_loc,
                "ByUser": by,
            }
            self.store.append_row(row, con=con)
            self.devices.update_where(
                "AssetID",
                asset_id,
                {"Status": "InTransit", "Location": to_loc},
                con=con,
            )
            self.history.log(
                "TRANSIT_SHIP",
                asset_id,
                dev.get("Status", ""),
                "InTransit",
                dev.get("EmployeeID", ""),
                "",
                f"{from_loc} → {to_loc}",
                "",
                by,
                "",
                con=con,
            )
        return dict(row)

    def receive(self, asset_id: str, by: str = "admin") -> dict[str, Any]:
        """Complete transit (InTransit → Assigned when held, else Available)."""
        asset_id = (asset_id or "").strip()
        if not asset_id:
            raise ValidationError("AssetID е задолжителен.")
        dev = self.devices.find("AssetID", asset_id)
        if dev is None:
            raise ValidationError(f"Невалиден AssetID: {asset_id}.")
        if (dev.get("Status", "") or "") != "InTransit":
            raise ValidationError(
                f"Уредот {asset_id} не е во транзит (статус: {dev.get('Status')})."
            )
        holder = dev.get("EmployeeID", "")
        new_status = "Assigned" if holder else "Available"
        with self._tx() as con:
            tid = self._new_id(con)
            row = {
                "TransitID": tid,
                "DateTime": stamp(),
                "AssetID": asset_id,
                "FromLoc": dev.get("Location", ""),
                "ToLoc": dev.get("Location", ""),
                "ByUser": by,
            }
            self.store.append_row(row, con=con)
            self.devices.update_where(
                "AssetID", asset_id, {"Status": new_status}, con=con
            )
            self.history.log(
                "TRANSIT_RECEIVE",
                asset_id,
                "InTransit",
                new_status,
                holder,
                "",
                "Примено",
                "",
                by,
                "",
                con=con,
            )
        return dict(row)
