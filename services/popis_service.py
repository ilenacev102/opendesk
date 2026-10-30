"""Popis (stocktaking): session with expected vs scanned assets."""

import datetime as _dt
import json
from typing import cast

from services.db_service import open_store
from utils.helpers import next_id_in, stamp

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
        db_path = self.db_path
        from services.db_service import db_transaction

        with db_transaction(db_path) as con:
            row["PopisID"] = next_id_in(self.store, "PopisID", "P", con)
            self.store.append_row(row, con=con)
        return row["PopisID"]

    def get(self, pid):
        rec = self.store.find("PopisID", pid)
        if rec is None:
            return None
        rec["ExpectedIDs"] = cast(list[str], json.loads(rec.get("Expected") or "[]"))
        rec["FoundIDs"] = cast(list[str], json.loads(rec.get("Found") or "[]"))
        return rec

    def scan(self, pid, asset_id):
        from services.db_service import db_transaction

        with db_transaction(self.db_path) as con:
            rec = self.get(pid)
            if rec is None or rec.get("Status") != "OPEN":
                return None
            found = cast(list[str], rec["FoundIDs"])
            if asset_id in rec["ExpectedIDs"] and asset_id not in found:
                found.append(asset_id)
                self.store.update_where(
                    "PopisID", pid, {"Found": json.dumps(found)}, con=con
                )
                return True
            if asset_id not in rec["ExpectedIDs"]:
                return False
            return True

    def finish(self, pid, doc_rel=""):
        from services.db_service import db_transaction

        with db_transaction(self.db_path) as con:
            rec = self.get(pid)
            if rec is None:
                return None
            missing = [a for a in rec["ExpectedIDs"] if a not in rec["FoundIDs"]]
            self.store.update_where(
                "PopisID",
                pid,
                {"Status": "CLOSED", "DocumentPath": doc_rel},
                con=con,
            )
            return {
                "expected": rec["ExpectedIDs"],
                "found": rec["FoundIDs"],
                "missing": missing,
            }


AUDIT_INTERVAL_DAYS = 30


def _today(today=None) -> _dt.date:
    if today is None:
        return _dt.date.today()
    if isinstance(today, _dt.date):
        return today
    return _dt.date.fromisoformat(str(today)[:10])


def mark_scanned(devices, asset_id: str, today=None) -> str:
    """Stamp NextAuditDate = today + 30 days after a successful scan."""
    from utils.validators import require_device

    asset_id = (asset_id or "").strip()
    require_device(devices, asset_id)
    due = (_today(today) + _dt.timedelta(days=AUDIT_INTERVAL_DAYS)).isoformat()
    devices.update_where("AssetID", asset_id, {"NextAuditDate": due})
    return due


def missing(devices, today=None):
    """Devices with a set NextAuditDate older than today (provable laggards)."""
    day = _today(today)
    out = []
    for dev in devices.records():
        raw = (dev.get("NextAuditDate", "") or "").strip()[:10]
        if not raw:
            continue
        try:
            if _dt.date.fromisoformat(raw) < day:
                out.append(dev)
        except ValueError:
            continue
    return out
