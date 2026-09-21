"""One-shot CSV -> SQLite migration. Run once: python3 migrate.py"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from services.assignment_service import ASSIGN_COLS
from services.csv_service import CsvStore
from services.db_service import DbStore, table_counts
from services.disposal_service import DISPOSAL_COLS
from services.history_service import HISTORY_COLS
from services.repair_service import REPAIR_COLS
from services.replacement_service import REPLACE_COLS
from services.return_service import RETURN_COLS
from services.schemas import DEV_COLS, EMP_COLS

DB = os.path.join(config.DATA_DIR, "servicedesk.db")

JOBS = [
    ("employees", EMP_COLS, os.path.join(config.DATA_DIR, "Employees.csv")),
    ("devices", DEV_COLS, os.path.join(config.DATA_DIR, "Devices.csv")),
    (
        "assignments",
        ASSIGN_COLS,
        os.path.join(config.TRANSACTIONS_DIR, "Assignments.csv"),
    ),
    ("returns", RETURN_COLS, os.path.join(config.TRANSACTIONS_DIR, "Returns.csv")),
    (
        "replacements",
        REPLACE_COLS,
        os.path.join(config.TRANSACTIONS_DIR, "Replacements.csv"),
    ),
    ("repairs", REPAIR_COLS, os.path.join(config.TRANSACTIONS_DIR, "Repairs.csv")),
    (
        "disposals",
        DISPOSAL_COLS,
        os.path.join(config.TRANSACTIONS_DIR, "Disposals.csv"),
    ),
    ("history", HISTORY_COLS, os.path.join(config.TRANSACTIONS_DIR, "History.csv")),
]

if __name__ == "__main__":
    for table, cols, csv_path in JOBS:
        src = CsvStore(csv_path, cols) if os.path.exists(csv_path) else None
        rows = src.records() if src else []
        dst = DbStore(DB, table, cols)
        dst.replace_all(rows)
        print(f"{table}: {len(rows)} rows")
    print(table_counts(DB))
