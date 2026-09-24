"""Discovery import: Intune/SCCM CSV normalize + reconcile + confirm.

Flow: parse (validate, no writes) -> reconcile (verdict per row, no writes)
-> confirm (transactional writes for new/match only).
Assigned devices and mismatched identity fields are never auto-overwritten.
"""

import io

import pandas as pd

from services.db_service import db_transaction
from utils.helpers import next_id_in

DISCOVERY_COLUMNS = [
    "Hostname",
    "SerialNumber",
    "Manufacturer",
    "Model",
    "OS",
    "LastSeen",
    "Source",
]

NEW, MATCH, CONFLICT = "new", "match", "conflict"


def normalize_serial(raw) -> str:
    """Canonical serial form: stripped + upper-case (empty stays empty)."""
    return str(raw or "").strip().upper()


def parse_discovery_csv(data: bytes):
    """Parse and normalize discovery CSV bytes. Raises ValueError, writes nothing."""
    try:
        df = pd.read_csv(io.BytesIO(data), dtype=str).fillna("")
    except Exception as exc:
        raise ValueError(f"Невалиден CSV: {exc}")
    if "SerialNumber" not in df.columns:
        raise ValueError("Недостасува колона: SerialNumber.")
    rows = []
    for _, raw in df.iterrows():
        row = {
            c: str(raw[c]).strip() if c in df.columns else "" for c in DISCOVERY_COLUMNS
        }
        row["SerialNumber"] = normalize_serial(row["SerialNumber"])
        rows.append(row)
    seen, dupes = set(), set()
    for row in rows:
        sn = row["SerialNumber"]
        if not sn:
            continue
        if sn in seen:
            dupes.add(sn)
        seen.add(sn)
    if dupes:
        raise ValueError(f"Дупли сериски во фајлот: {sorted(dupes)}")
    return rows


def reconcile(rows, devices):
    """Attach verdict (new/match/conflict) + reason to each row. No writes."""
    by_serial = {}
    for dev in devices.records():
        sn = normalize_serial(dev.get("SerialNumber", ""))
        if sn:
            by_serial[sn] = dev
    out = []
    for row in rows:
        verdict, reason = NEW, ""
        sn = row["SerialNumber"]
        dev = by_serial.get(sn)
        if not sn:
            verdict, reason = CONFLICT, "Празен сериски број."
        elif dev is None:
            verdict = NEW
        elif (dev.get("EmployeeID") or "").strip():
            verdict, reason = CONFLICT, "Уредот е задолжен — нема автоматска измена."
        else:
            mismatch = [
                label
                for label, key in (("производител", "Manufacturer"), ("модел", "Model"))
                if row.get(key)
                and (dev.get(key) or "").strip()
                and row[key].lower() != (dev.get(key) or "").strip().lower()
            ]
            if mismatch:
                verdict, reason = CONFLICT, f"Разлика во {', '.join(mismatch)}."
            else:
                verdict = MATCH
                reason = f"Постоечки уред {dev.get('AssetID', '')}."
        out.append({**row, "verdict": verdict, "reason": reason})
    return out


def _mint_asset_id(devices, con):
    return next_id_in(devices, "AssetID", "AST", con, width=3)


def confirm(rows, devices, staging, history, performed_by="admin", db_path=None):
    """Write new devices + LastSeen notes for matches in one transaction.

    Returns {"new": n, "updated": n, "skipped": n}. Conflicts are skipped.
    """
    counts = {"new": 0, "updated": 0, "skipped": 0}

    def _apply(con):
        for row in rows:
            verdict = row.get("verdict", NEW)
            if verdict == CONFLICT:
                counts["skipped"] += 1
                continue
            if verdict == MATCH:
                dev = None
                for cand in devices.records():
                    if (
                        normalize_serial(cand.get("SerialNumber", ""))
                        == row["SerialNumber"]
                    ):
                        dev = cand
                        break
                if dev is None:
                    counts["skipped"] += 1
                    continue
                note = (dev.get("Notes") or "").strip()
                seen_mark = f"[seen {row['LastSeen']} {row['Source']}]".strip()
                if row["LastSeen"] and seen_mark not in note:
                    note = f"{note} {seen_mark}".strip()
                    devices.update_where(
                        "AssetID", dev["AssetID"], {"Notes": note}, con=con
                    )
                _stage(row, staging, con)
                history.log(
                    "DISCOVERY_UPDATE",
                    dev["AssetID"],
                    dev.get("Status", ""),
                    dev.get("Status", ""),
                    dev.get("EmployeeID", ""),
                    "",
                    f"Discovery {row['Source']} {row['LastSeen']}".strip(),
                    "",
                    performed_by,
                    "",
                    con=con,
                )
                counts["updated"] += 1
            else:
                aid = _mint_asset_id(devices, con)
                devices.append_row(
                    {
                        "AssetID": aid,
                        "Type": "Друго",
                        "Manufacturer": row["Manufacturer"],
                        "Model": row["Model"],
                        "SerialNumber": row["SerialNumber"],
                        "Status": "Available",
                        "EmployeeID": "",
                        "Location": "",
                        "PurchaseDate": "",
                        "WarrantyUntil": "",
                        "PurchasePrice": "",
                        "Supplier": "",
                        "Notes": f"Discovery {row['Source']} {row['LastSeen']}".strip(),
                    },
                    con=con,
                )
                _stage(row, staging, con)
                history.log(
                    "DISCOVERY_NEW",
                    aid,
                    "",
                    "Available",
                    "",
                    "",
                    f"Discovery {row['Source']} {row['Hostname']}".strip(),
                    "",
                    performed_by,
                    "",
                    con=con,
                )
                counts["new"] += 1
        history.log(
            "DISCOVERY_IMPORT",
            "",
            "",
            "",
            "",
            "",
            f"new={counts['new']} updated={counts['updated']} "
            f"skipped={counts['skipped']}",
            "",
            performed_by,
            "",
            con=con,
        )

    if db_path:
        with db_transaction(db_path) as con:
            _apply(con)
    else:
        _apply(None)
    return counts


def _stage(row, staging, con):
    data = {c: row.get(c, "") for c in DISCOVERY_COLUMNS}
    changed = staging.update_where("SerialNumber", row["SerialNumber"], data, con=con)
    if not changed:
        staging.append_row(data, con=con)
