"""SQLite storage with CsvStore-compatible interface (drop-in swap)."""

import logging
import os
import sqlite3
from contextlib import contextmanager

log = logging.getLogger("servicedesk")

# One unique index per identity: either a single ID column or a natural key.
# Empty strings stay allowed so legacy rows without an ID never block startup.
IDENTITY_COLUMNS = {
    "devices": (("AssetID",),),
    "employees": (("EmployeeID",),),
    "history": (("HistoryID",),),
    "popis": (("PopisID",),),
    "incidents": (("IncidentID",),),
    "projects": (("ProjectID",),),
    "issue_types": (("TypeID",),),
    "consumables": (("ConsumableID",),),
    "licenses": (("LicenseID",),),
    "license_seats": (("SeatID",),),
    "field_defs": (("FieldID",),),
    "field_values": (("AssetID", "FieldID"),),
    "contracts": (("ContractID",),),
    "reservations": (("ReservationID",),),
    "requests": (("RequestID",),),
    "onboard": (("RequestID",),),
    "notifications": (("NotifID",),),
    "transit": (("TransitID",),),
    "ldapmap": (("UserName",),),
    "sla_policies": (("PolicyID",),),
    "macros": (("MacroID",),),
    "webhooks": (("WebhookID",),),
    "kb_articles": (("ArticleID",),),
    "comments": (("CommentID",),),
    "kb_links": (("ArticleID", "IncidentID"),),
    "kb_ratings": (("ArticleID", "UserName"),),
    "watchers": (("IncidentID", "UserName"),),
    "worklogs": (("WorklogID",),),
    "versions": (("VersionID",),),
    "sprints": (("SprintID",),),
    "racks": (("RackID",),),
    "rack_items": (("ItemID",),),
    "maintenance_schedules": (("ScheduleID",),),
    "problems": (("ProblemID",),),
    "changes": (("ChangeID",),),
    "cmdb_relations": (("RelID",),),
    "users": (("UserID",),),
    "api_tokens": (("TokenID",),),
}


def identity_columns(table):
    """Unique identity definitions for a table (empty when it has none)."""
    return IDENTITY_COLUMNS.get(table, ())


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
            for unique_cols in identity_columns(table):
                if not all(c in columns for c in unique_cols):
                    continue
                cond = " AND ".join(f"\"{c}\" <> ''" for c in unique_cols)
                idx_name = "uq_{}_{}".format(table, "_".join(unique_cols))
                cols_sql = ", ".join(f'"{c}"' for c in unique_cols)
                try:
                    con.execute(
                        f'CREATE UNIQUE INDEX IF NOT EXISTS "{idx_name}" '
                        f'ON "{table}"({cols_sql}) WHERE {cond}'
                    )
                except sqlite3.IntegrityError as exc:
                    log.warning(
                        "duplicate %s rows in %s; unique index skipped: %s",
                        unique_cols,
                        table,
                        exc,
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
            cur = con.execute(f'DELETE FROM "{self.table}" WHERE "{col}" = ?', (value,))
            return cur.rowcount
        with self._connect() as connection:
            cur = connection.execute(
                f'DELETE FROM "{self.table}" WHERE "{col}" = ?', (value,)
            )
            connection.commit()
            return cur.rowcount

    def update_where_all(self, conditions, updates, con=None):
        """Update rows matching every column/value in ``conditions``."""
        clean = {k: v for k, v in updates.items() if k in self.columns}
        where_cols = {k: v for k, v in conditions.items() if k in self.columns}
        if not clean or not where_cols:
            return 0
        stmt = ", ".join(f'"{k}" = ?' for k in clean)
        where = " AND ".join(f'"{k}" = ?' for k in where_cols)
        params = (*clean.values(), *where_cols.values())
        if con is not None:
            return con.execute(
                f'UPDATE "{self.table}" SET {stmt} WHERE {where}', params
            ).rowcount
        with self._connect() as connection:
            cur = connection.execute(
                f'UPDATE "{self.table}" SET {stmt} WHERE {where}', params
            )
            connection.commit()
            return cur.rowcount

    def delete_where_all(self, conditions, con=None):
        """Delete rows matching every column/value in ``conditions``.

        Targeted replacement for read-modify-write flows that used to rewrite
        whole tables (custom fields, watchers).
        """
        clean = {k: v for k, v in conditions.items() if k in self.columns}
        if not clean:
            return 0
        where = " AND ".join(f'"{k}" = ?' for k in clean)
        params = tuple(clean.values())
        if con is not None:
            return con.execute(
                f'DELETE FROM "{self.table}" WHERE {where}', params
            ).rowcount
        with self._connect() as connection:
            cur = connection.execute(
                f'DELETE FROM "{self.table}" WHERE {where}', params
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


@contextmanager
def store_transaction(*stores, fallback_path=None):
    """One write transaction spanning every given store.

    Backend-aware: SQLite stores share ``db_transaction``; Postgres stores
    share one psycopg2 connection. All stores must live in the same database,
    otherwise the write would silently escape the transaction.

    ``fallback_path`` keeps legacy callers that only know a db path working
    when the store exposes no backend attribute.
    """
    live = [s for s in stores if s is not None]
    if not live:
        if fallback_path:
            with db_transaction(fallback_path) as con:
                yield con
            return
        yield None
        return

    pg = [s for s in live if getattr(s, "dsn", None)]
    sqlite = [s for s in live if not getattr(s, "dsn", None)]

    if pg and sqlite:
        raise RuntimeError("Cannot mix Postgres and SQLite stores in one transaction.")
    if pg:
        dsns = {s.dsn for s in pg}
        if len(dsns) != 1:
            raise RuntimeError("All stores must share one Postgres DSN.")
        import psycopg2

        con = psycopg2.connect(dsns.pop())
        try:
            con.autocommit = False
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()
        return

    paths = {getattr(s, "db_path", None) for s in sqlite}
    paths.discard(None)
    if len(paths) > 1:
        raise RuntimeError("All stores must share one SQLite database file.")
    path = paths.pop() if paths else fallback_path
    if not path:
        yield None
        return
    with db_transaction(path) as con:
        yield con


def open_store(db_path, table, csv_path, cols):
    """PgStore when SERVICEDESK_DB_URL is set, else SQLite DbStore.

    csv_path is kept for migrate compatibility and ignored by both backends.
    """
    dsn = os.environ.get("SERVICEDESK_DB_URL", "").strip()
    if dsn:
        from services.pg_store import PgStore

        return PgStore(dsn, table, cols)
    return DbStore(db_path, table, cols)
