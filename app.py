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
from services.csv_service import CsvStore

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
from services.document_service import save_doc  # noqa: E402
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
assign_svc = AssignmentService(PATHS, devices, employees, history, save_doc)
return_svc = ReturnService(PATHS, devices, employees, history, save_doc)
replace_svc = ReplacementService(PATHS, devices, employees, history, save_doc)
repair_svc = RepairService(PATHS, devices, employees, history, save_doc)
repair_close_svc = RepairClosureService(PATHS, devices, history)
dispose_svc = DisposalService(PATHS, devices, history, save_doc)
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
    login_manager.login_view = "login"  # type: ignore[assignment]

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
    return {"health", "static", "login", "setup"}


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

    return _redirect(_url_for("login", next=request.path))


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


@app.route("/notify-digest", methods=["POST"])
@roles_required("admin", "magacioner")
def notify_digest():
    import os as _os

    expiring = warranty_expiring(devices.records(), days=30)
    admin_email = _os.environ.get("SERVICEDESK_ADMIN_EMAIL", "").strip()
    if not expiring:
        flash("Нема гаранции што истекуваат во следните 30 дена.", "success")
    elif not admin_email:
        flash("ГРЕШКА: поставете SERVICEDESK_ADMIN_EMAIL.", "danger")
    else:
        to, subject, body = digest_email(admin_email, expiring)
        if send_email(to, subject, body):
            flash(
                f"Digest испратен на {admin_email} ({len(expiring)} уреди).", "success"
            )
        else:
            flash("ГРЕШКА: mail не е испратен. Проверете SMTP-поставки.", "danger")
    return redirect(url_for("reports"))


@app.route("/qr/<asset_id>")
def qr_image(asset_id):
    dev = devices.find("AssetID", asset_id)
    if dev is None:
        abort(404)
    try:
        png = qr_png_bytes(asset_id, request.host_url)
    except ValueError:
        abort(404)
    import io as _io

    return send_file(
        _io.BytesIO(png),
        mimetype="image/png",
        download_name=f"{asset_id}.png",
    )


@app.route("/labels")
def labels():
    st = (request.args.get("status") or "").strip()
    tp = (request.args.get("type") or "").strip()
    loc = (request.args.get("loc") or "").strip()
    rows = []
    for d in devices.records():
        if st and d.get("Status") != st:
            continue
        if tp and d.get("Type") != tp:
            continue
        if loc and d.get("Location") != loc:
            continue
        rows.append(d)
    return render_template("labels.html", rows=rows, st=st, tp=tp, loc=loc)


def _parse_qty(raw):
    try:
        val = int(str(raw or "").strip())
    except ValueError:
        raise ValidationError("Количината мора да е цел број.")
    if val < 0:
        raise ValidationError("Количината не може да е негативна.")
    return val


@app.route("/consumables", methods=["GET", "POST"])
def consumables_view():
    if request.method == "POST":
        cid = request.form.get("ConsumableID", "").strip()
        try:
            if not cid:
                raise ValidationError("ID е задолжителен.")
            if consumables.find("ConsumableID", cid):
                raise ValidationError(f"{cid} веќе постои.")
            consumables.append_row(
                {
                    "ConsumableID": cid,
                    "Name": request.form.get("Name", "").strip(),
                    "Category": request.form.get("Category", "").strip(),
                    "Quantity": str(_parse_qty(request.form.get("Quantity", "0"))),
                    "MinLevel": str(_parse_qty(request.form.get("MinLevel", "0"))),
                    "Location": request.form.get("Location", "").strip(),
                    "Notes": request.form.get("Notes", "").strip(),
                }
            )
            if config.BACKUP_ON_WRITE:
                backup_all([consumables])
            flash(f"Материјалот {cid} е внесен.", "success")
        except ValidationError as exc:
            flash(f"ГРЕШКА: {exc}", "danger")
        return redirect(url_for("consumables_view"))
    rows = consumables.records()
    low_ids = set()
    for r in rows:
        try:
            if int(r.get("Quantity") or 0) <= int(r.get("MinLevel") or 0):
                low_ids.add(r.get("ConsumableID", ""))
        except ValueError:
            pass
    return render_template("consumables.html", rows=rows, low_ids=low_ids)


@app.route("/consumables/issue", methods=["POST"])
def consumables_issue():
    cid = request.form.get("consumable_id", "").strip()
    try:
        row = consumables.find("ConsumableID", cid)
        if row is None:
            raise ValidationError(f"Материјалот {cid} не постои.")
        qty = _parse_qty(request.form.get("qty", "0"))
        if qty <= 0:
            raise ValidationError("Количината мора да е позитивна.")
        stock = _parse_qty(row.get("Quantity", "0"))
        if qty > stock:
            raise ValidationError(f"Нема доволно залиха (достапно: {stock}).")
        new_stock = stock - qty
        consumables.update_where("ConsumableID", cid, {"Quantity": str(new_stock)})
        if config.BACKUP_ON_WRITE:
            backup_all([consumables])
        history.log(
            "CONSUME",
            cid,
            str(stock),
            str(new_stock),
            request.form.get("emp_id", "").strip(),
            "",
            request.form.get("notes", "").strip(),
            "",
            "admin",
            "",
        )
        flash(f"Издадени {qty} од {cid}. Преостанато: {new_stock}.", "success")
    except ValidationError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")
    return redirect(url_for("consumables_view"))


def _parse_seats(raw):
    try:
        val = int(str(raw or "").strip())
    except ValueError:
        raise ValidationError("Бројот на седишта мора да е цел број.")
    if val < 0:
        raise ValidationError("Бројот на седишта не може да е негативен.")
    return val


@app.route("/licenses", methods=["GET", "POST"])
def licenses_view():
    if request.method == "POST":
        lid = request.form.get("LicenseID", "").strip()
        try:
            if not lid:
                raise ValidationError("ID е задолжителен.")
            if licenses.find("LicenseID", lid):
                raise ValidationError(f"{lid} веќе постои.")
            licenses.append_row(
                {
                    "LicenseID": lid,
                    "Software": request.form.get("Software", "").strip(),
                    "LicenseKey": request.form.get("LicenseKey", "").strip(),
                    "Seats": str(_parse_seats(request.form.get("Seats", "1"))),
                    "SeatsUsed": "0",
                    "ExpiryDate": request.form.get("ExpiryDate", "").strip(),
                    "Supplier": request.form.get("Supplier", "").strip(),
                    "Notes": request.form.get("Notes", "").strip(),
                }
            )
            if config.BACKUP_ON_WRITE:
                backup_all([licenses])
            flash(f"Лиценцата {lid} е внесена.", "success")
        except ValidationError as exc:
            flash(f"ГРЕШКА: {exc}", "danger")
        return redirect(url_for("licenses_view"))
    import datetime as _dt

    rows = licenses.records()
    today = _dt.date.today()
    expiring_ids = set()
    for r in rows:
        try:
            exp = _dt.date.fromisoformat((r.get("ExpiryDate") or "").strip()[:10])
        except ValueError:
            continue
        if today <= exp <= today + _dt.timedelta(days=30):
            expiring_ids.add(r.get("LicenseID", ""))
    return render_template("licenses.html", rows=rows, expiring_ids=expiring_ids)


def _license_seat_change(lid, delta, emp_id, action):
    row = licenses.find("LicenseID", lid)
    if row is None:
        raise ValidationError(f"Лиценцата {lid} не постои.")
    seats = _parse_seats(row.get("Seats", "0"))
    used = _parse_seats(row.get("SeatsUsed", "0"))
    new_used = used + delta
    if new_used < 0 or new_used > seats:
        raise ValidationError(f"Недозволено: зафатени {used} од {seats} седишта.")
    licenses.update_where("LicenseID", lid, {"SeatsUsed": str(new_used)})
    if config.BACKUP_ON_WRITE:
        backup_all([licenses])
    history.log(action, lid, str(used), str(new_used), emp_id, "", "", "", "admin", "")
    return new_used


@app.route("/licenses/assign", methods=["POST"])
def licenses_assign():
    try:
        new_used = _license_seat_change(
            request.form.get("license_id", "").strip(),
            1,
            request.form.get("emp_id", "").strip(),
            "LIC_ASSIGN",
        )
        flash(f"Седиште доделено. Зафатени: {new_used}.", "success")
    except ValidationError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")
    return redirect(url_for("licenses_view"))


