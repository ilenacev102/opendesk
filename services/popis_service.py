"""Popis (stocktaking): session with expected vs scanned assets."""

import datetime as _dt
import json
from typing import cast

from services.db_service import open_store
from utils.helpers import next_id_in, stamp

from services.schemas import POPIS_COLS


class PopisService:
    def __init__(self, db_path, csv_path, history=None):
        self.db_path = db_path
        self.csv_path = csv_path
        self.store = open_store(db_path, "popis", csv_path, POPIS_COLS)
        self.history = history

    def _tx(self):
        from services.db_service import store_transaction

        return store_transaction(
            self.store,
            getattr(self.history, "store", None),
            fallback_path=self.db_path,
        )

    def _log(
        self, action, ref, old="", new="", notes="", performed_by="admin", con=None
    ):
        if self.history is None:
            return
        self.history.log(
            action, ref, old, new, "", "", notes, "", performed_by, "", con=con
        )

    def start(self, scope, name, expected_ids, performed_by="admin"):
        row = {
            "DateTime": stamp(),
            "Scope": scope,
            "Name": name,
            "Expected": json.dumps(expected_ids),
            "Found": json.dumps([]),
            "Status": "OPEN",
            "DocumentPath": "",
        }
        with self._tx() as con:
            row["PopisID"] = next_id_in(self.store, "PopisID", "P", con)
            self.store.append_row(row, con=con)
            self._log(
                "POPIS_START",
                row["PopisID"],
                "",
                "OPEN",
                f"{scope}: {name}",
                performed_by,
                con=con,
            )
        return row["PopisID"]

    def get(self, pid):
        rec = self.store.find("PopisID", pid)
        if rec is None:
            return None
        rec["ExpectedIDs"] = cast(list[str], json.loads(rec.get("Expected") or "[]"))
        rec["FoundIDs"] = cast(list[str], json.loads(rec.get("Found") or "[]"))
        return rec

    def scan(self, pid, asset_id, performed_by="admin"):
        with self._tx() as con:
            rec = self.get(pid)
            if rec is None or rec.get("Status") != "OPEN":
                return None
            found = cast(list[str], rec["FoundIDs"])
            if asset_id in rec["ExpectedIDs"] and asset_id not in found:
                found.append(asset_id)
                self.store.update_where(
                    "PopisID", pid, {"Found": json.dumps(found)}, con=con
                )
                self._log(
                    "POPIS_SCAN",
                    asset_id,
                    "",
                    "",
                    f"Попис {pid}",
                    performed_by,
                    con=con,
                )
                return True
            if asset_id not in rec["ExpectedIDs"]:
                return False
            return True

    def preview_finish(self, pid):
        """Read-only view of what finishing would do; never changes state."""
        rec = self.get(pid)
        if rec is None:
            return None
        missing = [a for a in rec["ExpectedIDs"] if a not in rec["FoundIDs"]]
        return {
            "expected": rec["ExpectedIDs"],
            "found": rec["FoundIDs"],
            "missing": missing,
        }

    def finish(self, pid, doc_rel="", performed_by="admin", devices=None):
        with self._tx() as con:
            result = self.preview_finish(pid)
            if result is None:
                return None
            self.store.update_where(
                "PopisID",
                pid,
                {"Status": "CLOSED", "DocumentPath": doc_rel},
                con=con,
            )
            self._log(
                "POPIS_CLOSE",
                pid,
                "OPEN",
                "CLOSED",
                f"недостасуваат {len(result['missing'])}",
                performed_by,
                con=con,
            )
            for aid in result["missing"]:
                dev = devices.find("AssetID", aid) if devices is not None else None
                self._log(
                    "POPIS_MISSING",
                    aid,
                    (dev or {}).get("Status", ""),
                    (dev or {}).get("Status", ""),
                    f"Попис {pid}",
                    performed_by,
                    con=con,
                )
            return result


AUDIT_INTERVAL_DAYS = 30


def _today(today=None) -> _dt.date:
    if today is None:
        return _dt.date.today()
    if isinstance(today, _dt.date):
        return today
    return _dt.date.fromisoformat(str(today)[:10])


def mark_scanned(
    devices, asset_id: str, today=None, *, history=None, performed_by="admin"
) -> str:
    """Stamp NextAuditDate = today + 30 days after a successful scan."""
    from services.db_service import store_transaction
    from utils.validators import require_device

    asset_id = (asset_id or "").strip()
    require_device(devices, asset_id)
    due = (_today(today) + _dt.timedelta(days=AUDIT_INTERVAL_DAYS)).isoformat()
    with store_transaction(devices, getattr(history, "store", None)) as con:
        devices.update_where("AssetID", asset_id, {"NextAuditDate": due}, con=con)
        if history is not None:
            history.log(
                "AUDIT_SCAN",
                asset_id,
                "",
                due,
                "",
                "",
                "Следен попис",
                "",
                performed_by,
                "",
                con=con,
            )
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
