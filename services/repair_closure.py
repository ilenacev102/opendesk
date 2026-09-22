"""Repair closure: unrepairable device -> terminal Disposed path."""

from services.db_service import db_transaction, open_store
from services.repair_service import REPAIR_COLS
from utils.helpers import next_id_in, stamp, backup_all
from utils.validators import ValidationError, require_device


class RepairClosureService:
    def __init__(self, paths, devices, history):
        self.store = open_store(
            paths.get("db"), "repairs", paths["repairs"], REPAIR_COLS
        )
        self.devices = devices
        self.history = history
        self.paths = paths

    def mark_unrepairable(
        self, asset_id, reason="Не се поправа", notes="", performed_by="admin"
    ):
        dev = require_device(self.devices, asset_id)
        old = dev.get("Status", "")
        if old not in ("Broken", "Repair"):
            raise ValidationError(
                f"Само уреди на сервис може да се означат како непоправливи (статус: {old})."
            )
        backup_all([self.devices, self.store, self.history.store])
        db_path = self.paths.get("db")
        with db_transaction(db_path) as con:
            tid = next_id_in(self.store, "TransactionID", "BR", con)
            self.devices.update_where(
                "AssetID",
                asset_id,
                {"Status": "Disposed", "EmployeeID": ""},
                con=con,
            )
            self.store.append_row(
                {
                    "TransactionID": tid,
                    "DateTime": stamp(),
                    "AssetID": asset_id,
                    "EmployeeID": dev.get("EmployeeID", ""),
                    "Problem": "",
                    "RepairStatus": "Unrepairable",
                    "ServiceProvider": "",
                    "ServiceDate": "",
                    "ReturnDate": stamp(),
                    "Notes": f"Непоправлив: {reason}. {notes}".strip(),
                    "PerformedBy": performed_by,
                    "DocumentPath": "",
                },
                con=con,
            )
            self.history.log(
                "REPAIR_UNREPAIRABLE",
                asset_id,
                old,
                "Disposed",
                dev.get("EmployeeID", ""),
                "",
                reason,
                notes,
                performed_by,
                "",
                con=con,
            )
        return tid
