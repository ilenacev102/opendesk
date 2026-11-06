"""Postgres record backend implementing the StoreProtocol surface.

Selected only when SERVICEDESK_DB_URL is set (see open_store); otherwise the
app stays on SQLite. Schema mirrors DbStore: TEXT columns, partial unique
indexes that ignore empty strings, first-column lookup indexes.
"""

IDENTITY_COLUMNS = {
    "devices": ("AssetID",),
    "employees": ("EmployeeID",),
    "history": ("HistoryID",),
    "popis": ("PopisID",),
    "incidents": ("IncidentID",),
}


def _identity(table):
    return IDENTITY_COLUMNS.get(table, ("TransactionID",))


class PgStore:
    def __init__(self, dsn, table, columns):
        import psycopg2

        self.dsn = dsn
        self.table = table
        self.columns = list(columns)
        con = psycopg2.connect(dsn)
        try:
            con.autocommit = True
            with con.cursor() as cur:
                cols = ", ".join(f"\"{c}\" TEXT DEFAULT ''''" for c in self.columns)
                cur.execute(f'CREATE TABLE IF NOT EXISTS "{table}" ({cols})')
                for c in self.columns:
                    cur.execute(
                        f'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS "{c}" TEXT'
                    )
                for idx_col in (
                    "AssetID",
                    "EmployeeID",
                    "TransactionID",
                    "HistoryID",
                    "PopisID",
                    "Status",
                    "SerialNumber",
                ):
                    if idx_col in self.columns:
                        cur.execute(
                            f'CREATE INDEX IF NOT EXISTS "idx_{table}_{idx_col}" '
                            f'ON "{table}"("{idx_col}")'
                        )
                for unique_col in _identity(table):
                    if unique_col in self.columns:
                        cur.execute(
                            f'CREATE UNIQUE INDEX IF NOT EXISTS "uq_{table}_{unique_col}" '
                            f'ON "{table}"("{unique_col}") '
                            f"WHERE \"{unique_col}\" <> ''"
                        )
                if table == "devices" and "SerialNumber" in self.columns:
                    cur.execute(
                        f'CREATE UNIQUE INDEX IF NOT EXISTS "uq_{table}_SerialNumber" '
                        f'ON "{table}"("SerialNumber") WHERE "SerialNumber" <> \'\''
                    )
        finally:
            con.close()

    def _connect(self):
        import psycopg2

        return psycopg2.connect(self.dsn)

    def _rows(self, cur):
        cols = cur.description and [d[0] for d in cur.description] or []
        out = []
        for r in cur.fetchall():
            row = dict(zip(cols, r))
            out.append(
                {
                    c: (row.get(c) if row.get(c) is not None else "")
                    for c in self.columns
                }
            )
        return out

    def _cols_sql(self):
        return ", ".join(f'"{c}"' for c in self.columns)

    def records(self):
        con = self._connect()
        try:
            with con.cursor() as cur:
                cur.execute(f'SELECT {self._cols_sql()} FROM "{self.table}"')
                return self._rows(cur)
        finally:
            con.close()

    def find(self, col, value):
        if col not in self.columns:
            return None
        con = self._connect()
        try:
            with con.cursor() as cur:
                cur.execute(
                    f'SELECT {self._cols_sql()} FROM "{self.table}" '
                    f'WHERE "{col}" = %s LIMIT 1',
                    (value,),
                )
                rows = self._rows(cur)
        finally:
            con.close()
        return rows[0] if rows else None

    def filter_eq(self, col, value):
        if col not in self.columns:
            return []
        con = self._connect()
        try:
            with con.cursor() as cur:
                cur.execute(
                    f'SELECT {self._cols_sql()} FROM "{self.table}" WHERE "{col}" = %s',
                    (value,),
                )
                return self._rows(cur)
        finally:
            con.close()

    def recent(self, limit=20):
        con = self._connect()
        try:
            with con.cursor() as cur:
                cur.execute(
                    f'SELECT {self._cols_sql()} FROM "{self.table}" '
                    f"ORDER BY ctid DESC LIMIT %s",
                    (limit,),
                )
                return self._rows(cur)
        finally:
            con.close()

    def update_where(self, col, value, updates, con=None):
        clean = {k: v for k, v in updates.items() if k in self.columns}
        if not clean:
            return 0
        stmt = ", ".join(f'"{k}" = %s' for k in clean)
        own = con is None
        if own:
            con = self._connect()
        try:
            with con.cursor() as cur:
                cur.execute(
                    f'UPDATE "{self.table}" SET {stmt} WHERE "{col}" = %s',
                    (*clean.values(), value),
                )
                count = cur.rowcount
            if own:
                con.commit()
            return count
        finally:
            if own:
                con.close()

    def append_row(self, row, con=None):
        data = {c: str(row.get(c, "")) for c in self.columns}
        cols = self._cols_sql()
        marks = ", ".join("%s" for _ in self.columns)
        own = con is None
        if own:
            con = self._connect()
        try:
            with con.cursor() as cur:
                cur.execute(
                    f'INSERT INTO "{self.table}" ({cols}) VALUES ({marks})',
                    [data[c] for c in self.columns],
                )
            if own:
                con.commit()
            return data
        finally:
            if own:
                con.close()

    def delete_where(self, col, value, con=None):
        if col not in self.columns:
            return 0
        own = con is None
        con = self._connect() if own else con
        try:
            with con.cursor() as cur:
                cur.execute(
                    f'DELETE FROM "{self.table}" WHERE "{col}" = %s', (value,)
                )
                cnt = cur.rowcount
            if own:
                con.commit()
            return cnt
        finally:
            if own:
                con.close()

    def replace_all(self, rows):
        con = self._connect()
        try:
            with con.cursor() as cur:
                cur.execute(f'DELETE FROM "{self.table}"')
                cols = self._cols_sql()
                marks = ", ".join("%s" for _ in self.columns)
                cur.executemany(
                    f'INSERT INTO "{self.table}" ({cols}) VALUES ({marks})',
                    [[str(r.get(c, "")) for c in self.columns] for r in rows],
                )
            con.commit()
        finally:
            con.close()

    def max_suffix(self, col, prefix):
        if col not in self.columns:
            return 0
        con = self._connect()
        try:
            return self.max_suffix_con(col, prefix, con)
        finally:
            con.close()

    def max_suffix_con(self, col, prefix, con):
        if col not in self.columns:
            return 0
        with con.cursor() as cur:
            cur.execute(
                f'SELECT "{col}" FROM "{self.table}" WHERE "{col}" LIKE %s',
                (prefix + "%",),
            )
            vals = [r[0] for r in cur.fetchall()]
        best = 0
        for val in vals:
            if val and val.startswith(prefix):
                try:
                    best = max(best, int(val[len(prefix) :]))
                except (ValueError, TypeError):
                    continue
        return best
