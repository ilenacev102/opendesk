"""Phase B.1: QR labels for devices. Payload points at device page."""

import io
import os
import re

import qrcode

SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def payload_for(asset_id: str, base_url: str = "/") -> str:
    base = (base_url or "/").rstrip("/") + "/"
    return f"{base}device/{asset_id}"


def qr_png_bytes(asset_id: str, base_url: str = "/") -> bytes:
    if not SAFE_ID.match(asset_id or ""):
        raise ValueError(f"Невалиден AssetID за QR: {asset_id!r}.")
    buf = io.BytesIO()
    qrcode.make(payload_for(asset_id, base_url)).save(buf)
    return buf.getvalue()


def make_qr(asset_id: str, dest_dir: str, base_url: str = "/") -> str:
    if not SAFE_ID.match(asset_id or ""):
        raise ValueError(f"Невалиден AssetID за QR: {asset_id!r}.")
    os.makedirs(dest_dir, exist_ok=True)
    path = os.path.join(dest_dir, f"{asset_id}.png")
    if not os.path.isfile(path):
        with open(path, "wb") as fh:
            fh.write(qr_png_bytes(asset_id, base_url))
    return path
