"""REPLACE: old Assigned->Returned, new Available->Assigned + docs + history."""

import uuid

from services.db_service import db_transaction, open_store
from services.document_service import fill_template, mk_date
from utils.helpers import next_id_in, stamp, backup_all
from utils.validators import ValidationError, require_device, require_employee

REPLACE_COLS = [
    "TransactionID",
    "DateTime",
    "OldAssetID",
    "NewAssetID",
    "EmployeeID",
    "Reason",
    "Notes",
    "PerformedBy",
    "DocumentPath",
]


class ReplacementService:
    def __init__(self, paths, devices, employees, history):
        self.store = open_store(
            paths.get("db"), "replacements", paths["replacements"], REPLACE_COLS
        )
        self.devices = devices
        self.employees = employees
        self.history = history
        self.paths = paths

    def confirm(
        self,
        old_id,
        new_id,
        emp_id,
        reason="",
        notes="",
        performed_by="admin",
        old_condition="Available",
    ):
        if old_id == new_id:
            raise ValidationError("Стариот и новиот уред се исти.")
        emp = require_employee(self.employees, emp_id)
        old = require_device(self.devices, old_id)
        new = require_device(self.devices, new_id)
        if old.get("EmployeeID") != emp_id or old.get("Status") != "Assigned":
            raise ValidationError(f"Уредот {old_id} не е задолжен кај {emp_id}.")
        if new.get("Status") != "Available":
            raise ValidationError(
                f"Новиот уред {new_id} не е достапен (статус: {new.get('Status')})."
            )
        target_old_status = (
            "Broken"
            if old_condition == "Broken"
            else ("Disposed" if old_condition == "Disposed" else "Available")
        )
        doc_rel = fill_template(
            "Zamena_Template.docx",
            {
                "«ИМЕ_ПРЕЗИМЕ»": f"{emp['FirstName']} {emp['LastName']}",
                "«EMAIL»": emp.get("Email", ""),
                "«КОМПАНИЈА»": emp.get("Organization", ""),
                "«ОДДЕЛ»": emp.get("Department", ""),
                "«СТАР_ПРОИЗВОДИТЕЛ»": old.get("Manufacturer", ""),
                "«СТАР_МОДЕЛ»": old.get("Model", ""),
                "«СТАР_СЕРИСКИ_БРОЈ»": old.get("SerialNumber", ""),
                "«СТАР_ИНВЕНТАРЕН_БРОЈ»": old_id,
                "«НОВ_ПРОИЗВОДИТЕЛ»": new.get("Manufacturer", ""),
                "«НОВ_МОДЕЛ»": new.get("Model", ""),
                "«НОВ_СЕРИСКИ_БРОЈ»": new.get("SerialNumber", ""),
                "«НОВ_ИНВЕНТАРЕН_БРОЈ»": new_id,
                "«ПРИЧИНА»": reason
                + (
                    f" (Состојба стар: {target_old_status})"
                    if target_old_status != "Available"
                    else ""
                ),
                "«ДАТУМ»": mk_date(),
            },
            f"Replacement_{emp_id}_{old_id}_{new_id}_{uuid.uuid4().hex[:8]}.docx",
            "replacements",
        )
        backup_all([self.devices, self.store, self.history.store])
        name = f"{emp['FirstName']} {emp['LastName']}"
        db_path = self.paths.get("db")
        with db_transaction(db_path) as con:
            tid = next_id_in(self.store, "TransactionID", "RP", con)
            self.devices.update_where(
                "AssetID",
                old_id,
                {"Status": target_old_status, "EmployeeID": ""},
                con=con,
            )
            self.devices.update_where(
                "AssetID",
                new_id,
                {"Status": "Assigned", "EmployeeID": emp_id},
                con=con,
            )
            self.store.append_row(
                {
                    "TransactionID": tid,
                    "DateTime": stamp(),
                    "OldAssetID": old_id,
                    "NewAssetID": new_id,
                    "EmployeeID": emp_id,
                    "Reason": reason,
                    "Notes": f"Состојба стар: {target_old_status}. " + (notes or ""),
                    "PerformedBy": performed_by,
                    "DocumentPath": doc_rel,
                },
                con=con,
            )
            self.history.log(
                "REPLACE_OUT",
                old_id,
                "Assigned",
                target_old_status,
                emp_id,
                name,
                reason,
                notes,
                performed_by,
                doc_rel,
                con=con,
            )
            self.history.log(
                "REPLACE_IN",
                new_id,
                "Available",
                "Assigned",
                emp_id,
                name,
                reason,
                notes,
                performed_by,
                doc_rel,
                con=con,
            )
        return tid, doc_rel
