"""REPAIR lifecycle: Broken -> Repair -> Repaired -> Available."""

import uuid

from services.db_service import db_transaction, open_store
from services.document_service import fill_template, mk_date
from utils.helpers import next_id_in, stamp, backup_all
from utils.validators import ValidationError, require_device, require_employee

REPAIR_COLS = [
    "TransactionID",
    "DateTime",
    "AssetID",
    "EmployeeID",
    "Problem",
    "RepairStatus",
    "ServiceProvider",
    "ServiceDate",
    "ReturnDate",
    "Notes",
    "PerformedBy",
    "DocumentPath",
]

FLOW = {"Broken": "Repair", "Repair": "Repaired", "Repaired": "Available"}


class RepairService:
    def __init__(self, paths, devices, employees, history):
        self.store = open_store(
            paths.get("db"), "repairs", paths["repairs"], REPAIR_COLS
        )
        self.devices = devices
        self.employees = employees
        self.history = history
        self.paths = paths

    def report_broken(
        self, asset_id, problem="", notes="", performed_by="admin", emp_id=""
    ):
        dev = require_device(self.devices, asset_id)
        if dev.get("Status") in ("Disposed", "Lost", "Stolen"):
            raise ValidationError(f"Уредот {asset_id} е {dev.get('Status')}.")
        old = dev.get("Status", "")
        holder_id = emp_id or dev.get("EmployeeID", "")
        backup_all([self.devices, self.store, self.history.store])
        row = {
            "DateTime": stamp(),
            "AssetID": asset_id,
            "EmployeeID": holder_id,
            "Problem": problem,
            "RepairStatus": "Broken",
            "ServiceProvider": "",
            "ServiceDate": "",
            "ReturnDate": "",
            "Notes": notes,
            "PerformedBy": performed_by,
            "DocumentPath": "",
        }
        db_path = self.paths.get("db")
        with db_transaction(db_path) as con:
            tid = next_id_in(self.store, "TransactionID", "BR", con)
            row["TransactionID"] = tid
            self.devices.update_where(
                "AssetID", asset_id, {"Status": "Broken"}, con=con
            )
            self.store.append_row(row, con=con)
            self.history.log(
                "BROKEN",
                asset_id,
                old,
                "Broken",
                dev.get("EmployeeID", ""),
                "",
                problem,
                notes,
                performed_by,
                "",
                con=con,
            )
        return tid

    def advance(
        self,
        asset_id,
        provider="",
        notes="",
        performed_by="admin",
        return_to_emp=False,
    ):
        dev = require_device(self.devices, asset_id)
        old = dev.get("Status", "")
        if old not in FLOW:
            raise ValidationError(
                f"Уредот {asset_id} со статус {old} не е во сервис- тек."
            )
        new = FLOW[old]
        doc_rel = ""
        holder_id = dev.get("EmployeeID", "")
        if old == "Broken":
            if not notes:
                for rec in self.store.records():
                    if rec.get("AssetID") == asset_id and rec.get("Problem"):
                        notes = rec["Problem"]
            holder = self.employees.find("EmployeeID", holder_id)
            if holder is None:
                for rec in self.store.records():
                    if rec.get("AssetID") == asset_id and rec.get("EmployeeID"):
                        holder = self.employees.find("EmployeeID", rec["EmployeeID"])
                        if holder is not None:
                            holder_id = rec["EmployeeID"]
                            break
            doc_rel = fill_template(
                "Servis_Template.docx",
                {
                    "«ИМЕ_ПРЕЗИМЕ»": (
                        f"{holder['FirstName']} {holder['LastName']}" if holder else ""
                    ),
                    "«EMAIL»": holder.get("Email", "") if holder else "",
                    "«КОМПАНИЈА»": holder.get("Organization", "") if holder else "",
                    "«ОДДЕЛ»": holder.get("Department", "") if holder else "",
                    "«ПРОИЗВОДИТЕЛ»": dev.get("Manufacturer", ""),
                    "«МОДЕЛ»": dev.get("Model", ""),
                    "«СЕРИСКИ_БРОЈ»": dev.get("SerialNumber", ""),
                    "«ИНВЕНТАРЕН_БРОЈ»": asset_id,
                    "«ДЕФЕКТ»": notes,
                    "«СЕРВИСЕР»": provider,
                    "«ДАТУМ_ИСПРАЌАЊЕ»": mk_date(),
                    "«ДАТУМ_ВРАЌАЊЕ»": "",
                    "«ДА_НЕ»": "",
                },
                f"Repair_{asset_id}_{uuid.uuid4().hex[:8]}.docx",
                "repairs",
            )
        backup_all([self.devices, self.store, self.history.store])
        patch = {"Status": new}
        final_status = new
        if new == "Available":
            if return_to_emp and holder_id:
                patch["Status"] = "Assigned"
                patch["EmployeeID"] = holder_id
                final_status = "Assigned"
            else:
                patch["EmployeeID"] = ""

        db_path = self.paths.get("db")
        with db_transaction(db_path) as con:
            tid = next_id_in(self.store, "TransactionID", "BR", con)
            self.devices.update_where("AssetID", asset_id, patch, con=con)
            self.store.append_row(
                {
                    "TransactionID": tid,
                    "DateTime": stamp(),
                    "AssetID": asset_id,
                    "EmployeeID": holder_id,
                    "Problem": "",
                    "RepairStatus": final_status,
                    "ServiceProvider": provider,
                    "ServiceDate": stamp() if old == "Broken" else "",
                    "ReturnDate": stamp()
                    if final_status in ("Available", "Assigned")
                    else "",
                    "Notes": notes,
                    "PerformedBy": performed_by,
                    "DocumentPath": doc_rel,
                },
                con=con,
            )
            self.history.log(
                "REPAIR_" + final_status.upper(),
                asset_id,
                old,
                final_status,
                holder_id,
                "",
                "",
                notes,
                performed_by,
                doc_rel,
                con=con,
            )
        return tid, doc_rel
