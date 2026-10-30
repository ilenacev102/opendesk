"""SQLite → Postgres mover (offline copy with dry-run and verification)."""

from collections.abc import Mapping
from typing import Any


class MoverError(Exception):
    """Raised when a table cannot be read, copied, or verified."""


def _table_name(store: Any, fallback: str) -> str:
    return str(getattr(store, "table", fallback))


def move_table(src: Any, dst: Any, dry_run: bool = False) -> dict[str, int]:
    """Copy all rows from src store to dst store.

    Args:
        src: Source store with ``records()``.
        dst: Target store with ``records()`` and ``append_row(row)``.
        dry_run: When True, read both sides but write nothing.

    Returns:
        Dict with ``source``/``target``/``copied`` counts.

    Raises:
        MoverError: If either side is unreachable or a row fails to copy.
    """
    try:
        src_rows = list(src.records())
    except Exception as exc:
        raise MoverError(f"cannot read source {_table_name(src, '?')}: {exc}") from exc
    try:
        target_before = len(list(dst.records()))
    except Exception as exc:
        raise MoverError(f"cannot reach target {_table_name(dst, '?')}: {exc}") from exc

    if dry_run:
        return {"source": len(src_rows), "target": target_before, "copied": 0}

    copied = 0
    for row in src_rows:
        try:
            dst.append_row(dict(row))
            copied += 1
        except Exception as exc:
            raise MoverError(f"copy failed for {_table_name(dst, '?')}: {exc}") from exc

    try:
        target_after = len(list(dst.records()))
    except Exception as exc:
        raise MoverError(
            f"cannot verify target {_table_name(dst, '?')}: {exc}"
        ) from exc
    return {"source": len(src_rows), "target": target_after, "copied": copied}


def move_all(
    mapping: Mapping[str, tuple[Any, Any]], dry_run: bool = False
) -> dict[str, dict[str, int]]:
    """Copy every table in mapping.

    Args:
        mapping: ``{table_name: (src_store, dst_store)}``.
        dry_run: When True, count only, write nothing.

    Returns:
        ``{table_name: {"source": n, "target": m, "copied": k}}``.

    Raises:
        MoverError: On the first table that fails.
    """
    report: dict[str, dict[str, int]] = {}
    for table, (src, dst) in mapping.items():
        try:
            report[table] = move_table(src, dst, dry_run=dry_run)
        except MoverError:
            raise
        except Exception as exc:
            raise MoverError(f"copy failed for {table}: {exc}") from exc
    return report


def verify_all(mapping: Mapping[str, tuple[Any, Any]]) -> dict[str, bool]:
    """Verify source and target row counts match per table.

    Args:
        mapping: ``{table_name: (src_store, dst_store)}``.

    Returns:
        ``{table_name: True/False}``.

    Raises:
        MoverError: If any side cannot be read.
    """
    result: dict[str, bool] = {}
    for table, (src, dst) in mapping.items():
        try:
            result[table] = len(list(src.records())) == len(list(dst.records()))
        except Exception as exc:
            raise MoverError(f"verify failed for {table}: {exc}") from exc
    return result
