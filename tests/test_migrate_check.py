"""Enterprise Wave2 todo 16: migration dry-check on legacy fixture."""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _legacy_db(path):
    con = sqlite3.connect(path)
    con.execute(
        'CREATE TABLE "devices" ("AssetID" TEXT, "Type" TEXT, '
        '"Manufacturer" TEXT, "Model" TEXT, "SerialNumber" TEXT, '
        '"Status" TEXT, "EmployeeID" TEXT, "Location" TEXT, '
        '"PurchaseDate" TEXT)'
    )
    con.executemany(
        'INSERT INTO "devices" VALUES (?,?,?,?,?,?,?,?,?)',
        [
            (
                f"AST{i:03d}",
                "Лаптоп",
                "Dell",
                "L5440",
                f"SN{i:03d}",
                "Available",
                "",
                "Скопје",
                "2024-01-01",
            )
            for i in range(1, 51)
        ],
    )
    con.execute(
        'CREATE TABLE "employees" ("EmployeeID" TEXT, "FirstName" TEXT, '
        '"LastName" TEXT, "UserName" TEXT, "Email" TEXT, "Department" TEXT)'
    )
    con.executemany(
        'INSERT INTO "employees" VALUES (?,?,?,?,?,?)',
        [
            (
                f"E{i:03d}",
                f"Име{i}",
                f"Презиме{i}",
                f"user{i}",
                f"user{i}@firma.mk",
                "IT",
            )
            for i in range(1, 11)
        ],
    )
    con.execute(
        'CREATE TABLE "history" ("HistoryID" TEXT, "DateTime" TEXT, '
        '"Action" TEXT, "AssetID" TEXT, "OldStatus" TEXT, "NewStatus" TEXT, '
        '"EmployeeID" TEXT, "EmployeeName" TEXT)'
    )
    con.executemany(
        'INSERT INTO "history" VALUES (?,?,?,?,?,?,?,?)',
        [
            (
                f"H{i:06d}",
                "2024-01-01 10:00",
                "ASSIGN",
                "AST001",
                "Available",
                "Assigned",
                "E001",
                "Име1",
            )
            for i in range(1, 31)
        ],
    )
    con.commit()
    con.close()


def test_legacy_migration_preserves_counts(tmp_path):
    from services.db_service import DbStore, table_counts
    from services.schemas import DEV_COLS, EMP_COLS

    db = os.path.join(str(tmp_path), "legacy.db")
    _legacy_db(db)
    devices = DbStore(db, "devices", DEV_COLS)
    employees = DbStore(db, "employees", EMP_COLS)
    from services.history_service import HISTORY_COLS
    from services.schemas import INCIDENT_COLS, LDAPMAP_COLS, STAGING_COLS

    history = DbStore(db, "history", HISTORY_COLS)
    DbStore(db, "incidents", INCIDENT_COLS)
    DbStore(db, "staging", STAGING_COLS)
    DbStore(db, "ldapmap", LDAPMAP_COLS)
    counts = table_counts(db)
    assert counts["devices"] == 50
    assert counts["employees"] == 10
    assert counts["history"] == 30
    assert counts["incidents"] == 0
    assert counts["staging"] == 0
    assert counts["ldapmap"] == 0
    dev = devices.find("AssetID", "AST001")
    assert dev is not None
    assert dev.get("Manufacturer") == "Dell"
    assert dev.get("PurchasePrice") == ""  # added column, empty default
    assert dev.get("Supplier") == ""
    emp = employees.find("EmployeeID", "E001")
    assert emp is not None
    assert emp.get("Active") == ""
    assert emp.get("Organization") == ""


def test_new_tables_created_empty(tmp_path):
    from services.db_service import DbStore
    from services.schemas import INCIDENT_COLS, LDAPMAP_COLS, STAGING_COLS

    db = os.path.join(str(tmp_path), "legacy.db")
    _legacy_db(db)
    assert DbStore(db, "incidents", INCIDENT_COLS).records() == []
    assert DbStore(db, "staging", STAGING_COLS).records() == []
    assert DbStore(db, "ldapmap", LDAPMAP_COLS).records() == []


def test_injected_failure_rolls_back(tmp_path):
    from services.db_service import DbStore, db_transaction
    from services.schemas import DEV_COLS

    db = os.path.join(str(tmp_path), "legacy.db")
    _legacy_db(db)
    devices = DbStore(db, "devices", DEV_COLS)
    before = len(devices.records())
    try:
        with db_transaction(db) as con:
            devices.append_row({"AssetID": "TMP001"}, con=con)
            raise RuntimeError("injected failure")
    except RuntimeError:
        pass
    assert len(devices.records()) == before
    assert devices.find("AssetID", "TMP001") is None


def test_live_data_dir_untouched(tmp_path):
    import config as config_mod
    from services.db_service import DbStore
    from services.schemas import DEV_COLS

    live_before = sorted(os.listdir(config_mod.DATA_DIR))
    db = os.path.join(str(tmp_path), "legacy.db")
    _legacy_db(db)
    assert os.path.commonpath([db, config_mod.DATA_DIR]) != config_mod.DATA_DIR
    DbStore(db, "devices", DEV_COLS)
    live_after = sorted(os.listdir(config_mod.DATA_DIR))
    assert live_before == live_after
