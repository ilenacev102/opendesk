"""Phase 1 + Phase 2 verification: replacement, return, disposal, repair, bulk, routes."""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import disposal_service as disp_mod
from services import repair_service as rep_mod
from services import replacement_service as repl_mod
from services import return_service as ret_mod
from services.assignment_service import AssignmentService
from services.db_service import DbStore
from services.disposal_service import DisposalService
from services.history_service import HISTORY_COLS, HistoryService
from services.repair_closure import RepairClosureService
from services.repair_service import RepairService
from services.replacement_service import ReplacementService
from services.return_service import ReturnService
from services.schemas import DEV_COLS, EMP_COLS
from utils import helpers as helpers_mod
from utils.validators import ValidationError


@pytest.fixture
def env(monkeypatch):
    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "test.db")
    paths = {
        "db": db,
        "assignments": os.path.join(tmp, "Assignments.csv"),
        "returns": os.path.join(tmp, "Returns.csv"),
        "replacements": os.path.join(tmp, "Replacements.csv"),
        "repairs": os.path.join(tmp, "Repairs.csv"),
        "disposals": os.path.join(tmp, "Disposals.csv"),
        "history": os.path.join(tmp, "History.csv"),
    }
    devices = DbStore(db, "devices", DEV_COLS)
    employees = DbStore(db, "employees", EMP_COLS)
    history = HistoryService(DbStore(db, "history", HISTORY_COLS))

    employees.append_row(
        {
            "EmployeeID": "E001",
            "FirstName": "Ана",
            "LastName": "Тест",
            "UserName": "ana",
            "Email": "a@x.mk",
            "Department": "IT",
            "Organization": "Comp",
            "Location": "Скопје",
            "Active": "YES",
        }
    )
    employees.append_row(
        {
            "EmployeeID": "E002",
            "FirstName": "Боб",
            "LastName": "Тест",
            "UserName": "bob",
            "Email": "b@x.mk",
            "Department": "IT",
            "Organization": "Comp",
            "Location": "Битола",
            "Active": "YES",
        }
    )
    for asset, status, emp, typ, loc in [
        ("LAP001", "Assigned", "E001", "Laptop", "Скопје"),
        ("LAP002", "Available", "", "Laptop", "Скопје"),
        ("LAP003", "Assigned", "E001", "Laptop", "Скопје"),
        ("MON001", "Available", "", "Монитор", "Битола"),
        ("PC001", "Assigned", "E002", "Компјутер", "Тетово"),
    ]:
        devices.append_row(
            {
                "AssetID": asset,
                "Type": typ,
                "Manufacturer": "Lenovo",
                "Model": "T14",
                "SerialNumber": f"SN-{asset}",
                "Status": status,
                "EmployeeID": emp,
                "Location": loc,
                "PurchaseDate": "2024-01-01",
                "WarrantyUntil": "2027-01-01",
                "Notes": "",
            }
        )

    # stub out docx generation + backups for speed
    monkeypatch.setattr(helpers_mod, "backup_all", lambda stores: None)
    monkeypatch.setattr(repl_mod, "fill_template", lambda *a, **k: "documents/x.docx")
    monkeypatch.setattr(ret_mod, "fill_zadolzenie", lambda *a, **k: "documents/x.docx")
    monkeypatch.setattr(rep_mod, "fill_template", lambda *a, **k: "documents/x.docx")
    monkeypatch.setattr(disp_mod, "fill_template", lambda *a, **k: "documents/x.docx")
    import services.return_service as _rs

    monkeypatch.setattr(
        _rs, "fill_template", lambda *a, **k: "documents/x.docx", raising=False
    )
    try:
        from services.document_service import fill_zadolzenie_multi as _m

        monkeypatch.setattr(
            _rs,
            "fill_zadolzenie_multi",
            lambda *a, **k: "documents/x.docx",
            raising=False,
        )
    except (ImportError, AttributeError):
        pass

    assign_svc = AssignmentService(paths, devices, employees, history)
    return_svc = ReturnService(paths, devices, employees, history)
    replace_svc = ReplacementService(paths, devices, employees, history)
    repair_svc = RepairService(paths, devices, employees, history)
    repair_close_svc = RepairClosureService(paths, devices, history)
    dispose_svc = DisposalService(paths, devices, history)
    return {
        "devices": devices,
        "employees": employees,
        "history": history,
        "paths": paths,
        "assign": assign_svc,
        "return": return_svc,
        "replace": replace_svc,
        "repair": repair_svc,
        "repair_close": repair_close_svc,
        "dispose": dispose_svc,
    }


def test_replace_old_broken_goes_to_broken(env):
    """Given assigned LAP001 / When replace with Broken / Then old=BROKEN, new=Assigned."""
    tid, _ = env["replace"].confirm(
        "LAP001", "LAP002", "E001", "дефект", "", "admin", "Broken"
    )
    assert tid.startswith("RP")
    assert env["devices"].find("AssetID", "LAP001")["Status"] == "Broken"
    assert env["devices"].find("AssetID", "LAP002")["Status"] == "Assigned"


