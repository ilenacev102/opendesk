"""Read-only duplicate scan for identity columns (run before enabling indexes).

Usage:
    python3 scripts/check_duplicate_ids.py [--db data/servicedesk.db]

Exits 1 when duplicates exist so a deploy can stop before the unique indexes
are attempted. Never writes to the database.
"""

import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.db_service import IDENTITY_COLUMNS  # noqa: E402


def duplicates(db_path):
    """Yield (table, columns, id, count) for every duplicated identity."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        tables = {
            r[0]
            for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        for table, identities in sorted(IDENTITY_COLUMNS.items()):
            if table not in tables:
                continue
            for cols in identities:
                cond = " AND ".join(f"\"{c}\" <> ''" for c in cols)
                group = ", ".join(f'"{c}"' for c in cols)
                rows = con.execute(
                    f'SELECT {group}, COUNT(*) FROM "{table}" '
                    f"WHERE {cond} GROUP BY {group} HAVING COUNT(*) > 1"
                ).fetchall()
                for row in rows:
                    yield table, cols, row[:-1], row[-1]
    finally:
        con.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        default=os.path.join("data", "servicedesk.db"),
        help="SQLite database path (read-only)",
    )
    args = parser.parse_args(argv)
    if not os.path.exists(args.db):
        print(f"нема база: {args.db}")
        return 0

    found = 0
    for table, cols, key, count in duplicates(args.db):
        found += 1
        print(f"{table} {'+'.join(cols)} = {key} -> {count} реда")
    if found:
        print(f"најдени {found} дупликати — исчисти ги пред миграција")
        return 1
    print("нема дупликати")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