@app.route("/licenses/revoke", methods=["POST"])
def licenses_revoke():
    try:
        new_used = _license_seat_change(
            request.form.get("license_id", "").strip(),
            -1,
            request.form.get("emp_id", "").strip(),
            "LIC_REVOKE",
        )
        flash(f"Седиште ослободено. Зафатени: {new_used}.", "success")
    except ValidationError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")
    return redirect(url_for("licenses_view"))


@app.route("/contracts", methods=["GET", "POST"])
def contracts_view():
    if request.method == "POST":
        cid = request.form.get("ContractID", "").strip()
        try:
            if not cid:
                raise ValidationError("ID е задолжителен.")
            if contracts.find("ContractID", cid):
                raise ValidationError(f"{cid} веќе постои.")
            contracts.append_row(
                {
                    "ContractID": cid,
                    "Title": request.form.get("Title", "").strip(),
                    "Supplier": request.form.get("Supplier", "").strip(),
                    "ValidUntil": request.form.get("ValidUntil", "").strip(),
                    "Value": request.form.get("Value", "").strip(),
                    "Notes": request.form.get("Notes", "").strip(),
                }
            )
            if config.BACKUP_ON_WRITE:
                backup_all([contracts])
            flash(f"Договорот {cid} е внесен.", "success")
        except ValidationError as exc:
            flash(f"ГРЕШКА: {exc}", "danger")
        return redirect(url_for("contracts_view"))
    import datetime as _dt

    rows = contracts.records()
    today = _dt.date.today()
    expiring_ids = set()
    for r in rows:
        try:
            exp = _dt.date.fromisoformat((r.get("ValidUntil") or "").strip()[:10])
        except ValueError:
            continue
        if today <= exp <= today + _dt.timedelta(days=30):
            expiring_ids.add(r.get("ContractID", ""))
    return render_template("contracts.html", rows=rows, expiring_ids=expiring_ids)


def _parse_day(raw, label):
    import datetime as _dt

    try:
        return _dt.date.fromisoformat((raw or "").strip()[:10])
    except ValueError:
        raise ValidationError(f"Невалиден датум: {label}.")


@app.route("/reservations", methods=["GET", "POST"])
def reservations_view():
    if request.method == "POST":
        try:
            asset_id = request.form.get("AssetID", "").strip()
            if devices.find("AssetID", asset_id) is None:
                raise ValidationError(f"Уредот {asset_id} не постои.")
            start = _parse_day(request.form.get("FromDate", ""), "од")
            end = _parse_day(request.form.get("ToDate", ""), "до")
            if end < start:
                raise ValidationError("Крајот е пред почетокот.")
            for r in reservations.records():
                if r.get("AssetID") != asset_id or r.get("Status") != "active":
                    continue
                try:
                    import datetime as _dt

                    rs = _dt.date.fromisoformat(r.get("FromDate", "")[:10])
                    re_ = _dt.date.fromisoformat(r.get("ToDate", "")[:10])
                except ValueError:
                    continue
                if start <= re_ and rs <= end:
                    raise ValidationError(
                        f"Преклопување со {r.get('ReservationID')} "
                        f"({r.get('FromDate')}–{r.get('ToDate')})."
                    )
            from utils.helpers import next_id as _next_id

            rid = _next_id(reservations, "ReservationID", "R")
            reservations.append_row(
                {
                    "ReservationID": rid,
                    "AssetID": asset_id,
                    "EmployeeID": request.form.get("EmployeeID", "").strip(),
                    "FromDate": start.isoformat(),
                    "ToDate": end.isoformat(),
                    "Status": "active",
                    "Notes": request.form.get("Notes", "").strip(),
                }
            )
            if config.BACKUP_ON_WRITE:
                backup_all([reservations])
            flash(f"Резервацијата {rid} е внесена.", "success")
        except ValidationError as exc:
            flash(f"ГРЕШКА: {exc}", "danger")
        return redirect(url_for("reservations_view"))
    rows = reservations.records()
    return render_template("reservations.html", rows=rows)


@app.route("/reservations/cancel", methods=["POST"])
def reservations_cancel():
    rid = request.form.get("reservation_id", "").strip()
    if reservations.find("ReservationID", rid) is None:
        flash(f"ГРЕШКА: резервацијата {rid} не постои.", "danger")
    else:
        reservations.update_where("ReservationID", rid, {"Status": "cancelled"})
        if config.BACKUP_ON_WRITE:
            backup_all([reservations])
        flash(f"Резервацијата {rid} е откажана.", "success")
    return redirect(url_for("reservations_view"))


@app.route("/requests", methods=["GET", "POST"])
def requests_view():
    if request.method == "POST":
        try:
            need = request.form.get("NeedText", "").strip()
            if not need:
                raise ValidationError("Опишете што ви треба.")
            from utils.helpers import next_id as _next_id

            qid = _next_id(requests, "RequestID", "Q")
            requests.append_row(
                {
                    "RequestID": qid,
                    "EmployeeID": request.form.get("EmployeeID", "").strip(),
                    "NeedText": need,
                    "Status": "open",
                    "Created": stamp().split(" ")[0],
                    "DecidedBy": "",
                }
            )
            if config.BACKUP_ON_WRITE:
                backup_all([requests])
            flash(f"Барањето {qid} е заведено.", "success")
        except ValidationError as exc:
            flash(f"ГРЕШКА: {exc}", "danger")
        return redirect(url_for("requests_view"))
    rows = requests.records()
    return render_template("requests.html", rows=rows)


@app.route("/requests/decide", methods=["POST"])
@roles_required("admin", "magacioner")
def requests_decide():
    qid = request.form.get("request_id", "").strip()
    decision = request.form.get("decision", "").strip()
    try:
        if requests.find("RequestID", qid) is None:
            raise ValidationError(f"Барањето {qid} не постои.")
        if decision not in ("approved", "rejected"):
            raise ValidationError("Невалидна одлука.")
        who = getattr(current_user, "id", "admin") if current_user else "admin"
        requests.update_where(
            "RequestID", qid, {"Status": decision, "DecidedBy": str(who)}
        )
        if config.BACKUP_ON_WRITE:
            backup_all([requests])
        flash(f"Барањето {qid}: {decision}.", "success")
    except ValidationError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")
    return redirect(url_for("requests_view"))


@app.route("/fields", methods=["GET", "POST"])
@roles_required("admin", "magacioner")
def field_defs_view():
    if request.method == "POST":
        action = request.form.get("action", "add")
        try:
            if action == "add":
                name = request.form.get("FieldName", "").strip()
                if not name:
                    raise ValidationError("Името е задолжително.")
                if any(d.get("FieldName") == name for d in field_defs.records()):
                    raise ValidationError(f"Полето {name} веќе постои.")
                from utils.helpers import next_id as _next_id

                fid = _next_id(field_defs, "FieldID", "F")
                field_defs.append_row({"FieldID": fid, "FieldName": name})
                if config.BACKUP_ON_WRITE:
                    backup_all([field_defs])
                flash(f"Полето {name} е додадено.", "success")
            elif action == "delete":
                fid = request.form.get("field_id", "").strip()
                field_defs.replace_all(
                    [d for d in field_defs.records() if d.get("FieldID") != fid]
                )
                field_values.replace_all(
                    [v for v in field_values.records() if v.get("FieldID") != fid]
                )
                if config.BACKUP_ON_WRITE:
                    backup_all([field_defs, field_values])
                flash("Полето е избришано.", "success")
        except ValidationError as exc:
            flash(f"ГРЕШКА: {exc}", "danger")
        return redirect(url_for("field_defs_view"))
    return render_template("fields.html", defs=field_defs.records())


@app.route("/device/<asset_id>/fields", methods=["POST"])
@roles_required("admin", "magacioner")
def device_fields_save(asset_id):
    dev = devices.find("AssetID", asset_id)
    if dev is None:
        abort(404)
    defs = {d.get("FieldID", ""): d for d in field_defs.records()}
    kept = [
        v
        for v in field_values.records()
        if not (v.get("AssetID") == asset_id and v.get("FieldID") in defs)
    ]
    for fid in defs:
        val = request.form.get(f"field_{fid}", "").strip()
        if val:
            kept.append({"AssetID": asset_id, "FieldID": fid, "Value": val})
    field_values.replace_all(kept)
    if config.BACKUP_ON_WRITE:
        backup_all([field_values])
    flash("Дополнителните полиња се зачувани.", "success")
    return redirect(url_for("device_detail", asset_id=asset_id))


