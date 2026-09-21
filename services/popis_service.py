"""Popis (stocktaking): session with expected vs scanned assets."""

import json
from typing import Any, cast

from services.csv_service import CsvStore
from services.db_service import open_store
from utils.helpers import next_id, next_id_in, stamp

POPIS_COLS = [
    "PopisID",
    "DateTime",
    "Scope",
    "Name",
    "Expected",
    "Found",
    "Status",
    "DocumentPath",
]


class PopisService:
    def __init__(self, db_path, csv_path):
        self.db_path = db_path
        self.store = open_store(db_path, "popis", csv_path, POPIS_COLS)

    def start(self, scope, name, expected_ids):
        row = {
            "DateTime": stamp(),
            "Scope": scope,
            "Name": name,
            "Expected": json.dumps(expected_ids),
            "Found": json.dumps([]),
            "Status": "OPEN",
            "DocumentPath": "",
        }
        if self.db_path:
            from services.db_service import db_transaction

            with db_transaction(self.db_path) as con:
                row["PopisID"] = next_id_in(self.store, "PopisID", "P", con)
                self.store.append_row(row, con=con)
            return row["PopisID"]
        pid = next_id(self.store, "PopisID", "P")
        row["PopisID"] = pid
        self.store.append_row(row)
        return pid

    def get(self, pid):
        rec = self.store.find("PopisID", pid)
        if rec is None:
            return None
        rec["ExpectedIDs"] = cast(list[str], json.loads(rec.get("Expected") or "[]"))
        rec["FoundIDs"] = cast(list[str], json.loads(rec.get("Found") or "[]"))
        return rec

    def scan(self, pid, asset_id):
        rec = self.get(pid)
        if rec is None or rec.get("Status") != "OPEN":
            return None
        found = cast(list[str], rec["FoundIDs"])
        if asset_id in rec["ExpectedIDs"] and asset_id not in found:
            found.append(asset_id)
            self.store.update_where("PopisID", pid, {"Found": json.dumps(found)})
            return True
        if asset_id not in rec["ExpectedIDs"]:
            return False
        return True

    def finish(self, pid, doc_rel=""):
        rec = self.get(pid)
        if rec is None:
            return None
        missing = [a for a in rec["ExpectedIDs"] if a not in rec["FoundIDs"]]
        self.store.update_where(
            "PopisID", pid, {"Status": "CLOSED", "DocumentPath": doc_rel}
        )
        return {
            "expected": rec["ExpectedIDs"],
            "found": rec["FoundIDs"],
            "missing": missing,
        }
