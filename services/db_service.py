"""SQLite storage with CsvStore-compatible interface (drop-in swap)."""

import os
import sqlite3


class DbStore:
    def __init__(self, db_path, table, columns):
        self.db_path = db_path
        self.path = db_path
        self.table = table
        self.columns = columns
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        cols = ", ".join(f'"{c}" TEXT DEFAULT ""' for c in columns)
        with sqlite3.connect(db_path) as con:
            # Establish the database-wide journal mode once. Repeating this on
            # every concurrent connection can contend for an exclusive lock.
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("PRAGMA busy_timeout=5000")
            con.execute(f'CREATE TABLE IF NOT EXISTS "{table}" ({cols})')
            existing = [r[1] for r in con.execute(f'PRAGMA table_info("{table}")')]
            for c in columns:
                if c not in existing:
                    con.execute(f'ALTER TABLE "{table}" ADD COLUMN "{c}" TEXT')
            # indexes for 1500-scale lookups: first col + common keys if present
            for idx_col in (
                "AssetID",
                "EmployeeID",
                "TransactionID",
                "HistoryID",
                "PopisID",
                "Status",
                "SerialNumber",
            ):
                if idx_col in columns:
                    con.execute(
                        f'CREATE INDEX IF NOT EXISTS "idx_{table}_{idx_col}" ON "{table}"("{idx_col}")'
                    )
            # Application checks are friendly, but these indexes are the final
            # guard when two requests race each other. Empty legacy fields stay valid.
            identity_columns = {
                "devices": ("AssetID",),
                "employees": ("EmployeeID",),
                "history": ("HistoryID",),
                "popis": ("PopisID",),
                "incidents": ("IncidentID",),
                "projects": ("ProjectID",),
                "issue_types": ("TypeID",),
            }.get(table, ("TransactionID",))
            for unique_col in identity_columns:
                if unique_col in columns:
                    con.execute(
                        f'CREATE UNIQUE INDEX IF NOT EXISTS "uq_{table}_{unique_col}" '
                        f'ON "{table}"("{unique_col}") WHERE "{unique_col}" <> ""'
                    )
            if table == "devices" and "SerialNumber" in columns:
                con.execute(
                    f'CREATE UNIQUE INDEX IF NOT EXISTS "uq_{table}_SerialNumber" '
                    f'ON "{table}"("SerialNumber") WHERE "SerialNumber" <> ""'
                )

    def _connect(self):
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA busy_timeout=5000")
        return con

    def records(self):
        with self._connect() as con:
            cols = ", ".join(f'"{c}"' for c in self.columns)
            rows = con.execute(f'SELECT {cols} FROM "{self.table}"').fetchall()
        return [
            {c: (r[c] if r[c] is not None else "") for c in self.columns} for r in rows
        ]

    def find(self, col, value):
        if col not in self.columns:
            return None
        with self._connect() as con:
            cols = ", ".join(f'"{c}"' for c in self.columns)
            row = con.execute(
                f'SELECT {cols} FROM "{self.table}" WHERE "{col}" = ? LIMIT 1',
                (value,),
            ).fetchone()
        if row is None:
            return None
        return {c: (row[c] if row[c] is not None else "") for c in self.columns}

    def filter_eq(self, col, value):
        if col not in self.columns:
            return []
        with self._connect() as con:
            cols = ", ".join(f'"{c}"' for c in self.columns)
            rows = con.execute(
                f'SELECT {cols} FROM "{self.table}" WHERE "{col}" = ?',
                (value,),
            ).fetchall()
        return [
            {c: (r[c] if r[c] is not None else "") for c in self.columns} for r in rows
        ]

    def recent(self, limit=20):
        with self._connect() as con:
            cols = ", ".join(f'"{c}"' for c in self.columns)
            rows = con.execute(
                f'SELECT {cols} FROM "{self.table}" ORDER BY rowid DESC LIMIT ?',
                (limit,),
            ).fetchall()
        return [
            {c: (r[c] if r[c] is not None else "") for c in self.columns} for r in rows
        ]

    def update_where(self, col, value, updates, con=None):
        clean = {k: v for k, v in updates.items() if k in self.columns}
        if not clean:
            return 0
        stmt = ", ".join(f'"{k}" = ?' for k in clean)
        if con is not None:
            cur = con.execute(
                f'UPDATE "{self.table}" SET {stmt} WHERE "{col}" = ?',
                (*clean.values(), value),
            )
            return cur.rowcount
        with self._connect() as connection:
            cur = connection.execute(
                f'UPDATE "{self.table}" SET {stmt} WHERE "{col}" = ?',
                (*clean.values(), value),
            )
            connection.commit()
            return cur.rowcount

    def append_row(self, row, con=None):
        data = {c: str(row.get(c, "")) for c in self.columns}
        cols = ", ".join(f'"{c}"' for c in self.columns)
        marks = ", ".join("?" for _ in self.columns)
        if con is not None:
            con.execute(
                f'INSERT INTO "{self.table}" ({cols}) VALUES ({marks})',
                [data[c] for c in self.columns],
            )
            return data
        with self._connect() as connection:
            connection.execute(
                f'INSERT INTO "{self.table}" ({cols}) VALUES ({marks})',
                [data[c] for c in self.columns],
            )
            connection.commit()
        return data

    def delete_where(self, col, value, con=None):
        if col not in self.columns:
            return 0
        if con is not None:
            cur = con.execute(
                f'DELETE FROM "{self.table}" WHERE "{col}" = ?', (value,)
            )
            return cur.rowcount
        with self._connect() as connection:
            cur = connection.execute(
                f'DELETE FROM "{self.table}" WHERE "{col}" = ?', (value,)
            )
            connection.commit()
            return cur.rowcount

    def replace_all(self, rows):
        with self._connect() as con:
            con.execute(f'DELETE FROM "{self.table}"')
            cols = ", ".join(f'"{c}"' for c in self.columns)
            marks = ", ".join("?" for _ in self.columns)
            con.executemany(
                f'INSERT INTO "{self.table}" ({cols}) VALUES ({marks})',
                [[str(r.get(c, "")) for c in self.columns] for r in rows],
            )
            con.commit()

    def max_suffix(self, col, prefix):
        if col not in self.columns:
            return 0
        with self._connect() as con:
            rows = con.execute(
                f'SELECT "{col}" FROM "{self.table}" WHERE "{col}" LIKE ?',
                (prefix + "%",),
            ).fetchall()
        best = 0
        for (val,) in rows:
            if val and val.startswith(prefix):
                try:
                    best = max(best, int(val[len(prefix) :]))
                except (ValueError, TypeError):
                    continue
        return best

    def max_suffix_con(self, col, prefix, con):
        """Same as max_suffix but on an open transaction connection (race-safe)."""
        if col not in self.columns:
            return 0
        rows = con.execute(
            f'SELECT "{col}" FROM "{self.table}" WHERE "{col}" LIKE ?',
            (prefix + "%",),
        ).fetchall()
        best = 0
        for (val,) in rows:
            if val and val.startswith(prefix):
                try:
                    best = max(best, int(val[len(prefix) :]))
                except (ValueError, TypeError):
                    continue
        return best


def table_counts(db_path):
    with sqlite3.connect(db_path) as con:
        tables = [
            r[0]
            for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        ]
        return {
            t: con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables
        }


from contextlib import contextmanager


@contextmanager
def db_transaction(db_path):
    """Context manager executing multiple operations in a single SQLite transaction."""
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=5000")
    try:
        con.execute("BEGIN IMMEDIATE TRANSACTION")
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def open_store(db_path, table, csv_path, cols):
    """PgStore when SERVICEDESK_DB_URL is set, else SQLite DbStore.

    csv_path is kept for migrate compatibility and ignored by both backends.
    """
    dsn = os.environ.get("SERVICEDESK_DB_URL", "").strip()
    if dsn:
        from services.pg_store import PgStore

        return PgStore(dsn, table, cols)
    return DbStore(db_path, table, cols)
