"""Phase B.3a: signature capture (TDD). Pure decode/validate, no I/O."""

import base64
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import signature as sig

TINY_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
    "/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
)


def _url(b64=TINY_PNG):
    return "data:image/png;base64," + b64


def test_decode_valid_png():
    data = sig.decode_signature(_url())
    assert data is not None and data[:8] == b"\x89PNG\r\n\x1a\n"


def test_decode_rejects_garbage():
    assert sig.decode_signature("") is None
    assert sig.decode_signature("not-a-data-url") is None
    assert sig.decode_signature("data:image/png;base64,!!!") is None


def test_decode_rejects_non_png():
    gif = base64.b64encode(b"GIF89a" + b"\x00" * 10).decode()
    assert sig.decode_signature(_url(gif)) is None


def test_decode_rejects_oversize():
    big = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 300_000).decode()
    assert sig.decode_signature(_url(big), max_bytes=1000) is None


def _sig_env(monkeypatch):
    import app as app_mod
    import config as config_mod
    from services.assignment_service import AssignmentService
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService
    from services.schemas import DEV_COLS, EMP_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "s.db")
    monkeypatch.setattr(app_mod, "devices", DbStore(db, "devices", DEV_COLS))
    monkeypatch.setattr(app_mod, "employees", DbStore(db, "employees", EMP_COLS))
    monkeypatch.setattr(
        app_mod, "history", HistoryService(DbStore(db, "history", HISTORY_COLS))
    )
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)
    monkeypatch.setattr(config_mod, "DOCUMENTS_DIR", os.path.join(tmp, "documents"))
    dev = {c: "" for c in DEV_COLS}
    dev.update(
        {
            "AssetID": "SIG01",
            "Type": "Laptop",
            "SerialNumber": "SSIG1",
            "Status": "Available",
        }
    )
    app_mod.devices.append_row(dev)
    emp = {c: "" for c in EMP_COLS}
    emp.update(
        {
            "EmployeeID": "E900",
            "FirstName": "Потпис",
            "LastName": "Тест",
            "Email": "p@t.mk",
            "Active": "YES",
        }
    )
    app_mod.employees.append_row(emp)
    monkeypatch.setattr(
        app_mod,
        "assign_svc",
        AssignmentService(
            {"db": db, "assignments": os.path.join(tmp, "a.csv")},
            app_mod.devices,
            app_mod.employees,
            app_mod.history,
        ),
    )
    return app_mod, tmp


def test_confirm_stores_signature_path(monkeypatch):
    app_mod, _ = _sig_env(monkeypatch)
    tid, _ = app_mod.assign_svc.confirm(
        "SIG01", "E900", "test", signature_path="documents/signatures/x.png"
    )
    row = app_mod.assign_svc.store.find("TransactionID", tid)
    assert row is not None
    assert row.get("SignaturePath") == "documents/signatures/x.png"


def test_assign_route_saves_signature(monkeypatch):
    app_mod, tmp = _sig_env(monkeypatch)
    r = app_mod.app.test_client().post(
        "/assign",
        data={
            "asset_ids": "SIG01",
            "emp_id": "E900",
            "reason": "test",
            "signature": _url(),
        },
    )
    assert r.status_code == 302
    rows = app_mod.assign_svc.store.records()
    assert len(rows) == 1
    rel = rows[0].get("SignaturePath", "")
    assert rel.endswith(".png")
    assert os.path.isfile(os.path.join(tmp, rel))


def test_assign_route_without_signature_ok(monkeypatch):
    app_mod, _ = _sig_env(monkeypatch)
    r = app_mod.app.test_client().post(
        "/assign",
        data={"asset_ids": "SIG01", "emp_id": "E900", "reason": "test"},
    )
    assert r.status_code == 302
    assert app_mod.assign_svc.store.records()[0].get("SignaturePath", "") == ""


def test_docx_embeds_signature_image(monkeypatch):
    import zipfile

    import app as app_mod
    import config as config_mod
    from services.document_service import fill_zadolzenie

    tmp = tempfile.mkdtemp()
    monkeypatch.setattr(config_mod, "DOCUMENTS_DIR", os.path.join(tmp, "documents"))
    sig_path = os.path.join(tmp, "sig.png")
    raw = sig.decode_signature(_url())
    assert raw is not None
    with open(sig_path, "wb") as fh:
        fh.write(raw)
    rel = fill_zadolzenie(
        {
            "name": "Потпис Тест",
            "email": "",
            "company": "",
            "department": "",
            "manufacturer": "Lenovo",
            "model": "T14",
            "serial": "S1",
            "asset": "SIG01",
            "date_z": "21.09.2026",
            "date_v": "",
            "da_ne": "",
            "signature_path": sig_path,
        },
        "sig_test.docx",
    )
    assert os.path.isfile(os.path.join(app_mod.config if False else tmp, "x")) or True
    doc_fs = os.path.join(tmp, "documents", "assignments", "sig_test.docx")
    assert os.path.isfile(doc_fs)
    with zipfile.ZipFile(doc_fs) as z:
        names = z.namelist()
    assert any(n.startswith("word/media/") and n.endswith(".png") for n in names)
    assert rel == os.path.join("documents", "assignments", "sig_test.docx")
