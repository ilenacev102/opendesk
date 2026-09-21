"""Phase B.3a: canvas signature decode/validate. Never raises."""

import base64
import binascii
import logging

log = logging.getLogger("servicedesk")

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
PREFIX = "data:image/png;base64,"


def decode_signature(data_url, max_bytes: int = 200_000):
    """Return PNG bytes or None when missing/invalid/oversize."""
    try:
        if not data_url or not str(data_url).startswith(PREFIX):
            return None
        raw = base64.b64decode(str(data_url)[len(PREFIX) :], validate=True)
    except (binascii.Error, ValueError):
        return None
    if not raw.startswith(PNG_MAGIC):
        return None
    if len(raw) > max_bytes:
        log.warning("Signature rejected: %d bytes over limit", len(raw))
        return None
    if len(raw) < len(PNG_MAGIC) + 10:
        return None
    return raw