def test_replace_old_available_goes_to_stock(env):
    """Given assigned LAP001 / When replace Available / Then old=Available."""
    env["replace"].confirm(
        "LAP001", "LAP002", "E001", "надградба", "", "admin", "Available"
    )
    assert env["devices"].find("AssetID", "LAP001")["Status"] == "Available"


def test_return_wrong_owner_raises(env):
    """Given LAP001 owned by E001 / When E002 returns / Then ValidationError."""
    with pytest.raises(ValidationError):
        env["return"].confirm("LAP001", "E002", "враќање", "Good", "")


def test_return_repair_status_blocked(env):
    """Given device in Repair / When return / Then ValidationError."""
    env["devices"].update_where("AssetID", "LAP001", {"Status": "Repair"})
    with pytest.raises(ValidationError):
        env["return"].confirm("LAP001", "E001", "враќање", "Good", "")


def test_dispose_assigned_blocked(env):
    """Given Assigned device / When dispose / Then ValidationError (single + many)."""
    with pytest.raises(ValidationError, match="задолжен"):
        env["dispose"].confirm("LAP001", "отпис", "уништување", "")
    with pytest.raises(ValidationError):
        env["dispose"].confirm_many(["LAP001"], "отпис", "уништување", "")


def test_bulk_return_offboarding(env):
    """Given E001 holds LAP001+LAP003 / When confirm_many / Then both Available."""
    tids, _ = env["return"].confirm_many(
        ["LAP001", "LAP003"], "E001", "Заминување", "Good", ""
    )
    assert len(tids) == 2
    assert env["devices"].find("AssetID", "LAP001")["Status"] == "Available"
    assert env["devices"].find("AssetID", "LAP003")["Status"] == "Available"


def test_repair_unrepairable_to_disposed(env):
    """Given Broken device / When mark_unrepairable / Then Disposed."""
    env["repair"].report_broken("LAP002", "пукнат екран", "", "admin", "")
    tid = env["repair_close"].mark_unrepairable("LAP002", "Не се исплати", "", "admin")
    assert tid.startswith("BR")
    assert env["devices"].find("AssetID", "LAP002")["Status"] == "Disposed"


def test_repair_advance_return_to_employee(env):
    """Given Broken->Repair->Repaired / When advance with return_to_emp / Then Assigned."""
    env["repair"].report_broken("LAP002", "проблем", "", "admin", "E001")
    env["devices"].update_where("AssetID", "LAP002", {"EmployeeID": "E001"})
    env["repair"].advance("LAP002", "Сервисер", "", "admin")
    env["repair"].advance("LAP002", "Сервисер", "", "admin")
    tid, _ = env["repair"].advance(
        "LAP002", "Сервисер", "", "admin", return_to_emp=True
    )
    assert tid.startswith("BR")
    dev = env["devices"].find("AssetID", "LAP002")
    assert dev["Status"] == "Assigned"
    assert dev["EmployeeID"] == "E001"


def test_devices_route_filters_and_pagination():
    """Given app / When /devices with filters+pagination / Then 200 + UI controls."""
    import os

    import app as app_mod

    client = app_mod.app.test_client()
    r = client.get("/devices?status=Available&type=Laptop&page=1&per=10")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "filter-bar" in html
    assert 'name="status"' in html
    assert 'name="type"' in html
    assert 'name="loc"' in html
    assert "table-responsive" in html
    assert "од вкупно" in html or "Нема уреди" in html
    base = os.path.dirname(os.path.abspath(app_mod.__file__))
    with open(
        os.path.join(base, "templates_web", "devices.html"), encoding="utf-8"
    ) as fh:
        src = fh.read()
    assert "sd-pagination" in src
    assert "Прва" in src and "Последна" in src
    assert 'name="per"' in src


def test_history_route_pagination():
    """Given app / When /history?page=1 / Then 200 + pagination UI."""
    import os

    import app as app_mod

    client = app_mod.app.test_client()
    r = client.get("/history?page=1&per=20")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "table-responsive" in html
    assert 'name="per"' in html
    base = os.path.dirname(os.path.abspath(app_mod.__file__))
    with open(
        os.path.join(base, "templates_web", "history.html"), encoding="utf-8"
    ) as fh:
        src = fh.read()
    assert "sd-pagination" in src
    assert "Прва" in src and "Последна" in src


def test_return_route_bulk_offboarding_ui():
    """Given app / When GET /return / Then single + bulk offboarding tabs."""
    import app as app_mod

    client = app_mod.app.test_client()
    r = client.get("/return")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Поединечно" in html
    assert "Групен поврат" in html
    assert "bulk_asset_ids" in html
    assert 'name="mode"' in html
