"""P2.8: every column list lives in services/schemas.py (documented invariant)."""

import importlib
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent

CONSOLIDATED = [
    ("USER_COLS", "services.auth_service"),
    ("TOKEN_COLS", "services.api_token_service"),
    ("HISTORY_COLS", "services.history_service"),
    ("POPIS_COLS", "services.popis_service"),
    ("ASSIGN_COLS", "services.assignment_service"),
    ("REPAIR_COLS", "services.repair_service"),
    ("RETURN_COLS", "services.return_service"),
    ("REPLACE_COLS", "services.replacement_service"),
    ("DISPOSAL_COLS", "services.disposal_service"),
]


def test_no_service_declares_columns_outside_schemas():
    offenders = []
    for path in (ROOT / "services").glob("*.py"):
        if path.name == "schemas.py":
            continue
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"^([A-Z][A-Z0-9_]*_COLS)\s*=\s*\[", text, re.M):
            offenders.append(f"{path.name}:{match.group(1)}")
    assert offenders == [], offenders


def test_consolidated_names_are_reexported_by_their_services():
    schemas = importlib.import_module("services.schemas")
    for name, module_name in CONSOLIDATED:
        canonical = getattr(schemas, name)
        assert getattr(importlib.import_module(module_name), name) is canonical, name


def test_every_column_list_is_non_empty_and_unique():
    import services.schemas as schemas

    names = [
        n
        for n in dir(schemas)
        if n.endswith("_COLS") and isinstance(getattr(schemas, n), list)
    ]
    assert names, "schemas.py defines no column lists"
    for name in names:
        cols = getattr(schemas, name)
        assert cols, name
        assert len(cols) == len(set(cols)), f"duplicate column in {name}: {cols}"
