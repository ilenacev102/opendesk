"""ID generation + backup helpers."""

import datetime
import os
import shutil
import sqlite3
import tempfile

import config


def next_id(store, col, prefix, width=6):
    fn = getattr(store, "max_suffix", None)
    if callable(fn):
        try:
            from collections.abc import Callable
            from typing import Any, cast

            raw: Any = cast(Callable[..., Any], fn)(col, prefix)
            best_val: int = int(raw)
            return f"{prefix}{best_val + 1:0{width}d}"
        except Exception:
            pass
    best = 0
    for rec in store.records():
        val = rec.get(col, "")
        if val.startswith(prefix):
            try:
                best = max(best, int(val[len(prefix) :]))
            except ValueError:
                continue
    return f"{prefix}{best + 1:0{width}d}"


def next_id_in(store, col, prefix, con, width=6):
    """Mint next ID on an open transaction connection.

    Must be called inside db_transaction (BEGIN IMMEDIATE holds the write
    lock), so concurrent callers serialize and never mint duplicates.
    Falls back to next_id for stores without con-aware max lookup.
    """
    fn = getattr(store, "max_suffix_con", None)
    if callable(fn):
        best = int(fn(col, prefix, con))
        return f"{prefix}{best + 1:0{width}d}"
    return next_id(store, col, prefix, width)


def stamp():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def backup_all(stores):
    """Create recoverable daily snapshots for CSV files and SQLite databases."""
    day = datetime.date.today().isoformat()
    dest = os.path.join(config.BACKUP_DIR, day)
    os.makedirs(dest, exist_ok=True)
    seen = set()
    for store in stores:
        src = getattr(store, "path", None)
        if src and os.path.exists(src) and src not in seen:
            seen.add(src)
            target = os.path.join(dest, os.path.basename(src))
            if src.lower().endswith((".db", ".sqlite", ".sqlite3")):
                # Copying only the main file loses writes still present in -wal.
                # SQLite's backup API reads a consistent view of the live database.
                fd, tmp_target = tempfile.mkstemp(
                    dir=dest,
                    prefix=f".{os.path.basename(src)}.",
                    suffix=".tmp",
                )
                os.close(fd)
                try:
                    with sqlite3.connect(src) as source, sqlite3.connect(
                        tmp_target
                    ) as snapshot:
                        source.execute("PRAGMA busy_timeout=5000")
                        source.backup(snapshot)
                    os.replace(tmp_target, target)
                finally:
                    if os.path.exists(tmp_target):
                        os.unlink(tmp_target)
            else:
                shutil.copy2(src, target)
    try:
        entries = sorted(
            d
            for d in os.listdir(config.BACKUP_DIR)
            if os.path.isdir(os.path.join(config.BACKUP_DIR, d))
        )
        for old in entries[:-7]:
            shutil.rmtree(os.path.join(config.BACKUP_DIR, old), ignore_errors=True)
    except OSError:
        pass
