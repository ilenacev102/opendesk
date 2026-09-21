"""P0 integrity: unique IDs under concurrency, SQLite pragmas, 500 handler."""

import os
import sqlite3
import sys
import tempfile
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import services.assignment_service as _am
from services.assignment_service import ASSIGN_COLS, AssignmentService
from services.db_service import DbStore
from services.history_service import HISTORY_COLS, HistoryService
from services.schemas import DEV_COLS, EMP_COLS
from utils.helpers import backup_all


def _env():
    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "race.db")
    paths = {"db": db, "assignments": os.path.join(tmp, "a.csv")}
    devices = DbStore(db, "devices", DEV_COLS)
    employees = DbStore(db, "employees", EMP_COLS)
    employees.append_row(
        {
            "EmployeeID": "E1",
            "FirstName": "A",
            "LastName": "B",
            "UserName": "ab",
            "Email": "",
            "Department": "IT",
            "Organization": "",
            "Location": "",
            "Active": "YES",
        }
    )
    for i in range(8):
        devices.append_row(
            {
                "AssetID": f"T{i:02d}",
                "Type": "Laptop",
                "Manufacturer": "M",
                "Model": "X",
                "SerialNumber": f"SN{i}",
                "Status": "Available",
                "EmployeeID": "",
                "Location": "",
                "PurchaseDate": "",
                "WarrantyUntil": "",
                "Notes": "",
            }
        )
    history = HistoryService(DbStore(db, "history", HISTORY_COLS))
    svc = AssignmentService(paths, devices, employees, history, lambda *a, **k: "x")
    return svc


def test_concurrent_assigns_mint_unique_tids(monkeypatch):
    """Given 8 parallel assigns / When run at once / Then all TransactionIDs unique."""
    monkeypatch.setattr(_am, "fill_zadolzenie", lambda *a, **k: "documents/x.docx")
    monkeypatch.setattr(_am, "backup_all", lambda stores: None)
    svc = _env()
    gate = threading.Barrier(8)
    out, errs = [], []

    def work(i):
        gate.wait()
        try:
            out.append(svc.confirm(f"T{i:02d}", "E1", "race"))
        except Exception as exc:  # noqa: BLE001 - collecting thread errors
            errs.append(exc)

    threads = [threading.Thread(target=work, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errs
    tids = [t[0] for t in out]
    assert len(set(tids)) == len(tids), f"duplicate tids: {tids}"


def test_sqlite_connection_pragmas():
    """Given DbStore / When connecting / Then busy_timeout set and WAL enabled."""
    tmp = tempfile.mkdtemp()
    store = DbStore(os.path.join(tmp, "prag.db"), "devices", DEV_COLS)
    con = store._connect()
    try:
        timeout = con.execute("PRAGMA busy_timeout").fetchone()[0]
        mode = con.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        con.close()
    assert timeout and int(timeout) > 0, "busy_timeout not set"
    assert str(mode).lower() == "wal", f"journal_mode={mode}"


def test_db_store_enforces_unique_asset_and_serial_numbers():
    """Given concurrent-safe store / When duplicate device identity is written / Then SQLite rejects it."""
    tmp = tempfile.mkdtemp()
    store = DbStore(os.path.join(tmp, "unique.db"), "devices", DEV_COLS)
    store.append_row({"AssetID": "LAP001", "SerialNumber": "SN-001"})
    with pytest.raises(sqlite3.IntegrityError):
        store.append_row({"AssetID": "LAP001", "SerialNumber": "SN-002"})
    with pytest.raises(sqlite3.IntegrityError):
        store.append_row({"AssetID": "LAP002", "SerialNumber": "SN-001"})


def test_backup_captures_live_wal_data(monkeypatch):
    """Given a write in SQLite WAL / When backed up / Then the snapshot contains it."""
    import config

    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "live.db")
    backup_dir = os.path.join(tmp, "backup")
    monkeypatch.setattr(config, "BACKUP_DIR", backup_dir)
    store = DbStore(db_path, "devices", DEV_COLS)

    con = store._connect()
    try:
        con.execute(
            'INSERT INTO "devices" ("AssetID", "Status") VALUES (?, ?)',
            ("WAL001", "Available"),
        )
        con.commit()
        backup_all([store])
    finally:
        con.close()

    snapshot = os.path.join(
        backup_dir, __import__("datetime").date.today().isoformat(), "live.db"
    )
    with sqlite3.connect(snapshot) as con:
        assert con.execute('SELECT "AssetID" FROM "devices"').fetchone()[0] == "WAL001"


def test_unhandled_error_renders_friendly_500(monkeypatch):
    """Given service crash / When POST /assign / Then friendly 500 page, no traceback leak."""
    import app as app_mod

    def boom(*a, **k):
        raise RuntimeError("simulated crash")

    monkeypatch.setattr(app_mod.assign_svc, "confirm", boom)
    client = app_mod.app.test_client()
    resp = client.post(
        "/assign",
        data={
            "asset_id": "LAP001",
            "emp_id": "E001",
            "reason": "x",
            "notes": "",
        },
    )
    assert resp.status_code == 500
    html = resp.get_data(as_text=True)
    assert "Се случи неочекувана грешка" in html
    assert "Traceback" not in html


def test_popis_list_route_shows_open_and_closed(monkeypatch):
    """Given 1 open + 1 closed popis / When GET /popis / Then both listed with actions."""
    import app as app_mod
    from services.popis_service import PopisService

    tmp = tempfile.mkdtemp()
    svc = PopisService(os.path.join(tmp, "p.db"), os.path.join(tmp, "p.csv"))
    pid_open = svc.start("location", "Скопје", ["LAP001"])
    pid_closed = svc.start("department", "ИТ", ["PC002"])
    svc.finish(pid_closed, "documents/x.docx")
    monkeypatch.setattr(app_mod, "popis_svc", svc)
    html = app_mod.app.test_client().get("/popis").get_data(as_text=True)
    assert pid_open in html and pid_closed in html
    assert "Продолжи" in html


def test_popis_service_start_scan_finish():
    """Given temp PopisService / When start-scan-finish / Then found counted, closed."""
    from services.popis_service import PopisService

    tmp = tempfile.mkdtemp()
    svc = PopisService(os.path.join(tmp, "p.db"), os.path.join(tmp, "p.csv"))
    pid = svc.start("location", "Скопје", ["LAP001", "PC002"])
    assert svc.scan(pid, "LAP001") is True
    assert svc.scan(pid, "NOPE") is False
    result = svc.finish(pid)
    assert result is not None
    assert result["found"] == ["LAP001"]
    assert result["missing"] == ["PC002"]
    assert svc.get(pid)["Status"] == "CLOSED"


def test_packages_page_lists_assign_actions():
    """Given app / When GET /packages / Then package cards with assign links."""
    import app as app_mod

    html = app_mod.app.test_client().get("/packages").get_data(as_text=True)
    assert "Додели пакет" in html
    assert "/package/" in html


def test_dispose_picker_wired_to_form():
    """Given /dispose where picker input lives outside the form / When rendered /
    Then DevicePicker receives the form element explicitly (no null closest)."""
    import app as app_mod

    html = app_mod.app.test_client().get("/dispose").get_data(as_text=True)
    assert "disForm" in html
    assert 'document.getElementById("disForm")' in html
    assert "new DevicePicker" in html
    anchor = html.index("new DevicePicker")
    assert 'getElementById("disForm")' in html[anchor : anchor + 200]


def _import_env(monkeypatch):
    """Isolated stores wired into app globals for import route tests."""
    import app as app_mod
    from services.db_service import DbStore
    from services.history_service import HistoryService

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "imp.db")
    monkeypatch.setattr(app_mod, "devices", DbStore(db, "devices", DEV_COLS))
    monkeypatch.setattr(app_mod, "employees", DbStore(db, "employees", EMP_COLS))
    monkeypatch.setattr(
        app_mod, "history", HistoryService(DbStore(db, "history", HISTORY_COLS))
    )
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)
    return app_mod


