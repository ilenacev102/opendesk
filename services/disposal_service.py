"""DISPOSAL: any status -> Disposed (one-way, blocked from re-assign)."""

import uuid

from services.db_service import open_store
from services.document_service import fill_template, mk_date
from utils.helpers import next_id, next_id_in, stamp, backup_all
from utils.validators import require_device

DISPOSAL_COLS = [
    "TransactionID",
    "DateTime",
    "AssetID",
    "EmployeeID",
    "Reason",
    "DisposalMethod",
    "Notes",
    "PerformedBy",
    "DocumentPath",
]


class DisposalService:
    def __init__(self, paths, devices, history, make_doc):
        self.store = open_store(
            paths.get("db"), "disposals", paths["disposals"], DISPOSAL_COLS
        )
        self.devices = devices
        self.history = history
        self.make_doc = make_doc
        self.paths = paths

    def confirm(self, asset_id, reason="", method="", notes="", performed_by="admin"):
        from utils.validators import require_disposable

        dev = require_disposable(self.devices, asset_id)
        old = dev.get("Status", "")
        doc_rel = fill_template(
            "Rashod_Template.docx",
            {
                "«ПРОИЗВОДИТЕЛ»": dev.get("Manufacturer", ""),
                "«МОДЕЛ»": dev.get("Model", ""),
                "«СЕРИСКИ_БРОЈ»": dev.get("SerialNumber", ""),
                "«ИНВЕНТАРЕН_БРОЈ»": asset_id,
                "«ТИП»": dev.get("Type", ""),
                "«ПРИЧИНА»": reason,
                "«НАЧИН»": method,
                "«КОМИСИЈА»": notes,
                "«ДАТУМ»": mk_date(),
            },
            f"Disposal_{asset_id}_{uuid.uuid4().hex[:8]}.docx",
            "disposals",
        )
        backup_all([self.devices, self.store, self.history.store])
        db_path = self.paths.get("db")
        if db_path:
            from services.db_service import db_transaction

            with db_transaction(db_path) as con:
                tid = next_id_in(self.store, "TransactionID", "D", con)
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
                        "Reason": reason,
                        "DisposalMethod": method,
                        "Notes": notes,
                        "PerformedBy": performed_by,
                        "DocumentPath": doc_rel,
                    },
                    con=con,
                )
                self.history.log(
                    "DISPOSE",
                    asset_id,
                    old,
                    "Disposed",
                    dev.get("EmployeeID", ""),
                    "",
                    reason,
                    notes,
                    performed_by,
                    doc_rel,
                    con=con,
                )
        else:
            tid = next_id(self.store, "TransactionID", "D")
            self.devices.update_where(
                "AssetID", asset_id, {"Status": "Disposed", "EmployeeID": ""}
            )
            self.store.append_row(
                {
                    "TransactionID": tid,
                    "DateTime": stamp(),
                    "AssetID": asset_id,
                    "EmployeeID": dev.get("EmployeeID", ""),
                    "Reason": reason,
                    "DisposalMethod": method,
                    "Notes": notes,
                    "PerformedBy": performed_by,
                    "DocumentPath": doc_rel,
                }
            )
            self.history.log(
                "DISPOSE",
                asset_id,
                old,
                "Disposed",
                dev.get("EmployeeID", ""),
                "",
                reason,
                notes,
                performed_by,
                doc_rel,
            )
        return tid, doc_rel

    def confirm_many(
        self, asset_ids, reason="", method="", notes="", performed_by="admin"
    ):
        from services.document_service import fill_template, mk_date
        from utils.validators import ValidationError, require_disposable

        if not asset_ids:
            raise ValidationError("Избери барем еден уред.")
        devs = [require_disposable(self.devices, aid) for aid in asset_ids]
        doc_rel = fill_template(
            "Rashod_Template.docx",
            {
                "«ПРОИЗВОДИТЕЛ»": "види список",
                "«МОДЕЛ»": f"{len(devs)} уреди",
                "«СЕРИСКИ_БРОЈ»": "—",
                "«ИНВЕНТАРЕН_БРОЈ»": ", ".join(asset_ids),
                "«ТИП»": "—",
                "«ПРИЧИНА»": reason,
                "«НАЧИН»": method,
                "«КОМИСИЈА»": notes,
                "«ДАТУМ»": mk_date(),
            },
            f"Disposal_grupen_{len(devs)}uredi_{stamp().replace(' ', '_').replace(':', '').replace('-', '')}.docx",
            "disposals",
        )
        backup_all([self.devices, self.store, self.history.store])
        tids = []
        db_path = self.paths.get("db")
        if db_path:
            from services.db_service import db_transaction

            with db_transaction(db_path) as con:
                for dev, asset_id in zip(devs, asset_ids):
                    old = dev.get("Status", "")
                    tid = next_id_in(self.store, "TransactionID", "D", con)
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
                            "Reason": reason,
                            "DisposalMethod": method,
                            "Notes": notes,
                            "PerformedBy": performed_by,
                            "DocumentPath": doc_rel,
                        },
                        con=con,
                    )
                    self.history.log(
                        "DISPOSE",
                        asset_id,
                        old,
                        "Disposed",
                        dev.get("EmployeeID", ""),
                        "",
                        reason,
                        notes,
                        performed_by,
                        doc_rel,
                        con=con,
                    )
                    tids.append(tid)
        else:
            for dev, asset_id in zip(devs, asset_ids):
                old = dev.get("Status", "")
                tid = next_id(self.store, "TransactionID", "D")
                self.devices.update_where(
                    "AssetID", asset_id, {"Status": "Disposed", "EmployeeID": ""}
                )
                self.store.append_row(
                    {
                        "TransactionID": tid,
                        "DateTime": stamp(),
                        "AssetID": asset_id,
                        "EmployeeID": dev.get("EmployeeID", ""),
                        "Reason": reason,
                        "DisposalMethod": method,
                        "Notes": notes,
                        "PerformedBy": performed_by,
                        "DocumentPath": doc_rel,
                    }
                )
                self.history.log(
                    "DISPOSE",
                    asset_id,
                    old,
                    "Disposed",
                    dev.get("EmployeeID", ""),
                    "",
                    reason,
                    notes,
                    performed_by,
                    doc_rel,
                )
                tids.append(tid)
        return tids, doc_rel