@app.route("/health")
def health():
    return {"status": "ok"}, 200


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


@app.route("/api/v1/devices")
def api_v1_devices():
    denied = _require_api_roles("magacioner", "citac")
    if denied is not None:
        return denied
    st = (request.args.get("status") or "").strip()
    tp = (request.args.get("type") or "").strip()
    loc = (request.args.get("location") or "").strip()
    q = (request.args.get("q") or "").strip().lower()
    out = []
    for d in devices.records():
        if st and d.get("Status") != st:
            continue
        if tp and d.get("Type") != tp:
            continue
        if loc and d.get("Location") != loc:
            continue
        if (
            q
            and q
            not in " ".join(
                [
                    d.get("AssetID", ""),
                    d.get("SerialNumber", ""),
                    d.get("Manufacturer", ""),
                    d.get("Model", ""),
                    d.get("EmployeeID", ""),
                ]
            ).lower()
        ):
            continue
        out.append(d)
    return {"results": out, "count": len(out)}


@app.route("/api/v1/devices/<asset_id>")
def api_v1_device_detail(asset_id):
    denied = _require_api_roles("magacioner", "citac")
    if denied is not None:
        return denied
    dev = devices.find("AssetID", asset_id)
    if dev is None:
        from flask import jsonify as _jsonify

        return _jsonify({"error": "not_found"}), 404
    return dev


@app.route("/api/v1/employees")
def api_v1_employees():
    denied = _require_api_roles("magacioner", "citac")
    if denied is not None:
        return denied
    return {"results": employees.records()}


@app.route("/api/v1/checkout", methods=["POST"])
def api_v1_checkout():
    denied = _require_api_roles("magacioner")
    if denied is not None:
        return denied
    data = request.get_json(silent=True) or {}
    try:
        tid, doc = assign_svc.confirm(
            (data.get("asset_id") or "").strip(),
            (data.get("emp_id") or "").strip(),
            (data.get("reason") or "").strip(),
            (data.get("notes") or "").strip(),
            getattr(_api_user(), "id", "api"),
        )
    except ValidationError as exc:
        from flask import jsonify as _jsonify

        return _jsonify({"error": str(exc)}), 422
    return {"transaction_id": tid, "document": doc}, 201


@app.route("/api/v1/checkin", methods=["POST"])
def api_v1_checkin():
    denied = _require_api_roles("magacioner")
    if denied is not None:
        return denied
    data = request.get_json(silent=True) or {}
    try:
        tid, doc = return_svc.confirm(
            (data.get("asset_id") or "").strip(),
            (data.get("emp_id") or "").strip(),
            (data.get("reason") or "").strip(),
            (data.get("condition") or "Good").strip(),
            (data.get("notes") or "").strip(),
            getattr(_api_user(), "id", "api"),
        )
    except ValidationError as exc:
        from flask import jsonify as _jsonify

        return _jsonify({"error": str(exc)}), 422
    return {"transaction_id": tid, "document": doc}, 201


@app.route("/api/v1/history")
def api_v1_history():
    denied = _require_api_roles("magacioner", "citac")
    if denied is not None:
        return denied
    asset_id = (request.args.get("asset_id") or "").strip()
    try:
        limit = min(200, max(1, int(request.args.get("limit", "50"))))
    except ValueError:
        limit = 50
    rows = history.recent(5000)
    if asset_id:
        rows = [h for h in rows if h.get("AssetID") == asset_id]
    return {"results": rows[:limit], "count": min(len(rows), limit)}


@app.route("/api-tokens", methods=["GET", "POST"])
@roles_required("admin")
def api_tokens():
    plain = None
    if request.method == "POST":
        action = request.form.get("action", "create")
        if action == "create":
            owner = request.form.get("username", "").strip()
            if auth_svc.get(owner) is None:
                flash(f"ГРЕШКА: корисникот {owner} не постои.", "danger")
            else:
                plain = token_svc.create(
                    owner,
                    request.form.get("name", "").strip(),
                )
                flash(
                    "Токенот е креиран. Копирајте го сега — нема повторно прикажување.",
                    "success",
                )
        elif action == "revoke":
            try:
                tid = request.form.get("token_id", "").strip()
                rows = token_svc.store.filter_eq("TokenID", tid)
                owner = rows[0].get("UserName", "") if rows else ""
                token_svc.revoke(tid, owner)
                flash("Токенот е отповикан.", "success")
            except ValueError as exc:
                flash(f"ГРЕШКА: {exc}", "danger")
    return render_template(
        "api_tokens.html", tokens=token_svc.store.records(), plain=plain
    )


@app.route("/setup", methods=["GET", "POST"])
def setup():
    if auth_svc.auth_required():
        return redirect(url_for("login"))
    if request.method == "POST":
        try:
            auth_svc.create_user(
                request.form.get("username", ""),
                request.form.get("password", ""),
                role="admin",
            )
            flash("Администраторот е креиран. Најавете се.", "success")
            return redirect(url_for("login"))
        except ValueError as exc:
            flash(f"ГРЕШКА: {exc}", "danger")
    return render_template("setup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = auth_svc.verify(
            request.form.get("username", ""), request.form.get("password", "")
        )
        if user is None:
            flash("ГРЕШКА: погрешно корисничко име или лозинка.", "danger")
        else:
            login_user(AppUser(user))
            log.info("Login user=%s", user.get("UserName", ""))
            nxt = request.args.get("next") or url_for("dashboard")
            return redirect(nxt)
    return render_template("login.html")


@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route("/users", methods=["GET", "POST"])
@roles_required("admin")
def users():
    if request.method == "POST":
        action = request.form.get("action", "create")
        try:
            if action == "create":
                auth_svc.create_user(
                    request.form.get("username", ""),
                    request.form.get("password", ""),
                    request.form.get("role", "magacioner"),
                )
                flash("Корисникот е креиран.", "success")
            elif action == "deactivate":
                auth_svc.set_active(request.form.get("username", ""), False)
            elif action == "activate":
                auth_svc.set_active(request.form.get("username", ""), True)
            elif action == "role":
                auth_svc.set_role(
                    request.form.get("username", ""),
                    request.form.get("role", "citac"),
                )
        except ValueError as exc:
            flash(f"ГРЕШКА: {exc}", "danger")
    return render_template("users.html", users=auth_svc.list_users())


@app.route("/")
def dashboard():
    devs = devices.records()
    active_emps = employees.filter_eq("Active", "YES")
    counts = dict(Counter(r.get("Status", "") for r in devs)) if devs else {}
    monthly = {}
    for h in history.recent(1000):
        month = (h.get("DateTime", "") or "")[:7]
        if month:
            monthly[month] = monthly.get(month, 0) + 1
    warranties = []
    for d in devs:
        days = warranty_days(d.get("WarrantyUntil", ""))
        if days is not None and days <= 90:
            level, text = warranty_level(days)
            warranties.append(
                {
                    "AssetID": d.get("AssetID", ""),
                    "Model": f"{d.get('Manufacturer', '')} {d.get('Model', '')}",
                    "Days": days,
                    "Level": level,
                    "Text": text,
                }
            )
    warranties.sort(key=lambda x: (x["Days"] is None, x["Days"]))
    attention_devs = [
        {
            "AssetID": d.get("AssetID", ""),
            "Model": f"{d.get('Manufacturer', '')} {d.get('Model', '')}",
            "Status": d.get("Status", ""),
            "Holder": d.get("EmployeeID", "") or "—",
        }
        for d in devs
        if d.get("Status") in ("Broken", "Repair", "Lost", "Stolen")
    ]
    stats = {
        "total_devices": len(devs),
        "total_employees": len(active_emps),
        "computers": sum(
            1 for d in devs if d.get("Type", "") in ("Компјутер", "Laptop")
        ),
        "statuses": counts,
        "available": counts.get("Available", 0),
        "assigned": counts.get("Assigned", 0),
        "attention": sum(
            counts.get(s, 0) for s in ("Broken", "Repair", "Lost", "Stolen")
        ),
        "recent": history.recent(8),
        "months": sorted(monthly),
        "mcounts": [monthly[m] for m in sorted(monthly)],
        "warranties": warranties[:8],
        "wcount": len(warranties),
        "attention_devs": attention_devs,
    }
    return render_template("dashboard.html", stats=stats)


