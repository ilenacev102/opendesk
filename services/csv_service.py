"""Thread-safe CSV storage: read -> validate -> tmp write -> verify -> replace."""

import fcntl
import logging
import os
import tempfile
from typing import Any, cast

import pandas as pd

log = logging.getLogger("servicedesk.csv")


class CsvStore:
    def __init__(self, path, columns):
        self.path = path
        self.columns = columns
        if not os.path.exists(path):
            pd.DataFrame(columns=columns).to_csv(path, index=False)

    def read(self):
        with open(self.path, "a+"):
            pass
        with open(self.path, "r", encoding="utf-8-sig") as fh:
            try:
                fcntl.flock(fh, fcntl.LOCK_SH)
                df = pd.read_csv(fh, dtype=str).fillna("")
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)
        for col in self.columns:
            if col not in df.columns:
                df[col] = ""
        return df[self.columns]

    def write(self, df):
        df = df[self.columns].fillna("")
        directory = os.path.dirname(self.path) or "."
        fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
        os.close(fd)
        try:
            with open(self.path, "r+", encoding="utf-8") as lockfh:
                fcntl.flock(lockfh, fcntl.LOCK_EX)
                try:
                    df.to_csv(tmp, index=False)
                    check = pd.read_csv(tmp, dtype=str).fillna("")
                    if list(check.columns) != self.columns:
                        raise ValueError("column mismatch after write")
                    os.replace(tmp, self.path)
                finally:
                    fcntl.flock(lockfh, fcntl.LOCK_UN)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

    def records(self):
        df = self.read()
        cols = list(df.columns)
        out = []
        for _, row in df.iterrows():
            raw = cast(dict[str, Any], row.to_dict())
            out.append({c: ("" if pd.isna(raw[c]) else str(raw[c])) for c in cols})
        return out

    def find(self, col, value):
        for rec in self.records():
            if rec.get(col) == value:
                return rec
        return None

    def filter_eq(self, col, value):
        return [r for r in self.records() if r.get(col) == value]

    def update_where(self, col, value, updates):
        df = self.read()
        cols = list(df.columns)
        changed = 0
        for i, row in df.iterrows():
            raw = cast(dict[str, Any], row.to_dict())
            cell = "" if pd.isna(raw[col]) else str(raw[col])
            if cell == value:
                for key, val in updates.items():
                    if key in cols:
                        df.at[i, key] = val
                changed += 1
        self.write(df)
        return changed

    def append_row(self, row):
        df = self.read()
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
        self.write(df)
        return row
