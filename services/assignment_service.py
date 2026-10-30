"""ASSIGN flow: validate -> devices -> assignments -> history -> doc."""

import uuid

from services.db_service import db_transaction, open_store
from services.document_service import fill_zadolzenie, fill_zadolzenie_multi
from utils.helpers import backup_all, next_id_in, stamp
from utils.validators import ValidationError, require_assignable, require_employee

ASSIGN_COLS = [
    "TransactionID",
    "DateTime",
    "AssetID",
    "EmployeeID",
    "Reason",
    "Notes",
    "PerformedBy",
    "DocumentPath",
    "SignaturePath",
]


class AssignmentService:
    def __init__(self, paths, devices, employees, history):
        self.store = open_store(
            paths.get("db"), "assignments", paths["assignments"], ASSIGN_COLS
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
        notes="",
        performed_by="admin",
        signature_path="",
    ):
        emp = require_employee(self.employees, emp_id)
        dev = require_assignable(self.devices, asset_id)
        old_status = dev.get("Status", "")
        today = stamp().split(" ")[0]
        parts = today.split("-")
        datum = f"{parts[2]}.{parts[1]}.{parts[0]}"
        doc_rel = fill_zadolzenie(
            {
                "name": f"{emp['FirstName']} {emp['LastName']}",
                "email": emp.get("Email", ""),
                "company": emp.get("Organization", ""),
                "department": emp.get("Department", ""),
                "manufacturer": dev.get("Manufacturer", ""),
                "model": dev.get("Model", ""),
                "serial": dev.get("SerialNumber", ""),
                "asset": asset_id,
                "date_z": datum,
                "date_v": "",
                "da_ne": "",
                "signature_path": signature_path,
            },
            f"Assignment_{emp_id}_{asset_id}_{uuid.uuid4().hex[:8]}.docx",
        )
        backup_all([self.devices, self.employees, self.store, self.history.store])
        db_path = self.paths.get("db")
        with db_transaction(db_path) as con:
            tid = next_id_in(self.store, "TransactionID", "A", con)
            self.devices.update_where(
                "AssetID",
                asset_id,
                {"Status": "Assigned", "EmployeeID": emp_id},
                con=con,
            )
            self.store.append_row(
                {
                    "TransactionID": tid,
                    "DateTime": stamp(),
                    "AssetID": asset_id,
                    "EmployeeID": emp_id,
                    "Reason": reason,
                    "Notes": notes,
                    "PerformedBy": performed_by,
                    "DocumentPath": doc_rel,
                    "SignaturePath": signature_path,
                },
                con=con,
            )
            self.history.log(
                "ASSIGN",
                asset_id,
                old_status,
                "Assigned",
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
        reason="",
        notes="",
        performed_by="admin",
        signature_path="",
    ):
        emp = require_employee(self.employees, emp_id)
        if not asset_ids:
            raise ValidationError("Избери барем еден уред.")
        devs = [require_assignable(self.devices, aid) for aid in asset_ids]
        today = stamp().split(" ")[0]
        parts = today.split("-")
        datum = f"{parts[2]}.{parts[1]}.{parts[0]}"
        items = [
            {
                "asset": d.get("AssetID", ""),
                "type": d.get("Type", ""),
                "model": d.get("Model", ""),
                "serial": d.get("SerialNumber", ""),
                "manufacturer": d.get("Manufacturer", ""),
            }
            for d in devs
        ]
        doc_rel = fill_zadolzenie_multi(
            {
                "name": f"{emp['FirstName']} {emp['LastName']}",
                "email": emp.get("Email", ""),
                "company": emp.get("Organization", ""),
                "department": emp.get("Department", ""),
                "date_z": datum,
                "date_v": "",
                "da_ne": "",
                "signature_path": signature_path,
            },
            items,
            f"Assignment_{emp_id}_{len(items)}uredi_{stamp().replace(' ', '_').replace(':', '').replace('-', '')}.docx",
        )
        backup_all([self.devices, self.employees, self.store, self.history.store])
        tids = []
        db_path = self.paths.get("db")
        with db_transaction(db_path) as con:
            for dev, asset_id in zip(devs, asset_ids):
                old_status = dev.get("Status", "")
                tid = next_id_in(self.store, "TransactionID", "A", con)
                self.devices.update_where(
                    "AssetID",
                    asset_id,
                    {"Status": "Assigned", "EmployeeID": emp_id},
                    con=con,
                )
                self.store.append_row(
                    {
                        "TransactionID": tid,
                        "DateTime": stamp(),
                        "AssetID": asset_id,
                        "EmployeeID": emp_id,
                        "Reason": reason,
                        "Notes": notes,
                        "PerformedBy": performed_by,
                        "DocumentPath": doc_rel,
                        "SignaturePath": signature_path,
                    },
                    con=con,
                )
                self.history.log(
                    "ASSIGN",
                    asset_id,
                    old_status,
                    "Assigned",
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
