"""Phase B.1: QR labels (TDD). Generates real PNG files in temp dir."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import qr_service as qr


def test_make_qr_creates_valid_png():
    tmp = tempfile.mkdtemp()
    path = qr.make_qr("LAP001", tmp)
    assert os.path.isfile(path)
    with open(path, "rb") as f:
        assert f.read(8) == b"\x89PNG\r\n\x1a\n"


def test_make_qr_deterministic_path():
    tmp = tempfile.mkdtemp()
    assert qr.make_qr("LAP001", tmp) == qr.make_qr("LAP001", tmp)


def test_qr_payload_contains_asset():
    assert "LAP001" in qr.payload_for("LAP001", base_url="http://x/")


def test_unsafe_asset_id_raises():
    import pytest

    with pytest.raises(ValueError):
        qr.make_qr("../../etc/passwd", tempfile.mkdtemp())


def test_qr_png_bytes_valid():
    assert qr.qr_png_bytes("LAP001")[:8] == b"\x89PNG\r\n\x1a\n"


def _qr_env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.schemas import DEV_COLS

    tmp = tempfile.mkdtemp()
    monkeypatch.setattr(
        app_mod, "devices", DbStore(os.path.join(tmp, "qr.db"), "devices", DEV_COLS)
    )
    row = {c: "" for c in DEV_COLS}
    row.update(
        {
            "AssetID": "QR01",
            "Type": "Laptop",
            "Manufacturer": "Lenovo",
            "Model": "T14",
            "SerialNumber": "SQR1",
            "Status": "Available",
            "Location": "Скопје",
        }
    )
    app_mod.devices.append_row(row)
    return app_mod


def test_qr_route_png(monkeypatch):
    app_mod = _qr_env(monkeypatch)
    r = app_mod.app.test_client().get("/qr/QR01")
    assert r.status_code == 200
    assert r.content_type == "image/png"
    assert r.data[:8] == b"\x89PNG\r\n\x1a\n"


def test_qr_route_missing(monkeypatch):
    app_mod = _qr_env(monkeypatch)
    assert app_mod.app.test_client().get("/qr/NOPE").status_code == 404


def test_labels_route_lists(monkeypatch):
    app_mod = _qr_env(monkeypatch)
    html = app_mod.app.test_client().get("/labels").get_data(as_text=True)
    assert "QR01" in html and "/qr/QR01" in html
