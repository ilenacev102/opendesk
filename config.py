"""Central configuration - no hardcoded paths elsewhere."""

import os
import secrets

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
TRANSACTIONS_DIR = os.path.join(BASE_DIR, "transactions")
DOCUMENTS_DIR = os.path.join(BASE_DIR, "documents")
TEMPLATES_DIR = os.environ.get(
    "SERVICEDESK_TEMPLATES_DIR", os.path.join(BASE_DIR, "templates")
)
BACKUP_DIR = os.path.join(BASE_DIR, "backup")
LOG_DIR = os.path.join(BASE_DIR, "logs")

for _d in (
    DATA_DIR,
    TRANSACTIONS_DIR,
    DOCUMENTS_DIR,
    TEMPLATES_DIR,
    BACKUP_DIR,
    LOG_DIR,
):
    os.makedirs(_d, exist_ok=True)

HOST = os.environ.get("SERVICEDESK_HOST", "127.0.0.1")
_configured_secret = os.environ.get("SERVICEDESK_SECRET", "").strip()

if _configured_secret:
    SECRET_KEY = _configured_secret
elif os.environ.get("SERVICEDESK_REQUIRE_SECRET") == "1":
    raise RuntimeError("SERVICEDESK_SECRET мора да биде поставен за овој deploy.")
else:
    # A local install remains usable without setup while avoiding a shared,
    # publicly known Flask signing key. Docker deployments require an explicit key.
    _secret_file = os.path.join(BASE_DIR, ".servicedesk_secret")
    try:
        with open(_secret_file, encoding="utf-8") as _fh:
            SECRET_KEY = _fh.read().strip()
    except FileNotFoundError:
        SECRET_KEY = secrets.token_urlsafe(48)
        _fd = os.open(_secret_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(_fd, "w", encoding="utf-8") as _fh:
            _fh.write(SECRET_KEY)
    if not SECRET_KEY:
        raise RuntimeError("Локалниот ServiceDesk secret е празен.")
BACKUP_ON_WRITE = True
