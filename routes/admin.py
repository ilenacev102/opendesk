"""Admin + auth routes (Flask Blueprint).

Shared app-owned names (stores, services) are imported lazily INSIDE each
view function, so they always resolve against the live ``app`` module object.
That keeps test monkeypatching of ``app`` attributes working. (Module-level
``__getattr__`` delegation was tried first and REJECTED: CPython LOAD_GLOBAL
inside function bodies never consults it, so bare globals stayed undefined.)
Flask names are plain top-level imports (no cycle possible).
"""

from flask import Blueprint, flash, redirect, render_template, request, url_for

bp = Blueprint("admin", __name__)

log = __import__("logging").getLogger("servicedesk")


def _admin_only(fn):
    from functools import wraps

    @wraps(fn)
    def wrapper(*args, **kwargs):
        import app as _runtime_app

        return _runtime_app.roles_required("admin")(fn)(*args, **kwargs)

    return wrapper


@bp.route("/api-tokens", methods=["GET", "POST"])
@_admin_only
def api_tokens():
    from app import auth_svc, token_svc

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


@bp.route("/setup", methods=["GET", "POST"])
def setup():
    from app import auth_svc

    if auth_svc.auth_required():
        return redirect(url_for("admin.login"))
    if request.method == "POST":
        try:
            auth_svc.create_user(
                request.form.get("username", ""),
                request.form.get("password", ""),
                role="admin",
            )
            flash("Администраторот е креиран. Најавете се.", "success")
            return redirect(url_for("admin.login"))
        except ValueError as exc:
            flash(f"ГРЕШКА: {exc}", "danger")
    return render_template("setup.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    from app import AppUser, auth_svc, login_user

    if request.method == "POST":
        user = auth_svc.verify(
            request.form.get("username", ""), request.form.get("password", "")
        )
        if user is None:
            flash("ГРЕШКА: погрешно корисничко име или лозинка.", "danger")
        else:
            login_user(AppUser(user))
            log.info("Login user=%s", user.get("UserName", ""))
            nxt = request.args.get("next") or url_for("system.dashboard")
            return redirect(nxt)
    from services import oidc_service as oidc

    return render_template(
        "login.html",
        sso_enabled=oidc.configured(),
        sso_name=oidc.provider_name(),
    )


@bp.route("/logout")
def logout():
    from app import logout_user

    logout_user()
    return redirect(url_for("admin.login"))


def _who():
    from flask_login import current_user as _cu

    return str(getattr(_cu, "id", "admin")) if _cu else "admin"


@bp.route("/users/sync", methods=["GET", "POST"])
@_admin_only
def users_sync():
    import config
    from app import backup_all, employees, history, ldapmap
    from services.ldap_service import LdapError, LdapService, configured

    db_path = getattr(ldapmap, "db_path", None)
    svc = LdapService(employees, ldapmap, history, db_path=db_path)
    if not configured():
        return render_template("users_sync.html", preview=None, hint=True)
    if request.method == "POST" and request.form.get("confirm") == "1":
        try:
            users = svc.fetch_users()
            result = svc.sync(users, dry_run=False, performed_by=_who())
        except LdapError as exc:
            flash(f"ГРЕШКА: {exc}", "danger")
            return redirect(url_for("admin.users_sync"))
        if config.BACKUP_ON_WRITE:
            backup_all([ldapmap])
        flash(
            f"LDAP синхронизација: {result['matched']} поврзани, "
            f"{result['staged']} за евиденција.",
            "success",
        )
        return redirect(url_for("admin.users"))
    try:
        users = svc.fetch_users()
    except LdapError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")
        return render_template("users_sync.html", preview=None, hint=False)
    return render_template("users_sync.html", preview=svc.reconcile(users), hint=False)


@bp.route("/users", methods=["GET", "POST"])
@_admin_only
def users():
    from app import auth_svc

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


@bp.route("/login/sso")
def sso_login():
    import secrets

    from flask import session

    from services import oidc_service as oidc
    from services.oidc_service import OidcError

    if not oidc.configured():
        flash("SSO не е конфигуриран.", "danger")
        return redirect(url_for("admin.login"))
    state = secrets.token_urlsafe(16)
    session["sso_state"] = state
    try:
        target = oidc.authorize_url(
            None, url_for("admin.sso_callback", _external=True), state
        )
    except OidcError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")
        return redirect(url_for("admin.login"))
    return redirect(target["url"])


@bp.route("/login/sso/callback")
def sso_callback():
    from flask import session

    from app import AppUser, auth_svc, login_user
    from services import oidc_service as oidc
    from services.auth_service import ROLES
    from services.oidc_service import OidcError

    if not oidc.configured():
        return redirect(url_for("admin.login"))
    code = request.args.get("code", "")
    state = request.args.get("state", "")
    session_state = session.pop("sso_state", "")
    try:
        claims = oidc.handle_callback(None, code, state, session_state)
    except OidcError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")
        return redirect(url_for("admin.login"))
    subject = claims.get("subject", "")
    email = (claims.get("email", "") or "").strip().lower()
    username = (claims.get("username", "") or "").strip()
    if not username:
        flash("ГРЕШКА: SSO одговорот нема корисничко име.", "danger")
        return redirect(url_for("admin.login"))
    user = None
    if subject:
        for cand in auth_svc.list_users():
            if (cand.get("OIDCSubject", "") or "") == subject:
                user = cand
                break
    if user is None and email:
        for cand in auth_svc.list_users():
            if (cand.get("Email", "") or "").strip().lower() == email:
                user = cand
                auth_svc.store.update_where(
                    "UserName", cand["UserName"], {"OIDCSubject": subject}
                )
                break
    if user is None:
        if auth_svc.get(username) is not None:
            username = f"{username}-{subject[:6]}"
        role = oidc.default_role()
        if role not in ROLES:
            role = "citac"
        try:
            user = auth_svc.create_sso_user(username, email, subject, role)
        except ValueError as exc:
            flash(f"ГРЕШКА: {exc}", "danger")
            return redirect(url_for("admin.login"))
    login_user(AppUser(user))
    log.info("SSO login user=%s", user.get("UserName", ""))
    return redirect(url_for("system.dashboard"))
