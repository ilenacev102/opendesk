"""IT ServiceDesk - Flask app (phased build, runnable after every phase)."""

import json
import logging
import logging.handlers
import os
import secrets
import sqlite3
import time
import uuid
from collections import Counter

from flask import (
    Flask,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

import config

os.makedirs(config.LOG_DIR, exist_ok=True)
_handler = logging.handlers.RotatingFileHandler(
    os.path.join(config.LOG_DIR, "app.log"),
    maxBytes=2_000_000,
    backupCount=3,
    encoding="utf-8",
)
logging.basicConfig(
    handlers=[_handler],
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("servicedesk")

app = Flask(__name__, template_folder="templates_web", static_folder="static")
app.secret_key = config.SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


@app.after_request
def set_security_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    resp.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        f"script-src 'self' 'nonce-{g.get('csp_nonce', '')}'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data:; "
        "object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    )
    return resp


@app.context_processor
def inject_csp_nonce():
    return {"csp_nonce": g.get("csp_nonce", "")}


from services.schemas import (  # noqa: E402
    CONS_COLS,
    CONTRACT_COLS,
    DEV_COLS,
    EMP_COLS,
    FIELD_DEF_COLS,
    FIELD_VAL_COLS,
    LIC_COLS,
    REQUEST_COLS,
    RESERV_COLS,
)

USE_DB = True
DB_PATH = os.environ.get(
    "SERVICEDESK_DB", os.path.join(config.DATA_DIR, "servicedesk.db")
)

from services.db_service import DbStore  # noqa: E402

employees = DbStore(DB_PATH, "employees", EMP_COLS)
devices = DbStore(DB_PATH, "devices", DEV_COLS)
consumables = DbStore(DB_PATH, "consumables", CONS_COLS)
licenses = DbStore(DB_PATH, "licenses", LIC_COLS)
field_defs = DbStore(DB_PATH, "field_defs", FIELD_DEF_COLS)
field_values = DbStore(DB_PATH, "field_values", FIELD_VAL_COLS)
contracts = DbStore(DB_PATH, "contracts", CONTRACT_COLS)
reservations = DbStore(DB_PATH, "reservations", RESERV_COLS)
requests = DbStore(DB_PATH, "requests", REQUEST_COLS)

PATHS = {
    "db": DB_PATH,
    "assignments": os.path.join(config.TRANSACTIONS_DIR, "Assignments.csv"),
    "returns": os.path.join(config.TRANSACTIONS_DIR, "Returns.csv"),
    "replacements": os.path.join(config.TRANSACTIONS_DIR, "Replacements.csv"),
    "repairs": os.path.join(config.TRANSACTIONS_DIR, "Repairs.csv"),
    "disposals": os.path.join(config.TRANSACTIONS_DIR, "Disposals.csv"),
    "history": os.path.join(config.TRANSACTIONS_DIR, "History.csv"),
}

from services.assignment_service import AssignmentService  # noqa: E402
from services.api_token_service import TOKEN_COLS, ApiTokenService  # noqa: E402
from services.auth_service import USER_COLS, AuthService  # noqa: E402
from services.db_service import open_store  # noqa: E402
from services.disposal_service import DisposalService  # noqa: E402
from services.history_service import HISTORY_COLS, HistoryService  # noqa: E402
from services.notify_service import (  # noqa: E402
    assignment_email,
    digest_email,
    return_email,
    send_email,
    warranty_expiring,
)
from services.popis_service import PopisService  # noqa: E402
from services.qr_service import qr_png_bytes  # noqa: E402
from services.repair_closure import RepairClosureService  # noqa: E402
from services.repair_service import RepairService  # noqa: E402
from services.replacement_service import ReplacementService  # noqa: E402
from services.return_service import ReturnService  # noqa: E402
from services.signature import decode_signature  # noqa: E402
from services.ratelimit import is_allowed as _rate_ok  # noqa: E402
from utils.helpers import backup_all, stamp  # noqa: E402
from utils.validators import ValidationError  # noqa: E402

history = HistoryService(
    open_store(PATHS["db"], "history", PATHS["history"], HISTORY_COLS)
)
assign_svc = AssignmentService(PATHS, devices, employees, history)
return_svc = ReturnService(PATHS, devices, employees, history)
replace_svc = ReplacementService(PATHS, devices, employees, history)
repair_svc = RepairService(PATHS, devices, employees, history)
repair_close_svc = RepairClosureService(PATHS, devices, history)
dispose_svc = DisposalService(PATHS, devices, history)
popis_svc = PopisService(
    PATHS["db"], os.path.join(config.TRANSACTIONS_DIR, "Popis.csv")
)
auth_svc = AuthService(
    open_store(
        PATHS["db"], "users", os.path.join(config.DATA_DIR, "Users.csv"), USER_COLS
    )
)
token_svc = ApiTokenService(
    open_store(
        PATHS["db"],
        "api_tokens",
        os.path.join(config.DATA_DIR, "ApiTokens.csv"),
        TOKEN_COLS,
    )
)

try:
    from flask_login import (
        LoginManager,
        UserMixin,
        current_user,
        login_required,
        login_user,
        logout_user,
    )

    login_manager = LoginManager(app)
    login_manager.login_view = "admin.login"  # type: ignore[assignment]

    class AppUser(UserMixin):
        def __init__(self, row):
            self.row = row
            self.id = row.get("UserName", "")
            self.role = row.get("Role", "citac")

    @login_manager.user_loader
    def load_user(user_id):
        row = auth_svc.get(user_id)
        if row is None or row.get("Active") != "YES":
            return None
        return AppUser(row)

    @login_manager.request_loader
    def load_user_from_token(req):
        authz = req.headers.get("Authorization", "")
        if not authz.startswith("Bearer "):
            return None
        user = token_svc.verify(authz[len("Bearer ") :].strip(), auth_svc)
        if user is None:
            return None
        return AppUser(user)

    _env_admin = os.environ.get("SERVICEDESK_ADMIN_USER", "").strip()
    _env_pass = os.environ.get("SERVICEDESK_ADMIN_PASS", "")
    if _env_admin and _env_pass and not auth_svc.auth_required():
        try:
            auth_svc.create_user(_env_admin, _env_pass, role="admin")
            log.info("Bootstrap admin user created from env")
        except ValueError:
            pass
except ImportError:  # Flask-Login недостапен: рутите остануваат отворени
    login_required = lambda f: f  # noqa: E731
    current_user = None

    class AppUser:  # минимален fallback за /login без Flask-Login
        def __init__(self, row):
            self.row = row
            self.id = row.get("UserName", "")
            self.role = row.get("Role", "citac")

    def login_user(user):
        return False

    def logout_user():
        return False


def _open_paths():
    return {"health", "static", "admin.login", "admin.setup"}


_RATE_LIMITS = (
    ("/pdf", 30, 60),
    ("/api/v1", 120, 60),
    ("/login", 30, 60),
)


@app.before_request
def security_checks():
    g.csp_nonce = secrets.token_urlsafe(16)
    if request.method == "POST":
        origin = request.headers.get("Origin") or request.headers.get("Referer")
        if origin:
            from urllib.parse import urlparse as _urlparse

            if _urlparse(origin).netloc != request.host:
                abort(403)
    for prefix, limit, window in _RATE_LIMITS:
        if (request.path or "").startswith(prefix):
            if not _rate_ok(f"{request.remote_addr}|{prefix}", limit, window):
                return "Too many requests", 429, {"Retry-After": "60"}
    return None


@app.before_request
def enforce_auth():
    if current_user is None or not auth_svc.auth_required():
        return None
    if request.endpoint in _open_paths():
        return None
    if getattr(current_user, "is_authenticated", False):
        if getattr(current_user, "role", "") == "citac" and request.method == "POST":
            abort(403)
        return None
    if (request.path or "").startswith("/api/v1"):
        from flask import jsonify as _jsonify

        return _jsonify({"error": "unauthorized"}), 401
    from flask import flash as _flash

    _flash("Најавете се за да продолжите.", "warning")
    from flask import redirect as _redirect, url_for as _url_for

    return _redirect(_url_for("admin.login", next=request.path))


def roles_required(*roles):
    def deco(fn):
        from functools import wraps

        @wraps(fn)
        def wrapper(*args, **kwargs):
            if current_user is None or not auth_svc.auth_required():
                return fn(*args, **kwargs)
            user_role = getattr(current_user, "role", "citac")
            if user_role != "admin" and user_role not in roles:
                abort(403)
            return fn(*args, **kwargs)

        return wrapper

    return deco


def _notify_assignment(emp_id, asset_ids, tid):
    try:
        emp = employees.find("EmployeeID", emp_id)
        if emp is None:
            return
        name = f"{emp.get('FirstName', '')} {emp.get('LastName', '')}".strip()
        if len(asset_ids) == 1:
            dev = devices.find("AssetID", asset_ids[0])
            desc = (
                f"{dev.get('Manufacturer', '')} {dev.get('Model', '')}".strip()
                if dev
                else ""
            )
            built = assignment_email(
                emp.get("Email", ""), name, asset_ids[0], desc, tid
            )
        else:
            built = assignment_email(
                emp.get("Email", ""),
                name,
                f"{len(asset_ids)} уреди",
                ", ".join(asset_ids),
                tid,
            )
        if built is not None:
            send_email(*built)
    except Exception:
        log.exception("Notify assignment failed emp=%s", emp_id)


def _notify_return(emp_id, asset_ids, tid):
    try:
        emp = employees.find("EmployeeID", emp_id)
        if emp is None:
            return
        name = f"{emp.get('FirstName', '')} {emp.get('LastName', '')}".strip()
        label = asset_ids[0] if len(asset_ids) == 1 else f"{len(asset_ids)} уреди"
        built = return_email(emp.get("Email", ""), name, label, tid)
        if built is not None:
            send_email(*built)
    except Exception:
        log.exception("Notify return failed emp=%s", emp_id)


def _parse_qty(raw):
    try:
        val = int(str(raw or "").strip())
    except ValueError:
        raise ValidationError("Количината мора да е цел број.")
    if val < 0:
        raise ValidationError("Количината не може да е негативна.")
    return val


def _api_user():
    if current_user is None or not getattr(current_user, "is_authenticated", False):
        return None
    return current_user


def _require_api_roles(*roles):
    if not auth_svc.auth_required():
        return None
    user = _api_user()
    if user is None:
        from flask import jsonify as _jsonify

        return _jsonify({"error": "unauthorized"}), 401
    role = getattr(user, "role", "citac")
    if role != "admin" and role not in roles:
        from flask import jsonify as _jsonify

        return _jsonify({"error": "forbidden"}), 403
    return None


def _row(store, col, value):
    rec = store.find(col, value)
    if rec is None:
        abort(404)
    return rec


ID_PREFIX = {
    "Laptop": "LAP",
    "Компјутер": "PC",
    "Монитор": "MON",
    "Печатач": "PRN",
    "Телефон": "TEL",
    "Таблет": "TAB",
    "Друго": "AST",
}


def warranty_days(date_str):
    import datetime

    try:
        target = datetime.date.fromisoformat((date_str or "").strip())
    except ValueError:
        return None
    return (target - datetime.date.today()).days


def warranty_level(days):
    if days is None:
        return ("unknown", "—")
    if days < 0:
        return ("expired", f"истечена ({abs(days)} дена)")
    if days <= 30:
        return ("critical", f"{days} дена")
    if days <= 90:
        return ("warning", f"{days} дена")
    return ("ok", f"{days} дена")


@app.errorhandler(500)
def internal_error(exc):
    """Boundary handler: log traceback with reference, render friendly page."""
    ref = uuid.uuid4().hex[:8]
    log.exception("Unhandled error ref=%s path=%s", ref, request.path)
    return render_template("500.html", ref=ref), 500


from routes.admin import bp as admin_bp
from routes.api import bp as api_bp
from routes.catalog import bp as catalog_bp
from routes.files import bp as files_bp
from routes.inventory import bp as inventory_bp
from routes.operations import bp as operations_bp
from routes.popis import bp as popis_bp
from routes.reports import bp as reports_bp
from routes.system import bp as system_bp

app.register_blueprint(admin_bp)
app.register_blueprint(api_bp)
app.register_blueprint(catalog_bp)
app.register_blueprint(files_bp)
app.register_blueprint(inventory_bp)
app.register_blueprint(operations_bp)
app.register_blueprint(popis_bp)
app.register_blueprint(reports_bp)
app.register_blueprint(system_bp)


if __name__ == "__main__":
    log.info("ServiceDesk starting")
    port = int(os.environ.get("SERVICEDESK_PORT", "5000"))
    app.run(host=config.HOST, port=port, debug=False)
