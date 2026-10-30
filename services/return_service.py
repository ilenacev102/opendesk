"""RETURN flow: validate -> devices -> returns -> history -> doc."""

import uuid

from services.db_service import db_transaction, open_store
from services.document_service import fill_zadolzenie, fill_zadolzenie_multi
from services.return_documents import multi_return_items, single_return_doc, today_datum
from utils.helpers import backup_all, next_id_in, stamp
from utils.validators import ValidationError, require_employee, require_returnable

RETURN_COLS = [
    "TransactionID",
    "DateTime",
    "AssetID",
    "EmployeeID",
    "Reason",
    "Condition",
    "Notes",
    "PerformedBy",
    "DocumentPath",
]

CONDITION_STATUS = {
    "Good": "Available",
    "Damaged": "Broken",
    "Broken": "Broken",
    "Incomplete": "Broken",
    "Other": "Available",
}


class ReturnService:
    def __init__(self, paths, devices, employees, history):
        self.store = open_store(
            paths.get("db"), "returns", paths["returns"], RETURN_COLS
        )
        self.devices = devices
        self.employees = employees
        self.history = history
        self.paths = paths

    def confirm(
        self,
        asset_id,
        emp_id,
        reason="",
        condition="Good",
        notes="",
        performed_by="admin",
    ):
        emp = require_employee(self.employees, emp_id)
        dev = require_returnable(self.devices, asset_id, emp_id)
        old_status = dev.get("Status", "")
        new_status = CONDITION_STATUS.get(condition, "Available")
        datum = today_datum()
        doc_rel = fill_zadolzenie(
            single_return_doc(emp, dev, asset_id, condition, datum),
            f"Return_{emp_id}_{asset_id}_{uuid.uuid4().hex[:8]}.docx",
            "returns",
        )
        backup_all([self.devices, self.employees, self.store, self.history.store])
        db_path = self.paths.get("db")
        with db_transaction(db_path) as con:
            tid = next_id_in(self.store, "TransactionID", "R", con)
            self.devices.update_where(
                "AssetID",
                asset_id,
                {"Status": new_status, "EmployeeID": ""},
                con=con,
            )
            self.store.append_row(
                {
                    "TransactionID": tid,
                    "DateTime": stamp(),
                    "AssetID": asset_id,
                    "EmployeeID": emp_id,
                    "Reason": reason,
                    "Condition": condition,
                    "Notes": notes,
                    "PerformedBy": performed_by,
                    "DocumentPath": doc_rel,
                },
                con=con,
            )
            self.history.log(
                "RETURN",
                asset_id,
                old_status,
                new_status,
                emp_id,
                f"{emp['FirstName']} {emp['LastName']}",
                reason,
                notes,
                performed_by,
                doc_rel,
                con=con,
            )
        return tid, doc_rel

    def confirm_many(
        self,
        asset_ids,
        emp_id,
        reason="Раздолжување при заминување",
        condition="Good",
        notes="",
        performed_by="admin",
    ):
        emp = require_employee(self.employees, emp_id)
        if not asset_ids:
            raise ValidationError("Избери барем еден уред за враќање.")
        devs = [require_returnable(self.devices, aid, emp_id) for aid in asset_ids]
        datum = today_datum()
        items = multi_return_items(devs)
        doc_rel = fill_zadolzenie_multi(
            {
                "name": f"{emp['FirstName']} {emp['LastName']}",
                "email": emp.get("Email", ""),
                "company": emp.get("Organization", ""),
                "department": emp.get("Department", ""),
                "date_z": "",
                "date_v": datum,
                "da_ne": "ДА" if condition == "Good" else "НЕ",
            },
            items,
            f"Return_{emp_id}_{len(items)}uredi_{stamp().replace(' ', '_').replace(':', '').replace('-', '')}.docx",
            "returns",
        )
        backup_all([self.devices, self.employees, self.store, self.history.store])
        new_status = CONDITION_STATUS.get(condition, "Available")
        tids = []
        db_path = self.paths.get("db")
        with db_transaction(db_path) as con:
            for dev, aid in zip(devs, asset_ids):
                old_status = dev.get("Status", "")
                tid = next_id_in(self.store, "TransactionID", "R", con)
                self.devices.update_where(
                    "AssetID",
                    aid,
                    {"Status": new_status, "EmployeeID": ""},
                    con=con,
                )
                self.store.append_row(
                    {
                        "TransactionID": tid,
                        "DateTime": stamp(),
                        "AssetID": aid,
                        "EmployeeID": emp_id,
                        "Reason": reason,
                        "Condition": condition,
                        "Notes": notes,
                        "PerformedBy": performed_by,
                        "DocumentPath": doc_rel,
                    },
                    con=con,
                )
                self.history.log(
                    "RETURN",
                    aid,
                    old_status,
                    new_status,
                    emp_id,
                    f"{emp['FirstName']} {emp['LastName']}",
                    reason,
                    notes,
                    performed_by,
                    doc_rel,
                    con=con,
                )
                tids.append(tid)
        return tids, doc_rel