def _csv_bytes(rows, cols):
    import io

    lines = [",".join(cols)]
    lines += [",".join(row.get(c, "") for c in cols) for row in rows]
    return io.BytesIO("\n".join(lines).encode("utf-8"))


def test_import_valid_csv_logs_history(monkeypatch):
    """Given valid CSV / When POST /import / Then rows stored + IMPORT history each."""
    from services.schemas import DEV_COLS as _DC

    app_mod = _import_env(monkeypatch)
    cols = list(_DC)
    rows = [
        {c: "" for c in cols}
        | {
            "AssetID": "IMP01",
            "Type": "Laptop",
            "SerialNumber": "S1",
            "Status": "Available",
        },
        {c: "" for c in cols}
        | {
            "AssetID": "IMP02",
            "Type": "Монитор",
            "SerialNumber": "S2",
            "Status": "Available",
        },
    ]
    resp = app_mod.app.test_client().post(
        "/import",
        data={"kind": "devices", "file": (_csv_bytes(rows, cols), "imp.csv")},
    )
    assert resp.status_code == 200
    assert app_mod.devices.find("AssetID", "IMP01") is not None
    actions = [r.get("Action") for r in app_mod.history.store.records()]
    assert actions.count("IMPORT") == 2


def test_import_rolls_back_on_mid_loop_failure(monkeypatch):
    """Given append fails on 2nd row / When POST /import / Then zero rows stored."""
    from services.schemas import DEV_COLS as _DC

    app_mod = _import_env(monkeypatch)
    cols = list(_DC)
    real_append = app_mod.devices.append_row
    calls = []

    def flaky(row, con=None):
        calls.append(row.get("AssetID"))
        if len(calls) == 2:
            raise IOError("simulated disk failure")
        return real_append(row, con=con)

    monkeypatch.setattr(app_mod.devices, "append_row", flaky)
    rows = [
        {c: "" for c in cols}
        | {"AssetID": "IMP11", "SerialNumber": "S11", "Status": "Available"},
        {c: "" for c in cols}
        | {"AssetID": "IMP12", "SerialNumber": "S12", "Status": "Available"},
    ]
    resp = app_mod.app.test_client().post(
        "/import",
        data={"kind": "devices", "file": (_csv_bytes(rows, cols), "imp.csv")},
    )
    assert resp.status_code == 200
    assert app_mod.devices.records() == []


def test_import_rejects_unknown_status(monkeypatch):
    """Given CSV with bad Status / When POST /import / Then error, nothing stored."""
    from services.schemas import DEV_COLS as _DC

    app_mod = _import_env(monkeypatch)
    cols = list(_DC)
    rows = [
        {c: "" for c in cols}
        | {"AssetID": "IMP21", "SerialNumber": "S21", "Status": "Flying"}
    ]
    resp = app_mod.app.test_client().post(
        "/import",
        data={"kind": "devices", "file": (_csv_bytes(rows, cols), "imp.csv")},
    )
    assert resp.status_code == 200
    assert "Непознат статус" in resp.get_data(as_text=True)
    assert app_mod.devices.records() == []
