"""Store protocol: the seam every record backend must satisfy.

DbStore implements this unchanged; a future Postgres backend implements the
same surface so routes and services never branch on backend type. Use
``check_store`` at wiring time to fail fast on incomplete backends.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class StoreProtocol(Protocol):
    @property
    def table(self) -> str: ...
    @property
    def columns(self) -> list[str]: ...

    def records(self) -> list[dict[str, str]]: ...
    def find(self, col, value): ...
    def filter_eq(self, col, value) -> list[dict[str, str]]: ...
    def recent(self, limit=20) -> list[dict[str, str]]: ...
    def update_where(self, col, value, updates, con=None): ...
    def append_row(self, row, con=None): ...
    def replace_all(self, rows) -> None: ...
    def max_suffix(self, col, prefix) -> int: ...
    def max_suffix_con(self, col, prefix, con) -> int: ...


def check_store(store) -> bool:
    """Return True when store satisfies StoreProtocol, else raise TypeError."""
    missing = [
        name
        for name in (
            "records",
            "find",
            "filter_eq",
            "recent",
            "update_where",
            "append_row",
            "replace_all",
            "max_suffix",
            "max_suffix_con",
        )
        if not callable(getattr(store, name, None))
    ]
    if missing:
        raise TypeError(
            f"Store {type(store).__name__} missing protocol methods: "
            + ", ".join(missing)
        )
    if not isinstance(store, StoreProtocol):
        raise TypeError(f"Store {type(store).__name__} does not satisfy StoreProtocol.")
    return True