def _row(store, col, value):
    rec = store.find(col, value)
    if rec is None:
        abort(404)
    return rec


@app.route("/employees")
def employee_list():
    return render_template("employees.html", employees=employees.records())


@app.route("/employees/new", methods=["GET", "POST"])
def employee_new():
    if request.method == "POST":
        data = {c: request.form.get(c, "").strip() for c in EMP_COLS}
        try:
            if not data["EmployeeID"]:
                raise ValidationError("EmployeeID е задолжителен.")
            if employees.find("EmployeeID", data["EmployeeID"]):
                raise ValidationError(f"Вработениот {data['EmployeeID']} веќе постои.")
            if not data["Active"]:
                data["Active"] = "YES"
            employees.append_row(data)
            if config.BACKUP_ON_WRITE:
                backup_all([employees])
            same_name = [
                e
                for e in employees.records()
                if e.get("EmployeeID") != data["EmployeeID"]
                and (e.get("FirstName", ""), e.get("LastName", ""))
                == (data["FirstName"], data["LastName"])
                and (data["FirstName"] or data["LastName"])
            ]
            if same_name:
                flash(
                    f"ВНИМАНИЕ: можен дупликат — {data['FirstName']} "
                    f"{data['LastName']} веќе постои како "
                    f"{same_name[0].get('EmployeeID', '')}.",
                    "warning",
                )
            else:
                flash(f"Вработениот {data['EmployeeID']} е внесен.", "success")
            return redirect(url_for("employee_detail", emp_id=data["EmployeeID"]))
        except ValidationError as exc:
            flash(f"ГРЕШКА: {exc}", "danger")
    prefill = (request.args.get("prefill", "") or "").strip().split()
    return render_template(
        "employee_new.html",
        first=prefill[0] if len(prefill) > 0 else "",
        last=" ".join(prefill[1:]) if len(prefill) > 1 else "",
    )


@app.route("/employee/<emp_id>")
def employee_detail(emp_id):
    emp = _row(employees, "EmployeeID", emp_id)
    mine = devices.filter_eq("EmployeeID", emp_id)
    hist = history.for_employee(emp_id)
    return render_template("employee.html", emp=emp, devices=mine, hist=hist)


@app.route("/devices/new", methods=["GET", "POST"])
def device_new():
    from utils.validators import ValidationError

    if request.method == "POST":
        data = {c: request.form.get(c, "").strip() for c in DEV_COLS}
        try:
            if not data["AssetID"]:
                raise ValidationError("Asset ID е задолжителен.")
            if devices.find("AssetID", data["AssetID"]):
                raise ValidationError(f"AssetID {data['AssetID']} веќе постои.")
            if data["SerialNumber"]:
                dup = [
                    d
                    for d in devices.records()
                    if d.get("SerialNumber") == data["SerialNumber"]
                ]
                if dup:
                    raise ValidationError(
                        f"Серискиот број веќе постои кај {dup[0]['AssetID']}."
                    )
            if not data["Status"]:
                data["Status"] = "Available"
            devices.append_row(data)
            if config.BACKUP_ON_WRITE:
                backup_all([devices])
            history.log(
                "CREATE",
                data["AssetID"],
                "",
                data["Status"],
                "",
                "",
                "Нов внес",
                "",
                "admin",
                "",
            )
            flash(f"Уредот {data['AssetID']} е внесен.", "success")
            if "add_another" in request.form:
                return redirect(url_for("device_new"))
            return redirect(url_for("device_detail", asset_id=data["AssetID"]))
        except ValidationError as exc:
            flash(f"ГРЕШКА: {exc}", "danger")
        except sqlite3.IntegrityError:
            flash("ГРЕШКА: Asset ID или серискиот број веќе постои.", "danger")
    prefill = {c: "" for c in DEV_COLS}
    src = devices.find("AssetID", (request.args.get("clone", "") or "").strip())
    if src is not None:
        for c in DEV_COLS:
            if c not in ("AssetID", "SerialNumber", "EmployeeID"):
                prefill[c] = src.get(c, "")
        prefill["Status"] = "Available"
    return render_template("device_new.html", prefill=prefill)


@app.route("/devices/bulk", methods=["GET", "POST"])
def device_bulk():
    if request.method == "POST":
        dtype = request.form.get("Type", "Друго").strip() or "Друго"
        shared = {
            "Type": dtype,
            "Manufacturer": request.form.get("Manufacturer", "").strip(),
            "Model": request.form.get("Model", "").strip(),
            "Location": request.form.get("Location", "").strip(),
            "PurchaseDate": request.form.get("PurchaseDate", "").strip(),
            "WarrantyUntil": request.form.get("WarrantyUntil", "").strip(),
            "PurchasePrice": request.form.get("PurchasePrice", "").strip(),
            "Supplier": request.form.get("Supplier", "").strip(),
            "Notes": request.form.get("Notes", "").strip(),
            "Status": "Available",
            "EmployeeID": "",
        }
        prefix = ID_PREFIX.get(dtype, "AST")
        best = 0
        for r in devices.records():
            aid = r.get("AssetID", "")
            if aid.startswith(prefix):
                try:
                    best = max(best, int(aid[len(prefix) :]))
                except ValueError:
                    continue
        created, skipped = [], []
        seen = set()
        for line in (request.form.get("serials", "") or "").splitlines():
            sn = line.strip()
            if not sn or sn in seen:
                continue
            seen.add(sn)
            dup = [d for d in devices.records() if d.get("SerialNumber") == sn]
            if dup:
                skipped.append(sn)
                continue
            best += 1
            aid = f"{prefix}{best:03d}"
            while devices.find("AssetID", aid):
                best += 1
                aid = f"{prefix}{best:03d}"
            data = dict(shared)
            data.update({"AssetID": aid, "SerialNumber": sn})
            try:
                devices.append_row(data)
            except sqlite3.IntegrityError:
                skipped.append(sn)
                continue
            history.log(
                "CREATE", aid, "", "Available", "", "", "Bulk внес", "", "admin", ""
            )
            created.append(aid)
        if config.BACKUP_ON_WRITE:
            backup_all([devices])
        flash(
            f"Создадени {len(created)} уреди"
            + (f" ({', '.join(created)})" if created else "")
            + (
                f". Прескокнати {len(skipped)}: {', '.join(skipped)}."
                if skipped
                else "."
            ),
            "success" if created else "warning",
        )
        return redirect(url_for("device_list"))
    return render_template("device_bulk.html")


