"""Validation rules - every business rule violation raises ValidationError."""

from services.db_service import DbStore


class ValidationError(Exception):
    pass


BLOCKED_STATUSES = {"Disposed", "Lost", "Stolen"}


def require_employee(employees: DbStore, emp_id: str):
    emp = employees.find("EmployeeID", emp_id)
    if emp is None:
        raise ValidationError(f"Невалиден EmployeeID: {emp_id}.")
    if emp.get("Active") != "YES":
        raise ValidationError(f"Вработениот {emp_id} не е активен.")
    return emp


def require_device(devices: DbStore, asset_id: str):
    dev = devices.find("AssetID", asset_id)
    if dev is None:
        raise ValidationError(f"Невалиден AssetID: {asset_id}.")
    return dev


def require_assignable(devices: DbStore, asset_id: str):
    dev = require_device(devices, asset_id)
    if dev.get("Status") in BLOCKED_STATUSES:
        raise ValidationError(
            f"Уредот {asset_id} има статус {dev.get('Status')} "
            "и не смее да се задолжува."
        )
    if dev.get("Status") == "Assigned":
        holder = dev.get("EmployeeID") or "непознато"
        raise ValidationError(f"Уредот {asset_id} е веќе задолжен кај {holder}.")
    if dev.get("Status") != "Available":
        raise ValidationError(
            f"Уредот {asset_id} не е достапен (статус: {dev.get('Status')})."
        )
    return dev


def require_returnable(devices: DbStore, asset_id: str, emp_id: str | None = None):
    dev = require_device(devices, asset_id)
    status = dev.get("Status", "")
    if status == "Available":
        raise ValidationError(f"Уредот {asset_id} е веќе на залиха.")
    if status in BLOCKED_STATUSES:
        raise ValidationError(
            f"Уредот {asset_id} има статус {status} и не може да се раздолжи."
        )
    if status == "Repair":
        raise ValidationError(
            f"Уредот {asset_id} е во сервис (статус: Repair). Завршете го сервисот пред раздолжување."
        )
    if emp_id and dev.get("EmployeeID") and dev.get("EmployeeID") != emp_id:
        raise ValidationError(
            f"Уредот {asset_id} не е задолжен кај вработениот {emp_id}, туку кај {dev.get('EmployeeID')}."
        )
    return dev


def require_disposable(devices: DbStore, asset_id: str):
    dev = require_device(devices, asset_id)
    status = dev.get("Status", "")
    if status == "Disposed":
        raise ValidationError(f"Уредот {asset_id} е веќе расходуван.")
    if status == "Assigned":
        holder = dev.get("EmployeeID") or "вработен"
        raise ValidationError(
            f"Уредот {asset_id} е сѐ уште задолжен кај {holder}. Мора прво да се раздолжи пред да се расходува."
        )
    return dev
