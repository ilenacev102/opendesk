"""Enterprise Wave1 todo 1: incident/staging/ldapmap schemas + auto-migration."""

import sqlite3

import app
from services.schemas import INCIDENT_COLS, LDAPMAP_COLS, STAGING_COLS


def test_incident_cols_defined():
    assert INCIDENT_COLS == [
        "IncidentID",
        "AssetID",
        "EmployeeID",
        "Title",
        "Priority",
        "Status",
        "Assignee",
        "DueDate",
        "Created",
        "ClosedAt",
        "Notes",
        "LinkedTo",
        "Satisfaction",
        "ProjectID",
        "TypeID",
        "EpicLink",
        "StoryPoints",
        "SprintID",
        "Rank",
        "FixVersion",
    ]


def test_staging_cols_defined():
    assert STAGING_COLS == [
        "SerialNumber",
        "Manufacturer",
        "Model",
        "Hostname",
        "OS",
        "LastSeen",
        "Source",
    ]


def test_ldapmap_cols_defined():
    assert LDAPMAP_COLS == ["UserName", "DN", "LastSync"]


def test_stores_wired_with_columns():
    assert app.incidents.columns == INCIDENT_COLS
    assert app.staging.columns == STAGING_COLS
    assert app.ldapmap.columns == LDAPMAP_COLS


def test_tables_exist_in_db():
    with sqlite3.connect(app.DB_PATH) as con:
        tables = {
            r[0]
            for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert {"incidents", "staging", "ldapmap"} <= tables


def test_incident_id_unique_index():
    with sqlite3.connect(app.DB_PATH) as con:
        idx = {
            r[0]
            for r in con.execute("SELECT name FROM sqlite_master WHERE type='index'")
        }
    assert "uq_incidents_IncidentID" in idx