@app.route("/devices")
def device_list():
    wf = request.args.get("w", "")
    st = request.args.get("status", "").strip()
    tp = request.args.get("type", "").strip()
    loc = request.args.get("loc", "").strip()
    q = request.args.get("q", "").strip().lower()

    raw_devs = devices.records()
    statuses = sorted({d.get("Status") for d in raw_devs if d.get("Status")})
    types = sorted({d.get("Type") for d in raw_devs if d.get("Type")})
    locations = sorted({d.get("Location") for d in raw_devs if d.get("Location")})

    filtered = []
    for d in raw_devs:
        if st and d.get("Status") != st:
            continue
        if tp and d.get("Type") != tp:
            continue
        if loc and d.get("Location") != loc:
            continue
        if q:
            haystack = " ".join(
                [
                    d.get("AssetID", ""),
                    d.get("SerialNumber", ""),
                    d.get("Manufacturer", ""),
                    d.get("Model", ""),
                    d.get("EmployeeID", ""),
                    d.get("Notes", ""),
                ]
            ).lower()
            if not all(w in haystack for w in q.split()):
                continue
        days = warranty_days(d.get("WarrantyUntil", ""))
        if days is not None:
            level, text = warranty_level(days)
            d["WLevel"], d["WText"] = level, text
        if wf in ("expiring", "expired"):
            if days is None or (
                days >= 0 if wf == "expired" else not (0 <= days <= 90)
            ):
                continue
        filtered.append(d)

    try:
        page = max(1, int(request.args.get("page", "1")))
    except ValueError:
        page = 1
    try:
        per = min(500, max(10, int(request.args.get("per", "50"))))
    except ValueError:
        per = 50
    total = len(filtered)
    total_pages = max(1, (total + per - 1) // per)
    if page > total_pages:
        page = total_pages
    start = (page - 1) * per
    return render_template(
        "devices.html",
        devices=filtered[start : start + per],
        wf=wf,
        st=st,
        tp=tp,
        loc=loc,
        q=q,
        statuses=statuses,
        types=types,
        locations=locations,
        page=page,
        per=per,
        total=total,
        total_pages=total_pages,
    )


@app.route("/device/<asset_id>")
def device_detail(asset_id):
    dev = _row(devices, "AssetID", asset_id)
    emp = None
    if dev.get("EmployeeID"):
        holder = employees.find("EmployeeID", dev["EmployeeID"])
        if holder is not None:
            emp = f"{holder['FirstName']} {holder['LastName']}"
    hist = history.for_asset(asset_id)
    docs = [h for h in hist if h.get("DocumentPath")]
    emails = {}
    for h in hist:
        eid = h.get("EmployeeID", "")
        if eid and eid not in emails:
            holder_rec = employees.find("EmployeeID", eid)
            emails[eid] = holder_rec.get("Email", "") if holder_rec else ""
    status = dev.get("Status", "")
    actions = []
    if status == "Available":
        actions = [("Задолжи", f"/assign?asset={asset_id}", "primary")]
    elif status == "Assigned":
        actions = [
            ("Раздолжи", f"/return?asset={asset_id}", "secondary"),
            (
                "Замени",
                f"/replace?old={asset_id}&emp={dev.get('EmployeeID', '')}",
                "warning",
            ),
            ("Пријави расипан", f"/repair?asset={asset_id}", "danger"),
        ]
    elif status == "Broken":
        actions = [("Испрати на сервис", f"/repair?asset={asset_id}", "warning")]
    elif status in ("Repair", "Repaired"):
        actions = [("Следен сервис-статус", f"/repair?asset={asset_id}", "primary")]
    if status != "Disposed":
        actions.append(("Расход", f"/dispose?asset={asset_id}", "danger"))
    _val_by_field = {
        v.get("FieldID", ""): v.get("Value", "")
        for v in field_values.records()
        if v.get("AssetID") == asset_id
    }
    cfields = [
        {
            "FieldID": d.get("FieldID", ""),
            "FieldName": d.get("FieldName", ""),
            "Value": _val_by_field.get(d.get("FieldID", ""), ""),
        }
        for d in field_defs.records()
    ]
    return render_template(
        "device.html",
        dev=dev,
        emp=emp,
        docs=docs,
        actions=actions,
        hist=hist,
        emails=emails,
        cfields=cfields,
    )


@app.route("/search")
def search():
    q = (request.args.get("q") or "").strip().lower()
    results = {"employees": [], "devices": []}
    if q:
        results["employees"] = [
            r for r in employees.records() if q in " ".join(r.values()).lower()
        ]
        results["devices"] = [
            r for r in devices.records() if q in " ".join(r.values()).lower()
        ]
    return render_template("search.html", q=q, results=results)


def _save_signature(data_url):
    """Decode canvas dataURL into documents/signatures. Never raises."""
    try:
        raw = decode_signature(data_url or "")
        if raw is None:
            return ""
        folder = os.path.join(config.DOCUMENTS_DIR, "signatures")
        os.makedirs(folder, exist_ok=True)
        fname = f"sig_{uuid.uuid4().hex[:8]}.png"
        with open(os.path.join(folder, fname), "wb") as fh:
            fh.write(raw)
        return os.path.join("documents", "signatures", fname)
    except Exception:
        log.exception("Signature save failed")
        return ""


@app.route("/assign", methods=["GET", "POST"])
def assign():
    if request.method == "POST":
        try:
            picked = [a.strip() for a in request.form.getlist("asset_ids") if a.strip()]
            if not picked and request.form.get("asset_id", "").strip():
                picked = [request.form.get("asset_id", "").strip()]
            emp_id = request.form.get("emp_id", "").strip()
            reason = request.form.get("reason", "").strip()
            notes = request.form.get("notes", "").strip()
            sig_rel = _save_signature(request.form.get("signature", ""))
            if len(picked) == 1:
                tid, doc = assign_svc.confirm(
                    picked[0],
                    emp_id,
                    reason,
                    notes,
                    signature_path=sig_rel,
                )
                flash(f"Задолжување {tid} успешно. Документ: {doc}", "success")
                _notify_assignment(emp_id, picked, tid)
                return redirect(url_for("device_detail", asset_id=picked[0]))
            tids, doc = assign_svc.confirm_many(
                picked, emp_id, reason, notes, signature_path=sig_rel
            )
            flash(
                f"Задолжени {len(tids)} уреди ({', '.join(tids)}). Документ: {doc}",
                "success",
            )
            _notify_assignment(emp_id, picked, ", ".join(tids))
            return redirect(url_for("employee_detail", emp_id=emp_id))
        except ValidationError as exc:
            flash(f"ГРЕШКА: {exc}", "danger")
    return render_template(
        "assignment.html",
        employees=employees.records(),
        devices=[d for d in devices.records() if d.get("Status") == "Available"],
        preset_asset=request.args.get("asset", ""),
        preset_emp=request.args.get("emp", ""),
    )


@app.route("/return", methods=["GET", "POST"])
def return_device():
    if request.method == "POST":
        mode = request.form.get("mode", "single")
        try:
            if mode == "bulk":
                emp_id = request.form.get("emp_id", "").strip()
                picked = [
                    a.strip()
                    for a in request.form.getlist("bulk_asset_ids")
                    if a.strip()
                ]
                if not picked:
                    raise ValidationError("Изберете барем еден уред за враќање.")
                tids, doc = return_svc.confirm_many(
                    picked,
                    emp_id,
                    request.form.get("reason", "").strip()
                    or "Раздолжување при заминување",
                    request.form.get("condition", "Good").strip(),
                    request.form.get("notes", "").strip(),
                )
                flash(
                    f"Успешно раздолжени {len(tids)} уреди за {emp_id} ({', '.join(tids)}). Документ: {doc}",
                    "success",
                )
                _notify_return(emp_id, picked, ", ".join(tids))
                return redirect(url_for("employee_detail", emp_id=emp_id))
            else:
                asset_id = request.form.get("asset_id", "").strip()
                emp_id = request.form.get("emp_id", "").strip()
                if not emp_id:
                    dev = devices.find("AssetID", asset_id)
                    if dev is not None:
                        emp_id = dev.get("EmployeeID", "")
                tid, doc = return_svc.confirm(
                    asset_id,
                    emp_id,
                    request.form.get("reason", "").strip(),
                    request.form.get("condition", "Good").strip(),
                    request.form.get("notes", "").strip(),
                )
                reason = request.form.get("reason", "")
                flash(f"Раздолжување {tid} успешно. Документ: {doc}", "success")
                _notify_return(emp_id, [asset_id], tid)
                if reason == "Расипан – не се поправа":
                    flash("Уредот е расипан: следен чекор е расход.", "warning")
                    return redirect(url_for("dispose") + f"?asset={asset_id}")
                if reason == "Расипан – на сервис":
                    return redirect(url_for("repair") + f"?asset={asset_id}")
                return redirect(url_for("device_detail", asset_id=asset_id))
        except ValidationError as exc:
            flash(f"ГРЕШКА: {exc}", "danger")
    return render_template(
        "return.html",
        employees=employees.records(),
        devices=[
            d
            for d in devices.records()
            if d.get("Status")
            not in ("Available", "Disposed", "Lost", "Stolen", "Repair")
        ],
        preset_asset=request.args.get("asset", ""),
        preset_emp=request.args.get("emp", ""),
    )


@app.route("/history")
def history_view():
    try:
        page = max(1, int(request.args.get("page", "1")))
    except ValueError:
        page = 1
    try:
        per = min(200, max(20, int(request.args.get("per", "50"))))
    except ValueError:
        per = 50
    all_rows = history.recent(5000)
    total = len(all_rows)
    total_pages = max(1, (total + per - 1) // per)
    if page > total_pages:
        page = total_pages
    start = (page - 1) * per
    rows = all_rows[start : start + per]
    emails = {}
    for h in rows:
        eid = h.get("EmployeeID", "")
        if eid and eid not in emails:
            holder_rec = employees.find("EmployeeID", eid)
            emails[eid] = holder_rec.get("Email", "") if holder_rec else ""
    return render_template(
        "history.html",
        rows=rows,
        emails=emails,
        page=page,
        per=per,
        total=total,
        total_pages=total_pages,
    )


@app.route("/doc/<path:rel>")
def download_doc(rel):
    docs_base = os.path.abspath(config.DOCUMENTS_DIR)
    root_base = os.path.abspath(config.BASE_DIR)
    clean = (rel or "").lstrip("/\\")
    full = os.path.abspath(os.path.join(root_base, clean))
    if os.path.commonpath([docs_base, full]) != docs_base:
        abort(404)
    if not os.path.isfile(full):
        abort(404)
    return send_file(full)


@app.route("/pdf/<path:rel>")
def download_pdf(rel):
    import subprocess

    docs_base = os.path.abspath(config.DOCUMENTS_DIR)
    root_base = os.path.abspath(config.BASE_DIR)
    clean = (rel or "").lstrip("/\\")
    # only .docx inside documents/ can be converted
    if not clean.lower().endswith(".docx"):
        abort(404)
    full = os.path.abspath(os.path.join(root_base, clean))
    if os.path.commonpath([docs_base, full]) != docs_base:
        abort(404)
    if not os.path.isfile(full):
        abort(404)
    pdf = os.path.splitext(full)[0] + ".pdf"
    if not os.path.exists(pdf) or (os.path.getmtime(full) > os.path.getmtime(pdf)):
        outdir = os.path.dirname(full)
        proc = subprocess.run(
            ["soffice", "--headless", "--convert-to", "pdf", "--outdir", outdir, full],
            capture_output=True,
            timeout=120,
        )
        if proc.returncode != 0 or not os.path.exists(pdf):
            log.error("PDF convert failed: %s", proc.stderr.decode()[-500:])
            abort(500)
    return send_file(pdf)


@app.route("/replace", methods=["GET", "POST"])
def replace():
    if request.method == "POST":
        try:
            tid, doc = replace_svc.confirm(
                request.form.get("old_id", "").strip(),
                request.form.get("new_id", "").strip(),
                request.form.get("emp_id", "").strip(),
                request.form.get("reason", "").strip(),
                request.form.get("notes", "").strip(),
                "admin",
                request.form.get("old_condition", "Available").strip(),
            )
            flash(f"Замена {tid} успешна. Документ: {doc}", "success")
            return redirect(
                url_for("device_detail", asset_id=request.form.get("new_id"))
            )
        except ValidationError as exc:
            flash(f"ГРЕШКА: {exc}", "danger")
    return render_template(
        "replacement.html",
        employees=employees.records(),
        assigned=[d for d in devices.records() if d.get("Status") == "Assigned"],
        available=[d for d in devices.records() if d.get("Status") == "Available"],
        preset_old=request.args.get("old", ""),
        preset_emp=request.args.get("emp", ""),
    )


@app.route("/repair", methods=["GET", "POST"])
def repair():
    if request.method == "POST":
        action = request.form.get("action", "report")
        asset = request.form.get("asset_id", "").strip()
        try:
            if action == "report":
                tid = repair_svc.report_broken(
                    asset,
                    request.form.get("problem", "").strip(),
                    request.form.get("notes", "").strip(),
                    "admin",
                    request.form.get("emp_id", "").strip(),
                )
            elif action == "unrepairable":
                tid = repair_close_svc.mark_unrepairable(
                    asset,
                    request.form.get("reason", "Не се поправа").strip(),
                    request.form.get("notes", "").strip(),
                    "admin",
                )
                flash(f"Уредот {asset} е расходуван како непоправлив.", "warning")
                return redirect(url_for("device_detail", asset_id=asset))
            else:
                return_to_emp = "return_to_emp" in request.form
                tid, _ = repair_svc.advance(
                    asset,
                    request.form.get("provider", "").strip(),
                    request.form.get("notes", "").strip(),
                    "admin",
                    return_to_emp=return_to_emp,
                )
            flash(f"Сервис операција {tid} успешна.", "success")
            return redirect(url_for("device_detail", asset_id=asset))
        except ValidationError as exc:
            flash(f"ГРЕШКА: {exc}", "danger")
    return render_template(
        "repair.html",
        devices=devices.records(),
        employees=employees.records(),
        preset_asset=request.args.get("asset", ""),
    )


@app.route("/dashboard")
def dashboard_alias():
    return redirect(url_for("dashboard"))


@app.route("/reports")
def reports():

    devs = devices.records()
    by = lambda key: dict(Counter(r.get(key, "") or "—" for r in devs))
    hist = history.recent(1000)
    monthly = Counter()
    for h in hist:
        if h.get("Action") in ("REPAIR_REPAIR", "REPLACE_IN", "DISPOSE"):
            monthly[h.get("DateTime", "")[:7]] += 1
    if request.args.get("export") == "devices":
        import csv
        import io

        def _safe(v):
            s = str(v or "")
            if s[:1] in ("=", "+", "-", "@", "\t", "\r"):
                s = "'" + s
            return s

        buf = io.StringIO()
        w = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
        w.writerow(
            [
                "AssetID",
                "Type",
                "Manufacturer",
                "Model",
                "SerialNumber",
                "Status",
                "EmployeeID",
                "Location",
                "PurchasePrice",
                "Supplier",
            ]
        )
        for r in devs:
            w.writerow(
                _safe(r.get(c, ""))
                for c in [
                    "AssetID",
                    "Type",
                    "Manufacturer",
                    "Model",
                    "SerialNumber",
                    "Status",
                    "EmployeeID",
                    "Location",
                    "PurchasePrice",
                    "Supplier",
                ]
            )
        return app.response_class(
            buf.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment;filename=devices.csv"},
        )
    if request.args.get("export") == "employees":
        import csv
        import io

        def _safe2(v):
            s = str(v or "")
            if s[:1] in ("=", "+", "-", "@", "\t", "\r"):
                s = "'" + s
            return s

        emps = employees.records()
        buf = io.StringIO()
        w = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
        w.writerow(EMP_COLS)
        for r in emps:
            w.writerow(_safe2(r.get(c, "")) for c in EMP_COLS)
        return app.response_class(
            buf.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment;filename=employees.csv"},
        )
    return render_template(
        "reports.html",
        by_status=by("Status"),
        by_type=by("Type"),
        by_mfr=by("Manufacturer"),
        by_loc=by("Location"),
        by_emp=by("EmployeeID"),
        monthly=dict(sorted(monthly.items())),
    )


@app.route("/import", methods=["GET", "POST"])
def import_bulk():
    from services.schemas import DEV_COLS as _DC, EMP_COLS as _EC
    from services.schemas import OPTIONAL_DEV_COLS as _OPT
    import io
    import pandas as pd

    report = None
    if request.method == "POST":
        kind = request.form.get("kind", "devices")
        file = request.files.get("file")
        if not file or not file.filename:
            flash("ГРЕШКА: избери CSV фајл.", "danger")
        else:
            try:
                ext = (
                    file.filename.rsplit(".", 1)[-1] if "." in file.filename else ""
                ).lower()
                if ext != "csv":
                    raise ValueError("Дозволени се само .csv фајлови.")
                df = pd.read_csv(io.BytesIO(file.read()), dtype=str).fillna("")
                cols = list(_DC) if kind == "devices" else list(_EC)
                optional = set(_OPT) if kind == "devices" else set()
                missing = [c for c in cols if c not in df.columns and c not in optional]
                if missing:
                    raise ValueError(f"Недостасуваат колони: {missing}")
                store = devices if kind == "devices" else employees
                key = "AssetID" if kind == "devices" else "EmployeeID"
                seen = {r.get(key) for r in store.records()}
                dup_file = df[df.duplicated(subset=[key], keep=False)][key].tolist()
                dup_base = [v for v in df[key].tolist() if v in seen]
                serials = set()
                dup_sn = []
                if kind == "devices":
                    for v in df["SerialNumber"].tolist():
                        if v and v in serials:
                            dup_sn.append(v)
                        serials.add(v)
                    base_sn = {r.get("SerialNumber") for r in store.records()}
                    dup_sn += [
                        v for v in df["SerialNumber"].tolist() if v and v in base_sn
                    ]
                errors = []
                if dup_file:
                    errors.append(
                        f"Дупликати во фајлот: {sorted(str(v) for v in set(dup_file) if v)}"
                    )
                if dup_base:
                    errors.append(
                        f"Веќе постојат: {sorted(str(v) for v in set(dup_base) if v)}"
                    )
                if dup_sn:
                    errors.append(
                        f"Дупли сериски: {sorted(str(v) for v in set(dup_sn) if v)}"
                    )
                valid_status = {
                    "Available",
                    "Assigned",
                    "Broken",
                    "Repair",
                    "Repaired",
                    "Disposed",
                    "Lost",
                    "Stolen",
                }
                if kind == "devices" and "Status" in df.columns:
                    bad_status = sorted(
                        {
                            str(v)
                            for v in df["Status"].tolist()
                            if str(v) not in valid_status
                        }
                    )
                    if bad_status:
                        errors.append(f"Непознат статус: {bad_status}")
                if errors:
                    report = {"ok": 0, "errors": errors}
                else:
                    from services.db_service import db_transaction

                    rows = [
                        {c: str(df.at[i, c]) if c in df.columns else "" for c in cols}
                        for i in df.index
                    ]
                    db_path = getattr(store, "db_path", None)
                    if db_path:
                        with db_transaction(db_path) as con:
                            for row in rows:
                                store.append_row(row, con=con)
                                if kind == "devices":
                                    history.log(
                                        "IMPORT",
                                        row.get("AssetID", ""),
                                        "",
                                        row.get("Status", ""),
                                        row.get("EmployeeID", ""),
                                        "",
                                        "Bulk import",
                                        "",
                                        "admin",
                                        "",
                                        con=con,
                                    )
                    else:
                        for row in rows:
                            store.append_row(row)
                    if config.BACKUP_ON_WRITE:
                        backup_all([store])
                    report = {"ok": len(rows), "errors": []}
            except (ValueError, KeyError) as exc:
                flash(f"ГРЕШКА: {exc}", "danger")
            except Exception as exc:
                # Import boundary: user file + bulk write can fail mid-way
                # (transaction rolls back); present clean failure, keep traceback in log.
                log.exception("Import failed")
                flash(f"ГРЕШКА при увоз: {exc}", "danger")
                report = {"ok": 0, "errors": [str(exc)]}
    return render_template("import.html", report=report)


@app.route("/quick-return")
def quick_return():
    q = (request.args.get("q") or "").strip()
    found, holder = None, None
    if q:
        dev = devices.find("AssetID", q)
        if dev is None:
            dev = devices.find("SerialNumber", q)
        if dev is None:
            ql = q.lower()
            for r in devices.records():
                hay = " ".join(
                    [
                        r.get("AssetID", ""),
                        r.get("SerialNumber", ""),
                        r.get("Manufacturer", ""),
                        r.get("Model", ""),
                    ]
                )
                if ql in hay.lower():
                    dev = r
                    break
        if dev is not None:
            found = dev
            if dev.get("EmployeeID"):
                holder = employees.find("EmployeeID", dev["EmployeeID"])
    return render_template(
        "quick_return.html",
        q=q,
        found=found,
        holder=holder,
        devices=devices.records(),
        scan=request.args.get("scan") == "1",
    )


@app.route("/dispose", methods=["GET", "POST"])
def dispose():
    if request.method == "POST":
        try:
            picked = [a.strip() for a in request.form.getlist("asset_ids") if a.strip()]
            if not picked and request.form.get("asset_id", "").strip():
                picked = [request.form.get("asset_id", "").strip()]
            reason = request.form.get("reason", "").strip()
            method = request.form.get("method", "").strip()
            notes = request.form.get("notes", "").strip()
            if len(picked) == 1:
                tid, doc = dispose_svc.confirm(picked[0], reason, method, notes)
                flash(f"Расход {tid} успешен. Документ: {doc}", "success")
                return redirect(url_for("device_detail", asset_id=picked[0]))
            tids, doc = dispose_svc.confirm_many(picked, reason, method, notes)
            flash(
                f"Расходувани {len(tids)} уреди ({', '.join(tids)}). Документ: {doc}",
                "success",
            )
            return redirect(url_for("reports"))
        except ValidationError as exc:
            flash(f"ГРЕШКА: {exc}", "danger")
    return render_template(
        "dispose.html",
        devices=[d for d in devices.records() if d.get("Status") != "Disposed"],
        employees=employees.records(),
    )


def _load_packages():

    path = os.path.join(config.DATA_DIR, "Packages.json")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


@app.route("/packages")
def packages():
    return render_template("packages.html", packages=_load_packages())


@app.route("/package/<pkg_id>", methods=["GET", "POST"])
def package_assign(pkg_id):
    pkgs = {p["id"]: p for p in _load_packages()}
    pkg = pkgs.get(pkg_id)
    if pkg is None:
        abort(404)
    devs = devices.records()
    if request.method == "POST":
        emp_id = request.form.get("emp_id", "").strip()
        picked = [a.strip() for a in request.form.getlist("asset_ids") if a.strip()]
        try:
            if len(picked) <= 1 and picked:
                tid, doc = assign_svc.confirm(
                    picked[0], emp_id, f"Пакет: {pkg['name']}", ""
                )
            else:
                tids, doc = assign_svc.confirm_many(
                    picked, emp_id, f"Пакет: {pkg['name']}", ""
                )
                tid = ",".join(tids)
            flash(f"Пакет доделен ({tid}). Документ: {doc}", "success")
            return redirect(url_for("employee_detail", emp_id=emp_id))
        except ValidationError as exc:
            flash(f"ГРЕШКА: {exc}", "danger")
    pool = [d for d in devs if d.get("Status") == "Available"]
    suggested = []
    for want in pkg.get("types", []):
        for d in pool:
            if d["AssetID"] not in suggested and d.get("Type") == want:
                suggested.append(d["AssetID"])
                break
    return render_template(
        "package.html",
        pkg=pkg,
        employees=employees.records(),
        available=pool,
        suggested=suggested,
    )


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


@app.route("/departments")
def department_list():
    emps = employees.records()
    devs = devices.records()
    names = sorted({e.get("Department", "") for e in emps if e.get("Department")})
    cards = []
    for name in names:
        members = [e for e in emps if e.get("Department") == name]
        ids = {e["EmployeeID"] for e in members}
        mine = [d for d in devs if d.get("EmployeeID") in ids]
        cards.append(
            {
                "name": name,
                "people": len(members),
                "devices": len(mine),
                "assigned": sum(1 for d in mine if d.get("Status") == "Assigned"),
            }
        )
    return render_template("departments.html", cards=cards)


@app.route("/department/<name>")
def department_detail(name):
    emps = employees.records()
    members = [e for e in emps if e.get("Department") == name]
    if not members:
        abort(404)
    devs = devices.records()
    ids = {e["EmployeeID"] for e in members}
    mine = [d for d in devs if d.get("EmployeeID") in ids]
    for d in mine:
        holder = employees.find("EmployeeID", d.get("EmployeeID", ""))
        d["HolderName"] = (
            f"{holder['FirstName']} {holder['LastName']}" if holder else ""
        )
        days = warranty_days(d.get("WarrantyUntil", ""))
        level, text = warranty_level(days)
        d["WLevel"], d["WText"] = level, text
    return render_template("department.html", name=name, members=members, devices=mine)


@app.route("/locations")
def location_list():
    emps = employees.records()
    devs = devices.records()
    names = sorted(
        {e.get("Location", "") for e in emps if e.get("Location")}
        | {d.get("Location", "") for d in devs if d.get("Location")}
    )
    cards = []
    for name in names:
        members = [e for e in emps if e.get("Location") == name]
        mine = [d for d in devs if d.get("Location") == name]
        cards.append(
            {
                "name": name,
                "people": len(members),
                "devices": len(mine),
                "assigned": sum(1 for d in mine if d.get("Status") == "Assigned"),
            }
        )
    return render_template("locations.html", cards=cards)


@app.route("/location/<name>")
def location_detail(name):
    emps = employees.records()
    devs = devices.records()
    members = [e for e in emps if e.get("Location") == name]
    mine = [d for d in devs if d.get("Location") == name]
    if not members and not mine:
        abort(404)
    for d in mine:
        holder = employees.find("EmployeeID", d.get("EmployeeID", ""))
        d["HolderName"] = (
            f"{holder['FirstName']} {holder['LastName']}" if holder else "—"
        )
        days = warranty_days(d.get("WarrantyUntil", ""))
        level, text = warranty_level(days)
        d["WLevel"], d["WText"] = level, text
    return render_template("location.html", name=name, members=members, devices=mine)


@app.route("/popis", methods=["GET", "POST"])
def popis_start():
    emps = employees.records()
    devs = devices.records()
    locs = sorted({d.get("Location", "") for d in devs if d.get("Location")})
    deps = sorted({e.get("Department", "") for e in emps if e.get("Department")})
    if request.method == "POST":
        scope = request.form.get("scope", "location")
        name = request.form.get("name", "").strip()
        if scope == "location":
            expected = [d["AssetID"] for d in devs if d.get("Location") == name]
        else:
            ids = {e["EmployeeID"] for e in emps if e.get("Department") == name}
            expected = [d["AssetID"] for d in devs if d.get("EmployeeID") in ids]
        if not expected:
            flash("ГРЕШКА: нема уреди за тој опсег.", "danger")
        else:
            pid = popis_svc.start(scope, name, expected)
            return redirect(url_for("popis_detail", pid=pid))
    popisi = []
    for rec in popis_svc.store.records():
        try:
            expected_ids = json.loads(rec.get("Expected") or "[]")
            found_ids = json.loads(rec.get("Found") or "[]")
        except (ValueError, TypeError):
            expected_ids, found_ids = [], []
        popisi.append(
            {
                "id": rec.get("PopisID", ""),
                "scope": rec.get("Scope", ""),
                "name": rec.get("Name", ""),
                "status": rec.get("Status", ""),
                "found": len(found_ids),
                "total": len(expected_ids),
                "doc": rec.get("DocumentPath", ""),
            }
        )
    popisi.sort(key=lambda r: r["status"] != "OPEN")
    return render_template("popis.html", locs=locs, deps=deps, popisi=popisi)


@app.route("/popis/<pid>", methods=["GET", "POST"])
def popis_detail(pid):
    from services.document_service import fill_template, mk_date

    rec = popis_svc.get(pid)
    if rec is None:
        abort(404)
    if request.method == "POST":
        if "scan" in request.form:
            code = request.form.get("code", "").strip()
            dev = devices.find("AssetID", code)
            if dev is None:
                for r in devices.records():
                    if r.get("SerialNumber") == code:
                        dev = r
                        break
            if dev is None:
                flash(f"ГРЕШКА: {code} не постои.", "danger")
            else:
                res = popis_svc.scan(pid, dev["AssetID"])
                if res is True:
                    flash(f"✔ {dev['AssetID']} евидентиран.", "success")
                elif res is False:
                    flash(f"⚠ {dev['AssetID']} не припаѓа на овој попис.", "warning")
            return redirect(url_for("popis_detail", pid=pid))
        result = popis_svc.finish(pid)
        if result is None:
            abort(404)
        missing = result["missing"]
        scope_name = rec["Scope"] or ""
        rec_name = rec["Name"] or ""
        doc_rel = fill_template(
            "Popis_Template.docx",
            {
                "«ОПФАТ»": f"{scope_name}: {rec_name}",
                "«ДАТУМ»": mk_date(),
                "«ОЧЕКУВАНИ»": str(len(result["expected"])),
                "«НАЈДЕНИ»": str(len(result["found"])),
                "«НЕДОСТАСУВААТ»": ", ".join(missing) if missing else "—",
            },
            f"Popis_{pid}.docx",
            "popis",
        )
        popis_svc.finish(pid, doc_rel)
        for aid in missing:
            dev = devices.find("AssetID", aid)
            history.log(
                "POPIS_MISSING",
                aid,
                dev.get("Status", "") if dev else "",
                dev.get("Status", "") if dev else "",
                dev.get("EmployeeID", "") if dev else "",
                "",
                f"Попис {pid}",
                "",
                "admin",
                doc_rel,
            )
        flash(
            f"Попис {pid} завршен. Недостасуваат: {len(missing)}.",
            "success" if not missing else "warning",
        )
        return redirect(url_for("popis_detail", pid=pid))
    rec2 = popis_svc.get(pid)
    if rec2 is None:
        abort(404)
    items = []
    for aid in rec2["ExpectedIDs"]:
        dev = devices.find("AssetID", aid)
        items.append(
            {
                "AssetID": aid,
                "Model": f"{dev.get('Manufacturer', '')} {dev.get('Model', '')}"
                if dev
                else "",
                "Found": aid in rec2["FoundIDs"],
            }
        )
    return render_template("popis_detail.html", rec=rec2, items=items)


@app.route("/api/search")
def api_search():

    t0 = time.time()
    q = (request.args.get("q") or "").strip().lower()
    out = []
    if len(q) >= 2:
        words = q.split()
        for d in devices.records():
            hay = " ".join(
                [
                    d.get("AssetID", ""),
                    d.get("SerialNumber", ""),
                    d.get("Manufacturer", ""),
                    d.get("Model", ""),
                    d.get("Type", ""),
                    d.get("Status", ""),
                    d.get("EmployeeID", ""),
                ]
            ).lower()
            if all(w in hay for w in words):
                out.append(
                    {
                        "kind": "device",
                        "id": d.get("AssetID", ""),
                        "title": f"{d.get('AssetID', '')} "
                        f"{d.get('Manufacturer', '')} "
                        f"{d.get('Model', '')}",
                        "sub": f"{d.get('SerialNumber', '')} | {d.get('Status', '')}",
                        "url": f"/device/{d.get('AssetID', '')}",
                    }
                )
                if len(out) >= 12:
                    break
        for e in employees.records():
            hay = " ".join(
                [
                    e.get("EmployeeID", ""),
                    e.get("FirstName", ""),
                    e.get("LastName", ""),
                    e.get("UserName", ""),
                    e.get("Email", ""),
                    e.get("Department", ""),
                ]
            ).lower()
            if all(w in hay for w in words):
                out.append(
                    {
                        "kind": "employee",
                        "id": e.get("EmployeeID", ""),
                        "title": f"{e.get('FirstName', '')} {e.get('LastName', '')}",
                        "sub": f"{e.get('EmployeeID', '')} | {e.get('Department', '')}",
                        "url": f"/employee/{e.get('EmployeeID', '')}",
                    }
                )
                if len(out) >= 20:
                    break
    ms = round((time.time() - t0) * 1000)
    return {"results": out, "ms": ms}


ID_PREFIX = {
    "Laptop": "LAP",
    "Компјутер": "PC",
    "Монитор": "MON",
    "Печатач": "PRN",
    "Телефон": "TEL",
    "Таблет": "TAB",
    "Друго": "AST",
}


@app.route("/api/next-id")
def api_next_id():
    dtype = request.args.get("type", "Друго")
    prefix = ID_PREFIX.get(dtype, "AST")
    best = 0
    for r in devices.records():
        aid = r.get("AssetID", "")
        if aid.startswith(prefix):
            try:
                best = max(best, int(aid[len(prefix) :]))
            except ValueError:
                continue
    return {"next_id": f"{prefix}{best + 1:03d}"}


@app.route("/api/check-serial")
def api_check_serial():
    sn = (request.args.get("q") or "").strip()
    if not sn:
        return {"exists": False}
    for r in devices.records():
        if r.get("SerialNumber") == sn:
            return {"exists": True, "asset": r.get("AssetID", "")}
    return {"exists": False}


@app.route("/api/check-asset")
def api_check_asset():
    aid = (request.args.get("q") or "").strip()
    if not aid:
        return {"exists": False}
    for r in devices.records():
        if r.get("AssetID") == aid:
            return {
                "exists": True,
                "info": f"{r.get('Manufacturer', '')} "
                f"{r.get('Model', '')} | SN: "
                f"{r.get('SerialNumber', '')} | "
                f"{r.get('Status', '')}",
            }
    return {"exists": False}


@app.route("/api/values")
def api_values():
    fields = ["Manufacturer", "Model", "Location"]
    out = {}
    for field in fields:
        seen = []
        for r in devices.records():
            val = r.get(field, "")
            if val and val not in seen:
                seen.append(val)
        out[field] = sorted(seen)
    for field in ["Department", "Organization", "Location"]:
        seen = []
        for r in employees.records():
            val = r.get(field, "")
            if val and val not in seen:
                seen.append(val)
        if field == "Location":
            out[field] = sorted(set(out[field]) | set(seen))
        else:
            out[field] = sorted(seen)
    return out


@app.errorhandler(500)
def internal_error(exc):
    """Boundary handler: log traceback with reference, render friendly page."""
    ref = uuid.uuid4().hex[:8]
    log.exception("Unhandled error ref=%s path=%s", ref, request.path)
    return render_template("500.html", ref=ref), 500


if __name__ == "__main__":
    log.info("ServiceDesk starting")
    port = int(os.environ.get("SERVICEDESK_PORT", "5000"))
    app.run(host=config.HOST, port=port, debug=False)
